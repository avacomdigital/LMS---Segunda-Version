using System.Net;
using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// MOD-019 en el cliente: el registro local (JSON Lines, saneamiento, rotación, cola de pendientes), la cabecera de aparato y la correlación
/// en cada petición, los clientes de /api/auditoria/ y /api/logs/, y el entregador de logs al nodo. Cada prueba escribe en una carpeta
/// temporal propia (AVACOM_LMS_DIR_LOGS), nunca en el registro real del equipo.
/// </summary>
[Collection("registro-local")]
public sealed class RegistroLocalTests : IDisposable
{
    private readonly string carpeta;

    public RegistroLocalTests()
    {
        carpeta = Path.Combine(Path.GetTempPath(), "avacom-core-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(carpeta);
        Environment.SetEnvironmentVariable("AVACOM_LMS_DIR_LOGS", carpeta);
        RegistroLocal.Reiniciar();
        RegistroLocal.VentanaDeRepeticion = TimeSpan.Zero;
        RegistroLocal.Configurar("student", "1.4.0", () => "d-prueba");
    }

    public void Dispose()
    {
        Environment.SetEnvironmentVariable("AVACOM_LMS_DIR_LOGS", null);
        RegistroLocal.Reiniciar();
        RegistroLocal.VentanaDeRepeticion = TimeSpan.FromSeconds(30);
        try { Directory.Delete(carpeta, recursive: true); } catch { }
    }

    private static List<JsonElement> Lineas(string ruta) =>
        File.ReadAllLines(ruta).Where(l => l.Length > 0).Select(l => JsonDocument.Parse(l).RootElement.Clone()).ToList();

    [Fact]
    public void UnRenglon_LlevaLosCamposMinimosYVaAlArchivoDeApp_YSoloWarningOPeorALosErrores()
    {
        RegistroLocal.Info(Canal.Dispositivo, "arranque", "La app arrancó", new { version = "1.4.0" }, corr: "c-1");
        RegistroLocal.Error(Canal.Escritura, "cola.persistir_fallo", "No se pudo escribir la cola", new { errno = 28, libre_mb = 0 }, new IOException("disco lleno"));
        var app = Lineas(RegistroLocal.RutaApp);
        var errores = Lineas(RegistroLocal.RutaErrores);
        Assert.Equal(2, app.Count);
        Assert.Single(errores);
        var error = errores[0];
        foreach (var campo in new[] { "ts", "nivel", "canal", "app", "modulo", "evento", "ruta", "mensaje", "detalle", "traza", "corr", "dispositivo_id", "version_app" })
            Assert.True(error.TryGetProperty(campo, out _), campo);
        Assert.Equal("ERROR", error.GetProperty("nivel").GetString());
        Assert.Equal("escritura", error.GetProperty("canal").GetString());
        Assert.Equal("student", error.GetProperty("app").GetString());
        Assert.Equal("bad", error.GetProperty("ruta").GetString());
        Assert.Equal("d-prueba", error.GetProperty("dispositivo_id").GetString());
        Assert.Equal(28, error.GetProperty("detalle").GetProperty("errno").GetInt32());
        Assert.Contains("disco lleno", error.GetProperty("traza").GetString());
        Assert.Equal("c-1", app[0].GetProperty("corr").GetString());
        Assert.Null(app[0].GetProperty("ruta").GetString());
    }

    [Fact]
    public void LasClavesProhibidasSeRedactanEnCualquierNivel_YLosIdentificadoresSeConservan()
    {
        RegistroLocal.Advertencia(Canal.Comunicacion, "http.error", "x",
            new { usuario_id = "u-1", password = "Secreta.1", anidado = new { pin = "1234", errno = 2 }, lista = new object[] { new { token = "abc" }, 3 }, nombre = "Juan", identificador_hw = "hw-7" });
        var texto = File.ReadAllText(RegistroLocal.RutaApp);
        Assert.DoesNotContain("Secreta.1", texto);
        Assert.DoesNotContain("1234", texto);
        Assert.DoesNotContain("Juan", texto);
        Assert.DoesNotContain("abc", texto);
        Assert.Contains("\"usuario_id\":\"u-1\"", texto);
        Assert.Contains("\"identificador_hw\":\"hw-7\"", texto);
        Assert.Contains("\"errno\":2", texto);
        Assert.Contains(RegistroLocal.Redactado, texto);
    }

    [Fact]
    public void LaRotacionPorTamanoNoDejaCrecerElArchivo()
    {
        RegistroLocal.TamanoMaximo = 2_000;
        RegistroLocal.Copias = 3;
        try
        {
            for (var i = 0; i < 60; i++) RegistroLocal.Info(Canal.Aplicacion, $"ev{i}", new string('x', 100));
            Assert.True(new FileInfo(RegistroLocal.RutaApp).Length <= 2_300);
            Assert.True(File.Exists(RegistroLocal.RutaApp + ".1"));
            Assert.True(File.Exists(RegistroLocal.RutaApp + ".3"));
            Assert.False(File.Exists(RegistroLocal.RutaApp + ".4"));
        }
        finally { RegistroLocal.TamanoMaximo = 2 * 1024 * 1024; RegistroLocal.Copias = 5; }
    }

    [Fact]
    public void LosWarningOPeorQuedanPendientesDeEntrega_YDevolverLosRestituye()
    {
        RegistroLocal.Info(Canal.Aplicacion, "a", "info");
        RegistroLocal.Advertencia(Canal.Comunicacion, "b", "aviso");
        RegistroLocal.Error(Canal.Escritura, "c", "error");
        Assert.Equal(2, RegistroLocal.CuentaPendientes);
        var tomados = RegistroLocal.TomarPendientes(1);
        Assert.Single(tomados);
        Assert.Equal("b", tomados[0].Evento);
        Assert.Equal(1, RegistroLocal.CuentaPendientes);
        RegistroLocal.Devolver(tomados);
        Assert.Equal(2, RegistroLocal.CuentaPendientes);
        Assert.Equal("b", RegistroLocal.TomarPendientes()[0].Evento);   // vuelve al frente, en orden
    }

    [Fact]
    public void LaVentanaDeRepeticionFrenaElMismoRenglon_PeroNoUnoDistinto()
    {
        RegistroLocal.VentanaDeRepeticion = TimeSpan.FromMinutes(1);
        RegistroLocal.Reiniciar();
        for (var i = 0; i < 5; i++) RegistroLocal.Advertencia(Canal.Comunicacion, "red.sin_conexion", "Sin conexión: /api/x");
        RegistroLocal.Advertencia(Canal.Comunicacion, "red.sin_conexion", "Sin conexión: /api/y");
        RegistroLocal.Escribir(NivelLog.Warning, Canal.Comunicacion, "red.sin_conexion", "Sin conexión: /api/x", sinFreno: true);
        Assert.Equal(3, Lineas(RegistroLocal.RutaApp).Count);
    }

    [Fact]
    public void ElLoggerNuncaEleva_AunqueLaCarpetaNoSePuedaEscribir()
    {
        var archivo = Path.Combine(carpeta, "bloqueo");
        File.WriteAllText(archivo, "x");
        Environment.SetEnvironmentVariable("AVACOM_LMS_DIR_LOGS", Path.Combine(archivo, "logs"));   // un archivo donde va una carpeta
        var excepcion = Record.Exception(() => RegistroLocal.Error(Canal.Aplicacion, "x", "y"));
        Assert.Null(excepcion);
    }

    [Fact]
    public void LeerDevuelveLasUltimasLineas_YExportarDiagnosticoArmaUnZipConLogsYFicha()
    {
        for (var i = 0; i < 5; i++) RegistroLocal.Info(Canal.Aplicacion, $"e{i}", $"m{i}");
        RegistroLocal.Advertencia(Canal.Dispositivo, "bateria.baja", "Batería al 9 %", new { bateria_pct = 9 });
        var ultimas = RegistroLocal.Leer(ultimos: 2);
        Assert.Equal(["e4", "bateria.baja"], ultimas.Select(r => r.Evento).ToArray());
        Assert.Single(RegistroLocal.Leer(soloErrores: true));
        var zip = RegistroLocal.ExportarDiagnostico(Path.Combine(carpeta, "salida", "diag.zip"), new { servidor = "http://127.0.0.1:8000", password = "no" });
        using var archivo = System.IO.Compression.ZipFile.OpenRead(zip);
        var nombres = archivo.Entries.Select(e => e.FullName).ToList();
        Assert.Contains("diagnostico.json", nombres);
        Assert.Contains("logs/student-app.log", nombres);
        Assert.Contains("logs/student-errores.log", nombres);
        using var lector = new StreamReader(archivo.GetEntry("diagnostico.json")!.Open());
        var ficha = lector.ReadToEnd();
        Assert.Contains("\"servidor\"", ficha);
        Assert.DoesNotContain("\"no\"", ficha);
        Assert.Contains("\"app\": \"student\"", ficha);
    }

    [Fact]
    public void RegistroDeFallosSigueEscribiendoSuArchivoYAdemasElRenglonDeAplicacion()
    {
        Environment.SetEnvironmentVariable("AVACOM_LMS_DIR_FALLOS", carpeta);
        try
        {
            RegistroDeFallos.Escribir("student", "Prueba.Origen", new InvalidOperationException("estado imposible"));
            Assert.Contains("Prueba.Origen", File.ReadAllText(RegistroDeFallos.Ruta("student")));
            var linea = Lineas(RegistroLocal.RutaErrores).Single();
            Assert.Equal(("aplicacion", "excepcion.no_controlada", "Prueba.Origen"),
                         (linea.GetProperty("canal").GetString(), linea.GetProperty("evento").GetString(), linea.GetProperty("mensaje").GetString()));
            Assert.Contains("estado imposible", linea.GetProperty("traza").GetString());
        }
        finally { Environment.SetEnvironmentVariable("AVACOM_LMS_DIR_FALLOS", null); }
    }
}

[Collection("registro-local")]
public sealed class CabecerasYClientesTests : IDisposable
{
    private readonly string carpeta;

    public CabecerasYClientesTests()
    {
        carpeta = Path.Combine(Path.GetTempPath(), "avacom-core-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(carpeta);
        Environment.SetEnvironmentVariable("AVACOM_LMS_DIR_LOGS", carpeta);
        RegistroLocal.Reiniciar();
        RegistroLocal.VentanaDeRepeticion = TimeSpan.Zero;
        RegistroLocal.Configurar("ops", "0.9");
        AparatoRegistrado.Cargar = null; AparatoRegistrado.Guardar = null; AparatoRegistrado.Olvidar();
        ClienteJson.Token = null;
    }

    public void Dispose()
    {
        Environment.SetEnvironmentVariable("AVACOM_LMS_DIR_LOGS", null);
        RegistroLocal.Reiniciar();
        RegistroLocal.VentanaDeRepeticion = TimeSpan.FromSeconds(30);
        AparatoRegistrado.Cargar = null; AparatoRegistrado.Guardar = null; AparatoRegistrado.Olvidar();
        ClienteJson.Token = null;
        try { Directory.Delete(carpeta, recursive: true); } catch { }
    }

    private static HttpResponseMessage Respuesta(HttpStatusCode estado, string json) =>
        new(estado) { Content = new StringContent(json, Encoding.UTF8, "application/json") };

    private sealed class ManejadorFalso(Func<HttpRequestMessage, Task<HttpResponseMessage>> responder) : HttpMessageHandler
    {
        public List<HttpRequestMessage> Peticiones { get; } = [];
        public List<string?> Cuerpos { get; } = [];   // el cliente libera la petición al terminar: el cuerpo se copia aquí
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Peticiones.Add(request);
            Cuerpos.Add(request.Content is null ? null : await request.Content.ReadAsStringAsync(cancellationToken));
            var respuesta = await responder(request);
            respuesta.RequestMessage = request;
            return respuesta;
        }
    }

    [Fact]
    public async Task CadaPeticionLlevaElAparatoYUnaCorrelacion_YSinAparatoNoSeInventa()
    {
        var manejador = new ManejadorFalso(_ => Task.FromResult(Respuesta(HttpStatusCode.OK, "{}")));
        var api = new AuditoriaApi(new HttpClient(manejador), new Uri("http://127.0.0.1:8000/"));
        await api.EstadoAsync();
        var sin = manejador.Peticiones[0];
        Assert.False(sin.Headers.Contains(ClienteJson.CabeceraDispositivo));
        Assert.True(sin.Headers.Contains(ClienteJson.CabeceraCorrelacion));
        Assert.Matches("^[A-Za-z0-9._:-]{8,64}$", sin.Headers.GetValues(ClienteJson.CabeceraCorrelacion).Single());
        Assert.Equal(api.UltimoCorr, sin.Headers.GetValues(ClienteJson.CabeceraCorrelacion).Single());

        AparatoRegistrado.Recordar("d-7f");
        await api.EstadoAsync();
        var con = manejador.Peticiones[1];
        Assert.Equal("d-7f", con.Headers.GetValues(ClienteJson.CabeceraDispositivo).Single());
        Assert.NotEqual(sin.Headers.GetValues(ClienteJson.CabeceraCorrelacion).Single(), con.Headers.GetValues(ClienteJson.CabeceraCorrelacion).Single());
    }

    [Fact]
    public void ElAparatoSePersisteConLosGanchosYSeNormaliza()
    {
        string? guardado = null;
        AparatoRegistrado.Cargar = () => "d-guardado";
        AparatoRegistrado.Guardar = v => guardado = v;
        AparatoRegistrado.Olvidar();
        Assert.Null(guardado);
        AparatoRegistrado.Cargar = () => "d-guardado";
        typeof(AparatoRegistrado).GetField("cargado", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static)!.SetValue(null, false);
        Assert.Equal("d-guardado", AparatoRegistrado.Id);
        AparatoRegistrado.Recordar("  nuevo-id  ");
        Assert.Equal("nuevo-id", AparatoRegistrado.Id);
        Assert.Equal("nuevo-id", guardado);
        AparatoRegistrado.Recordar("<script>");   // inválido: se ignora
        Assert.Equal("nuevo-id", AparatoRegistrado.Id);
        AparatoRegistrado.Recordar(null);
        Assert.Equal("nuevo-id", AparatoRegistrado.Id);
    }

    [Fact]
    public async Task ElLatidoYLaUnionRecuerdanElIdQueDaElNodo_YElLatidoDeclaraElTipo()
    {
        var manejador = new ManejadorFalso(req => Task.FromResult(Respuesta(HttpStatusCode.OK,
            req.RequestUri!.AbsolutePath.Contains("latido")
                ? """{"id":"d-latido","identificador_hw":"ops-NODO","nombre":"NODO","tipo":"MASTER","activo":true,"bloqueado":false,"en_linea":true,"registrado_en":1,"ultimo_latido_en":1,"sesion_abierta":null}"""
                : """
                  {"sesion":{"id":"s1","estado":"abierta","fuente_curso":"ejemplo","curso_ref":"c","curso_rotulo":"E","leccion_ref":"l1","leccion_rotulo":"L","grupo_rotulo":"","profesor_rotulo":"P"},"activa":true,
                   "participante":{"id":"p1","persona_id":"ana","persona_rotulo":"Ana","dispositivo":"tab","dispositivo_id":"d-union","dispositivo_bloqueado":false,"estado":"conectado","admision_nominal":false,"ingreso":1,"ultimo_latido_en":2},
                   "selector":null,"seguimiento":true,"pantallas_bloqueadas":false,"pendientes":[],"avisos":[],"servidor_en":6,"intervalo_sondeo_ms":2000,"nuevo":true,"en_espera":false}
                  """)));
        var dispositivos = new DispositivosApi(new HttpClient(manejador), new Uri("http://127.0.0.1:8000/"));
        var r = await dispositivos.LatidoAsync("ops-NODO", "NODO", "windows", "0.9", tipo: "MASTER");
        Assert.Equal("d-latido", r!.Id);
        Assert.Equal("d-latido", AparatoRegistrado.Id);
        Assert.Contains("\"tipo\":\"MASTER\"", manejador.Cuerpos[0]);

        var aula = new AulaApi(new HttpClient(manejador), new Uri("http://127.0.0.1:8000/"), "ejemplo");
        var estado = await aula.UnirseAsync("123456", "ana", "Ana", "student-TAB", null);
        Assert.Equal("d-union", estado!.Participante!.DispositivoId);
        Assert.Equal("d-union", AparatoRegistrado.Id);
        // La petición de unirse viajó con el id anterior; la siguiente ya lleva el que dio el nodo.
        Assert.Equal("d-latido", manejador.Peticiones[1].Headers.GetValues(ClienteJson.CabeceraDispositivo).Single());
        await aula.EstadoAsync("s1", "p1");
        Assert.Equal("d-union", manejador.Peticiones[2].Headers.GetValues(ClienteJson.CabeceraDispositivo).Single());
    }

    [Fact]
    public async Task UnErrorHttpYLaFaltaDeRedQuedanEnElCanalDeComunicacionSinElCuerpo()
    {
        var manejador = new ManejadorFalso(req => req.RequestUri!.AbsolutePath.Contains("estado")
            ? Task.FromResult(Respuesta(HttpStatusCode.Forbidden, """{"detail":"Tu rol no tiene concedido audit.read.","codigo":"permiso_denegado","permiso":"audit.read","nombre":"Juan"}"""))
            : throw new HttpRequestException("sin ruta"));
        var api = new AuditoriaApi(new HttpClient(manejador), new Uri("http://127.0.0.1:8000/"));
        Assert.Null(await api.EstadoAsync());
        Assert.Equal("permiso_denegado", api.UltimoError!.Codigo);
        Assert.Null(await api.TramosAsync());
        Assert.Equal("sin_conexion", api.UltimoError!.Codigo);
        var lineas = File.ReadAllLines(RegistroLocal.RutaErrores).Select(l => JsonDocument.Parse(l).RootElement.Clone()).ToList();
        Assert.Equal(2, lineas.Count);
        Assert.Equal(("comunicacion", "http.error", "WARNING", "sad"), (lineas[0].GetProperty("canal").GetString(), lineas[0].GetProperty("evento").GetString(), lineas[0].GetProperty("nivel").GetString(), lineas[0].GetProperty("ruta").GetString()));
        Assert.Equal(403, lineas[0].GetProperty("detalle").GetProperty("estado").GetInt32());
        Assert.Equal("permiso_denegado", lineas[0].GetProperty("detalle").GetProperty("codigo").GetString());
        Assert.DoesNotContain("Juan", File.ReadAllText(RegistroLocal.RutaErrores));
        Assert.Equal("red.sin_conexion", lineas[1].GetProperty("evento").GetString());
        Assert.Equal("/api/auditoria/tramos/", lineas[1].GetProperty("detalle").GetProperty("ruta").GetString());
        Assert.Equal(api.UltimoCorr, lineas[1].GetProperty("corr").GetString());
    }

    [Fact]
    public void LaUriDelCanalLlevaElAparatoCuandoSeConoce()
    {
        var sin = AulaSocketClient.UriDe(new Uri("http://192.168.0.5:8000/"), "s1", "estudiante", "p1", "tok", null);
        Assert.DoesNotContain("dispositivo=", sin.Query);
        var con = AulaSocketClient.UriDe(new Uri("http://192.168.0.5:8000/"), "s1", "estudiante", "p1", "tok", "d-1");
        Assert.Contains("&dispositivo=d-1", con.Query);
        Assert.Equal("ws", con.Scheme);
    }

    [Fact]
    public async Task AuditoriaApi_ConsultaConFiltrosYLeeAsientosEstadoYTramos()
    {
        var manejador = new ManejadorFalso(req =>
        {
            var ruta = req.RequestUri!.PathAndQuery;
            if (ruta.StartsWith("/api/auditoria/asientos/?"))
                return Task.FromResult(Respuesta(HttpStatusCode.OK, """
                    {"asientos":[{"id":"a1","secuencia":12,"ocurrido_en":1790000000000,"actor":{"tipo":"usuario","usuario_id":"u-1","rotulo":"Rectoría"},"roles_activos":["ADMIN"],
                      "modulo":"aula","modulo_etiqueta":"Aula (clase en vivo)","accion":"aula.sesion.iniciada","etiqueta":"Clase iniciada","resultado":"ok",
                      "objeto":{"tabla":"m07_sesion","id":"s1"},"motivo":null,"origen":"api","dispositivo_id":"d-1","correlacion_id":"c-1","evento_id":null,"tramo_id":"t1",
                      "sensible":false,"enmascarado":true,"huella":"abcd1234…wxyz5678","valor_anterior":null,"valor_nuevo":{"codigo":"123456"}}],
                     "siguiente":11,"orden":"desc","limite":50,"total":80,"enmascarado":true}
                    """));
            if (ruta == "/api/auditoria/estado/")
                return Task.FromResult(Respuesta(HttpStatusCode.OK, """
                    {"cabeza":{"secuencia":80,"huella":"abcd1234…wxyz5678"},"total_asientos":80,"tramo_activo":{"id":"t1","desde":1,"hasta":80,"estado":"verificada","abierta":true,"huella_cierre":"ab…cd",
                     "verificado_en":1790000000000,"verificado_hasta":79,"salto_en":null,"salto_causa":null,"exportado_en":null,"archivo":null,"rotado_en":null,"creado_en":1,"asientos":80},
                     "ultimo_verificado_en":1790000000000,"salto_detectado":false,"salto":null,"triggers_ok":true,"tamano_bytes":40000,"umbral_bytes":104857600,"porcentaje_umbral":0.04,
                     "tramos":1,"version_catalogo":"2026.09.30","verificar_cada_s":3600}
                    """));
            if (ruta == "/api/auditoria/tramos/")
                return Task.FromResult(Respuesta(HttpStatusCode.OK, """{"tramos":[{"id":"t1","desde":1,"hasta":3,"estado":"con_salto","abierta":true,"huella_cierre":"x","verificado_en":1,"verificado_hasta":1,"salto_en":2,"salto_causa":"huella_discordante","exportado_en":null,"archivo":null,"rotado_en":null,"creado_en":1,"asientos":3}]}"""));
            if (ruta == "/api/auditoria/verificar/")
                return Task.FromResult(Respuesta(HttpStatusCode.OK, """{"estado":"verificada","verificados":80,"salto_en":null,"causa":null,"tramos":[]}"""));
            return Task.FromResult(Respuesta(HttpStatusCode.NotFound, "{}"));
        });
        var api = new AuditoriaApi(new HttpClient(manejador), new Uri("http://127.0.0.1:8000/"));
        var pagina = await api.AsientosAsync(new FiltrosBitacora(Modulo: "aula", Resultado: "ok", Desde: 1, Limite: 50, Antes: 13, Texto: "sum a"));
        Assert.Equal("/api/auditoria/asientos/?desde=1&modulo=aula&resultado=ok&texto=sum%20a&limite=50&antes=13", manejador.Peticiones[0].RequestUri!.PathAndQuery);
        var asiento = pagina!.Asientos.Single();
        Assert.Equal(("Rectoría", "Clase iniciada", "Correcto", "m07_sesion · s1", 11L), (asiento.Actor!.Legible, asiento.EtiquetaLegible, asiento.ResultadoLegible, asiento.Objeto!.Legible, pagina.Siguiente!.Value));
        Assert.Equal(["ADMIN"], asiento.RolesActivos!.ToArray());
        Assert.Equal("123456", asiento.ValorNuevo!.Value.GetProperty("codigo").GetString());

        var estado = await api.EstadoAsync();
        Assert.Equal(("verde", 80L, true), (estado!.Semaforo, estado.Cabeza.Secuencia, estado.TriggersOk));
        var tramos = await api.TramosAsync();
        Assert.Equal(("Salto detectado", "1 – 3", 2L), (tramos!.Tramos[0].EstadoLegible, tramos.Tramos[0].Rango, tramos.Tramos[0].SaltoEn!.Value));
        var verificacion = await api.VerificarAsync();
        Assert.Equal("verificada", verificacion!.Estado);
        Assert.Contains("\"todos\":false", manejador.Cuerpos[^1]);
    }

    [Fact]
    public async Task LogsApi_EntregaLosRenglonesConLosNombresDelNodo_YElEntregadorDevuelveLoQueNoSePudoEntregar()
    {
        var falla = true;
        var manejador = new ManejadorFalso(req => falla
            ? throw new HttpRequestException("sin red")
            : Task.FromResult(Respuesta(HttpStatusCode.Accepted, """{"recibidos":2,"escritos":2,"descartados":0,"dispositivo_id":"d-1"}""")));
        var api = new LogsApi(new HttpClient(manejador), new Uri("http://127.0.0.1:8000/"));
        RegistroLocal.Advertencia(Canal.Comunicacion, "socket.caida", "Se cayó el canal", new { duracion_ms = 12000 }, corr: "c-9");
        RegistroLocal.Error(Canal.Escritura, "cola.persistir_fallo", "No se pudo escribir", new { errno = 28 });
        AparatoRegistrado.Recordar("d-1");
        var entregador = new EntregadorDeLogs(() => api, "student", () => "1.4.0");

        Assert.Null(await entregador.EntregarAhoraAsync());          // sin red: vuelven a la cola (más el renglón del propio fallo de red)
        Assert.True(RegistroLocal.CuentaPendientes >= 2);
        falla = false;
        var entrega = await entregador.EntregarAhoraAsync();
        Assert.NotNull(entrega);
        Assert.Equal(0, RegistroLocal.CuentaPendientes);
        using var doc = JsonDocument.Parse(manejador.Cuerpos[^1]!);
        var raiz = doc.RootElement;
        Assert.Equal(("student", "1.4.0", "d-1"), (raiz.GetProperty("app").GetString(), raiz.GetProperty("version_app").GetString(), raiz.GetProperty("dispositivo_id").GetString()));
        var primero = raiz.GetProperty("renglones")[0];
        foreach (var campo in new[] { "ts", "nivel", "canal", "app", "modulo", "evento", "ruta", "mensaje", "detalle", "traza", "corr", "version_app" })
            Assert.True(primero.TryGetProperty(campo, out _), campo);
        Assert.Equal(("WARNING", "comunicacion", "socket.caida", "c-9"), (primero.GetProperty("nivel").GetString(), primero.GetProperty("canal").GetString(), primero.GetProperty("evento").GetString(), primero.GetProperty("corr").GetString()));
        Assert.Equal(12000, primero.GetProperty("detalle").GetProperty("duracion_ms").GetInt32());
        Assert.Equal(2, entregador.UltimaEntrega!.Escritos);
        Assert.Null(await entregador.EntregarAhoraAsync());          // ya no hay nada que entregar
    }

    [Fact]
    public async Task ElEntregadorNoIntentaNadaSinAparatoNiSesion()
    {
        var manejador = new ManejadorFalso(_ => Task.FromResult(Respuesta(HttpStatusCode.Accepted, "{}")));
        var api = new LogsApi(new HttpClient(manejador), new Uri("http://127.0.0.1:8000/"));
        RegistroLocal.Advertencia(Canal.Dispositivo, "bateria.baja", "Batería al 5 %");
        var entregador = new EntregadorDeLogs(() => api, "student");
        Assert.Null(await entregador.EntregarAhoraAsync());
        Assert.Empty(manejador.Peticiones);
        Assert.Equal(1, RegistroLocal.CuentaPendientes);
        ClienteJson.Token = "pase";
        Assert.NotNull(await entregador.EntregarAhoraAsync());
        Assert.Single(manejador.Peticiones);
    }
}

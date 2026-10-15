using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Reportes;

namespace Avacom.Lms.Ops.Tests;

/// <summary>
/// El flujo de exportar un reporte a un archivo (FUN-146) de punta a punta, sin interfaz: el cliente REAL de <c>/api/reportes/</c> contra un nodo falso, el temporal REAL en disco y la
/// escritura segura REAL en una carpeta de prueba (o una que falla a propósito). Lo que se comprueba es lo que le importa a quien guarda en una memoria USB: que nada se registre
/// como guardado sin releer el archivo, que un fallo deje elegir otro destino SIN generar de nuevo, que el nodo nunca reciba una ruta, y que no quede ningún temporal.
/// </summary>
[Collection("estado global")]
public sealed class FlujoDeExportacionTests : IDisposable
{
    private static readonly JsonSerializerOptions Web = new(JsonSerializerDefaults.Web);
    private readonly List<string> _carpetas = [];

    public FlujoDeExportacionTests() => ClienteJson.Token = null;

    public void Dispose()
    {
        ClienteJson.Token = null;
        foreach (var c in _carpetas)
            try { Directory.Delete(c, true); } catch (IOException) { /* el sistema la limpia */ }
    }

    private string Carpeta(string nombre)
    {
        var ruta = Path.Combine(Path.GetTempPath(), "avacom-flujo-" + Guid.NewGuid().ToString("N"), nombre);
        Directory.CreateDirectory(ruta);
        _carpetas.Add(Path.GetDirectoryName(ruta)!);
        return ruta;
    }

    private static string Sha(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));

    private sealed record Captura(HttpMethod Metodo, string Ruta, string? Cuerpo)
    {
        public JsonElement Json => JsonDocument.Parse(Cuerpo!).RootElement.Clone();
    }

    /// <summary>El nodo de mentira: entrega el archivo en <c>exportaciones/</c>, anota lo que le llega y falla donde se le diga.</summary>
    private sealed class Escenario
    {
        public byte[] Contenido { get; set; } = Encoding.UTF8.GetBytes("Reporte;Grupo 8A\nAlumno 01;100\n").Concat(new byte[200_000]).ToArray();
        public long Ahora { get; set; } = 1_790_000_000_000;
        public long Vigencia { get; set; } = 900_000;                                   // 15 minutos, como el nodo
        public bool SinRed { get; set; }
        public (HttpStatusCode Estado, string Json)? NegarAutorizacion { get; set; }
        public Func<Captura, HttpResponseMessage?>? AlConfirmar { get; set; }
        public string HuellaDeclarada { get; set; } = string.Empty;
        public List<Captura> Peticiones { get; } = [];
        public int Autorizaciones => Peticiones.Count(p => p.Ruta.EndsWith("/exportaciones/", StringComparison.Ordinal));
        public IEnumerable<Captura> Confirmaciones => Peticiones.Where(p => p.Ruta.EndsWith("/confirmar/", StringComparison.Ordinal));

        public ReportesApi Api()
        {
            var http = new HttpClient(new Manejador(this));
            return new ReportesApi(http, new Uri("http://192.168.0.55:8000/"));
        }

        private HttpResponseMessage Atender(Captura c)
        {
            Peticiones.Add(c);
            if (SinRed) throw new HttpRequestException("sin red");
            if (c.Ruta.EndsWith("/exportaciones/alcance/", StringComparison.Ordinal))
                return Respuesta(HttpStatusCode.OK, """{"tipo":"grupo","formato":"csv","nominal":true,"texto_alcance":"Vas a guardar el reporte del grupo 8A (7 alumnos)","advertencia":"Sin datos de personas."}""");
            if (c.Ruta.EndsWith("/confirmar/", StringComparison.Ordinal))
                return AlConfirmar?.Invoke(c) ?? Respuesta(HttpStatusCode.OK, """{"exportacion":{"id":"e-1","estado":"entregada","intentos":[]},"reintento":false}""");
            if (c.Ruta.EndsWith("/exportaciones/", StringComparison.Ordinal))
            {
                if (NegarAutorizacion is { } n) return Respuesta(n.Estado, n.Json);
                var r = new HttpResponseMessage(HttpStatusCode.Created) { Content = new ByteArrayContent(Contenido) };
                r.Content.Headers.ContentType = new MediaTypeHeaderValue("text/csv") { CharSet = "utf-8" };
                void Poner(string n, string v) => r.Headers.Add("X-Avacom-Export-" + n, v);
                Poner("Id", $"e-{Autorizaciones}");
                Poner("Tipo", "grupo");
                Poner("Formato", "csv");
                Poner("Huella", string.IsNullOrEmpty(HuellaDeclarada) ? Sha(Contenido) : HuellaDeclarada);
                Poner("Bytes", Contenido.Length.ToString());
                Poner("Filas", "11");
                Poner("Nombre", "reporte-grupo-8A-2026-10-15-1042.csv");
                Poner("Expira-En", (Ahora + Vigencia).ToString());
                Poner("Corte-En", Ahora.ToString());
                Poner("Nominal", "true");
                Poner("Umbral-Aplicado", "false");
                Poner("Destino", c.Json.TryGetProperty("destino_tipo", out var pedido) ? pedido.GetString() ?? "extraible" : "extraible");       // el nodo autoriza la clase de destino que se le pidió
                return r;
            }
            throw new InvalidOperationException("Ruta no prevista: " + c.Ruta);
        }

        private static HttpResponseMessage Respuesta(HttpStatusCode estado, string json) => new(estado) { Content = new StringContent(json, Encoding.UTF8, "application/json") };

        private sealed class Manejador(Escenario e) : HttpMessageHandler
        {
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            {
                var cuerpo = request.Content is null ? null : await request.Content.ReadAsStringAsync(cancellationToken);
                return e.Atender(new Captura(request.Method, request.RequestUri!.AbsolutePath, cuerpo));
            }
        }
    }

    private static FlujoDeExportacion Flujo(Escenario e, string temporal, FlujoDeExportacion.Escritor? escritor = null) =>
        new(e.Api(), "prof-1", ReporteSolicitado.DeGrupo("g-1"), temporal, escritor, () => e.Ahora);

    private static FlujoDeExportacion.Escritor QueFalla(MotivoDeEscritura motivo, string? detalle = null) =>
        (_, _, _, _, _, _, _) => Task.FromResult(new ResultadoDeEscritura(false, null, 0, null, MotivosDeEscritura.De(motivo)) { Detalle = detalle });

    private sealed class Avance : IProgress<double>
    {
        public readonly List<double> Valores = [];
        public void Report(double valor) { lock (Valores) Valores.Add(valor); }
    }

    // ================================================================================================== el camino feliz

    [Fact]
    public async Task Guardar_AutorizaBajaEscribeVerificaYConfirmaConLaHuellaReleida()
    {
        var e = new Escenario();
        var temporal = Carpeta("temp");
        var destino = Carpeta("memoria");
        using var flujo = Flujo(e, temporal);
        var avance = new Avance();

        var r = await flujo.GuardarAsync(new DestinoElegido(destino, TipoDeDestino.Extraible), "csv", null, avance);

        Assert.Equal(EstadoDelGuardado.Guardado, r.Estado);
        Assert.True(r.Escrito);
        var ruta = Path.Combine(destino, "reporte-grupo-8A-2026-10-15-1042.csv");
        Assert.Equal(ruta, r.RutaFinal);
        Assert.Equal(e.Contenido.Length, r.Bytes);
        Assert.Equal(e.Contenido, await File.ReadAllBytesAsync(ruta));
        Assert.Empty(Directory.GetFiles(temporal));                                                   // el temporal se fue
        Assert.Equal(new[] { ruta }, Directory.GetFiles(destino));                                    // y en el destino no quedó ningún «.parte»

        Assert.Equal(1, e.Autorizaciones);
        var confirmacion = Assert.Single(e.Confirmaciones);
        Assert.Equal("/api/reportes/exportaciones/e-1/confirmar/", confirmacion.Ruta);
        Assert.Equal(new[] { "actor", "destino_tipo", "huella_verificada", "resultado" }, confirmacion.Json.EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal).ToArray());
        Assert.Equal(("guardado", "extraible", Sha(e.Contenido)),
            (confirmacion.Json.GetProperty("resultado").GetString(), confirmacion.Json.GetProperty("destino_tipo").GetString(), confirmacion.Json.GetProperty("huella_verificada").GetString()));
        Assert.DoesNotContain(destino, confirmacion.Cuerpo!);                                         // el nodo no recibe la ruta
        Assert.DoesNotContain("reporte-grupo", confirmacion.Cuerpo!);                                 // ni el nombre del archivo

        Assert.Equal(1.0, avance.Valores[^1]);
        Assert.Equal(avance.Valores.Order().ToArray(), avance.Valores.ToArray());                    // el avance sólo crece
        Assert.Contains(avance.Valores, v => v is > 0.3 and < 0.4);                                   // la bajada llega a su tramo antes de empezar a escribir
    }

    [Fact]
    public async Task ElDestinoSeNombraPorSuClase_NuncaPorSuRuta()
    {
        var e = new Escenario();
        using var flujo = Flujo(e, Carpeta("temp"));
        var r = await flujo.GuardarAsync(new DestinoElegido(Carpeta("docs"), TipoDeDestino.CarpetaLocal), "csv", null);
        Assert.Equal(EstadoDelGuardado.Guardado, r.Estado);
        var autorizacion = e.Peticiones.First(p => p.Ruta == "/api/reportes/exportaciones/");
        Assert.Equal("carpeta_local", autorizacion.Json.GetProperty("destino_tipo").GetString());
        Assert.Equal("csv", autorizacion.Json.GetProperty("formato").GetString());
        Assert.Equal("grupo", autorizacion.Json.GetProperty("reporte").GetProperty("tipo").GetString());
    }

    [Fact]
    public async Task LaRazonElegidaViajaEnLaAutorizacion_YSoloAhi()
    {
        var e = new Escenario();
        using var flujo = Flujo(e, Carpeta("temp"));
        await flujo.GuardarAsync(new DestinoElegido(Carpeta("m"), TipoDeDestino.Extraible), "csv", "entrega_a_familias");
        var autorizacion = e.Peticiones.First(p => p.Ruta == "/api/reportes/exportaciones/");
        Assert.Equal("entrega_a_familias", autorizacion.Json.GetProperty("razon_codigo").GetString());
        Assert.DoesNotContain("razon", Assert.Single(e.Confirmaciones).Cuerpo!);
    }

    // ================================================================================================== un destino que falla

    [Fact]
    public async Task UnaEscrituraQueFalla_AvisaElMotivoYDejaElegirOtroDestinoSinGenerarDeNuevo()
    {
        var e = new Escenario();
        var temporal = Carpeta("temp");
        var memoria = Carpeta("memoria");
        var otraMemoria = Carpeta("otra-memoria");
        var intento = 0;
        // La primera vez, la memoria «se retira»; la segunda, el destino responde de verdad.
        Task<ResultadoDeEscritura> Escritor(Stream origen, string sha, long bytes, string carpeta, string nombre, IProgress<double>? progreso, CancellationToken ct) =>
            ++intento == 1
                ? Task.FromResult(new ResultadoDeEscritura(false, null, 0, null, MotivosDeEscritura.De(MotivoDeEscritura.MedioRetirado)) { Detalle = "se retiró la unidad" })
                : EscrituraSegura.EscribirAsync(origen, sha, bytes, carpeta, nombre, progreso, ct);
        using var flujo = Flujo(e, temporal, Escritor);

        var primero = await flujo.GuardarAsync(new DestinoElegido(memoria, TipoDeDestino.Extraible), "csv", null);

        Assert.Equal(EstadoDelGuardado.NoSePudoEscribir, primero.Estado);
        Assert.False(primero.Escrito);
        Assert.Equal("Se retiró la memoria mientras se guardaba.", primero.Mensaje);
        Assert.Equal("Vuelve a conectarla y toca Guardar otra vez, o elige otro destino.", primero.Accion);
        Assert.Equal(MotivoDeEscritura.MedioRetirado, primero.Fallo!.Motivo);
        Assert.Equal("se retiró la unidad", primero.Detalle);
        Assert.True(flujo.TieneArchivoListo);                                                         // el archivo bajado se conserva para otro destino
        Assert.Single(Directory.GetFiles(temporal));
        var aviso = Assert.Single(e.Confirmaciones);
        Assert.Equal(("fallido", "extraible", "medio_retirado"),
            (aviso.Json.GetProperty("resultado").GetString(), aviso.Json.GetProperty("destino_tipo").GetString(), aviso.Json.GetProperty("motivo").GetString()));
        Assert.DoesNotContain(memoria, aviso.Cuerpo!);

        var segundo = await flujo.GuardarAsync(new DestinoElegido(otraMemoria, TipoDeDestino.Extraible), "csv", null);

        Assert.Equal(EstadoDelGuardado.Guardado, segundo.Estado);
        Assert.Equal(1, e.Autorizaciones);                                                            // NO se generó de nuevo (otra memoria: la misma clase de destino)
        Assert.Equal(e.Contenido, await File.ReadAllBytesAsync(segundo.RutaFinal!));
        Assert.Equal(2, e.Confirmaciones.Count());
        var guardado = e.Confirmaciones.Last();
        Assert.Equal(("guardado", "extraible"), (guardado.Json.GetProperty("resultado").GetString(), guardado.Json.GetProperty("destino_tipo").GetString()));
        Assert.Empty(Directory.GetFiles(temporal));
        Assert.False(flujo.TieneArchivoListo);
    }

    [Theory]
    [InlineData(MotivoDeEscritura.SinEspacio, "sin_espacio")]
    [InlineData(MotivoDeEscritura.ProtegidoContraEscritura, "protegido_contra_escritura")]
    [InlineData(MotivoDeEscritura.SinPermiso, "sin_permiso")]
    [InlineData(MotivoDeEscritura.RutaDeRedInalcanzable, "ruta_de_red_inalcanzable")]
    [InlineData(MotivoDeEscritura.NombreInvalido, "nombre_invalido")]
    [InlineData(MotivoDeEscritura.BloqueadoPorAntivirus, "bloqueado_por_antivirus")]
    [InlineData(MotivoDeEscritura.VerificacionFallida, "verificacion_fallida")]
    [InlineData(MotivoDeEscritura.Otro, "otro")]
    public async Task CadaMotivoDeEscritura_LlegaAlNodoConSuCodigoDeLaListaCerrada(MotivoDeEscritura motivo, string codigo)
    {
        var e = new Escenario();
        using var flujo = Flujo(e, Carpeta("temp"), QueFalla(motivo));
        var r = await flujo.GuardarAsync(new DestinoElegido(Carpeta("m"), TipoDeDestino.Extraible), "csv", null);
        Assert.Equal(EstadoDelGuardado.NoSePudoEscribir, r.Estado);
        Assert.False(string.IsNullOrWhiteSpace(r.Mensaje));
        Assert.False(string.IsNullOrWhiteSpace(r.Accion));
        Assert.Equal(codigo, Assert.Single(e.Confirmaciones).Json.GetProperty("motivo").GetString());
    }

    [Fact]
    public async Task UnDestinoReal_QueNoExiste_NoDejaNadaYElMensajeEsLaDeLaMemoriaRetirada()
    {
        var e = new Escenario();
        var temporal = Carpeta("temp");
        using var flujo = Flujo(e, temporal);
        var r = await flujo.GuardarAsync(new DestinoElegido(Path.Combine(Path.GetTempPath(), "avacom-no-existe-" + Guid.NewGuid().ToString("N")), TipoDeDestino.Extraible), "csv", null);
        Assert.Equal(EstadoDelGuardado.NoSePudoEscribir, r.Estado);
        Assert.Equal(MotivoDeEscritura.MedioRetirado, r.Fallo!.Motivo);
        Assert.True(flujo.TieneArchivoListo);
        Assert.Equal(1, e.Autorizaciones);
    }

    // ================================================================================================== cuándo SÍ se genera otra vez

    [Fact]
    public async Task UnFormatoDistinto_PideOtroArchivo()
    {
        var e = new Escenario();
        using var flujo = Flujo(e, Carpeta("temp"), QueFalla(MotivoDeEscritura.SinEspacio));
        await flujo.GuardarAsync(new DestinoElegido(Carpeta("m"), TipoDeDestino.Extraible), "csv", null);
        await flujo.GuardarAsync(new DestinoElegido(Carpeta("m2"), TipoDeDestino.Extraible), "xlsx", null);
        Assert.Equal(2, e.Autorizaciones);
        Assert.Equal("xlsx", e.Peticiones.Last(p => p.Ruta == "/api/reportes/exportaciones/").Json.GetProperty("formato").GetString());
    }

    [Fact]
    public async Task UnaClaseDeDestinoDistinta_VuelveAPasarPorElNodo_QueAplicaSuPoliticaAlAutorizar()
    {
        // Revisión independiente: si la memoria falla y se elige una carpeta del equipo (o al revés) NO se reutiliza el archivo autorizado para el otro tipo: el administrador pudo cerrar las
        // memorias mientras tanto, y el nodo decide por la clase de destino al AUTORIZAR (confirmar sólo anota).
        var e = new Escenario();
        var temporal = Carpeta("temp");
        var intento = 0;
        Task<ResultadoDeEscritura> Escritor(Stream origen, string sha, long bytes, string carpeta, string nombre, IProgress<double>? progreso, CancellationToken ct) =>
            ++intento == 1 ? Task.FromResult(new ResultadoDeEscritura(false, null, 0, null, MotivosDeEscritura.De(MotivoDeEscritura.SinEspacio)))
                           : EscrituraSegura.EscribirAsync(origen, sha, bytes, carpeta, nombre, progreso, ct);
        using var flujo = Flujo(e, temporal, Escritor);

        await flujo.GuardarAsync(new DestinoElegido(Carpeta("documentos"), TipoDeDestino.CarpetaLocal), "csv", null);
        Assert.Equal(1, e.Autorizaciones);
        var r = await flujo.GuardarAsync(new DestinoElegido(Carpeta("memoria"), TipoDeDestino.Extraible), "csv", null);

        Assert.Equal(EstadoDelGuardado.Guardado, r.Estado);
        Assert.Equal(2, e.Autorizaciones);                                                            // se autorizó otra vez, ahora como «extraible»
        var autorizaciones = e.Peticiones.Where(p => p.Ruta == "/api/reportes/exportaciones/").ToList();
        Assert.Equal(new[] { "carpeta_local", "extraible" }, autorizaciones.Select(a => a.Json.GetProperty("destino_tipo").GetString()).ToArray());
        Assert.Empty(Directory.GetFiles(temporal));
    }

    [Fact]
    public async Task SiElNodoYaNoPermiteLaNuevaClaseDeDestino_NoSeEscribeNada()
    {
        var e = new Escenario();
        var memoria = Carpeta("memoria");
        using var flujo = Flujo(e, Carpeta("temp"), QueFalla(MotivoDeEscritura.SinEspacio));
        await flujo.GuardarAsync(new DestinoElegido(Carpeta("documentos"), TipoDeDestino.CarpetaLocal), "csv", null);          // falla; el archivo queda listo
        e.NegarAutorizacion = (HttpStatusCode.Forbidden, """{"codigo":"destino_no_permitido","detail":"El administrador no permite guardar en memorias extraíbles."}""");

        var r = await flujo.GuardarAsync(new DestinoElegido(memoria, TipoDeDestino.Extraible), "csv", null);

        Assert.Equal(EstadoDelGuardado.NoAutorizado, r.Estado);                                       // el nodo lo niega y el archivo bajado para otra clase de destino no se usa
        Assert.Empty(Directory.GetFiles(memoria));
        Assert.Equal(2, e.Autorizaciones);
    }

    [Fact]
    public async Task UnaRazonDistinta_PideOtraAutorizacion()
    {
        var e = new Escenario();
        using var flujo = Flujo(e, Carpeta("temp"), QueFalla(MotivoDeEscritura.SinEspacio));
        await flujo.GuardarAsync(new DestinoElegido(Carpeta("m"), TipoDeDestino.Extraible), "csv", "entrega_a_familias");
        await flujo.GuardarAsync(new DestinoElegido(Carpeta("m"), TipoDeDestino.Extraible), "csv", "entrega_a_familias");
        Assert.Equal(1, e.Autorizaciones);                                                            // la misma razón: se reutiliza
        await flujo.GuardarAsync(new DestinoElegido(Carpeta("m"), TipoDeDestino.Extraible), "csv", "reunion_de_equipo");
        Assert.Equal(2, e.Autorizaciones);
    }

    [Fact]
    public async Task UnArchivoQueEstaPorVencer_SeGeneraDeNuevoSolo_SinPedirleNadaALaPersona()
    {
        var e = new Escenario();
        using var flujo = Flujo(e, Carpeta("temp"), QueFalla(MotivoDeEscritura.MedioRetirado));
        await flujo.GuardarAsync(new DestinoElegido(Carpeta("m"), TipoDeDestino.Extraible), "csv", null);
        Assert.True(flujo.TieneArchivoListo);
        e.Ahora += e.Vigencia - (long)FlujoDeExportacion.Margen.TotalMilliseconds + 1;               // faltan menos de 45 s
        Assert.False(flujo.TieneArchivoListo);
        var destino = Carpeta("otra");
        var r = await new Func<Task<ResultadoDelGuardado>>(() => flujo.GuardarAsync(new DestinoElegido(destino, TipoDeDestino.Extraible), "csv", null))();
        Assert.Equal(EstadoDelGuardado.NoSePudoEscribir, r.Estado);                                   // sigue fallando el escritor de la prueba, pero…
        Assert.Equal(2, e.Autorizaciones);                                                            // …se autorizó de nuevo antes de escribir
    }

    // ================================================================================================== lo que el nodo no autoriza

    [Fact]
    public async Task SiElNodoNiegaElDestino_NoSeEscribeNada_YSeDiceQueElegir()
    {
        var e = new Escenario { NegarAutorizacion = (HttpStatusCode.Forbidden, """{"codigo":"destino_no_permitido","detail":"El administrador no permite guardar en memorias extraíbles."}""") };
        var destino = Carpeta("m");
        using var flujo = Flujo(e, Carpeta("temp"));
        var r = await flujo.GuardarAsync(new DestinoElegido(destino, TipoDeDestino.Extraible), "csv", null);
        Assert.Equal(EstadoDelGuardado.NoAutorizado, r.Estado);
        Assert.Contains("memorias extraíbles", r.Mensaje);
        Assert.Equal("Elige una carpeta de este equipo o de la red.", r.Accion);
        Assert.Equal("destino_no_permitido", r.ErrorDelNodo!.Codigo);
        Assert.Empty(Directory.GetFiles(destino));
        Assert.Empty(e.Confirmaciones);
        Assert.False(flujo.TieneArchivoListo);
    }

    [Theory]
    [InlineData("razon_requerida", "Vuelve a elegir y escoge para qué vas a guardarlo.")]
    [InlineData("sin_permiso", "Si lo necesitas, pídelo a la administración.")]
    [InlineData("fuera_de_alcance", "Si lo necesitas, pídelo a la administración.")]
    [InlineData("algo_nuevo", "Vuelve a intentarlo.")]
    public async Task CadaNegativaDelNodo_DiceQueHacer(string codigo, string accion)
    {
        var e = new Escenario { NegarAutorizacion = (HttpStatusCode.Forbidden, $$"""{"codigo":"{{codigo}}","detail":"Detalle del nodo."}""") };
        using var flujo = Flujo(e, Carpeta("temp"));
        var r = await flujo.GuardarAsync(new DestinoElegido(Carpeta("m"), TipoDeDestino.CarpetaLocal), "csv", null);
        Assert.Equal(EstadoDelGuardado.NoAutorizado, r.Estado);
        Assert.Equal(accion, r.Accion);
        Assert.False(string.IsNullOrWhiteSpace(r.Mensaje));
    }

    [Fact]
    public async Task SinConexionConElAula_NoSeGeneraNada_YSeDiceQueHacer()
    {
        var e = new Escenario { SinRed = true };
        var destino = Carpeta("m");
        using var flujo = Flujo(e, Carpeta("temp"));
        var r = await flujo.GuardarAsync(new DestinoElegido(destino, TipoDeDestino.Extraible), "csv", null);
        Assert.Equal(EstadoDelGuardado.SinConexion, r.Estado);
        Assert.Contains("No hay conexión con el aula", r.Mensaje);
        Assert.Equal("Cuando el aula vuelva a estar conectada, toca Guardar otra vez.", r.Accion);
        Assert.Empty(Directory.GetFiles(destino));
    }

    [Fact]
    public async Task UnArchivoQueLlegaDanado_SeDescarta_YNoSeEscribeNada()
    {
        var e = new Escenario { HuellaDeclarada = new string('a', 64) };
        var temporal = Carpeta("temp");
        var destino = Carpeta("m");
        using var flujo = Flujo(e, temporal);
        var r = await flujo.GuardarAsync(new DestinoElegido(destino, TipoDeDestino.Extraible), "csv", null);
        Assert.Equal(EstadoDelGuardado.ArchivoDanado, r.Estado);
        Assert.Contains("dañado", r.Mensaje);
        Assert.Empty(Directory.GetFiles(temporal));
        Assert.Empty(Directory.GetFiles(destino));
        Assert.Empty(e.Confirmaciones);
    }

    // ================================================================================================== escrito pero sin poder avisar

    [Fact]
    public async Task EscritoYVerificadoPeroSinConexion_ElArchivoSeDaPorBueno_YLaConfirmacionQuedaPendiente()
    {
        var e = new Escenario { AlConfirmar = _ => throw new HttpRequestException("se cayó la red") };
        var destino = Carpeta("m");
        using var flujo = Flujo(e, Carpeta("temp"));
        var r = await flujo.GuardarAsync(new DestinoElegido(destino, TipoDeDestino.Extraible), "csv", null);

        Assert.Equal(EstadoDelGuardado.GuardadoSinConfirmar, r.Estado);
        Assert.True(r.Escrito);
        Assert.True(File.Exists(r.RutaFinal));
        Assert.Contains("No hubo conexión con el aula para anotarlo", r.Mensaje);
        Assert.Contains("Avisar al aula", r.Accion);
        Assert.True(flujo.HayConfirmacionPendiente);

        e.AlConfirmar = null;                                                                          // vuelve la conexión
        var despues = await flujo.ReintentarConfirmacionAsync();
        Assert.Equal(EstadoDelGuardado.Guardado, despues.Estado);
        Assert.Equal(r.RutaFinal, despues.RutaFinal);
        Assert.False(flujo.HayConfirmacionPendiente);
        var ultima = e.Confirmaciones.Last();
        Assert.Equal(("guardado", Sha(e.Contenido)), (ultima.Json.GetProperty("resultado").GetString(), ultima.Json.GetProperty("huella_verificada").GetString()));
        Assert.Equal(1, e.Autorizaciones);
    }

    [Fact]
    public async Task SiElNodoDiceQueCaduco_ElArchivoSigueBueno_YNoHayNadaQueReintentar()
    {
        var e = new Escenario { AlConfirmar = _ => new HttpResponseMessage(HttpStatusCode.Conflict) { Content = new StringContent("""{"codigo":"exportacion_caducada","detail":"Caducó."}""", Encoding.UTF8, "application/json") } };
        using var flujo = Flujo(e, Carpeta("temp"));
        var r = await flujo.GuardarAsync(new DestinoElegido(Carpeta("m"), TipoDeDestino.CarpetaLocal), "csv", null);
        Assert.Equal(EstadoDelGuardado.GuardadoSinConfirmar, r.Estado);
        Assert.Contains("ya no lo puede anotar como entregado", r.Mensaje);
        Assert.Contains("guarda el reporte otra vez", r.Accion);
        Assert.False(flujo.HayConfirmacionPendiente);
        Assert.True(File.Exists(r.RutaFinal));
    }

    [Fact]
    public async Task SiYaQuedoEntregada_NoEsUnFallo()
    {
        var e = new Escenario { AlConfirmar = _ => new HttpResponseMessage(HttpStatusCode.Conflict) { Content = new StringContent("""{"codigo":"exportacion_ya_confirmada","detail":"Ya."}""", Encoding.UTF8, "application/json") } };
        using var flujo = Flujo(e, Carpeta("temp"));
        var r = await flujo.GuardarAsync(new DestinoElegido(Carpeta("m"), TipoDeDestino.CarpetaLocal), "csv", null);
        Assert.Equal(EstadoDelGuardado.Guardado, r.Estado);
        Assert.False(flujo.HayConfirmacionPendiente);
    }

    [Fact]
    public async Task ReintentarSinNadaPendiente_NoInventaNada()
    {
        var e = new Escenario();
        using var flujo = Flujo(e, Carpeta("temp"));
        var r = await flujo.ReintentarConfirmacionAsync();
        Assert.False(r.Escrito);
        Assert.Empty(e.Peticiones);
    }

    // ================================================================================================== cancelar, soltar y no repetir nombres

    [Fact]
    public async Task Cancelar_BorraElTemporal_YElNodoRecibeUnFallidoPorCancelacion()
    {
        var e = new Escenario();
        var temporal = Carpeta("temp");
        using var flujo = Flujo(e, temporal);
        using var cancelar = new CancellationTokenSource();
        cancelar.Cancel();
        var r = await flujo.GuardarAsync(new DestinoElegido(Carpeta("m"), TipoDeDestino.Extraible), "csv", null, null, cancelar.Token);
        Assert.Equal(EstadoDelGuardado.Cancelado, r.Estado);
        Assert.False(r.Escrito);
        Assert.Empty(Directory.GetFiles(temporal));
        Assert.False(flujo.TieneArchivoListo);
    }

    [Fact]
    public async Task SoltarElFlujo_BorraElTemporalQueQuedaba()
    {
        var e = new Escenario();
        var temporal = Carpeta("temp");
        var flujo = Flujo(e, temporal, QueFalla(MotivoDeEscritura.SinEspacio));
        await flujo.GuardarAsync(new DestinoElegido(Carpeta("m"), TipoDeDestino.Extraible), "csv", null);
        Assert.Single(Directory.GetFiles(temporal));
        flujo.Dispose();
        Assert.Empty(Directory.GetFiles(temporal));
        flujo.Dispose();                                                                               // dos veces no rompe nada
    }

    [Fact]
    public async Task GuardarDosVecesElMismoReporte_NoSobrescribe_LeAgregaElSufijo()
    {
        var e = new Escenario();
        var destino = Carpeta("m");
        using var flujo = Flujo(e, Carpeta("temp"));
        var uno = await flujo.GuardarAsync(new DestinoElegido(destino, TipoDeDestino.CarpetaLocal), "csv", null);
        var dos = await flujo.GuardarAsync(new DestinoElegido(destino, TipoDeDestino.CarpetaLocal), "csv", null);
        Assert.Equal(Path.Combine(destino, "reporte-grupo-8A-2026-10-15-1042.csv"), uno.RutaFinal);
        Assert.Equal(Path.Combine(destino, "reporte-grupo-8A-2026-10-15-1042 (2).csv"), dos.RutaFinal);
        Assert.Equal(2, Directory.GetFiles(destino).Length);
        Assert.Equal(2, e.Autorizaciones);                                                             // la primera se entregó: la segunda es un reporte nuevo
    }

    // ================================================================================================== el alcance

    [Fact]
    public async Task ElAlcanceNoGeneraNiRegistraNada()
    {
        var e = new Escenario();
        using var flujo = Flujo(e, Carpeta("temp"));
        var alcance = await flujo.AlcanceAsync("csv");
        Assert.True(alcance!.Nominal);
        Assert.StartsWith("Vas a guardar el reporte del grupo 8A", alcance.TextoAlcance);
        var peticion = Assert.Single(e.Peticiones);
        Assert.Equal("/api/reportes/exportaciones/alcance/", peticion.Ruta);
        Assert.Equal(0, e.Autorizaciones);
        Assert.False(flujo.TieneArchivoListo);
    }

    // ================================================================================================== lo que dejó la revisión independiente

    [Fact]
    public async Task SiLaHojaSeCierraAMitadDeLaEscritura_ElTemporalSeBorraDeTodasFormas()
    {
        // Cerrar la hoja cancela la escritura y suelta el flujo. El temporal (con nombres de alumnos) seguía abierto por quien escribía y el borrado fallaba en silencio: quedaba en la caché.
        var e = new Escenario();
        var temporal = Carpeta("temp");
        FlujoDeExportacion? flujo = null;
        Task<ResultadoDeEscritura> Escritor(Stream origen, string sha, long bytes, string carpeta, string nombre, IProgress<double>? progreso, CancellationToken ct)
        {
            flujo!.Dispose();                                                                         // la hoja se cierra con el origen todavía abierto…
            return Task.FromResult(new ResultadoDeEscritura(false, null, 0, null, MotivosDeEscritura.De(MotivoDeEscritura.Cancelado)));
        }
        flujo = Flujo(e, temporal, Escritor);

        await flujo.GuardarAsync(new DestinoElegido(Carpeta("memoria"), TipoDeDestino.Extraible), "csv", null);

        Assert.Empty(Directory.GetFiles(temporal));                                                   // …y aun así no queda ningún temporal
        Assert.False(flujo.TieneArchivoListo);
    }

    [Fact]
    public async Task UnDestinoQueFalla_SeAnotaConSuDetalleTecnico_PeroUnaCancelacionNo()
    {
        var e = new Escenario();
        var anotados = new List<(ResultadoDelGuardado Resultado, TipoDeDestino Tipo)>();
        var intento = 0;
        Task<ResultadoDeEscritura> Escritor(Stream origen, string sha, long bytes, string carpeta, string nombre, IProgress<double>? progreso, CancellationToken ct) =>
            Task.FromResult(new ResultadoDeEscritura(false, null, 0, null, MotivosDeEscritura.De(++intento == 1 ? MotivoDeEscritura.Otro : MotivoDeEscritura.Cancelado)) { Detalle = "IOException (0x8007045D): fallo de prueba" });
        using var flujo = new FlujoDeExportacion(e.Api(), "prof-1", ReporteSolicitado.DeGrupo("g-1"), Carpeta("temp"), Escritor, () => e.Ahora) { AlFallarLaEscritura = (r, tipo) => anotados.Add((r, tipo)) };

        var primero = await flujo.GuardarAsync(new DestinoElegido(Carpeta("m"), TipoDeDestino.Extraible), "csv", null);
        Assert.Equal(EstadoDelGuardado.NoSePudoEscribir, primero.Estado);
        var (anotado, tipo) = Assert.Single(anotados);
        Assert.Equal((MotivoDeEscritura.Otro, "IOException (0x8007045D): fallo de prueba", TipoDeDestino.Extraible), (anotado.Fallo!.Motivo, anotado.Detalle, tipo));

        var segundo = await flujo.GuardarAsync(new DestinoElegido(Carpeta("m2"), TipoDeDestino.Extraible), "csv", null);
        Assert.Equal(EstadoDelGuardado.Cancelado, segundo.Estado);
        Assert.Single(anotados);                                                                      // cancelar no es un fallo: no se anota
    }

    [Fact]
    public async Task SiAnotarElFalloMismoFalla_LaPersonaSigueViendoSuMensaje()
    {
        var e = new Escenario();
        using var flujo = new FlujoDeExportacion(e.Api(), "prof-1", ReporteSolicitado.DeGrupo("g-1"), Carpeta("temp"), QueFalla(MotivoDeEscritura.SinEspacio), () => e.Ahora)
        { AlFallarLaEscritura = (_, _) => throw new InvalidOperationException("el registro no se pudo escribir") };
        var r = await flujo.GuardarAsync(new DestinoElegido(Carpeta("m"), TipoDeDestino.Extraible), "csv", null);
        Assert.Equal(EstadoDelGuardado.NoSePudoEscribir, r.Estado);
        Assert.Equal(MotivoDeEscritura.SinEspacio, r.Fallo!.Motivo);
    }
}

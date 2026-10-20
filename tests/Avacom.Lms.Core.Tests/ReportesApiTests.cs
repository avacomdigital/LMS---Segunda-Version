using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text.Json;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// El cliente de <c>/api/reportes/</c> contra un nodo falso: método, URL y cuerpo de cada ruta del contrato (los campos nulos NO viajan, quien consulta manda <c>actor</c>) y, sobre todo,
/// la bajada del archivo exportado: directo a un temporal, con su SHA-256 comprobado contra el que declaró el nodo, y un motivo con nombre para cada cosa que pueda salir mal.
/// </summary>
[Collection("estado global")]
public sealed class ReportesApiTests : IDisposable
{
    private const string Base = "/api/reportes/";
    private readonly List<string> carpetas = [];

    public ReportesApiTests() => ClienteJson.Token = null;

    public void Dispose()
    {
        ClienteJson.Token = null;
        foreach (var c in carpetas) try { Directory.Delete(c, true); } catch (IOException) { /* el sistema la limpia */ }
    }

    private string Temporal()
    {
        var c = Ayudas.CarpetaTemporal();
        carpetas.Add(c);
        return c;
    }

    private sealed record Captura(HttpMethod Metodo, string Url, string? Cuerpo)
    {
        public JsonElement Json => Ayudas.Json(Cuerpo!);
        public string[] Claves => Json.EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal).ToArray();
    }

    private static (ReportesApi Api, List<Captura> Capturas) Api(Func<Captura, HttpResponseMessage> responder)
    {
        var capturas = new List<Captura>();
        var http = new HttpClient(new ManejadorFalso(async (req, _) =>
        {
            var cuerpo = req.Content is null ? null : await req.Content.ReadAsStringAsync();
            var captura = new Captura(req.Method, req.RequestUri!.PathAndQuery, cuerpo);
            capturas.Add(captura);
            return responder(captura);
        }));
        return (new ReportesApi(http, new Uri("http://192.168.0.55:8000/")), capturas);
    }

    private static (ReportesApi Api, List<Captura> Capturas) Api(HttpStatusCode estado = HttpStatusCode.OK, string json = "{}") => Api(_ => Ayudas.Respuesta(estado, json));

    // ---------------------------------------------------------------------------------------------- leer

    [Fact]
    public async Task Clases_EsUnGetConLosFiltrosQueSeDieron_SinCamposVacios()
    {
        var (api, capturas) = Api();
        await api.ClasesAsync("prof-1");
        await api.ClasesAsync("prof-1", new FiltroDeClases("g-1", 100, 200, 10, new NodoAcademico(Country: "Colombia", Grade: "8º")));
        await api.ClasesAsync("prof-1", new FiltroDeClases(Nodo: new NodoAcademico()));
        Assert.Equal(new[]
        {
            Base + "clases/?actor=prof-1",
            Base + "clases/?grupo_id=g-1&desde=100&hasta=200&limite=10&actor=prof-1&country=Colombia&grade=8%C2%BA",
            Base + "clases/?actor=prof-1",
        }, capturas.Select(c => c.Url).ToArray());
        Assert.All(capturas, c => Assert.Equal(HttpMethod.Get, c.Metodo));
    }

    [Fact]
    public async Task LosDemasReportes_SonGets_ConElActorAlFinalDeLaConsulta()
    {
        var (api, capturas) = Api();
        await api.ClaseAsync("prof-1", "s 1");
        await api.GrupoAsync("prof-1", "g-1");
        await api.GrupoAsync("prof-1", "g-1", new NodoAcademico(Subject: "Historia", Topic: "Los estados"));
        await api.AlumnosAsync("prof-1", "g-1");
        await api.AlumnoAsync("prof-1", "al-1");
        await api.AlumnoAsync("prof-1", "al-1", "g-1");
        await api.UsoAsync("rep-1");
        await api.UsoAsync("rep-1", new PeriodoPedido(1000, 2000), "g-1", new NodoAcademico(Country: "Perú"));
        await api.UsoAsync("rep-1", new PeriodoPedido(null, 2000));
        await api.FiltrosAsync("prof-1");
        await api.RecientesAsync("prof-1");
        await api.ConfiguracionAsync("adm-1");
        await api.EstadoAsync("adm-1");
        await api.ExportacionAsync("prof-1", "e 1");
        await api.ExportacionesAsync("prof-1");
        await api.BoletinAsync("prof-1", "al-1", "g-1");
        await api.BoletinAsync("prof-1", "al-1", null, new NodoAcademico(Subject: "math"));
        await api.BoletinesAsync("prof-1", "g-1");
        Assert.Equal(new[]
        {
            Base + "clases/s%201/?actor=prof-1",
            Base + "grupos/g-1/?actor=prof-1",
            Base + "grupos/g-1/?actor=prof-1&subject=Historia&topic=Los%20estados",
            Base + "alumnos/?grupo_id=g-1&actor=prof-1",
            Base + "alumnos/al-1/?actor=prof-1",
            Base + "alumnos/al-1/?grupo_id=g-1&actor=prof-1",
            Base + "uso/?actor=rep-1",
            Base + "uso/?desde=1000&hasta=2000&grupo_id=g-1&actor=rep-1&country=Per%C3%BA",
            Base + "uso/?hasta=2000&actor=rep-1",
            Base + "filtros/?actor=prof-1",
            Base + "recientes/?actor=prof-1",
            Base + "configuracion/?actor=adm-1",
            Base + "estado/?actor=adm-1",
            Base + "exportaciones/e%201/?actor=prof-1",
            Base + "exportaciones/?actor=prof-1",
            Base + "boletines/al-1/?grupo_id=g-1&actor=prof-1",
            Base + "boletines/al-1/?actor=prof-1&subject=math",
            Base + "boletines/?grupo_id=g-1&actor=prof-1",
        }, capturas.Select(c => c.Url).ToArray());
        Assert.All(capturas, c => { Assert.Equal(HttpMethod.Get, c.Metodo); Assert.Null(c.Cuerpo); });
    }

    [Fact]
    public async Task ElNombreDeUnaPersonaNuncaViajaEnLaRuta_SoloIdentificadores()
    {
        var (api, capturas) = Api();
        await api.AlumnoAsync("prof-1", "al-1", "g-1");
        await api.ClaseAsync("prof-1", "s-1");
        Assert.All(capturas, c => Assert.DoesNotMatch(@"(?i)nombre|apellido|q=", c.Url));
    }

    // ---------------------------------------------------------------------------------- configuración y agregados

    [Fact]
    public async Task CambiarLaConfiguracion_EsUnPutQueSoloManda_LoQueSeCambio()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"configuracion":{"version":4,"umbral_privacidad":true},"cambiado":true}""");
        var r = await api.CambiarConfiguracionAsync("adm-1", new CambioDeConfiguracion(UmbralPrivacidad: true, VersionEsperada: 3));
        Assert.True(r!.Cambiado);
        Assert.Equal(4, r.Configuracion.Version);
        await api.CambiarConfiguracionAsync("adm-1", new CambioDeConfiguracion(ExtraiblesPermitidos: false, ExigirRazon: true));
        var (primera, segunda) = (capturas[0], capturas[1]);
        Assert.Equal((HttpMethod.Put, Base + "configuracion/"), (primera.Metodo, primera.Url));
        Assert.Equal(new[] { "actor", "umbral_privacidad", "version_esperada" }, primera.Claves);
        Assert.True(primera.Json.GetProperty("umbral_privacidad").GetBoolean());
        Assert.Equal(3, primera.Json.GetProperty("version_esperada").GetInt32());
        Assert.Equal(new[] { "actor", "exigir_razon", "extraibles_permitidos" }, segunda.Claves);
        Assert.False(segunda.Json.GetProperty("extraibles_permitidos").GetBoolean());
        // los ajustes del boletín viajan igual: sólo lo que se cambia
        await api.CambiarConfiguracionAsync("adm-1", new CambioDeConfiguracion(PlantillaBoletin: "mx", PeriodosBoletin: ["1.er periodo", "2.º periodo"]));
        var tercera = capturas[2];
        Assert.Equal(new[] { "actor", "periodos_boletin", "plantilla_boletin" }, tercera.Claves);
        Assert.Equal("mx", tercera.Json.GetProperty("plantilla_boletin").GetString());
        Assert.Equal(2, tercera.Json.GetProperty("periodos_boletin").GetArrayLength());
    }

    [Fact]
    public void ElBoletinDeUnGrupo_SePideSinAlumno_YSeEntregaComoZip()
    {
        var grupo = ReporteSolicitado.DeBoletin("g-1").ACuerpo();
        Assert.Equal(new[] { "grupo_id", "tipo" }, grupo.Keys.OrderBy(k => k, StringComparer.Ordinal).ToArray());
        Assert.Equal(TiposDeReporte.Boletin, grupo["tipo"]);
        var alumno = ReporteSolicitado.DeBoletin("g-1", "al-1").ACuerpo();
        Assert.Equal("al-1", alumno["alumno_id"]);
        Assert.Equal("zip", FormatosDeExportacion.Extension(FormatosDeExportacion.Zip));          // el nodo entrega un zip con un archivo por estudiante
        Assert.Equal("xlsx", FormatosDeExportacion.Extension(FormatosDeExportacion.Xlsx));
    }

    [Fact]
    public async Task Actualizar_Y_Reconstruir_SonPostConElActor()
    {
        var (api, capturas) = Api();
        await api.ActualizarAsync("adm-1");
        await api.ReconstruirAsync("tec-1");
        Assert.Equal(new[] { (HttpMethod.Post, Base + "actualizar/"), (HttpMethod.Post, Base + "reconstruir/") }, capturas.Select(c => (c.Metodo, c.Url)).ToArray());
        Assert.Equal("adm-1", capturas[0].Json.GetProperty("actor").GetString());
        Assert.Equal("tec-1", capturas[1].Json.GetProperty("actor").GetString());
        Assert.All(capturas, c => Assert.Equal(new[] { "actor" }, c.Claves));
    }

    // ---------------------------------------------------------------------------------------------- exportar: alcance

    [Fact]
    public async Task Alcance_DescribeElReporteSinDestino_YLoNuloNoViaja()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"tipo":"clase","formato":"csv","nominal":true}""");
        var a = await api.AlcanceAsync("prof-1", ReporteSolicitado.DeClase("s-1"), "csv");
        Assert.Equal(("clase", "csv", true), (a!.Tipo, a.Formato, a.Nominal));
        await api.AlcanceAsync("prof-1", ReporteSolicitado.DeAlumno("al-1", "g-1", new NodoAcademico(Country: "Colombia")), "xlsx");
        await api.AlcanceAsync("prof-1", ReporteSolicitado.DeGrupo("g-1"), "xlsx");
        await api.AlcanceAsync("rep-1", ReporteSolicitado.DeUso(new PeriodoPedido(1000, null), "g-1"), "xlsx");
        Assert.All(capturas, c => Assert.Equal((HttpMethod.Post, Base + "exportaciones/alcance/"), (c.Metodo, c.Url)));
        Assert.All(capturas, c => Assert.Equal(new[] { "actor", "formato", "reporte" }, c.Claves));            // el alcance no elige destino ni razón: no genera nada
        Assert.Equal(new[] { "sesion_id", "tipo" }, Claves(capturas[0].Json.GetProperty("reporte")));
        Assert.Equal(new[] { "alumno_id", "country", "grupo_id", "tipo" }, Claves(capturas[1].Json.GetProperty("reporte")));
        Assert.Equal(new[] { "grupo_id", "tipo" }, Claves(capturas[2].Json.GetProperty("reporte")));
        var uso = capturas[3].Json.GetProperty("reporte");
        Assert.Equal(new[] { "desde", "grupo_id", "tipo" }, Claves(uso));
        Assert.Equal(1000, uso.GetProperty("desde").GetInt64());
    }

    private static string[] Claves(JsonElement objeto) => objeto.EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal).ToArray();

    // ---------------------------------------------------------------------------------------------- exportar: el archivo

    private static string Sha(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));

    private static HttpResponseMessage Archivo(byte[] cuerpo, string? huella = null, long? bytes = null, string id = "e-1", bool conCabeceras = true, string nombre = "reporte-grupo-8A-2026-10-15-1042.csv")
    {
        var r = new HttpResponseMessage(HttpStatusCode.Created) { Content = new ByteArrayContent(cuerpo) };
        r.Content.Headers.ContentType = new MediaTypeHeaderValue("text/csv") { CharSet = "utf-8" };
        if (!conCabeceras) return r;
        void Poner(string n, string v) => r.Headers.Add("X-Avacom-Export-" + n, v);
        Poner("Id", id);
        Poner("Tipo", "grupo");
        Poner("Formato", "csv");
        Poner("Huella", huella ?? Sha(cuerpo));
        Poner("Bytes", (bytes ?? cuerpo.Length).ToString());
        Poner("Filas", "11");
        Poner("Nombre", nombre);
        Poner("Expira-En", "1790003330000");
        Poner("Corte-En", "1790002430000");
        Poner("Nominal", "true");
        Poner("Umbral-Aplicado", "false");
        Poner("Destino", "extraible");
        return r;
    }

    private static byte[] Cuerpo(int bytes)
    {
        var datos = new byte[bytes];
        new Random(7).NextBytes(datos);
        return datos;
    }

    private sealed class Avance : IProgress<double>
    {
        public readonly List<double> Valores = [];
        public void Report(double valor) => Valores.Add(valor);
    }

    [Fact]
    public async Task AutorizarExportacion_BajaElArchivoAUnTemporal_ConLaHuellaVerificada()
    {
        var cuerpo = Cuerpo(300_000);                                                          // más de un bloque: el streaming parte la lectura
        var (api, capturas) = Api(_ => Archivo(cuerpo));
        var carpeta = Temporal();
        var avance = new Avance();
        using var archivo = await api.AutorizarExportacionAsync("prof-1", ReporteSolicitado.DeGrupo("g-1"), "csv", "extraible", "entrega_a_familias", carpeta, avance);
        Assert.NotNull(archivo);
        Assert.Null(api.UltimoError);
        Assert.Equal(("e-1", "grupo", "csv", 300_000L, 11), (archivo.Id, archivo.Tipo, archivo.Formato, archivo.Bytes, archivo.Filas));
        Assert.Equal(("reporte-grupo-8A-2026-10-15-1042.csv", Sha(cuerpo), "extraible"), (archivo.NombreArchivo, archivo.Huella, archivo.DestinoAutorizado));
        Assert.Equal((1790003330000L, 1790002430000L, true, false), (archivo.ExpiraEn, archivo.CorteEn, archivo.Nominal, archivo.UmbralAplicado));
        Assert.Equal(Path.Combine(carpeta, "e-1.parte"), archivo.RutaTemporal);
        Assert.Equal(cuerpo, await File.ReadAllBytesAsync(archivo.RutaTemporal));
        Assert.Equal(1.0, avance.Valores[^1]);
        Assert.True(avance.Valores.Count >= 3, "el avance debe ir creciendo mientras llega el archivo");
        Assert.Equal(avance.Valores.Order().ToArray(), avance.Valores.ToArray());
        var c = capturas.Single();
        Assert.Equal((HttpMethod.Post, Base + "exportaciones/"), (c.Metodo, c.Url));
        Assert.Equal(new[] { "actor", "destino_tipo", "formato", "razon_codigo", "reporte" }, c.Claves);
        Assert.Equal(("extraible", "entrega_a_familias"), (c.Json.GetProperty("destino_tipo").GetString(), c.Json.GetProperty("razon_codigo").GetString()));
    }

    [Fact]
    public async Task AutorizarExportacion_SinRazon_NoMandaRazon()
    {
        var (api, capturas) = Api(_ => Archivo(Cuerpo(10)));
        using var archivo = await api.AutorizarExportacionAsync("prof-1", ReporteSolicitado.DeClase("s-1"), "csv", "carpeta_local", null, Temporal());
        Assert.NotNull(archivo);
        Assert.Equal(new[] { "actor", "destino_tipo", "formato", "reporte" }, capturas.Single().Claves);
    }

    [Fact]
    public async Task LiberarElArchivo_BorraElTemporal_YPuedeHacerseDosVeces()
    {
        var (api, _) = Api(_ => Archivo(Cuerpo(1000)));
        var archivo = await api.AutorizarExportacionAsync("prof-1", ReporteSolicitado.DeGrupo("g-1"), "csv", "extraible", null, Temporal());
        Assert.True(File.Exists(archivo!.RutaTemporal));
        archivo.Dispose();
        Assert.False(File.Exists(archivo.RutaTemporal));
        archivo.Dispose();
    }

    [Fact]
    public async Task UnArchivoQueLlegaConOtraHuella_SeDescartaYSeDiceQueLlegoDanado()
    {
        var carpeta = Temporal();
        var (api, _) = Api(_ => Archivo(Cuerpo(5000), huella: new string('a', 64)));
        var archivo = await api.AutorizarExportacionAsync("prof-1", ReporteSolicitado.DeGrupo("g-1"), "csv", "extraible", null, carpeta);
        Assert.Null(archivo);
        Assert.Equal(("archivo_danado", -1), (api.UltimoError!.Codigo, api.UltimoError.Estado));
        Assert.False(string.IsNullOrWhiteSpace(api.UltimoMotivo));
        Assert.False(string.IsNullOrWhiteSpace(api.UltimoError.Sugerencia));
        Assert.Empty(Directory.GetFiles(carpeta));                                              // ni un temporal queda
        Assert.False(MensajesDeReportes.SinConexion(api.UltimoError));                           // dañado no es «el aula está apagada»
    }

    [Fact]
    public async Task UnaCancelacionDuranteLaBajada_NoDejaUnTemporalAMedias()
    {
        var carpeta = Temporal();
        var (api, _) = Api(_ => Archivo(Cuerpo(300_000)));
        using var cancelar = new CancellationTokenSource();
        cancelar.Cancel();
        try
        {
            using var archivo = await api.AutorizarExportacionAsync("prof-1", ReporteSolicitado.DeGrupo("g-1"), "csv", "extraible", null, carpeta, null, cancelar.Token);
            Assert.Null(archivo);                                                                // si el cliente la cuenta como «sin conexión», tampoco hay archivo
        }
        catch (OperationCanceledException)
        {
            // la cancelación puede salir como excepción: lo que importa es lo que quedó en disco
        }
        Assert.Empty(Directory.GetFiles(carpeta));
    }

    [Fact]
    public async Task UnArchivoMasCortoQueLoDeclarado_TambienSeDescarta()
    {
        var carpeta = Temporal();
        var cuerpo = Cuerpo(2000);
        var (api, _) = Api(_ => Archivo(cuerpo, bytes: 2500));
        Assert.Null(await api.AutorizarExportacionAsync("prof-1", ReporteSolicitado.DeGrupo("g-1"), "csv", "extraible", null, carpeta));
        Assert.Equal("archivo_danado", api.UltimoError!.Codigo);
        Assert.Empty(Directory.GetFiles(carpeta));
    }

    [Fact]
    public async Task UnArchivoSinSusDatosDeControl_NoSeGuardaConSeguridad()
    {
        var carpeta = Temporal();
        var (api, _) = Api(_ => Archivo(Cuerpo(100), conCabeceras: false));
        Assert.Null(await api.AutorizarExportacionAsync("prof-1", ReporteSolicitado.DeGrupo("g-1"), "csv", "extraible", null, carpeta));
        Assert.Equal("respuesta_incompleta", api.UltimoError!.Codigo);
        Assert.Empty(Directory.GetFiles(carpeta));
        var (api2, _) = Api(_ => Archivo(Cuerpo(100), huella: "corta"));
        Assert.Null(await api2.AutorizarExportacionAsync("prof-1", ReporteSolicitado.DeGrupo("g-1"), "csv", "extraible", null, carpeta));
        Assert.Equal("respuesta_incompleta", api2.UltimoError!.Codigo);
    }

    [Theory]
    [InlineData(@"..\..\afuera")]
    [InlineData("../afuera")]
    [InlineData("a:b")]
    [InlineData("con espacio")]
    [InlineData("a.b")]
    public async Task UnIdentificadorQueNoEsUnCodigo_NoSeUsaComoNombreDelTemporal(string id)
    {
        // El id da nombre al archivo temporal: una cabecera manipulada (el transporte es HTTP) no puede sacarlo de la carpeta ni borrar otra cosa.
        var carpeta = Temporal();
        var (api, _) = Api(_ => Archivo(Cuerpo(100), id: id));
        Assert.Null(await api.AutorizarExportacionAsync("prof-1", ReporteSolicitado.DeGrupo("g-1"), "csv", "extraible", null, carpeta));
        Assert.Equal("respuesta_incompleta", api.UltimoError!.Codigo);
        Assert.Empty(Directory.GetFileSystemEntries(carpeta));
        Assert.False(File.Exists(Path.Combine(Path.GetDirectoryName(carpeta)!, "afuera.parte")));
    }

    [Fact]
    public async Task UnUuid_EsUnIdentificadorValido()
    {
        var id = Guid.NewGuid().ToString();
        var (api, _) = Api(_ => Archivo(Cuerpo(100), id: id));
        using var archivo = await api.AutorizarExportacionAsync("prof-1", ReporteSolicitado.DeGrupo("g-1"), "csv", "extraible", null, Temporal());
        Assert.NotNull(archivo);
        Assert.Equal(id + ".parte", Path.GetFileName(archivo.RutaTemporal));
    }

    [Fact]
    public async Task LiberarUnArchivoQueEstaEnUso_NoLoDaPorLiberado_YLoVuelveAIntentar()
    {
        // Un temporal con nombres de alumnos no puede quedarse porque alguien lo tenía abierto en el momento de borrarlo: la próxima liberación lo termina.
        var (api, _) = Api(_ => Archivo(Cuerpo(1000)));
        var archivo = await api.AutorizarExportacionAsync("prof-1", ReporteSolicitado.DeGrupo("g-1"), "csv", "extraible", null, Temporal());
        var ruta = archivo!.RutaTemporal;
        var abierto = new FileStream(ruta, FileMode.Open, FileAccess.Read, FileShare.Read);       // sin FileShare.Delete: Windows no deja borrarlo
        archivo.Dispose();
        Assert.True(File.Exists(ruta));                                                           // no se pudo… y no lo dio por hecho
        abierto.Dispose();
        archivo.Dispose();
        Assert.False(File.Exists(ruta));
    }

    [Fact]
    public async Task SiElNodoLaNiega_DejaElCodigoYNoCreaNada()
    {
        var carpeta = Temporal();
        var (api, _) = Api(HttpStatusCode.Forbidden, """{"codigo":"destino_no_permitido","detail":"El administrador no permite guardar en memorias extraíbles."}""");
        Assert.Null(await api.AutorizarExportacionAsync("prof-1", ReporteSolicitado.DeGrupo("g-1"), "csv", "extraible", null, carpeta));
        Assert.Equal((403, "destino_no_permitido"), (api.UltimoError!.Estado, api.UltimoError.Codigo));
        Assert.Equal("El administrador no permite guardar en memorias extraíbles.", api.UltimoMotivo);
        Assert.Empty(Directory.GetFiles(carpeta));
        Assert.Contains("memorias extraíbles", MensajesDeReportes.De(api.UltimoError));
    }

    [Fact]
    public async Task SinRed_DiceQueNoHayConexionConElAula()
    {
        var http = new HttpClient(new ManejadorFalso((_, _) => throw new HttpRequestException("sin red")));
        var api = new ReportesApi(http, new Uri("http://192.168.0.55:8000/"));
        Assert.Null(await api.AutorizarExportacionAsync("prof-1", ReporteSolicitado.DeGrupo("g-1"), "csv", "extraible", null, Temporal()));
        Assert.Equal(("sin_conexion", 0), (api.UltimoError!.Codigo, api.UltimoError.Estado));
        Assert.True(MensajesDeReportes.SinConexion(api.UltimoError));
    }

    [Fact]
    public async Task SiNoSePuedeCrearLaCarpetaTemporal_SeDiceSinTemporal_YElNodoNoSabeNada()
    {
        var carpeta = Temporal();
        var ocupada = Path.Combine(carpeta, "es-un-archivo");
        await File.WriteAllTextAsync(ocupada, "no soy una carpeta");
        var (api, capturas) = Api(_ => Archivo(Cuerpo(100)));
        Assert.Null(await api.AutorizarExportacionAsync("prof-1", ReporteSolicitado.DeGrupo("g-1"), "csv", "extraible", null, ocupada));
        Assert.Equal(("sin_temporal", -1), (api.UltimoError!.Codigo, api.UltimoError.Estado));
        Assert.False(string.IsNullOrWhiteSpace(MensajesDeReportes.De(api.UltimoError)));
        Assert.Single(capturas);                                                                 // sólo la autorización: nada se confirma ni se avisa como entregado
    }

    // ---------------------------------------------------------------------------------------------- exportar: segundo tiempo

    [Fact]
    public async Task ConfirmarGuardado_MandaLaHuellaQueSeVerificoReleyendoElArchivo()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"exportacion":{"id":"e-1","estado":"entregada"},"reintento":false}""");
        var r = await api.ConfirmarGuardadoAsync("prof-1", "e-1", "carpeta_local", new string('b', 64));
        Assert.Equal(EstadosDeExportacion.Entregada, r!.Exportacion.Estado);
        var c = capturas.Single();
        Assert.Equal((HttpMethod.Post, Base + "exportaciones/e-1/confirmar/"), (c.Metodo, c.Url));
        Assert.Equal(new[] { "actor", "destino_tipo", "huella_verificada", "resultado" }, c.Claves);
        Assert.Equal(("guardado", "carpeta_local", new string('b', 64)),
            (c.Json.GetProperty("resultado").GetString(), c.Json.GetProperty("destino_tipo").GetString(), c.Json.GetProperty("huella_verificada").GetString()));
    }

    [Fact]
    public async Task ConfirmarFallo_MandaSoloElMotivoDeLaListaCerrada_NuncaLaRuta()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"exportacion":{"id":"e-1","estado":"autorizada"},"reintento":false}""");
        var r = await api.ConfirmarFalloAsync("prof-1", "e-1", "extraible", MotivosDeEscritura.Codigo(MotivoDeEscritura.MedioRetirado));
        Assert.Equal(EstadosDeExportacion.Autorizada, r!.Exportacion.Estado);
        var c = capturas.Single();
        Assert.Equal((HttpMethod.Post, Base + "exportaciones/e-1/confirmar/"), (c.Metodo, c.Url));
        Assert.Equal(new[] { "actor", "destino_tipo", "motivo", "resultado" }, c.Claves);
        Assert.Equal(("fallido", "extraible", "medio_retirado"),
            (c.Json.GetProperty("resultado").GetString(), c.Json.GetProperty("destino_tipo").GetString(), c.Json.GetProperty("motivo").GetString()));
        Assert.DoesNotContain(":\\", c.Cuerpo!);
    }

    [Fact]
    public async Task ConfirmarUnaExportacionCaducada_DiceQueSeGenereDeNuevo()
    {
        var (api, _) = Api(HttpStatusCode.Gone, """{"codigo":"exportacion_caducada","detail":"La exportación caducó."}""");
        Assert.Null(await api.ConfirmarGuardadoAsync("prof-1", "e-1", "carpeta_local", new string('c', 64)));
        Assert.Equal("exportacion_caducada", api.UltimoError!.Codigo);
        Assert.Contains("Genera el reporte de nuevo", MensajesDeReportes.De(api.UltimoError));
    }
}

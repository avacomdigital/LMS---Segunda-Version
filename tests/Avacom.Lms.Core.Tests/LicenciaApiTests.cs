using System.Net;
using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// El cliente de <c>/api/licencia/</c> (MOD-018) contra un nodo falso que responde con las respuestas REALES capturadas: método, URL y cuerpo de cada ruta (quien actúa manda <c>actor</c>;
/// el archivo viaja como texto <c>licencia</c> o como <c>archivo_b64</c>), y lo que queda en <c>UltimoError</c> ante cada error. Y el texto COMÚN de los dos 402: cualquier cliente (aquí,
/// el de reportes y el de acceso) lo deja como motivo sin que ninguna pantalla lo parchee.
/// </summary>
[Collection("estado global")]
public sealed class LicenciaApiTests : IDisposable
{
    private const string Base = "/api/licencia/";

    public LicenciaApiTests() => ClienteJson.Token = null;

    public void Dispose() => ClienteJson.Token = null;

    private static string Fixture(string nombre) => File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "licencia", nombre + ".json"));
    private static byte[] Archivo(string nombre) => File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "Fixtures", "licencia", nombre));

    private sealed record Captura(HttpMethod Metodo, string Url, string? Cuerpo)
    {
        public JsonElement Json => Ayudas.Json(Cuerpo!);
        public string[] Claves => Json.EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal).ToArray();
    }

    private static (HttpClient Http, List<Captura> Capturas) Nodo(Func<Captura, HttpResponseMessage> responder)
    {
        var capturas = new List<Captura>();
        var http = new HttpClient(new ManejadorFalso(async (req, _) =>
        {
            var cuerpo = req.Content is null ? null : await req.Content.ReadAsStringAsync();
            var captura = new Captura(req.Method, req.RequestUri!.PathAndQuery, cuerpo);
            capturas.Add(captura);
            return responder(captura);
        }));
        return (http, capturas);
    }

    private static (LicenciaApi Api, List<Captura> Capturas) Api(Func<Captura, HttpResponseMessage> responder)
    {
        var (http, capturas) = Nodo(responder);
        return (new LicenciaApi(http, new Uri("http://192.168.0.55:8000/")), capturas);
    }

    private static (LicenciaApi Api, List<Captura> Capturas) Api(HttpStatusCode estado, string json) => Api(_ => Ayudas.Respuesta(estado, json));

    // ---------------------------------------------------------------------------------------------------- leer

    [Fact]
    public async Task LasLecturas_SonGets_ConElActorEnLaConsulta()
    {
        var (api, capturas) = Api(c => Ayudas.Respuesta(HttpStatusCode.OK, c.Url switch
        {
            var u when u.StartsWith(Base + "estado/") => Fixture("estado_activa"),
            var u when u.StartsWith(Base + "consumo/") => Fixture("consumo"),
            var u when u.StartsWith(Base + "capacidades/") => Fixture("capacidades"),
            _ => Fixture("copia"),
        }));
        var estado = await api.EstadoAsync("adm 1");
        var consumo = await api.ConsumoAsync("adm 1");
        var capacidades = await api.CapacidadesAsync("adm 1");
        var copia = await api.CopiaAsync("adm 1");
        Assert.Equal(new[] { Base + "estado/?actor=adm%201", Base + "consumo/?actor=adm%201", Base + "capacidades/?actor=adm%201", Base + "copia/?actor=adm%201" },
            capturas.Select(c => c.Url).ToArray());
        Assert.All(capturas, c => Assert.Equal(HttpMethod.Get, c.Metodo));
        Assert.Equal(EstadosDeLicencia.Activa, estado!.Estado);
        Assert.Equal(1, consumo!.Equipos!.EnUso);
        Assert.False(capacidades!.Restringe);
        Assert.EndsWith(".avlic", copia!.Nombre);
        Assert.Null(api.UltimoError);
    }

    [Fact]
    public async Task SinActor_NoViajaLaConsulta()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, Fixture("estado_activa"));
        await api.EstadoAsync(string.Empty);
        Assert.Equal(Base + "estado/", capturas.Single().Url);
    }

    // ---------------------------------------------------------------------------------------------------- actuar

    [Fact]
    public async Task LaSolicitudLaLiberacionYLaFecha_SonPostsConElActor()
    {
        var (api, capturas) = Api(c => c.Url switch
        {
            Base + "solicitud/" => Ayudas.Respuesta(HttpStatusCode.Created, Fixture("solicitud")),
            Base + "liberar/" => Ayudas.Respuesta(HttpStatusCode.Created, Fixture("liberar")),
            _ => Ayudas.Respuesta(HttpStatusCode.OK, Fixture("reloj_confirmar")),
        });
        var solicitud = await api.SolicitudAsync("tec-1");
        var liberacion = await api.LiberarAsync("tec-1");
        var fecha = await api.ConfirmarRelojAsync("tec-1");
        Assert.Equal(new[] { Base + "solicitud/", Base + "liberar/", Base + "reloj/confirmar/" }, capturas.Select(c => c.Url).ToArray());
        Assert.All(capturas, c =>
        {
            Assert.Equal(HttpMethod.Post, c.Metodo);
            Assert.Equal(["actor"], c.Claves);
            Assert.Equal("tec-1", c.Json.GetProperty("actor").GetString());
        });
        Assert.Equal(NivelesDeHuella.Hardware, solicitud!.Nivel);
        Assert.Equal(("a7a7a7a7-0001-4000-8000-000000000001", 2), (liberacion!.Archivo.LicenciaId, liberacion.Archivo.Serie));
        Assert.Equal(EstadosDeLicencia.SinLicencia, liberacion.Estado.Estado);
        Assert.Equal(liberacion.Archivo.Sha256, Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(liberacion.Archivo.Bytes())));
        Assert.Empty(fecha!.BanderasActivas);
    }

    [Fact]
    public async Task ActivarConLosBytesDelAvlic_ViajaComoArchivoB64()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, Fixture("activar"));
        var bytes = Archivo("ejemplo.avlic");
        var r = await api.ActivarAsync("adm-1", bytes);
        var c = capturas.Single();
        Assert.Equal((HttpMethod.Post, Base + "activar/"), (c.Metodo, c.Url));
        Assert.Equal(["actor", "archivo_b64"], c.Claves);
        Assert.Equal(bytes, Convert.FromBase64String(c.Json.GetProperty("archivo_b64").GetString()!));
        Assert.Equal(AccionesDeInstalacion.Activada, r!.Accion);
    }

    [Fact]
    public async Task ActivarConUnArchivoEnFormaDeTexto_ViajaComoTexto_SinLaMarcaUtf8NiLosSaltos()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, Fixture("activar"));
        var texto = File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "licencia", "ejemplo-texto.avlic")).Trim();
        var conMarca = new byte[] { 0xEF, 0xBB, 0xBF }.Concat(Encoding.ASCII.GetBytes("  " + texto + "\r\n")).ToArray();
        await api.ActivarAsync("adm-1", conMarca);
        var c = capturas.Single();
        Assert.Equal(["actor", "licencia"], c.Claves);
        Assert.Equal(texto, c.Json.GetProperty("licencia").GetString());
    }

    [Theory]
    [InlineData("AVL1.QVZMQw", "licencia", "AVL1.QVZMQw")]
    [InlineData("  AVL1.QVZMQw \n", "licencia", "AVL1.QVZMQw")]
    [InlineData("﻿AVL1.QVZMQw", "licencia", "AVL1.QVZMQw")]
    [InlineData("QVZMQwABBWRl", "archivo_b64", "QVZMQwABBWRl")]
    [InlineData(" QVZMQwABBWRl ", "archivo_b64", "QVZMQwABBWRl")]
    public void ConUnTexto_ElCampoDependeDeSiEsLaFormaDeTexto(string entrada, string campo, string valor)
    {
        Assert.Equal((campo, valor), LicenciaApi.CampoDeInstalacion(entrada));
    }

    [Fact]
    public async Task Renovar_UsaSuPropiaRuta()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, Fixture("renovar"));
        var r1 = await api.RenovarAsync("adm-1", Archivo("ejemplo.avlic"));
        var r2 = await api.RenovarAsync("adm-1", "AVL1.QVZMQw");
        Assert.All(capturas, c => Assert.Equal((HttpMethod.Post, Base + "renovar/"), (c.Metodo, c.Url)));
        Assert.Equal(["actor", "archivo_b64"], capturas[0].Claves);
        Assert.Equal(["actor", "licencia"], capturas[1].Claves);
        Assert.Equal((AccionesDeInstalacion.Renovada, 2), (r1!.Accion, r1.Licencia!.Serie));
        Assert.NotNull(r2);
    }

    [Fact]
    public async Task UnaLiberacionSinElArchivo_NoSeDaPorBuena_YLoDice()
    {
        var (api, _) = Api(HttpStatusCode.Created, Fixture("estado_tras_liberar"));      // el estado sin el .avrel
        Assert.Null(await api.LiberarAsync("adm-1"));
        Assert.Equal((-1, "respuesta_incompleta"), (api.UltimoError!.Estado, api.UltimoError.Codigo));
        Assert.Contains("liberó", api.UltimoMotivo);
    }

    // ---------------------------------------------------------------------------------------------------- los errores, tal como los dejó el nodo

    [Theory]
    [InlineData("error_firma_invalida", 400, CodigosDeLicencia.LicenciaInvalida)]
    [InlineData("error_texto_invalido", 400, CodigosDeLicencia.LicenciaInvalida)]
    [InlineData("error_sin_cuerpo", 400, CodigosDeLicencia.DatosInvalidos)]
    [InlineData("error_otra_licencia", 400, CodigosDeLicencia.LicenciaInvalida)]
    [InlineData("error_serie_no_posterior", 400, CodigosDeLicencia.LicenciaInvalida)]
    [InlineData("error_aun_no_vigente", 400, CodigosDeLicencia.LicenciaInvalida)]
    [InlineData("error_sin_licencia_para_renovar", 400, CodigosDeLicencia.LicenciaInvalida)]
    [InlineData("error_sin_permiso", 403, CodigosDeLicencia.SinPermiso)]
    [InlineData("error_sin_permiso_renovar", 403, CodigosDeLicencia.SinPermiso)]
    [InlineData("error_sin_licencia_para_copiar", 404, CodigosDeLicencia.NoEncontrado)]
    [InlineData("error_huella_no_coincide", 409, CodigosDeLicencia.HuellaNoCoincide)]
    [InlineData("error_sin_licencia_para_liberar", 409, CodigosDeLicencia.Conflicto)]
    [InlineData("error_sesion_requerida", 401, null)]
    public async Task UnErrorDelNodo_NoEsUnaExcepcion_QuedaEnUltimoError_YTieneSuTexto(string fixture, int estado, string? codigo)
    {
        var (api, _) = Api((HttpStatusCode)estado, Fixture(fixture));
        Assert.Null(await api.ActivarAsync("adm-1", Archivo("ejemplo.avlic")));
        var e = api.UltimoError!;
        Assert.Equal((estado, codigo), (e.Estado, e.Codigo));
        Assert.False(e.PorLicencia);
        Assert.Equal(Ayudas.Json(Fixture(fixture)).GetProperty("detail").GetString(), e.Detalle);     // los que no son 402 conservan el texto del nodo
        var m = LicenciaTexto.DeError(e);
        Assert.False(string.IsNullOrWhiteSpace(m.Titulo));
        Assert.False(string.IsNullOrWhiteSpace(m.Texto));
        Assert.False(string.IsNullOrWhiteSpace(m.Accion));
        Assert.DoesNotContain(codigo ?? "codigo_inexistente", m.Completo);                      // nunca el código en pantalla
    }

    [Fact]
    public async Task SinConexion_EsEstadoCero_YSeDiceSinCulparANadie()
    {
        var http = new HttpClient(new ManejadorFalso((_, _) => throw new HttpRequestException("apagado")));
        var api = new LicenciaApi(http, new Uri("http://192.168.0.55:8000/"));
        Assert.Null(await api.EstadoAsync("adm-1"));
        Assert.Equal(0, api.UltimoError!.Estado);
        Assert.Equal("Sin conexión con el aula", LicenciaTexto.DeError(api.UltimoError).Titulo);
    }

    // ---------------------------------------------------------------------------------------------------- los 402: el texto común, en cualquier cliente

    [Theory]
    [InlineData("error_modulo_no_disponible")]
    [InlineData("error_cupo_equipos")]
    [InlineData("error_cupo_usuarios")]
    public async Task Un402DeLicencia_EnCualquierCliente_DejaElTextoComunComoMotivo_YConservaLosDatos(string fixture)
    {
        var (http, _) = Nodo(_ => Ayudas.Respuesta(HttpStatusCode.PaymentRequired, Fixture(fixture)));
        var reportes = new ReportesApi(http, new Uri("http://192.168.0.55:8000/"));
        Assert.Null(await reportes.ClasesAsync("prof-1"));
        var e = reportes.UltimoError!;
        Assert.Equal(402, e.Estado);
        Assert.True(e.PorLicencia);
        var comun = LicenciaTexto.ParaError(e)!;
        Assert.Equal(comun, e.Detalle);
        Assert.Equal(comun, reportes.UltimoMotivo);
        Assert.Equal(Ayudas.Json(Fixture(fixture)).GetProperty("detail").GetString(), e.Texto("detail"));      // el texto del nodo sigue en los extras
        // Las pantallas de reportes, que muestran el detalle de lo que no conocen, dicen el texto común sin haberse tocado:
        Assert.Equal(comun, MensajesDeReportes.De(e));
    }

    [Fact]
    public async Task ElCupoDeUsuarios_EnElAccesoDelAlumno_DiceAQuienPedirAyuda()
    {
        var (http, _) = Nodo(_ => Ayudas.Respuesta(HttpStatusCode.PaymentRequired, Fixture("error_cupo_usuarios")));
        var acceso = new AccesoApi(http, new Uri("http://192.168.0.55:8000/"));
        Assert.Null(await acceso.ConfiguracionAsync());
        var e = acceso.UltimoError!;
        Assert.True(e.EsCupoAgotado);
        var alumno = MensajesDeAcceso.Texto(e, Audiencia.Alumno);
        Assert.Equal(LicenciaTexto.ParaError(e, Audiencia.Alumno), alumno);
        Assert.Contains("profesor", alumno);
        Assert.DoesNotContain("cupo", alumno);                                                      // al alumno no se le habla de licencias
        var personal = MensajesDeAcceso.Texto(e);
        Assert.Contains("4 de 4", personal);
        Assert.Contains("ampliar la licencia", personal);
    }

    [Fact]
    public void UnCodigoDeLicenciaQueNoEsUn402_NoEsDeLicencia()
    {
        var falso = new Avacom.Lms.Core.Models.ErrorAula(403, "cupo_agotado", "x", null, null);
        Assert.False(falso.PorLicencia);
        Assert.Null(LicenciaTexto.ParaError(falso));
        var otro402 = new Avacom.Lms.Core.Models.ErrorAula(402, "otra_cosa", "x", null, null);
        Assert.False(otro402.PorLicencia);
    }
}

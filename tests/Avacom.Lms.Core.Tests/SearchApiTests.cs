using System.Net;
using System.Text.Json;
using Avacom.Lms.Core.Search;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// El cliente de <c>/api/search/</c> contra un nodo falso: método, URL y cuerpo de cada ruta — los valores vacíos NO viajan, el profesor manda <c>actor</c> — y los errores con su código.
/// </summary>
[Collection("estado global")]
public sealed class SearchApiTests : IDisposable
{
    private const string Base = "/api/search/";

    public SearchApiTests() => ClienteJson.Token = null;
    public void Dispose() => ClienteJson.Token = null;

    private sealed record Captura(HttpMethod Metodo, string Url, string? Cuerpo)
    {
        public JsonElement Json => Ayudas.Json(Cuerpo!);
    }

    private static (SearchApi Api, List<Captura> Capturas) Api(HttpStatusCode estado = HttpStatusCode.OK, string json = "{}")
    {
        var capturas = new List<Captura>();
        var http = new HttpClient(new ManejadorFalso(async (req, _) =>
        {
            capturas.Add(new Captura(req.Method, req.RequestUri!.PathAndQuery, req.Content is null ? null : await req.Content.ReadAsStringAsync()));
            return Ayudas.Respuesta(estado, json);
        }));
        return (new SearchApi(http, new Uri("http://192.168.0.55:8000/")), capturas);
    }

    [Fact]
    public async Task Buscar_EsUnGetConElTextoYSoloLosFiltrosQueSeDieron()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"query":"fracciones","normalized":"fracciones","total":0,"total_exact":true,"page":1,"page_size":20,"has_more":false,"results":[],"match_mode":"all","index_status":"consultable","index_notice":""}""");
        var r = await api.BuscarAsync("prof-1", new ConsultaDeBusqueda("  fracciones "));
        Assert.Equal(0, r!.Total);
        await api.BuscarAsync("prof-1", new ConsultaDeBusqueda("suma de fracciones", [TiposDeBusqueda.Curso, TiposDeBusqueda.Clase], Pais: "CO", Nivel: "primary", Grado: "4", Materia: "math",
            Periodo: "2026", GrupoId: "g 1", Pagina: 2, Limite: 10));
        Assert.Equal(Base + "?q=fracciones&actor=prof-1", capturas[0].Url);
        Assert.Equal(Base + "?q=suma%20de%20fracciones&type=course%2Cclass&country=CO&level=primary&grade=4&subject=math&period=2026&group=g%201&page=2&limit=10&actor=prof-1", capturas[1].Url);
        Assert.All(capturas, c => Assert.Equal(HttpMethod.Get, c.Metodo));
    }

    [Fact]
    public async Task Buscar_ConTildesYEnies_ViajaCodificado()
    {
        var (api, capturas) = Api();
        await api.BuscarAsync("p", new ConsultaDeBusqueda("año pequeño"));
        Assert.Equal(Base + "?q=a%C3%B1o%20peque%C3%B1o&actor=p", capturas[0].Url);
    }

    [Fact]
    public async Task Filtros_Y_Estado_SonGets()
    {
        var (api, capturas) = Api();
        await api.FiltrosAsync("prof-1");
        await api.EstadoAsync("prof-1");
        Assert.Equal(new[] { Base + "filters/?actor=prof-1", Base + "status/?actor=prof-1" }, capturas.Select(c => c.Url).ToArray());
        Assert.All(capturas, c => Assert.Equal(HttpMethod.Get, c.Metodo));
    }

    [Fact]
    public async Task Abrir_EsUnPostConLoQueIdentificaAlResultado_SinCamposVacios()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"allowed":true,"verified":true,"navigation_target":{"entity_type":"lesson","entity_id":"l1","course_ref":"c","lesson_ref":"l1","source":"biblioteca"}}""");
        var r = await api.AbrirAsync("prof-1", new DestinoDeNavegacion(TiposDeBusqueda.Leccion, "l1", CursoRef: "c", LeccionRef: "l1"));
        Assert.True(r!.Permitido);
        Assert.Equal(HttpMethod.Post, capturas[0].Metodo);
        Assert.Equal(Base + "open/", capturas[0].Url);
        Assert.Equal(new[] { "actor", "course_ref", "entity_id", "entity_type", "lesson_ref" }, capturas[0].Json.EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal).ToArray());
    }

    [Fact]
    public async Task UnErrorNoEsUnaExcepcion_DevuelveNullConSuCodigo()
    {
        var (api, _) = Api(HttpStatusCode.BadRequest, """{"detail":"Escribe qué quieres buscar.","codigo":"consulta_vacia"}""");
        Assert.Null(await api.BuscarAsync("prof-1", new ConsultaDeBusqueda("")));
        Assert.Equal(("consulta_vacia", 400), (api.UltimoError!.Codigo, api.UltimoError.Estado));
        Assert.Equal("Escribe qué quieres buscar.", api.UltimoMotivo);
        var (sin, _) = Api(HttpStatusCode.NotFound, """{"detail":"Ese resultado ya no está disponible.","codigo":"no_disponible"}""");
        Assert.Null(await sin.AbrirAsync("prof-1", new DestinoDeNavegacion(TiposDeBusqueda.Evaluacion, "x")));
        Assert.Equal("no_disponible", sin.UltimoError!.Codigo);
    }

    [Fact]
    public async Task ConElNodoApagado_ElEstadoEsCero()
    {
        var api = new SearchApi(new HttpClient(new ManejadorFalso((_, _) => throw new HttpRequestException("sin red"))), new Uri("http://192.168.0.55:8000/"));
        Assert.Null(await api.BuscarAsync("prof-1", new ConsultaDeBusqueda("fracciones")));
        Assert.Equal(0, api.UltimoError!.Estado);
        Assert.Contains("No hay conexión", BusquedaTexto.Error(api.UltimoError, api.UltimoMotivo).Titulo);
    }

    [Fact]
    public async Task LaSesionViajaComoPase()
    {
        ClienteJson.Token = "jwt-de-prueba";
        string? autorizacion = null;
        var http = new HttpClient(new ManejadorFalso((req, _) =>
        {
            autorizacion = req.Headers.Authorization?.ToString();
            return Task.FromResult(Ayudas.Respuesta(HttpStatusCode.OK, "{}"));
        }));
        await new SearchApi(http, new Uri("http://192.168.0.55:8000/")).EstadoAsync("prof-1");
        Assert.Equal("Bearer jwt-de-prueba", autorizacion);
    }
}

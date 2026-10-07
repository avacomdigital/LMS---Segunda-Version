using System.Net;
using System.Net.Http.Headers;
using System.Text;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// Bugfix 01 (QA-27): el reproductor dice «formato no compatible» (MediaError 4) también cuando el servidor contesta 401 o 404. El sondeo averigua qué
/// contestó de verdad el equipo del aula para que la pantalla y el archivo de fallos digan la causa real.
/// </summary>
public sealed class DiagnosticoDeMedioTests
{
    private sealed class Falso(Func<HttpRequestMessage, HttpResponseMessage> responder) : HttpMessageHandler
    {
        public List<HttpRequestMessage> Peticiones { get; } = [];

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Peticiones.Add(request);
            return Task.FromResult(responder(request));
        }
    }

    private static HttpResponseMessage Json(HttpStatusCode estado, string cuerpo) =>
        new(estado) { Content = new StringContent(cuerpo, Encoding.UTF8, "application/json") };

    private static readonly Uri Medio = new("http://aula.local:8000/api/m/pase.firma.x/aula/cursos/c/medios/vid-changes/?fuente=biblioteca");

    [Fact]
    public async Task Un_401_con_pase_vencido_dice_que_la_sesion_termino_y_no_que_el_formato_falla()
    {
        var falso = new Falso(_ => Json(HttpStatusCode.Unauthorized, """{"detail":"x","codigo":"pase_de_medios_vencido"}"""));
        var sondeo = await DiagnosticoDeMedio.SondearAsync(Medio, new HttpClient(falso));
        Assert.Equal(401, sondeo.Estado);
        Assert.Equal("pase_de_medios_vencido", sondeo.Codigo);
        Assert.False(sondeo.Entrega);
        Assert.Contains("sesión terminó", sondeo.Causa);
        Assert.DoesNotContain("formato", sondeo.Causa);
        Assert.Equal("HTTP 401 pase_de_medios_vencido", sondeo.Resumen);
    }

    [Fact]
    public async Task Pide_solo_el_primer_byte_y_con_pase_en_el_camino_no_manda_Authorization()
    {
        var falso = new Falso(_ => Json(HttpStatusCode.NotFound, """{"codigo":"referencia_no_encontrada"}"""));
        var anterior = ClienteJson.Token;
        ClienteJson.Token = "jwt-de-prueba";
        try { await DiagnosticoDeMedio.SondearAsync(Medio, new HttpClient(falso)); }
        finally { ClienteJson.Token = anterior; }
        var peticion = Assert.Single(falso.Peticiones);
        Assert.Equal(new RangeHeaderValue(0, 0), peticion.Headers.Range);
        Assert.Null(peticion.Headers.Authorization);
    }

    [Fact]
    public async Task Sin_pase_en_la_ruta_si_manda_el_Bearer_de_la_sesion()
    {
        var falso = new Falso(_ => Json(HttpStatusCode.NotFound, "{}"));
        var anterior = ClienteJson.Token;
        ClienteJson.Token = "jwt-de-prueba";
        try { await DiagnosticoDeMedio.SondearAsync(new Uri("http://aula.local:8000/api/aula/cursos/c/medios/m/"), new HttpClient(falso)); }
        finally { ClienteJson.Token = anterior; }
        Assert.Equal(new AuthenticationHeaderValue("Bearer", "jwt-de-prueba"), Assert.Single(falso.Peticiones).Headers.Authorization);
    }

    [Fact]
    public async Task Un_206_significa_que_el_aula_entrega_y_entonces_si_es_cosa_del_dispositivo()
    {
        var falso = new Falso(_ =>
        {
            var r = new HttpResponseMessage(HttpStatusCode.PartialContent) { Content = new ByteArrayContent([1]) };
            r.Content.Headers.ContentType = new MediaTypeHeaderValue("video/mp4");
            r.Content.Headers.ContentRange = new ContentRangeHeaderValue(0, 0, 154451);
            return r;
        });
        var sondeo = await DiagnosticoDeMedio.SondearAsync(Medio, new HttpClient(falso));
        Assert.True(sondeo.Entrega);
        Assert.Equal(154451, sondeo.Bytes);
        Assert.Equal("video/mp4", sondeo.Tipo);
        Assert.Contains("no pudo reproducirlo", sondeo.Causa);
        Assert.Equal("HTTP 206 video/mp4 154451 bytes", sondeo.Resumen);
    }

    [Theory]
    [InlineData(403, "sin_permiso", "no tiene permiso")]
    [InlineData(404, "referencia_no_encontrada", "no está en el curso")]
    [InlineData(401, "sesion_invalida", "no reconoció el permiso")]
    [InlineData(500, null, "respondió 500")]
    public async Task Cada_estado_dice_su_causa(int estado, string? codigo, string frase)
    {
        var cuerpo = codigo is null ? "oops" : $$"""{"codigo":"{{codigo}}"}""";
        var falso = new Falso(_ => Json((HttpStatusCode)estado, cuerpo));
        var sondeo = await DiagnosticoDeMedio.SondearAsync(Medio, new HttpClient(falso));
        Assert.Equal(estado, sondeo.Estado);
        Assert.Contains(frase, sondeo.Causa);
    }

    [Fact]
    public async Task Un_503_repite_la_sugerencia_del_backend()
    {
        var falso = new Falso(_ => Json(HttpStatusCode.ServiceUnavailable, """{"disponible":false,"codigo":"fuente_no_disponible","sugerencia":"Abre AVACOM Contenido."}"""));
        var sondeo = await DiagnosticoDeMedio.SondearAsync(Medio, new HttpClient(falso));
        Assert.Equal("Abre AVACOM Contenido.", sondeo.Causa);
    }

    [Fact]
    public async Task Sin_respuesta_no_lanza_y_lo_dice()
    {
        var falso = new Falso(_ => throw new HttpRequestException("Connection refused"));
        var sondeo = await DiagnosticoDeMedio.SondearAsync(Medio, new HttpClient(falso));
        Assert.Null(sondeo.Estado);
        Assert.Contains("Connection refused", sondeo.Resumen);
        Assert.Contains("equipo del aula", sondeo.Causa);
    }

    [Fact]
    public async Task Descargar_una_imagen_devuelve_los_bytes_o_la_causa()
    {
        var bien = new Falso(_ =>
        {
            var r = new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent([0x89, 0x50, 0x4E, 0x47]) };
            r.Content.Headers.ContentType = new MediaTypeHeaderValue("image/png");
            return r;
        });
        var (bytes, sondeo) = await DiagnosticoDeMedio.DescargarImagenAsync(Medio, new HttpClient(bien));
        Assert.Equal([0x89, 0x50, 0x4E, 0x47], bytes);
        Assert.True(sondeo.Entrega);

        var mal = new Falso(_ => Json(HttpStatusCode.Unauthorized, """{"codigo":"pase_de_medios_invalido"}"""));
        var (nada, causa) = await DiagnosticoDeMedio.DescargarImagenAsync(Medio, new HttpClient(mal));
        Assert.Null(nada);
        Assert.Equal(401, causa.Estado);
    }
}

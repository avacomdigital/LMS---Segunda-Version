using System.Net;
using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>PAN-241 / ESC-03: otra persona concede la escalada de audit.export en el mismo equipo; el pase de quien usa el equipo vuelve siempre.</summary>
[Collection("registro-local")]
public sealed class AutorizacionDeSalidaTests : IDisposable
{
    private readonly string carpeta;

    public AutorizacionDeSalidaTests()
    {
        carpeta = Path.Combine(Path.GetTempPath(), "avacom-core-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(carpeta);
        Environment.SetEnvironmentVariable("AVACOM_LMS_DIR_LOGS", carpeta);
        RegistroLocal.Reiniciar();
        ClienteJson.Token = "pase-de-rectoria";
    }

    public void Dispose()
    {
        Environment.SetEnvironmentVariable("AVACOM_LMS_DIR_LOGS", null);
        ClienteJson.Token = null;
        try { Directory.Delete(carpeta, recursive: true); } catch { }
    }

    private sealed class Nodo : HttpMessageHandler
    {
        public List<(string Metodo, string Ruta, string? Cuerpo, string? Pase)> Llamadas { get; } = [];
        public bool CredencialesMalas { get; set; }
        public string IdDeQuienAutoriza { get; set; } = "u-coordinacion";
        public HttpStatusCode EstadoEscalada { get; set; } = HttpStatusCode.Created;

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage req, CancellationToken ct)
        {
            var cuerpo = req.Content is null ? null : await req.Content.ReadAsStringAsync(ct);
            var pase = req.Headers.Authorization?.Parameter;
            var ruta = req.RequestUri!.AbsolutePath;
            Llamadas.Add((req.Method.Method, ruta, cuerpo, pase));
            HttpResponseMessage Json(HttpStatusCode estado, string json) => new(estado) { Content = new StringContent(json, Encoding.UTF8, "application/json"), RequestMessage = req };
            if (ruta == "/api/acceso/sesiones/" && req.Method == HttpMethod.Post)
                return CredencialesMalas
                    ? Json(HttpStatusCode.Unauthorized, """{"detail":"Identificador o clave incorrectos.","codigo":"credenciales_invalidas"}""")
                    : Json(HttpStatusCode.OK, $$$"""{"token":"pase-de-otra","expira_en":1,"sesion_id":"s2","usuario":{"id":"{{{IdDeQuienAutoriza}}}","alias":"Coordinación","rol":"ADMIN","menu":"admin","nivel":3}}""");
            if (ruta.EndsWith("/escaladas/"))
                return Json(EstadoEscalada, EstadoEscalada == HttpStatusCode.Created ? """{"id":"e1","permiso":"audit.export"}""" : """{"detail":"No tiene permiso.","codigo":"sin_permiso"}""");
            if (ruta == "/api/acceso/sesiones/actual/" && req.Method == HttpMethod.Delete)
                return new HttpResponseMessage(HttpStatusCode.NoContent) { RequestMessage = req };
            return Json(HttpStatusCode.NotFound, "{}");
        }
    }

    [Fact]
    public async Task OtraPersonaConcedeLaEscalada_ConSuPase_YElPaseDelEquipoVuelve()
    {
        var nodo = new Nodo();
        var acceso = new AccesoApi(new HttpClient(nodo), new Uri("http://127.0.0.1:8000/"));
        var r = await AutorizacionDeSalida.ConcederAsync(acceso, "u-rectoria", "ops-NODO", "52000111", "Coordina.2026!Aula", "Auditoría externa");
        Assert.True(r.Ok, r.Mensaje);
        Assert.NotNull(r.VigenteHastaMs);
        Assert.Equal("pase-de-rectoria", ClienteJson.Token);
        Assert.Equal(["POST /api/acceso/sesiones/", "POST /api/acceso/usuarios/u-rectoria/escaladas/", "DELETE /api/acceso/sesiones/actual/"],
                     nodo.Llamadas.Select(l => $"{l.Metodo} {l.Ruta}").ToArray());
        Assert.Null(nodo.Llamadas[0].Pase);                       // el login no viaja con el pase de la rectoría
        Assert.Equal("pase-de-otra", nodo.Llamadas[1].Pase);     // la escalada la firma quien autoriza
        Assert.Equal("pase-de-otra", nodo.Llamadas[2].Pase);     // y es su sesión la que se cierra
        using var doc = JsonDocument.Parse(nodo.Llamadas[1].Cuerpo!);
        Assert.Equal(("audit.export", "ORGANIZATION", "Auditoría externa"),
                     (doc.RootElement.GetProperty("permiso").GetString(), doc.RootElement.GetProperty("alcance").GetString(), doc.RootElement.GetProperty("motivo").GetString()));
        var vigente = doc.RootElement.GetProperty("vigente_hasta").GetInt64();
        Assert.InRange(vigente - DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), 29 * 60_000, 31 * 60_000);
        Assert.Contains("Autorización concedida", r.Mensaje);
    }

    [Fact]
    public async Task NoExisteLaAutoconcesion_YLaSesionDeQuienAutorizaSeCierraIgual()
    {
        var nodo = new Nodo { IdDeQuienAutoriza = "u-rectoria" };
        var acceso = new AccesoApi(new HttpClient(nodo), new Uri("http://127.0.0.1:8000/"));
        var r = await AutorizacionDeSalida.ConcederAsync(acceso, "u-rectoria", "ops-NODO", "1042888795", "Rectoria.2026!", "Inspección interna");
        Assert.False(r.Ok);
        Assert.Contains("autoconcesión", r.Mensaje);
        Assert.DoesNotContain(nodo.Llamadas, l => l.Ruta.EndsWith("/escaladas/"));
        Assert.Equal("DELETE", nodo.Llamadas[^1].Metodo);
        Assert.Equal("pase-de-rectoria", ClienteJson.Token);
    }

    [Fact]
    public async Task CredencialesMalas_SinPermiso_YEntradaIncompleta()
    {
        var nodo = new Nodo { CredencialesMalas = true };
        var acceso = new AccesoApi(new HttpClient(nodo), new Uri("http://127.0.0.1:8000/"));
        var r = await AutorizacionDeSalida.ConcederAsync(acceso, "u-rectoria", "ops-NODO", "52000111", "mal", "Inspección interna");
        Assert.Equal((false, "Documento o clave incorrectos."), (r.Ok, r.Mensaje));
        Assert.Equal("pase-de-rectoria", ClienteJson.Token);

        nodo = new Nodo { EstadoEscalada = HttpStatusCode.Forbidden };
        acceso = new AccesoApi(new HttpClient(nodo), new Uri("http://127.0.0.1:8000/"));
        r = await AutorizacionDeSalida.ConcederAsync(acceso, "u-rectoria", "ops-NODO", "80123456", "Docente.2026!", "Inspección interna");
        Assert.False(r.Ok);
        Assert.Contains("rol de administración", r.Mensaje);
        Assert.Equal("DELETE", nodo.Llamadas[^1].Metodo);
        Assert.Equal("pase-de-rectoria", ClienteJson.Token);

        Assert.False((await AutorizacionDeSalida.ConcederAsync(acceso, null, "ops-NODO", "x", "y", "m")).Ok);
        Assert.False((await AutorizacionDeSalida.ConcederAsync(acceso, "u-rectoria", "ops-NODO", "", "y", "m")).Ok);
        Assert.False((await AutorizacionDeSalida.ConcederAsync(acceso, "u-rectoria", "ops-NODO", "x", "y", "")).Ok);
        Assert.Equal(1, nodo.Llamadas.Count(l => l.Ruta == "/api/acceso/sesiones/"));   // las entradas incompletas no llegan al nodo
    }
}

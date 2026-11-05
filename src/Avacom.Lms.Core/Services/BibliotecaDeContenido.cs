using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>
/// Fachada única de los clientes MAUI hacia AVACOM Biblioteca.
///
/// Habla con el BACKEND del LMS, nunca con la biblioteca: la biblioteca sólo
/// escucha en loopback del equipo maestro y las tabletas no la alcanzan. El
/// backend descubre el puerto, lleva la ficha y aplica la degradación.
///
/// Reglas que replica de la línea base:
///  - Un 503 del backend no es una excepción de negocio: las listas vuelven vacías
///    y los detalles vuelven null; el motivo queda en <see cref="UltimoMotivo"/>.
///  - null de <see cref="CursoAsync"/> significa «no se pudo comprobar», y la
///    pantalla debe decir eso, no afirmar que el contenido desapareció.
///  - Guarda una huella local para saber si el catálogo cambió sin recargar todo.
/// </summary>
public interface IBibliotecaDeContenido
{
    Uri BaseUri { get; }
    string? UltimoMotivo { get; }
    Task<EstadoBiblioteca> EstadoAsync(CancellationToken ct = default);
    Task<(EstadoBiblioteca estado, bool cambio)> ConsultarEstadoAsync(CancellationToken ct = default);
    void OlvidarHuella();
    Task<RespuestaCursos> CursosAsync(string? personaId, CancellationToken ct = default);
    Task<CursoDetalle?> CursoAsync(string cursoRef, string? personaId, CancellationToken ct = default);
    Uri MedioUri(string elementoRef, string? rutaInterna = null);
    Uri VozUri(string elementoRef, string? preguntaRef = null);
    Task<LeccionDetalle?> LeccionAsync(string elementoRef, CancellationToken ct = default);
    Task<(bool aceptado, string? motivo)> MostrarEnAulaAsync(string elementoRef, CancellationToken ct = default);
    Task<AperturaRegistrada?> RegistrarAperturaAsync(AperturaSolicitud solicitud, CancellationToken ct = default);
    Task CerrarAperturaAsync(long aperturaId, int? progresoPct, CancellationToken ct = default);
    Task<IntentoIniciado?> IniciarIntentoAsync(IntentoSolicitud solicitud, CancellationToken ct = default);
    Task<VeredictoRespuesta?> ResponderAsync(long intentoId, string preguntaRef, string respuesta, CancellationToken ct = default);
    Task<ResultadoIntento?> FinalizarIntentoAsync(long intentoId, CancellationToken ct = default);
    Task<ConsolidadoCurso?> ConsolidadoAsync(string cursoRef, CancellationToken ct = default);
}

public sealed record AperturaSolicitud(
    string CursoRef, string PersonaId, string ElementoRef, string LeccionCodigo, string? VersionElemento,
    string Tipo, string ElementoRotulo, string? PersonaRotulo, string? CursoRotulo, string Dispositivo, string Origen);

public sealed record IntentoSolicitud(
    string EvaluacionRef, string PersonaId, string CursoRef, string LeccionCodigo, string? PersonaRotulo,
    string? CursoRotulo, string Dispositivo);

public sealed class BibliotecaDeContenido(HttpClient http, Uri baseUri) : IBibliotecaDeContenido
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private string? _huella;

    public Uri BaseUri { get; } = baseUri;
    public string? UltimoMotivo { get; private set; }

    public async Task<EstadoBiblioteca> EstadoAsync(CancellationToken ct = default)
    {
        try
        {
            var estado = await http.GetFromJsonAsync<EstadoBiblioteca>(new Uri(BaseUri, "api/biblioteca/estado/"), Json, ct);
            UltimoMotivo = estado?.Disponible == true ? null : estado?.Motivo;
            return estado ?? EstadoBiblioteca.SinBackend("La biblioteca de cursos no respondió.");
        }
        catch (Exception ex) when (EsDeRed(ex))
        {
            UltimoMotivo = "No hay conexión con el aula.";
            return EstadoBiblioteca.SinBackend(UltimoMotivo);
        }
    }

    public async Task<(EstadoBiblioteca estado, bool cambio)> ConsultarEstadoAsync(CancellationToken ct = default)
    {
        var estado = await EstadoAsync(ct);
        var huella = estado.Disponible ? estado.HuellaCatalogo ?? string.Empty : "sin-biblioteca";
        var cambio = !string.Equals(huella, _huella, StringComparison.Ordinal);
        _huella = huella;
        return (estado, cambio);
    }

    /// <summary>Fuerza que la próxima consulta cuente como cambio (para recargar al entrar en una pantalla).</summary>
    public void OlvidarHuella() => _huella = null;

    public async Task<RespuestaCursos> CursosAsync(string? personaId, CancellationToken ct = default)
    {
        // Con persona se usa la ruta del expediente: responde 200 aunque la
        // biblioteca esté cerrada, con los cursos conocidos y un aviso.
        var ruta = string.IsNullOrWhiteSpace(personaId)
            ? "api/biblioteca/cursos/"
            : $"api/students/{Uri.EscapeDataString(personaId)}/courses/";
        try
        {
            using var respuesta = await http.GetAsync(new Uri(BaseUri, ruta), ct);
            if (respuesta.StatusCode == HttpStatusCode.ServiceUnavailable || respuesta.StatusCode == HttpStatusCode.NotImplemented)
            {
                UltimoMotivo = await MotivoAsync(respuesta, ct);
                return RespuestaCursos.Vacia(UltimoMotivo);
            }
            respuesta.EnsureSuccessStatusCode();
            var datos = await respuesta.Content.ReadFromJsonAsync<RespuestaCursos>(Json, ct);
            UltimoMotivo = datos?.Disponible == true ? null : datos?.Aviso;
            return datos ?? RespuestaCursos.Vacia("La biblioteca de cursos no respondió.");
        }
        catch (Exception ex) when (EsDeRed(ex))
        {
            UltimoMotivo = "No hay conexión con el aula.";
            return RespuestaCursos.Vacia(UltimoMotivo);
        }
    }

    public async Task<CursoDetalle?> CursoAsync(string cursoRef, string? personaId, CancellationToken ct = default)
    {
        var ruta = $"api/biblioteca/cursos/{Uri.EscapeDataString(cursoRef)}/";
        if (!string.IsNullOrWhiteSpace(personaId)) ruta += $"?persona={Uri.EscapeDataString(personaId)}";
        return await ObtenerAsync<CursoDetalle>(ruta, ct);
    }

    public Uri MedioUri(string elementoRef, string? rutaInterna = null)
    {
        var ruta = $"api/biblioteca/medio/{Uri.EscapeDataString(elementoRef)}/";
        if (!string.IsNullOrWhiteSpace(rutaInterna)) ruta += rutaInterna.TrimStart('/');
        return new Uri(BaseUri, ruta);
    }

    public Uri VozUri(string elementoRef, string? preguntaRef = null)
    {
        var ruta = $"api/biblioteca/voz/{Uri.EscapeDataString(elementoRef)}/";
        if (!string.IsNullOrWhiteSpace(preguntaRef)) ruta += $"{Uri.EscapeDataString(preguntaRef)}/";
        return new Uri(BaseUri, ruta);
    }

    public Task<LeccionDetalle?> LeccionAsync(string elementoRef, CancellationToken ct = default) =>
        ObtenerAsync<LeccionDetalle>($"api/biblioteca/leccion/{Uri.EscapeDataString(elementoRef)}/", ct);

    public async Task<(bool aceptado, string? motivo)> MostrarEnAulaAsync(string elementoRef, CancellationToken ct = default)
    {
        try
        {
            using var respuesta = await http.PostAsync(new Uri(BaseUri, "api/biblioteca/mostrar/"), Cuerpo(new { elemento_ref = elementoRef }), ct);
            if (respuesta.IsSuccessStatusCode) return (true, null);
            return (false, await MotivoAsync(respuesta, ct));
        }
        catch (Exception ex) when (EsDeRed(ex))
        {
            return (false, "No hay conexión con el aula.");
        }
    }

    public Task<AperturaRegistrada?> RegistrarAperturaAsync(AperturaSolicitud s, CancellationToken ct = default) =>
        EnviarAsync<AperturaRegistrada>("api/aperturas/", new
        {
            curso_ref = s.CursoRef, persona_id = s.PersonaId, elemento_ref = s.ElementoRef, leccion_codigo = s.LeccionCodigo,
            version_elemento = s.VersionElemento, tipo = s.Tipo, elemento_rotulo = s.ElementoRotulo,
            persona_rotulo = s.PersonaRotulo, curso_rotulo = s.CursoRotulo, dispositivo = s.Dispositivo, origen = s.Origen,
        }, ct);

    public async Task CerrarAperturaAsync(long aperturaId, int? progresoPct, CancellationToken ct = default) =>
        await EnviarAsync<JsonElement?>($"api/aperturas/{aperturaId}/cerrar/", new { progreso_pct = progresoPct }, ct);

    public Task<IntentoIniciado?> IniciarIntentoAsync(IntentoSolicitud s, CancellationToken ct = default) =>
        EnviarAsync<IntentoIniciado>("api/intentos/start/", new
        {
            evaluacion_ref = s.EvaluacionRef, persona_id = s.PersonaId, curso_ref = s.CursoRef, leccion_codigo = s.LeccionCodigo,
            persona_rotulo = s.PersonaRotulo, curso_rotulo = s.CursoRotulo, dispositivo = s.Dispositivo,
        }, ct);

    public Task<VeredictoRespuesta?> ResponderAsync(long intentoId, string preguntaRef, string respuesta, CancellationToken ct = default) =>
        EnviarAsync<VeredictoRespuesta>("api/intentos/answer/", new { intento_id = intentoId, pregunta_ref = preguntaRef, respuesta }, ct);

    public Task<ResultadoIntento?> FinalizarIntentoAsync(long intentoId, CancellationToken ct = default) =>
        EnviarAsync<ResultadoIntento>("api/intentos/finish/", new { intento_id = intentoId }, ct);

    public Task<ConsolidadoCurso?> ConsolidadoAsync(string cursoRef, CancellationToken ct = default) =>
        ObtenerAsync<ConsolidadoCurso>($"api/cursos/{Uri.EscapeDataString(cursoRef)}/consolidado/", ct);

    // ------------------------------------------------------------------ ayudas

    private async Task<T?> ObtenerAsync<T>(string ruta, CancellationToken ct)
    {
        try
        {
            using var respuesta = await http.GetAsync(new Uri(BaseUri, ruta), ct);
            if (!respuesta.IsSuccessStatusCode)
            {
                UltimoMotivo = await MotivoAsync(respuesta, ct);
                return default;
            }
            UltimoMotivo = null;
            return await respuesta.Content.ReadFromJsonAsync<T>(Json, ct);
        }
        catch (Exception ex) when (EsDeRed(ex))
        {
            UltimoMotivo = "No hay conexión con el aula.";
            return default;
        }
    }

    private async Task<T?> EnviarAsync<T>(string ruta, object cuerpo, CancellationToken ct)
    {
        try
        {
            using var respuesta = await http.PostAsync(new Uri(BaseUri, ruta), Cuerpo(cuerpo), ct);
            if (!respuesta.IsSuccessStatusCode)
            {
                UltimoMotivo = await MotivoAsync(respuesta, ct);
                return default;
            }
            UltimoMotivo = null;
            return await respuesta.Content.ReadFromJsonAsync<T>(Json, ct);
        }
        catch (Exception ex) when (EsDeRed(ex))
        {
            UltimoMotivo = "No hay conexión con el aula.";
            return default;
        }
    }

    /// <summary>
    /// El cuerpo se serializa a texto ANTES de enviarlo para que la petición lleve
    /// Content-Length. PostAsJsonAsync envía con Transfer-Encoding: chunked, y el
    /// servidor de desarrollo de Django (WSGI) no lee cuerpos troceados: llegaría vacío.
    /// </summary>
    private static StringContent Cuerpo(object cuerpo) =>
        new(JsonSerializer.Serialize(cuerpo, Json), Encoding.UTF8, "application/json");

    private static async Task<string> MotivoAsync(HttpResponseMessage respuesta, CancellationToken ct)
    {
        try
        {
            var texto = await respuesta.Content.ReadAsStringAsync(ct);
            using var doc = JsonDocument.Parse(string.IsNullOrWhiteSpace(texto) ? "{}" : texto);
            foreach (var clave in new[] { "detail", "motivo", "aviso", "error" })
                if (doc.RootElement.TryGetProperty(clave, out var v) && v.ValueKind == JsonValueKind.String)
                    return v.GetString()!;
        }
        catch (JsonException) { }
        return "La biblioteca de cursos no respondió como se esperaba.";
    }

    private static bool EsDeRed(Exception ex) =>
        ex is HttpRequestException or TaskCanceledException or JsonException or IOException;
}

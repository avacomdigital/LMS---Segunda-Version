using System.Text.Json;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>
/// Cliente de <c>/api/aula/</c> (MOD-007 · Classroom Engine) para OPS y Student.
///
/// Mismas reglas que <see cref="BibliotecaDeContenido"/>: habla con el backend del
/// LMS (nunca con la biblioteca), toda URL nace de <see cref="ClienteJson.BaseUri"/>, un 503 no es
/// una excepción de negocio (devuelve null y deja el motivo en <see cref="ClienteJson.UltimoMotivo"/>)
/// y los cuerpos viajan con Content-Length. Además expone <see cref="ClienteJson.UltimoError"/> con el
/// <c>codigo</c> del backend para que la pantalla decida (por ejemplo
/// <c>sesion_activa_existente</c> → «Continuar esa clase», <c>dispositivo_bloqueado</c> → «usa otra tableta»).
/// </summary>
public interface IAulaApi
{
    Uri BaseUri { get; }

    /// <summary>
    /// Fuente de cursos que se pide al backend (<c>?fuente=biblioteca|ejemplo</c>). Vacía o nula, el
    /// parámetro no viaja y el backend decide: la biblioteca (API de Contenido v2) por defecto, o el
    /// manifiesto de ejemplo cuando la referencia es la suya. Así una tableta sigue cualquier clase sin
    /// saber de dónde salió el curso.
    /// </summary>
    string? Fuente { get; }
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }
    Uri Absoluta(string rutaRelativa);

    Task<CatalogoAula?> CursosAsync(CancellationToken ct = default);
    Task<VistaCurso?> CursoAsync(string cursoRef, bool docente, CancellationToken ct = default);
    Task<ObjetoSuelto?> ObjetoAsync(string cursoRef, string objetoRef, bool docente, CancellationToken ct = default);

    Task<SesionDeClase?> IniciarAsync(IniciarSesionSolicitud solicitud, CancellationToken ct = default);
    Task<SesionDeClase?> SesionAsync(string sesionId, CancellationToken ct = default);
    /// <summary>Declara el selector (lo que se proyecta): un objeto y, opcionalmente, su lámina o página.</summary>
    Task<SelectorAula?> ProyectarAsync(string sesionId, string actor, string objetoRef, string? unidadRef, CancellationToken ct = default);
    Task<bool> ControlAsync(string sesionId, string actor, string tipo, bool activo, CancellationToken ct = default);
    Task<DistribucionAula?> DistribuirAsync(string sesionId, string actor, DistribuirSolicitud solicitud, CancellationToken ct = default);
    Task<DistribucionAula?> CerrarDistribucionAsync(string sesionId, string actor, string distribucionId, CancellationToken ct = default);
    Task<bool> AvisarAsync(string sesionId, string actor, string texto, string? participanteId, CancellationToken ct = default);
    Task<ParticipanteAula?> ParticipanteAsync(string sesionId, string actor, string participanteId, string accion, CancellationToken ct = default);
    Task<SesionDeClase?> CerrarAsync(string sesionId, string actor, bool forzar, CancellationToken ct = default);

    /// <summary>La tableta entra con el código; declara su huella, su plataforma y su versión para que MOD-009 la reconozca.</summary>
    Task<EstadoTableta?> UnirseAsync(string codigo, string personaId, string personaRotulo, string dispositivo, string? participanteId,
                                     string? plataforma = null, string? versionApp = null, CancellationToken ct = default);
    Task<EstadoTableta?> EstadoAsync(string sesionId, string participanteId, CancellationToken ct = default);
    Task<EstadoTableta?> PresenciaAsync(string sesionId, string participanteId, string? estado, string dispositivo, CancellationToken ct = default);
    Task<bool> ConfirmarEntregaAsync(string sesionId, string distribucionId, string participanteId, CancellationToken ct = default);
}

public sealed class AulaApi(HttpClient http, Uri baseUri, string? fuente = null) : ClienteJson(http, baseUri), IAulaApi
{
    public string? Fuente { get; } = string.IsNullOrWhiteSpace(fuente) ? null : fuente;

    private string ConFuente(string ruta) =>
        Fuente is null ? ruta : ruta.Contains('?') ? $"{ruta}&fuente={Uri.EscapeDataString(Fuente)}" : $"{ruta}?fuente={Uri.EscapeDataString(Fuente)}";

    // ------------------------------------------------------------------ curso

    public Task<CatalogoAula?> CursosAsync(CancellationToken ct = default) =>
        ObtenerAsync<CatalogoAula>(ConFuente("api/aula/cursos/"), ct);

    public Task<VistaCurso?> CursoAsync(string cursoRef, bool docente, CancellationToken ct = default) =>
        ObtenerAsync<VistaCurso>(ConFuente($"api/aula/cursos/{Uri.EscapeDataString(cursoRef)}/?rol={(docente ? "docente" : "estudiante")}"), ct);

    public Task<ObjetoSuelto?> ObjetoAsync(string cursoRef, string objetoRef, bool docente, CancellationToken ct = default) =>
        ObtenerAsync<ObjetoSuelto>(ConFuente($"api/aula/cursos/{Uri.EscapeDataString(cursoRef)}/objetos/{Uri.EscapeDataString(objetoRef)}/?rol={(docente ? "docente" : "estudiante")}"), ct);

    // ----------------------------------------------------------------- docente

    public Task<SesionDeClase?> IniciarAsync(IniciarSesionSolicitud s, CancellationToken ct = default) =>
        EnviarAsync<SesionDeClase>("api/aula/sesiones/", new
        {
            via = s.Via, curso_ref = s.CursoRef, leccion_ref = s.LeccionRef, objeto_ref = s.ObjetoRef, fuente = s.Fuente,
            profesor_id = s.ProfesorId, profesor_rotulo = s.ProfesorRotulo, superficie = s.Superficie,
        }, ct);

    public Task<SesionDeClase?> SesionAsync(string sesionId, CancellationToken ct = default) =>
        ObtenerAsync<SesionDeClase>($"api/aula/sesiones/{sesionId}/", ct);

    public Task<SelectorAula?> ProyectarAsync(string sesionId, string actor, string objetoRef, string? unidadRef, CancellationToken ct = default) =>
        EnviarAsync<SelectorAula>($"api/aula/sesiones/{sesionId}/selector/", new { objeto_ref = objetoRef, unidad_ref = unidadRef, profesor_id = actor }, ct);

    public async Task<bool> ControlAsync(string sesionId, string actor, string tipo, bool activo, CancellationToken ct = default) =>
        await EnviarAsync<JsonElement?>($"api/aula/sesiones/{sesionId}/controles/", new { tipo, activo, profesor_id = actor }, ct) is not null;

    public Task<DistribucionAula?> DistribuirAsync(string sesionId, string actor, DistribuirSolicitud s, CancellationToken ct = default) =>
        EnviarAsync<DistribucionAula>($"api/aula/sesiones/{sesionId}/distribuciones/", new
        {
            clase = s.Clase, objeto_ref = s.ObjetoRef, media_ref = s.MediaRef, rotulo = s.Rotulo,
            disponible_estudio = s.DisponibleEstudio, alcance = s.Alcance, participantes = s.Participantes,
            intentos_permitidos = s.IntentosPermitidos, tiempo_limite_seg = s.TiempoLimiteSeg, profesor_id = actor,
        }, ct);

    public Task<DistribucionAula?> CerrarDistribucionAsync(string sesionId, string actor, string distribucionId, CancellationToken ct = default) =>
        EnviarAsync<DistribucionAula>($"api/aula/sesiones/{sesionId}/distribuciones/{distribucionId}/cerrar/", new { profesor_id = actor }, ct);

    public async Task<bool> AvisarAsync(string sesionId, string actor, string texto, string? participanteId, CancellationToken ct = default) =>
        await EnviarAsync<AvisoAula>($"api/aula/sesiones/{sesionId}/avisos/", new { texto, participante_id = participanteId, profesor_id = actor }, ct) is not null;

    public Task<ParticipanteAula?> ParticipanteAsync(string sesionId, string actor, string participanteId, string accion, CancellationToken ct = default) =>
        EnviarAsync<ParticipanteAula>($"api/aula/sesiones/{sesionId}/participantes/{participanteId}/{accion}/", new { profesor_id = actor }, ct);

    public Task<SesionDeClase?> CerrarAsync(string sesionId, string actor, bool forzar, CancellationToken ct = default) =>
        EnviarAsync<SesionDeClase>($"api/aula/sesiones/{sesionId}/cerrar/", new { forzar, profesor_id = actor }, ct);

    // -------------------------------------------------------------- estudiante

    public Task<EstadoTableta?> UnirseAsync(string codigo, string personaId, string personaRotulo, string dispositivo, string? participanteId,
                                            string? plataforma = null, string? versionApp = null, CancellationToken ct = default) =>
        EnviarAsync<EstadoTableta>("api/aula/sesiones/unirse/", new
        {
            codigo_union = codigo, persona_id = personaId, persona_rotulo = personaRotulo, dispositivo, participante_id = participanteId,
            plataforma, version_app = versionApp,
        }, ct);

    public Task<EstadoTableta?> EstadoAsync(string sesionId, string participanteId, CancellationToken ct = default) =>
        ObtenerAsync<EstadoTableta>($"api/aula/sesiones/{sesionId}/estado/?participante={Uri.EscapeDataString(participanteId)}", ct);

    public Task<EstadoTableta?> PresenciaAsync(string sesionId, string participanteId, string? estado, string dispositivo, CancellationToken ct = default) =>
        EnviarAsync<EstadoTableta>($"api/aula/sesiones/{sesionId}/participantes/{participanteId}/presencia/", new { estado, dispositivo }, ct);

    public async Task<bool> ConfirmarEntregaAsync(string sesionId, string distribucionId, string participanteId, CancellationToken ct = default) =>
        await EnviarAsync<JsonElement?>($"api/aula/sesiones/{sesionId}/distribuciones/{distribucionId}/confirmar/", new { participante_id = participanteId }, ct) is not null;
}

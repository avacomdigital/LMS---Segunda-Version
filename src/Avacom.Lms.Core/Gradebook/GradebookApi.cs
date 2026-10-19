using System.Text;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Gradebook;

/// <summary>
/// Cliente de <c>/api/gradebook/</c> (MOD-011): las rutas de <c>spec-driven/12-gradebook/02-api.md</c>, una por método de <see cref="IGradebookApi"/> (OPS) y
/// de <see cref="IGradebookAlumnoApi"/> (Student). El profesor se identifica con <c>actor</c> en la consulta (GET) o en el cuerpo (POST/PUT); los campos opcionales
/// que valen null NO viajan: un serializador estricto del backend no distingue «ausente» de «nulo». Un error HTTP o de red no es una excepción: devuelve null y
/// deja el motivo y el <c>codigo</c> en <see cref="ClienteJson.UltimoMotivo"/> y <see cref="ClienteJson.UltimoError"/>.
/// </summary>
public sealed class GradebookApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri), IGradebookApi, IGradebookAlumnoApi
{
    private const string Base = "api/gradebook/";

    private static string Esc(string valor) => Uri.EscapeDataString(valor);

    /// <summary>La ruta con su consulta; los valores nulos o vacíos no viajan.</summary>
    private static string Ruta(string ruta, params (string Clave, string? Valor)[] consulta)
    {
        var texto = new StringBuilder(Base).Append(ruta);
        var separador = '?';
        foreach (var (clave, valor) in consulta)
        {
            if (string.IsNullOrEmpty(valor)) continue;
            texto.Append(separador).Append(clave).Append('=').Append(Esc(valor));
            separador = '&';
        }
        return texto.ToString();
    }

    /// <summary>El cuerpo de una petición del personal: sus campos que no son nulos y el <c>actor</c>.</summary>
    private static Dictionary<string, object?> Docente(string actor, params (string Clave, object? Valor)[] campos)
    {
        var cuerpo = new Dictionary<string, object?>();
        foreach (var (clave, valor) in campos)
            if (valor is not null) cuerpo[clave] = valor;
        cuerpo["actor"] = actor;
        return cuerpo;
    }

    private static string Cal(string id) => $"calificaciones/{Esc(id)}/";
    private static string Rev(string intento) => $"revisiones/{Esc(intento)}/";

    // ================================================================================================== leer

    public Task<LibroDelGrupo?> LibroAsync(string actor, string grupoId, string? asignacionId = null, string? periodo = null, string? cursoRef = null, string? busqueda = null, CancellationToken ct = default) =>
        ObtenerAsync<LibroDelGrupo>(Ruta("libro/", ("grupo_id", grupoId), ("asignacion_id", asignacionId), ("periodo", periodo), ("curso_ref", cursoRef), ("q", busqueda), ("actor", actor)), ct);

    public Task<ResumenDePeriodo?> ResumenAsync(string actor, string grupoId, string? periodo = null, string? cursoRef = null, CancellationToken ct = default) =>
        ObtenerAsync<ResumenDePeriodo>(Ruta("resumen/", ("grupo_id", grupoId), ("periodo", periodo), ("curso_ref", cursoRef), ("actor", actor)), ct);

    public Task<DetalleDeCalificacion?> CalificacionAsync(string actor, string calificacionId, CancellationToken ct = default) =>
        ObtenerAsync<DetalleDeCalificacion>(Ruta(Cal(calificacionId), ("actor", actor)), ct);

    public Task<NotasDeAsignacion?> NotasDeAsignacionAsync(string actor, string asignacionId, CancellationToken ct = default) =>
        ObtenerAsync<NotasDeAsignacion>(Ruta($"asignaciones/{Esc(asignacionId)}/", ("actor", actor)), ct);

    // ====================================================================================== revisión docente

    public Task<BandejaDeRevision?> BandejaAsync(string actor, string? grupoId = null, string? asignacionId = null, CancellationToken ct = default) =>
        ObtenerAsync<BandejaDeRevision>(Ruta("revisiones/", ("grupo_id", grupoId), ("asignacion_id", asignacionId), ("actor", actor)), ct);

    public Task<RevisionParaDocente?> RevisionAsync(string actor, string intentoId, CancellationToken ct = default) =>
        ObtenerAsync<RevisionParaDocente>(Ruta(Rev(intentoId), ("actor", actor)), ct);

    public Task<RevisionAplicada?> PuntuarAsync(string actor, string intentoId, string preguntaRef, decimal puntaje, string? comentario, string? motivo, string solicitudId, CancellationToken ct = default) =>
        EnviarAsync<RevisionAplicada>(Base + Rev(intentoId) + $"respuestas/{Esc(preguntaRef)}/",
            Docente(actor, ("puntaje", puntaje), ("comentario", comentario), ("motivo", motivo), ("solicitud_id", solicitudId)), ct);

    public Task<RevisionAplicada?> AplicarRubricaAsync(string actor, string intentoId, string preguntaRef, IReadOnlyList<CriterioPuntuado> criterios, string? comentario, string? motivo, string solicitudId, CancellationToken ct = default) =>
        EnviarAsync<RevisionAplicada>(Base + Rev(intentoId) + $"respuestas/{Esc(preguntaRef)}/",
            Docente(actor, ("criterios", criterios.Select(c => new Dictionary<string, object> { ["criterio_id"] = c.CriterioId, ["puntos"] = c.Puntos }).ToList()),
                    ("comentario", comentario), ("motivo", motivo), ("solicitud_id", solicitudId)), ct);

    public Task<RevisionConfirmada?> ConfirmarRevisionAsync(string actor, string intentoId, CancellationToken ct = default) =>
        EnviarAsync<RevisionConfirmada>(Base + Rev(intentoId) + "confirmar/", Docente(actor), ct);

    // ====================================================================================== cambios a una nota

    public Task<CambioDeCalificacion?> AjustarAsync(string actor, string calificacionId, decimal puntajeNuevo, string motivo, int versionEsperada, string solicitudId, CancellationToken ct = default) =>
        EnviarAsync<CambioDeCalificacion>(Base + Cal(calificacionId) + "ajustar/",
            Docente(actor, ("puntaje_nuevo", puntajeNuevo), ("motivo", motivo), ("version_esperada", versionEsperada), ("solicitud_id", solicitudId)), ct);

    public Task<CambioDeCalificacion?> ReabrirAsync(string actor, string calificacionId, string motivo, int versionEsperada, string solicitudId, CancellationToken ct = default) =>
        EnviarAsync<CambioDeCalificacion>(Base + Cal(calificacionId) + "reabrir/",
            Docente(actor, ("motivo", motivo), ("version_esperada", versionEsperada), ("solicitud_id", solicitudId)), ct);

    public Task<CambioDeCalificacion?> ValorarAsync(string actor, string calificacionId, string tramo, string motivo, int versionEsperada, string solicitudId, CancellationToken ct = default) =>
        EnviarAsync<CambioDeCalificacion>(Base + Cal(calificacionId) + "valoracion/",
            Docente(actor, ("tramo", tramo), ("motivo", motivo), ("version_esperada", versionEsperada), ("solicitud_id", solicitudId)), ct);

    public Task<CambioDeCalificacion?> RetroalimentarAsync(string actor, string calificacionId, IReadOnlyDictionary<string, string> campos, string? adaptacion, int versionEsperada, string solicitudId, CancellationToken ct = default)
    {
        var cuerpo = Docente(actor, ("adaptacion", adaptacion), ("version_esperada", versionEsperada), ("solicitud_id", solicitudId));
        foreach (var (clave, valor) in campos) cuerpo[clave] = valor;
        return EnviarAsync<CambioDeCalificacion>(Base + Cal(calificacionId) + "retroalimentacion/", cuerpo, ct);
    }

    // ============================================================================================ publicar

    public Task<CambioDeCalificacion?> PublicarAsync(string actor, string calificacionId, int? versionEsperada = null, string? solicitudId = null, CancellationToken ct = default) =>
        EnviarAsync<CambioDeCalificacion>(Base + Cal(calificacionId) + "publicar/", Docente(actor, ("version_esperada", versionEsperada), ("solicitud_id", solicitudId)), ct);

    public Task<CambioDeCalificacion?> RetirarPublicacionAsync(string actor, string calificacionId, string motivo, int versionEsperada, string solicitudId, CancellationToken ct = default) =>
        EnviarAsync<CambioDeCalificacion>(Base + Cal(calificacionId) + "retirar-publicacion/",
            Docente(actor, ("motivo", motivo), ("version_esperada", versionEsperada), ("solicitud_id", solicitudId)), ct);

    public Task<PublicacionDeAsignacion?> PublicarAsignacionAsync(string actor, string asignacionId, CancellationToken ct = default) =>
        EnviarAsync<PublicacionDeAsignacion>(Base + $"asignaciones/{Esc(asignacionId)}/publicar/", Docente(actor), ct);

    public Task<RegistroDeAsignacion?> RegistrarAsignacionAsync(string actor, string asignacionId, CancellationToken ct = default) =>
        EnviarAsync<RegistroDeAsignacion>(Base + $"asignaciones/{Esc(asignacionId)}/registrar/", Docente(actor), ct);

    // ====================================================================================== configuración

    public Task<ConfiguracionAcademica?> ConfiguracionAsync(string actor, CancellationToken ct = default) =>
        ObtenerAsync<ConfiguracionAcademica>(Ruta("configuracion/", ("actor", actor)), ct);

    public Task<PlantillasDeEscalas?> PlantillasAsync(string actor, string? pais = null, CancellationToken ct = default) =>
        ObtenerAsync<PlantillasDeEscalas>(Ruta("escalas/plantillas/", ("pais", pais), ("actor", actor)), ct);

    public Task<EscalaAdoptada?> AdoptarPlantillaAsync(string actor, string plantilla, string? jurisdiccion = null, string? nota = null, CancellationToken ct = default) =>
        EnviarAsync<EscalaAdoptada>(Base + "escalas/adoptar/", Docente(actor, ("plantilla", plantilla), ("jurisdiccion", jurisdiccion), ("nota", nota)), ct);

    public Task<VistaPreviaDeEscala?> VistaPreviaAsync(string actor, string? plantilla, string? versionId, IReadOnlyList<decimal> valores, CancellationToken ct = default) =>
        EnviarAsync<VistaPreviaDeEscala>(Base + "escalas/vista-previa/", Docente(actor, ("plantilla", plantilla), ("escala_version_id", versionId), ("valores", valores)), ct);

    public Task<ValidacionDeNivel?> ValidarNivelAsync(string actor, string nivel, string modo, string? escalaId, CancellationToken ct = default) =>
        ReemplazarAsync<ValidacionDeNivel>(Base + $"niveles/{Esc(nivel)}/", Docente(actor, ("modo", modo), ("escala_id", escalaId), ("validar", true)), ct);

    public Task<NivelCambiado?> ConfigurarNivelAsync(string actor, string nivel, string modo, string? escalaId, CancellationToken ct = default) =>
        ReemplazarAsync<NivelCambiado>(Base + $"niveles/{Esc(nivel)}/", Docente(actor, ("modo", modo), ("escala_id", escalaId)), ct);

    public Task<PoliticaConfigurada?> ConfigurarPoliticaAsync(string actor, string politicaIntentos, CancellationToken ct = default) =>
        ReemplazarAsync<PoliticaConfigurada>(Base + "politica/", Docente(actor, ("politica_intentos", politicaIntentos)), ct);

    // ================================================================================================ alumno

    public Task<MisResultados?> MisResultadosAsync(string? alumnoId = null, string? dispositivo = null, CancellationToken ct = default) =>
        ObtenerAsync<MisResultados>(Ruta("mias/", ("alumno_id", alumnoId), ("dispositivo", dispositivo)), ct);
}

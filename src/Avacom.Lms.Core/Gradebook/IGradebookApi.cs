using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Gradebook;

/// <summary>
/// Cliente de <c>/api/gradebook/</c> (MOD-011) para el PERSONAL (OPS): el libro de calificaciones, la revisión docente, los ajustes, la publicación y la
/// configuración académica. Contrato en <c>spec-driven/12-gradebook/02-api.md</c>.
///
/// Mismas reglas de degradación que el resto de clientes del LMS: un error HTTP o de red NO es una excepción, devuelve <c>null</c> y deja el motivo en
/// <see cref="UltimoMotivo"/> y el <c>codigo</c> del backend en <see cref="UltimoError"/> (<c>conflicto_de_version</c>, <c>sin_permiso</c>, <c>modo_simple</c>,
/// <c>no_publicable</c>, <c>evaluaciones_en_curso</c>…). Con <see cref="UltimoError"/>.Estado == 0 no hay conexión con el nodo del aula.
///
/// Todo cambio manda una <c>solicitud_id</c> (idempotencia: reenviarla tras perder la señal no repite el efecto) y, sobre una calificación, la
/// <c>version_esperada</c> que se leyó (concurrencia optimista). El profesor se identifica con <c>actor</c> mientras el nodo no exija sesión (Q-34); con sesión
/// manda el JWT.
/// </summary>
public interface IGradebookApi
{
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }

    // ---- leer
    Task<LibroDelGrupo?> LibroAsync(string actor, string grupoId, string? asignacionId = null, string? periodo = null, string? cursoRef = null, string? busqueda = null, CancellationToken ct = default);
    Task<ResumenDePeriodo?> ResumenAsync(string actor, string grupoId, string? periodo = null, string? cursoRef = null, CancellationToken ct = default);
    Task<DetalleDeCalificacion?> CalificacionAsync(string actor, string calificacionId, CancellationToken ct = default);

    // ---- revisión docente (FUN-120, FUN-121)
    Task<BandejaDeRevision?> BandejaAsync(string actor, string? grupoId = null, string? asignacionId = null, CancellationToken ct = default);
    Task<RevisionParaDocente?> RevisionAsync(string actor, string intentoId, CancellationToken ct = default);
    /// <summary>FUN-120: puntúa a mano un reactivo (respuesta abierta, dibujo, entrega). <paramref name="motivo"/> es obligatorio si ya estaba puntuado.</summary>
    Task<RevisionAplicada?> PuntuarAsync(string actor, string intentoId, string preguntaRef, decimal puntaje, string? comentario, string? motivo, string solicitudId, CancellationToken ct = default);
    /// <summary>FUN-121: aplica la rúbrica de la biblioteca criterio por criterio (deben venir todos).</summary>
    Task<RevisionAplicada?> AplicarRubricaAsync(string actor, string intentoId, string preguntaRef, IReadOnlyList<CriterioPuntuado> criterios, string? comentario, string? motivo, string solicitudId, CancellationToken ct = default);
    Task<RevisionConfirmada?> ConfirmarRevisionAsync(string actor, string intentoId, CancellationToken ct = default);

    // ---- cambios a una calificación (FUN-122, FUN-123)
    /// <summary>FUN-123: cambia el valor efectivo (0–100, dos decimales). El motivo es obligatorio; el original queda.</summary>
    Task<CambioDeCalificacion?> AjustarAsync(string actor, string calificacionId, decimal puntajeNuevo, string motivo, int versionEsperada, string solicitudId, CancellationToken ct = default);
    Task<CambioDeCalificacion?> ReabrirAsync(string actor, string calificacionId, string motivo, int versionEsperada, string solicitudId, CancellationToken ct = default);
    /// <summary>La valoración pedagógica del nivel de desempeño (<paramref name="tramo"/> vacío la retira).</summary>
    Task<CambioDeCalificacion?> ValorarAsync(string actor, string calificacionId, string tramo, string motivo, int versionEsperada, string solicitudId, CancellationToken ct = default);
    Task<CambioDeCalificacion?> RetroalimentarAsync(string actor, string calificacionId, IReadOnlyDictionary<string, string> campos, string? adaptacion, int versionEsperada, string solicitudId, CancellationToken ct = default);

    // ---- publicar (extensión técnica propuesta)
    Task<CambioDeCalificacion?> PublicarAsync(string actor, string calificacionId, int? versionEsperada = null, string? solicitudId = null, CancellationToken ct = default);
    Task<CambioDeCalificacion?> RetirarPublicacionAsync(string actor, string calificacionId, string motivo, int versionEsperada, string solicitudId, CancellationToken ct = default);
    Task<PublicacionDeAsignacion?> PublicarAsignacionAsync(string actor, string asignacionId, CancellationToken ct = default);

    // ---- configuración académica (FUN-124, FUN-125)
    Task<ConfiguracionAcademica?> ConfiguracionAsync(string actor, CancellationToken ct = default);
    Task<PlantillasDeEscalas?> PlantillasAsync(string actor, string? pais = null, CancellationToken ct = default);
    Task<EscalaAdoptada?> AdoptarPlantillaAsync(string actor, string plantilla, string? jurisdiccion = null, string? nota = null, CancellationToken ct = default);
    /// <summary>La conversión de unos resultados internos de muestra con una plantilla (o una versión adoptada): no guarda nada.</summary>
    Task<VistaPreviaDeEscala?> VistaPreviaAsync(string actor, string? plantilla, string? versionId, IReadOnlyList<decimal> valores, CancellationToken ct = default);
    /// <summary>Comprueba las precondiciones de un cambio de modo sin hacerlo: si se puede, qué lo impide y qué advertencias hay.</summary>
    Task<ValidacionDeNivel?> ValidarNivelAsync(string actor, string nivel, string modo, string? escalaId, CancellationToken ct = default);
    Task<NivelCambiado?> ConfigurarNivelAsync(string actor, string nivel, string modo, string? escalaId, CancellationToken ct = default);
    /// <summary>Qué intento cuenta cuando un estudiante presenta una evaluación más de una vez: <c>ultimo</c>, <c>mejor</c>, <c>primero</c> o <c>promedio</c>. Recalcula lo derivado; ninguna calificación cambia.</summary>
    Task<PoliticaConfigurada?> ConfigurarPoliticaAsync(string actor, string politicaIntentos, CancellationToken ct = default);
}

/// <summary>Cliente de <c>/api/gradebook/mias/</c> para la TABLETA del alumno (Student): sus resultados, nunca una nota sin publicar y nunca un número en modo simple.</summary>
public interface IGradebookAlumnoApi
{
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }

    Task<MisResultados?> MisResultadosAsync(string? alumnoId = null, string? dispositivo = null, CancellationToken ct = default);
}

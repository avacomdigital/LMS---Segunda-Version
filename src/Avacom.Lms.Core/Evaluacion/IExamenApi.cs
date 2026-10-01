using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Evaluacion;

/// <summary>Lo que la tableta cuenta de sí misma al abrir un intento: el nodo lo guarda en <c>m09_dispositivo</c> (nombre, plataforma, capacidad de control).</summary>
public sealed record DatosDeTableta(string? Nombre = null, string? Plataforma = null, string? VersionApp = null, string? CapacidadControl = null);

/// <summary>
/// Lo que la tableta manda en cada latido (cada 5 s): por dónde va, cuánto lleva según su cronómetro monotónico (el nodo toma el MAYOR de los dos valores
/// acotado por el tiempo real, de modo que desconectarse no regala tiempo) y lo que declara poder garantizar. Nada de esto decide: el reloj es del nodo.
/// </summary>
public sealed record LatidoDeTableta(
    string? PreguntaActual = null, long? TranscurridoMs = null, long? HoraTabletaMs = null, string? CapacidadControl = null,
    int? BateriaPct = null, int? EspacioLibreMb = null);

/// <summary>
/// Cliente de <c>/api/evaluacion/</c> (MOD-010) para la TABLETA del alumno (Student). Contrato en
/// <c>spec-driven/06-evaluation-delivery/backend.md</c> §4.4.
///
/// Mismas reglas de degradación que el resto de clientes del LMS: un error HTTP o de red NO es una excepción, devuelve <c>null</c> (o <c>false</c>) y deja
/// el motivo en <see cref="UltimoMotivo"/> y el <c>codigo</c> del backend en <see cref="UltimoError"/> (<c>intento_cerrado</c>, <c>asignacion_cerrada</c>,
/// <c>resultados_no_liberados</c>, <c>admision_rechazada</c>…). Con <see cref="UltimoError"/>.Estado == 0 no hay conexión con el aula.
///
/// Al aparato se le identifica con su huella (<c>dispositivo</c>); <c>alumnoId</c> sólo lo manda una tableta compartida sin sesión (D-19).
/// </summary>
public interface IExamenAlumnoApi
{
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }

    /// <summary>El «¿Quién eres?» sin sesión: los alumnos de los grupos con una evaluación abierta. Sin conexión devuelve null.</summary>
    Task<EstudiantesDeExamen?> EstudiantesAsync(CancellationToken ct = default);

    /// <summary>Las evaluaciones que le alcanzan al alumno (programadas, abiertas y, con <paramref name="todas"/>, las cerradas de la última semana en que tiene intento).</summary>
    Task<MisEvaluaciones?> MisAsync(string dispositivo, string? alumnoId = null, bool todas = false, CancellationToken ct = default);

    /// <summary>PAN-120: duración, condiciones del nivel y qué se registra, ANTES de empezar.</summary>
    Task<AntesalaDeExamen?> AntesalaAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default);

    /// <summary>FUN-109. Idempotente. Una tableta que no alcanza el nivel recibe <see cref="AperturaDeIntento.EnEsperaDeAdmision"/> (202) y el intento NO empieza.</summary>
    Task<AperturaDeIntento?> AbrirAsync(string dispositivo, string asignacionId, DatosDeTableta? tableta = null, string? alumnoId = null, CancellationToken ct = default);

    Task<EstadoDeIntento?> EstadoAsync(string dispositivo, string intentoId, string? alumnoId = null, CancellationToken ct = default);

    /// <summary>El punto de recuperación de 5 s. Responde lo mismo que <see cref="EstadoAsync"/>: el latido es también el sondeo.</summary>
    Task<EstadoDeIntento?> LatirAsync(string dispositivo, string intentoId, LatidoDeTableta latido, string? alumnoId = null, CancellationToken ct = default);

    /// <summary>El examen DE ESTE ALUMNO, en su orden y sin ninguna clave.</summary>
    Task<PreguntasDeIntento?> PreguntasAsync(string dispositivo, string intentoId, string? alumnoId = null, CancellationToken ct = default);

    /// <summary>FUN-110/111. Hasta 200 por llamada (lo que sale de la cola local). <paramref name="origen"/>: <c>directo</c> o <c>cola</c>.</summary>
    Task<AcuseDeRespuestas?> EnviarRespuestasAsync(string dispositivo, string intentoId, IReadOnlyList<RespuestaDeExamen> respuestas, string origen = "directo",
                                                   string? preguntaActual = null, long? transcurridoMs = null, string? alumnoId = null, CancellationToken ct = default);

    /// <summary>FUN-117. Idempotente por <c>ref_cliente</c>. Sólo los tipos que ve la tableta (<see cref="TiposDeIncidente.DeLaTableta"/>).</summary>
    Task<AcuseDeIncidentes?> EnviarIncidentesAsync(string dispositivo, string intentoId, IReadOnlyList<IncidenteDeTableta> incidentes, string? alumnoId = null, CancellationToken ct = default);

    /// <summary>D-12: lo que la tableta LOGRÓ aplicar del plan. El nodo no presume que se aplicó.</summary>
    Task<AcuseDeBloqueo?> InformarBloqueoAsync(string dispositivo, string intentoId, InformeDeBloqueo informe, string? alumnoId = null, CancellationToken ct = default);

    /// <summary>FUN-114. <paramref name="confirmar"/> es obligatorio si quedan reactivos sin responder. Idempotente.</summary>
    Task<EntregaDeIntento?> EntregarAsync(string dispositivo, string intentoId, bool confirmar, IReadOnlyList<RespuestaDeExamen>? respuestas = null,
                                          long? transcurridoMs = null, string? alumnoId = null, CancellationToken ct = default);

    /// <summary>Sólo cuando el profesor liberó los resultados (DEC-032); antes, <c>resultados_no_liberados</c> (403).</summary>
    Task<ResultadoDeIntento?> ResultadoAsync(string dispositivo, string intentoId, string? alumnoId = null, CancellationToken ct = default);
}

/// <summary>
/// Cliente de <c>/api/evaluacion/</c> (MOD-010) para el PROFESOR (OPS), §4.1 a §4.3 del contrato. El profesor se identifica con <c>actor</c>
/// (y <c>actor_rotulo</c>) mientras el nodo no exija sesión (Q-34); con sesión manda el JWT.
/// </summary>
public interface IExamenDocenteApi
{
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }

    // ---- asignaciones
    Task<ListaDeAsignaciones?> AsignacionesAsync(string actor, string? estado = null, string? grupoId = null, string? sesionId = null, CancellationToken ct = default);
    Task<AsignacionDeExamen?> AsignacionAsync(string actor, string asignacionId, CancellationToken ct = default);
    /// <summary>FUN-108 + FUN-105 + FUN-106. <c>nivel_examen</c> es obligatorio: el sistema nunca preselecciona «Controlado» por el profesor.</summary>
    Task<AsignacionDeExamen?> CrearAsync(string actor, string? actorRotulo, NuevoExamen nuevo, CancellationToken ct = default);
    Task<AsignacionDeExamen?> IniciarAsync(string actor, string asignacionId, CancellationToken ct = default);
    Task<AsignacionDeExamen?> CerrarAsync(string actor, string asignacionId, string? motivo = null, CancellationToken ct = default);
    Task<AsignacionDeExamen?> ProrrogarAsync(string actor, string asignacionId, long limiteEn, CancellationToken ct = default);
    Task<AsignacionDeExamen?> ReabrirAsync(string actor, string asignacionId, long? limiteEn = null, CancellationToken ct = default);
    Task<AsignacionDeExamen?> ConfigurarPlazoAsync(string actor, string asignacionId, long limiteEn, string? plazo = null, int? graciaMin = null, CancellationToken ct = default);
    Task<AsignacionDeExamen?> EndurecerAsync(string actor, string asignacionId, long? limiteEn = null, CancellationToken ct = default);
    /// <summary>FUN-105: fija el nivel ANTES de que haya intentos vivos.</summary>
    Task<AsignacionDeExamen?> DefinirNivelAsync(string actor, string asignacionId, string nivel, CancellationToken ct = default);
    /// <summary>FUN-118: baja el nivel de una evaluación en curso (nunca sube) con un motivo.</summary>
    Task<AsignacionDeExamen?> DegradarAsync(string actor, string asignacionId, string nivel, string motivo, CancellationToken ct = default);
    Task<AsignacionDeExamen?> LiberarResultadosAsync(string actor, string asignacionId, CancellationToken ct = default);

    // ---- vigilar y decidir
    Task<PanelDeExamen?> PanelAsync(string actor, string asignacionId, CancellationToken ct = default);
    Task<ElegibilidadDeTabletas?> ElegibilidadAsync(string actor, string asignacionId, string? nivel = null, CancellationToken ct = default);
    Task<ListaDeAdmisiones?> AdmisionesAsync(string actor, string asignacionId, bool todas = false, CancellationToken ct = default);
    /// <summary>FUN-116 / BR-076. <c>admitir</c> exige un nivel MENOR que el exigido y un motivo; <c>rechazar</c>, un motivo.</summary>
    Task<AdmisionPendiente?> DecidirAdmisionAsync(string actor, string asignacionId, string admisionId, string decision, string? nivelAdmitido, string motivo, CancellationToken ct = default);
    /// <summary>Guion paso 12: cuántos esperan reactivación, ANTES de confirmar (no cambia nada).</summary>
    Task<ReactivacionHecha?> ContarSuspendidosAsync(string actor, string asignacionId, CancellationToken ct = default);
    /// <summary>Guion paso 12: reactiva a todos los suspendidos y dice a cuántos afectó.</summary>
    Task<ReactivacionHecha?> ReactivarTodosAsync(string actor, string asignacionId, CancellationToken ct = default);
    Task<ResultadosDeExamen?> ResultadosAsync(string actor, string asignacionId, CancellationToken ct = default);

    // ---- el intento
    Task<ExpedienteDeIntento?> ExpedienteAsync(string actor, string intentoId, CancellationToken ct = default);
    Task<RevisionDeIntento?> RevisionAsync(string actor, string intentoId, CancellationToken ct = default);
    Task<ReactivacionHecha?> ReactivarAsync(string actor, string intentoId, string? desdePregunta = null, CancellationToken ct = default);
    Task<bool> CerrarIntentoAsync(string actor, string intentoId, CancellationToken ct = default);
    /// <summary>La ÚNICA flecha hacia <c>anulado</c> (INV-018): una persona con nombre y un motivo escrito.</summary>
    Task<bool> AnularAsync(string actor, string intentoId, string motivo, CancellationToken ct = default);
    Task<PuntajeAsentado?> PuntuarAsync(string actor, string intentoId, string preguntaRef, double puntaje, string? comentario = null, string? motivo = null, CancellationToken ct = default);
    Task<IntentoPublicado?> PublicarAsync(string actor, string intentoId, CancellationToken ct = default);
    Task<bool> DecidirEnvioAsync(string actor, string intentoId, string decision, string? motivo = null, CancellationToken ct = default);
    Task<bool> RecalificarAsync(string actor, string intentoId, CancellationToken ct = default);
}

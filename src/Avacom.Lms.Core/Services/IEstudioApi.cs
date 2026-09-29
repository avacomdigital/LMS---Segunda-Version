using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>
/// Cliente de <c>/api/modo-estudio/</c> (MOD-008 · Modo Estudio) para Student (alumno) y OPS (profesor). Contrato en
/// <c>spec-driven/04-modo-estudio/02-modelo-y-api.md</c>.
///
/// Mismas reglas de degradación que <see cref="IAulaApi"/>: un error HTTP o de red NO es una excepción, devuelve <c>null</c> (o
/// <c>false</c>) y deja el motivo en <see cref="UltimoMotivo"/> y el <c>codigo</c> del backend en <see cref="UltimoError"/>
/// (<c>descarga_denegada</c>, <c>bloques_pendientes</c>, <c>paquete_vencido</c>, <c>fuente_no_disponible</c>…). Con
/// <see cref="UltimoError"/>.Estado == 0 no hay conexión con el aula.
///
/// Al aparato se le identifica con su huella (<c>dispositivo</c> = <c>Sesion.Dispositivo</c>); <c>alumnoId</c> sólo lo manda una tableta compartida
/// sin sesión (D-3): en un aparato asignado el nodo sabe quién es.
/// </summary>
public interface IEstudioApi
{
    Uri BaseUri { get; }
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }
    Uri Absoluta(string rutaRelativa);

    // ---- estado y sesión de estudio (FUN-080, FUN-089, FUN-090)
    /// <summary>Nunca falla por el modo de estudio: <c>Disponible=false</c> con su motivo. Sin conexión devuelve null.</summary>
    Task<EstadoEstudio?> EstadoAsync(string dispositivo, string? alumnoId = null, CancellationToken ct = default);
    Task<SesionEstudio?> AbrirSesionAsync(string dispositivo, string? nombre, string? plataforma, string? versionApp, string? alumnoId = null, CancellationToken ct = default);
    Task<bool> CerrarSesionAsync(string dispositivo, int colaPendiente, bool limpiezaCompleta, string? alumnoId = null, CancellationToken ct = default);
    Task<bool> LimpiezaReintentadaAsync(string dispositivo, string resultado, CancellationToken ct = default);

    // ---- pendientes y lección (FUN-081, FUN-082, FUN-087)
    Task<AsignacionesEstudio?> AsignacionesAsync(string dispositivo, string? alumnoId = null, CancellationToken ct = default);
    Task<AsignacionAlumno?> AsignacionAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default);
    Task<LeccionEstudio?> LeccionAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default);
    /// <summary>Monótono: registra bloques vistos, el bloque actual y su posición. <c>capturadoEn</c> ya va normalizado al reloj del nodo.</summary>
    Task<ProgresoEstudio?> ProgresoAsync(string dispositivo, string asignacionId, IReadOnlyList<string> bloquesVistos, string? bloqueActual,
                                         int? posicionSeg, long? capturadoEn = null, string? alumnoId = null, CancellationToken ct = default);
    /// <summary>409 <c>bloques_pendientes</c> si faltan obligatorios: el error trae <c>faltan</c> en <see cref="ErrorAula.Extra"/>.</summary>
    Task<CompletadaEstudio?> CompletarAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default);

    // ---- práctica autocalificable, separada de la evaluación formal (FUN-083, FUN-088)
    Task<PracticaAbierta?> PracticaAsync(string dispositivo, string asignacionId, string? objetoRef = null, bool nueva = false, string? alumnoId = null, CancellationToken ct = default);
    Task<AcusePractica?> ResponderAsync(string dispositivo, string practicaId, IReadOnlyList<RespuestaPractica> respuestas, bool terminar = false,
                                        string? alumnoId = null, CancellationToken ct = default);
    Task<AcusePractica?> TerminarPracticaAsync(string dispositivo, string practicaId, string? alumnoId = null, CancellationToken ct = default);

    // ---- paquete de estudio (FUN-084, FUN-085)
    /// <summary>Aparato compartido: null con <c>UltimoError.Codigo == "descarga_denegada"</c>; el paquete «denegado» viaja en <c>Extra.paquete</c>.</summary>
    Task<PaqueteEstudio?> SolicitarPaqueteAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default);
    Task<ListaPaquetes?> PaquetesAsync(string dispositivo, string? alumnoId = null, CancellationToken ct = default);
    Task<PaqueteEstudio?> PaqueteAsync(string dispositivo, string paqueteId, string? alumnoId = null, CancellationToken ct = default);
    Task<ManifiestoPaquete?> ManifiestoAsync(string dispositivo, string paqueteId, string? alumnoId = null, CancellationToken ct = default);
    /// <summary>
    /// El archivo de un medio, en streaming y reanudable: <paramref name="desdeByte"/> manda <c>Range: bytes=N-</c>. Devuelve la respuesta
    /// abierta (200 o 206) para que quien llama la lea y la libere; null si el backend respondió un error (queda en <see cref="UltimoError"/>).
    /// </summary>
    Task<HttpResponseMessage?> ArchivoAsync(string dispositivo, string paqueteId, string mediaRef, long? desdeByte = null, string? alumnoId = null, CancellationToken ct = default);
    Task<PaqueteEstudio?> ConfirmarPaqueteAsync(string dispositivo, string paqueteId, string huella, long bytes, string? alumnoId = null, CancellationToken ct = default);
    Task<bool> RetirarPaqueteAsync(string dispositivo, string paqueteId, string? alumnoId = null, CancellationToken ct = default);

    // ---- trabajo sin red (FUN-086)
    Task<AcuseSync?> SincronizarAsync(string dispositivo, string emisorId, IReadOnlyList<EventoEstudio> eventos, string? alumnoId = null, CancellationToken ct = default);
    Task<EstadoSync?> EstadoSyncAsync(string dispositivo, string emisorId, CancellationToken ct = default);

    // ---- profesor · OPS (CAP-050, CAP-051)
    Task<GruposDocente?> GruposAsync(string actor, CancellationToken ct = default);
    Task<ListaAsignacionesDocente?> AsignacionesDocenteAsync(string actor, string? grupoId = null, string? estado = null, CancellationToken ct = default);
    Task<AsignacionDocente?> CrearAsignacionAsync(string actor, string? actorRotulo, NuevaAsignacion nueva, CancellationToken ct = default);
    Task<AsignacionDocente?> AsignacionDocenteAsync(string actor, string asignacionId, CancellationToken ct = default);
    Task<AsignacionDocente?> CambiarAsignacionAsync(string actor, string asignacionId, CambiosAsignacion cambios, CancellationToken ct = default);
    Task<AsignacionDocente?> CerrarAsignacionAsync(string actor, string asignacionId, CancellationToken ct = default);
    /// <summary>BR-074: el profesor acepta o descarta lo que quedó pendiente de su decisión.</summary>
    Task<bool> DecidirAsync(string actor, string asignacionId, string alumnoId, long secuencia, string? emisorId, string decision, CancellationToken ct = default);
}

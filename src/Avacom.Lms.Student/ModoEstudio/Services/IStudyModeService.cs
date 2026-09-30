using Avacom.Lms.Core.Models;
using Avacom.Lms.Student.ModoEstudio.Models;

namespace Avacom.Lms.Student.ModoEstudio.Services;

/// <summary>
/// Los datos de una lección tal como los entrega el servicio: sin textos de pantalla ni comandos. El ViewModel los vuelca en su
/// <see cref="StudyLessonItem"/> (uno por lección), y cuando algo cambia llega otro <c>StudyLessonData</c> con el mismo <c>Id</c> y sólo se
/// repinta esa tarjeta.
/// </summary>
public sealed record StudyLessonData(
    string Id,
    string Subject,
    string UnitName,
    string Title,
    string Description,
    DateTimeOffset? DueDate,
    DateTimeOffset? CompletedOn,
    double Progress,
    int CompletedBlocks,
    int TotalBlocks,
    StudyLessonState State,
    bool CanResume,
    string ResumeLabel,
    StudyDownloadState DownloadState,
    double DownloadProgress,
    long DownloadedBytes,
    long TotalBytes,
    bool CanDownload,
    string DownloadDeniedReason,
    bool HasPractice,
    string PracticeTitle,
    int PracticeQuestionCount,
    int PracticeAttempts,
    int? PracticeBestScore,
    bool PracticeInProgress,
    bool HasExam,
    string ExamTitle,
    string ExamAvailability,
    bool IsPendingSync);

/// <summary>
/// El resultado de pedir la lista: del aula si contestó, de la tableta si no (para verla sin conexión). <c>NeedsIdentity</c>: todavía no se sabe
/// quién estudia; la pantalla pregunta «¿Quién eres?» antes de mostrar nada.
/// </summary>
public sealed record StudyListResult(IReadOnlyList<StudyLessonData> Lessons, bool FromCache, bool AulaReachable, string? Notice, bool NeedsIdentity = false)
{
    public static readonly StudyListResult Empty = new([], false, true, null);
    public static readonly StudyListResult AskWho = new([], false, true, null, true);
}

/// <summary>Una persona que se puede elegir en «¿Quién eres?». Nada la verifica: en un LMS sin sistema central, cada quien dice su nombre.</summary>
public sealed record StudyStudent(string Id, string Name);

public sealed record StudyRosterGroup(string Id, string Name, IReadOnlyList<StudyStudent> Students);

/// <summary>
/// Los nombres entre los que se elige (los grupos con lecciones asignadas), con dos sugerencias: <c>Owner</c> (a quién está asignada la tableta) y
/// <c>Last</c> (quién estudió aquí la última vez). Vienen del aula o, sin ella, de lo último que se supo (<c>FromCache</c>).
/// </summary>
public sealed record StudyRoster(IReadOnlyList<StudyRosterGroup> Groups, StudyStudent? Owner, StudyStudent? Last, bool FromCache, bool AulaReachable, string? Notice)
{
    public bool HasStudents => Groups.Any(g => g.Students.Count > 0);
}

/// <summary>Cuánto ocupa lo descargado y cuánto espacio queda (MSG-045). Nulo: no se pudo saber.</summary>
public sealed record StudyStorageInfo(long UsedBytes, long? FreeBytes);

/// <summary>
/// El servicio del modo de estudio, tal como lo ve el ViewModel. Lo implementan <c>StudyModeService</c> (aula + cola y almacén locales) y
/// <c>MockStudyModeService</c> (datos y práctica de demostración). Nada aquí lanza por falta de red: lo que no se pueda hacer sin el aula se
/// dice con un resultado, en lenguaje del alumno.
/// </summary>
public interface IStudyModeService
{
    /// <summary>Verdadero si el servicio real habla con el aula; falso en la demostración (la pantalla lo muestra discretamente).</summary>
    bool IsDemo { get; }

    /// <summary>Quién estudia ahora; nulo mientras no lo haya dicho (o si pulsó «Cambiar»).</summary>
    StudyStudent? CurrentStudent { get; }

    /// <summary>Los nombres entre los que se elige (grupos con lecciones asignadas), del aula o de lo último que se supo de ella.</summary>
    Task<StudyRoster> GetRosterAsync(CancellationToken ct = default);

    /// <summary>
    /// La persona dice quién es (D-15): sin código y sin contraseña. Si es otra que la última en esta tableta, se le deja el aparato limpio de lo de
    /// la anterior (su trabajo sin enviar sigue guardado y sale solo). El profesor verá el avance con este nombre.
    /// </summary>
    Task<bool> ChooseStudentAsync(StudyStudent student, CancellationToken ct = default);

    /// <summary>«¿No eres tú?»: vuelve a preguntar quién estudia. Lo de la persona anterior no se toca hasta que otra se elija.</summary>
    Task ChangeStudentAsync(CancellationToken ct = default);

    /// <summary>Las lecciones asignadas, con el estado de su descarga en este aparato. Sin persona elegida devuelve <see cref="StudyListResult.AskWho"/>.</summary>
    Task<StudyListResult> LoadAsync(CancellationToken ct = default);

    /// <summary>Cambió una lección sin que el alumno lo pidiera (llegó de la sincronización o venció).</summary>
    event Action<StudyLessonData>? LessonChanged;

    /// <summary>✓ Guardado · ↑ Pendiente de enviar · ↻ Sincronizando.</summary>
    StudySyncState SyncState { get; }
    int PendingSyncCount { get; }
    event Action? SyncStateChanged;

    /// <summary>Intenta enviar ahora lo pendiente. Sin aula no pasa nada y todo queda guardado.</summary>
    Task SyncNowAsync(CancellationToken ct = default);

    Task<StudyStorageInfo> GetStorageAsync();

    /// <summary>Prepara la lección para leerla: desde el paquete descargado o, con aula, en línea. Nulo en <c>Error</c> si no se pudo.</summary>
    Task<StudyLessonOpen> OpenLessonAsync(string lessonId, CancellationToken ct = default);

    /// <summary>Abre (o reanuda) una práctica. Con <paramref name="retry"/> empieza un intento nuevo.</summary>
    Task<StudyPracticeOpen> OpenPracticeAsync(string lessonId, bool retry, CancellationToken ct = default);

    /// <summary>
    /// «Salir» (FUN-089, BR-053): cierra la sesión de estudio en el aula (si contesta, con un tope corto) y suelta lo que la pantalla tenía en
    /// memoria. Nunca pierde nada: lo pendiente queda en la cola cifrada de la tableta y sale solo (BR-137).
    /// </summary>
    Task CloseSessionAsync(CancellationToken ct = default);

    /// <summary>La evaluación formal se explica, no se practica: el texto que ve el alumno al pedir información.</summary>
    string ExamExplanation(string lessonId);

    /// <summary>La URL que la pantalla puede pintar para una ruta del contenido (imagen, audio…) de una lección: del aula, o del paquete descargado.</summary>
    Uri ResolveMedia(string lessonId, string relativeUrl);
}

/// <summary>Un bloque de la lección: una lámina, una página, un laboratorio o la práctica. «Actividad 4 de 7» es su posición.</summary>
public sealed record StudyBlock(
    string Ref, int Index, string Kind, string Title, bool Required, bool Attended, ObjetoAula? Objeto, string? UnidadRef)
{
    public bool IsPractice => Kind == "practica";
    public bool NeedsAula => Kind == "laboratorio";
}

public sealed record StudyCompleteResult(bool Completed, string Message, IReadOnlyList<string> Missing);

/// <summary>Una lección abierta para leer. Cada bloque visto se guarda en la tableta y sale solo hacia el aula.</summary>
public interface IStudyLessonSession
{
    string LessonId { get; }
    string Title { get; }
    string Eyebrow { get; }
    IReadOnlyList<StudyBlock> Blocks { get; }
    int StartIndex { get; }

    /// <summary>La lección se lee del paquete descargado (sin red) y no del aula.</summary>
    bool IsOfflineContent { get; }

    /// <summary>La asignación ya se cerró: se lee, pero no se registra avance.</summary>
    bool IsReadOnly { get; }

    /// <summary>La lección ya está completada (se puede releer; no hay nada más que marcar).</summary>
    bool IsCompleted { get; }

    /// <summary>Convierte una ruta del contenido (imagen, audio, pdf…) en la URL que la pantalla puede pintar.</summary>
    Uri Resolve(string relativeUrl);

    /// <summary>Marca el bloque como atendido (idempotente): guarda en la tableta primero y avisa al aula cuando puede.</summary>
    Task MarkViewedAsync(StudyBlock block, CancellationToken ct = default);

    bool IsAttended(StudyBlock block);
    int AttendedRequired { get; }
    int Required { get; }
    bool AllRequiredAttended { get; }

    /// <summary>Marca la lección como completada. Si faltan bloques obligatorios dice cuáles.</summary>
    Task<StudyCompleteResult> CompleteAsync(CancellationToken ct = default);

    /// <summary>Vuelve a leer lo hecho (al regresar de la práctica, por ejemplo): bloques atendidos y estado de la lección.</summary>
    Task RefreshAsync(CancellationToken ct = default);

    /// <summary>Cambia cuando se marca un bloque o se completa.</summary>
    event Action? Changed;
}

/// <summary>La respuesta de <see cref="IStudyModeService.OpenLessonAsync"/>: la lección abierta o el motivo, dicho con amabilidad.</summary>
public sealed record StudyLessonOpen(IStudyLessonSession? Session, string? ErrorTitle, string? ErrorMessage)
{
    public bool Ok => Session is not null;
}

public sealed record StudyPracticeOpen(IStudyPracticeSession? Session, string? ErrorTitle, string? ErrorMessage)
{
    public bool Ok => Session is not null;
}

using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Student.ModoEstudio.Services;

/// <summary>
/// Una lección real abierta para leer, del aula o del paquete descargado. Marcar un bloque lo guarda PRIMERO en la tableta (avance local y cola
/// cifrada) y sale solo hacia el aula; completar exige todos los bloques obligatorios atendidos (FUN-087) y también se guarda antes de enviarse.
/// Con la asignación cerrada se lee, pero no se registra nada.
/// </summary>
internal sealed class StudyLessonSession : IStudyLessonSession
{
    private readonly StudyModeService _servicio;
    private readonly List<StudyBlock> _bloques;
    private readonly HashSet<string> _atendidos;

    public StudyLessonSession(StudyModeService servicio, string lessonId, string title, string eyebrow, List<StudyBlock> bloques, int startIndex,
                              bool isOfflineContent, bool isReadOnly, bool isCompleted)
    {
        _servicio = servicio;
        LessonId = lessonId;
        Title = title;
        Eyebrow = eyebrow;
        _bloques = bloques;
        _atendidos = new HashSet<string>(bloques.Where(b => b.Attended).Select(b => b.Ref), StringComparer.Ordinal);
        StartIndex = startIndex;
        IsOfflineContent = isOfflineContent;
        IsReadOnly = isReadOnly;
        IsCompleted = isCompleted;
    }

    public string LessonId { get; }
    public string Title { get; }
    public string Eyebrow { get; }
    public IReadOnlyList<StudyBlock> Blocks => _bloques;
    public int StartIndex { get; }
    public bool IsOfflineContent { get; }
    public bool IsReadOnly { get; }
    public bool IsCompleted { get; private set; }
    public event Action? Changed;

    public Uri Resolve(string relativeUrl) => _servicio.ResolveMedia(LessonId, relativeUrl);

    public bool IsAttended(StudyBlock block) => _atendidos.Contains(block.Ref);
    public int Required => _bloques.Count(b => b.Required);
    public int AttendedRequired => _bloques.Count(b => b.Required && _atendidos.Contains(b.Ref));
    public bool AllRequiredAttended => AttendedRequired >= Required;

    public Task MarkViewedAsync(StudyBlock block, CancellationToken ct = default)
    {
        if (!_atendidos.Add(block.Ref)) return Task.CompletedTask;
        if (!IsReadOnly && !IsCompleted)
        {
            try { _servicio.RegistrarBloque(LessonId, block.Ref); }
            catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyLessonSession.MarkViewed", ex); }
        }
        Changed?.Invoke();
        return Task.CompletedTask;
    }

    public Task<StudyCompleteResult> CompleteAsync(CancellationToken ct = default)
    {
        if (IsReadOnly)
            return Task.FromResult(new StudyCompleteResult(false, "Esta asignación ya se cerró: puedes leerla, pero ya no se registra tu avance.", []));
        if (IsCompleted)
            return Task.FromResult(new StudyCompleteResult(true, "Esta lección ya está completada.", []));
        if (!AllRequiredAttended)
        {
            var faltan = _bloques.Where(b => b.Required && !_atendidos.Contains(b.Ref)).Select(b => b.Title).ToList();
            return Task.FromResult(new StudyCompleteResult(false, "Todavía te faltan actividades por ver.", faltan));
        }
        try { _servicio.RegistrarCompletada(LessonId); }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "StudyLessonSession.Complete", ex);
            return Task.FromResult(new StudyCompleteResult(false, "No pudimos guardar que terminaste. Inténtalo de nuevo.", []));
        }
        IsCompleted = true;
        Changed?.Invoke();
        return Task.FromResult(new StudyCompleteResult(true, "¡Lección completada!", []));
    }

    public Task RefreshAsync(CancellationToken ct = default)
    {
        try
        {
            var tarea = _servicio.LeerTarea(LessonId);
            var cambio = false;
            foreach (var vista in tarea.BloquesVistos)
                if (_bloques.Any(b => b.Ref == vista) && _atendidos.Add(vista)) cambio = true;
            if (tarea.Completada && !IsCompleted)
            {
                IsCompleted = true;
                cambio = true;
            }
            if (cambio) Changed?.Invoke();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyLessonSession.Refresh", ex); }
        return Task.CompletedTask;
    }
}

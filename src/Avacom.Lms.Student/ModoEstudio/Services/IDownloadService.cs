using Avacom.Lms.Student.ModoEstudio.Models;

namespace Avacom.Lms.Student.ModoEstudio.Services;

/// <summary>Un cambio en la descarga de una lección: estado, avance, bytes y estimación. <c>Message</c> es para el alumno, sin códigos.</summary>
public sealed record StudyDownloadUpdate(
    string LessonId, StudyDownloadState State, double Progress, long DownloadedBytes, long TotalBytes, TimeSpan? Remaining, string? Message = null);

/// <summary>
/// Las descargas del modo de estudio (CAP-047). Nunca bloquean la interfaz: <see cref="StartAsync"/> vuelve enseguida y el avance llega
/// por <see cref="Updated"/>. Pausar conserva lo bajado y volver a empezar continúa donde se quedó (descarga reanudable).
/// </summary>
public interface IDownloadService
{
    event Action<StudyDownloadUpdate>? Updated;

    /// <summary>Empieza o continúa la descarga de la lección. Sale de inmediato; el avance llega por <see cref="Updated"/>.</summary>
    Task StartAsync(string lessonId);

    /// <summary>Pausa: lo ya descargado se queda.</summary>
    void Pause(string lessonId);

    /// <summary>Borra lo descargado de esa lección (el avance del alumno no se toca).</summary>
    Task DeleteAsync(string lessonId);

    /// <summary>Hay una descarga en marcha para esa lección.</summary>
    bool IsActive(string lessonId);
}

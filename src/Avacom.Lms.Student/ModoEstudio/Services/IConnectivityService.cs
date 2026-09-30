namespace Avacom.Lms.Student.ModoEstudio.Services;

/// <summary>
/// ¿Se ve el aula? No es lo mismo que «hay red»: una tableta puede tener Wi-Fi y no llegar al equipo del aula (o al revés, estar en la red
/// del aula sin internet). Sólo importa lo segundo: el modo de estudio es offline-first y jamás bloquea lo ya descargado.
/// </summary>
public interface IConnectivityService
{
    /// <summary>El aula contestó la última vez que se le preguntó.</summary>
    bool IsOnline { get; }

    /// <summary>Cambió la respuesta (verdadero = se ve el aula).</summary>
    event Action<bool>? Changed;

    /// <summary>Pregunta ahora al aula (con un tope corto) y actualiza <see cref="IsOnline"/>.</summary>
    Task<bool> ProbeAsync(CancellationToken ct = default);
}

/// <summary>
/// Las decisiones de navegación y de diálogo del modo de estudio, aparte del ViewModel: así éste no conoce Shell ni las páginas y las
/// pruebas pueden sustituirlo.
/// </summary>
public interface IStudyNavigation
{
    Task CloseAsync();
    Task OpenLessonAsync(string lessonId);
    Task OpenPracticeAsync(string lessonId, bool retry);
    Task ShowInfoAsync(string title, string message);

    /// <summary>Un menú de opciones (Ver información, Eliminar descarga). Devuelve el texto elegido o nulo.</summary>
    Task<string?> ChooseAsync(string title, IReadOnlyList<string> options, string? destruction = null);

    Task<bool> ConfirmAsync(string title, string message, string accept, string cancel);
}

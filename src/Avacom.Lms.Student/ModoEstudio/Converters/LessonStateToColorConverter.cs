using System.Globalization;
using Avacom.Lms.Student.ModoEstudio.Models;

namespace Avacom.Lms.Student.ModoEstudio.Converters;

/// <summary>
/// El color de la marca de estado de una lección. El parámetro dice cuál: <c>bg</c> (fondo de la píldora, por defecto), <c>fg</c> (texto)
/// o <c>accent</c> (el color fuerte, para barras). Los colores comunican estado, no adornan: pendiente amarillo, en curso azul,
/// completada verde, vencida rojo suave. Nunca es lo único que dice el estado: la píldora lleva además icono y texto.
/// </summary>
public sealed class LessonStateToColorConverter : IValueConverter
{
    private static readonly Color PendienteFondo = Color.FromArgb("#FFF7D6"), PendienteTexto = Color.FromArgb("#806600");
    private static readonly Color EnCursoFondo = Color.FromArgb("#E5F5FB"), EnCursoTexto = Color.FromArgb("#02739E");
    private static readonly Color CompletadaFondo = Color.FromArgb("#E5F6ED"), CompletadaTexto = Color.FromArgb("#017A48");
    private static readonly Color VencidaFondo = Color.FromArgb("#1AE5262B"), VencidaTexto = Color.FromArgb("#C1191D");   // rgba(229,38,43,.10)

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        var estado = value is StudyLessonState s ? s : StudyLessonState.Pending;
        var cual = (parameter as string)?.ToLowerInvariant() ?? "bg";
        return (estado, cual) switch
        {
            (StudyLessonState.Pending, "fg") => PendienteTexto,
            (StudyLessonState.Pending, "accent") => Color.FromArgb("#F3C701"),
            (StudyLessonState.Pending, _) => PendienteFondo,
            (StudyLessonState.InProgress, "fg") => EnCursoTexto,
            (StudyLessonState.InProgress, "accent") => Color.FromArgb("#01A4E1"),
            (StudyLessonState.InProgress, _) => EnCursoFondo,
            (StudyLessonState.Completed, "fg") => CompletadaTexto,
            (StudyLessonState.Completed, "accent") => Color.FromArgb("#019D60"),
            (StudyLessonState.Completed, _) => CompletadaFondo,
            (_, "fg") => VencidaTexto,
            (_, "accent") => Color.FromArgb("#E5262B"),
            _ => VencidaFondo,
        };
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}

/// <summary>El color del texto de «Guardado / Pendiente de enviar / Sincronizando».</summary>
public sealed class SyncStateToColorConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture) => value switch
    {
        StudySyncState.Syncing => Color.FromArgb("#02739E"),
        StudySyncState.PendingSend => Color.FromArgb("#806600"),
        _ => Color.FromArgb("#017A48"),
    };

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}

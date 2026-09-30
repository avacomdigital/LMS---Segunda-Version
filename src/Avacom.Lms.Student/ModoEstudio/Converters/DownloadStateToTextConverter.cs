using System.Globalization;
using Avacom.Lms.Student.ModoEstudio.Models;

namespace Avacom.Lms.Student.ModoEstudio.Converters;

/// <summary>
/// El texto de cada estado de descarga (spec §10), en español y sin conceptos técnicos. Sin parámetro devuelve la línea de estado; con
/// <c>corto</c> devuelve la etiqueta breve que se usa en filas estrechas.
/// </summary>
public sealed class DownloadStateToTextConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        var estado = value is StudyDownloadState s ? s : StudyDownloadState.None;
        var corto = string.Equals(parameter as string, "corto", StringComparison.OrdinalIgnoreCase);
        return estado switch
        {
            StudyDownloadState.Requested => corto ? "Preparando" : "Preparando la descarga…",
            StudyDownloadState.Downloading => corto ? "Descargando" : "Descargando contenido…",
            StudyDownloadState.Paused => corto ? "Pausada" : "Descarga pausada",
            StudyDownloadState.Available => corto ? "Sin conexión" : "Disponible sin conexión",
            StudyDownloadState.Expired => corto ? "Venció" : "El contenido descargado venció.",
            StudyDownloadState.Denied => corto ? "No permitida" : "Este dispositivo no permite descargar contenido para estudiar sin conexión.",
            _ => corto ? "Sin descargar" : "Aún no la has descargado",
        };
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}

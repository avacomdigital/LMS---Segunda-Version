namespace Avacom.Lms.Student.ModoEstudio.Models;

/// <summary>
/// El estado del paquete de estudio en ESTE aparato. Sigue los cinco del Maestro (solicitado, descargándose, disponible, vencido,
/// denegado por dispositivo compartido) más «sin descargar» y «pausada», que sólo existen en el aparato.
/// </summary>
public enum StudyDownloadState
{
    None,
    Requested,
    Downloading,
    Paused,
    Available,
    Expired,
    Denied,
}

using Avacom.Lms.Student.ModoEstudio.Services;

namespace Avacom.Lms.Student.ModoEstudio;

/// <summary>
/// Los servicios reales del modo de estudio, armados sobre el Core: el cliente del aula (<see cref="Sesion.Estudio"/>), el almacén y la cola
/// cifrados de la tableta, el descargador de paquetes y el servidor local de medios. Lo único que depende de la plataforma es la clave
/// (<see cref="ClaveDeStudent"/>: DPAPI en Windows, SecureStorage en Android) y la conectividad.
/// </summary>
internal static class EstudioReal
{
    public static (IStudyModeService Servicio, IDownloadService Descargas, IConnectivityService Conectividad) Crear()
    {
        var api = Sesion.Estudio;
        var dispositivo = Sesion.Dispositivo;
        var local = EstudioLocal.Crear(api, dispositivo);
        var conectividad = new ConnectivityService(api, dispositivo);
        var descargas = new DownloadService(local);
        var aparato = new DatosDelAparato(DeviceInfo.Current.Name, Sesion.Plataforma, Sesion.VersionApp);
        // Una tableta que nunca entró a una clase no está en el inventario del aula: el latido la da de alta (idempotente, por su huella).
        var servicio = new StudyModeService(local, descargas, conectividad, aparato,
            ct => Sesion.Dispositivos.LatidoAsync(dispositivo, aparato.Nombre, aparato.Plataforma, aparato.Version, ct));
        // FUN-090: si la última vez se salió con trabajo por enviar, la limpieza que quedó pendiente se termina en cuanto la cola esté vacía.
        _ = servicio.TerminarLimpiezaPendienteAsync();
        return (servicio, descargas, conectividad);
    }
}

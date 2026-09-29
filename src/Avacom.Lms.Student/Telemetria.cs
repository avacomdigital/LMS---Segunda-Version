namespace Avacom.Lms.Student;

/// <summary>
/// Lo que la tableta cuenta de sí misma con cada latido (009-04): cuánto espacio libre le queda y cuánta batería. El profesor lo lee
/// antes de distribuir un paquete (MSG-045). Es el mejor esfuerzo: si el sistema no lo da, no se manda y nada falla.
/// </summary>
public static class Telemetria
{
    /// <summary><c>{ espacio_libre_mb, bateria_pct }</c> con lo que se pudo leer, o nulo si nada.</summary>
    public static object? Leer()
    {
        int? espacio = null, bateria = null;
        try { espacio = EspacioLibreMb(); } catch { }
        try
        {
            var nivel = Battery.Default.ChargeLevel;       // 0..1; −1 si no hay batería (un equipo de escritorio)
            if (nivel >= 0) bateria = (int)Math.Round(nivel * 100);
        }
        catch { }
        return espacio is null && bateria is null ? null : new { espacio_libre_mb = espacio, bateria_pct = bateria };
    }

    private static int? EspacioLibreMb()
    {
        var carpeta = FileSystem.AppDataDirectory;
#if ANDROID
        var estado = new Android.OS.StatFs(carpeta);
        return (int)(estado.AvailableBytes / (1024 * 1024));
#else
        var raiz = Path.GetPathRoot(carpeta);
        return string.IsNullOrEmpty(raiz) ? null : (int)(new DriveInfo(raiz).AvailableFreeSpace / (1024 * 1024));
#endif
    }
}

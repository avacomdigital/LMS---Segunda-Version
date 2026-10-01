using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Student;

/// <summary>
/// Lo que la tableta cuenta de sí misma con cada latido (009-04): cuánto espacio libre le queda y cuánta batería. El profesor lo lee
/// antes de distribuir un paquete (MSG-045). Es el mejor esfuerzo: si el sistema no lo da, no se manda y nada falla.
/// </summary>
public static class Telemetria
{
    /// <summary>Umbrales de aviso (MOD-019 §2.4, canal dispositivo): se registra la TRANSICIÓN a «bajo» y la vuelta a «normal», nunca cada latido.</summary>
    public const int EspacioBajoMb = 500;
    public const int BateriaBajaPct = 15;
    private static bool _espacioBajo, _bateriaBaja;

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
        Vigilar(espacio, bateria);
        return espacio is null && bateria is null ? null : new { espacio_libre_mb = espacio, bateria_pct = bateria };
    }

    /// <summary>Lo que el aparato cuenta de sí mismo cuando cruza un umbral. Idempotente: un estado no se repite mientras no cambie.</summary>
    internal static void Vigilar(int? espacioMb, int? bateriaPct)
    {
        if (espacioMb is { } e)
        {
            var bajo = e < EspacioBajoMb;
            if (bajo && !_espacioBajo) RegistroLocal.Advertencia(Canal.Dispositivo, "espacio.bajo", "Queda poco espacio en la tableta", new { espacio_libre_mb = e, umbral_mb = EspacioBajoMb });
            else if (!bajo && _espacioBajo) RegistroLocal.Info(Canal.Dispositivo, "espacio.normal", "El espacio de la tableta volvió a la normalidad", new { espacio_libre_mb = e });
            _espacioBajo = bajo;
        }
        if (bateriaPct is { } b)
        {
            var baja = b < BateriaBajaPct;
            if (baja && !_bateriaBaja) RegistroLocal.Advertencia(Canal.Dispositivo, "bateria.baja", "La batería de la tableta está baja", new { bateria_pct = b, umbral_pct = BateriaBajaPct });
            else if (!baja && _bateriaBaja) RegistroLocal.Info(Canal.Dispositivo, "bateria.normal", "La batería volvió a un nivel normal", new { bateria_pct = b });
            _bateriaBaja = baja;
        }
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

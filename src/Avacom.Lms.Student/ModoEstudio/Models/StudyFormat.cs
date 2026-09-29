using System.Globalization;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Student.ModoEstudio.Models;

/// <summary>
/// Cómo se escriben para el alumno los tamaños, los tiempos y las fechas: en español, en cristiano y sin conceptos técnicos.
/// «Ahora» es la hora del nodo que el aparato aprendió (<see cref="RelojNodo"/>), pasada a la zona horaria de la tableta: la fecha
/// límite es del aula, no del reloj del aparato (BR-062).
/// </summary>
public static class StudyFormat
{
    private static readonly CultureInfo Es = Cultura();

    private static CultureInfo Cultura()
    {
        foreach (var nombre in new[] { "es-CO", "es-ES", "es" })
        {
            try { return CultureInfo.GetCultureInfo(nombre); }
            catch (CultureNotFoundException) { }
        }
        return CultureInfo.InvariantCulture;
    }

    /// <summary>La hora del aula ahora, con la zona de la tableta.</summary>
    public static DateTimeOffset Ahora() => DateTimeOffset.FromUnixTimeMilliseconds(RelojNodo.AhoraMs).ToLocalTime();

    public static DateTimeOffset? Fecha(long? milisegundos) =>
        milisegundos is > 0 ? DateTimeOffset.FromUnixTimeMilliseconds(milisegundos.Value).ToLocalTime() : null;

    /// <summary>«84 MB», «8,4 MB», «312 KB», «2,1 GB».</summary>
    public static string Bytes(long bytes)
    {
        if (bytes <= 0) return "0 MB";
        const double kb = 1024, mb = kb * 1024, gb = mb * 1024;
        return bytes switch
        {
            >= (long)gb => $"{(bytes / gb).ToString("0.0", Es)} GB",
            >= (long)(mb * 10) => $"{Math.Round(bytes / mb).ToString("0", Es)} MB",
            >= (long)mb => $"{(bytes / mb).ToString("0.0", Es)} MB",
            >= (long)kb => $"{Math.Round(bytes / kb).ToString("0", Es)} KB",
            _ => $"{bytes} B",
        };
    }

    /// <summary>«62 %» a partir de una fracción 0..1.</summary>
    public static string Porcentaje(double fraccion) => $"{Math.Round(Math.Clamp(fraccion, 0, 1) * 100).ToString("0", Es)} %";

    /// <summary>«2 min restantes», «menos de 1 min», «1 h 5 min restantes». Nulo si no hay estimación todavía.</summary>
    public static string? Restante(TimeSpan? restante)
    {
        if (restante is not { } r) return null;
        if (r.TotalSeconds < 45) return "Menos de 1 min";
        if (r.TotalMinutes < 60) return $"{Math.Max(1, (int)Math.Round(r.TotalMinutes))} min restantes";
        return $"{(int)r.TotalHours} h {r.Minutes} min restantes";
    }

    /// <summary>«4:00 p. m.».</summary>
    public static string Hora(DateTimeOffset fecha) => fecha.ToString("h:mm tt", Es);

    /// <summary>«4 oct.» (con el año si no es el actual).</summary>
    public static string DiaCorto(DateTimeOffset fecha, DateTimeOffset ahora) =>
        fecha.Year == ahora.Year ? fecha.ToString("d MMM", Es) : fecha.ToString("d MMM yyyy", Es);

    /// <summary>«Entrega: hoy, 4:00 p. m.» · «Entrega: mañana» · «Entrega: 4 oct.» · «Venció el 4 oct.». Vacío sin fecha.</summary>
    public static string Entrega(DateTimeOffset? limite, DateTimeOffset ahora, bool completada)
    {
        if (limite is not { } fecha || completada) return string.Empty;
        var dias = (fecha.Date - ahora.Date).Days;
        if (fecha < ahora) return $"Venció el {DiaCorto(fecha, ahora)}";
        return dias switch
        {
            0 => $"Entrega: hoy, {Hora(fecha)}",
            1 => "Entrega: mañana",
            _ => $"Entrega: {DiaCorto(fecha, ahora)}",
        };
    }

    /// <summary>La marca que acompaña a la fecha: «Vence hoy» sólo cuando queda poco; «Vencida» en su estado. Nada alarmista.</summary>
    public static string MarcaDeEntrega(DateTimeOffset? limite, DateTimeOffset ahora, bool completada)
    {
        if (limite is not { } fecha || completada || fecha < ahora) return string.Empty;
        return (fecha.Date - ahora.Date).Days == 0 ? "Vence hoy" : string.Empty;
    }

    /// <summary>«Completada el 3 oct.».</summary>
    public static string CompletadaEl(DateTimeOffset? cuando, DateTimeOffset ahora) =>
        cuando is { } c ? $"Completada el {DiaCorto(c, ahora)}" : "Lección completada";

    /// <summary>«Disponible desde el 20 de octubre».</summary>
    public static string DisponibleDesde(DateTimeOffset? desde) =>
        desde is { } d ? $"Disponible desde el {d.ToString("d 'de' MMMM", Es)}" : "Te la presentará tu profesor";
}

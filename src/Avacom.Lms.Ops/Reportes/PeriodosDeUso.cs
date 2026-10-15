using Avacom.Lms.Core.Reporting;

namespace Avacom.Lms.Ops.Reportes;

/// <summary>
/// Los periodos del reporte de uso de equipos (FUN-142) como fichas que se tocan: nadie escribe una fecha (el equipo del aula no tiene teclado). Cada ficha se traduce a los
/// instantes <c>desde</c>/<c>hasta</c> en milisegundos que entiende el nodo, contando los días del calendario del equipo (la medianoche es la local), no bloques de 24 horas.
/// <c>hasta</c> queda sin tope: significa «hasta ahora» (lo que el nodo tenga al consultar). Puro y determinista: la hora se pasa de fuera.
/// </summary>
public static class PeriodosDeUso
{
    public const string Todo = "todo", Hoy = "hoy", SieteDias = "7d", TreintaDias = "30d", EsteAnio = "anio";

    /// <summary>Las fichas, en el orden en que se ofrecen: lo más amplio primero (es lo que se espera ver al entrar).</summary>
    public static readonly IReadOnlyList<(string Clave, string Rotulo)> Fichas =
    [
        (Todo, "Todo el tiempo"),
        (EsteAnio, "Este año"),
        (TreintaDias, "Últimos 30 días"),
        (SieteDias, "Últimos 7 días"),
        (Hoy, "Hoy"),
    ];

    /// <summary>El rótulo de una clave (la desconocida se lee como «Todo el tiempo», que es lo que hace).</summary>
    public static string Rotulo(string? clave) => Fichas.FirstOrDefault(f => f.Clave == clave).Rotulo ?? Fichas[0].Rotulo;

    /// <summary>
    /// El periodo de una ficha visto desde <paramref name="ahora"/> (con la zona del equipo: su <see cref="DateTimeOffset.Offset"/>). «Hoy» arranca a la medianoche de hoy;
    /// «Últimos 7 días» incluye hoy y los seis anteriores (a partir de la medianoche del primero); «Últimos 30 días», hoy y los 29 anteriores; «Este año», desde el 1 de enero.
    /// </summary>
    public static PeriodoPedido Resolver(string? clave, DateTimeOffset ahora)
    {
        var medianoche = new DateTimeOffset(ahora.Year, ahora.Month, ahora.Day, 0, 0, 0, ahora.Offset);
        return clave switch
        {
            Hoy => new PeriodoPedido(medianoche.ToUnixTimeMilliseconds(), null),
            SieteDias => new PeriodoPedido(medianoche.AddDays(-6).ToUnixTimeMilliseconds(), null),
            TreintaDias => new PeriodoPedido(medianoche.AddDays(-29).ToUnixTimeMilliseconds(), null),
            EsteAnio => new PeriodoPedido(new DateTimeOffset(ahora.Year, 1, 1, 0, 0, 0, ahora.Offset).ToUnixTimeMilliseconds(), null),
            _ => new PeriodoPedido(null, null),
        };
    }

    /// <summary>La ficha que corresponde a un periodo ya resuelto (para volver a abrir un reporte reciente con la ficha marcada); null si no coincide con ninguna.</summary>
    public static string? ClaveDe(PeriodoPedido periodo, DateTimeOffset ahora)
    {
        if (periodo.Hasta is not null) return null;
        foreach (var (clave, _) in Fichas)
            if (Resolver(clave, ahora) == periodo) return clave;
        return null;
    }
}

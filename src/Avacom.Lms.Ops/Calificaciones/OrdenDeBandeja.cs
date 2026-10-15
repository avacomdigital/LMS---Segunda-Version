using Avacom.Lms.Core.Gradebook;

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>
/// La bandeja de revisión docente (FUN-120): qué se filtra, en qué orden se ve y cómo se dice cada renglón. Sin dependencias de MAUI: se prueba sin interfaz.
/// Primero lo que está pendiente de revisión (lo más antiguo arriba, porque es lo que más lleva esperando), después lo reabierto.
/// </summary>
internal static class OrdenDeBandeja
{
    public static IReadOnlyList<ItemDeBandeja> Filtrar(IEnumerable<ItemDeBandeja> items, string? grupoId, string? asignacionId = null) =>
        items.Where(i => (string.IsNullOrEmpty(grupoId) || i.GrupoId == grupoId) && (string.IsNullOrEmpty(asignacionId) || i.AsignacionId == asignacionId)).ToList();

    public static IReadOnlyList<ItemDeBandeja> Ordenar(IEnumerable<ItemDeBandeja> items) =>
        items.OrderBy(i => i.EsReapertura ? 1 : 0)
             .ThenBy(i => i.EntregadoEn ?? long.MaxValue)
             .ThenBy(i => i.AlumnoRotulo, StringComparer.CurrentCultureIgnoreCase)
             .ToList();

    /// <summary>Los grupos que hay en la bandeja, con cuántos renglones tiene cada uno, por nombre. El filtro por grupo sólo ofrece lo que existe.</summary>
    public static IReadOnlyList<(string Id, string Rotulo, int Cantidad)> Grupos(IEnumerable<ItemDeBandeja> items) =>
        items.GroupBy(i => i.GrupoId)
             .Select(g => (g.Key, g.Select(i => i.GrupoRotulo).FirstOrDefault(r => !string.IsNullOrWhiteSpace(r)) ?? "Grupo", g.Count()))
             .OrderBy(g => g.Item2, StringComparer.CurrentCultureIgnoreCase).ToList();

    public static string Motivo(ItemDeBandeja i) => i.EsReapertura ? "Reabierta para recalificar" : "Pendiente de revisión";

    /// <summary>Lo que falta en una frase: cuántas respuestas esperan puntaje, o que la calificación reabierta espera confirmar su revisión.</summary>
    public static string Falta(ItemDeBandeja i) => i.EsReapertura
        ? i.NPendientes > 0 ? $"Reabierta · {Respuestas(i.NPendientes)} por puntuar" : "Reabierta · confirma la revisión para volver a registrar la calificación"
        : $"Faltan {Respuestas(i.NPendientes)}";

    private static string Respuestas(int n) => n == 1 ? "1 respuesta" : $"{n} respuestas";

    /// <summary>
    /// La cifra provisional, que NO es una calificación: es el porcentaje de lo ya calificado. Nulo si el nodo no la mandó. Se dice siempre como parcial, para que
    /// no se lea como una nota definitiva.
    /// </summary>
    public static string? CifraProvisional(ItemDeBandeja i) =>
        i.PorcentajeProvisional is { } p ? $"Cifra provisional: {GradebookTexto.Puntaje(p)} % de lo ya calificado (aún no es la calificación)" : null;
}

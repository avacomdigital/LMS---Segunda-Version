using Avacom.Lms.Core.Reporting;

namespace Avacom.Lms.Ops.Reportes;

/// <summary>
/// Cómo se llega a un reporte sin escribir (FUN-143): los grupos que el nodo deja ver, sus periodos, y los alumnos de un grupo por su inicial. Todo son fichas que se tocan.
/// Es lógica pura (sin MAUI): qué fichas hay, cuál queda elegida cuando lo elegido ya no existe, y qué alumnos entran bajo una inicial.
/// </summary>
public static class ListasDeReportes
{
    /// <summary>Lo que quedó elegido: un periodo (null = todos) y un grupo (null = ninguno todavía o «todos», según la pantalla).</summary>
    public readonly record struct Eleccion(string? Periodo, GrupoParaFiltro? Grupo);

    /// <summary>Los periodos distintos de los grupos, el más reciente primero. Sin periodo no hay ficha.</summary>
    public static IReadOnlyList<string> Periodos(IReadOnlyList<GrupoParaFiltro> grupos) =>
        grupos.Select(g => g.Periodo).Where(p => !string.IsNullOrWhiteSpace(p)).Distinct().OrderByDescending(p => p, StringComparer.Ordinal).ToList();

    /// <summary>Los grupos de un periodo (todos si no se eligió ninguno), por código.</summary>
    public static IReadOnlyList<GrupoParaFiltro> Grupos(IReadOnlyList<GrupoParaFiltro> grupos, string? periodo) =>
        grupos.Where(g => periodo is null || g.Periodo == periodo).OrderBy(g => g.Rotulo, StringComparer.CurrentCultureIgnoreCase).ToList();

    /// <summary>
    /// Pone en orden lo elegido: un periodo que ya no existe se suelta; un grupo que no está en el periodo se suelta. Con <paramref name="grupoObligatorio"/> y un único grupo
    /// posible, ese queda elegido solo (nadie debería tener que tocar la única opción); con varios, la persona elige.
    /// </summary>
    public static Eleccion Resolver(IReadOnlyList<GrupoParaFiltro> grupos, string? periodo, string? grupoId, bool grupoObligatorio)
    {
        var periodoValido = periodo is not null && Periodos(grupos).Contains(periodo) ? periodo : null;
        var posibles = Grupos(grupos, periodoValido);
        var grupo = grupoId is null ? null : posibles.FirstOrDefault(g => g.Id == grupoId);
        if (grupo is null && grupoObligatorio && posibles.Count == 1) grupo = posibles[0];
        return new Eleccion(periodoValido, grupo);
    }

    /// <summary>Los alumnos que empiezan por una inicial (sin distinguir mayúsculas); sin inicial, todos.</summary>
    public static IReadOnlyList<AlumnoParaElegir> PorInicial(IReadOnlyList<AlumnoParaElegir> alumnos, string? inicial) =>
        string.IsNullOrEmpty(inicial) ? alumnos : alumnos.Where(a => string.Equals(a.Inicial, inicial, StringComparison.OrdinalIgnoreCase)).ToList();

    /// <summary>Si la inicial elegida ya no tiene alumnos (se cambió de grupo), se suelta; si la tiene, se devuelve tal como la escribe el nodo («J», aunque se haya pedido «j»).</summary>
    public static string? InicialValida(IReadOnlyList<InicialConCantidad> iniciales, string? elegida) =>
        elegida is null ? null : iniciales.FirstOrDefault(i => string.Equals(i.Inicial, elegida, StringComparison.OrdinalIgnoreCase))?.Inicial;

    /// <summary>Lo que dice la tarjeta de un grupo: cuántos alumnos tiene y cuántos necesitan atención (sin cifras que el nodo no entregó).</summary>
    public static string ResumenDeGrupo(GrupoParaFiltro grupo)
    {
        var partes = new List<string>();
        if (grupo.Alumnos is { } n) partes.Add(FormatoDeReportes.Plural(n, "alumno", "alumnos"));
        if (grupo.EnAtencion is { } a and > 0) partes.Add(a == 1 ? "1 necesita atención" : $"{a} necesitan atención");
        if (grupo.Desactualizado) partes.Add("se está actualizando");
        return partes.Count == 0 ? "Sin datos todavía" : string.Join(" · ", partes);
    }

    /// <summary>El título que se le da en una ficha a un grupo: «8A · Octavo A» (el código y el nombre cuando difieren).</summary>
    public static string RotuloLargo(GrupoParaFiltro grupo) =>
        string.IsNullOrWhiteSpace(grupo.Nombre) || string.Equals(grupo.Nombre, grupo.Codigo, StringComparison.OrdinalIgnoreCase) ? grupo.Rotulo : $"{grupo.Codigo} · {grupo.Nombre}";
}

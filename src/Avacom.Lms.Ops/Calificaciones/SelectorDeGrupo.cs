using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>Lo elegido para el libro: nivel educativo, periodo y grupo. <c>Grupo</c> nulo = no hay ninguno que elegir.</summary>
internal sealed record EleccionDeGrupo(string? Nivel, string? Periodo, GrupoPadron? Grupo);

/// <summary>
/// Nivel educativo → periodo → grupo, con lo que el padrón sabe de cada grupo. Un grupo es de un solo nivel y de un solo periodo, así que elegir el periodo sólo acota qué
/// grupos se ofrecen. Si el padrón no trae el nivel de un grupo, ese grupo cae en «sin nivel»; si ninguno lo trae, no hay nivel que elegir y se agrupa sólo por grupo.
/// Sin dependencias de MAUI: se prueba sin interfaz.
/// </summary>
internal static class SelectorDeGrupo
{
    /// <summary>La clave con la que se agrupan los grupos que no traen nivel.</summary>
    public const string SinNivel = "";

    private static string Clave(GrupoPadron g) => g.NivelClave?.Trim().ToLowerInvariant() ?? SinNivel;

    public static string RotuloDeNivel(string? clave) => (clave ?? SinNivel).Trim().ToLowerInvariant() switch
    {
        "preescolar" => "Preescolar",
        "primaria" => "Primaria",
        "secundaria" => "Secundaria",
        "bachillerato" => "Bachillerato",
        "preuniversitario" => "Preuniversitario",
        "" => "Sin nivel",
        var otro => char.ToUpperInvariant(otro[0]) + otro[1..],
    };

    /// <summary>Los niveles que hay entre los grupos, en el orden de la escuela (preescolar → preuniversitario) y al final los desconocidos.</summary>
    public static IReadOnlyList<string> Niveles(IEnumerable<GrupoPadron> grupos)
    {
        var presentes = grupos.Select(Clave).Distinct().ToList();
        var orden = NivelesEducativos.Todos.ToList();
        return presentes.OrderBy(n => orden.IndexOf(n) is var i and >= 0 ? i : orden.Count).ThenBy(n => n, StringComparer.Ordinal).ToList();
    }

    /// <summary>Los periodos de los grupos de un nivel, el más reciente primero. Sin periodo no se ofrece.</summary>
    public static IReadOnlyList<string> Periodos(IEnumerable<GrupoPadron> grupos, string? nivel) =>
        grupos.Where(g => Clave(g) == (nivel ?? SinNivel)).Select(g => g.Periodo?.Trim() ?? string.Empty).Where(p => p.Length > 0)
              .Distinct().OrderByDescending(p => p, StringComparer.Ordinal).ToList();

    /// <summary>Los grupos de un nivel y, si se eligió, de un periodo: los activos primero y por nombre.</summary>
    public static IReadOnlyList<GrupoPadron> Grupos(IEnumerable<GrupoPadron> grupos, string? nivel, string? periodo) =>
        grupos.Where(g => Clave(g) == (nivel ?? SinNivel) && (string.IsNullOrEmpty(periodo) || (g.Periodo?.Trim() ?? string.Empty) == periodo))
              .OrderByDescending(g => g.Activo).ThenBy(g => g.Nombre, StringComparer.CurrentCultureIgnoreCase).ToList();

    /// <summary>
    /// Deja una elección coherente: el nivel pedido si existe (si no, el del grupo pedido, y si no el primero), el periodo si pertenece a ese nivel (si no, «todos») y
    /// el grupo pedido si sigue a la vista (si no, el primero de la lista). Sin grupos, nada.
    /// </summary>
    public static EleccionDeGrupo Resolver(IReadOnlyList<GrupoPadron> grupos, string? nivel, string? periodo, string? grupoId)
    {
        if (grupos.Count == 0) return new(null, null, null);
        var niveles = Niveles(grupos);
        string nivelFinal;
        if (nivel is not null && niveles.Contains(nivel)) nivelFinal = nivel;
        else if (grupoId is not null && grupos.FirstOrDefault(g => g.Id == grupoId) is { } pedido) nivelFinal = Clave(pedido);
        else nivelFinal = niveles[0];

        var periodoFinal = !string.IsNullOrEmpty(periodo) && Periodos(grupos, nivelFinal).Contains(periodo) ? periodo : null;
        var visibles = Grupos(grupos, nivelFinal, periodoFinal);
        var grupo = visibles.FirstOrDefault(g => g.Id == grupoId) ?? visibles.FirstOrDefault();
        return new(nivelFinal, periodoFinal, grupo);
    }
}

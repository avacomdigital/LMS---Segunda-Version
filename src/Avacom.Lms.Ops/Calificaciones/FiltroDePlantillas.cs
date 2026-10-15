using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>
/// El catálogo de plantillas de escala (orientativas: la institución debe revisarlas y adoptarlas) filtrado por país con fichas que se tocan. Las plantillas sin país son las genéricas
/// (0–5, 0–10, 0–20, 0–100, letras, conceptual). Sin dependencias de MAUI: se prueba sin interfaz.
/// </summary>
internal static class FiltroDePlantillas
{
    /// <summary>El valor del filtro para las plantillas genéricas (las que no son de ningún país).</summary>
    public const string Genericas = "*";

    /// <summary>Los países que hay en el catálogo, por nombre. Las genéricas no son un país y no aparecen aquí.</summary>
    public static IReadOnlyList<string> Paises(IEnumerable<PlantillaDeEscala> plantillas) =>
        plantillas.Select(p => p.Pais?.Trim().ToUpperInvariant() ?? string.Empty).Where(p => p.Length > 0).Distinct()
                  .OrderBy(NombreDePais, StringComparer.CurrentCultureIgnoreCase).ToList();

    public static string NombreDePais(string codigo) => IndiceDeCursos.NombrePais(codigo) ?? codigo;

    public static bool HayGenericas(IEnumerable<PlantillaDeEscala> plantillas) => plantillas.Any(p => string.IsNullOrWhiteSpace(p.Pais));

    /// <summary>Todas (sin filtro), sólo las genéricas (<see cref="Genericas"/>) o las de un país.</summary>
    public static IReadOnlyList<PlantillaDeEscala> Filtrar(IEnumerable<PlantillaDeEscala> plantillas, string? filtro) => filtro switch
    {
        null or "" => plantillas.ToList(),
        Genericas => plantillas.Where(p => string.IsNullOrWhiteSpace(p.Pais)).ToList(),
        _ => plantillas.Where(p => string.Equals(p.Pais?.Trim(), filtro, StringComparison.OrdinalIgnoreCase)).ToList(),
    };

    /// <summary>De dónde es una plantilla, en palabras: «Colombia», «Colombia · Antioquia» o «Genérica».</summary>
    public static string Origen(PlantillaDeEscala p)
    {
        if (string.IsNullOrWhiteSpace(p.Pais)) return "Genérica";
        var pais = NombreDePais(p.Pais.Trim().ToUpperInvariant());
        return string.IsNullOrWhiteSpace(p.Jurisdiccion) ? pais : $"{pais} · {p.Jurisdiccion}";
    }
}

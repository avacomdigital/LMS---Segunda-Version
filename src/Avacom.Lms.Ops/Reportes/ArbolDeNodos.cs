using Avacom.Lms.Core.Reporting;

namespace Avacom.Lms.Ops.Reportes;

/// <summary>
/// El árbol académico de AVACOM Biblioteca (país · nivel · grado · materia · tema) como filas de fichas que se tocan, para filtrar un reporte por nodo (FUN-143) sin escribir. Cada
/// fila muestra los hermanos de un nivel; elegir uno muestra sus hijos en la fila de abajo y suelta lo que había más abajo. Lo que viaja al nodo son los CÓDIGOS (los mismos que
/// entiende la biblioteca), nunca los nombres. Puro, sin MAUI.
/// </summary>
public static class ArbolDeNodos
{
    /// <summary>Los niveles del árbol, de arriba abajo: el orden en que se eligen y el orden en que se sueltan.</summary>
    public static readonly IReadOnlyList<string> Niveles = ["country", "level", "grade", "subject", "topic"];

    /// <summary>Una fila de fichas: de qué nivel es, sus opciones y cuál está elegida (null = «todos»).</summary>
    public sealed record Fila(string Nivel, IReadOnlyList<NodoDelArbol> Opciones, string? Elegido);

    /// <summary>El código elegido en un nivel de un nodo académico.</summary>
    public static string? Valor(NodoAcademico? nodo, string nivel) => nodo is null ? null : nivel switch
    {
        "country" => nodo.Country,
        "level" => nodo.Level,
        "grade" => nodo.Grade,
        "subject" => nodo.Subject,
        "topic" => nodo.Topic,
        _ => null,
    };

    /// <summary>
    /// El nodo académico con <paramref name="codigo"/> elegido en <paramref name="nivel"/> (null o vacío = «todos» en ese nivel) y lo de MÁS ABAJO soltado: cambiar el país
    /// descarta el nivel, el grado, la materia y el tema que se habían elegido. Devuelve null si no queda ninguno elegido.
    /// </summary>
    public static NodoAcademico? Con(NodoAcademico? actual, string nivel, string? codigo)
    {
        var posicion = Niveles.ToList().IndexOf(nivel);
        if (posicion < 0) return actual;
        string? Mantener(string n) => Niveles.ToList().IndexOf(n) < posicion ? Valor(actual, n) : n == nivel ? (string.IsNullOrWhiteSpace(codigo) ? null : codigo) : null;
        var nuevo = new NodoAcademico(Mantener("country"), Mantener("level"), Mantener("grade"), Mantener("subject"), Mantener("topic"));
        return nuevo.EstaVacio ? null : nuevo;
    }

    /// <summary>
    /// Las filas de fichas que corresponden a lo elegido: la primera con los nodos de la raíz; si hay uno elegido, otra con sus hijos, y así mientras el elegido tenga hijos. Una
    /// elección que ya no existe en el árbol (la biblioteca cambió) corta la cadena ahí.
    /// </summary>
    public static IReadOnlyList<Fila> Filas(IReadOnlyList<NodoDelArbol> arbol, NodoAcademico? nodo)
    {
        var filas = new List<Fila>();
        IReadOnlyList<NodoDelArbol> actuales = arbol;
        while (actuales.Count > 0)
        {
            var nivel = actuales.Select(n => n.Kind).FirstOrDefault(k => !string.IsNullOrEmpty(k)) ?? string.Empty;
            var codigo = Valor(nodo, nivel);
            var elegido = codigo is null ? null : actuales.FirstOrDefault(n => string.Equals(n.Code, codigo, StringComparison.Ordinal));
            filas.Add(new Fila(nivel, actuales, elegido?.Code));
            if (elegido?.Children is not { Count: > 0 } hijos) break;
            actuales = hijos;
        }
        return filas;
    }

    /// <summary>El nombre que se lee en una ficha (el código cuando el nodo no trae nombre).</summary>
    public static string Rotulo(NodoDelArbol nodo) => !string.IsNullOrWhiteSpace(nodo.Name) ? nodo.Name! : nodo.Code ?? "—";

    /// <summary>«País» · «Nivel» · «Grado» · «Materia» · «Tema»: el rótulo de una fila.</summary>
    public static string RotuloDeNivel(string nivel) => nivel switch
    {
        "country" => "País",
        "level" => "Nivel",
        "grade" => "Grado",
        "subject" => "Materia",
        "topic" => "Tema",
        _ => "Más filtros",
    };

    /// <summary>Lo elegido en palabras: «Colombia › Secundaria › 8.º». Sin elección, vacío. Un código que ya no está en el árbol se muestra tal cual.</summary>
    public static string Resumen(IReadOnlyList<NodoDelArbol> arbol, NodoAcademico? nodo)
    {
        if (nodo is null || nodo.EstaVacio) return string.Empty;
        var partes = new List<string>();
        IReadOnlyList<NodoDelArbol> actuales = arbol;
        foreach (var nivel in Niveles)
        {
            var codigo = Valor(nodo, nivel);
            if (string.IsNullOrEmpty(codigo)) break;
            var nodoDelArbol = actuales.FirstOrDefault(n => string.Equals(n.Code, codigo, StringComparison.Ordinal));
            partes.Add(nodoDelArbol is null ? codigo : Rotulo(nodoDelArbol));
            actuales = nodoDelArbol?.Children ?? [];
        }
        return string.Join(" › ", partes);
    }
}

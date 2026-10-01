using System.Globalization;
using System.Text;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>Un curso del catálogo con la materia en la que vive y su texto de búsqueda ya normalizado.</summary>
public sealed record EntradaDeCurso(FichaCurso Curso, AsignaturaAula? Asignatura, string Texto, string Titulo);

/// <summary><see cref="Total"/> es cuántos cursos coinciden; <see cref="Mostrados"/> sólo los primeros (<c>limite</c>), mejor puestos primero.</summary>
public sealed record ResultadoDeBusqueda(int Total, IReadOnlyList<EntradaDeCurso> Mostrados)
{
    public bool HayMas => Total > Mostrados.Count;
}

/// <summary>
/// Búsqueda de cursos sobre TODO el catálogo (el MVP llegará a ~25 000 cursos): el texto de cada curso se normaliza una sola vez al construir el
/// índice, así que cada tecla es una pasada de comparaciones de cadenas y no de normalizaciones. Sin tildes ni mayúsculas («matematicas» encuentra
/// «Matemáticas»); todas las palabras deben aparecer, en cualquier campo: título, subtítulo, descripción, código, materia, país, idioma, nivel, grado, tema.
/// Los que tienen todas las palabras en el título van primero. La pantalla pinta sólo <c>limite</c> resultados.
/// </summary>
public sealed class IndiceDeCursos
{
    private static readonly Dictionary<string, string> Paises = new(StringComparer.OrdinalIgnoreCase)
    {
        ["CO"] = "Colombia", ["US"] = "Estados Unidos", ["MX"] = "México", ["ES"] = "España", ["AR"] = "Argentina",
        ["PE"] = "Perú", ["CL"] = "Chile", ["EC"] = "Ecuador", ["PA"] = "Panamá", ["CR"] = "Costa Rica", ["GT"] = "Guatemala",
    };

    private readonly List<EntradaDeCurso> _entradas;

    public IndiceDeCursos(CatalogoAula catalogo)
    {
        _entradas = [];
        foreach (var asignatura in catalogo.Asignaturas)
            foreach (var curso in asignatura.Cursos)
                _entradas.Add(Entrada(curso, asignatura));
        // Catálogo sin materias: los cursos sueltos.
        if (_entradas.Count == 0)
            foreach (var curso in catalogo.Cursos) _entradas.Add(Entrada(curso, null));
    }

    public int Total => _entradas.Count;

    private static EntradaDeCurso Entrada(FichaCurso curso, AsignaturaAula? asignatura) =>
        new(curso, asignatura, string.Join(' ', Campos(curso, asignatura).Select(Normalizar)), Normalizar(curso.Titulo));

    /// <summary>Los campos en los que se busca un curso.</summary>
    public static IEnumerable<string> Campos(FichaCurso curso, AsignaturaAula? asignatura)
    {
        var cl = curso.Clasificacion;
        return new[]
        {
            curso.Titulo, curso.Subtitulo, curso.Descripcion, curso.CursoRef, asignatura?.Nombre, asignatura?.Codigo,
            cl?.Pais, NombrePais(cl?.Pais), cl?.Idioma, cl?.Nivel?.Nombre, cl?.Nivel?.Codigo, cl?.Grado?.Nombre, cl?.Grado?.Codigo,
            cl?.Tema?.Nombre, cl?.Tema?.Codigo, cl?.Asignatura?.Nombre, cl?.Asignatura?.Codigo,
        }.Where(x => !string.IsNullOrWhiteSpace(x))!;
    }

    public static string? NombrePais(string? codigo) =>
        string.IsNullOrWhiteSpace(codigo) ? null : Paises.TryGetValue(codigo, out var nombre) ? nombre : codigo;

    /// <summary>Minúsculas y sin tildes.</summary>
    public static string Normalizar(string? texto)
    {
        if (string.IsNullOrWhiteSpace(texto)) return string.Empty;
        var descompuesto = texto.Trim().ToLowerInvariant().Normalize(NormalizationForm.FormD);
        var sb = new StringBuilder(descompuesto.Length);
        foreach (var c in descompuesto)
            if (CharUnicodeInfo.GetUnicodeCategory(c) != UnicodeCategory.NonSpacingMark) sb.Append(c);
        return sb.ToString().Normalize(NormalizationForm.FormC);
    }

    public static string[] Palabras(string? texto) => Normalizar(texto).Split(' ', StringSplitOptions.RemoveEmptyEntries);

    /// <summary>
    /// Cursos que traen todas las palabras de <paramref name="texto"/>. Con <paramref name="asignaturaCodigo"/> sólo esa materia; sin él, todas.
    /// Sin texto devuelve los de la materia en el orden del catálogo (o todos). Muestra a lo sumo <paramref name="limite"/>.
    /// </summary>
    public ResultadoDeBusqueda Buscar(string? texto, string? asignaturaCodigo, int limite)
    {
        var palabras = Palabras(texto);
        var candidatos = asignaturaCodigo is null ? _entradas : _entradas.Where(e => e.Asignatura?.Codigo == asignaturaCodigo);
        if (palabras.Length == 0)
        {
            var todos = candidatos.ToList();
            return new ResultadoDeBusqueda(todos.Count, todos.Take(limite).ToList());
        }
        var coinciden = candidatos.Where(e => palabras.All(p => e.Texto.Contains(p, StringComparison.Ordinal))).ToList();
        var ordenados = coinciden.OrderBy(e => palabras.All(p => e.Titulo.Contains(p, StringComparison.Ordinal)) ? 0 : 1).Take(limite).ToList();
        return new ResultadoDeBusqueda(coinciden.Count, ordenados);
    }
}

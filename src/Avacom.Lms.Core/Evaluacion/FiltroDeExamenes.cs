using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Evaluacion;

/// <summary>El curso del catálogo del aula, con la materia en la que vive, al que pertenece un examen: de ahí hereda su clasificación.</summary>
public readonly record struct CursoClasificado(FichaCurso Curso, AsignaturaAula Asignatura);

/// <summary>
/// El buscador y los filtros de «Evaluaciones» (los mismos de «Clase de hoy»): texto libre, País, Nivel, Grado y Materia. Un examen no trae clasificación propia: hereda la de su
/// CURSO, que sale del catálogo del aula y se cruza por <c>curso_ref</c>. Sin interfaz, para poder probarlo.
///
/// Reglas (las de «Clase de hoy», <c>ClaseHoyPage.Coincide</c>): un selector elegido exige que el curso lo cumpla; el texto exige TODAS sus palabras, sin tildes ni mayúsculas, en
/// algún campo (examen, lección, curso o la clasificación que trae <see cref="IndiceDeCursos.Campos"/>). Un curso que no está en el catálogo (otra materia, no asignada a esta
/// persona) no tiene clasificación: sólo se oculta si se elige algún selector, y el texto sigue buscando en su título y en el del examen.
/// </summary>
public static class FiltroDeExamenes
{
    /// <summary>El catálogo del aula indexado por <c>curso_ref</c> (un curso puede vivir en más de una materia).</summary>
    public static Dictionary<string, List<CursoClasificado>> Indexar(CatalogoAula? catalogo)
    {
        var indice = new Dictionary<string, List<CursoClasificado>>(StringComparer.Ordinal);
        if (catalogo is null) return indice;
        foreach (var asignatura in catalogo.Asignaturas)
            foreach (var curso in asignatura.Cursos)
            {
                if (!indice.TryGetValue(curso.CursoRef, out var lista)) indice[curso.CursoRef] = lista = [];
                lista.Add(new CursoClasificado(curso, asignatura));
            }
        return indice;
    }

    public static bool Coincide(CursoConExamenes curso, ExamenDisponible examen, IReadOnlyList<CursoClasificado>? clasificacion,
                                string? pais, string? nivel, string? grado, string? materia, IReadOnlyList<string> palabras)
    {
        IEnumerable<CursoClasificado> candidatas = clasificacion ?? [];
        if (pais is not null || nivel is not null || grado is not null || materia is not null)
        {
            candidatas = candidatas.Where(e =>
                (pais is null || IndiceDeCursos.NombrePais(e.Curso.Clasificacion?.Pais) == pais)
                && (nivel is null || e.Curso.Clasificacion?.Nivel?.Nombre == nivel)
                && (grado is null || e.Curso.Clasificacion?.Grado?.Nombre == grado)
                && (materia is null || e.Asignatura.Nombre == materia)).ToList();
            if (!candidatas.Any()) return false;
        }
        if (palabras.Count == 0) return true;
        IEnumerable<string?> campos = [examen.Titulo, examen.LeccionTitulo, examen.ObjetoRef, curso.Titulo, curso.CursoRef];
        campos = campos.Concat(candidatas.SelectMany(e => IndiceDeCursos.Campos(e.Curso, e.Asignatura)));
        var texto = string.Join(' ', campos.Select(IndiceDeCursos.Normalizar));
        return palabras.All(p => texto.Contains(p, StringComparison.Ordinal));
    }

    /// <summary>Los valores de cada selector: sólo lo que hay entre los cursos indicados, distintos y en el orden de la clasificación (el de «Clase de hoy»).</summary>
    public static (IReadOnlyList<string> Paises, IReadOnlyList<string> Niveles, IReadOnlyList<string> Grados, IReadOnlyList<string> Materias) Opciones(
        IEnumerable<string> cursoRefs, IReadOnlyDictionary<string, List<CursoClasificado>> indice)
    {
        var entradas = cursoRefs.Distinct().SelectMany(c => indice.TryGetValue(c, out var lista) ? lista : []).ToList();
        static IReadOnlyList<string> Ordenados(IEnumerable<NodoClasificacion?> nodos) => nodos
            .Where(n => !string.IsNullOrWhiteSpace(n?.Nombre))
            .GroupBy(n => n!.Nombre!)
            .OrderBy(g => g.Min(n => n!.Orden ?? int.MaxValue))
            .ThenBy(g => g.Key, StringComparer.CurrentCultureIgnoreCase)
            .Select(g => g.Key).ToList();
        return (
            entradas.Select(e => IndiceDeCursos.NombrePais(e.Curso.Clasificacion?.Pais)).Where(x => x is not null).Select(x => x!).Distinct()
                .OrderBy(x => x, StringComparer.CurrentCultureIgnoreCase).ToList(),
            Ordenados(entradas.Select(e => e.Curso.Clasificacion?.Nivel)),
            Ordenados(entradas.Select(e => e.Curso.Clasificacion?.Grado)),
            entradas.Select(e => e.Asignatura.Nombre).Where(x => !string.IsNullOrWhiteSpace(x)).Distinct().ToList());
    }
}

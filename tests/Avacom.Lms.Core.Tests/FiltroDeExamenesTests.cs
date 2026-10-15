using System.Text.Json;
using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// El buscador y los filtros de «Evaluaciones» (los de «Clase de hoy»): texto libre sin tildes y con todas las palabras, y País, Nivel, Grado y Materia heredados del CURSO del examen.
/// Un curso que no está en el catálogo (otra materia) sólo se oculta si se elige algún selector.
/// </summary>
public sealed class FiltroDeExamenesTests
{
    private static CursoClasificado Curso(string cursoRef, string titulo, string materia, string codigoMateria, string nivel, int ordenNivel, string grado, string pais = "CO") =>
        Fabricar(cursoRef, titulo, materia, codigoMateria, nivel, ordenNivel, grado, pais);

    private static CursoClasificado Fabricar(string cursoRef, string titulo, string materia, string codigoMateria, string nivel, int ordenNivel, string grado, string pais)
    {
        var ficha = JsonSerializer.Deserialize<FichaCurso>($$"""
            {"fuente":"biblioteca","esquema":"1.1","curso_ref":"{{cursoRef}}","version":"1.0.0","titulo":"{{titulo}}","subtitulo":null,"descripcion":null,"idioma":"es",
             "clasificacion":{"pais":"{{pais}}","idioma":"es","nivel":{"codigo":"n","nombre":"{{nivel}}","orden":{{ordenNivel}}},"grado":{"codigo":"g","nombre":"{{grado}}","orden":1},
                              "asignatura":{"codigo":"{{codigoMateria}}","nombre":"{{materia}}","orden":1},"tema":null},
             "duracion_estimada_min":60,"modos":["class"],"portada_url":null,"lecciones":3,"objetos":9,"medios":0}
            """, Ayudas.Web)!;
        return new CursoClasificado(ficha, new AsignaturaAula(codigoMateria, materia, [ficha]));
    }

    private static (CursoConExamenes Curso, ExamenDisponible Examen) Examen(string cursoRef, string tituloCurso, string objeto, string titulo, string leccion) =>
        (new CursoConExamenes(cursoRef, tituloCurso, "1.0.0", []), new ExamenDisponible(objeto, titulo, "l", leccion, 12));

    private static readonly CursoClasificado Ciencias = Curso("c-ciencias", "Estados de la materia", "Ciencias", "sci", "Secundaria básica", 2, "Sexto");
    private static readonly CursoClasificado Matematicas = Curso("c-mate", "Fracciones: partes de un todo", "Matemáticas", "math", "Primaria", 1, "Cuarto");
    private static readonly CursoClasificado Historia = Curso("c-hist", "Guerra Fría y América Latina", "Ciencias sociales", "soc", "Secundaria básica", 2, "Noveno", "US");

    private static bool Coincide((CursoConExamenes Curso, ExamenDisponible Examen) e, CursoClasificado? clasificado, string? pais = null, string? nivel = null,
                                 string? grado = null, string? materia = null, string texto = "") =>
        FiltroDeExamenes.Coincide(e.Curso, e.Examen, clasificado is { } c ? [c] : null, pais, nivel, grado, materia, Avacom.Lms.Core.Services.IndiceDeCursos.Palabras(texto));

    [Fact]
    public void SinNadaElegido_TodoCoincide_AunqueElCursoNoEsteEnElCatalogo()
    {
        var e = Examen("c-mate", "Fracciones", "l2-exam", "Examen de fracciones", "Evaluación");
        Assert.True(Coincide(e, Matematicas));
        Assert.True(Coincide(e, null));
    }

    [Theory]
    [InlineData("fracciones", true)]
    [InlineData("FRACCIONES", true)]
    [InlineData("matematicas", true)]            // sin tildes: encuentra «Matemáticas» (la materia del curso)
    [InlineData("primaria cuarto", true)]        // todas las palabras, en cualquier campo: nivel y grado del curso
    [InlineData("colombia", true)]               // el país se busca por su nombre, no sólo por el código
    [InlineData("evaluacion", true)]             // el título de la lección
    [InlineData("fracciones historia", false)]   // con una palabra que no aparece no coincide
    [InlineData("pitagoras", false)]
    public void ElTexto_BuscaSinTildesYExigeTodasLasPalabras(string texto, bool esperado)
    {
        var e = Examen("c-mate", "Fracciones", "l2-exam", "Examen de fracciones", "Evaluación");
        Assert.Equal(esperado, Coincide(e, Matematicas, texto: texto));
    }

    [Fact]
    public void LosSelectores_FiltranPorLaClasificacionDelCurso()
    {
        var mate = Examen("c-mate", "Fracciones", "l2-exam", "Examen de fracciones", "Evaluación");
        var hist = Examen("c-hist", "Guerra Fría", "l8-examen", "Examen de la unidad", "Evaluación");
        Assert.True(Coincide(mate, Matematicas, nivel: "Primaria"));
        Assert.False(Coincide(mate, Matematicas, nivel: "Secundaria básica"));
        Assert.True(Coincide(hist, Historia, nivel: "Secundaria básica", grado: "Noveno"));
        Assert.False(Coincide(hist, Historia, nivel: "Secundaria básica", grado: "Sexto"));
        Assert.True(Coincide(hist, Historia, pais: "Estados Unidos"));
        Assert.False(Coincide(mate, Matematicas, pais: "Estados Unidos"));
        Assert.True(Coincide(mate, Matematicas, materia: "Matemáticas"));
        Assert.False(Coincide(mate, Matematicas, materia: "Ciencias"));
    }

    [Fact]
    public void SelectoresYTexto_SeCombinan()
    {
        var e = Examen("c-ciencias", "Estados de la materia", "l3-exam", "Examen de estados de la materia", "Evaluación");
        Assert.True(Coincide(e, Ciencias, nivel: "Secundaria básica", grado: "Sexto", materia: "Ciencias", texto: "estados"));
        Assert.False(Coincide(e, Ciencias, nivel: "Secundaria básica", grado: "Sexto", materia: "Ciencias", texto: "fracciones"));
        Assert.False(Coincide(e, Ciencias, nivel: "Primaria", texto: "estados"));
    }

    [Fact]
    public void UnCursoFueraDelCatalogo_SoloSeOcultaSiSeEligeUnSelector_YElTextoBuscaEnSuTitulo()
    {
        var e = Examen("c-otro", "Lectura crítica de medios", "l5-examen", "Examen: lectura crítica", "Evaluación del curso");
        Assert.True(Coincide(e, null));                                  // sin filtros se ve (la lista nunca esconde lo que existe)
        Assert.True(Coincide(e, null, texto: "lectura critica"));        // el texto busca en lo poco que se sabe de él
        Assert.False(Coincide(e, null, texto: "fracciones"));
        Assert.False(Coincide(e, null, nivel: "Primaria"));              // no tiene clasificación: un selector lo oculta
        Assert.False(Coincide(e, null, materia: "Ciencias"));
    }

    [Fact]
    public void Indexar_CruzaPorCursoRef_YUnCursoPuedeVivirEnMasDeUnaMateria()
    {
        var catalogo = JsonSerializer.Deserialize<CatalogoAula>("""
            {"fuente":"biblioteca","disponible":true,"cursos":[],
             "asignaturas":[
               {"codigo":"math","nombre":"Matemáticas","cursos":[{"curso_ref":"c-1","titulo":"Uno","lecciones":1,"objetos":1}]},
               {"codigo":"sci","nombre":"Ciencias","cursos":[{"curso_ref":"c-1","titulo":"Uno","lecciones":1,"objetos":1},{"curso_ref":"c-2","titulo":"Dos","lecciones":1,"objetos":1}]}]}
            """, Ayudas.Web);
        var indice = FiltroDeExamenes.Indexar(catalogo);
        Assert.Equal(2, indice["c-1"].Count);
        Assert.Equal(new[] { "Matemáticas", "Ciencias" }, indice["c-1"].Select(c => c.Asignatura.Nombre));
        Assert.Single(indice["c-2"]);
        Assert.Empty(FiltroDeExamenes.Indexar(null));
    }

    [Fact]
    public void Opciones_SoloOfrecenLoQueHayEntreLosCursosConExamen_EnElOrdenDeLaClasificacion()
    {
        var indice = new Dictionary<string, List<CursoClasificado>>
        {
            ["c-ciencias"] = [Ciencias], ["c-mate"] = [Matematicas], ["c-hist"] = [Historia], ["c-sin-examen"] = [Curso("c-sin-examen", "Otro", "Arte", "art", "Preescolar", 0, "Primero")],
        };
        var (paises, niveles, grados, materias) = FiltroDeExamenes.Opciones(["c-ciencias", "c-mate", "c-hist", "c-fuera-del-catalogo"], indice);
        Assert.Equal(new[] { "Colombia", "Estados Unidos" }, paises);
        Assert.Equal(new[] { "Primaria", "Secundaria básica" }, niveles);           // por `orden` de la clasificación, no alfabético
        Assert.Equal(new[] { "Cuarto", "Noveno", "Sexto" }.OrderBy(x => x, StringComparer.CurrentCultureIgnoreCase), grados.OrderBy(x => x, StringComparer.CurrentCultureIgnoreCase));
        Assert.Equal(new[] { "Ciencias", "Matemáticas", "Ciencias sociales" }.OrderBy(x => x), materias.OrderBy(x => x));
        Assert.DoesNotContain("Arte", materias);                                      // el curso sin examen no aporta opciones
        Assert.DoesNotContain("Preescolar", niveles);
    }
}

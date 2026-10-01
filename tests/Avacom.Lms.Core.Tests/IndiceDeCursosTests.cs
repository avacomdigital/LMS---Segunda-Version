using System.Diagnostics;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

public class IndiceDeCursosTests
{
    private static FichaCurso Curso(string id, string titulo, string? subtitulo = null, string? pais = "CO", string? grado = null, string? tema = null) =>
        new("biblioteca", "2.0", id, "1", titulo, subtitulo, null, "es-CO",
            new Clasificacion(pais, "es-CO", new NodoClasificacion("secondary", "Básica secundaria", 2),
                grado is null ? null : new NodoClasificacion("6", grado, 6), null, tema is null ? null : new NodoClasificacion("t", tema, 1)),
            60, null, null, 1, 1, null);

    private static CatalogoAula Catalogo(params (string Codigo, string Nombre, FichaCurso[] Cursos)[] materias) =>
        new("biblioteca", true, materias.Select(m => new AsignaturaAula(m.Codigo, m.Nombre, m.Cursos)).ToList(), []);

    private static CatalogoAula Basico() => Catalogo(
        ("math", "Matemáticas", [Curso("m1", "Fracciones: partes de un todo", grado: "Cuarto"), Curso("m2", "Teoremas de Pitágoras y Tales", grado: "Octavo")]),
        ("sci", "Ciencias naturales", [Curso("c1", "Estados de la materia y sus cambios", tema: "Estados de la materia")]),
        ("soc", "Social Studies", [Curso("s1", "The U.S. Constitution", pais: "US")]));

    [Fact]
    public void Busca_en_todas_las_materias_sin_tildes_ni_mayusculas()
    {
        var r = new IndiceDeCursos(Basico()).Buscar("MATEMATICAS", null, 20);
        Assert.Equal(2, r.Total);
        var r2 = new IndiceDeCursos(Basico()).Buscar("pitagoras", null, 20);
        Assert.Equal("m2", Assert.Single(r2.Mostrados).Curso.CursoRef);
    }

    [Fact]
    public void Todas_las_palabras_deben_aparecer_aunque_esten_en_campos_distintos()
    {
        var indice = new IndiceDeCursos(Basico());
        Assert.Single(indice.Buscar("fracciones cuarto", null, 20).Mostrados);   // título + grado
        Assert.Empty(indice.Buscar("fracciones octavo", null, 20).Mostrados);
        Assert.Single(indice.Buscar("estados colombia", null, 20).Mostrados);     // país por nombre, no por código
        Assert.Single(indice.Buscar("constitution estados unidos", null, 20).Mostrados);
    }

    [Fact]
    public void Se_busca_por_el_codigo_del_curso()
    {
        var r = new IndiceDeCursos(Basico()).Buscar("c1", null, 20);
        Assert.Equal("c1", Assert.Single(r.Mostrados).Curso.CursoRef);
    }

    [Fact]
    public void Con_materia_elegida_busca_solo_en_ella()
    {
        var indice = new IndiceDeCursos(Basico());
        Assert.Equal(2, indice.Buscar("", "math", 20).Total);
        Assert.Empty(indice.Buscar("estados", "math", 20).Mostrados);
    }

    [Fact]
    public void Sin_texto_ni_materia_son_todos_en_el_orden_del_catalogo()
    {
        var r = new IndiceDeCursos(Basico()).Buscar("   ", null, 20);
        Assert.Equal(4, r.Total);
        Assert.Equal(["m1", "m2", "c1", "s1"], r.Mostrados.Select(e => e.Curso.CursoRef));
    }

    [Fact]
    public void Los_del_titulo_van_primero()
    {
        var cat = Catalogo(("a", "A", [Curso("x1", "Otra cosa", subtitulo: "Sobre fracciones"), Curso("x2", "Fracciones para todos")]));
        var r = new IndiceDeCursos(cat).Buscar("fracciones", null, 20);
        Assert.Equal(["x2", "x1"], r.Mostrados.Select(e => e.Curso.CursoRef));
    }

    [Fact]
    public void El_limite_recorta_lo_mostrado_pero_el_total_cuenta_todo()
    {
        var cat = Catalogo(("a", "A", Enumerable.Range(0, 100).Select(i => Curso($"c{i}", $"Fracciones {i}")).ToArray()));
        var r = new IndiceDeCursos(cat).Buscar("fracciones", null, 25);
        Assert.Equal(100, r.Total);
        Assert.Equal(25, r.Mostrados.Count);
        Assert.True(r.HayMas);
    }

    [Fact]
    public void Un_catalogo_sin_materias_usa_los_cursos_sueltos()
    {
        var cat = new CatalogoAula("biblioteca", true, [], [Curso("z1", "Suelto")]);
        Assert.Equal("z1", Assert.Single(new IndiceDeCursos(cat).Buscar("suelto", null, 5).Mostrados).Curso.CursoRef);
    }

    [Fact]
    public void Veinticinco_mil_cursos_se_buscan_en_una_fraccion_de_segundo()
    {
        var cursos = Enumerable.Range(0, 25_000).Select(i => Curso($"avacom.co.curso.{i}", $"Curso número {i} de álgebra y geometría", $"Subtítulo {i}", grado: "Séptimo", tema: $"Tema {i % 300}")).ToArray();
        var indice = new IndiceDeCursos(Catalogo(("a", "Matemáticas", cursos)));
        Assert.Equal(25_000, indice.Total);
        var reloj = Stopwatch.StartNew();
        for (var i = 0; i < 20; i++) indice.Buscar("algebra 24999", null, 25);
        reloj.Stop();
        Assert.True(reloj.ElapsedMilliseconds / 20 < 250, $"{reloj.ElapsedMilliseconds / 20} ms por búsqueda");
        Assert.Equal("avacom.co.curso.24999", indice.Buscar("algebra 24999", null, 25).Mostrados[0].Curso.CursoRef);
    }
}

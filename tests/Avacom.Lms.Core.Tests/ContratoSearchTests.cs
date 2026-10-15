using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Search;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// Los DTOs de <c>/api/search/</c> contra respuestas REALES del backend, capturadas por <c>backend/search/tests/test_capturar_contrato.py</c> en <c>Fixtures/search/</c>. Un campo mal
/// escrito en un DTO se descubre aquí y no en una pantalla. Se comprueba la FORMA y los valores que no cambian entre corridas (los identificadores sí cambian).
/// </summary>
public sealed class ContratoSearchTests
{
    private static T Cargar<T>(string nombre) =>
        JsonSerializer.Deserialize<T>(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "search", nombre + ".json")), Ayudas.Web)
        ?? throw new InvalidOperationException($"{nombre}.json no se pudo leer como {typeof(T).Name}.");

    [Fact]
    public void Busqueda_MezclaCatalogoYLmsOrdenadosPorRelevancia()
    {
        var r = Cargar<RespuestaDeBusqueda>("busqueda");
        Assert.Equal(("estados", 5, true, 1, 20, false), (r.Consulta, r.Total, r.TotalExacto, r.Pagina, r.Tamano, r.HayMas));
        Assert.Equal(EstadosDelIndice.Consultable, r.EstadoDelIndice);
        Assert.Equal(string.Empty, r.AvisoDelIndice);
        Assert.False(r.Relajada);
        Assert.False(r.CatalogoNoDisponible);
        Assert.Equal(new[] { TiposDeBusqueda.Curso, TiposDeBusqueda.Evaluacion, TiposDeBusqueda.Estudio, TiposDeBusqueda.Leccion, TiposDeBusqueda.Clase },
                     r.Resultados.Select(h => h.Tipo).ToArray());
        Assert.Equal(r.Resultados.Select(h => h.Puntaje).OrderByDescending(p => p), r.Resultados.Select(h => h.Puntaje));
        Assert.All(r.Resultados, h => Assert.Equal(h.Tipo, h.Destino.Tipo));
    }

    [Fact]
    public void UnResultadoDelLms_TraeContextoDeGrupoYDestinoParaAbrirlo()
    {
        var h = Cargar<RespuestaDeBusqueda>("busqueda").Resultados.Single(x => x.Tipo == TiposDeBusqueda.Evaluacion);
        Assert.Equal(("local", "examen", "Estados de la materia"), (h.Origen, h.Subtipo, h.Titulo));
        Assert.Equal(h.Id, h.EntidadId);
        Assert.Equal(("Octavo A", "2026"), (h.Contexto!.Grupo, h.Contexto.Periodo));
        Assert.Equal(h.EntidadId, h.Destino.EntidadId);
        Assert.False(string.IsNullOrEmpty(h.Destino.GrupoId));
        Assert.Equal("l3-exam", h.Destino.ObjetoRef);
        Assert.Equal("Examen · Octavo A · 2026 · Estados de la materia y sus cambios".Replace("Examen · ", string.Empty), BusquedaTexto.Contexto(h).Split(" · ").Take(3).Aggregate((a, b) => a + " · " + b));
    }

    [Fact]
    public void UnResultadoDelCatalogo_TraeLaRutaDelArbolYLosResaltados()
    {
        var curso = Cargar<RespuestaDeBusqueda>("busqueda").Resultados.Single(x => x.Tipo == TiposDeBusqueda.Curso);
        Assert.Equal("catalog", curso.Origen);
        Assert.Equal(new[] { "CO", "Estados de la materia" }, curso.Contexto!.Ruta);
        Assert.Equal("CO › Estados de la materia", BusquedaTexto.Contexto(curso));
        Assert.Equal("biblioteca", curso.Destino.Fuente);
        Assert.False(string.IsNullOrEmpty(curso.Destino.CursoRef));
        var trozos = BusquedaTexto.Trozos(curso.Fragmento, curso.Resaltados);
        Assert.Equal(curso.Fragmento, string.Concat(trozos.Select(t => t.Texto)));
    }

    [Fact]
    public void Paginar_DaLaSiguientePaginaConElMismoTotal()
    {
        var r = Cargar<RespuestaDeBusqueda>("busqueda_pagina_2");
        Assert.Equal((5, 2, 2, true), (r.Total, r.Pagina, r.Tamano, r.HayMas));
        Assert.Equal(2, r.Resultados.Count);
    }

    [Fact]
    public void SinCoincidencias_NoEsUnError()
    {
        var r = Cargar<RespuestaDeBusqueda>("busqueda_sin_coincidencias");
        Assert.Equal((0, true), (r.Total, r.Resultados.Count == 0));
        Assert.Equal("Sin coincidencias para «trigonometria».", BusquedaTexto.Resumen(r));
    }

    [Fact]
    public void BusquedaRelajada_SeAclara()
    {
        var r = Cargar<RespuestaDeBusqueda>("busqueda_relajada");
        Assert.True(r.Relajada);
        Assert.True(r.Total > 0);
        Assert.NotNull(BusquedaTexto.AclaracionDeCoincidencia(r));
    }

    [Fact]
    public void BibliotecaCerrada_LaBusquedaSigueConLoDelLms()
    {
        var r = Cargar<RespuestaDeBusqueda>("busqueda_catalogo_cerrado");
        Assert.True(r.CatalogoNoDisponible);
        Assert.All(r.Resultados, h => Assert.Equal("local", h.Origen));
        var aviso = BusquedaTexto.AvisoDelCatalogo(r)!;
        Assert.Contains("AVACOM Biblioteca", aviso.Titulo);
        Assert.False(aviso.Grave);
    }

    [Fact]
    public void LosFiltrosFiltrados_SoloLleganLosValoresDeQuienConsulta()
    {
        var f = Cargar<OpcionesDeFiltros>("filtros");
        Assert.Equal(new[] { "course", "lesson", "resource", "assessment", "study", "class" }, f.Tipos.Select(t => t.Valor).ToArray());
        Assert.Equal(("Octavo A", "2026"), (f.Grupos.Single().Nombre, f.Grupos.Single().Periodo));
        Assert.Equal(new[] { "2026" }, f.Periodos);
        Assert.Equal("2026", f.PeriodoVigente);
        Assert.Equal(("CO", "Colombia"), (f.Paises!.Single().Codigo, f.Paises!.Single().Nombre));
        Assert.Equal("primary", f.Niveles!.Single().Codigo);
        Assert.Equal("4", f.Grados!.Single().Codigo);
        Assert.Equal("math", f.Materias!.Single().Codigo);
        Assert.Equal("ok", f.Catalogo!.Estado);
    }

    [Fact]
    public void ElEstado_ElDetalleSoloSeVeConElPermisoDeMantenerlo()
    {
        var e = Cargar<EstadoDeBusqueda>("estado");
        Assert.Equal((EstadosDelIndice.Consultable, true), (e.EstadoDelIndice, e.Consultable));
        Assert.DoesNotContain("detail", File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "search", "estado.json")));
        Assert.Contains("detail", File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "search", "estado_detalle.json")));
    }

    [Fact]
    public void Abrir_DevuelveElDestinoYElNoDisponibleSeExplica()
    {
        var ok = Cargar<AperturaDeResultado>("abrir");
        Assert.True(ok.Permitido && ok.Verificado);
        Assert.Equal(TiposDeBusqueda.Evaluacion, ok.Destino.Tipo);
        var error = Cargar<JsonElement>("abrir_no_disponible");
        Assert.Equal("no_disponible", error.GetProperty("codigo").GetString());
    }

    [Fact]
    public void LosErrores_TraenSuCodigo()
    {
        foreach (var (archivo, codigo) in new[] { ("error_consulta_vacia", "consulta_vacia"), ("error_consulta_invalida", "consulta_invalida"), ("error_tipo_invalido", "datos_invalidos"),
                                                  ("error_sin_permiso", "sin_permiso") })
            Assert.Equal(codigo, Cargar<JsonElement>(archivo).GetProperty("codigo").GetString());
    }
}

using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Search;

namespace Avacom.Lms.Core.Tests;

/// <summary>Lo que la pantalla Buscar dice y comprueba, sin pintar nada.</summary>
public sealed class BusquedaTextoTests
{
    private static ErrorAula Error(int estado, string? codigo, string detalle = "") => new(estado, codigo, detalle, null, null);

    private static RespuestaDeBusqueda Respuesta(int total = 3, bool exacto = true, string consulta = "fracciones", string modo = "all") =>
        new(consulta, consulta, total, exacto, 1, 20, false, [], modo, EstadosDelIndice.Consultable, string.Empty);

    [Theory]
    [InlineData("fracciones", true)]
    [InlineData("  8A ", true)]
    [InlineData("ñu", true)]
    [InlineData("a", false)]
    [InlineData("  ", false)]
    [InlineData("", false)]
    [InlineData("¿?", false)]
    public void ConsultaValida_UsaLasReglasDelNodo(string texto, bool esperado) => Assert.Equal(esperado, BusquedaTexto.ConsultaValida(texto));

    [Fact]
    public void ConsultaValida_RechazaLoDemasiadoLargo()
    {
        Assert.True(BusquedaTexto.ConsultaValida(new string('x', 120)));
        Assert.False(BusquedaTexto.ConsultaValida(new string('x', 121)));
        Assert.Contains("demasiado larga", BusquedaTexto.PorQueNoSeBusca(new string('x', 121)));
        Assert.Contains("al menos dos letras", BusquedaTexto.PorQueNoSeBusca("a"));
        Assert.Equal(string.Empty, BusquedaTexto.PorQueNoSeBusca("fracciones"));
        Assert.Equal(string.Empty, BusquedaTexto.PorQueNoSeBusca("   "));
    }

    [Fact]
    public void LosRotulos_DeTipoYDeEstado()
    {
        Assert.Equal(new[] { "Curso", "Lección", "Recurso", "Evaluación", "Estudio asignado", "Clase" }, TiposDeBusqueda.Todos.Select(BusquedaTexto.Rotulo).ToArray());
        Assert.Equal("Clases", BusquedaTexto.RotuloDeTipoPlural(TiposDeBusqueda.Clase));
        Assert.Equal("Abierta", BusquedaTexto.Estado(TiposDeBusqueda.Evaluacion, "activa"));
        Assert.Equal("En curso", BusquedaTexto.Estado(TiposDeBusqueda.Clase, "abierta"));
        Assert.Equal("Terminada", BusquedaTexto.Estado(TiposDeBusqueda.Clase, "cerrada"));
        Assert.Equal(string.Empty, BusquedaTexto.Estado(TiposDeBusqueda.Curso, null));
        Assert.Equal("rara", BusquedaTexto.Estado(TiposDeBusqueda.Clase, "rara"));
        Assert.True(BusquedaTexto.ClaseEnCurso("suspendida"));
        Assert.False(BusquedaTexto.ClaseEnCurso("cerrada"));
    }

    [Fact]
    public void UnaEvaluacion_EsExamenOActividad()
    {
        DestinoDeNavegacion d = new(TiposDeBusqueda.Evaluacion, "a");
        Assert.Equal("Examen", BusquedaTexto.RotuloCompleto(new Hallazgo("a", TiposDeBusqueda.Evaluacion, "a", "t", 1, "local", d, "examen")));
        Assert.Equal("Actividad", BusquedaTexto.RotuloCompleto(new Hallazgo("a", TiposDeBusqueda.Evaluacion, "a", "t", 1, "local", d, "actividad")));
        Assert.Equal("Curso", BusquedaTexto.RotuloCompleto(new Hallazgo("a", TiposDeBusqueda.Curso, "a", "t", 1, "catalog", d)));
    }

    [Fact]
    public void Contexto_DelLmsEsGrupoCicloYCurso_YDelCatalogoLaRutaDelArbol()
    {
        DestinoDeNavegacion d = new(TiposDeBusqueda.Clase, "c");
        var clase = new Hallazgo("c", TiposDeBusqueda.Clase, "c", "Los tres estados", 1, "local", d, Contexto: new ContextoDeHallazgo(Grupo: "Octavo A", Periodo: "2026", Curso: "Estados de la materia", Leccion: "Los tres estados"));
        Assert.Equal("Octavo A · 2026 · Estados de la materia", BusquedaTexto.Contexto(clase));            // la lección que es el título no se repite
        var curso = new Hallazgo("x", TiposDeBusqueda.Curso, "x", "Fracciones", 1, "catalog", d, Contexto: new ContextoDeHallazgo(Ruta: ["Colombia", "Primaria", "", "Fracciones"]));
        Assert.Equal("Colombia › Primaria › Fracciones", BusquedaTexto.Contexto(curso));
        Assert.Equal(string.Empty, BusquedaTexto.Contexto(new Hallazgo("x", TiposDeBusqueda.Curso, "x", "t", 1, "catalog", d)));
    }

    [Fact]
    public void Trozos_PartenElFragmentoPorLosResaltados()
    {
        var trozos = BusquedaTexto.Trozos("Las fracciones propias", [[4, 14]]);
        Assert.Equal(new[] { ("Las ", false), ("fracciones", true), (" propias", false) }, trozos.Select(t => (t.Texto, t.Resaltado)).ToArray());
        Assert.Equal("Las fracciones propias", string.Concat(trozos.Select(t => t.Texto)));
    }

    [Fact]
    public void Trozos_ToleraRangosMalos()
    {
        Assert.Empty(BusquedaTexto.Trozos(null, null));
        Assert.Equal("abc", BusquedaTexto.Trozos("abc", null).Single().Texto);
        // fuera de rango, invertidos, vacíos, repetidos y encimados: se ignoran, y el texto siempre se reconstruye completo
        var raros = BusquedaTexto.Trozos("abcdef", [[0, 2], [0, 2], [1, 3], [5, 99], [4, 4], [-1, 2], [3]]);
        Assert.Equal("abcdef", string.Concat(raros.Select(t => t.Texto)));
        Assert.Equal(new[] { "ab" }, raros.Where(t => t.Resaltado).Select(t => t.Texto).ToArray());
    }

    [Fact]
    public void Resumen_DelTotal()
    {
        Assert.Equal("1 resultado para «suma»", BusquedaTexto.Resumen(Respuesta(1, consulta: "suma")));
        Assert.Equal("3 resultados para «fracciones»", BusquedaTexto.Resumen(Respuesta(3)));
        Assert.Equal("300+ resultados para «fracciones»", BusquedaTexto.Resumen(Respuesta(300, exacto: false)));
        Assert.Equal("Sin coincidencias para «fracciones».", BusquedaTexto.Resumen(Respuesta(0)));
    }

    [Fact]
    public void LaBusquedaRelajadaSeAclara_SoloSiHayResultados()
    {
        Assert.NotNull(BusquedaTexto.AclaracionDeCoincidencia(Respuesta(2, modo: "any")));
        Assert.Null(BusquedaTexto.AclaracionDeCoincidencia(Respuesta(2)));
        Assert.Null(BusquedaTexto.AclaracionDeCoincidencia(Respuesta(0, modo: "any")));
    }

    [Theory]
    [InlineData(EstadosDelIndice.Construyendose, "construyendo")]
    [InlineData(EstadosDelIndice.Reconstruyendose, "reconstruyendo")]
    [InlineData(EstadosDelIndice.Rezagado, "atrás")]
    public void AvisoDelIndice_SoloCuandoNoEstaAlDia(string estado, string contiene)
    {
        var aviso = BusquedaTexto.AvisoDelIndice(estado, string.Empty)!;
        Assert.Contains(contiene, aviso.Titulo);
        Assert.False(aviso.Grave);                              // se sigue consultando: es un aviso, no un error
        Assert.Equal("lo dijo el nodo", BusquedaTexto.AvisoDelIndice(estado, "lo dijo el nodo")!.Detalle);
    }

    [Fact]
    public void AvisoDelIndice_AlDiaNoDiceNada()
    {
        Assert.Null(BusquedaTexto.AvisoDelIndice(EstadosDelIndice.Consultable, string.Empty));
        Assert.Null(BusquedaTexto.AvisoDelIndice(null, null));
    }

    [Fact]
    public void Error_DistingueNoEncontrarDeNoPoderBuscar()
    {
        Assert.Contains("No hay conexión", BusquedaTexto.Error(null, null).Titulo);
        Assert.Contains("No hay conexión", BusquedaTexto.Error(Error(0, null), null).Titulo);
        Assert.Contains("Tu rol no puede buscar", BusquedaTexto.Error(Error(403, "sin_permiso"), null).Titulo);
        Assert.False(BusquedaTexto.Error(Error(400, "consulta_vacia"), null).Grave);
        Assert.Equal("Demasiado larga", BusquedaTexto.Error(Error(400, "consulta_invalida", "Demasiado larga"), null).Detalle);
        Assert.Contains("ya no está disponible", BusquedaTexto.Error(Error(404, "no_disponible"), null).Titulo);
        Assert.Contains("Biblioteca", BusquedaTexto.Error(Error(503, "catalogo_no_disponible"), null).Titulo);
        Assert.Contains("sesión terminó", BusquedaTexto.Error(Error(401, "sesion_expirada"), null).Titulo);
        var generico = BusquedaTexto.Error(Error(500, "x"), "motivo del nodo");
        Assert.Equal(("No se pudo buscar", "motivo del nodo", true), (generico.Titulo, generico.Detalle, generico.Grave));
    }

    [Fact]
    public void LasRecientes_VanPorOrden_SinRepetirNiSumarLoQueNoVale()
    {
        var r = BusquedaTexto.AgregarReciente(["fracciones", "Decimales", "x"], "  Geometría ");
        Assert.Equal(new[] { "Geometría", "fracciones", "Decimales" }, r.ToArray());
        // repetir una (sin mayúsculas ni tildes) la sube a la cabeza y no la duplica
        Assert.Equal(new[] { "DECIMALES", "fracciones" }, BusquedaTexto.AgregarReciente(["fracciones", "decimales"], "DECIMALES").ToArray());
        Assert.Equal(new[] { "Geometría" }, BusquedaTexto.AgregarReciente(["geometria"], "Geometría").ToArray());
        // lo que no vale como búsqueda no entra, y el máximo se respeta
        Assert.Equal(new[] { "fracciones" }, BusquedaTexto.AgregarReciente(["fracciones"], "a").ToArray());
        Assert.Equal(3, BusquedaTexto.AgregarReciente(["aa", "bb", "cc", "dd"], "ee", 3).Count);
        Assert.Equal("ee", BusquedaTexto.AgregarReciente(["aa", "bb"], "ee", 3)[0]);
    }
}

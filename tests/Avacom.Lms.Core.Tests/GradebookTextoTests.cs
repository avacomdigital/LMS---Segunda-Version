using System.Text.Json;
using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// Lo que las pantallas del Gradebook dicen y comprueban antes de mandar algo al nodo: la puntuación (0–100, a lo sumo dos decimales), el motivo y los textos de cada
/// estado. Nada de esto decide una calificación: el backend es la fuente autoritativa, y vuelve a comprobar todo.
/// </summary>
public sealed class GradebookTextoTests
{
    [Theory]
    [InlineData("85", 85)]
    [InlineData("85,5", 85.5)]
    [InlineData("85.25", 85.25)]
    [InlineData(" 70 ", 70)]
    [InlineData("0", 0)]
    [InlineData("100", 100)]
    [InlineData("100,00", 100)]
    public void LeerPuntaje_AceptaLoValido(string texto, double esperado)
    {
        var r = GradebookTexto.LeerPuntaje(texto);
        Assert.True(r.EsValido, r.Error);
        Assert.Equal((decimal)esperado, r.Valor);
    }

    [Theory]
    [InlineData(null, "Escribe")]
    [InlineData("", "Escribe")]
    [InlineData("   ", "Escribe")]
    [InlineData("abc", "debe ser un número")]
    [InlineData("85a", "debe ser un número")]
    [InlineData("1e2", "debe ser un número")]
    [InlineData("-1", "de 0 a 100")]
    [InlineData("100,01", "de 0 a 100")]
    [InlineData("101", "de 0 a 100")]
    [InlineData("85,123", "dos decimales")]
    [InlineData("0,001", "dos decimales")]
    public void LeerPuntaje_RechazaLoInvalido_ConLoQueEstaMal(string? texto, string fragmento)
    {
        var r = GradebookTexto.LeerPuntaje(texto);
        Assert.False(r.EsValido);
        Assert.Null(r.Valor);
        Assert.Contains(fragmento, r.Error);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("  ")]
    [InlineData("ok")]
    [InlineData(" no ")]
    public void ElMotivoExigeAlMenosTresLetras(string? motivo) => Assert.NotNull(GradebookTexto.ValidarMotivo(motivo));

    [Fact]
    public void ElMotivoValidoNoDaError() => Assert.Null(GradebookTexto.ValidarMotivo("Error de transcripción"));

    [Fact]
    public void ErroresDeAjuste_NoSePuedeConfirmarFueraDeRangoNiSinMotivo()
    {
        Assert.Empty(GradebookTexto.ErroresDeAjuste("85", "Se reconoció una respuesta correcta", 70m));
        Assert.Single(GradebookTexto.ErroresDeAjuste("150", "Un motivo válido", 70m));
        Assert.Single(GradebookTexto.ErroresDeAjuste("85", "", 70m));
        Assert.Equal(2, GradebookTexto.ErroresDeAjuste("abc", "no", 70m).Count);
        var igual = GradebookTexto.ErroresDeAjuste("70,00", "Un motivo válido", 70m);
        Assert.Contains("igual al vigente", Assert.Single(igual));
    }

    [Fact]
    public void LosPuntosDeUnCriterioVanDeCeroALoQueVale()
    {
        Assert.Null(GradebookTexto.ErrorDePuntosDeCriterio("1,5", 2m));
        Assert.Null(GradebookTexto.ErrorDePuntosDeCriterio("0", 2m));
        Assert.Contains("de 0 a 2", GradebookTexto.ErrorDePuntosDeCriterio("3", 2m));
        Assert.Contains("de 0 a 2", GradebookTexto.ErrorDePuntosDeCriterio("-1", 2m));
        Assert.Contains("dos decimales", GradebookTexto.ErrorDePuntosDeCriterio("1,001", 2m));
        Assert.NotNull(GradebookTexto.ErrorDePuntosDeCriterio("", 2m));
    }

    [Fact]
    public void LoPendienteNuncaSePintaComoCero()
    {
        Assert.Equal("—", GradebookTexto.Puntaje(null));
        Assert.Equal("0", GradebookTexto.Puntaje(0m));                                 // un cero REAL es un cero
        Assert.Equal("70,5", GradebookTexto.Puntaje(70.50m));
        Assert.Equal("85,25", GradebookTexto.Puntaje(85.25m));
        Assert.Equal("70", GradebookTexto.Puntaje(70.00m));
        Assert.Equal("—", GradebookTexto.Presentada(null));
    }

    [Fact]
    public void Presentada_UnaEscalaNumericaMuestraElValorYUnaDeLetrasLaEtiqueta()
    {
        var numerica = new Presentacion(50m, new ValorPresentado(3.0m, "3.0", "3.0"), new Desempeno("Básico", "basico", 2), new CriterioDeAprobacion(true));
        var letra = new Presentacion(95m, new ValorPresentado(null, "A", "A"), new Desempeno("Sobresaliente", "A", 5), new CriterioDeAprobacion(null));
        Assert.Equal("3,0", GradebookTexto.Presentada(numerica));                       // los decimales los fija la escala: una nota de 3,0 no es «3»
        Assert.Equal("A", GradebookTexto.Presentada(letra));
        Assert.Equal("Cumple el criterio", GradebookTexto.Aprobacion(numerica.Aprobacion));
        Assert.Equal("Sin criterio de aprobación", GradebookTexto.Aprobacion(letra.Aprobacion));
        Assert.Equal("No cumple el criterio", GradebookTexto.Aprobacion(new CriterioDeAprobacion(false)));
    }

    [Fact]
    public void CadaEstadoTieneSuPalabraYSuExplicacion()
    {
        foreach (var estado in new[] { "pendiente", "provisional", "revisado", "definitivo", "reabierto", "anulado", "sin_registro" })
        {
            Assert.NotEqual(estado, GradebookTexto.Estado(estado));
            Assert.NotEmpty(GradebookTexto.EstadoExplicado(estado));
        }
        Assert.Contains("No es un cero", GradebookTexto.EstadoExplicado(EstadosDeResultado.Pendiente));
        Assert.Equal(new[] { "No iniciado", "En progreso", "Completado" }, new[] { "no_iniciado", "en_progreso", "completado" }.Select(GradebookTexto.EstadoSimple).ToArray());
        Assert.Equal(new[] { "○", "◐", "●" }, new[] { "vacio", "medio", "lleno" }.Select(GradebookTexto.Simbolo).ToArray());
        Assert.Equal(("★", "☆"), (GradebookTexto.SimboloDeAcierto("acierto"), GradebookTexto.SimboloDeAcierto("fallo")));
    }

    [Fact]
    public void LoQueElAlumnoLeeSinNotaPublicadaNoLlevaCifras()
    {
        foreach (var estado in new[] { "no_iniciado", "en_progreso", "entregado", "en_revision", "resultado_no_publicado", "publicado" })
            Assert.False(GradebookTexto.EstadoDeEntrega(estado).Any(char.IsDigit), estado);
        Assert.Contains("aún no publica", GradebookTexto.EstadoDeEntrega("resultado_no_publicado"));
    }

    [Fact]
    public void LosEstadosDeUnaCalificacionDicenQueSePuedeHacer()
    {
        Calificacion De(string estado) => new("c", "i", "a", "al", "g", "secundaria", "2026", "curso", 1, 70m, 70m, false, "mod10.porcentaje.v1", "automatica", "sistema", estado, 1, estado == "definitiva", 1, 1);
        var revisada = De(EstadosDeCalificacion.Revisada);
        Assert.True(GradebookTexto.PuedeAjustar(revisada) && GradebookTexto.PuedeReabrir(revisada) && GradebookTexto.PuedePublicar(revisada));
        Assert.False(GradebookTexto.PuedeRetirar(revisada));
        var definitiva = De(EstadosDeCalificacion.Definitiva);
        Assert.True(GradebookTexto.PuedeAjustar(definitiva) && GradebookTexto.PuedeRetirar(definitiva));
        Assert.False(GradebookTexto.PuedePublicar(definitiva));
        foreach (var cerrada in new[] { EstadosDeCalificacion.Reabierta, EstadosDeCalificacion.Anulada })
            Assert.False(GradebookTexto.PuedeAjustar(De(cerrada)) || GradebookTexto.PuedePublicar(De(cerrada)) || GradebookTexto.PuedeReabrir(De(cerrada)));
    }

    [Fact]
    public void TST069_ElTecnicoNoVeNiToca_LaAdministracionConfiguraPeroNoCalifica()
    {
        Assert.False(GradebookTexto.PuedeCalificar("TECHNICIAN"));
        Assert.False(GradebookTexto.PuedeLeerElLibro("TECHNICIAN"));
        Assert.False(GradebookTexto.PuedeConfigurar("TECHNICIAN"));
        Assert.True(GradebookTexto.PuedeCalificar("TEACHER"));
        Assert.False(GradebookTexto.PuedeCalificar("ADMIN"));
        Assert.True(GradebookTexto.PuedeConfigurar("ADMIN"));
        Assert.False(GradebookTexto.PuedeConfigurar("TEACHER"));
        Assert.True(GradebookTexto.PuedeLeerElLibro("REPORTS"));
        Assert.False(GradebookTexto.PuedeCalificar("REPORTS"));
        Assert.False(GradebookTexto.PuedeCalificar(null));
    }

    [Fact]
    public void Errores_CadaCodigoTieneUnaFraseQueNoCulpaALaCalificacion()
    {
        static ErrorAula E(int estado, string? codigo, string detalle = "x", string? extra = null) =>
            new(estado, codigo, detalle, null, extra is null ? null : JsonDocument.Parse(extra).RootElement.Clone());
        Assert.Contains("Sin conexión", GradebookTexto.Error(E(0, null), null));
        Assert.Contains("Otra persona", GradebookTexto.Error(E(409, "conflicto_de_version"), null));
        Assert.Contains("modo simple", GradebookTexto.Error(E(409, "modo_simple"), null));
        Assert.Contains("evaluaciones en curso", GradebookTexto.Error(E(409, "evaluaciones_en_curso"), null));
        Assert.Contains("rúbrica", GradebookTexto.Error(E(409, "rubrica_no_disponible"), null));
        Assert.Contains("no puede hacer esto", GradebookTexto.Error(E(403, "sin_permiso"), null));
        Assert.Contains("no puede hacer esto", GradebookTexto.Error(E(403, "fuera_de_alcance"), null));
        Assert.Equal("Dato mal escrito", GradebookTexto.Error(E(400, "puntaje_invalido", "Dato mal escrito"), null));
        var noPublicable = E(409, "no_publicable", "x", """{"motivos":["El intento tiene revisiones pendientes.","Otra razón."]}""");
        Assert.Contains("revisiones pendientes", GradebookTexto.Error(noPublicable, null));
        Assert.Contains("Otra razón", GradebookTexto.Error(noPublicable, null));
        Assert.Equal("Sin pistas", GradebookTexto.Error(null, "Sin pistas"));
        Assert.Equal(7, GradebookTexto.VersionActual(E(409, "conflicto_de_version", "x", """{"version_actual":7}""")));
        Assert.Null(GradebookTexto.VersionActual(E(409, "otro")));
    }

    [Fact]
    public void Valor_ConservaLosDecimalesQueLaEscalaFija_ConComa()
    {
        // El nodo formatea con los decimales de la escala (`etiqueta`, con punto): una nota de 4,0 no se vuelve «4» ni una de 10,00 «10».
        Assert.Equal("4,0", GradebookTexto.Valor(new ValorPresentado(4.0m, "4.0", "4.0")));
        Assert.Equal("3,8", GradebookTexto.Valor(new ValorPresentado(3.8m, "3.8", "3.8")));
        Assert.Equal("10,00", GradebookTexto.Valor(new ValorPresentado(10m, "10.00", "10.00")));
        Assert.Equal("17", GradebookTexto.Valor(new ValorPresentado(17m, "17", "17")));              // una escala sin decimales
        Assert.Equal("Notable", GradebookTexto.Valor(new ValorPresentado(null, "Notable", "NT")));   // una escala sin números: la etiqueta
        Assert.Equal("—", GradebookTexto.Valor(null));
        Assert.Equal("4", GradebookTexto.Valor(new ValorPresentado(4m, "", "")));                    // sin etiqueta, el número sin ceros de más
    }

    [Fact]
    public void Politicas_LasCuatroSeOfrecenYCadaUnaTieneSuFrase()
    {
        Assert.Equal(new[] { "ultimo", "mejor", "primero", "promedio" }, GradebookTexto.PoliticasDeIntentos);
        Assert.All(GradebookTexto.PoliticasDeIntentos, p =>
        {
            Assert.NotEqual(p, GradebookTexto.Politica(p));                             // el texto no es la clave cruda
            Assert.False(string.IsNullOrWhiteSpace(GradebookTexto.PoliticaExplicada(p)));
        });
        Assert.Equal(string.Empty, GradebookTexto.PoliticaExplicada("inventada"));
    }
}

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

    // ------------------------------------------------------------------------------------------- el boletín

    [Theory]
    [InlineData("Julian Reyes", "JR")]
    [InlineData("Ana", "A")]
    [InlineData("Juan P.", "JP")]
    [InlineData("  ", "?")]
    [InlineData(null, "?")]
    [InlineData("maría pérez", "MP")]
    public void Boletin_LasInicialesDelAvatar(string? nombre, string esperado) => Assert.Equal(esperado, BoletinTexto.Iniciales(nombre));

    [Fact]
    public void Boletin_ElPromedioSeLeeConComaYSinPromedioEsUnGuion()
    {
        Assert.Equal("3,8", BoletinTexto.Promedio(new PromedioPresentado("3.8", 3.8m, "3.8", "Básico", true)));
        Assert.Equal("NT", BoletinTexto.Promedio(new PromedioPresentado("NT", null, "NT", "Notable", true)));          // en una escala sin números es la etiqueta
        Assert.Equal("—", BoletinTexto.Promedio(null));
        Assert.Equal("—", BoletinTexto.PromedioInterno(null));                                                           // lo que no se ha calificado no es un cero
        Assert.Equal("71,43", BoletinTexto.PromedioInterno(71.43m));
        Assert.Equal("Básico · cumple el criterio", BoletinTexto.LecturaDelPromedio(new PromedioPresentado("3.8", 3.8m, "3.8", "Básico", true)));
        Assert.Equal("Bajo · no cumple el criterio", BoletinTexto.LecturaDelPromedio(new PromedioPresentado("2.0", 2m, "2.0", "Bajo", false)));
        Assert.Equal("A", BoletinTexto.LecturaDelPromedio(new PromedioPresentado("A", null, "A", "A", null)));
        Assert.Equal(string.Empty, BoletinTexto.LecturaDelPromedio(null));
    }

    [Fact]
    public void Boletin_LoQueLeQuedaAlProfesorSeDiceEnUnaFraseOQuedaVacio()
    {
        Assert.Equal("2 por revisar · 1 sin registrar · 3 sin publicar", BoletinTexto.PorAtender(new ConteoDeEvaluaciones(0, 0, 0, 3, 2, 1, 0, 0, 0)));
        Assert.Equal("1 por revisar", BoletinTexto.PorAtender(new ConteoDeEvaluaciones(0, 0, 0, 0, 1, 0, 0, 0, 0)));
        Assert.Equal(string.Empty, BoletinTexto.PorAtender(new ConteoDeEvaluaciones(5, 5, 5, 0, 0, 0, 0, 5, 0)));
        Assert.Equal(6, new ConteoDeEvaluaciones(0, 0, 0, 3, 2, 1, 0, 0, 0).PorAtender);
    }

    [Fact]
    public void Boletin_LaConstanciaSeDiceConLoQueHay()
    {
        Assert.Equal("Completó 5 de 8 evaluaciones.", BoletinTexto.Constancia(new ConstanciaDelEstudiante(5, 8)));
        Assert.Equal("Todavía no hay evaluaciones.", BoletinTexto.Constancia(new ConstanciaDelEstudiante(0, 0)));
        Assert.Equal("Completó su única evaluación.", BoletinTexto.Constancia(new ConstanciaDelEstudiante(1, 1)));
    }

    [Fact]
    public void Boletin_LaTendenciaNoSeInventaConPocosDatos()
    {
        Assert.Contains("lleva 1 calificación y se necesitan 4", BoletinTexto.Tendencia(new TendenciaDelEstudiante("insuficiente", 1, 4)));
        Assert.Contains("Va mejorando", BoletinTexto.Tendencia(new TendenciaDelEstudiante("sube", 5, null, 66m, 78.5m, 12.5m, 2)));
        Assert.Contains("78,5 de 100", BoletinTexto.Tendencia(new TendenciaDelEstudiante("sube", 5, null, 66m, 78.5m, 12.5m, 2)));
        Assert.Contains("Va bajando", BoletinTexto.Tendencia(new TendenciaDelEstudiante("baja", 5, null, 80m, 60m, -20m, 2)));
        Assert.Contains("estable", BoletinTexto.Tendencia(new TendenciaDelEstudiante("estable", 6, null, 70m, 71m, 1m, 3)));
        Assert.Equal(["▲", "▼", "▬", "·"], new[] { "sube", "baja", "estable", "insuficiente" }.Select(BoletinTexto.SimboloDeTendencia).ToArray());
    }

    [Fact]
    public void Boletin_LaFechaSeLeeEnEspanolYSinFechaEsUnGuion()
    {
        Assert.Equal("—", BoletinTexto.Fecha(null));
        Assert.Equal("—", BoletinTexto.Fecha(0));
        var texto = BoletinTexto.Fecha(new DateTimeOffset(2026, 10, 12, 15, 0, 0, TimeSpan.Zero).ToUnixTimeMilliseconds());
        Assert.Contains("2026", texto);
        Assert.DoesNotContain(".", texto);
    }

    // ---------------------------------------------------------------------------------- el sistema de calificación

    private static EscalaResumen Sistema(string nombre, decimal? min = null, decimal? max = null, decimal? aprobacion = null, string? apruebaDesde = null, params string[] niveles) =>
        new("e1", "codigo", nombre, "v1", 1, "numerica", "CO", null, min, max, aprobacion, apruebaDesde, niveles.Select(n => new TramoResumen(n, n, null)).ToList());

    [Fact]
    public void Sistema_NumericoDiceRangoYMinimoParaAprobar()
    {
        var co = Sistema("Colombia · 1,0 a 5,0 (Bajo a Superior)", 1, 5, 3, "Básico", "Bajo", "Básico", "Alto", "Superior");
        Assert.Equal("Colombia · 1,0 a 5,0 (Bajo a Superior)", GradebookTexto.Sistema(co));
        Assert.Equal("De 1 a 5", GradebookTexto.Rango(co));
        Assert.Equal("Se aprueba con 3 o más", GradebookTexto.MinimoParaAprobar(co));
        Assert.Equal("De 1 a 5 · Se aprueba con 3 o más", GradebookTexto.ResumenDelSistema(co));
        Assert.Equal("Bajo · Básico · Alto · Superior", GradebookTexto.Niveles(co));
        Assert.Equal("Se aprueba con 4,5 o más", GradebookTexto.MinimoParaAprobar(Sistema("x", 0, 10, 4.5m)));
    }

    [Fact]
    public void Sistema_PorNivelesAprueba_DesdeElPrimeroQueAprueba_SinNumeros()
    {
        var es = Sistema("España · Primaria y ESO", apruebaDesde: "Suficiente", niveles: ["Insuficiente", "Suficiente", "Bien"]);
        Assert.Equal(string.Empty, GradebookTexto.Rango(es));
        Assert.Equal("Se aprueba desde Suficiente", GradebookTexto.MinimoParaAprobar(es));
        Assert.Equal("Se aprueba desde Suficiente", GradebookTexto.ResumenDelSistema(es));
    }

    [Fact]
    public void Sistema_SinMinimo_NoInventaUnUmbral()
    {
        var peru = Sistema("Perú · literal AD, A, B, C", niveles: ["C", "B", "A", "AD"]);
        Assert.Null(GradebookTexto.MinimoParaAprobar(peru));
        Assert.Equal(string.Empty, GradebookTexto.ResumenDelSistema(peru));
        Assert.Equal("C · B · A · AD", GradebookTexto.Niveles(peru));
    }

    [Fact]
    public void Sistema_LoQueElNodoNoDijoSeDiceConPalabrasOQuedaVacio()
    {
        Assert.Equal("Sin sistema de calificación", GradebookTexto.Sistema(null));
        Assert.Equal(string.Empty, GradebookTexto.ResumenDelSistema(null));
        Assert.Equal(string.Empty, GradebookTexto.Niveles(null));
        Assert.Null(GradebookTexto.MinimoParaAprobar(null));
        // Una nota publicada con una versión que ya no se lee trae sólo nombre y tipo: no revienta ni inventa nada.
        var minimo = new EscalaResumen("", "", "Colombia · 1,0 a 5,0", "", 0, "numerica");
        Assert.Equal("Colombia · 1,0 a 5,0", GradebookTexto.Sistema(minimo));
        Assert.Equal(string.Empty, GradebookTexto.ResumenDelSistema(minimo));
    }

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
    public void Bruto_DiceLosPuntosSobreElMaximoYElPorcentaje_YNoInventaNada()
    {
        // La nota se lee con los tres: puntos · porcentaje · sistema. Sin puntos (registrada a mano) sólo el porcentaje; sin nada, vacío.
        Assert.Equal("14 de 18 puntos · 77,78 %", GradebookTexto.Bruto(new NotaEnBruto(14m, 18m, 7, 9, 77.78m)));
        Assert.Equal("77,78 %", GradebookTexto.Bruto(new NotaEnBruto(null, null, null, null, 77.78m)));
        Assert.Equal(string.Empty, GradebookTexto.Bruto(new NotaEnBruto(null, null, null, null, null)));
        Assert.Equal(string.Empty, GradebookTexto.Bruto(null));
        Assert.Equal("14 de 18 puntos", GradebookTexto.Puntos(new NotaEnBruto(14m, 18m, null, null, null)));
        Assert.Equal(string.Empty, GradebookTexto.Puntos(new NotaEnBruto(14m, 0m, null, null, null)));       // un máximo de cero no es una cuenta
        Assert.Equal("27 de 36 puntos · 75 %", BoletinTexto.Bruto(new SumaBruta(27m, 36m, 75m, 2)));
        Assert.Equal(string.Empty, BoletinTexto.Bruto(new SumaBruta(null, null, null, 0)));
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

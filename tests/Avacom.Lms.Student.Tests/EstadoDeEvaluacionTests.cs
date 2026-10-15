using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Student.Examen;

namespace Avacom.Lms.Student.Tests;

/// <summary>
/// Los ocho estados visuales de «Mis evaluaciones» (RF-006): programada, disponible, en curso, entrega pendiente de sincronización, entregada / pendiente de
/// calificación, calificada pero no publicada, resultado publicado y cerrada. Ninguna frase de un estado reservado revela la nota ni si aprobó; sólo CUÁNDO
/// se verá, según la política de publicación (RF-004).
/// </summary>
public sealed class EstadoDeEvaluacionTests
{
    private static string Hora(long ms) => $"[{ms}]";

    private static EvaluacionDelAlumno Eval(string estado = "activa", bool puede = false, string? motivo = null, MiIntento? intento = null,
                                            string? resultados = null, long? publicarEn = null, long? abreEn = null) =>
        new("a-1", "Estados de la materia", "Ciencias", estado, Niveles.Supervisado, abreEn, null, "blando", null, 6, puede, motivo, intento, resultados, publicarEn);

    private static MiIntento Intento(string estado, bool disponible = false, bool pendiente = false, bool revision = false) =>
        new("i-1", 1, estado, disponible, pendiente, revision);

    [Fact]
    public void Programada_DiceCuandoAbre_YNoOfreceBoton()
    {
        var v = EstadoDeEvaluacion.Calcular(Eval("programada", motivo: "no_abierta", abreEn: 1_000), hora: Hora);
        Assert.Equal((EstadoVisual.Programada, false, "Abre [1000]"), (v.Estado, v.TieneBoton, v.Frase));
    }

    [Fact]
    public void Disponible_OfreceComenzar_YEnEsperaDeAdmisionOfreceVer()
    {
        var v = EstadoDeEvaluacion.Calcular(Eval(puede: true));
        Assert.Equal((EstadoVisual.Disponible, AccionDeEvaluacion.Comenzar, "Comenzar"), (v.Estado, v.Accion, v.Boton));
        var espera = EstadoDeEvaluacion.Calcular(Eval(motivo: "espera_admision"));
        Assert.Equal((EstadoVisual.Disponible, AccionDeEvaluacion.Comenzar, "Ver"), (espera.Estado, espera.Accion, espera.Boton));
    }

    [Theory]
    [InlineData(EstadosIntento.EnCurso, "Tienes un examen en curso")]
    [InlineData(EstadosIntento.EnCursoFueraDePlazo, "Tienes un examen en curso")]
    [InlineData(EstadosIntento.Pausado, "Tu examen está en pausa: avisa a tu profesor")]
    [InlineData(EstadosIntento.Restaurando, "Tu examen está en pausa: avisa a tu profesor")]
    public void EnCurso_OfreceContinuar(string estado, string frase)
    {
        var v = EstadoDeEvaluacion.Calcular(Eval(intento: Intento(estado)));
        Assert.Equal((EstadoVisual.EnCurso, AccionDeEvaluacion.Continuar, "Continuar", frase), (v.Estado, v.Accion, v.Boton, v.Frase));
    }

    [Fact]
    public void EntregaPendienteDeSincronizacion_CuandoLaTabletaAunTieneAlgoGuardado()
    {
        var v = EstadoDeEvaluacion.Calcular(Eval(intento: Intento(EstadosIntento.Entregado)), pendientesEnDispositivo: 2);
        Assert.Equal(EstadoVisual.EntregaPendienteDeSincronizacion, v.Estado);
        Assert.Contains("se enviará solo cuando haya conexión", v.Frase);
        Assert.False(v.TieneBoton);
        // también si el nodo ya lo calificó pero la tableta todavía no vació su cola (y la nota aún no se publica)
        var calificado = EstadoDeEvaluacion.Calcular(Eval(intento: Intento(EstadosIntento.Calificado)), pendientesEnDispositivo: 1);
        Assert.Equal(EstadoVisual.EntregaPendienteDeSincronizacion, calificado.Estado);
    }

    [Fact]
    public void PendienteDeCalificacion_DistingueLaBibliotecaDelProfesor()
    {
        var espera = EstadoDeEvaluacion.Calcular(Eval(intento: Intento(EstadosIntento.Entregado, pendiente: true)));
        Assert.Equal((EstadoVisual.PendienteDeCalificacion, "Entregado · pendiente de calificación"), (espera.Estado, espera.Frase));
        var revision = EstadoDeEvaluacion.Calcular(Eval(intento: Intento(EstadosIntento.EnRevision)));
        Assert.Equal((EstadoVisual.PendienteDeCalificacion, "Entregado · algunas respuestas las revisa tu profesor"), (revision.Estado, revision.Frase));
    }

    [Theory]
    [InlineData(PoliticasDeResultados.TrasLiberar, "Calificado · tu profesor publicará los resultados")]
    [InlineData("manual", "Calificado · tu profesor publicará los resultados")]
    [InlineData(PoliticasDeResultados.AlFinalizarGrupo, "Calificado · verás tu resultado cuando todo el grupo haya terminado")]
    [InlineData(PoliticasDeResultados.AlEntregar, "Calificado · tu resultado estará disponible en cuanto termine de calificarse")]
    [InlineData(PoliticasDeResultados.Nunca, "Calificado · este examen no muestra el resultado en la tableta")]
    public void CalificadaNoPublicada_DiceCuandoSegunLaPolitica_SinRevelarLaNota(string politica, string frase)
    {
        var v = EstadoDeEvaluacion.Calcular(Eval(intento: Intento(EstadosIntento.Calificado), resultados: politica), hora: Hora);
        Assert.Equal((EstadoVisual.CalificadaNoPublicada, false, frase), (v.Estado, v.TieneBoton, v.Frase));
        Assert.DoesNotContain("%", v.Frase);
        Assert.DoesNotContain("aprob", v.Frase, StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData(PoliticasDeResultados.AlEntregar)]
    [InlineData(PoliticasDeResultados.TrasLiberar)]
    public void CalificadaNoPublicada_SiLoRetieneElLibro_DiceQueElProfesorPublicaraLaCalificacion(string politica)
    {
        var intento = new MiIntento("i-1", 1, EstadosIntento.Calificado, false, false, false, "libro_de_calificaciones");
        var v = EstadoDeEvaluacion.Calcular(Eval(intento: intento, resultados: politica), hora: Hora);
        Assert.Equal((EstadoVisual.CalificadaNoPublicada, false, "Calificado · tu profesor publicará tu calificación"), (v.Estado, v.TieneBoton, v.Frase));
        Assert.DoesNotContain("termine de calificarse", v.Frase);                  // ya está calificado: lo que falta es la publicación, no la nota
    }

    [Fact]
    public void Programada_DiceLaFechaDePublicacion()
    {
        var v = EstadoDeEvaluacion.Calcular(Eval(intento: Intento(EstadosIntento.Calificado), resultados: PoliticasDeResultados.Programada, publicarEn: 777), hora: Hora);
        Assert.Equal("Calificado · verás tu resultado [777]", v.Frase);
    }

    [Fact]
    public void ResultadoPublicado_OfreceVerlo()
    {
        var v = EstadoDeEvaluacion.Calcular(Eval(intento: Intento(EstadosIntento.Calificado, disponible: true)));
        Assert.Equal((EstadoVisual.ResultadoPublicado, AccionDeEvaluacion.VerResultado, "Ver resultado"), (v.Estado, v.Accion, v.Boton));
    }

    [Theory]
    [InlineData("ya_entregado", "Ya presentaste este examen")]
    [InlineData("intentos_agotados", "Ya presentaste este examen")]
    [InlineData("rechazada", "Tu profesor no admitió esta tableta: pídele que te indique cómo continuar")]
    [InlineData("no_abierta", "Este examen ya cerró")]
    public void Cerrada_SinBoton_ConSuMotivo(string motivo, string frase)
    {
        var v = EstadoDeEvaluacion.Calcular(Eval("cerrada", motivo: motivo));
        Assert.Equal((EstadoVisual.Cerrada, false, frase), (v.Estado, v.TieneBoton, v.Frase));
        var anulado = EstadoDeEvaluacion.Calcular(Eval(intento: Intento(EstadosIntento.Anulado)));
        Assert.Equal(EstadoVisual.Cerrada, anulado.Estado);
    }
}

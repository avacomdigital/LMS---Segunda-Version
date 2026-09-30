using System.Text.Json;
using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Student.ModoEstudio.Models;
using Avacom.Lms.Student.ModoEstudio.Services;

namespace Avacom.Lms.Student.Tests;

/// <summary>
/// La práctica (BR-055: aparte de la evaluación formal): con el aula se califica en el momento; sin ella, la respuesta se guarda PRIMERO en la tableta,
/// sale por la cola cifrada y se califica al integrarse (D-6: la clave de respuesta nunca está en la tableta).
/// </summary>
public sealed class PracticaTests
{
    private static AcusePractica Acuse(string veredictos = "[]", string? resultado = null) => FalsoEstudioApi.Json<AcusePractica>($$"""
        {"acuse":true,"veredictos":{{veredictos}},"aceptadas":[],"duplicadas":[],"superadas":[],"rechazadas":[],
         "practica":{"id":"prac-1","estado":"en_curso","respondidas":1,"aciertos":1,"total_preguntas":2,"sin_calificar":0},
         "resultado":{{resultado ?? "null"}},"servidor_en":{{Escenario.Ahora}}}
        """);

    private const string Bien = """[{"pregunta_ref":"q1","correcta":true,"puntaje":1,"puntaje_maximo":1,"pendiente":false,"retroalimentacion":["¡Bien! 2 + 2 es 4."]}]""";

    private const string Resultado = """
        {"correctas":1,"total":2,"porcentaje":50,"mensaje":"¡Buen avance!","sin_calificar":0,
         "revision":[{"pregunta_ref":"q1","correcta":true,"retroalimentacion":["Muy bien"]},{"pregunta_ref":"q2","correcta":false,"retroalimentacion":["Casi"]}]}
        """;

    private static async Task<Escenario> ConAulaAsync()
    {
        var e = new Escenario().ConAulaLista();
        e.Api.Asignaciones = _ => Escenario.ListaDe(Escenario.AsignacionJson());
        e.Api.Practica = (_, nueva, _) => Escenario.PracticaJson(numero: nueva ? 2 : 1);
        e.Api.Responder = (_, _, _) => Acuse(Bien);
        e.Api.Terminar = _ => Acuse(resultado: Resultado);
        await e.ElegirAsync(Escenario.Ethan);
        await e.CargarAsync();
        return e;
    }

    private static PreguntaAula Pregunta(IStudyPracticeSession sesion, string preguntaRef) => sesion.Activity.Preguntas!.Single(p => p.PreguntaRef == preguntaRef);

    private static async Task<Escenario> ConPaqueteAsync()
    {
        var e = new Escenario().ConAulaLista(dueno: Escenario.Ethan);
        var asignacion = Escenario.AsignacionJson(conBloques: true);
        e.Api.Asignaciones = _ => Escenario.ListaDe(asignacion);
        await e.ElegirAsync(Escenario.Ethan);
        await e.CargarAsync();
        var paquete = FalsoEstudioApi.Json<PaqueteEstudio>($$"""
            {"id":"paq-1","asignacion_id":"{{Escenario.Asignacion}}","estado":"solicitado","motivo":"","curso_version":"1.0.0","bytes_total":10,"huella":"h",
             "vigente_hasta":{{Escenario.Ahora + Escenario.Dia}},"solicitado_en":10,"disponible_en":null,"archivos":[],"no_incluidos":[],"servidor_en":{{Escenario.Ahora}}}
            """);
        var crudo = $$"""
            {"paquete_id":"paq-1","asignacion":{{asignacion}},"curso":null,"leccion_ref":"l1","vigente_hasta":{{Escenario.Ahora + Escenario.Dia}},"generado_en":{{Escenario.Ahora}},
             "leccion":{"leccion_ref":"l1","titulo":"Los tres estados","objetos":{{Escenario.ObjetosJson}}},"archivos":[],"no_incluidos":[],"huella":"h"}
            """;
        e.Local.Almacen.RegistrarPaquete(Escenario.Ethan, paquete);
        e.Local.Almacen.GuardarManifiesto(Escenario.Ethan, Escenario.Asignacion, crudo, FalsoEstudioApi.Json<ManifiestoPaquete>(crudo));
        e.Local.Almacen.MarcarDisponible(Escenario.Ethan, Escenario.Asignacion);
        e.Api.EnLinea = false;
        return e;
    }

    [Fact]
    public async Task ConAula_CadaRespuestaSeCalificaAlInstante_YNoHaceFaltaLaCola()
    {
        using var e = await ConAulaAsync();
        var abierta = await e.Servicio.OpenPracticeAsync(Escenario.Asignacion, retry: false);
        Assert.True(abierta.Ok, abierta.ErrorMessage);
        var sesion = abierta.Session!;
        Assert.True(sesion.CanGradeNow);
        Assert.Equal(1, sesion.Number);

        var veredicto = await sesion.SubmitAsync(Pregunta(sesion, "q1"), Escenario.Respuesta("""{"selectedOptionIds":["a"]}"""));

        Assert.True(veredicto.Known);
        Assert.True(veredicto.Correct);
        Assert.Equal(["¡Bien! 2 + 2 es 4."], veredicto.Feedback);
        Assert.Contains($"Responder({Escenario.Dispositivo},{Escenario.Ethan},prac-1,q1)", e.Api.Llamadas);
        Assert.Equal(0, e.Local.Cola.CantidadPendiente(Escenario.Ethan));
        var local = e.Local.Almacen.LeerTarea(Escenario.Ethan, Escenario.Asignacion)!.Practicas.Single();
        Assert.Equal((1, "en_curso"), (local.Numero, local.Estado));
        Assert.NotNull(local.Respuestas["q1"].Veredicto);                       // lo respondido y su veredicto también quedan en la tableta
    }

    [Fact]
    public async Task ReanudarUnaPractica_TraeLoYaRespondidoConSuVeredicto()
    {
        using var e = await ConAulaAsync();
        e.Api.Practica = (_, _, _) => Escenario.PracticaJson(respondidas: """
            {"q1":{"respuesta":{"selectedOptionIds":["a"]},"veredicto":{"pregunta_ref":"q1","correcta":true,"puntaje":1,"puntaje_maximo":1,"pendiente":false,"retroalimentacion":["Bien"]}}}
            """);

        var sesion = (await e.Servicio.OpenPracticeAsync(Escenario.Asignacion, retry: false)).Session!;

        var previa = sesion.Previous["q1"];
        Assert.True(previa.Verdict!.Correct);
        Assert.Equal("a", previa.Answer.GetProperty("selectedOptionIds")[0].GetString());
    }

    [Fact]
    public async Task SiElAulaSeCaeAMitad_LaRespuestaVaALaCola_YSeDiceQueSeCalificaDespues()
    {
        using var e = await ConAulaAsync();
        var sesion = (await e.Servicio.OpenPracticeAsync(Escenario.Asignacion, retry: false)).Session!;
        await sesion.SubmitAsync(Pregunta(sesion, "q1"), Escenario.Respuesta("""{"selectedOptionIds":["a"]}"""));

        e.Api.EnLinea = false;
        var pendiente = await sesion.SubmitAsync(Pregunta(sesion, "q2"), Escenario.Respuesta("""{"value":true}"""));

        Assert.True(pendiente.Pending);                                          // «Guardado en tu tableta», no un veredicto
        Assert.False(sesion.CanGradeNow);
        var evento = Assert.Single(e.Local.Cola.Pendientes(Escenario.Ethan)).Evento;
        Assert.Equal(TiposEventoEstudio.RespuestaEnviada, evento.Tipo);
        Assert.Equal(("q2", 1, "o-act"), (evento.Carga.GetProperty("pregunta_ref").GetString(), evento.Carga.GetProperty("intento_numero").GetInt32(), evento.Carga.GetProperty("objeto_ref").GetString()));
        Assert.True(evento.Carga.GetProperty("respuesta").GetProperty("value").GetBoolean());

        var resultado = await sesion.FinishAsync();

        Assert.Equal((1, 1, 2), (resultado.Correct, resultado.Ungraded, resultado.Total));
        Assert.Contains("Se calificará", resultado.Message);
        Assert.Equal([TiposEventoEstudio.RespuestaEnviada, TiposEventoEstudio.PracticaTerminada], e.Local.Cola.Pendientes(Escenario.Ethan).Select(p => p.Evento.Tipo));
    }

    [Fact]
    public async Task SinAula_ConLaLeccionDescargada_SePractica_TodoSeGuardaYSaleEnOrden()
    {
        using var e = await ConPaqueteAsync();

        var abierta = await e.Servicio.OpenPracticeAsync(Escenario.Asignacion, retry: false);

        Assert.True(abierta.Ok, abierta.ErrorMessage);
        var sesion = abierta.Session!;
        Assert.False(sesion.CanGradeNow);                                         // sin aula no hay quien califique: la clave no está en la tableta
        Assert.Equal((1, 2), (sesion.Number, sesion.Activity.Preguntas!.Count));
        await sesion.SubmitAsync(Pregunta(sesion, "q1"), Escenario.Respuesta("""{"selectedOptionIds":["a"]}"""));
        await sesion.SubmitAsync(Pregunta(sesion, "q2"), Escenario.Respuesta("""{"value":true}"""));

        var resultado = await sesion.FinishAsync();

        Assert.True(resultado.IsPendingGrade);
        Assert.Equal("Práctica guardada", resultado.Headline);
        var eventos = e.Local.Cola.Pendientes(Escenario.Ethan);
        Assert.Equal([TiposEventoEstudio.RespuestaEnviada, TiposEventoEstudio.RespuestaEnviada, TiposEventoEstudio.PracticaTerminada], eventos.Select(x => x.Evento.Tipo));
        Assert.True(eventos.Select(x => x.Evento.Secuencia).SequenceEqual(eventos.Select(x => x.Evento.Secuencia).Order()));
        // Terminar la práctica cuenta como bloque atendido (D-4), también en la tableta.
        Assert.Contains("o-act", e.Local.Almacen.LeerTarea(Escenario.Ethan, Escenario.Asignacion)!.BloquesVistos);
    }

    [Fact]
    public async Task IntentarNuevamente_SinAula_ContinuaLaNumeracionDeLaTableta()
    {
        using var e = await ConPaqueteAsync();
        var primera = (await e.Servicio.OpenPracticeAsync(Escenario.Asignacion, retry: false)).Session!;
        await primera.SubmitAsync(Pregunta(primera, "q1"), Escenario.Respuesta("""{"selectedOptionIds":["b"]}"""));
        await primera.FinishAsync();

        var segunda = (await e.Servicio.OpenPracticeAsync(Escenario.Asignacion, retry: true)).Session!;

        Assert.Equal(2, segunda.Number);
        Assert.Empty(segunda.Previous);                                            // un intento nuevo empieza limpio
    }

    [Fact]
    public async Task SinTerminar_SeReanudaLaPracticaQueQuedoAMedias()
    {
        using var e = await ConPaqueteAsync();
        var primera = (await e.Servicio.OpenPracticeAsync(Escenario.Asignacion, retry: false)).Session!;
        await primera.SubmitAsync(Pregunta(primera, "q1"), Escenario.Respuesta("""{"selectedOptionIds":["a"]}"""));

        var reanudada = (await e.Servicio.OpenPracticeAsync(Escenario.Asignacion, retry: false)).Session!;

        Assert.Equal(1, reanudada.Number);
        Assert.Equal("a", reanudada.Previous["q1"].Answer.GetProperty("selectedOptionIds")[0].GetString());
    }

    [Fact]
    public async Task CambiarUnaRespuesta_LlevaUnaSecuenciaMayor_AsiGanaLaUltima()
    {
        using var e = await ConPaqueteAsync();
        var sesion = (await e.Servicio.OpenPracticeAsync(Escenario.Asignacion, retry: false)).Session!;

        await sesion.SubmitAsync(Pregunta(sesion, "q1"), Escenario.Respuesta("""{"selectedOptionIds":["a"]}"""));
        await sesion.SubmitAsync(Pregunta(sesion, "q1"), Escenario.Respuesta("""{"selectedOptionIds":["b"]}"""));

        var secuencias = e.Local.Cola.Pendientes(Escenario.Ethan).Select(x => x.Evento.Carga.GetProperty("secuencia_respuesta").GetInt32()).ToList();
        Assert.Equal(2, secuencias.Count);
        Assert.True(secuencias[1] > secuencias[0]);
    }

    [Fact]
    public async Task LoRespondidoSinAula_SeCalificaAlIntegrarse_YElVeredictoQuedaEnLaTableta()
    {
        using var e = await ConPaqueteAsync();
        var sesion = (await e.Servicio.OpenPracticeAsync(Escenario.Asignacion, retry: false)).Session!;
        await sesion.SubmitAsync(Pregunta(sesion, "q1"), Escenario.Respuesta("""{"selectedOptionIds":["a"]}"""));
        await sesion.FinishAsync();
        Assert.Null(e.Local.Almacen.LeerTarea(Escenario.Ethan, Escenario.Asignacion)!.Practicas.Single().Respuestas["q1"].Veredicto);

        var avisos = new List<StudyLessonData>();
        e.Servicio.LessonChanged += avisos.Add;
        e.Api.EnLinea = true;
        e.Api.Sincronizar = (_, eventos, _) => FalsoEstudioApi.Json<AcuseSync>($$$"""
            {"acuse":true,"servidor_en":{{{Escenario.Ahora}}},
             "resultados":[{{{string.Join(",", eventos.Select(ev => $$"""{"secuencia":{{ev.Secuencia}},"estado":"integrado","motivo":"","detalle":null}"""))}}}],
             "resumen":{"integrados":{{{eventos.Count}}},"duplicados":0,"rechazados":0,"pendientes_decision":0},"asignaciones":[],
             "veredictos":[{"asignacion_id":"{{{Escenario.Asignacion}}}","objeto_ref":"o-act","numero":1,"pregunta_ref":"q1",
                            "veredicto":{"pregunta_ref":"q1","correcta":true,"puntaje":1,"puntaje_maximo":1,"pendiente":false,"retroalimentacion":["Bien"]}}]}
            """);
        await e.Servicio.SyncNowAsync();

        var respuesta = e.Local.Almacen.LeerTarea(Escenario.Ethan, Escenario.Asignacion)!.Practicas.Single().Respuestas["q1"];
        Assert.True(respuesta.Veredicto!.Correcta);
        Assert.NotEmpty(avisos);                                                  // la tarjeta se repinta sin que la persona haga nada
        Assert.Equal(0, e.Local.Cola.CantidadPendiente(Escenario.Ethan));
    }

    [Fact]
    public async Task SinAulaYSinDescargar_NoSePuedePracticar_YSeExplicaQueHayQueDescargar()
    {
        using var e = await ConAulaAsync();
        e.Api.EnLinea = false;

        var abierta = await e.Servicio.OpenPracticeAsync(Escenario.Asignacion, retry: false);

        Assert.False(abierta.Ok);
        Assert.Contains("descarga primero la lección", abierta.ErrorTitle);
    }

    [Fact]
    public async Task ConAula_TerminarDaElResultadoDelAula_ConSuRevision_YMarcaElBloque()
    {
        using var e = await ConAulaAsync();
        var sesion = (await e.Servicio.OpenPracticeAsync(Escenario.Asignacion, retry: false)).Session!;
        await sesion.SubmitAsync(Pregunta(sesion, "q1"), Escenario.Respuesta("""{"selectedOptionIds":["a"]}"""));

        var resultado = await sesion.FinishAsync();

        Assert.Equal((1, 2, 0, "¡Buen avance!", "1 de 2 correctas"), (resultado.Correct, resultado.Total, resultado.Ungraded, resultado.Message, resultado.Headline));
        Assert.Equal([true, false], resultado.Review.Select(r => r.Correct));
        Assert.Equal([1, 2], resultado.Review.Select(r => r.Number));
        Assert.Equal("¿Cuánto es 2 + 2?", resultado.Review[0].Prompt);
        Assert.Contains("o-act", e.Local.Almacen.LeerTarea(Escenario.Ethan, Escenario.Asignacion)!.BloquesVistos);
        Assert.Equal("terminada", e.Local.Almacen.LeerTarea(Escenario.Ethan, Escenario.Asignacion)!.Practicas.Single().Estado);
    }
}

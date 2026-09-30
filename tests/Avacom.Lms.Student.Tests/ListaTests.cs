using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Student.ModoEstudio.Models;
using Avacom.Lms.Student.ModoEstudio.Services;

namespace Avacom.Lms.Student.Tests;

/// <summary>
/// «Mis lecciones»: lo que el aula dice y lo que la tableta ya sabe se mezclan en un solo estado por lección (pendiente, en curso, completada,
/// vencida), con su descarga, su práctica y su marca de «pendiente de enviar». Sin el aula se ve lo último que se supo.
/// </summary>
public sealed class ListaTests
{
    private static async Task<(Escenario Escenario, IReadOnlyDictionary<string, StudyLessonData> Lecciones)> CargarAsync(params string[] asignaciones)
    {
        var e = new Escenario().ConAulaLista();
        e.Api.Asignaciones = _ => Escenario.ListaDe(asignaciones);
        await e.ElegirAsync(Escenario.Ethan);
        var lista = await e.CargarAsync();
        return (e, lista.Lessons.ToDictionary(l => l.Id));
    }

    [Fact]
    public async Task CadaLeccion_TieneSuEstado_SuProgreso_YDesdeDondeContinuar()
    {
        var (e, l) = await CargarAsync(
            Escenario.AsignacionJson("pendiente", "Pendiente", tarea: "null"),
            Escenario.AsignacionJson("en-curso", "En curso", tarea: Escenario.TareaJson("en_curso", 2, 5, ultimo: """{"ref":"o-pres:u3","indice":3,"titulo":"Tres","tipo":"lamina","posicion_seg":null}""")),
            Escenario.AsignacionJson("hecha", "Hecha", tarea: Escenario.TareaJson("completada", 5, 5, completadaEn: "1789900000000")),
            Escenario.AsignacionJson("vencida", "Vencida", limite: Escenario.Ahora - Escenario.Dia, tarea: "null"));
        using (e)
        {
            Assert.Equal((StudyLessonState.Pending, 0d, false, ""), (l["pendiente"].State, l["pendiente"].Progress, l["pendiente"].CanResume, l["pendiente"].ResumeLabel));
            Assert.NotNull(l["pendiente"].DueDate);

            var curso = l["en-curso"];
            Assert.Equal((StudyLessonState.InProgress, 2, 5, true), (curso.State, curso.CompletedBlocks, curso.TotalBlocks, curso.CanResume));
            Assert.Equal(0.4, curso.Progress, 3);
            Assert.Equal("Continúa desde: Actividad 3 de 5", curso.ResumeLabel);

            var hecha = l["hecha"];
            Assert.Equal((StudyLessonState.Completed, 1d, false), (hecha.State, hecha.Progress, hecha.CanResume));
            Assert.NotNull(hecha.CompletedOn);

            // «Vencida» se deriva con la hora del NODO: la fecha pasó y no está completada.
            Assert.Equal(StudyLessonState.Expired, l["vencida"].State);
        }
    }

    [Fact]
    public async Task LaPractica_ContaLosIntentosDelAula_YLaEvaluacionSoloInforma()
    {
        var (e, l) = await CargarAsync(Escenario.AsignacionJson("a", "Con práctica", practica:
            """{"disponible":true,"objeto_ref":"o-act","titulo":"Comprueba lo aprendido","total_preguntas":2,"intentos":2,"mejor_correctas":1,"ultima_correctas":1,"en_curso":false}"""));
        using (e)
        {
            var leccion = l["a"];
            Assert.True(leccion.HasPractice);
            Assert.Equal(("Comprueba lo aprendido", 2, 2, 1, false), (leccion.PracticeTitle, leccion.PracticeQuestionCount, leccion.PracticeAttempts, leccion.PracticeBestScore, leccion.PracticeInProgress));
            Assert.True(leccion.HasExam);
            Assert.Equal("Evaluación de la unidad", leccion.ExamTitle);
            Assert.Equal("Te la presentará tu profesor", leccion.ExamAvailability);   // se explica, nunca se practica (BR-055)
        }
    }

    [Fact]
    public async Task LoHechoEnLaTableta_ManejaSiVaMasAdelanteQueLoQueElAulaSabe()
    {
        var (e, _) = await CargarAsync(Escenario.AsignacionJson("a", "Una", tarea: Escenario.TareaJson("en_curso", 2, 5)));
        using (e)
        {
            // La tableta vio 4 bloques y terminó una práctica (intento 3) que el aula todavía no conoce.
            e.Local.Almacen.GuardarTarea(Escenario.Ethan, new TareaLocal("a", ["o-pres:u1", "o-pres:u2", "o-pres:u3", "o-lab"], "o-lab", null, false, 1,
                [new PracticaLocal("o-act", 3, "terminada", new Dictionary<string, RespuestaLocal>(), 2, false, 2)]));

            var leccion = (await e.Servicio.LoadAsync()).Lessons.Single();

            Assert.Equal(4, leccion.CompletedBlocks);                 // gana lo mayor: el avance es monótono
            Assert.Equal(0.8, leccion.Progress, 3);
            Assert.Equal(3, leccion.PracticeAttempts);
            Assert.Equal(2, leccion.PracticeBestScore);
            Assert.Equal("Continúa desde: Actividad 5 de 5", leccion.ResumeLabel);
        }
    }

    [Fact]
    public async Task UnaLeccionCompletadaEnLaTableta_SeVeCompletadaAunqueElAulaNoLoSepa()
    {
        var (e, _) = await CargarAsync(Escenario.AsignacionJson("a", "Una", tarea: Escenario.TareaJson("en_curso", 4, 5)));
        using (e)
        {
            e.Local.Almacen.GuardarTarea(Escenario.Ethan, new TareaLocal("a", [], null, null, true, Escenario.Ahora, []));

            var leccion = (await e.Servicio.LoadAsync()).Lessons.Single();

            Assert.Equal((StudyLessonState.Completed, 1d), (leccion.State, leccion.Progress));
        }
    }

    [Fact]
    public async Task LoQueEsperaEnLaCola_SeMarcaComoPendienteDeEnviarSoloEnSuLeccion()
    {
        var (e, _) = await CargarAsync(Escenario.AsignacionJson("a", "Una"), Escenario.AsignacionJson("b", "Otra"));
        using (e)
        {
            e.Local.Cola.Encolar(Escenario.Ethan, TiposEventoEstudio.BloqueVisto, Escenario.Respuesta("""{"asignacion_id":"a","bloques_vistos":["o-pres:u1"]}"""));

            var lecciones = (await e.Servicio.LoadAsync()).Lessons.ToDictionary(x => x.Id);

            Assert.True(lecciones["a"].IsPendingSync);
            Assert.False(lecciones["b"].IsPendingSync);
            Assert.Equal(StudySyncState.PendingSend, e.Servicio.SyncState);
            Assert.Equal(1, e.Servicio.PendingSyncCount);
        }
    }

    [Fact]
    public async Task SinAula_SeVeLoUltimoQueSeSupo_YSeDiceQueNoHayAula()
    {
        var (e, _) = await CargarAsync(Escenario.AsignacionJson("a", "Una"), Escenario.AsignacionJson("b", "Otra"));
        using (e)
        {
            e.Api.EnLinea = false;

            var resultado = await e.Servicio.LoadAsync();

            Assert.Equal(["a", "b"], resultado.Lessons.Select(x => x.Id).Order());
            Assert.True(resultado.FromCache);
            Assert.False(resultado.AulaReachable);
        }
    }

    [Fact]
    public async Task SinAulaYSinNadaGuardado_LaListaVaVaciaConUnAvisoAmable()
    {
        using var e = new Escenario().ConAulaLista();
        await e.ElegirAsync(Escenario.Sofia);
        e.Api.EnLinea = false;

        var resultado = await e.Servicio.LoadAsync();

        Assert.Empty(resultado.Lessons);
        Assert.False(resultado.AulaReachable);
        Assert.Contains("Sin conexión con el aula", resultado.Notice);
    }

    // ------------------------------------------------------------------------------------ descargas

    private static string Paquete(string id, string estado, long bytes = 300, long? vigente = null) => $$"""
        {"id":"{{id}}","asignacion_id":"a","estado":"{{estado}}","motivo":"","curso_version":"1.0.0","bytes_total":{{bytes}},"huella":"h",
         "vigente_hasta":{{(vigente is null ? "null" : vigente.Value.ToString())}},"solicitado_en":10,"disponible_en":null,"archivos":[],"no_incluidos":[],"servidor_en":{{Escenario.Ahora}}}
        """;

    private static PaqueteEstudio ParaGuardar(string id, long? vigente) => FalsoEstudioApi.Json<PaqueteEstudio>(Paquete(id, "solicitado", vigente: vigente));

    [Fact]
    public async Task LaDescarga_SeVeSegunLoQueHayEnLaTableta()
    {
        var (e, _) = await CargarAsync(Escenario.AsignacionJson("a", "Una"));
        using (e)
        {
            StudyDownloadState Estado() => e.Servicio.LoadAsync().Result.Lessons.Single().DownloadState;
            Assert.Equal(StudyDownloadState.None, Estado());

            e.Local.Almacen.RegistrarPaquete(Escenario.Ethan, ParaGuardar("paq-1", Escenario.Ahora + Escenario.Dia));
            Assert.Equal(StudyDownloadState.Paused, Estado());          // empezó a bajar y ya no hay descarga en marcha

            e.Local.Almacen.MarcarDisponible(Escenario.Ethan, "a");
            Assert.Equal(StudyDownloadState.Available, Estado());
        }
    }

    [Fact]
    public async Task UnPaqueteQueSeVencioPorFecha_SeLiberaSoloYSeLeAvisaALaPersona()
    {
        var (e, _) = await CargarAsync(Escenario.AsignacionJson("a", "Una"));
        using (e)
        {
            e.Local.Almacen.RegistrarPaquete(Escenario.Ethan, ParaGuardar("paq-1", Escenario.Ahora - 1_000));
            e.Local.Almacen.MarcarDisponible(Escenario.Ethan, "a");

            var resultado = await e.Servicio.LoadAsync();

            Assert.Equal(StudyDownloadState.None, resultado.Lessons.Single().DownloadState);   // no se sirve contenido caducado (MSG-045)
            Assert.Null(e.Local.Almacen.ObtenerPaquete(Escenario.Ethan, "a"));
            Assert.Contains("Liberamos una lección descargada que ya venció", resultado.Notice);
        }
    }

    [Fact]
    public async Task ElAulaPuedeDarPorVencidoLoDescargado_AunqueLaFechaNoHayaPasado()
    {
        var (e, _) = await CargarAsync(Escenario.AsignacionJson("a", "Una", paquete: Paquete("paq-1", "vencido", vigente: Escenario.Ahora + Escenario.Dia)));
        using (e)
        {
            e.Local.Almacen.RegistrarPaquete(Escenario.Ethan, ParaGuardar("paq-1", Escenario.Ahora + Escenario.Dia));   // salió una versión nueva del curso
            e.Local.Almacen.MarcarDisponible(Escenario.Ethan, "a");

            Assert.Equal(StudyDownloadState.Expired, (await e.Servicio.LoadAsync()).Lessons.Single().DownloadState);
        }
    }

    [Fact]
    public async Task CuandoElProfesorNoDejaLlevarselaLeccion_SeExplicaSinTecnicismos()
    {
        var (e, l) = await CargarAsync(Escenario.AsignacionJson("a", "Una", descarga: """{"permitida":false,"motivo":"paquete_no_permitido"}"""));
        using (e)
        {
            var leccion = l["a"];
            Assert.Equal((StudyDownloadState.Denied, false), (leccion.DownloadState, leccion.CanDownload));
            Assert.Contains("no dejó este material", leccion.DownloadDeniedReason);
        }
    }

    [Fact]
    public async Task SiElAulaDiceQueLaTabletaEsDeOtro_ElMensajeNoCulpaAlAlumno()
    {
        var (e, l) = await CargarAsync(Escenario.AsignacionJson("a", "Una", descarga: """{"permitida":false,"motivo":"dispositivo_ajeno"}"""));
        using (e)
            Assert.Equal("Esta tableta es de otra persona.", l["a"].DownloadDeniedReason);
    }

    [Fact]
    public async Task UnaAsignacionCerrada_YaNoSeDescarga()
    {
        var (e, l) = await CargarAsync(Escenario.AsignacionJson("a", "Una", estadoAsignacion: "cerrada"));
        using (e)
            Assert.False(l["a"].CanDownload);
    }
}

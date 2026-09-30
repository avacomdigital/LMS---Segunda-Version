using System.Text.Json;
using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Student.ModoEstudio.Models;
using Avacom.Lms.Student.ModoEstudio.Services;

namespace Avacom.Lms.Student.Tests;

/// <summary>
/// Abrir, leer y completar una lección: en línea o desde el paquete descargado. Todo lo que la persona hace se guarda PRIMERO en la tableta y
/// sale solo hacia el aula (BR-059, BR-137); completar sólo se puede con todos los bloques obligatorios atendidos (FUN-087).
/// </summary>
public sealed class LeccionTests
{
    private static AcuseSync Acuse(IEnumerable<EventoEstudio> eventos, string? tarea = null, string? asignacion = null) => FalsoEstudioApi.Json<AcuseSync>($$"""
        {"acuse":true,"servidor_en":{{Escenario.Ahora}},
         "resultados":[{{string.Join(",", eventos.Select(ev => $$"""{"secuencia":{{ev.Secuencia}},"estado":"integrado","motivo":"","detalle":null}"""))}}],
         "resumen":{"integrados":{{eventos.Count()}},"duplicados":0,"rechazados":0,"pendientes_decision":0},
         "asignaciones":[{{(tarea is null ? "" : $$"""{"id":"{{asignacion ?? Escenario.Asignacion}}","tarea":{{tarea}}}""")}}],"veredictos":[]}
        """);

    /// <summary>Una tableta con la lección de cinco bloques lista para abrirse en línea.</summary>
    private static async Task<(Escenario Escenario, IStudyLessonSession Sesion)> AbrirAsync(string estadoAsignacion = "activa", string tarea = "null", string reanudar = "null",
                                                                                            string bloques = Escenario.BloquesJson)
    {
        var e = new Escenario().ConAulaLista();
        var asignacion = Escenario.AsignacionJson(estadoAsignacion: estadoAsignacion, tarea: tarea, conBloques: true);
        e.Api.Asignaciones = _ => Escenario.ListaDe(asignacion);
        e.Api.Leccion = (_, _) => Escenario.LeccionJson(asignacion, bloques, reanudar);
        await e.ElegirAsync(Escenario.Ethan);
        await e.CargarAsync();
        var abierta = await e.Servicio.OpenLessonAsync(Escenario.Asignacion);
        Assert.True(abierta.Ok, abierta.ErrorMessage);
        return (e, abierta.Session!);
    }

    [Fact]
    public async Task EnLinea_LosBloquesSalenDeLaLeccionConSuObjeto_YSeEmpiezaDondeSeQuedo()
    {
        var (e, sesion) = await AbrirAsync(reanudar: """{"bloque_ref":"o-pres:u2","indice":2,"posicion_seg":null,"puede":true}""");
        using (e)
        {
            Assert.Equal(["lamina", "lamina", "lamina", "laboratorio", "practica"], sesion.Blocks.Select(b => b.Kind));
            Assert.Equal(("o-pres", "u1"), (sesion.Blocks[0].Objeto!.ObjetoRef, sesion.Blocks[0].UnidadRef));
            Assert.True(sesion.Blocks[3].NeedsAula);
            Assert.True(sesion.Blocks[4].IsPractice);
            Assert.Equal(1, sesion.StartIndex);           // el aula dice «bloque 2» y no lo había terminado de ver
            Assert.False(sesion.IsOfflineContent);
            Assert.Equal((5, 0), (sesion.Required, sesion.AttendedRequired));
            Assert.Equal("MATEMÁTICAS · UNIDAD 2", sesion.Eyebrow);
        }
    }

    [Fact]
    public async Task SiElAulaNoEntregaLaEstructura_SeDeduceDeLaLeccion_ConLasMismasReglas()
    {
        var (e, sesion) = await AbrirAsync(bloques: "[]");
        using (e)
        {
            // Tres láminas, un laboratorio y una práctica; el examen no es bloque.
            Assert.Equal(["o-pres:u1", "o-pres:u2", "o-pres:u3", "o-lab", "o-act"], sesion.Blocks.Select(b => b.Ref));
        }
    }

    [Fact]
    public async Task SinAulaYSinDescargar_ExplicaQueHayQueDescargarLaLeccion()
    {
        using var e = new Escenario().ConAulaLista();
        e.Api.Asignaciones = _ => Escenario.ListaDe(Escenario.AsignacionJson());
        await e.ElegirAsync(Escenario.Ethan);
        await e.CargarAsync();
        e.Api.EnLinea = false;

        var abierta = await e.Servicio.OpenLessonAsync(Escenario.Asignacion);

        Assert.False(abierta.Ok);
        Assert.Equal("Sin conexión con el aula", abierta.ErrorTitle);
        Assert.Contains("Descárgala", abierta.ErrorMessage);
    }

    [Fact]
    public async Task UnBloqueVisto_SeGuardaPrimeroEnLaTableta_SeEncolaYLaPantallaSeEntera()
    {
        var (e, sesion) = await AbrirAsync();
        using (e)
        {
            var cambios = new List<StudyLessonData>();
            e.Servicio.LessonChanged += cambios.Add;
            var bloque = sesion.Blocks[0];

            await sesion.MarkViewedAsync(bloque);

            var tarea = e.Local.Almacen.LeerTarea(Escenario.Ethan, Escenario.Asignacion)!;
            Assert.Contains(bloque.Ref, tarea.BloquesVistos);
            Assert.Equal(bloque.Ref, tarea.UltimoBloqueRef);
            var pendiente = Assert.Single(e.Local.Cola.Pendientes(Escenario.Ethan));
            Assert.Equal(TiposEventoEstudio.BloqueVisto, pendiente.Evento.Tipo);
            Assert.Equal(Escenario.Asignacion, pendiente.Evento.Carga.GetProperty("asignacion_id").GetString());
            Assert.Equal([bloque.Ref], pendiente.Evento.Carga.GetProperty("bloques_vistos").EnumerateArray().Select(x => x.GetString()));
            Assert.Equal(bloque.Ref, pendiente.Evento.Carga.GetProperty("bloque_actual").GetString());
            Assert.True(sesion.IsAttended(bloque));
            Assert.Equal(1, sesion.AttendedRequired);
            var visto = Assert.Single(cambios);
            Assert.Equal((1, true, StudyLessonState.InProgress), (visto.CompletedBlocks, visto.IsPendingSync, visto.State));
            Assert.Equal(StudySyncState.PendingSend, e.Servicio.SyncState);
        }
    }

    [Fact]
    public async Task VerUnBloqueDosVeces_NoEncolaDosVeces()
    {
        var (e, sesion) = await AbrirAsync();
        using (e)
        {
            await sesion.MarkViewedAsync(sesion.Blocks[0]);
            await sesion.MarkViewedAsync(sesion.Blocks[0]);

            Assert.Equal(1, e.Local.Cola.CantidadPendiente(Escenario.Ethan));
        }
    }

    [Fact]
    public async Task ConLaAsignacionCerrada_SeLee_PeroNoSeRegistraNada()
    {
        var (e, sesion) = await AbrirAsync(estadoAsignacion: "cerrada");
        using (e)
        {
            Assert.True(sesion.IsReadOnly);

            await sesion.MarkViewedAsync(sesion.Blocks[0]);
            var completa = await sesion.CompleteAsync();

            Assert.Equal(0, e.Local.Cola.CantidadPendiente(Escenario.Ethan));
            Assert.False(completa.Completed);
            Assert.Contains("ya se cerró", completa.Message);
        }
    }

    [Fact]
    public async Task Completar_SinTodosLosBloques_DiceCuales_YNoEncolaNada()
    {
        var (e, sesion) = await AbrirAsync();
        using (e)
        {
            await sesion.MarkViewedAsync(sesion.Blocks[0]);

            var resultado = await sesion.CompleteAsync();

            Assert.False(resultado.Completed);
            Assert.Equal(["Dos", "Tres", "Laboratorio", "Comprueba lo aprendido"], resultado.Missing);
            Assert.DoesNotContain(e.Local.Cola.Pendientes(Escenario.Ethan), p => p.Evento.Tipo == TiposEventoEstudio.LeccionCompletada);
            Assert.False(sesion.IsCompleted);
        }
    }

    [Fact]
    public async Task Completar_ConTodosLosBloques_SeGuardaYSeEncolaAlFinal()
    {
        var (e, sesion) = await AbrirAsync();
        using (e)
        {
            foreach (var bloque in sesion.Blocks) await sesion.MarkViewedAsync(bloque);

            var resultado = await sesion.CompleteAsync();

            Assert.True(resultado.Completed);
            Assert.True(sesion.IsCompleted);
            Assert.True(e.Local.Almacen.LeerTarea(Escenario.Ethan, Escenario.Asignacion)!.Completada);
            var eventos = e.Local.Cola.Pendientes(Escenario.Ethan);
            Assert.Equal(6, eventos.Count);
            Assert.Equal(TiposEventoEstudio.LeccionCompletada, eventos[^1].Evento.Tipo);                    // después de todos los bloques: el aula los integra en orden
            Assert.True(eventos.Select(x => x.Evento.Secuencia).SequenceEqual(eventos.Select(x => x.Evento.Secuencia).Order()));
            var lista = (await e.Servicio.LoadAsync()).Lessons.Single();
            Assert.Equal((StudyLessonState.Completed, true), (lista.State, lista.IsPendingSync));
        }
    }

    [Fact]
    public async Task LoHechoSinAula_SaleSoloAlVolver_YLoQueElAulaDiceSeReflejaEnLaLista()
    {
        var (e, sesion) = await AbrirAsync();
        using (e)
        {
            e.Api.EnLinea = false;
            await sesion.MarkViewedAsync(sesion.Blocks[0]);
            await sesion.MarkViewedAsync(sesion.Blocks[1]);
            await e.Servicio.SyncNowAsync();
            Assert.Equal(2, e.Local.Cola.CantidadPendiente(Escenario.Ethan));           // sin aula: no se pierde nada, todo sigue guardado
            Assert.Equal(StudySyncState.PendingSend, e.Servicio.SyncState);

            var avisos = new List<StudyLessonData>();
            e.Servicio.LessonChanged += avisos.Add;
            e.Api.EnLinea = true;
            e.Api.Sincronizar = (_, eventos, _) => Acuse(eventos, Escenario.TareaJson("en_curso", 2, 5));
            await e.Servicio.SyncNowAsync();

            Assert.Equal(0, e.Local.Cola.CantidadPendiente(Escenario.Ethan));
            Assert.Equal(StudySyncState.Saved, e.Servicio.SyncState);
            Assert.Contains(e.Api.Llamadas, l => l.StartsWith($"Sincronizar({Escenario.Dispositivo},{Escenario.Ethan},1:study.block.viewed+2:study.block.viewed"));
            var nueva = avisos.Last();
            Assert.Equal((2, false), (nueva.CompletedBlocks, nueva.IsPendingSync));     // ya no hay «↑ pendiente» en la tarjeta
        }
    }

    // ------------------------------------------------------------------------------------ desde el paquete

    private static async Task<Escenario> ConPaqueteDescargadoAsync()
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
        return e;
    }

    [Fact]
    public async Task UnaLeccionDescargada_SeLeeDelPaquete_SinPreguntarleNadaAlAula()
    {
        using var e = await ConPaqueteDescargadoAsync();
        e.Api.EnLinea = false;
        e.Api.Llamadas.Clear();

        var abierta = await e.Servicio.OpenLessonAsync(Escenario.Asignacion);

        Assert.True(abierta.Ok, abierta.ErrorMessage);
        var sesion = abierta.Session!;
        Assert.True(sesion.IsOfflineContent);
        Assert.Equal(5, sesion.Blocks.Count);
        Assert.Equal("o-pres", sesion.Blocks[0].Objeto!.ObjetoRef);
        Assert.DoesNotContain(e.Api.Llamadas, l => l.StartsWith("Leccion("));
    }

    [Fact]
    public async Task LosMediosDeUnaLeccionDescargada_SalenDelServidorLocalYNoDelAula()
    {
        using var e = await ConPaqueteDescargadoAsync();
        await e.Servicio.OpenLessonAsync(Escenario.Asignacion);

        var url = e.Servicio.ResolveMedia(Escenario.Asignacion, "/api/modo-estudio/asignaciones/asig-1/medios/img%201/");

        Assert.Equal("127.0.0.1", url.Host);
        Assert.EndsWith($"/{Escenario.Ethan}/{Escenario.Asignacion}/img%201", url.AbsolutePath);
    }

    [Fact]
    public async Task LosMediosDeUnaLeccionEnLinea_SeVanAlAulaConElAparatoYLaPersonaElegida()
    {
        var (e, sesion) = await AbrirAsync();
        using (e)
        {
            var url = sesion.Resolve("/api/modo-estudio/asignaciones/asig-1/medios/img-1/foto.png");

            Assert.Equal("aula.test", url.Host);
            Assert.Equal("/api/modo-estudio/asignaciones/asig-1/medios/img-1/foto.png", url.AbsolutePath);
            Assert.Equal($"?dispositivo={Escenario.Dispositivo}&alumno_id={Escenario.Ethan}", url.Query);
        }
    }

    [Fact]
    public async Task ATerceros_NoSeLesCuentaNada()
    {
        var (e, sesion) = await AbrirAsync();
        using (e)
        {
            var url = sesion.Resolve("https://cdn.ejemplo.org/foto.png?v=2");

            Assert.Equal("https://cdn.ejemplo.org/foto.png?v=2", url.ToString());
        }
    }
}

using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Student.ModoEstudio.Services;

namespace Avacom.Lms.Student.Tests;

/// <summary>
/// «Salir» (008-07, FUN-089/090, BR-053): cierra la sesión de estudio y deja la tableta limpia para la persona siguiente. Sin trabajo pendiente la
/// clave se destruye (todo lo cifrado queda ilegible); con trabajo sin enviar sólo se conserva su cola cifrada y la limpieza se termina después.
/// </summary>
public sealed class SalirTests
{
    private static async Task<Escenario> ConTrabajoAsync()
    {
        var e = new Escenario().ConAulaLista();
        e.Api.Asignaciones = _ => Escenario.ListaDe(Escenario.AsignacionJson());
        await e.Servicio.GetRosterAsync();                 // deja la lista de nombres guardada
        await e.ElegirAsync(Escenario.Ethan);
        await e.CargarAsync();                             // y la lista de lecciones
        return e;
    }

    private static AcuseSync AcuseDe(IEnumerable<EventoEstudio> eventos) => FalsoEstudioApi.Json<AcuseSync>($$"""
        {"acuse":true,"servidor_en":{{Escenario.Ahora}},
         "resultados":[{{string.Join(",", eventos.Select(ev => $$"""{"secuencia":{{ev.Secuencia}},"estado":"integrado","motivo":"","detalle":null}"""))}}],
         "resumen":{"integrados":{{eventos.Count()}},"duplicados":0,"rechazados":0,"pendientes_decision":0},"asignaciones":[],"veredictos":[]}
        """);

    [Fact]
    public async Task SinNadaPendiente_SeDestruyeLaClave_YNoQuedaNadaDeLaPersona()
    {
        using var e = await ConTrabajoAsync();
        Assert.True(File.Exists(Path.Combine(e.Local.Carpeta, "estudiantes.avc")));
        Assert.True(File.Exists(e.Local.RutaCola));

        await e.Servicio.CloseSessionAsync();

        Assert.True(e.Clave.Destrucciones >= 1);                                  // BR-053: lo cifrado queda ilegible de un golpe
        Assert.False(File.Exists(e.Local.RutaCola));
        Assert.False(File.Exists(Path.Combine(e.Local.Carpeta, "estudiantes.avc")));
        Assert.Null(e.Local.Almacen.LeerLista(Escenario.Ethan));
        Assert.Null(Preferences.Default.Get<string?>(EstudioLocal.ClaveAlumno, null));
        Assert.Null(e.Servicio.CurrentStudent);
        Assert.Contains($"CerrarSesion({Escenario.Dispositivo},{Escenario.Ethan},cola=0,completa=True)", e.Api.Llamadas);
    }

    [Fact]
    public async Task ConTrabajoSinEnviar_SeConservaSoloLaCola_YLaLimpiezaQuedaPendiente()
    {
        using var e = await ConTrabajoAsync();
        e.Local.Cola.Encolar(Escenario.Ethan, TiposEventoEstudio.LeccionCompletada, Escenario.Respuesta("""{"asignacion_id":"asig-1"}"""));

        await e.Servicio.CloseSessionAsync();

        Assert.Equal(0, e.Clave.Destrucciones);                                    // perder lo que el alumno hizo sería peor que un día más de clave
        Assert.True(File.Exists(e.Local.RutaCola));
        Assert.Equal(1, e.Local.Cola.CantidadPendiente(Escenario.Ethan));          // sigue esperando y sale sola (BR-137)
        Assert.Null(e.Local.Almacen.LeerLista(Escenario.Ethan));                   // pero lo personal ya no está
        Assert.False(File.Exists(Path.Combine(e.Local.Carpeta, "estudiantes.avc")));
        Assert.True(Preferences.Default.Get(EstudioLocal.ClaveLimpiezaPendiente, false));
        Assert.Contains($"CerrarSesion({Escenario.Dispositivo},{Escenario.Ethan},cola=1,completa=False)", e.Api.Llamadas);
    }

    [Fact]
    public async Task CuandoLaColaSale_SeTerminaLaLimpieza_YSeAvisaAlAula()
    {
        using var e = await ConTrabajoAsync();
        e.Local.Cola.Encolar(Escenario.Ethan, TiposEventoEstudio.LeccionCompletada, Escenario.Respuesta("""{"asignacion_id":"asig-1"}"""));
        await e.Servicio.CloseSessionAsync();
        Assert.True(Preferences.Default.Get(EstudioLocal.ClaveLimpiezaPendiente, false));

        e.Api.Sincronizar = (_, eventos, _) => AcuseDe(eventos);
        await e.Servicio.SyncNowAsync();

        Assert.Equal(0, e.Local.Cola.CantidadPendiente());
        Assert.True(e.Clave.Destrucciones >= 1);
        Assert.False(Preferences.Default.Get(EstudioLocal.ClaveLimpiezaPendiente, false));
        Assert.Contains($"LimpiezaReintentada({Escenario.Dispositivo},completa)", e.Api.Llamadas);
    }

    [Fact]
    public async Task ElProximoArranque_TerminaLaLimpiezaQueQuedoPendiente()
    {
        using var e = await ConTrabajoAsync();
        e.Local.Cola.Encolar(Escenario.Ethan, TiposEventoEstudio.LeccionCompletada, Escenario.Respuesta("""{"asignacion_id":"asig-1"}"""));
        await e.Servicio.CloseSessionAsync();
        e.Local.Cola.Reconocer(e.Local.Cola.Pendientes().Select(p => p.Evento.Secuencia));   // el aula ya recibió lo pendiente en otro momento

        await e.Servicio.TerminarLimpiezaPendienteAsync();                                      // FUN-090, al arrancar

        Assert.True(e.Clave.Destrucciones >= 1);
        Assert.False(Preferences.Default.Get(EstudioLocal.ClaveLimpiezaPendiente, false));
        Assert.Contains($"LimpiezaReintentada({Escenario.Dispositivo},completa)", e.Api.Llamadas);
    }

    [Fact]
    public async Task AunqueNadieLlegueAElegirSuNombre_LaListaDeCompanerosNoSeQueda()
    {
        using var e = new Escenario().ConAulaLista();
        await e.Servicio.GetRosterAsync();
        Assert.True(File.Exists(Path.Combine(e.Local.Carpeta, "estudiantes.avc")));

        await e.Servicio.CloseSessionAsync();

        Assert.False(File.Exists(Path.Combine(e.Local.Carpeta, "estudiantes.avc")));
    }

    [Fact]
    public async Task SinAula_SalirIgualLimpia_YNoEsperaAlAula()
    {
        using var e = await ConTrabajoAsync();
        e.Api.EnLinea = false;

        await e.Servicio.CloseSessionAsync();

        Assert.Null(e.Local.Almacen.LeerLista(Escenario.Ethan));
        Assert.True(e.Clave.Destrucciones >= 1);
        Assert.Null(e.Servicio.CurrentStudent);
    }
}

/// <summary>¿Se ve el aula? Se le pregunta al aula misma, y cualquier llamada real que conteste (o no) también lo dice.</summary>
public sealed class ConectividadTests
{
    [Fact]
    public async Task ProbeAsync_PreguntaAlAula_YAvisaSoloCuandoCambia()
    {
        using var e = new Escenario().ConAulaLista();
        var cambios = new List<bool>();
        e.Conectividad.Changed += cambios.Add;

        Assert.True(await e.Conectividad.ProbeAsync());
        e.Api.EnLinea = false;
        Assert.False(await e.Conectividad.ProbeAsync());
        Assert.False(await e.Conectividad.ProbeAsync());
        e.Api.EnLinea = true;
        Assert.True(await e.Conectividad.ProbeAsync());

        Assert.Equal([false, true], cambios);
        Assert.True(e.Conectividad.IsOnline);
    }

    [Fact]
    public async Task SiElSistemaDiceQueNoHayRed_ElAulaSeDaPorPerdidaSinPreguntar()
    {
        using var e = new Escenario().ConAulaLista();
        var cambios = new List<bool>();
        e.Conectividad.Changed += cambios.Add;

        Connectivity.Current.Cambiar(NetworkAccess.None);
        await Task.Delay(50);

        Assert.Equal([false], cambios);
        Assert.False(e.Conectividad.IsOnline);
    }
}

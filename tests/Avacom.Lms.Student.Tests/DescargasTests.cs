using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Student.ModoEstudio.Models;
using Avacom.Lms.Student.ModoEstudio.Services;

namespace Avacom.Lms.Student.Tests;

/// <summary>Las descargas de la pantalla: nunca bloquean, lo bajado se conserva y todo lo que no se puede hacer se dice sin códigos.</summary>
public sealed class DescargasTests
{
    private static PaqueteEstudio Paquete() => FalsoEstudioApi.Json<PaqueteEstudio>($$"""
        {"id":"paq-1","asignacion_id":"{{Escenario.Asignacion}}","estado":"solicitado","motivo":"","curso_version":"1.0.0","bytes_total":10,"huella":"h",
         "vigente_hasta":{{Escenario.Ahora + Escenario.Dia}},"solicitado_en":10,"disponible_en":null,"archivos":[],"no_incluidos":[],"servidor_en":{{Escenario.Ahora}}}
        """);

    [Fact]
    public async Task SinPersonaElegida_NoDescarga_YSeLoDiceAlAlumno()
    {
        using var e = new Escenario().ConAulaLista();
        var avisos = new List<StudyDownloadUpdate>();
        e.Descargas.Updated += avisos.Add;

        await e.Descargas.StartAsync(Escenario.Asignacion);

        var aviso = Assert.Single(avisos);
        Assert.Equal(StudyDownloadState.None, aviso.State);
        Assert.Contains("Todavía no sabemos", aviso.Message);
    }

    [Fact]
    public async Task SiNoHayAula_LaDescargaQuedaPausada_ConUnMensajeAmable_YNoHayNadaActivo()
    {
        using var e = new Escenario().ConAulaLista();
        await e.ElegirAsync(Escenario.Ethan);
        e.Api.EnLinea = false;
        var avisos = new List<StudyDownloadUpdate>();
        var terminada = new TaskCompletionSource<StudyDownloadUpdate>();
        e.Descargas.Updated += a => { avisos.Add(a); if (a.State is StudyDownloadState.Paused or StudyDownloadState.Denied or StudyDownloadState.Available) terminada.TrySetResult(a); };

        await e.Descargas.StartAsync(Escenario.Asignacion);
        var final = await terminada.Task.WaitAsync(TimeSpan.FromSeconds(10));

        Assert.Equal(StudyDownloadState.Requested, avisos[0].State);              // se ve al instante que «se pidió»
        Assert.Equal(StudyDownloadState.Paused, final.State);
        Assert.Contains("Sin conexión con el aula", final.Message);
        for (var i = 0; i < 50 && e.Descargas.IsActive(Escenario.Asignacion); i++) await Task.Delay(20);
        Assert.False(e.Descargas.IsActive(Escenario.Asignacion));
    }

    [Fact]
    public async Task BorrarUnaDescarga_QuitaLoLocal_AvisaAlAula_YNoTocaElAvance()
    {
        using var e = new Escenario().ConAulaLista(dueno: Escenario.Ethan);
        await e.ElegirAsync(Escenario.Ethan);
        e.Local.Almacen.RegistrarPaquete(Escenario.Ethan, Paquete());
        e.Local.Almacen.MarcarDisponible(Escenario.Ethan, Escenario.Asignacion);
        e.Local.Almacen.GuardarTarea(Escenario.Ethan, new TareaLocal(Escenario.Asignacion, ["o-pres:u1"], "o-pres:u1", null, false, 1, []));
        var avisos = new List<StudyDownloadUpdate>();
        e.Descargas.Updated += avisos.Add;

        await e.Descargas.DeleteAsync(Escenario.Asignacion);

        Assert.Null(e.Local.Almacen.ObtenerPaquete(Escenario.Ethan, Escenario.Asignacion));
        Assert.Contains($"RetirarPaquete({Escenario.Dispositivo},{Escenario.Ethan},paq-1)", e.Api.Llamadas);
        Assert.Equal(StudyDownloadState.None, avisos.Last().State);
        Assert.Contains("o-pres:u1", e.Local.Almacen.LeerTarea(Escenario.Ethan, Escenario.Asignacion)!.BloquesVistos);   // lo que estudió se conserva
    }

    [Fact]
    public async Task PausarSinDescargaActiva_NoHaceNada_YSalirPausaTodo()
    {
        using var e = new Escenario().ConAulaLista();
        await e.ElegirAsync(Escenario.Ethan);

        e.Descargas.Pause("no-existe");
        e.Descargas.PauseAll();

        Assert.False(e.Descargas.IsActive("no-existe"));
    }
}

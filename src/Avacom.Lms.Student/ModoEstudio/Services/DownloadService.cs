using System.Collections.Concurrent;
using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Student.ModoEstudio.Models;

namespace Avacom.Lms.Student.ModoEstudio.Services;

/// <summary>
/// Las descargas del modo de estudio (CAP-047) sobre <see cref="DescargadorDePaquetes"/>. Cada lección tiene su propia descarga, reanudable:
/// pausar cancela el token y lo bajado se queda; volver a empezar continúa donde se quedó. Nada de aquí bloquea la interfaz: el avance
/// llega por <see cref="Updated"/> y los textos para el alumno no llevan códigos.
/// </summary>
internal sealed class DownloadService : IDownloadService, IDisposable
{
    private readonly EstudioLocal _local;
    private readonly ConcurrentDictionary<string, CancellationTokenSource> _activas = new();

    public DownloadService(EstudioLocal local) => _local = local;

    public event Action<StudyDownloadUpdate>? Updated;

    public bool IsActive(string lessonId) => _activas.ContainsKey(lessonId);

    public Task StartAsync(string lessonId)
    {
        var alumno = _local.AlumnoId;
        if (alumno is null)
        {
            Avisar(new StudyDownloadUpdate(lessonId, StudyDownloadState.None, 0, 0, 0, null, "Todavía no sabemos de quién es esta tableta. Conéctate al aula una vez."));
            return Task.CompletedTask;
        }
        var cancelacion = new CancellationTokenSource();
        if (!_activas.TryAdd(lessonId, cancelacion))
        {
            cancelacion.Dispose();
            return Task.CompletedTask;
        }
        var previo = _local.Almacen.ObtenerPaquete(alumno, lessonId);
        Avisar(new StudyDownloadUpdate(lessonId, previo is { BytesDescargados: > 0 } ? StudyDownloadState.Downloading : StudyDownloadState.Requested,
            previo?.Fraccion ?? 0, previo?.BytesDescargados ?? 0, previo?.BytesTotal ?? 0, null));
        _ = Task.Run(() => CorrerAsync(lessonId, alumno, cancelacion));
        return Task.CompletedTask;
    }

    private async Task CorrerAsync(string lessonId, string alumno, CancellationTokenSource cancelacion)
    {
        var ultimo = new ProgresoDescarga(lessonId, 0, 0, 0, null, null, null, "descargando");
        var progreso = new Progress<ProgresoDescarga>(p =>
        {
            ultimo = p;
            Avisar(new StudyDownloadUpdate(lessonId, StudyDownloadState.Downloading, p.Fraccion, p.BytesDescargados, p.BytesTotal, p.Restante));
        });
        ResultadoDescarga resultado;
        try
        {
            resultado = await _local.Descargador.DescargarAsync(_local.Dispositivo, alumno, lessonId, progreso, cancelacion.Token);
        }
        catch (OperationCanceledException) { resultado = ResultadoDescarga.Pausada; }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "DownloadService.Correr", ex);
            resultado = ResultadoDescarga.Fallida;
        }
        finally
        {
            _activas.TryRemove(lessonId, out _);
            cancelacion.Dispose();
        }

        var local = _local.Almacen.ObtenerPaquete(alumno, lessonId);
        var bajados = local?.BytesDescargados ?? ultimo.BytesDescargados;
        var total = local?.BytesTotal is > 0 ? local.BytesTotal : ultimo.BytesTotal;
        var fraccion = local?.Fraccion ?? ultimo.Fraccion;
        Avisar(resultado switch
        {
            ResultadoDescarga.Completa => new StudyDownloadUpdate(lessonId, StudyDownloadState.Available, 1, total, total, null),
            ResultadoDescarga.Pausada => new StudyDownloadUpdate(lessonId, StudyDownloadState.Paused, fraccion, bajados, total, null),
            ResultadoDescarga.Denegada => new StudyDownloadUpdate(lessonId, StudyDownloadState.Denied, 0, 0, total, null,
                "Este material está disponible durante la clase. Para llevártelo necesitas una tableta asignada a ti."),
            ResultadoDescarga.Vencida => new StudyDownloadUpdate(lessonId, StudyDownloadState.Expired, fraccion, bajados, total, null,
                "Esta descarga ya venció. Vuelve a descargarla cuando tengas conexión con el aula."),
            ResultadoDescarga.HuellaInvalida => new StudyDownloadUpdate(lessonId, StudyDownloadState.Paused, fraccion, bajados, total, null,
                "La descarga no llegó completa. Inténtalo otra vez."),
            ResultadoDescarga.SinEspacio => new StudyDownloadUpdate(lessonId, StudyDownloadState.Paused, fraccion, bajados, total, null,
                "No hay espacio suficiente en tu tableta. Borra alguna descarga que ya no uses y continúa."),
            ResultadoDescarga.SinConexion => new StudyDownloadUpdate(lessonId, StudyDownloadState.Paused, fraccion, bajados, total, null,
                "Sin conexión con el aula. La descarga sigue cuando vuelvas a verla."),
            _ => new StudyDownloadUpdate(lessonId, StudyDownloadState.Paused, fraccion, bajados, total, null,
                "Se interrumpió la descarga. Toca para continuar."),
        });
    }

    public void Pause(string lessonId)
    {
        if (_activas.TryGetValue(lessonId, out var cancelacion))
        {
            try { cancelacion.Cancel(); }
            catch (ObjectDisposedException) { /* ya terminó */ }
        }
    }

    /// <summary>Pausa todo lo que esté bajando (al salir): lo bajado se queda hasta que se limpie el aparato.</summary>
    public void PauseAll()
    {
        foreach (var id in _activas.Keys.ToList()) Pause(id);
    }

    public async Task DeleteAsync(string lessonId)
    {
        Pause(lessonId);
        for (var i = 0; i < 40 && _activas.ContainsKey(lessonId); i++) await Task.Delay(50);   // deja que la descarga en curso suelte sus archivos
        var alumno = _local.AlumnoId;
        if (alumno is null) return;
        var paquete = _local.Almacen.ObtenerPaquete(alumno, lessonId);
        _local.Almacen.EliminarPaquete(alumno, lessonId);
        if (paquete is not null)
        {
            // Avisa al aula (retira su copia de la lista de paquetes); si no contesta no importa: lo borrado ya está borrado en la tableta.
            try { await _local.Api.RetirarPaqueteAsync(_local.Dispositivo, paquete.PaqueteId, alumno); }
            catch (Exception ex) { RegistroDeFallos.Escribir("student", "DownloadService.Retirar", ex); }
        }
        Avisar(new StudyDownloadUpdate(lessonId, StudyDownloadState.None, 0, 0, paquete?.BytesTotal ?? 0, null));
    }

    private void Avisar(StudyDownloadUpdate cambio)
    {
        try { Updated?.Invoke(cambio); }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "DownloadService.Updated", ex); }
    }

    public void Dispose()
    {
        foreach (var cancelacion in _activas.Values)
        {
            try { cancelacion.Cancel(); } catch (ObjectDisposedException) { }
        }
    }
}

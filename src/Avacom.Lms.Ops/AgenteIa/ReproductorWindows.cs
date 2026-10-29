using System.Runtime.InteropServices.WindowsRuntime;
using Avacom.Lms.Core.AgenteIa;
using Windows.Media.Core;
using Windows.Media.Playback;
using Windows.Storage.Streams;

namespace Avacom.Lms.Ops.AgenteIa;

/// <summary>
/// Reproduce la voz del asistente en Windows con <see cref="MediaPlayer"/> (WinRT): el WAV se reproduce desde memoria, sin archivos temporales, sin bloquear el hilo de la interfaz y con corte
/// inmediato (<see cref="Detener"/> o cancelación). Cada reproducción usa su propio reproductor, que se libera siempre al terminar.
///
/// <b>Tres cosas que pueden pasar y ninguna cuelga la pantalla:</b> el sistema avisa que terminó (lo normal), el sistema avisa que falló (sin tarjeta de sonido, formato que no entiende:
/// <see cref="IOException"/> con el motivo del sistema) o nunca avisa nada (el audio dura lo que dura más 15 s de margen y entonces se da por fallido con <see cref="TimeoutException"/>).
/// Quien llama (<see cref="ConversacionConAgente"/>) lo convierte en «no se pudo reproducir la voz» y deja el motivo en el log.
/// </summary>
public sealed class ReproductorWindows : IReproductorDeAudio
{
    private static readonly TimeSpan Margen = TimeSpan.FromSeconds(15);

    private readonly object _cerrojo = new();
    private MediaPlayer? _actual;
    private TaskCompletionSource<bool>? _fin;

    /// <summary>Volumen de esta aplicación, de 0 a 1 (1 = el que tenga el sistema). Las pruebas automáticas lo ponen en 0 para recorrer toda la tubería de audio sin hacer ruido en el aula.</summary>
    public double Volumen { get; set; } = 1.0;

    public async Task ReproducirAsync(byte[] wav, int duracionMs, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        Detener();                                                  // lo anterior, si todavía sonaba

        using var flujo = new InMemoryRandomAccessStream();
        await flujo.WriteAsync(wav.AsBuffer());
        flujo.Seek(0);

        var fin = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        using var origen = MediaSource.CreateFromStream(flujo, "audio/wav");
        var reproductor = new MediaPlayer { AutoPlay = false, Source = origen, Volume = Math.Clamp(Volumen, 0.0, 1.0) };
        try
        {
            // Sin los controles multimedia del sistema (el panel de volumen de Windows no debe mostrar «AVACOM» como si fuera un reproductor de música).
            try { reproductor.CommandManager.IsEnabled = false; } catch { /* versiones sin CommandManager: no pasa nada */ }
            reproductor.MediaEnded += (_, _) => fin.TrySetResult(true);
            reproductor.MediaFailed += (_, e) => fin.TrySetException(new IOException($"El sistema no pudo reproducir el audio ({e.Error}): {e.ErrorMessage}"));
            lock (_cerrojo)
            {
                _actual = reproductor;
                _fin = fin;
            }
            using var registro = ct.Register(() => fin.TrySetCanceled(ct));
            reproductor.Play();

            var tope = Task.Delay(TimeSpan.FromMilliseconds(Math.Max(duracionMs, 0)) + Margen, CancellationToken.None);
            if (await Task.WhenAny(fin.Task, tope) == tope)
                throw new TimeoutException($"El sistema no avisó que el audio de {duracionMs} ms terminó.");
            await fin.Task;                                         // relanza la falla o la cancelación
        }
        finally
        {
            lock (_cerrojo)
            {
                if (ReferenceEquals(_actual, reproductor)) { _actual = null; _fin = null; }
            }
            try { reproductor.Pause(); } catch { }
            try { reproductor.Source = null; } catch { }
            try { reproductor.Dispose(); } catch { }
        }
    }

    public void Detener()
    {
        MediaPlayer? reproductor;
        TaskCompletionSource<bool>? fin;
        lock (_cerrojo)
        {
            reproductor = _actual;
            fin = _fin;
        }
        try { reproductor?.Pause(); } catch { }
        fin?.TrySetCanceled();
    }
}

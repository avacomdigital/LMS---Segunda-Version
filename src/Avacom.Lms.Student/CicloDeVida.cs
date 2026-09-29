using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Student;

/// <summary>
/// El ciclo de vida de la ventana de Student frente al aula (007-04): la tableta declara «reconectando» cuando la app pasa a segundo
/// plano, «conectado» cuando vuelve y «salió» cuando se cierra, para que el profesor vea la verdad de cada tableta sin esperar a que
/// venza el latido. Todo es de mejor esfuerzo: si el nodo no contesta, lo resuelve por latido vencido. Sin clase guardada
/// (<see cref="Sesion.ClaseSesionId"/> nulo) no se declara nada.
///
/// Decisiones por plataforma:
/// · Android: <c>Stopped</c> (la app dejó de verse: otra app, la pantalla se apagó) es «reconectando»; <c>Resumed</c>/<c>Activated</c>
///   al volver es «conectado». <c>Deactivated</c> (OnPause) NO cuenta: también salta con el panel de notificaciones, un diálogo o el
///   modo de pantalla dividida, y ahí el alumno sigue viendo la clase.
/// · Windows: <c>Deactivated</c> sólo significa que la ventana perdió el foco (el alumno puede estar usando otra ventana un momento):
///   NO se declara «reconectando» por eso. Sí cuando la ventana se minimiza (<c>Stopped</c> de MAUI, y además el estado minimizado del
///   <c>AppWindow</c>, que no siempre lo dispara) y al cerrarla (<c>Destroying</c>).
/// · <c>Backgrounding</c> es de iOS/MacCatalyst, plataformas que Student no tiene.
/// · «conectado» al volver sólo se declara si antes se declaró «reconectando»; el canal en tiempo real lo reabre
///   <c>ClaseSiguiendoPage</c>.
/// </summary>
public static class CicloDeVida
{
    private static readonly TimeSpan TopeEnSegundoPlano = TimeSpan.FromSeconds(3);
    private static readonly TimeSpan TopeAlCerrar = TimeSpan.FromMilliseconds(1500);
    private static int _enSegundoPlano;   // 1 mientras se declaró «reconectando» y aún no se volvió

    public static void Enganchar(Window ventana)
    {
        ventana.Stopped += (_, _) => PasoASegundoPlano();
        ventana.Resumed += (_, _) => Volvio();
        ventana.Activated += (_, _) => Volvio();
        ventana.Destroying += (_, _) => Cerrando();
        // Deactivated: sin manejador a propósito (ver arriba).
#if WINDOWS
        EngancharMinimizado(ventana);
#endif
    }

    private static bool HayClaseGuardada(out string sesionId, out string participanteId)
    {
        sesionId = Sesion.ClaseSesionId ?? string.Empty;
        participanteId = Sesion.ClaseParticipanteId ?? string.Empty;
        return sesionId.Length > 0 && participanteId.Length > 0;
    }

    /// <summary>La app dejó de verse: «reconectando» con la participación guardada.</summary>
    private static void PasoASegundoPlano()
    {
        if (Volatile.Read(ref _enSegundoPlano) == 1) return;
        if (!HayClaseGuardada(out var sesionId, out var participanteId)) return;
        Volatile.Write(ref _enSegundoPlano, 1);
        _ = DeclararAsync(sesionId, participanteId, "reconectando", TopeEnSegundoPlano);
    }

    /// <summary>La app volvió: «conectado», sólo si la clase guardada sigue.</summary>
    private static void Volvio()
    {
        if (Interlocked.Exchange(ref _enSegundoPlano, 0) == 0) return;
        if (!HayClaseGuardada(out var sesionId, out var participanteId)) return;
        _ = DeclararAsync(sesionId, participanteId, "conectado", TopeEnSegundoPlano);
    }

    /// <summary>
    /// La app se cierra: «salió» por REST con un tope de 1,5 s. El cierre espera a lo sumo eso (en una red sana son milisegundos); si no
    /// llega, el nodo lo resolverá por latido vencido.
    /// </summary>
    private static void Cerrando()
    {
        if (!HayClaseGuardada(out var sesionId, out var participanteId)) return;
        try
        {
            var declarada = Task.Run(async () =>
            {
                using var limite = new CancellationTokenSource(TopeAlCerrar);
                await Sesion.Aula.PresenciaAsync(sesionId, participanteId, "salio", Sesion.Dispositivo, limite.Token);
            });
            declarada.Wait(TopeAlCerrar + TimeSpan.FromMilliseconds(250));
        }
        catch { /* mejor esfuerzo: nunca se bloquea el cierre por esto */ }
    }

    /// <summary>Por el canal en tiempo real si está abierto; si no hay canal, por REST (el nodo cuenta cualquiera de los dos).</summary>
    private static Task DeclararAsync(string sesionId, string participanteId, string estado, TimeSpan tope) => Task.Run(async () =>
    {
        try
        {
            using var limite = new CancellationTokenSource(tope);
            if (Sesion.SocketActual is { } canal && await canal.DeclararPresenciaAsync(estado, limite.Token)) return;
            await Sesion.Aula.PresenciaAsync(sesionId, participanteId, estado, Sesion.Dispositivo, limite.Token);
        }
        catch { /* mejor esfuerzo */ }
    });

#if WINDOWS
    /// <summary>
    /// En Windows, minimizar la ventana cuenta como segundo plano. MAUI no siempre lanza <c>Stopped</c> al minimizar, así que se mira el
    /// estado del presentador nativo en cada cambio de la ventana (posición, tamaño, estado): minimizada → segundo plano; cualquier otro
    /// estado → volvió. Ambos son idempotentes.
    /// </summary>
    private static void EngancharMinimizado(Window ventana)
    {
        ventana.HandlerChanged += (_, _) =>
        {
            try
            {
                if (ventana.Handler?.PlatformView is not Microsoft.UI.Xaml.Window nativa) return;
                nativa.AppWindow.Changed -= AlCambiarLaVentana;
                nativa.AppWindow.Changed += AlCambiarLaVentana;
            }
            catch { /* sin ventana nativa no hay nada que vigilar */ }
        };
    }

    private static void AlCambiarLaVentana(Microsoft.UI.Windowing.AppWindow ventana, Microsoft.UI.Windowing.AppWindowChangedEventArgs cambio)
    {
        if (ventana.Presenter is Microsoft.UI.Windowing.OverlappedPresenter { State: Microsoft.UI.Windowing.OverlappedPresenterState.Minimized }) PasoASegundoPlano();
        else Volvio();
    }
#endif
}

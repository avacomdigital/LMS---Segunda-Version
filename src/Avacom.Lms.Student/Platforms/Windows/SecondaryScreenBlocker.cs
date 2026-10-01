#if WINDOWS
using Microsoft.UI.Windowing;
using WinWindow = Microsoft.UI.Xaml.Window;
using WinGrid = Microsoft.UI.Xaml.Controls.Grid;
using WinTextBlock = Microsoft.UI.Xaml.Controls.TextBlock;
using WinSolidColorBrush = Microsoft.UI.Xaml.Media.SolidColorBrush;

namespace Avacom.Lms.Student.Examen;

/// <summary>
/// Cubre con una ventana opaca a pantalla completa cada monitor que NO es el del examen, con el texto «Esta pantalla queda bloqueada» (kiosk.md §4.4). Sólo actúa en
/// modo extendido: en modo duplicado Windows expone un único display y ambos ya muestran lo mismo, así que no hay nada que cubrir. Si el alumno conecta un monitor a
/// mitad del examen, <see cref="Sincronizar"/> (se llama periódicamente) lo cubre en la siguiente pasada.
///
/// Todo corre en el hilo de interfaz. Las ventanas de cubierta son ventanas WinUI nativas con un <c>Grid</c> y un <c>TextBlock</c> y nada más: ningún <c>Path</c> ni
/// <c>Ellipse</c>, porque una geometría degenerada tumba todos los lienzos Win2D de la ventana (D2DERR_BAD_NUMBER). No aparecen en la barra de tareas ni en Alt+Tab. Si
/// una cubierta recibe el foco (el alumno hizo clic en ella), se le devuelve a la ventana del examen.
/// </summary>
internal sealed class SecondaryScreenBlocker : IDisposable
{
    private readonly Microsoft.UI.WindowId ventanaDelExamen;
    private readonly Action? alActivarseUnaCubierta;
    private readonly Dictionary<ulong, Cubierta> cubiertas = [];
    private bool desechado;

    private sealed class Cubierta(WinWindow ventana, AppWindow appWindow)
    {
        public WinWindow Ventana { get; } = ventana;
        public AppWindow AppWindow { get; } = appWindow;
        /// <summary>Verdadero cuando somos nosotros quienes la cerramos (monitor retirado o fin del bloqueo); mientras no, el cierre se rechaza.</summary>
        public bool Cerrando { get; set; }
    }

    /// <param name="ventanaDelExamen">La ventana del examen: su monitor es el único que queda libre.</param>
    /// <param name="alActivarseUnaCubierta">Se invoca cuando el foco cae en una cubierta (para devolvérselo al examen).</param>
    public SecondaryScreenBlocker(Microsoft.UI.WindowId ventanaDelExamen, Action? alActivarseUnaCubierta = null)
    {
        this.ventanaDelExamen = ventanaDelExamen;
        this.alActivarseUnaCubierta = alActivarseUnaCubierta;
    }

    /// <summary>Cuántos monitores adicionales hay cubiertos ahora mismo.</summary>
    public int Cantidad => cubiertas.Count;

    /// <summary>
    /// Pone al día las cubiertas con los monitores que hay AHORA: abre una por cada monitor nuevo que no sea el del examen y cierra las de monitores que ya no existen.
    /// Devuelve cuántos monitores adicionales hay. Hilo de interfaz.
    /// </summary>
    public int Sincronizar()
    {
        if (desechado) return 0;
        var examen = DisplayArea.GetFromWindowId(ventanaDelExamen, DisplayAreaFallback.Nearest);
        var extras = DisplayArea.FindAll().Where(d => d.DisplayId.Value != examen.DisplayId.Value).ToDictionary(d => d.DisplayId.Value);

        foreach (var id in cubiertas.Keys.Where(id => !extras.ContainsKey(id)).ToList())
        {
            Cerrar(cubiertas[id]);
            cubiertas.Remove(id);
        }
        foreach (var (id, area) in extras)
        {
            if (cubiertas.TryGetValue(id, out var existente))
            {
                // Si el monitor cambió de resolución o de posición, la cubierta lo sigue.
                try
                {
                    var posicion = existente.AppWindow.Position;
                    var tamano = existente.AppWindow.Size;
                    var limites = area.OuterBounds;
                    if (posicion.X != limites.X || posicion.Y != limites.Y || tamano.Width != limites.Width || tamano.Height != limites.Height)
                        existente.AppWindow.MoveAndResize(limites);
                }
                catch (Exception) { /* la siguiente pasada lo reintenta */ }
                continue;
            }
            var nueva = Abrir(area);
            if (nueva is not null) cubiertas[id] = nueva;
        }
        return extras.Count;
    }

    private Cubierta? Abrir(DisplayArea area)
    {
        try
        {
            var ventana = new WinWindow
            {
                Title = "AVACOM · pantalla bloqueada",
                Content = new WinGrid
                {
                    Background = new WinSolidColorBrush(Microsoft.UI.Colors.Black),
                    Children =
                    {
                        new WinTextBlock
                        {
                            Text = "Esta pantalla queda bloqueada",
                            Foreground = new WinSolidColorBrush(Microsoft.UI.Colors.White),
                            FontSize = 32,
                            HorizontalAlignment = Microsoft.UI.Xaml.HorizontalAlignment.Center,
                            VerticalAlignment = Microsoft.UI.Xaml.VerticalAlignment.Center,
                        },
                    },
                },
            };
            var appWindow = ventana.AppWindow;
            var cubierta = new Cubierta(ventana, appWindow);
            // Primero se coloca en el monitor de destino y después se pasa a pantalla completa: el presentador usa el monitor donde está la ventana.
            appWindow.MoveAndResize(area.OuterBounds);
            appWindow.SetPresenter(AppWindowPresenterKind.FullScreen);
            try { appWindow.IsShownInSwitchers = false; } catch (Exception) { /* una versión sin la propiedad: la cubierta se ve en Alt+Tab, que ya está descartado */ }
            appWindow.Closing += (_, args) => { if (!cubierta.Cerrando) args.Cancel = true; };   // ni Alt+F4 ni la barra de tareas la cierran mientras dure el bloqueo
            ventana.Activated += (_, args) =>
            {
                if (args.WindowActivationState == Microsoft.UI.Xaml.WindowActivationState.Deactivated || desechado) return;
                try { alActivarseUnaCubierta?.Invoke(); } catch (Exception) { /* devolver el foco es un detalle, no una condición */ }
            };
            ventana.Activate();
            return cubierta;
        }
        catch (Exception)
        {
            return null;
        }
    }

    private static void Cerrar(Cubierta cubierta)
    {
        cubierta.Cerrando = true;
        try { cubierta.Ventana.Close(); }
        catch (Exception) { /* ya estaba cerrada */ }
    }

    /// <summary>Cierra todas las cubiertas. Hilo de interfaz. Repetible.</summary>
    public void Dispose()
    {
        if (desechado) return;
        desechado = true;
        foreach (var cubierta in cubiertas.Values) Cerrar(cubierta);
        cubiertas.Clear();
    }
}
#endif

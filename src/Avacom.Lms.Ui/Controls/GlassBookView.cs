using System.Diagnostics;
using Avacom.Lms.Ui.Graphics;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Libro abierto de cristal con hexágonos flotantes (<see cref="GlassBookDrawable"/>) para la esquina superior
/// derecha de «Clase de hoy». Sólo decorativo: ni la vista ni el lienzo capturan toques (<c>InputTransparent</c>).
/// Flota despacio (unos 30 cuadros por segundo, con tiempo delta) y entra en fundido con escala al cargarse; el
/// reloj arranca al entrar en el árbol visual y se detiene al salir, como <see cref="Pencil3DView"/>.
/// Ocupa el área que se le asigne desde XAML y se encuadra solo.
/// </summary>
public class GlassBookView : ContentView
{
    private readonly GlassBookDrawable dibujo = new();
    private readonly GraphicsView lienzo;
    private readonly Stopwatch cronometro = new();
    private IDispatcherTimer? reloj;
    private bool aparecido;

    public GlassBookView()
    {
        InputTransparent = true;
        BackgroundColor = Colors.Transparent;
        lienzo = new GraphicsView
        {
            Drawable = dibujo, InputTransparent = true, BackgroundColor = Colors.Transparent, Opacity = 0, Scale = 0.94,
            HorizontalOptions = LayoutOptions.Fill, VerticalOptions = LayoutOptions.Fill,
        };
        Content = lienzo;
        Loaded += (_, _) => Reanudar();
        Unloaded += (_, _) => Pausar();
    }

    /// <summary>Detiene la flotación. Seguro en cualquier momento.</summary>
    public void Pausar()
    {
        reloj?.Stop();
        cronometro.Stop();
    }

    /// <summary>(Re)arranca la flotación y, la primera vez, el fundido de entrada.</summary>
    public void Reanudar()
    {
        reloj ??= CrearReloj();
        cronometro.Restart();
        reloj.Start();
        if (aparecido) return;
        aparecido = true;
        _ = lienzo.FadeToAsync(1, 800, Easing.CubicOut);
        _ = lienzo.ScaleToAsync(1, 800, Easing.CubicOut);
    }

    private IDispatcherTimer CrearReloj()
    {
        var temporizador = Dispatcher.CreateTimer();
        temporizador.Interval = TimeSpan.FromMilliseconds(33);
        temporizador.IsRepeating = true;
        temporizador.Tick += (_, _) =>
        {
            dibujo.Phase += (float)(Math.Clamp(cronometro.Elapsed.TotalSeconds, 0, 0.1) * 0.9);
            cronometro.Restart();
            lienzo.Invalidate();
        };
        return temporizador;
    }
}

using Microsoft.Graphics.Canvas;
using Microsoft.Graphics.Canvas.Effects;
using Microsoft.Maui.Handlers;
using Microsoft.Maui.Platform;
using Microsoft.UI.Composition;
using Microsoft.UI.Xaml.Media;

namespace Avacom.Lms.Ui.Controls;

public partial class GlassBorder
{
    static partial void RegistrarPlataforma()
    {
        // MAUI pinta fondo y trazo de un Border en un Path hijo del panel, recortado a StrokeShape. Tras su mapeo del
        // fondo (y tras cambiar la forma, que lo vuelve a pintar) se cambia ese relleno por el pincel de vidrio.
        BorderHandler.Mapper.AppendToMapping(nameof(IView.Background), AplicarVidrio);
        BorderHandler.Mapper.AppendToMapping(nameof(IBorderStroke.Shape), AplicarVidrio);
    }

    private static void AplicarVidrio(IBorderHandler handler, IBorderView view)
    {
        if (view is not GlassBorder vidrio || handler.PlatformView is not ContentPanel panel) return;
        var contorno = panel.Children.OfType<Microsoft.UI.Xaml.Shapes.Path>().FirstOrDefault();
        if (contorno is null) return;
        panel.Background = null;
        contorno.Fill = new PincelVidrio(
            vidrio.Tinte.ToWindowsColor(),
            (float)Math.Max(0, vidrio.BlurRadius),
            (float)Math.Clamp(vidrio.Brightness, -2, 2),
            (float)Math.Max(0, vidrio.Saturation));
    }
}

/// <summary>
/// Pincel de composición del vidrio: lo que hay detrás del elemento, desenfocado, saturado y expuesto, y encima el
/// tinte. Si la composición no está disponible (efectos de transparencia apagados, fallo del compositor), XAML usa
/// el color de reserva: el tinte.
/// </summary>
internal sealed partial class PincelVidrio : XamlCompositionBrushBase
{
    private readonly Windows.UI.Color tinte;
    private readonly float desenfoque;
    private readonly float exposicion;
    private readonly float saturacion;

    public PincelVidrio(Windows.UI.Color tinte, float desenfoque, float exposicion, float saturacion)
    {
        this.tinte = tinte;
        this.desenfoque = desenfoque;
        this.exposicion = exposicion;
        this.saturacion = saturacion;
        FallbackColor = tinte;
    }

    protected override void OnConnected()
    {
        if (CompositionBrush is not null) return;
        var compositor = Microsoft.UI.Xaml.Media.CompositionTarget.GetCompositorForCurrentThread();
        try
        {
            var grafo = new CompositeEffect
            {
                Mode = CanvasComposite.SourceOver,
                Sources =
                {
                    new ExposureEffect
                    {
                        Exposure = exposicion,
                        Source = new SaturationEffect
                        {
                            Saturation = saturacion,
                            Source = new GaussianBlurEffect
                            {
                                BlurAmount = desenfoque,
                                BorderMode = EffectBorderMode.Hard,
                                Source = new CompositionEffectSourceParameter("fondo"),
                            },
                        },
                    },
                    new ColorSourceEffect { Color = tinte },
                },
            };
            var pincel = compositor.CreateEffectFactory(grafo).CreateBrush();
            pincel.SetSourceParameter("fondo", compositor.CreateBackdropBrush());
            CompositionBrush = pincel;
        }
        catch (Exception)
        {
            CompositionBrush = compositor.CreateColorBrush(tinte);
        }
    }

    protected override void OnDisconnected()
    {
        CompositionBrush?.Dispose();
        CompositionBrush = null;
    }
}

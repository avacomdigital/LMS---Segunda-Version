using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Lámina Liquid Glass: un <see cref="GlassBorder"/> (en Windows, lo de detrás desenfocado, saturado y teñido; en las
/// demás plataformas el tinte plano) vestido con el canto luminoso, un canto interior a 2 px, el reflejo del tercio
/// superior y una sombra violeta amplia. Sirve igual desde XAML (<c>&lt;ui:LiquidGlassPanel&gt;…&lt;/ui:LiquidGlassPanel&gt;</c>)
/// que desde código (<c>new LiquidGlassPanel { Content = … }</c>): el contenido va en <see cref="ContentView.Content"/>
/// y lo presenta la plantilla, así que las capas del material nunca estorban a lo que se pone dentro.
///
/// El aire interior se da con <see cref="ContentPadding"/>: el <c>Padding</c> heredado de <c>TemplatedView</c>
/// separa la lámina entera del borde del control (hace de margen), no el contenido de la lámina.
///
/// Niveles del lenguaje (<see cref="Glass"/>): el menú lateral usa tinte 0,14 y desenfoque 14 con radio 28; las
/// tarjetas, tinte 0,14 y desenfoque 10 con radio 22; los avisos semánticos, el tinte de su color al 50–60 %.
/// </summary>
public class LiquidGlassPanel : ContentView
{
    public static readonly BindableProperty CornerRadiusProperty = Crear(nameof(CornerRadius), 22.0);
    public static readonly BindableProperty TintColorProperty =
        BindableProperty.Create(nameof(TintColor), typeof(Color), typeof(LiquidGlassPanel), Colors.White, propertyChanged: AlCambiar);
    public static readonly BindableProperty TintOpacityProperty = Crear(nameof(TintOpacity), 0.14);
    public static readonly BindableProperty BlurRadiusProperty = Crear(nameof(BlurRadius), 10.0);
    public static readonly BindableProperty BrightnessProperty = Crear(nameof(Brightness), 0.06);
    public static readonly BindableProperty SaturationProperty = Crear(nameof(Saturation), 1.15);
    public static readonly BindableProperty BackdropProperty =
        BindableProperty.Create(nameof(Backdrop), typeof(bool), typeof(LiquidGlassPanel), true, propertyChanged: AlCambiar);
    public static readonly BindableProperty ContentPaddingProperty =
        BindableProperty.Create(nameof(ContentPadding), typeof(Thickness), typeof(LiquidGlassPanel), new Thickness(20), propertyChanged: AlCambiar);
    public static readonly BindableProperty SheenProperty =
        BindableProperty.Create(nameof(Sheen), typeof(bool), typeof(LiquidGlassPanel), true, propertyChanged: AlCambiar);
    public static readonly BindableProperty SheenHeightProperty = Crear(nameof(SheenHeight), 120.0);
    public static readonly BindableProperty SheenOpacityProperty = Crear(nameof(SheenOpacity), 0.30);
    public static readonly BindableProperty EdgeOpacityProperty = Crear(nameof(EdgeOpacity), 1.0);
    public static readonly BindableProperty ShadowColorProperty =
        BindableProperty.Create(nameof(ShadowColor), typeof(Color), typeof(LiquidGlassPanel), Glass.SombraVioleta, propertyChanged: AlCambiar);
    public static readonly BindableProperty ShadowOpacityProperty = Crear(nameof(ShadowOpacity), 0.20);
    public static readonly BindableProperty ShadowRadiusProperty = Crear(nameof(ShadowRadius), 36.0);
    public static readonly BindableProperty ShadowOffsetYProperty = Crear(nameof(ShadowOffsetY), 16.0);

    private GlassBorder? lamina;
    private Border? canto;
    private Border? reflejo;
    private Grid? cuerpo;

    public LiquidGlassPanel() => ControlTemplate = new ControlTemplate(Construir);

    /// <summary>Radio de las esquinas de la lámina (tarjetas 20–24, menú 28).</summary>
    public double CornerRadius { get => (double)GetValue(CornerRadiusProperty); set => SetValue(CornerRadiusProperty, value); }

    /// <summary>Color del tinte sobre el fondo desenfocado. Blanco para vidrio claro; un color semántico para un aviso.</summary>
    public Color TintColor { get => (Color)GetValue(TintColorProperty); set => SetValue(TintColorProperty, value); }

    /// <summary>Opacidad del tinte (0–1). 0,10–0,18 para vidrio claro.</summary>
    public double TintOpacity { get => (double)GetValue(TintOpacityProperty); set => SetValue(TintOpacityProperty, value); }

    /// <summary>Desenfoque del fondo (desviación típica en píxeles). 0 lo apaga.</summary>
    public double BlurRadius { get => (double)GetValue(BlurRadiusProperty); set => SetValue(BlurRadiusProperty, value); }

    /// <summary>Exposición del fondo desenfocado, para que el interior no se apague bajo la sombra.</summary>
    public double Brightness { get => (double)GetValue(BrightnessProperty); set => SetValue(BrightnessProperty, value); }

    /// <summary>Saturación del fondo desenfocado (1 = tal cual).</summary>
    public double Saturation { get => (double)GetValue(SaturationProperty); set => SetValue(SaturationProperty, value); }

    /// <summary>
    /// Pincel de fondo desenfocado (Windows). Apagado, la lámina es el tinte plano translúcido con canto, reflejo y
    /// sombra: es lo que usan las láminas dentro del <c>ScrollView</c> de «Clase de hoy», porque el pincel de fondo
    /// rompe los lienzos Win2D (formas y GraphicsView) que comparten el mismo desplazable.
    /// </summary>
    public bool Backdrop { get => (bool)GetValue(BackdropProperty); set => SetValue(BackdropProperty, value); }

    /// <summary>Aire entre el canto de la lámina y el contenido.</summary>
    public Thickness ContentPadding { get => (Thickness)GetValue(ContentPaddingProperty); set => SetValue(ContentPaddingProperty, value); }

    /// <summary>Si se pinta el reflejo blanco del tercio superior.</summary>
    public bool Sheen { get => (bool)GetValue(SheenProperty); set => SetValue(SheenProperty, value); }

    /// <summary>Alto del reflejo superior, en píxeles.</summary>
    public double SheenHeight { get => (double)GetValue(SheenHeightProperty); set => SetValue(SheenHeightProperty, value); }

    /// <summary>Intensidad del reflejo en su borde superior (0–1).</summary>
    public double SheenOpacity { get => (double)GetValue(SheenOpacityProperty); set => SetValue(SheenOpacityProperty, value); }

    /// <summary>Intensidad del canto luminoso (0–1).</summary>
    public double EdgeOpacity { get => (double)GetValue(EdgeOpacityProperty); set => SetValue(EdgeOpacityProperty, value); }

    /// <summary>Color de la sombra exterior (violeta por defecto).</summary>
    public Color ShadowColor { get => (Color)GetValue(ShadowColorProperty); set => SetValue(ShadowColorProperty, value); }

    public double ShadowOpacity { get => (double)GetValue(ShadowOpacityProperty); set => SetValue(ShadowOpacityProperty, value); }
    public double ShadowRadius { get => (double)GetValue(ShadowRadiusProperty); set => SetValue(ShadowRadiusProperty, value); }
    public double ShadowOffsetY { get => (double)GetValue(ShadowOffsetYProperty); set => SetValue(ShadowOffsetYProperty, value); }

    private static BindableProperty Crear(string nombre, double porDefecto) =>
        BindableProperty.Create(nombre, typeof(double), typeof(LiquidGlassPanel), porDefecto, propertyChanged: AlCambiar);

    private static void AlCambiar(BindableObject bindable, object oldValue, object newValue) => ((LiquidGlassPanel)bindable).Aplicar();

    /// <summary>Árbol de la plantilla: lámina → [canto interior, reflejo, cuerpo con el ContentPresenter]. Se construye una vez por instancia.</summary>
    private object Construir()
    {
        canto = new Border { InputTransparent = true, BackgroundColor = Colors.Transparent, StrokeThickness = 1, Margin = 2, Padding = 0 };
        reflejo = new Border
        {
            InputTransparent = true, BackgroundColor = Colors.Transparent, StrokeThickness = 0, StrokeShape = new Rectangle(),
            VerticalOptions = LayoutOptions.Start, Padding = 0,
        };
        cuerpo = new Grid { Children = { new ContentPresenter() } };
        lamina = new GlassBorder
        {
            Padding = 0, StrokeThickness = 1, BackgroundColor = Colors.Transparent,
            Content = new Grid { Children = { canto, reflejo, cuerpo } },
        };
        Aplicar();
        return lamina;
    }

    private void Aplicar()
    {
        if (lamina is null || canto is null || reflejo is null || cuerpo is null) return;
        lamina.StrokeShape = new RoundRectangle { CornerRadius = CornerRadius };
        lamina.Stroke = Glass.CantoLuminoso(EdgeOpacity);
        lamina.TintColor = TintColor;
        lamina.TintOpacity = TintOpacity;
        lamina.BlurRadius = BlurRadius;
        lamina.Brightness = Brightness;
        lamina.Saturation = Saturation;
        lamina.Backdrop = Backdrop;
        lamina.Shadow = new Shadow
        {
            Brush = new SolidColorBrush(ShadowColor), Offset = new Point(0, ShadowOffsetY), Radius = (float)ShadowRadius, Opacity = (float)ShadowOpacity,
        };
        canto.StrokeShape = new RoundRectangle { CornerRadius = Math.Max(0, CornerRadius - 2) };
        canto.Stroke = Glass.CantoInterior(EdgeOpacity);
        reflejo.IsVisible = Sheen;
        reflejo.HeightRequest = SheenHeight;
        reflejo.Background = Glass.Reflejo(SheenOpacity);
        cuerpo.Padding = ContentPadding;
    }
}

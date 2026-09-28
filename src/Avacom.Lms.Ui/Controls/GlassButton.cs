using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Botón Liquid Glass (nivel 4 del lenguaje, sin desenfoque): cuerpo blanco translúcido con degradado, canto
/// luminoso, reflejo superior y sombra violeta difusa; etiqueta blanca en Inter SemiBold. Con <see cref="Accent"/>
/// el cuerpo toma ese color casi opaco y el halo se tiñe (la píldora de acción de una materia).
///
/// Microinteracciones: al pasar el puntero crece a 1,02 y se ilumina (150 ms); al presionar baja a 0,98 (90 ms) y al
/// soltar vuelve (140 ms); <see cref="Clicked"/> se dispara al tocar. Es un <see cref="ContentView"/> y no un
/// <see cref="Button"/> porque el material (degradados, reflejo y halo) no cabe en el botón nativo de WinUI.
/// Tamaño por defecto 64 px de alto, como los botones del kit; el ancho lo fija quien lo usa.
/// </summary>
public class GlassButton : ContentView
{
    public static readonly BindableProperty TextProperty =
        BindableProperty.Create(nameof(Text), typeof(string), typeof(GlassButton), string.Empty, propertyChanged: AlCambiar);
    public static readonly BindableProperty FontSizeProperty =
        BindableProperty.Create(nameof(FontSize), typeof(double), typeof(GlassButton), 18.0, propertyChanged: AlCambiar);
    public static readonly BindableProperty TextColorProperty =
        BindableProperty.Create(nameof(TextColor), typeof(Color), typeof(GlassButton), Colors.White, propertyChanged: AlCambiar);
    public static readonly BindableProperty AccentProperty =
        BindableProperty.Create(nameof(Accent), typeof(Color), typeof(GlassButton), null, propertyChanged: AlCambiar);
    public static readonly BindableProperty CornerRadiusProperty =
        BindableProperty.Create(nameof(CornerRadius), typeof(double), typeof(GlassButton), 20.0, propertyChanged: AlCambiar);

    private readonly Border cuerpo;
    private readonly Border luz;
    private readonly Label etiqueta;
    private bool sobre;

    public GlassButton()
    {
        HeightRequest = 64;
        MinimumHeightRequest = 64;
        etiqueta = new Label
        {
            FontFamily = Ds.FuenteSemi, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center,
            HorizontalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.TailTruncation,
        };
        var reflejo = new Border
        {
            InputTransparent = true, BackgroundColor = Colors.Transparent, StrokeThickness = 0, StrokeShape = new Rectangle(), Padding = 0,
            VerticalOptions = LayoutOptions.Start, HeightRequest = 30, Background = Glass.Reflejo(0.38),
        };
        luz = new Border
        {
            InputTransparent = true, BackgroundColor = Color.FromArgb("#24FFFFFF"), StrokeThickness = 0, StrokeShape = new Rectangle(), Padding = 0, Opacity = 0,
        };
        cuerpo = new Border
        {
            BackgroundColor = Colors.Transparent, StrokeThickness = 1, Padding = new Thickness(22, 0),
            Content = new Grid { Children = { reflejo, luz, etiqueta } },
        };
        Content = cuerpo;
        Pintar();

        var toque = new TapGestureRecognizer();
        toque.Tapped += (_, _) => Clicked?.Invoke(this, EventArgs.Empty);
        var puntero = new PointerGestureRecognizer();
        puntero.PointerEntered += async (_, _) =>
        {
            sobre = true;
            _ = luz.FadeToAsync(1, 150, Easing.CubicOut);
            await cuerpo.ScaleToAsync(1.02, 150, Easing.CubicOut);
        };
        puntero.PointerExited += async (_, _) =>
        {
            sobre = false;
            _ = luz.FadeToAsync(0, 150, Easing.CubicOut);
            await cuerpo.ScaleToAsync(1, 150, Easing.CubicOut);
        };
        puntero.PointerPressed += async (_, _) => await cuerpo.ScaleToAsync(0.98, 90, Easing.CubicOut);
        puntero.PointerReleased += async (_, _) => await cuerpo.ScaleToAsync(sobre ? 1.02 : 1, 140, Easing.CubicOut);
        GestureRecognizers.Add(toque);
        GestureRecognizers.Add(puntero);
    }

    /// <summary>Se dispara al tocar el botón.</summary>
    public event EventHandler? Clicked;

    public string Text { get => (string)GetValue(TextProperty); set => SetValue(TextProperty, value); }
    public double FontSize { get => (double)GetValue(FontSizeProperty); set => SetValue(FontSizeProperty, value); }
    public Color TextColor { get => (Color)GetValue(TextColorProperty); set => SetValue(TextColorProperty, value); }

    /// <summary>Color de acento del cuerpo; null (por defecto) es vidrio blanco.</summary>
    public Color? Accent { get => (Color?)GetValue(AccentProperty); set => SetValue(AccentProperty, value); }

    public double CornerRadius { get => (double)GetValue(CornerRadiusProperty); set => SetValue(CornerRadiusProperty, value); }

    private static void AlCambiar(BindableObject bindable, object oldValue, object newValue) => ((GlassButton)bindable).Pintar();

    private void Pintar()
    {
        var acento = Accent;
        cuerpo.StrokeShape = new RoundRectangle { CornerRadius = CornerRadius };
        cuerpo.Stroke = Glass.CantoLuminoso(0.95);
        cuerpo.Background = acento is null ? Glass.Relleno(Colors.White, 0.30, 0.14) : Glass.RellenoAcento(acento, 0.92);
        cuerpo.Shadow = acento is null ? Glass.SombraVidrio(0.18, 22, 8) : Glass.Halo(acento, 0.42, 20, 8);
        etiqueta.Text = Text;
        etiqueta.FontSize = FontSize;
        // Sobre un acento claro (ámbar, cian) la etiqueta pasa a tinta oscura; sobre vidrio blanco manda TextColor.
        etiqueta.TextColor = acento is null ? TextColor : Glass.TintaSobre(acento);
    }
}

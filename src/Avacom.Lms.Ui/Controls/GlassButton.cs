using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Botón secundario del Aula · Design System: píldora blanca con contorno de 2 px en <see cref="Ds.Linea"/> y etiqueta
/// en tinta (Lexend 500); al pasar el puntero se tiñe de <see cref="Ds.Superficie2"/>. Con <see cref="Accent"/> el
/// cuerpo toma el relleno 600 → 700 de ese color y una sombra difusa del mismo tono (un botón lleno de rol).
/// Pulsado: escala 0,97 en 60 ms y vuelta. Es un <see cref="ContentView"/> (no un <see cref="Button"/>) para conservar
/// la API anterior. Alto por defecto 64 px; el ancho lo fija quien lo usa.
/// </summary>
public class GlassButton : ContentView
{
    public static readonly BindableProperty TextProperty =
        BindableProperty.Create(nameof(Text), typeof(string), typeof(GlassButton), string.Empty, propertyChanged: AlCambiar);
    public static readonly BindableProperty FontSizeProperty =
        BindableProperty.Create(nameof(FontSize), typeof(double), typeof(GlassButton), 18.0, propertyChanged: AlCambiar);
    public static readonly BindableProperty TextColorProperty =
        BindableProperty.Create(nameof(TextColor), typeof(Color), typeof(GlassButton), Ds.Tinta, propertyChanged: AlCambiar);
    public static readonly BindableProperty AccentProperty =
        BindableProperty.Create(nameof(Accent), typeof(Color), typeof(GlassButton), null, propertyChanged: AlCambiar);
    public static readonly BindableProperty CornerRadiusProperty =
        BindableProperty.Create(nameof(CornerRadius), typeof(double), typeof(GlassButton), 20.0, propertyChanged: AlCambiar);

    private readonly Border cuerpo;
    private readonly Border luz;
    private readonly Label etiqueta;

    public GlassButton()
    {
        HeightRequest = 64;
        MinimumHeightRequest = 64;
        etiqueta = new Label
        {
            FontFamily = Ds.FuenteMedia, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center,
            HorizontalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.TailTruncation,
        };
        var reflejo = new Border
        {
            InputTransparent = true, BackgroundColor = Colors.Transparent, StrokeThickness = 0, StrokeShape = new Rectangle(), Padding = 0,
            VerticalOptions = LayoutOptions.Start, HeightRequest = 30, Background = Glass.Reflejo(0.38),
        };
        luz = new Border
        {
            InputTransparent = true, BackgroundColor = Ds.Superficie2.WithAlpha(0.9f), StrokeThickness = 0, StrokeShape = new Rectangle(), Padding = 0, Opacity = 0,
        };
        cuerpo = new Border
        {
            BackgroundColor = Colors.Transparent, StrokeThickness = 1, Padding = new Thickness(22, 0),
            Content = new Grid { Children = { reflejo, luz, etiqueta } },
        };
        Content = cuerpo;
        Pintar();
        PropertyChanged += (_, e) => { if (e.PropertyName == nameof(HeightRequest)) Pintar(); };   // el radio de la píldora sigue al alto

        var toque = new TapGestureRecognizer();
        toque.Tapped += (_, _) => Clicked?.Invoke(this, EventArgs.Empty);
        var puntero = new PointerGestureRecognizer();
        puntero.PointerEntered += async (_, _) =>
        {
            await luz.FadeToAsync(Accent is null ? 1 : 0, Ds.DurBase, Easing.CubicOut);
        };
        puntero.PointerExited += async (_, _) =>
        {
            await luz.FadeToAsync(0, Ds.DurBase, Easing.CubicOut);
        };
        puntero.PointerPressed += async (_, _) => await cuerpo.ScaleToAsync(0.97, 60, Easing.CubicOut);
        puntero.PointerReleased += async (_, _) => await cuerpo.ScaleToAsync(1, 60, Easing.CubicOut);
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
        cuerpo.StrokeShape = new RoundRectangle { CornerRadius = HeightRequest > 0 ? HeightRequest / 2 : CornerRadius };   // píldora
        cuerpo.Stroke = new SolidColorBrush(acento is null ? Ds.Linea : Colors.Transparent);
        cuerpo.StrokeThickness = acento is null ? 2 : 0;
        cuerpo.Background = acento is null ? new SolidColorBrush(Ds.Superficie) : Glass.RellenoAcento(acento);
        cuerpo.Shadow = acento is null ? Ds.SombraDe(Ds.Superficie) : Glass.Halo(acento, 0.30);
        etiqueta.Text = Text;
        etiqueta.FontSize = FontSize;
        etiqueta.TextColor = acento is null ? TextColor : Glass.TintaSobre(acento);
    }
}

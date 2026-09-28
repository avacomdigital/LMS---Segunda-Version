using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Chip flotante del estado de la fuente de cursos (CMP-001 en vidrio): una cápsula blanca translúcida pequeña, con
/// filo de 9 % y sombra suave sobre el fondo claro, un punto de color semántico y una etiqueta corta en tinta. El
/// punto y el halo cambian con <see cref="Tone"/> (verde «Biblioteca conectada», ámbar «Curso de ejemplo» o
/// «Biblioteca apagada», rojo «Sin conexión con el aula», neutro «Comprobando…»); la cápsula sigue igual para que el
/// texto se lea igual en todos los estados. Es tocable como cualquier vista (la pantalla le pone su
/// <c>TapGestureRecognizer</c>); <see cref="Mostrar"/> fija texto y tono de una vez.
///
/// El punto y su halo son <see cref="Border"/> redondos y no <c>Ellipse</c>: en Windows la elipse se dibuja con Win2D
/// y en su primer cuadro dentro de esta pantalla falla (D2DERR_BAD_NUMBER) arrastrando al resto de lienzos.
/// </summary>
public class SourceStatusChip : ContentView
{
    public static readonly BindableProperty TextProperty =
        BindableProperty.Create(nameof(Text), typeof(string), typeof(SourceStatusChip), "Comprobando…", propertyChanged: AlCambiar);
    public static readonly BindableProperty ToneProperty =
        BindableProperty.Create(nameof(Tone), typeof(Glass.Tono), typeof(SourceStatusChip), Glass.Tono.Neutro, propertyChanged: AlCambiar);

    private readonly Border cuerpo;
    private readonly Border punto;
    private readonly Border halo;
    private readonly Label etiqueta;

    public SourceStatusChip()
    {
        halo = Redondo(18, 0.30);
        punto = Redondo(10, 1);
        var senal = new Grid { WidthRequest = 18, HeightRequest = 18, VerticalOptions = LayoutOptions.Center, Children = { halo, punto } };
        etiqueta = new Label
        {
            FontFamily = Ds.FuenteMedia, FontSize = 14, TextColor = Ds.Tinta, VerticalOptions = LayoutOptions.Center, LineBreakMode = LineBreakMode.TailTruncation,
        };
        cuerpo = new Border
        {
            BackgroundColor = Colors.Transparent,
            Background = Glass.Relleno(Colors.White, 0.85, 0.62),
            Stroke = new SolidColorBrush(Ds.Filo),
            StrokeThickness = 1,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioPildora },
            Padding = new Thickness(14, 10),
            Content = new HorizontalStackLayout { Spacing = 10, Children = { senal, etiqueta } },
        };
        Content = cuerpo;
        Pintar();
    }

    public string Text { get => (string)GetValue(TextProperty); set => SetValue(TextProperty, value); }
    public Glass.Tono Tone { get => (Glass.Tono)GetValue(ToneProperty); set => SetValue(ToneProperty, value); }

    /// <summary>Texto y tono de una vez.</summary>
    public void Mostrar(string texto, Glass.Tono tono)
    {
        Text = texto;
        Tone = tono;
    }

    private static Border Redondo(double diametro, double opacidad) => new()
    {
        WidthRequest = diametro, HeightRequest = diametro, Opacity = opacidad, StrokeThickness = 0, Padding = 0,
        StrokeShape = new RoundRectangle { CornerRadius = diametro / 2 }, BackgroundColor = Ds.TintaSuave,
        HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center, InputTransparent = true,
    };

    private static void AlCambiar(BindableObject bindable, object oldValue, object newValue) => ((SourceStatusChip)bindable).Pintar();

    private void Pintar()
    {
        var neutro = Tone == Glass.Tono.Neutro;
        var color = neutro ? Ds.TintaSuave : Glass.ColorDe(Tone);
        punto.BackgroundColor = color;
        halo.BackgroundColor = color;
        etiqueta.Text = Text;
        cuerpo.Shadow = neutro ? Glass.SombraVidrio(0.10, 16, 5) : Glass.Halo(color, 0.20, 16, 5);
    }
}

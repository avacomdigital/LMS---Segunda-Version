using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Graphics;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Controls;

/// <summary>
/// La composición de las pantallas de acceso de OPS (RF-00b): el mismo fondo degradado, el panal, el saludo vertical, la tarjeta de vidrio y el lápiz 3D
/// que <c>LoginPage</c>, sobre la cuadrícula de tercios: Grid <c>*,*,*</c> / <c>*,4*,*</c>, la tarjeta en el tercio central en X y de 1/6 a 5/6 en Y,
/// el lápiz centrado en el tercio derecho. Dentro de la tarjeta el tercio superior es identidad + mensaje (<see cref="Titulo"/>, <see cref="Mensaje"/>) y los
/// dos tercios inferiores son la acción (<see cref="Cuerpo"/>, en un ScrollView por si una ventana baja la deja sin sitio).
/// Lo usan el primer arranque, «Crear mi usuario», «Olvidé mi contraseña» y «Elige tu contraseña». Nada de Path ni Ellipse nuevos (Win2D).
/// </summary>
public sealed class MarcoDeAcceso : Grid
{
    public enum Tono { Neutro, Bien, Aviso, Problema }

    public Label Titulo { get; } = new() { FontSize = 22, FontAttributes = FontAttributes.Bold, LineBreakMode = LineBreakMode.WordWrap };
    public Label Mensaje { get; } = new() { FontSize = 14, TextColor = Color.FromArgb("#52525B"), LineBreakMode = LineBreakMode.WordWrap };
    /// <summary>Los dos tercios inferiores de la tarjeta: aquí va la acción de cada paso.</summary>
    public VerticalStackLayout Cuerpo { get; } = new() { Padding = new Thickness(40, 0, 40, 24), Spacing = 12, VerticalOptions = LayoutOptions.Start };
    public ScrollView Desplazamiento { get; }

    public MarcoDeAcceso()
    {
        ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)];
        RowDefinitions = [new RowDefinition(GridLength.Star), new RowDefinition(new GridLength(4, GridUnitType.Star)), new RowDefinition(GridLength.Star)];
        Background = new LinearGradientBrush(
            [new GradientStop(Color.FromArgb("#FDECEC"), 0f), new GradientStop(Color.FromArgb("#E6F6FC"), 0.42f), new GradientStop(Color.FromArgb("#FEF9E6"), 0.78f), new GradientStop(Color.FromArgb("#F5E8F1"), 1f)],
            new Point(0, 0), new Point(1, 1));

        var panal = new GraphicsView
        {
            InputTransparent = true, HorizontalOptions = LayoutOptions.Fill, VerticalOptions = LayoutOptions.Fill,
            Drawable = new RoundedHexagonBackgroundDrawable { HexagonWidth = 240, CornerRadius = 12, Gap = 6, StrokeColor = Color.FromArgb("#1A000000"), StrokeWidth = 1.25f },
        };
        Add(panal);
        SetColumnSpan((IView)panal, 3); SetRowSpan((IView)panal, 3);

        var saludo = new CyclingLabel
        {
            WidthRequest = 1200, HorizontalOptions = LayoutOptions.Start, VerticalOptions = LayoutOptions.Center, HorizontalTextAlignment = TextAlignment.Center,
            Rotation = -90, TranslationX = -520, InputTransparent = true, Words = "BIENVENIDO|WELCOME|WILLKOMMEN|BENVINGUT|BENVENUTO|BEM-VINDO",
            FadeMilliseconds = 1400, HoldMilliseconds = 2000, FontFamily = "InterLight", FontAttributes = FontAttributes.Italic, FontSize = 90,
            CharacterSpacing = 4.3, LineBreakMode = LineBreakMode.NoWrap, TextColor = Color.FromArgb("#E5262B"), TextTransform = TextTransform.Uppercase,
        };
        Add(saludo);
        SetColumnSpan((IView)saludo, 3); SetRowSpan((IView)saludo, 3);

        var cabecera = new VerticalStackLayout { Padding = new Thickness(40, 0, 40, 18), Spacing = 8, VerticalOptions = LayoutOptions.End };
        cabecera.Add(new Image { Source = "avacom_lms_kit_logo.png", Aspect = Aspect.AspectFit, HeightRequest = 100, HorizontalOptions = LayoutOptions.Start, Margin = new Thickness(-8, 0, 0, -18) });
        cabecera.Add(Titulo);
        cabecera.Add(Mensaje);

        var division = new BoxView { HeightRequest = 1, Color = Color.FromArgb("#14000000") };
        var accion = new VerticalStackLayout { Spacing = 14 };
        accion.Add(new VerticalStackLayout { Padding = new Thickness(40, 0), Children = { division } });
        accion.Add(Cuerpo);
        Desplazamiento = new ScrollView { VerticalScrollBarVisibility = ScrollBarVisibility.Never, Content = accion };

        var tercios = new Grid { RowDefinitions = [new RowDefinition(GridLength.Star), new RowDefinition(new GridLength(2, GridUnitType.Star))] };
        tercios.Add(cabecera, 0, 0);
        tercios.Add(Desplazamiento, 0, 1);

        var canto = new Border
        {
            InputTransparent = true, BackgroundColor = Colors.Transparent, StrokeThickness = 1, StrokeShape = new RoundRectangle { CornerRadius = 22 }, Margin = new Thickness(2),
            Stroke = new LinearGradientBrush([new GradientStop(Color.FromArgb("#8CFFFFFF"), 0f), new GradientStop(Color.FromArgb("#14FFFFFF"), 0.5f), new GradientStop(Color.FromArgb("#66FFFFFF"), 1f)], new Point(0, 0), new Point(1, 1)),
        };
        var brillo = new Border
        {
            InputTransparent = true, StrokeThickness = 0, StrokeShape = new Rectangle(), VerticalOptions = LayoutOptions.Start, HeightRequest = 180,
            Background = new LinearGradientBrush([new GradientStop(Color.FromArgb("#4DFFFFFF"), 0f), new GradientStop(Color.FromArgb("#00FFFFFF"), 1f)], new Point(0, 0), new Point(0, 1)),
        };
        var interior = new Grid();
        interior.Add(canto);
        interior.Add(brillo);
        interior.Add(tercios);

        var tarjeta = new GlassBorder
        {
            Padding = 0, HorizontalOptions = LayoutOptions.Fill, VerticalOptions = LayoutOptions.Fill, StrokeShape = new RoundRectangle { CornerRadius = 24 }, StrokeThickness = 1.5,
            TintColor = Colors.White, TintOpacity = 0.32, BlurRadius = 8, Brightness = 0.08, Saturation = 1.2,
            Stroke = new LinearGradientBrush(
                [new GradientStop(Color.FromArgb("#FFFFFFFF"), 0f), new GradientStop(Color.FromArgb("#8CFFFFFF"), 0.3f), new GradientStop(Color.FromArgb("#4DFFFFFF"), 0.5f), new GradientStop(Color.FromArgb("#80FFFFFF"), 0.7f), new GradientStop(Color.FromArgb("#D9FFFFFF"), 1f)],
                new Point(0, 0), new Point(1, 1)),
            Shadow = new Shadow { Brush = new SolidColorBrush(Colors.Black), Opacity = 0.12f, Offset = new Point(0, 20), Radius = 48 },
            Content = interior,
        };
        this.Add(tarjeta, 1, 1);

        this.Add(new Pencil3DView { InputTransparent = true, HorizontalOptions = LayoutOptions.Fill, VerticalOptions = LayoutOptions.Fill, SecondsPerTurn = 12, TiltDegrees = 8, FloatPixels = 3, FillRatio = 0.53 }, 2, 1);
    }

    // ------------------------------------------------------------------------------------------------------------ piezas comunes del acceso

    private static T Recurso<T>(string clave) where T : class =>
        Application.Current?.Resources.TryGetValue(clave, out var valor) == true && valor is T t ? t : null!;

    /// <summary>Rótulo pequeño encima de un campo, como en el acceso.</summary>
    public static Label Rotulo(string texto) => new() { Text = texto, FontSize = 13, Margin = new Thickness(0, 4, 0, 0) };

    public static Label Nota(string texto) => new() { Text = texto, FontSize = 12, TextColor = Color.FromArgb("#52525B"), LineBreakMode = LineBreakMode.WordWrap };

    /// <summary>Un campo de texto del acceso (el teclado del sistema, PA-08). El PIN nunca va en uno de éstos.</summary>
    public static Entry Campo(string marcador, string descripcion, bool secreto = false, bool numerico = false)
    {
        var e = new Entry
        {
            Placeholder = marcador, IsPassword = secreto, IsSpellCheckEnabled = false, IsTextPredictionEnabled = false, ReturnType = ReturnType.Next,
            Keyboard = numerico ? Keyboard.Numeric : Keyboard.Default,
        };
        SemanticProperties.SetDescription(e, descripcion);
        AutomationProperties.SetName(e, descripcion);
        return e;
    }

    /// <summary>La acción principal (rojo, con el relieve del acceso). Una sola por pantalla.</summary>
    public static (View Vista, Button Boton) Principal(string texto, EventHandler alPulsar)
    {
        var boton = new Button
        {
            Text = texto, Style = Recurso<Style>("PrimaryButton"), CornerRadius = 12, BorderWidth = 0, MinimumWidthRequest = 150, MinimumHeightRequest = 46,
            Background = new LinearGradientBrush([new GradientStop(Color.FromArgb("#F25055"), 0f), new GradientStop(Color.FromArgb("#E5262B"), 0.55f), new GradientStop(Color.FromArgb("#B81C21"), 1f)], new Point(0, 0), new Point(0, 1)),
        };
        boton.Clicked += alPulsar;
        var capsula = new Border
        {
            Style = Recurso<Style>("NeuButtonShell"), BackgroundColor = Color.FromArgb("#E5262B"), Margin = new Thickness(0, 6, 0, 0), Content = boton,
            Shadow = new Shadow { Brush = new SolidColorBrush(Color.FromArgb("#80C8222F")), Offset = new Point(0, 8), Radius = 18 },
        };
        return (capsula, boton);
    }

    /// <summary>Acción secundaria oscura (como «Comprobar conexión»).</summary>
    public static (View Vista, Button Boton) Secundaria(string texto, EventHandler alPulsar)
    {
        var boton = new Button
        {
            Text = texto, Style = Recurso<Style>("DarkButton"), CornerRadius = 12, BorderWidth = 0, MinimumWidthRequest = 150, MinimumHeightRequest = 46,
            Background = new LinearGradientBrush([new GradientStop(Color.FromArgb("#3A3A40"), 0f), new GradientStop(Color.FromArgb("#232326"), 0.55f), new GradientStop(Color.FromArgb("#0E0E10"), 1f)], new Point(0, 0), new Point(0, 1)),
        };
        boton.Clicked += alPulsar;
        var capsula = new Border
        {
            Style = Recurso<Style>("NeuButtonShell"), BackgroundColor = Color.FromArgb("#18181B"), Margin = new Thickness(0, 4, 0, 0), Content = boton,
            Shadow = new Shadow { Brush = new SolidColorBrush(Color.FromArgb("#66000000")), Offset = new Point(0, 8), Radius = 18 },
        };
        return (capsula, boton);
    }

    /// <summary>Acción discreta (texto gris, sin relieve), con el objetivo táctil del nodo: 150 × 46 px o más.</summary>
    public static Button Discreta(string texto, EventHandler alPulsar)
    {
        var b = new Button
        {
            Text = texto, BackgroundColor = Colors.Transparent, TextColor = Color.FromArgb("#52525B"), FontSize = 14, HeightRequest = 46,
            MinimumWidthRequest = 150, Padding = new Thickness(12, 0),
        };
        b.Clicked += alPulsar;
        return b;
    }

    /// <summary>Una ficha tocable (país, idioma, grupo): blanca en reposo, roja si está elegida. 150 × 46 px o más.</summary>
    public static Button Ficha(string texto, bool elegida, EventHandler alPulsar)
    {
        var b = new Button
        {
            Text = texto, HeightRequest = 46, MinimumWidthRequest = 150, CornerRadius = 12, BorderWidth = 1, Padding = new Thickness(14, 0), FontSize = 15,
            Margin = new Thickness(0, 0, 8, 8),
        };
        PintarFicha(b, elegida);
        b.Clicked += alPulsar;
        return b;
    }

    public static void PintarFicha(Button b, bool elegida)
    {
        b.BackgroundColor = elegida ? Color.FromArgb("#E5262B") : Colors.White;
        b.TextColor = elegida ? Colors.White : Color.FromArgb("#18181B");
        b.BorderColor = elegida ? Color.FromArgb("#B81C21") : Color.FromArgb("#17000000");
    }

    /// <summary>El teclado del PIN maestro con las medidas del nodo táctil (teclas de 150 × 46 px, seis puntos).</summary>
    public static TecladoPinView TecladoMaestro() => new() { Longitud = 6, TeclaAncho = 150, TeclaAlto = 46, Separacion = 10, HorizontalOptions = LayoutOptions.Center };

    /// <summary>El recuadro de estado del acceso: el texto dice lo que pasa; el color sólo acompaña.</summary>
    public sealed class Estado : Border
    {
        private readonly Label _punto = new() { Text = "●", VerticalOptions = LayoutOptions.Start };
        private readonly Label _texto = new() { LineBreakMode = LineBreakMode.WordWrap };

        public Estado()
        {
            Padding = 14;
            StrokeThickness = 0;
            var g = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 10 };
            g.Add(_punto, 0, 0);
            g.Add(_texto, 1, 0);
            Content = g;
            IsVisible = false;
        }

        public string Texto => _texto.Text ?? string.Empty;

        public void Mostrar(string? texto, Tono tono = Tono.Neutro)
        {
            if (string.IsNullOrWhiteSpace(texto)) { IsVisible = false; _texto.Text = string.Empty; return; }
            var (fondo, punto, glifo) = tono switch
            {
                Tono.Bien => ("#E6F5EE", "#019D60", "✓"),
                Tono.Aviso => ("#FEF9E6", "#9A7B00", "!"),
                Tono.Problema => ("#FDECEC", "#E5262B", "!"),
                _ => ("#F1F1F1", "#52525B", "●"),
            };
            BackgroundColor = Color.FromArgb(fondo);
            _punto.TextColor = Color.FromArgb(punto);
            _punto.Text = glifo;
            _texto.Text = texto;
            IsVisible = true;
        }
    }
}

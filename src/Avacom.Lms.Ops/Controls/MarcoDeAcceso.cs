using Avacom.Lms.Ui.Controls;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Controls;

/// <summary>
/// La composición de las pantallas de acceso de OPS (RF-00b), la misma que <c>LoginPage</c> con la estructura del Aula · Design System: fondo Nube con
/// hexágonos de marca, isla de marca, fecha y hora en la esquina y una caja blanca centrada con <see cref="Titulo"/>, <see cref="Mensaje"/> y <see cref="Cuerpo"/>.
/// La caja va en el área segura (bajo la isla) y se desplaza por dentro si una ventana baja la deja sin sitio.
/// Lo usan el primer arranque, «Crear mi usuario», «Olvidé mi contraseña» y «Elige tu contraseña». Nada de Path ni Ellipse nuevos (Win2D).
/// </summary>
public sealed class MarcoDeAcceso : Grid
{
    public enum Tono { Neutro, Bien, Aviso, Problema }

    public Label Titulo { get; } = new() { FontSize = 30, FontFamily = "LexendSemiBold", HorizontalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.WordWrap };
    public Label Mensaje { get; } = new() { FontSize = 17, TextColor = Color.FromArgb("#4F5566"), HorizontalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.WordWrap };
    /// <summary>Debajo de la cabecera de la caja: aquí va la acción de cada paso.</summary>
    public VerticalStackLayout Cuerpo { get; } = new() { Padding = new Thickness(56, 0, 56, 28), Spacing = 10, VerticalOptions = LayoutOptions.Start };
    public ScrollView Desplazamiento { get; }

    public MarcoDeAcceso()
    {
        // Aula · Design System (pizarra): fondo Nube con hexágonos de marca, isla de marca neumórfica arriba al centro, fecha y
        // hora en la esquina superior izquierda y, en el área segura, una caja blanca centrada con antetítulo, título y la acción.
        RowDefinitions = [new RowDefinition(128), new RowDefinition(GridLength.Star), new RowDefinition(48)];

        var fondo = new FondoHexagonos();
        Add(fondo);
        SetRowSpan((IView)fondo, 3);
        this.Add(new IslaDeMarca(), 0, 0);
        this.Add(new EsquinaFechaHora { Margin = new Thickness(64, 24, 0, 0) }, 0, 0);

        var cabecera = new VerticalStackLayout { Padding = new Thickness(56, 28, 56, 8), Spacing = 6 };
        cabecera.Add(new Label
        {
            Text = "ACCESO", FontFamily = "LexendSemiBold", FontSize = 12, CharacterSpacing = 1.9,
            TextColor = Color.FromArgb("#4F5566"), HorizontalTextAlignment = TextAlignment.Center,
        });
        cabecera.Add(Titulo);
        cabecera.Add(Mensaje);

        var contenido = new VerticalStackLayout { Spacing = 8 };
        contenido.Add(cabecera);
        contenido.Add(Cuerpo);
        Desplazamiento = new ScrollView { VerticalScrollBarVisibility = ScrollBarVisibility.Never, Content = contenido };

        var tarjeta = new GlassBorder
        {
            Padding = 0, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center, WidthRequest = 640,
            StrokeShape = new RoundRectangle { CornerRadius = 32 }, StrokeThickness = 1,
            TintColor = Colors.White, TintOpacity = 1, BlurRadius = 0, Brightness = 0, Saturation = 1, Backdrop = false,
            Stroke = new SolidColorBrush(Color.FromArgb("#E3E6EC")),
            Shadow = new Shadow { Brush = new SolidColorBrush(Color.FromArgb("#1F2433")), Opacity = 0.13f, Offset = new Point(0, 14), Radius = 32 },
            Content = Desplazamiento,
        };
        this.Add(tarjeta, 0, 1);
        // Sin desplazamiento: si la ventana es baja (el paso del PIN con su teclado), la caja se reduce para caber entera.
        AjusteDeCaja.Encajar(this, tarjeta, contenido, 128, 48);
    }

    // ------------------------------------------------------------------------------------------------------------ piezas comunes del acceso

    private static T Recurso<T>(string clave) where T : class =>
        Application.Current?.Resources.TryGetValue(clave, out var valor) == true && valor is T t ? t : null!;

    /// <summary>Rótulo pequeño encima de un campo, como en el acceso.</summary>
    public static Label Rotulo(string texto) => new() { Text = texto, FontSize = 13, Margin = new Thickness(0, 4, 0, 0) };

    public static Label Nota(string texto) => new() { Text = texto, FontSize = 12, TextColor = Color.FromArgb("#4F5566"), LineBreakMode = LineBreakMode.WordWrap };

    /// <summary>Un campo de texto del acceso (el teclado del sistema, PA-08). El PIN nunca va en uno de éstos.</summary>
    public static Entry Campo(string marcador, string descripcion, bool secreto = false, bool numerico = false)
    {
        var e = new Entry
        {
            Placeholder = marcador, IsPassword = secreto && !Ajustes.ClavesVisiblesDePrueba, IsSpellCheckEnabled = false, IsTextPredictionEnabled = false, ReturnType = ReturnType.Next,
            Keyboard = numerico ? Keyboard.Numeric : Keyboard.Default,
        };
        SemanticProperties.SetDescription(e, descripcion);
        AutomationProperties.SetName(e, descripcion);
        return e;
    }

    /// <summary>La acción principal del acceso (verde 600 → 700 en píldora, con sombra difusa verde). Una sola por pantalla.</summary>
    public static (View Vista, Button Boton) Principal(string texto, EventHandler alPulsar)
    {
        var boton = new Button
        {
            Text = texto, Style = Recurso<Style>("PrimaryButton"), BorderWidth = 0, MinimumWidthRequest = 120, MinimumHeightRequest = 44,
        };
        boton.Clicked += alPulsar;
        var capsula = new Border
        {
            Style = Recurso<Style>("NeuButtonShell"), BackgroundColor = Color.FromArgb("#047857"), Margin = new Thickness(0, 4, 0, 0), Content = boton,
            Shadow = new Shadow { Brush = new SolidColorBrush(Color.FromArgb("#047857")), Opacity = 0.22f, Offset = new Point(0, 4), Radius = 10 },
        };
        return (capsula, boton);
    }

    /// <summary>Acción secundaria (como «Comprobar conexión»): píldora blanca con contorno de 2 px.</summary>
    public static (View Vista, Button Boton) Secundaria(string texto, EventHandler alPulsar)
    {
        var boton = new Button
        {
            Text = texto, Style = Recurso<Style>("DarkButton"), MinimumWidthRequest = 120, MinimumHeightRequest = 44,
        };
        boton.Clicked += alPulsar;
        var capsula = new Border
        {
            Style = Recurso<Style>("NeuButtonShell"), BackgroundColor = Colors.White, Margin = new Thickness(0, 4, 0, 0), Content = boton,
            Shadow = new Shadow { Brush = new SolidColorBrush(Colors.Transparent), Opacity = 0f, Offset = new Point(0, 0), Radius = 0 },
        };
        return (capsula, boton);
    }

    /// <summary>Acción terciaria (texto azul 700, sin relleno), más baja que los botones del acceso para no competir con la acción principal.</summary>
    public static Button Discreta(string texto, EventHandler alPulsar)
    {
        var b = new Button
        {
            Text = texto, BackgroundColor = Colors.Transparent, TextColor = Color.FromArgb("#075985"), FontSize = 14, HeightRequest = 40, HorizontalOptions = LayoutOptions.Center,
            MinimumWidthRequest = 110, Padding = new Thickness(12, 0),
        };
        b.Clicked += alPulsar;
        return b;
    }

    /// <summary>Una ficha tocable (país, idioma, grupo): blanca con contorno en reposo, verde si está elegida.</summary>
    public static Button Ficha(string texto, bool elegida, EventHandler alPulsar)
    {
        var b = new Button
        {
            Text = texto, HeightRequest = 40, MinimumWidthRequest = 96, CornerRadius = 20, BorderWidth = 2, Padding = new Thickness(14, 0), FontSize = 14,
            Margin = new Thickness(0, 0, 8, 8),
        };
        PintarFicha(b, elegida);
        b.Clicked += alPulsar;
        return b;
    }

    public static void PintarFicha(Button b, bool elegida)
    {
        b.BackgroundColor = elegida ? Color.FromArgb("#047857") : Colors.White;
        b.TextColor = elegida ? Colors.White : Color.FromArgb("#1F2433");
        b.BorderColor = elegida ? Color.FromArgb("#047857") : Color.FromArgb("#E3E6EC");
    }

    /// <summary>El teclado del PIN maestro: seis puntos y las teclas por defecto del control (68 × 52), del orden de los botones del acceso.</summary>
    public static TecladoPinView TecladoMaestro() => new() { Longitud = 6, Separacion = 10, HorizontalOptions = LayoutOptions.Center };

    /// <summary>El recuadro de estado del acceso: el texto dice lo que pasa; el color sólo acompaña.</summary>
    public sealed class Estado : Border
    {
        private readonly Label _punto = new() { Text = "●", VerticalOptions = LayoutOptions.Start };
        private readonly Label _texto = new() { LineBreakMode = LineBreakMode.WordWrap };

        public Estado()
        {
            Padding = 14;
            StrokeThickness = 0;
            StrokeShape = new RoundRectangle { CornerRadius = 16 };
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
                Tono.Bien => ("#E1F5EC", "#047857", "✓"),
                Tono.Aviso => ("#FFEDDF", "#C2410C", "!"),
                Tono.Problema => ("#FDE7E7", "#C81E24", "!"),
                _ => ("#F6F7F9", "#4F5566", "●"),
            };
            BackgroundColor = Color.FromArgb(fondo);
            _punto.TextColor = Color.FromArgb(punto);
            _punto.Text = glifo;
            _texto.Text = texto;
            IsVisible = true;
        }
    }
}

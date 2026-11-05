using Avacom.Lms.Ui.Controls;
using Microsoft.Maui.Controls.Shapes;
using Path = Microsoft.Maui.Controls.Shapes.Path;

namespace Avacom.Lms.Ui.Design;

/// <summary>
/// Fábricas del antiguo lenguaje Liquid Glass, ya traducidas al <b>Aula · Design System</b>: sin desenfoque, cantos
/// luminosos, reflejos ni sombras de texto. Una «lámina» es una caja blanca con contorno completo y sombra difusa;
/// un control de color es un relleno 600 → 700 con sombra difusa del mismo color; un aviso es el 50 de su color con
/// texto en el 700. Las firmas se conservan para no tocar las pantallas que las usan.
/// Colores de materia del DS (sólo en chip e icono de materia): Ciencias verde, Matemáticas naranja, Lenguaje
/// magenta, Idiomas y sociales azul.
/// </summary>
public static class Glass
{
    // ------------------------------------------------------------------- fondo
    public static readonly Color LavandaOscura = Color.FromArgb("#A99ABD");
    public static readonly Color Lavanda = Color.FromArgb("#B5A6C5");
    public static readonly Color LavandaClara = Color.FromArgb("#C2B3CF");
    public static readonly Color TrazoPanal = Color.FromArgb("#C9BDD5");
    /// <summary>Violeta intenso: la tarjeta «Continuar la clase» y el elemento activo del menú.</summary>
    public static readonly Color Violeta = Color.FromArgb("#6D3FA3");
    /// <summary>Sombra de todas las láminas: violeta profundo, nunca negro.</summary>
    public static readonly Color SombraVioleta = Color.FromArgb("#3B1E5E");

    // ------------------------------------------------------------------- texto
    public static readonly Color Blanco = Colors.White;
    public static readonly Color Blanco85 = Color.FromArgb("#D9FFFFFF");
    public static readonly Color Blanco75 = Color.FromArgb("#BFFFFFFF");
    public static readonly Color Blanco65 = Color.FromArgb("#A6FFFFFF");
    /// <summary>Tinta oscura para los avisos ámbar y verde: el blanco no contrasta sobre esos tintes.</summary>
    public static readonly Color TintaAlerta = Ds.Naranja700;
    public static readonly Color TintaExito = Ds.Verde700;

    // ------------------------------------------------------- acentos de materia
    public static readonly Color AcentoRosa = Ds.Verde600;      // Ciencias (el nombre es histórico)
    public static readonly Color AcentoAzul = Ds.Azul600;       // Idiomas y comunicación
    public static readonly Color AcentoAmbar = Ds.Naranja600;   // Matemáticas
    public static readonly Color AcentoVioleta = Ds.Azul700;    // Sociales (azul del DS, un tono más profundo)
    public static readonly Color AcentoCian = Ds.Turquesa600;
    public static readonly Color AcentoVerde = Ds.Magenta600;   // Lenguaje (el nombre es histórico)
    private static readonly Color[] Acentos = [AcentoRosa, AcentoAzul, AcentoAmbar, AcentoVerde, AcentoCian, AcentoVioleta];

    /// <summary>
    /// Acento de una materia (colores de materia del DS): por su nombre cuando es una de las conocidas (ciencias → verde,
    /// lenguaje y comunicación → magenta, idiomas → azul, sociales → azul profundo, matemáticas → naranja) y, si no, por su posición en el catálogo,
    /// para que dos materias desconocidas no compartan color.
    /// </summary>
    public static Color AcentoMateria(string? nombre, int indice)
    {
        var n = (nombre ?? string.Empty).ToLowerInvariant();
        if (n.Contains("social") || n.Contains("histor") || n.Contains("geograf")) return AcentoVioleta;   // antes que «ciencias»: «Ciencias Sociales» es social
        if (n.Contains("cienc") || n.Contains("natur")) return AcentoRosa;
        if ((n.Contains("leng") || n.Contains("comunic")) && !n.Contains("extranj")) return AcentoVerde;   // Lenguaje y comunicación: magenta
        if (n.Contains("leng") || n.Contains("idiom") || n.Contains("ingl") || n.Contains("english")) return AcentoAzul;
        if (n.Contains("matem") || n.Contains("math")) return AcentoAmbar;
        return Acentos[((indice % Acentos.Length) + Acentos.Length) % Acentos.Length];
    }

    /// <summary>Icono sólido del Aula · Design System para una materia, con las mismas reglas de nombre que <see cref="AcentoMateria"/>; si no se reconoce, los libros.</summary>
    public static string IconoMateria(string? nombre)
    {
        var n = (nombre ?? string.Empty).ToLowerInvariant();
        if (n.Contains("social") || n.Contains("histor") || n.Contains("geograf")) return "ico_mundo.png";
        if (n.Contains("cienc") || n.Contains("natur") || n.Contains("biolog") || n.Contains("fisic") || n.Contains("quimic")) return "ico_ciencia.png";
        if (n.Contains("idiom") || n.Contains("ingl") || n.Contains("english") || n.Contains("extranj")) return "ico_idioma.png";
        if (n.Contains("leng") || n.Contains("comunic") || n.Contains("espa") || n.Contains("lectur")) return "ico_lenguaje.png";
        if (n.Contains("matem") || n.Contains("math")) return "ico_mate.png";
        return "ico_libros.png";
    }

    /// <summary>Bloque de icono del DS: cuadrado redondeado en el tono 50 de la materia con su icono sólido encima.</summary>
    public static Border BloqueIcono(Color acento, ImageSource icono, double lado = 64, double radio = 16) => new()
    {
        BackgroundColor = Ds.Suave(acento),
        StrokeThickness = 0,
        StrokeShape = new RoundRectangle { CornerRadius = radio },
        WidthRequest = lado, HeightRequest = lado,
        Content = new Image { Source = icono, Aspect = Aspect.AspectFit, WidthRequest = lado * 0.66, HeightRequest = lado * 0.66, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
    };

    /// <summary>
    /// Tinta que contrasta sobre un acento: oscura sobre los claros (ámbar, amarillo, cian), blanca sobre el resto.
    /// Usa la luminancia percibida (0,299 R + 0,587 G + 0,114 B) con umbral 0,55, no la L de HSL.
    /// </summary>
    public static Color TintaSobre(Color acento) => Ds.TintaSobre(acento);

    // ---------------------------------------------------------------- semántica
    public enum Tono { Neutro, Exito, Info, Alerta, Peligro }

    public static Color ColorDe(Tono tono) => tono switch
    {
        Tono.Exito => Ds.Exito,
        Tono.Info => Ds.Info,
        Tono.Alerta => Ds.Alerta,
        Tono.Peligro => Ds.Peligro,
        _ => Ds.Tinta3,
    };

    // ---------------------------------------------------------------- material
    /// <summary>Contorno de una caja: 1 px en <see cref="Ds.Linea"/> (contorno completo, nunca de un solo lado).</summary>
    public static LinearGradientBrush CantoLuminoso(double intensidad = 1) => Liso(Ds.Linea);

    /// <summary>Sin canto interior en el DS: pincel transparente.</summary>
    public static LinearGradientBrush CantoInterior(double intensidad = 1) => Liso(Colors.Transparent);

    /// <summary>Sin reflejos en el DS: pincel transparente.</summary>
    public static LinearGradientBrush Reflejo(double intensidad = 0.32) => Liso(Colors.Transparent);

    /// <summary>Relleno suave de un tono (fondos de estado y de selección): el tono a la opacidad media de las dos dadas.</summary>
    public static LinearGradientBrush Relleno(Color tono, double arriba, double abajo) => Liso(tono.WithAlpha((float)((arriba + abajo) / 2)));

    /// <summary>Relleno de un control de color: degradado 600 → 700 del mismo color (o liso si no es de rol).</summary>
    public static LinearGradientBrush RellenoAcento(Color acento, double alfa = 0.92) => Ds.Degradado(acento);

    /// <summary>Pincel de un solo color con la forma de un degradado, para conservar los tipos que esperan las pantallas.</summary>
    private static LinearGradientBrush Liso(Color c) => new(
        new GradientStopCollection { new GradientStop(c, 0f), new GradientStop(c, 1f) }, new Point(0, 0), new Point(0, 1));

    /// <summary>Sombra difusa de una caja (entre sh-1 y sh-2 según lo pedido).</summary>
    public static Shadow SombraVidrio(double opacidad = 0.12, double radio = 36, double desplazamiento = 14) =>
        new() { Brush = new SolidColorBrush(Ds.Tinta), Offset = new Point(0, Math.Min(desplazamiento, 14)), Radius = (float)Math.Min(radio, 32), Opacity = (float)Math.Min(opacidad, 0.12) };

    /// <summary>Sombra difusa del mismo color alrededor de un control de color.</summary>
    public static Shadow Halo(Color tono, double opacidad = 0.45, double radio = 24, double desplazamiento = 8) =>
        new() { Brush = new SolidColorBrush(tono), Offset = new Point(0, 8), Radius = 20, Opacity = (float)Math.Min(opacidad, 0.30) };

    /// <summary>El DS no lleva sombras de texto: sombra nula.</summary>
    public static Shadow SombraTexto(double opacidad = 0.28) =>
        new() { Brush = new SolidColorBrush(Colors.Transparent), Offset = new Point(0, 0), Radius = 0, Opacity = 0f };

    /// <summary>Geometría de un icono a partir de sus datos de trazado (mismo formato que <c>ProfessorHexTile.IconGeometry</c>).</summary>
    public static Geometry? Geometria(string? datos) =>
        string.IsNullOrWhiteSpace(datos) ? null : new PathGeometryConverter().ConvertFromInvariantString(datos) as Geometry;

    // ------------------------------------------------------------------- textos
    public static Label Titulo(string texto, double tamano = 21) => new()
    {
        Text = texto, FontSize = tamano, FontFamily = Ds.FuenteSemi, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap,
    };

    public static Label Cuerpo(string texto, double tamano = 16) => new()
    {
        Text = texto, FontSize = tamano, FontFamily = Ds.FuenteRegular, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.WordWrap,
    };

    public static Label Secundario(string texto, double tamano = 14) => new()
    {
        Text = texto, FontSize = tamano, FontFamily = Ds.FuenteMedia, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.WordWrap,
    };

    // ------------------------------------------------------------- componentes
    /// <summary>Chip de materia o categoría: el tono suave del acento con el texto en su tono oscuro. Identifica, no llama a la acción.</summary>
    public static Border Pildora(string texto, Color acento, double tamano = 13) => new()
    {
        BackgroundColor = Ds.Suave(acento),
        StrokeThickness = 0,
        StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioPildora },
        Padding = new Thickness(14, 6),
        VerticalOptions = LayoutOptions.Center,
        Content = new Label { Text = texto, FontSize = tamano, FontFamily = Ds.FuenteMedia, TextColor = Ds.Oscuro(acento), LineBreakMode = LineBreakMode.WordWrap },
    };

    /// <summary>Bloque de icono del color de la materia: un cuadrado redondeado con el relleno 600 → 700, sombra difusa del mismo color e icono blanco.</summary>
    public static Border Bloque(Color acento, string? geometria, double lado = 64, double radio = 16)
    {
        var reflejo = new Border
        {
            InputTransparent = true, BackgroundColor = Colors.Transparent, StrokeThickness = 0, StrokeShape = new Rectangle(),
            VerticalOptions = LayoutOptions.Start, HeightRequest = lado * 0.48, Background = Reflejo(0.45),
        };
        var capas = new Grid { Children = { reflejo } };
        // Sin geometría no se crea el Path: en Windows un Shape con trazado vacío se dibuja con una escala infinita
        // (Aspect) y Direct2D aborta la app (D2DERR_BAD_NUMBER).
        if (Geometria(geometria) is { } datos)
            capas.Children.Add(new Path
            {
                Data = datos, Aspect = Stretch.Uniform, Fill = new SolidColorBrush(TintaSobre(acento)),
                WidthRequest = lado * 0.47, HeightRequest = lado * 0.47, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center,
            });
        return new Border
        {
            BackgroundColor = Colors.Transparent,
            Background = RellenoAcento(acento, 0.92),
            StrokeThickness = 0,
            StrokeShape = new RoundRectangle { CornerRadius = radio },
            WidthRequest = lado, HeightRequest = lado, Padding = 0,
            Shadow = Halo(acento, 0.25, 20, 8),
            VerticalOptions = LayoutOptions.Center,
            Content = capas,
        };
    }

    /// <summary>
    /// Aviso no bloqueante (CMP-005): el 50 de su color de estado con el texto en el 700 (≥ 5:1), radio m 16.
    /// </summary>
    public static LiquidGlassPanel Alerta(string titulo, string? detalle, Tono tono)
    {
        var (fondo, opacidad, tinta) = tono switch
        {
            Tono.Alerta => (Ds.Naranja50, 1.0, Ds.Naranja700),
            Tono.Peligro => (Ds.Rojo50, 1.0, Ds.Rojo700),
            Tono.Exito => (Ds.Verde50, 1.0, Ds.Verde700),
            Tono.Info => (Ds.Azul50, 1.0, Ds.Azul700),
            _ => (Ds.Superficie, 1.0, Ds.Tinta),
        };
        var pila = new VerticalStackLayout { Spacing = 4 };
        pila.Add(new Label { Text = titulo, FontFamily = Ds.FuenteSemi, FontSize = 17, TextColor = tinta, LineBreakMode = LineBreakMode.WordWrap });
        if (!string.IsNullOrWhiteSpace(detalle))
            pila.Add(new Label { Text = detalle, FontFamily = Ds.FuenteRegular, FontSize = 15, TextColor = tinta.WithAlpha(0.9f), LineBreakMode = LineBreakMode.WordWrap });
        return new LiquidGlassPanel
        {
            CornerRadius = Ds.RadioM, TintColor = fondo, TintOpacity = opacidad, BlurRadius = 0, Sheen = false,
            ContentPadding = new Thickness(18, 14), ShadowOpacity = 0, Content = pila,
        };
    }

    /// <summary>Botón secundario del DS (blanco con contorno de 2 px). El principal es el verde de <see cref="Ds.Boton"/> (uno por pantalla).</summary>
    public static GlassButton Boton(string texto, EventHandler? alPulsar = null, double alto = 64, double? ancho = null)
    {
        var boton = new GlassButton { Text = texto, HeightRequest = alto, MinimumHeightRequest = alto };
        if (ancho is not null) boton.WidthRequest = ancho.Value;
        if (alPulsar is not null) boton.Clicked += alPulsar;
        return boton;
    }

    /// <summary>Estado vacío: una lámina centrada con un icono tenue, un título y una frase. No inventa contenido.</summary>
    public static LiquidGlassPanel EstadoVacio(string titulo, string detalle, string? geometriaIcono = null, double ancho = 560)
    {
        var pila = new VerticalStackLayout { Spacing = 8, HorizontalOptions = LayoutOptions.Center };
        if (geometriaIcono is not null)
            pila.Add(new Path
            {
                Data = Geometria(geometriaIcono), Aspect = Stretch.Uniform, Fill = new SolidColorBrush(Ds.TintaSuave),
                WidthRequest = 44, HeightRequest = 44, HorizontalOptions = LayoutOptions.Center, Margin = new Thickness(0, 0, 0, 6),
            });
        var cabeza = Titulo(titulo, 22);
        cabeza.HorizontalTextAlignment = TextAlignment.Center;
        var cuerpo = Cuerpo(detalle, 16);
        cuerpo.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(cabeza);
        pila.Add(cuerpo);
        return new LiquidGlassPanel
        {
            CornerRadius = Ds.RadioGrande, ContentPadding = new Thickness(32, 30), WidthRequest = ancho,
            HorizontalOptions = LayoutOptions.Center, Content = pila,
        };
    }
}

using Avacom.Lms.Ui.Controls;
using Microsoft.Maui.Controls.Shapes;
using Path = Microsoft.Maui.Controls.Shapes.Path;

namespace Avacom.Lms.Ui.Design;

/// <summary>
/// Lenguaje Liquid Glass de AVACOM para el tablero táctil del aula (estrenado en «Clase de hoy», 2026-09-28):
/// fondo lavanda con un panal de hexágonos grandes y redondeados y, encima, superficies de vidrio en cuatro niveles
/// para que la interfaz tenga jerarquía y no se ahogue en desenfoque:
/// <list type="number">
///   <item><b>Panal</b>: <c>RoundedHexagonBackgroundDrawable</c> con <see cref="TrazoPanal"/> al 40 %, detrás de todo.</item>
///   <item><b>Menú lateral</b>: una <see cref="LiquidGlassPanel"/> grande (tinte 0,14, desenfoque 14, radio 28).</item>
///   <item><b>Tarjetas</b>: <see cref="LiquidGlassPanel"/> (tinte 0,14, desenfoque 10, radio 22) y avisos semánticos
///   con tinte del color (<see cref="Alerta"/>).</item>
///   <item><b>Botones, chips, píldoras y hexágonos</b>: sin desenfoque; degradado translúcido, canto luminoso y halo
///   del color de acento (<see cref="GlassButton"/>, <see cref="SourceStatusChip"/>, <see cref="Pildora"/>,
///   <see cref="Bloque"/>, <c>ProfessorHexTile.Glass</c>).</item>
/// </list>
/// Todo el texto va en blanco (100 / 85 / 75 / 65 %) con Inter en pesos reales, como manda <see cref="Ds"/>; los
/// títulos llevan una sombra violeta breve que sostiene la legibilidad sobre el vidrio claro. Los colores semánticos
/// y el Primary rojo siguen siendo los de <see cref="Ds"/>: el vidrio cambia el material, no el significado.
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
    public static readonly Color TintaAlerta = Color.FromArgb("#3A2A00");
    public static readonly Color TintaExito = Color.FromArgb("#06301F");

    // ------------------------------------------------------- acentos de materia
    public static readonly Color AcentoRosa = Color.FromArgb("#E0409A");     // Ciencias naturales
    public static readonly Color AcentoAzul = Color.FromArgb("#2F7BF6");     // Dimensión comunicativa
    public static readonly Color AcentoAmbar = Color.FromArgb("#F5A524");    // Matemáticas
    public static readonly Color AcentoVioleta = Color.FromArgb("#8A5CF6");  // Social Studies
    public static readonly Color AcentoCian = Color.FromArgb("#1FB6E8");
    public static readonly Color AcentoVerde = Color.FromArgb("#22B573");
    private static readonly Color[] Acentos = [AcentoRosa, AcentoAzul, AcentoAmbar, AcentoVioleta, AcentoCian, AcentoVerde];

    /// <summary>
    /// Acento de una materia: por su nombre cuando es una de las conocidas (ciencias → rosa, comunicación e idiomas →
    /// azul, matemáticas → ámbar, sociales → violeta) y, si no, por su posición en el catálogo, para que dos materias
    /// desconocidas no compartan color.
    /// </summary>
    public static Color AcentoMateria(string? nombre, int indice)
    {
        var n = (nombre ?? string.Empty).ToLowerInvariant();
        if (n.Contains("cienc") || n.Contains("natur")) return AcentoRosa;
        if (n.Contains("comunic") || n.Contains("leng") || n.Contains("idiom") || n.Contains("ingl") || n.Contains("english")) return AcentoAzul;
        if (n.Contains("matem") || n.Contains("math")) return AcentoAmbar;
        if (n.Contains("social") || n.Contains("histor") || n.Contains("geograf")) return AcentoVioleta;
        return Acentos[((indice % Acentos.Length) + Acentos.Length) % Acentos.Length];
    }

    /// <summary>
    /// Tinta que contrasta sobre un acento: oscura sobre los claros (ámbar, amarillo, cian), blanca sobre el resto.
    /// Usa la luminancia percibida (0,299 R + 0,587 G + 0,114 B) con umbral 0,55, no la L de HSL.
    /// </summary>
    public static Color TintaSobre(Color acento)
    {
        var luminancia = 0.299 * acento.Red + 0.587 * acento.Green + 0.114 * acento.Blue;
        return luminancia > 0.55 ? Ds.Tinta : Blanco;
    }

    // ---------------------------------------------------------------- semántica
    public enum Tono { Neutro, Exito, Info, Alerta, Peligro }

    public static Color ColorDe(Tono tono) => tono switch
    {
        Tono.Exito => Ds.Exito,
        Tono.Info => Ds.Info,
        Tono.Alerta => Ds.Alerta,
        Tono.Peligro => Ds.Peligro,
        _ => Blanco75,
    };

    // ---------------------------------------------------------------- material
    /// <summary>Canto de una lámina: luz que entra arriba a la izquierda, se apaga en los lados y vuelve abajo a la derecha.</summary>
    public static LinearGradientBrush CantoLuminoso(double intensidad = 1) => new(
        new GradientStopCollection
        {
            new GradientStop(Blanco.WithAlpha((float)(0.95 * intensidad)), 0f),
            new GradientStop(Blanco.WithAlpha((float)(0.45 * intensidad)), 0.35f),
            new GradientStop(Blanco.WithAlpha((float)(0.18 * intensidad)), 0.55f),
            new GradientStop(Blanco.WithAlpha((float)(0.40 * intensidad)), 0.75f),
            new GradientStop(Blanco.WithAlpha((float)(0.80 * intensidad)), 1f),
        },
        new Point(0, 0), new Point(1, 1));

    /// <summary>Canto interior, a 2 px del borde: el vidrio es más luminoso junto a su filo.</summary>
    public static LinearGradientBrush CantoInterior(double intensidad = 1) => new(
        new GradientStopCollection
        {
            new GradientStop(Blanco.WithAlpha((float)(0.50 * intensidad)), 0f),
            new GradientStop(Blanco.WithAlpha((float)(0.06 * intensidad)), 0.5f),
            new GradientStop(Blanco.WithAlpha((float)(0.32 * intensidad)), 1f),
        },
        new Point(0, 0), new Point(1, 1));

    /// <summary>Reflejo del tercio superior: blanco que se funde hacia abajo.</summary>
    public static LinearGradientBrush Reflejo(double intensidad = 0.32) => new(
        new GradientStopCollection { new GradientStop(Blanco.WithAlpha((float)intensidad), 0f), new GradientStop(Blanco.WithAlpha(0f), 1f) },
        new Point(0, 0), new Point(0, 1));

    /// <summary>Cuerpo translúcido de un control: el mismo tono, algo más presente arriba (donde da la luz) que abajo.</summary>
    public static LinearGradientBrush Relleno(Color tono, double arriba, double abajo) => new(
        new GradientStopCollection { new GradientStop(tono.WithAlpha((float)arriba), 0f), new GradientStop(tono.WithAlpha((float)abajo), 1f) },
        new Point(0, 0), new Point(0, 1));

    /// <summary>Cuerpo de un control de color: el acento algo más claro arriba y más oscuro abajo, casi opaco.</summary>
    public static LinearGradientBrush RellenoAcento(Color acento, double alfa = 0.92) => new(
        new GradientStopCollection
        {
            new GradientStop(acento.AddLuminosity(0.08f).WithAlpha((float)alfa), 0f),
            new GradientStop(acento.WithAlpha((float)alfa), 0.55f),
            new GradientStop(acento.AddLuminosity(-0.06f).WithAlpha((float)alfa), 1f),
        },
        new Point(0, 0), new Point(0, 1));

    /// <summary>Sombra violeta amplia y suave que despega una lámina del fondo.</summary>
    public static Shadow SombraVidrio(double opacidad = 0.20, double radio = 36, double desplazamiento = 16) =>
        new() { Brush = new SolidColorBrush(SombraVioleta), Offset = new Point(0, desplazamiento), Radius = (float)radio, Opacity = (float)opacidad };

    /// <summary>Halo del color de acento alrededor de un control coloreado.</summary>
    public static Shadow Halo(Color tono, double opacidad = 0.45, double radio = 24, double desplazamiento = 8) =>
        new() { Brush = new SolidColorBrush(tono), Offset = new Point(0, desplazamiento), Radius = (float)radio, Opacity = (float)opacidad };

    /// <summary>Sombra breve bajo un título blanco: sostiene la legibilidad sobre el vidrio claro.</summary>
    public static Shadow SombraTexto(double opacidad = 0.28) =>
        new() { Brush = new SolidColorBrush(SombraVioleta), Offset = new Point(0, 2), Radius = 10, Opacity = (float)opacidad };

    /// <summary>Geometría de un icono a partir de sus datos de trazado (mismo formato que <c>ProfessorHexTile.IconGeometry</c>).</summary>
    public static Geometry? Geometria(string? datos) =>
        string.IsNullOrWhiteSpace(datos) ? null : new PathGeometryConverter().ConvertFromInvariantString(datos) as Geometry;

    // ------------------------------------------------------------------- textos
    public static Label Titulo(string texto, double tamano = 21) => new()
    {
        Text = texto, FontSize = tamano, FontFamily = Ds.FuenteSemi, TextColor = Blanco, LineBreakMode = LineBreakMode.WordWrap, Shadow = SombraTexto(),
    };

    public static Label Cuerpo(string texto, double tamano = 16) => new()
    {
        Text = texto, FontSize = tamano, FontFamily = Ds.FuenteRegular, TextColor = Blanco85, LineBreakMode = LineBreakMode.WordWrap,
    };

    public static Label Secundario(string texto, double tamano = 14) => new()
    {
        Text = texto, FontSize = tamano, FontFamily = Ds.FuenteMedia, TextColor = Blanco75, LineBreakMode = LineBreakMode.WordWrap,
    };

    // ------------------------------------------------------------- componentes
    /// <summary>Cápsula de categoría con el acento de la materia: degradado, canto luminoso y halo muy suave. Identifica, no llama a la acción.</summary>
    public static Border Pildora(string texto, Color acento, double tamano = 13) => new()
    {
        BackgroundColor = Colors.Transparent,
        Background = RellenoAcento(acento, 0.96),
        Stroke = CantoLuminoso(0.9),
        StrokeThickness = 1,
        StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioPildora },
        Padding = new Thickness(14, 7),
        Shadow = Halo(acento, 0.38, 18, 6),
        VerticalOptions = LayoutOptions.Center,
        Content = new Label { Text = texto, FontSize = tamano, FontFamily = Ds.FuenteSemi, TextColor = TintaSobre(acento), LineBreakMode = LineBreakMode.WordWrap },
    };

    /// <summary>Bloque de icono del color de la materia: un cuadrado de vidrio coloreado con reflejo superior, canto claro, halo e icono blanco.</summary>
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
            Stroke = CantoLuminoso(0.9),
            StrokeThickness = 1,
            StrokeShape = new RoundRectangle { CornerRadius = radio },
            WidthRequest = lado, HeightRequest = lado, Padding = 0,
            Shadow = Halo(acento, 0.45, 20, 8),
            VerticalOptions = LayoutOptions.Center,
            Content = capas,
        };
    }

    /// <summary>
    /// Alerta no bloqueante (CMP-005) en vidrio semántico: ámbar, rojo o verde translúcidos. La tinta del texto se elige
    /// por contraste: blanca sobre rojo e info, oscura sobre ámbar y verde.
    /// </summary>
    public static LiquidGlassPanel Alerta(string titulo, string? detalle, Tono tono)
    {
        var (fondo, opacidad, tinta) = tono switch
        {
            Tono.Alerta => (Ds.Alerta, 0.55, TintaAlerta),
            Tono.Peligro => (Ds.Peligro, 0.62, Blanco),
            Tono.Exito => (Ds.Exito, 0.55, TintaExito),
            Tono.Info => (Ds.Info, 0.50, Blanco),
            _ => (Blanco, 0.18, Blanco),
        };
        var pila = new VerticalStackLayout { Spacing = 4 };
        pila.Add(new Label { Text = titulo, FontFamily = Ds.FuenteSemi, FontSize = 17, TextColor = tinta, LineBreakMode = LineBreakMode.WordWrap });
        if (!string.IsNullOrWhiteSpace(detalle))
            pila.Add(new Label { Text = detalle, FontFamily = Ds.FuenteRegular, FontSize = 15, TextColor = tinta.WithAlpha(0.9f), LineBreakMode = LineBreakMode.WordWrap });
        return new LiquidGlassPanel
        {
            CornerRadius = 16, TintColor = fondo, TintOpacity = opacidad, BlurRadius = 8, SheenHeight = 40,
            ContentPadding = new Thickness(18, 14), ShadowOpacity = 0.16, Content = pila,
        };
    }

    /// <summary>Botón de vidrio: el Secondary del lenguaje. El Primary sigue siendo el rojo de <see cref="Ds.Boton"/> (uno por pantalla).</summary>
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
                Data = Geometria(geometriaIcono), Aspect = Stretch.Uniform, Fill = new SolidColorBrush(Blanco75),
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

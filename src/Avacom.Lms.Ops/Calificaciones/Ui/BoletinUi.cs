using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>
/// Las piezas del boletín y de las listas de estudiantes, en el mismo neumorfismo del resto de OPS: superficies del color del lienzo que se levantan con dos sombras (luz arriba a la izquierda,
/// sombra abajo a la derecha), pozos hundidos para lo que se lee en tabla, y notas «selladas» como en un boletín de colegio. MAUI sólo admite una sombra por vista: el relieve son DOS capas
/// (la exterior echa la luz, la interior la sombra). Sólo rectángulos redondeados y círculos: ningún trazo (Win2D se cae con las geometrías degeneradas, ver win2d-path-nan).
/// </summary>
internal static class BoletinUi
{
    public static readonly Color Lienzo = Color.FromArgb("#EAF0F6");
    public static readonly Color Superficie = Color.FromArgb("#F6F7F9");
    public static readonly Color PozoFondo = Color.FromArgb("#E3E6EC");
    public static readonly Color Regla = Color.FromArgb("#1F000000");

    /// <summary>
    /// Una superficie en relieve: se ve levantada del lienzo. Todo lo que se lee va en una. Un <see cref="Border"/> recorta lo que contiene (incluidas las sombras de un Border interior), así
    /// que las dos sombras viven en DOS bordes hermanos que se superponen en un Grid: el de abajo echa la sombra oscura (abajo a la derecha) y el de arriba, con el contenido, la luz.
    /// </summary>
    public static View Relieve(View contenido, double radio = 26, Thickness? relleno = null, Color? fondo = null)
    {
        var color = fondo ?? Superficie;
        var sombra = new Border
        {
            BackgroundColor = color, StrokeThickness = 0, StrokeShape = new RoundRectangle { CornerRadius = radio },
            Shadow = new Shadow { Brush = new SolidColorBrush(Color.FromArgb("#1F2433")), Offset = new Point(10, 12), Radius = 22, Opacity = 0.26f },
        };
        var luz = new Border
        {
            BackgroundColor = color, Stroke = new SolidColorBrush(Color.FromArgb("#99FFFFFF")), StrokeThickness = 1, StrokeShape = new RoundRectangle { CornerRadius = radio },
            Padding = relleno ?? new Thickness(22), Content = contenido,
            Shadow = new Shadow { Brush = new SolidColorBrush(Colors.White), Offset = new Point(-9, -9), Radius = 18, Opacity = 1f },
        };
        var capas = new Grid();
        capas.Add(sombra);
        capas.Add(luz);
        return capas;
    }

    /// <summary>Un pozo hundido: lo contrario del relieve. Sirve para las filas de una tabla y para los números que se leen de un vistazo.</summary>
    public static Border Hundido(View contenido, double radio = 16, Thickness? relleno = null, Color? fondo = null) => new()
    {
        BackgroundColor = fondo ?? PozoFondo,
        Stroke = new LinearGradientBrush(new GradientStopCollection
        {
            new GradientStop(Color.FromArgb("#2E000000"), 0f), new GradientStop(Color.FromArgb("#00FFFFFF"), 0.5f), new GradientStop(Color.FromArgb("#D9FFFFFF"), 1f),
        }, new Point(0, 0), new Point(1, 1)),
        StrokeThickness = 1.5,
        StrokeShape = new RoundRectangle { CornerRadius = radio },
        Padding = relleno ?? new Thickness(14, 10),
        Content = contenido,
    };

    /// <summary>La banda de colores de la marca (la misma de la barra de búsqueda): la cabecera de un boletín.</summary>
    public static View BandaDeColores(double alto = 8)
    {
        var banda = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)], HeightRequest = alto };
        Color[] colores = [Color.FromArgb("#F6C3C4"), Color.FromArgb("#F3E29A"), Color.FromArgb("#BFE6D3"), Color.FromArgb("#BCE5F5"), Color.FromArgb("#E8C2DD"), Color.FromArgb("#E3E6EC")];
        for (var i = 0; i < colores.Length; i++) banda.Add(new BoxView { Color = colores[i], CornerRadius = 0 }, i, 0);
        return banda;
    }

    /// <summary>El círculo con las iniciales de quien es: azul de perfil (catálogo de iconos del DS).</summary>
    public static View Avatar(string nombre, double lado = 88)
    {
        var circulo = new Border
        {
            WidthRequest = lado, HeightRequest = lado, Background = Ds.Degradado(Ds.Azul600), StrokeThickness = 0,
            Stroke = Ds.Bisel(), StrokeShape = new RoundRectangle { CornerRadius = lado / 2 }, Shadow = Ds.SombraDe(Ds.Azul600), VerticalOptions = LayoutOptions.Center,
            Content = new Label { Text = BoletinTexto.Iniciales(nombre), FontFamily = Ds.FuenteMedia, FontSize = lado * 0.38, TextColor = Colors.White, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
        };
        SemanticProperties.SetDescription(circulo, $"Iniciales de {nombre}");
        return circulo;
    }

    /// <summary>
    /// La nota «sellada»: un cuadro redondeado con la nota grande y, debajo, su lectura. Verde si cumple el criterio de aprobación del sistema, rojo si no, gris si no hay nota o el sistema no lo
    /// define: nunca un cero inventado, sin nota es un guion.
    /// </summary>
    public static View Sello(string nota, string? lectura, bool? cumple, double ancho = 112, double nota_tamano = 34)
    {
        var (fondo, tinta) = ColoresDeNota(cumple, hayNota: nota != "—");
        var pila = new VerticalStackLayout { Spacing = 2, HorizontalOptions = LayoutOptions.Fill, VerticalOptions = LayoutOptions.Center };
        pila.Add(new Label { Text = nota, FontFamily = Ds.FuenteMedia, FontSize = nota_tamano, TextColor = tinta, HorizontalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.NoWrap });
        if (!string.IsNullOrWhiteSpace(lectura))
            pila.Add(new Label { Text = lectura, FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = tinta, HorizontalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.WordWrap, MaxLines = 2 });
        return new Border
        {
            WidthRequest = ancho, BackgroundColor = fondo, Stroke = new SolidColorBrush(tinta.WithAlpha(0.28f)), StrokeThickness = 1.5,
            StrokeShape = new RoundRectangle { CornerRadius = 18 }, Padding = new Thickness(8, 10), Content = pila, VerticalOptions = LayoutOptions.Center,
        };
    }

    public static (Color Fondo, Color Tinta) ColoresDeNota(bool? cumple, bool hayNota = true) => !hayNota ? (ExamenUi.FondoNeutro, Ds.TintaSuave)
        : cumple switch { true => (Ds.ExitoSuave, ExamenUi.TintaExito), false => (Ds.PeligroSuave, Ds.Peligro), _ => (Ds.InfoSuave, ExamenUi.TintaInfo) };

    /// <summary>Una barra de avance: lo que se lleva de lo que hay. Sólo rectángulos redondeados; la fracción se acota a [0, 1].</summary>
    public static View Medidor(double fraccion, Color color, double alto = 10)
    {
        fraccion = double.IsNaN(fraccion) ? 0 : Math.Clamp(fraccion, 0, 1);
        var relleno = new BoxView { Color = color, CornerRadius = alto / 2, HeightRequest = alto };
        var pozo = new Grid { HeightRequest = alto, ColumnSpacing = 0 };
        pozo.Add(new BoxView { Color = Color.FromArgb("#E3E6EC"), CornerRadius = alto / 2, HeightRequest = alto }, 0, 0);
        if (fraccion > 0)
        {
            var avance = new Grid { ColumnDefinitions = [new ColumnDefinition(new GridLength(fraccion, GridUnitType.Star)), new ColumnDefinition(new GridLength(1 - fraccion, GridUnitType.Star))], HeightRequest = alto };
            avance.Add(relleno, 0, 0);
            pozo.Add(avance, 0, 0);
        }
        return pozo;
    }

    /// <summary>Un dato grande con su rótulo, dentro de un pozo: «5 de 8 / completadas».</summary>
    public static View Cifra(string valor, string rotulo, Color? color = null, double ancho = 0)
    {
        var pila = new VerticalStackLayout { Spacing = 0 };
        pila.Add(new Label { Text = valor, FontFamily = Ds.FuenteMedia, FontSize = 26, TextColor = color ?? Ds.Tinta, LineBreakMode = LineBreakMode.NoWrap });
        pila.Add(new Label { Text = rotulo, FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.WordWrap });
        var pozo = Hundido(pila, 16, new Thickness(16, 10));
        if (ancho > 0) pozo.WidthRequest = ancho;
        return pozo;
    }

    /// <summary>El rótulo en mayúsculas con espaciado, como el de una cabecera de formulario impreso: «INFORME DE CALIFICACIONES».</summary>
    public static Label Rotulo(string texto, double tamano = 12, Color? color = null) =>
        new() { Text = texto.ToUpperInvariant(), FontFamily = Ds.FuenteRegular, FontSize = tamano, TextColor = color ?? Ds.TintaSuave, CharacterSpacing = 2.6, LineBreakMode = LineBreakMode.WordWrap };

    /// <summary>Una regla fina, como las líneas de una libreta: separa las filas de la tabla de notas.</summary>
    public static View Linea() => new BoxView { HeightRequest = 1, Color = Regla, HorizontalOptions = LayoutOptions.Fill };
}

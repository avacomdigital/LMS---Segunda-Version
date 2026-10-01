using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Examen;

/// <summary>
/// Los tonos del examen en OPS. Ninguno es rojo: un examen no es un panel de vigilancia (Guion, paso 6). Lo que necesita al profesor se
/// dice con ámbar sereno y con palabras, nunca con una alarma. Cada tono lleva siempre su texto: el color nunca es el único aviso.
/// </summary>
internal enum Tono { Neutro, Info, Ambar, AmbarFuerte, Exito, Violeta, Gris }

/// <summary>Piezas visuales pequeñas que comparten las cuatro pantallas del examen. Sólo Border, Label y Button del kit: nada de Path ni Ellipse.</summary>
internal static class ExamenUi
{
    public static readonly Color TintaAmbar = Color.FromArgb("#806600");
    public static readonly Color TintaAmbarFuerte = Color.FromArgb("#5F4B00");
    public static readonly Color FondoAmbarFuerte = Color.FromArgb("#FDEFB0");
    public static readonly Color TintaInfo = Color.FromArgb("#02739E");
    public static readonly Color TintaExito = Color.FromArgb("#0B5D3B");
    public static readonly Color TintaVioleta = Color.FromArgb("#7A1560");
    public static readonly Color FondoNeutro = Color.FromArgb("#F0F0F2");
    public static readonly Color FondoGris = Color.FromArgb("#E7E7EA");

    public static (Color Fondo, Color Tinta) Colores(Tono tono) => tono switch
    {
        Tono.Info => (Ds.InfoSuave, TintaInfo),
        Tono.Ambar => (Ds.AlertaSuave, TintaAmbar),
        Tono.AmbarFuerte => (FondoAmbarFuerte, TintaAmbarFuerte),
        Tono.Exito => (Ds.ExitoSuave, TintaExito),
        Tono.Violeta => (Ds.VioletaSuave, TintaVioleta),
        Tono.Gris => (FondoGris, Ds.Tinta),
        _ => (FondoNeutro, Ds.TintaMedia),
    };

    public static Border Pildora(string texto, Tono tono, double tamano = 13)
    {
        var (fondo, tinta) = Colores(tono);
        var pildora = Ds.Pildora(texto, fondo, tinta, tamano);
        pildora.HorizontalOptions = LayoutOptions.Start;
        return pildora;
    }

    /// <summary>Una pastilla en una fila que se parte sola: lleva su margen para que el espacio entre ellas sea parejo.</summary>
    public static Border PildoraEnFila(string texto, Tono tono, double tamano = 13)
    {
        var p = Pildora(texto, tono, tamano);
        p.Margin = new Thickness(0, 0, 8, 8);
        return p;
    }

    /// <summary>Un aviso que informa sin alarmar (CMP-005): ámbar para lo que pide atención, verde suave para lo que salió bien, azul suave para lo que sólo se cuenta.</summary>
    public static Border Aviso(string titulo, string? detalle, Tono tono = Tono.Ambar)
    {
        var (fondo, tinta) = Colores(tono);
        return Ds.Alerta_(titulo, detalle, fondo, tinta);
    }

    /// <summary>Un total grande con su rótulo (las cuentas del panel). Con cero se atenúa, sin esconderse: la tira conserva su forma.</summary>
    public static View Total(int valor, string rotulo, Color color)
    {
        var pila = new VerticalStackLayout { Spacing = 0, HorizontalOptions = LayoutOptions.Start, MinimumWidthRequest = 84 };
        pila.Add(new Label { Text = valor.ToString(System.Globalization.CultureInfo.InvariantCulture), FontFamily = Ds.FuenteMedia, FontSize = 26, TextColor = color });
        pila.Add(Ds.Secundario(rotulo, 12));
        pila.Opacity = valor == 0 ? 0.55 : 1;
        return pila;
    }

    /// <summary>Un renglón «rótulo · valor» para los resúmenes: rótulo a la izquierda en tinta suave, valor a la derecha.</summary>
    public static View Dato(string rotulo, string valor, double ancho = 190)
    {
        var g = new Grid { ColumnDefinitions = [new ColumnDefinition(new GridLength(ancho)), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 14 };
        g.Add(Ds.Secundario(rotulo, 15), 0, 0);
        g.Add(new Label { Text = valor, FontFamily = Ds.FuenteRegular, FontSize = 16, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap }, 1, 0);
        return g;
    }

    /// <summary>Una tarjeta blanca de contenido (lo que se lee), con el relleno de las pantallas del examen.</summary>
    public static Border Tarjeta(View contenido, Color? fondo = null) =>
        Ds.Tarjeta(contenido, Ds.RadioTarjeta, new Thickness(26, 20), fondo ?? Colors.White);

    /// <summary>Un título de sección dentro de una tarjeta.</summary>
    public static Label Seccion(string texto) => Ds.Titulo(texto, 20);

    /// <summary>
    /// Un botón de 56 px del kit, listo para colocar. Los de relieve (Primary, Secondary, Destructive) van en su cápsula; el Quiet va plano, sin cápsula ni borde:
    /// es sólo texto tocable. <paramref name="id"/> es el AutomationId; <paramref name="margen"/> deja 10 px a la derecha y debajo para las filas que se parten.
    /// </summary>
    public static (Button Boton, View Vista) Accion(string texto, Ds.Rango rango, Func<Task> alPulsar, double? ancho = null, string? id = null, double alto = 56, bool margen = true)
    {
        var b = Ds.Boton(texto, rango, async (_, _) => await alPulsar(), alto, ancho);
        b.FontSize = 16;
        if (id is not null) b.AutomationId = id;
        View vista = rango == Ds.Rango.Quiet ? b : Ds.Capsula(b);
        vista.Margin = margen ? new Thickness(0, 0, 10, 10) : new Thickness(0);
        return (b, vista);
    }

    /// <summary>Una franja de acciones: se parte sola cuando no caben.</summary>
    public static FlexLayout Fila() => new()
    {
        Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap, Direction = Microsoft.Maui.Layouts.FlexDirection.Row,
        JustifyContent = Microsoft.Maui.Layouts.FlexJustify.Start, AlignItems = Microsoft.Maui.Layouts.FlexAlignItems.Start,
    };

    /// <summary>Un panel de fondo suave con borde de 1 px, para una zona dentro de una tarjeta (la franja de acciones de una fila).</summary>
    public static Border Zona(View contenido, Color fondo) => new()
    {
        BackgroundColor = fondo, StrokeThickness = 0, Padding = new Thickness(16, 12),
        StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = contenido,
    };
}

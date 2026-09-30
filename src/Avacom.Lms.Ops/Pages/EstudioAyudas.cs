using System.Globalization;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Textos del modo de estudio en OPS (MOD-008): fechas en español, estados con nombre de persona y mensajes de error sin jerga.
/// La hora que ve la profesora es la de su equipo; la que viaja al nodo es un instante absoluto (ms), así que nada depende del huso.
/// </summary>
internal static class EstudioTexto
{
    private static readonly CultureInfo Es = CultureInfo.GetCultureInfo("es-CO");

    public static DateTime Local(long ms) => DateTimeOffset.FromUnixTimeMilliseconds(ms).ToLocalTime().DateTime;

    public static long AMs(DateTime local) => new DateTimeOffset(DateTime.SpecifyKind(local, DateTimeKind.Local)).ToUnixTimeMilliseconds();

    public static string Hora(DateTime f) => f.ToString("h:mm tt", Es);

    /// <summary>«vie 3 oct · 11:59 p. m.»; con el año sólo si no es el actual.</summary>
    public static string Momento(long ms)
    {
        var f = Local(ms);
        var fecha = f.ToString("ddd d MMM", Es).Replace(".", string.Empty);
        if (f.Year != DateTime.Now.Year) fecha += $" {f.Year}";
        return $"{fecha} · {Hora(f)}";
    }

    /// <summary>«viernes 3 de octubre, 11:59 p. m.»</summary>
    public static string FechaLarga(DateTime f) => $"{f.ToString("dddd d 'de' MMMM", Es)}, {Hora(f)}";

    /// <summary>Cuánto hace de algo, en palabras: «ahora mismo», «hace 12 min», «hace 3 h», o la fecha si ya pasó más de un día.</summary>
    public static string Relativo(long? ms)
    {
        if (ms is null or <= 0) return "todavía nada";
        var dif = RelojNodo.AhoraMs - ms.Value;
        if (dif < 60_000) return "ahora mismo";
        if (dif < 3_600_000) return $"hace {dif / 60_000} min";
        if (dif < 86_400_000) return $"hace {dif / 3_600_000} h";
        return Momento(ms.Value);
    }

    public static string Entrega(long? fechaLimite) => fechaLimite is null ? "Sin fecha límite" : $"Entrega: {Momento(fechaLimite.Value)}";

    public static string PlazoLegible(string? plazo) => plazo == "endurecido"
        ? "Estricto: cierra al vencer"
        : "Flexible: se acepta tarde y se marca";

    public static string PaqueteLegible(string? estado) => estado switch
    {
        "solicitado" => "Descarga pedida",
        "descargandose" => "Descargando",
        "disponible" => "En el aparato",
        "vencido" => "Vencido",
        "denegado" => "No se descarga aquí",
        _ => "Sin descargar",
    };

    public static string Plural(int n, string singular, string plural) => n == 1 ? $"1 {singular}" : $"{n} {plural}";

    /// <summary>El estado de una tarea con la paleta del modo de estudio (la misma de Student): pendiente, en curso, completada, vencida.</summary>
    public static (string Texto, Color Fondo, Color Tinta) Estado(string? estado, bool vencida) =>
        vencida && estado != "completada" ? ("VENCIDA", Color.FromRgba(229, 38, 43, 26), Color.FromArgb("#C1191D"))
        : estado == "completada" ? ("COMPLETADA", Color.FromArgb("#E5F6ED"), Color.FromArgb("#017A48"))
        : estado == "en_curso" ? ("EN CURSO", Color.FromArgb("#E5F5FB"), Color.FromArgb("#02739E"))
        : ("PENDIENTE", Color.FromArgb("#FFF7D6"), Color.FromArgb("#806600"));

    /// <summary>La frase que sustituye al código técnico del nodo. Lo que el nodo cuenta de más (detalle y sugerencia) se conserva.</summary>
    public static string Error(ErrorAula? e, string? motivo)
    {
        if (e is { Estado: 0 }) return "No hay conexión con el aula. Revisa que el nodo esté encendido y vuelve a intentarlo.";
        var detalle = string.Join(" ", new[] { string.IsNullOrWhiteSpace(e?.Detalle) ? motivo : e!.Detalle, e?.Sugerencia }.Where(x => !string.IsNullOrWhiteSpace(x)));
        return e?.Codigo switch
        {
            "no_instalado" => "El nodo todavía no tiene una organización instalada; sin ella no hay grupos ni alumnos a quienes asignar.",
            "fuente_no_disponible" => "AVACOM Contenido no responde. Una lección no se asigna a ciegas: vuelve a intentarlo cuando la biblioteca esté conectada.",
            "sin_permiso" or "no_es_el_titular" => "Sólo el profesor titular del grupo o la administración puede hacerlo.",
            "dispositivo_ya_asignado" => "Esta tableta ya es de otro alumno. Primero hay que devolverla al fondo compartido.",
            "paquete_sin_integrar" => "El alumno todavía tiene lecciones descargadas o trabajo sin enviar en esta tableta. Que abra el modo de estudio con conexión para que se envíe y se limpie, y vuelve a intentarlo.",
            _ => detalle.Length > 0 ? detalle : "Sin detalle.",
        };
    }
}

/// <summary>Piezas visuales pequeñas que comparten las tres vistas de «Modo de estudio» en OPS. Todo se toca; nada se escribe.</summary>
internal static class EstudioUi
{
    public static readonly Color TintaPeligro = Color.FromArgb("#8A1C1F");
    public static readonly Color PistaBarra = Color.FromArgb("#E7E7EA");

    /// <summary>
    /// Una opción de las que se eligen con el dedo: 52 px, cápsula, con ✓ cuando está elegida (no sólo el color). Es un botón de verdad, así
    /// que el lector de pantalla y la automatización la ven y la activan.
    /// </summary>
    public static Button Chip(string texto, bool activo, Func<Task> alTocar, string? id = null, double alto = 52)
    {
        var b = new Button
        {
            Text = activo ? $"✓  {texto}" : texto,
            HeightRequest = alto,
            MinimumHeightRequest = alto,
            CornerRadius = (int)(alto / 2),
            FontFamily = Ds.FuenteMedia,
            FontSize = 16,
            Padding = new Thickness(22, 0),
            BorderWidth = 1,
            BackgroundColor = activo ? Ds.Tinta : Colors.White,
            TextColor = activo ? Colors.White : Ds.TintaMedia,
            BorderColor = activo ? Ds.Tinta : Color.FromArgb("#29000000"),
            Margin = new Thickness(0, 0, 10, 10),
        };
        if (id is not null) b.AutomationId = id;
        Ds.Hundir(b);
        b.Clicked += async (_, _) => await alTocar();
        return b;
    }

    /// <summary>Filas que se parten solas cuando no caben (chips, alumnos).</summary>
    public static FlexLayout Envolver() => new() { Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap, Direction = Microsoft.Maui.Layouts.FlexDirection.Row, JustifyContent = Microsoft.Maui.Layouts.FlexJustify.Start, AlignItems = Microsoft.Maui.Layouts.FlexAlignItems.Start };

    /// <summary>Barra de avance: dos columnas proporcionales, sin medir nada (no depende del ancho disponible).</summary>
    public static View Barra(double fraccion, Color? color = null, double alto = 10)
    {
        var f = double.IsNaN(fraccion) ? 0 : Math.Clamp(fraccion, 0, 1);
        var relleno = new Border { BackgroundColor = color ?? Ds.Exito, StrokeThickness = 0, HeightRequest = alto };
        var pista = new Grid { ColumnDefinitions = [new ColumnDefinition(new GridLength(f, GridUnitType.Star)), new ColumnDefinition(new GridLength(1 - f, GridUnitType.Star))], ColumnSpacing = 0 };
        pista.Add(relleno, 0, 0);
        return new Border
        {
            BackgroundColor = PistaBarra, StrokeThickness = 0, HeightRequest = alto, Padding = 0,
            StrokeShape = new RoundRectangle { CornerRadius = alto / 2 }, Content = pista, VerticalOptions = LayoutOptions.Center,
        };
    }

    /// <summary>Un total grande con su rótulo, para el resumen de una asignación.</summary>
    public static View Total(int valor, string rotulo, Color color)
    {
        var pila = new VerticalStackLayout { Spacing = 2, HorizontalOptions = LayoutOptions.Start };
        pila.Add(new Label { Text = valor.ToString(CultureInfo.InvariantCulture), FontFamily = Ds.FuenteMedia, FontSize = 34, TextColor = color });
        pila.Add(Ds.Secundario(rotulo, 14));
        return pila;
    }

    /// <summary>
    /// Una tarjeta que se elige con el dedo. El contenido se pinta debajo y un botón transparente lo cubre: el toque es un botón de verdad
    /// (lo ven el lector de pantalla y la automatización) y la tarjeta se hunde al pulsarla como los botones del kit.
    /// </summary>
    public static Border TarjetaElegible(View contenido, bool elegida, Func<Task> alTocar, string descripcion, string? id = null, bool activa = true)
    {
        contenido.InputTransparent = true;
        var cuerpo = new Grid();
        cuerpo.Add(contenido);
        var boton = new Button { BackgroundColor = Colors.Transparent, BorderWidth = 0, Text = string.Empty, Opacity = 1, Padding = 0, IsEnabled = activa };
        SemanticProperties.SetDescription(boton, descripcion);
        if (id is not null) boton.AutomationId = id;
        cuerpo.Add(boton);
        var tarjeta = new Border
        {
            BackgroundColor = activa ? Colors.White : Color.FromArgb("#F7F7F8"),
            Stroke = new SolidColorBrush(elegida ? Ds.Tinta : Ds.Filo),
            StrokeThickness = elegida ? 2.5 : 1,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioTarjeta },
            Padding = new Thickness(22, 16),
            Content = cuerpo,
            Shadow = Ds.SombraTarjeta(),
            Opacity = activa ? 1 : 0.6,
        };
        boton.Pressed += async (_, _) => await tarjeta.ScaleToAsync(0.985, 80, Easing.CubicOut);
        boton.Released += async (_, _) => await tarjeta.ScaleToAsync(1, 130, Easing.CubicOut);
        boton.Clicked += async (_, _) => await alTocar();
        return tarjeta;
    }

    /// <summary>Un botón de acción de 56 px (cápsula con relieve si no es «Quiet»).</summary>
    public static (Button Boton, View Vista) Accion(string texto, Ds.Rango rango, Func<Task> alPulsar, double? ancho = null, string? id = null)
    {
        var b = Ds.Boton(texto, rango, async (_, _) => await alPulsar(), 56, ancho);
        b.FontSize = 16;
        if (id is not null) b.AutomationId = id;
        return (b, Ds.Capsula(b));
    }

    public static Label Eyebrow(string texto) => new()
    {
        Text = texto, FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = Ds.TintaSuave, CharacterSpacing = 2.5,
    };

    public static Border Aviso(string titulo, string? detalle, Color fondo, Color tinta) => Ds.Alerta_(titulo, detalle, fondo, tinta);
}

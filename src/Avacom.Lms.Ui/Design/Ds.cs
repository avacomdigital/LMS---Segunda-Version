using System.Runtime.CompilerServices;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Design;

/// <summary>
/// Tokens y fábricas del Avacom LMS UI Kit v2 para las pantallas del aula (MOD-007).
///
/// Tres materiales: <b>content surface</b> (blanco 96 %, sin desenfoque, sombra doble
/// suave) para todo lo que se lee; <b>glass chrome</b> (blanco 70 %) sólo para barras y
/// navegación; <b>dark glass</b> (casi negro 82 %) para la barra de controles multimedia.
/// MAUI no ofrece desenfoque de fondo en WinUI/Android sin código de plataforma, así que el
/// vidrio se aproxima con la transparencia y un filo de 1 px; los párrafos nunca van sobre él.
///
/// Tipografía: Inter en cuatro pesos (300/400/500/600), ver <see cref="FuenteLigera"/>. Sin negrita sintética.
/// Botones: 64 px de alto, radio 16, etiqueta 18/500. Un solo Primary por pantalla.
/// Neumorfismo: cuerpo con degradado vertical (luz arriba), bisel de 1,5 px con luz arriba-izquierda y sombra
/// exterior teñida del color del control (<see cref="Capsula"/>); el control se hunde (escala + sombra recogida) al pulsar.
/// </summary>
public static class Ds
{
    // ------------------------------------------------------------------ color
    public static readonly Color Rojo = Color.FromArgb("#E5262B");        // marca · Primary · Audio
    public static readonly Color Tinta = Color.FromArgb("#18181B");
    public static readonly Color TintaSuave = Color.FromArgb("#52525B");
    public static readonly Color TintaMedia = Color.FromArgb("#3F3F46");
    public static readonly Color Lienzo = Color.FromArgb("#F1F1F1");
    public static readonly Color Filo = Color.FromArgb("#17000000");       // hairline 9 % negro
    public static readonly Color Exito = Color.FromArgb("#019D60");
    public static readonly Color Info = Color.FromArgb("#01A4E1");
    public static readonly Color Alerta = Color.FromArgb("#F3C701");
    public static readonly Color Peligro = Color.FromArgb("#C82230");
    public static readonly Color ExitoSuave = Color.FromArgb("#E6F5EE");
    public static readonly Color InfoSuave = Color.FromArgb("#E6F6FC");
    public static readonly Color AlertaSuave = Color.FromArgb("#FEF9E6");
    public static readonly Color PeligroSuave = Color.FromArgb("#FDECEC");
    public static readonly Color VioletaSuave = Color.FromArgb("#F5E8F1");

    /// <summary>Categorías de contenido del cubo del logo. Identifican; nunca rellenan un CTA.</summary>
    public static readonly Color CatVideo = Color.FromArgb("#01A4E1");     // cyan / azul
    public static readonly Color CatClaseEnVivo = Color.FromArgb("#A81D81"); // magenta / púrpura
    public static readonly Color CatQuiz = Color.FromArgb("#019D60");      // verde
    public static readonly Color CatLectura = Color.FromArgb("#F3C701");   // amarillo
    public static readonly Color CatAudio = Color.FromArgb("#E5262B");     // rojo

    public static readonly Color SuperficieContenido = Color.FromArgb("#F5FFFFFF"); // blanco 96 %
    public static readonly Color GlassChrome = Color.FromArgb("#B3FFFFFF");         // blanco 70 %
    public static readonly Color GlassOscuro = Color.FromArgb("#D1141417");          // casi negro 82 %

    // ------------------------------------------------------------- tipografía
    /// <summary>
    /// Inter (SIL OFL 1.1, v4.1) en cuatro pesos estáticos que cada app registra en <c>ConfigureFonts</c> con estos
    /// alias: 300 para lo secundario a partir de 15 px, 400 para el cuerpo, 500 para títulos, botones y píldoras, y
    /// 600 sólo para los tramos <c>**negrita**</c> del manifiesto. Nada del kit usa <see cref="FontAttributes.Bold"/>:
    /// la jerarquía la dan el tamaño y el peso real de la fuente, no una negrita sintetizada.
    /// </summary>
    public const string FuenteLigera = "InterLight", FuenteRegular = "InterRegular", FuenteMedia = "InterMedium", FuenteSemi = "InterSemiBold";

    /// <summary>Light sólo cuando el texto es lo bastante grande para que el trazo fino siga legible en el aula.</summary>
    public static string FuenteSecundaria(double tamano) => tamano >= 15 ? FuenteLigera : FuenteRegular;

    // ----------------------------------------------------------------- radios
    public const int RadioControl = 12, RadioInterno = 14, RadioBoton = 16, RadioTarjeta = 20, RadioBarra = 22, RadioGrande = 24, RadioPildora = 999;

    // ------------------------------------------------------------- categorías
    /// <summary>Color de categoría de un objeto o bloque, por su <c>componente</c>.</summary>
    public static Color Categoria(string? componente) => componente switch
    {
        "presentacion" => CatClaseEnVivo,
        "lectura" or "texto" or "titulo" or "lista" or "pdf" => CatLectura,
        "laboratorio_web" or "webview" or "video" or "imagen" => CatVideo,
        "actividad" or "opcion_multiple" or "verdadero_falso" or "completar" or "relacionar" or "ordenar" or "abierta" => CatQuiz,
        "audio" => CatAudio,
        "examen" => TintaSuave,
        _ => TintaSuave,
    };

    /// <summary>La categoría amarilla necesita tinta oscura encima; las demás, blanca.</summary>
    public static Color TintaSobre(Color fondo) => fondo == CatLectura || fondo == Alerta ? Tinta : Colors.White;

    public static string Icono(string? componente) => componente switch
    {
        "presentacion" => "▣",
        "lectura" or "pdf" => "▤",
        "laboratorio_web" or "webview" => "⌗",
        "actividad" => "✎",
        "examen" => "✓",
        "video" => "▶",
        "audio" => "♪",
        "imagen" => "▧",
        _ => "•",
    };

    // ---------------------------------------------------------------- sombras
    public static Shadow SombraTarjeta() => new() { Brush = new SolidColorBrush(Tinta), Offset = new Point(0, 10), Radius = 26, Opacity = 0.07f };
    public static Shadow SombraElevada() => new() { Brush = new SolidColorBrush(Tinta), Offset = new Point(6, 8), Radius = 14, Opacity = 0.14f };
    public static Shadow SombraLuz() => new() { Brush = new SolidColorBrush(Colors.White), Offset = new Point(-5, -5), Radius = 12, Opacity = 0.9f };

    // ---------------------------------------------------------------- relieve
    /// <summary>Blanco al 20 % sobre dark glass: el cuerpo de un mando en reposo en la barra de controles.</summary>
    public static readonly Color Fantasma = Color.FromArgb("#33FFFFFF");

    /// <summary>
    /// Degradado vertical del cuerpo de un control en relieve: algo más claro arriba, donde da la luz, y más oscuro
    /// abajo. Un color translúcido (los mandos sobre dark glass) gradúa su alfa en vez de su luminosidad.
    /// </summary>
    public static LinearGradientBrush Degradado(Color fondo)
    {
        Color arriba, abajo;
        if (fondo.Alpha < 0.999f)
        {
            arriba = fondo.WithAlpha(Math.Min(1f, fondo.Alpha * 1.45f));
            abajo = fondo.WithAlpha(fondo.Alpha * 0.6f);
        }
        else
        {
            arriba = fondo.AddLuminosity(0.05f);
            abajo = fondo.AddLuminosity(-0.07f);
        }
        return new LinearGradientBrush(
            new GradientStopCollection { new GradientStop(arriba, 0f), new GradientStop(fondo, 0.55f), new GradientStop(abajo, 1f) },
            new Point(0, 0), new Point(0, 1));
    }

    /// <summary>Bisel de un control en relieve: luz arriba-izquierda, sombra abajo-derecha. Es el mismo trazo que el estilo <c>NeuButtonShell</c> de OPS.</summary>
    public static LinearGradientBrush Bisel() => new(
        new GradientStopCollection { new GradientStop(Color.FromArgb("#B3FFFFFF"), 0f), new GradientStop(Color.FromArgb("#26FFFFFF"), 0.45f), new GradientStop(Color.FromArgb("#66000000"), 1f) },
        new Point(0, 0), new Point(1, 1));

    /// <summary>Sombra exterior de un control en relieve: teñida del color del control si es de color; gris si es blanco o translúcido.</summary>
    public static Shadow SombraDe(Color? tono)
    {
        var tenida = tono is not null && tono.Alpha >= 0.999f && tono.GetLuminosity() < 0.85f;
        return new Shadow { Brush = new SolidColorBrush(tenida ? tono! : Tinta), Offset = new Point(0, 8), Radius = 18, Opacity = tenida ? 0.42f : 0.14f };
    }

    // ------------------------------------------------------------- superficies
    /// <summary>Content surface: blanco 96 %, filo de 9 % y sombra doble suave. Aquí va todo lo que se lee.</summary>
    public static Border Tarjeta(View contenido, int radio = RadioTarjeta, Thickness? relleno = null, Color? fondo = null)
    {
        var borde = new Border
        {
            BackgroundColor = fondo ?? SuperficieContenido,
            Stroke = new SolidColorBrush(Filo),
            StrokeThickness = 1,
            StrokeShape = new RoundRectangle { CornerRadius = radio },
            Padding = relleno ?? new Thickness(20),
            Content = contenido,
            Shadow = SombraTarjeta(),
        };
        return borde;
    }

    /// <summary>Glass chrome: sólo barras y navegación, etiquetas cortas.</summary>
    public static Border BarraClara(View contenido, Thickness? relleno = null) => new()
    {
        BackgroundColor = GlassChrome,
        Stroke = new SolidColorBrush(Filo),
        StrokeThickness = 1,
        StrokeShape = new RoundRectangle { CornerRadius = RadioBarra },
        Padding = relleno ?? new Thickness(18, 10),
        Content = contenido,
        Shadow = new Shadow { Brush = new SolidColorBrush(Tinta), Offset = new Point(0, 4), Radius = 16, Opacity = 0.08f },
    };

    /// <summary>Dark glass: la barra de controles de la clase y los mandos multimedia.</summary>
    public static Border BarraOscura(View contenido, Thickness? relleno = null) => new()
    {
        BackgroundColor = GlassOscuro,
        StrokeThickness = 0,
        StrokeShape = new RoundRectangle { CornerRadius = RadioBarra },
        Padding = relleno ?? new Thickness(16, 10),
        Content = contenido,
        Shadow = new Shadow { Brush = new SolidColorBrush(Tinta), Offset = new Point(0, 8), Radius = 20, Opacity = 0.22f },
    };

    // ---------------------------------------------------------------- botones
    public enum Rango { Primary, Secondary, Quiet, Destructive }

    /// <summary>Botón del kit: 64 px, radio 16, 18/500, cuerpo con degradado y sombra teñida; se hunde al pulsar. El bisel lo pone <see cref="Capsula"/>.</summary>
    public static Button Boton(string texto, Rango rango, EventHandler? alPulsar = null, double alto = 64, double? ancho = null)
    {
        var boton = new Button
        {
            Text = texto,
            HeightRequest = alto,
            MinimumHeightRequest = alto,
            CornerRadius = RadioBoton,
            FontSize = alto >= 64 ? 18 : 16,
            FontFamily = FuenteMedia,
            Padding = new Thickness(22, 0),
            BorderWidth = 0,
        };
        if (ancho is not null) boton.WidthRequest = ancho.Value;
        switch (rango)
        {
            case Rango.Primary:
                PintarRelieve(boton, Rojo, Colors.White); break;
            case Rango.Secondary:
                PintarRelieve(boton, Colors.White, Tinta); break;
            case Rango.Quiet:
                boton.BackgroundColor = Colors.Transparent; boton.TextColor = Color.FromArgb("#27272A"); break;
            case Rango.Destructive:
                PintarRelieve(boton, Peligro, Colors.White); break;
        }
        Hundir(boton);
        if (alPulsar is not null) boton.Clicked += alPulsar;
        return boton;
    }

    /// <summary>Viste un botón con el relieve del kit: degradado vertical del color dado y sombra exterior teñida (en la cápsula, si ya la tiene).</summary>
    public static void PintarRelieve(Button boton, Color fondo, Color texto)
    {
        boton.Background = Degradado(fondo);
        boton.TextColor = texto;
        CuerpoDe(boton).Shadow = SombraDe(fondo);
    }

    private static readonly ConditionalWeakTable<Button, Border> Capsulas = new();

    /// <summary>
    /// Cápsula neumórfica de un botón del kit: el bisel (<see cref="Bisel"/>) alrededor y la sombra teñida por fuera.
    /// Un <see cref="Border"/> recorta su contenido a la forma, así que la sombra tiene que vivir en la cápsula y no
    /// en el botón; margen, alineación y hundimiento pasan también a la cápsula, mientras texto, tamaño, color e
    /// <c>IsEnabled</c> siguen en el botón. Se coloca la cápsula donde iría el botón. Un botón Quiet no lleva
    /// cápsula: se devuelve tal cual.
    /// </summary>
    public static View Capsula(Button boton)
    {
        if (Capsulas.TryGetValue(boton, out var existente)) return existente;
        if (boton.Background is null) return boton;
        var capsula = new Border
        {
            BackgroundColor = Colors.Transparent,
            Stroke = Bisel(),
            StrokeThickness = 1.5,
            StrokeShape = new RoundRectangle { CornerRadius = boton.CornerRadius },
            Padding = 0,
            Content = boton,
            Shadow = boton.Shadow,
            Margin = boton.Margin,
            HorizontalOptions = boton.HorizontalOptions,
            VerticalOptions = boton.VerticalOptions,
        };
        boton.Shadow = null!;
        boton.Margin = 0;
        Capsulas.Add(boton, capsula);
        return capsula;
    }

    /// <summary>La cápsula del botón si la tiene; si no, el propio botón. Es lo que lleva la sombra y lo que se hunde.</summary>
    private static VisualElement CuerpoDe(Button boton) => Capsulas.TryGetValue(boton, out var capsula) ? capsula : boton;

    /// <summary>Habilita o atenúa un botón del kit, cápsula incluida, de una sola vez.</summary>
    public static void Habilitar(Button boton, bool activo, double atenuado = 0.5)
    {
        boton.IsEnabled = activo;
        var cuerpo = CuerpoDe(boton);
        cuerpo.Opacity = activo ? 1 : atenuado;
        if (!ReferenceEquals(cuerpo, boton)) boton.Opacity = 1;
    }

    /// <summary>El botón no «baja»: se hunde en la superficie (escala 0,96 y la sombra se recoge) en menos de 120 ms. Con cápsula, se hunde la cápsula.</summary>
    public static void Hundir(Button boton)
    {
        Shadow? reposo = null;
        boton.Pressed += async (_, _) =>
        {
            var cuerpo = CuerpoDe(boton);
            reposo = cuerpo.Shadow;
            if (reposo is not null) cuerpo.Shadow = new Shadow { Brush = reposo.Brush, Offset = new Point(0, 2), Radius = 6, Opacity = reposo.Opacity * 0.6f };
            await cuerpo.ScaleToAsync(0.96, 90, Easing.CubicOut);
        };
        boton.Released += async (_, _) =>
        {
            var cuerpo = CuerpoDe(boton);
            await cuerpo.ScaleToAsync(1, 140, Easing.CubicOut);
            if (reposo is not null) cuerpo.Shadow = reposo;
        };
    }

    /// <summary>Interruptor tocable para la barra de controles (dark glass): dos estados con color semántico. 64 px por defecto; en barras densas se puede pedir más bajo.</summary>
    public static Button Interruptor(string texto, bool activo, Color activoColor, EventHandler alPulsar, double alto = 64)
    {
        var b = new Button
        {
            Text = texto,
            HeightRequest = alto,
            MinimumHeightRequest = alto,
            CornerRadius = RadioBoton,
            FontSize = alto >= 64 ? 18 : 15,
            FontFamily = FuenteMedia,
            Padding = new Thickness(alto >= 64 ? 18 : 14, 0),
            BorderWidth = 0,
        };
        PintarInterruptor(b, activo, activoColor);
        Hundir(b);
        b.Clicked += alPulsar;
        return b;
    }

    /// <summary>Activo: degradado del color semántico y sombra teñida. En reposo: blanco al 20 % sobre el dark glass.</summary>
    public static void PintarInterruptor(Button b, bool activo, Color activoColor) =>
        PintarRelieve(b, activo ? activoColor : Fantasma, activo ? TintaSobre(activoColor) : Colors.White);

    /// <summary>
    /// Botón redondo, sólo glifo, para una acción secundaria de la barra de controles que no necesita etiqueta
    /// (bloquear pantallas, aviso). Mismo relieve y hundimiento que <see cref="Interruptor"/>, sin texto: ahorra
    /// espacio en la barra dark glass cuando varias acciones compiten por sitio. Añade su propia descripción
    /// semántica porque, a diferencia de <see cref="Boton"/>, no hay etiqueta visible que la sustituya.
    /// </summary>
    public static Button BotonIcono(string glifo, bool activo, Color activoColor, EventHandler alPulsar, string descripcion, double lado = 44)
    {
        var b = new Button
        {
            Text = glifo,
            WidthRequest = lado,
            HeightRequest = lado,
            MinimumWidthRequest = lado,
            MinimumHeightRequest = lado,
            CornerRadius = (int)(lado / 2),
            FontSize = lado * 0.42,
            FontFamily = FuenteMedia,
            Padding = 0,
            BorderWidth = 0,
        };
        SemanticProperties.SetDescription(b, descripcion);
        PintarInterruptor(b, activo, activoColor);
        Hundir(b);
        b.Clicked += alPulsar;
        return b;
    }

    // ----------------------------------------------------------------- textos
    public static Label Titulo(string texto, double tamano = 26, Color? color = null) => new()
    {
        Text = texto, FontSize = tamano, FontFamily = FuenteMedia, TextColor = color ?? Tinta, LineBreakMode = LineBreakMode.WordWrap,
    };

    public static Label Cuerpo(string texto, double tamano = 18, Color? color = null) => new()
    {
        Text = texto, FontSize = tamano, FontFamily = FuenteRegular, TextColor = color ?? Tinta, LineBreakMode = LineBreakMode.WordWrap,
    };

    public static Label Secundario(string texto, double tamano = 16) => new()
    {
        Text = texto, FontSize = tamano, FontFamily = FuenteSecundaria(tamano), TextColor = TintaSuave, LineBreakMode = LineBreakMode.WordWrap,
    };

    /// <summary>
    /// Los tramos del manifiesto → FormattedString. Sin Markdown en la tableta: `**negrita**` es el peso 600,
    /// `*cursiva*` y la matemática en línea (`$…$`, ya legible) van en itálica; no hay Inter Italic empaquetada,
    /// así que es la única itálica sintética del kit (la misma del bloque `formula`).
    /// </summary>
    public static FormattedString Formateado(IReadOnlyList<Tramo>? tramos, string? plano)
    {
        var fs = new FormattedString();
        if (tramos is null || tramos.Count == 0)
        {
            fs.Spans.Add(new Span { Text = plano ?? string.Empty });
            return fs;
        }
        foreach (var t in tramos)
            fs.Spans.Add(new Span
            {
                Text = t.Texto,
                FontFamily = t.Negrita ? FuenteSemi : FuenteRegular,
                FontAttributes = t.Cursiva || t.Matematica ? FontAttributes.Italic : FontAttributes.None,
            });
        return fs;
    }

    public static Label ConTramos(IReadOnlyList<Tramo>? tramos, string? plano, double tamano = 18, Color? color = null) => new()
    {
        FormattedText = Formateado(tramos, plano), FontSize = tamano, FontFamily = FuenteRegular, TextColor = color ?? Tinta, LineBreakMode = LineBreakMode.WordWrap,
    };

    // ---------------------------------------------------------------- píldoras
    /// <summary>Badge de categoría o estado: identifica, no llama a la acción.</summary>
    public static Border Pildora(string texto, Color fondo, Color? tinta = null, double tamano = 13) => new()
    {
        BackgroundColor = fondo,
        StrokeThickness = 0,
        StrokeShape = new RoundRectangle { CornerRadius = RadioPildora },
        Padding = new Thickness(12, 6),
        Content = new Label { Text = texto, FontSize = tamano, FontFamily = FuenteMedia, TextColor = tinta ?? TintaSobre(fondo), LineBreakMode = LineBreakMode.WordWrap },
        VerticalOptions = LayoutOptions.Center,
    };

    /// <summary>Punto de estado de conexión (CMP-001): conectado, reconectando o sin señal. Sin porcentajes.</summary>
    public static Border PuntoEstado(string texto, Color color) => Pildora($"●  {texto}", Color.FromArgb("#1AFFFFFF"), color, 13);

    /// <summary>Icono de categoría en un cuadrado redondeado (26–34 px).</summary>
    public static Border IconoCategoria(string? componente, double lado = 44)
    {
        var color = Categoria(componente);
        return new Border
        {
            BackgroundColor = color,
            StrokeThickness = 0,
            WidthRequest = lado, HeightRequest = lado,
            StrokeShape = new RoundRectangle { CornerRadius = RadioControl },
            Content = new Label
            {
                Text = Icono(componente), FontSize = lado * 0.5, TextColor = TintaSobre(color),
                HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center,
            },
            VerticalOptions = LayoutOptions.Center,
        };
    }

    /// <summary>Alerta no bloqueante (CMP-005): informa, no interrumpe.</summary>
    public static Border Alerta_(string titulo, string? detalle, Color fondo, Color tinta)
    {
        var pila = new VerticalStackLayout { Spacing = 4 };
        pila.Add(new Label { Text = titulo, FontFamily = FuenteMedia, FontSize = 17, TextColor = tinta, LineBreakMode = LineBreakMode.WordWrap });
        if (!string.IsNullOrWhiteSpace(detalle))
            pila.Add(new Label { Text = detalle, FontSize = 15, TextColor = tinta, LineBreakMode = LineBreakMode.WordWrap });
        return new Border
        {
            BackgroundColor = fondo, StrokeThickness = 0, Padding = new Thickness(18, 14),
            StrokeShape = new RoundRectangle { CornerRadius = RadioInterno }, Content = pila,
        };
    }

    public static Border Separador() => new() { HeightRequest = 1, BackgroundColor = Filo, StrokeThickness = 0 };

    public static void Tocable(View vista, Func<Task> accion)
    {
        var tap = new TapGestureRecognizer();
        tap.Tapped += async (_, _) =>
        {
            // Un toque corre en un `async void`: una excepción que se escapara de la acción cerraba la aplicación entera (en plena clase). Se anota
            // como ERROR —con la pantalla, el control y el lugar del código— y la app sigue.
            try
            {
                await vista.ScaleToAsync(0.97, 70, Easing.CubicOut);
                await vista.ScaleToAsync(1, 110, Easing.CubicOut);
                await accion();
            }
            catch (Exception ex)
            {
                var donde = RegistroDeFallos.DondeFallo(ex);
                var control = string.IsNullOrWhiteSpace(vista.AutomationId) ? vista.GetType().Name : vista.AutomationId;
                RegistroDeFallos.Anotar(RegistroLocal.App, $"Toque en {control}", ex, "ui.toque.fallo",
                    $"Falló la acción de un toque en la pantalla (control «{control}»); la aplicación sigue abierta. {RegistroDeFallos.Resumen(ex)}{(donde is null ? string.Empty : $" · en {donde}")}",
                    new { control, tipo_excepcion = ex.GetType().Name, codigo = RegistroDeFallos.CodigoDe(ex), donde });
            }
        };
        vista.GestureRecognizers.Add(tap);
    }
}

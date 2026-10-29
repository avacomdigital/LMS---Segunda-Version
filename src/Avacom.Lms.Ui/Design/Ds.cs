using System.Runtime.CompilerServices;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Design;

/// <summary>
/// Tokens y fábricas del <b>Aula · Design System v1.0</b> (octubre 2026) para la pizarra (OPS) y la tableta (Student).
///
/// Color: escala de 5 pasos por color (50/100 fondos, 500 iconos, 600 rellenos con texto blanco, 700 texto de
/// color) y <b>un color, un significado</b>: azul moverse/información, verde enseñar/empezar/hecho, magenta
/// contenido, amarillo practicar (lleva texto oscuro), violeta evaluar, turquesa gestionar, naranja atención,
/// rojo sólo parar, borrar o error. Proporción 60 fondo · 30 cajas · ≤ 10 color de rol.
/// Superficies: cajas blancas con contorno completo <see cref="Linea"/> y sombra difusa; nada de neumorfismo fuera
/// de la isla de marca, ni bordes de un solo lado, ni bases de color bajo los botones.
/// Tipografía: Lexend (400 texto · 500 etiquetas y botones · 600 títulos) y Andika para lectura en Inicial y Primaria.
/// Botones: píldora; el principal lleva degradado 600 → 700 del mismo color y sombra difusa de ese color; pulsado,
/// escala 0,97. Un solo principal por pantalla.
/// Los nombres anteriores (Tinta, Lienzo, Exito…) se conservan y apuntan a los tokens del DS.
/// </summary>
public static class Ds
{
    // ------------------------------------------------------------------ paleta
    public static readonly Color Azul50 = Color.FromArgb("#E3F5FC"), Azul100 = Color.FromArgb("#BCE5F5"), Azul500 = Color.FromArgb("#01A4E1"), Azul600 = Color.FromArgb("#0A72A6"), Azul700 = Color.FromArgb("#075985");
    public static readonly Color Verde50 = Color.FromArgb("#E1F5EC"), Verde100 = Color.FromArgb("#BFE6D3"), Verde500 = Color.FromArgb("#019D60"), Verde600 = Color.FromArgb("#047857"), Verde700 = Color.FromArgb("#0B5E3E");
    public static readonly Color Magenta50 = Color.FromArgb("#F7E5F1"), Magenta100 = Color.FromArgb("#E8C2DD"), Magenta500 = Color.FromArgb("#A81D81"), Magenta600 = Color.FromArgb("#A81D81"), Magenta700 = Color.FromArgb("#7D155F");
    public static readonly Color Amarillo50 = Color.FromArgb("#FFF6CF"), Amarillo100 = Color.FromArgb("#F3E29A"), Amarillo500 = Color.FromArgb("#F3C701"), Amarillo600 = Color.FromArgb("#F3C701"), Amarillo700 = Color.FromArgb("#6B4E00");
    public static readonly Color Violeta50 = Color.FromArgb("#EEEBFD"), Violeta100 = Color.FromArgb("#D6CFFA"), Violeta500 = Color.FromArgb("#6A55E0"), Violeta600 = Color.FromArgb("#5B45D1"), Violeta700 = Color.FromArgb("#4B36B8");
    public static readonly Color Turquesa50 = Color.FromArgb("#E0F6FA"), Turquesa100 = Color.FromArgb("#B3E8F1"), Turquesa500 = Color.FromArgb("#1BA9C9"), Turquesa600 = Color.FromArgb("#0E7490"), Turquesa700 = Color.FromArgb("#155E75");
    public static readonly Color Naranja50 = Color.FromArgb("#FFEDDF"), Naranja100 = Color.FromArgb("#FDD0AE"), Naranja500 = Color.FromArgb("#F26B1D"), Naranja600 = Color.FromArgb("#C2410C"), Naranja700 = Color.FromArgb("#9A3412");
    public static readonly Color Rojo50 = Color.FromArgb("#FDE7E7"), Rojo100 = Color.FromArgb("#F6C3C4"), Rojo500 = Color.FromArgb("#E5262B"), Rojo600 = Color.FromArgb("#C81E24"), Rojo700 = Color.FromArgb("#A51C20");
    /// <summary>Texto sobre el amarillo lleno (8,2:1).</summary>
    public static readonly Color TintaAmarillo = Color.FromArgb("#3D2E00");

    // ------------------------------------------------------------------ neutros
    /// <summary>Fondo elegido para el aula: «Nube» (#EAF0F6). Los otros del DS: Blanco #F5F6F8, Menta #E6F2EE, Lavanda #EEEDF7, Arena #ECEAE5.</summary>
    public static readonly Color Fondo = Color.FromArgb("#EAF0F6");
    public static readonly Color Fondo2 = Color.FromArgb("#DDE6F0");       // franja «toca aquí para subir» y velos sobre el fondo

    // ------------------------------------------------------------ neumorfismo
    /// <summary>Sólo isla de marca y esquinas superiores: base, sombra oscura (abajo-derecha) y luz (arriba-izquierda).</summary>
    public static readonly Color NeuBase = Color.FromArgb("#EEF1F5");
    public static readonly Color NeuOscura = Color.FromArgb("#8CA3B1C6");  // #A3B1C6 al 55 %
    public static readonly Color NeuLuz = Color.FromArgb("#F2FFFFFF");     // blanco al 95 %
    public static readonly Color Superficie = Colors.White;                // cajas
    public static readonly Color Superficie2 = Color.FromArgb("#F6F7F9");  // cajas dentro de cajas, desactivado
    public static readonly Color Linea = Color.FromArgb("#E3E6EC");        // bordes
    public static readonly Color Tinta = Color.FromArgb("#1F2433");        // texto principal · 15,5:1
    public static readonly Color Tinta2 = Color.FromArgb("#4F5566");       // texto secundario · 7,4:1
    public static readonly Color Tinta3 = Color.FromArgb("#5F6474");       // ayudas y metadatos · 5,9:1
    public static readonly Color Utilidad = Color.FromArgb("#6A788E");     // iconos de Ajustes y Filtra
    public static readonly Color Foco = Azul600;                           // anillo de foco 3 px

    // ------------------------------------------------------------------- roles
    /// <summary>Acción principal de la pantalla y elemento activo: verde (enseñar, empezar, hecho).</summary>
    public static readonly Color Principal = Verde600;
    public static readonly Color Navegacion = Azul600, Contenido = Magenta600, Practica = Amarillo500, Evaluacion = Violeta600, Gestion = Turquesa600, Atencion = Naranja600;

    // ------------------------------------------------- nombres anteriores → DS
    /// <summary>Rojo de peligro: terminar, salir, borrar o error. Nunca decorativo.</summary>
    public static readonly Color Rojo = Rojo600;
    public static readonly Color TintaSuave = Tinta2;
    public static readonly Color TintaMedia = Tinta2;
    public static readonly Color Lienzo = Fondo;
    public static readonly Color Filo = Linea;
    public static readonly Color Exito = Verde600;
    public static readonly Color Info = Azul600;
    /// <summary>Aviso: naranja 600 (reconectando, revisa, bloqueo). Lleva texto blanco.</summary>
    public static readonly Color Alerta = Naranja600;
    public static readonly Color Peligro = Rojo600;
    public static readonly Color ExitoSuave = Verde50;
    public static readonly Color InfoSuave = Azul50;
    public static readonly Color AlertaSuave = Naranja50;
    public static readonly Color PeligroSuave = Rojo50;
    public static readonly Color VioletaSuave = Magenta50;

    /// <summary>Categorías de contenido. Identifican (chip e icono); nunca rellenan un CTA.</summary>
    public static readonly Color CatVideo = Azul600;
    public static readonly Color CatClaseEnVivo = Magenta600;
    public static readonly Color CatQuiz = Amarillo500;      // practicar
    public static readonly Color CatLectura = Magenta700;    // contenido de lectura
    public static readonly Color CatAudio = Turquesa600;
    public static readonly Color CatExamen = Violeta600;     // evaluar

    public static readonly Color SuperficieContenido = Superficie;
    public static readonly Color GlassChrome = Superficie;
    public static readonly Color GlassOscuro = Superficie;

    // ------------------------------------------------------------- tipografía
    /// <summary>
    /// Lexend (OFL) en tres pesos que cada app registra en <c>ConfigureFonts</c>: 400 texto, 500 etiquetas y botones,
    /// 600 títulos. El DS no usa el peso ligero: <see cref="FuenteLigera"/> queda en 400. Andika (400/700) para la
    /// lectura del alumno en Inicial y Primaria. Sin cursivas ni negrita sintética.
    /// </summary>
    public const string FuenteLigera = "Lexend", FuenteRegular = "Lexend", FuenteMedia = "LexendMedium", FuenteSemi = "LexendSemiBold";
    public const string FuenteLectura = "Andika", FuenteLecturaNegrita = "AndikaBold";

    /// <summary>El DS no usa el peso ligero: el texto secundario va en 400 a cualquier tamaño.</summary>
    public static string FuenteSecundaria(double tamano) => FuenteRegular;

    // ------------------------------------------------------------------ radios
    /// <summary>Escala del DS: s 12 (chips cuadrados), m 16 (campos, avisos), l 24 (tarjetas), xl 32 (mosaicos), píldora (botones, barra inferior).</summary>
    public const int RadioS = 12, RadioM = 16, RadioL = 24, RadioXL = 32;
    public const int RadioControl = RadioS, RadioInterno = RadioM, RadioBoton = 24, RadioTarjeta = RadioL, RadioBarra = RadioL, RadioGrande = RadioXL, RadioPildora = 999;

    // ------------------------------------------------------------------ espacio
    /// <summary>Escala de espaciado de base 4.</summary>
    public const double Esp1 = 4, Esp2 = 8, Esp3 = 12, Esp4 = 16, Esp5 = 24, Esp6 = 32, Esp7 = 48, Esp8 = 64, Esp9 = 96;

    // -------------------------------------------------------------- movimiento
    public const uint DurRapida = 120, DurBase = 200, DurLenta = 320;

    // ------------------------------------------------------------- categorías
    /// <summary>Color de categoría de un objeto o bloque, por su <c>componente</c>.</summary>
    public static Color Categoria(string? componente) => componente switch
    {
        "presentacion" => CatClaseEnVivo,
        "lectura" or "texto" or "titulo" or "lista" or "pdf" => CatLectura,
        "laboratorio_web" or "webview" or "video" or "imagen" => CatVideo,
        "actividad" or "opcion_multiple" or "verdadero_falso" or "completar" or "relacionar" or "ordenar" or "abierta" => CatQuiz,
        "audio" => CatAudio,
        "examen" => CatExamen,
        _ => TintaSuave,
    };

    /// <summary>El amarillo lleva texto oscuro (#3D2E00); el resto de rellenos 600, blanco; las superficies claras, tinta.</summary>
    public static Color TintaSobre(Color fondo)
    {
        if (fondo == Amarillo500) return TintaAmarillo;
        if (fondo.Alpha < 0.5f) return Tinta;
        var luminancia = 0.299 * fondo.Red + 0.587 * fondo.Green + 0.114 * fondo.Blue;
        return luminancia > 0.62 ? Tinta : Colors.White;
    }

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

    // ----------------------------------------------------------------- sombras
    /// <summary>sh-1 (0 8 20 −12 · 22 %): tarjetas en reposo. MAUI no tiene «spread»: se compensa con menos opacidad.</summary>
    public static Shadow SombraTarjeta() => new() { Brush = new SolidColorBrush(Tinta), Offset = new Point(0, 8), Radius = 20, Opacity = 0.09f };
    /// <summary>sh-2 (0 18 40 −20 · 30 %): barra inferior y elementos elevados.</summary>
    public static Shadow SombraElevada() => new() { Brush = new SolidColorBrush(Tinta), Offset = new Point(0, 14), Radius = 32, Opacity = 0.13f };
    /// <summary>Sin luz neumórfica fuera de la isla de marca: sombra nula, se conserva la firma.</summary>
    public static Shadow SombraLuz() => new() { Brush = new SolidColorBrush(Colors.Transparent), Offset = new Point(0, 0), Radius = 0, Opacity = 0f };

    // ----------------------------------------------------------------- rellenos
    /// <summary>Superficie suave de un control secundario en reposo.</summary>
    public static readonly Color Fantasma = Superficie2;

    /// <summary>
    /// Relleno de un control. El DS sólo permite degradado entre dos tonos del mismo color (600 → 700, 135°); el
    /// resto de colores van lisos (se devuelve un pincel de un solo tono para no cambiar el tipo).
    /// </summary>
    public static LinearGradientBrush Degradado(Color fondo)
    {
        var hasta = TonoOscuro(fondo) ?? fondo;
        return new LinearGradientBrush(
            new GradientStopCollection { new GradientStop(fondo, 0f), new GradientStop(hasta, 1f) },
            new Point(0, 0), new Point(1, 1));
    }

    /// <summary>El 700 del mismo color para los 600 de la paleta; nulo si el color no es un relleno de rol.</summary>
    private static Color? TonoOscuro(Color c)
    {
        if (c == Verde600) return Verde700;
        if (c == Azul600) return Azul700;
        if (c == Magenta600) return Magenta700;
        if (c == Violeta600) return Violeta700;
        if (c == Turquesa600) return Turquesa700;
        if (c == Naranja600) return Naranja700;
        if (c == Rojo600) return Rojo700;
        if (c == Amarillo500) return Color.FromArgb("#E9BC00");   // par claro del amarillo, con texto oscuro
        return null;
    }

    private static readonly Color[][] Familias =
    [
        [Azul50, Azul500, Azul600, Azul700], [Verde50, Verde500, Verde600, Verde700], [Magenta50, Magenta500, Magenta600, Magenta700],
        [Amarillo50, Amarillo500, Amarillo600, Amarillo700], [Violeta50, Violeta500, Violeta600, Violeta700],
        [Turquesa50, Turquesa500, Turquesa600, Turquesa700], [Naranja50, Naranja500, Naranja600, Naranja700], [Rojo50, Rojo500, Rojo600, Rojo700],
    ];

    private static Color[]? FamiliaDe(Color c) => Familias.FirstOrDefault(f => f.Skip(1).Any(t => t == c));

    /// <summary>El 50 de la familia del color (fondo de chip, aviso o selección); si no es de la paleta, el color al 12 % sobre blanco.</summary>
    public static Color Suave(Color c) => FamiliaDe(c)?[0] ?? Mezcla(c, 0.12f);

    /// <summary>El 700 de la familia del color (texto de color sobre su 50); si no es de la paleta, el mismo color.</summary>
    public static Color Oscuro(Color c) => FamiliaDe(c)?[3] ?? c;

    /// <summary>El color a la opacidad dada, ya compuesto sobre blanco (opaco).</summary>
    public static Color Mezcla(Color c, float alfa) =>
        new(1 - (1 - c.Red) * alfa, 1 - (1 - c.Green) * alfa, 1 - (1 - c.Blue) * alfa);

    /// <summary>Contorno de los controles: sin bisel (el neumorfismo sólo vive en la isla de marca).</summary>
    public static SolidColorBrush Bisel() => new(Colors.Transparent);

    /// <summary>Sombra difusa de un control: del mismo color si es un relleno de rol; ninguna si es claro (el secundario sólo lleva contorno).</summary>
    public static Shadow SombraDe(Color? tono)
    {
        // Compacta a propósito: en WinUI la sombra se recorta contra el contenedor y una muy amplia deja ver el corte.
        var tenida = tono is not null && tono.Alpha >= 0.999f && tono.GetLuminosity() < 0.85f;
        return tenida
            ? new Shadow { Brush = new SolidColorBrush(tono!), Offset = new Point(0, 4), Radius = 10, Opacity = 0.22f }
            : new Shadow { Brush = new SolidColorBrush(Colors.Transparent), Offset = new Point(0, 0), Radius = 0, Opacity = 0f };
    }

    // -------------------------------------------------------------- superficies
    /// <summary>Caja del DS: blanca, contorno completo de 1 px en <see cref="Linea"/>, radio 24 y sombra sh-1.</summary>
    public static Border Tarjeta(View contenido, int radio = RadioTarjeta, Thickness? relleno = null, Color? fondo = null)
    {
        var borde = new Border
        {
            BackgroundColor = fondo ?? Superficie,
            Stroke = new SolidColorBrush(Linea),
            StrokeThickness = 1,
            StrokeShape = new RoundRectangle { CornerRadius = radio },
            Padding = relleno ?? new Thickness(Esp5),
            Content = contenido,
            Shadow = SombraTarjeta(),
        };
        return borde;
    }

    /// <summary>Barra clara: superficie blanca con contorno y sombra sh-2 (barras y navegación).</summary>
    public static Border BarraClara(View contenido, Thickness? relleno = null) => new()
    {
        BackgroundColor = Superficie,
        Stroke = new SolidColorBrush(Linea),
        StrokeThickness = 1,
        StrokeShape = new RoundRectangle { CornerRadius = RadioBarra },
        Padding = relleno ?? new Thickness(18, 10),
        Content = contenido,
        Shadow = SombraElevada(),
    };

    /// <summary>Barra de mandos de la clase: en el DS también es una barra blanca flotante con sombra sh-2.</summary>
    public static Border BarraOscura(View contenido, Thickness? relleno = null) => new()
    {
        BackgroundColor = Superficie,
        Stroke = new SolidColorBrush(Linea),
        StrokeThickness = 1,
        StrokeShape = new RoundRectangle { CornerRadius = RadioBarra },
        Padding = relleno ?? new Thickness(16, 10),
        Content = contenido,
        Shadow = SombraElevada(),
    };

    // ------------------------------------------------------------------ botones
    public enum Rango { Primary, Secondary, Quiet, Destructive }

    /// <summary>
    /// Botón del DS, en píldora. Primary: verde 600 → 700, texto blanco y sombra difusa verde. Secondary: blanco con
    /// contorno de 2 px. Quiet: sólo texto azul 700. Destructive: rojo 600 → 700. Pulsado: escala 0,97.
    /// </summary>
    public static Button Boton(string texto, Rango rango, EventHandler? alPulsar = null, double alto = 64, double? ancho = null)
    {
        var boton = new Button
        {
            Text = texto,
            HeightRequest = alto,
            MinimumHeightRequest = alto,
            CornerRadius = (int)(alto / 2),   // píldora: radio = medio alto (en WinUI un radio mayor deforma el botón)
            FontSize = alto >= 64 ? 18 : 16,
            FontFamily = FuenteMedia,
            Padding = new Thickness(24, 0),
            BorderWidth = 0,
        };
        if (ancho is not null) boton.WidthRequest = ancho.Value;
        switch (rango)
        {
            case Rango.Primary:
                PintarRelieve(boton, Principal, Colors.White); break;
            case Rango.Secondary:
                PintarRelieve(boton, Superficie, Tinta); break;
            case Rango.Quiet:
                boton.BackgroundColor = Colors.Transparent; boton.TextColor = Azul700; break;
            case Rango.Destructive:
                PintarRelieve(boton, Peligro, Colors.White); break;
        }
        Hundir(boton);
        if (alPulsar is not null) boton.Clicked += alPulsar;
        return boton;
    }

    /// <summary>
    /// Viste un botón del DS: relleno del color dado (degradado 600 → 700 si es de rol) y sombra difusa del mismo
    /// color. Un relleno claro lleva contorno de 2 px en <see cref="Linea"/> (botón secundario).
    /// </summary>
    public static void PintarRelieve(Button boton, Color fondo, Color texto)
    {
        boton.Background = Degradado(fondo);
        boton.TextColor = texto;
        var claro = fondo.GetLuminosity() >= 0.85f;
        boton.BorderColor = claro ? Linea : Colors.Transparent;
        boton.BorderWidth = claro ? 2 : 0;
        CuerpoDe(boton).Shadow = SombraDe(fondo);
    }

    private static readonly ConditionalWeakTable<Button, Border> Capsulas = new();

    /// <summary>
    /// Cápsula de un botón del DS: la sombra difusa vive por fuera (un <see cref="Border"/> recorta su contenido a
    /// la forma). Margen, alineación y hundimiento pasan a la cápsula; texto, tamaño, color e <c>IsEnabled</c> siguen
    /// en el botón. Se coloca la cápsula donde iría el botón. Un botón Quiet no lleva cápsula: se devuelve tal cual.
    /// </summary>
    public static View Capsula(Button boton)
    {
        if (Capsulas.TryGetValue(boton, out var existente)) return existente;
        if (boton.Background is null) return boton;
        var capsula = new Border
        {
            BackgroundColor = Colors.Transparent,
            StrokeThickness = 0,
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

    /// <summary>Pulsación del DS (120 ms): escala 0,97 y vuelta; la sombra se recoge mientras se pulsa. Con cápsula, se hunde la cápsula.</summary>
    public static void Hundir(Button boton)
    {
        Shadow? reposo = null;
        boton.Pressed += async (_, _) =>
        {
            var cuerpo = CuerpoDe(boton);
            reposo = cuerpo.Shadow;
            if (reposo is not null) cuerpo.Shadow = new Shadow { Brush = reposo.Brush, Offset = new Point(0, 3), Radius = 10, Opacity = reposo.Opacity * 0.6f };
            await cuerpo.ScaleToAsync(0.97, 60, Easing.CubicOut);
        };
        boton.Released += async (_, _) =>
        {
            var cuerpo = CuerpoDe(boton);
            await cuerpo.ScaleToAsync(1, 60, Easing.CubicOut);
            if (reposo is not null) cuerpo.Shadow = reposo;
        };
    }

    /// <summary>Interruptor tocable para la barra de mandos: dos estados con color semántico. 64 px por defecto; en barras densas se puede pedir más bajo.</summary>
    public static Button Interruptor(string texto, bool activo, Color activoColor, EventHandler alPulsar, double alto = 64)
    {
        var b = new Button
        {
            Text = texto,
            HeightRequest = alto,
            MinimumHeightRequest = alto,
            CornerRadius = (int)(alto / 2),
            FontSize = alto >= 64 ? 18 : 15,
            FontFamily = FuenteMedia,
            Padding = new Thickness(alto >= 64 ? 20 : 16, 0),
            BorderWidth = 0,
        };
        PintarInterruptor(b, activo, activoColor);
        Hundir(b);
        b.Clicked += alPulsar;
        return b;
    }

    /// <summary>Activo: relleno del color semántico y su sombra. En reposo: superficie suave con contorno y texto en tinta.</summary>
    public static void PintarInterruptor(Button b, bool activo, Color activoColor) =>
        PintarRelieve(b, activo ? activoColor : Superficie2, activo ? TintaSobre(activoColor) : Tinta);

    /// <summary>
    /// Botón redondo, sólo glifo, para una acción secundaria de la barra de mandos que no necesita etiqueta
    /// (bloquear pantallas, aviso). Mismo relleno y pulsación que <see cref="Interruptor"/>, sin texto. Añade su
    /// propia descripción semántica porque no hay etiqueta visible que la sustituya.
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
    /// `*cursiva*` y la matemática en línea (`$…$`, ya legible) van en itálica; no hay Lexend Italic empaquetada,
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
    /// <summary>
    /// Chip de categoría o estado: identifica, no llama a la acción. Regla del DS: el 700 sobre el 50. Si se pasa un color de
    /// rol (500/600) sin tinta propia, el chip toma el 50 de esa familia y el texto en su 700; un fondo suave o neutro se respeta.
    /// </summary>
    public static Border Pildora(string texto, Color fondo, Color? tinta = null, double tamano = 13) =>
        tinta is null && FamiliaDe(fondo) is not null ? PildoraBase(texto, Suave(fondo), Oscuro(fondo), tamano) : PildoraBase(texto, fondo, tinta, tamano);

    private static Border PildoraBase(string texto, Color fondo, Color? tinta, double tamano) => new()
    {
        BackgroundColor = fondo,
        StrokeThickness = 0,
        StrokeShape = new RoundRectangle { CornerRadius = RadioPildora },
        Padding = new Thickness(14, 6),
        Content = new Label { Text = texto, FontSize = tamano, FontFamily = FuenteMedia, TextColor = tinta ?? TintaSobre(fondo), LineBreakMode = LineBreakMode.WordWrap },
        VerticalOptions = LayoutOptions.Center,
    };

    /// <summary>Punto de estado de conexión (CMP-001): conectado, reconectando o sin señal. Sin porcentajes. El punto y la palabra, nunca sólo el color.</summary>
    public static Border PuntoEstado(string texto, Color color) => Pildora($"●  {texto}", Superficie2, color, 13);

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

    /// <summary>El DS no dibuja líneas divisorias entre filas: se separa con espacio. Se conserva el hueco de 1 px.</summary>
    public static Border Separador() => new() { HeightRequest = 1, BackgroundColor = Colors.Transparent, StrokeThickness = 0 };

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

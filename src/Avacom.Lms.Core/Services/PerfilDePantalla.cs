using System.Globalization;

namespace Avacom.Lms.Core.Services;

/// <summary>Resolución física de la pantalla donde se proyecta el aula. <see cref="Auto"/> = la que mide la propia ventana.</summary>
public enum ResolucionPantalla { Auto, FullHd, Uhd4k }

/// <summary>Un recuadro (ancho × alto) en unidades lógicas (DIP) de MAUI.</summary>
public readonly record struct CajaDeMedio(double Ancho, double Alto)
{
    public static readonly CajaDeMedio Vacia = new(0, 0);
    public bool EsVacia => Ancho <= 0 || Alto <= 0;
}

/// <summary>
/// Perfil de pantalla del aula: resolución física × escala de Windows («Configuración › Pantalla › Escala»).
/// Lo que MAUI maqueta son unidades lógicas, es decir píxeles físicos ÷ escala: un 4K al 200 % maqueta igual que un
/// Full HD al 100 % (1920×1080), un Full HD al 80 % da 2400×1350 y un 4K al 80 %, 4800×2700. El perfil sirve para
/// que OPS acote el vídeo de la clase al espacio que de verdad tiene esa pantalla (docs: 02-classroom-engine/responsive.md).
/// </summary>
public sealed record PerfilDePantalla(ResolucionPantalla Resolucion, int EscalaPct)
{
    /// <summary>Escalas de Windows que se ofrecen (la de «Recomendada» de Windows 11 puede ser 125 % o 150 %).</summary>
    public static readonly IReadOnlyList<int> Escalas = [80, 100, 125, 150, 200];

    /// <summary>Lo que el chrome de OPS (secuencia de 360, márgenes, barra de título/controles/tareas) quita a la proyección, a 1920×1080 al 100 %.</summary>
    public const double ReservaAnchoOps = 424;
    public const double ReservaAltoOps = 400;
    /// <summary>Margen interior de la tarjeta de contenido a cada lado (28 × escala de texto 1,15 ≈ 32).</summary>
    public const double MargenLateral = 32;
    public const double MargenVertical = 32;

    public static PerfilDePantalla Auto { get; } = new(ResolucionPantalla.Auto, 100);

    public bool EsAuto => Resolucion == ResolucionPantalla.Auto;

    public int AnchoPx => Resolucion switch { ResolucionPantalla.FullHd => 1920, ResolucionPantalla.Uhd4k => 3840, _ => 0 };
    public int AltoPx => Resolucion switch { ResolucionPantalla.FullHd => 1080, ResolucionPantalla.Uhd4k => 2160, _ => 0 };

    /// <summary>Ancho/alto lógicos (DIP) de la pantalla completa; 0 en automático.</summary>
    public double AnchoLogico => EsAuto ? 0 : AnchoPx * 100.0 / EscalaPct;
    public double AltoLogico => EsAuto ? 0 : AltoPx * 100.0 / EscalaPct;

    public string Rotulo => EsAuto ? "Automático" : $"{AnchoPx}×{AltoPx} · {EscalaPct} %";

    /// <summary>Clave estable para guardarlo en las preferencias: «auto» o «1920x1080@100».</summary>
    public string Clave => EsAuto ? "auto" : $"{AnchoPx}x{AltoPx}@{EscalaPct}";

    /// <summary>Lee una clave guardada; cualquier cosa rara (vacía, vieja, a mano) cae en automático.</summary>
    public static PerfilDePantalla Leer(string? clave)
    {
        if (string.IsNullOrWhiteSpace(clave)) return Auto;
        var partes = clave.Trim().ToLowerInvariant().Split('@');
        if (partes.Length != 2 || !int.TryParse(partes[1], NumberStyles.None, CultureInfo.InvariantCulture, out var escala) || !Escalas.Contains(escala)) return Auto;
        return partes[0] switch
        {
            "1920x1080" => new PerfilDePantalla(ResolucionPantalla.FullHd, escala),
            "3840x2160" => new PerfilDePantalla(ResolucionPantalla.Uhd4k, escala),
            _ => Auto,
        };
    }

    /// <summary>
    /// A qué perfil estándar se parece la pantalla que reporta el sistema (píxeles físicos y densidad: 1,0 = 100 %, 1,25 = 125 %…).
    /// Se usa sólo para decirle al docente «Detectado: …» junto al selector; nunca cambia el perfil por sí solo.
    /// </summary>
    public static PerfilDePantalla Detectar(double anchoPx, double densidad)
    {
        if (anchoPx <= 0 || densidad <= 0) return Auto;
        var pct = densidad * 100;
        var escala = Escalas.OrderBy(e => Math.Abs(e - pct)).First();
        return new PerfilDePantalla(anchoPx >= 3000 ? ResolucionPantalla.Uhd4k : ResolucionPantalla.FullHd, escala);
    }

    /// <summary>Techo del recuadro de un medio en este perfil: el espacio de proyección de OPS en esa pantalla, menos márgenes. Vacío en automático.</summary>
    public CajaDeMedio TechoDeMedio => EsAuto
        ? CajaDeMedio.Vacia
        : new CajaDeMedio(Math.Max(0, AnchoLogico - ReservaAnchoOps - 2 * MargenLateral), Math.Max(0, AltoLogico - ReservaAltoOps - MargenVertical));
}

/// <summary>
/// Calcula el recuadro de un video o una imagen dentro de la proyección. Regla única para cualquier medio del curso, venga con
/// la proporción que venga (16∶9, 4∶3, vertical, sin declarar): cabe ENTERO en el espacio visible —ancho y alto— sin recortarse
/// ni obligar a desplazar para verlo completo, conserva su proporción y queda centrado por quien lo aloje.
/// </summary>
public static class AjusteDeMedio
{
    /// <summary>Proporción de respaldo cuando la biblioteca no publica ancho/alto del medio.</summary>
    public const double ProporcionPorDefecto = 9.0 / 16.0;
    /// <summary>Un recuadro más chico que esto no se puede ver ni tocar; si el espacio es menor se prefiere desplazar.</summary>
    public const double AnchoMinimo = 320;
    public const double AltoMinimo = 180;

    /// <summary>Alto ÷ ancho del medio, o 16∶9 si no se conoce (o es absurda).</summary>
    public static double Proporcion(int? ancho, int? alto) =>
        ancho is > 0 && alto is > 0 && (double)alto.Value / ancho.Value is >= 0.2 and <= 3.0 ? (double)alto.Value / ancho.Value : ProporcionPorDefecto;

    /// <summary>
    /// <paramref name="anchoLibre"/> y <paramref name="altoLibre"/> son lo que mide la ventana (0 si aún no se sabe); el perfil manual
    /// puede sólo ENCOGER ese espacio, nunca agrandarlo. Con nada conocido devuelve <see cref="CajaDeMedio.Vacia"/> (no hay nada que maquetar todavía).
    /// </summary>
    public static CajaDeMedio Ajustar(double anchoLibre, double altoLibre, double proporcion, PerfilDePantalla? perfil = null)
    {
        if (proporcion <= 0) proporcion = ProporcionPorDefecto;
        var techo = (perfil ?? PerfilDePantalla.Auto).TechoDeMedio;
        var ancho = Acotar(anchoLibre, techo.Ancho);
        var alto = Acotar(altoLibre, techo.Alto);
        if (ancho <= 0) return CajaDeMedio.Vacia;

        var w = alto > 0 ? Math.Min(ancho, alto / proporcion) : ancho;
        // Si el alto disponible es tan poco que el medio quedaría ilegible, gana el ancho y la página se desplaza.
        if (w < AnchoMinimo || w * proporcion < AltoMinimo) w = Math.Min(ancho, Math.Max(w, AnchoMinimo));
        return new CajaDeMedio(Math.Floor(w), Math.Floor(w * proporcion));
    }

    private static double Acotar(double real, double techo) =>
        real > 0 && techo > 0 ? Math.Min(real, techo) : real > 0 ? real : techo;
}

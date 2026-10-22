using Avacom.Lms.Core.Actualizacion;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Pages;
using Avacom.Lms.Ops.Reportes.Ui;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Actualizacion.Ui;

/// <summary>
/// Las piezas que comparten la pantalla «Actualizaciones» y su hoja (MOD-017): quién actúa, el cliente y las superficies. Sólo Border, Label y Button del kit (y la lámina de vidrio, que
/// también es un Border): ningún Path ni Ellipse, porque una geometría degenerada deja sin pintar todos los lienzos Win2D de la ventana. Todo lo que se toca mide al menos 60 px (NFR-044,
/// pantalla táctil de 86"). Nada pide escribir: OPS no tiene teclado.
/// </summary>
internal static class ActualizacionUi
{
    /// <summary>El alto de todo lo que se toca en estas pantallas.</summary>
    public const double AltoTactil = 64;

    public static string Actor => Sesion.ProfesorId;
    public static IActualizacionApi Api => Sesion.Actualizacion;

    /// <summary>Un toque corre en un <c>async void</c>: una excepción que se escapara cerraría OPS en plena clase. Se anota y la pantalla sigue.</summary>
    public static Func<Task> Seguro(string donde, Func<Task> accion) => ReportesUi.Seguro("Actualizaciones", donde, accion);

    public static Tono TonoDe(TonoDeActualizacion tono) => tono switch
    {
        TonoDeActualizacion.Bien => Tono.Exito,
        TonoDeActualizacion.Info => Tono.Info,
        TonoDeActualizacion.Atencion => Tono.Ambar,
        _ => Tono.Neutro,
    };

    /// <summary>Un paquete ya importado (o la ficha que se está mirando) en el flujo, con la hora del nodo y la zona de este equipo.</summary>
    public static FlujoDeActualizacion NuevoFlujo() =>
        new(Api, Actor, Sesion.Usuario, () => Sesion.ClaseAbiertaId is not null, () => Avacom.Lms.Core.Services.RelojNodo.AhoraMs);

    /// <summary>La lámina de vidrio de la tarjeta central. Sin el pincel de fondo desenfocado (rompe los lienzos Win2D que comparten el desplazable).</summary>
    public static LiquidGlassPanel Vidrio(View contenido) => new()
    {
        CornerRadius = Ds.RadioGrande, TintColor = Colors.White, TintOpacity = 0.82, Backdrop = false, BlurRadius = 0, SheenHeight = 90, SheenOpacity = 0.35,
        ContentPadding = new Thickness(30, 26), ShadowOpacity = 0.12, Content = contenido,
    };

    /// <summary>Una tarjeta blanca de las de los lados.</summary>
    public static Border Tarjeta(View contenido) => Ds.Tarjeta(contenido, Ds.RadioGrande, new Thickness(28, 24), Colors.White);

    /// <summary>Un botón grande del kit (64 px), listo para colocar en una fila que se parte sola.</summary>
    public static (Button Boton, View Vista) Accion(string texto, Ds.Rango rango, Func<Task> alPulsar, string id, double? ancho = null) =>
        ExamenUi.Accion(texto, rango, alPulsar, ancho, id, AltoTactil);

    /// <summary>Un botón de acción de ancho completo, con una línea que dice para qué sirve.</summary>
    public static View AccionConDescripcion(string texto, string descripcion, Ds.Rango rango, Func<Task> alPulsar, string id)
    {
        var (boton, vista) = ExamenUi.Accion(texto, rango, alPulsar, null, id, AltoTactil, margen: false);
        boton.HorizontalOptions = LayoutOptions.Fill;
        vista.HorizontalOptions = LayoutOptions.Fill;
        var pila = new VerticalStackLayout { Spacing = 6, Margin = new Thickness(0, 0, 0, 14) };
        pila.Add(vista);
        pila.Add(Ds.Secundario(descripcion, 14));
        return pila;
    }

    public static View Dato(string rotulo, string? valor, double ancho = 120) => ExamenUi.Dato(rotulo, string.IsNullOrWhiteSpace(valor) ? "—" : valor!, ancho);

    /// <summary>Una tarjeta que se toca (un paquete de la memoria, un motivo): 64 px como mínimo, un botón transparente encima del contenido.</summary>
    public static Border Tocable(View contenido, Func<Task> alTocar, string descripcion, string id, bool elegida = false)
    {
        var t = ReportesUi.Tocable(contenido, alTocar, descripcion, id, Colors.White, new Thickness(16, 12), elegida);
        t.MinimumHeightRequest = AltoTactil;
        t.Margin = new Thickness(0, 0, 0, 8);
        return t;
    }

    public static Label Eyebrow(string texto) => EstudioUi.Eyebrow(texto);

    /// <summary>El aviso del último resultado (o problema) con su tono y su AutomationId.</summary>
    public static Border Aviso(MensajeDeActualizacion m, bool problema, string id)
    {
        var aviso = ExamenUi.Aviso(m.Titulo, m.Completo, problema ? Tono.Ambar : Tono.Exito);
        aviso.AutomationId = id;
        return aviso;
    }
}

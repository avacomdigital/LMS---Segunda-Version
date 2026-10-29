using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Pages;
using Avacom.Lms.Ops.Reportes;
using Avacom.Lms.Ops.Reportes.Ui;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Licencia.Ui;

/// <summary>
/// Las piezas que comparten la pantalla «Licencia», su hoja de pasos y el banner del menú principal (MOD-018): quién actúa, los clientes, las memorias, y las superficies. Sólo Border,
/// Label y Button del kit (y la lámina de vidrio, que también es un Border): ningún Path ni Ellipse, porque una geometría degenerada deja sin pintar todos los lienzos Win2D de la ventana.
/// Todo lo que se toca mide al menos 60 px (NFR-044, pantalla táctil de 86").
/// </summary>
internal static class LicenciaUi
{
    /// <summary>El alto de todo lo que se toca en estas pantallas.</summary>
    public const double AltoTactil = 64;

    public static string Actor => Sesion.ProfesorId;
    public static ILicenciaApi Api => Sesion.Licencia;

    /// <summary>Las unidades del sistema más las de prueba (sólo con el perfil de UI Automation, <c>AVACOM_OPS_UNIDADES_PRUEBA</c>): las mismas que ve la hoja de exportar.</summary>
    public static readonly IProveedorDeUnidades Unidades = new ProveedorConUnidadesDePrueba(new ProveedorDeUnidadesDelSistema());

    /// <summary>La última carpeta que usó esta persona para la licencia (aparte de la de los reportes).</summary>
    public static readonly PreferenciasDeDestino Preferencias = new(new AlmacenConPrefijo(new AlmacenDeAjustes(), AlmacenConPrefijo.DeLicencia));

    public static BuscadorDeLicencias Buscador() =>
        new(Unidades, new CarpetasConocidasDelSistema(), new LectorDeArchivosDelSistema(), () => Preferencias.UltimaCarpeta(Actor));

    public static void RecordarCarpeta(string carpeta) => Preferencias.RecordarCarpeta(Actor, carpeta);

    /// <summary>Un toque corre en un <c>async void</c>: una excepción que se escapara cerraría OPS en plena clase. Se anota y la pantalla sigue.</summary>
    public static Func<Task> Seguro(string donde, Func<Task> accion) => ReportesUi.Seguro("Licencia", donde, accion);

    // ------------------------------------------------------------------------------------------------------------------ tonos

    public static Tono TonoDe(TonoDeAviso tono) => tono switch
    {
        TonoDeAviso.Fuerte => Tono.AmbarFuerte,
        TonoDeAviso.Atencion => Tono.Ambar,
        _ => Tono.Info,
    };

    /// <summary>Los colores del banner del menú principal (fondo, tinta y filo), con la misma familia que las bandas del PIN y del aviso de entrada.</summary>
    public static (Color Fondo, Color Tinta, Color Filo) ColoresDelBanner(TonoDeAviso tono) => tono switch
    {
        TonoDeAviso.Fuerte => (ExamenUi.FondoAmbarFuerte, ExamenUi.TintaAmbarFuerte, Color.FromArgb("#66C2410C")),
        TonoDeAviso.Atencion => (Color.FromArgb("#FFEDDF"), Color.FromArgb("#9A3412"), Color.FromArgb("#FDD0AE")),
        _ => (Color.FromArgb("#E3F5FC"), Color.FromArgb("#075985"), Color.FromArgb("#BCE5F5")),
    };

    // ------------------------------------------------------------------------------------------------------------------ superficies

    /// <summary>
    /// La lámina de vidrio de la tarjeta central (el estado). Sin el pincel de fondo desenfocado: en una pantalla con desplazable es lo que el kit recomienda (el pincel rompe los lienzos
    /// Win2D que comparten el desplazable); el vidrio queda en el tinte, el canto luminoso, el reflejo y la sombra.
    /// </summary>
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

    /// <summary>Un botón de acción de la tarjeta «Qué puedes hacer»: ancho completo, 64 px, con una línea que dice para qué sirve.</summary>
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

    /// <summary>Un renglón «rótulo · valor» del estado.</summary>
    public static View Dato(string rotulo, string? valor, double ancho = 120) => ExamenUi.Dato(rotulo, string.IsNullOrWhiteSpace(valor) ? "—" : valor!, ancho);

    /// <summary>
    /// Una barra de consumo hecha con Border (nunca un Path): el rótulo, la cifra y la barra desde cero. Sin tope no hay barra: se dice «sin tope». En ámbar a partir del 90 %.
    /// </summary>
    public static View Barra(string rotulo, UsoDelCupo? uso, string tipo)
    {
        var pila = new VerticalStackLayout { Spacing = 6, Margin = new Thickness(0, 0, 0, 12) };
        var cabeza = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 10 };
        cabeza.Add(new Label { Text = rotulo, FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, VerticalOptions = LayoutOptions.Center }, 0, 0);
        cabeza.Add(new Label { Text = LicenciaTexto.Uso(uso, tipo), FontFamily = Ds.FuenteRegular, FontSize = 16, TextColor = Ds.TintaMedia, VerticalOptions = LayoutOptions.Center,
            AutomationId = $"licencia-uso-{tipo}" }, 1, 0);
        pila.Add(cabeza);
        if (uso is { EnUso: { } enUso, Limite: { } limite } && limite > 0)
        {
            var fraccion = Math.Clamp((double)enUso / limite, 0, 1);
            var color = uso.Porcentaje is >= 90 || enUso >= limite ? ReportesUi.ColorDeAdvertencia : Ds.Exito;
            pila.Add(EstudioUi.Barra(fraccion, color, 12));
        }
        return pila;
    }

    /// <summary>Un módulo licenciable con su estado (habilitado o en pausa): el color nunca es el único aviso, también lo dice la píldora.</summary>
    public static View Modulo(string codigo, bool habilitado)
    {
        var texto = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        texto.Add(new Label { Text = LicenciaTexto.Capacidad(codigo), FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta });
        texto.Add(Ds.Secundario(LicenciaTexto.DescripcionDeCapacidad(codigo), 13));
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12, Margin = new Thickness(0, 0, 0, 6) };
        fila.Add(texto, 0, 0);
        fila.Add(ExamenUi.Pildora(habilitado ? "✓  Disponible" : "En pausa", habilitado ? Tono.Exito : Tono.AmbarFuerte, 13), 1, 0);
        return fila;
    }

    /// <summary>Una tarjeta que se toca (un archivo de licencia, un destino): 64 px como mínimo, un botón transparente encima del contenido.</summary>
    public static Border Tocable(View contenido, Func<Task> alTocar, string descripcion, string id, bool elegida = false)
    {
        var t = ReportesUi.Tocable(contenido, alTocar, descripcion, id, Colors.White, new Thickness(16, 12), elegida);
        t.MinimumHeightRequest = AltoTactil;
        t.Margin = new Thickness(0, 0, 0, 8);
        return t;
    }

    /// <summary>Un título de sección con su línea de ayuda.</summary>
    public static View Seccion(string titulo, string? ayuda = null) => ReportesUi.Seccion(titulo, ayuda);

    public static Label Eyebrow(string texto) => EstudioUi.Eyebrow(texto);

    /// <summary>La frase de un error de red o del nodo, para la pantalla.</summary>
    public static MensajeDeLicencia Error(ILicenciaApi api) => LicenciaTexto.DeError(api.UltimoError);

    public static void Anotar(string evento, string mensaje, object? detalle = null) => RegistroLocal.Advertencia(Canal.Escritura, evento, mensaje, detalle);
}

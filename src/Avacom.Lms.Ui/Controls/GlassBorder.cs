namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Tarjeta de vidrio (liquid glass): un <see cref="Border"/> cuyo fondo deja ver, desenfocado y teñido, lo que hay
/// debajo. En Windows el material es un pincel de composición (lo de detrás + desenfoque gaussiano + saturación +
/// exposición + tinte), ver <c>Platforms/Windows/GlassBorder.Windows.cs</c>; en las demás plataformas se aproxima con
/// el tinte translúcido sin desenfoque, como el resto del kit. El control sólo aporta el material: el canto luminoso
/// se pone con <see cref="Border.Stroke"/> (un degradado blanco) y la profundidad con <see cref="VisualElement.Shadow"/>.
///
/// La sombra queda detrás de la tarjeta y el desenfoque la muestrea también, así que el interior tiende a apagarse:
/// <see cref="Brightness"/> y <see cref="Saturation"/> lo compensan para que el vidrio se vea iluminado y conserve el
/// tono del fondo. El texto que va encima debe seguir legible: con tinte blanco sobre fondos claros lo es.
/// </summary>
public partial class GlassBorder : Border
{
    public static readonly BindableProperty TintColorProperty =
        BindableProperty.Create(nameof(TintColor), typeof(Color), typeof(GlassBorder), Colors.White, propertyChanged: AlCambiarMaterial);

    public static readonly BindableProperty TintOpacityProperty =
        BindableProperty.Create(nameof(TintOpacity), typeof(double), typeof(GlassBorder), 0.45, propertyChanged: AlCambiarMaterial);

    public static readonly BindableProperty BlurRadiusProperty =
        BindableProperty.Create(nameof(BlurRadius), typeof(double), typeof(GlassBorder), 8.0, propertyChanged: AlCambiarMaterial);

    public static readonly BindableProperty BrightnessProperty =
        BindableProperty.Create(nameof(Brightness), typeof(double), typeof(GlassBorder), 0.05, propertyChanged: AlCambiarMaterial);

    public static readonly BindableProperty SaturationProperty =
        BindableProperty.Create(nameof(Saturation), typeof(double), typeof(GlassBorder), 1.15, propertyChanged: AlCambiarMaterial);

    public static readonly BindableProperty BackdropProperty =
        BindableProperty.Create(nameof(Backdrop), typeof(bool), typeof(GlassBorder), true, propertyChanged: AlCambiarMaterial);

    static GlassBorder() => RegistrarPlataforma();

    public GlassBorder() => ActualizarRespaldo();

    /// <summary>Color del tinte que se superpone al fondo desenfocado. Blanco para vidrio claro.</summary>
    public Color TintColor { get => (Color)GetValue(TintColorProperty); set => SetValue(TintColorProperty, value); }

    /// <summary>Opacidad del tinte (0–1). Más alto, más opaco y luminoso; más bajo, más se ve lo de detrás.</summary>
    public double TintOpacity { get => (double)GetValue(TintOpacityProperty); set => SetValue(TintOpacityProperty, value); }

    /// <summary>Desviación típica del desenfoque gaussiano del fondo, en píxeles (el radio visible es unas tres veces).</summary>
    public double BlurRadius { get => (double)GetValue(BlurRadiusProperty); set => SetValue(BlurRadiusProperty, value); }

    /// <summary>Exposición del fondo desenfocado, en pasos (0 = tal cual; 0,05 ≈ 3,5 % más luz). Compensa la sombra que hay debajo.</summary>
    public double Brightness { get => (double)GetValue(BrightnessProperty); set => SetValue(BrightnessProperty, value); }

    /// <summary>Saturación del fondo desenfocado (1 = tal cual). Algo más de 1 devuelve el tono que la sombra y el tinte apagan.</summary>
    public double Saturation { get => (double)GetValue(SaturationProperty); set => SetValue(SaturationProperty, value); }

    /// <summary>
    /// Si en Windows se usa el pincel de composición que muestrea lo de detrás (verdadero por defecto). Apagado, la
    /// tarjeta es el tinte plano translúcido: vale para láminas dentro de un <c>ScrollView</c> que conviven con lienzos
    /// Win2D (formas, GraphicsView), con los que el pincel de fondo no se lleva bien, y como reserva para equipos flojos.
    /// </summary>
    public bool Backdrop { get => (bool)GetValue(BackdropProperty); set => SetValue(BackdropProperty, value); }

    /// <summary>El tinte con su opacidad aplicada: fondo plano donde no hay desenfoque y color de reserva en Windows.</summary>
    internal Color Tinte => (TintColor ?? Colors.White).WithAlpha((float)Math.Clamp(TintOpacity, 0, 1));

    /// <summary>En Windows engancha el pincel de vidrio al mapeo del fondo del Border; en otras plataformas no hace nada.</summary>
    static partial void RegistrarPlataforma();

    private static void AlCambiarMaterial(BindableObject bindable, object oldValue, object newValue) => ((GlassBorder)bindable).ActualizarRespaldo();

    /// <summary>
    /// Fondo plano translúcido. Asignarlo vuelve a ejecutar el mapeo del fondo, que en Windows lo sustituye por el vidrio;
    /// si el color no cambia (sólo cambió desenfoque, exposición o saturación) se fuerza el mapeo a mano.
    /// </summary>
    private void ActualizarRespaldo()
    {
        var tinte = Tinte;
        if (BackgroundColor == tinte) Handler?.UpdateValue(nameof(Background));
        else BackgroundColor = tinte;
    }
}

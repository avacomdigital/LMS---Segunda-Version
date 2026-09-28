using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Tarjeta de curso en Liquid Glass: conserva todos los datos de la ficha (título, descripción y metadatos) y las
/// dos vías de abrir el curso que ya tenía la tarjeta blanca: tocar cualquier punto de la tarjeta o el botón
/// «Ver lecciones ›». Las dos disparan <see cref="Abrir"/>; <see cref="Lanzar"/> descarta un segundo disparo en
/// menos de 400 ms para que un toque sobre el botón (que en algunas plataformas burbujea hasta la tarjeta) no abra
/// el curso dos veces.
/// </summary>
public partial class CourseGlassCard : ContentView
{
    public static readonly BindableProperty TituloProperty = BindableProperty.Create(nameof(Titulo), typeof(string), typeof(CourseGlassCard), string.Empty);
    public static readonly BindableProperty SubtituloProperty = BindableProperty.Create(nameof(Subtitulo), typeof(string), typeof(CourseGlassCard), null,
        propertyChanged: (b, _, n) => ((CourseGlassCard)b).SubtituloLabel.IsVisible = !string.IsNullOrWhiteSpace(n as string));
    public static readonly BindableProperty DetalleProperty = BindableProperty.Create(nameof(Detalle), typeof(string), typeof(CourseGlassCard), string.Empty);
    public static readonly BindableProperty AccentColorProperty = BindableProperty.Create(nameof(AccentColor), typeof(Color), typeof(CourseGlassCard), Glass.AcentoRosa,
        propertyChanged: (b, _, _) => ((CourseGlassCard)b).PintarBloque());
    public static readonly BindableProperty IconGeometryProperty = BindableProperty.Create(nameof(IconGeometry), typeof(string), typeof(CourseGlassCard), string.Empty,
        propertyChanged: (b, _, _) => ((CourseGlassCard)b).PintarBloque());

    private DateTime ultimo = DateTime.MinValue;

    public CourseGlassCard()
    {
        InitializeComponent();
        PintarBloque();
        // Toda la tarjeta es tocable: se hunde (como Ds.Tocable) y abre.
        var toque = new TapGestureRecognizer();
        toque.Tapped += async (_, _) =>
        {
            await this.ScaleToAsync(0.985, 70, Easing.CubicOut);
            await this.ScaleToAsync(1, 110, Easing.CubicOut);
            Lanzar();
        };
        GestureRecognizers.Add(toque);
    }

    /// <summary>Se dispara al tocar la tarjeta o el botón «Ver lecciones ›».</summary>
    public event EventHandler? Abrir;

    public string Titulo { get => (string)GetValue(TituloProperty); set => SetValue(TituloProperty, value); }
    public string? Subtitulo { get => (string?)GetValue(SubtituloProperty); set => SetValue(SubtituloProperty, value); }
    public string Detalle { get => (string)GetValue(DetalleProperty); set => SetValue(DetalleProperty, value); }
    public Color AccentColor { get => (Color)GetValue(AccentColorProperty); set => SetValue(AccentColorProperty, value); }
    public string IconGeometry { get => (string)GetValue(IconGeometryProperty); set => SetValue(IconGeometryProperty, value); }

    private void OnVerClicked(object? sender, EventArgs e) => Lanzar();

    private void Lanzar()
    {
        var ahora = DateTime.UtcNow;
        if ((ahora - ultimo).TotalMilliseconds < 400) return;
        ultimo = ahora;
        Abrir?.Invoke(this, EventArgs.Empty);
    }

    private void PintarBloque()
    {
        if (BloqueHost is null) return;
        BloqueHost.Children.Clear();
        BloqueHost.Children.Add(Glass.Bloque(AccentColor, IconGeometry, 64, 16));
    }
}

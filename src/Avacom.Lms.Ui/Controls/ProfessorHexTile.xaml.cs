using Avacom.Lms.Ui.Graphics;
using Microsoft.Maui.Controls.Shapes;
using Path = Microsoft.Maui.Controls.Shapes.Path;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Hexágono de módulo o materia (146 × 168) con icono vectorial y etiqueta. Dos materiales: el blanco de siempre
/// (tablero y Asignaturas) y, con <see cref="Glass"/>, el Liquid Glass de «Clase de hoy»: cuerpo translúcido del
/// color de acento con degradado, reflejo blanco superior, canto luminoso y resplandor del acento
/// (<see cref="HexGlassDrawable"/>), con icono y texto en la tinta que contraste. La geometría del hexágono es la
/// misma en ambos; sólo cambia cómo se pinta. Interacciones iguales: hover 1,04 · pressed 0,97 · release 1,0.
/// </summary>
public partial class ProfessorHexTile : ContentView
{
    public static readonly BindableProperty TextProperty = BindableProperty.Create(nameof(Text), typeof(string), typeof(ProfessorHexTile), string.Empty);
    public static readonly BindableProperty AccentColorProperty = BindableProperty.Create(nameof(AccentColor), typeof(Color), typeof(ProfessorHexTile), Colors.Black, propertyChanged: OnAccentColorChanged);
    public static readonly BindableProperty IconGeometryProperty = BindableProperty.Create(
        nameof(IconGeometry),
        typeof(string),
        typeof(ProfessorHexTile),
        string.Empty,
        propertyChanged: OnIconGeometryChanged);
    public static readonly BindableProperty GlassProperty = BindableProperty.Create(nameof(Glass), typeof(bool), typeof(ProfessorHexTile), false, propertyChanged: OnGlassChanged);

    private readonly HexGlassDrawable vidrio = new();

    public ProfessorHexTile()
    {
        InitializeComponent();
        Vidrio.Drawable = vidrio;
    }

    public event EventHandler? Tapped;
    public string Text { get => (string)GetValue(TextProperty); set => SetValue(TextProperty, value); }
    public Color AccentColor { get => (Color)GetValue(AccentColorProperty); set => SetValue(AccentColorProperty, value); }
    public string IconGeometry { get => (string)GetValue(IconGeometryProperty); set => SetValue(IconGeometryProperty, value); }

    /// <summary>Material Liquid Glass (cuerpo del acento translúcido, reflejo, canto y resplandor). Falso: el hexágono blanco de siempre.</summary>
    public bool Glass { get => (bool)GetValue(GlassProperty); set => SetValue(GlassProperty, value); }

    private static void OnIconGeometryChanged(BindableObject bindable, object oldValue, object newValue)
    {
        if (bindable is not ProfessorHexTile tile || newValue is not string data || string.IsNullOrWhiteSpace(data)) return;
        var converter = new PathGeometryConverter();
        tile.IconPath.Data = converter.ConvertFromInvariantString(data) as Geometry;
    }

    private static void OnGlassChanged(BindableObject bindable, object oldValue, object newValue) => ((ProfessorHexTile)bindable).AplicarMaterial();

    /// <summary>El material blanco no se toca al cambiar el acento (el icono va enlazado); el de vidrio se repinta.</summary>
    private static void OnAccentColorChanged(BindableObject bindable, object oldValue, object newValue)
    {
        if (bindable is ProfessorHexTile { Glass: true } tile) tile.AplicarMaterial();
    }

    private void AplicarMaterial()
    {
        var conVidrio = Glass;
        var acento = AccentColor ?? Colors.Black;
        Sombra1.IsVisible = Sombra2.IsVisible = Sombra3.IsVisible = Cuerpo.IsVisible = !conVidrio;
        Vidrio.IsVisible = conVidrio;
        if (conVidrio)
        {
            vidrio.Accent = acento;
            Vidrio.Invalidate();
            var tinta = Design.Glass.TintaSobre(acento);
            IconPath.Fill = new SolidColorBrush(tinta);
            Etiqueta.TextColor = tinta;
            Etiqueta.FontFamily = Design.Ds.FuenteSemi;
            Etiqueta.FontAttributes = FontAttributes.None;
            Etiqueta.Shadow = tinta == Colors.White ? Design.Glass.SombraTexto(0.30) : null!;
        }
        else
        {
            IconPath.SetBinding(Path.FillProperty, new Binding(nameof(AccentColor), source: this));
            Etiqueta.TextColor = Color.FromArgb("#3F3F46");
            Etiqueta.FontFamily = "InterMedium";
            Etiqueta.FontAttributes = FontAttributes.Bold;
            Etiqueta.Shadow = null!;
        }
    }

    private async void OnTapped(object? sender, TappedEventArgs e)
    {
        await TileRoot.ScaleToAsync(0.97, 60, Easing.CubicOut);
        await TileRoot.ScaleToAsync(1, 90, Easing.CubicOut);
        Tapped?.Invoke(this, EventArgs.Empty);
    }

    private async void OnPointerEntered(object? sender, PointerEventArgs e) => await TileRoot.ScaleToAsync(1.04, 120, Easing.CubicOut);
    private async void OnPointerExited(object? sender, PointerEventArgs e) => await TileRoot.ScaleToAsync(1, 120, Easing.CubicOut);
}

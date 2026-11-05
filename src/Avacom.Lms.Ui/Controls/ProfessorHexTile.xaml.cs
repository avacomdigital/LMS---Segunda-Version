using Avacom.Lms.Ui.Graphics;
using Microsoft.Maui.Controls.Shapes;
using Path = Microsoft.Maui.Controls.Shapes.Path;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Hexágono del panal (Aula · Design System, 146 × 168) con icono vectorial de color y etiqueta en tinta. Dos
/// materiales: el blanco que flota con sombra difusa (menú principal y Asignaturas) y, con <see cref="Glass"/>, el
/// lleno de rol: degradado 600 → 700 del acento con sombra difusa del mismo color (<see cref="HexGlassDrawable"/>),
/// icono y texto en blanco (o tinta oscura sobre amarillo). La geometría es la misma en ambos.
/// Interacciones del DS: encima sube 6 · pulsado 0,97 · vuelta en 120 ms.
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
    public static readonly BindableProperty IconSourceProperty = BindableProperty.Create(nameof(IconSource), typeof(ImageSource), typeof(ProfessorHexTile), null, propertyChanged: OnGlassChanged);

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

    /// <summary>Icono sólido del catálogo del DS (p. ej. <c>ico_libros.png</c>). Si se da, sustituye al trazado de <see cref="IconGeometry"/>.</summary>
    public ImageSource? IconSource { get => (ImageSource?)GetValue(IconSourceProperty); set => SetValue(IconSourceProperty, value); }

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
        var conImagen = IconSource is not null;
        IconoImagen.Source = IconSource;
        IconoImagen.IsVisible = conImagen;
        IconoCirculo.IsVisible = conImagen && conVidrio;
        IconPath.IsVisible = !conImagen;
        if (conVidrio)
        {
            vidrio.Accent = acento;
            Vidrio.Invalidate();
            var tinta = Design.Glass.TintaSobre(acento);
            IconPath.Fill = new SolidColorBrush(tinta);
            Etiqueta.TextColor = tinta;
            Etiqueta.FontFamily = Design.Ds.FuenteMedia;
            Etiqueta.FontAttributes = FontAttributes.None;
            Etiqueta.Shadow = null!;
        }
        else
        {
            IconPath.SetBinding(Path.FillProperty, new Binding(nameof(AccentColor), source: this));
            Etiqueta.TextColor = Design.Ds.Tinta;
            Etiqueta.FontFamily = Design.Ds.FuenteMedia;
            Etiqueta.FontAttributes = FontAttributes.None;
            Etiqueta.Shadow = null!;
        }
    }

    private async void OnTapped(object? sender, TappedEventArgs e)
    {
        await TileRoot.ScaleToAsync(0.97, 60, Easing.CubicOut);
        await TileRoot.ScaleToAsync(1, 90, Easing.CubicOut);
        Tapped?.Invoke(this, EventArgs.Empty);
    }

    private async void OnPointerEntered(object? sender, PointerEventArgs e) => await TileRoot.TranslateToAsync(0, -6, Design.Ds.DurBase, Easing.CubicOut);
    private async void OnPointerExited(object? sender, PointerEventArgs e) => await TileRoot.TranslateToAsync(0, 0, Design.Ds.DurBase, Easing.CubicOut);
}

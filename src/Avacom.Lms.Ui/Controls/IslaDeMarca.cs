using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;
using Path = Microsoft.Maui.Controls.Shapes.Path;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Isla de marca del Aula · Design System: el logo AVACOM original, centrado y unido al borde superior, en una muesca
/// con el radio inferior y dos curvas de unión cóncavas con el borde. Siempre visible y sin interacción.
/// Pizarra 360 × 88 · radio 32 · curvas 28 · logo 210. Tableta (<see cref="Compacta"/>) 220 × 60 · radio 22 · curvas 20 · logo 128.
/// Con el neumorfismo activo (el del aula) la muesca toma la base neumórfica, con sombra abajo a la derecha y luz arriba a
/// la izquierda; se colocan dos muescas iguales superpuestas porque MAUI admite una sola sombra por elemento.
/// Se pone en la fila superior de la página con <c>VerticalOptions="Start"</c>; no ocupa ancho fuera de la muesca.
/// </summary>
public sealed class IslaDeMarca : Grid
{
    public static readonly BindableProperty CompactaProperty =
        BindableProperty.Create(nameof(Compacta), typeof(bool), typeof(IslaDeMarca), false, propertyChanged: (b, _, _) => ((IslaDeMarca)b).Construir());

    public IslaDeMarca()
    {
        InputTransparent = true;
        HorizontalOptions = LayoutOptions.Center;
        VerticalOptions = LayoutOptions.Start;
        ZIndex = 35;
        Construir();
    }

    /// <summary>Tamaño de tableta (220 × 60) en lugar del de pizarra (360 × 88).</summary>
    public bool Compacta { get => (bool)GetValue(CompactaProperty); set => SetValue(CompactaProperty, value); }

    private void Construir()
    {
        Children.Clear();
        ColumnDefinitions.Clear();
        var (ancho, alto, radio, curva, logo) = Compacta ? (220d, 60d, 22d, 20d, 128d) : (360d, 88d, 32d, 28d, 210d);
        ColumnDefinitions = [new ColumnDefinition(curva), new ColumnDefinition(ancho), new ColumnDefinition(curva)];
        HeightRequest = alto;

        var forma = new RoundRectangle { CornerRadius = new CornerRadius(0, 0, radio, radio) };
        var luz = new Border
        {
            BackgroundColor = Ds.NeuBase, StrokeThickness = 0, StrokeShape = forma,
            Shadow = new Shadow { Brush = new SolidColorBrush(Ds.NeuLuz), Offset = new Point(-6, -2), Radius = 16, Opacity = 1f },
        };
        var muesca = new Border
        {
            BackgroundColor = Ds.NeuBase, StrokeThickness = 0, StrokeShape = new RoundRectangle { CornerRadius = new CornerRadius(0, 0, radio, radio) },
            Shadow = new Shadow { Brush = new SolidColorBrush(Ds.NeuOscura), Offset = new Point(7, 8), Radius = 18, Opacity = 1f },
            Content = new Image { Source = "avacom_logo.png", Aspect = Aspect.AspectFit, WidthRequest = logo, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
        };
        this.Add(luz, 1, 0);
        this.Add(muesca, 1, 0);

        // Curvas de unión: el cuadrado de la curva menos el cuarto de círculo centrado abajo, hacia fuera de la muesca.
        this.Add(Curva($"M0,0 L{curva},0 L{curva},{curva} A{curva},{curva} 0 0 0 0,0 Z", curva), 0, 0);
        this.Add(Curva($"M0,0 L{curva},0 A{curva},{curva} 0 0 0 0,{curva} Z", curva), 2, 0);
    }

    private static Path Curva(string datos, double lado) => new()
    {
        Data = (Geometry)new PathGeometryConverter().ConvertFromInvariantString(datos)!,
        Fill = new SolidColorBrush(Ds.NeuBase), StrokeThickness = 0, Aspect = Stretch.None,
        WidthRequest = lado, HeightRequest = lado, VerticalOptions = LayoutOptions.Start, HorizontalOptions = LayoutOptions.Fill,
    };
}

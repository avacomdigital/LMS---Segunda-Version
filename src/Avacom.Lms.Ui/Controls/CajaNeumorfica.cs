using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Píldora neumórfica del Aula · Design System para las esquinas superiores (fecha y hora, avatar, modo): la misma
/// base que el fondo (<see cref="Ds.NeuBase"/>), luz blanca arriba a la izquierda y sombra #A3B1C6 al 55 % abajo a la
/// derecha, radio 24. MAUI admite una sola sombra por elemento, así que son dos <see cref="Border"/> con la misma forma
/// superpuestos (el de la luz detrás), como indica el DS. Sólo se usa en la isla de marca y en las esquinas.
/// </summary>
[ContentProperty(nameof(Interior))]
public class CajaNeumorfica : ContentView
{
    public static readonly BindableProperty RadioProperty =
        BindableProperty.Create(nameof(Radio), typeof(double), typeof(CajaNeumorfica), 24.0, propertyChanged: (b, _, _) => ((CajaNeumorfica)b).Aplicar());
    public static readonly BindableProperty RellenoProperty =
        BindableProperty.Create(nameof(Relleno), typeof(Thickness), typeof(CajaNeumorfica), new Thickness(22, 10), propertyChanged: (b, _, _) => ((CajaNeumorfica)b).Aplicar());

    private readonly Border luz;
    private readonly Border cuerpo;

    public CajaNeumorfica()
    {
        luz = new Border
        {
            InputTransparent = true, BackgroundColor = Ds.NeuBase, StrokeThickness = 0,
            Shadow = new Shadow { Brush = new SolidColorBrush(Ds.NeuLuz), Offset = new Point(-7, -7), Radius = 16, Opacity = 1f },
        };
        cuerpo = new Border
        {
            BackgroundColor = Ds.NeuBase, StrokeThickness = 0,
            Shadow = new Shadow { Brush = new SolidColorBrush(Ds.NeuOscura), Offset = new Point(7, 7), Radius = 16, Opacity = 1f },
        };
        base.Content = new Grid { Children = { luz, cuerpo } };
        Aplicar();
    }

    /// <summary>Radio de la píldora (24 por defecto).</summary>
    public double Radio { get => (double)GetValue(RadioProperty); set => SetValue(RadioProperty, value); }

    /// <summary>Aire entre el borde de la píldora y el contenido.</summary>
    public Thickness Relleno { get => (Thickness)GetValue(RellenoProperty); set => SetValue(RellenoProperty, value); }

    /// <summary>Lo que va dentro de la píldora.</summary>
    public View? Interior { get => cuerpo.Content as View; set => cuerpo.Content = value; }

    private void Aplicar()
    {
        luz.StrokeShape = new RoundRectangle { CornerRadius = Radio };
        cuerpo.StrokeShape = new RoundRectangle { CornerRadius = Radio };
        cuerpo.Padding = Relleno;
    }
}

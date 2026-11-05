using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Fondo «Aurora» del Aula · Design System, el predeterminado de pizarra y tableta: el fondo elegido (Nube, #EAF0F6) con cuatro
/// radiales de marca (azul, magenta, verde y amarillo) al 7–13 %, estáticos. Va en la capa más baja de la página,
/// a pantalla completa y sin captar toques. No se usa en Evaluar, exámenes, bloqueo ni monitoreo (ahí el fondo es
/// liso) ni en el acceso (hexágonos de marca).
/// </summary>
public sealed class FondoAurora : Grid
{
    public FondoAurora()
    {
        InputTransparent = true;
        HorizontalOptions = LayoutOptions.Fill;
        VerticalOptions = LayoutOptions.Fill;
        BackgroundColor = Ds.Fondo;
        Add(Radial(Ds.Azul500, 0.11f, new Point(0.08, 0.05)));
        Add(Radial(Ds.Magenta500, 0.08f, new Point(0.95, 0.10)));
        Add(Radial(Ds.Verde500, 0.09f, new Point(0.05, 0.98)));
        Add(Radial(Ds.Amarillo500, 0.13f, new Point(0.92, 0.95)));
    }

    private static BoxView Radial(Color color, float alfa, Point centro) => new()
    {
        InputTransparent = true,
        Color = Colors.Transparent,
        Background = new RadialGradientBrush(
            new GradientStopCollection { new GradientStop(color.WithAlpha(alfa), 0f), new GradientStop(color.WithAlpha(0f), 1f) },
            centro, 0.65),
    };
}

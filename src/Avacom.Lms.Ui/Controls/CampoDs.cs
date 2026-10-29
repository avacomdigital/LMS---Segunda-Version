using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Campo de texto del Aula · Design System: caja blanca con contorno completo de 2 px en <see cref="Ds.Linea"/> y radio
/// m 16; al enfocar, el contorno pasa al azul de foco. Envuelve el <see cref="Entry"/> que se le pone dentro, que debe
/// llevar <c>ClassId="neumo"</c> para que <see cref="NeumoChrome"/> le quite el borde y el subrayado nativos. El
/// <see cref="Entry"/> sigue siendo el mismo control (nombre, eventos y AutomationId no cambian).
/// </summary>
public sealed class CampoDs : Border
{
    static CampoDs() => NeumoChrome.Registrar();

    public CampoDs()
    {
        BackgroundColor = Ds.Superficie;
        Stroke = new SolidColorBrush(Ds.Linea);
        StrokeThickness = 2;
        StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioM };
        Padding = new Thickness(16, 0);
        MinimumHeightRequest = 56;
    }

    protected override void OnPropertyChanged(string? propertyName = null)
    {
        base.OnPropertyChanged(propertyName);
        if (propertyName != nameof(Content) || Content is not Entry campo) return;
        campo.BackgroundColor = Colors.Transparent;
        campo.Focused += (_, _) => Stroke = new SolidColorBrush(Ds.Foco);
        campo.Unfocused += (_, _) => Stroke = new SolidColorBrush(Ds.Linea);
    }
}

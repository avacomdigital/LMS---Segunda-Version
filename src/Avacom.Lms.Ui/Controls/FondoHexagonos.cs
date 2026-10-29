using Avacom.Lms.Ui.Design;
using Avacom.Lms.Ui.Graphics;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Efecto «Hexágonos de marca» del Aula · Design System para el acceso y las portadas: sobre el fondo elegido, cuatro
/// hexágonos grandes de puntas redondeadas, de los colores del logo al 8–14 %, estáticos y medio fuera de los bordes
/// para no competir con el contenido. Un solo efecto por pantalla; no capta toques.
/// </summary>
public sealed class FondoHexagonos : GraphicsView
{
    public FondoHexagonos()
    {
        InputTransparent = true;
        HorizontalOptions = LayoutOptions.Fill;
        VerticalOptions = LayoutOptions.Fill;
        BackgroundColor = Ds.Fondo;
        Drawable = new HexagonosDeMarcaDrawable();
    }
}

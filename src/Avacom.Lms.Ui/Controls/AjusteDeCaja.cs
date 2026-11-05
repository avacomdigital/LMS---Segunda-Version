namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// La caja centrada de las pantallas de acceso cabe SIEMPRE entera en el área segura, sin desplazamiento: si la ventana es más baja que
/// el contenido (p. ej. el paso del PIN con su teclado), la caja se reduce a escala en vez de cortarse. La caja ocupa todas las filas de
/// la escena y se desplaza al centro del área segura (entre la franja de arriba y la de abajo). Sólo visual: no cambia ningún control.
/// </summary>
public static class AjusteDeCaja
{
    public static void Encajar(Grid escena, View caja, View contenido, double arriba, double abajo)
    {
        Grid.SetRow(caja, 0);
        Grid.SetRowSpan(caja, Math.Max(1, escena.RowDefinitions.Count));
        caja.TranslationY = (arriba - abajo) / 2;

        var pendiente = false;
        void Pedir()
        {
            if (pendiente) return;
            pendiente = true;
            escena.Dispatcher.Dispatch(() => { pendiente = false; Ajustar(); });
        }

        void Ajustar()
        {
            if (escena.Height <= 0 || escena.Width <= 0) return;
            // El relleno y el borde de la caja (si es un Border) también ocupan.
            var relleno = caja is Border borde ? borde.Padding : new Thickness(0);
            var filo = caja is Border b2 ? b2.StrokeThickness * 2 : 2;
            var anchoCaja = caja.Width > 0 ? caja.Width : (caja.WidthRequest > 0 ? Math.Min(caja.WidthRequest, escena.Width) : escena.Width);
            var ancho = anchoCaja - relleno.HorizontalThickness - filo;
            var alto = ((IView)contenido).Measure(ancho, double.PositiveInfinity).Height + relleno.VerticalThickness + filo;
            if (alto <= 0 || double.IsInfinity(alto)) return;
            var disponible = Math.Max(120, escena.Height - arriba - abajo - 16);
            var escala = Math.Min(1, disponible / alto);
            if (Math.Abs(caja.HeightRequest - alto) > 0.5) caja.HeightRequest = alto;
            // Si la caja es más alta que la escena, el margen negativo le da sitio para no recortarse antes de la escala.
            var sobra = Math.Max(0, alto - escena.Height) / 2;
            if (Math.Abs(caja.Margin.Top + sobra) > 0.5) caja.Margin = new Thickness(caja.Margin.Left, -sobra, caja.Margin.Right, -sobra);
            if (Math.Abs(caja.Scale - escala) > 0.001) caja.Scale = escala;
        }

        escena.SizeChanged += (_, _) => Pedir();
        contenido.MeasureInvalidated += (_, _) => Pedir();
    }
}

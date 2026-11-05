using System.Globalization;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Esquina superior izquierda de la pizarra (Aula · Design System): fecha y hora, sólo información, en una píldora
/// neumórfica. La fecha va como antetítulo (mayúsculas 11 px con tracking) y la hora en Lexend 600. Se actualiza sola
/// cada 15 s mientras está en pantalla.
/// </summary>
public sealed class EsquinaFechaHora : CajaNeumorfica
{
    private static readonly CultureInfo Es = CultureInfo.GetCultureInfo("es-CO");
    private readonly Label fecha = new() { FontFamily = Ds.FuenteSemi, FontSize = 11, CharacterSpacing = 1.6, TextColor = Ds.Tinta2, TextTransform = TextTransform.Uppercase };
    private readonly Label hora = new() { FontFamily = Ds.FuenteSemi, FontSize = 24, TextColor = Ds.Tinta };
    private IDispatcherTimer? reloj;

    public EsquinaFechaHora()
    {
        InputTransparent = true;
        HorizontalOptions = LayoutOptions.Start;
        VerticalOptions = LayoutOptions.Start;
        Interior = new VerticalStackLayout { Spacing = 0, Children = { fecha, hora } };
        Actualizar();
        Loaded += (_, _) =>
        {
            reloj ??= Dispatcher.CreateTimer();
            reloj.Interval = TimeSpan.FromSeconds(15);
            reloj.Tick -= AlTick;
            reloj.Tick += AlTick;
            reloj.Start();
            Actualizar();
        };
        Unloaded += (_, _) => reloj?.Stop();
    }

    private void AlTick(object? sender, EventArgs e) => Actualizar();

    private void Actualizar()
    {
        var ahora = DateTime.Now;
        fecha.Text = ahora.ToString("dddd d 'de' MMMM", Es);
        hora.Text = ahora.ToString("H:mm", Es);
    }
}

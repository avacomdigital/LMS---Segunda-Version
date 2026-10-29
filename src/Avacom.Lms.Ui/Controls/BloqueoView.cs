using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// La pantalla de bloqueo del alumno (CAP-042 · FUN-074): «Mira al frente». Cubre todo,
/// sin cuenta regresiva ni botones. Se muestra mientras la sesión declare
/// <c>pantallas_bloqueadas: true</c> y desaparece sola al liberar.
/// </summary>
public sealed class BloqueoView : ContentView
{
    private readonly Label _detalle;

    public BloqueoView()
    {
        var pila = new VerticalStackLayout { Spacing = 14, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center, Padding = 40 };
        pila.Add(new Label { Text = "◉", FontSize = 96, TextColor = Colors.White, HorizontalTextAlignment = TextAlignment.Center });
        pila.Add(new Label { Text = "Mira al frente", FontSize = 40, FontFamily = Ds.FuenteSemi, TextColor = Colors.White, HorizontalTextAlignment = TextAlignment.Center });
        _detalle = new Label { Text = "Tu profesor está explicando. Tu trabajo sigue guardado.", FontSize = 20, TextColor = Color.FromArgb("#E3E6EC"), HorizontalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.WordWrap };
        pila.Add(_detalle);
        Content = new Grid { BackgroundColor = Color.FromArgb("#1F2433"), Children = { pila } };
        IsVisible = false;
    }

    public void Mostrar(string? detalle = null)
    {
        if (!string.IsNullOrWhiteSpace(detalle)) _detalle.Text = detalle;
        IsVisible = true;
    }

    public void Ocultar() => IsVisible = false;
}

using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Diálogo del Aula · Design System en lugar del cuadro nativo de Windows: velo de tinta, caja blanca centrada (radio 24, sombra difusa),
/// título, mensaje y las acciones en píldora. La de aceptar es la principal (verde) o de peligro (rojo) si borra, expulsa o termina algo;
/// la de cancelar es secundaria. Mismo contrato que <c>DisplayAlertAsync</c>: devuelve true si se toca la de aceptar.
/// </summary>
public static class DialogoDs
{
    private static readonly string[] Peligrosas = ["Terminar", "Expulsar", "Descartar", "Anular", "Eliminar", "Borrar", "Reprocesar", "Reproducir", "Cerrar", "Salir", "Devolver"];

    public static Task AlertaAsync(this Page pagina, string titulo, string? mensaje, string cerrar) =>
        MostrarAsync(pagina, titulo, mensaje, null, cerrar);

    public static Task<bool> AlertaAsync(this Page pagina, string titulo, string? mensaje, string aceptar, string cancelar) =>
        MostrarAsync(pagina, titulo, mensaje, aceptar, cancelar);

    private static async Task<bool> MostrarAsync(Page pagina, string titulo, string? mensaje, string? aceptar, string cancelar)
    {
        var resultado = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var modal = new Velo { BackgroundColor = Ds.Tinta.WithAlpha(0.45f) };
        Shell.SetNavBarIsVisible(modal, false);
        NavigationPage.SetHasNavigationBar(modal, false);

        var cerrando = false;
        async Task Cerrar(bool valor)
        {
            if (cerrando) return;
            cerrando = true;
            // Primero se quita el velo y después se responde: quien preguntó puede navegar en cuanto tiene la respuesta.
            try { await modal.Navigation.PopModalAsync(false); } catch (Exception) { }
            resultado.TrySetResult(valor);
        }

        modal.AlVolver = () => Cerrar(false);

        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(new Label
        {
            Text = titulo, FontFamily = Ds.FuenteSemi, FontSize = 24, TextColor = Ds.Tinta,
            HorizontalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.WordWrap,
        });
        if (!string.IsNullOrWhiteSpace(mensaje))
            pila.Add(new Label
            {
                Text = mensaje, FontFamily = Ds.FuenteRegular, FontSize = 17, TextColor = Ds.TintaMedia,
                HorizontalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.WordWrap,
            });

        var acciones = new HorizontalStackLayout { Spacing = 12, HorizontalOptions = LayoutOptions.Center, Margin = new Thickness(0, 12, 0, 0) };
        if (aceptar is null)
            acciones.Add(Ancho(Ds.Boton(cancelar, Ds.Rango.Primary, async (_, _) => await Cerrar(false), 56)));
        else
        {
            acciones.Add(Ancho(Ds.Boton(cancelar, Ds.Rango.Secondary, async (_, _) => await Cerrar(false), 56)));
            var peligro = Peligrosas.Any(p => aceptar.StartsWith(p, StringComparison.OrdinalIgnoreCase));
            acciones.Add(Ancho(Ds.Boton(aceptar, peligro ? Ds.Rango.Destructive : Ds.Rango.Primary, async (_, _) => await Cerrar(true), 56)));
        }
        pila.Add(acciones);

        modal.Content = new Border
        {
            BackgroundColor = Colors.White, Stroke = new SolidColorBrush(Ds.Linea), StrokeThickness = 1,
            StrokeShape = new RoundRectangle { CornerRadius = 24 }, Padding = new Thickness(36, 32),
            WidthRequest = 560, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center,
            Shadow = new Shadow { Brush = new SolidColorBrush(Ds.Tinta), Opacity = 0.18f, Offset = new Point(0, 14), Radius = 32 },
            Content = pila,
        };

        try { await pagina.Navigation.PushModalAsync(modal, false); }
        catch (Exception)
        {
            // Sin pila de navegación disponible: el cuadro nativo, para no perder la pregunta.
            return aceptar is null ? await pagina.DisplayAlertAsync(titulo, mensaje, cancelar).ContinueWith(_ => false) : await pagina.DisplayAlertAsync(titulo, mensaje, aceptar, cancelar);
        }
        return await resultado.Task;
    }

    /// <summary>El botón crece con su texto (nunca se corta) y no baja de 180.</summary>
    private static Button Ancho(Button b) { b.MinimumWidthRequest = 180; return b; }

    /// <summary>La página del velo: «atrás» (Esc o el botón del sistema) cuenta como cancelar.</summary>
    private sealed class Velo : ContentPage
    {
        public Func<Task>? AlVolver { get; set; }

        protected override bool OnBackButtonPressed()
        {
            _ = AlVolver?.Invoke();
            return true;
        }
    }
}

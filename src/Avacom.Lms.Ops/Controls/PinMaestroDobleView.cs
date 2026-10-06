using Avacom.Lms.Ops.Acceso;
using Avacom.Lms.Ui.Controls;

namespace Avacom.Lms.Ops.Controls;

/// <summary>
/// Configurar o cambiar el PIN maestro (RF-01 paso 4, RF-08): el teclado propio dos veces, marcar y confirmar. Un PIN trivial se avisa al marcarlo, antes
/// de pedir la confirmación (RN-05 explicada con palabras); si la confirmación no coincide se vuelve a empezar. Lo que el nodo diga después (<c>pin_debil</c>
/// porque se repite uno de los tres últimos, por ejemplo) lo muestra la pantalla y llama a <see cref="Reiniciar"/>. El PIN sólo vive en memoria hasta
/// entregarse con <see cref="PinConfirmado"/>.
/// </summary>
public sealed class PinMaestroDobleView : ContentView
{
    private readonly TecladoPinView _teclado = MarcoDeAcceso.TecladoMaestro();
    private readonly Label _indicacion = new() { FontSize = 15, FontAttributes = FontAttributes.Bold, HorizontalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.WordWrap };
    private readonly Label _problema = new() { FontSize = 13, TextColor = Color.FromArgb("#8A1C1F"), HorizontalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.WordWrap, IsVisible = false };
    private string? _primero;

    /// <summary>Las dos marcas coincidieron y pasaron la regla local. Quien lo recibe lo envía al nodo.</summary>
    public event EventHandler<string>? PinConfirmado;

    public string TextoMarcar { get; set; } = "Marca el PIN maestro.";
    public string TextoConfirmar { get; set; } = "Márcalo otra vez para confirmar.";

    public PinMaestroDobleView()
    {
        _teclado.PinCompleto += AlCompletar;
        Content = new VerticalStackLayout { Spacing = 10, Children = { _indicacion, _problema, _teclado } };
        Reiniciar();
    }

    public bool Habilitado { get => _teclado.Habilitado; set => _teclado.Habilitado = value; }

    /// <summary>Vuelve a «marcar» y olvida lo marcado; <paramref name="problema"/> dice por qué (o nada).</summary>
    public void Reiniciar(string? problema = null)
    {
        _primero = null;
        _teclado.Limpiar();
        _indicacion.Text = TextoMarcar;
        _problema.Text = problema ?? string.Empty;
        _problema.IsVisible = !string.IsNullOrWhiteSpace(problema);
    }

    private async void AlCompletar(object? sender, string pin)
    {
        if (_primero is null)
        {
            if (PinMaestroLocal.Problema(pin) is { } problema)
            {
                await _teclado.SacudirAsync();
                Reiniciar(problema);
                return;
            }
            _primero = pin;
            _teclado.Limpiar();
            _indicacion.Text = TextoConfirmar;
            _problema.IsVisible = false;
            return;
        }
        if (pin != _primero)
        {
            await _teclado.SacudirAsync();
            Reiniciar("Las dos veces no coinciden. Márcalo de nuevo desde el principio.");
            return;
        }
        _primero = null;
        _teclado.Limpiar();
        PinConfirmado?.Invoke(this, pin);
    }
}

using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Acceso;
using Avacom.Lms.Ops.Controls;
using Avacom.Lms.Ui.Controls;
using Tono = Avacom.Lms.Ops.Controls.MarcoDeAcceso.Tono;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// «Olvidé mi contraseña» (RF-07 · RN-24 · RN-25 · RB-14): el profesor da su documento, el PIN maestro y su contraseña nueva dos veces; el nodo cierra todas
/// sus sesiones y vuelve al acceso con «Listo. Cerramos tus sesiones abiertas…». No existe un «verificar PIN» (D-A6): el PIN viaja con la contraseña nueva, así
/// que se marca en el paso 2 y se guarda SÓLO en memoria hasta enviarlo; si el nodo lo rechaza se vuelve a ese paso con los intentos que quedan, y si rechaza
/// la contraseña el PIN se conserva para no tener que marcarlo otra vez. Administración y técnico no se restablecen así (RN-12): el nodo contesta igual que a
/// un documento que no existe.
/// </summary>
public sealed class RestablecerContrasenaPage : ContentPage
{
    private const int PasoDocumento = 1, PasoPin = 2, PasoClave = 3;

    private readonly MarcoDeAcceso _marco = new();
    private readonly MarcoDeAcceso.Estado _estado = new();
    private readonly VerticalStackLayout _pasoDocumento = new() { Spacing = 8 };
    private readonly VerticalStackLayout _pasoPin = new() { Spacing = 8 };
    private readonly VerticalStackLayout _pasoClave = new() { Spacing = 8 };
    private readonly Entry _documento = MarcoDeAcceso.Campo("Tu número de documento", "Documento");
    private readonly Entry _clave = MarcoDeAcceso.Campo("Tu contraseña nueva", "Contraseña nueva", secreto: true);
    private readonly Entry _repetida = MarcoDeAcceso.Campo("Escríbela otra vez", "Repite la contraseña nueva", secreto: true);
    private readonly Label _reglaClave = MarcoDeAcceso.Nota(string.Empty);
    private readonly TecladoPinView _teclado = MarcoDeAcceso.TecladoMaestro();
    private readonly Button _cambiar;
    private string? _pin;
    private bool _ocupado;

    public RestablecerContrasenaPage()
    {
        Shell.SetNavBarIsVisible(this, false);
        Title = "Olvidé mi contraseña";
        Content = _marco;
        _marco.Titulo.Text = "Olvidé mi contraseña";

        _pasoDocumento.Add(MarcoDeAcceso.Rotulo("Documento"));
        _pasoDocumento.Add(_documento);
        _pasoDocumento.Add(MarcoDeAcceso.Principal("Siguiente", (_, _) => ConfirmarDocumento()).Vista);
        _pasoDocumento.Add(MarcoDeAcceso.Discreta("Volver al acceso", async (_, _) => await Shell.Current.GoToAsync("..")));
        _documento.Completed += (_, _) => ConfirmarDocumento();

        _teclado.PinCompleto += (_, pin) => { _pin = pin; _estado.Mostrar(null); Mostrar(PasoClave); };
        _pasoPin.Add(new Label { Text = "Marca el PIN maestro de la escuela.", FontSize = 15, FontAttributes = FontAttributes.Bold, HorizontalTextAlignment = TextAlignment.Center });
        _pasoPin.Add(_teclado);
        _pasoPin.Add(MarcoDeAcceso.Discreta("Atrás", (_, _) => { _pin = null; Mostrar(PasoDocumento); }));

        _pasoClave.Add(MarcoDeAcceso.Rotulo("Contraseña nueva"));
        _pasoClave.Add(_clave);
        _pasoClave.Add(MarcoDeAcceso.Rotulo("Repite la contraseña nueva"));
        _pasoClave.Add(_repetida);
        _pasoClave.Add(_reglaClave);
        var (vista, boton) = MarcoDeAcceso.Principal("Cambiar mi contraseña", async (_, _) => await RestablecerAsync());
        _cambiar = boton;
        _pasoClave.Add(vista);
        _pasoClave.Add(MarcoDeAcceso.Discreta("Atrás", (_, _) => { _pin = null; Mostrar(PasoPin); }));
        _repetida.Completed += async (_, _) => await RestablecerAsync();

        _marco.Cuerpo.Add(_estado);
        foreach (var p in new[] { _pasoDocumento, _pasoPin, _pasoClave }) _marco.Cuerpo.Add(p);
    }

    private int Minimo => ContrasenaNueva.Minimo(Sesion.Configuracion, "teacher", 8);

    protected override void OnAppearing()
    {
        base.OnAppearing();
        _ = Sesion.RegistrarEquipoAsync();   // RN-11, antes de enviar el PIN
        if (!_pasoPin.IsVisible && !_pasoClave.IsVisible) Mostrar(PasoDocumento);
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _pin = null;
        _teclado.Limpiar();
        _clave.Text = _repetida.Text = string.Empty;
    }

    private void Mostrar(int paso)
    {
        _pasoDocumento.IsVisible = paso == PasoDocumento;
        _pasoPin.IsVisible = paso == PasoPin;
        _pasoClave.IsVisible = paso == PasoClave;
        _teclado.Limpiar();
        _teclado.Habilitado = true;
        _marco.Mensaje.Text = paso switch
        {
            PasoDocumento => "Paso 1 de 3 · Tu documento. Así sabemos de qué profesor es la contraseña.",
            PasoPin => "Paso 2 de 3 · El PIN maestro de la escuela. Si no lo tienes, pide el PIN maestro a administración.",
            _ => "Paso 3 de 3 · Tu contraseña nueva. Al cambiarla cerramos tus sesiones abiertas en otros equipos.",
        };
        _reglaClave.Text = $"Al menos {Minimo} caracteres, con una mayúscula y un símbolo.";
    }

    private void ConfirmarDocumento()
    {
        if (string.IsNullOrWhiteSpace(_documento.Text)) { _estado.Mostrar("Escribe tu documento para seguir.", Tono.Aviso); _documento.Focus(); return; }
        _estado.Mostrar(null);
        Mostrar(PasoPin);
    }

    private async Task RestablecerAsync()
    {
        if (_ocupado) return;
        if (_pin is null) { Mostrar(PasoPin); return; }
        if (ContrasenaNueva.Problema(_clave.Text, _repetida.Text, Minimo) is { } problema)
        {
            _estado.Mostrar(problema, Tono.Aviso);
            _repetida.Text = string.Empty;
            return;
        }
        _ocupado = true;
        _cambiar.IsEnabled = false;
        _estado.Mostrar("Cambiando tu contraseña…", Tono.Neutro);
        try
        {
            await Sesion.AsegurarEquipoAsync();
            var acceso = Sesion.Acceso;
            var cerradas = await acceso.RestablecerContrasenaDocenteAsync(_pin, (_documento.Text ?? string.Empty).Trim(), _clave.Text!, Sesion.Dispositivo);
            if (cerradas is null)
            {
                var error = acceso.UltimoError;
                var texto = MensajesDeAcceso.Texto(error);
                if (error is null or { Estado: 0 })
                {
                    // Sin conexión: todo se conserva, también el PIN, para reintentar con un toque (RF-00e).
                    _estado.Mostrar(texto + " Toca «Cambiar mi contraseña» cuando vuelva.", Tono.Problema);
                    return;
                }
                switch (error.Codigo)
                {
                    case "secreto_debil" or "datos_invalidos":
                        _repetida.Text = string.Empty;   // el PIN se conserva: no hace falta marcarlo otra vez
                        _estado.Mostrar(texto, Tono.Problema);
                        return;
                    case "no_encontrado":
                        _pin = null;
                        Mostrar(PasoDocumento);
                        _estado.Mostrar(texto, Tono.Problema);
                        return;
                    case "pin_maestro_bloqueado":
                        _pin = null;
                        Mostrar(PasoPin);
                        _teclado.Habilitado = false;
                        _estado.Mostrar(texto, Tono.Problema);
                        return;
                    default:
                        // PIN equivocado (con los intentos que quedan), vencido, sin configurar o desde una tableta: se vuelve al PIN, lo demás se conserva.
                        _pin = null;
                        Mostrar(PasoPin);
                        _teclado.Habilitado = error is not { PinMaestroVencido: true } and not { PinMaestroNoConfigurado: true } and not { DispositivoNoAutorizado: true };
                        _estado.Mostrar(texto, Tono.Problema);
                        return;
                }
            }
            _pin = null;
            _documento.Text = _clave.Text = _repetida.Text = string.Empty;
            Sesion.AvisoDeAcceso = MensajesDeAcceso.ContrasenaRestablecida;
            await Shell.Current.GoToAsync("//login");
        }
        finally
        {
            _cambiar.IsEnabled = true;
            _ocupado = false;
        }
    }
}

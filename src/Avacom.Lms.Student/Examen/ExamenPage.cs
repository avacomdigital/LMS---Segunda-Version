using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Student.Examen;

/// <summary>
/// El examen (PAN-121, PAN-122): <see cref="ExamenView"/> a pantalla completa más lo que la plataforma pone alrededor.
///
///  · <b>Latido</b> cada <c>plan.latido_seg</c> (5 s): da señal al nodo, aprende su reloj, sigue el plan de bloqueo, detecta la suspensión y vacía la cola. Un fallo de red no es un
///    error: es «Guardado en tu tableta».
///  · <b>Sin salida</b>: «Atrás», el gesto de volver y cualquier navegación del Shell se descartan mientras el examen está en curso, suspendido o entregándose. Sólo se sale cuando
///    el nodo confirmó la entrega (o ya entregó), otra tableta lo tomó o un administrador liberó la tableta.
///  · <b>Salida administrativa</b> (kiosk.md §5.3): siete toques en dos segundos sobre el título y el PIN local de ESTA tableta, sin depender del servidor. Sin PIN fijado no hay salida
///    local: el profesor usa el cierre forzado y la tableta se suelta sola al ver el intento entregado.
/// </summary>
public sealed class ExamenPage : ContentPage
{
    private const int ToquesParaSalir = 7;
    private static readonly TimeSpan VentanaDeToques = TimeSpan.FromSeconds(2);

    private readonly ExamenView _vista = new() { AreaTactil = 56 };
    private SesionDeExamen? _sesion;
    private IDispatcherTimer? _latido;
    private bool _latiendo;
    private bool _permitirSalida;
    private readonly List<DateTime> _toques = [];

    public ExamenPage()
    {
        Shell.SetNavBarIsVisible(this, false);
        Shell.SetBackButtonBehavior(this, new BackButtonBehavior { IsVisible = false, IsEnabled = false });
        BackgroundColor = Ds.Lienzo;

        // La zona de la esquina (donde está el título) cuenta los siete toques de la salida administrativa. No tapa nada interactivo.
        var zona = new BoxView { Color = Colors.Transparent, WidthRequest = 260, HeightRequest = 84, HorizontalOptions = LayoutOptions.Start, VerticalOptions = LayoutOptions.Start, Margin = new Thickness(16, 14, 0, 0), AutomationId = "exa-zona-admin" };
        var toque = new TapGestureRecognizer();
        toque.Tapped += async (_, _) => await ContarToqueAsync();
        zona.GestureRecognizers.Add(toque);

        var raiz = new Grid();       // sin relleno: la tarjeta de estado se ancla a los tercios de la ventana completa (el margen lo pone ExamenView)
        raiz.Add(_vista);
        raiz.Add(zona);
        Content = raiz;

        _vista.EntregaTerminada += () => MainThread.BeginInvokeOnMainThread(async () => await IrAEntregaAsync());
        _vista.SalidaPedida += () => MainThread.BeginInvokeOnMainThread(async () => await SalirAsync());
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _sesion = Sesion.ExamenActual;
        if (_sesion is null || _sesion.Fase == FaseDeExamen.SinExamen)
        {
            _permitirSalida = true;
            await Shell.Current.GoToAsync("..");
            return;
        }
        _vista.ResolverUrl = ruta => new Uri(Sesion.BaseUri, ruta.TrimStart('/'));
        _vista.Cargar(_sesion);
        Shell.Current.Navigating += AlNavegar;
        IniciarLatido();
        if (_sesion.Preguntas is null) _ = _sesion.CargarPreguntasAsync();
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        Shell.Current.Navigating -= AlNavegar;
        _latido?.Stop();
        _vista.Soltar();
    }

    /// <summary>Sin salida mientras haya examen: el botón Atrás no hace nada (kiosk.md §3.4: lo ignora la app, no el sistema operativo).</summary>
    protected override bool OnBackButtonPressed() => HayExamen;

    private bool HayExamen => _sesion is { Fase: FaseDeExamen.EnCurso or FaseDeExamen.Suspendido or FaseDeExamen.Entregando } && !_permitirSalida;

    private void AlNavegar(object? remitente, ShellNavigatingEventArgs e)
    {
        if (HayExamen) e.Cancel();
    }

    // ------------------------------------------------------------------------------------ latido

    private void IniciarLatido()
    {
        var segundos = Math.Clamp(_sesion?.Plan?.LatidoSeg ?? 5, 2, 15);
        _latido ??= Dispatcher.CreateTimer();
        _latido.Interval = TimeSpan.FromSeconds(segundos);
        _latido.Tick -= AlLatir;
        _latido.Tick += AlLatir;
        if (!_latido.IsRunning) _latido.Start();
    }

    private async void AlLatir(object? remitente, EventArgs e)
    {
        var sesion = _sesion;
        if (sesion is null || _latiendo) return;
        _latiendo = true;
        try
        {
            if (sesion.Preguntas is null) await sesion.CargarPreguntasAsync();     // la biblioteca no estaba al abrir: se reintenta sola
            await sesion.LatirAsync();
            var segundos = Math.Clamp(sesion.Plan?.LatidoSeg ?? 5, 2, 15);
            if (_latido is { } t && Math.Abs(t.Interval.TotalSeconds - segundos) > 0.5) t.Interval = TimeSpan.FromSeconds(segundos);
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "ExamenPage.Latido", ex);
        }
        finally { _latiendo = false; }
    }

    // ---------------------------------------------------------------------------------- salidas

    private async Task IrAEntregaAsync()
    {
        _permitirSalida = true;
        _latido?.Stop();
        await Shell.Current.GoToAsync("../examen-entrega");
    }

    private async Task SalirAsync()
    {
        _permitirSalida = true;
        _latido?.Stop();
        await Shell.Current.GoToAsync("..");
    }

    /// <summary>Siete toques en dos segundos sobre el título → PIN local. Nunca se explica en pantalla (es para quien administra la tableta).</summary>
    private async Task ContarToqueAsync()
    {
        var ahora = DateTime.UtcNow;
        _toques.RemoveAll(t => ahora - t > VentanaDeToques);
        _toques.Add(ahora);
        if (_toques.Count < ToquesParaSalir || _sesion is null) return;
        _toques.Clear();
        try
        {
            var pin = await DisplayPromptAsync("Salida del examen", "Sólo para quien administra la tableta. Escribe el PIN.", "Salir", "Cancelar", "PIN", 12, Keyboard.Numeric);
            if (string.IsNullOrEmpty(pin)) return;
            switch (await _sesion.SalidaAdministrativaAsync(pin))
            {
                case ResultadoDePin.Correcto:
                    await SalirAsync();
                    Avisos.Mostrar("La tableta se liberó del examen. Tus respuestas quedaron guardadas.");
                    break;
                case ResultadoDePin.Incorrecto:
                    Avisos.Mostrar("El PIN no es correcto.");
                    break;
                case ResultadoDePin.Frenado:
                    var espera = Sesion.PinDeSalida.EsperaRestante;
                    Avisos.Mostrar(espera is { } e ? $"Demasiados intentos. Espera {Math.Ceiling(e.TotalMinutes)} min." : "Demasiados intentos. Espera un momento.");
                    break;
                default:
                    Avisos.Mostrar("Esta tableta no tiene PIN de salida. Pide a tu profesor que cierre tu examen desde su pantalla.");
                    break;
            }
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "ExamenPage.SalidaAdministrativa", ex);
        }
    }
}

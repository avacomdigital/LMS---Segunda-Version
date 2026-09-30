using Avacom.Lms.Core.Services;
using Avacom.Lms.Student.ModoEstudio.Services;
using Avacom.Lms.Student.ModoEstudio.ViewModels;

namespace Avacom.Lms.Student.ModoEstudio.Views;

/// <summary>
/// «Modo estudio · Mis lecciones». El code-behind se limita a lo que es de la vista: el tamaño del modal según la ventana, el pulso del
/// esqueleto y las acciones de navegación y diálogo que el ViewModel pide por <see cref="IStudyNavigation"/>. Nada de lógica de negocio.
/// </summary>
public partial class StudyModePage : ContentPage, IStudyNavigation
{
    /// <summary>El ancho máximo del modal y la parte de la ventana que ocupa (spec §3).</summary>
    private const double AnchoMaximo = 1050, FraccionAncho = 0.88, FraccionAlto = 0.80;

    private readonly StudyModeViewModel _vm;
    private bool _pulsando;

    public StudyModePage()
    {
        InitializeComponent();
        _vm = EstudioCompose.CrearViewModel(this);
        BindingContext = _vm;
        _vm.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(StudyModeViewModel.IsLoading)) AjustarPulso();
        };
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _vm.Activate();
        AjustarPulso();
        try { await _vm.OnAppearingAsync(); }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyModePage.OnAppearing", ex); }
    }

    protected override void OnDisappearing()
    {
        _pulsando = false;
        _vm.Deactivate();
        base.OnDisappearing();
    }

    /// <summary>
    /// Tableta o portátil: el modal usa min(1050, 88 % del ancho) y ~80 % del alto, y nunca baja de un tamaño en que quepa la tarjeta.
    /// En pantallas bajas (1280×800 o menos) sube al 92 % del alto para que la lista respire. El aro de color del fondo acompaña.
    /// </summary>
    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0 || Height <= 0) return;
        var estrecha = Width < 700;
        var baja = Height < 820;
        var ancho = Math.Min(AnchoMaximo, Width * (estrecha ? 0.94 : FraccionAncho));
        var alto = Height * (baja ? 0.92 : FraccionAlto);
        Modal.WidthRequest = Math.Max(320, ancho);
        Modal.HeightRequest = Math.Max(420, alto);
        var lado = Math.Min(Width, Height) * 0.95;
        Aro.WidthRequest = lado;
        Aro.HeightRequest = lado;
    }

    /// <summary>El esqueleto «respira» mientras carga: un pulso de opacidad lento, sin girar nada.</summary>
    private void AjustarPulso()
    {
        if (_vm.IsLoading)
        {
            if (_pulsando) return;
            _pulsando = true;
            _ = PulsarAsync();
        }
        else
        {
            _pulsando = false;
            Esqueleto.Opacity = 1;
        }
    }

    private async Task PulsarAsync()
    {
        try
        {
            while (_pulsando && _vm.IsLoading)
            {
                await Esqueleto.FadeToAsync(0.55, 650, Easing.SinInOut);
                if (!_pulsando) break;
                await Esqueleto.FadeToAsync(1, 650, Easing.SinInOut);
            }
        }
        catch { /* la animación es un adorno: si falla, el esqueleto queda quieto */ }
        finally { Esqueleto.Opacity = 1; }
    }

    // ---------------------------------------------------------------------------- IStudyNavigation

    public Task CloseAsync() => Shell.Current.GoToAsync("..");

    public Task OpenLessonAsync(string lessonId) =>
        Shell.Current.GoToAsync($"estudio-leccion?asignacion={Uri.EscapeDataString(lessonId)}");

    public Task OpenPracticeAsync(string lessonId, bool retry) =>
        Shell.Current.GoToAsync($"estudio-practica?asignacion={Uri.EscapeDataString(lessonId)}&nueva={(retry ? "1" : "0")}");

    public Task ShowInfoAsync(string title, string message) => DisplayAlertAsync(title, message, "Entendido");

    public async Task<string?> ChooseAsync(string title, IReadOnlyList<string> options, string? destruction = null)
    {
        var elegido = await DisplayActionSheetAsync(title, "Cancelar", destruction, [.. options]);
        return string.IsNullOrEmpty(elegido) || elegido == "Cancelar" ? null : elegido;
    }

    public Task<bool> ConfirmAsync(string title, string message, string accept, string cancel) =>
        DisplayAlertAsync(title, message, accept, cancel);
}

using Avacom.Lms.Core.Services;
using Avacom.Lms.Student.ModoEstudio.Services;
using Avacom.Lms.Student.ModoEstudio.ViewModels;

namespace Avacom.Lms.Student.ModoEstudio.Views;

/// <summary>
/// Una lección para leer. La página enmarca los visores del aula (<see cref="Avacom.Lms.Ui.Controls.AulaContenidoView"/>) y pinta la actividad
/// que el ViewModel indica; todo lo demás (avance, guardado, completar) es del ViewModel y del servicio.
/// </summary>
[QueryProperty(nameof(Asignacion), "asignacion")]
public partial class StudyLessonPage : ContentPage, IStudyLessonNavigation
{
    private const double AnchoMaximo = 1050, FraccionAncho = 0.88, FraccionAlto = 0.92;
    private readonly IStudyModeService _servicio = EstudioCompose.Servicio;
    private readonly StudyLessonViewModel _vm;
    private bool _cargada;

    public StudyLessonPage()
    {
        InitializeComponent();
        _vm = new StudyLessonViewModel(_servicio, this);
        BindingContext = _vm;
        _vm.BlockChanged += AlCambiarLaActividad;
        Contenido.PuedeNavegar = false;   // se navega con las actividades de la lección, no con los mandos internos del visor
    }

    /// <summary>El id de la asignación (de la lista).</summary>
    public string Asignacion { get; set; } = string.Empty;

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        try
        {
            if (!_cargada)
            {
                _cargada = true;
                await _vm.LoadAsync(Asignacion);
            }
            else await _vm.OnAppearingAsync();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyLessonPage.OnAppearing", ex); }
    }

    protected override void OnDisappearing()
    {
        Contenido.MostrarVacio(string.Empty, string.Empty);   // detiene los reproductores y las WebView de la actividad que se deja
        base.OnDisappearing();
    }

    // La actividad actual: los visores del aula pintan láminas, páginas y laboratorios; la práctica y el aviso del laboratorio son tarjetas propias.
    private void AlCambiarLaActividad(StudyBlock bloque)
    {
        MainThread.BeginInvokeOnMainThread(() =>
        {
            try
            {
                if (bloque.IsPractice || _vm.NeedsAula || bloque.Objeto is null)
                {
                    Contenido.MostrarVacio(string.Empty, string.Empty);
                    return;
                }
                Contenido.Absoluta = url => _servicio.ResolveMedia(Asignacion, url);
                Contenido.Mostrar(bloque.Objeto, bloque.UnidadRef);
            }
            catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyLessonPage.Pintar", ex); }
        });
    }

    // ------------------------------------------------------------------------- IStudyLessonNavigation
    public Task BackAsync() => Shell.Current.GoToAsync("..");
    public Task OpenPracticeAsync(string lessonId) => Shell.Current.GoToAsync($"estudio-practica?asignacion={Uri.EscapeDataString(lessonId)}&nueva=0");
    public Task ShowInfoAsync(string title, string message) => DisplayAlertAsync(title, message, "Entendido");

    private async void OnCerrar(object? sender, EventArgs e) => await Shell.Current.GoToAsync("..");

    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0 || Height <= 0) return;
        var estrecha = Width < 700;
        Modal.WidthRequest = Math.Max(320, Math.Min(AnchoMaximo, Width * (estrecha ? 0.96 : FraccionAncho)));
        Modal.HeightRequest = Math.Max(440, Height * (Height < 820 ? 0.95 : FraccionAlto));
    }
}

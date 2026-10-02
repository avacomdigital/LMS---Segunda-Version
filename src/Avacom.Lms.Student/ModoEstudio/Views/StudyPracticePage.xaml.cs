using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Student.ModoEstudio.Models;
using Avacom.Lms.Ui.Controls;

namespace Avacom.Lms.Student.ModoEstudio.Views;

/// <summary>
/// La práctica de una lección en el modo de estudio. Abre la práctica (o la reanuda) por el servicio, se la da a <see cref="PracticaEstudioView"/>
/// y traduce entre los tipos del módulo y los del control. Sin lógica de negocio: comprobar y terminar los resuelve la sesión de práctica.
/// </summary>
[QueryProperty(nameof(Asignacion), "asignacion")]
[QueryProperty(nameof(Nueva), "nueva")]
[QueryProperty(nameof(Objeto), "objeto")]
public partial class StudyPracticePage : ContentPage
{
    private const double AnchoMaximo = 1050, FraccionAncho = 0.88, FraccionAlto = 0.90;
    private readonly Services.IStudyModeService _servicio = EstudioCompose.Servicio;
    private IStudyPracticeSession? _sesion;
    private int _cargas;

    public StudyPracticePage() => InitializeComponent();

    /// <summary>El id de la asignación (de la lista).</summary>
    public string Asignacion { get; set; } = string.Empty;

    /// <summary>«1»: «Intentar nuevamente» (empieza un intento nuevo).</summary>
    public string Nueva { get; set; } = "0";

    /// <summary>La actividad del bloque desde el que se abrió (una lección puede tener varias prácticas); vacío: la primera.</summary>
    public string Objeto { get; set; } = string.Empty;

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        if (_sesion is null) await CargarAsync(Nueva == "1");
    }

    private async Task CargarAsync(bool reintento)
    {
        var carga = ++_cargas;
        Cargando.IsVisible = true;
        Problema.IsVisible = false;
        Practica.IsVisible = false;
        try
        {
            var abierta = await _servicio.OpenPracticeAsync(Asignacion, reintento, string.IsNullOrEmpty(Objeto) ? null : Objeto);
            if (carga != _cargas) return;
            if (!abierta.Ok || abierta.Session is null)
            {
                Mostrar(abierta.ErrorTitle ?? "No pudimos abrir la práctica", abierta.ErrorMessage ?? "Vuelve a Mis lecciones e inténtalo de nuevo.");
                return;
            }
            _sesion = abierta.Session;
            Eyebrow.Text = "PRÁCTICA DE ESTUDIO";
            Practica.PuedeCalificarAhora = _sesion.CanGradeNow;
            Practica.ResolverUrl = url => _servicio.ResolveMedia(Asignacion, url);
            Practica.Comprobar = ComprobarAsync;
            Practica.Terminar = TerminarAsync;
            Practica.IntentarNuevamente -= AlIntentarNuevamente;
            Practica.IntentarNuevamente += AlIntentarNuevamente;
            Practica.VolverALaLeccion -= AlVolver;
            Practica.VolverALaLeccion += AlVolver;

            var previas = _sesion.Previous.ToDictionary(
                p => p.Key,
                p => (p.Value.Answer, p.Value.Verdict is { } v ? Traducir(v) : null));
            Practica.Cargar(_sesion.Activity, _sesion.Number, previas);
            Practica.PonerGuardado(EstadoGuardado.Guardado);
            Cargando.IsVisible = false;
            Practica.IsVisible = true;
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "StudyPracticePage.Cargar", ex);
            Mostrar("No pudimos abrir la práctica", "Lo que ya habías hecho está guardado. Vuelve a Mis lecciones e inténtalo de nuevo.");
        }
    }

    private void Mostrar(string titulo, string texto)
    {
        Cargando.IsVisible = false;
        Practica.IsVisible = false;
        ProblemaTitulo.Text = titulo;
        ProblemaTexto.Text = texto;
        Problema.IsVisible = true;
    }

    private static VeredictoPractica Traducir(StudyAnswerVerdict v) => new(v.Correct, v.Pending, v.Feedback);

    private async Task<VeredictoPractica> ComprobarAsync(PreguntaAula pregunta, JsonElement respuesta, CancellationToken ct)
    {
        var sesion = _sesion ?? throw new InvalidOperationException("No hay práctica abierta.");
        Practica.PonerGuardado(EstadoGuardado.Guardando);
        try
        {
            var veredicto = await sesion.SubmitAsync(pregunta, respuesta, ct);
            Practica.PonerGuardado(veredicto.Pending ? EstadoGuardado.GuardadoEnElDispositivo : EstadoGuardado.Guardado);
            return Traducir(veredicto);
        }
        catch
        {
            Practica.PonerGuardado(EstadoGuardado.GuardadoEnElDispositivo);
            throw;
        }
    }

    private async Task<ResultadoDePractica> TerminarAsync(CancellationToken ct)
    {
        var sesion = _sesion ?? throw new InvalidOperationException("No hay práctica abierta.");
        var r = await sesion.FinishAsync(ct);
        return new ResultadoDePractica(
            r.Correct, r.Total, r.Message, r.Ungraded,
            r.Review.Select(x => new RevisionPractica(x.QuestionRef, x.Number, x.Prompt, x.Correct, x.Feedback)).ToList());
    }

    private async void AlIntentarNuevamente()
    {
        _sesion = null;
        await CargarAsync(reintento: true);
    }

    private async void AlVolver() => await Shell.Current.GoToAsync("..");
    private async void OnAtras(object? sender, EventArgs e) => await Shell.Current.GoToAsync("..");

    /// <summary>Cerrar vuelve directo a «Mis lecciones» (la lista), no a la lección.</summary>
    private async void OnCerrar(object? sender, EventArgs e) => await Shell.Current.GoToAsync("..");

    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0 || Height <= 0) return;
        var estrecha = Width < 700;
        Modal.WidthRequest = Math.Max(320, Math.Min(AnchoMaximo, Width * (estrecha ? 0.96 : FraccionAncho)));
        Modal.HeightRequest = Math.Max(440, Height * (Height < 820 ? 0.95 : FraccionAlto));
    }
}

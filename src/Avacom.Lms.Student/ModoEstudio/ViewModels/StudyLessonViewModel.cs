using System.Collections.ObjectModel;
using System.Windows.Input;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Student.ModoEstudio.Models;
using Avacom.Lms.Student.ModoEstudio.Services;

namespace Avacom.Lms.Student.ModoEstudio.ViewModels;

/// <summary>Lo que la lección pide a la navegación: volver a la lista, abrir la práctica y decir algo con amabilidad.</summary>
public interface IStudyLessonNavigation
{
    Task BackAsync();
    Task OpenPracticeAsync(string lessonId);
    Task ShowInfoAsync(string title, string message);
}

/// <summary>Un número de la tira de actividades: ✓ atendida, el número si no, resaltada la actual. Lleva su propio comando de toque.</summary>
public sealed class StudyBlockChip : ObservableObject
{
    private static readonly Color Blanco = Colors.White, VerdeSuave = Color.FromArgb("#E5F6ED"), VerdeTinta = Color.FromArgb("#017A48");
    private static readonly Color Tinta = Color.FromArgb("#1D1D1F"), Gris = Color.FromArgb("#6E6E73"), Borde = Color.FromArgb("#D4D4D8");
    private bool _actual, _atendida;

    public StudyBlockChip(int indice, string titulo, Action<StudyBlockChip> alTocar)
    {
        Index = indice;
        Title = titulo;
        TapCommand = new Command(() => alTocar(this));
    }

    public int Index { get; }
    public string Title { get; }
    public ICommand TapCommand { get; }

    public bool IsCurrent { get => _actual; set => SetProperty(ref _actual, value, tambien: [nameof(Description), nameof(BorderColor), nameof(BorderWidth)]); }
    public bool IsAttended { get => _atendida; set => SetProperty(ref _atendida, value, tambien: [nameof(Glyph), nameof(Description), nameof(FillColor), nameof(InkColor)]); }
    public string Glyph => IsAttended ? "✓" : Index.ToString();
    public Color FillColor => IsAttended ? VerdeSuave : Blanco;
    public Color InkColor => IsAttended ? VerdeTinta : Gris;
    public Color BorderColor => IsCurrent ? Tinta : Borde;
    public double BorderWidth => IsCurrent ? 2.5 : 1;
    public string Description => $"Actividad {Index}, {Title}{(IsAttended ? ", vista" : string.Empty)}{(IsCurrent ? ", actual" : string.Empty)}";
}

/// <summary>
/// La lección abierta en el modo de estudio (MOD-008 · FUN-082, FUN-087, FUN-088): recorre sus actividades («Actividad 4 de 7»), guarda cada
/// una como vista y sólo permite marcar la lección como completada cuando todas las obligatorias se atendieron. La lógica vive aquí; la
/// página sólo pinta el contenido de la actividad actual con los visores del aula.
/// </summary>
public sealed class StudyLessonViewModel : ObservableObject
{
    private readonly IStudyModeService _servicio;
    private readonly IStudyLessonNavigation _navegacion;
    private IStudyLessonSession? _sesion;
    private int _indice;
    private int _cargas;

    public StudyLessonViewModel(IStudyModeService servicio, IStudyLessonNavigation navegacion)
    {
        _servicio = servicio;
        _navegacion = navegacion;
        PrevCommand = new AsyncCommand(() => IrAsync(_indice - 1), () => CanPrev);
        NextCommand = new AsyncCommand(() => IrAsync(_indice + 1), () => CanNext);
                CompleteCommand = new AsyncCommand(CompletarAsync, () => CanComplete);
        OpenPracticeCommand = new AsyncCommand(() => _sesion is null ? Task.CompletedTask : _navegacion.OpenPracticeAsync(_sesion.LessonId));
        BackCommand = new AsyncCommand(() => _navegacion.BackAsync());
    }

    public ICommand PrevCommand { get; }
    public ICommand NextCommand { get; }
    public ICommand CompleteCommand { get; }
    public ICommand OpenPracticeCommand { get; }
    public ICommand BackCommand { get; }

    /// <summary>La actividad actual cambió: la página repinta su contenido con el visor que toque.</summary>
    public event Action<StudyBlock>? BlockChanged;

    public ObservableCollection<StudyBlockChip> Chips { get; } = [];
    public IStudyLessonSession? Session => _sesion;

    // ------------------------------------------------------------------------------- estado de carga
    private bool _cargando = true, _hayProblema;
    private string _tituloProblema = string.Empty, _textoProblema = string.Empty;
    public bool IsLoading { get => _cargando; private set => SetProperty(ref _cargando, value, tambien: [nameof(ShowContent)]); }
    public bool HasProblem { get => _hayProblema; private set => SetProperty(ref _hayProblema, value, tambien: [nameof(ShowContent)]); }
    public string ProblemTitle { get => _tituloProblema; private set => SetProperty(ref _tituloProblema, value); }
    public string ProblemMessage { get => _textoProblema; private set => SetProperty(ref _textoProblema, value); }
    public bool ShowContent => !IsLoading && !HasProblem;

    // ---------------------------------------------------------------------------------- la lección
    private string _titulo = string.Empty, _eyebrow = string.Empty, _posicion = string.Empty, _atendidas = string.Empty, _tituloBloque = string.Empty, _aviso = string.Empty;
    private double _progreso;
    private StudyBlock? _bloque;
    private bool _puedeAnterior, _puedeSiguiente, _puedeCompletar, _completada, _esUltima, _soloLectura, _sinConexion, _necesitaAula;

    public string Title { get => _titulo; private set => SetProperty(ref _titulo, value); }
    public string Eyebrow { get => _eyebrow; private set => SetProperty(ref _eyebrow, value); }
    public string PositionText { get => _posicion; private set => SetProperty(ref _posicion, value); }
    public string AttendedText { get => _atendidas; private set => SetProperty(ref _atendidas, value); }
    public string BlockTitle { get => _tituloBloque; private set => SetProperty(ref _tituloBloque, value); }
    public double Progress { get => _progreso; private set => SetProperty(ref _progreso, value, tambien: [nameof(ProgressText)]); }
    public string ProgressText => StudyFormat.Porcentaje(Progress);
    public StudyBlock? CurrentBlock { get => _bloque; private set => SetProperty(ref _bloque, value, tambien: [nameof(IsPracticeBlock), nameof(IsContentBlock)]); }
    public bool IsPracticeBlock => CurrentBlock?.IsPractice == true;
    public bool IsContentBlock => CurrentBlock is { IsPractice: false } && !NeedsAula;
    public bool CanPrev { get => _puedeAnterior; private set { if (SetProperty(ref _puedeAnterior, value)) (PrevCommand as AsyncCommand)?.RaiseCanExecuteChanged(); } }
    public bool CanNext { get => _puedeSiguiente; private set { if (SetProperty(ref _puedeSiguiente, value)) (NextCommand as AsyncCommand)?.RaiseCanExecuteChanged(); } }
    public bool IsLastBlock { get => _esUltima; private set => SetProperty(ref _esUltima, value); }
    public bool ShowComplete => !IsReadOnly && !IsCompleted && (CanComplete || IsLastBlock);
    public bool CanComplete { get => _puedeCompletar; private set { if (SetProperty(ref _puedeCompletar, value)) (CompleteCommand as AsyncCommand)?.RaiseCanExecuteChanged(); } }
    public bool IsCompleted { get => _completada; private set => SetProperty(ref _completada, value); }
    public bool IsReadOnly { get => _soloLectura; private set => SetProperty(ref _soloLectura, value); }
    public bool IsOfflineContent { get => _sinConexion; private set => SetProperty(ref _sinConexion, value); }
    public bool NeedsAula { get => _necesitaAula; private set => SetProperty(ref _necesitaAula, value, tambien: [nameof(IsContentBlock)]); }
    public string Notice { get => _aviso; private set => SetProperty(ref _aviso, value, tambien: [nameof(HasNotice)]); }
    public bool HasNotice => !string.IsNullOrEmpty(Notice);

    // ================================================================================== carga

    public async Task LoadAsync(string lessonId)
    {
        var carga = ++_cargas;
        IsLoading = true;
        HasProblem = false;
        try
        {
            var abierta = await _servicio.OpenLessonAsync(lessonId);
            if (carga != _cargas) return;
            if (!abierta.Ok || abierta.Session is null)
            {
                ProblemTitle = abierta.ErrorTitle ?? "No pudimos abrir la lección";
                ProblemMessage = abierta.ErrorMessage ?? "Vuelve a Mis lecciones e inténtalo de nuevo.";
                HasProblem = true;
                return;
            }
            _sesion = abierta.Session;
            _sesion.Changed += AlCambiarLaSesion;
            Title = _sesion.Title;
            Eyebrow = _sesion.Eyebrow;
            IsOfflineContent = _sesion.IsOfflineContent;
            IsReadOnly = _sesion.IsReadOnly;
            Chips.Clear();
            foreach (var b in _sesion.Blocks) Chips.Add(new StudyBlockChip(b.Index, b.Title, chip => _ = IrAsync(chip.Index - 1)));
            if (_sesion.IsReadOnly) Notice = "El profesor ya cerró esta tarea: puedes releerla, pero no se guardará más avance.";
            IsLoading = false;
            await MostrarAsync(Math.Clamp(_sesion.StartIndex, 0, Math.Max(0, _sesion.Blocks.Count - 1)));
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "StudyLessonViewModel.Load", ex);
            ProblemTitle = "No pudimos abrir la lección";
            ProblemMessage = "Lo que ya habías hecho está guardado. Vuelve a Mis lecciones e inténtalo de nuevo.";
            HasProblem = true;
        }
        finally { IsLoading = false; }
    }

    /// <summary>Se vuelve a ver la lección (al regresar de la práctica): se relee lo hecho.</summary>
    public async Task OnAppearingAsync()
    {
        if (_sesion is null) return;
        await _sesion.RefreshAsync();
        RefrescarBanderas();
        if (CurrentBlock is { } actual) BlockChanged?.Invoke(actual);   // la página vació el visor al dejar de verse
    }

    // ================================================================================ navegar

    private async Task IrAsync(int indice)
    {
        if (_sesion is null || _sesion.Blocks.Count == 0) return;
        await MostrarAsync(Math.Clamp(indice, 0, _sesion.Blocks.Count - 1));
    }

    private async Task MostrarAsync(int indice)
    {
        if (_sesion is null || _sesion.Blocks.Count == 0) return;
        _indice = indice;
        var bloque = _sesion.Blocks[indice];
        CurrentBlock = bloque;
        BlockTitle = bloque.Title;
        NeedsAula = bloque.NeedsAula && _sesion.IsOfflineContent;
        foreach (var chip in Chips) chip.IsCurrent = chip.Index - 1 == indice;
        RefrescarBanderas();
        BlockChanged?.Invoke(bloque);
        // Ver una lámina o una página es atenderla. El laboratorio se atiende al abrirlo (con el aula); la práctica, al terminarla.
        if (!_sesion.IsReadOnly && bloque.Kind is "lamina" or "pagina" or "laboratorio" && !NeedsAula)
        {
            try { await _sesion.MarkViewedAsync(bloque); }
            catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyLessonViewModel.Marcar", ex); }
            RefrescarBanderas();
        }
    }

    private void AlCambiarLaSesion() => MainThread.BeginInvokeOnMainThread(RefrescarBanderas);

    private void RefrescarBanderas()
    {
        if (_sesion is null) return;
        var total = _sesion.Blocks.Count;
        PositionText = total == 0 ? string.Empty : $"Actividad {_indice + 1} de {total}";
        var obligatorias = Math.Max(1, _sesion.Required);
        Progress = _sesion.IsCompleted ? 1 : Math.Clamp((double)_sesion.AttendedRequired / obligatorias, 0, 1);
        AttendedText = _sesion.IsCompleted ? "Lección completada" : $"{_sesion.AttendedRequired} de {_sesion.Required} actividades vistas";
        CanPrev = _indice > 0;
        CanNext = _indice < total - 1;
        IsLastBlock = _indice >= total - 1;
        IsCompleted = _sesion.IsCompleted;
        CanComplete = !_sesion.IsReadOnly && !_sesion.IsCompleted && _sesion.AllRequiredAttended;
        foreach (var chip in Chips)
        {
            var bloque = _sesion.Blocks[chip.Index - 1];
            chip.IsAttended = _sesion.IsAttended(bloque);
        }
        OnPropertyChanged(nameof(ShowComplete));
    }

    // =============================================================================== completar

    private async Task CompletarAsync()
    {
        if (_sesion is null) return;
        var resultado = await _sesion.CompleteAsync();
        RefrescarBanderas();
        if (resultado.Completed)
        {
            await _navegacion.ShowInfoAsync("¡Lección completada!", "Tu avance quedó guardado. Si estás sin conexión, se enviará solo cuando vuelvas al aula.");
            await _navegacion.BackAsync();
            return;
        }
        var falta = resultado.Missing.Count == 0 ? string.Empty : $"\n\nTe falta ver: {string.Join(", ", resultado.Missing.Take(4))}{(resultado.Missing.Count > 4 ? "…" : string.Empty)}.";
        await _navegacion.ShowInfoAsync("Todavía te faltan actividades", resultado.Message + falta);
    }

    public void Detach()
    {
        if (_sesion is not null) _sesion.Changed -= AlCambiarLaSesion;
    }
}

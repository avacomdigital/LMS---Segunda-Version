using System.Collections.ObjectModel;
using System.Windows.Input;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Student.ModoEstudio.Models;
using Avacom.Lms.Student.ModoEstudio.Services;

namespace Avacom.Lms.Student.ModoEstudio.ViewModels;

/// <summary>
/// «Modo estudio · Mis lecciones» (MOD-008 · PAN-124/130). Toda la lógica de la pantalla vive aquí y en el servicio; la página sólo pinta.
///
/// Reglas de la pantalla que este ViewModel hace cumplir:
///  · Offline-first: lo descargado sigue habilitado sin el aula; lo que necesita el aula se explica sin errores técnicos (UXR-004).
///  · Sólo se repinta la tarjeta afectada: las descargas y la sincronización actualizan su <see cref="StudyLessonItem"/>, no la lista.
///  · La práctica no es una evaluación (BR-055): la tarjeta de evaluación es aparte y sólo informa.
///  · «Salir» de esta pantalla nunca pierde nada: lo hecho está en la tableta y sale solo (BR-137).
/// </summary>
public sealed class StudyModeViewModel : ObservableObject, IStudyLessonActions, IDisposable
{
    private readonly IStudyModeService _servicio;
    private readonly IDownloadService _descargas;
    private readonly IConnectivityService _conectividad;
    private readonly IStudyNavigation _navegacion;
    private readonly Dictionary<string, StudyLessonItem> _porId = new();
    private readonly CancellationTokenSource _vida = new();
    private int _cargando;

    public StudyModeViewModel(IStudyModeService servicio, IDownloadService descargas, IConnectivityService conectividad, IStudyNavigation navegacion)
    {
        _servicio = servicio;
        _descargas = descargas;
        _conectividad = conectividad;
        _navegacion = navegacion;

        FilterLessonsCommand = new Command<string>(nombre =>
        {
            if (Enum.TryParse<StudyFilter>(nombre, true, out var filtro)) SelectedFilter = filtro;
        });
        CloseStudyModeCommand = new AsyncCommand(() => _navegacion.CloseAsync());
        OpenLessonCommand = new AsyncCommand<StudyLessonItem>(item => AbrirAsync(item, reanudar: false));
        ResumeLessonCommand = new AsyncCommand<StudyLessonItem>(item => AbrirAsync(item, reanudar: true));
        OpenCompletedLessonCommand = new AsyncCommand<StudyLessonItem>(item => AbrirAsync(item, reanudar: false));
        DownloadLessonCommand = new AsyncCommand<StudyLessonItem>(DescargarAsync);
        PauseDownloadCommand = new AsyncCommand<StudyLessonItem>(item => { if (item is not null) _descargas.Pause(item.Id); return Task.CompletedTask; });
        ResumeDownloadCommand = new AsyncCommand<StudyLessonItem>(DescargarAsync);
        DeleteDownloadCommand = new AsyncCommand<StudyLessonItem>(EliminarDescargaAsync);
        OpenPracticeCommand = new AsyncCommand<StudyLessonItem>(item => PracticarAsync(item, reintentar: false));
        RetryPracticeCommand = new AsyncCommand<StudyLessonItem>(item => PracticarAsync(item, reintentar: true));
        GoToCompletedCommand = new Command(() => SelectedFilter = StudyFilter.Completed);
        RefreshCommand = new AsyncCommand(() => LoadAsync(silencioso: true));
        ConfirmStudentCommand = new AsyncCommand(ConfirmarEstudianteAsync);
        ContinueAsSuggestedCommand = new AsyncCommand(ContinuarComoSugeridoAsync);
        ChangeStudentCommand = new AsyncCommand(CambiarEstudianteAsync);
        RetryRosterCommand = new AsyncCommand(MostrarSelectorAsync);

        IsOffline = !_conectividad.IsOnline;
        ActualizarSincronizacion();
    }

    private bool _activo;

    /// <summary>La pantalla se ve: empieza a escuchar a los servicios. Las descargas siguen en segundo plano mientras no se ve.</summary>
    public void Activate()
    {
        if (_activo) return;
        _activo = true;
        _descargas.Updated += AlActualizarseUnaDescarga;
        _servicio.LessonChanged += AlCambiarUnaLeccion;
        _servicio.SyncStateChanged += AlCambiarLaSincronizacion;
        _conectividad.Changed += AlCambiarLaConexion;
        IsOffline = !_conectividad.IsOnline;
        ActualizarSincronizacion();
    }

    /// <summary>La pantalla dejó de verse (otra encima o cerrada): deja de escuchar. Nada se pierde; al volver se recarga el estado.</summary>
    public void Deactivate()
    {
        if (!_activo) return;
        _activo = false;
        _descargas.Updated -= AlActualizarseUnaDescarga;
        _servicio.LessonChanged -= AlCambiarUnaLeccion;
        _servicio.SyncStateChanged -= AlCambiarLaSincronizacion;
        _conectividad.Changed -= AlCambiarLaConexion;
    }

    // ================================================================================ comandos (spec §25)
    public ICommand OpenLessonCommand { get; }
    public ICommand ResumeLessonCommand { get; }
    public ICommand DownloadLessonCommand { get; }
    public ICommand PauseDownloadCommand { get; }
    public ICommand ResumeDownloadCommand { get; }
    public ICommand DeleteDownloadCommand { get; }
    public ICommand OpenPracticeCommand { get; }
    public ICommand RetryPracticeCommand { get; }
    public ICommand OpenCompletedLessonCommand { get; }
    public ICommand FilterLessonsCommand { get; }
    public ICommand CloseStudyModeCommand { get; }
    public ICommand GoToCompletedCommand { get; }
    public ICommand RefreshCommand { get; }
    public ICommand ConfirmStudentCommand { get; }
    public ICommand ContinueAsSuggestedCommand { get; }
    public ICommand ChangeStudentCommand { get; }
    public ICommand RetryRosterCommand { get; }

    // ================================================================================== lo que se pinta
    public string Title => IsChoosingStudent ? "¿Quién eres?" : "Modo estudio";
    public string Subtitle => IsChoosingStudent
        ? "Elige tu nombre para ver las lecciones que te asignó tu profesor."
        : "Continúa tus lecciones asignadas incluso cuando estés sin conexión.";

    // ======================================================================================= ¿quién eres? (D-15)
    // «Modo estudio» no pide código (eso es «Clase en vivo»): las lecciones se asignan a un grupo, así que aquí la persona dice quién es. En un LMS
    // offline nada puede verificarlo: se elige el propio nombre y el profesor verá el avance con él.

    private bool _eligiendo, _cargandoNombres, _confirmando;
    private StudyStudentItem? _elegido;
    private StudyStudent? _sugerido;
    private string _avisoNombres = string.Empty, _sugerenciaEtiqueta = string.Empty;

    public ObservableCollection<StudyRosterGroupItem> RosterGroups { get; } = [];
    public ObservableCollection<StudyStudentItem> RosterStudents { get; } = [];

    public bool IsChoosingStudent
    {
        get => _eligiendo;
        private set => SetProperty(ref _eligiendo, value, tambien: [nameof(IsStudyView), nameof(Title), nameof(Subtitle), nameof(HasCurrentStudent), nameof(StudyingAsText)]);
    }

    /// <summary>Se ve la lista de lecciones (y no el selector de nombres).</summary>
    public bool IsStudyView => !IsChoosingStudent;

    public bool IsLoadingRoster { get => _cargandoNombres; private set => SetProperty(ref _cargandoNombres, value); }

    public string RosterNotice { get => _avisoNombres; private set => SetProperty(ref _avisoNombres, value, tambien: [nameof(HasRosterNotice), nameof(ShowRetryRoster)]); }
    public bool HasRosterNotice => !string.IsNullOrEmpty(RosterNotice);
    public bool ShowRetryRoster => IsChoosingStudent && !IsLoadingRoster && !HasRosterStudents && !HasSuggestion;

    public bool ShowRosterGroups => RosterGroups.Count > 1;
    public bool HasRosterStudents => RosterStudents.Count > 0;

    public bool HasSuggestion => _sugerido is not null;
    public string SuggestionName => _sugerido?.Name ?? string.Empty;
    public string SuggestionEyebrow => _sugerenciaEtiqueta;
    public string SuggestionButtonText => _sugerido is null ? string.Empty : $"Continuar como {PrimerNombre(_sugerido.Name)}";

    public bool CanConfirmStudent => _elegido is not null && !_confirmando;
    public string ConfirmStudentText => _elegido is null ? "Elige tu nombre" : $"Continuar como {PrimerNombre(_elegido.Name)}";

    /// <summary>Quién está estudiando ahora (el aviso de la cabecera, con el que se puede cambiar).</summary>
    public bool HasCurrentStudent => !IsChoosingStudent && _servicio.CurrentStudent is not null;
    public string StudyingAsText => _servicio.CurrentStudent is { } yo ? $"Estudias como {yo.Name}  ·  Cambiar" : string.Empty;

    private static string PrimerNombre(string nombre) => nombre.Split(' ', StringSplitOptions.RemoveEmptyEntries).FirstOrDefault() ?? nombre;

    /// <summary>Pide los nombres al aula (o a lo último que se supo de ella) y pinta el selector.</summary>
    private async Task MostrarSelectorAsync()
    {
        await EnHiloUi(() =>
        {
            IsChoosingStudent = true;
            IsLoading = false;
            IsLoadingRoster = true;
            Notice = string.Empty;
            RosterNotice = string.Empty;
            NotificarSelector();
        });
        StudyRoster roster;
        try { roster = await _servicio.GetRosterAsync(_vida.Token); }
        catch (OperationCanceledException) { return; }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "StudyModeViewModel.Nombres", ex);
            roster = new StudyRoster([], null, null, false, false, "No pudimos ver a tus compañeros. Inténtalo de nuevo en un momento.");
        }
        await EnHiloUi(() => AplicarNombres(roster));
    }

    private void AplicarNombres(StudyRoster roster)
    {
        IsOffline = !roster.AulaReachable;
        RosterGroups.Clear();
        RosterStudents.Clear();
        _elegido = null;
        foreach (var grupo in roster.Groups) RosterGroups.Add(new StudyRosterGroupItem(grupo, SeleccionarGrupo));
        // Lo que se ofrece primero: el último que estudió aquí y, si no, a quien está asignada la tableta.
        var propio = roster.Last ?? roster.Owner;
        _sugerido = propio;
        _sugerenciaEtiqueta = propio is null ? string.Empty
            : roster.Last is not null && (roster.Owner is null || roster.Last.Id != roster.Owner.Id) ? "LA ÚLTIMA PERSONA QUE ESTUDIÓ AQUÍ"
            : roster.Owner is not null && roster.Owner.Id == propio.Id ? "ESTA TABLETA ES DE"
            : "LA ÚLTIMA PERSONA QUE ESTUDIÓ AQUÍ";
        var primero = roster.Groups.FirstOrDefault(g => propio is not null && g.Students.Any(a => a.Id == propio.Id)) ?? roster.Groups.FirstOrDefault();
        if (primero is not null && RosterGroups.FirstOrDefault(g => g.Group == primero) is { } item) SeleccionarGrupo(item, owner: roster.Owner);
        RosterNotice = roster.Notice ?? string.Empty;
        IsLoadingRoster = false;
        NotificarSelector();
    }

    private StudyStudent? _duenoTableta;

    private void SeleccionarGrupo(StudyRosterGroupItem item) => SeleccionarGrupo(item, _duenoTableta);

    private void SeleccionarGrupo(StudyRosterGroupItem item, StudyStudent? owner)
    {
        _duenoTableta = owner;
        foreach (var g in RosterGroups) g.IsSelected = ReferenceEquals(g, item);
        RosterStudents.Clear();
        _elegido = null;
        foreach (var alumno in item.Group.Students) RosterStudents.Add(new StudyStudentItem(alumno, owner is not null && owner.Id == alumno.Id, SeleccionarEstudiante));
        NotificarSelector();
    }

    private void SeleccionarEstudiante(StudyStudentItem item)
    {
        foreach (var s in RosterStudents) s.IsSelected = ReferenceEquals(s, item);
        _elegido = item;
        NotificarSelector();
    }

    private void NotificarSelector()
    {
        OnPropertyChanged(nameof(ShowRosterGroups));
        OnPropertyChanged(nameof(HasRosterStudents));
        OnPropertyChanged(nameof(HasSuggestion));
        OnPropertyChanged(nameof(SuggestionName));
        OnPropertyChanged(nameof(SuggestionEyebrow));
        OnPropertyChanged(nameof(SuggestionButtonText));
        OnPropertyChanged(nameof(CanConfirmStudent));
        OnPropertyChanged(nameof(ConfirmStudentText));
        OnPropertyChanged(nameof(ShowRetryRoster));
        OnPropertyChanged(nameof(HasCurrentStudent));
        OnPropertyChanged(nameof(StudyingAsText));
    }

    private Task ContinuarComoSugeridoAsync() => _sugerido is null ? Task.CompletedTask : ElegirAsync(_sugerido);

    private Task ConfirmarEstudianteAsync() => _elegido is null ? Task.CompletedTask : ElegirAsync(_elegido.Student);

    private async Task ElegirAsync(StudyStudent estudiante)
    {
        if (_confirmando) return;
        await EnHiloUi(() => { _confirmando = true; NotificarSelector(); });
        bool bien;
        try { bien = await _servicio.ChooseStudentAsync(estudiante, _vida.Token); }
        catch (OperationCanceledException) { return; }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "StudyModeViewModel.Elegir", ex);
            bien = false;
        }
        await EnHiloUi(() =>
        {
            _confirmando = false;
            if (!bien)
            {
                RosterNotice = "No pudimos guardar tu nombre. Inténtalo de nuevo.";
                NotificarSelector();
                return;
            }
            // Nada de la persona anterior queda a la vista.
            Lessons.Clear();
            VisibleLessons.Clear();
            _porId.Clear();
            RosterGroups.Clear();
            RosterStudents.Clear();
            _elegido = null;
            IsChoosingStudent = false;
            NotificarSelector();
        });
        if (bien) await LoadAsync();
    }

    /// <summary>«¿No eres tú?»: vuelve a preguntar. No borra nada: si vuelve a elegir el mismo nombre, sigue donde iba.</summary>
    private async Task CambiarEstudianteAsync()
    {
        try { await _servicio.ChangeStudentAsync(_vida.Token); }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyModeViewModel.Cambiar", ex); }
        await EnHiloUi(() =>
        {
            Lessons.Clear();
            VisibleLessons.Clear();
            _porId.Clear();
            Recontar();
        });
        await MostrarSelectorAsync();
    }

    /// <summary>Todas las lecciones (una tarjeta por elemento). La lista que se ve es <see cref="VisibleLessons"/>.</summary>
    public ObservableCollection<StudyLessonItem> Lessons { get; } = [];

    /// <summary>Las lecciones del filtro elegido, en su orden. Se actualiza por diferencias: no se recrea al cambiar un progreso.</summary>
    public ObservableCollection<StudyLessonItem> VisibleLessons { get; } = [];

    /// <summary>Tres filas de esqueleto mientras se cargan las lecciones (no un spinner gigante).</summary>
    public IReadOnlyList<int> SkeletonRows { get; } = [1, 2, 3];

    private StudyFilter _filtro = StudyFilter.Pending;
    public StudyFilter SelectedFilter
    {
        get => _filtro;
        set
        {
            if (!SetProperty(ref _filtro, value, tambien: [nameof(IsPendingFilter), nameof(IsDownloadedFilter), nameof(IsCompletedFilter)])) return;
            AplicarFiltro();
        }
    }

    public bool IsPendingFilter => SelectedFilter == StudyFilter.Pending;
    public bool IsDownloadedFilter => SelectedFilter == StudyFilter.Downloaded;
    public bool IsCompletedFilter => SelectedFilter == StudyFilter.Completed;

    private int _pendientes, _descargadas, _completadas;
    public int PendingCount { get => _pendientes; private set => SetProperty(ref _pendientes, value, tambien: [nameof(PendingLabel)]); }
    public int DownloadedCount { get => _descargadas; private set => SetProperty(ref _descargadas, value, tambien: [nameof(DownloadedLabel)]); }
    public int CompletedCount { get => _completadas; private set => SetProperty(ref _completadas, value, tambien: [nameof(CompletedLabel)]); }
    public string PendingLabel => $"Pendientes {PendingCount}";
    public string DownloadedLabel => $"Descargadas {DownloadedCount}";
    public string CompletedLabel => $"Completadas {CompletedCount}";

    private bool _cargandoLista;
    public bool IsLoading { get => _cargandoLista; private set => SetProperty(ref _cargandoLista, value, tambien: [nameof(ShowList), nameof(ShowEmpty)]); }

    private bool _vacia;
    public bool IsEmpty { get => _vacia; private set => SetProperty(ref _vacia, value, tambien: [nameof(ShowList), nameof(ShowEmpty)]); }
    public bool ShowList => !IsLoading && !IsEmpty;
    public bool ShowEmpty => !IsLoading && IsEmpty;

    private string _tituloVacio = string.Empty, _textoVacio = string.Empty;
    private bool _accionVacio;
    public string EmptyTitle { get => _tituloVacio; private set => SetProperty(ref _tituloVacio, value); }
    public string EmptyMessage { get => _textoVacio; private set => SetProperty(ref _textoVacio, value); }
    public bool ShowEmptyAction { get => _accionVacio; private set => SetProperty(ref _accionVacio, value); }

    public bool IsDemo => _servicio.IsDemo;

    // -------------------------------------------------------------------------------------- conexión
    private bool _sinConexion;
    public bool IsOffline
    {
        get => _sinConexion;
        private set
        {
            if (!SetProperty(ref _sinConexion, value, tambien: [nameof(OfflineText)])) return;
            foreach (var item in Lessons) item.IsOffline = value;
        }
    }

    public string OfflineText => "Sin conexión";

    private string _aviso = string.Empty;
    /// <summary>Un aviso amable y pasajero (no un error): «Tu avance está guardado en la tableta».</summary>
    public string Notice { get => _aviso; private set => SetProperty(ref _aviso, value, tambien: [nameof(HasNotice)]); }
    public bool HasNotice => !string.IsNullOrEmpty(Notice);

    // ------------------------------------------------------------------------------ descargas activas
    private bool _hayDescargas;
    private double _descargaGlobal;
    private string _textoDescargas = string.Empty;
    public bool HasActiveDownloads { get => _hayDescargas; private set => SetProperty(ref _hayDescargas, value); }
    public double GlobalDownloadProgress { get => _descargaGlobal; private set => SetProperty(ref _descargaGlobal, value, tambien: [nameof(GlobalDownloadPercentText)]); }
    public string GlobalDownloadPercentText => StudyFormat.Porcentaje(GlobalDownloadProgress);
    public string ActiveDownloadsText { get => _textoDescargas; private set => SetProperty(ref _textoDescargas, value); }

    // ------------------------------------------------------------------------------ guardado y espacio
    private StudySyncState _sync;
    private string _textoSync = string.Empty, _iconoSync = string.Empty, _textoEspacio = string.Empty;
    public StudySyncState SyncState { get => _sync; private set => SetProperty(ref _sync, value); }
    public string SyncText { get => _textoSync; private set => SetProperty(ref _textoSync, value); }
    public string SyncIcon { get => _iconoSync; private set => SetProperty(ref _iconoSync, value); }
    public string StorageText { get => _textoEspacio; private set => SetProperty(ref _textoEspacio, value); }

    // ============================================================================================ cargar

    /// <summary>Pide las lecciones (al aula si contesta, a la tableta si no) y las vuelca en las tarjetas.</summary>
    public async Task LoadAsync(bool silencioso = false)
    {
        if (Interlocked.Exchange(ref _cargando, 1) == 1) return;
        var primera = Lessons.Count == 0;
        try
        {
            if (primera && !silencioso) IsLoading = true;
            var resultado = await _servicio.LoadAsync(_vida.Token);
            if (resultado.NeedsIdentity)
            {
                await MostrarSelectorAsync();
                return;
            }
            await EnHiloUi(() =>
            {
                if (IsChoosingStudent) IsChoosingStudent = false;
                Aplicar(resultado);
                IsOffline = !resultado.AulaReachable;
                Notice = resultado.Notice ?? string.Empty;
            });
            _ = ActualizarEspacioAsync();
            if (resultado.AulaReachable) _ = _servicio.SyncNowAsync(_vida.Token);
        }
        catch (OperationCanceledException) { }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "StudyModeViewModel.Load", ex);
            await EnHiloUi(() => Notice = "No pudimos actualizar tus lecciones. Lo que ya tenías sigue aquí.");
        }
        finally
        {
            await EnHiloUi(() => IsLoading = false);
            Interlocked.Exchange(ref _cargando, 0);
        }
    }

    /// <summary>Se vuelve a ver la pantalla (por ejemplo, tras cerrar una lección): se refresca sin esqueleto.</summary>
    public Task OnAppearingAsync() => LoadAsync(silencioso: Lessons.Count > 0);

    private void Aplicar(StudyListResult resultado)
    {
        var vistos = new HashSet<string>();
        foreach (var dato in resultado.Lessons)
        {
            vistos.Add(dato.Id);
            if (!_porId.TryGetValue(dato.Id, out var item))
            {
                item = new StudyLessonItem(dato.Id, this) { IsOffline = IsOffline };
                _porId[dato.Id] = item;
                Lessons.Add(item);
            }
            Volcar(item, dato);
        }
        foreach (var sobrante in _porId.Keys.Where(k => !vistos.Contains(k)).ToList())
        {
            Lessons.Remove(_porId[sobrante]);
            _porId.Remove(sobrante);
        }
        Recontar();
        AplicarFiltro();
        ActualizarDescargasGlobales();
    }

    private static void Volcar(StudyLessonItem item, StudyLessonData d)
    {
        item.Subject = d.Subject;
        item.UnitName = d.UnitName;
        item.Title = d.Title;
        item.Description = d.Description;
        item.State = d.State;
        item.DueDate = d.DueDate;
        item.CompletedOn = d.CompletedOn;
        item.CompletedBlocks = d.CompletedBlocks;
        item.TotalBlocks = d.TotalBlocks;
        item.Progress = d.Progress;
        item.ResumeLabel = d.ResumeLabel;
        item.CanResume = d.CanResume;
        item.CanDownload = d.CanDownload;
        item.DownloadDeniedReason = d.DownloadDeniedReason;
        item.TotalBytes = d.TotalBytes;
        item.DownloadedBytes = d.DownloadedBytes;
        item.DownloadProgress = d.DownloadProgress;
        item.DownloadState = d.DownloadState;
        item.HasPractice = d.HasPractice;
        item.PracticeTitle = d.PracticeTitle;
        item.PracticeQuestionCount = d.PracticeQuestionCount;
        item.PracticeAttempts = d.PracticeAttempts;
        item.PracticeBestScore = d.PracticeBestScore;
        item.PracticeInProgress = d.PracticeInProgress;
        item.HasExam = d.HasExam;
        item.ExamTitle = d.ExamTitle;
        item.ExamAvailability = d.ExamAvailability;
        item.IsPendingSync = d.IsPendingSync;
        if (d.DownloadState != StudyDownloadState.Downloading) item.Remaining = null;
    }

    // ============================================================================================ filtros

    private static bool EnFiltro(StudyLessonItem item, StudyFilter filtro) => filtro switch
    {
        StudyFilter.Pending => item.State != StudyLessonState.Completed,
        StudyFilter.Downloaded => item.DownloadState is StudyDownloadState.Available or StudyDownloadState.Downloading
            or StudyDownloadState.Paused or StudyDownloadState.Expired,
        _ => item.State == StudyLessonState.Completed,
    };

    private void Recontar()
    {
        PendingCount = Lessons.Count(i => EnFiltro(i, StudyFilter.Pending));
        DownloadedCount = Lessons.Count(i => EnFiltro(i, StudyFilter.Downloaded));
        CompletedCount = Lessons.Count(i => EnFiltro(i, StudyFilter.Completed));
    }

    private IEnumerable<StudyLessonItem> Ordenadas(StudyFilter filtro)
    {
        var lista = Lessons.Where(i => EnFiltro(i, filtro));
        return filtro switch
        {
            StudyFilter.Completed => lista.OrderByDescending(i => i.CompletedOn ?? DateTimeOffset.MinValue).ThenBy(i => i.Title),
            StudyFilter.Downloaded => lista.OrderBy(i => i.Title),
            _ => lista.OrderBy(i => i.DueDate ?? DateTimeOffset.MaxValue).ThenBy(i => i.Title),
        };
    }

    /// <summary>Deja <see cref="VisibleLessons"/> como debe ser con las mínimas altas, bajas y movimientos (las demás tarjetas ni se enteran).</summary>
    private void AplicarFiltro()
    {
        var deseadas = Ordenadas(SelectedFilter).ToList();
        for (var i = VisibleLessons.Count - 1; i >= 0; i--)
            if (!deseadas.Contains(VisibleLessons[i])) VisibleLessons.RemoveAt(i);
        for (var i = 0; i < deseadas.Count; i++)
        {
            if (i < VisibleLessons.Count && ReferenceEquals(VisibleLessons[i], deseadas[i])) continue;
            var actual = VisibleLessons.IndexOf(deseadas[i]);
            if (actual >= 0) VisibleLessons.Move(actual, i);
            else VisibleLessons.Insert(i, deseadas[i]);
        }
        IsEmpty = VisibleLessons.Count == 0;
        PintarVacio();
    }

    private void PintarVacio()
    {
        switch (SelectedFilter)
        {
            case StudyFilter.Pending:
                EmptyTitle = "Estás al día";
                EmptyMessage = "No tienes lecciones pendientes en modo estudio.";
                ShowEmptyAction = CompletedCount > 0;
                break;
            case StudyFilter.Downloaded:
                EmptyTitle = "Todavía no descargas lecciones";
                EmptyMessage = "Descarga una lección con conexión y podrás estudiarla aunque no estés en el aula.";
                ShowEmptyAction = false;
                break;
            default:
                EmptyTitle = "Aún no completas lecciones";
                EmptyMessage = "Cuando termines una, la verás aquí.";
                ShowEmptyAction = false;
                break;
        }
    }

    // ===================================================================== acciones de una tarjeta

    private async Task AbrirAsync(StudyLessonItem? item, bool reanudar)
    {
        if (item is null) return;
        if (!item.CanOpen)
        {
            await _navegacion.ShowInfoAsync("Necesitas conexión con el aula",
                "Esta lección todavía no está en tu tableta. Conéctate al aula para abrirla o descárgala para estudiar sin conexión.");
            return;
        }
        await _navegacion.OpenLessonAsync(item.Id);
    }

    private async Task DescargarAsync(StudyLessonItem? item)
    {
        if (item is null) return;
        if (!item.CanStartDownload)
        {
            if (!item.CanDownload)
                await _navegacion.ShowInfoAsync("No se puede descargar aquí",
                    string.IsNullOrWhiteSpace(item.DownloadDeniedReason)
                        ? "Este dispositivo no permite descargar contenido para estudiar sin conexión."
                        : item.DownloadDeniedReason);
            else
                await _navegacion.ShowInfoAsync("Necesitas conexión con el aula", "Conéctate al aula para descargar esta lección.");
            return;
        }
        item.DownloadState = StudyDownloadState.Requested;
        ActualizarDescargasGlobales();
        await _descargas.StartAsync(item.Id);
    }

    private async Task EliminarDescargaAsync(StudyLessonItem? item)
    {
        if (item is null) return;
        var acepta = await _navegacion.ConfirmAsync("¿Eliminar la descarga?",
            "Se liberará el espacio de esta lección en tu tableta. Tu avance se conserva y podrás descargarla otra vez.", "Eliminar", "Cancelar");
        if (!acepta) return;
        await _descargas.DeleteAsync(item.Id);
        _ = ActualizarEspacioAsync();
    }

    private async Task PracticarAsync(StudyLessonItem? item, bool reintentar)
    {
        if (item is null) return;
        if (!item.CanUsePractice)
        {
            await _navegacion.ShowInfoAsync("Necesitas conexión con el aula",
                "Para practicar esta lección conéctate al aula o descárgala antes para estudiar sin conexión.");
            return;
        }
        await _navegacion.OpenPracticeAsync(item.Id, reintentar);
    }

    // --- IStudyLessonActions: lo que llama cada tarjeta a través de sus comandos
    void IStudyLessonActions.Open(StudyLessonItem item) => OpenLessonCommand.Execute(item);
    void IStudyLessonActions.Resume(StudyLessonItem item) => ResumeLessonCommand.Execute(item);
    void IStudyLessonActions.OpenCompleted(StudyLessonItem item) => OpenCompletedLessonCommand.Execute(item);
    void IStudyLessonActions.Download(StudyLessonItem item) => DownloadLessonCommand.Execute(item);
    void IStudyLessonActions.PauseDownload(StudyLessonItem item) => PauseDownloadCommand.Execute(item);
    void IStudyLessonActions.ResumeDownload(StudyLessonItem item) => ResumeDownloadCommand.Execute(item);
    void IStudyLessonActions.DeleteDownload(StudyLessonItem item) => DeleteDownloadCommand.Execute(item);
    void IStudyLessonActions.OpenPractice(StudyLessonItem item) => OpenPracticeCommand.Execute(item);
    void IStudyLessonActions.RetryPractice(StudyLessonItem item) => RetryPracticeCommand.Execute(item);
    void IStudyLessonActions.ShowExamInfo(StudyLessonItem item) =>
        _ = _navegacion.ShowInfoAsync(string.IsNullOrWhiteSpace(item.ExamTitle) ? "Evaluación" : item.ExamTitle, _servicio.ExamExplanation(item.Id));

    void IStudyLessonActions.ShowDownloadMenu(StudyLessonItem item) => _ = MenuDeDescargaAsync(item);

    private async Task MenuDeDescargaAsync(StudyLessonItem item)
    {
        var elegido = await _navegacion.ChooseAsync(item.Title, ["Ver información"], "Eliminar descarga");
        switch (elegido)
        {
            case "Ver información":
                await _navegacion.ShowInfoAsync("Disponible sin conexión",
                    $"Esta lección está guardada en tu tableta{(item.TotalBytes > 0 ? $" ({item.DownloadSizeText})" : string.Empty)}. " +
                    "Puedes estudiarla y practicar sin conexión con el aula; tu avance se enviará solo cuando vuelvas.");
                break;
            case "Eliminar descarga":
                DeleteDownloadCommand.Execute(item);
                break;
        }
    }

    // ============================================================= eventos de los servicios (hilos de fondo)

    private void AlActualizarseUnaDescarga(StudyDownloadUpdate u) => _ = EnHiloUi(() =>
    {
        if (!_porId.TryGetValue(u.LessonId, out var item)) return;
        item.TotalBytes = u.TotalBytes > 0 ? u.TotalBytes : item.TotalBytes;
        item.DownloadedBytes = u.DownloadedBytes;
        item.DownloadProgress = u.State == StudyDownloadState.Available ? 1 : u.Progress;
        item.Remaining = u.State == StudyDownloadState.Downloading ? u.Remaining : null;
        if (u.State == StudyDownloadState.Denied)
        {
            item.CanDownload = false;
            item.DownloadDeniedReason = u.Message ?? string.Empty;
        }
        item.DownloadState = u.State;
        if (!string.IsNullOrWhiteSpace(u.Message) && u.State != StudyDownloadState.Denied) Notice = u.Message!;
        ActualizarDescargasGlobales();
        Recontar();
        if (SelectedFilter == StudyFilter.Downloaded) AplicarFiltro();
        if (u.State is StudyDownloadState.Available or StudyDownloadState.None or StudyDownloadState.Expired) _ = ActualizarEspacioAsync();
    });

    private void AlCambiarUnaLeccion(StudyLessonData dato) => _ = EnHiloUi(() =>
    {
        if (!_porId.TryGetValue(dato.Id, out var item)) return;
        Volcar(item, dato);
        Recontar();
        AplicarFiltro();
        ActualizarDescargasGlobales();
    });

    private void AlCambiarLaSincronizacion() => _ = EnHiloUi(ActualizarSincronizacion);

    private void AlCambiarLaConexion(bool enLinea) => _ = EnHiloUi(() =>
    {
        IsOffline = !enLinea;
        Notice = enLinea ? string.Empty : "Sin conexión con el aula. Lo descargado sigue disponible y lo que hagas se enviará solo.";
        if (enLinea) _ = LoadAsync(silencioso: true);
    });

    private void ActualizarSincronizacion()
    {
        SyncState = _servicio.SyncState;
        var pendientes = _servicio.PendingSyncCount;
        (SyncText, SyncIcon) = SyncState switch
        {
            StudySyncState.Syncing => ("Sincronizando…", "estudio_sync_blue.png"),
            StudySyncState.PendingSend => (pendientes > 1 ? $"Pendiente de enviar · {pendientes}" : "Pendiente de enviar", "estudio_cloud_up_amber.png"),
            _ => ("Guardado", "estudio_cloud_check_green.png"),
        };
    }

    private void ActualizarDescargasGlobales()
    {
        var activas = Lessons.Where(i => i.IsDownloading || i.IsDownloadRequested).ToList();
        HasActiveDownloads = activas.Count > 0;
        if (activas.Count == 0)
        {
            GlobalDownloadProgress = 0;
            ActiveDownloadsText = string.Empty;
            return;
        }
        var total = activas.Sum(i => i.TotalBytes);
        GlobalDownloadProgress = total > 0 ? Math.Clamp((double)activas.Sum(i => i.DownloadedBytes) / total, 0, 1) : activas.Average(i => i.DownloadProgress);
        ActiveDownloadsText = activas.Count == 1 ? "Descargando 1 lección" : $"Descargando {activas.Count} lecciones";
    }

    private async Task ActualizarEspacioAsync()
    {
        try
        {
            var info = await _servicio.GetStorageAsync();
            var usado = $"{StudyFormat.Bytes(info.UsedBytes)} en tu tableta";
            var texto = info.FreeBytes is { } libre ? $"{usado} · {StudyFormat.Bytes(libre)} libres" : usado;
            await EnHiloUi(() => StorageText = texto);
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyModeViewModel.Espacio", ex); }
    }

    // =================================================================================== utilidades

    private static Task EnHiloUi(Action accion)
    {
        if (MainThread.IsMainThread)
        {
            accion();
            return Task.CompletedTask;
        }
        return MainThread.InvokeOnMainThreadAsync(accion);
    }

    public void Dispose()
    {
        Deactivate();
        _vida.Cancel();
        _vida.Dispose();
    }
}

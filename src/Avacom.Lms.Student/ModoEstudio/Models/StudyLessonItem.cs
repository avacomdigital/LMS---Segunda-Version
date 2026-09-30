using System.Windows.Input;

namespace Avacom.Lms.Student.ModoEstudio.Models;

/// <summary>
/// Lo que el ViewModel sabe hacer con una lección de la lista. El item lo recibe por constructor y expone comandos ya atados a él: así
/// la plantilla de la tarjeta se enlaza sólo al item (sin buscar al ViewModel «hacia arriba») y cada tarjeta actúa sobre sí misma.
/// </summary>
public interface IStudyLessonActions
{
    void Open(StudyLessonItem item);
    void Resume(StudyLessonItem item);
    void OpenCompleted(StudyLessonItem item);
    void Download(StudyLessonItem item);
    void PauseDownload(StudyLessonItem item);
    void ResumeDownload(StudyLessonItem item);
    void DeleteDownload(StudyLessonItem item);
    void ShowDownloadMenu(StudyLessonItem item);
    void OpenPractice(StudyLessonItem item);
    void RetryPractice(StudyLessonItem item);
    void ShowExamInfo(StudyLessonItem item);
}

/// <summary>
/// Una lección asignada tal como la pinta «Modo estudio · Mis lecciones». Es observable: cuando cambia el avance de una descarga o el
/// progreso de una lección, sólo se repinta ESA tarjeta (no se recrea la lista). Todos los textos que ve el alumno se calculan aquí,
/// en español y sin conceptos técnicos; los colores los pone la plantilla según <see cref="State"/> y <see cref="DownloadState"/>.
/// </summary>
public sealed class StudyLessonItem : ObservableObject
{
    private readonly IStudyLessonActions _acciones;

    public StudyLessonItem(string id, IStudyLessonActions acciones)
    {
        Id = id;
        _acciones = acciones;
        OpenCommand = new Command(() =>
        {
            if (State == StudyLessonState.Completed) _acciones.OpenCompleted(this);
            else if (CanResume) _acciones.Resume(this);
            else _acciones.Open(this);
        });
        DownloadCommand = new Command(() => _acciones.Download(this));
        PauseCommand = new Command(() => _acciones.PauseDownload(this));
        ResumeDownloadCommand = new Command(() => _acciones.ResumeDownload(this));
        DeleteDownloadCommand = new Command(() => _acciones.DeleteDownload(this));
        DownloadMenuCommand = new Command(() => _acciones.ShowDownloadMenu(this));
        PracticeCommand = new Command(() =>
        {
            if (PracticeAttempts > 0 && !PracticeInProgress) _acciones.RetryPractice(this);
            else _acciones.OpenPractice(this);
        });
        ExamInfoCommand = new Command(() => _acciones.ShowExamInfo(this));
    }

    // ------------------------------------------------------------------------------- comandos
    public ICommand OpenCommand { get; }
    public ICommand DownloadCommand { get; }
    public ICommand PauseCommand { get; }
    public ICommand ResumeDownloadCommand { get; }
    public ICommand DeleteDownloadCommand { get; }
    public ICommand DownloadMenuCommand { get; }
    public ICommand PracticeCommand { get; }
    public ICommand ExamInfoCommand { get; }

    // ----------------------------------------------------------------------------- identidad
    public string Id { get; }

    private string _subject = string.Empty, _unitName = string.Empty, _title = string.Empty, _description = string.Empty;
    public string Subject { get => _subject; set => SetProperty(ref _subject, value, tambien: [nameof(EyebrowText)]); }
    public string UnitName { get => _unitName; set => SetProperty(ref _unitName, value, tambien: [nameof(EyebrowText)]); }
    public string Title { get => _title; set => SetProperty(ref _title, value, tambien: [nameof(CardDescription)]); }
    public string Description { get => _description; set => SetProperty(ref _description, value, tambien: [nameof(SubtitleText), nameof(HasSubtitle)]); }

    /// <summary>«LENGUA CASTELLANA · UNIDAD 2».</summary>
    public string EyebrowText =>
        string.Join(" · ", new[] { Subject, UnitName }.Where(x => !string.IsNullOrWhiteSpace(x))).ToUpperInvariant();

    // --------------------------------------------------------------------------- fecha límite
    private DateTimeOffset? _dueDate, _completedOn;
    public DateTimeOffset? DueDate
    {
        get => _dueDate;
        set => SetProperty(ref _dueDate, value, tambien: [nameof(HasDue), nameof(DueText), nameof(DueChipText), nameof(HasDueChip), nameof(CardDescription)]);
    }

    public DateTimeOffset? CompletedOn
    {
        get => _completedOn;
        set => SetProperty(ref _completedOn, value, tambien: [nameof(CompletedText)]);
    }

    public bool HasDue => DueDate is not null && State != StudyLessonState.Completed;
    public string DueText => StudyFormat.Entrega(DueDate, StudyFormat.Ahora(), State == StudyLessonState.Completed);
    public string DueChipText => StudyFormat.MarcaDeEntrega(DueDate, StudyFormat.Ahora(), State == StudyLessonState.Completed);
    public bool HasDueChip => !string.IsNullOrEmpty(DueChipText);
    public string CompletedText => StudyFormat.CompletadaEl(CompletedOn, StudyFormat.Ahora());

    // ------------------------------------------------------------------------------- estado
    private StudyLessonState _state;
    public StudyLessonState State
    {
        get => _state;
        set => SetProperty(ref _state, value, tambien:
        [
            nameof(IsCompleted), nameof(IsInProgress), nameof(IsExpired), nameof(StateChipText), nameof(StateChipGlyph), nameof(StateChipLabel),
            nameof(PrimaryCtaText), nameof(SubtitleText), nameof(HasSubtitle), nameof(HasDue), nameof(DueText), nameof(DueChipText), nameof(HasDueChip),
            nameof(ShowProgress), nameof(CardDescription),
        ]);
    }

    public bool IsCompleted => State == StudyLessonState.Completed;
    public bool IsInProgress => State == StudyLessonState.InProgress;
    public bool IsExpired => State == StudyLessonState.Expired;

    public string StateChipText => State switch
    {
        StudyLessonState.Pending => "PENDIENTE",
        StudyLessonState.InProgress => "EN CURSO",
        StudyLessonState.Completed => "COMPLETADA",
        StudyLessonState.Expired => "VENCIDA",
        _ => string.Empty,
    };

    /// <summary>Icono + texto + color (UXR-011): el estado nunca se lee sólo por el color.</summary>
    public string StateChipGlyph => State switch
    {
        StudyLessonState.Pending => "○",
        StudyLessonState.InProgress => "◐",
        StudyLessonState.Completed => "✓",
        StudyLessonState.Expired => "!",
        _ => string.Empty,
    };

    public string StateChipLabel => $"{StateChipGlyph}  {StateChipText}";

    // ---------------------------------------------------------------------------- progreso
    private double _progress;
    private int _completedBlocks, _totalBlocks;
    private bool _canResume;
    private string _resumeLabel = string.Empty;

    /// <summary>De 0 a 1: los bloques obligatorios atendidos entre los obligatorios. NO es una nota (DEC-032).</summary>
    public double Progress
    {
        get => _progress;
        set => SetProperty(ref _progress, Math.Clamp(value, 0, 1),
            tambien: [nameof(ProgressPercent), nameof(ProgressText), nameof(ShowProgress), nameof(CardDescription)]);
    }

    public int CompletedBlocks { get => _completedBlocks; set => SetProperty(ref _completedBlocks, value); }
    public int TotalBlocks { get => _totalBlocks; set => SetProperty(ref _totalBlocks, value); }

    public bool CanResume
    {
        get => _canResume;
        set => SetProperty(ref _canResume, value, tambien: [nameof(PrimaryCtaText), nameof(SubtitleText), nameof(HasSubtitle)]);
    }

    /// <summary>«Continúa desde: Actividad 4 de 7» o «Último avance: Actividad 4 · 03:28». Vacío: «Continuarás donde quedaste».</summary>
    public string ResumeLabel
    {
        get => _resumeLabel;
        set => SetProperty(ref _resumeLabel, value ?? string.Empty, tambien: [nameof(SubtitleText), nameof(HasSubtitle)]);
    }

    public double ProgressPercent => Math.Round(Progress * 100);
    public string ProgressText => StudyFormat.Porcentaje(Progress);
    public bool ShowProgress => Progress > 0 || State == StudyLessonState.InProgress;

    public string PrimaryCtaText => State == StudyLessonState.Completed ? "Ver lección" : CanResume ? "Continuar lección" : "Comenzar lección";

    /// <summary>Bajo el título: dónde se quedó, o la descripción corta de la lección.</summary>
    public string SubtitleText => State == StudyLessonState.Completed
        ? Description
        : CanResume ? (string.IsNullOrWhiteSpace(ResumeLabel) ? "Continuarás donde quedaste" : ResumeLabel) : Description;

    public bool HasSubtitle => !string.IsNullOrWhiteSpace(SubtitleText);

    // ---------------------------------------------------------------------------- descarga
    private StudyDownloadState _downloadState;
    private double _downloadProgress;
    private long _downloadedBytes, _totalBytes;
    private TimeSpan? _remaining;
    private bool _canDownload = true;
    private string _downloadDeniedReason = string.Empty;

    public StudyDownloadState DownloadState
    {
        get => _downloadState;
        set => SetProperty(ref _downloadState, value, tambien:
        [
            nameof(IsDownloadNone), nameof(IsDownloadRequested), nameof(IsDownloading), nameof(IsDownloadPaused), nameof(IsDownloadAvailable),
            nameof(IsDownloadExpired), nameof(IsDownloadDenied), nameof(IsAvailableOffline), nameof(DownloadStatusText), nameof(DownloadPercentText),
            nameof(DownloadSizeText), nameof(CanStartDownload), nameof(CanOpen), nameof(OfflineHint), nameof(HasOfflineHint), nameof(CanUsePractice),
            nameof(DownloadDescription), nameof(CardDescription), nameof(IsActiveDownload),
        ]);
    }

    public double DownloadProgress
    {
        get => _downloadProgress;
        set => SetProperty(ref _downloadProgress, Math.Clamp(value, 0, 1),
            tambien: [nameof(DownloadPercentText), nameof(DownloadStatusText), nameof(DownloadDescription)]);
    }

    public long DownloadedBytes
    {
        get => _downloadedBytes;
        set => SetProperty(ref _downloadedBytes, value, tambien: [nameof(DownloadedOfTotalText)]);
    }

    public long TotalBytes
    {
        get => _totalBytes;
        set => SetProperty(ref _totalBytes, value, tambien: [nameof(DownloadedOfTotalText), nameof(DownloadSizeText)]);
    }

    /// <summary>Lo que falta por bajar, estimado por la velocidad. Nulo mientras no hay estimación.</summary>
    public TimeSpan? Remaining
    {
        get => _remaining;
        set => SetProperty(ref _remaining, value, tambien: [nameof(DownloadRemainingText), nameof(HasDownloadRemaining)]);
    }

    /// <summary>El nodo permite bajar el paquete de esta lección a este aparato (BR-054). Falso: «denegada».</summary>
    public bool CanDownload
    {
        get => _canDownload;
        set => SetProperty(ref _canDownload, value, tambien: [nameof(CanStartDownload)]);
    }

    public string DownloadDeniedReason
    {
        get => _downloadDeniedReason;
        set => SetProperty(ref _downloadDeniedReason, value ?? string.Empty);
    }

    public bool IsDownloadNone => DownloadState == StudyDownloadState.None;
    public bool IsDownloadRequested => DownloadState == StudyDownloadState.Requested;
    public bool IsDownloading => DownloadState == StudyDownloadState.Downloading;
    public bool IsDownloadPaused => DownloadState == StudyDownloadState.Paused;
    public bool IsDownloadAvailable => DownloadState == StudyDownloadState.Available;
    public bool IsDownloadExpired => DownloadState == StudyDownloadState.Expired;
    public bool IsDownloadDenied => DownloadState == StudyDownloadState.Denied;
    public bool IsAvailableOffline => DownloadState == StudyDownloadState.Available;
    public bool IsActiveDownload => DownloadState is StudyDownloadState.Downloading or StudyDownloadState.Requested;

    public string DownloadPercentText => StudyFormat.Porcentaje(DownloadProgress);
    public string DownloadSizeText => TotalBytes > 0 ? StudyFormat.Bytes(TotalBytes) : string.Empty;
    public string DownloadedOfTotalText => $"{StudyFormat.Bytes(DownloadedBytes)} de {StudyFormat.Bytes(TotalBytes)}";
    public string DownloadRemainingText => StudyFormat.Restante(Remaining) ?? string.Empty;
    public bool HasDownloadRemaining => Remaining is not null;

    /// <summary>La línea que acompaña a cada estado (spec §10). El botón lo pone la plantilla.</summary>
    public string DownloadStatusText => DownloadState switch
    {
        StudyDownloadState.Requested => "Preparando la descarga…",
        StudyDownloadState.Downloading => "Descargando contenido…",
        StudyDownloadState.Paused => $"Descarga pausada · {DownloadPercentText}",
        StudyDownloadState.Available => "Disponible sin conexión",
        StudyDownloadState.Expired => "El contenido descargado venció.",
        StudyDownloadState.Denied => string.IsNullOrWhiteSpace(DownloadDeniedReason)
            ? "Este dispositivo no permite descargar contenido para estudiar sin conexión."
            : DownloadDeniedReason,
        _ => string.Empty,
    };

    // ------------------------------------------------------------------------ sin conexión
    private bool _isOffline;

    /// <summary>Sin conexión con el aula. Lo descargado sigue habilitado; lo que necesita el aula se explica, sin errores técnicos.</summary>
    public bool IsOffline
    {
        get => _isOffline;
        set => SetProperty(ref _isOffline, value, tambien:
            [nameof(CanStartDownload), nameof(CanOpen), nameof(OfflineHint), nameof(HasOfflineHint), nameof(CanUsePractice)]);
    }

    public bool CanStartDownload => CanDownload && !IsOffline;
    public bool CanOpen => IsAvailableOffline || !IsOffline;
    public bool CanUsePractice => IsAvailableOffline || !IsOffline;

    public string OfflineHint => IsOffline && !IsAvailableOffline
        ? (IsDownloadNone || IsDownloadExpired ? "Con conexión con el aula podrás descargarla para estudiar sin red." : "Vuelve a conectarte al aula para abrirla.")
        : string.Empty;

    public bool HasOfflineHint => !string.IsNullOrEmpty(OfflineHint);

    // ------------------------------------------------------------------------ sincronización
    private bool _isPendingSync;

    /// <summary>Hay avance de esta lección guardado en la tableta que aún no llegó al aula (☁ Pendiente de sincronización).</summary>
    public bool IsPendingSync { get => _isPendingSync; set => SetProperty(ref _isPendingSync, value); }

    // ------------------------------------------------------------------------------ práctica
    private bool _hasPractice, _practiceInProgress;
    private int _practiceQuestionCount, _practiceAttempts;
    private int? _practiceBestScore;
    private string _practiceTitle = "Comprueba lo aprendido";

    public bool HasPractice { get => _hasPractice; set => SetProperty(ref _hasPractice, value); }
    public string PracticeTitle { get => _practiceTitle; set => SetProperty(ref _practiceTitle, string.IsNullOrWhiteSpace(value) ? "Comprueba lo aprendido" : value); }

    public int PracticeQuestionCount
    {
        get => _practiceQuestionCount;
        set => SetProperty(ref _practiceQuestionCount, value, tambien: [nameof(PracticeCaption), nameof(PracticeBestText), nameof(PracticeDescription)]);
    }

    public int PracticeAttempts
    {
        get => _practiceAttempts;
        set => SetProperty(ref _practiceAttempts, value, tambien: [nameof(PracticeCtaText), nameof(PracticeBestText), nameof(HasPracticeBest)]);
    }

    public bool PracticeInProgress
    {
        get => _practiceInProgress;
        set => SetProperty(ref _practiceInProgress, value, tambien: [nameof(PracticeCtaText)]);
    }

    /// <summary>Aciertos de su mejor intento (no una nota): «7 de 8».</summary>
    public int? PracticeBestScore
    {
        get => _practiceBestScore;
        set => SetProperty(ref _practiceBestScore, value, tambien: [nameof(PracticeBestText), nameof(HasPracticeBest), nameof(PracticeDescription)]);
    }

    public string PracticeCaption => $"{PracticeQuestionCount} {(PracticeQuestionCount == 1 ? "pregunta" : "preguntas")} · Autocalificable";
    public bool HasPracticeBest => PracticeBestScore is not null && PracticeAttempts > 0;
    public string PracticeBestText => HasPracticeBest
        ? $"Mejor resultado: {PracticeBestScore} de {PracticeQuestionCount} · puedes intentarlo nuevamente"
        : "Puedes intentarlo las veces que quieras";
    public string PracticeCtaText => PracticeInProgress ? "Continuar práctica" : PracticeAttempts > 0 ? "Intentar nuevamente" : "Practicar";

    // ---------------------------------------------------------------- evaluación formal (aparte)
    private bool _hasExam;
    private string _examTitle = string.Empty, _examAvailability = string.Empty;

    /// <summary>La evaluación formal de la unidad: sólo informativa. Nunca se practica desde aquí (BR-055).</summary>
    public bool HasExam { get => _hasExam; set => SetProperty(ref _hasExam, value); }
    public string ExamTitle { get => _examTitle; set => SetProperty(ref _examTitle, value); }
    public string ExamAvailability { get => _examAvailability; set => SetProperty(ref _examAvailability, value); }

    // ------------------------------------------------------------------------ accesibilidad
    public string CardDescription
    {
        get
        {
            var partes = new List<string> { Title, StateChipText.ToLowerInvariant() };
            if (ShowProgress) partes.Add($"progreso {ProgressPercent:0} por ciento");
            if (HasDue) partes.Add(DueText.Replace("Entrega:", "entrega").Replace("Venció el", "venció el"));
            if (IsAvailableOffline) partes.Add("disponible sin conexión");
            return string.Join(". ", partes.Where(p => !string.IsNullOrWhiteSpace(p))) + ".";
        }
    }

    public string DownloadDescription => DownloadState switch
    {
        StudyDownloadState.Downloading => $"Descarga de {Title}, {ProgressPercentFor(DownloadProgress)} por ciento completada.",
        StudyDownloadState.Paused => $"Descarga de {Title} pausada en {ProgressPercentFor(DownloadProgress)} por ciento.",
        StudyDownloadState.Available => $"{Title} está disponible sin conexión.",
        StudyDownloadState.Expired => $"El contenido descargado de {Title} venció.",
        StudyDownloadState.Denied => $"Este dispositivo no permite descargar {Title}.",
        _ => $"Descargar {Title}{(TotalBytes > 0 ? $", {DownloadSizeText}" : string.Empty)}.",
    };

    public string PracticeDescription => $"Práctica de estudio, {PracticeQuestionCount} {(PracticeQuestionCount == 1 ? "pregunta" : "preguntas")}."
        + (HasPracticeBest ? $" Mejor resultado {PracticeBestScore} de {PracticeQuestionCount}." : string.Empty);

    private static string ProgressPercentFor(double fraccion) => Math.Round(Math.Clamp(fraccion, 0, 1) * 100).ToString("0");

    /// <summary>Repinta lo que depende del reloj (fecha límite, «Vence hoy») sin tocar el resto.</summary>
    public void RefreshClock() => OnPropertiesChanged(nameof(DueText), nameof(DueChipText), nameof(HasDueChip), nameof(CardDescription));
}

using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Student.ModoEstudio.Models;

namespace Avacom.Lms.Student.ModoEstudio.Services;

/// <summary>
/// El estado compartido de la demostración: las lecciones de muestra, que el servicio de estudio y el de descargas leen y cambian juntos.
/// Cubre TODOS los estados de la pantalla para poder validarlos de un vistazo: sin descargar, descargando, pausada, disponible, vencida y
/// denegada; pendiente, en curso, completada y vencida; con y sin práctica; con evaluación formal aparte.
/// </summary>
internal sealed class MockStudyStore
{
    public readonly object Candado = new();
    public readonly List<StudyLessonData> Lessons;

    public MockStudyStore()
    {
        var ahora = StudyFormat.Ahora();
        DateTimeOffset A(int dias, int hora) => new(ahora.Date.AddDays(dias).AddHours(hora), ahora.Offset);
        const long Mb = 1024 * 1024;

        StudyLessonData Base(string id, string unidad, string titulo, string descripcion) => new(
            id, "Lengua Castellana", unidad, titulo, descripcion, null, null, 0, 0, 7, StudyLessonState.Pending, false, string.Empty,
            StudyDownloadState.None, 0, 0, 84 * Mb, true, string.Empty, true, "Comprueba lo aprendido", 8, 0, null, false,
            false, string.Empty, string.Empty, false);

        Lessons =
        [
            // 1 · en curso, descargada, con práctica y evaluación aparte; entrega mañana
            Base("mock-1", "Unidad 2", "Área y volumen con lenguaje algebraico", "Expresa el área y el volumen de figuras con letras.") with
            {
                State = StudyLessonState.InProgress, Progress = 0.62, CompletedBlocks = 4, CanResume = true, ResumeLabel = "Continúa desde: Actividad 4 de 7",
                DueDate = A(1, 16), DownloadState = StudyDownloadState.Available, DownloadProgress = 1, DownloadedBytes = 84 * Mb,
                PracticeAttempts = 2, PracticeBestScore = 7, HasExam = true, ExamTitle = "Evaluación de la Unidad 2",
                ExamAvailability = "Disponible desde el 20 de octubre",
            },
            // 2 · pendiente, sin descargar (84 MB), con práctica
            Base("mock-2", "Unidad 2", "Geometría y medida", "Medidas, unidades y figuras planas.") with { DueDate = A(6, 12) },
            // 3 · en curso, descargándose (64 %: 54 MB de 84 MB)
            Base("mock-3", "Unidad 3", "Literatura latinoamericana", "Autores, épocas y voces del continente.") with
            {
                State = StudyLessonState.InProgress, Progress = 0.35, CompletedBlocks = 2, DueDate = A(9, 18),
                DownloadState = StudyDownloadState.Downloading, DownloadProgress = 0.64, DownloadedBytes = 54 * Mb, HasPractice = false,
            },
            // 4 · completada, disponible sin conexión
            Base("mock-4", "Unidad 1", "Textos argumentativos", "Tesis, argumentos y conclusiones.") with
            {
                State = StudyLessonState.Completed, Progress = 1, CompletedBlocks = 7, CompletedOn = A(-3, 15), DownloadState = StudyDownloadState.Available,
                DownloadProgress = 1, DownloadedBytes = 84 * Mb, HasPractice = false,
            },
            // 5 · pendiente, descarga denegada (aparato sin permiso)
            Base("mock-5", "Unidad 3", "Análisis de textos", "Ideas principales, secundarias y tono.") with
            {
                DueDate = A(3, 14), DownloadState = StudyDownloadState.Denied, CanDownload = false, HasPractice = false,
                DownloadDeniedReason = "Este dispositivo no permite descargar contenido para estudiar sin conexión.",
            },
            // 6 · vencida, con su descarga vencida
            Base("mock-6", "Unidad 1", "Ortografía y puntuación", "Reglas de acentuación y uso de la coma.") with
            {
                State = StudyLessonState.Expired, Progress = 0.28, CompletedBlocks = 2, CanResume = true, DueDate = A(-2, 17),
                DownloadState = StudyDownloadState.Expired, DownloadProgress = 1, DownloadedBytes = 84 * Mb,
            },
            // 7 · pendiente, descarga pausada (41 %)
            Base("mock-7", "Unidad 3", "Comprensión lectora", "Leer con atención y responder con evidencia.") with
            {
                DueDate = A(0, 20), DownloadState = StudyDownloadState.Paused, DownloadProgress = 0.41, DownloadedBytes = 34 * Mb, HasPractice = false,
            },
        ];
    }

    public StudyLessonData? Find(string id) => Lessons.FirstOrDefault(l => l.Id == id);

    /// <summary>Reemplaza la lección por su versión modificada y la devuelve.</summary>
    public StudyLessonData Update(string id, Func<StudyLessonData, StudyLessonData> cambio)
    {
        lock (Candado)
        {
            var i = Lessons.FindIndex(l => l.Id == id);
            if (i < 0) throw new KeyNotFoundException(id);
            return Lessons[i] = cambio(Lessons[i]);
        }
    }

    public long UsedBytes() => Lessons.Where(l => l.DownloadState is StudyDownloadState.Available or StudyDownloadState.Expired
        or StudyDownloadState.Paused or StudyDownloadState.Downloading).Sum(l => l.DownloadedBytes);
}

/// <summary>El servicio de demostración: datos de muestra, práctica que se califica en el propio servicio y sincronización simulada.</summary>
internal sealed class MockStudyModeService : IStudyModeService
{
    private readonly MockStudyStore _almacen;
    private StudySyncState _estado = StudySyncState.Saved;
    private int _pendientes;

    public MockStudyModeService(MockStudyStore almacen) => _almacen = almacen;

    public bool IsDemo => true;
    public event Action<StudyLessonData>? LessonChanged;
    public event Action? SyncStateChanged;
    public StudySyncState SyncState => _estado;
    public int PendingSyncCount => _pendientes;

    // ------------------------------------------------------------------------- ¿quién eres? (D-15)
    private static readonly StudyStudent[] Compañeros =
    [
        new("demo-ethan", "Ethan Martínez"), new("demo-sofia", "Sofía Ramírez"), new("demo-mateo", "Mateo Gómez"),
        new("demo-valentina", "Valentina Cruz"), new("demo-daniel", "Daniel Ortiz"),
    ];

    private StudyStudent? _actual, _ultimo;

    public StudyStudent? CurrentStudent => _actual;

    public async Task<StudyRoster> GetRosterAsync(CancellationToken ct = default)
    {
        await Task.Delay(350, ct);
        return new StudyRoster([new StudyRosterGroup("demo-5b", "Quinto B", Compañeros)], Owner: Compañeros[0], Last: _ultimo, FromCache: false, AulaReachable: true, Notice: null);
    }

    public Task<bool> ChooseStudentAsync(StudyStudent student, CancellationToken ct = default)
    {
        _actual = _ultimo = student;
        return Task.FromResult(true);
    }

    public Task ChangeStudentAsync(CancellationToken ct = default)
    {
        _actual = null;   // el último se conserva: es la sugerencia de «Continuar como…»
        return Task.CompletedTask;
    }

    public async Task<StudyListResult> LoadAsync(CancellationToken ct = default)
    {
        if (_actual is null) return StudyListResult.AskWho;
        await Task.Delay(650, ct);   // el esqueleto se ve un instante, como con el aula
        lock (_almacen.Candado) return new StudyListResult([.. _almacen.Lessons], false, true, null);
    }

    public Task<StudyStorageInfo> GetStorageAsync() =>
        Task.FromResult(new StudyStorageInfo(_almacen.UsedBytes(), 32L * 1024 * 1024 * 1024 + 700L * 1024 * 1024));

    public async Task SyncNowAsync(CancellationToken ct = default)
    {
        if (_pendientes == 0) return;
        Poner(StudySyncState.Syncing, _pendientes);
        await Task.Delay(1400, ct);
        Poner(StudySyncState.Saved, 0);
    }

    private void Poner(StudySyncState estado, int pendientes)
    {
        _estado = estado;
        _pendientes = pendientes;
        SyncStateChanged?.Invoke();
    }

    /// <summary>La demostración imita la cola: una respuesta o un bloque «se guarda», queda pendiente un momento y luego «llega».</summary>
    internal void SimularGuardado(string lessonId, Func<StudyLessonData, StudyLessonData> cambio)
    {
        var dato = _almacen.Update(lessonId, l => cambio(l) with { IsPendingSync = true });
        LessonChanged?.Invoke(dato);
        Poner(StudySyncState.PendingSend, Math.Max(1, _pendientes + 1));
        _ = Task.Run(async () =>
        {
            await Task.Delay(1200);
            Poner(StudySyncState.Syncing, _pendientes);
            await Task.Delay(1400);
            var listo = _almacen.Update(lessonId, l => l with { IsPendingSync = false });
            LessonChanged?.Invoke(listo);
            Poner(StudySyncState.Saved, 0);
        });
    }

    public Task<StudyLessonOpen> OpenLessonAsync(string lessonId, CancellationToken ct = default)
    {
        var dato = _almacen.Find(lessonId);
        if (dato is null) return Task.FromResult(new StudyLessonOpen(null, "No encontramos la lección", "Vuelve a la lista e inténtalo de nuevo."));
        return Task.FromResult(new StudyLessonOpen(new MockLessonSession(this, dato), null, null));
    }

    public Task<StudyPracticeOpen> OpenPracticeAsync(string lessonId, bool retry, CancellationToken ct = default)
    {
        var dato = _almacen.Find(lessonId);
        if (dato is null) return Task.FromResult(new StudyPracticeOpen(null, "No encontramos la práctica", "Vuelve a la lista e inténtalo de nuevo."));
        var numero = dato.PracticeAttempts + 1;
        return Task.FromResult(new StudyPracticeOpen(new MockPracticeSession(this, dato, numero), null, null));
    }

    public Task CloseSessionAsync(CancellationToken ct = default) => Task.CompletedTask;

    public Uri ResolveMedia(string lessonId, string relativeUrl) => new(new Uri("http://localhost/"), relativeUrl.TrimStart('/'));

    public string ExamExplanation(string lessonId) =>
        "La evaluación de la unidad la aplica tu profesor en clase o cuando él la abra. No es parte de la práctica: aquí puedes prepararte todas las veces que quieras, sin que cuente como nota.";

    internal StudyLessonData? Datos(string lessonId) => _almacen.Find(lessonId);

    internal void PracticaTerminada(string lessonId, int correctas, int total)
    {
        SimularGuardado(lessonId, l => l with
        {
            PracticeAttempts = l.PracticeAttempts + 1,
            PracticeBestScore = Math.Max(l.PracticeBestScore ?? 0, correctas),
            PracticeInProgress = false,
        });
    }

    internal void BloqueAtendido(string lessonId, int atendidos, int total, string rotuloReanudar, bool completada)
    {
        SimularGuardado(lessonId, l => l with
        {
            CompletedBlocks = atendidos,
            TotalBlocks = total,
            Progress = total == 0 ? 0 : Math.Min(1.0, (double)atendidos / total),
            State = completada ? StudyLessonState.Completed : atendidos > 0 && l.State != StudyLessonState.Expired ? StudyLessonState.InProgress : l.State,
            CompletedOn = completada ? StudyFormat.Ahora() : l.CompletedOn,
            CanResume = !completada && atendidos > 0,
            ResumeLabel = completada ? string.Empty : rotuloReanudar,
        });
    }
}

/// <summary>Una lección de demostración abierta: siete bloques (tres láminas, dos páginas, un laboratorio y la práctica).</summary>
internal sealed class MockLessonSession : IStudyLessonSession
{
    private readonly MockStudyModeService _servicio;
    private readonly HashSet<string> _atendidos = new();
    private readonly List<StudyBlock> _bloques;

    public MockLessonSession(MockStudyModeService servicio, StudyLessonData dato)
    {
        _servicio = servicio;
        LessonId = dato.Id;
        Title = dato.Title;
        Eyebrow = $"{dato.Subject} · {dato.UnitName}".ToUpperInvariant();
        IsOfflineContent = dato.DownloadState == StudyDownloadState.Available;

        var presentacion = MockStudyContent.Presentacion();
        var lectura = MockStudyContent.Lectura();
        var laboratorio = MockStudyContent.Laboratorio();
        var practica = MockStudyContent.Practica();
        var lista = new List<StudyBlock>();
        var n = 0;
        foreach (var lamina in presentacion.Unidades)
            lista.Add(new StudyBlock($"{presentacion.ObjetoRef}:{lamina.UnidadRef}", ++n, "lamina", lamina.Titulo ?? presentacion.Titulo, true, false, presentacion, lamina.UnidadRef));
        foreach (var pagina in lectura.Unidades)
            lista.Add(new StudyBlock($"{lectura.ObjetoRef}:{pagina.UnidadRef}", ++n, "pagina", pagina.Titulo ?? lectura.Titulo, true, false, lectura, pagina.UnidadRef));
        lista.Add(new StudyBlock(laboratorio.ObjetoRef, ++n, "laboratorio", laboratorio.Titulo, true, false, laboratorio, null));
        lista.Add(new StudyBlock(practica.ObjetoRef, ++n, "practica", practica.Titulo, true, false, practica, null));
        _bloques = lista;

        // Lo ya visto: tantos bloques como diga el avance de la lección.
        for (var i = 0; i < Math.Min(dato.CompletedBlocks, _bloques.Count); i++) _atendidos.Add(_bloques[i].Ref);
        StartIndex = dato.State == StudyLessonState.Completed ? 0 : Math.Clamp(dato.CompletedBlocks, 0, _bloques.Count - 1);
        IsReadOnly = false;
        IsCompleted = dato.State == StudyLessonState.Completed;
    }

    public string LessonId { get; }
    public string Title { get; }
    public string Eyebrow { get; }
    public IReadOnlyList<StudyBlock> Blocks => _bloques;
    public int StartIndex { get; }
    public bool IsOfflineContent { get; }
    public bool IsReadOnly { get; }
    public bool IsCompleted { get; private set; }
    public event Action? Changed;

    public Uri Resolve(string relativeUrl) => new(new Uri("http://localhost/"), relativeUrl.TrimStart('/'));

    public bool IsAttended(StudyBlock block) => _atendidos.Contains(block.Ref);
    public int Required => _bloques.Count(b => b.Required);
    public int AttendedRequired => _bloques.Count(b => b.Required && _atendidos.Contains(b.Ref));
    public bool AllRequiredAttended => AttendedRequired >= Required;

    public Task RefreshAsync(CancellationToken ct = default)
    {
        var dato = _servicio.Datos(LessonId);
        var practica = _bloques.FirstOrDefault(b => b.IsPractice);
        if (dato is { PracticeAttempts: > 0 } && practica is not null && _atendidos.Add(practica.Ref)) Changed?.Invoke();
        return Task.CompletedTask;
    }

    public Task MarkViewedAsync(StudyBlock block, CancellationToken ct = default)
    {
        if (!_atendidos.Add(block.Ref)) return Task.CompletedTask;
        var siguiente = _bloques.FirstOrDefault(b => !_atendidos.Contains(b.Ref));
        var rotulo = siguiente is null ? string.Empty : $"Continúa desde: Actividad {siguiente.Index} de {_bloques.Count}";
        _servicio.BloqueAtendido(LessonId, AttendedRequired, _bloques.Count, rotulo, completada: false);
        Changed?.Invoke();
        return Task.CompletedTask;
    }

    public Task<StudyCompleteResult> CompleteAsync(CancellationToken ct = default)
    {
        if (!AllRequiredAttended)
        {
            var faltan = _bloques.Where(b => b.Required && !_atendidos.Contains(b.Ref)).Select(b => b.Title).ToList();
            return Task.FromResult(new StudyCompleteResult(false, "Todavía te faltan actividades por ver.", faltan));
        }
        _servicio.BloqueAtendido(LessonId, _bloques.Count, _bloques.Count, string.Empty, completada: true);
        IsCompleted = true;
        Changed?.Invoke();
        return Task.FromResult(new StudyCompleteResult(true, "¡Lección completada!", []));
    }
}

/// <summary>La práctica de demostración: se califica al instante con la clave de <see cref="MockStudyContent"/> (sólo aquí existe una clave local).</summary>
internal sealed class MockPracticeSession : IStudyPracticeSession
{
    private readonly MockStudyModeService _servicio;
    private readonly StudyLessonData _dato;
    private readonly Dictionary<string, (JsonElement Answer, StudyAnswerVerdict Verdict)> _respuestas = new();

    public MockPracticeSession(MockStudyModeService servicio, StudyLessonData dato, int numero)
    {
        _servicio = servicio;
        _dato = dato;
        Number = numero;
        Activity = MockStudyContent.Practica();
        Title = Activity.Titulo;
    }

    public string Title { get; }
    public ObjetoAula Activity { get; }
    public int Number { get; }
    public bool CanGradeNow => true;

    public IReadOnlyDictionary<string, (JsonElement Answer, StudyAnswerVerdict? Verdict)> Previous { get; } =
        new Dictionary<string, (JsonElement, StudyAnswerVerdict?)>();

    public async Task<StudyAnswerVerdict> SubmitAsync(PreguntaAula question, JsonElement answer, CancellationToken ct = default)
    {
        await Task.Delay(220, ct);   // el aula responde en menos de 2 s (NFR-012); aquí, en una fracción
        var correcta = MockStudyContent.EsCorrecta(question.PreguntaRef, answer);
        var veredicto = new StudyAnswerVerdict(question.PreguntaRef, correcta, false, [MockStudyContent.Retroalimentacion(question.PreguntaRef, correcta)]);
        _respuestas[question.PreguntaRef] = (answer.Clone(), veredicto);
        return veredicto;
    }

    public Task<StudyPracticeResult> FinishAsync(CancellationToken ct = default)
    {
        var preguntas = Activity.Preguntas ?? [];
        var revision = preguntas.Select((p, i) => new StudyPracticeReview(
            p.PreguntaRef, i + 1, p.Enunciado,
            _respuestas.TryGetValue(p.PreguntaRef, out var r) ? r.Verdict.Correct : false,
            _respuestas.TryGetValue(p.PreguntaRef, out var rr) ? rr.Verdict.Feedback : ["Sin responder."])).ToList();
        var correctas = revision.Count(r => r.Correct == true);
        var total = preguntas.Count;
        var mensaje = correctas * 100 >= total * 85 ? "¡Muy bien!" : correctas * 100 >= total * 60 ? "¡Buen avance!" : "Sigue practicando: puedes intentarlo otra vez.";
        _servicio.PracticaTerminada(_dato.Id, correctas, total);
        return Task.FromResult(new StudyPracticeResult(correctas, total, mensaje, 0, revision));
    }
}

/// <summary>Descargas de demostración: un avance simulado del 2–4 % cada cuarto de segundo, con pausa, continuación y borrado.</summary>
internal sealed class MockDownloadService : IDownloadService
{
    private readonly MockStudyStore _almacen;
    private readonly Dictionary<string, CancellationTokenSource> _activas = new();
    private readonly Random _azar = new(7);

    public MockDownloadService(MockStudyStore almacen)
    {
        _almacen = almacen;
        // La lección 3 «ya venía descargándose» al abrir la pantalla: se reanuda sola para que se vea el avance.
        foreach (var l in _almacen.Lessons.Where(l => l.DownloadState == StudyDownloadState.Downloading).ToList()) _ = Correr(l.Id);
    }

    public event Action<StudyDownloadUpdate>? Updated;

    public bool IsActive(string lessonId) => _activas.ContainsKey(lessonId);

    public Task StartAsync(string lessonId)
    {
        if (!_activas.ContainsKey(lessonId)) _ = Correr(lessonId);
        return Task.CompletedTask;
    }

    public void Pause(string lessonId)
    {
        if (_activas.TryGetValue(lessonId, out var cts)) cts.Cancel();
    }

    public Task DeleteAsync(string lessonId)
    {
        Pause(lessonId);
        var d = _almacen.Update(lessonId, l => l with { DownloadState = StudyDownloadState.None, DownloadProgress = 0, DownloadedBytes = 0 });
        Updated?.Invoke(new StudyDownloadUpdate(lessonId, StudyDownloadState.None, 0, 0, d.TotalBytes, null));
        return Task.CompletedTask;
    }

    private async Task Correr(string lessonId)
    {
        var cts = new CancellationTokenSource();
        _activas[lessonId] = cts;
        try
        {
            var inicio = _almacen.Find(lessonId)!;
            Publicar(lessonId, StudyDownloadState.Requested, inicio.DownloadProgress, inicio.DownloadedBytes, inicio.TotalBytes, null);
            await Task.Delay(500, cts.Token);
            var progreso = inicio.DownloadProgress;
            var total = inicio.TotalBytes;
            var ritmo = 2.4 * 1024 * 1024;   // bytes por segundo simulados
            while (progreso < 1)
            {
                await Task.Delay(250, cts.Token);
                progreso = Math.Min(1, progreso + (0.02 + _azar.NextDouble() * 0.02));
                var bajados = (long)(total * progreso);
                var restante = TimeSpan.FromSeconds(Math.Max(1, (total - bajados) / ritmo));
                Publicar(lessonId, StudyDownloadState.Downloading, progreso, bajados, total, restante);
            }
            await Task.Delay(300, cts.Token);
            Publicar(lessonId, StudyDownloadState.Available, 1, total, total, null);
        }
        catch (OperationCanceledException)
        {
            var actual = _almacen.Find(lessonId);
            if (actual is not null && actual.DownloadState == StudyDownloadState.Downloading)
                Publicar(lessonId, StudyDownloadState.Paused, actual.DownloadProgress, actual.DownloadedBytes, actual.TotalBytes, null);
            else if (actual is not null && actual.DownloadState == StudyDownloadState.Requested)
                Publicar(lessonId, StudyDownloadState.None, 0, 0, actual.TotalBytes, null);
        }
        finally { _activas.Remove(lessonId); }
    }

    private void Publicar(string id, StudyDownloadState estado, double progreso, long bajados, long total, TimeSpan? restante)
    {
        _almacen.Update(id, l => l with { DownloadState = estado, DownloadProgress = progreso, DownloadedBytes = bajados });
        Updated?.Invoke(new StudyDownloadUpdate(id, estado, progreso, bajados, total, restante));
    }
}

/// <summary>El aula «siempre está» en la demostración, salvo que se arranque sin conexión para verla (<c>AVACOM_ESTUDIO_DEMO_OFFLINE=1</c>).</summary>
internal sealed class MockConnectivityService : IConnectivityService
{
    private bool _enLinea = Environment.GetEnvironmentVariable("AVACOM_ESTUDIO_DEMO_OFFLINE") != "1";

    public bool IsOnline => _enLinea;
    public event Action<bool>? Changed;

    public Task<bool> ProbeAsync(CancellationToken ct = default) => Task.FromResult(_enLinea);

    public void Set(bool enLinea)
    {
        if (_enLinea == enLinea) return;
        _enLinea = enLinea;
        Changed?.Invoke(enLinea);
    }
}

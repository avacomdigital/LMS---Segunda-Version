using System.Text.Json;
using System.Text.RegularExpressions;
using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Student.ModoEstudio.Models;

namespace Avacom.Lms.Student.ModoEstudio.Services;

/// <summary>Lo que el servicio necesita saber del aparato para presentarse al aula (nombre, plataforma y versión de la app).</summary>
internal sealed record DatosDelAparato(string Nombre, string Plataforma, string Version);

/// <summary>
/// El servicio real del modo de estudio (MOD-008) en la tableta: mezcla lo que dice el aula (<see cref="IEstudioApi"/>) con lo que hay en la
/// propia tableta (almacén cifrado, cola cifrada, paquetes descargados) y no depende de que el aula conteste. Reglas que cumple aquí:
/// <list type="bullet">
/// <item>Offline-first (BR-059, BR-137): todo lo que el alumno hace —bloques vistos, respuestas de la práctica, lección completada— se guarda
/// PRIMERO en la tableta (avance local y cola cifrada) y sale solo hacia el aula cuando la ve. La pantalla nunca espera a la red.</item>
/// <item>Lo descargado se lee sin red (BR-054): la lección sale del paquete cifrado y sus medios, del servidor local en 127.0.0.1.</item>
/// <item>La práctica es aparte de la evaluación formal (BR-055): se califica con el aula en ≤ 2 s; sin ella se guarda y se califica al integrarse.
/// La clave de respuesta nunca está en la tableta.</item>
/// <item>«Salir» (008-07, BR-053): cierra la sesión en el aula, borra lo personal de la tableta y destruye la clave; si queda trabajo sin enviar
/// se conserva SOLO esa cola cifrada (y su clave) hasta que salga, y la limpieza completa se termina después (FUN-090).</item>
/// </list>
/// </summary>
internal sealed class StudyModeService : IStudyModeService, IDisposable
{
    internal static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    private readonly EstudioLocal _local;
    private readonly DownloadService _descargas;
    private readonly ConnectivityService _conectividad;
    private readonly DatosDelAparato _aparato;
    private readonly Func<CancellationToken, Task> _registrarAparato;
    private readonly object _candado = new();
    private readonly Dictionary<string, AsignacionAlumno> _asignaciones = new(StringComparer.Ordinal);
    private readonly HashSet<string> _desdePaquete = new(StringComparer.Ordinal);
    private AsignacionesEstudio? _lista;
    private bool _sesionAbierta;
    private bool _confirmado;          // la persona ya dijo quién es en ESTA ejecución (el último nombre sólo se ofrece, nunca se da por hecho)
    private int _sincronizando, _programada;
    private StudySyncState _estadoSync = StudySyncState.Saved;
    private Timer? _reloj;

    public StudyModeService(EstudioLocal local, DownloadService descargas, ConnectivityService conectividad, DatosDelAparato aparato,
                            Func<CancellationToken, Task> registrarAparato)
    {
        _local = local;
        _descargas = descargas;
        _conectividad = conectividad;
        _aparato = aparato;
        _registrarAparato = registrarAparato;
        _local.Cola.Cambio += AlCambiarLaCola;
        _local.Sincronizador.Integrado += AlIntegrarse;
        _descargas.Updated += AlActualizarseUnaDescarga;
        // Un latido lento por si algo quedó pendiente y el aula vuelve sin que nadie toque nada.
        _reloj = new Timer(_ => AlLatir(), null, TimeSpan.FromSeconds(30), TimeSpan.FromSeconds(30));
        _estadoSync = Recalcular();
    }

    public bool IsDemo => false;
    public event Action<StudyLessonData>? LessonChanged;
    public event Action? SyncStateChanged;

    private IEstudioApi Api => _local.Api;
    internal EstudioLocal Local => _local;
    internal string Alumno => _local.AlumnoId ?? throw new InvalidOperationException("Todavía no se sabe de quién es esta tableta.");

    // ============================================================================ quién estudia (D-15)

    /// <summary>
    /// «¿Quién eres?»: el LMS es offline y no hay un sistema central que verifique a nadie, así que la persona dice su nombre (entre los de los grupos
    /// con lecciones asignadas) y el profesor ve su avance con ese nombre. Sin código y sin contraseña. Se pregunta cada vez que se abre el modo de
    /// estudio en una ejecución nueva; el último nombre se ofrece primero para seguir con un toque.
    /// </summary>
    public StudyStudent? CurrentStudent =>
        _confirmado && _local.AlumnoId is { } id ? new StudyStudent(id, _local.AlumnoRotulo ?? id) : null;

    public async Task<StudyRoster> GetRosterAsync(CancellationToken ct = default)
    {
        EstudiantesEstudio? nombres;
        try
        {
            nombres = await Api.EstudiantesAsync(_local.Dispositivo, ct);
            if (nombres is { Disponible: false, Motivo: "dispositivo_desconocido" })
            {
                // Una tableta que nunca entró a una clase: se da de alta (registro idempotente por su huella) y se vuelve a preguntar.
                await _registrarAparato(ct);
                nombres = await Api.EstudiantesAsync(_local.Dispositivo, ct) ?? nombres;
            }
        }
        catch (OperationCanceledException) { throw; }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "StudyModeService.GetRoster", ex);
            nombres = null;
        }

        var visible = nombres is not null;
        _conectividad.Informar(visible);
        string? aviso = null;
        if (nombres is not null)
        {
            Aprender(nombres.ServidorEn);
            if (nombres.Disponible) _local.GuardarNombres(nombres);
            else aviso = AvisoDeEstado(nombres.Motivo);
        }
        else
        {
            nombres = _local.LeerNombres();   // sin aula: lo último que se supo, para poder elegir el nombre igual
        }

        var grupos = (nombres?.Grupos ?? [])
            .Select(g => new StudyRosterGroup(g.Id, string.IsNullOrWhiteSpace(g.Nombre) ? g.Codigo is { Length: > 0 } c ? c : "Alumnos" : g.Nombre!,
                [.. g.Alumnos.Select(a => new StudyStudent(a.Id, string.IsNullOrWhiteSpace(a.Rotulo) ? a.Id : a.Rotulo!))
                    .OrderBy(a => a.Name, StringComparer.CurrentCultureIgnoreCase)]))
            .Where(g => g.Students.Count > 0)
            .OrderBy(g => g.Name, StringComparer.CurrentCultureIgnoreCase)
            .ToList();
        var dueno = nombres?.Dueno is { } d ? new StudyStudent(d.Id, string.IsNullOrWhiteSpace(d.Rotulo) ? d.Id : d.Rotulo!) : null;
        var ultimo = _local.AlumnoId is { } u ? new StudyStudent(u, _local.AlumnoRotulo ?? u) : null;
        if (aviso is null && grupos.Count == 0)
            aviso = visible
                ? "Todavía no hay lecciones asignadas para ningún grupo. Cuando tu profesor las asigne, tu nombre aparecerá aquí."
                : "Sin conexión con el aula y todavía no hay nombres guardados. Conéctate al aula una vez para elegir el tuyo.";
        return new StudyRoster(grupos, dueno, ultimo, FromCache: !visible && grupos.Count > 0, AulaReachable: visible, aviso);
    }

    public Task<bool> ChooseStudentAsync(StudyStudent student, CancellationToken ct = default)
    {
        try
        {
            var anterior = _local.AlumnoId;
            if (anterior is not null && anterior != student.Id)
            {
                // Otra persona en la misma tableta (BR-053): lo personal de la anterior se va. Su trabajo sin enviar queda en la cola y sale solo.
                _descargas.PauseAll();
                _local.Almacen.OlvidarAlumno(anterior);
            }
            lock (_candado) { _asignaciones.Clear(); _desdePaquete.Clear(); _lista = null; }
            _local.RecordarAlumno(student.Id, student.Name);
            _sesionAbierta = false;
            _confirmado = true;
            Poner(Recalcular());
            return Task.FromResult(true);
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "StudyModeService.ChooseStudent", ex);
            return Task.FromResult(false);
        }
    }

    public Task ChangeStudentAsync(CancellationToken ct = default)
    {
        // Sólo se vuelve a preguntar: lo de la persona actual no se toca hasta que otra se elija (si es la misma, sigue donde iba).
        _descargas.PauseAll();
        lock (_candado) { _asignaciones.Clear(); _desdePaquete.Clear(); _lista = null; }
        _sesionAbierta = false;
        _confirmado = false;
        return Task.CompletedTask;
    }

    private sealed record Identidad(bool Ok, bool AulaVisible, string? Aviso);

    /// <summary>
    /// ¿Se puede estudiar desde esta tableta como la persona elegida? Se pregunta al aula (<c>GET /estado/</c>, que no falla) y se abre la sesión de
    /// estudio una vez por elección. Sin aula, se sigue con lo guardado. Una tableta que nunca entró a una clase se da de alta primero.
    /// </summary>
    private async Task<Identidad> IdentificarAsync(CancellationToken ct)
    {
        if (!_confirmado || _local.AlumnoId is null) return new(false, false, null);
        if (_sesionAbierta) return new(true, true, null);
        var estado = await Api.EstadoAsync(_local.Dispositivo, Alumno, ct);
        if (estado is null)
        {
            _conectividad.Informar(false);
            return new(true, false, null);
        }
        _conectividad.Informar(true);
        Aprender(estado.ServidorEn);
        if (estado is { Disponible: false, Motivo: "dispositivo_desconocido" })
        {
            await _registrarAparato(ct);
            estado = await Api.EstadoAsync(_local.Dispositivo, Alumno, ct) ?? estado;
        }
        if (!estado.Disponible) return new(false, true, AvisoDeEstado(estado.Motivo));
        await AbrirSesionAsync(ct);
        return new(true, true, null);
    }

    private async Task AbrirSesionAsync(CancellationToken ct)
    {
        if (_sesionAbierta) return;
        var sesion = await Api.AbrirSesionAsync(_local.Dispositivo, _aparato.Nombre, _aparato.Plataforma, _aparato.Version, Alumno, ct);
        if (sesion is null) return;   // no es grave: se vuelve a intentar en la próxima carga
        Aprender(sesion.ServidorEn);
        _sesionAbierta = true;
        _local.RecordarAlumno(sesion.Alumno.Id, sesion.Alumno.Rotulo ?? _local.AlumnoRotulo);
    }

    private static void Aprender(long servidorEn)
    {
        if (servidorEn > 0) RelojNodo.Aprender(servidorEn);
    }

    private static string AvisoDeEstado(string? motivo) => motivo switch
    {
        "dispositivo_bloqueado" => "Esta tableta está bloqueada. Habla con tu profesor.",
        "dispositivo_desconocido" => "Esta tableta todavía no está registrada en el aula. Conéctate al aula e inténtalo otra vez.",
        "dispositivo_inactivo" => "Esta tableta fue retirada del aula.",
        "nodo_no_instalado" => "El aula todavía no está lista. Avisa a tu profesor.",
        _ => "El modo de estudio no está disponible en esta tableta por ahora.",
    };

    // ==================================================================================== la lista

    public async Task<StudyListResult> LoadAsync(CancellationToken ct = default)
    {
        if (!_confirmado || _local.AlumnoId is null) return StudyListResult.AskWho;
        var identidad = await IdentificarAsync(ct);
        if (!identidad.Ok) return new StudyListResult([], false, identidad.AulaVisible, identidad.Aviso);
        var alumno = Alumno;

        AsignacionesEstudio? lista = null;
        if (identidad.AulaVisible)
        {
            lista = await Api.AsignacionesAsync(_local.Dispositivo, alumno, ct);
            _conectividad.Informar(lista is not null);
            if (lista is not null)
            {
                Aprender(lista.ServidorEn);
                _local.Almacen.GuardarLista(alumno, lista);
            }
        }
        var visible = lista is not null;
        lista ??= _local.Almacen.LeerLista(alumno);
        if (lista is null)
            return new StudyListResult([], true, false, "Sin conexión con el aula y todavía no hay lecciones guardadas en esta tableta.");

        RegistrarLista(lista);
        // MSG-045: lo descargado que ya venció se libera solo (no se sirve contenido caducado); se le dice a la persona para que no se sorprenda.
        string? aviso = null;
        try
        {
            var (liberados, _) = _local.Almacen.LiberarVencidos(alumno, RelojNodo.AhoraMs);
            if (liberados > 0)
                aviso = liberados == 1
                    ? "Liberamos una lección descargada que ya venció. Puedes volver a descargarla."
                    : $"Liberamos {liberados} lecciones descargadas que ya vencieron. Puedes volver a descargarlas.";
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyModeService.LiberarVencidos", ex); }
        return new StudyListResult(MapearTodo(), !visible, visible, aviso);
    }

    private void RegistrarLista(AsignacionesEstudio lista)
    {
        lock (_candado)
        {
            _lista = lista;
            _asignaciones.Clear();
            foreach (var a in lista.Asignaciones) _asignaciones[a.Id] = a;
        }
    }

    private AsignacionAlumno? Conocida(string id)
    {
        lock (_candado)
        {
            if (_asignaciones.TryGetValue(id, out var a)) return a;
        }
        var guardada = _local.AlumnoId is { } alumno ? _local.Almacen.LeerLista(alumno) : null;
        if (guardada is null) return null;
        RegistrarLista(guardada);
        lock (_candado) return _asignaciones.GetValueOrDefault(id);
    }

    private List<StudyLessonData> MapearTodo()
    {
        List<AsignacionAlumno> todas;
        lock (_candado) todas = [.. _asignaciones.Values];
        var paquetes = _local.Almacen.ListarPaquetes(Alumno);
        var pendientes = AsignacionesConPendientes();
        return todas.Select(a => Mapear(a, paquetes, pendientes)).ToList();
    }

    /// <summary>Las asignaciones que tienen algo esperando en la cola (para el «↑» de su tarjeta).</summary>
    private HashSet<string> AsignacionesConPendientes()
    {
        var conjunto = new HashSet<string>(StringComparer.Ordinal);
        foreach (var evento in _local.Cola.Pendientes(_local.AlumnoId, int.MaxValue))
        {
            if (evento.Evento.Carga.ValueKind == JsonValueKind.Object
                && evento.Evento.Carga.TryGetProperty("asignacion_id", out var id) && id.ValueKind == JsonValueKind.String && id.GetString() is { } valor)
                conjunto.Add(valor);
        }
        return conjunto;
    }

    /// <summary>Recalcula una sola lección y avisa a la pantalla (sólo se repinta esa tarjeta).</summary>
    internal void Refrescar(string asignacionId)
    {
        var a = Conocida(asignacionId);
        if (a is null || _local.AlumnoId is null) return;
        var dato = Mapear(a, _local.Almacen.ListarPaquetes(Alumno), AsignacionesConPendientes());
        try { LessonChanged?.Invoke(dato); }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyModeService.LessonChanged", ex); }
    }

    private StudyLessonData Mapear(AsignacionAlumno a, IReadOnlyList<PaqueteLocal> paquetes, HashSet<string> conPendientes)
    {
        var alumno = Alumno;
        var local = _local.Almacen.LeerTarea(alumno, a.Id);
        var tarea = a.Tarea;
        var ahora = RelojNodo.AhoraMs;

        // -------- avance: lo que dice el aula y lo que la tableta ya sabe (gana lo mayor: el avance es monótono)
        var completada = tarea?.Completada == true || local?.Completada == true;
        var total = Math.Max(tarea?.BloquesTotal ?? 0, a.Bloques?.Count ?? 0);
        var atendidosAula = tarea?.BloquesAtendidos ?? a.Bloques?.Count(b => b.Atendido) ?? 0;
        var atendidos = Math.Max(atendidosAula, local?.BloquesVistos.Count ?? 0);
        if (total > 0) atendidos = Math.Min(atendidos, total);
        if (completada && total > 0) atendidos = total;
        var progreso = completada ? 1 : total > 0 ? Math.Clamp((double)atendidos / total, 0, 1) : Math.Clamp((tarea?.AvancePct ?? 0) / 100d, 0, 1);
        var vencida = !completada && a.FechaLimite is { } limite && limite < ahora;
        var estado = completada ? StudyLessonState.Completed
            : vencida ? StudyLessonState.Expired
            : atendidos > 0 || tarea?.EnCurso == true ? StudyLessonState.InProgress
            : StudyLessonState.Pending;

        var puedeReanudar = !completada && (atendidos > 0 || tarea?.PuedeReanudar == true);
        var indice = Math.Max(tarea?.UltimoBloque?.Indice ?? 0, atendidos + 1);
        if (total > 0) indice = Math.Clamp(indice, 1, total);
        var etiqueta = puedeReanudar && total > 0 ? $"Continúa desde: Actividad {indice} de {total}" : string.Empty;

        // -------- descarga: la verdad es lo que hay en la tableta; el aula sólo dice si se permite
        var paquete = paquetes.FirstOrDefault(p => p.AsignacionId == a.Id);
        var permitida = a.Descarga?.Permitida ?? true;
        var totalBytes = a.Paquete?.BytesTotal is > 0 ? a.Paquete.BytesTotal : a.Paquete?.BytesEstimados ?? 0;
        long bajados = 0;
        double fraccionDescarga = 0;
        StudyDownloadState descarga;
        if (paquete is not null)
        {
            if (paquete.BytesTotal > 0) totalBytes = paquete.BytesTotal;
            bajados = paquete.BytesDescargados;
            fraccionDescarga = paquete.Fraccion;
            // El aula puede dar por vencido lo descargado aunque la fecha no haya pasado (salió una versión nueva del curso): se le cree.
            var vencidoPorElAula = a.Paquete is { Estado: "vencido" } delAula && delAula.Id == paquete.PaqueteId;
            descarga = paquete.Estado switch
            {
                "disponible" when vencidoPorElAula => StudyDownloadState.Expired,
                "disponible" when paquete.VigenteHasta is { } hasta && hasta < ahora => StudyDownloadState.Expired,
                "disponible" => StudyDownloadState.Available,
                "vencido" => StudyDownloadState.Expired,
                "pausado" => StudyDownloadState.Paused,
                "descargando" => _descargas.IsActive(a.Id) ? StudyDownloadState.Downloading : StudyDownloadState.Paused,
                _ => StudyDownloadState.None,
            };
        }
        else
        {
            descarga = a.Paquete?.Estado == "denegado" || !permitida ? StudyDownloadState.Denied : StudyDownloadState.None;
        }
        var motivoDenegado = descarga == StudyDownloadState.Denied ? MotivoDeDenegacion(a.Descarga?.Motivo ?? a.Paquete?.Motivo) : string.Empty;

        // -------- práctica y evaluación formal (BR-055: cosas distintas)
        var practica = a.Practica;
        var practicas = local?.Practicas ?? [];
        var intentos = Math.Max(practica?.Intentos ?? 0, practicas.Where(p => p.Terminada).Select(p => p.Numero).DefaultIfEmpty(0).Max());
        int? mejor = new[] { practica?.MejorCorrectas, practicas.Where(p => p.Correctas.HasValue).Select(p => p.Correctas).DefaultIfEmpty(null).Max() }.Max();
        var enCurso = practica?.EnCurso == true || practicas.Any(p => !p.Terminada);

        return new StudyLessonData(
            Id: a.Id,
            Subject: a.Asignatura ?? a.Curso?.Titulo ?? string.Empty,
            UnitName: a.Unidad ?? string.Empty,
            Title: a.Titulo,
            Description: !string.IsNullOrWhiteSpace(a.Consigna) ? a.Consigna! : a.Descripcion ?? string.Empty,
            DueDate: StudyFormat.Fecha(a.FechaLimite),
            CompletedOn: StudyFormat.Fecha(tarea?.CompletadaEn ?? (local?.Completada == true ? local.ActualizadoEn : null)),
            Progress: progreso,
            CompletedBlocks: atendidos,
            TotalBlocks: total,
            State: estado,
            CanResume: puedeReanudar,
            ResumeLabel: etiqueta,
            DownloadState: descarga,
            DownloadProgress: fraccionDescarga,
            DownloadedBytes: bajados,
            TotalBytes: totalBytes,
            CanDownload: permitida && !a.Cerrada,
            DownloadDeniedReason: motivoDenegado,
            HasPractice: practica?.Disponible == true,
            PracticeTitle: practica?.Titulo ?? "Comprueba lo aprendido",
            PracticeQuestionCount: practica?.TotalPreguntas ?? 0,
            PracticeAttempts: intentos,
            PracticeBestScore: mejor,
            PracticeInProgress: enCurso,
            HasExam: a.Evaluacion is not null,
            ExamTitle: a.Evaluacion?.Titulo ?? string.Empty,
            ExamAvailability: StudyFormat.DisponibleDesde(null),
            IsPendingSync: conPendientes.Contains(a.Id));
    }

    private static string MotivoDeDenegacion(string? codigo) => codigo switch
    {
        "dispositivo_compartido" => "Este material está disponible durante la clase. Para llevártelo necesitas una tableta asignada a ti.",
        "paquete_no_permitido" => "Tu profesor no dejó este material para llevártelo. Puedes estudiarlo con la tableta conectada al aula.",
        "dispositivo_ajeno" => "Esta tableta es de otra persona.",
        _ => "Este material se estudia con la tableta conectada al aula.",
    };

    private void AlActualizarseUnaDescarga(StudyDownloadUpdate cambio)
    {
        if (cambio.State is StudyDownloadState.Downloading or StudyDownloadState.Requested) return;   // el avance lo pinta la propia descarga
        Refrescar(cambio.LessonId);
    }

    // ============================================================================ sincronización

    public StudySyncState SyncState => _estadoSync;
    public int PendingSyncCount => _local.Cola.CantidadPendiente(_local.AlumnoId);

    private StudySyncState Recalcular() =>
        Volatile.Read(ref _sincronizando) == 1 ? StudySyncState.Syncing
        : _local.Cola.CantidadPendiente(_local.AlumnoId) > 0 ? StudySyncState.PendingSend
        : StudySyncState.Saved;

    private void Poner(StudySyncState estado)
    {
        _estadoSync = estado;
        try { SyncStateChanged?.Invoke(); }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyModeService.SyncStateChanged", ex); }
    }

    private void AlCambiarLaCola() => Poner(Recalcular());

    private void AlLatir()
    {
        try
        {
            if (_local.Cola.CantidadPendiente() > 0) _ = SyncNowAsync();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyModeService.Latido", ex); }
    }

    /// <summary>Cuánto se espera antes de enviar lo que acaba de guardarse (varios cambios seguidos salen en un solo envío). Las pruebas lo alargan.</summary>
    internal static int RetrasoDeSincronizacionMs = 700;

    /// <summary>Sincroniza en un momento (varios cambios seguidos salen en un solo envío).</summary>
    internal void ProgramarSincronizacion()
    {
        if (Interlocked.Exchange(ref _programada, 1) == 1) return;
        _ = Task.Run(async () =>
        {
            try
            {
                await Task.Delay(RetrasoDeSincronizacionMs);
                Interlocked.Exchange(ref _programada, 0);
                await SyncNowAsync();
            }
            catch (Exception ex)
            {
                Interlocked.Exchange(ref _programada, 0);
                RegistroDeFallos.Escribir("student", "StudyModeService.ProgramarSincronizacion", ex);
            }
        });
    }

    public async Task SyncNowAsync(CancellationToken ct = default)
    {
        if (_local.Cola.CantidadPendiente() == 0) { Poner(Recalcular()); return; }
        if (Interlocked.Exchange(ref _sincronizando, 1) == 1) return;
        try
        {
            Poner(StudySyncState.Syncing);
            var resultado = await _local.Sincronizador.VaciarAsync(_local.Dispositivo, ct);
            _conectividad.Informar(!resultado.SinConexion);
        }
        catch (OperationCanceledException) { /* la pantalla se cerró: lo pendiente sigue guardado */ }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyModeService.Sync", ex); }
        finally
        {
            Interlocked.Exchange(ref _sincronizando, 0);
            Poner(Recalcular());
            await TerminarLimpiezaPendienteAsync();
        }
    }

    /// <summary>El aula acusó recibo de un envío: lo que dijo de cada tarea y de cada respuesta pasa a lo local y se repinta lo que cambió.</summary>
    private void AlIntegrarse(string alumnoId, AcuseSync acuse)
    {
        if (alumnoId != _local.AlumnoId) return;
        Aprender(acuse.ServidorEn);
        var tocadas = new HashSet<string>(StringComparer.Ordinal);
        try
        {
            lock (_candado)
            {
                foreach (var t in acuse.Asignaciones ?? [])
                {
                    if (t.Tarea is null || !_asignaciones.TryGetValue(t.Id, out var actual)) continue;
                    _asignaciones[t.Id] = actual with { Tarea = t.Tarea };
                    tocadas.Add(t.Id);
                }
            }
            foreach (var v in acuse.Veredictos ?? [])
            {
                if (v.Veredicto is null) continue;
                var tarea = _local.Almacen.LeerTarea(alumnoId, v.AsignacionId);
                if (tarea is null) continue;
                var practicas = tarea.Practicas.Select(p =>
                    p.ObjetoRef == (v.ObjetoRef ?? p.ObjetoRef) && p.Numero == v.Numero && p.Respuestas.TryGetValue(v.PreguntaRef, out var r)
                        ? p with { Respuestas = new Dictionary<string, RespuestaLocal>(p.Respuestas) { [v.PreguntaRef] = r with { Veredicto = v.Veredicto } }, Sincronizada = true }
                        : p).ToList();
                _local.Almacen.GuardarTarea(alumnoId, tarea with { Practicas = practicas });
                tocadas.Add(v.AsignacionId);
            }
            // Lo completado en el aula queda completado aquí también, aunque el aparato no lo hubiera marcado (otro aparato, el profesor…).
            foreach (var id in tocadas.ToList())
            {
                AsignacionAlumno? a;
                lock (_candado) a = _asignaciones.GetValueOrDefault(id);
                if (a?.Tarea is { Completada: true } && _local.Almacen.LeerTarea(alumnoId, id) is { Completada: false } tarea)
                    _local.Almacen.GuardarTarea(alumnoId, tarea with { Completada = true });
            }
            AsignacionesEstudio? lista;
            lock (_candado) lista = _lista is null ? null : _lista with { Asignaciones = [.. _asignaciones.Values] };
            if (lista is not null) _local.Almacen.GuardarLista(alumnoId, lista);
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyModeService.Integrado", ex); }
        foreach (var id in tocadas) Refrescar(id);
    }

    // ==================================================================== registrar lo que hace el alumno

    internal TareaLocal LeerTarea(string asignacionId) =>
        _local.Almacen.LeerTarea(Alumno, asignacionId) ?? new TareaLocal(asignacionId, [], null, null, false, 0, []);

    internal void GuardarTarea(TareaLocal tarea) => _local.Almacen.GuardarTarea(Alumno, tarea with { ActualizadoEn = RelojNodo.AhoraMs });

    internal void Encolar(string tipo, object carga)
    {
        _local.Cola.Encolar(Alumno, tipo, JsonSerializer.SerializeToElement(carga, Json));
        ProgramarSincronizacion();
    }

    /// <summary>Un bloque visto: primero en la tableta, después a la cola (que sale sola). Idempotente y monótono.</summary>
    internal void RegistrarBloque(string asignacionId, string bloqueRef)
    {
        var tarea = LeerTarea(asignacionId);
        if (tarea.BloquesVistos.Contains(bloqueRef) && tarea.UltimoBloqueRef == bloqueRef) return;
        var vistos = tarea.BloquesVistos.Contains(bloqueRef) ? tarea.BloquesVistos : [.. tarea.BloquesVistos, bloqueRef];
        GuardarTarea(tarea with { BloquesVistos = vistos, UltimoBloqueRef = bloqueRef });
        Encolar(TiposEventoEstudio.BloqueVisto, new { asignacion_id = asignacionId, bloques_vistos = new[] { bloqueRef }, bloque_actual = bloqueRef });
        Refrescar(asignacionId);
    }

    internal void RegistrarCompletada(string asignacionId)
    {
        var tarea = LeerTarea(asignacionId);
        GuardarTarea(tarea with { Completada = true });
        Encolar(TiposEventoEstudio.LeccionCompletada, new { asignacion_id = asignacionId });
        Refrescar(asignacionId);
    }

    /// <summary>La práctica terminada cuenta como bloque atendido (D-4): se marca en la tableta y se avisa por el mismo evento de bloque visto.</summary>
    internal void RegistrarBloquePractica(string asignacionId, string objetoRef)
    {
        var tarea = LeerTarea(asignacionId);
        if (tarea.BloquesVistos.Contains(objetoRef)) return;
        GuardarTarea(tarea with { BloquesVistos = [.. tarea.BloquesVistos, objetoRef] });
        Refrescar(asignacionId);
    }

    /// <summary>Guarda (o actualiza) una práctica en la tableta: el intento, sus respuestas y, si lo hay, el veredicto de cada una.</summary>
    internal void GuardarPractica(string asignacionId, string objetoRef, int numero, int totalPreguntas,
                                  Func<PracticaLocal, PracticaLocal> cambio)
    {
        var tarea = LeerTarea(asignacionId);
        var existente = tarea.Practicas.FirstOrDefault(p => p.ObjetoRef == objetoRef && p.Numero == numero);
        var nueva = cambio(existente ?? new PracticaLocal(objetoRef, numero, "en_curso", new Dictionary<string, RespuestaLocal>(), totalPreguntas, false, null));
        var resto = tarea.Practicas.Where(p => !(p.ObjetoRef == objetoRef && p.Numero == numero));
        GuardarTarea(tarea with { Practicas = [.. resto, nueva] });
    }

    // ===================================================================================== abrir una lección

    public async Task<StudyLessonOpen> OpenLessonAsync(string lessonId, CancellationToken ct = default)
    {
        try
        {
            var identidad = await IdentificarAsync(ct);
            if (!identidad.Ok) return Falla("Todavía no podemos abrir tus lecciones", identidad.Aviso);
            var alumno = Alumno;
            var conocida = Conocida(lessonId);

            // 1) Descargada: se lee del paquete, sin red.
            var paquete = _local.Almacen.ObtenerPaquete(alumno, lessonId);
            if (paquete is { Disponible: true } && !(paquete.VigenteHasta is { } hasta && hasta < RelojNodo.AhoraMs)
                && _local.Almacen.LeerManifiesto(alumno, lessonId) is { } manifiesto)
            {
                var desdePaquete = LeccionDelPaquete(manifiesto);
                if (desdePaquete is not null)
                {
                    lock (_candado) _desdePaquete.Add(lessonId);
                    return new StudyLessonOpen(NuevaSesion(lessonId, conocida ?? manifiesto.Asignacion, desdePaquete.Value.Leccion, desdePaquete.Value.Bloques, null, true), null, null);
                }
            }

            // 2) En línea.
            lock (_candado) _desdePaquete.Remove(lessonId);
            if (identidad.AulaVisible)
            {
                var leccion = await Api.LeccionAsync(_local.Dispositivo, lessonId, alumno, ct);
                _conectividad.Informar(leccion is not null || Api.UltimoError is { Estado: > 0 });
                if (leccion is not null)
                {
                    Aprender(leccion.ServidorEn);
                    var bloques = leccion.Bloques.Count > 0 ? leccion.Bloques : leccion.Asignacion.Bloques ?? BloquesDeLeccion(leccion.Leccion);
                    return new StudyLessonOpen(NuevaSesion(lessonId, leccion.Asignacion, leccion.Leccion, bloques, leccion.Reanudar, false), null, null);
                }
                return FallaDeAula(Api.UltimoError, "la lección");
            }
            return FallaDeAula(null, "la lección");   // sin aula y sin descargar: dice que hay que conectarse y descargarla
        }
        catch (OperationCanceledException) { throw; }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "StudyModeService.OpenLesson", ex);
            return Falla("No pudimos abrir la lección", "Inténtalo de nuevo en un momento. Lo que ya habías hecho está guardado.");
        }
    }

    private static StudyLessonOpen Falla(string titulo, string? mensaje) => new(null, titulo, mensaje);

    private static StudyLessonOpen FallaDeAula(ErrorAula? error, string queSe)
    {
        if (error is null or { Estado: 0 })
            return Falla("Sin conexión con el aula", "Esta lección todavía no está en tu tableta. Descárgala cuando tengas conexión para leerla sin ella.");
        return error.Codigo switch
        {
            "fuente_no_disponible" => Falla($"No pudimos abrir {queSe}", "La biblioteca no responde ahora. Inténtalo en un momento o descarga la lección cuando tengas conexión."),
            "dispositivo_bloqueado" => Falla("Esta tableta está bloqueada", "Habla con tu profesor."),
            "dispositivo_ajeno" => Falla("Esta tableta es de otra persona", null),
            "no_encontrado" => Falla("Ya no encontramos esta lección", "Tu profesor pudo haberla quitado. Vuelve a la lista."),
            _ => Falla($"No pudimos abrir {queSe}", "Inténtalo de nuevo en un momento."),
        };
    }

    private (LeccionAula Leccion, IReadOnlyList<BloqueEstudio> Bloques)? LeccionDelPaquete(ManifiestoPaquete manifiesto)
    {
        try
        {
            var leccion = manifiesto.Leccion.Deserialize<LeccionAula>(Json);
            if (leccion is null) return null;
            var bloques = manifiesto.Asignacion?.Bloques is { Count: > 0 } propios ? propios : BloquesDeLeccion(leccion);
            return (leccion, bloques);
        }
        catch (JsonException ex)
        {
            RegistroDeFallos.Escribir("student", "StudyModeService.LeccionDelPaquete", ex);
            return null;
        }
    }

    /// <summary>
    /// La estructura de bloques de una lección, con las mismas reglas que el aula (D-4): cada lámina, cada página, cada laboratorio y cada actividad;
    /// el examen no es bloque. Sólo se usa cuando el aula no entregó la estructura (un paquete antiguo).
    /// </summary>
    internal static IReadOnlyList<BloqueEstudio> BloquesDeLeccion(LeccionAula leccion)
    {
        var lista = new List<BloqueEstudio>();
        foreach (var objeto in leccion.Objetos ?? [])
        {
            switch (objeto.Componente)
            {
                case "presentacion" or "lectura":
                    var tipo = objeto.Componente == "presentacion" ? "lamina" : "pagina";
                    var n = 0;
                    foreach (var unidad in objeto.Unidades)
                        lista.Add(new BloqueEstudio($"{objeto.ObjetoRef}:{unidad.UnidadRef}", lista.Count + 1, tipo,
                            string.IsNullOrWhiteSpace(unidad.Titulo) ? $"{objeto.Titulo} · {++n}" : unidad.Titulo, true, false, objeto.ObjetoRef));
                    break;
                case "laboratorio_web":
                    lista.Add(new BloqueEstudio(objeto.ObjetoRef, lista.Count + 1, "laboratorio", objeto.Titulo, true, false, objeto.ObjetoRef));
                    break;
                case "actividad":
                    lista.Add(new BloqueEstudio(objeto.ObjetoRef, lista.Count + 1, "practica", objeto.Titulo, true, false, objeto.ObjetoRef));
                    break;
            }
        }
        // Obligatorias: sólo las prácticas (terminarlas una vez basta); sin práctica, todos los bloques (la misma regla del aula).
        return lista.Any(b => b.Tipo == "practica") ? lista.Select(b => b with { Obligatorio = b.Tipo == "practica" }).ToList() : lista;
    }

    private StudyLessonSession NuevaSesion(string lessonId, AsignacionAlumno? asignacion, LeccionAula leccion, IReadOnlyList<BloqueEstudio> bloques,
                                           ReanudarEstudio? reanudar, bool desdePaquete)
    {
        var local = LeerTarea(lessonId);
        var atendidos = new HashSet<string>(local.BloquesVistos, StringComparer.Ordinal);
        foreach (var b in bloques.Where(b => b.Atendido)) atendidos.Add(b.Ref);
        var completada = asignacion?.Tarea?.Completada == true || local.Completada;
        var lista = bloques.Select(b => ABloque(b, leccion, atendidos)).ToList();

        // Se empieza donde la persona se quedó: en el bloque que el aula dice si aún no lo terminó de ver; si no, en el primero sin ver.
        var inicio = 0;
        if (!completada && lista.Count > 0)
        {
            var primeraSinVer = lista.FindIndex(b => !atendidos.Contains(b.Ref));
            var indicada = reanudar?.Indice is { } i ? Math.Clamp(i - 1, 0, lista.Count - 1) : -1;
            inicio = primeraSinVer < 0 ? 0 : indicada >= 0 && !atendidos.Contains(lista[indicada].Ref) ? indicada : primeraSinVer;
        }
        var titulo = asignacion?.Titulo ?? leccion.Titulo;
        var eyebrow = string.Join(" · ", new[] { asignacion?.Asignatura, asignacion?.Unidad }.Where(x => !string.IsNullOrWhiteSpace(x))).ToUpperInvariant();
        return new StudyLessonSession(this, lessonId, titulo, eyebrow, lista, inicio, desdePaquete, asignacion?.Cerrada == true, completada);
    }

    private static StudyBlock ABloque(BloqueEstudio b, LeccionAula leccion, HashSet<string> atendidos)
    {
        var objetoRef = b.ObjetoRef;
        if (string.IsNullOrEmpty(objetoRef))
        {
            var corte = b.Ref.IndexOf(':');
            objetoRef = corte > 0 ? b.Ref[..corte] : b.Ref;
        }
        var objeto = leccion.Objetos?.FirstOrDefault(o => o.ObjetoRef == objetoRef);
        var unidad = b.Tipo is "lamina" or "pagina" && b.Ref.StartsWith(objetoRef + ":", StringComparison.Ordinal) ? b.Ref[(objetoRef.Length + 1)..] : null;
        return new StudyBlock(b.Ref, b.Indice, b.Tipo ?? string.Empty, b.Titulo ?? objeto?.Titulo ?? string.Empty, b.Obligatorio,
            atendidos.Contains(b.Ref) || b.Atendido, objeto, unidad);
    }

    // ============================================================================== abrir una práctica

    public async Task<StudyPracticeOpen> OpenPracticeAsync(string lessonId, bool retry, string? objetoRef = null, CancellationToken ct = default)
    {
        try
        {
            var identidad = await IdentificarAsync(ct);
            if (!identidad.Ok) return FallaPractica("Todavía no podemos abrir la práctica", identidad.Aviso);
            var alumno = Alumno;
            var conocida = Conocida(lessonId);
            objetoRef ??= conocida?.Practica?.ObjetoRef;
            var local = LeerTarea(lessonId);

            // En línea: la práctica en curso (o la siguiente) la lleva el aula y califica en ≤ 2 s.
            if (identidad.AulaVisible)
            {
                var abierta = await Api.PracticaAsync(_local.Dispositivo, lessonId, objetoRef, retry, alumno, ct);
                _conectividad.Informar(abierta is not null || Api.UltimoError is { Estado: > 0 });
                if (abierta is not null)
                {
                    Aprender(abierta.Practica.IniciadaEn);
                    return new StudyPracticeOpen(SesionEnLinea(lessonId, abierta), null, null);
                }
                if (Api.UltimoError is { Estado: > 0 } error)
                    return error.Codigo switch
                    {
                        "asignacion_cerrada" => FallaPractica("Esta asignación ya se cerró", "Puedes leer la lección, pero ya no se registra la práctica."),
                        "fuente_no_disponible" => FallaPractica("No pudimos abrir la práctica", "La biblioteca no responde ahora. Inténtalo en un momento."),
                        _ => FallaPractica("No pudimos abrir la práctica", "Inténtalo de nuevo en un momento."),
                    };
            }

            // Sin aula: sólo si la lección está descargada (ahí está la actividad sin claves). Se guarda y se califica al volver.
            var paquete = _local.Almacen.ObtenerPaquete(alumno, lessonId);
            var manifiesto = paquete is { Disponible: true } ? _local.Almacen.LeerManifiesto(alumno, lessonId) : null;
            var desdePaquete = manifiesto is null ? null : LeccionDelPaquete(manifiesto);
            var actividad = desdePaquete?.Leccion.Objetos?.FirstOrDefault(o => o.EsActividad && (objetoRef is null || o.ObjetoRef == objetoRef))
                            ?? desdePaquete?.Leccion.Objetos?.FirstOrDefault(o => o.EsActividad);
            if (actividad is null)
                return FallaPractica("Para practicar sin conexión, descarga primero la lección",
                    "Cuando estés conectado al aula, toca «Descargar» en la lección y podrás practicar donde quieras.");
            return new StudyPracticeOpen(SesionSinAula(lessonId, actividad, retry, local), null, null);
        }
        catch (OperationCanceledException) { throw; }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "StudyModeService.OpenPractice", ex);
            return FallaPractica("No pudimos abrir la práctica", "Inténtalo de nuevo en un momento. Lo que ya habías respondido está guardado.");
        }
    }

    private static StudyPracticeOpen FallaPractica(string titulo, string? mensaje) => new(null, titulo, mensaje);

    private StudyPracticeSession SesionEnLinea(string lessonId, PracticaAbierta abierta)
    {
        var practica = abierta.Practica;
        var previas = new Dictionary<string, (JsonElement Answer, StudyAnswerVerdict? Verdict)>();
        foreach (var (pregunta, r) in practica.Respondidas ?? [])
            previas[pregunta] = (r.Respuesta.Clone(), r.Veredicto is null ? null : StudyPracticeSession.Traducir(r.Veredicto));
        var total = practica.TotalPreguntas > 0 ? practica.TotalPreguntas : abierta.Objeto.Preguntas?.Count ?? 0;
        // Se refleja en la tableta el intento que el aula ya conoce: el siguiente sin aula continúa la numeración.
        GuardarPractica(lessonId, practica.ObjetoRef ?? abierta.Objeto.ObjetoRef, practica.Numero, total,
            existente => existente with { Estado = practica.Terminada ? "terminada" : "en_curso", TotalPreguntas = total, Sincronizada = true });
        return new StudyPracticeSession(this, lessonId, abierta.Objeto, practica.ObjetoRef ?? abierta.Objeto.ObjetoRef, practica.Numero, practica.Id, previas);
    }

    private StudyPracticeSession SesionSinAula(string lessonId, ObjetoAula actividad, bool retry, TareaLocal local)
    {
        var conocida = Conocida(lessonId);
        var hechas = Math.Max(conocida?.Practica?.Intentos ?? 0, local.Practicas.Select(p => p.Numero).DefaultIfEmpty(0).Max());
        var enCurso = retry ? null : local.Practicas.Where(p => p.ObjetoRef == actividad.ObjetoRef && !p.Terminada).OrderByDescending(p => p.Numero).FirstOrDefault();
        var numero = enCurso?.Numero ?? hechas + 1;
        var previas = new Dictionary<string, (JsonElement Answer, StudyAnswerVerdict? Verdict)>();
        foreach (var (pregunta, r) in enCurso?.Respuestas ?? new Dictionary<string, RespuestaLocal>())
            previas[pregunta] = (r.Respuesta.Clone(), r.Veredicto is null ? null : StudyPracticeSession.Traducir(r.Veredicto));
        return new StudyPracticeSession(this, lessonId, actividad, actividad.ObjetoRef, numero, null, previas);
    }

    // ================================================================== cerrar, espacio, medios, examen

    public async Task<StudyStorageInfo> GetStorageAsync()
    {
        await Task.CompletedTask;
        var alumno = _local.AlumnoId;
        return new StudyStorageInfo(alumno is null ? 0 : _local.Almacen.BytesUsados(alumno), _local.Almacen.EspacioLibreBytes());
    }

    public string ExamExplanation(string lessonId) =>
        "La evaluación de la unidad la aplica tu profesor en clase o cuando él la abra. No es parte de la práctica: aquí puedes prepararte todas las veces que quieras, sin que cuente como nota.";

    private static readonly Regex Medio = new(@"/medios/([^/?#]+)", RegexOptions.Compiled | RegexOptions.CultureInvariant);

    public Uri ResolveMedia(string lessonId, string relativeUrl)
    {
        if (string.IsNullOrWhiteSpace(relativeUrl)) return Api.Absoluta(string.Empty);
        var esDelPaquete = false;
        lock (_candado) esDelPaquete = _desdePaquete.Contains(lessonId);
        if (esDelPaquete && _local.AlumnoId is { } alumno && Medio.Match(relativeUrl) is { Success: true } coincidencia)
        {
            try { return _local.Servidor.UrlDe(alumno, lessonId, Uri.UnescapeDataString(coincidencia.Groups[1].Value)); }
            catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyModeService.ResolveMedia", ex); }
        }
        var uri = Uri.TryCreate(relativeUrl, UriKind.Absolute, out var absoluta) ? absoluta : Api.Absoluta(relativeUrl);
        return ConAparato(uri);
    }

    /// <summary>
    /// Un medio que se pide al aula lo pide el visor (imagen, audio, WebView), que no sabe mandar cabeceras: el aparato y la persona viajan en la propia
    /// URL (<c>?dispositivo=&amp;alumno_id=</c>), como en el resto de la API. Sólo si la URL es del aula: a un tercero no se le cuenta nada.
    /// </summary>
    private Uri ConAparato(Uri uri)
    {
        var aula = Api.BaseUri;
        if (!uri.IsAbsoluteUri || !string.Equals(uri.Host, aula.Host, StringComparison.OrdinalIgnoreCase) || uri.Port != aula.Port) return uri;
        var consulta = uri.Query.TrimStart('?');
        if (consulta.Contains("dispositivo=", StringComparison.Ordinal)) return uri;
        var agregado = "dispositivo=" + Uri.EscapeDataString(_local.Dispositivo)
            + (_local.AlumnoId is { } alumno && !consulta.Contains("alumno_id=", StringComparison.Ordinal) ? "&alumno_id=" + Uri.EscapeDataString(alumno) : string.Empty);
        var constructor = new UriBuilder(uri) { Query = (consulta.Length > 0 ? consulta + "&" : string.Empty) + agregado };
        return constructor.Uri;
    }

    /// <summary>
    /// «Salir» (FUN-089, 008-07, BR-053): cierra la sesión de estudio en el aula y limpia la tableta. Sin trabajo pendiente se destruye la clave y
    /// con ella todo lo cifrado. Con trabajo pendiente sólo se borra lo demás (lista, avance, paquetes) y se conserva la cola cifrada, que sale
    /// sola (BR-137); la limpieza completa se termina cuando la cola se vacíe.
    /// </summary>
    public async Task CloseSessionAsync(CancellationToken ct = default)
    {
        var alumno = _local.AlumnoId;
        try
        {
            _descargas.PauseAll();
            if (alumno is not null)
            {
                // Un último intento de enviar lo pendiente, con un tope corto: la persona siguiente no debe esperar (JRN-022).
                using (var tope = CancellationTokenSource.CreateLinkedTokenSource(ct))
                {
                    tope.CancelAfter(TimeSpan.FromSeconds(2));
                    try { await _local.Sincronizador.VaciarAsync(_local.Dispositivo, tope.Token); }
                    catch (OperationCanceledException) { /* el aula no contestó a tiempo: queda en la cola */ }
                }
                var pendiente = _local.Cola.CantidadPendiente(alumno);
                var completa = LimpiarTableta(alumno, pendiente);
                try
                {
                    using var tope = CancellationTokenSource.CreateLinkedTokenSource(ct);
                    tope.CancelAfter(TimeSpan.FromSeconds(2));
                    await Api.CerrarSesionAsync(_local.Dispositivo, pendiente, completa, alumno, tope.Token);
                }
                catch (OperationCanceledException) { /* sin aula: la sesión se cierra por inactividad y la limpieza ya se hizo */ }
            }
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyModeService.CloseSession", ex); }
        finally
        {
            lock (_candado) { _asignaciones.Clear(); _desdePaquete.Clear(); _lista = null; }
            _sesionAbierta = false;
            _confirmado = false;
            _local.BorrarNombres();   // aunque nadie llegara a elegir su nombre, la lista de compañeros no se queda en la tableta
            _local.OlvidarAlumno();
        }
    }

    /// <summary>Devuelve si la limpieza quedó completa (la clave destruida). Nunca lanza: un fallo deja la limpieza pendiente para el próximo arranque.</summary>
    private bool LimpiarTableta(string alumno, int pendiente)
    {
        try
        {
            _local.Almacen.OlvidarAlumno(alumno);
            _local.BorrarNombres();   // los nombres de los compañeros tampoco se quedan (BR-053)
            if (pendiente > 0)
            {
                Preferences.Default.Set(EstudioLocal.ClaveLimpiezaPendiente, true);
                return false;
            }
            DestruirTodo();
            return true;
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "StudyModeService.LimpiarTableta", ex);
            Preferences.Default.Set(EstudioLocal.ClaveLimpiezaPendiente, true);
            return false;
        }
    }

    /// <summary>Destruye la clave (todo lo cifrado queda ilegible), borra el almacén y la cola vacía. La próxima vez se crea una clave y una cola nuevas.</summary>
    private void DestruirTodo()
    {
        _local.Almacen.Destruir();
        try { if (File.Exists(_local.RutaCola)) File.Delete(_local.RutaCola); }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { /* ilegible sin clave: se aparta al próximo arranque */ }
        Preferences.Default.Remove(EstudioLocal.ClaveLimpiezaPendiente);
    }

    /// <summary>FUN-090: si al salir quedó trabajo por enviar, cuando la cola se vacía (o en el próximo arranque) se termina la limpieza y se avisa al aula.</summary>
    internal async Task TerminarLimpiezaPendienteAsync()
    {
        try
        {
            if (!Preferences.Default.Get(EstudioLocal.ClaveLimpiezaPendiente, false)) return;
            if (_local.Cola.CantidadPendiente() > 0) return;
            DestruirTodo();
            await Api.LimpiezaReintentadaAsync(_local.Dispositivo, "completa");
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "StudyModeService.TerminarLimpieza", ex); }
    }

    public void Dispose()
    {
        _reloj?.Dispose();
        _reloj = null;
        _local.Cola.Cambio -= AlCambiarLaCola;
        _local.Sincronizador.Integrado -= AlIntegrarse;
        _descargas.Updated -= AlActualizarseUnaDescarga;
        _local.Dispose();
    }
}

using Avacom.Lms.Core.Diagnostico;
using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ops;

/// <summary>
/// Lo que el OPS Master necesita saber de la sesión: a qué backend hablar y con
/// qué fachada. El docente no tiene expediente: no registra progreso.
/// </summary>
public static class Sesion
{
    private static readonly HttpClient Http = new HttpClient(new HandlerDeMedicion()) { Timeout = TimeSpan.FromSeconds(15) };
    private static IBibliotecaDeContenido? _biblioteca;
    private static IAulaApi? _aula;
    private static IDispositivosApi? _dispositivos;
    private static IPadronApi? _padron;
    private static Uri? _basePadron;
    private static IEstudioApi? _estudio;
    private static IAccesoApi? _acceso;
    private static IAuditoriaApi? _auditoria;
    private static EvaluacionApi? _evaluacion;
    private static Uri? _baseEvaluacion;
    private static ILogsApi? _logs;
    private static EntregadorDeLogs? _entregador;
    private static Uri? _baseAuditoria;
    private static Uri? _baseLogs;
    private static Uri? _baseAcceso;
    private static Uri? _baseActual;
    private static Uri? _baseAula;
    private static Uri? _baseDispositivos;
    private static Uri? _baseEstudio;
    private static string? _fuenteAula;

    public const string DireccionPorDefecto = "http://127.0.0.1:8000";

    public const string FuenteBiblioteca = "biblioteca";

    /// <summary>
    /// Fuente de cursos de MOD-007: SIEMPRE <c>biblioteca</c>, la API de Contenido v2 de AVACOM Biblioteca a través del backend. El curso de ejemplo ya no se
    /// ofrece: si la biblioteca no está encendida, las pantallas lo dicen y dejan reintentar. Una preferencia antigua <c>ops_fuente_aula</c> se ignora.
    /// </summary>
    public static string FuenteAula => FuenteBiblioteca;

    public static Uri BaseUri
    {
        get
        {
            var texto = Ajustes.ServidorDePrueba ?? Ajustes.Get("ops_server", DireccionPorDefecto);
            try { return ConnectionOptions.Normalize(texto); }
            catch (ArgumentException) { return ConnectionOptions.Normalize(DireccionPorDefecto); }
        }
    }

    /// <summary>Una sola fachada por dirección: conserva la huella entre pantallas.</summary>
    public static IBibliotecaDeContenido Biblioteca
    {
        get
        {
            var actual = BaseUri;
            if (_biblioteca is null || _baseActual != actual)
            {
                _biblioteca = new BibliotecaDeContenido(Http, actual);
                _baseActual = actual;
            }
            return _biblioteca;
        }
    }

    /// <summary>El cliente de <c>/api/aula/</c> (MOD-007), una instancia por dirección y fuente.</summary>
    public static IAulaApi Aula
    {
        get
        {
            var actual = BaseUri;
            var fuente = FuenteAula;
            if (_aula is null || _baseAula != actual || _fuenteAula != fuente)
            {
                _aula = new AulaApi(Http, actual, fuente);
                _baseAula = actual;
                _fuenteAula = fuente;
            }
            return _aula;
        }
    }

    /// <summary>El cliente de <c>/api/dispositivos/</c> (MOD-009): inventario y bloqueo de tabletas, una instancia por dirección.</summary>
    public static IDispositivosApi Dispositivos
    {
        get
        {
            var actual = BaseUri;
            if (_dispositivos is null || _baseDispositivos != actual)
            {
                _dispositivos = new DispositivosApi(Http, actual);
                _baseDispositivos = actual;
            }
            return _dispositivos;
        }
    }

    /// <summary>El cliente de <c>/api/acceso/padron/</c> (MOD-001): grupos y estudiantes del aula, una instancia por dirección.</summary>
    public static IPadronApi Padron
    {
        get
        {
            var actual = BaseUri;
            if (_padron is null || _basePadron != actual)
            {
                _padron = new PadronApi(Http, actual);
                _basePadron = actual;
            }
            return _padron;
        }
    }

    /// <summary>El cliente de <c>/api/modo-estudio/</c> (MOD-008): asignar lecciones a los alumnos y ver quién las completó, una instancia por dirección.</summary>
    public static IEstudioApi Estudio
    {
        get
        {
            var actual = BaseUri;
            if (_estudio is null || _baseEstudio != actual)
            {
                _estudio = new EstudioApi(Http, actual);
                _baseEstudio = actual;
            }
            return _estudio;
        }
    }

    /// <summary>
    /// El cliente de <c>/api/evaluacion/</c> (MOD-010), una instancia por dirección. Es el mismo objeto que implementa <see cref="IExamenDocenteApi"/> (lo que usa
    /// OPS: aplicar un examen, vigilarlo, reactivar, revisar y anular) y <see cref="IExamenAlumnoApi"/> (lo que usa Student); aquí sólo se usa la del profesor.
    /// </summary>
    public static EvaluacionApi Evaluacion
    {
        get
        {
            var actual = BaseUri;
            if (_evaluacion is null || _baseEvaluacion != actual)
            {
                _evaluacion = new EvaluacionApi(Http, actual);
                _baseEvaluacion = actual;
            }
            return _evaluacion;
        }
    }

    /// <summary>El cliente de <c>/api/acceso/</c> (MOD-001): sólo para identificarse cuando el nodo exige sesión (Q-34).</summary>
    public static IAccesoApi Acceso
    {
        get
        {
            var actual = BaseUri;
            if (_acceso is null || _baseAcceso != actual)
            {
                _acceso = new AccesoApi(Http, actual);
                _baseAcceso = actual;
            }
            return _acceso;
        }
    }

    public static string Dispositivo => $"ops-{DeviceInfo.Current.Name}";

    /// <summary>El cliente de <c>/api/auditoria/</c> (MOD-019): la bitácora de sólo lectura, la integridad y las exportaciones. Una instancia por dirección.</summary>
    public static IAuditoriaApi Auditoria
    {
        get
        {
            var actual = BaseUri;
            if (_auditoria is null || _baseAuditoria != actual)
            {
                _auditoria = new AuditoriaApi(Http, actual);
                _baseAuditoria = actual;
            }
            return _auditoria;
        }
    }

    /// <summary>El cliente de <c>/api/logs/</c> (MOD-019): entrega de los avisos de este equipo y lectura de los logs del nodo.</summary>
    public static ILogsApi Logs
    {
        get
        {
            var actual = BaseUri;
            if (_logs is null || _baseLogs != actual)
            {
                _logs = new LogsApi(Http, actual);
                _baseLogs = actual;
            }
            return _logs;
        }
    }

    private static DiagnosticoApi? _diagnostico;
    private static Uri? _baseDiagnostico;

    /// <summary>El cliente del diagnóstico del canal en tiempo real (alumnos conectados, demora de los avisos) para el panel «Rendimiento».</summary>
    public static DiagnosticoApi Diagnostico
    {
        get
        {
            var actual = BaseUri;
            if (_diagnostico is null || _baseDiagnostico != actual)
            {
                _diagnostico = new DiagnosticoApi(Http, actual);
                _baseDiagnostico = actual;
            }
            return _diagnostico;
        }
    }

    private static ColaDeMediosApi? _colaDeMedios;
    private static Uri? _baseColaDeMedios;

    /// <summary>El cliente de la cola de medios del nodo (recursos que trae de AVACOM Contenido y reparte a las tabletas) para la pestaña «Medios» de la bitácora.</summary>
    public static ColaDeMediosApi ColaDeMedios
    {
        get
        {
            var actual = BaseUri;
            if (_colaDeMedios is null || _baseColaDeMedios != actual)
            {
                _colaDeMedios = new ColaDeMediosApi(Http, actual);
                _baseColaDeMedios = actual;
            }
            return _colaDeMedios;
        }
    }

    /// <summary>Arranca (una sola vez) la medición de rendimiento de este equipo contra el nodo actual: CPU, RAM, red, disco y latencias.</summary>
    public static MonitorDeRendimiento IniciarMonitor()
    {
        var monitor = MonitorDeRendimiento.Global;
        monitor.RutaDeDatos = FileSystem.AppDataDirectory;
        monitor.Iniciar(BaseUri, ct => Diagnostico.AlumnosConectadosAsync(ct));
        return monitor;
    }

    /// <summary>Sube al nodo, cada minuto y de mejor esfuerzo, los renglones WARNING+ del registro local de OPS (§2.4 de MOD-019).</summary>
    public static EntregadorDeLogs EntregadorDeLogs => _entregador ??= new EntregadorDeLogs(() => Logs, "ops", () => AppInfo.Current.VersionString);

    /// <summary>
    /// MOD-019 (019-01): el id con el que el nodo conoce a este equipo (<c>m09_dispositivo</c>, tipo MASTER). Se aprende con el latido al
    /// entrar al tablero y se guarda en Preferences; desde entonces viaja en <c>X-Avacom-Dispositivo</c> en cada petición y en el WebSocket.
    /// </summary>
    public static void PrepararAparato()
    {
        AparatoRegistrado.Cargar = () => Ajustes.Get<string?>("ops_dispositivo_id", null);
        AparatoRegistrado.Guardar = id => { if (id is null) Ajustes.Remove("ops_dispositivo_id"); else Ajustes.Set("ops_dispositivo_id", id); };
        RegistroLocal.Configurar("ops", AppInfo.Current.VersionString, () => AparatoRegistrado.Id);
    }

    private static readonly object CandadoRegistro = new();
    private static Task? _registro;
    private static Uri? _registradoEn;

    /// <summary>Verdadero si el nodo de <see cref="BaseUri"/> ya conoce a este equipo como MASTER (el último latido contestó).</summary>
    public static bool EquipoRegistrado => _registradoEn == BaseUri;

    /// <summary>
    /// Se presenta ante el nodo como equipo MASTER (idempotente, por su huella). Mejor esfuerzo: si el nodo no contesta, se reintenta en el siguiente tablero.
    /// Si ya hay una presentación en curso, devuelve ESA (quien necesita esperarla, como el PIN maestro, la espera de verdad).
    /// </summary>
    public static Task RegistrarEquipoAsync()
    {
        lock (CandadoRegistro)
        {
            if (_registro is { IsCompleted: false } enCurso) return enCurso;
            return _registro = PresentarEquipoAsync();
        }
    }

    private static async Task PresentarEquipoAsync()
    {
        var base_ = BaseUri;
        try
        {
            using var limite = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            var equipo = await Dispositivos.LatidoAsync(Dispositivo, DeviceInfo.Current.Name, "windows", AppInfo.Current.VersionString, limite.Token, tipo: "MASTER");
            if (equipo is not null)
            {
                _registradoEn = base_;
                RegistroLocal.Info(Canal.Dispositivo, "equipo.registrado", "Este equipo se presentó ante el nodo", new { dispositivo_id = equipo.Id, bloqueado = equipo.Bloqueado });
            }
        }
        catch (Exception ex) { RegistroLocal.Advertencia(Canal.Comunicacion, "equipo.registro_fallo", "No se pudo presentar el equipo ante el nodo", new { tipo = ex.GetType().Name }); }
    }

    /// <summary>
    /// RN-11: el nodo sólo acepta el PIN maestro (y sólo lista los grupos) si sabe que este equipo NO es una tableta de alumno. Antes de pedir el PIN se espera
    /// a que la presentación termine, como mucho unos 5 s; si el nodo no contesta, se sigue igual y el nodo dirá lo que corresponda.
    /// </summary>
    public static async Task AsegurarEquipoAsync()
    {
        if (EquipoRegistrado) return;
        try { await RegistrarEquipoAsync().WaitAsync(TimeSpan.FromSeconds(6)); }
        catch (TimeoutException) { /* el nodo no contestó a tiempo: la operación lo dirá */ }
    }

    /// <summary>Lo último que el nodo dijo de sí mismo (<c>/api/acceso/configuracion/</c>): si está instalado, si exige sesión y el estado público del PIN maestro.</summary>
    public static ConfiguracionAcceso? Configuracion { get; set; }

    /// <summary>Pregunta al nodo por su configuración (máx. 4 s) y la recuerda. Nulo si no contesta.</summary>
    public static async Task<ConfiguracionAcceso?> ConsultarConfiguracionAsync()
    {
        using var limite = new CancellationTokenSource(TimeSpan.FromSeconds(4));
        try
        {
            var c = await Acceso.ConfiguracionAsync(limite.Token);
            if (c is not null)
            {
                Configuracion = c;
                SesionObligatoria = c.SesionObligatoria;
            }
            return c;
        }
        catch (OperationCanceledException) { return null; }
    }

    /// <summary>Guarda la dirección del nodo que el acceso acaba de usar (en el perfil de pruebas manda la variable de entorno y no se escribe nada).</summary>
    public static void GuardarServidor(string? direccion)
    {
        if (Ajustes.ServidorDePrueba is not null) return;
        Ajustes.Set("ops_server", string.IsNullOrWhiteSpace(direccion) ? DireccionPorDefecto : direccion);
    }

    private static string? _claveProvisional;

    /// <summary>
    /// La contraseña provisional con la que alguien acaba de entrar (la de la hoja de acceso, <c>DebeCambiarCredencial</c>), sólo en memoria y sólo hasta
    /// que «Elige tu contraseña» la tome: así no hay que volver a escribirla. Se borra al leerla.
    /// </summary>
    public static void RecordarClaveProvisional(string? clave) => _claveProvisional = clave;
    public static string? TomarClaveProvisional()
    {
        var c = _claveProvisional;
        _claveProvisional = null;
        return c;
    }

    /// <summary>
    /// La persona que se identificó con MOD-001 (007-10). Vive sólo en memoria: el pase (JWT) no se guarda en disco y
    /// cada arranque de OPS vuelve a pedirlo cuando el nodo exige sesión. Nulo en modo prototipo (nodo sin sesión obligatoria).
    /// </summary>
    public static UsuarioDeSesion? Usuario { get; set; }

    /// <summary>Verdadero si el nodo exige sesión (<c>AVACOM_LMS_EXIGIR_SESION</c>). Se conoce al pulsar «Comprobar» en el acceso.</summary>
    public static bool SesionObligatoria { get; set; }

    /// <summary>Cierra la sesión de usuario de esta app: suelta el pase y la clase guardada, y avisa al nodo si contesta.</summary>
    public static async Task CerrarSesionDeUsuarioAsync()
    {
        try { if (ClienteJson.Token is not null) await Acceso.CerrarSesionAsync(); } catch { /* aunque el nodo no conteste, esta app deja de presentarse */ }
        ClienteJson.Token = null;
        Usuario = null;
        _claveProvisional = null;
    }

    /// <summary>MSG-021: aviso que el tablero muestra una sola vez tras entrar, cuando este acceso cerró la clase que la misma persona tenía abierta en otro equipo.</summary>
    public static string? AvisoAlEntrar { get; set; }

    /// <summary>Mensaje suave que la pantalla de acceso muestra una sola vez al volver a ella (la sesión terminó, se abrió en otro equipo…).</summary>
    public static string? AvisoDeAcceso { get; set; }

    /// <summary>
    /// 007-10: si el nodo negó la operación por permisos (<c>sin_permiso</c>, <c>no_es_el_titular</c>), la frase amable que sustituye
    /// al detalle técnico; nulo en cualquier otro caso. <paramref name="profesor"/> es quien lleva la clase, si se sabe.
    /// </summary>
    public static string? MensajeDePermiso(ErrorAula? error, string? profesor = null) => error?.Codigo is "sin_permiso" or "no_es_el_titular"
        ? $"Esta clase la lleva {(string.IsNullOrWhiteSpace(profesor) ? "otro profesor" : profesor)}. Sólo su profesor o la administración puede hacerlo."
        : null;

    /// <summary>Con sesión (MOD-001) el profesor es quien se identificó; sin ella, la identidad estable del equipo (Q-04).</summary>
    public static string ProfesorRotulo => Usuario?.Alias is { Length: > 0 } alias ? alias : Ajustes.Get("ops_profesor_nombre", "Ms. Carter");
    public static string ProfesorId => Usuario?.Id is { Length: > 0 } uid ? uid
        : Ajustes.Get("ops_profesor_id", string.Empty) is { Length: > 0 } id ? id : $"docente-{Identidad.SlugDe(ProfesorRotulo)}";

    /// <summary>
    /// Dónde se guarda la clase abierta: con sesión de usuario, una por persona (si otra profesora entra en este equipo no ve ni
    /// hereda la clase de la anterior, y la anterior la encuentra al volver); sin sesión, la de siempre.
    /// </summary>
    private static string ClaveClaseAbierta => Usuario?.Id is { Length: > 0 } uid ? $"aula_sesion_ops_{uid}" : "aula_sesion_ops";

    /// <summary>La clase que este equipo dejó abierta, para poder continuarla (BR-051) sin volver a elegir.</summary>
    public static string? ClaseAbiertaId
    {
        get => Ajustes.Get<string?>(ClaveClaseAbierta, null);
        set { if (value is null) Ajustes.Remove(ClaveClaseAbierta); else Ajustes.Set(ClaveClaseAbierta, value); }
    }

    public static readonly string[] Paleta = ["#E5262B", "#F3C701", "#01A4E1", "#019D60", "#A81D81", "#52525B"];

    /// <summary>El mismo libro abierto del hexágono «Asignaturas» del menú principal.</summary>
    public const string IconoLibro =
        "M232,48 H160 A40,40 0 0 0 128,64 A40,40 0 0 0 96,48 H24 A8,8 0 0 0 16,56 V200 A8,8 0 0 0 24,208 H96 A24,24 0 0 1 120,232 A8,8 0 0 0 136,232 A24,24 0 0 1 160,208 H232 A8,8 0 0 0 240,200 V56 A8,8 0 0 0 232,48 Z M96,192 H32 V64 H96 A24,24 0 0 1 120,88 V200 A39.81,39.81 0 0 0 96,192 Z M224,192 H160 A39.81,39.81 0 0 0 136,200 V88 A24,24 0 0 1 160,64 H224 Z";

    /// <summary>El icono del hexágono «Clase de hoy».</summary>
    public const string IconoClase =
        "M128,88 A40,40 0 1 0 168,128 A40,40 0 0 0 128,88 Z M128,152 A24,24 0 1 1 152,128 A24,24 0 0 1 128,152 Z M201.71,159.14 A80,80 0 0 1 187.63,181.34 A8,8 0 0 1 175.71,170.67 A63.95,63.95 0 0 0 175.71,85.34 A8,8 0 1 1 187.63,74.67 A80.08,80.08 0 0 1 201.71,159.14 Z M69,103.09 A64,64 0 0 0 80.26,170.67 A8,8 0 0 1 68.34,181.34 A79.93,79.93 0 0 1 68.34,74.67 A8,8 0 1 1 80.29,85.34 A63.77,63.77 0 0 0 69,103.09 Z M248,128 A119.58,119.58 0 0 1 213.71,212 A8,8 0 1 1 202.29,200.8 A103.9,103.9 0 0 0 202.29,55.24 A8,8 0 1 1 213.71,44 A119.58,119.58 0 0 1 248,128 Z M53.71,200.78 A8,8 0 1 1 42.29,212 A119.87,119.87 0 0 1 42.29,44 A8,8 0 1 1 53.71,55.2 A103.9,103.9 0 0 0 53.71,200.78 Z";
}

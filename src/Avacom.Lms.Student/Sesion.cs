using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Student;

/// <summary>
/// La sesión del estudiante: quién es (identidad lógica del expediente), en qué
/// aula está (backend) y la fachada hacia la biblioteca a través del backend.
/// </summary>
public static class Sesion
{
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(15) };
    private static IBibliotecaDeContenido? _biblioteca;
    private static IAulaApi? _aula;
    private static IAccesoApi? _acceso;
    private static IEstudioApi? _estudio;
    private static IDispositivosApi? _dispositivos;
    private static ILogsApi? _logs;
    private static EntregadorDeLogs? _entregador;
    private static Uri? _baseLogs;
    private static ColaRespuestas? _cola;
    private static SincronizadorRespuestas? _sincronizador;
    private static Uri? _baseActual;
    private static Uri? _baseAula;
    private static Uri? _baseAcceso;
    private static Uri? _baseEstudio;
    private static Uri? _baseDispositivos;
    private static readonly object Candado = new();

    /// <summary>
    /// La persona que se identificó con MOD-001 (007-10, PAN-101). Vive sólo en memoria: el pase (JWT) no se guarda en disco
    /// y cada arranque vuelve a pedirlo cuando el nodo exige sesión. Nulo en modo prototipo (nodo sin sesión obligatoria).
    /// </summary>
    public static UsuarioDeSesion? Usuario { get; set; }

    /// <summary>Verdadero si el nodo exige sesión (<c>AVACOM_LMS_EXIGIR_SESION</c>); se conoce al identificarse.</summary>
    public static bool SesionObligatoria { get; set; }

    public static string Nombre => Usuario?.Alias is { Length: > 0 } alias ? alias : Preferences.Default.Get("student_name", ConnectionOptions.Default.StudentName);
    /// <summary>Con sesión, la identidad es la de MOD-001 (la persona, nunca el aparato); sin ella, el nombre escrito pasado a slug (Q-04).</summary>
    public static string PersonaId => Usuario?.Id is { Length: > 0 } id ? id : Identidad.SlugDe(Nombre);

    public static Uri BaseUri
    {
        get
        {
            var texto = Preferences.Default.Get("student_server", ConnectionOptions.Default.ServerAddress);
            try { return ConnectionOptions.Normalize(texto); }
            catch (ArgumentException) { return ConnectionOptions.Normalize(ConnectionOptions.Default.ServerAddress); }
        }
    }

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

    /// <summary>
    /// El cliente de <c>/api/aula/</c>. La tableta NO elige fuente de cursos: sigue la clase que abrió el
    /// profesor y el backend resuelve de dónde sale el curso (la biblioteca por la API de Contenido v2,
    /// o el manifiesto de ejemplo cuando la referencia es la suya). Las URL de los medios ya llegan con
    /// su fuente desde el backend.
    /// </summary>
    public static IAulaApi Aula
    {
        get
        {
            var actual = BaseUri;
            if (_aula is null || _baseAula != actual)
            {
                _aula = new AulaApi(Http, actual);
                _baseAula = actual;
            }
            return _aula;
        }
    }

    /// <summary>El cliente de <c>/api/acceso/</c> (MOD-001): sólo para identificarse cuando el nodo exige sesión.</summary>
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

    /// <summary>El cliente de <c>/api/modo-estudio/</c> (MOD-008): pendientes, lecciones, prácticas, paquetes y sincronización del trabajo sin red.</summary>
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

    /// <summary>El cliente de <c>/api/dispositivos/</c> (MOD-009): sólo para dar de alta esta tableta la primera vez que se usa el modo de estudio (registro idempotente por su huella).</summary>
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

    /// <summary>
    /// La cola local de respuestas (DEC-006, PAN-132): lo que el alumno responde se guarda AQUÍ, en el dispositivo, antes de
    /// intentar enviarlo, y sólo se borra cuando el nodo acusa recibo. Un archivo por instalación, en el almacenamiento de la app.
    /// </summary>
    public static ColaRespuestas Cola
    {
        get
        {
            lock (Candado)
                return _cola ??= new ColaRespuestas(Path.Combine(FileSystem.AppDataDirectory, "cola-respuestas.json"));
        }
    }

    /// <summary>Vacía la cola local hacia el nodo. Se recrea si cambia la dirección del aula.</summary>
    public static SincronizadorRespuestas Sincronizador
    {
        get
        {
            lock (Candado)
            {
                if (_sincronizador is null || _baseAula != BaseUri) _sincronizador = new SincronizadorRespuestas(Aula, Cola);
                return _sincronizador;
            }
        }
    }

    /// <summary>La huella con la que MOD-009 reconoce esta tableta en el inventario del aula.</summary>
    public static string Dispositivo => $"student-{DeviceInfo.Current.Name}";

    /// <summary>El cliente de <c>/api/logs/</c> (MOD-019): la tableta entrega sus avisos WARNING+ al nodo, de mejor esfuerzo. Nunca lee la bitácora.</summary>
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

    /// <summary>Sube al nodo, cada minuto y cuando hay red del aula, los renglones WARNING+ del registro local (§2.4 de MOD-019). Sin red, espera.</summary>
    public static EntregadorDeLogs EntregadorDeLogs => _entregador ??= new EntregadorDeLogs(() => Logs, "student", () => VersionApp);

    /// <summary>
    /// MOD-019 (019-01): el id con el que el nodo conoce a esta tableta (<c>m09_dispositivo</c>). Lo aprende del latido y de la participación
    /// en una clase, se guarda en Preferences y desde entonces viaja en <c>X-Avacom-Dispositivo</c> en cada petición y en el WebSocket.
    /// Nunca se inventa: una tableta que no entró nunca a una clase no lleva cabecera.
    /// </summary>
    public static void PrepararAparato()
    {
        AparatoRegistrado.Cargar = () => Preferences.Default.Get<string?>("student_dispositivo_id", null);
        AparatoRegistrado.Guardar = id => { if (id is null) Preferences.Default.Remove("student_dispositivo_id"); else Preferences.Default.Set("student_dispositivo_id", id); };
        RegistroLocal.Configurar("student", VersionApp, () => AparatoRegistrado.Id);
    }

    /// <summary>Plataforma y versión declaradas al entrar a clase, para que el inventario sepa qué app corre cada tableta.</summary>
    public static string Plataforma =>
        DeviceInfo.Current.Platform == DevicePlatform.Android ? "android" : DeviceInfo.Current.Platform == DevicePlatform.WinUI ? "windows" : string.Empty;

    public static string VersionApp => AppInfo.Current.VersionString;

    /// <summary>Lo que la tableta declara de sí misma con su latido (009-04): espacio libre y batería. Nunca lanza.</summary>
    public static object? Telemetria() => Avacom.Lms.Student.Telemetria.Leer();

    /// <summary>
    /// Cierra la sesión de usuario de esta app: suelta el pase y avisa al nodo si contesta (PAN-104, MSG-024). El aviso al nodo tiene
    /// un tope corto: en una tableta compartida la persona siguiente no espera a que el nodo conteste (JRN-022, ≤ 3 s).
    /// </summary>
    public static async Task CerrarSesionDeUsuarioAsync()
    {
        try
        {
            using var tope = new CancellationTokenSource(TimeSpan.FromMilliseconds(1200));
            if (ClienteJson.Token is not null) await Acceso.CerrarSesionAsync(tope.Token);
        }
        catch { /* aunque el nodo no conteste, esta app deja de presentarse */ }
        ClienteJson.Token = null;
        Usuario = null;
    }

    /// <summary>
    /// Lo pone el aviso de «sesión terminada» para que la pantalla de acceso conserve el código que la misma persona ya había
    /// escrito (sólo cambia la clave). La pantalla de acceso lo apaga al leerlo: cualquier otra vuelta (Salir) la presenta limpia.
    /// </summary>
    public static bool RecordarCodigo { get; set; }

    /// <summary>La participación en curso: se conserva para readmitirse sin escribir el código (FUN-077, RF-A10).</summary>
    public static string? ClaseSesionId
    {
        get => Preferences.Default.Get<string?>("aula_sesion", null);
        set { if (value is null) Preferences.Default.Remove("aula_sesion"); else Preferences.Default.Set("aula_sesion", value); }
    }

    public static string? ClaseParticipanteId
    {
        get => Preferences.Default.Get<string?>("aula_participante", null);
        set { if (value is null) Preferences.Default.Remove("aula_participante"); else Preferences.Default.Set("aula_participante", value); }
    }

    /// <summary>
    /// El canal en tiempo real de la clase en curso (007-01), si lo hay. Lo abre y lo cierra <c>ClaseSiguiendoPage</c>; el resto de la app
    /// (el ciclo de vida de la ventana: segundo plano, cierre) lo usa para declarar «reconectando» y «salió» (007-04).
    /// </summary>
    public static AulaSocketClient? SocketActual { get; set; }

    /// <summary>La persona a la que pertenece la participación guardada: una tableta compartida nunca readmite a otra persona (BR-053, INV-011).</summary>
    public static string? ClasePersonaId
    {
        get => Preferences.Default.Get<string?>("aula_persona", null);
        set { if (value is null) Preferences.Default.Remove("aula_persona"); else Preferences.Default.Set("aula_persona", value); }
    }

    public static string? ClaseCodigo
    {
        get => Preferences.Default.Get<string?>("aula_codigo", null);
        set { if (value is null) Preferences.Default.Remove("aula_codigo"); else Preferences.Default.Set("aula_codigo", value); }
    }

    public static void OlvidarClase()
    {
        ClaseSesionId = null;
        ClaseParticipanteId = null;
        ClaseCodigo = null;
        ClasePersonaId = null;
    }

    public static readonly string[] Paleta = ["#E5262B", "#F3C701", "#01A4E1", "#019D60", "#A81D81", "#52525B"];

    public const string IconoLibro =
        "M232,48 H160 A40,40 0 0 0 128,64 A40,40 0 0 0 96,48 H24 A8,8 0 0 0 16,56 V200 A8,8 0 0 0 24,208 H96 A24,24 0 0 1 120,232 A8,8 0 0 0 136,232 A24,24 0 0 1 160,208 H232 A8,8 0 0 0 240,200 V56 A8,8 0 0 0 232,48 Z M96,192 H32 V64 H96 A24,24 0 0 1 120,88 V200 A39.81,39.81 0 0 0 96,192 Z M224,192 H160 A39.81,39.81 0 0 0 136,200 V88 A24,24 0 0 1 160,64 H224 Z";
}

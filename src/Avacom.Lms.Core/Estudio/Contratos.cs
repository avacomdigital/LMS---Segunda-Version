using System.Text.Json;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Estudio;

// Contratos del lado del dispositivo de MOD-008 (spec-driven/04-modo-estudio/02-modelo-y-api.md §5). Core no conoce MAUI: lo que
// depende de la plataforma (dónde vive la clave, cómo se sabe si hay red) entra por interfaz y lo implementa cada app.
//
// Reglas que estas piezas hacen cumplir en el aparato:
//  · BR-059 · BR-137 · CAP-048  lo que el alumno hace SIN red se guarda en una cola local cifrada, con secuencia monotónica persistida
//    ANTES de intentar enviarla, y sólo se borra cuando el nodo acusa recibo. Se envía sin exigir sesión abierta.
//  · BR-054 · CAP-047           el paquete descargado se guarda CIFRADO, es reanudable, tiene vigencia y se puede borrar.
//  · BR-053 · JRN-022           destruir la clave deja ilegible todo lo local de un golpe (el «borrado real» es destruir la clave).
//  · BR-062 · INV-017           ninguna hora con valor académico sale del reloj del aparato: todo se normaliza con RelojNodo.

/// <summary>Quien guarda la clave AES-256 de lo local. Student: SecureStorage (Android) o DPAPI (Windows). Las pruebas usan una fija.</summary>
public interface IProveedorDeClave
{
    /// <summary>32 bytes. La primera vez la crea y la conserva; después devuelve siempre la misma hasta que se destruya.</summary>
    byte[] Obtener();

    /// <summary>Destruye la clave: lo cifrado con ella queda ilegible al instante (BR-053). La siguiente <see cref="Obtener"/> crea otra.</summary>
    void Destruir();
}

// ------------------------------------------------------------------------ lo que se guarda

/// <summary>Un paquete guardado en el aparato. <c>Estado</c>: descargando · pausado · disponible · vencido.</summary>
public sealed record PaqueteLocal(
    string AlumnoId, string AsignacionId, string PaqueteId, string Estado, long BytesTotal, long BytesDescargados,
    long? VigenteHasta, string Huella, string? CursoVersion)
{
    public bool Disponible => Estado == "disponible";
    public double Fraccion => BytesTotal <= 0 ? 0 : Math.Clamp((double)BytesDescargados / BytesTotal, 0, 1);
}

/// <summary>Lo que el alumno respondió en una práctica y el veredicto si ya lo tiene. Sin red el veredicto es nulo hasta integrarse.</summary>
public sealed record RespuestaLocal(JsonElement Respuesta, int Secuencia, VeredictoEstudio? Veredicto);

/// <summary>
/// Una práctica hecha (o a medias) en el aparato. <c>Numero</c> es el que el aparato eligió («el siguiente al último»); el nodo lo respeta al
/// integrar. <c>Sincronizada</c>: el nodo ya tiene todas sus respuestas. <c>Correctas</c> sólo existe cuando ya se calificó (con el nodo).
/// </summary>
public sealed record PracticaLocal(
    string ObjetoRef, int Numero, string Estado, IReadOnlyDictionary<string, RespuestaLocal> Respuestas, int TotalPreguntas,
    bool Sincronizada, int? Correctas)
{
    public bool Terminada => Estado == "terminada";
}

/// <summary>El avance local de una tarea: la verdad del alumno mientras el nodo no la conoce. Se mezcla con lo que dijo el nodo por última vez.</summary>
public sealed record TareaLocal(
    string AsignacionId, IReadOnlyCollection<string> BloquesVistos, string? UltimoBloqueRef, int? PosicionSeg, bool Completada,
    long ActualizadoEn, IReadOnlyList<PracticaLocal> Practicas);

/// <summary>
/// El almacén local cifrado de UN aparato. Todo se guarda por alumno (un aparato asignado tiene un solo dueño, pero la ruta lo separa
/// igual) y nada sale en claro al disco. Implementación en <c>AlmacenEstudio</c>; hilo-seguro.
/// </summary>
public interface IAlmacenEstudio
{
    // ---- la lista de pendientes (para verla sin red)
    AsignacionesEstudio? LeerLista(string alumnoId);
    void GuardarLista(string alumnoId, AsignacionesEstudio lista);

    // ---- el avance local de las tareas
    TareaLocal? LeerTarea(string alumnoId, string asignacionId);
    void GuardarTarea(string alumnoId, TareaLocal tarea);

    // ---- paquetes
    IReadOnlyList<PaqueteLocal> ListarPaquetes(string alumnoId);
    PaqueteLocal? ObtenerPaquete(string alumnoId, string asignacionId);
    /// <summary>El manifiesto del paquete ya descargado (sin red); nulo si no está o no está completo.</summary>
    ManifiestoPaquete? LeerManifiesto(string alumnoId, string asignacionId);
    /// <summary>El archivo de un medio, descifrado al vuelo y con acceso aleatorio (para <c>Range</c>). Nulo si no está. Quien llama lo libera.</summary>
    Stream? AbrirArchivo(string alumnoId, string asignacionId, string mediaRef);
    /// <summary>Longitud y tipo del archivo sin abrirlo.</summary>
    (long Longitud, string? Mime)? InfoArchivo(string alumnoId, string asignacionId, string mediaRef);

    /// <summary>Borra el paquete (lo que se descargó, lo parcial y su manifiesto). El avance local de la tarea NO se toca.</summary>
    void EliminarPaquete(string alumnoId, string asignacionId);
    /// <summary>MSG-045: libera lo vencido (según el reloj del nodo). Devuelve cuántos paquetes quitó y cuántos bytes liberó.</summary>
    (int Paquetes, long Bytes) LiberarVencidos(string alumnoId, long ahoraNodoMs);
    long BytesUsados(string alumnoId);
    /// <summary>Espacio libre en el volumen del almacén, o nulo si no se puede saber.</summary>
    long? EspacioLibreBytes();

    /// <summary>Borra TODO lo de un alumno (lista, tareas, paquetes). No toca la cola: ésa se envía sola y sin sesión (BR-137).</summary>
    void OlvidarAlumno(string alumnoId);
    /// <summary>BR-053: destruye la clave y borra todo el almacén. Lo cifrado queda ilegible aunque el barrido físico falle.</summary>
    void Destruir();

    /// <summary>Cambió algo (lista, tarea o paquete) para el alumno indicado.</summary>
    event Action<string>? Cambio;
}

// ---------------------------------------------------------------------------- descarga

public enum ResultadoDescarga { Completa, Pausada, Fallida, Denegada, Vencida, HuellaInvalida, SinEspacio, SinConexion }

/// <summary>El avance de una descarga (0..1) con lo que la pantalla necesita: bytes, velocidad y tiempo restante estimado.</summary>
public sealed record ProgresoDescarga(
    string AsignacionId, long BytesDescargados, long BytesTotal, double Fraccion, string? Archivo, double? BytesPorSegundo,
    TimeSpan? Restante, string Estado);

/// <summary>
/// Baja un paquete completo: pide el paquete al nodo (si aún no lo tiene), baja el manifiesto y sus archivos, uno por uno, REANUDABLES
/// (<c>Range</c>) y cifrados al escribirse, verifica la huella del manifiesto y el SHA-256 de cada archivo, y confirma con el nodo.
/// Pausar es cancelar el token: lo bajado queda, y volver a llamar continúa donde se quedó.
/// </summary>
public interface IDescargadorDePaquetes
{
    /// <summary>Descarga (o continúa) el paquete de una asignación. Nunca lanza por red ni por el nodo: devuelve el resultado.</summary>
    Task<ResultadoDescarga> DescargarAsync(string dispositivo, string alumnoId, string asignacionId, IProgress<ProgresoDescarga>? progreso = null,
                                           CancellationToken ct = default);
}

// ------------------------------------------------------------------------------- cola

/// <summary>Un evento de la cola local, ya con su secuencia. <c>Carga</c> es el JSON de la §4.5 del contrato.</summary>
public sealed record EventoEnCola(string AlumnoId, EventoEstudio Evento);

/// <summary>
/// La cola local cifrada de eventos de estudio (CAP-048). <c>Encolar</c> asigna la siguiente secuencia y la PERSISTE antes de devolver: aunque
/// la app se cierre un instante después, la secuencia no se reutiliza. Se borra sólo con el acuse del nodo.
/// </summary>
public interface IColaEstudio
{
    /// <summary>La identidad de esta instalación como emisor (una nueva si se reinstala): con ella el nodo separa las secuencias.</summary>
    string EmisorId { get; }

    /// <summary>Guarda el evento y devuelve su secuencia. <c>ocurridoEnNodoMs</c> nulo = ahora, normalizado con el reloj del nodo.</summary>
    long Encolar(string alumnoId, string tipo, JsonElement carga, long? ocurridoEnNodoMs = null);

    /// <summary>Lo pendiente en orden de secuencia (una copia). Sin <paramref name="alumnoId"/>, de todos.</summary>
    IReadOnlyList<EventoEnCola> Pendientes(string? alumnoId = null, int maximo = 200);
    int CantidadPendiente(string? alumnoId = null);
    /// <summary>El nodo acusó estas secuencias (integradas, duplicadas o rechazadas de forma definitiva): se borran.</summary>
    void Reconocer(IEnumerable<long> secuencias);
    /// <summary>Para el estado de guardado de tres valores (CMP-002): cambia cuando se encola o se reconoce algo.</summary>
    event Action? Cambio;
}

/// <summary>Cuánto salió, cuánto sigue esperando y cuánto rechazó el nodo de forma definitiva en una pasada del sincronizador.</summary>
public sealed record ResultadoSincronizacionEstudio(
    int Enviados, int Duplicados, int Rechazados, int PendientesDeDecision, int Pendientes, bool SinConexion, AcuseSync? Ultimo)
{
    public static readonly ResultadoSincronizacionEstudio Nada = new(0, 0, 0, 0, 0, false, null);
}

/// <summary>
/// Vacía la cola local hacia el nodo (<c>POST /sync/</c>): manda hasta 200 eventos por envío EN ORDEN de secuencia, y borra de la cola lo que el
/// nodo acusa. Sin conexión no pierde nada. No reentrante. Al integrar avisa a la pantalla con los veredictos y el estado de las tareas.
/// </summary>
public interface ISincronizadorEstudio
{
    /// <summary>El nodo acusó un envío: quien lo escuche actualiza tareas y prácticas locales con lo que el nodo respondió.</summary>
    event Action<string, AcuseSync>? Integrado;

    Task<ResultadoSincronizacionEstudio> VaciarAsync(string dispositivo, CancellationToken ct = default);
}

// ------------------------------------------------------------------------- servidor local

/// <summary>
/// Un servidor HTTP en <c>127.0.0.1</c> que sirve, con soporte de <c>Range</c>, los archivos del paquete ya descargado (descifrados al vuelo)
/// para que los mismos visores del aula (<c>WebView</c>, <c>Image</c>) lean la lección SIN red. Sólo escucha en loopback y cada arranque usa
/// una capacidad aleatoria en la ruta: otra app del equipo no puede leer los medios sin conocerla.
/// </summary>
public interface IServidorLocalDeMedios : IDisposable
{
    /// <summary>Arranca (si no lo está) y devuelve la URL base, terminada en «/».</summary>
    Uri Iniciar();

    /// <summary>La URL local del medio de un paquete descargado.</summary>
    Uri UrlDe(string alumnoId, string asignacionId, string mediaRef);
}

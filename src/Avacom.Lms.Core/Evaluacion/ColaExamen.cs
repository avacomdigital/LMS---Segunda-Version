using System.Security.Cryptography;
using System.Text.Json;
using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Evaluacion;

/// <summary>Lo pendiente de enviar de UN intento: respuestas con su secuencia, incidentes con su <c>ref_cliente</c>, el último informe de bloqueo y, si ya se pidió, la entrega.</summary>
public sealed record PaqueteDeExamen(
    string IntentoId, IReadOnlyList<RespuestaDeExamen> Respuestas, IReadOnlyList<IncidenteDeTableta> Incidentes, InformeDeBloqueo? Bloqueo,
    bool Entregar, bool Confirmar, long EncoladoEn)
{
    public bool Vacio => Respuestas.Count == 0 && Incidentes.Count == 0 && Bloqueo is null && !Entregar;
    public int Cantidad => Respuestas.Count + Incidentes.Count + (Bloqueo is null ? 0 : 1) + (Entregar ? 1 : 0);
    public int MayorSecuencia => Respuestas.Count == 0 ? 0 : Respuestas.Max(r => r.Secuencia);
}

/// <summary>Qué partes de un paquete se descartan porque el nodo las rechazó de forma definitiva.</summary>
[Flags]
public enum PartesDeCola { Nada = 0, Respuestas = 1, Incidentes = 2, Bloqueo = 4, Entrega = 8, Todo = 15 }

/// <summary>
/// La cola local CIFRADA de la tableta durante un examen (BR-009, BR-071, INV-005): cada respuesta, cada incidente y el informe de bloqueo se guardan en el
/// DISPOSITIVO antes de intentar enviarlos y sólo se borran cuando el nodo acusa recibo. Un corte de red, el cierre de la app o un reinicio no pierden nada.
///
/// La secuencia de una respuesta es un contador monotónico POR INTENTO que se persiste ANTES de devolver y no retrocede aunque la cola se vacíe ni aunque la
/// app se reinicie (el nodo deduplica por pregunta + sesión + secuencia, INV-013). El <c>ref_cliente</c> de un incidente nace igual: emisor de esta instalación
/// más un contador persistente, así reenviar la cola no duplica incidentes. Todo va en un solo archivo AES-256-GCM de escritura atómica con la clave de
/// <see cref="IProveedorDeClave"/> (en la tableta no queda nada en claro; destruir la clave deja la cola ilegible, BR-053). Si el archivo no se puede descifrar
/// se aparta como <c>.dañado</c> y se empieza de cero CON UN EMISOR NUEVO, de modo que ninguna referencia vieja choque con las nuevas.
/// </summary>
public sealed class ColaExamen
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private static readonly byte[] Contexto = "avacom-cola-examen"u8.ToArray();

    private readonly string ruta;
    private readonly IProveedorDeClave proveedor;
    private readonly Func<long> reloj;
    private readonly object candado = new();
    private readonly Estado estado;

    public ColaExamen(string ruta, IProveedorDeClave proveedor, Func<long>? reloj = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(ruta);
        this.ruta = Path.GetFullPath(ruta);
        this.proveedor = proveedor ?? throw new ArgumentNullException(nameof(proveedor));
        this.reloj = reloj ?? (() => RelojNodo.ANodo(RelojNodo.LocalMs));
        estado = Cargar(out var persistir);
        if (persistir) Persistir();   // el emisor nuevo queda guardado desde el principio
    }

    /// <summary>Identifica esta INSTALACIÓN: prefijo de todos los <c>ref_cliente</c>.</summary>
    public string EmisorId => estado.EmisorId;

    /// <summary>Cambia cuando se guarda o se reconoce algo (para el estado de guardado de tres valores).</summary>
    public event Action? Cambio;

    private sealed class Estado
    {
        public string EmisorId { get; set; } = "";
        /// <summary>El último número de <c>ref_cliente</c>. Persiste aunque la cola se vacíe: una referencia nunca se reutiliza.</summary>
        public long UltimaReferencia { get; set; }
        /// <summary>La última secuencia usada por intento. Persiste aunque la entrada se vacíe: una secuencia nunca se reutiliza.</summary>
        public Dictionary<string, int> Contadores { get; set; } = [];
        public List<Entrada> Entradas { get; set; } = [];
    }

    private sealed class Entrada
    {
        public string IntentoId { get; set; } = "";
        public List<RespuestaDeExamen> Respuestas { get; set; } = [];
        public List<IncidenteDeTableta> Incidentes { get; set; } = [];
        public InformeDeBloqueo? Bloqueo { get; set; }
        public bool Entregar { get; set; }
        public bool Confirmar { get; set; }
        public long EncoladoEn { get; set; }
        public bool Vacia => Respuestas.Count == 0 && Incidentes.Count == 0 && Bloqueo is null && !Entregar;
    }

    // ------------------------------------------------------------------------------ carga y guardado

    private Estado Cargar(out bool persistir)
    {
        persistir = false;
        byte[]? claro = null;
        if (File.Exists(ruta))
        {
            var sellado = File.ReadAllBytes(ruta);   // un fallo de disco aquí no es corrupción: propaga
            try { claro = DocumentoCifrado.Abrir(sellado, proveedor.Obtener(), Contexto); }
            catch (Exception ex) when (ex is ArchivoCifradoException or CryptographicException) { ArchivosLocales.Apartar(ruta); }
        }
        if (claro is not null)
        {
            try
            {
                var leido = JsonSerializer.Deserialize<Estado>(claro, Json);
                if (leido is not null && !string.IsNullOrWhiteSpace(leido.EmisorId))
                {
                    leido.Entradas.RemoveAll(e => string.IsNullOrEmpty(e.IntentoId));
                    foreach (var e in leido.Entradas)
                        leido.Contadores[e.IntentoId] = Math.Max(leido.Contadores.GetValueOrDefault(e.IntentoId), e.Respuestas.Count == 0 ? 0 : e.Respuestas.Max(r => r.Secuencia));
                    return leido;
                }
            }
            catch (JsonException) { }
            ArchivosLocales.Apartar(ruta);
        }
        persistir = true;
        return new Estado { EmisorId = Guid.NewGuid().ToString("N") };
    }

    private void Persistir() =>
        ArchivosLocales.EscribirAtomico(ruta, DocumentoCifrado.Sellar(JsonSerializer.SerializeToUtf8Bytes(estado, Json), proveedor.Obtener(), Contexto));

    private void Avisar()
    {
        try { Cambio?.Invoke(); }
        catch (Exception) { /* lo guardado ya está guardado: una pantalla que falla no debe hacer creer al llamador que no lo está */ }
    }

    private Entrada Buscar(string intentoId, bool crear)
    {
        var e = estado.Entradas.FirstOrDefault(x => x.IntentoId == intentoId);
        if (e is not null || !crear) return e!;
        e = new Entrada { IntentoId = intentoId, EncoladoEn = reloj() };
        estado.Entradas.Add(e);
        return e;
    }

    // ----------------------------------------------------------------------------------------- uso

    /// <summary>
    /// Guarda una respuesta en el dispositivo y devuelve su secuencia. Volver a responder la misma pregunta sustituye lo pendiente de ella (la secuencia mayor
    /// gana en el nodo); lo ya enviado no se toca. La secuencia queda persistida ANTES de devolver.
    /// </summary>
    public int Guardar(string intentoId, string preguntaRef, JsonElement respuesta)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(intentoId);
        ArgumentException.ThrowIfNullOrWhiteSpace(preguntaRef);
        if (respuesta.ValueKind != JsonValueKind.Object) throw new ArgumentException("Una respuesta es un objeto JSON.", nameof(respuesta));
        int secuencia;
        lock (candado)
        {
            secuencia = estado.Contadores.GetValueOrDefault(intentoId) + 1;
            estado.Contadores[intentoId] = secuencia;   // gastada aunque el guardado falle: nunca se reutiliza
            var entrada = Buscar(intentoId, crear: true);
            var anteriores = entrada.Respuestas.Where(r => r.PreguntaRef == preguntaRef).ToList();
            entrada.Respuestas.RemoveAll(r => r.PreguntaRef == preguntaRef);
            var local = RelojNodo.LocalMs;
            var nueva = new RespuestaDeExamen(preguntaRef, secuencia, respuesta.Clone(), RelojNodo.ANodo(local), local);
            entrada.Respuestas.Add(nueva);
            try { Persistir(); }
            catch
            {
                // No se pudo guardar: esa respuesta no existe (el llamador se entera). Lo que ya había pendiente de la pregunta vuelve a estar.
                entrada.Respuestas.Remove(nueva);
                entrada.Respuestas.AddRange(anteriores);
                if (entrada.Vacia) estado.Entradas.Remove(entrada);
                throw;
            }
        }
        Avisar();
        return secuencia;
    }

    /// <summary>Guarda un incidente en el dispositivo y devuelve su <c>ref_cliente</c> (idempotencia, INV-005). La hora va normalizada al reloj del nodo y la cruda como dato adicional.</summary>
    public string RegistrarIncidente(string intentoId, string tipo, Dictionary<string, object?>? detalle = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(intentoId);
        if (!TiposDeIncidente.DeLaTableta.Contains(tipo)) throw new ArgumentException($"La tableta no informa incidentes de tipo «{tipo}».", nameof(tipo));
        string referencia;
        lock (candado)
        {
            referencia = $"{estado.EmisorId[..Math.Min(8, estado.EmisorId.Length)]}-{++estado.UltimaReferencia}";   // gastada aunque el guardado falle
            var entrada = Buscar(intentoId, crear: true);
            var local = RelojNodo.LocalMs;
            var incidente = new IncidenteDeTableta(tipo, referencia, RelojNodo.ANodo(local), local, detalle is { Count: > 0 } ? detalle : null);
            entrada.Incidentes.Add(incidente);
            try { Persistir(); }
            catch
            {
                entrada.Incidentes.Remove(incidente);
                if (entrada.Vacia) estado.Entradas.Remove(entrada);
                throw;
            }
        }
        Avisar();
        return referencia;
    }

    /// <summary>Deja pendiente el informe de bloqueo (sólo el último importa: el nodo guarda el más reciente).</summary>
    public void PonerBloqueo(string intentoId, InformeDeBloqueo informe)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(intentoId);
        ArgumentNullException.ThrowIfNull(informe);
        lock (candado)
        {
            var entrada = Buscar(intentoId, crear: true);
            var anterior = entrada.Bloqueo;
            entrada.Bloqueo = informe;
            try { Persistir(); }
            catch
            {
                entrada.Bloqueo = anterior;
                if (entrada.Vacia) estado.Entradas.Remove(entrada);
                throw;
            }
        }
        Avisar();
    }

    /// <summary>Marca el intento para entregarlo en cuanto lo pendiente llegue al nodo (la entrega sin red no se pierde: sale sola al volver la conexión).</summary>
    public void MarcarEntrega(string intentoId, bool confirmar)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(intentoId);
        lock (candado)
        {
            var entrada = Buscar(intentoId, crear: true);
            entrada.Entregar = true;
            entrada.Confirmar |= confirmar;
            Persistir();
        }
        Avisar();
    }

    /// <summary>La secuencia más alta que ya se usó en un intento (0 si ninguna).</summary>
    public int UltimaSecuencia(string intentoId)
    {
        lock (candado) return estado.Contadores.GetValueOrDefault(intentoId);
    }

    /// <summary>
    /// La secuencia nunca retrocede: si esta instalación perdió su contador (datos borrados, otra tableta que continúa el intento) arranca desde la mayor que el
    /// nodo ya aceptó, de modo que la primera respuesta nueva no llegue como «superada».
    /// </summary>
    public void AsegurarSecuenciaMinima(string intentoId, int minima)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(intentoId);
        if (minima <= 0) return;
        lock (candado)
        {
            if (estado.Contadores.GetValueOrDefault(intentoId) >= minima) return;
            estado.Contadores[intentoId] = minima;
            try { Persistir(); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }   // en memoria vale; se persistirá con el siguiente guardado
        }
    }

    /// <summary>La respuesta que el alumno dio y aún no llegó al nodo, para pintarla al reabrir el examen sin red.</summary>
    public RespuestaDeExamen? RespuestaPendiente(string intentoId, string preguntaRef)
    {
        lock (candado)
            return Buscar(intentoId, crear: false)?.Respuestas.FirstOrDefault(r => r.PreguntaRef == preguntaRef);
    }

    /// <summary>Lo que falta por enviar (copias: se puede recorrer mientras se sigue guardando).</summary>
    public IReadOnlyList<PaqueteDeExamen> Pendientes(string? intentoId = null)
    {
        lock (candado)
        {
            return estado.Entradas.Where(e => (intentoId is null || e.IntentoId == intentoId) && !e.Vacia)
                .Select(e => new PaqueteDeExamen(e.IntentoId, [.. e.Respuestas], [.. e.Incidentes], e.Bloqueo, e.Entregar, e.Confirmar, e.EncoladoEn))
                .ToList();
        }
    }

    /// <summary>Cuántas cosas (respuestas, incidentes, informe, entrega) esperan en el dispositivo.</summary>
    public int CantidadPendiente(string? intentoId = null)
    {
        lock (candado)
            return estado.Entradas.Where(e => intentoId is null || e.IntentoId == intentoId)
                .Sum(e => e.Respuestas.Count + e.Incidentes.Count + (e.Bloqueo is null ? 0 : 1) + (e.Entregar ? 1 : 0));
    }

    /// <summary>
    /// El nodo acusó recibo de lo que contenía este paquete: se borra lo enviado. Lo que se guardó mientras el envío viajaba (secuencias mayores, otros
    /// incidentes, otro informe) se conserva. Si no se puede grabar el borrado no es grave: en el disco queda de más y el próximo envío lo repite, y el nodo lo
    /// reconoce como duplicado. Perder un borrado es inocuo; perder un dato no.
    /// </summary>
    public void Reconocer(PaqueteDeExamen enviado, PartesDeCola partes = PartesDeCola.Todo)
    {
        ArgumentNullException.ThrowIfNull(enviado);
        lock (candado)
        {
            var entrada = Buscar(enviado.IntentoId, crear: false);
            if (entrada is null) return;
            if (partes.HasFlag(PartesDeCola.Respuestas))
            {
                var enviadas = enviado.Respuestas.ToDictionary(r => r.PreguntaRef, r => r.Secuencia);
                entrada.Respuestas.RemoveAll(r => enviadas.TryGetValue(r.PreguntaRef, out var s) && r.Secuencia <= s);
            }
            if (partes.HasFlag(PartesDeCola.Incidentes))
            {
                var referencias = enviado.Incidentes.Select(i => i.RefCliente).ToHashSet();
                entrada.Incidentes.RemoveAll(i => referencias.Contains(i.RefCliente));
            }
            if (partes.HasFlag(PartesDeCola.Bloqueo) && enviado.Bloqueo is not null && entrada.Bloqueo == enviado.Bloqueo) entrada.Bloqueo = null;
            if (partes.HasFlag(PartesDeCola.Entrega) && enviado.Entregar) { entrada.Entregar = false; entrada.Confirmar = false; }
            if (entrada.Vacia) estado.Entradas.Remove(entrada);
            try { Persistir(); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
        }
        Avisar();
    }

    /// <summary>Descarta partes que el nodo rechazó de forma definitiva (intento ya entregado, anulado, ajeno…) para no reintentarlas eternamente.</summary>
    public void Descartar(string intentoId, PartesDeCola partes)
    {
        lock (candado)
        {
            var entrada = Buscar(intentoId, crear: false);
            if (entrada is null) return;
            if (partes.HasFlag(PartesDeCola.Respuestas)) entrada.Respuestas.Clear();
            if (partes.HasFlag(PartesDeCola.Incidentes)) entrada.Incidentes.Clear();
            if (partes.HasFlag(PartesDeCola.Bloqueo)) entrada.Bloqueo = null;
            if (partes.HasFlag(PartesDeCola.Entrega)) { entrada.Entregar = false; entrada.Confirmar = false; }
            if (entrada.Vacia) estado.Entradas.Remove(entrada);
            try { Persistir(); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
        }
        Avisar();
    }

    /// <summary>Olvida el contador de un intento ya entregado y sin nada pendiente (el nodo no acepta más respuestas de él).</summary>
    public void Olvidar(string intentoId)
    {
        lock (candado)
        {
            var entrada = Buscar(intentoId, crear: false);
            if (entrada is not null && !entrada.Vacia) return;
            if (entrada is not null) estado.Entradas.Remove(entrada);
            estado.Contadores.Remove(intentoId);
            try { Persistir(); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
        }
    }
}

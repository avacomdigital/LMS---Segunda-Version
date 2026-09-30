using System.Security.Cryptography;
using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Estudio;

/// <summary>
/// La cola local cifrada de lo que el alumno hace SIN el nodo a la vista (CAP-048, BR-059, BR-137): avance de la lección, respuestas de la
/// práctica, práctica terminada, lección completada. Es un solo archivo, AES-256-GCM entero y de escritura atómica, con la clave de
/// <see cref="IProveedorDeClave"/>: en la tableta no queda nada en claro.
///
/// <see cref="EmisorId"/> identifica esta INSTALACIÓN (un GUID creado la primera vez y guardado en el propio archivo): con él el nodo separa las
/// secuencias de cada aparato (<c>UNIQUE(emisor_id, secuencia)</c>) y el reenvío no duplica nada. La secuencia es monotónica por instalación: cada
/// <see cref="Encolar"/> la persiste ANTES de devolver, y no retrocede aunque la cola se vacíe ni aunque la app se reinicie.
///
/// Si el archivo no se puede descifrar (la clave se destruyó, está corrupto) se aparta como <c>.dañado</c> y se empieza de cero CON UN EMISOR
/// NUEVO: así ninguna secuencia vieja puede chocar con las nuevas aunque el contador se haya perdido. Si sólo se pudo leer una parte (algún
/// evento malformado) se conserva el emisor y el contador, y se descartan sólo esos eventos. Un fallo de lectura del disco (archivo en uso) no
/// se trata como corrupción: lanza, porque empezar de cero sobre un archivo bueno perdería la cola.
/// </summary>
public sealed class ColaEstudio : IColaEstudio
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private static readonly byte[] Contexto = "avacom-cola-estudio"u8.ToArray();

    private readonly string ruta;
    private readonly IProveedorDeClave proveedor;
    private readonly object candado = new();
    private readonly Estado estado;

    public ColaEstudio(string ruta, IProveedorDeClave proveedor)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(ruta);
        this.ruta = Path.GetFullPath(ruta);
        this.proveedor = proveedor ?? throw new ArgumentNullException(nameof(proveedor));
        estado = Cargar(out var persistir);
        if (persistir) Persistir();   // el emisor nuevo queda guardado desde el principio
    }

    public string EmisorId => estado.EmisorId;

    /// <summary>Cambia cuando se encola o se reconoce algo (para el estado de guardado de tres valores, CMP-002).</summary>
    public event Action? Cambio;

    private sealed class Estado
    {
        public string EmisorId { get; set; } = "";
        /// <summary>La última secuencia entregada. Persiste aunque la cola se vacíe: una secuencia nunca se reutiliza.</summary>
        public long UltimaSecuencia { get; set; }
        public List<Entrada> Eventos { get; set; } = [];
    }

    private sealed class Entrada
    {
        public string AlumnoId { get; set; } = "";
        public long Secuencia { get; set; }
        public string Tipo { get; set; } = "";
        /// <summary>Cuándo ocurrió, normalizado al reloj del nodo (BR-062).</summary>
        public long OcurridoEn { get; set; }
        /// <summary>Cuándo ocurrió según el reloj crudo del aparato: dato adicional, el nodo decide con el suyo.</summary>
        public long? OcurridoEnTableta { get; set; }
        public JsonElement Carga { get; set; }
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
        var leido = claro is null ? null : Interpretar(claro, out persistir);
        if (claro is not null && leido is null) ArchivosLocales.Apartar(ruta);
        if (leido is not null) return leido;
        persistir = true;
        return new Estado { EmisorId = Guid.NewGuid().ToString("N") };
    }

    /// <summary>Lee la cola tolerando lo que se pueda: el emisor y el contador si están, y cada evento por separado (uno malformado no tumba a los demás).</summary>
    private static Estado? Interpretar(byte[] claro, out bool reescribir)
    {
        reescribir = false;
        try
        {
            using var documento = JsonDocument.Parse(claro);
            var raiz = documento.RootElement;
            if (raiz.ValueKind != JsonValueKind.Object) return null;
            var leido = new Estado();
            if (raiz.TryGetProperty("emisorId", out var emisor) && emisor.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(emisor.GetString()))
                leido.EmisorId = emisor.GetString()!;
            if (raiz.TryGetProperty("ultimaSecuencia", out var ultima) && ultima.ValueKind == JsonValueKind.Number && ultima.TryGetInt64(out var numero))
                leido.UltimaSecuencia = Math.Max(0, numero);
            if (raiz.TryGetProperty("eventos", out var eventos) && eventos.ValueKind == JsonValueKind.Array)
            {
                foreach (var item in eventos.EnumerateArray())
                {
                    try
                    {
                        var entrada = item.Deserialize<Entrada>(Json);
                        if (entrada is not null && entrada.Secuencia > 0 && !string.IsNullOrEmpty(entrada.AlumnoId) && !string.IsNullOrEmpty(entrada.Tipo)
                            && entrada.Carga.ValueKind != JsonValueKind.Undefined)
                            leido.Eventos.Add(entrada);
                        else reescribir = true;
                    }
                    catch (JsonException) { reescribir = true; }
                }
            }
            if (string.IsNullOrEmpty(leido.EmisorId))
            {
                leido.EmisorId = Guid.NewGuid().ToString("N");   // sin emisor legible las secuencias de antes no se pueden respetar: emisor nuevo
                reescribir = true;
            }
            if (leido.Eventos.Count > 0) leido.UltimaSecuencia = Math.Max(leido.UltimaSecuencia, leido.Eventos.Max(e => e.Secuencia));
            leido.Eventos.Sort((a, b) => a.Secuencia.CompareTo(b.Secuencia));
            return leido;
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private void Persistir() =>
        ArchivosLocales.EscribirAtomico(ruta, DocumentoCifrado.Sellar(JsonSerializer.SerializeToUtf8Bytes(estado, Json), proveedor.Obtener(), Contexto));

    private void Avisar()
    {
        try { Cambio?.Invoke(); }
        catch (Exception) { /* la secuencia ya está guardada: una pantalla que falla no debe hacer creer al llamador que no lo está */ }
    }

    // ----------------------------------------------------------------------------------------- uso

    public long Encolar(string alumnoId, string tipo, JsonElement carga, long? ocurridoEnNodoMs = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(alumnoId);
        ArgumentException.ThrowIfNullOrWhiteSpace(tipo);
        if (carga.ValueKind == JsonValueKind.Undefined) throw new ArgumentException("La carga del evento no es un JSON.", nameof(carga));
        long secuencia;
        lock (candado)
        {
            var local = RelojNodo.LocalMs;
            // Sin hora dada: ahora, normalizada al reloj del nodo, y la cruda del aparato como dato adicional (BR-062). Con hora dada (ya del
            // nodo) la cruda se deduce con el desfase aprendido, para que las dos sigan diciendo lo mismo.
            var ocurrido = ocurridoEnNodoMs ?? RelojNodo.ANodo(local);
            var tableta = ocurridoEnNodoMs is { } dada ? dada - RelojNodo.DesfaseMs : local;
            secuencia = ++estado.UltimaSecuencia;
            var entrada = new Entrada { AlumnoId = alumnoId, Secuencia = secuencia, Tipo = tipo, OcurridoEn = ocurrido, OcurridoEnTableta = tableta, Carga = carga.Clone() };
            estado.Eventos.Add(entrada);
            try { Persistir(); }
            catch
            {
                // No se pudo guardar: el evento no existe (el llamador se entera). La secuencia queda gastada: nunca se reutiliza.
                estado.Eventos.Remove(entrada);
                throw;
            }
        }
        Avisar();
        return secuencia;
    }

    public IReadOnlyList<EventoEnCola> Pendientes(string? alumnoId = null, int maximo = 200)
    {
        if (maximo <= 0) return [];
        lock (candado)
        {
            return estado.Eventos
                .Where(e => alumnoId is null || e.AlumnoId == alumnoId)
                .OrderBy(e => e.Secuencia)
                .Take(maximo)
                .Select(e => new EventoEnCola(e.AlumnoId, new EventoEstudio(e.Secuencia, e.Tipo, e.OcurridoEn, e.OcurridoEnTableta, e.Carga)))
                .ToList();
        }
    }

    public int CantidadPendiente(string? alumnoId = null)
    {
        lock (candado) return estado.Eventos.Count(e => alumnoId is null || e.AlumnoId == alumnoId);
    }

    public void Reconocer(IEnumerable<long> secuencias)
    {
        ArgumentNullException.ThrowIfNull(secuencias);
        var acusadas = secuencias.ToHashSet();
        int quitadas;
        lock (candado)
        {
            quitadas = estado.Eventos.RemoveAll(e => acusadas.Contains(e.Secuencia));
            if (quitadas == 0) return;
            try { Persistir(); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                // El nodo ya los tiene: si no se puede grabar el borrado, en el disco quedan de más y el próximo envío los repite; el nodo
                // los reconoce como duplicados (idempotencia por emisor y secuencia). Perder un borrado es inocuo; perder un evento no.
            }
        }
        Avisar();
    }
}

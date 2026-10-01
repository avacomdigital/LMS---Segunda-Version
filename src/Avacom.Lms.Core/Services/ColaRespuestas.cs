using System.Text.Json;
using System.Text.Json.Serialization;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>Lo pendiente de enviar de un intento: respuestas con su secuencia y, si ya se pidió, su entrega.</summary>
public sealed record PaqueteCola(
    string SesionId, string DistribucionId, string ParticipanteId, int IntentoNumero,
    IReadOnlyList<RespuestaEnviada> Respuestas, bool Entregar, long EncoladoEn)
{
    public int MayorSecuencia => Respuestas.Count == 0 ? 0 : Respuestas.Max(r => r.Secuencia);
    public bool Vacio => Respuestas.Count == 0 && !Entregar;
}

/// <summary>
/// La cola local de la tableta (DEC-006, BR-059, PAN-132, 007-08): cada respuesta se guarda en el DISPOSITIVO antes de intentar enviarla,
/// con una secuencia monotónica por intento que se persiste y nunca se reutiliza, y sólo se borra cuando el nodo acusa recibo. Así un
/// corte de red, el cierre de la app o el cierre de la clase no pierden nada: lo capturado sale solo cuando la tableta vuelve al aula.
///
/// Es un archivo JSON escrito de forma atómica (temporal + reemplazo). Si el archivo se corrompe se aparta como <c>.dañado</c> y se
/// empieza de cero: es preferible perder un borrador que quedar sin poder guardar.
/// </summary>
public sealed class ColaRespuestas
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { WriteIndented = false };

    private readonly string ruta;
    private readonly object candado = new();
    private Estado estado;

    public ColaRespuestas(string ruta)
    {
        this.ruta = ruta;
        estado = Cargar(ruta);
    }

    /// <summary>Cambia cada vez que se guarda, se entrega o se reconoce algo (para repintar «guardando» / «guardado en el dispositivo»).</summary>
    public event Action? Cambio;

    private sealed class Estado
    {
        public List<Entrada> Entradas { get; set; } = [];
        /// <summary>Última secuencia usada por intento. Persiste aunque la entrada se vacíe: una secuencia nunca se reutiliza.</summary>
        public Dictionary<string, int> Contadores { get; set; } = [];
    }

    private sealed class Entrada
    {
        public string SesionId { get; set; } = "";
        public string DistribucionId { get; set; } = "";
        public string ParticipanteId { get; set; } = "";
        public int IntentoNumero { get; set; }
        public bool Entregar { get; set; }
        public long EncoladoEn { get; set; }
        public List<RespuestaEnviada> Respuestas { get; set; } = [];
    }

    private static string Clave(string sesion, string distribucion, string participante, int intento) => $"{sesion}|{distribucion}|{participante}|{intento}";

    private static Estado Cargar(string ruta)
    {
        try
        {
            if (File.Exists(ruta))
                return JsonSerializer.Deserialize<Estado>(File.ReadAllText(ruta), Json) ?? new Estado();
        }
        catch (Exception ex) when (ex is JsonException or IOException or UnauthorizedAccessException)
        {
            try { File.Move(ruta, ruta + ".dañado", overwrite: true); } catch { }
        }
        return new Estado();
    }

    private void Persistir()
    {
        try
        {
            var carpeta = Path.GetDirectoryName(ruta);
            if (!string.IsNullOrEmpty(carpeta)) Directory.CreateDirectory(carpeta);
            var temporal = ruta + ".tmp";
            File.WriteAllText(temporal, JsonSerializer.Serialize(estado, Json));
            File.Move(temporal, ruta, overwrite: true);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // MOD-019 §2.4 (canal escritura): disco lleno, permisos, archivo bloqueado. Se registra con el código, nunca con el contenido.
            RegistroLocal.Error(Canal.Escritura, "cola.persistir_fallo", "No se pudo escribir la cola de respuestas",
                                new { hresult = ex.HResult, tipo = ex.GetType().Name, entradas = estado.Entradas.Count }, ex);
            throw;
        }
    }

    private Entrada Buscar(string sesion, string distribucion, string participante, int intento, bool crear)
    {
        var e = estado.Entradas.FirstOrDefault(x => x.SesionId == sesion && x.DistribucionId == distribucion && x.ParticipanteId == participante && x.IntentoNumero == intento);
        if (e is not null || !crear) return e!;
        e = new Entrada { SesionId = sesion, DistribucionId = distribucion, ParticipanteId = participante, IntentoNumero = intento, EncoladoEn = RelojNodo.LocalMs };
        estado.Entradas.Add(e);
        return e;
    }

    /// <summary>
    /// Guarda una respuesta en el dispositivo y devuelve su secuencia. Volver a responder la misma pregunta sustituye lo pendiente de ella
    /// (la secuencia mayor gana en el nodo); lo ya enviado no se toca. Cuando vuelve la conexión sale con <c>capturada_en</c> normalizada.
    /// </summary>
    public int Guardar(string sesionId, string distribucionId, string participanteId, int intentoNumero, string preguntaRef, JsonElement respuesta)
    {
        lock (candado)
        {
            var clave = Clave(sesionId, distribucionId, participanteId, intentoNumero);
            estado.Contadores.TryGetValue(clave, out var ultima);
            var secuencia = ultima + 1;
            estado.Contadores[clave] = secuencia;
            var entrada = Buscar(sesionId, distribucionId, participanteId, intentoNumero, crear: true);
            entrada.Respuestas.RemoveAll(r => r.PreguntaRef == preguntaRef);
            var local = RelojNodo.LocalMs;
            entrada.Respuestas.Add(new RespuestaEnviada(preguntaRef, secuencia, respuesta.Clone(), RelojNodo.ANodo(local), local));
            Persistir();
        }
        Cambio?.Invoke();
        return Math.Max(1, estado.Contadores[Clave(sesionId, distribucionId, participanteId, intentoNumero)]);
    }

    /// <summary>Marca el intento para entregarlo en cuanto lo pendiente llegue al nodo.</summary>
    public void Entregar(string sesionId, string distribucionId, string participanteId, int intentoNumero)
    {
        lock (candado)
        {
            Buscar(sesionId, distribucionId, participanteId, intentoNumero, crear: true).Entregar = true;
            Persistir();
        }
        Cambio?.Invoke();
    }

    /// <summary>La secuencia más alta que ya se usó en un intento (0 si ninguna).</summary>
    public int UltimaSecuencia(string sesionId, string distribucionId, string participanteId, int intentoNumero)
    {
        lock (candado) return estado.Contadores.TryGetValue(Clave(sesionId, distribucionId, participanteId, intentoNumero), out var s) ? s : 0;
    }

    /// <summary>Lo que falta por enviar (una copia: se puede recorrer mientras se sigue guardando).</summary>
    public IReadOnlyList<PaqueteCola> Pendientes(string? sesionId = null)
    {
        lock (candado)
        {
            return estado.Entradas.Where(e => (sesionId is null || e.SesionId == sesionId) && (e.Respuestas.Count > 0 || e.Entregar))
                .Select(e => new PaqueteCola(e.SesionId, e.DistribucionId, e.ParticipanteId, e.IntentoNumero, [.. e.Respuestas], e.Entregar, e.EncoladoEn))
                .ToList();
        }
    }

    /// <summary>Cuántas respuestas (y entregas) esperan en el dispositivo.</summary>
    public int CantidadPendiente(string? sesionId = null)
    {
        lock (candado)
            return estado.Entradas.Where(e => sesionId is null || e.SesionId == sesionId).Sum(e => e.Respuestas.Count + (e.Entregar ? 1 : 0));
    }

    /// <summary>
    /// El nodo acusó recibo de este paquete: se borra lo enviado. Lo que se guardó mientras el envío viajaba (secuencias mayores) se conserva.
    /// </summary>
    public void Reconocer(PaqueteCola paquete)
    {
        lock (candado)
        {
            var e = Buscar(paquete.SesionId, paquete.DistribucionId, paquete.ParticipanteId, paquete.IntentoNumero, crear: false);
            if (e is null) return;
            var enviadas = paquete.Respuestas.ToDictionary(r => r.PreguntaRef, r => r.Secuencia);
            e.Respuestas.RemoveAll(r => enviadas.TryGetValue(r.PreguntaRef, out var s) && r.Secuencia <= s);
            if (paquete.Entregar && e.Respuestas.Count == 0) e.Entregar = false;
            if (e.Respuestas.Count == 0 && !e.Entregar) estado.Entradas.Remove(e);
            Persistir();
        }
        Cambio?.Invoke();
    }

    /// <summary>Descarta un paquete que el nodo rechazó de forma definitiva (actividad cerrada fuera de plazo, intento ya entregado…).</summary>
    public void Descartar(PaqueteCola paquete)
    {
        lock (candado)
        {
            var e = Buscar(paquete.SesionId, paquete.DistribucionId, paquete.ParticipanteId, paquete.IntentoNumero, crear: false);
            if (e is null) return;
            estado.Entradas.Remove(e);
            Persistir();
        }
        Cambio?.Invoke();
    }

    /// <summary>Olvida todo lo de una sesión de clase (sólo cuando ya no queda nada pendiente).</summary>
    public void Olvidar(string sesionId)
    {
        lock (candado)
        {
            if (estado.Entradas.Any(e => e.SesionId == sesionId && (e.Respuestas.Count > 0 || e.Entregar))) return;
            estado.Entradas.RemoveAll(e => e.SesionId == sesionId);
            foreach (var k in estado.Contadores.Keys.Where(k => k.StartsWith(sesionId + "|", StringComparison.Ordinal)).ToList()) estado.Contadores.Remove(k);
            Persistir();
        }
    }
}

/// <summary>Cuánto salió, cuánto sigue esperando y cuánto rechazó el nodo de forma definitiva en una pasada de <see cref="SincronizadorRespuestas"/>.</summary>
public sealed record ResultadoSincronizacion(int Enviados, int Pendientes, int Descartados, bool SinConexion)
{
    public static readonly ResultadoSincronizacion Nada = new(0, 0, 0, false);
}

/// <summary>
/// Vacía la cola local hacia el nodo (007-05, 007-08): manda cada paquete, y sólo cuando llega el acuse borra lo enviado. Sin conexión
/// no se pierde nada y se reintentará; un rechazo definitivo del nodo (409 <c>distribucion_cerrada</c> / <c>intento_entregado</c>,
/// 403, 404, 400) descarta el paquete para no reintentarlo eternamente. No reentrante: una segunda llamada mientras hay una en curso no hace nada.
/// </summary>
public sealed class SincronizadorRespuestas(IAulaApi api, ColaRespuestas cola)
{
    private readonly SemaphoreSlim ocupado = new(1, 1);

    /// <summary>Un envío llegó al nodo (acuse positivo) o se descartó: lo que la pantalla necesite refrescar.</summary>
    public event Action<PaqueteCola, AcuseRespuestas?>? PaqueteResuelto;

    public async Task<ResultadoSincronizacion> VaciarAsync(CancellationToken ct = default)
    {
        if (!await ocupado.WaitAsync(0, ct)) return ResultadoSincronizacion.Nada;
        int enviados = 0, descartados = 0;
        var sinConexion = false;
        try
        {
            foreach (var paquete in cola.Pendientes())
            {
                ct.ThrowIfCancellationRequested();
                var antiguedad = RelojNodo.LocalMs - paquete.EncoladoEn;
                var envio = new EnvioRespuestas(paquete.ParticipanteId, paquete.Respuestas, paquete.Entregar, paquete.IntentoNumero,
                                                antiguedad > 5_000 ? "cola" : "directo");
                var acuse = await api.EnviarRespuestasAsync(paquete.SesionId, paquete.DistribucionId, envio, ct);
                if (acuse is not null)
                {
                    RelojNodo.Aprender(acuse.ServidorEn);
                    cola.Reconocer(paquete);
                    enviados++;
                    PaqueteResuelto?.Invoke(paquete, acuse);
                    continue;
                }
                var error = api.UltimoError;
                if (error is null || error.Estado == 0 || error.Estado >= 500 || error.SesionPerdida)
                {
                    sinConexion = error is null || error.Estado == 0;
                    break;   // volverá a intentarse: la cola conserva todo
                }
                // Tableta compartida (INV-011): el paquete es de OTRA persona y esta sesión no puede hablar por ella. No es un rechazo
                // definitivo: sólo su dueña puede vaciarlo (cuando vuelva a identificarse), así que se conserva y se sigue con los demás.
                if (error.PersonaAjena) continue;
                cola.Descartar(paquete);   // el nodo lo rechazó de forma definitiva: 400, 403, 404, 409
                descartados++;
                PaqueteResuelto?.Invoke(paquete, null);
            }
        }
        finally
        {
            ocupado.Release();
        }
        return new ResultadoSincronizacion(enviados, cola.CantidadPendiente(), descartados, sinConexion);
    }
}

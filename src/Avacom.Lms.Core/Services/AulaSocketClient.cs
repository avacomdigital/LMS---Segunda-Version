using System.Diagnostics;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>UXR-003: tres valores y nada más. Nunca un porcentaje ni una calidad de señal.</summary>
public enum ConexionAula
{
    /// <summary>El canal en tiempo real con el aula está abierto.</summary>
    Conectado,
    /// <summary>Se cayó hace poco: se está reintentando y el HTTP sigue de respaldo.</summary>
    Reconectando,
    /// <summary>Lleva un rato sin canal: la app sigue trabajando con lo que tiene y guarda en el dispositivo.</summary>
    TrabajandoEnElDispositivo,
}

/// <summary>
/// El canal en tiempo real de una sesión de clase (007-01): <c>ws://nodo/ws/aula/sesiones/{id}/?rol=docente|estudiante</c>. Un solo cliente
/// para OPS (profesor: recibe los avisos de cambio y el conteo de conectados) y Student (tableta: recibe los avisos, manda su latido
/// y declara su presencia). Se reconecta solo con espera creciente; mientras el canal está caído, la pantalla sigue sondeando por HTTP,
/// que es la fuente de verdad. Los eventos se disparan en un hilo de fondo: la pantalla debe pasarlos al hilo de la interfaz.
///
/// El protocolo completo está en <c>backend/classroom_engine/interfaces/websockets.py</c>.
/// </summary>
public sealed class AulaSocketClient : IAsyncDisposable
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private static readonly TimeSpan[] Esperas = [TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(3), TimeSpan.FromSeconds(5), TimeSpan.FromSeconds(8), TimeSpan.FromSeconds(10)];

    /// <summary>Tras este tiempo sin canal el estado pasa de «reconectando» a «trabajando en el dispositivo».</summary>
    public static readonly TimeSpan TiempoPorDefectoParaTrabajarSolo = TimeSpan.FromSeconds(10);

    private readonly Uri uri;
    private readonly Func<object?>? telemetria;
    private readonly TimeSpan tiempoParaTrabajarSolo;
    private readonly SemaphoreSlim envio = new(1, 1);
    private CancellationTokenSource? parada;
    private Task? bucle;
    private ClientWebSocket? socket;
    private int rechazado;
    private readonly Stopwatch sinCanal = Stopwatch.StartNew();

    public AulaSocketClient(Uri baseHttp, string sesionId, string rol, string? participanteId = null, string? token = null,
                            Func<object?>? telemetria = null, TimeSpan? tiempoParaTrabajarSolo = null)
    {
        Rol = rol;
        uri = UriDe(baseHttp, sesionId, rol, participanteId, token);
        this.telemetria = telemetria;
        this.tiempoParaTrabajarSolo = tiempoParaTrabajarSolo ?? TiempoPorDefectoParaTrabajarSolo;
    }

    public string Rol { get; }
    public ConexionAula Conexion { get; private set; } = ConexionAula.Reconectando;
    public bool Conectado => Conexion == ConexionAula.Conectado;
    /// <summary>El saludo del último canal abierto: estado de la sesión, conteo (profesor) y el latido que pide el nodo.</summary>
    public MensajeAula? Hola { get; private set; }
    /// <summary>Verdadero si el nodo cerró el canal con un rechazo (sesión inexistente, sin permiso, expulsado): no se reintenta.</summary>
    public bool Rechazado => Volatile.Read(ref rechazado) == 1;
    public MensajeAula? UltimoRechazo { get; private set; }
    /// <summary>Viaje de ida y vuelta del último ping, en milisegundos (medida del canal, 007-01).</summary>
    public long? UltimoRttMs { get; private set; }

    public event Action<MensajeAula>? Mensaje;
    public event Action<ConexionAula>? ConexionCambio;

    public static Uri UriDe(Uri baseHttp, string sesionId, string rol, string? participanteId, string? token)
    {
        var construido = new UriBuilder(baseHttp) { Scheme = baseHttp.Scheme == Uri.UriSchemeHttps ? "wss" : "ws" };
        var consulta = new StringBuilder($"rol={(rol == "docente" ? "docente" : "estudiante")}");
        if (!string.IsNullOrWhiteSpace(participanteId)) consulta.Append("&participante=").Append(Uri.EscapeDataString(participanteId));
        if (!string.IsNullOrWhiteSpace(token)) consulta.Append("&token=").Append(Uri.EscapeDataString(token));
        return new Uri(new Uri(construido.Uri.AbsoluteUri), $"ws/aula/sesiones/{Uri.EscapeDataString(sesionId)}/?{consulta}");
    }

    /// <summary>Abre el canal y lo mantiene abierto (reintenta hasta <see cref="DetenerAsync"/>).</summary>
    public void Iniciar()
    {
        if (bucle is not null) return;
        parada = new CancellationTokenSource();
        bucle = Task.Run(() => BucleAsync(parada.Token));
    }

    public async Task DetenerAsync()
    {
        var cts = parada;
        if (cts is null) return;
        parada = null;
        cts.Cancel();
        var s = socket;
        if (s is { State: WebSocketState.Open })
        {
            try { using var limite = new CancellationTokenSource(TimeSpan.FromSeconds(2)); await s.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "app", limite.Token); }
            catch { /* el aula lo verá como una desconexión más */ }
        }
        if (bucle is not null)
        {
            try { await bucle.WaitAsync(TimeSpan.FromSeconds(3)); } catch { }
        }
        bucle = null;
        cts.Dispose();
        Cambiar(ConexionAula.TrabajandoEnElDispositivo);
    }

    /// <summary>Manda un mensaje JSON por el canal si está abierto. Falso si no hay canal (el llamador no pierde nada: sigue el HTTP).</summary>
    public async Task<bool> EnviarAsync(object mensaje, CancellationToken ct = default)
    {
        var s = socket;
        if (s is not { State: WebSocketState.Open }) return false;
        var bytes = JsonSerializer.SerializeToUtf8Bytes(mensaje, Json);
        await envio.WaitAsync(ct);
        try
        {
            await s.SendAsync(bytes, WebSocketMessageType.Text, true, ct);
            return true;
        }
        catch (Exception ex) when (ex is WebSocketException or ObjectDisposedException or InvalidOperationException or OperationCanceledException)
        {
            return false;
        }
        finally
        {
            envio.Release();
        }
    }

    /// <summary>La tableta declara su presencia por el canal (conectado · reconectando · salio).</summary>
    public Task<bool> DeclararPresenciaAsync(string estado, CancellationToken ct = default) =>
        EnviarAsync(new { tipo = "presencia", estado, telemetria = telemetria?.Invoke() }, ct);

    public Task<bool> PingAsync(CancellationToken ct = default) =>
        EnviarAsync(new { tipo = "ping", t = Stopwatch.GetTimestamp() }, ct);

    // --------------------------------------------------------------------------- bucle

    private async Task BucleAsync(CancellationToken ct)
    {
        var intento = 0;
        while (!ct.IsCancellationRequested && !Rechazado)
        {
            var abierto = false;
            try
            {
                using var nuevo = new ClientWebSocket();
                socket = nuevo;
                await nuevo.ConnectAsync(uri, ct);
                abierto = true;
                using var latidos = CancellationTokenSource.CreateLinkedTokenSource(ct);
                var latido = Task.Run(() => LatidoAsync(latidos.Token), latidos.Token);
                try { await RecibirAsync(nuevo, ct); }
                finally { latidos.Cancel(); try { await latido; } catch { } }
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { break; }
            catch (Exception ex) when (ex is WebSocketException or HttpRequestException or IOException or InvalidOperationException or OperationCanceledException) { }
            finally
            {
                socket = null;
            }
            if (ct.IsCancellationRequested || Rechazado) break;
            if (Conexion == ConexionAula.Conectado) { sinCanal.Restart(); }
            Cambiar(sinCanal.Elapsed >= tiempoParaTrabajarSolo ? ConexionAula.TrabajandoEnElDispositivo : ConexionAula.Reconectando);
            intento = abierto ? 0 : Math.Min(intento + 1, Esperas.Length - 1);
            try
            {
                var espera = Esperas[intento];
                var resto = tiempoParaTrabajarSolo - sinCanal.Elapsed;
                if (resto > TimeSpan.Zero && resto < espera)
                {
                    await Task.Delay(resto, ct);
                    Cambiar(ConexionAula.TrabajandoEnElDispositivo);
                    espera -= resto;
                }
                await Task.Delay(espera, ct);
            }
            catch (OperationCanceledException) { break; }
        }
        if (Rechazado) Cambiar(ConexionAula.TrabajandoEnElDispositivo);   // el nodo no admite este canal: no habrá tiempo real
    }

    private async Task RecibirAsync(ClientWebSocket s, CancellationToken ct)
    {
        var buffer = new byte[16 * 1024];
        using var acumulado = new MemoryStream();
        while (s.State == WebSocketState.Open && !ct.IsCancellationRequested)
        {
            acumulado.SetLength(0);
            ValueWebSocketReceiveResult resultado;
            do
            {
                resultado = await s.ReceiveAsync(buffer.AsMemory(), ct);
                if (resultado.MessageType == WebSocketMessageType.Close)
                {
                    if (s.CloseStatus is { } estado && (int)estado is >= 4400 and <= 4499) Marcar(rechazo: true);
                    try { await s.CloseAsync(WebSocketCloseStatus.NormalClosure, "ok", CancellationToken.None); } catch { }
                    return;
                }
                acumulado.Write(buffer, 0, resultado.Count);
            } while (!resultado.EndOfMessage);

            MensajeAula? mensaje;
            try { mensaje = JsonSerializer.Deserialize<MensajeAula>(acumulado.ToArray(), Json); }
            catch (JsonException) { continue; }
            if (mensaje is null) continue;
            Procesar(mensaje);
        }
    }

    private void Procesar(MensajeAula mensaje)
    {
        switch (mensaje.Tipo)
        {
            case "hola":
                Hola = mensaje;
                if (mensaje.ServidorEn is { } servidor) RelojNodo.Aprender(servidor);
                sinCanal.Restart();
                Cambiar(ConexionAula.Conectado);
                break;
            case "pong":
                if (mensaje.T is { ValueKind: JsonValueKind.Number } t && t.TryGetInt64(out var marca))
                    UltimoRttMs = (long)Stopwatch.GetElapsedTime(marca).TotalMilliseconds;
                if (mensaje.ServidorEn is { } servidorPong) RelojNodo.Aprender(servidorPong);
                break;
            case "error":
                UltimoRechazo = mensaje;
                break;
        }
        try { Mensaje?.Invoke(mensaje); }
        catch { /* una pantalla que falla al pintar no debe cerrar el canal */ }
    }

    private void Marcar(bool rechazo)
    {
        if (rechazo) Interlocked.Exchange(ref rechazado, 1);
    }

    /// <summary>La tableta manda su latido cada <c>latido_ms</c> (lo que pide el nodo) y de vez en cuando un ping para medir el viaje;
    /// el profesor sólo manda el ping (su socket es de escucha).</summary>
    private async Task LatidoAsync(CancellationToken ct)
    {
        var ciclo = 0;
        while (!ct.IsCancellationRequested)
        {
            var cada = Hola?.LatidoMs is { } ms and > 0 ? ms : 1000;   // antes del saludo no se sabe lo que pide el nodo
            try { await Task.Delay(cada, ct); }
            catch (OperationCanceledException) { return; }
            if (Rol == "docente")
            {
                await PingAsync(ct);
                continue;
            }
            await EnviarAsync(new { tipo = "latido", telemetria = telemetria?.Invoke() }, ct);
            if (++ciclo % 6 == 0) await PingAsync(ct);
        }
    }

    private void Cambiar(ConexionAula nueva)
    {
        if (Conexion == nueva) return;
        Conexion = nueva;
        try { ConexionCambio?.Invoke(nueva); }
        catch { }
    }

    public async ValueTask DisposeAsync() => await DetenerAsync();
}

using System.Net.WebSockets;
using System.Text;
using System.Text.Json;

namespace Avacom.Lms.Core.Services;

public interface IActivitySocketClient : IAsyncDisposable
{
    event EventHandler<string>? MessageReceived;
    bool IsConnected { get; }
    Task ConnectAsync(Uri socketBaseUri, string activityId, string role, string? attemptId = null, CancellationToken cancellationToken = default);
}

public sealed class ActivitySocketClient : IActivitySocketClient
{
    private readonly ClientWebSocket socket = new();
    private CancellationTokenSource? receiveLoopCancellation;

    public event EventHandler<string>? MessageReceived;
    public bool IsConnected => socket.State == WebSocketState.Open;

    public async Task ConnectAsync(Uri socketBaseUri, string activityId, string role, string? attemptId = null, CancellationToken cancellationToken = default)
    {
        var query = $"role={Uri.EscapeDataString(role)}";
        if (!string.IsNullOrWhiteSpace(attemptId)) query += $"&attempt_id={Uri.EscapeDataString(attemptId)}";
        var uri = new Uri(socketBaseUri, $"ws/activities/{Uri.EscapeDataString(activityId)}/?{query}");
        if (AparatoRegistrado.Id is { } aparato) { try { socket.Options.SetRequestHeader(ClienteJson.CabeceraDispositivo, aparato); } catch { } }
        await socket.ConnectAsync(uri, cancellationToken);
        receiveLoopCancellation = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        _ = ReceiveLoopAsync(receiveLoopCancellation.Token);
    }

    private async Task ReceiveLoopAsync(CancellationToken cancellationToken)
    {
        var buffer = new byte[4096];
        while (socket.State == WebSocketState.Open && !cancellationToken.IsCancellationRequested)
        {
            var result = await socket.ReceiveAsync(buffer, cancellationToken);
            if (result.MessageType == WebSocketMessageType.Close) break;
            var json = Encoding.UTF8.GetString(buffer, 0, result.Count);
            if (JsonDocument.Parse(json).RootElement.TryGetProperty("type", out _))
            {
                MessageReceived?.Invoke(this, json);
            }
        }
    }

    public async ValueTask DisposeAsync()
    {
        receiveLoopCancellation?.Cancel();
        if (socket.State == WebSocketState.Open)
        {
            await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "App closed", CancellationToken.None);
        }
        socket.Dispose();
        receiveLoopCancellation?.Dispose();
    }
}


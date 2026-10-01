using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>
/// Entrega al nodo, de mejor esfuerzo, los renglones WARNING+ que <see cref="RegistroLocal"/> acumuló (§2.4 del prompt de MOD-019): cada
/// minuto, y además cuando el latido lo pida (<see cref="EntregarAhoraAsync"/>). Sin equipo registrado ni sesión no intenta nada (el
/// nodo lo rechazaría); si la entrega falla, los renglones vuelven a la cola y el archivo local conserva todo. Una sola instancia por app.
/// </summary>
public sealed class EntregadorDeLogs : IDisposable
{
    public static readonly TimeSpan CadaPorDefecto = TimeSpan.FromSeconds(60);
    private static readonly TimeSpan PrimeraEspera = TimeSpan.FromSeconds(15);

    private readonly Func<ILogsApi> api;
    private readonly string app;
    private readonly Func<string?> version;
    private readonly TimeSpan cada;
    private readonly SemaphoreSlim turno = new(1, 1);
    private Timer? temporizador;

    public EntregadorDeLogs(Func<ILogsApi> api, string app, Func<string?>? version = null, TimeSpan? cada = null)
    {
        this.api = api;
        this.app = app;
        this.version = version ?? (() => RegistroLocal.VersionApp);
        this.cada = cada ?? CadaPorDefecto;
    }

    /// <summary>La última entrega aceptada por el nodo (para la pantalla de diagnóstico).</summary>
    public EntregaLogs? UltimaEntrega { get; private set; }
    public DateTimeOffset? UltimaEntregaEn { get; private set; }
    public int Entregados { get; private set; }

    /// <summary>Arranca el temporizador (idempotente).</summary>
    public void Iniciar()
    {
        temporizador ??= new Timer(_ => _ = EntregarAhoraAsync(), null, PrimeraEspera, cada);
    }

    public void Detener()
    {
        temporizador?.Dispose();
        temporizador = null;
    }

    /// <summary>Intenta entregar lo pendiente ahora. Devuelve lo que el nodo contestó, o null si no había nada, no había con qué o falló.</summary>
    public async Task<EntregaLogs?> EntregarAhoraAsync(CancellationToken ct = default)
    {
        if (!await turno.WaitAsync(0, ct)) return null;   // ya hay una entrega en curso
        try
        {
            if (!AparatoRegistrado.Conocido && ClienteJson.Token is null) return null;
            var renglones = RegistroLocal.TomarPendientes();
            if (renglones.Count == 0) return null;
            EntregaLogs? respuesta = null;
            try
            {
                using var limite = CancellationTokenSource.CreateLinkedTokenSource(ct);
                limite.CancelAfter(TimeSpan.FromSeconds(10));
                respuesta = await api().EntregarAsync(app, version(), renglones, limite.Token);
            }
            catch (Exception) { respuesta = null; }
            if (respuesta is null)
            {
                RegistroLocal.Devolver(renglones);   // sin red: el log local conserva todo y se reintenta en el siguiente tick
                return null;
            }
            UltimaEntrega = respuesta;
            UltimaEntregaEn = DateTimeOffset.Now;
            Entregados += respuesta.Escritos;
            return respuesta;
        }
        finally { turno.Release(); }
    }

    public void Dispose() => Detener();
}

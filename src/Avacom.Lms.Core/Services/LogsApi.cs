using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>
/// Cliente de <c>/api/logs/</c> (MOD-019): OPS y Student entregan sus renglones WARNING+ al nodo (<c>clientes/</c>, mejor esfuerzo, con
/// el equipo autenticado por <c>X-Avacom-Dispositivo</c> o la sesión) y el Administrador o el Técnico leen las últimas líneas de los logs
/// del nodo (<c>GET /api/logs/</c>, permiso <c>diagnostics.read</c>, sin datos personales). Nada de esto toca la bitácora.
/// </summary>
public interface ILogsApi
{
    Uri BaseUri { get; }
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }

    Task<EntregaLogs?> EntregarAsync(string app, string? versionApp, IReadOnlyList<RenglonLog> renglones, CancellationToken ct = default);
    Task<LogsDelNodo?> LeerAsync(FiltrosLogs? filtros = null, CancellationToken ct = default);
}

public sealed class LogsApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri), ILogsApi
{
    public Task<EntregaLogs?> EntregarAsync(string app, string? versionApp, IReadOnlyList<RenglonLog> renglones, CancellationToken ct = default) =>
        EnviarAsync<EntregaLogs>("api/logs/clientes/", new
        {
            app, version_app = versionApp ?? string.Empty, dispositivo_id = AparatoRegistrado.Id,
            // Nombres tal como los espera el serializador del nodo (RenglonCliente): snake_case explícito donde el camelCase no coincide.
            renglones = renglones.Select(r => new
            {
                ts = r.Ts, nivel = r.Nivel, canal = r.Canal, app = r.App, modulo = r.Modulo, evento = r.Evento, ruta = r.Ruta,
                mensaje = r.Mensaje, detalle = r.Detalle, traza = r.Traza, corr = r.Corr, version_app = r.VersionApp,
            }),
        }, ct);

    public Task<LogsDelNodo?> LeerAsync(FiltrosLogs? filtros = null, CancellationToken ct = default) =>
        ObtenerAsync<LogsDelNodo>("api/logs/" + (filtros ?? new FiltrosLogs()).Query(), ct);
}

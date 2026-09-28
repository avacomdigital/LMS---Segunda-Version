using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>
/// Cliente de <c>/api/dispositivos/</c> (MOD-009 · Device Manager). OPS lo usa para ver el inventario
/// del aula con su estado en vivo y para bloquear o desbloquear una tableta (que entonces no entra a
/// clase ni recibe lanzamientos); Student, para el latido cuando no está dentro de una clase.
/// Mismas reglas de degradación que <see cref="AulaApi"/>.
/// </summary>
public interface IDispositivosApi
{
    Uri BaseUri { get; }
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }

    Task<IReadOnlyList<DispositivoAula>?> ListarAsync(bool todos = false, CancellationToken ct = default);
    Task<DispositivoAula?> DispositivoAsync(string dispositivoId, CancellationToken ct = default);
    Task<DispositivoAula?> BloquearAsync(string dispositivoId, string actor, string? motivo = null, CancellationToken ct = default);
    Task<DispositivoAula?> DesbloquearAsync(string dispositivoId, string actor, CancellationToken ct = default);
    Task<DispositivoAula?> LatidoAsync(string identificadorHw, string nombre, string? plataforma, string? versionApp, CancellationToken ct = default);
}

public sealed class DispositivosApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri), IDispositivosApi
{
    public Task<IReadOnlyList<DispositivoAula>?> ListarAsync(bool todos = false, CancellationToken ct = default) =>
        ObtenerAsync<IReadOnlyList<DispositivoAula>>(todos ? "api/dispositivos/?todos=1" : "api/dispositivos/", ct);

    public Task<DispositivoAula?> DispositivoAsync(string dispositivoId, CancellationToken ct = default) =>
        ObtenerAsync<DispositivoAula>($"api/dispositivos/{Uri.EscapeDataString(dispositivoId)}/", ct);

    public Task<DispositivoAula?> BloquearAsync(string dispositivoId, string actor, string? motivo = null, CancellationToken ct = default) =>
        EnviarAsync<DispositivoAula>($"api/dispositivos/{Uri.EscapeDataString(dispositivoId)}/bloquear/", new { motivo, actor }, ct);

    public Task<DispositivoAula?> DesbloquearAsync(string dispositivoId, string actor, CancellationToken ct = default) =>
        EnviarAsync<DispositivoAula>($"api/dispositivos/{Uri.EscapeDataString(dispositivoId)}/desbloquear/", new { actor }, ct);

    public Task<DispositivoAula?> LatidoAsync(string identificadorHw, string nombre, string? plataforma, string? versionApp, CancellationToken ct = default) =>
        EnviarAsync<DispositivoAula>("api/dispositivos/latido/", new { identificador_hw = identificadorHw, nombre, plataforma, version_app = versionApp }, ct);
}

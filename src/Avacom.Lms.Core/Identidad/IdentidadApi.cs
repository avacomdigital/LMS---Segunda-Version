using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.IdentidadDeDispositivo;

/// <summary>
/// Cliente de <c>/api/licencia/identidad/</c> (MOD-018, Fase 5): el reto del nodo y el enrolamiento de la clave del equipo. Las dos rutas son públicas (como el latido): el equipo se identifica
/// antes de tener sesión. Un error HTTP o de red no es una excepción: devuelve null y deja el motivo y el <c>codigo</c> en <see cref="ClienteJson.UltimoMotivo"/> y <see cref="ClienteJson.UltimoError"/>.
/// </summary>
public sealed class IdentidadApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri)
{
    public Task<RetoDeIdentidad?> RetoAsync(CancellationToken ct = default) => EnviarAsync<RetoDeIdentidad>("api/licencia/identidad/reto/", new { }, ct);

    public Task<ResultadoDeIdentidad?> EnrolarAsync(string identificadorHw, IReadOnlyDictionary<string, object> identidad, CancellationToken ct = default) =>
        EnviarAsync<ResultadoDeIdentidad>("api/licencia/identidad/enrolar/", new { identificador_hw = identificadorHw, identidad }, ct);
}

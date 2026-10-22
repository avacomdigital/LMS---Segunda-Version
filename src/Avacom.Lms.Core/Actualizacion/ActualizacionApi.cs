using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Actualizacion;

/// <summary>
/// Cliente de <c>/api/actualizacion/</c> (MOD-017): una ruta por método de <see cref="IActualizacionApi"/>. Quien actúa viaja como <c>actor</c> en la consulta (GET) o en el cuerpo (POST).
/// Un error HTTP o de red no es una excepción: devuelve null y deja el motivo y el <c>codigo</c> en <see cref="ClienteJson.UltimoMotivo"/> y <see cref="ClienteJson.UltimoError"/>.
/// El id de un paquete va en la ruta tal como lo entregó el nodo (un UUID): se escapa por si acaso, nunca se arma a partir de texto escrito.
/// </summary>
public sealed class ActualizacionApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri), IActualizacionApi
{
    private const string Base = "api/actualizacion/";

    private static string Consulta(string ruta, string actor, string? extra = null)
    {
        var partes = new List<string>();
        if (!string.IsNullOrEmpty(extra)) partes.Add(extra);
        if (!string.IsNullOrEmpty(actor)) partes.Add($"actor={Uri.EscapeDataString(actor)}");
        return partes.Count == 0 ? Base + ruta : $"{Base}{ruta}?{string.Join('&', partes)}";
    }

    private static Dictionary<string, object?> Cuerpo(string actor, params (string Clave, object? Valor)[] campos)
    {
        var cuerpo = new Dictionary<string, object?>();
        foreach (var (clave, valor) in campos)
            if (valor is not null) cuerpo[clave] = valor;
        if (!string.IsNullOrEmpty(actor)) cuerpo["actor"] = actor;
        return cuerpo;
    }

    private static string Id(string paqueteId) => Uri.EscapeDataString(paqueteId);

    // ================================================================================================== leer

    public Task<EstadoDeActualizacion?> EstadoAsync(string actor, CancellationToken ct = default) => ObtenerAsync<EstadoDeActualizacion>(Consulta("estado/", actor), ct);

    public Task<ListaDePaquetes?> PaquetesAsync(string actor, CancellationToken ct = default) => ObtenerAsync<ListaDePaquetes>(Consulta("paquetes/", actor), ct);

    public Task<FichaDePaquete?> PaqueteAsync(string actor, string paqueteId, CancellationToken ct = default) =>
        ObtenerAsync<FichaDePaquete>(Consulta($"paquetes/{Id(paqueteId)}/", actor), ct);

    public Task<HistorialDeActualizacion?> HistorialAsync(string actor, int limite = 50, IReadOnlyList<string>? tipos = null, CancellationToken ct = default)
    {
        var filtros = new List<string> { $"limite={Math.Clamp(limite, 1, 500)}" };
        if (tipos is not null)
            foreach (var tipo in tipos.Where(t => !string.IsNullOrWhiteSpace(t)))
                filtros.Add($"tipo={Uri.EscapeDataString(tipo)}");
        return ObtenerAsync<HistorialDeActualizacion>(Consulta("historial/", actor, string.Join('&', filtros)), ct);
    }

    // ================================================================================================== actuar

    public Task<FichaDePaquete?> ImportarAsync(string actor, string candidatoId, CancellationToken ct = default) =>
        EnviarAsync<FichaDePaquete>(Base + "paquetes/importar/", Cuerpo(actor, ("candidato", candidatoId)), ct);

    public Task<FichaDePaquete?> ProgramarAsync(string actor, string paqueteId, long desde, long hasta, CancellationToken ct = default) =>
        EnviarAsync<FichaDePaquete>($"{Base}paquetes/{Id(paqueteId)}/programar/", Cuerpo(actor, ("desde", desde), ("hasta", hasta)), ct);

    public Task<FichaDePaquete?> DesprogramarAsync(string actor, string paqueteId, CancellationToken ct = default) =>
        EnviarAsync<FichaDePaquete>($"{Base}paquetes/{Id(paqueteId)}/desprogramar/", Cuerpo(actor), ct);

    public Task<FichaDePaquete?> AplicarAsync(string actor, string paqueteId, CancellationToken ct = default) =>
        EnviarAsync<FichaDePaquete>($"{Base}paquetes/{Id(paqueteId)}/aplicar/", Cuerpo(actor), ct);

    public Task<FichaDePaquete?> RevertirAsync(string actor, string paqueteId, string nota, CancellationToken ct = default) =>
        EnviarAsync<FichaDePaquete>($"{Base}paquetes/{Id(paqueteId)}/revertir/", Cuerpo(actor, ("nota", nota)), ct);
}

using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Nodo;

/// <summary>
/// Cliente de <c>/api/nodo/</c> (MOD-015): una ruta por método de <see cref="INodoApi"/>. Quien actúa viaja como <c>actor</c> en la consulta (GET) o en el cuerpo (POST). Un error HTTP
/// o de red no es una excepción: devuelve null y deja el motivo y el <c>codigo</c> en <see cref="ClienteJson.UltimoMotivo"/> y <see cref="ClienteJson.UltimoError"/>.
/// </summary>
public sealed class NodoApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri), INodoApi
{
    private const string Base = "api/nodo/";

    private static string Consulta(string ruta, string actor, params (string Clave, string? Valor)[] campos)
    {
        var partes = new List<string>();
        if (!string.IsNullOrEmpty(actor)) partes.Add($"actor={Uri.EscapeDataString(actor)}");
        foreach (var (clave, valor) in campos)
            if (!string.IsNullOrEmpty(valor)) partes.Add($"{clave}={Uri.EscapeDataString(valor)}");
        return partes.Count == 0 ? Base + ruta : $"{Base}{ruta}?{string.Join("&", partes)}";
    }

    private static Dictionary<string, object?> Cuerpo(string actor, params (string Clave, object? Valor)[] campos)
    {
        var cuerpo = new Dictionary<string, object?>();
        foreach (var (clave, valor) in campos)
            if (valor is not null) cuerpo[clave] = valor;
        if (!string.IsNullOrEmpty(actor)) cuerpo["actor"] = actor;
        return cuerpo;
    }

    public Task<EstadoDelNodo?> EstadoAsync(string actor, CancellationToken ct = default) => ObtenerAsync<EstadoDelNodo>(Consulta("estado/", actor), ct);

    public Task<ColaDelNodo?> ColaAsync(string actor, CancellationToken ct = default) => ObtenerAsync<ColaDelNodo>(Consulta("cola/", actor), ct);

    public Task<ProblemasDeCola?> ProblemasAsync(string actor, string? consumidor = null, string? estado = null, int limite = 100, CancellationToken ct = default) =>
        ObtenerAsync<ProblemasDeCola>(Consulta("problemas/", actor, ("consumidor", consumidor), ("estado", estado), ("limite", limite is > 0 and not 100 ? limite.ToString() : null)), ct);

    public Task<ProblemaDeCola?> ReprocesarAsync(string actor, long problemaId, CancellationToken ct = default) =>
        EnviarAsync<ProblemaDeCola>($"{Base}problemas/{problemaId}/reprocesar/", Cuerpo(actor), ct);

    public Task<ReproduccionDeConsumidor?> ReproducirAsync(string actor, string consumidor, string? fuente = null, CancellationToken ct = default) =>
        EnviarAsync<ReproduccionDeConsumidor>($"{Base}consumidores/{Uri.EscapeDataString(consumidor)}/reproducir/", Cuerpo(actor, ("fuente", fuente)), ct);

    public async Task<NodoEnSalud?> SaludAsync(CancellationToken ct = default) => (await ObtenerAsync<SaludConNodo>("health/", ct))?.Nodo;
}

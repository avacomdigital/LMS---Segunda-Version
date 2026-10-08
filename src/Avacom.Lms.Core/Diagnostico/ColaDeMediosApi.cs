using System.Text.Json.Serialization;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Diagnostico;

/// <summary>
/// Cómo va la cola de medios del nodo (<c>GET /api/medios/cola/</c>): los recursos (video, audio, imagen, PDF, html) que el nodo trae de AVACOM Contenido a
/// su caché de disco y reparte a las tabletas. Nunca lleva bytes ni contenido de cursos: sólo referencias, conteos y avance.
/// </summary>
public sealed record EstadoDeLaCola(
    bool Activa,
    [property: JsonPropertyName("motivo_apagada")] string? MotivoApagada,
    string? Modo,
    ColaPendiente? Cola,
    Dictionary<string, int>? Recursos,
    CacheDeMedios? Cache,
    TransferenciasDelNodo? Transferencias,
    LimitesDeLaCola? Limites,
    Dictionary<string, long>? Contadores)
{
    public int En(string estado) => Recursos is not null && Recursos.TryGetValue(estado, out var n) ? n : 0;
}

public sealed record ColaPendiente(int Pendientes, int Descargando);

public sealed record CacheDeMedios(
    [property: JsonPropertyName("bytes_ocupados")] long BytesOcupados,
    [property: JsonPropertyName("bytes_maximo")] long BytesMaximo,
    [property: JsonPropertyName("bytes_libres_disco")] long BytesLibresDisco,
    [property: JsonPropertyName("bytes_libres_minimo")] long BytesLibresMinimo,
    [property: JsonPropertyName("lecturas_activas")] int LecturasActivas);

public sealed record TransferenciasDelNodo(
    [property: JsonPropertyName("en_uso")] int EnUso,
    int Maximo,
    int Pico);

public sealed record LimitesDeLaCola(
    [property: JsonPropertyName("descargas_simultaneas")] int DescargasSimultaneas,
    [property: JsonPropertyName("transferencias_simultaneas")] int TransferenciasSimultaneas,
    [property: JsonPropertyName("ancho_entrada_bps")] long AnchoEntradaBps,
    [property: JsonPropertyName("ancho_salida_bps")] long AnchoSalidaBps);

/// <summary>Un recurso de la cola. <c>Estado</c>: pendiente · descargando · disponible · fallido · cancelado.</summary>
public sealed record RecursoDeMedios(
    string Id,
    string Estado,
    string? Prioridad,
    string? Fuente,
    [property: JsonPropertyName("curso_ref")] string? CursoRef,
    [property: JsonPropertyName("media_ref")] string MediaRef,
    string? Ruta,
    [property: JsonPropertyName("tipo_mime")] string? TipoMime,
    [property: JsonPropertyName("bytes_total")] long? BytesTotal,
    [property: JsonPropertyName("bytes_hechos")] long BytesHechos,
    int? Porcentaje,
    string? Sha256,
    int Intentos,
    [property: JsonPropertyName("error_codigo")] string? ErrorCodigo,
    [property: JsonPropertyName("error_detalle")] string? ErrorDetalle,
    int Usos,
    [property: JsonPropertyName("actualizado_en")] long ActualizadoEn)
{
    public bool EnCurso => Estado is "pendiente" or "descargando";
    public bool Fallo => Estado is "fallido";
}

public sealed record ListaDeRecursos(List<RecursoDeMedios>? Recursos, int Total);

/// <summary>Cliente de la cola de medios. Leer cualquier sesión; cancelar, reintentar y vaciar la caché sólo el personal del aula.</summary>
public sealed class ColaDeMediosApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri)
{
    public Task<EstadoDeLaCola?> EstadoAsync(CancellationToken ct = default) =>
        ObtenerAsync<EstadoDeLaCola>("api/medios/cola/", ct);

    /// <param name="contexto">La sesión de clase, la asignación o el intento cuyos recursos se quieren ver (vacío: todos).</param>
    /// <param name="estado">pendiente · descargando · disponible · fallido · cancelado (vacío: todos).</param>
    public Task<ListaDeRecursos?> RecursosAsync(string? contexto = null, string? estado = null, int limite = 100, CancellationToken ct = default)
    {
        var consulta = new List<string> { $"limite={Math.Clamp(limite, 1, 200)}" };
        if (!string.IsNullOrWhiteSpace(contexto)) consulta.Add($"contexto={Uri.EscapeDataString(contexto)}");
        if (!string.IsNullOrWhiteSpace(estado)) consulta.Add($"estado={Uri.EscapeDataString(estado)}");
        return ObtenerAsync<ListaDeRecursos>("api/medios/cola/recursos/?" + string.Join('&', consulta), ct);
    }

    public async Task<bool> CancelarAsync(string recursoId, CancellationToken ct = default) =>
        await EnviarAsync<System.Text.Json.JsonElement?>($"api/medios/cola/recursos/{Uri.EscapeDataString(recursoId)}/cancelar/", new { }, ct) is not null;

    public async Task<bool> ReintentarAsync(string recursoId, CancellationToken ct = default) =>
        await EnviarAsync<System.Text.Json.JsonElement?>($"api/medios/cola/recursos/{Uri.EscapeDataString(recursoId)}/reintentar/", new { }, ct) is not null;

    /// <summary>Vacía la caché de lo que nadie está leyendo; la próxima petición de cada medio lo vuelve a traer. Devuelve cuántos recursos salieron, o nulo si no se pudo.</summary>
    public async Task<int?> LimpiarAsync(CancellationToken ct = default) =>
        (await EnviarAsync<ResultadoDeLimpieza>("api/medios/cola/limpiar/", new { }, ct))?.Expulsados;

    private sealed record ResultadoDeLimpieza(int Expulsados);
}

using System.Text.Json.Serialization;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Diagnostico;

/// <summary>Lo que el nodo cuenta de su canal en tiempo real (<c>GET /api/aula/tiempo-real/</c>, 007-01): sockets abiertos por clase y cuánto tarda cada aviso.</summary>
public sealed record TiempoRealDelNodo(
    Dictionary<string, FichaDeSesionEnVivo>? Sesiones,
    [property: JsonPropertyName("avisos_entregados")] long AvisosEntregados,
    [property: JsonPropertyName("demora_ms")] DemoraDeAvisos? Demora,
    [property: JsonPropertyName("objetivo_ms")] int ObjetivoMs)
{
    public int Alumnos => Sesiones?.Values.Sum(s => s.Alumnos) ?? 0;
    public int Docentes => Sesiones?.Values.Sum(s => s.Docentes) ?? 0;
}

public sealed record FichaDeSesionEnVivo(int Docentes, int Alumnos);

public sealed record DemoraDeAvisos(int Muestras, int? P50, int? P95, int? Maximo);

/// <summary>Cliente del diagnóstico del canal en tiempo real. Es de sólo lectura y sus llamadas no cuentan en las mediciones de la app.</summary>
public sealed class DiagnosticoApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri)
{
    public Task<TiempoRealDelNodo?> TiempoRealAsync(CancellationToken ct = default) =>
        ObtenerAsync<TiempoRealDelNodo>("api/aula/tiempo-real/", ct);

    /// <summary>Los alumnos con canal abierto en todas las clases del nodo, o nulo si el nodo no contestó.</summary>
    public async Task<int?> AlumnosConectadosAsync(CancellationToken ct = default) =>
        (await TiempoRealAsync(ct))?.Alumnos;
}

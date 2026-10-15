using System.Text;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Search;

/// <summary>
/// Cliente de <c>/api/search/</c> (MOD-021): las rutas de <c>spec-driven/13-search/02-api.md</c>, una por método de <see cref="ISearchApi"/>. El profesor se identifica con
/// <c>actor</c> en la consulta (GET) o en el cuerpo (POST); los valores vacíos NO viajan. Un error HTTP o de red no es una excepción: devuelve null y deja el motivo y el
/// <c>codigo</c> en <see cref="ClienteJson.UltimoMotivo"/> y <see cref="ClienteJson.UltimoError"/>.
/// </summary>
public sealed class SearchApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri), ISearchApi
{
    private const string Base = "api/search/";

    private static string Esc(string valor) => Uri.EscapeDataString(valor);

    /// <summary>La ruta con su consulta; los valores nulos o vacíos no viajan.</summary>
    internal static string Ruta(string ruta, params (string Clave, string? Valor)[] consulta)
    {
        var texto = new StringBuilder(Base).Append(ruta);
        var separador = '?';
        foreach (var (clave, valor) in consulta)
        {
            if (string.IsNullOrEmpty(valor)) continue;
            texto.Append(separador).Append(clave).Append('=').Append(Esc(valor));
            separador = '&';
        }
        return texto.ToString();
    }

    /// <summary>La ruta completa de una consulta de búsqueda (pública para probarla sin red).</summary>
    public static string RutaDeBusqueda(string actor, ConsultaDeBusqueda c) => Ruta(string.Empty,
        ("q", c.Texto.Trim()),
        ("type", c.Tipos is { Count: > 0 } ? string.Join(',', c.Tipos) : null),
        ("country", c.Pais), ("level", c.Nivel), ("grade", c.Grado), ("subject", c.Materia), ("topic", c.Tema),
        ("period", c.Periodo), ("group", c.GrupoId),
        ("page", c.Pagina > 1 ? c.Pagina.ToString() : null),
        ("limit", c.Limite != 20 ? c.Limite.ToString() : null),
        ("actor", actor));

    public Task<RespuestaDeBusqueda?> BuscarAsync(string actor, ConsultaDeBusqueda consulta, CancellationToken ct = default) =>
        ObtenerAsync<RespuestaDeBusqueda>(RutaDeBusqueda(actor, consulta), ct);

    public Task<OpcionesDeFiltros?> FiltrosAsync(string actor, CancellationToken ct = default) =>
        ObtenerAsync<OpcionesDeFiltros>(Ruta("filters/", ("actor", actor)), ct);

    public Task<EstadoDeBusqueda?> EstadoAsync(string actor, CancellationToken ct = default) =>
        ObtenerAsync<EstadoDeBusqueda>(Ruta("status/", ("actor", actor)), ct);

    public Task<AperturaDeResultado?> AbrirAsync(string actor, DestinoDeNavegacion destino, CancellationToken ct = default)
    {
        var cuerpo = new Dictionary<string, object?> { ["entity_type"] = destino.Tipo, ["entity_id"] = destino.EntidadId, ["actor"] = actor };
        if (!string.IsNullOrEmpty(destino.CursoRef)) cuerpo["course_ref"] = destino.CursoRef;
        if (!string.IsNullOrEmpty(destino.LeccionRef)) cuerpo["lesson_ref"] = destino.LeccionRef;
        if (!string.IsNullOrEmpty(destino.ObjetoRef)) cuerpo["object_ref"] = destino.ObjetoRef;
        return EnviarAsync<AperturaDeResultado>(Base + "open/", cuerpo, ct);
    }
}

using System.Net.Http.Headers;
using System.Text.Json;

namespace Avacom.Lms.Core.Services;

/// <summary>
/// Lo que contestó el equipo del aula al pedir un medio (video, audio, imagen). El reproductor de la WebView sólo sabe decir
/// «MediaError 4: formato no compatible» tanto cuando el códec no sirve como cuando el servidor contestó un 401 o un 404, así que la causa REAL se averigua
/// aparte, con un sondeo (<see cref="DiagnosticoDeMedio.SondearAsync"/>) hecho por el código de la app.
/// </summary>
/// <param name="Estado">Estado HTTP, o null si el equipo del aula no contestó (red, tiempo agotado).</param>
/// <param name="Codigo">El <c>codigo</c> del cuerpo de error del backend (<c>pase_de_medios_vencido</c>, <c>referencia_no_encontrada</c>…).</param>
/// <param name="Tipo">El <c>Content-Type</c> con el que se entrega, si lo entrega.</param>
/// <param name="Bytes">Tamaño total del archivo (de <c>Content-Range</c> o <c>Content-Length</c>), si se conoce.</param>
/// <param name="Sugerencia">Lo que el backend sugiere hacer (503: «Abre AVACOM Contenido»).</param>
/// <param name="ErrorDeRed">El motivo cuando no hubo respuesta.</param>
public sealed record SondeoDeMedio(int? Estado, string? Codigo, string? Tipo, long? Bytes, string? Sugerencia, string? ErrorDeRed)
{
    /// <summary>El equipo del aula SÍ entrega el archivo (200, o 206 al pedir un trozo).</summary>
    public bool Entrega => Estado is 200 or 206;

    /// <summary>Una línea para el archivo de fallos: «HTTP 401 pase_de_medios_vencido», «HTTP 206 video/mp4 154451 bytes», «sin respuesta (…)».</summary>
    public string Resumen => Estado switch
    {
        null => $"sin respuesta ({ErrorDeRed})",
        _ when Entrega => $"HTTP {Estado} {Tipo}{(Bytes is { } b ? $" {b} bytes" : string.Empty)}",
        _ => $"HTTP {Estado}{(string.IsNullOrWhiteSpace(Codigo) ? string.Empty : $" {Codigo}")}",
    };

    /// <summary>La causa dicha para quien está frente a la pantalla (sin jerga de HTTP).</summary>
    public string Causa => (Estado, Codigo) switch
    {
        (null, _) => "No se pudo hablar con el equipo del aula: revisa la red o que el aula siga encendida.",
        (401, "pase_de_medios_vencido" or "sesion_expirada" or "sesion_revocada" or "sesion_inactiva" or "sesion_cerrada_otro_dispositivo")
            => "Tu sesión terminó. Vuelve a entrar para ver este medio.",
        (401, _) => "El equipo del aula no reconoció el permiso de este medio (401). Vuelve a abrir la clase.",
        (403, _) => "Tu cuenta no tiene permiso para ver este medio.",
        (404, _) => "Este medio no está en el curso instalado en el aula.",
        (502 or 503, _) => string.IsNullOrWhiteSpace(Sugerencia) ? "AVACOM Contenido no está disponible en el equipo del aula." : Sugerencia!,
        (200 or 206, _) => $"El equipo del aula sí entrega el archivo ({Tipo}), pero este dispositivo no pudo reproducirlo: el formato o el códec no es compatible.",
        _ => $"El equipo del aula respondió {Estado}.",
    };
}

/// <summary>
/// Sondeo y descarga de medios con el cliente HTTP de la app. El visor del aula (la <c>&lt;video&gt;</c> de la WebView, <c>Image</c> de MAUI) pide los medios
/// SIN cabeceras: la dirección ya lleva su permiso (<c>/api/m/&lt;pase&gt;/…</c>, ver bugfix 01). Aquí, en cambio, el código de la app sí puede mandar el
/// <c>Authorization</c>, y lo hace para las rutas sin pase (pruebas, herramientas).
/// </summary>
public static class DiagnosticoDeMedio
{
    private const long TopeDeImagen = 24L * 1024 * 1024;
    private static readonly HttpClient Compartido = new() { Timeout = TimeSpan.FromSeconds(10) };

    /// <summary>
    /// La dirección sin el pase de medios (<c>/api/m/&lt;pase&gt;/…</c> → <c>/api/m/…/…</c>): para los archivos de fallos y los registros, que se copian y se
    /// entregan al nodo. El pase es un permiso de lectura de la sesión: no debe quedar escrito.
    /// </summary>
    public static string SinPase(Uri url) =>
        PasePorCamino.Replace(url.GetLeftPart(UriPartial.Authority) + url.PathAndQuery, "/api/m/…/");

    private static readonly System.Text.RegularExpressions.Regex PasePorCamino =
        new(@"/api/m/[^/?#]+/", System.Text.RegularExpressions.RegexOptions.Compiled | System.Text.RegularExpressions.RegexOptions.CultureInvariant);

    private static HttpRequestMessage Peticion(Uri url, bool soloUnByte)
    {
        var peticion = new HttpRequestMessage(HttpMethod.Get, url);
        if (soloUnByte) peticion.Headers.Range = new RangeHeaderValue(0, 0);
        // Con pase en el camino no hace falta nada más; sin él, la ruta con Bearer de siempre.
        if (ClienteJson.Token is { } token && !url.AbsolutePath.StartsWith("/api/m/", StringComparison.Ordinal))
            peticion.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return peticion;
    }

    /// <summary>Pide el primer byte del medio y cuenta qué contestó el equipo del aula. Nunca lanza.</summary>
    public static async Task<SondeoDeMedio> SondearAsync(Uri url, HttpClient? http = null, CancellationToken ct = default)
    {
        try
        {
            using var peticion = Peticion(url, soloUnByte: true);
            using var respuesta = await (http ?? Compartido).SendAsync(peticion, HttpCompletionOption.ResponseHeadersRead, ct);
            return await LeerAsync(respuesta, ct);
        }
        catch (Exception ex)
        {
            return new SondeoDeMedio(null, null, null, null, null, ex is OperationCanceledException ? (ct.IsCancellationRequested ? "cancelado" : "tiempo agotado") : ex.Message);
        }
    }

    /// <summary>Descarga una imagen entera. Si el equipo del aula no la entrega, devuelve el sondeo con la causa y ningún byte. Nunca lanza.</summary>
    public static async Task<(byte[]? Bytes, SondeoDeMedio Sondeo)> DescargarImagenAsync(Uri url, HttpClient? http = null, CancellationToken ct = default)
    {
        try
        {
            using var peticion = Peticion(url, soloUnByte: false);
            using var respuesta = await (http ?? Compartido).SendAsync(peticion, HttpCompletionOption.ResponseHeadersRead, ct);
            var sondeo = await LeerAsync(respuesta, ct);
            if (!sondeo.Entrega) return (null, sondeo);
            if (respuesta.Content.Headers.ContentLength is > TopeDeImagen) return (null, sondeo with { Estado = 413, Codigo = "imagen_demasiado_grande" });
            return (await respuesta.Content.ReadAsByteArrayAsync(ct), sondeo);
        }
        catch (Exception ex)
        {
            return (null, new SondeoDeMedio(null, null, null, null, null, ex is OperationCanceledException ? (ct.IsCancellationRequested ? "cancelado" : "tiempo agotado") : ex.Message));
        }
    }

    private static async Task<SondeoDeMedio> LeerAsync(HttpResponseMessage respuesta, CancellationToken ct)
    {
        var estado = (int)respuesta.StatusCode;
        var tipo = respuesta.Content.Headers.ContentType?.MediaType;
        if (respuesta.IsSuccessStatusCode)
        {
            var total = respuesta.Content.Headers.ContentRange?.Length ?? respuesta.Content.Headers.ContentLength;
            return new SondeoDeMedio(estado, null, tipo, total, null, null);
        }
        string? codigo = null, sugerencia = null;
        try
        {
            // El cuerpo de error del backend es JSON pequeño: {detail, codigo, sugerencia?}. Se lee acotado por si algún intermediario devuelve una página.
            var texto = await respuesta.Content.ReadAsStringAsync(ct);
            if (texto.Length is > 0 and < 8192 && texto.TrimStart().StartsWith('{'))
            {
                using var documento = JsonDocument.Parse(texto);
                if (documento.RootElement.TryGetProperty("codigo", out var c) && c.ValueKind == JsonValueKind.String) codigo = c.GetString();
                if (documento.RootElement.TryGetProperty("sugerencia", out var s) && s.ValueKind == JsonValueKind.String) sugerencia = s.GetString();
            }
        }
        catch (Exception ex) when (ex is JsonException or HttpRequestException or IOException) { /* sin cuerpo legible: vale el estado */ }
        return new SondeoDeMedio(estado, codigo, tipo, null, sugerencia, null);
    }
}

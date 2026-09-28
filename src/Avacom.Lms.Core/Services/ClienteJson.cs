using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>
/// Lo que comparten los clientes del backend del LMS (aula, dispositivos): toda URL nace de
/// <see cref="BaseUri"/>, un error HTTP no es una excepción de negocio (devuelve null y deja el
/// motivo en <see cref="UltimoMotivo"/> y el <c>codigo</c> del backend en <see cref="UltimoError"/>)
/// y los cuerpos viajan con Content-Length (el servidor de desarrollo de Django no lee cuerpos troceados).
/// </summary>
public abstract class ClienteJson(HttpClient http, Uri baseUri)
{
    protected static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public Uri BaseUri { get; } = baseUri;
    public string? UltimoMotivo { get; private set; }
    public ErrorAula? UltimoError { get; private set; }

    public Uri Absoluta(string rutaRelativa) => new(BaseUri, rutaRelativa.TrimStart('/'));

    protected async Task<T?> ObtenerAsync<T>(string ruta, CancellationToken ct)
    {
        try
        {
            using var respuesta = await http.GetAsync(Absoluta(ruta), ct);
            if (!respuesta.IsSuccessStatusCode)
            {
                await RegistrarErrorAsync(respuesta, ct);
                return default;
            }
            Limpiar();
            return await respuesta.Content.ReadFromJsonAsync<T>(Json, ct);
        }
        catch (Exception ex) when (EsDeRed(ex))
        {
            SinRed();
            return default;
        }
    }

    protected async Task<T?> EnviarAsync<T>(string ruta, object cuerpo, CancellationToken ct)
    {
        try
        {
            var contenido = new StringContent(JsonSerializer.Serialize(cuerpo, Json), Encoding.UTF8, "application/json");
            using var respuesta = await http.PostAsync(Absoluta(ruta), contenido, ct);
            if (!respuesta.IsSuccessStatusCode)
            {
                await RegistrarErrorAsync(respuesta, ct);
                return default;
            }
            Limpiar();
            return await respuesta.Content.ReadFromJsonAsync<T>(Json, ct);
        }
        catch (Exception ex) when (EsDeRed(ex))
        {
            SinRed();
            return default;
        }
    }

    private void Limpiar()
    {
        UltimoMotivo = null;
        UltimoError = null;
    }

    private void SinRed()
    {
        UltimoMotivo = "No hay conexión con el aula.";
        UltimoError = new ErrorAula(0, "sin_conexion", UltimoMotivo, "Revisa que el equipo del aula esté encendido y en la misma red.", null);
    }

    private async Task RegistrarErrorAsync(HttpResponseMessage respuesta, CancellationToken ct)
    {
        var estado = (int)respuesta.StatusCode;
        string? codigo = null, detalle = null, sugerencia = null;
        JsonElement? extra = null;
        try
        {
            var texto = await respuesta.Content.ReadAsStringAsync(ct);
            if (!string.IsNullOrWhiteSpace(texto))
            {
                using var doc = JsonDocument.Parse(texto);
                var raiz = doc.RootElement.Clone();
                extra = raiz;
                if (raiz.ValueKind == JsonValueKind.Object)
                {
                    if (raiz.TryGetProperty("detail", out var d) && d.ValueKind == JsonValueKind.String) detalle = d.GetString();
                    if (raiz.TryGetProperty("codigo", out var c) && c.ValueKind == JsonValueKind.String) codigo = c.GetString();
                    if (raiz.TryGetProperty("sugerencia", out var s) && s.ValueKind == JsonValueKind.String) sugerencia = s.GetString();
                }
            }
        }
        catch (JsonException) { }
        detalle ??= estado switch
        {
            (int)HttpStatusCode.ServiceUnavailable => "El aula no puede leer el curso en este momento.",
            (int)HttpStatusCode.NotFound => "No se encontró lo que se pedía.",
            _ => $"El backend respondió {estado}.",
        };
        UltimoMotivo = detalle;
        UltimoError = new ErrorAula(estado, codigo, detalle, sugerencia, extra);
    }

    private static bool EsDeRed(Exception ex) =>
        ex is HttpRequestException or TaskCanceledException or JsonException or IOException;
}

using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>
/// Lo que comparten los clientes del backend del LMS (aula, dispositivos, acceso): toda URL nace de
/// <see cref="BaseUri"/>, un error HTTP no es una excepción de negocio (devuelve null y deja el
/// motivo en <see cref="UltimoMotivo"/> y el <c>codigo</c> del backend en <see cref="UltimoError"/>)
/// y los cuerpos viajan con Content-Length (el servidor de desarrollo de Django no lee cuerpos troceados).
///
/// Con el nodo en modo «sesión obligatoria» (Q-34), <see cref="Token"/> es el JWT de MOD-001 de quien usa la app: se
/// manda en cada petición. Es de todo el proceso porque cada app (OPS, Student) tiene una sola persona al frente. Si el
/// backend responde 401 con un código <c>sesion_*</c> (caducó, se cerró por inactividad, se abrió en otro dispositivo…)
/// se avisa por <see cref="SesionRechazada"/> y la pantalla decide qué mostrar.
/// </summary>
public abstract class ClienteJson(HttpClient http, Uri baseUri)
{
    protected static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    private static volatile string? token;

    /// <summary>El JWT de la sesión de usuario (<c>Authorization: Bearer</c>). Nulo mientras el nodo no exija sesión.</summary>
    public static string? Token
    {
        get => token;
        set => token = string.IsNullOrWhiteSpace(value) ? null : value;
    }

    /// <summary>El backend rechazó la sesión: <c>sesion_expirada</c>, <c>sesion_inactiva</c>, <c>sesion_cerrada_otro_dispositivo</c>…</summary>
    public static event Action<ErrorAula>? SesionRechazada;

    public Uri BaseUri { get; } = baseUri;
    public string? UltimoMotivo { get; private set; }
    public ErrorAula? UltimoError { get; private set; }

    public Uri Absoluta(string rutaRelativa) => new(BaseUri, rutaRelativa.TrimStart('/'));

    private HttpRequestMessage Peticion(HttpMethod metodo, string ruta, HttpContent? contenido = null)
    {
        var mensaje = new HttpRequestMessage(metodo, Absoluta(ruta)) { Content = contenido };
        if (Token is { } t) mensaje.Headers.Authorization = new AuthenticationHeaderValue("Bearer", t);
        return mensaje;
    }

    protected async Task<T?> ObtenerAsync<T>(string ruta, CancellationToken ct)
    {
        try
        {
            using var peticion = Peticion(HttpMethod.Get, ruta);
            using var respuesta = await http.SendAsync(peticion, ct);
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
            using var peticion = Peticion(HttpMethod.Post, ruta, contenido);
            using var respuesta = await http.SendAsync(peticion, ct);
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

    /// <summary>PATCH con cuerpo JSON (cambiar una asignación, registrar avance). Mismas reglas que <see cref="EnviarAsync{T}"/>.</summary>
    protected async Task<T?> ParchearAsync<T>(string ruta, object cuerpo, CancellationToken ct)
    {
        try
        {
            var contenido = new StringContent(JsonSerializer.Serialize(cuerpo, Json), Encoding.UTF8, "application/json");
            using var peticion = Peticion(HttpMethod.Patch, ruta, contenido);
            using var respuesta = await http.SendAsync(peticion, ct);
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

    /// <summary>
    /// GET que devuelve el cuerpo TAL COMO LLEGÓ, sin interpretarlo. Lo necesita quien debe verificar una huella sobre el texto original
    /// (el manifiesto de un paquete de estudio): volver a serializar un DTO no reproduce lo que el nodo firmó.
    /// </summary>
    protected async Task<string?> ObtenerTextoAsync(string ruta, CancellationToken ct)
    {
        try
        {
            using var peticion = Peticion(HttpMethod.Get, ruta);
            using var respuesta = await http.SendAsync(peticion, ct);
            if (!respuesta.IsSuccessStatusCode)
            {
                await RegistrarErrorAsync(respuesta, ct);
                return null;
            }
            var texto = await respuesta.Content.ReadAsStringAsync(ct);
            Limpiar();
            return texto;
        }
        catch (Exception ex) when (EsDeRed(ex))
        {
            SinRed();
            return null;
        }
    }

    /// <summary>
    /// GET en streaming: devuelve la respuesta ABIERTA (solo cabeceras leídas, <see cref="HttpCompletionOption.ResponseHeadersRead"/>) para que
    /// quien llama lea el cuerpo por partes y la libere; sirve para bajar archivos grandes y reanudables (<c>Range</c>). <paramref name="cabeceras"/>
    /// añade cabeceras a la petición. Con un estado que no es 2xx registra el error, libera la respuesta y devuelve null.
    /// </summary>
    protected async Task<HttpResponseMessage?> ObtenerRespuestaAsync(string ruta, Action<HttpRequestHeaders>? cabeceras, CancellationToken ct)
    {
        HttpResponseMessage? respuesta = null;
        try
        {
            using var peticion = Peticion(HttpMethod.Get, ruta);
            cabeceras?.Invoke(peticion.Headers);
            respuesta = await http.SendAsync(peticion, HttpCompletionOption.ResponseHeadersRead, ct);
            if (!respuesta.IsSuccessStatusCode)
            {
                await RegistrarErrorAsync(respuesta, ct);
                respuesta.Dispose();
                return null;
            }
            Limpiar();
            return respuesta;
        }
        catch (Exception ex) when (EsDeRed(ex))
        {
            respuesta?.Dispose();
            SinRed();
            return null;
        }
    }

    /// <summary>DELETE sin cuerpo de respuesta (cerrar la sesión de usuario). Verdadero si el backend contestó 2xx.</summary>
    protected async Task<bool> EliminarAsync(string ruta, CancellationToken ct)
    {
        try
        {
            using var peticion = Peticion(HttpMethod.Delete, ruta);
            using var respuesta = await http.SendAsync(peticion, ct);
            if (!respuesta.IsSuccessStatusCode)
            {
                await RegistrarErrorAsync(respuesta, ct);
                return false;
            }
            Limpiar();
            return true;
        }
        catch (Exception ex) when (EsDeRed(ex))
        {
            SinRed();
            return false;
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
        if (UltimoError.SesionPerdida) SesionRechazada?.Invoke(UltimoError);
    }

    private static bool EsDeRed(Exception ex) =>
        ex is HttpRequestException or TaskCanceledException or JsonException or IOException;
}

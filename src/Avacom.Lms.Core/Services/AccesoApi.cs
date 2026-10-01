using System.Text.Json;
using System.Text.Json.Serialization;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>Lo que el nodo dice de sí mismo antes de identificarse (PAN-101): si está instalado y si exige sesión (Q-34).</summary>
public sealed record ConfiguracionAcceso(
    [property: JsonPropertyName("instalado")] bool Instalado,
    [property: JsonPropertyName("sesion_obligatoria")] bool SesionObligatoria,
    [property: JsonPropertyName("perfiles")] JsonElement? Perfiles = null,
    [property: JsonPropertyName("inactividad_min")] int? InactividadMin = null);

public sealed record UsuarioDeSesion(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("alias")] string? Alias,
    [property: JsonPropertyName("rol")] string? Rol,
    [property: JsonPropertyName("menu")] string? Menu,
    [property: JsonPropertyName("nivel")] int Nivel,
    [property: JsonPropertyName("debe_cambiar_credencial")] bool DebeCambiarCredencial = false);

/// <summary>La sesión de usuario que abre el login (MOD-001). <c>SesionAnterior</c> existe cuando esta entrada cerró otra de la misma persona (MSG-020/021).</summary>
public sealed record SesionAcceso(
    [property: JsonPropertyName("token")] string Token,
    [property: JsonPropertyName("expira_en")] long ExpiraEn,
    [property: JsonPropertyName("sesion_id")] string SesionId,
    [property: JsonPropertyName("usuario")] UsuarioDeSesion Usuario,
    [property: JsonPropertyName("sesion_anterior")] SesionAnterior? SesionAnterior = null)
{
    public bool CerroOtraSesion => SesionAnterior is not null;
}

public sealed record SesionAnterior(
    [property: JsonPropertyName("sesion_id")] string? SesionId,
    [property: JsonPropertyName("dispositivo")] string? Dispositivo);

/// <summary>
/// Cliente de <c>/api/acceso/</c> (MOD-001) para OPS y Student: sólo lo que hace falta para identificarse. El JWT que devuelve el login
/// queda en <see cref="ClienteJson.Token"/> y viaja en cada petición de todos los clientes del proceso.
/// </summary>
public interface IAccesoApi
{
    Uri BaseUri { get; }
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }
    Task<ConfiguracionAcceso?> ConfiguracionAsync(CancellationToken ct = default);
    Task<SesionAcceso?> IniciarSesionAsync(string identificador, string secreto, string dispositivo, string? rol = null, CancellationToken ct = default);
    Task<bool> CerrarSesionAsync(CancellationToken ct = default);
    /// <summary>
    /// BR-101 / PAN-241: concede a <paramref name="usuarioId"/> una escalada temporal de <paramref name="permiso"/> con motivo y caducidad. La
    /// concede quien firma el pase vigente (<see cref="ClienteJson.Token"/>), que debe ser una identidad DISTINTA de quien la recibe.
    /// Es la «autorización de salida» que exige exportar la bitácora (MOD-019, ESC-03). Devuelve la escalada o null (y el motivo en UltimoError).
    /// </summary>
    Task<JsonElement?> OtorgarEscaladaAsync(string usuarioId, string permiso, string alcance, string motivo, long vigenteHastaMs, CancellationToken ct = default);
}

public sealed class AccesoApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri), IAccesoApi
{
    public Task<ConfiguracionAcceso?> ConfiguracionAsync(CancellationToken ct = default) =>
        ObtenerAsync<ConfiguracionAcceso>("api/acceso/configuracion/", ct);

    public async Task<SesionAcceso?> IniciarSesionAsync(string identificador, string secreto, string dispositivo, string? rol = null, CancellationToken ct = default)
    {
        Token = null;   // un login nuevo no viaja con el pase de la sesión anterior
        var sesion = await EnviarAsync<SesionAcceso>("api/acceso/sesiones/", new { identificador, secreto, dispositivo, rol = rol ?? "" }, ct);
        if (sesion is not null) Token = sesion.Token;
        return sesion;
    }

    public Task<JsonElement?> OtorgarEscaladaAsync(string usuarioId, string permiso, string alcance, string motivo, long vigenteHastaMs, CancellationToken ct = default) =>
        EnviarAsync<JsonElement?>($"api/acceso/usuarios/{Uri.EscapeDataString(usuarioId)}/escaladas/",
                                  new { permiso, alcance, motivo, vigente_hasta = vigenteHastaMs }, ct);

    public async Task<bool> CerrarSesionAsync(CancellationToken ct = default)
    {
        var mio = Token;
        var cerrada = await EliminarAsync("api/acceso/sesiones/actual/", ct);
        // Aunque el nodo no conteste, esta app deja de presentarse como esa persona. Pero sólo si el pase sigue siendo el de quien se
        // despide: si otra persona ya se identificó mientras la llamada viajaba, su pase no se toca.
        if (Token == mio) Token = null;
        return cerrada;
    }
}

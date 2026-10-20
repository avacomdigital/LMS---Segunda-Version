using System.Text.Json;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Licencia;

/// <summary>
/// Cliente de <c>/api/licencia/</c> (MOD-018): una ruta por método de <see cref="ILicenciaApi"/>. Quien actúa viaja como <c>actor</c> en la consulta (GET) o en el cuerpo (POST). Los
/// archivos viajan en JSON: al instalar, el texto <c>AVL1.…</c> como <c>licencia</c> o los bytes en base64 como <c>archivo_b64</c>. Un error HTTP o de red no es una excepción: devuelve
/// null y deja el motivo y el <c>codigo</c> en <see cref="ClienteJson.UltimoMotivo"/> y <see cref="ClienteJson.UltimoError"/>.
/// </summary>
public sealed class LicenciaApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri), ILicenciaApi
{
    private const string Base = "api/licencia/";

    private static string Consulta(string ruta, string actor) =>
        string.IsNullOrEmpty(actor) ? Base + ruta : $"{Base}{ruta}?actor={Uri.EscapeDataString(actor)}";

    private static Dictionary<string, object?> Cuerpo(string actor, params (string Clave, object? Valor)[] campos)
    {
        var cuerpo = new Dictionary<string, object?>();
        foreach (var (clave, valor) in campos)
            if (valor is not null) cuerpo[clave] = valor;
        if (!string.IsNullOrEmpty(actor)) cuerpo["actor"] = actor;
        return cuerpo;
    }

    /// <summary>
    /// Qué viaja al instalar a partir de un texto: si es la forma de texto (<c>AVL1.…</c>, con o sin espacios a los lados) va como <c>licencia</c>; si no, se toma como el base64 de los
    /// bytes del archivo y va como <c>archivo_b64</c>. El nodo valida las dos formas de manera estricta.
    /// </summary>
    public static (string Clave, string Valor) CampoDeInstalacion(string textoOBase64)
    {
        var limpio = (textoOBase64 ?? string.Empty).Trim().TrimStart('﻿').Trim();
        return limpio.StartsWith(MarcaDeLicencia.PrefijoDeTexto, StringComparison.Ordinal) ? ("licencia", limpio) : ("archivo_b64", limpio);
    }

    /// <summary>Qué viaja al instalar a partir de los bytes del archivo: un archivo en forma de texto va como texto; cualquier otro, como sus bytes (el nodo decide si es una licencia).</summary>
    public static (string Clave, string Valor) CampoDeInstalacion(byte[] archivo)
    {
        ArgumentNullException.ThrowIfNull(archivo);
        return MarcaDeLicencia.TextoDe(archivo) is { } texto ? ("licencia", texto) : ("archivo_b64", Convert.ToBase64String(archivo));
    }

    // ================================================================================================== leer

    public Task<EstadoLicencia?> EstadoAsync(string actor, CancellationToken ct = default) => ObtenerAsync<EstadoLicencia>(Consulta("estado/", actor), ct);

    public Task<ConsumoDeLicencia?> ConsumoAsync(string actor, CancellationToken ct = default) => ObtenerAsync<ConsumoDeLicencia>(Consulta("consumo/", actor), ct);

    public Task<CapacidadesDelNodo?> CapacidadesAsync(string actor, CancellationToken ct = default) => ObtenerAsync<CapacidadesDelNodo>(Consulta("capacidades/", actor), ct);

    public Task<CopiaDeLicencia?> CopiaAsync(string actor, CancellationToken ct = default) => ObtenerAsync<CopiaDeLicencia>(Consulta("copia/", actor), ct);

    // ================================================================================================== actuar

    public Task<SolicitudDeLicencia?> SolicitudAsync(string actor, CancellationToken ct = default) =>
        EnviarAsync<SolicitudDeLicencia>(Base + "solicitud/", Cuerpo(actor), ct);

    public Task<EstadoLicencia?> ActivarAsync(string actor, string textoOBase64, CancellationToken ct = default) => InstalarAsync("activar/", actor, CampoDeInstalacion(textoOBase64), ct);

    public Task<EstadoLicencia?> ActivarAsync(string actor, byte[] archivo, CancellationToken ct = default) => InstalarAsync("activar/", actor, CampoDeInstalacion(archivo), ct);

    public Task<EstadoLicencia?> RenovarAsync(string actor, string textoOBase64, CancellationToken ct = default) => InstalarAsync("renovar/", actor, CampoDeInstalacion(textoOBase64), ct);

    public Task<EstadoLicencia?> RenovarAsync(string actor, byte[] archivo, CancellationToken ct = default) => InstalarAsync("renovar/", actor, CampoDeInstalacion(archivo), ct);

    private Task<EstadoLicencia?> InstalarAsync(string ruta, string actor, (string Clave, string Valor) campo, CancellationToken ct) =>
        EnviarAsync<EstadoLicencia>(Base + ruta, Cuerpo(actor, (campo.Clave, campo.Valor)), ct);

    public async Task<ResultadoDeLiberacion?> LiberarAsync(string actor, CancellationToken ct = default)
    {
        // El nodo responde en UN cuerpo el archivo de liberación y su estado nuevo: se lee una vez y se separa en las dos partes.
        var cuerpo = await EnviarAsync<JsonElement>(Base + "liberar/", Cuerpo(actor), ct);
        if (cuerpo.ValueKind != JsonValueKind.Object) return null;
        try
        {
            var archivo = cuerpo.Deserialize<LiberacionDeLicencia>(Json);
            var estado = cuerpo.Deserialize<EstadoLicencia>(Json);
            if (archivo is not null && estado is not null && !string.IsNullOrEmpty(archivo.ArchivoB64) && !string.IsNullOrEmpty(archivo.Sha256))
                return new ResultadoDeLiberacion(archivo, estado);
        }
        catch (JsonException) { /* se dice abajo */ }
        // El equipo YA quedó liberado en el nodo: lo que falta es el archivo que lo prueba. Se dice tal cual, sin dar a entender que no pasó nada.
        AnotarMotivo("respuesta_incompleta", "El aula liberó la licencia pero no entregó completo el archivo de liberación.", "Vuelve a activar el mismo archivo de licencia para deshacerlo, o avisa a soporte.");
        return null;
    }

    public Task<EstadoLicencia?> ConfirmarRelojAsync(string actor, CancellationToken ct = default) =>
        EnviarAsync<EstadoLicencia>(Base + "reloj/confirmar/", Cuerpo(actor), ct);
}

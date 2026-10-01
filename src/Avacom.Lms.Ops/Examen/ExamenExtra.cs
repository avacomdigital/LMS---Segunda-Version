using System.Text.Json;
using System.Text.Json.Serialization;
using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ops.Examen;

// Lo que el nodo ya manda en /api/evaluacion/ y los registros del Core no recogen (los registros del Core están cubiertos por pruebas de contrato y no se tocan).
// Son solamente de lectura y sólo los usa OPS; si el Core los incorpora, estos archivos se borran.

/// <summary>Una asignación con las referencias que la lista del Core no trae: qué objeto del curso es (para saber cuál examen de la clase ya se aplicó) y a qué grupo.</summary>
internal sealed record AsignacionConReferencias(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("titulo")] string? Titulo,
    [property: JsonPropertyName("curso_ref")] string? CursoRef,
    [property: JsonPropertyName("objeto_ref")] string? ObjetoRef,
    [property: JsonPropertyName("grupo_id")] string? GrupoId,
    [property: JsonPropertyName("grupo_rotulo")] string? GrupoRotulo,
    [property: JsonPropertyName("sesion_id")] string? SesionId,
    [property: JsonPropertyName("creada_en")] long? CreadaEn = null)
{
    /// <summary>Está viva o terminó pero se puede ver: la que cuenta como «el examen de esta clase».</summary>
    public bool CuentaEnLaClase => Estado is "activa" or "activa_fuera_de_plazo" or "cerrada";
}

internal sealed record ListaConReferencias(
    [property: JsonPropertyName("asignaciones")] IReadOnlyList<AsignacionConReferencias> Asignaciones);

/// <summary>El último informe de bloqueo de la tableta (D-12): qué logró aplicar y cuándo lo dijo.</summary>
internal sealed record BloqueoInformado(
    [property: JsonPropertyName("resultado")] string? Resultado,
    [property: JsonPropertyName("capas")] CapasDeBloqueo? Capas,
    [property: JsonPropertyName("motivo")] string? Motivo,
    [property: JsonPropertyName("informado_en")] long? InformadoEn);

/// <summary>Los campos del intento que el expediente del Core no recoge: la tableta, si la calificación quedó pendiente y el último informe de bloqueo.</summary>
internal sealed record DatosExtraDelIntento(
    [property: JsonPropertyName("asignacion_id")] string? AsignacionId,
    [property: JsonPropertyName("dispositivo_id")] string? DispositivoId,
    [property: JsonPropertyName("calificacion_pendiente")] bool CalificacionPendiente,
    [property: JsonPropertyName("requiere_revision")] bool RequiereRevision,
    [property: JsonPropertyName("tiempo_limite_seg")] int? TiempoLimiteSeg,
    [property: JsonPropertyName("anulado_en")] long? AnuladoEn,
    [property: JsonPropertyName("calificado_por")] string? CalificadoPor);

internal sealed record ExpedienteExtra(
    [property: JsonPropertyName("intento")] DatosExtraDelIntento Intento,
    [property: JsonPropertyName("bloqueo")] BloqueoInformado? Bloqueo);

/// <summary>
/// Cliente de las dos lecturas de arriba. Hereda de <see cref="ClienteJson"/> como los demás clientes del LMS (misma cabecera de sesión, mismo aparato, mismos
/// errores tranquilos), así que un fallo es <c>null</c> y no una excepción.
/// </summary>
internal sealed class ExamenExtraApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri)
{
    private static string Esc(string valor) => Uri.EscapeDataString(valor);

    /// <summary>Las asignaciones de una clase, con su objeto y su grupo.</summary>
    public Task<ListaConReferencias?> AsignacionesDeClaseAsync(string actor, string sesionId, CancellationToken ct = default) =>
        ObtenerAsync<ListaConReferencias>($"api/evaluacion/asignaciones/?sesion_id={Esc(sesionId)}&actor={Esc(actor)}", ct);

    public Task<ExpedienteExtra?> ExpedienteAsync(string actor, string intentoId, CancellationToken ct = default) =>
        ObtenerAsync<ExpedienteExtra>($"api/evaluacion/intentos/{Esc(intentoId)}/?actor={Esc(actor)}", ct);
}

/// <summary>Una instancia del cliente extra por dirección del nodo, como <c>Sesion</c> hace con los demás.</summary>
internal static class ExamenExtra
{
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(15) };
    private static ExamenExtraApi? _api;
    private static Uri? _base;

    public static ExamenExtraApi Api
    {
        get
        {
            var actual = Sesion.BaseUri;
            if (_api is null || _base != actual)
            {
                _api = new ExamenExtraApi(Http, actual);
                _base = actual;
            }
            return _api;
        }
    }
}

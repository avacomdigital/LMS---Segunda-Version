using System.Text.Json;
using Avacom.Lms.Core.Gradebook;

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>
/// La respuesta de un alumno, en palabras, para que el profesor la lea al revisar. Lo que requiere revisión es respuesta abierta (texto) o evidencia (dibujo, audio,
/// entrega): del texto se muestra lo escrito y de la evidencia sólo su REFERENCIA (los archivos viven en otro módulo; aquí no se pintan). Sin MAUI.
/// </summary>
internal static class RespuestaDeRevision
{
    public const string SinRespuesta = "No respondió";

    /// <summary>«Dibujo», «Audio» o «Evidencia», según lo que la referencia diga que es.</summary>
    public static string RotuloDeEvidencia(string? tipo)
    {
        var t = (tipo ?? string.Empty).ToLowerInvariant();
        if (t.Contains("draw") || t.Contains("dibujo")) return "Dibujo";
        if (t.Contains("audio")) return "Audio";
        return "Evidencia";
    }

    /// <summary>Una línea por evidencia: «Dibujo: referencia abc». No se pinta ningún archivo.</summary>
    public static IReadOnlyList<string> Evidencias(ReactivoParaRevisar r) =>
        (r.Evidencias ?? []).Select(e => $"{RotuloDeEvidencia(e.Tipo)}: referencia {e.Ref}").ToList();

    /// <summary>El texto que escribió el alumno; si no escribió (respondió con una evidencia), nada.</summary>
    public static string? TextoEscrito(ReactivoParaRevisar r) =>
        r.Respuesta is { ValueKind: JsonValueKind.Object } o && o.TryGetProperty("text", out var t) && t.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(t.GetString())
            ? t.GetString()
            : null;

    /// <summary>Lo que se muestra de la respuesta de un reactivo que requiere revisión: lo escrito, o la nota de que respondió con evidencia, o que no respondió.</summary>
    public static string Para(ReactivoParaRevisar r)
    {
        if (TextoEscrito(r) is { } texto) return texto;
        if (r.Evidencias is { Count: > 0 }) return "Respondió con evidencia (se muestra sólo su referencia).";
        return r.Respondida ? "Respondió, pero la respuesta no es un texto que se pueda mostrar aquí." : SinRespuesta;
    }

    /// <summary>
    /// Una línea corta de una respuesta que el sistema ya calificó (opción, verdadero o falso, huecos, orden, pares). Sólo para el resumen de lo que no requiere
    /// revisión: sin las opciones de la pregunta no se pueden nombrar, así que se dice cuántas o cuáles marcó.
    /// </summary>
    public static string Resumen(ReactivoParaRevisar r)
    {
        if (!r.Respondida) return SinRespuesta;
        if (r.Respuesta is not { ValueKind: JsonValueKind.Object } o) return "Respondió";
        try
        {
            if (o.TryGetProperty("value", out var v) && v.ValueKind is JsonValueKind.True or JsonValueKind.False) return v.GetBoolean() ? "Verdadero" : "Falso";
            if (o.TryGetProperty("selectedOptionIds", out var ids) && ids.ValueKind == JsonValueKind.Array) return $"Marcó {ids.GetArrayLength()} {(ids.GetArrayLength() == 1 ? "opción" : "opciones")}";
            if (o.TryGetProperty("blanks", out var huecos) && huecos.ValueKind == JsonValueKind.Object)
                return string.Join("; ", huecos.EnumerateObject().Select(h => h.Value.ValueKind == JsonValueKind.String ? h.Value.GetString() : h.Value.ToString()));
            if (o.TryGetProperty("order", out var orden) && orden.ValueKind == JsonValueKind.Array) return $"Ordenó {orden.GetArrayLength()} elementos";
            if (o.TryGetProperty("pairs", out var pares) && pares.ValueKind == JsonValueKind.Array) return $"Relacionó {pares.GetArrayLength()} pares";
            if (TextoEscrito(r) is { } texto) return texto;
        }
        catch (Exception ex) when (ex is InvalidOperationException or FormatException) { /* una forma inesperada cae a «Respondió» */ }
        return "Respondió";
    }
}

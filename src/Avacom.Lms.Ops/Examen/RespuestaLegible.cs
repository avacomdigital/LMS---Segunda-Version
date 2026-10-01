using System.Globalization;
using System.Text.Json;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Ops.Examen;

/// <summary>Lo que la biblioteca dijo de una respuesta al calificar (<c>veredicto</c>). El nodo nunca lo inventa: lo copia tal cual.</summary>
internal sealed record VeredictoLeido(bool? Correcta, bool Pendiente, double? Puntaje, double? PuntajeMaximo, bool RequiereCorreccionManual)
{
    public static VeredictoLeido? De(JsonElement? json)
    {
        if (json is not { ValueKind: JsonValueKind.Object } v) return null;
        return new VeredictoLeido(
            Bool(v, "correcta"), Bool(v, "pendiente") == true, Numero(v, "puntaje"), Numero(v, "puntaje_maximo"), Bool(v, "requiere_correccion_manual") == true);
    }

    public static double? Numero(JsonElement v, string clave) =>
        v.ValueKind == JsonValueKind.Object && v.TryGetProperty(clave, out var n) && n.ValueKind == JsonValueKind.Number ? n.GetDouble() : null;

    public static bool? Bool(JsonElement v, string clave) =>
        v.ValueKind == JsonValueKind.Object && v.TryGetProperty(clave, out var b) && b.ValueKind is JsonValueKind.True or JsonValueKind.False ? b.GetBoolean() : null;
}

/// <summary>El puntaje que el profesor puso a mano a un reactivo que la biblioteca no califica sola.</summary>
internal sealed record PuntajeDelProfesor(double? Puntaje, string? Comentario, string? RevisadaPor, long? RevisadaEn)
{
    public static PuntajeDelProfesor? De(JsonElement? json)
    {
        if (json is not { ValueKind: JsonValueKind.Object } r) return null;
        var por = r.TryGetProperty("revisada_por", out var p) && p.ValueKind == JsonValueKind.String ? p.GetString() : null;
        var en = r.TryGetProperty("revisada_en", out var e) && e.ValueKind == JsonValueKind.Number && e.TryGetInt64(out var n) ? n : (long?)null;
        var comentario = r.TryGetProperty("comentario", out var c) && c.ValueKind == JsonValueKind.String ? c.GetString() : null;
        return new PuntajeDelProfesor(VeredictoLeido.Numero(r, "puntaje"), comentario, por, en);
    }
}

/// <summary>
/// La respuesta de un alumno en palabras, para que el profesor la lea al revisar (sin teclado, sin JSON a la vista). Cada tipo de pregunta de la biblioteca guarda su
/// respuesta con su propia forma (<c>selectedOptionIds</c>, <c>value</c>, <c>blanks</c>, <c>order</c>, <c>pairs</c>, <c>text</c>); aquí se traducen usando la pregunta tal como
/// la vio el alumno.
/// </summary>
internal static class RespuestaLegible
{
    private static readonly CultureInfo Es = CultureInfo.GetCultureInfo("es-CO");
    public const string SinRespuesta = "No respondió";

    public static string De(PreguntaAula pregunta, JsonElement? respuesta, bool respondida)
    {
        if (!respondida || respuesta is not { ValueKind: JsonValueKind.Object } r) return SinRespuesta;
        try
        {
            switch (pregunta.Tipo)
            {
                case "multiple_choice":
                {
                    var ids = Lista(r, "selectedOptionIds");
                    var textos = ids.Select(id => pregunta.Opciones?.FirstOrDefault(o => o.OpcionRef == id)?.Texto ?? id).ToList();
                    return textos.Count == 0 ? SinRespuesta : string.Join(", ", textos);
                }
                case "true_false":
                    return r.TryGetProperty("value", out var v) && v.ValueKind is JsonValueKind.True or JsonValueKind.False ? (v.GetBoolean() ? "Verdadero" : "Falso") : SinRespuesta;
                case "fill_blanks":
                {
                    if (!r.TryGetProperty("blanks", out var blanks) || blanks.ValueKind != JsonValueKind.Object) return SinRespuesta;
                    var texto = pregunta.Plantilla ?? string.Empty;
                    var valores = new List<string>();
                    foreach (var campo in blanks.EnumerateObject())
                    {
                        var valor = campo.Value.ValueKind == JsonValueKind.String ? campo.Value.GetString() ?? string.Empty : campo.Value.ToString();
                        valores.Add(valor);
                        texto = texto.Replace("{{" + campo.Name + "}}", $"[{valor}]");
                    }
                    return string.IsNullOrWhiteSpace(pregunta.Plantilla) ? string.Join("; ", valores) : texto;
                }
                case "ordering":
                {
                    var orden = Lista(r, "order");
                    if (orden.Count == 0) return SinRespuesta;
                    return string.Join("  →  ", orden.Select(id => pregunta.Elementos?.FirstOrDefault(e => e.Ref == id)?.Texto ?? id));
                }
                case "matching":
                {
                    if (!r.TryGetProperty("pairs", out var pares) || pares.ValueKind != JsonValueKind.Array || pares.GetArrayLength() == 0) return SinRespuesta;
                    var lineas = new List<string>();
                    foreach (var par in pares.EnumerateArray())
                    {
                        var izq = Texto(par, "leftId");
                        var der = Texto(par, "rightId");
                        lineas.Add($"{pregunta.Izquierda?.FirstOrDefault(e => e.Ref == izq)?.Texto ?? izq}  ↔  {pregunta.Derecha?.FirstOrDefault(e => e.Ref == der)?.Texto ?? der}");
                    }
                    return string.Join("\n", lineas);
                }
                case "open":
                {
                    if (r.TryGetProperty("text", out var t) && t.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(t.GetString())) return t.GetString()!;
                    return pregunta.FormatoRespuesta switch
                    {
                        "drawing" => "Respondió con un dibujo (no se muestra aquí)",
                        "audio" => "Respondió con un audio (no se muestra aquí)",
                        _ => SinRespuesta,
                    };
                }
            }
        }
        catch (Exception ex) when (ex is InvalidOperationException or FormatException) { /* una forma inesperada cae al texto de abajo */ }
        return "Respondió (la forma de la respuesta no se puede mostrar aquí)";
    }

    private static List<string> Lista(JsonElement r, string clave) =>
        r.TryGetProperty(clave, out var a) && a.ValueKind == JsonValueKind.Array
            ? a.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!).ToList()
            : [];

    private static string Texto(JsonElement e, string clave) =>
        e.ValueKind == JsonValueKind.Object && e.TryGetProperty(clave, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? string.Empty : string.Empty;

    /// <summary>«1,5» o «2»: puntos sin ceros de sobra.</summary>
    public static string Puntos(double? valor) => valor is null ? "—" : valor.Value.ToString("0.##", Es);
}

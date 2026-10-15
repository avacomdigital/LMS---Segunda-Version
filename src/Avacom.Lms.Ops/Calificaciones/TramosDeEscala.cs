using System.Globalization;
using System.Text.Json;

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>Un nivel de desempeño de una escala (un tramo): su clave, lo que se lee y su orden.</summary>
internal sealed record TramoDeEscala(string Clave, string Etiqueta, int Orden);

/// <summary>
/// Lo que la pantalla lee de la definición de una escala (<c>definicion</c>, tal como la guarda el nodo; los números viajan como TEXTO para que la huella no dependa
/// de un decimal). Sólo se LEEN los tramos para ofrecer la valoración del desempeño y un resumen para la vista previa: ninguna conversión ocurre aquí. Sin MAUI.
/// </summary>
internal static class TramosDeEscala
{
    /// <summary>Los tramos de la definición, en su orden. Vacío si no se pueden leer.</summary>
    public static IReadOnlyList<TramoDeEscala> Leer(JsonElement? definicion)
    {
        if (definicion is not { ValueKind: JsonValueKind.Object } d || !d.TryGetProperty("tramos", out var tramos) || tramos.ValueKind != JsonValueKind.Array) return [];
        var lista = new List<TramoDeEscala>();
        var posicion = 0;
        foreach (var t in tramos.EnumerateArray())
        {
            posicion++;
            if (t.ValueKind != JsonValueKind.Object) continue;
            var clave = Texto(t, "clave");
            if (clave.Length == 0) continue;
            var etiqueta = Texto(t, "etiqueta");
            var orden = t.TryGetProperty("orden", out var o) && o.ValueKind == JsonValueKind.Number && o.TryGetInt32(out var n) ? n : posicion;
            lista.Add(new TramoDeEscala(clave, etiqueta.Length == 0 ? clave : etiqueta, orden));
        }
        return lista.OrderBy(t => t.Orden).ToList();
    }

    public static string TipoLegible(string? tipo) => tipo switch
    {
        "numerica" => "Numérica",
        "alfabetica" => "Alfabética",
        "cualitativa" => "Cualitativa",
        "competencias" => "Por competencias",
        _ => tipo ?? "—",
    };

    /// <summary>«De 1 a 5 · aprueba desde 3»: el rango y el mínimo de aprobación de una escala numérica, tal como los guarda la definición. Nulo si no hay nada que decir.</summary>
    public static string? Rango(JsonElement? definicion)
    {
        if (definicion is not { ValueKind: JsonValueKind.Object } d) return null;
        var min = Texto(d, "valor_min");
        var max = Texto(d, "valor_max");
        var aprobacion = Texto(d, "aprobacion_minima");
        var partes = new List<string>();
        if (min.Length > 0 && max.Length > 0) partes.Add($"de {Formato(min)} a {Formato(max)}");
        if (aprobacion.Length > 0) partes.Add($"el criterio de aprobación empieza en {Formato(aprobacion)}");
        return partes.Count == 0 ? null : string.Join(" · ", partes);
    }

    private static string Formato(string numero) => decimal.TryParse(numero, NumberStyles.Number, CultureInfo.InvariantCulture, out var v) ? v.ToString("0.##", new CultureInfo("es-CO")) : numero;

    private static string Texto(JsonElement e, string clave) =>
        e.TryGetProperty(clave, out var v) ? v.ValueKind switch { JsonValueKind.String => v.GetString() ?? string.Empty, JsonValueKind.Number => v.ToString(), _ => string.Empty } : string.Empty;
}

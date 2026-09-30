using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Avacom.Lms.Core.Estudio;

/// <summary>
/// El JSON canónico con el que el nodo firma el manifiesto de un paquete (contrato §4.4): claves ordenadas de forma recursiva, sin espacios y
/// en UTF-8; la <c>huella</c> es el SHA-256 hexadecimal de ese texto SIN el campo <c>huella</c> de la raíz.
///
/// Se calcula sobre el JSON crudo que llegó —nunca sobre un DTO— y no reserializa nada con el escritor de JSON de .NET (que escapa distinto que
/// Python): las cadenas se escriben con las reglas de <c>json.dumps</c> (sólo <c>"</c>, <c>\</c> y los caracteres de control se escapan; lo demás
/// va tal cual en UTF-8) y los números con el texto que tenían. Las claves se ordenan por punto de código Unicode, como <c>sort_keys=True</c>.
///
/// Por si el nodo firma con el <c>json.dumps</c> por defecto de Python (<c>ensure_ascii=True</c>, todo lo que no es ASCII como <c>\uXXXX</c>),
/// <see cref="CoincideConHuella"/> acepta también esa codificación del mismo texto canónico: son dos escrituras del MISMO contenido, así que
/// aceptar cualquiera de las dos no debilita la verificación de integridad.
/// </summary>
public static class JsonCanonico
{
    /// <summary>El texto canónico de un valor JSON. <paramref name="sinPropiedadRaiz"/> omite esa propiedad de la raíz (<c>huella</c>).</summary>
    public static string Canonico(JsonElement raiz, bool soloAscii = false, string? sinPropiedadRaiz = null)
    {
        var texto = new StringBuilder();
        Escribir(raiz, texto, soloAscii, sinPropiedadRaiz);
        return texto.ToString();
    }

    /// <summary>El SHA-256 hexadecimal (minúsculas) del texto canónico, en UTF-8.</summary>
    public static string Sha256(JsonElement raiz, bool soloAscii = false, string? sinPropiedadRaiz = null) =>
        Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(Canonico(raiz, soloAscii, sinPropiedadRaiz))));

    /// <summary>¿La huella declarada es la del manifiesto sin su campo <c>huella</c>? Compara sin distinguir mayúsculas y prueba las dos codificaciones.</summary>
    public static bool CoincideConHuella(JsonElement manifiesto, string huellaDeclarada)
    {
        if (string.IsNullOrWhiteSpace(huellaDeclarada) || manifiesto.ValueKind != JsonValueKind.Object) return false;
        var declarada = huellaDeclarada.Trim();
        return string.Equals(Sha256(manifiesto, soloAscii: false, "huella"), declarada, StringComparison.OrdinalIgnoreCase)
            || string.Equals(Sha256(manifiesto, soloAscii: true, "huella"), declarada, StringComparison.OrdinalIgnoreCase);
    }

    private static void Escribir(JsonElement valor, StringBuilder texto, bool soloAscii, string? omitir)
    {
        switch (valor.ValueKind)
        {
            case JsonValueKind.Object:
                var propiedades = new List<(string Nombre, JsonElement Valor)>();
                foreach (var p in valor.EnumerateObject())
                    if (omitir is null || p.Name != omitir) propiedades.Add((p.Name, p.Value));
                propiedades.Sort((a, b) => CompararPorPuntoDeCodigo(a.Nombre, b.Nombre));
                texto.Append('{');
                for (var i = 0; i < propiedades.Count; i++)
                {
                    if (i > 0) texto.Append(',');
                    Cadena(texto, propiedades[i].Nombre, soloAscii);
                    texto.Append(':');
                    Escribir(propiedades[i].Valor, texto, soloAscii, omitir: null);   // sólo la raíz omite una propiedad
                }
                texto.Append('}');
                break;
            case JsonValueKind.Array:
                texto.Append('[');
                var primero = true;
                foreach (var elemento in valor.EnumerateArray())
                {
                    if (!primero) texto.Append(',');
                    primero = false;
                    Escribir(elemento, texto, soloAscii, omitir: null);
                }
                texto.Append(']');
                break;
            case JsonValueKind.String:
                Cadena(texto, valor.GetString()!, soloAscii);
                break;
            case JsonValueKind.Number:
                texto.Append(valor.GetRawText());
                break;
            case JsonValueKind.True:
                texto.Append("true");
                break;
            case JsonValueKind.False:
                texto.Append("false");
                break;
            case JsonValueKind.Null:
                texto.Append("null");
                break;
            default:
                throw new InvalidOperationException("Valor JSON no válido para canonizar.");
        }
    }

    /// <summary>Una cadena como la escribe <c>json.dumps</c>: sin <c>ensure_ascii</c> sólo se escapan <c>"</c>, <c>\</c> y los controles (&lt; U+0020).</summary>
    private static void Cadena(StringBuilder texto, string valor, bool soloAscii)
    {
        texto.Append('"');
        foreach (var c in valor)
        {
            switch (c)
            {
                case '"': texto.Append("\\\""); break;
                case '\\': texto.Append("\\\\"); break;
                case '\n': texto.Append("\\n"); break;
                case '\r': texto.Append("\\r"); break;
                case '\t': texto.Append("\\t"); break;
                case '\b': texto.Append("\\b"); break;
                case '\f': texto.Append("\\f"); break;
                default:
                    if (c < 0x20 || (soloAscii && c > 0x7E)) texto.Append("\\u").Append(((int)c).ToString("x4"));
                    else texto.Append(c);
                    break;
            }
        }
        texto.Append('"');
    }

    /// <summary>Orden por punto de código Unicode (igual al orden de los bytes UTF-8): el de <c>sort_keys=True</c> de Python.</summary>
    private static int CompararPorPuntoDeCodigo(string a, string b)
    {
        var ea = a.EnumerateRunes().GetEnumerator();
        var eb = b.EnumerateRunes().GetEnumerator();
        while (true)
        {
            var hayA = ea.MoveNext();
            var hayB = eb.MoveNext();
            if (!hayA || !hayB) return hayA == hayB ? 0 : hayA ? 1 : -1;
            var comparacion = ea.Current.Value.CompareTo(eb.Current.Value);
            if (comparacion != 0) return comparacion;
        }
    }
}

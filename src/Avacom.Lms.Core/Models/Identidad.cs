using System.Globalization;
using System.Text;

namespace Avacom.Lms.Core.Models;

/// <summary>
/// Identidad lógica de la persona en el expediente. El prototipo no tiene
/// autenticación (Q-04): el identificador externo se deriva del nombre con el que
/// la persona entra al aula, de forma estable y sin acentos ni espacios.
/// </summary>
public static class Identidad
{
    public static string SlugDe(string nombre)
    {
        var normalizado = (nombre ?? string.Empty).Trim().Normalize(NormalizationForm.FormD);
        var sb = new StringBuilder();
        var guion = false;
        foreach (var c in normalizado)
        {
            var categoria = CharUnicodeInfo.GetUnicodeCategory(c);
            if (categoria == UnicodeCategory.NonSpacingMark) continue;
            if (char.IsLetterOrDigit(c))
            {
                sb.Append(char.ToLowerInvariant(c));
                guion = false;
            }
            else if (!guion && sb.Length > 0)
            {
                sb.Append('-');
                guion = true;
            }
        }
        var slug = sb.ToString().TrimEnd('-');
        return string.IsNullOrEmpty(slug) ? "anonimo" : slug;
    }

    public static string InicialesDe(string nombre)
    {
        var partes = (nombre ?? string.Empty).Split(' ', StringSplitOptions.RemoveEmptyEntries);
        return partes.Length == 0 ? "?" : string.Concat(partes.Take(2).Select(p => char.ToUpperInvariant(p[0])));
    }

    /// <summary>
    /// Un código corto y propio de ESTA instalación de la app (ocho dígitos hexadecimales al azar). El nombre del aparato no basta para
    /// distinguir tabletas: 35 del mismo modelo traen el mismo nombre de fábrica y el nodo las vería como una sola (presencia, bloqueo
    /// por tableta y registro en Dispositivos se pisarían). Quien lo guarda es la app (<c>Preferences</c>); aquí sólo se fabrica.
    /// </summary>
    public static string NuevaInstalacion() => Guid.NewGuid().ToString("N")[..8];

    /// <summary>La huella con la que el nodo reconoce a una tableta: la app, el nombre del aparato y el código de su instalación.</summary>
    public static string HuellaDeTableta(string? nombreDelAparato, string instalacion) =>
        $"student-{(string.IsNullOrWhiteSpace(nombreDelAparato) ? "tableta" : nombreDelAparato.Trim())}-{instalacion}";

    private static readonly System.Text.RegularExpressions.Regex HuellaConocida =
        new(@"^(?:ops|student)-(?<nombre>.+?)(?:-[0-9a-f]{8})?$", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.CultureInvariant);

    /// <summary>
    /// El equipo de una huella para leerlo dentro de una frase: sin el prefijo interno de la app («ops-», «student-») y sin el código de
    /// instalación. Vacío si no hay huella. Una cadena que no tiene la forma de una huella se devuelve tal cual.
    /// </summary>
    public static string EquipoLegible(string? dispositivo)
    {
        if (string.IsNullOrWhiteSpace(dispositivo)) return string.Empty;
        var m = HuellaConocida.Match(dispositivo.Trim());
        return m.Success && m.Groups["nombre"].Length > 0 ? m.Groups["nombre"].Value : dispositivo.Trim();
    }
}

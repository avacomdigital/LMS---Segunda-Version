using System.Text.Json;

namespace Avacom.Ops.Host;

/// <summary>
/// Lo que el instalador dejo escrito en manifiesto.json, junto al programa.
///
/// La politica de datos es un dato de cada version y no logica cableada:
///
///   reemplazables  la base todavia es desechable. Se conserva si migra bien y
///                  solo se reemplaza (dejando antes la copia) si no migra.
///   protegidos     la base nunca se reemplaza. La copia previa es obligatoria y
///                  una migracion que falla restaura la copia y se detiene.
///
/// Pasar a protegidos cuando exista el modulo de progreso y calificaciones es
/// cambiar ese valor al compilar (Build-Installer.ps1 -PoliticaDatos).
/// </summary>
internal static class Manifiesto
{
    public const string Reemplazables = "reemplazables";
    public const string Protegidos = "protegidos";

    public static string PoliticaDeDatos()
    {
        var valor = Leer("politica_datos");
        // Ante la duda (manifiesto ausente o ilegible) se protege: perder
        // datos por un manifiesto roto es peor que detener una actualizacion.
        return string.Equals(valor, Reemplazables, StringComparison.OrdinalIgnoreCase) ? Reemplazables : Protegidos;
    }

    public static string Version() => Leer("version") ?? "desconocida";

    private static string? Leer(string clave)
    {
        try
        {
            if (!File.Exists(Rutas.ArchivoManifiesto)) return null;
            using var documento = JsonDocument.Parse(File.ReadAllText(Rutas.ArchivoManifiesto));
            return documento.RootElement.TryGetProperty(clave, out var propiedad) ? propiedad.GetString() : null;
        }
        catch (Exception error) when (error is IOException or JsonException or InvalidOperationException)
        {
            return null;
        }
    }
}

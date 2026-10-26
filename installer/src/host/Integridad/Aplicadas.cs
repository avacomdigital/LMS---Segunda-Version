using System.Text.Json;
using Avacom.Ops.Host.Actualizacion;

namespace Avacom.Ops.Host.Integridad;

/// <summary>
/// Los archivos que un paquete de actualizacion FIRMADO (MOD-017) cambio despues de la instalacion. Sin esto, la primera actualizacion legitima haria saltar la alarma de integridad.
///
/// Lo escribe el Host al terminar una orden con exito, con las huellas que el paquete firmado declaro y el Host ya comprobo al copiar (no recalcula nada del disco: si lo hiciera, daria por buena
/// una alteracion hecha antes de actualizar). Una reversion exitosa retira las entradas de ese paquete. Vive en Actualizaciones\integridad-aplicada.json, la carpeta que solo SYSTEM y los
/// administradores escriben.
/// </summary>
internal static class Aplicadas
{
    public const string Archivo = "integridad-aplicada.json";

    public static string Ruta(string carpetaActualizaciones) => Path.Combine(carpetaActualizaciones, Archivo);

    /// <summary>{ruta → SHA-256} con los paquetes en el orden en que se aplicaron (el ultimo manda). Un archivo ilegible vale como vacio: la alarma es mas ruidosa, no menos.</summary>
    public static IReadOnlyDictionary<string, string> Leer(string carpetaActualizaciones)
    {
        var salida = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var paquete in Paquetes(carpetaActualizaciones))
            foreach (var (ruta, sha) in paquete.Archivos) salida[ruta] = sha;
        return salida;
    }

    public static void RegistrarAplicado(Orden orden) => RegistrarAplicado(Rutas.CarpetaActualizaciones, orden.PaqueteId, orden.Archivos.Select(a => (a.Ruta, a.Sha256)));

    public static void RegistrarRevertido(Orden orden) => RegistrarRevertido(Rutas.CarpetaActualizaciones, orden.PaqueteId);

    internal static void RegistrarAplicado(string carpeta, string paqueteId, IEnumerable<(string Ruta, string Sha256)> archivos)
    {
        var paquetes = Paquetes(carpeta).Where(p => p.Id != paqueteId).ToList();
        paquetes.Add(new Paquete(paqueteId, archivos.Select(a => ("Backend/" + a.Ruta.Replace('\\', '/').TrimStart('/'), a.Sha256.ToLowerInvariant())).ToList()));
        Guardar(carpeta, paquetes);
    }

    internal static void RegistrarRevertido(string carpeta, string paqueteId) =>
        Guardar(carpeta, Paquetes(carpeta).Where(p => p.Id != paqueteId).ToList());

    private sealed record Paquete(string Id, IReadOnlyList<(string Ruta, string Sha256)> Archivos);

    private static List<Paquete> Paquetes(string carpeta)
    {
        var lista = new List<Paquete>();
        try
        {
            var ruta = Ruta(carpeta);
            if (!File.Exists(ruta)) return lista;
            using var doc = JsonDocument.Parse(File.ReadAllText(ruta));
            foreach (var p in doc.RootElement.GetProperty("paquetes").EnumerateArray())
            {
                var archivos = p.GetProperty("archivos").EnumerateArray().Select(a => (a[0].GetString()!, a[1].GetString()!)).ToList();
                lista.Add(new Paquete(p.GetProperty("id").GetString()!, archivos));
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or JsonException or KeyNotFoundException or InvalidOperationException or NullReferenceException)
        {
            return [];
        }
        return lista;
    }

    private static void Guardar(string carpeta, List<Paquete> paquetes)
    {
        try
        {
            var cuerpo = new { version = 1, paquetes = paquetes.Select(p => new { id = p.Id, archivos = p.Archivos.Select(a => new[] { a.Ruta, a.Sha256 }) }) };
            Disco.EscribirAtomico(Ruta(carpeta), JsonSerializer.Serialize(cuerpo));
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            // Sin poder anotarlo, la siguiente verificacion lo vera como una diferencia: es la direccion segura del error.
        }
    }
}

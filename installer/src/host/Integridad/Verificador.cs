using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Avacom.Ops.Host.Actualizacion;
using Org.BouncyCastle.Math.EC.Rfc8032;

namespace Avacom.Ops.Host.Integridad;

/// <summary>Un grupo de diferencias del mismo tipo: «modificado», «falta» o «sobra» dentro de una parte del paquete (backend, runtime, app, nativo, manifiesto o firma).</summary>
internal sealed record Hallazgo(string Tipo, string Detalle, int Cantidad, IReadOnlyList<string> Ejemplos);

/// <summary>
/// Lo que concluyo la verificacion del despliegue. Estado:
///   ok              todo coincide con lo que firmo el instalador.
///   alterada        algo no coincide (o la firma no valida): hay HALLAZGOS. El nodo arranca igual: es evidencia, no prevencion.
///   sin_firma       este paquete se compilo sin llave de publicacion (un desarrollo): se comprobaron las huellas, no la firma.
///   no_verificable  el paquete no trae la lista de integridad (una version anterior a la 2.16.0): no hay nada que comprobar.
/// </summary>
internal sealed record ResultadoDeIntegridad(string Estado, string Firma, string? Kid, string VersionDelProducto, int ArchivosComprobados, IReadOnlyList<Hallazgo> Hallazgos);

/// <summary>
/// MOD-018 (P-23): la verificacion de integridad del despliegue, al arrancar el servicio.
///
/// Cadena de confianza (de afuera hacia adentro):
///   llaves publicas de publicacion (incrustadas en ESTE ejecutable al compilarlo)
///     → manifiesto.firma.json (Ed25519 sobre los bytes EXACTOS de manifiesto.json)
///       → manifiesto.json (trae el SHA-256 de integridad.json)
///         → integridad.json (la lista «ruta · SHA-256» de Backend, Runtime, App y la DLL nativa)
///           → cada archivo del disco.
///
/// Lo que NO es: prevencion. Este ejecutable tambien es un archivo que quien administra el equipo puede parchear (y con el, las llaves que lleva dentro). Es EVIDENCIA: deja un asiento
/// en servicio.log y una señal que el backend convierte en un aviso y un asiento de bitacora. Una diferencia nunca impide arrancar (un antivirus o un parche de campo no pueden dejar
/// un aula sin clase).
///
/// Las actualizaciones legitimas (MOD-017) no son diferencias: el Host anota los archivos que un paquete firmado cambio (<see cref="Aplicadas"/>) y esos valen en lugar de la lista original.
/// </summary>
internal static class Verificador
{
    public const string ArchivoDeLista = "integridad.json";
    public const string ArchivoDeFirma = "manifiesto.firma.json";
    private const int MaximoDeEjemplos = 8;

    // Extensiones de lo que se EJECUTA: un archivo de estos tipos que no esta en la lista «sobra» (alguien lo agrego).
    private static readonly string[] Ejecutables = [".py", ".pyd", ".dll", ".exe", ".pth", ".so", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".wsf", ".scr"];
    private static readonly string[] CarpetasIgnoradas = ["__pycache__"];

    /// <summary>Las llaves publicas de publicacion que este ejecutable lleva incrustadas («kid:hex|kid:hex»: la coma y el punto y coma separan propiedades de MSBuild). Vacio en una compilacion de desarrollo.</summary>
    public static IReadOnlyDictionary<string, byte[]> LlavesIncrustadas()
    {
        var texto = Assembly.GetExecutingAssembly().GetCustomAttributes<AssemblyMetadataAttribute>()
            .FirstOrDefault(a => a.Key == "ClavesDePublicacion")?.Value;
        return AnalizarLlaves(texto);
    }

    public static IReadOnlyDictionary<string, byte[]> AnalizarLlaves(string? texto)
    {
        var llaves = new Dictionary<string, byte[]>(StringComparer.Ordinal);
        foreach (var par in (texto ?? "").Split('|', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            var partes = par.Split(':', 2);
            if (partes.Length != 2 || partes[0].Length is 0 or > 32) continue;
            try
            {
                var bytes = Convert.FromHexString(partes[1]);
                if (bytes.Length == 32) llaves[partes[0]] = bytes;
            }
            catch (FormatException) { /* una entrada mal formada no cuenta */ }
        }
        return llaves;
    }

    public static ResultadoDeIntegridad Verificar() =>
        Verificar(Rutas.RaizInstalacion, LlavesIncrustadas(), Aplicadas.Leer(Rutas.CarpetaActualizaciones));

    /// <summary>La verificacion sobre una carpeta de instalacion cualquiera (la usan las pruebas y el verbo verificar-integridad).</summary>
    public static ResultadoDeIntegridad Verificar(string raiz, IReadOnlyDictionary<string, byte[]> llaves, IReadOnlyDictionary<string, string> aplicadas)
    {
        var hallazgos = new List<(string Tipo, string Detalle, string Ruta)>();
        var rutaManifiesto = Path.Combine(raiz, "manifiesto.json");
        var rutaLista = Path.Combine(raiz, ArchivoDeLista);
        var rutaFirma = Path.Combine(raiz, ArchivoDeFirma);

        byte[]? manifiesto = LeerOrNull(rutaManifiesto);
        var version = "desconocida";
        string? shaDeLista = null;
        if (manifiesto is not null)
        {
            try
            {
                using var doc = Parsear(manifiesto);
                if (doc.RootElement.TryGetProperty("version", out var v) && v.ValueKind == JsonValueKind.String) version = v.GetString() ?? version;
                if (doc.RootElement.TryGetProperty("integridad", out var i) && i.ValueKind == JsonValueKind.Object
                    && i.TryGetProperty("sha256", out var s) && s.ValueKind == JsonValueKind.String)
                    shaDeLista = s.GetString()?.ToLowerInvariant();
            }
            catch (JsonException) { hallazgos.Add(("manifiesto", "ilegible", "manifiesto.json")); }
        }

        // ---- 1. la firma del manifiesto
        var firma = "sin_llave";
        string? kid = null;
        if (llaves.Count > 0)
        {
            (firma, kid) = ComprobarFirma(manifiesto, LeerOrNull(rutaFirma), llaves);
            if (firma != "ok") hallazgos.Add(("firma", firma, ArchivoDeFirma));
        }

        // ---- 2. la lista de integridad contra el manifiesto
        var lista = LeerOrNull(rutaLista);
        if (manifiesto is null)
            return Terminar(llaves.Count > 0 ? "alterada" : "no_verificable", firma, kid, version, 0, llaves.Count > 0 ? [("manifiesto", "falta", "manifiesto.json")] : []);
        if (shaDeLista is null)
        {
            // Un paquete anterior a la 2.16.0 no trae lista: no hay nada que comprobar. Si la firma fallo, ya hay un hallazgo que contar.
            return Terminar(hallazgos.Count > 0 ? "alterada" : "no_verificable", firma, kid, version, 0, hallazgos);
        }
        if (lista is null)
        {
            hallazgos.Add(("manifiesto", "falta", ArchivoDeLista));
            return Terminar("alterada", firma, kid, version, 0, hallazgos);
        }
        if (shaDeLista is not null && !string.Equals(Convert.ToHexString(SHA256.HashData(lista)), shaDeLista, StringComparison.OrdinalIgnoreCase))
        {
            hallazgos.Add(("manifiesto", "lista_alterada", ArchivoDeLista));
            // Una lista que no es la que firmo el instalador no sirve de referencia: no se acusa a los archivos por ella.
            return Terminar("alterada", firma, kid, version, 0, hallazgos);
        }

        Dictionary<string, string> esperado;
        try { esperado = LeerLista(lista); }
        catch (Exception error) when (error is JsonException or InvalidOperationException or FormatException)
        {
            hallazgos.Add(("manifiesto", "ilegible", ArchivoDeLista));
            return Terminar("alterada", firma, kid, version, 0, hallazgos);
        }

        // ---- 3. cada archivo del disco
        foreach (var (ruta, sha) in aplicadas) esperado[ruta] = sha;          // lo que un paquete firmado cambio vale en lugar de lo original
        var comprobados = 0;
        foreach (var (ruta, sha) in esperado.OrderBy(p => p.Key, StringComparer.Ordinal))
        {
            string completa;
            try { completa = Disco.Confinar(raiz, ruta); }
            catch (IOException) { hallazgos.Add((TipoDe(ruta), "ruta_invalida", ruta)); continue; }
            comprobados++;
            if (!File.Exists(completa)) { hallazgos.Add((TipoDe(ruta), "falta", ruta)); continue; }
            try
            {
                if (!string.Equals(Disco.Sha256DeArchivo(completa), sha, StringComparison.OrdinalIgnoreCase))
                    hallazgos.Add((TipoDe(ruta), "modificado", ruta));
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
                // Un archivo que no se pudo leer (un antivirus lo tiene tomado) no es evidencia de nada: se deja pasar.
            }
        }

        // ---- 4. lo que se agrego
        foreach (var carpeta in new[] { "Backend", "Runtime", "App" })
        {
            var baseDeLaCarpeta = Path.Combine(raiz, carpeta);
            if (!Directory.Exists(baseDeLaCarpeta)) continue;
            foreach (var archivo in Recorrer(baseDeLaCarpeta))
            {
                var ruta = carpeta + "/" + Path.GetRelativePath(baseDeLaCarpeta, archivo).Replace('\\', '/');
                if (esperado.ContainsKey(ruta) || !Ejecutables.Contains(Path.GetExtension(ruta).ToLowerInvariant())) continue;
                if (carpeta == "App" && !ruta.StartsWith("App/Avacom.Lms.", StringComparison.OrdinalIgnoreCase) && !ruta.Contains("avacom_lic", StringComparison.OrdinalIgnoreCase)) continue;   // App\ trae cientos de DLL de terceros: de ella solo se vigilan las propias
                hallazgos.Add((TipoDe(ruta), "sobra", ruta));
            }
        }

        return Terminar(hallazgos.Count > 0 ? "alterada" : llaves.Count > 0 ? "ok" : "sin_firma", firma, kid, version, comprobados, hallazgos);
    }

    private static ResultadoDeIntegridad Terminar(string estado, string firma, string? kid, string version, int comprobados, IEnumerable<(string Tipo, string Detalle, string Ruta)> hallazgos)
    {
        var grupos = hallazgos
            .GroupBy(h => (h.Tipo, h.Detalle))
            .Select(g => new Hallazgo(g.Key.Tipo, g.Key.Detalle, g.Count(), g.Select(h => h.Ruta).OrderBy(r => r, StringComparer.Ordinal).Take(MaximoDeEjemplos).ToList()))
            .OrderBy(g => g.Tipo, StringComparer.Ordinal).ThenBy(g => g.Detalle, StringComparer.Ordinal)
            .ToList();
        // Sin llaves y con diferencias, la lista no esta firmada: aun asi es evidencia, y se declara alterada.
        return new ResultadoDeIntegridad(estado, firma, kid, version, comprobados, grupos);
    }

    /// <summary>La firma de manifiesto.json: devuelve «ok», «ausente», «ilegible», «kid_desconocido» o «invalida», y con cual llave se verifico.</summary>
    internal static (string Resultado, string? Kid) ComprobarFirma(byte[]? manifiesto, byte[]? archivoDeFirma, IReadOnlyDictionary<string, byte[]> llaves)
    {
        if (manifiesto is null || archivoDeFirma is null) return ("ausente", null);
        string? kid;
        byte[] firma;
        try
        {
            using var doc = Parsear(archivoDeFirma);
            kid = doc.RootElement.GetProperty("kid").GetString();
            firma = Convert.FromBase64String(doc.RootElement.GetProperty("firma").GetString() ?? "");
        }
        catch (Exception error) when (error is JsonException or KeyNotFoundException or FormatException or InvalidOperationException)
        {
            return ("ilegible", null);
        }
        if (kid is null || !llaves.TryGetValue(kid, out var publica)) return ("kid_desconocido", kid);
        if (firma.Length != 64) return ("invalida", kid);
        try
        {
            return (Ed25519.Verify(firma, 0, publica, 0, manifiesto, 0, manifiesto.Length) ? "ok" : "invalida", kid);
        }
        catch (Exception error) when (error is ArgumentException or InvalidOperationException)
        {
            return ("invalida", kid);
        }
    }

    /// <summary>{"archivos": [["Backend/manage.py", "sha256"], ...]} → {ruta: sha256}. Una ruta repetida o un hash que no es de 64 hexadecimales invalida la lista.</summary>
    internal static Dictionary<string, string> LeerLista(byte[] lista)
    {
        var salida = new Dictionary<string, string>(StringComparer.Ordinal);
        using var doc = Parsear(lista);
        foreach (var par in doc.RootElement.GetProperty("archivos").EnumerateArray())
        {
            var ruta = par[0].GetString() ?? throw new FormatException("ruta vacia");
            var sha = (par[1].GetString() ?? "").ToLowerInvariant();
            if (sha.Length != 64 || !sha.All(Uri.IsHexDigit)) throw new FormatException("hash invalido");
            if (!salida.TryAdd(ruta, sha)) throw new FormatException("ruta repetida");
        }
        return salida;
    }

    private static IEnumerable<string> Recorrer(string carpeta)
    {
        var pila = new Stack<string>();
        pila.Push(carpeta);
        while (pila.Count > 0)
        {
            var actual = pila.Pop();
            string[] archivos, subcarpetas;
            try
            {
                archivos = Directory.GetFiles(actual);
                subcarpetas = Directory.GetDirectories(actual);
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException) { continue; }
            foreach (var a in archivos) yield return a;
            foreach (var s in subcarpetas)
                if (!CarpetasIgnoradas.Contains(Path.GetFileName(s), StringComparer.OrdinalIgnoreCase)) pila.Push(s);
        }
    }

    internal static string TipoDe(string ruta)
    {
        var nombre = ruta.Substring(ruta.LastIndexOf('/') + 1);
        if (nombre.StartsWith("avacom_lic", StringComparison.OrdinalIgnoreCase) || nombre.StartsWith("libavacom_lic", StringComparison.OrdinalIgnoreCase)) return "nativo";
        if (ruta.StartsWith("Backend/", StringComparison.Ordinal)) return "backend";
        if (ruta.StartsWith("Runtime/", StringComparison.Ordinal)) return "runtime";
        if (ruta.StartsWith("App/", StringComparison.Ordinal)) return "app";
        return "otro";
    }

    /// <summary>Un JSON de bytes, con o sin la marca de orden de bytes UTF-8 (Windows PowerShell 5.1 la pone al escribir con -Encoding utf8).</summary>
    private static JsonDocument Parsear(byte[] bytes) =>
        JsonDocument.Parse(bytes.AsMemory(bytes.Length >= 3 && bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF ? 3 : 0));

    private static byte[]? LeerOrNull(string ruta)
    {
        try { return File.Exists(ruta) ? File.ReadAllBytes(ruta) : null; }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException) { return null; }
    }
}

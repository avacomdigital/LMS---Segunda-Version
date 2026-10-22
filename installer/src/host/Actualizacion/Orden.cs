using System.Text.Json;
using System.Text.RegularExpressions;

namespace Avacom.Ops.Host.Actualizacion;

/// <summary>La orden no se puede obedecer (forma invalida, ruta fuera de su sitio): el host no toca nada.</summary>
internal sealed class OrdenInvalida(string motivo) : Exception(motivo);

internal sealed record ArchivoDeOrden(string Ruta, long Bytes, string Sha256);

internal sealed record MigracionDeOrden(string Nombre, string Reverso);

internal sealed record ModuloDeOrden(string Nombre, IReadOnlyList<MigracionDeOrden> Migraciones);

/// <summary>
/// La orden que el backend deja en Actualizaciones\orden.json (MOD-017, P-06): que paquete, que accion y que archivos. Contrato en spec-driven/17-update-manager/02-api.md §3.
///
/// El host la obedece con el servicio parado y como SYSTEM, asi que NO se fia de ella: la forma, cada ruta (relativa a Backend\, dentro de las apps que
/// la propia orden declara, nunca biblioteca\, el host, backend.env ni claves) y las carpetas de staging e instantanea se vuelven a validar aqui
/// (R-07). Una orden que no pasa se rechaza sin escribir un byte.
/// </summary>
internal sealed record Orden(
    string OrdenId,
    string PaqueteId,
    string Accion,
    int LimiteMinutos,
    string PaqueteSha256,
    long PaqueteBytes,
    string NombreDelPaquete,
    IReadOnlyList<ModuloDeOrden> Modulos,
    IReadOnlyList<ArchivoDeOrden> Archivos)
{
    public const string Aplicar = "aplicar";
    public const string Revertir = "revertir";
    public const string ModulosJson = "avacom_lms/modulos.json";

    public bool EsReversion => Accion == Revertir;

    /// <summary>Los pasos con checkpoint, en el orden en que el host los hace. En una reversion se migra hacia atras ANTES de volver al codigo viejo: el reverso de una migracion necesita el codigo que la define.</summary>
    public IReadOnlyList<string> Secuencia => EsReversion
        ? [Pasos.Comprobar, Pasos.Respaldar, Pasos.Migrar, Pasos.Copiar, Pasos.Verificar]
        : [Pasos.Comprobar, Pasos.Respaldar, Pasos.Instantanea, Pasos.Copiar, Pasos.Migrar, Pasos.Verificar];

    /// <summary>Carpeta del paquete en staging, relativa a Actualizaciones (la orden la declara; aqui se exige que sea exactamente esta).</summary>
    public string Staging => Path.Combine(Rutas.CarpetaActualizaciones, "staging", PaqueteId);

    public string CarpetaDeVersion => Path.Combine(Rutas.CarpetaActualizaciones, "versiones", PaqueteId);
    public string Anterior => Path.Combine(CarpetaDeVersion, "anterior");
    public string Posterior => Path.Combine(CarpetaDeVersion, "posterior");
    public string ArchivoDelPaquete => Path.Combine(Rutas.CarpetaActualizaciones, "paquetes", PaqueteId + ".avupd");

    private static readonly Regex IdDeOrden = new(@"^[A-Za-z0-9-]{8,64}$", RegexOptions.Compiled);
    private static readonly Regex Modulo = new(@"^[a-z][a-z0-9_]{0,40}$", RegexOptions.Compiled);
    private static readonly Regex Migracion = new(@"^[A-Za-z0-9_]{1,100}$", RegexOptions.Compiled);
    private static readonly Regex Componente = new(@"^[A-Za-z0-9_][A-Za-z0-9._-]{0,79}$", RegexOptions.Compiled);
    private static readonly Regex Sha256Hex = new(@"^[0-9a-f]{64}$", RegexOptions.Compiled);
    private static readonly string[] Extensiones = [".py", ".json", ".txt", ".md", ".html", ".css", ".js", ".sql", ".csv", ".ini", ".cfg"];
    private static readonly string[] ReservadosDeWindows =
        ["con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9", "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9"];

    public static Orden Leer(string ruta)
    {
        string texto;
        try
        {
            texto = File.ReadAllText(ruta);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            throw new OrdenInvalida($"No se pudo leer orden.json: {error.Message}");
        }
        return Interpretar(texto);
    }

    public static Orden Interpretar(string texto)
    {
        try
        {
            using var documento = JsonDocument.Parse(texto);
            var raiz = documento.RootElement;
            if (raiz.ValueKind != JsonValueKind.Object) throw new OrdenInvalida("orden.json no es un objeto.");
            if (!raiz.TryGetProperty("formato", out var formato) || formato.ValueKind != JsonValueKind.Number || formato.GetInt32() != 1)
                throw new OrdenInvalida("orden.json trae un formato que este host no conoce.");

            var ordenId = Texto(raiz, "orden_id");
            if (!IdDeOrden.IsMatch(ordenId)) throw new OrdenInvalida("orden_id invalido.");
            var paqueteId = Texto(raiz, "paquete_id");
            if (!Guid.TryParseExact(paqueteId, "D", out var guid) || guid.ToString("D") != paqueteId)
                throw new OrdenInvalida("paquete_id invalido.");
            var accion = Texto(raiz, "accion");
            if (accion != Aplicar && accion != Revertir) throw new OrdenInvalida("accion desconocida.");
            var limite = raiz.TryGetProperty("limite_minutos", out var l) && l.ValueKind == JsonValueKind.Number ? l.GetInt32() : 0;
            if (limite is < 1 or > 60) throw new OrdenInvalida("limite_minutos fuera de rango.");

            var paquete = Objeto(raiz, "paquete");
            var sha = Texto(paquete, "sha256");
            if (!Sha256Hex.IsMatch(sha)) throw new OrdenInvalida("La huella del paquete no es SHA-256.");
            var bytes = paquete.TryGetProperty("bytes", out var b) && b.ValueKind == JsonValueKind.Number ? b.GetInt64() : -1;
            if (bytes < 0) throw new OrdenInvalida("El tamano del paquete es invalido.");

            // Las carpetas se declaran, pero no se eligen: son exactamente las del paquete, dentro de Actualizaciones.
            var carpetas = Objeto(raiz, "carpetas");
            if (Texto(carpetas, "staging") != $"staging/{paqueteId}" || Texto(carpetas, "instantanea") != $"versiones/{paqueteId}/anterior")
                throw new OrdenInvalida("Las carpetas de la orden no son las del paquete.");

            var modulos = new List<ModuloDeOrden>();
            foreach (var m in Lista(raiz, "modulos", 64))
            {
                var nombre = Texto(m, "nombre");
                if (!Modulo.IsMatch(nombre) || nombre == "biblioteca") throw new OrdenInvalida($"Modulo invalido: {nombre}.");
                var migraciones = new List<MigracionDeOrden>();
                foreach (var g in Lista(m, "migraciones", 200))
                {
                    var nombreMigracion = Texto(g, "nombre");
                    var reverso = Texto(g, "reverso");
                    if (!Migracion.IsMatch(nombreMigracion) || !Migracion.IsMatch(reverso)) throw new OrdenInvalida("Una migracion trae un nombre invalido.");
                    migraciones.Add(new MigracionDeOrden(nombreMigracion, reverso));
                }
                modulos.Add(new ModuloDeOrden(nombre, migraciones));
            }
            if (modulos.Count == 0 || modulos.Select(m => m.Nombre).Distinct().Count() != modulos.Count) throw new OrdenInvalida("La lista de modulos es invalida.");

            var nombres = modulos.Select(m => m.Nombre).ToHashSet();
            var archivos = new List<ArchivoDeOrden>();
            var vistos = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var a in Lista(raiz, "archivos", 5000))
            {
                var rutaArchivo = Texto(a, "ruta");
                ValidarRuta(rutaArchivo, nombres);
                var huella = Texto(a, "sha256");
                var tam = a.TryGetProperty("bytes", out var t) && t.ValueKind == JsonValueKind.Number ? t.GetInt64() : -1;
                if (!Sha256Hex.IsMatch(huella) || tam < 0) throw new OrdenInvalida($"Archivo con huella o tamano invalido: {rutaArchivo}.");
                if (!vistos.Add(rutaArchivo)) throw new OrdenInvalida($"Archivo repetido: {rutaArchivo}.");
                archivos.Add(new ArchivoDeOrden(rutaArchivo, tam, huella));
            }
            if (archivos.Count == 0) throw new OrdenInvalida("La orden no trae archivos.");

            var nombrePaquete = paquete.TryGetProperty("nombre", out var np) && np.ValueKind == JsonValueKind.String ? np.GetString() ?? "" : "";
            return new Orden(ordenId, paqueteId, accion, limite, sha, bytes, nombrePaquete, modulos, archivos);
        }
        catch (JsonException error)
        {
            throw new OrdenInvalida($"orden.json no es JSON valido: {error.Message}");
        }
        catch (Exception error) when (error is InvalidOperationException or FormatException or OverflowException)
        {
            throw new OrdenInvalida($"orden.json no tiene la forma esperada: {error.Message}");
        }
    }

    /// <summary>
    /// Una ruta de archivo: relativa a Backend\, con /, dentro de una de las apps que la orden declara (o el registro de modulos), sin retrocesos, sin letra de unidad,
    /// sin nombres reservados de Windows y con extension de codigo o datos. Es la misma regla de dominio/rutas.py del backend, vuelta a comprobar por quien escribe en Program Files.
    /// </summary>
    internal static void ValidarRuta(string ruta, ISet<string> modulos)
    {
        if (string.IsNullOrEmpty(ruta) || ruta.Length > 200) throw new OrdenInvalida("Ruta vacia o demasiado larga.");
        if (ruta.Contains('\\') || ruta.Contains(':') || ruta.StartsWith('/')) throw new OrdenInvalida($"Ruta no permitida: {ruta}.");
        var partes = ruta.Split('/');
        if (partes.Length < 2) throw new OrdenInvalida($"Ruta fuera de una app: {ruta}.");
        foreach (var parte in partes)
        {
            if (!Componente.IsMatch(parte) || parte.EndsWith('.') || parte == "__pycache__")
                throw new OrdenInvalida($"Componente de ruta no permitido: {ruta}.");
            var sinExtension = parte.Split('.')[0].ToLowerInvariant();
            if (ReservadosDeWindows.Contains(sinExtension)) throw new OrdenInvalida($"Nombre reservado de Windows: {ruta}.");
        }
        if (!modulos.Contains(partes[0]) && ruta != ModulosJson)
            throw new OrdenInvalida($"La ruta {ruta} no es de ninguna de las apps que declara el paquete.");
        if (partes[0] == "biblioteca") throw new OrdenInvalida("biblioteca\\ es de AVACOM Contenido: un paquete no la toca.");
        var extension = Path.GetExtension(partes[^1]).ToLowerInvariant();
        if (Array.IndexOf(Extensiones, extension) < 0) throw new OrdenInvalida($"Extension no permitida: {ruta}.");
    }

    private static string Texto(JsonElement objeto, string nombre) =>
        objeto.TryGetProperty(nombre, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";

    private static JsonElement Objeto(JsonElement objeto, string nombre) =>
        objeto.TryGetProperty(nombre, out var v) && v.ValueKind == JsonValueKind.Object ? v : throw new OrdenInvalida($"Falta {nombre} en la orden.");

    private static IEnumerable<JsonElement> Lista(JsonElement objeto, string nombre, int maximo)
    {
        if (!objeto.TryGetProperty(nombre, out var v) || v.ValueKind != JsonValueKind.Array) throw new OrdenInvalida($"Falta la lista {nombre}.");
        if (v.GetArrayLength() > maximo) throw new OrdenInvalida($"La lista {nombre} es demasiado larga.");
        foreach (var elemento in v.EnumerateArray())
        {
            if (elemento.ValueKind != JsonValueKind.Object) throw new OrdenInvalida($"Un elemento de {nombre} no es un objeto.");
            yield return elemento;
        }
    }
}

/// <summary>Los pasos con checkpoint (P-07), con los nombres del catalogo del backend.</summary>
internal static class Pasos
{
    public const string Comprobar = "comprobar";
    public const string Respaldar = "respaldar";
    public const string Instantanea = "instantanea";
    public const string Copiar = "copiar";
    public const string Migrar = "migrar";
    public const string Verificar = "verificar";
}

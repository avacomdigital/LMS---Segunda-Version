using System.Security.Cryptography;
using System.Text;
using static Avacom.Ops.Host.Dispositivo.FormatoSello;

namespace Avacom.Ops.Host.Dispositivo;

/// <summary>No se pudo liberar la llave del paquete cifrado: el codigo del nodo no se puede abrir. <see cref="Motivo"/> es un codigo corto sin datos del equipo.</summary>
internal sealed class LiberacionFallida(string motivo) : Exception(motivo)
{
    public string Motivo { get; } = motivo;
}

/// <summary>
/// S2 · la LIBERACION DE LA CLAVE (<i>key release</i>): lo que hace real el «no copiable». El codigo propio del backend viaja cifrado en <c>Backend\codigo.avpkg</c> con una llave de paquete K. K no esta
/// en el instalador ni en el disco: esta en <c>Config\sello\paquete-&lt;kid&gt;.avclave</c>, ENVUELTA (RSA-OAEP-SHA256) para la clave de cifrado del equipo, que vive en su TPM y no sale de el. Solo ese TPM
/// la desenvuelve: copiar la instalacion y la carpeta de datos a otro equipo deja un paquete que nadie puede abrir.
///
/// Se libera SOLO si el equipo es «autenticado» (sello firmado por AVACOM, clave presente y firmando, no revocado) y la .avclave (firmada por la llave de sello) es para ESTE paquete y ESTA clave de cifrado.
///
/// Lo que NO es: K tiene que estar en memoria mientras el backend corre; quien administre el equipo y vuelque la memoria del proceso la vera (A4). Y K no se escribe en disco, no va en una variable de
/// entorno ni en la linea de comandos: se la pasa al proceso de Python por su entrada estandar (primera linea).
/// </summary>
internal static class LiberacionDeClave
{
    public const string NombreDelPaquete = "codigo.avpkg";
    public const string ClaveDeDesarrollo = "paquete-desarrollo.k";
    private const int LargoDeCabecera = 37;
    private static byte[]? _k;

    public static string RutaDelPaquete => Path.Combine(Rutas.CarpetaBackend, NombreDelPaquete);
    public static bool HayPaqueteCifrado => File.Exists(RutaDelPaquete);

    /// <summary>El kid (8 bytes) del paquete: esta en su cabecera, que NO va cifrada. null si no es un paquete valido.</summary>
    public static byte[]? KidDelPaquete(string ruta)
    {
        try
        {
            using var f = File.OpenRead(ruta);
            var c = new byte[LargoDeCabecera];
            if (f.Read(c, 0, c.Length) != c.Length || !c.AsSpan(0, 4).SequenceEqual("AVPK"u8)) return null;
            return c[7..15];
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return null; }
    }

    /// <summary>La llave del paquete, liberada una sola vez por proceso. Lanza <see cref="LiberacionFallida"/> con el motivo.</summary>
    public static byte[] Obtener()
    {
        if (_k is not null) return _k;
        var kid = KidDelPaquete(RutaDelPaquete) ?? throw new LiberacionFallida("paquete_ilegible");
        var (k, motivo) = Liberar(Verbos.ClavesDeEsteEquipo(), PuertaDeDispositivo.LlavesIncrustadas(), PuertaDeDispositivo.CarpetaDeSelloDelNodo, kid, DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                                   PuertaDeDispositivo.HayMarcadorDeDesarrollo(), Verbos.LectorUefiDeEsteEquipo());
        if (k is null) throw new LiberacionFallida(motivo);
        return _k = k;
    }

    /// <summary>Desenvuelve K. Devuelve <c>(K, "")</c> o <c>(null, motivo)</c>. No lanza.</summary>
    internal static (byte[]? K, string Motivo) Liberar(IClavesDeEquipo claves, IReadOnlyDictionary<string, byte[]> llaves, string carpetaSello, byte[] kidDelPaquete, long ahoraMs, bool desarrollo, ILectorUefi lector)
    {
        // Desarrollo (SP-10): un archivo con K en hexadecimal junto al sello, SOLO si el marcador de desarrollo lo firma la administracion. No hay otra forma de abrir un paquete sin el TPM.
        if (desarrollo && PuertaDeDispositivo.Leer(Path.Combine(carpetaSello, ClaveDeDesarrollo)) is { } crudo)
        {
            try
            {
                var kd = Convert.FromHexString(Encoding.ASCII.GetString(crudo).Trim());
                if (kd.Length == 32 && KidDePaquete(kd).AsSpan().SequenceEqual(kidDelPaquete)) return (kd, "");
            }
            catch (FormatException) { }
        }
        // La misma puerta que el instalador y el servicio, con la identidad UEFI incluida: sin ella la llave no se libera.
        var veredicto = PuertaDeDispositivo.Verificar(claves, llaves, carpetaSello, ahoraMs, lector);
        if (veredicto.Estado != Autenticado) return (null, "dispositivo_" + veredicto.Estado);
        var cifrado = claves.CifradoSpki();
        if (cifrado is null) return (null, "sin_clave_de_cifrado");
        var huella = HuellaDe(cifrado);
        var motivos = new List<string>();
        var archivos = Directory.Exists(carpetaSello) ? Directory.EnumerateFiles(carpetaSello, "*.avclave").Order(StringComparer.Ordinal).ToList() : new List<string>();
        foreach (var archivo in archivos)
        {
            var datos = PuertaDeDispositivo.Leer(archivo);
            if (datos is null) continue;
            ClaveDePaquete c;
            try { c = LeerClave(datos, llaves); }
            catch (Rechazo r) { motivos.Add("clave_" + r.Motivo); continue; }
            if (!c.KidPaquete.AsSpan().SequenceEqual(kidDelPaquete)) continue;                 // es de otra version del paquete
            if (!c.CifradoHuella.AsSpan().SequenceEqual(huella)) { motivos.Add("clave_de_otro_equipo"); continue; }
            var k = claves.Desenvolver(c.Envuelta);
            if (k is null || k.Length != 32) { motivos.Add("tpm_no_desenvuelve"); continue; }
            if (!KidDePaquete(k).AsSpan().SequenceEqual(kidDelPaquete)) { motivos.Add("clave_no_abre_el_paquete"); continue; }
            return (k, "");
        }
        return (null, motivos.FirstOrDefault() ?? "sin_clave_para_este_paquete");
    }

    /// <summary>Para las pruebas: olvida la llave cacheada.</summary>
    internal static void Olvidar() { if (_k is not null) CryptographicOperations.ZeroMemory(_k); _k = null; }
}

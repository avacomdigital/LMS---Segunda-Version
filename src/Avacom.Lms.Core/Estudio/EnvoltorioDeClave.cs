using System.Runtime.Versioning;
using System.Security.Cryptography;

namespace Avacom.Lms.Core.Estudio;

/// <summary>
/// Envuelve la clave AES-256 de lo local (<see cref="IProveedorDeClave"/>) con una clave que NO sale del Keystore de Android ni de CNG de Windows (MOD-018 · Fase 5, P-25). Hoy la clave de datos
/// se guarda con DPAPI (Windows) o <c>SecureStorage</c> (Android); con esto, además, quien se lleve el archivo guardado no puede abrirlo sin la clave no exportable del equipo. Está DETRÁS DE UNA
/// BANDERA y apagada de fábrica: cambiarla de sitio sin querer dejaría ilegible el trabajo local de un alumno (BR-053 destruye la clave a propósito; perderla por un error no).
/// </summary>
public interface IEnvoltorioDeClave
{
    /// <summary>Con qué se envuelve: <c>cng-tpm</c>, <c>cng-software</c>, <c>keystore</c>… Informativo.</summary>
    string Nombre { get; }

    /// <summary>La clave de datos envuelta. Sólo se puede abrir en ESTE equipo y con ESTA clave no exportable.</summary>
    byte[] Envolver(byte[] clave);

    /// <summary>La clave de datos, o null si lo envuelto no se puede abrir (otro equipo, una clave destruida, un archivo dañado).</summary>
    byte[]? Desenvolver(byte[] envuelta);

    /// <summary>Destruye la clave envolvente: lo envuelto con ella queda inabrible.</summary>
    void Destruir();
}

/// <summary>
/// El envoltorio de Windows: una clave RSA-2048 de CNG sin política de exportación (en el TPM si el equipo lo tiene, en software si no) con relleno OAEP-SHA256. La clave de datos mide 32 bytes y
/// el resultado, 256.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class EnvoltorioCng : IEnvoltorioDeClave
{
    public const string NombreDeLaClave = "AVACOM-ClaveDeDatos-v1";
    private static readonly CngProvider Plataforma = new("Microsoft Platform Crypto Provider");
    private static readonly CngProvider Software = CngProvider.MicrosoftSoftwareKeyStorageProvider;

    private readonly string nombre;
    private readonly bool probarTpm;
    private string declarado = "cng-software";

    public EnvoltorioCng(string? nombreDeLaClave = null, bool probarTpm = true)
    {
        nombre = string.IsNullOrWhiteSpace(nombreDeLaClave) ? NombreDeLaClave : nombreDeLaClave;
        this.probarTpm = probarTpm;
    }

    public string Nombre => declarado;

    public byte[] Envolver(byte[] clave)
    {
        ArgumentNullException.ThrowIfNull(clave);
        using var llave = Abrir() ?? Crear() ?? throw new CryptographicException("No hay dónde guardar la clave envolvente en este equipo.");
        using var rsa = new RSACng(llave);
        return rsa.Encrypt(clave, RSAEncryptionPadding.OaepSHA256);
    }

    public byte[]? Desenvolver(byte[] envuelta)
    {
        try
        {
            using var llave = Abrir();
            if (llave is null) return null;
            using var rsa = new RSACng(llave);
            return rsa.Decrypt(envuelta, RSAEncryptionPadding.OaepSHA256);
        }
        catch (Exception ex) when (ex is CryptographicException or ArgumentException) { return null; }
    }

    public void Destruir()
    {
        foreach (var (proveedor, _) in Candidatos())
        {
            try { if (CngKey.Exists(nombre, proveedor)) { using var llave = CngKey.Open(nombre, proveedor); llave.Delete(); } }
            catch (CryptographicException) { }
        }
    }

    private CngKey? Abrir()
    {
        foreach (var (proveedor, etiqueta) in Candidatos())
        {
            try
            {
                if (!CngKey.Exists(nombre, proveedor)) continue;
                var llave = CngKey.Open(nombre, proveedor);
                declarado = etiqueta;
                return llave;
            }
            catch (CryptographicException) { }
        }
        return null;
    }

    private CngKey? Crear()
    {
        foreach (var (proveedor, etiqueta) in Candidatos())
        {
            try
            {
                var parametros = new CngKeyCreationParameters { Provider = proveedor, ExportPolicy = CngExportPolicies.None, KeyUsage = CngKeyUsages.Decryption };
                parametros.Parameters.Add(new CngProperty("Length", BitConverter.GetBytes(2048), CngPropertyOptions.None));
                var llave = CngKey.Create(CngAlgorithm.Rsa, nombre, parametros);
                declarado = etiqueta;
                return llave;
            }
            catch (CryptographicException) { }
        }
        return null;
    }

    private IEnumerable<(CngProvider Proveedor, string Etiqueta)> Candidatos()
    {
        if (probarTpm) yield return (Plataforma, "cng-tpm");
        yield return (Software, "cng-software");
    }
}

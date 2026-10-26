using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Security.Cryptography;

namespace Avacom.Lms.Core.IdentidadDeDispositivo;

/// <summary>
/// La clave de identidad de un equipo Windows (OPS y Student Windows) en CNG: EC P-256, con <b>política de exportación «ninguna»</b> (la app firma con ella pero no puede sacarla). Se intenta primero
/// en el <i>Microsoft Platform Crypto Provider</i> (el TPM del equipo, si lo hay) y, si no se puede, en el <i>Microsoft Software Key Storage Provider</i>.
///
/// Probado en el equipo de desarrollo, sin elevar privilegios: el proveedor de plataforma crea la clave, firma y su <c>Impl Type</c> dice «hardware»; el de software dice «software». Pero el nodo NO
/// puede verificarlo (no hay atestación de TPM sin una CA): lo que el equipo dice de dónde guarda la clave viaja como <c>proveedor</c>, informativo, y la garantía de un Windows queda en «software».
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class ProveedorCng : IProveedorDeIdentidad
{
    public const string NombreDeLaClave = "AVACOM-Identidad-v1";
    private static readonly CngProvider Plataforma = new("Microsoft Platform Crypto Provider");
    private static readonly CngProvider Software = CngProvider.MicrosoftSoftwareKeyStorageProvider;

    private readonly string nombre;
    private readonly bool probarTpm;
    private string declarado = "software";

    public ProveedorCng(string? nombreDeLaClave = null, bool probarTpm = true)
    {
        nombre = string.IsNullOrWhiteSpace(nombreDeLaClave) ? NombreDeLaClave : nombreDeLaClave;
        this.probarTpm = probarTpm;
    }

    public string Nombre => declarado;

    public Task<PruebaDeClave?> ProbarAsync(string identificadorHw, byte[] reto, CancellationToken ct = default)
    {
        try
        {
            using var clave = Abrir() ?? Crear();
            if (clave is null) return Task.FromResult<PruebaDeClave?>(null);
            using var ecdsa = new ECDsaCng(clave);
            var firma = ecdsa.SignData(ReglasDeIdentidad.MensajeDelReto(reto, identificadorHw), HashAlgorithmName.SHA256);     // IEEE P1363 (64 bytes); el nodo lo acepta
            return Task.FromResult<PruebaDeClave?>(new PruebaDeClave(ecdsa.ExportSubjectPublicKeyInfo(), firma, [], declarado));
        }
        catch (Exception ex) when (ex is CryptographicException or PlatformNotSupportedException or InvalidOperationException or NotSupportedException)
        {
            return Task.FromResult<PruebaDeClave?>(null);       // sin clave no hay prueba: el equipo sigue como «declarada»
        }
    }

    private CngKey? Abrir()
    {
        foreach (var (proveedor, etiqueta) in Candidatos())
        {
            try
            {
                if (!CngKey.Exists(nombre, proveedor)) continue;
                var clave = CngKey.Open(nombre, proveedor);
                declarado = etiqueta == "tpm" && !EsHardware(proveedor) ? "software" : etiqueta;
                return clave;
            }
            catch (CryptographicException) { /* ese proveedor no la tiene o no responde: se prueba el otro */ }
        }
        return null;
    }

    private CngKey? Crear()
    {
        foreach (var (proveedor, etiqueta) in Candidatos())
        {
            try
            {
                var parametros = new CngKeyCreationParameters { Provider = proveedor, ExportPolicy = CngExportPolicies.None, KeyUsage = CngKeyUsages.Signing };
                var clave = CngKey.Create(CngAlgorithm.ECDsaP256, nombre, parametros);
                declarado = etiqueta == "tpm" && !EsHardware(proveedor) ? "software" : etiqueta;
                return clave;
            }
            catch (CryptographicException) { /* sin TPM o sin permiso: se cae al proveedor de software */ }
        }
        return null;
    }

    private IEnumerable<(CngProvider Proveedor, string Etiqueta)> Candidatos()
    {
        if (probarTpm) yield return (Plataforma, "tpm");
        yield return (Software, "software");
    }

    /// <summary>Lo que dice el propio proveedor de sí mismo: su propiedad <c>Impl Type</c> trae la bandera de hardware (1). Se lee del PROVEEDOR, no de la clave (NTE_NOT_SUPPORTED).</summary>
    public static bool EsHardware(CngProvider proveedor)
    {
        var manija = IntPtr.Zero;
        try
        {
            if (NCryptOpenStorageProvider(out manija, proveedor.Provider, 0) != 0) return false;
            var buffer = new byte[4];
            return NCryptGetProperty(manija, "Impl Type", buffer, buffer.Length, out _, 0) == 0 && (BitConverter.ToUInt32(buffer, 0) & 1) != 0;
        }
        catch (Exception ex) when (ex is DllNotFoundException or EntryPointNotFoundException) { return false; }
        finally { if (manija != IntPtr.Zero) NCryptFreeObject(manija); }
    }

    /// <summary>Borra la clave de este equipo (las pruebas; y «reiniciar identidad» del lado de la app, si se necesita).</summary>
    public void Borrar()
    {
        foreach (var (proveedor, _) in Candidatos())
        {
            try { if (CngKey.Exists(nombre, proveedor)) { using var clave = CngKey.Open(nombre, proveedor); clave.Delete(); } }
            catch (CryptographicException) { }
        }
    }

    /// <summary>
    /// El proveedor de este equipo si es Windows; en otro sistema, null. Cada app lleva SU clave (<paramref name="nombreDeLaClave"/>): OPS y Student pueden vivir en el mismo PC de desarrollo o de
    /// QA con el mismo usuario de Windows, y una clave compartida contaría como un solo equipo con dos huellas (<c>409 clave_en_uso</c>).
    /// </summary>
    public static IProveedorDeIdentidad? SiEsWindows(string? nombreDeLaClave = null) => OperatingSystem.IsWindows() ? new ProveedorCng(nombreDeLaClave) : null;

    [DllImport("ncrypt.dll", CharSet = CharSet.Unicode)]
    private static extern int NCryptOpenStorageProvider(out IntPtr proveedor, string nombre, int banderas);

    [DllImport("ncrypt.dll", CharSet = CharSet.Unicode)]
    private static extern int NCryptGetProperty(IntPtr objeto, string propiedad, byte[] salida, int largo, out int escrito, int banderas);

    [DllImport("ncrypt.dll")]
    private static extern int NCryptFreeObject(IntPtr objeto);
}

using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Security.Cryptography;

namespace Avacom.Ops.Host.Dispositivo;

/// <summary>Las dos claves que hacen de un equipo «un dispositivo AVACOM»: la de identidad (firma el reto) y la de cifrado (desenvuelve la clave del paquete, S2). Ninguna sale del equipo.</summary>
internal interface IClavesDeEquipo
{
    /// <summary>La clave publica de identidad (SubjectPublicKeyInfo DER), o null si el equipo no la tiene. NO la crea.</summary>
    byte[]? IdentidadSpki();
    /// <summary>Firma ECDSA P-256 SHA-256 en 64 bytes (IEEE P1363) con la clave de identidad; null si no se pudo.</summary>
    byte[]? Firmar(byte[] mensaje);
    /// <summary>La clave publica de cifrado (SPKI RSA-2048), o null.</summary>
    byte[]? CifradoSpki();
    /// <summary>RSA-OAEP-SHA256: desenvuelve con la clave privada, que no sale de su proveedor; null si no se pudo (TPM restablecido, clave ausente).</summary>
    byte[]? Desenvolver(byte[] envuelto);
    /// <summary>Crea las dos claves si faltan. Devuelve true si tras la llamada existen las dos.</summary>
    bool Crear();
    /// <summary>true si el proveedor dice ser hardware (TPM). Es lo que el equipo DICE de si mismo: el sello no lo prueba (evidencia «inventario»).</summary>
    bool EnTpm { get; }
    /// <summary>La EKPub del TPM tal como la entrega el proveedor de plataforma (PCP_EKPUB); null si no hay TPM o no se pudo leer.</summary>
    byte[]? EkPub();
}

/// <summary>
/// Las claves en CNG, en el ALMACEN DEL EQUIPO (ambito de maquina): las usan el instalador (administrador), el servicio (SYSTEM) y, mas adelante, OPS. Una clave de usuario no la podria abrir SYSTEM.
/// Crearlas exige administrador (probado: sin elevar, el proveedor de plataforma niega las de maquina). Primero el <i>Microsoft Platform Crypto Provider</i> (el TPM), y si no hay, el de software.
/// Politica de exportacion «ninguna» en las dos.
/// </summary>
[SupportedOSPlatform("windows")]
internal sealed class ClavesCng : IClavesDeEquipo
{
    public const string NombreIdentidad = "AVACOM-Sello-Identidad-v1";
    public const string NombreCifrado = "AVACOM-Sello-Cifrado-v1";
    private static readonly CngProvider Plataforma = new("Microsoft Platform Crypto Provider");
    private static readonly CngProvider Software = CngProvider.MicrosoftSoftwareKeyStorageProvider;

    private readonly string _identidad, _cifrado;
    private readonly bool _maquina, _probarTpm;

    public ClavesCng(string? sufijo = null, bool maquina = true, bool probarTpm = true)
    {
        _identidad = NombreIdentidad + sufijo;
        _cifrado = NombreCifrado + sufijo;
        _maquina = maquina;
        _probarTpm = probarTpm;
    }

    public bool EnTpm { get; private set; }

    private CngKeyOpenOptions Abrir => _maquina ? CngKeyOpenOptions.MachineKey : CngKeyOpenOptions.None;

    private IEnumerable<CngProvider> Proveedores()
    {
        if (_probarTpm) yield return Plataforma;
        yield return Software;
    }

    private CngKey? Buscar(string nombre)
    {
        foreach (var p in Proveedores())
        {
            try
            {
                if (!CngKey.Exists(nombre, p, Abrir)) continue;
                var clave = CngKey.Open(nombre, p, Abrir);
                EnTpm = p == Plataforma && EsHardware(p);
                return clave;
            }
            catch (CryptographicException) { /* ese proveedor no la tiene o no responde: se prueba el otro */ }
        }
        return null;
    }

    public byte[]? IdentidadSpki()
    {
        try { using var k = Buscar(_identidad); return k is null ? null : new ECDsaCng(k).ExportSubjectPublicKeyInfo(); }
        catch (Exception ex) when (ex is CryptographicException or PlatformNotSupportedException) { return null; }
    }

    public byte[]? CifradoSpki()
    {
        try { using var k = Buscar(_cifrado); return k is null ? null : new RSACng(k).ExportSubjectPublicKeyInfo(); }
        catch (Exception ex) when (ex is CryptographicException or PlatformNotSupportedException) { return null; }
    }

    public byte[]? Firmar(byte[] mensaje)
    {
        try
        {
            using var k = Buscar(_identidad);
            return k is null ? null : new ECDsaCng(k).SignData(mensaje, HashAlgorithmName.SHA256);       // IEEE P1363, 64 bytes
        }
        catch (Exception ex) when (ex is CryptographicException or PlatformNotSupportedException) { return null; }
    }

    public byte[]? Desenvolver(byte[] envuelto)
    {
        try
        {
            using var k = Buscar(_cifrado);
            return k is null ? null : new RSACng(k).Decrypt(envuelto, RSAEncryptionPadding.OaepSHA256);
        }
        catch (Exception ex) when (ex is CryptographicException or PlatformNotSupportedException) { return null; }
    }

    public bool Crear()
    {
        foreach (var p in Proveedores())
        {
            try
            {
                var tieneId = CngKey.Exists(_identidad, p, Abrir);
                var tieneCif = CngKey.Exists(_cifrado, p, Abrir);
                if (tieneId && tieneCif) { EnTpm = p == Plataforma && EsHardware(p); return true; }
                if (tieneId != tieneCif) continue;               // a medias en este proveedor: no se mezcla; se prueba el otro
                var opciones = _maquina ? CngKeyCreationOptions.MachineKey : CngKeyCreationOptions.None;
                using (CngKey.Create(CngAlgorithm.ECDsaP256, _identidad, new CngKeyCreationParameters { Provider = p, ExportPolicy = CngExportPolicies.None, KeyUsage = CngKeyUsages.Signing, KeyCreationOptions = opciones })) { }
                var rsa = new CngKeyCreationParameters { Provider = p, ExportPolicy = CngExportPolicies.None, KeyUsage = CngKeyUsages.Decryption, KeyCreationOptions = opciones };
                rsa.Parameters.Add(new CngProperty("Length", BitConverter.GetBytes(2048), CngPropertyOptions.None));
                using (CngKey.Create(CngAlgorithm.Rsa, _cifrado, rsa)) { }
                EnTpm = p == Plataforma && EsHardware(p);
                return true;
            }
            catch (CryptographicException) { /* sin TPM, sin permiso o sin elevar: se prueba el de software, y si tampoco, se devuelve false */ }
        }
        return false;
    }

    /// <summary>Borra las dos claves (las pruebas; «reiniciar identidad» de un tecnico).</summary>
    public void Borrar()
    {
        foreach (var nombre in new[] { _identidad, _cifrado })
            foreach (var p in Proveedores())
            {
                try { if (CngKey.Exists(nombre, p, Abrir)) { using var k = CngKey.Open(nombre, p, Abrir); k.Delete(); } }
                catch (CryptographicException) { }
            }
    }

    public byte[]? EkPub() => !_probarTpm ? null : LeerPropiedadDelProveedor("PCP_EKPUB");

    private static byte[]? LeerPropiedadDelProveedor(string propiedad)
    {
        var manija = IntPtr.Zero;
        try
        {
            if (NCryptOpenStorageProvider(out manija, Plataforma.Provider, 0) != 0) return null;
            if (NCryptGetProperty(manija, propiedad, null, 0, out var necesario, 0) != 0 || necesario <= 0 || necesario > 4096) return null;
            var buffer = new byte[necesario];
            return NCryptGetProperty(manija, propiedad, buffer, buffer.Length, out var escrito, 0) == 0 ? buffer[..escrito] : null;
        }
        catch (Exception ex) when (ex is DllNotFoundException or EntryPointNotFoundException) { return null; }
        finally { if (manija != IntPtr.Zero) NCryptFreeObject(manija); }
    }

    private static bool EsHardware(CngProvider proveedor)
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

    [DllImport("ncrypt.dll", CharSet = CharSet.Unicode)]
    private static extern int NCryptOpenStorageProvider(out IntPtr proveedor, string nombre, int banderas);

    [DllImport("ncrypt.dll", CharSet = CharSet.Unicode)]
    private static extern int NCryptGetProperty(IntPtr objeto, string propiedad, byte[]? salida, int largo, out int escrito, int banderas);

    [DllImport("ncrypt.dll")]
    private static extern int NCryptFreeObject(IntPtr objeto);
}

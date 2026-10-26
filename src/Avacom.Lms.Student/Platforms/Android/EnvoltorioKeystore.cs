using System.Runtime.Versioning;
using Android.Runtime;
using Android.Security.Keystore;
using Avacom.Lms.Core.Estudio;
using Java.Security;
using Javax.Crypto;
using Javax.Crypto.Spec;

namespace Avacom.Lms.Student.Platforms.Android;

/// <summary>
/// El envoltorio de la clave de datos en Android (MOD-018 · Fase 5, P-25): una clave AES-256-GCM del Keystore que NO se exporta; la clave de datos se guarda como <c>IV (12) + texto cifrado</c>. Sólo
/// se usa con la bandera encendida (apagada de fábrica). SIN COMPROBAR en un aparato real: no hubo tableta Android 14 física.
/// </summary>
[SupportedOSPlatform("android23.0")]
public sealed class EnvoltorioKeystore : IEnvoltorioDeClave
{
    public const string Alias = "avacom-clave-datos-v1";
    private const string Almacen = "AndroidKeyStore";
    private const int LargoDelIv = 12;

    public string Nombre => "keystore";

    public byte[] Envolver(byte[] clave)
    {
        var llave = Abrir() ?? Crear();
        var cifrador = Cipher.GetInstance("AES/GCM/NoPadding")!;
        cifrador.Init(CipherMode.EncryptMode, llave);
        var iv = cifrador.GetIV()!;
        var cifrado = cifrador.DoFinal(clave)!;
        var salida = new byte[iv.Length + cifrado.Length];
        iv.CopyTo(salida, 0);
        cifrado.CopyTo(salida, iv.Length);
        return salida;
    }

    public byte[]? Desenvolver(byte[] envuelta)
    {
        try
        {
            if (envuelta.Length <= LargoDelIv || Abrir() is not { } llave) return null;
            var cifrador = Cipher.GetInstance("AES/GCM/NoPadding")!;
            cifrador.Init(CipherMode.DecryptMode, llave, new GCMParameterSpec(128, envuelta, 0, LargoDelIv));
            return cifrador.DoFinal(envuelta, LargoDelIv, envuelta.Length - LargoDelIv);
        }
        catch (Exception ex) when (ex is Java.Lang.Exception or InvalidOperationException) { return null; }
    }

    public void Destruir()
    {
        try { var a = KeyStore.GetInstance(Almacen)!; a.Load(null); if (a.ContainsAlias(Alias)) a.DeleteEntry(Alias); }
        catch (Exception ex) when (ex is Java.Lang.Exception) { }
    }

    private static ISecretKey? Abrir()
    {
        var almacen = KeyStore.GetInstance(Almacen)!;
        almacen.Load(null);
        return almacen.ContainsAlias(Alias) ? almacen.GetKey(Alias, null)?.JavaCast<ISecretKey>() : null;
    }

    private static ISecretKey Crear()
    {
        var generador = KeyGenerator.GetInstance(KeyProperties.KeyAlgorithmAes, Almacen)!;
        generador.Init(new KeyGenParameterSpec.Builder(Alias, KeyStorePurpose.Encrypt | KeyStorePurpose.Decrypt)
            .SetBlockModes(KeyProperties.BlockModeGcm)!
            .SetEncryptionPaddings(KeyProperties.EncryptionPaddingNone)!
            .SetKeySize(256)!
            .Build());
        return generador.GenerateKey()!;
    }
}

using System.Runtime.Versioning;
using Android.Content.PM;
using Android.Runtime;
using Android.Security.Keystore;
using Avacom.Lms.Core.IdentidadDeDispositivo;
using Java.Security;
using Java.Security.Spec;

namespace Avacom.Lms.Student.Platforms.Android;

/// <summary>
/// La clave de identidad de esta tableta en el Keystore de Android (MOD-018, Fase 5, P-24): EC P-256 que NO se puede exportar (la app firma con ella pero no la ve), creada en el primer contacto
/// con el reto del nodo como desafío de atestación (<c>setAttestationChallenge</c>) y, si el equipo lo declara, en StrongBox. La cadena de certificados que entrega el Keystore es lo que el nodo
/// verifica sin internet contra las raíces de Google: sin ella (o si no cuadra) la tableta queda en «software», nunca bloqueada.
///
/// SIN COMPROBAR en un aparato real: no hubo tableta Android 14 física. Esto se probó en un emulador (Android 37, x86_64), cuya clave vive en software.
/// </summary>
[SupportedOSPlatform("android24.0")]
public sealed class ProveedorKeystore : IProveedorDeIdentidad
{
    public const string Alias = "avacom-identidad-v1";
    private const string Almacen = "AndroidKeyStore";
    private string declarado = "software";

    public string Nombre => declarado;

    /// <summary>Por qué la última prueba no pudo hacerse (el tipo y el mensaje de la excepción): para el registro local y para quien depura. Nunca viaja al nodo.</summary>
    public string? UltimoError { get; private set; }

    public Task<PruebaDeClave?> ProbarAsync(string identificadorHw, byte[] reto, CancellationToken ct = default) => Task.Run(() => Probar(identificadorHw, reto), ct);

    private PruebaDeClave? Probar(string identificadorHw, byte[] reto)
    {
        try
        {
            if (!OperatingSystem.IsAndroidVersionAtLeast(24)) return null;      // la atestación por clave llegó con Android 7
            var almacen = KeyStore.GetInstance(Almacen)!;
            almacen.Load(null);
            IReadOnlyList<byte[]> cadena = [];
            if (!almacen.ContainsAlias(Alias)) cadena = Crear(almacen, reto);
            // `GetKey` entrega un envoltorio genérico de Java: se convierte con JavaCast (un `as IPrivateKey` común no lo reconoce y daba null).
            var privada = almacen.GetKey(Alias, null)?.JavaCast<IPrivateKey>();
            if (privada is null || almacen.GetCertificate(Alias) is not { } certificado)
            {
                UltimoError = "sin_clave_privada_en_el_keystore";
                return null;
            }
            DeclararNivel(privada);
            var firma = Java.Security.Signature.GetInstance("SHA256withECDSA")!;
            firma.InitSign(privada);
            firma.Update(ReglasDeIdentidad.MensajeDelReto(reto, identificadorHw));
            return new PruebaDeClave(certificado.PublicKey!.GetEncoded()!, firma.Sign()!, cadena, declarado);
        }
        catch (Exception ex) when (ex is Java.Lang.Exception or InvalidOperationException or ArgumentException)
        {
            UltimoError = $"{ex.GetType().Name}: {ex.Message}";
            return null;       // sin clave no hay prueba: la tableta sigue como «declarada»
        }
    }

    private IReadOnlyList<byte[]> Crear(KeyStore almacen, byte[] reto)
    {
        var contexto = global::Android.App.Application.Context;
        var strongbox = OperatingSystem.IsAndroidVersionAtLeast(28) && contexto.PackageManager?.HasSystemFeature(PackageManager.FeatureStrongboxKeystore) == true;
        try { Generar(reto, strongbox); }
        catch (Exception ex) when (strongbox && ex is Java.Lang.Exception)
        {
            Generar(reto, false);          // StrongBox anunciado pero no disponible (StrongBoxUnavailableException): se cae al entorno seguro normal
        }
        var certificados = almacen.GetCertificateChain(Alias);
        return certificados is null ? [] : certificados.Select(c => c.GetEncoded()!).ToList();
    }

    private static void Generar(byte[] reto, bool strongbox)
    {
        var generador = KeyPairGenerator.GetInstance(KeyProperties.KeyAlgorithmEc, Almacen)!;
        var especificacion = new KeyGenParameterSpec.Builder(Alias, KeyStorePurpose.Sign)
            .SetAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1"))!
            .SetDigests(KeyProperties.DigestSha256)!
            .SetAttestationChallenge(reto)!;
        if (strongbox && OperatingSystem.IsAndroidVersionAtLeast(28)) especificacion.SetIsStrongBoxBacked(true);
        generador.Initialize(especificacion.Build());
        generador.GenerateKeyPair();
    }

    /// <summary>Dónde vive la clave según el propio Keystore: <c>strongbox</c>, <c>tee</c> o <c>software</c>. Informativo: el nodo lo decide con la atestación, no con esto.</summary>
    private void DeclararNivel(IPrivateKey privada)
    {
        try
        {
            var fabrica = KeyFactory.GetInstance(privada.Algorithm!, Almacen)!;
            if (fabrica.GetKeySpec(privada, Java.Lang.Class.FromType(typeof(KeyInfo))!) is not KeyInfo info) return;
            if (OperatingSystem.IsAndroidVersionAtLeast(31))
                declarado = (int)info.SecurityLevel switch          // KeyProperties.SECURITY_LEVEL_*: 0 software · 1 entorno seguro (TEE) · 2 StrongBox
                {
                    2 => "strongbox",
                    1 => "tee",
                    _ => "software",
                };
            else
#pragma warning disable CA1422
                declarado = info.IsInsideSecureHardware ? "tee" : "software";
#pragma warning restore CA1422
        }
        catch (Exception ex) when (ex is Java.Lang.Exception or InvalidOperationException) { /* queda «software» */ }
    }

    /// <summary>Borra la clave (las pruebas en el emulador).</summary>
    public static void Borrar()
    {
        try { var a = KeyStore.GetInstance(Almacen)!; a.Load(null); if (a.ContainsAlias(Alias)) a.DeleteEntry(Alias); }
        catch (Exception ex) when (ex is Java.Lang.Exception) { }
    }
}

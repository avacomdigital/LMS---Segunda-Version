using System.Runtime.InteropServices;
using System.Security.Cryptography;

namespace Avacom.Lms.Core.Licencia;

/// <summary>
/// La biblioteca nativa <c>avacom_lic</c> (MOD-018, Fase 4, P-20/P-22) vista desde Core. Es el ÚNICO archivo con <c>DllImport</c> de la licencia: ni Ops.Tests ni Student.Tests lo enlazan
/// como fuente (sólo referencian el ensamblado) y nada del arranque de OPS o de Student lo toca.
///
/// LA NATIVA NUNCA ES OBLIGATORIA. Cada función devuelve <c>null</c> cuando la biblioteca no está, no es de esta ABI o falla su autoprueba: quien llama usa entonces su referencia (o, si no la
/// tiene, sigue sin esta función). No lanza <see cref="DllNotFoundException"/>, <see cref="EntryPointNotFoundException"/> ni <see cref="BadImageFormatException"/>: se registran en
/// <see cref="MotivoDeNoDisponible"/>. Se carga la primera vez que se usa, por RUTA ABSOLUTA junto a la aplicación (Windows) o por el nombre que el APK instala (Android):
/// nunca por el directorio actual ni por el PATH.
///
/// Las llaves y los textos viajan en arreglos de bytes (sin <c>unsafe</c>): no se compila con <c>AllowUnsafeBlocks</c>.
/// </summary>
public static class NativoLicencia
{
    /// <summary>La ABI que este código espera de <c>avl_abi_version()</c>.</summary>
    public const uint AbiEsperada = 1;

    /// <summary>Un envoltorio (nonce 24 + etiqueta 16) mide esto más que el texto claro.</summary>
    public const int SobrecargaDeEnvoltura = 40;

    private const string Nombre = "avacom_lic";
    private static readonly object Candado = new();
    private static bool? _disponible;
    private static string? _motivo;

    /// <summary>¿Cargó, tiene la ABI esperada y pasó su autoprueba? La primera consulta la carga.</summary>
    public static bool Disponible
    {
        get
        {
            lock (Candado)
            {
                _disponible ??= Intentar();
                return _disponible.Value;
            }
        }
    }

    /// <summary>Por qué no está disponible (vacío si lo está o si todavía no se intentó). Sin rutas ni contenido: sirve para el registro.</summary>
    public static string? MotivoDeNoDisponible
    {
        get { lock (Candado) { return _motivo; } }
    }

    /// <summary>Sólo para pruebas: olvida lo cargado para volver a intentarlo.</summary>
    public static void Olvidar()
    {
        lock (Candado) { _disponible = null; _motivo = null; }
    }

    // ============================================================================================================ funciones
    /// <summary>
    /// ¿La firma Ed25519 (RFC 8032) de <paramref name="mensaje"/> es válida con <paramref name="publica"/>? <c>null</c> = la nativa no está (usa tu referencia). La nativa rechaza además las
    /// llaves y los R de orden pequeño y las S no canónicas (D-33).
    /// </summary>
    public static bool? VerificarFirma(byte[] mensaje, byte[] firma, byte[] publica)
    {
        if (firma.Length != 64 || publica.Length != 32) { return false; }
        if (!Disponible) { return null; }
        try { return Interop.avl_verify_detached(mensaje, (nuint)mensaje.Length, firma, publica) == 0; }
        catch (Exception e) when (EsFalloDeCarga(e)) { Marcar(e); return null; }
    }

    /// <summary>HKDF-SHA-512 (RFC 5869). <c>null</c> = la nativa no está.</summary>
    public static byte[]? Derivar(byte[] secreto, byte[] sal, byte[] info, int largo)
    {
        if (largo < 1 || largo > 255 * 64) { throw new ArgumentOutOfRangeException(nameof(largo)); }
        if (!Disponible) { return null; }
        var salida = new byte[largo];
        try
        {
            var rc = Interop.avl_key_derive(secreto, (nuint)secreto.Length, sal, (nuint)sal.Length, info, (nuint)info.Length, salida, (nuint)largo);
            return rc == 0 ? salida : null;
        }
        catch (Exception e) when (EsFalloDeCarga(e)) { Marcar(e); return null; }
    }

    /// <summary>XChaCha20-Poly1305 con el contexto como dato asociado: <c>nonce(24) · texto cifrado · etiqueta(16)</c>. <c>null</c> = la nativa no está.</summary>
    public static byte[]? Envolver(byte[] llave, byte[] nonce, byte[] contexto, byte[] claro)
    {
        if (llave.Length != 32 || nonce.Length != 24) { throw new ArgumentException("La llave mide 32 bytes y el nonce 24."); }
        if (!Disponible) { return null; }
        var salida = new byte[claro.Length + SobrecargaDeEnvoltura];
        try
        {
            var rc = Interop.avl_key_wrap(llave, nonce, contexto, (nuint)contexto.Length, claro, (nuint)claro.Length, salida, (nuint)salida.Length, out var escrito);
            return rc == 0 ? salida.AsSpan(0, (int)escrito).ToArray() : null;
        }
        catch (Exception e) when (EsFalloDeCarga(e)) { Marcar(e); return null; }
    }

    /// <summary>
    /// Abre una envoltura. <c>null</c> = la nativa no está. Si la etiqueta no cuadra (llave, contexto o texto distintos) lanza <see cref="CryptographicException"/>: eso no es un fallo de la
    /// biblioteca sino un dato que no es el que se envolvió.
    /// </summary>
    public static byte[]? Desenvolver(byte[] llave, byte[] contexto, byte[] envuelto)
    {
        if (llave.Length != 32) { throw new ArgumentException("La llave mide 32 bytes."); }
        if (!Disponible) { return null; }
        var salida = new byte[Math.Max(envuelto.Length, 1)];
        try
        {
            var rc = Interop.avl_key_unwrap(llave, contexto, (nuint)contexto.Length, envuelto, (nuint)envuelto.Length, salida, (nuint)salida.Length, out var escrito);
            if (rc == -14) { throw new CryptographicException("La envoltura no se abre con esta llave y este contexto."); }
            if (rc != 0) { return null; }
            var claro = salida.AsSpan(0, (int)escrito).ToArray();
            CryptographicOperations.ZeroMemory(salida);
            return claro;
        }
        catch (Exception e) when (EsFalloDeCarga(e)) { Marcar(e); return null; }
    }

    // ============================================================================================================ carga
    private static bool Intentar()
    {
        try
        {
            if (!OperatingSystem.IsWindows() && !OperatingSystem.IsAndroid() && !OperatingSystem.IsLinux()) { _motivo = "plataforma_no_soportada"; return false; }
            var abi = Interop.avl_abi_version();
            if (abi != AbiEsperada) { _motivo = $"abi_{abi}"; return false; }
            var paso = Interop.avl_selftest();
            if (paso != 0) { _motivo = $"autoprueba_{paso}"; return false; }
            return true;
        }
        catch (Exception e) when (EsFalloDeCarga(e))
        {
            _motivo = e.GetType().Name;
            return false;
        }
    }

    private static bool EsFalloDeCarga(Exception e) => e is DllNotFoundException or EntryPointNotFoundException or BadImageFormatException or FileNotFoundException or MarshalDirectiveException;

    private static void Marcar(Exception e)
    {
        lock (Candado) { _disponible = false; _motivo = e.GetType().Name; }
    }

    /// <summary>El resolvedor: en Windows carga <c>avacom_lic.dll</c> desde la carpeta de la aplicación con ruta absoluta; en el resto deja el sondeo de la plataforma (Android instala <c>libavacom_lic.so</c> por ABI).</summary>
    private static IntPtr Resolver(string nombre, System.Reflection.Assembly ensamblado, DllImportSearchPath? ruta)
    {
        if (nombre != Nombre || !OperatingSystem.IsWindows()) { return IntPtr.Zero; }
        var completa = Path.Combine(AppContext.BaseDirectory, "avacom_lic.dll");
        return File.Exists(completa) && NativeLibrary.TryLoad(completa, out var manejador) ? manejador : IntPtr.Zero;
    }

    static NativoLicencia()
    {
        try { NativeLibrary.SetDllImportResolver(typeof(NativoLicencia).Assembly, Resolver); }
        catch (InvalidOperationException) { /* ya había un resolvedor para este ensamblado: se usa el que haya */ }
    }

    private static class Interop
    {
        [DllImport(Nombre, CallingConvention = CallingConvention.Cdecl)]
        internal static extern uint avl_abi_version();

        [DllImport(Nombre, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int avl_selftest();

        [DllImport(Nombre, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int avl_verify_detached(byte[] msg, nuint msgLen, byte[] sig, byte[] pub);

        [DllImport(Nombre, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int avl_key_derive(byte[] secret, nuint secretLen, byte[] salt, nuint saltLen, byte[] info, nuint infoLen, byte[] output, nuint outLen);

        [DllImport(Nombre, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int avl_key_wrap(byte[] key, byte[] nonce, byte[] ctx, nuint ctxLen, byte[] plain, nuint plainLen, byte[] output, nuint outCap, out nuint outLen);

        [DllImport(Nombre, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int avl_key_unwrap(byte[] key, byte[] ctx, nuint ctxLen, byte[] wrapped, nuint wrappedLen, byte[] output, nuint outCap, out nuint outLen);
    }
}

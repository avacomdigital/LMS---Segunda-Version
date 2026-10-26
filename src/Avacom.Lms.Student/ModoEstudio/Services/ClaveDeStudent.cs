using System.Runtime.InteropServices;
using System.Security.Cryptography;
using Avacom.Lms.Core.Estudio;

namespace Avacom.Lms.Student.ModoEstudio.Services;

/// <summary>
/// La clave AES-256 de todo lo local del modo de estudio (BR-053: destruirla deja ilegible lo cifrado de un golpe). En Windows la protege
/// DPAPI con la cuenta de la persona que usa el equipo (sirve también sin empaquetar la app); en Android, <see cref="SecureStorage"/>
/// (Keystore). Se crea la primera vez que hace falta y se conserva hasta que se destruya. Si lo guardado no se puede leer (otro usuario de
/// Windows, un Keystore invalidado), se crea una clave nueva: lo que estaba cifrado con la anterior es ilegible y el almacén lo trata como ausente.
/// </summary>
internal sealed class ClaveDeStudent : IProveedorDeClave
{
    private readonly string _carpeta;
    private readonly object _candado = new();
    private readonly IEnvoltorioDeClave? _envoltorio;
    private readonly bool _envolver;
    private byte[]? _clave;

    /// <param name="carpeta">Dónde vive lo de esta clave.</param>
    /// <param name="envoltorio">MOD-018 · Fase 5 (P-25): la clave no exportable del Keystore o de CNG con que se puede envolver la clave de datos; nulo si la plataforma no la ofrece.</param>
    /// <param name="envolver">LA BANDERA (apagada de fábrica): si está encendida, la clave de datos NUEVA se guarda envuelta y la de antes se migra al leerla. Apagarla no desenvuelve lo ya envuelto:
    /// sigue abriéndose con el envoltorio (perderla sería dejar ilegible el trabajo local de un alumno).</param>
    public ClaveDeStudent(string carpeta, IEnvoltorioDeClave? envoltorio = null, bool envolver = false)
    {
        _carpeta = carpeta;
        _envoltorio = envoltorio;
        _envolver = envolver && envoltorio is not null;
    }

    private string RutaEnvuelta => Path.Combine(_carpeta, "clave.env");

    private byte[]? Leer()
    {
        if (_envoltorio is not null)
        {
            try
            {
                if (File.Exists(RutaEnvuelta) && _envoltorio.Desenvolver(File.ReadAllBytes(RutaEnvuelta)) is { Length: 32 } envuelta) return envuelta;
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { /* se cae al almacén de siempre */ }
        }
        var legado = LeerLegado();
        if (legado is not null && _envolver && GuardarEnvuelta(legado)) BorrarLegado();          // la migración: la MISMA clave, otro sitio (lo cifrado con ella sigue legible)
        return legado;
    }

    private byte[] CrearNueva()
    {
        if (_envolver)
        {
            var clave = RandomNumberGenerator.GetBytes(32);
            if (GuardarEnvuelta(clave)) return clave;
            CryptographicOperations.ZeroMemory(clave);          // no se pudo envolver: se vuelve al almacén de siempre, nunca se deja a la tableta sin clave
        }
        return CrearLegado();
    }

    private bool GuardarEnvuelta(byte[] clave)
    {
        try
        {
            Directory.CreateDirectory(_carpeta);
            File.WriteAllBytes(RutaEnvuelta, _envoltorio!.Envolver(clave));
            return true;
        }
        catch (Exception ex) when (ex is CryptographicException or IOException or UnauthorizedAccessException or InvalidOperationException) { return false; }
    }

    private void Borrar()
    {
        try { File.Delete(RutaEnvuelta); } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { /* sin la clave en memoria, el archivo envuelto ya no abre nada nuevo */ }
        BorrarLegado();
    }

    public byte[] Obtener()
    {
        lock (_candado)
        {
            _clave ??= Leer() ?? CrearNueva();
            return (byte[])_clave.Clone();
        }
    }

    public void Destruir()
    {
        lock (_candado)
        {
            if (_clave is not null) CryptographicOperations.ZeroMemory(_clave);
            _clave = null;
            Borrar();
        }
    }

#if WINDOWS
    // DPAPI directo (crypt32): no necesita paquetes ni que la app esté empaquetada. La clave queda atada a la cuenta de Windows de quien usa el equipo.
    private static readonly byte[] Entropia = "avacom-estudio-clave-v1"u8.ToArray();
    private const int CryptprotectUiForbidden = 0x1;

    [StructLayout(LayoutKind.Sequential)]
    private struct DataBlob
    {
        public int cbData;
        public IntPtr pbData;
    }

    [DllImport("crypt32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool CryptProtectData(ref DataBlob datosEntrada, string? descripcion, ref DataBlob entropia, IntPtr reservado, IntPtr aviso, int banderas, out DataBlob datosSalida);

    [DllImport("crypt32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool CryptUnprotectData(ref DataBlob datosEntrada, IntPtr descripcion, ref DataBlob entropia, IntPtr reservado, IntPtr aviso, int banderas, out DataBlob datosSalida);

    [DllImport("kernel32.dll")]
    private static extern IntPtr LocalFree(IntPtr memoria);

    private static byte[] Transformar(byte[] entrada, bool proteger)
    {
        var fijaEntrada = GCHandle.Alloc(entrada, GCHandleType.Pinned);
        var fijaEntropia = GCHandle.Alloc(Entropia, GCHandleType.Pinned);
        try
        {
            var dentro = new DataBlob { cbData = entrada.Length, pbData = fijaEntrada.AddrOfPinnedObject() };
            var sal = new DataBlob { cbData = Entropia.Length, pbData = fijaEntropia.AddrOfPinnedObject() };
            DataBlob fuera;
            var bien = proteger
                ? CryptProtectData(ref dentro, null, ref sal, IntPtr.Zero, IntPtr.Zero, CryptprotectUiForbidden, out fuera)
                : CryptUnprotectData(ref dentro, IntPtr.Zero, ref sal, IntPtr.Zero, IntPtr.Zero, CryptprotectUiForbidden, out fuera);
            if (!bien) throw new CryptographicException(Marshal.GetLastWin32Error());
            try
            {
                var resultado = new byte[fuera.cbData];
                Marshal.Copy(fuera.pbData, resultado, 0, fuera.cbData);
                return resultado;
            }
            finally { LocalFree(fuera.pbData); }
        }
        finally
        {
            fijaEntrada.Free();
            fijaEntropia.Free();
        }
    }

    private string Ruta => Path.Combine(_carpeta, "clave.dpapi");

    private byte[]? LeerLegado()
    {
        try
        {
            if (!File.Exists(Ruta)) return null;
            var abierta = Transformar(File.ReadAllBytes(Ruta), proteger: false);
            return abierta.Length == 32 ? abierta : null;
        }
        catch (Exception ex) when (ex is CryptographicException or IOException or UnauthorizedAccessException) { return null; }
    }

    private byte[] CrearLegado()
    {
        var clave = RandomNumberGenerator.GetBytes(32);
        Directory.CreateDirectory(_carpeta);
        File.WriteAllBytes(Ruta, Transformar(clave, proteger: true));
        return clave;
    }

    private void BorrarLegado()
    {
        try { File.Delete(Ruta); } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { /* la clave ya no está en memoria; el archivo se sobrescribe la próxima vez */ }
    }
#else
    private const string Nombre = "avacom_estudio_clave_v1";

    private static byte[]? LeerLegado()
    {
        try
        {
            var texto = Task.Run(() => SecureStorage.Default.GetAsync(Nombre)).GetAwaiter().GetResult();
            if (string.IsNullOrEmpty(texto)) return null;
            var clave = Convert.FromBase64String(texto);
            return clave.Length == 32 ? clave : null;
        }
        catch (Exception) { return null; }
    }

    private static byte[] CrearLegado()
    {
        var clave = RandomNumberGenerator.GetBytes(32);
        Task.Run(() => SecureStorage.Default.SetAsync(Nombre, Convert.ToBase64String(clave))).GetAwaiter().GetResult();
        return clave;
    }

    private static void BorrarLegado()
    {
        try { SecureStorage.Default.Remove(Nombre); } catch (Exception) { /* sin clave en memoria y sin la guardada, lo cifrado ya es ilegible */ }
    }
#endif
}

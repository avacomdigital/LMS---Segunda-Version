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
    private byte[]? _clave;

    public ClaveDeStudent(string carpeta) => _carpeta = carpeta;

    public byte[] Obtener()
    {
        lock (_candado)
        {
            _clave ??= Leer() ?? Crear();
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

    private byte[]? Leer()
    {
        try
        {
            if (!File.Exists(Ruta)) return null;
            var abierta = Transformar(File.ReadAllBytes(Ruta), proteger: false);
            return abierta.Length == 32 ? abierta : null;
        }
        catch (Exception ex) when (ex is CryptographicException or IOException or UnauthorizedAccessException) { return null; }
    }

    private byte[] Crear()
    {
        var clave = RandomNumberGenerator.GetBytes(32);
        Directory.CreateDirectory(_carpeta);
        File.WriteAllBytes(Ruta, Transformar(clave, proteger: true));
        return clave;
    }

    private void Borrar()
    {
        try { File.Delete(Ruta); } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { /* la clave ya no está en memoria; el archivo se sobrescribe la próxima vez */ }
    }
#else
    private const string Nombre = "avacom_estudio_clave_v1";

    private static byte[]? Leer()
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

    private static byte[] Crear()
    {
        var clave = RandomNumberGenerator.GetBytes(32);
        Task.Run(() => SecureStorage.Default.SetAsync(Nombre, Convert.ToBase64String(clave))).GetAwaiter().GetResult();
        return clave;
    }

    private static void Borrar()
    {
        try { SecureStorage.Default.Remove(Nombre); } catch (Exception) { /* sin clave en memoria y sin la guardada, lo cifrado ya es ilegible */ }
    }
#endif
}

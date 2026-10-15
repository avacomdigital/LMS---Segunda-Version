using System.Runtime.InteropServices;
using Avacom.Lms.Core.Reporting;
using Microsoft.Win32.SafeHandles;

namespace Avacom.Lms.Ops.Reportes;

/// <summary>
/// Lo que <see cref="EscrituraSegura"/> necesita del sistema de archivos, y nada más. Existe para que las pruebas puedan simular lo que un disco real hace de verdad pero no se puede
/// provocar a voluntad en un equipo de desarrollo: que se retire la memoria a mitad de una copia, que se llene, que otro proceso gane un nombre, que lo releído no sea lo escrito.
/// </summary>
public interface IOperacionesDeArchivo
{
    /// <summary>¿Existe esa carpeta? Con plazo: una ruta de red que no contesta es «no».</summary>
    bool ExisteCarpeta(string ruta);

    /// <summary>¿Hay ya un archivo o una carpeta con ese nombre?</summary>
    bool Existe(string ruta);

    /// <summary>Los bytes que se pueden escribir en esa carpeta (descontadas las cuotas), o null si no se pudo saber.</summary>
    long? EspacioLibre(string carpeta);

    /// <summary>Crea un archivo NUEVO para escribir (<c>FileMode.CreateNew</c>: si ya existe, falla), con acceso exclusivo y sin que la clase de flujo guarde nada en memoria aparte.</summary>
    Stream CrearNuevo(string ruta);

    /// <summary>Abre un archivo para leerlo tal como ESTÁ en la unidad, no como lo recuerda el sistema. Es la lectura con la que se verifica lo escrito.</summary>
    Stream AbrirLectura(string ruta);

    /// <summary>El tamaño que el sistema de archivos dice que tiene el archivo.</summary>
    long Tamano(string ruta);

    /// <summary>Cambia de nombre SIN sobrescribir: si el destino existe, lanza <see cref="IOException"/>.</summary>
    void MoverSinSobrescribir(string origen, string destino);

    /// <summary>Borra el archivo. No lanza si ya no existe.</summary>
    void Borrar(string ruta);

    /// <summary>Fuerza a que lo escrito (los datos y la entrada del directorio) llegue a la unidad.</summary>
    void VaciarADisco(string ruta);

    /// <summary>
    /// ¿La carpeta cuelga de una unidad de red MAPEADA a una letra («Z:\Reportes»)? Por el texto sólo se reconocen las rutas UNC; la letra la conoce el sistema. Sirve para decir «no se pudo
    /// llegar a esa carpeta de red» y no «se retiró la memoria» cuando una unidad mapeada se cae. Por omisión, no.
    /// </summary>
    bool EsUnidadDeRed(string carpeta) => false;
}

/// <summary>El sistema de archivos de verdad.</summary>
public sealed class OperacionesDeArchivoDelSistema : IOperacionesDeArchivo
{
    private static readonly TimeSpan PlazoParaExistir = TimeSpan.FromSeconds(5);

    public bool ExisteCarpeta(string ruta) => Existencia.DeCarpeta(ruta, PlazoParaExistir);

    public bool Existe(string ruta) => File.Exists(ruta) || Directory.Exists(ruta);

    public long? EspacioLibre(string carpeta)
    {
        try
        {
            if (OperatingSystem.IsWindows())
            {
                // GetDiskFreeSpaceEx sirve para cualquier carpeta, también una UNC (a la que DriveInfo no llega), y descuenta la cuota del usuario. Pide la barra final.
                var directorio = carpeta.EndsWith('\\') ? carpeta : carpeta + "\\";
                return GetDiskFreeSpaceExW(directorio, out var libre, out _, out _) ? (long)libre : null;
            }
            var raiz = Path.GetPathRoot(Path.GetFullPath(carpeta));
            return string.IsNullOrEmpty(raiz) ? null : new DriveInfo(raiz).AvailableFreeSpace;
        }
        catch
        {
            return null;
        }
    }

    // Sin búfer propio (los bloques de 80 KiB ya son lo bastante grandes) y asíncrono: así una cancelación interrumpe la escritura en curso en vez de esperar a que el sistema devuelva el control.
    public Stream CrearNuevo(string ruta) => new FileStream(ruta, FileMode.CreateNew, FileAccess.Write, FileShare.None, bufferSize: 0, FileOptions.Asynchronous);

    public Stream AbrirLectura(string ruta) => LecturaDeVerificacion.Abrir(ruta);

    public long Tamano(string ruta) => new FileInfo(ruta).Length;

    public void MoverSinSobrescribir(string origen, string destino) => File.Move(origen, destino, overwrite: false);

    public void Borrar(string ruta) => File.Delete(ruta);

    public bool EsUnidadDeRed(string carpeta)
    {
        try
        {
            var raiz = Path.GetPathRoot(carpeta);
            if (string.IsNullOrEmpty(raiz) || raiz.StartsWith(@"\\", StringComparison.Ordinal)) return false;           // una UNC ya la reconoce el texto
            return new DriveInfo(raiz).DriveType == DriveType.Network;
        }
        catch (Exception) { return false; }
    }

    public void VaciarADisco(string ruta)
    {
        using var archivo = new FileStream(ruta, FileMode.Open, FileAccess.Write, FileShare.Read, bufferSize: 0);
        archivo.Flush(flushToDisk: true);
    }

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetDiskFreeSpaceExW(string directorio, out ulong libreParaElUsuario, out ulong total, out ulong libreEnTotal);
}

/// <summary>
/// La lectura con la que se comprueba lo que quedó escrito. Releer un archivo recién escrito por el camino normal NO prueba nada de la unidad: Windows guarda en memoria lo que
/// acaba de escribir y lo devolvería de ahí aunque en la memoria USB hubiera otra cosa (o nada). Por eso se lee sin pasar por esa memoria (<c>FILE_FLAG_NO_BUFFERING</c>), que obliga a
/// pedirle los datos a la unidad. Si el sistema de archivos del destino no admite esa lectura (algunos recursos de red y de nube) se recurre a la normal: es mejor comprobar un poco menos
/// que no poder guardar.
/// </summary>
internal static class LecturaDeVerificacion
{
    public static Stream Abrir(string ruta)
    {
        if (OperatingSystem.IsWindows())
        {
            try { return LectorSinCache.Abrir(ruta); }
            catch (Exception e) when (SinSoporteDeLecturaDirecta(e)) { /* se sigue con la lectura normal */ }
        }
        return new FileStream(ruta, FileMode.Open, FileAccess.Read, FileShare.Read, bufferSize: 81_920, FileOptions.SequentialScan);
    }

    /// <summary>¿El fallo es «este sistema de archivos no sabe leer así» y no un fallo real de la unidad? (función no válida, no admitida, parámetro no válido.)</summary>
    internal static bool SinSoporteDeLecturaDirecta(Exception e) =>
        e is ArgumentException or NotSupportedException || (e is IOException && MotivosDeEscritura.CodigoDeWindows(e) is 1 or 50 or 87);
}

/// <summary>
/// Un flujo de sólo lectura que lee el archivo sin la memoria del sistema (<c>FILE_FLAG_NO_BUFFERING</c>), en bloques de 1 MiB. Esa lectura exige que cada petición empiece en un
/// múltiplo del tamaño de sector, mida un múltiplo de él y use un búfer alineado en memoria: se usa 4096 (vale para sectores de 512 y de 4096) y el búfer sale del montón de objetos
/// inmóviles, donde la dirección no cambia, alineado a mano. El último bloque suele traer menos (el archivo no mide un múltiplo de 4096): una lectura que termina a medio sector es el
/// final del archivo. No es posible desplazarse: sólo se lee de principio a fin.
/// </summary>
internal sealed class LectorSinCache : Stream
{
    private const FileOptions SinCache = (FileOptions)0x20000000;          // FILE_FLAG_NO_BUFFERING
    private const int Alineacion = 4096;
    private const int TamanoDeBloque = 1024 * 1024;                        // múltiplo de la alineación

    private readonly SafeFileHandle _archivo;
    private readonly byte[] _almacen;
    private readonly int _desplazamiento;
    private readonly long _longitud;
    private long _posicionEnElArchivo;
    private long _entregadosEnTotal;
    private int _validos;
    private int _entregados;
    private bool _terminado;

    private LectorSinCache(SafeFileHandle archivo)
    {
        _archivo = archivo;
        _longitud = RandomAccess.GetLength(archivo);
        _almacen = GC.AllocateUninitializedArray<byte>(TamanoDeBloque + Alineacion, pinned: true);
        var direccion = (long)Marshal.UnsafeAddrOfPinnedArrayElement(_almacen, 0);
        _desplazamiento = (int)((Alineacion - direccion % Alineacion) % Alineacion);
    }

    /// <summary>
    /// Abre el archivo y lee ya el primer bloque: si el sistema de archivos no admite la lectura directa, el error sale AQUÍ, donde quien llama todavía puede recurrir a la lectura normal,
    /// y no a mitad de una verificación.
    /// </summary>
    public static LectorSinCache Abrir(string ruta)
    {
        var archivo = File.OpenHandle(ruta, FileMode.Open, FileAccess.Read, FileShare.Read, SinCache | FileOptions.SequentialScan);
        try
        {
            var lector = new LectorSinCache(archivo);
            lector.LlenarBloque();
            return lector;
        }
        catch
        {
            archivo.Dispose();
            throw;
        }
    }

    private void LlenarBloque()
    {
        var leidos = RandomAccess.Read(_archivo, _almacen.AsSpan(_desplazamiento, TamanoDeBloque), _posicionEnElArchivo);
        _posicionEnElArchivo += leidos;
        _validos = leidos;
        _entregados = 0;
        // Sin datos, o terminando a medio sector, es el final: sólo ahí el sistema entrega un sector incompleto. (Y no se vuelve a pedir: el desplazamiento ya no estaría alineado.)
        if (leidos == 0 || leidos % Alineacion != 0) _terminado = true;
    }

    public override int Read(Span<byte> destino)
    {
        if (destino.IsEmpty) return 0;
        if (_entregados == _validos)
        {
            if (_terminado) return 0;
            LlenarBloque();
            if (_validos == 0) return 0;
        }
        var n = Math.Min(destino.Length, _validos - _entregados);
        _almacen.AsSpan(_desplazamiento + _entregados, n).CopyTo(destino);
        _entregados += n;
        _entregadosEnTotal += n;
        return n;
    }

    public override int Read(byte[] buffer, int offset, int count) => Read(buffer.AsSpan(offset, count));

    public override ValueTask<int> ReadAsync(Memory<byte> destino, CancellationToken ct = default)
    {
        ct.ThrowIfCancellationRequested();
        return ValueTask.FromResult(Read(destino.Span));
    }

    public override bool CanRead => true;
    public override bool CanSeek => false;
    public override bool CanWrite => false;
    public override long Length => _longitud;
    public override long Position { get => _entregadosEnTotal; set => throw new NotSupportedException(); }
    public override void Flush() { }
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();

    protected override void Dispose(bool disposing)
    {
        if (disposing) _archivo.Dispose();
        base.Dispose(disposing);
    }
}

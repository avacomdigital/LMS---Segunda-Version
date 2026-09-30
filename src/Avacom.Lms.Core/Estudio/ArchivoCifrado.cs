using System.Buffers.Binary;
using System.Security.Cryptography;
using Microsoft.Win32.SafeHandles;

namespace Avacom.Lms.Core.Estudio;

// Cifrado local de MOD-008 (BR-053, BR-054, JRN-022): nada de lo que el alumno descarga o escribe queda en claro en la tableta, y destruir la
// clave (IProveedorDeClave.Destruir) deja todo ilegible de un golpe. Hay dos formatos, los dos AES-256-GCM:
//
//  · ArchivoCifrado (EscritorCifrado / LectorCifrado)  medios grandes, por bloques de 64 KiB con acceso aleatorio (para servir Range) y
//    reanudables (la descarga se puede pausar y continuar sin volver a bajar ni a cifrar lo ya escrito).
//  · DocumentoCifrado                                  archivos pequeños de una sola pieza: la lista, el avance de cada tarea, el manifiesto,
//                                                      el estado de un paquete y la cola de eventos.
//
// Formato por bloques (todo en bytes):
//   cabecera (36)  "AVCE" · versión (1) · reservado (3) · longitud de bloque (4, LE) · prefijo de nonce aleatorio (8) · verificador (16)
//   bloque i       texto cifrado (hasta 64 KiB) · etiqueta GCM (16)      en el desplazamiento 36 + i·(65 536 + 16)
// El nonce de cada bloque es «prefijo · contador de bloque» (12 bytes): único por bloque y por archivo. El verificador es la etiqueta de un
// mensaje vacío con el contador reservado 0xFFFFFFFF y la cabecera como dato asociado: con él se distingue «clave equivocada» de «bloque
// alterado» y se detecta una cabecera manipulada. La longitud en claro se deduce del tamaño del archivo: sólo el último bloque puede ser corto.

/// <summary>Cualquier fallo al abrir o leer un archivo cifrado: quien guarda el archivo lo trata como ausente y lo aparta.</summary>
public class ArchivoCifradoException(string mensaje, Exception? interna = null) : Exception(mensaje, interna);

/// <summary>La clave no abre este archivo (la clave se destruyó o es de otra instalación) o la cabecera no coincide con su verificador.</summary>
public sealed class ClaveIncorrectaException(string mensaje) : ArchivoCifradoException(mensaje);

/// <summary>Una etiqueta de autenticación no coincide: el contenido fue alterado, está truncado o está dañado. Nunca se entrega lo que no autentica.</summary>
public sealed class ManipulacionDetectadaException(string mensaje, Exception? interna = null) : ArchivoCifradoException(mensaje, interna);

/// <summary>Constantes, cálculos de longitud y utilidades del formato de archivo cifrado por bloques.</summary>
public static class ArchivoCifrado
{
    /// <summary>Bytes en claro por bloque (64 KiB).</summary>
    public const int LongitudBloque = 64 * 1024;
    public const int LongitudEtiqueta = 16;
    public const int LongitudClave = 32;

    internal const int LongitudNonce = 12;
    internal const int LongitudPrefijo = 8;
    internal const int LongitudCabecera = 36;
    internal const int LongitudBloqueSellado = LongitudBloque + LongitudEtiqueta;

    private const int LongitudAutenticada = 20;               // firma · versión · reservado · longitud de bloque · prefijo
    private const uint ContadorDelVerificador = uint.MaxValue;   // reservado: ningún bloque lo usa
    private const byte Version = 1;
    private static ReadOnlySpan<byte> Firma => "AVCE"u8;

    /// <summary>Los bytes en claro que contiene un archivo cifrado de ese tamaño. Lanza si el tamaño no puede ser el de un archivo íntegro.</summary>
    public static long LongitudEnClaro(long longitudDelArchivo)
    {
        var carga = longitudDelArchivo - LongitudCabecera;
        if (carga < 0) throw new ManipulacionDetectadaException("El archivo cifrado está incompleto: falta la cabecera.");
        var completos = carga / LongitudBloqueSellado;
        var resto = carga % LongitudBloqueSellado;
        if (resto == 0) return completos * LongitudBloque;
        if (resto <= LongitudEtiqueta) throw new ManipulacionDetectadaException("El archivo cifrado termina en un bloque incompleto.");
        return completos * LongitudBloque + (resto - LongitudEtiqueta);
    }

    /// <summary>El tamaño en disco de un archivo cerrado con esa cantidad de bytes en claro (para calcular el espacio que hace falta).</summary>
    public static long LongitudDelArchivo(long longitudEnClaro)
    {
        var bloques = (longitudEnClaro + LongitudBloque - 1) / LongitudBloque;
        return LongitudCabecera + longitudEnClaro + bloques * LongitudEtiqueta;
    }

    /// <summary>
    /// Los bytes en claro de los bloques COMPLETOS de un archivo a medio escribir, según su tamaño (sin descifrar nada, sin lanzar): lo que
    /// una descarga en curso ya tiene a salvo en disco.
    /// </summary>
    public static long BytesDeBloquesCompletos(long longitudDelArchivo) =>
        Math.Max(0, longitudDelArchivo - LongitudCabecera) / LongitudBloqueSellado * LongitudBloque;

    /// <summary>Un <see cref="Stream"/> de sólo lectura, con <c>Seek</c>, sobre el archivo descifrado al vuelo. Liberarlo cierra el archivo.</summary>
    public static Stream AbrirLectura(string ruta, byte[] clave) => LectorCifrado.Abrir(ruta, clave).AbrirStream();

    /// <summary>Recalcula el SHA-256 (hexadecimal en minúsculas) del contenido en claro releyendo y descifrando el archivo completo.</summary>
    public static string Sha256DeContenido(string ruta, byte[] clave)
    {
        using var lector = LectorCifrado.Abrir(ruta, clave);
        using var sha = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        var buffer = new byte[LongitudBloque];
        long posicion = 0;
        while (true)
        {
            var n = lector.Leer(posicion, buffer);
            if (n == 0) break;
            sha.AppendData(buffer.AsSpan(0, n));
            posicion += n;
        }
        return Convert.ToHexStringLower(sha.GetCurrentHash());
    }

    // ---------------------------------------------------------------- lo que comparten escritor y lector

    internal static void ValidarClave(byte[] clave)
    {
        ArgumentNullException.ThrowIfNull(clave);
        if (clave.Length != LongitudClave) throw new ArgumentException($"La clave debe tener {LongitudClave} bytes.", nameof(clave));
    }

    internal static void ArmarNonce(ReadOnlySpan<byte> prefijo, uint contador, Span<byte> nonce)
    {
        prefijo.CopyTo(nonce);
        BinaryPrimitives.WriteUInt32BigEndian(nonce[LongitudPrefijo..], contador);
    }

    internal static void ArmarCabecera(AesGcm aes, ReadOnlySpan<byte> prefijo, Span<byte> cabecera)
    {
        cabecera.Clear();
        Firma.CopyTo(cabecera);
        cabecera[4] = Version;
        BinaryPrimitives.WriteUInt32LittleEndian(cabecera[8..], LongitudBloque);
        prefijo.CopyTo(cabecera[12..]);
        Span<byte> nonce = stackalloc byte[LongitudNonce];
        ArmarNonce(prefijo, ContadorDelVerificador, nonce);
        aes.Encrypt(nonce, ReadOnlySpan<byte>.Empty, Span<byte>.Empty, cabecera.Slice(LongitudAutenticada, LongitudEtiqueta), cabecera[..LongitudAutenticada]);
    }

    /// <summary>Comprueba firma, versión y verificador de la cabecera y entrega el prefijo de nonce del archivo.</summary>
    internal static void VerificarCabecera(ReadOnlySpan<byte> cabecera, AesGcm aes, Span<byte> prefijo)
    {
        if (!cabecera[..4].SequenceEqual(Firma)) throw new ArchivoCifradoException("No es un archivo cifrado de AVACOM.");
        if (cabecera[4] != Version) throw new ArchivoCifradoException($"Versión de formato no soportada ({cabecera[4]}).");
        if (BinaryPrimitives.ReadUInt32LittleEndian(cabecera[8..]) != LongitudBloque) throw new ArchivoCifradoException("Longitud de bloque no soportada.");
        cabecera.Slice(12, LongitudPrefijo).CopyTo(prefijo);
        Span<byte> nonce = stackalloc byte[LongitudNonce];
        ArmarNonce(prefijo, ContadorDelVerificador, nonce);
        try
        {
            aes.Decrypt(nonce, ReadOnlySpan<byte>.Empty, cabecera.Slice(LongitudAutenticada, LongitudEtiqueta), Span<byte>.Empty, cabecera[..LongitudAutenticada]);
        }
        catch (CryptographicException)
        {
            throw new ClaveIncorrectaException("La clave no abre este archivo (o su cabecera fue alterada).");
        }
    }

    internal static void LeerExacto(SafeFileHandle archivo, Span<byte> destino, long posicion)
    {
        var hecho = 0;
        while (hecho < destino.Length)
        {
            var n = RandomAccess.Read(archivo, destino[hecho..], posicion + hecho);
            if (n == 0) throw new ManipulacionDetectadaException("El archivo cifrado se truncó mientras se leía.");
            hecho += n;
        }
    }
}

/// <summary>
/// Escribe un archivo cifrado por bloques, en orden. Sólo los bloques COMPLETOS llegan a disco mientras se escribe: la cola parcial vive en
/// memoria y se cifra en <see cref="Cerrar"/>; si el proceso muere antes, lo que queda en disco son bloques íntegros y <see cref="Reanudar"/>
/// continúa desde ahí. Calcula a la vez el SHA-256 del contenido en claro (<see cref="Sha256Hex"/>) para que quien descarga verifique sin releer.
///
/// Un <see cref="Dispose"/> sin <see cref="Cerrar"/> es una PAUSA: no escribe la cola ni borra nada.
/// </summary>
public sealed class EscritorCifrado : IDisposable
{
    private readonly SafeFileHandle archivo;
    private readonly AesGcm aes;
    private readonly byte[] prefijo;
    private readonly byte[] pendiente = new byte[ArchivoCifrado.LongitudBloque];          // texto en claro que aún no completa un bloque
    private readonly byte[] sellado = new byte[ArchivoCifrado.LongitudBloqueSellado];     // texto cifrado + etiqueta de un bloque
    private readonly IncrementalHash hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
    private int enPendiente;
    private long bloquesEscritos;
    private long total;
    private bool cerrado;
    private bool roto;
    private bool liberado;

    private EscritorCifrado(SafeFileHandle archivo, AesGcm aes, byte[] prefijo)
    {
        this.archivo = archivo;
        this.aes = aes;
        this.prefijo = prefijo;
    }

    /// <summary>Los bytes en claro que ya se aceptaron (incluida la cola que aún no está en disco). Tras <see cref="Reanudar"/>: lo que ya había.</summary>
    public long BytesEnClaro => total;

    /// <summary>Los bytes en claro que ya están a salvo en disco (sólo bloques completos): desde aquí se reanudaría tras un corte.</summary>
    public long BytesPersistidos => bloquesEscritos * ArchivoCifrado.LongitudBloque;

    /// <summary>Crea (o reemplaza) el archivo con una cabecera nueva y un prefijo de nonce aleatorio.</summary>
    public static EscritorCifrado Crear(string ruta, byte[] clave)
    {
        ArchivoCifrado.ValidarClave(clave);
        var carpeta = Path.GetDirectoryName(Path.GetFullPath(ruta));
        if (!string.IsNullOrEmpty(carpeta)) Directory.CreateDirectory(carpeta);
        var aes = new AesGcm(clave, ArchivoCifrado.LongitudEtiqueta);
        SafeFileHandle? archivo = null;
        try
        {
            var prefijo = RandomNumberGenerator.GetBytes(ArchivoCifrado.LongitudPrefijo);
            archivo = File.OpenHandle(ruta, FileMode.Create, FileAccess.ReadWrite, FileShare.Read | FileShare.Delete);
            Span<byte> cabecera = stackalloc byte[ArchivoCifrado.LongitudCabecera];
            ArchivoCifrado.ArmarCabecera(aes, prefijo, cabecera);
            RandomAccess.Write(archivo, cabecera, 0);
            return new EscritorCifrado(archivo, aes, prefijo);
        }
        catch
        {
            archivo?.Dispose();
            aes.Dispose();
            throw;
        }
    }

    /// <summary>
    /// Continúa un archivo a medio escribir: verifica la cabecera y CADA bloque ya escrito (y con ellos recalcula el SHA-256 de lo que había),
    /// descarta lo que sobre después del último bloque íntegro (una escritura rota por un corte) y deja el escritor listo para seguir agregando.
    /// Si lo que había terminaba en una cola corta pero íntegra (un archivo ya cerrado) la recupera en memoria. <see cref="BytesEnClaro"/> dice
    /// cuánto había. Lanza <see cref="ClaveIncorrectaException"/> con otra clave y <see cref="ManipulacionDetectadaException"/> si un bloque del
    /// medio no autentica: quien descarga entonces empieza de cero.
    /// </summary>
    public static EscritorCifrado Reanudar(string ruta, byte[] clave)
    {
        ArchivoCifrado.ValidarClave(clave);
        var aes = new AesGcm(clave, ArchivoCifrado.LongitudEtiqueta);
        SafeFileHandle? archivo = null;
        try
        {
            archivo = File.OpenHandle(ruta, FileMode.Open, FileAccess.ReadWrite, FileShare.Read | FileShare.Delete);
            var longitud = RandomAccess.GetLength(archivo);
            if (longitud < ArchivoCifrado.LongitudCabecera) throw new ArchivoCifradoException("La cabecera del archivo cifrado está incompleta.");
            Span<byte> cabecera = stackalloc byte[ArchivoCifrado.LongitudCabecera];
            ArchivoCifrado.LeerExacto(archivo, cabecera, 0);
            var prefijo = new byte[ArchivoCifrado.LongitudPrefijo];
            ArchivoCifrado.VerificarCabecera(cabecera, aes, prefijo);
            var escritor = new EscritorCifrado(archivo, aes, prefijo);
            try { escritor.Recuperar(longitud); }
            catch { escritor.Dispose(); throw; }
            return escritor;
        }
        catch
        {
            archivo?.Dispose();
            aes.Dispose();
            throw;
        }
    }

    private static long PosicionDe(long bloque) => ArchivoCifrado.LongitudCabecera + bloque * ArchivoCifrado.LongitudBloqueSellado;

    private void Recuperar(long longitud)
    {
        var carga = longitud - ArchivoCifrado.LongitudCabecera;
        var completos = carga / ArchivoCifrado.LongitudBloqueSellado;
        var resto = carga % ArchivoCifrado.LongitudBloqueSellado;
        Span<byte> nonce = stackalloc byte[ArchivoCifrado.LongitudNonce];
        for (long i = 0; i < completos; i++)
        {
            ArchivoCifrado.LeerExacto(archivo, sellado, PosicionDe(i));
            ArchivoCifrado.ArmarNonce(prefijo, (uint)i, nonce);
            if (!Descifrar(nonce, sellado.AsSpan(0, ArchivoCifrado.LongitudBloque), sellado.AsSpan(ArchivoCifrado.LongitudBloque, ArchivoCifrado.LongitudEtiqueta), pendiente))
            {
                // Un bloque entero que no autentica y es lo último que hay puede ser una escritura rota por un corte de energía (el sistema
                // alargó el archivo sin llegar a grabar los datos): se descarta. Si detrás hay más, alguien tocó lo ya escrito.
                if (i == completos - 1 && resto == 0)
                {
                    bloquesEscritos = i;
                    Truncar();
                    return;
                }
                throw new ManipulacionDetectadaException($"El bloque {i} ya escrito no pasa la verificación: el archivo fue alterado o está dañado.");
            }
            hash.AppendData(pendiente);
            total += ArchivoCifrado.LongitudBloque;
            bloquesEscritos = i + 1;
        }
        if (resto > ArchivoCifrado.LongitudEtiqueta)
        {
            // Una cola corta: si autentica, es lo último de un archivo cerrado y se recupera (se volverá a cifrar con el mismo nonce y el mismo
            // contenido, o se completará hasta un bloque); si no, es una escritura rota y se descarta.
            var largo = (int)(resto - ArchivoCifrado.LongitudEtiqueta);
            ArchivoCifrado.LeerExacto(archivo, sellado.AsSpan(0, (int)resto), PosicionDe(completos));
            ArchivoCifrado.ArmarNonce(prefijo, (uint)completos, nonce);
            if (Descifrar(nonce, sellado.AsSpan(0, largo), sellado.AsSpan(largo, ArchivoCifrado.LongitudEtiqueta), pendiente.AsSpan(0, largo)))
            {
                enPendiente = largo;
                hash.AppendData(pendiente.AsSpan(0, largo));
                total += largo;
            }
        }
        Truncar();
    }

    private bool Descifrar(ReadOnlySpan<byte> nonce, ReadOnlySpan<byte> cifrado, ReadOnlySpan<byte> etiqueta, Span<byte> claro)
    {
        try
        {
            aes.Decrypt(nonce, cifrado, etiqueta, claro);
            return true;
        }
        catch (CryptographicException)
        {
            return false;
        }
    }

    /// <summary>Deja el archivo justo después del último bloque completo: lo que sobraba se vuelve a escribir al seguir.</summary>
    private void Truncar()
    {
        var fin = PosicionDe(bloquesEscritos);
        if (RandomAccess.GetLength(archivo) != fin) RandomAccess.SetLength(archivo, fin);
    }

    /// <summary>Agrega bytes en claro al final. Cada vez que se completa un bloque se cifra y se escribe.</summary>
    public void Escribir(ReadOnlySpan<byte> datos)
    {
        Comprobar();
        hash.AppendData(datos);
        total += datos.Length;
        while (!datos.IsEmpty)
        {
            if (enPendiente == 0 && datos.Length >= ArchivoCifrado.LongitudBloque)
            {
                SellarBloque(datos[..ArchivoCifrado.LongitudBloque]);       // un bloque entero: se cifra sin pasar por la cola
                datos = datos[ArchivoCifrado.LongitudBloque..];
                continue;
            }
            var caben = Math.Min(datos.Length, ArchivoCifrado.LongitudBloque - enPendiente);
            datos[..caben].CopyTo(pendiente.AsSpan(enPendiente));
            enPendiente += caben;
            datos = datos[caben..];
            if (enPendiente == ArchivoCifrado.LongitudBloque)
            {
                SellarBloque(pendiente);
                enPendiente = 0;
            }
        }
    }

    private void SellarBloque(ReadOnlySpan<byte> claro)
    {
        try
        {
            if (bloquesEscritos >= uint.MaxValue) throw new InvalidOperationException("El archivo supera el máximo de bloques del formato.");
            Span<byte> nonce = stackalloc byte[ArchivoCifrado.LongitudNonce];
            ArchivoCifrado.ArmarNonce(prefijo, (uint)bloquesEscritos, nonce);
            aes.Encrypt(nonce, claro, sellado.AsSpan(0, claro.Length), sellado.AsSpan(claro.Length, ArchivoCifrado.LongitudEtiqueta));
            RandomAccess.Write(archivo, sellado.AsSpan(0, claro.Length + ArchivoCifrado.LongitudEtiqueta), PosicionDe(bloquesEscritos));
            bloquesEscritos++;
        }
        catch
        {
            roto = true;   // el hash y los contadores ya no coinciden con el disco: este escritor no sirve más (se reanuda con otro)
            throw;
        }
    }

    /// <summary>Escribe la cola parcial como último bloque y asegura el archivo en disco. Después ya no se puede escribir.</summary>
    public void Cerrar()
    {
        if (cerrado) return;
        Comprobar();
        if (enPendiente > 0)
        {
            SellarBloque(pendiente.AsSpan(0, enPendiente));
            enPendiente = 0;
        }
        RandomAccess.FlushToDisk(archivo);
        cerrado = true;
    }

    /// <summary>El SHA-256 (hexadecimal en minúsculas) de TODO lo aceptado hasta ahora; tras <see cref="Reanudar"/> incluye lo que ya había.</summary>
    public string Sha256Hex()
    {
        ObjectDisposedException.ThrowIf(liberado, this);
        return Convert.ToHexStringLower(hash.GetCurrentHash());
    }

    private void Comprobar()
    {
        ObjectDisposedException.ThrowIf(liberado, this);
        if (cerrado) throw new InvalidOperationException("El archivo cifrado ya se cerró.");
        if (roto) throw new InvalidOperationException("Una escritura anterior falló: hay que reanudar el archivo con otro escritor.");
    }

    public void Dispose()
    {
        if (liberado) return;
        liberado = true;
        archivo.Dispose();
        aes.Dispose();
        hash.Dispose();
        CryptographicOperations.ZeroMemory(pendiente);
    }
}

/// <summary>
/// Lee un archivo cifrado por bloques con acceso aleatorio: cada lectura descifra sólo los bloques que toca (y recuerda el último), así que se
/// puede servir un <c>Range</c> del medio o saltar en un video sin cargar el archivo entero. Un bloque que no autentica lanza
/// <see cref="ManipulacionDetectadaException"/> y nunca entrega su contenido. Una instancia no es para varios hilos a la vez: cada lector abre la suya.
/// </summary>
public sealed class LectorCifrado : IDisposable
{
    private readonly SafeFileHandle archivo;
    private readonly AesGcm aes;
    private readonly byte[] prefijo;
    private readonly byte[] sellado = new byte[ArchivoCifrado.LongitudBloqueSellado];
    private readonly byte[] claro = new byte[ArchivoCifrado.LongitudBloque];
    private long bloqueEnCache = -1;
    private bool liberado;

    private LectorCifrado(SafeFileHandle archivo, AesGcm aes, byte[] prefijo, long longitud)
    {
        this.archivo = archivo;
        this.aes = aes;
        this.prefijo = prefijo;
        Longitud = longitud;
    }

    /// <summary>Los bytes en claro del archivo, deducidos de su tamaño.</summary>
    public long Longitud { get; }

    /// <summary>
    /// Abre el archivo y comprueba su cabecera con la clave: <see cref="ClaveIncorrectaException"/> si no es la suya,
    /// <see cref="ArchivoCifradoException"/> si no es un archivo de este formato o <see cref="ManipulacionDetectadaException"/> si su tamaño es imposible.
    /// </summary>
    public static LectorCifrado Abrir(string ruta, byte[] clave)
    {
        ArchivoCifrado.ValidarClave(clave);
        var aes = new AesGcm(clave, ArchivoCifrado.LongitudEtiqueta);
        SafeFileHandle? archivo = null;
        try
        {
            // FileShare.Delete: el almacén puede borrar o reemplazar el archivo (retirar el paquete) aunque haya un visor leyéndolo.
            archivo = File.OpenHandle(ruta, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete, FileOptions.RandomAccess);
            var longitud = RandomAccess.GetLength(archivo);
            if (longitud < ArchivoCifrado.LongitudCabecera) throw new ArchivoCifradoException("La cabecera del archivo cifrado está incompleta.");
            Span<byte> cabecera = stackalloc byte[ArchivoCifrado.LongitudCabecera];
            ArchivoCifrado.LeerExacto(archivo, cabecera, 0);
            var prefijo = new byte[ArchivoCifrado.LongitudPrefijo];
            ArchivoCifrado.VerificarCabecera(cabecera, aes, prefijo);
            return new LectorCifrado(archivo, aes, prefijo, ArchivoCifrado.LongitudEnClaro(longitud));
        }
        catch
        {
            archivo?.Dispose();
            aes.Dispose();
            throw;
        }
    }

    /// <summary>Lee hasta <c>destino.Length</c> bytes desde <paramref name="posicion"/>. Devuelve cuántos leyó (0 al llegar al final).</summary>
    public int Leer(long posicion, Span<byte> destino)
    {
        ObjectDisposedException.ThrowIf(liberado, this);
        ArgumentOutOfRangeException.ThrowIfNegative(posicion);
        if (posicion >= Longitud || destino.IsEmpty) return 0;
        var total = (int)Math.Min(destino.Length, Longitud - posicion);
        var hecho = 0;
        while (hecho < total)
        {
            var actual = posicion + hecho;
            var indice = actual / ArchivoCifrado.LongitudBloque;
            var dentro = (int)(actual % ArchivoCifrado.LongitudBloque);
            var largoDelBloque = (int)Math.Min(ArchivoCifrado.LongitudBloque, Longitud - indice * ArchivoCifrado.LongitudBloque);
            var quiero = Math.Min(total - hecho, largoDelBloque - dentro);
            if (dentro == 0 && quiero == largoDelBloque)
            {
                DescifrarBloque(indice, largoDelBloque, destino.Slice(hecho, largoDelBloque));   // el bloque cabe entero: directo al destino
            }
            else
            {
                if (bloqueEnCache != indice)
                {
                    bloqueEnCache = -1;
                    DescifrarBloque(indice, largoDelBloque, claro);
                    bloqueEnCache = indice;
                }
                claro.AsSpan(dentro, quiero).CopyTo(destino[hecho..]);
            }
            hecho += quiero;
        }
        return hecho;
    }

    private void DescifrarBloque(long indice, int largo, Span<byte> destino)
    {
        ArchivoCifrado.LeerExacto(archivo, sellado.AsSpan(0, largo + ArchivoCifrado.LongitudEtiqueta),
                                  ArchivoCifrado.LongitudCabecera + indice * ArchivoCifrado.LongitudBloqueSellado);
        Span<byte> nonce = stackalloc byte[ArchivoCifrado.LongitudNonce];
        ArchivoCifrado.ArmarNonce(prefijo, (uint)indice, nonce);
        try
        {
            aes.Decrypt(nonce, sellado.AsSpan(0, largo), sellado.AsSpan(largo, ArchivoCifrado.LongitudEtiqueta), destino[..largo]);
        }
        catch (CryptographicException ex)
        {
            throw new ManipulacionDetectadaException($"El bloque {indice} no pasa la verificación: el archivo fue alterado o está dañado.", ex);
        }
    }

    /// <summary>Un <see cref="Stream"/> de sólo lectura con <c>Seek</c>. Liberar el flujo libera este lector: después no se usa el lector suelto.</summary>
    public Stream AbrirStream() => new FlujoDeLectura(this);

    public void Dispose()
    {
        if (liberado) return;
        liberado = true;
        archivo.Dispose();
        aes.Dispose();
        CryptographicOperations.ZeroMemory(claro);
    }

    private sealed class FlujoDeLectura(LectorCifrado lector) : Stream
    {
        private long posicion;

        public override bool CanRead => true;
        public override bool CanSeek => true;
        public override bool CanWrite => false;
        public override long Length => lector.Longitud;

        public override long Position
        {
            get => posicion;
            set
            {
                ArgumentOutOfRangeException.ThrowIfNegative(value);
                posicion = value;
            }
        }

        public override int Read(byte[] buffer, int offset, int count) => Read(buffer.AsSpan(offset, count));

        public override int Read(Span<byte> destino)
        {
            var n = lector.Leer(posicion, destino);
            posicion += n;
            return n;
        }

        public override Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            return Task.FromResult(Read(buffer.AsSpan(offset, count)));
        }

        public override ValueTask<int> ReadAsync(Memory<byte> destino, CancellationToken ct = default)
        {
            ct.ThrowIfCancellationRequested();
            return ValueTask.FromResult(Read(destino.Span));
        }

        public override long Seek(long desplazamiento, SeekOrigin origen)
        {
            var nueva = origen switch
            {
                SeekOrigin.Begin => desplazamiento,
                SeekOrigin.Current => posicion + desplazamiento,
                SeekOrigin.End => lector.Longitud + desplazamiento,
                _ => throw new ArgumentOutOfRangeException(nameof(origen)),
            };
            if (nueva < 0) throw new IOException("No se puede posicionar antes del inicio del archivo.");
            posicion = nueva;
            return nueva;
        }

        public override void Flush() { }
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();

        protected override void Dispose(bool disposing)
        {
            if (disposing) lector.Dispose();
            base.Dispose(disposing);
        }
    }
}

/// <summary>
/// Un documento pequeño cifrado de una sola pieza (la lista de pendientes, el avance de una tarea, el manifiesto, la cola de eventos):
/// «AVCD» · versión · nonce aleatorio · etiqueta · texto cifrado. El <c>contexto</c> viaja como dato asociado: un documento sólo abre en el
/// lugar para el que se selló (copiar el archivo de un alumno a la carpeta de otro, o el de una tarea a otra, no autentica).
/// </summary>
public static class DocumentoCifrado
{
    private const int LongitudCabecera = 4 + 1 + ArchivoCifrado.LongitudNonce + ArchivoCifrado.LongitudEtiqueta;
    private const byte Version = 1;
    private static ReadOnlySpan<byte> Firma => "AVCD"u8;

    public static byte[] Sellar(ReadOnlySpan<byte> claroEntrada, byte[] clave, ReadOnlySpan<byte> contexto)
    {
        ArchivoCifrado.ValidarClave(clave);
        var resultado = new byte[LongitudCabecera + claroEntrada.Length];
        Firma.CopyTo(resultado);
        resultado[4] = Version;
        var nonce = resultado.AsSpan(5, ArchivoCifrado.LongitudNonce);
        RandomNumberGenerator.Fill(nonce);
        using var aes = new AesGcm(clave, ArchivoCifrado.LongitudEtiqueta);
        aes.Encrypt(nonce, claroEntrada, resultado.AsSpan(LongitudCabecera), resultado.AsSpan(5 + ArchivoCifrado.LongitudNonce, ArchivoCifrado.LongitudEtiqueta), contexto);
        return resultado;
    }

    /// <summary>Descifra y autentica. Lanza <see cref="ArchivoCifradoException"/> si no es un documento de este formato y
    /// <see cref="ManipulacionDetectadaException"/> si la etiqueta no coincide (contenido alterado, contexto distinto o clave destruida).</summary>
    public static byte[] Abrir(ReadOnlySpan<byte> sellado, byte[] clave, ReadOnlySpan<byte> contexto)
    {
        ArchivoCifrado.ValidarClave(clave);
        if (sellado.Length < LongitudCabecera || !sellado[..4].SequenceEqual(Firma) || sellado[4] != Version)
            throw new ArchivoCifradoException("No es un documento cifrado de AVACOM.");
        var nonce = sellado.Slice(5, ArchivoCifrado.LongitudNonce);
        var etiqueta = sellado.Slice(5 + ArchivoCifrado.LongitudNonce, ArchivoCifrado.LongitudEtiqueta);
        var claroSalida = new byte[sellado.Length - LongitudCabecera];
        try
        {
            using var aes = new AesGcm(clave, ArchivoCifrado.LongitudEtiqueta);
            aes.Decrypt(nonce, sellado[LongitudCabecera..], etiqueta, claroSalida, contexto);
            return claroSalida;
        }
        catch (CryptographicException ex)
        {
            CryptographicOperations.ZeroMemory(claroSalida);
            throw new ManipulacionDetectadaException("El documento no pasa la verificación: fue alterado, es de otro lugar o su clave ya no existe.", ex);
        }
    }
}

/// <summary>Escritura de archivos pequeños sin dejar nunca uno a medias: temporal + reemplazo (como <c>ColaRespuestas</c>).</summary>
internal static class ArchivosLocales
{
    public static void EscribirAtomico(string ruta, byte[] contenido)
    {
        var carpeta = Path.GetDirectoryName(Path.GetFullPath(ruta));
        if (!string.IsNullOrEmpty(carpeta)) Directory.CreateDirectory(carpeta);
        var temporal = $"{ruta}.{Guid.NewGuid():N}.tmp";
        try
        {
            using (var archivo = new FileStream(temporal, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                archivo.Write(contenido);
                archivo.Flush(flushToDisk: true);
            }
            // Un antivirus o el indexador de Windows pueden tener el archivo abierto un instante: el reemplazo se reintenta un par de veces antes de rendirse.
            for (var intento = 1; ; intento++)
            {
                try
                {
                    File.Move(temporal, ruta, overwrite: true);
                    break;
                }
                catch (Exception ex) when (intento < 5 && ex is IOException or UnauthorizedAccessException)
                {
                    Thread.Sleep(30 * intento);
                }
            }
        }
        catch
        {
            try { File.Delete(temporal); } catch { /* el temporal huérfano no estorba: tiene otro nombre en cada intento */ }
            throw;
        }
    }

    /// <summary>Aparta un archivo que no se puede leer (<c>.dañado</c>, como la cola de respuestas) para empezar de cero sin perderlo del todo.</summary>
    public static void Apartar(string ruta)
    {
        try { File.Move(ruta, ruta + ".dañado", overwrite: true); }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            try { File.Delete(ruta); } catch { /* si ni siquiera se puede borrar, se intentará de nuevo la próxima vez */ }
        }
    }
}

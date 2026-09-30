using System.Security.Cryptography;
using System.Text;
using Avacom.Lms.Core.Estudio;

namespace Avacom.Lms.Core.Tests;

/// <summary>El archivo cifrado por bloques (AES-256-GCM, 64 KiB): ida y vuelta, acceso aleatorio, manipulación, clave y reanudación tras un corte.</summary>
public sealed class ArchivoCifradoTests : IDisposable
{
    private const int B = ArchivoCifrado.LongitudBloque;
    private const int Cabecera = 36;
    private const int Sellado = B + ArchivoCifrado.LongitudEtiqueta;
    private static readonly byte[] Clave = Enumerable.Range(1, 32).Select(i => (byte)i).ToArray();
    private static readonly byte[] OtraClave = Enumerable.Range(101, 32).Select(i => (byte)i).ToArray();

    private readonly string carpeta = Ayudas.CarpetaTemporal();
    private string Ruta(string nombre = "medio.avc") => Path.Combine(carpeta, nombre);
    public void Dispose() { try { Directory.Delete(carpeta, true); } catch { } }

    /// <summary>Escribe los datos por trozos del tamaño pedido y cierra; devuelve el SHA-256 que calculó el propio escritor.</summary>
    private string Escribir(byte[] datos, string ruta, int trozo = 7000)
    {
        using var escritor = EscritorCifrado.Crear(ruta, Clave);
        for (var i = 0; i < datos.Length; i += trozo) escritor.Escribir(datos.AsSpan(i, Math.Min(trozo, datos.Length - i)));
        escritor.Cerrar();
        return escritor.Sha256Hex();
    }

    private static void Alterar(string ruta, long posicion)
    {
        var bytes = File.ReadAllBytes(ruta);
        bytes[posicion] ^= 0x01;
        File.WriteAllBytes(ruta, bytes);
    }

    // ------------------------------------------------------------------------ ida y vuelta

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(B - 1)]
    [InlineData(B)]
    [InlineData(B + 1)]
    [InlineData(2 * B)]
    [InlineData(3 * B + 123)]
    public void IdaYVuelta_ConCualquierLongitud_DevuelveLoMismoYMideLoEsperado(int longitud)
    {
        var datos = EstudioAyudas.Datos(longitud);
        var sha = Escribir(datos, Ruta());

        Assert.Equal(ArchivoCifrado.LongitudDelArchivo(longitud), new FileInfo(Ruta()).Length);
        Assert.Equal(longitud, ArchivoCifrado.LongitudEnClaro(new FileInfo(Ruta()).Length));
        using var lector = LectorCifrado.Abrir(Ruta(), Clave);
        Assert.Equal(longitud, lector.Longitud);
        using var flujo = ArchivoCifrado.AbrirLectura(Ruta(), Clave);
        Assert.Equal(longitud, flujo.Length);
        Assert.Equal(datos, EstudioAyudas.LeerTodo(flujo));
        Assert.Equal(EstudioAyudas.Sha256(datos), sha);
        Assert.Equal(sha, ArchivoCifrado.Sha256DeContenido(Ruta(), Clave));
    }

    [Fact]
    public void UnaEscrituraGrande_EnUnSoloTrozo_TambienIdaYVuelta()
    {
        var datos = EstudioAyudas.Datos(5 * B + 77, 9);
        Escribir(datos, Ruta(), trozo: datos.Length);
        using var flujo = ArchivoCifrado.AbrirLectura(Ruta(), Clave);
        Assert.Equal(datos, EstudioAyudas.LeerTodo(flujo));
    }

    [Fact]
    public void LosTamanosImposibles_SeRechazan()
    {
        Assert.Throws<ManipulacionDetectadaException>(() => ArchivoCifrado.LongitudEnClaro(Cabecera - 1));
        Assert.Throws<ManipulacionDetectadaException>(() => ArchivoCifrado.LongitudEnClaro(Cabecera + 5));               // ni siquiera cabe una etiqueta
        Assert.Throws<ManipulacionDetectadaException>(() => ArchivoCifrado.LongitudEnClaro(Cabecera + Sellado + 16));    // un bloque siguiente sin contenido
        Assert.Equal(0, ArchivoCifrado.LongitudEnClaro(Cabecera));
        Assert.Equal(1, ArchivoCifrado.LongitudEnClaro(Cabecera + 17));
        Assert.Equal(B + 1, ArchivoCifrado.LongitudEnClaro(Cabecera + Sellado + 17));
    }

    [Fact]
    public void NoDejaTextoEnClaroEnElDisco_Ni_ElMismoContenidoDaElMismoArchivo()
    {
        var marca = Encoding.UTF8.GetBytes("MARCA-SECRETA-DE-LA-LECCION");
        var datos = Enumerable.Range(0, 5000).SelectMany(_ => marca).ToArray();     // ~135 KB de una marca repetida
        Escribir(datos, Ruta("a.avc"));
        Escribir(datos, Ruta("b.avc"));
        var a = File.ReadAllBytes(Ruta("a.avc"));
        var b = File.ReadAllBytes(Ruta("b.avc"));
        Assert.False(EstudioAyudas.Contiene(a, marca));
        Assert.False(EstudioAyudas.Contiene(a, marca[..8]));
        Assert.NotEqual(a, b);                                                       // prefijo de nonce aleatorio por archivo
        Assert.Equal(a.Length, b.Length);
    }

    // ------------------------------------------------------------------- acceso aleatorio

    [Fact]
    public void AccesoAleatorio_EnLosBordesDeBloque_LeeExactamenteLoPedido()
    {
        var datos = EstudioAyudas.Datos(3 * B + 500, 3);
        Escribir(datos, Ruta());
        using var lector = LectorCifrado.Abrir(Ruta(), Clave);
        (long Posicion, int Cantidad)[] casos =
        [
            (0, 1), (0, 10), (B - 1, 2), (B, 1), (B - 1, 1), (2 * B - 3, 6), (2 * B, B), (3 * B - 1, 2), (3 * B, 500), (3 * B + 499, 1), (10, 2 * B + 5), (5, 3 * B + 495),
        ];
        foreach (var (posicion, cantidad) in casos)
        {
            var leido = new byte[cantidad];
            var n = lector.Leer(posicion, leido);
            Assert.Equal(cantidad, n);
            Assert.Equal(datos.AsSpan((int)posicion, cantidad).ToArray(), leido);
        }
        Assert.Equal(0, lector.Leer(lector.Longitud, new byte[10]));                 // justo al final
        Assert.Equal(0, lector.Leer(lector.Longitud + 100, new byte[10]));           // más allá
        var corto = new byte[100];
        Assert.Equal(20, lector.Leer(lector.Longitud - 20, corto));                  // un tramo que se pasa: entrega lo que hay
        Assert.Equal(datos[^20..], corto[..20]);
        Assert.Equal(0, lector.Leer(0, Span<byte>.Empty));
    }

    [Fact]
    public void ElFlujo_TieneSeek_LeeDesdeDondeSePosiciona_YEsSoloDeLectura()
    {
        var datos = EstudioAyudas.Datos(2 * B + 300, 4);
        Escribir(datos, Ruta());
        using var flujo = ArchivoCifrado.AbrirLectura(Ruta(), Clave);
        Assert.True(flujo.CanRead && flujo.CanSeek);
        Assert.False(flujo.CanWrite);

        flujo.Seek(B - 10, SeekOrigin.Begin);
        var trozo = new byte[20];
        Assert.Equal(20, flujo.Read(trozo));
        Assert.Equal(datos.AsSpan(B - 10, 20).ToArray(), trozo);
        Assert.Equal(B + 10, flujo.Position);

        flujo.Seek(-5, SeekOrigin.End);
        var final = new byte[50];
        Assert.Equal(5, flujo.Read(final));
        Assert.Equal(datos[^5..], final[..5]);
        Assert.Equal(0, flujo.Read(final));

        flujo.Seek(-3, SeekOrigin.Current);
        Assert.Equal(datos.Length - 3, flujo.Position);
        Assert.Throws<IOException>(() => flujo.Seek(-1, SeekOrigin.Begin));
        Assert.Throws<NotSupportedException>(() => flujo.Write(new byte[1], 0, 1));
        Assert.Throws<NotSupportedException>(() => flujo.SetLength(1));
    }

    [Fact]
    public async Task ElFlujo_SeLeeTambienDeFormaAsincrona()
    {
        var datos = EstudioAyudas.Datos(B + 4000, 5);
        Escribir(datos, Ruta());
        await using var flujo = ArchivoCifrado.AbrirLectura(Ruta(), Clave);
        using var memoria = new MemoryStream();
        await flujo.CopyToAsync(memoria);
        Assert.Equal(datos, memoria.ToArray());
    }

    // ------------------------------------------------------------- manipulación y clave

    [Fact]
    public void UnBitAlterado_SeDetectaEnSuBloque_SinAfectarALosDemas()
    {
        var datos = EstudioAyudas.Datos(3 * B, 6);
        Escribir(datos, Ruta());
        Alterar(Ruta(), Cabecera + Sellado + 1234);                // un bit del texto cifrado del bloque 1
        using var lector = LectorCifrado.Abrir(Ruta(), Clave);
        var bloque = new byte[B];
        Assert.Equal(B, lector.Leer(0, bloque));                   // el bloque 0 sigue íntegro
        Assert.Equal(datos.AsSpan(0, B).ToArray(), bloque);
        Assert.Throws<ManipulacionDetectadaException>(() => lector.Leer(B, new byte[10]));
        Assert.Equal(B, lector.Leer(2 * B, bloque));               // y el 2 también
        using var flujo = ArchivoCifrado.AbrirLectura(Ruta(), Clave);
        Assert.Throws<ManipulacionDetectadaException>(() => EstudioAyudas.LeerTodo(flujo));
    }

    [Fact]
    public void UnBitAlteradoEnLaEtiqueta_TambienSeDetecta()
    {
        Escribir(EstudioAyudas.Datos(B + 50, 7), Ruta());
        Alterar(Ruta(), Cabecera + B + 3);                          // dentro de la etiqueta del bloque 0
        using var lector = LectorCifrado.Abrir(Ruta(), Clave);
        Assert.Throws<ManipulacionDetectadaException>(() => lector.Leer(0, new byte[10]));
    }

    [Fact]
    public void UnBloqueMovidoDeSitio_NoAutentica()
    {
        var datos = EstudioAyudas.Datos(2 * B, 8);
        Escribir(datos, Ruta());
        var bytes = File.ReadAllBytes(Ruta());
        var intercambiado = (byte[])bytes.Clone();
        Array.Copy(bytes, Cabecera + Sellado, intercambiado, Cabecera, Sellado);          // el bloque 1 en el lugar del 0
        Array.Copy(bytes, Cabecera, intercambiado, Cabecera + Sellado, Sellado);
        File.WriteAllBytes(Ruta(), intercambiado);
        using var lector = LectorCifrado.Abrir(Ruta(), Clave);
        Assert.Throws<ManipulacionDetectadaException>(() => lector.Leer(0, new byte[10]));
        Assert.Throws<ManipulacionDetectadaException>(() => lector.Leer(B, new byte[10]));
    }

    [Fact]
    public void UnArchivoTruncado_SeDetecta()
    {
        Escribir(EstudioAyudas.Datos(2 * B + 100, 10), Ruta());
        var completo = File.ReadAllBytes(Ruta());
        File.WriteAllBytes(Ruta(), completo[..^5]);                  // se le comió un pedazo de la etiqueta final
        using (var lector = LectorCifrado.Abrir(Ruta(), Clave))
            Assert.Throws<ManipulacionDetectadaException>(() => lector.Leer(2 * B, new byte[10]));

        File.WriteAllBytes(Ruta(), completo[..(Cabecera + 2 * Sellado + 8)]);   // termina dentro de una etiqueta: ni siquiera parece un archivo
        Assert.Throws<ManipulacionDetectadaException>(() => LectorCifrado.Abrir(Ruta(), Clave));

        File.WriteAllBytes(Ruta(), completo[..10]);
        Assert.Throws<ArchivoCifradoException>(() => LectorCifrado.Abrir(Ruta(), Clave));
    }

    [Fact]
    public void ConOtraClave_FallaAlAbrir_ConClaveIncorrecta()
    {
        Escribir(EstudioAyudas.Datos(B + 10, 11), Ruta());
        Assert.Throws<ClaveIncorrectaException>(() => LectorCifrado.Abrir(Ruta(), OtraClave));
        Assert.Throws<ClaveIncorrectaException>(() => ArchivoCifrado.AbrirLectura(Ruta(), OtraClave));
        Assert.Throws<ClaveIncorrectaException>(() => EscritorCifrado.Reanudar(Ruta(), OtraClave));
        Assert.Throws<ClaveIncorrectaException>(() => ArchivoCifrado.Sha256DeContenido(Ruta(), OtraClave));
        Assert.Throws<ArgumentException>(() => LectorCifrado.Abrir(Ruta(), new byte[16]));    // una clave que no es de 32 bytes ni se intenta
    }

    [Fact]
    public void UnaCabeceraManipulada_NoPasa_ElVerificadorLaProtege()
    {
        Escribir(EstudioAyudas.Datos(100, 12), Ruta());
        Alterar(Ruta(), 14);                                          // un byte del prefijo de nonce
        Assert.Throws<ClaveIncorrectaException>(() => LectorCifrado.Abrir(Ruta(), Clave));
        Escribir(EstudioAyudas.Datos(100, 12), Ruta());
        Alterar(Ruta(), 6);                                           // un byte reservado de la cabecera
        Assert.Throws<ClaveIncorrectaException>(() => LectorCifrado.Abrir(Ruta(), Clave));
        Escribir(EstudioAyudas.Datos(100, 12), Ruta());
        Alterar(Ruta(), 0);                                           // la firma
        var ex = Assert.Throws<ArchivoCifradoException>(() => LectorCifrado.Abrir(Ruta(), Clave));
        Assert.IsNotType<ClaveIncorrectaException>(ex);
    }

    // --------------------------------------------------------------------------- reanudar

    [Fact]
    public void Dispose_SinCerrar_EsUnaPausa_SoloLosBloquesCompletosLlegaronAlDisco()
    {
        var datos = EstudioAyudas.Datos(3 * B + 5000, 13);
        using (var escritor = EscritorCifrado.Crear(Ruta(), Clave))
        {
            escritor.Escribir(datos);
            Assert.Equal(datos.Length, escritor.BytesEnClaro);
            Assert.Equal(3 * B, escritor.BytesPersistidos);
        }
        Assert.Equal(Cabecera + 3 * Sellado, new FileInfo(Ruta()).Length);         // la cola de 5000 bytes no se escribió
    }

    [Fact]
    public void Reanudar_TrasCortarAMitadDeBloque_ConservaLoValido_YElSha256FinalCoincide()
    {
        var datos = EstudioAyudas.Datos(4 * B + 1234, 14);
        using (var escritor = EscritorCifrado.Crear(Ruta(), Clave)) escritor.Escribir(datos.AsSpan(0, 3 * B + 800));    // se pausa con 3 bloques a salvo

        // El corte llegó a mitad de la escritura del cuarto bloque: quedó a medias.
        using (var archivo = new FileStream(Ruta(), FileMode.Append)) archivo.Write(EstudioAyudas.Datos(1000, 99));
        Assert.Equal(Cabecera + 3 * Sellado + 1000, new FileInfo(Ruta()).Length);

        string sha;
        using (var escritor = EscritorCifrado.Reanudar(Ruta(), Clave))
        {
            Assert.Equal(3 * B, escritor.BytesEnClaro);                             // lo válido se conserva
            Assert.Equal(Cabecera + 3 * Sellado, new FileInfo(Ruta()).Length);      // y lo roto se descartó
            for (var i = (int)escritor.BytesEnClaro; i < datos.Length; i += 9000) escritor.Escribir(datos.AsSpan(i, Math.Min(9000, datos.Length - i)));
            escritor.Cerrar();
            sha = escritor.Sha256Hex();
        }
        Assert.Equal(EstudioAyudas.Sha256(datos), sha);                             // incluye lo que ya había: se releyó al reanudar
        Assert.Equal(sha, ArchivoCifrado.Sha256DeContenido(Ruta(), Clave));
        using var flujo = ArchivoCifrado.AbrirLectura(Ruta(), Clave);
        Assert.Equal(datos, EstudioAyudas.LeerTodo(flujo));
    }

    [Fact]
    public void Reanudar_UnArchivoCerradoQueSeCortoALaMitad_VuelveAlUltimoBloqueIntegro()
    {
        var datos = EstudioAyudas.Datos(4 * B + 10, 15);
        Escribir(datos, Ruta());
        var completo = File.ReadAllBytes(Ruta());
        File.WriteAllBytes(Ruta(), completo[..(Cabecera + 2 * Sellado + 777)]);     // un archivo cortado a mitad del tercer bloque

        using var escritor = EscritorCifrado.Reanudar(Ruta(), Clave);
        Assert.Equal(2 * B, escritor.BytesEnClaro);
        escritor.Escribir(datos.AsSpan(2 * B));
        escritor.Cerrar();
        Assert.Equal(EstudioAyudas.Sha256(datos), escritor.Sha256Hex());
        escritor.Dispose();
        using var flujo = ArchivoCifrado.AbrirLectura(Ruta(), Clave);
        Assert.Equal(datos, EstudioAyudas.LeerTodo(flujo));
    }

    [Fact]
    public void Reanudar_ConLaColaCortaDeUnArchivoCerrado_LaRecupera_YCerrarLoDejaIdentico()
    {
        var datos = EstudioAyudas.Datos(2 * B + 500, 16);
        Escribir(datos, Ruta());
        var antes = File.ReadAllBytes(Ruta());
        using (var escritor = EscritorCifrado.Reanudar(Ruta(), Clave))
        {
            Assert.Equal(datos.Length, escritor.BytesEnClaro);
            Assert.Equal(2 * B, escritor.BytesPersistidos);
            Assert.Equal(EstudioAyudas.Sha256(datos), escritor.Sha256Hex());
            escritor.Cerrar();
        }
        Assert.Equal(antes, File.ReadAllBytes(Ruta()));            // mismo nonce y mismo contenido: el mismo archivo, byte por byte
    }

    [Fact]
    public void Reanudar_UnBloqueCompletoFinalQueNoAutentica_SeDescarta()
    {
        var datos = EstudioAyudas.Datos(3 * B, 17);
        Escribir(datos, Ruta());
        Alterar(Ruta(), Cabecera + 2 * Sellado + 100);              // el último bloque, entero pero con datos de basura (un corte de energía)
        using var escritor = EscritorCifrado.Reanudar(Ruta(), Clave);
        Assert.Equal(2 * B, escritor.BytesEnClaro);
        Assert.Equal(Cabecera + 2 * Sellado, new FileInfo(Ruta()).Length);
    }

    [Fact]
    public void Reanudar_ConUnBloqueDelMedioAlterado_LanzaManipulacion()
    {
        Escribir(EstudioAyudas.Datos(3 * B, 18), Ruta());
        Alterar(Ruta(), Cabecera + Sellado + 100);                  // el bloque 1 de 3: lo que se creía a salvo ya no lo está
        Assert.Throws<ManipulacionDetectadaException>(() => EscritorCifrado.Reanudar(Ruta(), Clave));
    }

    [Fact]
    public void Reanudar_ConSoloLaCabecera_ContinuaDesdeCero()
    {
        var datos = EstudioAyudas.Datos(B + 3, 19);
        using (var escritor = EscritorCifrado.Crear(Ruta(), Clave)) { }
        using var reanudado = EscritorCifrado.Reanudar(Ruta(), Clave);
        Assert.Equal(0, reanudado.BytesEnClaro);
        reanudado.Escribir(datos);
        reanudado.Cerrar();
        Assert.Equal(EstudioAyudas.Sha256(datos), reanudado.Sha256Hex());
    }

    [Fact]
    public void UnEscritorCerrado_NoAceptaMasDatos_YCerrarDosVecesEsInocuo()
    {
        using var escritor = EscritorCifrado.Crear(Ruta(), Clave);
        escritor.Escribir(new byte[10]);
        escritor.Cerrar();
        escritor.Cerrar();
        Assert.Throws<InvalidOperationException>(() => escritor.Escribir(new byte[1]));
        escritor.Dispose();
        Assert.Throws<ObjectDisposedException>(() => escritor.Sha256Hex());
    }

    // --------------------------------------------------------------- documentos pequeños

    [Fact]
    public void UnDocumento_IdaYVuelta_AutenticaElContexto_YNoDejaTextoEnClaro()
    {
        var contexto = Encoding.UTF8.GetBytes("lista|ana");
        var claro = Encoding.UTF8.GetBytes("Área y volumen · texto de la lección que no debe verse en el disco");
        var sellado = DocumentoCifrado.Sellar(claro, Clave, contexto);
        Assert.Equal(claro, DocumentoCifrado.Abrir(sellado, Clave, contexto));
        Assert.False(EstudioAyudas.Contiene(sellado, claro[..12]));
        Assert.NotEqual(sellado, DocumentoCifrado.Sellar(claro, Clave, contexto));            // nonce aleatorio
        Assert.Throws<ManipulacionDetectadaException>(() => DocumentoCifrado.Abrir(sellado, Clave, Encoding.UTF8.GetBytes("lista|beto")));   // otro lugar
        Assert.Throws<ManipulacionDetectadaException>(() => DocumentoCifrado.Abrir(sellado, OtraClave, contexto));                          // otra clave
        var alterado = (byte[])sellado.Clone();
        alterado[^1] ^= 1;
        Assert.Throws<ManipulacionDetectadaException>(() => DocumentoCifrado.Abrir(alterado, Clave, contexto));
        Assert.Throws<ArchivoCifradoException>(() => DocumentoCifrado.Abrir(new byte[5], Clave, contexto));
        Assert.Equal([], DocumentoCifrado.Abrir(DocumentoCifrado.Sellar([], Clave, contexto), Clave, contexto));
    }

    [Fact]
    public void LaClaveEnMemoria_EntregaCopias_YDestruirLaCambia()
    {
        var proveedor = new ProveedorDeClaveEnMemoria(Clave);
        var primera = proveedor.Obtener();
        Assert.Equal(Clave, primera);
        primera[0] ^= 0xFF;                                          // quien recibe la copia la puede tocar sin afectar al proveedor
        Assert.Equal(Clave, proveedor.Obtener());
        proveedor.Destruir();
        Assert.NotEqual(Clave, proveedor.Obtener());
        Assert.Equal(1, proveedor.Destrucciones);
        Assert.Equal(32, new ProveedorDeClaveEnMemoria().Obtener().Length);
        Assert.NotEqual(new ProveedorDeClaveEnMemoria().Obtener(), new ProveedorDeClaveEnMemoria().Obtener());
        Assert.Throws<ArgumentException>(() => new ProveedorDeClaveEnMemoria(new byte[5]));
    }
}

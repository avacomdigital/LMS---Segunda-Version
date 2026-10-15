using System.Security.Cryptography;
using System.Text.RegularExpressions;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Ops.Reportes;

namespace Avacom.Lms.Ops.Tests;

/// <summary>
/// Guardar un reporte en una unidad que se puede retirar, llenar o proteger a mitad de la escritura (MOD-013). Los casos que se pueden hacer de verdad se hacen contra el sistema de
/// archivos REAL en una carpeta temporal única; los que un disco real hace pero no se pueden provocar a voluntad (se retira la memoria a mitad, se llena, otro proceso gana un nombre,
/// lo releído no es lo escrito) se simulan con un <see cref="IOperacionesDeArchivo"/> que envuelve al real y falla donde la prueba le dice. NO hay memoria USB física ni VHD aquí.
/// </summary>
public sealed class EscrituraSeguraTests : IDisposable
{
    private readonly string _carpeta;

    public EscrituraSeguraTests()
    {
        _carpeta = Path.Combine(Path.GetTempPath(), "avacom-ops-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_carpeta);
    }

    public void Dispose()
    {
        try { Directory.Delete(_carpeta, recursive: true); }
        catch { /* queda en la carpeta temporal del sistema */ }
    }

    // ---------------------------------------------------------------------------------------------------- piezas

    private static int Hr(int win32) => unchecked((int)(0x80070000u | (uint)win32));

    private static byte[] Datos(int largo, int semilla = 1)
    {
        var datos = new byte[largo];
        new Random(semilla).NextBytes(datos);
        return datos;
    }

    private static string Sha(byte[] datos) => Convert.ToHexStringLower(SHA256.HashData(datos));

    /// <summary>Todo lo que hay en la carpeta (archivos, temporales, ocultos), ordenado: lo que NO debe quedar se nota.</summary>
    private string[] Entradas() => Directory.GetFileSystemEntries(_carpeta).Select(p => Path.GetFileName(p)!).OrderBy(n => n, StringComparer.Ordinal).ToArray();

    private Task<ResultadoDeEscritura> Escribir(byte[] datos, string nombre = "reporte.xlsx", IOperacionesDeArchivo? io = null, IProgress<double>? progreso = null,
                                                CancellationToken ct = default, string? sha = null, long? bytes = null, string? carpeta = null) =>
        EscrituraSegura.EscribirAsync(new MemoryStream(datos), sha ?? Sha(datos), bytes ?? datos.Length, carpeta ?? _carpeta, nombre, progreso, ct, io);

    private static void Fallo(ResultadoDeEscritura r, MotivoDeEscritura esperado)
    {
        Assert.False(r.Ok, "se esperaba un fallo");
        Assert.NotNull(r.Fallo);
        Assert.Equal(esperado, r.Fallo.Motivo);
        Assert.Equal(MotivosDeEscritura.Codigo(esperado), r.Fallo.Codigo);
        Assert.Null(r.RutaFinal);                       // en un fallo no hay archivo ni valores a medias
        Assert.Equal(0, r.Bytes);
        Assert.Null(r.Sha256);
    }

    private sealed class ProgresoSincrono : IProgress<double>
    {
        private readonly object _candado = new();
        private readonly List<double> _valores = [];
        public void Report(double valor) { lock (_candado) _valores.Add(valor); }
        public double[] Valores { get { lock (_candado) return _valores.ToArray(); } }
    }

    private sealed class ProgresoQueLanza : IProgress<double>
    {
        public void Report(double valor) => throw new InvalidOperationException("quien escucha el avance falló");
    }

    /// <summary>El sistema de archivos real con ganchos: cada método hace lo normal salvo que la prueba le ponga otra cosa. Anota qué se llamó.</summary>
    private sealed class IoDeLaPrueba : IOperacionesDeArchivo
    {
        private readonly object _candado = new();
        private readonly List<string> _llamadas = [];

        public IOperacionesDeArchivo Real { get; } = new OperacionesDeArchivoDelSistema();
        public Func<string, bool>? ExisteCarpetaHook { get; set; }
        public Func<string, bool>? ExisteHook { get; set; }
        public Func<string, long?>? EspacioLibreHook { get; set; }
        public Func<string, Stream>? CrearNuevoHook { get; set; }
        public Func<string, Stream>? AbrirLecturaHook { get; set; }
        public Func<string, long>? TamanoHook { get; set; }
        public Action<string, string>? MoverHook { get; set; }
        public Action<string>? BorrarHook { get; set; }
        public Action<string>? VaciarHook { get; set; }
        public Func<string, bool>? EsUnidadDeRedHook { get; set; }

        public int Veces(string metodo) { lock (_candado) return _llamadas.Count(l => l == metodo); }
        public string[] Llamadas { get { lock (_candado) return _llamadas.ToArray(); } }
        private void Anotar(string metodo) { lock (_candado) _llamadas.Add(metodo); }

        public bool ExisteCarpeta(string ruta) { Anotar(nameof(ExisteCarpeta)); return ExisteCarpetaHook?.Invoke(ruta) ?? Real.ExisteCarpeta(ruta); }
        public bool EsUnidadDeRed(string carpeta) => EsUnidadDeRedHook?.Invoke(carpeta) ?? false;
        public bool Existe(string ruta) { Anotar(nameof(Existe)); return ExisteHook?.Invoke(ruta) ?? Real.Existe(ruta); }
        public long? EspacioLibre(string carpeta) { Anotar(nameof(EspacioLibre)); return EspacioLibreHook is null ? Real.EspacioLibre(carpeta) : EspacioLibreHook(carpeta); }
        public Stream CrearNuevo(string ruta) { Anotar(nameof(CrearNuevo)); return CrearNuevoHook?.Invoke(ruta) ?? Real.CrearNuevo(ruta); }
        public Stream AbrirLectura(string ruta) { Anotar(nameof(AbrirLectura)); return AbrirLecturaHook?.Invoke(ruta) ?? Real.AbrirLectura(ruta); }
        public long Tamano(string ruta) { Anotar(nameof(Tamano)); return TamanoHook?.Invoke(ruta) ?? Real.Tamano(ruta); }

        public void MoverSinSobrescribir(string origen, string destino)
        {
            Anotar(nameof(MoverSinSobrescribir));
            if (MoverHook is null) Real.MoverSinSobrescribir(origen, destino);
            else MoverHook(origen, destino);
        }

        public void Borrar(string ruta)
        {
            Anotar(nameof(Borrar));
            if (BorrarHook is null) Real.Borrar(ruta);
            else BorrarHook(ruta);
        }

        public void VaciarADisco(string ruta)
        {
            Anotar(nameof(VaciarADisco));
            if (VaciarHook is null) Real.VaciarADisco(ruta);
            else VaciarHook(ruta);
        }
    }

    /// <summary>Un archivo de escritura que falla cuando la prueba quiere: al escribir un bloque (sabiendo cuántos bytes lleva) o al vaciar.</summary>
    private sealed class FlujoQueFalla(Stream interno, Func<long, Exception?> alEscribir, Func<Exception?>? alVaciar = null) : Stream
    {
        private long _escritos;

        public override async ValueTask WriteAsync(ReadOnlyMemory<byte> buffer, CancellationToken cancellationToken = default)
        {
            if (alEscribir(_escritos) is { } error) throw error;
            await interno.WriteAsync(buffer, cancellationToken);
            _escritos += buffer.Length;
        }

        public override Task FlushAsync(CancellationToken cancellationToken)
        {
            if (alVaciar?.Invoke() is { } error) throw error;
            return interno.FlushAsync(cancellationToken);
        }

        public override void Write(byte[] buffer, int offset, int count) => WriteAsync(buffer.AsMemory(offset, count)).AsTask().GetAwaiter().GetResult();
        public override void Flush() => interno.Flush();
        public override ValueTask DisposeAsync() => interno.DisposeAsync();
        protected override void Dispose(bool disposing) { if (disposing) interno.Dispose(); base.Dispose(disposing); }
        public override bool CanRead => false;
        public override bool CanSeek => false;
        public override bool CanWrite => true;
        public override long Length => interno.Length;
        public override long Position { get => interno.Position; set => throw new NotSupportedException(); }
        public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
    }

    /// <summary>Lo que se relee de la unidad, con un byte cambiado: una memoria que devuelve otra cosa de lo que se escribió.</summary>
    private sealed class LecturaCorrupta(Stream interno, long posicionDelByte) : Stream
    {
        private long _posicion;

        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        {
            var n = await interno.ReadAsync(buffer, cancellationToken);
            if (n > 0 && _posicion <= posicionDelByte && posicionDelByte < _posicion + n) buffer.Span[(int)(posicionDelByte - _posicion)] ^= 0xFF;
            _posicion += n;
            return n;
        }

        public override int Read(byte[] buffer, int offset, int count) => ReadAsync(buffer.AsMemory(offset, count)).AsTask().GetAwaiter().GetResult();
        public override ValueTask DisposeAsync() => interno.DisposeAsync();
        protected override void Dispose(bool disposing) { if (disposing) interno.Dispose(); base.Dispose(disposing); }
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => interno.Length;
        public override long Position { get => _posicion; set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }

    /// <summary>Un origen que genera sus bytes al pedirlos (no hay un arreglo de 5 MB detrás) y anota cuánto se le pidió de golpe. No se puede medir ni retroceder.</summary>
    private sealed class GeneradorDeBytes(long total, int semilla) : Stream
    {
        private long _posicion;
        public int MayorPeticion { get; private set; }
        public long Lecturas { get; private set; }

        public static byte Valor(long i, int semilla) => (byte)(((i * 2654435761L) >> 7) ^ semilla ^ (i >> 13));

        public override int Read(Span<byte> destino)
        {
            MayorPeticion = Math.Max(MayorPeticion, destino.Length);
            var n = (int)Math.Min(destino.Length, total - _posicion);
            for (var i = 0; i < n; i++) destino[i] = Valor(_posicion + i, semilla);
            _posicion += n;
            Lecturas++;
            return n;
        }

        public override int Read(byte[] buffer, int offset, int count) => Read(buffer.AsSpan(offset, count));
        public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default) => ValueTask.FromResult(Read(buffer.Span));
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => _posicion; set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();

        public static string Sha256De(long total, int semilla)
        {
            using var generador = new GeneradorDeBytes(total, semilla);
            return Convert.ToHexStringLower(SHA256.HashData(generador));
        }
    }

    /// <summary>Un origen que entrega parte de los datos y luego falla (el archivo local con el reporte se dañó o se borró), o que cancela a su vez a mitad de la lectura.</summary>
    private sealed class OrigenQueSeInterrumpe(byte[] datos, int despuesDe, Action alLlegar) : Stream
    {
        private int _posicion;

        public override int Read(Span<byte> destino)
        {
            if (_posicion >= despuesDe) alLlegar();
            var n = Math.Min(Math.Min(destino.Length, datos.Length - _posicion), despuesDe > _posicion ? despuesDe - _posicion : destino.Length);
            datos.AsSpan(_posicion, n).CopyTo(destino);
            _posicion += n;
            return n;
        }

        public override int Read(byte[] buffer, int offset, int count) => Read(buffer.AsSpan(offset, count));
        public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default) => ValueTask.FromResult(Read(buffer.Span));
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => _posicion; set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }

    // ---------------------------------------------------------------------------------------------------- lo que sí se puede hacer de verdad

    [Fact]
    public async Task Escribe_UnArchivoSano_ConSuTamanoYSuHash_SinTemporalesSobrantes()
    {
        var datos = Datos(300_000);
        var r = await Escribir(datos);

        Assert.True(r.Ok, r.Detalle);
        Assert.Null(r.Fallo);
        Assert.Null(r.Detalle);
        Assert.Equal(Path.Combine(_carpeta, "reporte.xlsx"), r.RutaFinal);
        Assert.Equal(datos.Length, r.Bytes);
        Assert.Equal(Sha(datos), r.Sha256);
        Assert.Equal(datos, await File.ReadAllBytesAsync(r.RutaFinal!));
        Assert.Equal(["reporte.xlsx"], Entradas());               // ni un .parte de sobra
    }

    [Fact]
    public async Task Escribe_UnArchivoVacio()
    {
        var r = await Escribir([], "vacio.csv");
        Assert.True(r.Ok, r.Detalle);
        Assert.Equal(0, new FileInfo(r.RutaFinal!).Length);
        Assert.Equal(Sha([]), r.Sha256);
        Assert.Equal(["vacio.csv"], Entradas());
    }

    [Theory]
    [InlineData(1)]
    [InlineData(4095)]
    [InlineData(4096)]
    [InlineData(4097)]
    [InlineData(81_920)]
    [InlineData(81_921)]
    [InlineData(1_048_576)]
    [InlineData(1_048_577)]
    public async Task Escribe_ConTamanosEnLosBordesDeLosBloquesYDeLosSectores(int largo)
    {
        var datos = Datos(largo, 11);
        var r = await Escribir(datos);
        Assert.True(r.Ok, r.Detalle);
        Assert.Equal(datos, await File.ReadAllBytesAsync(r.RutaFinal!));
        Assert.Equal(Sha(datos), r.Sha256);
    }

    [Fact]
    public async Task ElSha256Esperado_SeCompara_SinDistinguirMayusculas()
    {
        var datos = Datos(5_000);
        var r = await Escribir(datos, sha: Sha(datos).ToUpperInvariant());
        Assert.True(r.Ok, r.Detalle);
        Assert.Equal(Sha(datos), r.Sha256);                          // y lo que se devuelve es lo releído, en minúsculas
    }

    [Fact]
    public async Task ElAvance_EmpiezaEnCero_LlegaAUno_YNuncaRetrocede()
    {
        var progreso = new ProgresoSincrono();
        var datos = Datos(2_000_000);
        var r = await Escribir(datos, progreso: progreso);

        Assert.True(r.Ok, r.Detalle);
        var valores = progreso.Valores;
        Assert.True(valores.Length > 5, $"hubo {valores.Length} avisos de avance");
        Assert.Equal(0.0, valores[0]);
        Assert.Equal(1.0, valores[^1]);
        Assert.All(valores, v => Assert.InRange(v, 0.0, 1.0));
        Assert.Equal(valores.OrderBy(v => v).ToArray(), valores);     // nunca retrocede
        Assert.Equal(1, valores.Count(v => v >= 1.0));                // y sólo llega a 100 % una vez, al final
    }

    [Fact]
    public async Task ElAvance_DeUnArchivoVacio_TambienLlegaAUno()
    {
        var progreso = new ProgresoSincrono();
        var r = await Escribir([], progreso: progreso);
        Assert.True(r.Ok, r.Detalle);
        Assert.Equal([0.0, 1.0], progreso.Valores);
    }

    [Fact]
    public async Task QuienEscuchaElAvanceYFalla_NoHaceFallarElGuardado()
    {
        var r = await Escribir(Datos(200_000), progreso: new ProgresoQueLanza());
        Assert.True(r.Ok, r.Detalle);
    }

    [Fact]
    public async Task NoSobrescribeNada_YAgregaDosYTres()
    {
        await File.WriteAllTextAsync(Path.Combine(_carpeta, "reporte.xlsx"), "de otra persona");         // ya había uno
        var primero = Datos(1_000, 1);
        var segundo = Datos(2_000, 2);

        var r1 = await Escribir(primero);
        var r2 = await Escribir(segundo);

        Assert.True(r1.Ok, r1.Detalle);
        Assert.True(r2.Ok, r2.Detalle);
        Assert.Equal(Path.Combine(_carpeta, "reporte (2).xlsx"), r1.RutaFinal);
        Assert.Equal(Path.Combine(_carpeta, "reporte (3).xlsx"), r2.RutaFinal);
        Assert.Equal("de otra persona", await File.ReadAllTextAsync(Path.Combine(_carpeta, "reporte.xlsx")));      // lo que había sigue intacto
        Assert.Equal(primero, await File.ReadAllBytesAsync(r1.RutaFinal!));
        Assert.Equal(segundo, await File.ReadAllBytesAsync(r2.RutaFinal!));
        Assert.Equal(["reporte (2).xlsx", "reporte (3).xlsx", "reporte.xlsx"], Entradas());
    }

    [Fact]
    public async Task UnaCarpetaConElMismoNombre_TampocoSeSobrescribe()
    {
        Directory.CreateDirectory(Path.Combine(_carpeta, "reporte.xlsx"));
        var r = await Escribir(Datos(1_000));
        Assert.True(r.Ok, r.Detalle);
        Assert.Equal(Path.Combine(_carpeta, "reporte (2).xlsx"), r.RutaFinal);
    }

    [Fact]
    public async Task OchoGuardadosAlMismoTiempoConElMismoNombre_QuedanTodos_ConNombresDistintos()
    {
        var contenidos = Enumerable.Range(1, 8).Select(i => Datos(50_000 + i, i)).ToArray();
        var resultados = await Task.WhenAll(contenidos.Select(datos => Task.Run(() => Escribir(datos))));

        Assert.All(resultados, r => Assert.True(r.Ok, r.Detalle));
        Assert.Equal(8, resultados.Select(r => r.RutaFinal).Distinct(StringComparer.OrdinalIgnoreCase).Count());           // ninguno pisó a otro
        Assert.Equal(8, Entradas().Length);                                                                               // y no sobró ningún temporal
        var guardados = resultados.Select(r => Sha(File.ReadAllBytes(r.RutaFinal!))).ToHashSet();
        Assert.Equal(contenidos.Select(Sha).ToHashSet(), guardados);                                                      // cada contenido está, completo, en algún archivo
    }

    [Fact]
    public async Task ElHashEsperadoEquivocado_EsVerificacionFallida_YNoQuedaNiElTemporalNiElFinal()
    {
        var r = await Escribir(Datos(200_000), sha: new string('0', 64));
        Fallo(r, MotivoDeEscritura.VerificacionFallida);
        Assert.Empty(Entradas());
        Assert.Contains("SHA-256", r.Detalle);
    }

    [Theory]
    [InlineData("")]
    [InlineData("zz")]
    [InlineData("abc")]
    [InlineData("0123456789012345678901234567890123456789012345678901234567890123x")]
    public async Task UnShaEsperadoQueNoEsUnSha_SeRechazaSinTocarElDisco(string sha)
    {
        var io = new IoDeLaPrueba();
        var r = await Escribir(Datos(10_000), sha: sha, io: io);
        Fallo(r, MotivoDeEscritura.VerificacionFallida);
        Assert.Equal(0, io.Veces(nameof(IOperacionesDeArchivo.CrearNuevo)));
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task UnOrigenDeOtroTamano_ConOrigenMedible_SeRechazaSinCrearNada()
    {
        var io = new IoDeLaPrueba();
        var datos = Datos(10_000);
        var r = await Escribir(datos, bytes: datos.Length + 1, io: io);
        Fallo(r, MotivoDeEscritura.VerificacionFallida);
        Assert.Equal(0, io.Veces(nameof(IOperacionesDeArchivo.CrearNuevo)));
        Assert.Empty(Entradas());
    }

    [Theory]
    [InlineData(999)]          // el origen trae más de lo prometido
    [InlineData(1001)]         // y menos
    public async Task UnOrigenQueNoSePuedeMedir_ConOtroTamano_FallaAlCopiar_SinDejarNada(long prometido)
    {
        await using var origen = new GeneradorDeBytes(1_000, 5);
        var r = await EscrituraSegura.EscribirAsync(origen, GeneradorDeBytes.Sha256De(1_000, 5), prometido, _carpeta, "reporte.csv");
        Fallo(r, MotivoDeEscritura.VerificacionFallida);
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task UnOrigenQueLanzaALaMitad_NoDejaNada_NoLanza_YNoSeLeEchaLaCulpaALaUnidad()
    {
        var datos = Datos(400_000);
        await using var origen = new OrigenQueSeInterrumpe(datos, 150_000, () => throw new IOException("el archivo local se dañó", Hr(0x15)));      // con el código de «memoria retirada» a propósito
        var r = await EscrituraSegura.EscribirAsync(origen, Sha(datos), datos.Length, _carpeta, "reporte.xlsx");

        Fallo(r, MotivoDeEscritura.Otro);                               // NO «se retiró la memoria»: el que falló fue el origen
        Assert.Contains("origen", r.Detalle);
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task LaCancelacionALaMitad_EsCancelado_YNoQuedaNada()
    {
        var datos = Datos(400_000);
        using var cancelacion = new CancellationTokenSource();
        await using var origen = new OrigenQueSeInterrumpe(datos, 200_000, () => cancelacion.Cancel());
        var r = await EscrituraSegura.EscribirAsync(origen, Sha(datos), datos.Length, _carpeta, "reporte.xlsx", ct: cancelacion.Token);

        Fallo(r, MotivoDeEscritura.Cancelado);
        Assert.Equal("Cancelaste el guardado.", r.Fallo!.Mensaje);
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task UnaCancelacionPrevia_EsCancelado_SinTocarElDisco()
    {
        var io = new IoDeLaPrueba();
        using var cancelacion = new CancellationTokenSource();
        cancelacion.Cancel();
        var r = await Escribir(Datos(10_000), io: io, ct: cancelacion.Token);
        Fallo(r, MotivoDeEscritura.Cancelado);
        Assert.Empty(io.Llamadas);
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task UnaCarpetaQueNoExiste_EsUnFalloClasificado_YNoSeCreaNada()
    {
        var inexistente = Path.Combine(_carpeta, "no-existe");
        var r = await Escribir(Datos(10_000), carpeta: inexistente);
        Fallo(r, MotivoDeEscritura.MedioRetirado);                        // la carpeta o la unidad ya no está: «se retiró la memoria»
        Assert.Contains("DirectoryNotFoundException", r.Detalle);
        Assert.False(Directory.Exists(inexistente));
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task UnaCarpetaVacia_EsNombreInvalido()
    {
        var r = await Escribir(Datos(10), carpeta: "   ");
        Fallo(r, MotivoDeEscritura.NombreInvalido);
    }

    [Theory]
    [InlineData("a:b*c.xlsx", "a-b-c.xlsx")]                        // los caracteres que la unidad no admite pasan a guion
    [InlineData("CON.xlsx", "reporte-CON.xlsx")]                    // un nombre que Windows reserva
    [InlineData("  informe 8A  .csv", "informe 8A.csv")]            // espacios a los lados
    [InlineData("", "reporte")]                                     // sin nombre: el de respaldo
    [InlineData("Reporte 8.A", "Reporte 8.A")]                      // un nombre ya seguro no se toca ni en la caja de lo que sigue al último punto
    [InlineData("Año 2026 – Grupo «8°A».xlsx", "Año 2026 – Grupo «8°A».xlsx")]
    public async Task ElNombreSeVuelveASanear_ElQueYaEsSeguroNoSeToca(string pedido, string esperado)
    {
        var r = await Escribir(Datos(1_000), pedido);
        Assert.True(r.Ok, r.Detalle);
        Assert.Equal([esperado], Entradas());
    }

    [Fact]
    public async Task UnNombreQueIntentaSalirDeLaCarpeta_SeQuedaDentro()
    {
        var r = await Escribir(Datos(1_000), @"..\..\evil.xlsx");
        Assert.True(r.Ok, r.Detalle);
        Assert.Equal(_carpeta, Path.GetDirectoryName(r.RutaFinal));
        Assert.Equal(["-..-evil.xlsx"], Entradas());                      // las barras pasaron a guion y el nombre ya no tiene separadores: es un nombre más de ESA carpeta
        Assert.False(File.Exists(Path.Combine(Path.GetDirectoryName(_carpeta)!, "evil.xlsx")));
    }

    [Fact]
    public async Task UnNombreDemasiadoLargo_SeRecortaConservandoLaExtension()
    {
        var r = await Escribir(Datos(1_000), new string('a', 150) + ".xlsx");
        Assert.True(r.Ok, r.Detalle);
        var guardado = Path.GetFileName(r.RutaFinal)!;
        Assert.Equal(100, guardado.Length);
        Assert.EndsWith(".xlsx", guardado);
    }

    [Fact]
    public async Task UnArchivoDeCincoMegas_SeEscribeEnBloques_SinCargarloEntero()
    {
        const long cinco = 5L * 1024 * 1024;
        await using var origen = new GeneradorDeBytes(cinco, 9);                 // no hay un arreglo de 5 MB detrás: los bytes se inventan al pedirlos
        var r = await EscrituraSegura.EscribirAsync(origen, GeneradorDeBytes.Sha256De(cinco, 9), cinco, _carpeta, "grande.csv");

        Assert.True(r.Ok, r.Detalle);
        Assert.Equal(cinco, new FileInfo(r.RutaFinal!).Length);
        Assert.Equal(GeneradorDeBytes.Sha256De(cinco, 9), r.Sha256);
        Assert.True(origen.MayorPeticion <= 81_920, $"se le pidió al origen un bloque de {origen.MayorPeticion} bytes");      // nunca más de 80 KiB de golpe
        Assert.True(origen.Lecturas >= cinco / 81_920, $"se leyó en {origen.Lecturas} bloques");
        Assert.Equal(["grande.csv"], Entradas());
    }

    [Fact]
    public async Task Los_ArgumentosNulosONegativos_SonErroresDeQuienLlama()
    {
        using var origen = new MemoryStream([1]);
        var sha = Sha([1]);
        await Assert.ThrowsAsync<ArgumentNullException>(() => EscrituraSegura.EscribirAsync(null!, sha, 1, _carpeta, "x"));
        await Assert.ThrowsAsync<ArgumentNullException>(() => EscrituraSegura.EscribirAsync(origen, null!, 1, _carpeta, "x"));
        await Assert.ThrowsAsync<ArgumentNullException>(() => EscrituraSegura.EscribirAsync(origen, sha, 1, null!, "x"));
        await Assert.ThrowsAsync<ArgumentNullException>(() => EscrituraSegura.EscribirAsync(origen, sha, 1, _carpeta, null!));
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => EscrituraSegura.EscribirAsync(origen, sha, -1, _carpeta, "x"));
    }

    // ---------------------------------------------------------------------------------------------------- lo que sólo se puede simular

    [Fact]
    public async Task SinEspacio_SeDiceAntesDeEscribirNada()
    {
        var io = new IoDeLaPrueba { EspacioLibreHook = _ => 10 };         // la memoria tiene 10 bytes libres
        var r = await Escribir(Datos(5_000), io: io);
        Fallo(r, MotivoDeEscritura.SinEspacio);
        Assert.Equal(0, io.Veces(nameof(IOperacionesDeArchivo.CrearNuevo)));
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task UnTamanoQueNoCabeEnLaUnidadReal_EsSinEspacio_AntesDeEscribirNada()
    {
        // sin ganchos: el espacio libre es el del disco de verdad, y lo prometido es más de lo que cabe en cualquier disco
        await using var origen = new GeneradorDeBytes(10, 1);
        var r = await EscrituraSegura.EscribirAsync(origen, new string('a', 64), long.MaxValue, _carpeta, "enorme.csv");
        Fallo(r, MotivoDeEscritura.SinEspacio);
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task UnaUnidadSinBarra_SeTomaPorSuRaiz_NoPorLaCarpetaActualDeEsaUnidad()
    {
        string? creada = null;
        var io = new IoDeLaPrueba
        {
            ExisteCarpetaHook = _ => true,
            EspacioLibreHook = _ => null,
            CrearNuevoHook = ruta => { creada = ruta; throw new IOException("la memoria se retiró", Hr(0x15)); },
        };
        var r = await Escribir(Datos(100), io: io, carpeta: "E:");
        Fallo(r, MotivoDeEscritura.MedioRetirado);
        Assert.StartsWith(@"E:\.reporte.xlsx.", creada);                   // «E:\…» y no «E:…» (que sería relativo a la carpeta actual de E)
        Assert.EndsWith(".parte", creada);
    }

    [Fact]
    public async Task ConJustoElEspacioQueHaceFalta_SiSeEscribe()
    {
        var datos = Datos(5_000);
        var io = new IoDeLaPrueba { EspacioLibreHook = _ => datos.Length };
        Assert.True((await Escribir(datos, io: io)).Ok);
    }

    [Fact]
    public async Task SiNoSePuedeSaberElEspacio_SeIntentaIgual()
    {
        var io = new IoDeLaPrueba { EspacioLibreHook = _ => null };
        Assert.True((await Escribir(Datos(5_000), io: io)).Ok);
    }

    [Fact]
    public async Task SeLlenaAlEscribir_EsSinEspacio_LimpiaElTemporal_YNoLanza()
    {
        var io = new IoDeLaPrueba();
        io.CrearNuevoHook = ruta => new FlujoQueFalla(io.Real.CrearNuevo(ruta), escritos => escritos >= 160_000 ? new IOException("no hay espacio", Hr(0x70)) : null);
        var r = await Escribir(Datos(400_000), io: io);

        Fallo(r, MotivoDeEscritura.SinEspacio);
        Assert.Equal("La memoria no tiene espacio suficiente para este archivo.", r.Fallo!.Mensaje);
        Assert.True(io.Veces(nameof(IOperacionesDeArchivo.Borrar)) >= 1);
        Assert.Empty(Entradas());                                          // se borró el temporal: no queda un archivo a medias
    }

    [Fact]
    public async Task SeRetiraLaMemoriaAMitadDeLaCopia_EsMedioRetirado_YLimpia()
    {
        var io = new IoDeLaPrueba();
        io.CrearNuevoHook = ruta => new FlujoQueFalla(io.Real.CrearNuevo(ruta), escritos => escritos >= 160_000 ? new IOException("el dispositivo no está listo", Hr(0x15)) : null);
        var r = await Escribir(Datos(400_000), io: io);

        Fallo(r, MotivoDeEscritura.MedioRetirado);
        Assert.Equal("Se retiró la memoria mientras se guardaba.", r.Fallo!.Mensaje);
        Assert.Contains("0x80070015", r.Detalle);                          // el código exacto queda en el detalle, para la bitácora
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task SiLaMemoriaYaNoEstaParaBorrarElTemporal_NoSeInsiste_YElMotivoSigueSiendoElOriginal()
    {
        var io = new IoDeLaPrueba { BorrarHook = _ => throw new DirectoryNotFoundException("la unidad ya no está") };
        io.CrearNuevoHook = ruta => new FlujoQueFalla(io.Real.CrearNuevo(ruta), escritos => escritos >= 80_000 ? new IOException("x", Hr(0x45D)) : null);
        var r = await Escribir(Datos(400_000), io: io);

        Fallo(r, MotivoDeEscritura.MedioRetirado);
        Assert.Equal(1, io.Veces(nameof(IOperacionesDeArchivo.Borrar)));    // una sola vez: si no hay unidad no hay nada que reintentar
    }

    [Fact]
    public async Task SeRetiraJustoAntesDelRenombre_EsMedioRetirado_YSeBorraElTemporal()
    {
        var io = new IoDeLaPrueba { MoverHook = (_, _) => throw new IOException("el dispositivo ya no existe", Hr(0x45D)) };
        var r = await Escribir(Datos(100_000), io: io);

        Fallo(r, MotivoDeEscritura.MedioRetirado);
        Assert.Empty(Entradas());
        Assert.True(io.Veces(nameof(IOperacionesDeArchivo.Borrar)) >= 1);
    }

    [Fact]
    public async Task UnaMemoriaProtegidaContraEscritura_SeDiceAlCrearElTemporal()
    {
        var io = new IoDeLaPrueba { CrearNuevoHook = _ => throw new IOException("El medio está protegido contra escritura.", Hr(0x13)) };
        var r = await Escribir(Datos(10_000), io: io);
        Fallo(r, MotivoDeEscritura.ProtegidoContraEscritura);
        Assert.Equal(0, io.Veces(nameof(IOperacionesDeArchivo.Borrar)));    // no llegó a crearse nada: no hay nada que borrar
    }

    [Fact]
    public async Task SinPermiso_AlCrearElTemporal()
    {
        var io = new IoDeLaPrueba { CrearNuevoHook = _ => throw new UnauthorizedAccessException("Acceso denegado.") };
        Fallo(await Escribir(Datos(10_000), io: io), MotivoDeEscritura.SinPermiso);
    }

    [Fact]
    public async Task UnAntivirusQueBloqueaAlCerrar_EsBloqueadoPorAntivirus()
    {
        var io = new IoDeLaPrueba();
        io.CrearNuevoHook = ruta => new FlujoQueFalla(io.Real.CrearNuevo(ruta), _ => null, () => new IOException("El archivo contiene un virus.", Hr(0xE1)));
        Fallo(await Escribir(Datos(10_000), io: io), MotivoDeEscritura.BloqueadoPorAntivirus);
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task SiElTemporalYaCerradoDesapareceDeUnaCarpetaQueSigueAhi_EsElAntivirus()
    {
        // algunos antivirus ponen el archivo en cuarentena sin dar ningún error de «virus»: simplemente ya no está
        var io = new IoDeLaPrueba { TamanoHook = _ => throw new FileNotFoundException("no está") };
        var r = await Escribir(Datos(10_000), io: io);
        Fallo(r, MotivoDeEscritura.BloqueadoPorAntivirus);
        Assert.Contains("cuarentena", r.Detalle);
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task SiElTemporalYaCerradoDesapareceJuntoConLaCarpeta_EsMedioRetirado()
    {
        var io = new IoDeLaPrueba();
        var preguntas = 0;
        io.ExisteCarpetaHook = ruta => Interlocked.Increment(ref preguntas) == 1 && io.Real.ExisteCarpeta(ruta);      // está al empezar y después ya no
        io.TamanoHook = _ => throw new FileNotFoundException("no está");
        Fallo(await Escribir(Datos(10_000), io: io), MotivoDeEscritura.MedioRetirado);
    }

    [Fact]
    public async Task SiElArchivoDesapareceMientrasSigueAbierto_ES_LaUnidadQueSeFue_AunqueLaCarpetaSigaAhi()
    {
        var io = new IoDeLaPrueba();
        io.CrearNuevoHook = ruta => new FlujoQueFalla(io.Real.CrearNuevo(ruta), escritos => escritos >= 80_000 ? new FileNotFoundException("no está") : null);
        Fallo(await Escribir(Datos(400_000), io: io), MotivoDeEscritura.MedioRetirado);
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task UnaRutaDeRedQueNoContesta_EsRutaDeRedInalcanzable()
    {
        var io = new IoDeLaPrueba
        {
            ExisteCarpetaHook = _ => true,
            EspacioLibreHook = _ => null,
            CrearNuevoHook = _ => throw new IOException("No se encontró la ruta de red.", Hr(0x35)),
        };
        var r = await Escribir(Datos(10_000), io: io, carpeta: @"\\servidor\reportes");
        Fallo(r, MotivoDeEscritura.RutaDeRedInalcanzable);
        Assert.Equal("No se pudo llegar a esa carpeta de red.", r.Fallo!.Mensaje);
    }

    [Fact]
    public async Task UnaCarpetaDeRedQueDesaparece_EsRutaDeRedInalcanzable_YUnaLocalMedioRetirado()
    {
        var sinCarpeta = new IoDeLaPrueba { ExisteCarpetaHook = _ => false };
        Fallo(await Escribir(Datos(100), io: sinCarpeta, carpeta: @"\\servidor\reportes\2026"), MotivoDeEscritura.RutaDeRedInalcanzable);
        Fallo(await Escribir(Datos(100), io: sinCarpeta, carpeta: @"E:\Reportes"), MotivoDeEscritura.MedioRetirado);
    }

    [Fact]
    public async Task UnaUnidadDeRedMapeadaQueSeCae_EsRutaDeRedInalcanzable_AunqueLaRutaNoSeaUnc()
    {
        // «Z:\Reportes» no se distingue de un disco local por el texto: lo dice el sistema (DriveType.Network). Sin eso, «se retiró la memoria» y el nodo recibiría `medio_retirado`.
        var cae = new IoDeLaPrueba { ExisteCarpetaHook = _ => false, EsUnidadDeRedHook = _ => true };
        var r = await Escribir(Datos(100), io: cae, carpeta: @"Z:\Reportes");
        Fallo(r, MotivoDeEscritura.RutaDeRedInalcanzable);
        Assert.Equal("No se pudo llegar a esa carpeta de red.", r.Fallo!.Mensaje);
        Fallo(await Escribir(Datos(100), io: new IoDeLaPrueba { ExisteCarpetaHook = _ => false, EsUnidadDeRedHook = _ => false }, carpeta: @"Z:\Reportes"), MotivoDeEscritura.MedioRetirado);
    }

    [Fact]
    public void LaUnidadDeRedDeVerdad_SeReconoceSoloPorElSistema_YUnaCarpetaLocalNo()
    {
        var real = new OperacionesDeArchivoDelSistema();
        Assert.False(real.EsUnidadDeRed(Path.GetTempPath()));                                          // el disco local nunca es de red
        Assert.False(real.EsUnidadDeRed(@"\\servidor\recurso\carpeta"));                              // una UNC la reconoce el texto, no esta pregunta
        Assert.False(real.EsUnidadDeRed(""));
        Assert.False(real.EsUnidadDeRed("no es una ruta ?*"));                                         // y nada de esto lanza
    }

    [Fact]
    public async Task UnArchivoEnUso_AlCambiarElNombre_SeReintentaUnasCuantasVeces_Y_SiPersiste_EsArchivoEnUso()
    {
        var io = new IoDeLaPrueba { MoverHook = (_, _) => throw new IOException("El archivo está en uso.", Hr(0x20)) };
        var r = await Escribir(Datos(10_000), io: io);

        Fallo(r, MotivoDeEscritura.ArchivoEnUso);
        Assert.Equal(4, io.Veces(nameof(IOperacionesDeArchivo.MoverSinSobrescribir)));      // el intento y tres reintentos
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task UnAntivirusQueSoltoElArchivoALaSegundaVez_SeGuardaSinMasQueUnReintento()
    {
        var io = new IoDeLaPrueba();
        var intentos = 0;
        io.MoverHook = (de, a) =>
        {
            if (Interlocked.Increment(ref intentos) <= 2) throw new IOException("El archivo está en uso.", Hr(0x20));
            io.Real.MoverSinSobrescribir(de, a);
        };
        var r = await Escribir(Datos(10_000), io: io);

        Assert.True(r.Ok, r.Detalle);
        Assert.Equal(3, io.Veces(nameof(IOperacionesDeArchivo.MoverSinSobrescribir)));
        Assert.Equal(["reporte.xlsx"], Entradas());
    }

    [Fact]
    public async Task SiOtroProcesoGanaElNombreEntreMedias_SePruebaConElSiguiente_SinPisarloNiPerderElNuestro()
    {
        var io = new IoDeLaPrueba();
        var primera = true;
        io.MoverHook = (de, a) =>
        {
            if (primera)
            {
                primera = false;
                File.WriteAllText(a, "lo creó otro proceso");               // entre la comprobación y el cambio de nombre
            }
            io.Real.MoverSinSobrescribir(de, a);
        };
        var datos = Datos(30_000);
        var r = await Escribir(datos, io: io);

        Assert.True(r.Ok, r.Detalle);
        Assert.Equal(Path.Combine(_carpeta, "reporte (2).xlsx"), r.RutaFinal);
        Assert.Equal("lo creó otro proceso", await File.ReadAllTextAsync(Path.Combine(_carpeta, "reporte.xlsx")));
        Assert.Equal(datos, await File.ReadAllBytesAsync(r.RutaFinal!));
        Assert.Equal(["reporte (2).xlsx", "reporte.xlsx"], Entradas());
    }

    [Fact]
    public async Task SiTodosLosNombresEstanOcupados_NoSePisaNada_Y_SeLimpia()
    {
        var io = new IoDeLaPrueba { ExisteHook = _ => true };
        var r = await Escribir(Datos(10_000), io: io);
        Fallo(r, MotivoDeEscritura.Otro);
        Assert.Contains("No hay un nombre libre", r.Detalle);
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task LoReleidoDeLaUnidadNoEsLoEscrito_EsVerificacionFallida_YSeDescarta()
    {
        var io = new IoDeLaPrueba();
        io.AbrirLecturaHook = ruta => new LecturaCorrupta(io.Real.AbrirLectura(ruta), posicionDelByte: 123_456);
        var r = await Escribir(Datos(300_000), io: io);

        Fallo(r, MotivoDeEscritura.VerificacionFallida);
        Assert.Contains("SHA-256", r.Detalle);
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task ElTamanoQueDiceLaUnidad_NoCoincide_EsVerificacionFallida_SinNiSiquieraReleer()
    {
        var io = new IoDeLaPrueba { TamanoHook = _ => 299_999 };
        var r = await Escribir(Datos(300_000), io: io);

        Fallo(r, MotivoDeEscritura.VerificacionFallida);
        Assert.Equal(0, io.Veces(nameof(IOperacionesDeArchivo.AbrirLectura)));
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task LaVerificacion_ReleeSinPasarPorLaMemoriaDelSistema_EnUnDiscoLocalDeWindows()
    {
        if (!OperatingSystem.IsWindows()) return;
        var io = new IoDeLaPrueba();
        Type? tipoDeLectura = null;
        io.AbrirLecturaHook = ruta =>
        {
            var lectura = io.Real.AbrirLectura(ruta);
            tipoDeLectura = lectura.GetType();
            return lectura;
        };
        var r = await Escribir(Datos(100_000), io: io);
        Assert.True(r.Ok, r.Detalle);
        Assert.Equal(typeof(LectorSinCache), tipoDeLectura);              // releer por el camino normal devolvería lo que Windows tiene en memoria, no lo que hay en la unidad
    }

    [Fact]
    public async Task LaVerificacion_SeHaceDeVerdad_YAntesDelRenombre()
    {
        var io = new IoDeLaPrueba();
        var r = await Escribir(Datos(100_000), io: io);
        Assert.True(r.Ok, r.Detalle);
        var orden = io.Llamadas.Where(l => l is nameof(IOperacionesDeArchivo.CrearNuevo) or nameof(IOperacionesDeArchivo.Tamano) or nameof(IOperacionesDeArchivo.AbrirLectura)
                                             or nameof(IOperacionesDeArchivo.MoverSinSobrescribir) or nameof(IOperacionesDeArchivo.VaciarADisco)).ToArray();
        Assert.Equal(["CrearNuevo", "Tamano", "AbrirLectura", "MoverSinSobrescribir", "VaciarADisco"], orden);       // crear, medir, releer, renombrar, y vaciar el nombre nuevo
    }

    [Fact]
    public async Task SiNoSeCancelo_PeroElSistemaAborto_NoSeDiceQueSeCancelo()
    {
        // lo que Windows hace con una escritura en curso cuando la unidad desaparece (ERROR_OPERATION_ABORTED): .NET lo entrega como una cancelación que nadie pidió
        var io = new IoDeLaPrueba();
        io.CrearNuevoHook = ruta => new FlujoQueFalla(io.Real.CrearNuevo(ruta), escritos => escritos >= 80_000 ? new OperationCanceledException("abortada") : null);
        var r = await Escribir(Datos(400_000), io: io);

        Fallo(r, MotivoDeEscritura.MedioRetirado);
        Assert.Empty(Entradas());
    }

    [Fact]
    public async Task SiFallaElVaciadoFinalDeLaEntradaDelDirectorio_ElArchivoYaVerificadoSigueSiendoBueno()
    {
        var io = new IoDeLaPrueba { VaciarHook = _ => throw new IOException("la memoria se retiró justo ahora", Hr(0x15)) };
        var datos = Datos(50_000);
        var r = await Escribir(datos, io: io);

        Assert.True(r.Ok, r.Detalle);
        Assert.Equal(datos, await File.ReadAllBytesAsync(r.RutaFinal!));
    }

    [Fact]
    public async Task SiElBorradoDelTemporalFallaDosVeces_SeReintenta_Y_QuedaLimpio()
    {
        var io = new IoDeLaPrueba();
        var intentos = 0;
        io.BorrarHook = ruta =>
        {
            if (Interlocked.Increment(ref intentos) <= 2) throw new IOException("lo tiene el antivirus", Hr(0x20));
            io.Real.Borrar(ruta);
        };
        io.CrearNuevoHook = ruta => new FlujoQueFalla(io.Real.CrearNuevo(ruta), escritos => escritos >= 80_000 ? new IOException("x", Hr(0x70)) : null);
        var r = await Escribir(Datos(400_000), io: io);

        Fallo(r, MotivoDeEscritura.SinEspacio);
        Assert.Equal(3, io.Veces(nameof(IOperacionesDeArchivo.Borrar)));
        Assert.Empty(Entradas());
        Assert.DoesNotContain("No se pudo borrar", r.Detalle);
    }

    [Fact]
    public async Task SiElTemporalNoSePuedeBorrarNunca_NoSeOcultaElErrorOriginal_ConstaEnElDetalle_YNoLanza()
    {
        var io = new IoDeLaPrueba { BorrarHook = _ => throw new IOException("lo tiene el antivirus", Hr(0x20)) };
        io.CrearNuevoHook = ruta => new FlujoQueFalla(io.Real.CrearNuevo(ruta), escritos => escritos >= 80_000 ? new IOException("x", Hr(0x15)) : null);
        var r = await Escribir(Datos(400_000), io: io);

        Fallo(r, MotivoDeEscritura.MedioRetirado);                         // el motivo es el original, no el del borrado
        Assert.Equal(4, io.Veces(nameof(IOperacionesDeArchivo.Borrar)));    // el intento y tres reintentos
        Assert.Contains("No se pudo borrar el temporal", r.Detalle);
        var sobrante = Assert.Single(Entradas());                           // y el temporal sigue ahí, con el nombre que dice que es un temporal de ese archivo
        Assert.Matches(new Regex(@"^\.reporte\.xlsx\.[0-9a-f]{32}\.parte$"), sobrante);
    }

    // ---------------------------------------------------------------------------------------------------- el sistema de archivos de verdad, pieza por pieza

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(4095)]
    [InlineData(4096)]
    [InlineData(4097)]
    [InlineData(1_048_575)]
    [InlineData(1_048_576)]
    [InlineData(1_048_577)]
    [InlineData(5_243_003)]
    public async Task LaLecturaDeVerificacion_DaExactamenteLoQueHayEnElArchivo(int largo)
    {
        var datos = Datos(largo, 3);
        var ruta = Path.Combine(_carpeta, $"v{largo}.bin");
        await File.WriteAllBytesAsync(ruta, datos);

        await using var lectura = new OperacionesDeArchivoDelSistema().AbrirLectura(ruta);
        if (OperatingSystem.IsWindows()) Assert.IsType<LectorSinCache>(lectura);          // en un disco local de Windows se lee sin pasar por la memoria del sistema
        using var leido = new MemoryStream();
        await lectura.CopyToAsync(leido);
        Assert.Equal(datos, leido.ToArray());
    }

    [Fact]
    public void LaLecturaDeVerificacion_EsSoloLectura_YSinDesplazamiento()
    {
        var ruta = Path.Combine(_carpeta, "x.bin");
        File.WriteAllBytes(ruta, Datos(10_000));
        using var lectura = new OperacionesDeArchivoDelSistema().AbrirLectura(ruta);
        Assert.True(lectura.CanRead);
        Assert.False(lectura.CanWrite);
        if (lectura is LectorSinCache)
        {
            Assert.False(lectura.CanSeek);
            Assert.Equal(10_000, lectura.Length);
            Assert.Throws<NotSupportedException>(() => lectura.Seek(0, SeekOrigin.Begin));
            Assert.Throws<NotSupportedException>(() => lectura.Write([1], 0, 1));
            var cinco = new byte[5];
            Assert.Equal(5, lectura.Read(cinco, 0, 5));
            Assert.Equal(5, lectura.Position);
        }
    }

    [Fact]
    public void LaLecturaDeVerificacion_DeUnArchivoQueNoExiste_Lanza_YNoSeTomaPorFaltaDeSoporte()
    {
        var ex = Assert.ThrowsAny<IOException>(() => new OperacionesDeArchivoDelSistema().AbrirLectura(Path.Combine(_carpeta, "no-existe.bin")));
        Assert.False(LecturaDeVerificacion.SinSoporteDeLecturaDirecta(ex));                       // un archivo que no está es un fallo REAL: no se recurre a la lectura normal
    }

    [Fact]
    public void QueFalloLaLecturaDirecta_SoloSiElSistemaDiceQueNoLaSoporta()
    {
        foreach (var codigo in new[] { 1, 50, 87 })
            Assert.True(LecturaDeVerificacion.SinSoporteDeLecturaDirecta(new IOException("x", Hr(codigo))), $"código {codigo}");
        Assert.True(LecturaDeVerificacion.SinSoporteDeLecturaDirecta(new ArgumentException("opción no admitida")));
        Assert.True(LecturaDeVerificacion.SinSoporteDeLecturaDirecta(new NotSupportedException()));
        foreach (var real in new Exception[] { new IOException("x", Hr(0x15)), new IOException("x", Hr(0x70)), new FileNotFoundException(), new DirectoryNotFoundException(), new UnauthorizedAccessException() })
            Assert.False(LecturaDeVerificacion.SinSoporteDeLecturaDirecta(real), real.GetType().Name);
    }

    [Fact]
    public void LasOperacionesDelSistema_Existen_YMidenYMueven_SinSobrescribir()
    {
        var io = new OperacionesDeArchivoDelSistema();
        var archivo = Path.Combine(_carpeta, "a.txt");
        var otro = Path.Combine(_carpeta, "b.txt");
        File.WriteAllText(archivo, "uno");
        File.WriteAllText(otro, "dos");

        Assert.True(io.ExisteCarpeta(_carpeta));
        Assert.False(io.ExisteCarpeta(archivo));                                  // un archivo no es una carpeta
        Assert.False(io.ExisteCarpeta(Path.Combine(_carpeta, "nada")));
        Assert.False(io.ExisteCarpeta("  "));
        Assert.True(io.Existe(archivo));
        Assert.True(io.Existe(_carpeta));                                         // y un nombre ocupado por una carpeta cuenta como ocupado
        Assert.False(io.Existe(Path.Combine(_carpeta, "nada")));
        Assert.Equal(3, io.Tamano(archivo));

        var error = Assert.Throws<IOException>(() => io.MoverSinSobrescribir(archivo, otro));
        Assert.Equal(MotivoDeEscritura.Otro, MotivosDeEscritura.Clasificar(error).Motivo);
        Assert.Equal("dos", File.ReadAllText(otro));                              // el destino no se tocó
        Assert.True(File.Exists(archivo));                                        // ni se perdió el origen

        io.MoverSinSobrescribir(archivo, Path.Combine(_carpeta, "c.txt"));
        Assert.False(File.Exists(archivo));
        Assert.Equal("uno", File.ReadAllText(Path.Combine(_carpeta, "c.txt")));

        io.Borrar(Path.Combine(_carpeta, "c.txt"));
        io.Borrar(Path.Combine(_carpeta, "c.txt"));                               // borrar lo que ya no está no es un error
        io.VaciarADisco(otro);
        Assert.Equal("dos", File.ReadAllText(otro));
    }

    [Fact]
    public async Task CrearNuevo_NoPisaUnArchivoQueYaExiste()
    {
        var io = new OperacionesDeArchivoDelSistema();
        var ruta = Path.Combine(_carpeta, "unico.bin");
        await using (var primero = io.CrearNuevo(ruta)) await primero.WriteAsync(new byte[] { 1, 2, 3 });
        var error = Assert.ThrowsAny<IOException>(() => io.CrearNuevo(ruta));
        Assert.Equal(3, new FileInfo(ruta).Length);                               // el primero quedó intacto
        Assert.Equal(0x50, MotivosDeEscritura.CodigoDeWindows(error));            // ERROR_FILE_EXISTS
    }

    [Fact]
    public void ElEspacioLibre_DeUnaCarpetaReal_EsUnNumero_YDeUnaQueNoExiste_NoSeSabe()
    {
        var io = new OperacionesDeArchivoDelSistema();
        Assert.True(io.EspacioLibre(_carpeta) > 0);
        Assert.Null(io.EspacioLibre(Path.Combine(_carpeta, "no-existe", "tampoco")));
        Assert.Null(io.EspacioLibre("???"));
    }
}

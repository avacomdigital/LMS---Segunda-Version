using System.Security.Cryptography;
using System.Text;
using Avacom.Lms.Ops.Reportes;

namespace Avacom.Lms.Ops.Tests;

/// <summary>
/// Adónde se puede guardar un reporte (MOD-013): la lista de destinos con la política del administrador, la clase de una ruta elegida a mano, el aviso cuando se enchufa o se
/// retira una unidad y la última carpeta de cada persona. Todo con unidades y carpetas falsas: no hay memoria USB en el equipo de pruebas.
/// </summary>
public sealed class DestinosTests : IDisposable
{
    private readonly string _carpeta = Path.Combine(Path.GetTempPath(), "avacom-ops-tests", Guid.NewGuid().ToString("N"));

    public DestinosTests() => Directory.CreateDirectory(_carpeta);

    public void Dispose()
    {
        try { Directory.Delete(_carpeta, recursive: true); }
        catch { /* el sistema todavía la tiene: no importa, está en la carpeta temporal */ }
    }

    // ---------------------------------------------------------------------------------------------------- piezas falsas

    private static UnidadInfo U(string raiz, string etiqueta, TipoDeUnidad tipo, bool lista = true, long libre = 1_000, long total = 10_000, bool usb = false) =>
        new(raiz, etiqueta, tipo, lista, libre, total, usb);

    private static readonly UnidadInfo MemoriaUsb = U(@"E:\", "KINGSTON", TipoDeUnidad.Extraible, libre: 5_000, total: 16_000);
    private static readonly UnidadInfo DiscoExterno = U(@"F:\", "", TipoDeUnidad.Fija, libre: 100_000, total: 500_000, usb: true);       // Windows lo reporta «fijo»; el bus lo delata
    private static readonly UnidadInfo DiscoLocal = U(@"C:\", "OS", TipoDeUnidad.Fija, libre: 200_000, total: 1_000_000);
    private static readonly UnidadInfo UnidadDeRed = U(@"Z:\", "Compartida", TipoDeUnidad.Red, libre: 3_000, total: 9_000);
    private static readonly UnidadInfo LectorVacio = U(@"D:\", "", TipoDeUnidad.Optica, lista: false, libre: 0, total: 0);
    private static readonly UnidadInfo LectorConDisco = U(@"G:\", "PELICULA", TipoDeUnidad.Optica);
    private static readonly UnidadInfo LectorDeTarjetasVacio = U(@"I:\", "", TipoDeUnidad.Extraible, lista: false, libre: 0, total: 0);
    private static readonly UnidadInfo DiscoEnMemoria = U(@"R:\", "", TipoDeUnidad.Ram);
    private static readonly UnidadInfo SinRaiz = new("", "", TipoDeUnidad.SinRaiz, false, 0, 0, false);

    private static readonly UnidadInfo[] Todas = [DiscoLocal, LectorVacio, MemoriaUsb, DiscoExterno, UnidadDeRed, LectorConDisco, LectorDeTarjetasVacio, DiscoEnMemoria, SinRaiz];

    private sealed class UnidadesFalsas : IProveedorDeUnidades
    {
        private readonly object _candado = new();
        private readonly List<(int Meta, TaskCompletionSource Senal)> _esperas = [];
        private int _llamadas;

        public volatile IReadOnlyList<UnidadInfo> Lista = [];
        public volatile Exception? Lanza;
        public int Llamadas => Volatile.Read(ref _llamadas);

        public IReadOnlyList<UnidadInfo> Unidades()
        {
            var n = Interlocked.Increment(ref _llamadas);
            lock (_candado)
                foreach (var (meta, senal) in _esperas)
                    if (n >= meta) senal.TrySetResult();
            if (Lanza is { } error) throw error;
            return Lista;
        }

        /// <summary>Se completa cuando el proveedor ya fue consultado al menos <paramref name="meta"/> veces: así las pruebas esperan sondeos y no milisegundos.</summary>
        public Task EsperarLlamadas(int meta)
        {
            lock (_candado)
            {
                if (_llamadas >= meta) return Task.CompletedTask;
                var senal = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                _esperas.Add((meta, senal));
                return senal.Task;
            }
        }
    }

    private sealed class CarpetasFalsas(string? documentos = null, string? escritorio = null, string? descargas = null, bool lanza = false) : ICarpetasConocidas
    {
        public string? Documentos => lanza ? throw new IOException("sin acceso") : documentos;
        public string? Escritorio => lanza ? throw new IOException("sin acceso") : escritorio;
        public string? Descargas => lanza ? throw new IOException("sin acceso") : descargas;
    }

    private static readonly CarpetasFalsas CarpetasDeAna = new(@"C:\Users\Ana\Documents", @"C:\Users\Ana\Desktop", @"C:\Users\Ana\Downloads");

    private static UnidadesFalsas ConUnidades(params UnidadInfo[] unidades) => new() { Lista = unidades };

    private static CatalogoDeDestinos Catalogo(IProveedorDeUnidades unidades, ICarpetasConocidas? carpetas = null, PoliticaDeDestinos? politica = null) =>
        new(unidades, carpetas ?? CarpetasDeAna, politica ?? new PoliticaDeDestinos());

    private static string[] Ids(ResultadoDeBusqueda r) => r.Destinos.Select(d => d.Id).ToArray();

    // ---------------------------------------------------------------------------------------------------- el tipo de destino

    [Fact]
    public void LosCodigosDeTipo_SonElContratoConElBackend()
    {
        Assert.Equal("extraible", TipoDeDestino.Extraible.Codigo());
        Assert.Equal("carpeta_local", TipoDeDestino.CarpetaLocal.Codigo());
        Assert.Equal("red", TipoDeDestino.Red.Codigo());
        Assert.Equal("red", TiposDeDestino.Codigo(TipoDeDestino.Red));                  // también como llamada estática
        Assert.Equal(3, Enum.GetValues<TipoDeDestino>().Length);
        Assert.Throws<ArgumentOutOfRangeException>(() => ((TipoDeDestino)99).Codigo());
    }

    [Fact]
    public void UnaUnidadFijaQueCuelgaDeUsb_SeTrataComoExtraible()
    {
        Assert.Equal(TipoDeUnidad.Extraible, DiscoExterno.TipoEfectivo);
        Assert.Equal(TipoDeUnidad.Fija, DiscoLocal.TipoEfectivo);
        Assert.Equal(TipoDeUnidad.Extraible, MemoriaUsb.TipoEfectivo);
        Assert.Equal(TipoDeUnidad.Red, UnidadDeRed.TipoEfectivo);
        Assert.Equal(TipoDeUnidad.Red, (UnidadDeRed with { EsUsb = true }).TipoEfectivo);           // el bus sólo cambia a las fijas
    }

    [Theory]
    [InlineData(@"E:\", "E:")]
    [InlineData(@"e:\", "E:")]
    [InlineData("Z:", "Z:")]
    [InlineData(@"\\servidor\recurso", null)]
    [InlineData("", null)]
    [InlineData("1:\\", null)]
    public void LaLetra_DeLaRaiz(string raiz, string? esperada) => Assert.Equal(esperada, U(raiz, "", TipoDeUnidad.Fija).Letra);

    // ---------------------------------------------------------------------------------------------------- el catálogo

    [Fact]
    public void LaLista_TraeLosAtajos_LuegoExtraibles_LuegoInternas_LuegoRed()
    {
        var r = Catalogo(ConUnidades(Todas)).Buscar();

        Assert.Equal(["atajo:documentos", "atajo:escritorio", "atajo:descargas", "unidad:E", "unidad:F", "unidad:C", "unidad:Z"], Ids(r));
        Assert.Equal(["Documentos", "Escritorio", "Descargas", "KINGSTON", "Memoria USB (F:)", "OS", "Compartida"], r.Destinos.Select(d => d.Nombre).ToArray());
        Assert.Equal([TipoDeDestino.CarpetaLocal, TipoDeDestino.CarpetaLocal, TipoDeDestino.CarpetaLocal, TipoDeDestino.Extraible, TipoDeDestino.Extraible, TipoDeDestino.CarpetaLocal, TipoDeDestino.Red],
                     r.Destinos.Select(d => d.Tipo).ToArray());
        Assert.Equal([true, true, true, false, false, false, false], r.Destinos.Select(d => d.EsAtajo).ToArray());
        Assert.All(r.Destinos, d => Assert.True(d.Listo));
        Assert.True(r.HayExtraibles);
        Assert.False(r.ExtraiblesOcultosPorPolitica);
        Assert.Null(r.Aviso);
    }

    [Fact]
    public void LosAtajos_LlevanSuCarpeta_YNoTienenLetraNiTamanos()
    {
        var atajo = Catalogo(ConUnidades(DiscoLocal)).Buscar().Destinos[0];
        Assert.Equal(("atajo:documentos", "Documentos", @"C:\Users\Ana\Documents"), (atajo.Id, atajo.Nombre, atajo.Ruta));
        Assert.Null(atajo.Letra);
        Assert.Null(atajo.LibreBytes);
        Assert.Null(atajo.TotalBytes);
    }

    [Fact]
    public void LasUnidades_LlevanLetraRutaYTamanos()
    {
        var usb = Catalogo(ConUnidades(Todas)).Buscar().Destinos.Single(d => d.Id == "unidad:E");
        Assert.Equal(("E:", @"E:\", 5_000L, 16_000L), (usb.Letra, usb.Ruta, usb.LibreBytes, usb.TotalBytes));
        var externo = Catalogo(ConUnidades(Todas)).Buscar().Destinos.Single(d => d.Id == "unidad:F");
        Assert.Equal(TipoDeDestino.Extraible, externo.Tipo);                                         // el disco USB «fijo» se ofrece como extraíble
        Assert.Equal(100_000L, externo.LibreBytes);
    }

    [Fact]
    public void SinEtiqueta_ElNombreEsLaClaseDeUnidadMasLaLetra()
    {
        var sinEtiqueta = new[]
        {
            U(@"C:\", "", TipoDeUnidad.Fija), U(@"E:\", "  ", TipoDeUnidad.Extraible), U(@"Z:\", "", TipoDeUnidad.Red), U(@"F:\", "", TipoDeUnidad.Fija, usb: true),
        };
        var nombres = Catalogo(ConUnidades(sinEtiqueta), new CarpetasFalsas()).Buscar().Destinos.ToDictionary(d => d.Id, d => d.Nombre);
        Assert.Equal("Disco local (C:)", nombres["unidad:C"]);
        Assert.Equal("Memoria USB (E:)", nombres["unidad:E"]);
        Assert.Equal("Unidad de red (Z:)", nombres["unidad:Z"]);
        Assert.Equal("Memoria USB (F:)", nombres["unidad:F"]);
    }

    [Fact]
    public void LoQueNoEsUnLugarDondeGuardar_NoEntra()
    {
        var ids = Ids(Catalogo(ConUnidades(LectorVacio, LectorConDisco, LectorDeTarjetasVacio, DiscoEnMemoria, SinRaiz), new CarpetasFalsas()).Buscar());
        Assert.Empty(ids);                                  // ni el lector sin disco, ni el lector con disco, ni el de tarjetas vacío, ni el disco en RAM, ni la unidad sin raíz
    }

    [Fact]
    public void SinExtraibles_Quedan_LosAtajos_YUnAvisoParaConectarUna()
    {
        var r = Catalogo(ConUnidades(DiscoLocal, UnidadDeRed, LectorDeTarjetasVacio)).Buscar();
        Assert.Equal(["atajo:documentos", "atajo:escritorio", "atajo:descargas", "unidad:C", "unidad:Z"], Ids(r));
        Assert.False(r.HayExtraibles);
        Assert.False(r.ExtraiblesOcultosPorPolitica);
        Assert.Equal("Conecta una memoria USB y toca Buscar de nuevo.", r.Aviso);
        Assert.Equal(AvisosDeDestinos.SinExtraibles, r.Aviso);
    }

    [Fact]
    public void ConLaPoliticaSinExtraibles_NoSeOfrecenNiLasMemoriasNiLosDiscosUsb_YSeDiceElPorQue()
    {
        var r = Catalogo(ConUnidades(Todas), politica: new PoliticaDeDestinos(PermitirExtraibles: false)).Buscar();
        Assert.Equal(["atajo:documentos", "atajo:escritorio", "atajo:descargas", "unidad:C", "unidad:Z"], Ids(r));
        Assert.DoesNotContain(r.Destinos, d => d.Tipo == TipoDeDestino.Extraible);
        Assert.False(r.HayExtraibles);
        Assert.True(r.ExtraiblesOcultosPorPolitica);
        Assert.Equal("El administrador del colegio desactivó guardar reportes en memorias USB.", r.Aviso);
    }

    [Fact]
    public void LaPoliticaSinExtraibles_SeDiceAunqueNoHayaNingunaMemoriaConectada()
    {
        // si no se dijera, «Conecta una memoria USB» mandaría a conectar algo que no se va a ofrecer de todos modos
        var r = Catalogo(ConUnidades(DiscoLocal), politica: new PoliticaDeDestinos(PermitirExtraibles: false)).Buscar();
        Assert.True(r.ExtraiblesOcultosPorPolitica);
        Assert.Equal(AvisosDeDestinos.ExtraiblesDesactivados, r.Aviso);
    }

    [Fact]
    public void ConLaPoliticaSinRed_NoSeOfrecenLasUnidadesDeRed_PeroSiLoDemas()
    {
        var r = Catalogo(ConUnidades(Todas), politica: new PoliticaDeDestinos(PermitirRed: false)).Buscar();
        Assert.Equal(["atajo:documentos", "atajo:escritorio", "atajo:descargas", "unidad:E", "unidad:F", "unidad:C"], Ids(r));
        Assert.True(r.HayExtraibles);
        Assert.Null(r.Aviso);
    }

    [Fact]
    public void LosAtajosRedirigidosALaRed_SonDeRed_YSiguenLaPolitica()
    {
        var redirigidos = new CarpetasFalsas(@"\\servidor\usuarios\ana\Documentos", @"Z:\Escritorio", @"C:\Users\Ana\Downloads");
        var permitida = Catalogo(ConUnidades(DiscoLocal, UnidadDeRed), redirigidos).Buscar();
        Assert.Equal([TipoDeDestino.Red, TipoDeDestino.Red, TipoDeDestino.CarpetaLocal], permitida.Destinos.Take(3).Select(d => d.Tipo).ToArray());

        var prohibida = Catalogo(ConUnidades(DiscoLocal, UnidadDeRed), redirigidos, new PoliticaDeDestinos(PermitirRed: false)).Buscar();
        Assert.Equal(["atajo:descargas", "unidad:C"], Ids(prohibida));
    }

    [Fact]
    public void ConExtraiblesPermitidosYConectados_NoHayAviso()
    {
        var r = Catalogo(ConUnidades(MemoriaUsb)).Buscar();
        Assert.True(r.HayExtraibles);
        Assert.Null(r.Aviso);
    }

    [Fact]
    public void UnProveedorQueLanza_DejaLosAtajos_YElAvisoDeQueNoHayMemorias()
    {
        var r = Catalogo(new UnidadesFalsas { Lanza = new IOException("se retiró la memoria") }).Buscar();
        Assert.Equal(["atajo:documentos", "atajo:escritorio", "atajo:descargas"], Ids(r));
        Assert.Equal(AvisosDeDestinos.SinExtraibles, r.Aviso);
    }

    [Fact]
    public void Carpetas_QueNoExistenOFallan_NoSeOfrecen_NiSeRepiten()
    {
        // nulas o en blanco: no están; que lance: tampoco rompe nada
        Assert.Equal(["atajo:escritorio"], Ids(Catalogo(ConUnidades(), new CarpetasFalsas(null, @"C:\Users\Ana\Desktop", "  ")).Buscar()));
        Assert.Empty(Catalogo(ConUnidades(), new CarpetasFalsas(lanza: true)).Buscar().Destinos);
        // dos atajos a la MISMA carpeta (sin distinguir mayúsculas ni la barra final) salen una vez
        Assert.Equal(["atajo:documentos"], Ids(Catalogo(ConUnidades(), new CarpetasFalsas(@"C:\Users\Ana\Documents", @"c:\users\ana\documents\", @"C:\USERS\ANA\DOCUMENTS")).Buscar()));
    }

    [Fact]
    public void LaListaNuncaQuedaVacia_PorFaltaDeExtraibles()
    {
        var r = Catalogo(ConUnidades()).Buscar();
        Assert.Equal(3, r.Destinos.Count);                  // los tres atajos
        Assert.All(r.Destinos, d => Assert.True(d.EsAtajo));
    }

    [Fact]
    public void LosIdsSonEstables_EntreBusquedas()
    {
        var catalogo = Catalogo(ConUnidades(Todas));
        Assert.Equal(Ids(catalogo.Buscar()), Ids(catalogo.Buscar()));
    }

    [Fact]
    public void ElCatalogo_ExigeSusDependencias()
    {
        Assert.Throws<ArgumentNullException>(() => new CatalogoDeDestinos(null!, CarpetasDeAna, new PoliticaDeDestinos()));
        Assert.Throws<ArgumentNullException>(() => new CatalogoDeDestinos(ConUnidades(), null!, new PoliticaDeDestinos()));
        Assert.Throws<ArgumentNullException>(() => new CatalogoDeDestinos(ConUnidades(), CarpetasDeAna, null!));
    }

    [Fact]
    public void LaPoliticaPorOmision_PermiteTodo()
    {
        var politica = new PoliticaDeDestinos();
        Assert.True(politica.PermitirExtraibles);
        Assert.True(politica.PermitirRed);
    }

    // ---------------------------------------------------------------------------------------------------- las carpetas del sistema y las unidades reales (sin hardware)

    [Fact]
    public void LasCarpetasDelSistema_SonNulasOExisten_YNuncaLanzan()
    {
        var carpetas = new CarpetasConocidasDelSistema();
        foreach (var ruta in new[] { carpetas.Documentos, carpetas.Escritorio, carpetas.Descargas })
            Assert.True(ruta is null || Directory.Exists(ruta), $"«{ruta}» se ofrece pero no existe");
    }

    [Fact]
    public void LasUnidadesDelSistema_NoLanzan_YIncluyenLaDelEquipo()
    {
        if (!OperatingSystem.IsWindows()) return;           // las letras de unidad son de Windows
        var unidades = new ProveedorDeUnidadesDelSistema().Unidades();
        var raiz = Path.GetPathRoot(Path.GetTempPath())!;
        if (raiz.Length < 2 || !char.IsAsciiLetter(raiz[0]) || raiz[1] != ':') return;         // si la carpeta temporal está en una ruta de red no hay letra que buscar
        var delEquipo = unidades.Single(u => string.Equals(u.Raiz, raiz, StringComparison.OrdinalIgnoreCase));
        Assert.True(delEquipo.Lista);
        Assert.True(delEquipo.TotalBytes > 0);
        Assert.True(delEquipo.LibreBytes >= 0);
        Assert.NotEqual(TipoDeUnidad.Desconocida, delEquipo.Tipo);
    }

    [Theory]
    [InlineData("")]
    [InlineData("E")]
    [InlineData(@"\\servidor\recurso")]
    [InlineData(@"1:\")]
    [InlineData(@"ñ:\")]
    [InlineData("\0:\\")]
    public void ElDetectorDeUsb_ConUnaRaizQueNoEsUnaLetra_DiceQueNo(string raiz) => Assert.False(DetectorDeUsb.EsUsb(raiz));

    [Fact]
    public void ElDetectorDeUsb_ConUnaUnidadQueNoExiste_DiceQueNo_YNoLanza()
    {
        var existentes = DriveInfo.GetDrives().Select(d => char.ToUpperInvariant(d.Name[0])).ToHashSet();
        var libre = "QRSTUVWXYZ".First(c => !existentes.Contains(c));
        Assert.False(DetectorDeUsb.EsUsb($@"{libre}:\"));
    }

    [Fact]
    public void ElDetectorDeUsb_ConLasUnidadesReales_NoLanza()
    {
        foreach (var unidad in DriveInfo.GetDrives())
            _ = DetectorDeUsb.EsUsb(unidad.Name);           // sea cual sea la respuesta (depende de lo que haya conectado), no debe lanzar ni colgarse
    }

    // ---------------------------------------------------------------------------------------------------- comprobar que una carpeta existe, con plazo

    [Fact]
    public void Existencia_UnaComprobacionQueSeCuelga_DiceQueNo_SinEsperarlaParaSiempre()
    {
        using var colgada = new ManualResetEventSlim(false);
        try
        {
            var reloj = System.Diagnostics.Stopwatch.StartNew();
            Assert.False(Existencia.DeCarpeta(@"\\servidor\apagado\reportes", TimeSpan.FromMilliseconds(100), _ => { colgada.Wait(); return true; }));
            Assert.True(reloj.Elapsed < TimeSpan.FromSeconds(10), $"tardó {reloj.Elapsed}");
        }
        finally { colgada.Set(); }
    }

    [Fact]
    public void Existencia_LoQueContestaAHora_SeRespeta_YLoQueLanzaOEstaEnBlanco_EsQueNo()
    {
        Assert.True(Existencia.DeCarpeta(@"E:\Reportes", TimeSpan.FromSeconds(10), _ => true));
        Assert.False(Existencia.DeCarpeta(@"E:\Reportes", TimeSpan.FromSeconds(10), _ => false));
        Assert.False(Existencia.DeCarpeta(@"E:\Reportes", TimeSpan.FromSeconds(10), _ => throw new IOException("se retiró")));
        Assert.False(Existencia.DeCarpeta("   ", TimeSpan.FromSeconds(10), _ => true));
        Assert.False(Existencia.DeCarpeta(null, TimeSpan.FromSeconds(10), _ => true));
        Assert.True(Existencia.DeCarpeta(_carpeta, TimeSpan.FromSeconds(10)));                    // con el sistema de archivos de verdad
        Assert.False(Existencia.DeCarpeta(Path.Combine(_carpeta, "no-existe"), TimeSpan.FromSeconds(10)));
    }

    // ---------------------------------------------------------------------------------------------------- unidades que se cuelgan o que fallan

    private static RaizDeUnidad Raiz(string raiz, TipoDeUnidad tipo) => new(raiz, tipo);

    [Fact]
    public void UnaUnidadQueLanzaAlLeerla_QuedaNoLista_YNoTumbaLasDemas()
    {
        var proveedor = new ProveedorDeUnidadesDelSistema(
            () => [Raiz(@"C:\", TipoDeUnidad.Fija), Raiz(@"E:\", TipoDeUnidad.Extraible)],
            r => r.Raiz == @"E:\" ? throw new IOException("se retiró") : U(r.Raiz, "OS", r.Tipo),
            TimeSpan.FromSeconds(5));

        var unidades = proveedor.Unidades();
        Assert.Equal([@"C:\", @"E:\"], unidades.Select(u => u.Raiz).ToArray());
        Assert.True(unidades[0].Lista);
        Assert.False(unidades[1].Lista);
        Assert.Equal(TipoDeUnidad.Extraible, unidades[1].Tipo);                       // lo único que se sabía de ella se conserva
    }

    [Fact]
    public void SiNoSePuedenEnumerarLasUnidades_LaListaEstaVacia_YNoLanza()
    {
        var proveedor = new ProveedorDeUnidadesDelSistema(() => throw new UnauthorizedAccessException(), r => U(r.Raiz, "", r.Tipo), TimeSpan.FromSeconds(5));
        Assert.Empty(proveedor.Unidades());
    }

    [Fact]
    public async Task UnaUnidadQueSeCuelga_NoCongelaLaLista_NiSeApilanLecturas()
    {
        using var liberar = new ManualResetEventSlim(false);
        var lecturasDeRed = 0;
        var proveedor = new ProveedorDeUnidadesDelSistema(
            () => [Raiz(@"C:\", TipoDeUnidad.Fija), Raiz(@"Z:\", TipoDeUnidad.Red)],
            r =>
            {
                if (r.Raiz != @"Z:\") return U(r.Raiz, "OS", r.Tipo);
                Interlocked.Increment(ref lecturasDeRed);
                liberar.Wait();                                                       // la unidad de red mapeada cuyo servidor está apagado: Windows no contesta
                return U(r.Raiz, "Compartida", r.Tipo);
            },
            TimeSpan.FromMilliseconds(200));

        try
        {
            var reloj = System.Diagnostics.Stopwatch.StartNew();
            var primera = proveedor.Unidades();
            var segunda = proveedor.Unidades();
            reloj.Stop();

            Assert.True(reloj.Elapsed < TimeSpan.FromSeconds(10), $"las dos lecturas tardaron {reloj.Elapsed}");     // con un plazo de 200 ms; sin el plazo no volvería nunca
            Assert.True(primera[0].Lista);                                            // la que sí contesta, sale
            Assert.False(primera[1].Lista);                                           // la colgada, como «no lista»
            Assert.Equal(TipoDeUnidad.Red, primera[1].Tipo);
            Assert.False(segunda[1].Lista);
            Assert.Equal(1, Volatile.Read(ref lecturasDeRed));                        // la segunda llamada esperó la MISMA lectura: no apiló otra hebra bloqueada

            liberar.Set();                                                            // por fin contesta
            UnidadInfo? red = null;
            for (var intento = 0; intento < 500 && red is not { Lista: true }; intento++)
            {
                red = proveedor.Unidades()[1];
                if (!red.Lista) await Task.Delay(10);
            }
            Assert.True(red is { Lista: true, Etiqueta: "Compartida" });              // y a partir de ahí se ve
        }
        finally { liberar.Set(); }
    }

    // ---------------------------------------------------------------------------------------------------- la clase de una ruta elegida a mano

    [Theory]
    [InlineData(@"E:\Reportes", TipoDeDestino.Extraible)]
    [InlineData(@"e:\reportes", TipoDeDestino.Extraible)]          // la letra sin distinguir mayúsculas
    [InlineData(@"E:", TipoDeDestino.Extraible)]
    [InlineData(@"\\?\E:\Reportes", TipoDeDestino.Extraible)]
    [InlineData(@"F:\Datos", TipoDeDestino.Extraible)]             // el disco USB que Windows ve «fijo»
    [InlineData(@"C:\Users\x", TipoDeDestino.CarpetaLocal)]
    [InlineData(@"\\srv\carpeta", TipoDeDestino.Red)]
    [InlineData(@"\\srv\carpeta\sub\dir", TipoDeDestino.Red)]
    [InlineData("//srv/carpeta", TipoDeDestino.Red)]
    [InlineData(@"\\?\UNC\srv\carpeta", TipoDeDestino.Red)]
    [InlineData(@"Z:\", TipoDeDestino.Red)]                        // la letra mapeada a la red
    [InlineData(@"z:\Reportes\2026", TipoDeDestino.Red)]
    [InlineData(@"Reportes\2026", TipoDeDestino.CarpetaLocal)]     // relativa
    [InlineData("Reportes", TipoDeDestino.CarpetaLocal)]
    [InlineData(@"Q:\Desconocida", TipoDeDestino.CarpetaLocal)]    // una letra que no está entre las unidades
    [InlineData(@"G:\Peliculas", TipoDeDestino.CarpetaLocal)]      // un lector óptico: no es extraíble ni de red
    [InlineData("", TipoDeDestino.CarpetaLocal)]
    [InlineData("   ", TipoDeDestino.CarpetaLocal)]
    public void ClasificadorDeRuta_DiceDeQueClaseEsElLugar(string ruta, TipoDeDestino esperado) =>
        Assert.Equal(esperado, ClasificadorDeRuta.Clasificar(ruta, ConUnidades(Todas)));

    [Fact]
    public void ClasificadorDeRuta_ConUnProveedorQueLanza_TomaPorLocalLoQueNoSePuedeSaber()
    {
        var proveedor = new UnidadesFalsas { Lanza = new IOException("x") };
        Assert.Equal(TipoDeDestino.CarpetaLocal, ClasificadorDeRuta.Clasificar(@"E:\Reportes", proveedor));
        Assert.Equal(TipoDeDestino.Red, ClasificadorDeRuta.Clasificar(@"\\srv\x", proveedor));          // y una UNC es de red sin preguntarle nada a las unidades
    }

    [Fact]
    public void ClasificadorDeRuta_NoLeeLasUnidades_SiLaRutaNoLasNecesita()
    {
        var proveedor = ConUnidades(Todas);
        _ = ClasificadorDeRuta.Clasificar(@"\\srv\x", proveedor);
        _ = ClasificadorDeRuta.Clasificar(@"relativa\x", proveedor);
        Assert.Equal(0, proveedor.Llamadas);
        _ = ClasificadorDeRuta.Clasificar(@"E:\x", proveedor);
        Assert.Equal(1, proveedor.Llamadas);
    }

    // ---------------------------------------------------------------------------------------------------- el vigilante: la comparación, sin reloj

    /// <summary>Un vigilante SIN iniciar: sus lecturas se piden a mano con <c>Sondear</c>, así que no depende del tiempo.</summary>
    private static VigilanteDeUnidades SinReloj(IProveedorDeUnidades unidades) => new(unidades, TimeSpan.FromSeconds(1));

    [Fact]
    public void Sondear_LaPrimeraLecturaEsLaBase_YSoloLosCambiosAvisan()
    {
        var unidades = ConUnidades(DiscoLocal);
        using var vigilante = SinReloj(unidades);
        var avisos = 0;
        vigilante.Cambio += () => avisos++;

        Assert.False(vigilante.Sondear());                  // la base
        Assert.False(vigilante.Sondear());                  // nada cambió

        unidades.Lista = [DiscoLocal, MemoriaUsb];          // se enchufa
        Assert.True(vigilante.Sondear());
        Assert.False(vigilante.Sondear());                  // y ya no es novedad

        unidades.Lista = [DiscoLocal];                      // se retira
        Assert.True(vigilante.Sondear());
        Assert.Equal(2, avisos);
    }

    [Fact]
    public void Sondear_ElEspacioLibreNoEsUnCambio_PeroLaEtiquetaYElTamanoSi()
    {
        var unidades = ConUnidades(DiscoLocal, MemoriaUsb);
        using var vigilante = SinReloj(unidades);
        vigilante.Sondear();

        unidades.Lista = [DiscoLocal, MemoriaUsb with { LibreBytes = 1 }];            // se escribió algo en la memoria
        Assert.False(vigilante.Sondear());

        unidades.Lista = [DiscoLocal, MemoriaUsb with { Etiqueta = "OTRA" }];         // otra memoria en la misma letra, entre un sondeo y el siguiente
        Assert.True(vigilante.Sondear());

        unidades.Lista = [DiscoLocal, MemoriaUsb with { Etiqueta = "OTRA", TotalBytes = 32_000 }];
        Assert.True(vigilante.Sondear());
    }

    [Fact]
    public void Sondear_UnaUnidadQuePasaAEstarListaOSeTrataDistinto_EsUnCambio()
    {
        var unidades = ConUnidades(DiscoLocal, LectorDeTarjetasVacio);
        using var vigilante = SinReloj(unidades);
        vigilante.Sondear();

        unidades.Lista = [DiscoLocal, LectorDeTarjetasVacio with { Lista = true, Etiqueta = "SD", TotalBytes = 8_000 }];       // se metió una tarjeta
        Assert.True(vigilante.Sondear());

        unidades.Lista = [DiscoLocal, DiscoExterno];                                  // otra unidad
        Assert.True(vigilante.Sondear());
        unidades.Lista = [DiscoLocal, DiscoExterno with { EsUsb = false }];           // pasa de «extraíble efectivo» a «fija»
        Assert.True(vigilante.Sondear());
    }

    [Fact]
    public void Sondear_ElOrdenEnQueLlegaLaListaNoEsUnCambio()
    {
        var unidades = ConUnidades(DiscoLocal, MemoriaUsb, UnidadDeRed);
        using var vigilante = SinReloj(unidades);
        vigilante.Sondear();
        unidades.Lista = [UnidadDeRed, DiscoLocal, MemoriaUsb];
        Assert.False(vigilante.Sondear());
    }

    [Fact]
    public void Sondear_UnProveedorQueLanza_NoEsUnCambio_YNoPierdeLaBase()
    {
        var unidades = ConUnidades(DiscoLocal);
        using var vigilante = SinReloj(unidades);
        vigilante.Sondear();

        unidades.Lanza = new IOException("se retiró la memoria a mitad de la lectura");
        Assert.False(vigilante.Sondear());
        Assert.False(vigilante.Sondear());

        unidades.Lanza = null;                              // vuelve igual que estaba: no pasó nada
        Assert.False(vigilante.Sondear());

        unidades.Lanza = new IOException("otra vez");
        Assert.False(vigilante.Sondear());
        unidades.Lanza = null;
        unidades.Lista = [DiscoLocal, MemoriaUsb];          // y esta vez sí cambió: se avisa
        Assert.True(vigilante.Sondear());
    }

    [Fact]
    public void Sondear_SiLaPrimeraLecturaFallo_LaPrimeraBuenaEsLaBase()
    {
        var unidades = new UnidadesFalsas { Lanza = new IOException("x"), Lista = [DiscoLocal] };
        using var vigilante = SinReloj(unidades);
        Assert.False(vigilante.Sondear());
        unidades.Lanza = null;
        Assert.False(vigilante.Sondear());                  // sin base anterior no se sabe qué cambió: ésta lo es
        unidades.Lista = [DiscoLocal, MemoriaUsb];
        Assert.True(vigilante.Sondear());
    }

    [Fact]
    public void Sondear_DespuesDeDispose_NoHaceNada()
    {
        var unidades = ConUnidades(DiscoLocal);
        var vigilante = SinReloj(unidades);
        vigilante.Sondear();
        vigilante.Dispose();
        var llamadas = unidades.Llamadas;
        unidades.Lista = [DiscoLocal, MemoriaUsb];
        Assert.False(vigilante.Sondear());
        Assert.Equal(llamadas, unidades.Llamadas);          // ni siquiera le pregunta al proveedor
    }

    [Fact]
    public void UnManejadorQueLanza_NoCallaALosDemas_NiRompeElSondeo()
    {
        var unidades = ConUnidades(DiscoLocal);
        using var vigilante = SinReloj(unidades);
        var recibidos = new List<string>();
        vigilante.Cambio += () => throw new InvalidOperationException("el que escucha falló");
        vigilante.Cambio += () => recibidos.Add("segundo");
        vigilante.Sondear();

        unidades.Lista = [DiscoLocal, MemoriaUsb];
        Assert.True(vigilante.Sondear());
        unidades.Lista = [DiscoLocal];
        Assert.True(vigilante.Sondear());
        Assert.Equal(["segundo", "segundo"], recibidos);
    }

    [Fact]
    public void ElVigilante_ExigeSusArgumentos()
    {
        Assert.Throws<ArgumentNullException>(() => new VigilanteDeUnidades(null!, TimeSpan.FromSeconds(1)));
        Assert.Throws<ArgumentOutOfRangeException>(() => new VigilanteDeUnidades(ConUnidades(), TimeSpan.Zero));
        Assert.Throws<ArgumentOutOfRangeException>(() => new VigilanteDeUnidades(ConUnidades(), TimeSpan.FromSeconds(-1)));
    }

    // ---------------------------------------------------------------------------------------------------- el vigilante con reloj (intervalos de milisegundos)

    private static readonly TimeSpan Tic = TimeSpan.FromMilliseconds(10);
    private static readonly TimeSpan Limite = TimeSpan.FromSeconds(20);          // sólo es la red de seguridad: las pruebas terminan en cuanto pasa lo que esperan

    [Fact]
    public async Task ElVigilante_AvisaAlEnchufarYAlRetirar()
    {
        var unidades = ConUnidades(DiscoLocal);
        using var vigilante = new VigilanteDeUnidades(unidades, Tic);
        var avisos = new SemaphoreSlim(0);
        vigilante.Cambio += () => avisos.Release();
        vigilante.Iniciar();

        unidades.Lista = [DiscoLocal, MemoriaUsb];          // se enchufa la memoria
        Assert.True(await avisos.WaitAsync(Limite));

        unidades.Lista = [DiscoLocal];                      // se retira
        Assert.True(await avisos.WaitAsync(Limite));
    }

    [Fact]
    public async Task ElVigilante_NoAvisaSiNadaCambia()
    {
        var unidades = ConUnidades(DiscoLocal, MemoriaUsb);
        using var vigilante = new VigilanteDeUnidades(unidades, Tic);
        var avisos = 0;
        vigilante.Cambio += () => Interlocked.Increment(ref avisos);
        vigilante.Iniciar();

        await unidades.EsperarLlamadas(1 + 12).WaitAsync(Limite);            // la base de Iniciar y doce sondeos más
        Assert.Equal(0, Volatile.Read(ref avisos));
    }

    [Fact]
    public async Task ElVigilante_ConUnProveedorQueLanza_NoAvisa_PeroSigueVivo()
    {
        var unidades = ConUnidades(DiscoLocal);
        using var vigilante = new VigilanteDeUnidades(unidades, Tic);
        var avisos = new SemaphoreSlim(0);
        vigilante.Cambio += () => avisos.Release();
        vigilante.Iniciar();

        unidades.Lanza = new IOException("se retiró la memoria a mitad de la lectura");
        var antes = unidades.Llamadas;
        await unidades.EsperarLlamadas(antes + 8).WaitAsync(Limite);        // ocho sondeos fallidos seguidos
        Assert.Equal(0, avisos.CurrentCount);                               // no son un cambio

        unidades.Lanza = null;                                              // la unidad vuelve...
        unidades.Lista = [DiscoLocal, MemoriaUsb];                          // ...y con una memoria nueva: el vigilante, que no murió, lo ve
        Assert.True(await avisos.WaitAsync(Limite));
    }

    [Fact]
    public async Task ElVigilante_IniciarYDisposeRepetidos_SonSeguros_YDespuesDeDisposeNoSondea()
    {
        var unidades = ConUnidades(DiscoLocal);
        var vigilante = new VigilanteDeUnidades(unidades, Tic);
        var avisos = 0;
        vigilante.Cambio += () => Interlocked.Increment(ref avisos);

        vigilante.Iniciar();
        vigilante.Iniciar();                                // una segunda vez no arranca otro reloj
        await unidades.EsperarLlamadas(1 + 5).WaitAsync(Limite);

        vigilante.Dispose();
        vigilante.Dispose();
        vigilante.Iniciar();                                // y tras liberarlo no revive

        await Task.Delay(40);                               // si siguiera sondeando cada 10 ms haría unos cuatro más
        var llamadas = unidades.Llamadas;
        await Task.Delay(120);
        Assert.True(unidades.Llamadas - llamadas <= 1, $"siguió sondeando después de Dispose: {unidades.Llamadas - llamadas} lecturas");
        unidades.Lista = [DiscoLocal, MemoriaUsb];
        await Task.Delay(60);
        Assert.Equal(0, Volatile.Read(ref avisos));
    }

    [Fact]
    public async Task ElVigilante_UnDisposeAntesDeIniciar_NoHaceNada()
    {
        var unidades = ConUnidades(DiscoLocal);
        var vigilante = new VigilanteDeUnidades(unidades, Tic);
        vigilante.Dispose();
        vigilante.Iniciar();
        await Task.Delay(60);
        Assert.Equal(0, unidades.Llamadas);
    }

    [Fact]
    public async Task ElVigilante_SePuedeLiberarDesdeElPropioManejador_SinColgarse()
    {
        var unidades = ConUnidades(DiscoLocal);
        var vigilante = new VigilanteDeUnidades(unidades, Tic);
        var llego = new TaskCompletionSource();
        vigilante.Cambio += () =>
        {
            vigilante.Dispose();                            // se llama desde la hebra del propio vigilante: esperar a que termine sería un abrazo mortal
            llego.TrySetResult();
        };
        vigilante.Iniciar();
        unidades.Lista = [DiscoLocal, MemoriaUsb];
        await llego.Task.WaitAsync(Limite);

        var llamadas = unidades.Llamadas;
        await Task.Delay(100);
        Assert.True(unidades.Llamadas - llamadas <= 1);
    }

    [Fact]
    public async Task ElVigilante_UnManejadorQueLanza_NoLoDetiene()
    {
        var unidades = ConUnidades(DiscoLocal);
        using var vigilante = new VigilanteDeUnidades(unidades, Tic);
        var avisos = new SemaphoreSlim(0);
        vigilante.Cambio += () => throw new InvalidOperationException("el que escucha falló");
        vigilante.Cambio += () => avisos.Release();
        vigilante.Iniciar();

        unidades.Lista = [DiscoLocal, MemoriaUsb];
        Assert.True(await avisos.WaitAsync(Limite));
        unidades.Lista = [DiscoLocal];
        Assert.True(await avisos.WaitAsync(Limite));        // y sigue avisando
    }

    // ---------------------------------------------------------------------------------------------------- la última carpeta de cada persona

    private sealed class AlmacenFalso : IAlmacenDePreferencias
    {
        public Dictionary<string, string> Valores { get; } = [];
        public bool LanzaAlLeer { get; set; }
        public bool LanzaAlGuardar { get; set; }

        public string? Leer(string clave) => LanzaAlLeer ? throw new InvalidOperationException("almacén roto") : Valores.GetValueOrDefault(clave);

        public void Guardar(string clave, string valor)
        {
            if (LanzaAlGuardar) throw new InvalidOperationException("almacén roto");
            Valores[clave] = valor;
        }
    }

    private string CarpetaReal(string nombre)
    {
        var ruta = Path.Combine(_carpeta, nombre);
        Directory.CreateDirectory(ruta);
        return ruta;
    }

    [Fact]
    public void LaUltimaCarpeta_SeRecuerdaPorUsuario()
    {
        var almacen = new AlmacenFalso();
        var preferencias = new PreferenciasDeDestino(almacen);
        var deAna = CarpetaReal("ana");
        var deLuis = CarpetaReal("luis");

        Assert.Null(preferencias.UltimaCarpeta("u-ana"));               // todavía no eligió
        preferencias.RecordarCarpeta("u-ana", deAna);
        preferencias.RecordarCarpeta("u-luis", deLuis);

        Assert.Equal(deAna, preferencias.UltimaCarpeta("u-ana"));
        Assert.Equal(deLuis, preferencias.UltimaCarpeta("u-luis"));
        Assert.Null(preferencias.UltimaCarpeta("u-marta"));            // otra persona no hereda la de nadie

        preferencias.RecordarCarpeta("u-ana", deLuis);                  // la nueva reemplaza a la anterior
        Assert.Equal(deLuis, preferencias.UltimaCarpeta("u-ana"));
        Assert.Equal(2, almacen.Valores.Count);
    }

    [Fact]
    public void SiLaCarpetaRecordadaYaNoExiste_NoSeOfrece()
    {
        var preferencias = new PreferenciasDeDestino(new AlmacenFalso());
        var carpeta = CarpetaReal("temporal");
        preferencias.RecordarCarpeta("u-ana", carpeta);
        Assert.Equal(carpeta, preferencias.UltimaCarpeta("u-ana"));

        Directory.Delete(carpeta);                                      // se retiró la memoria, se borró la carpeta
        Assert.Null(preferencias.UltimaCarpeta("u-ana"));
    }

    [Fact]
    public void LaClave_NoLlevaElIdentificadorEnClaro_SinoSuResumen()
    {
        var clave = PreferenciasDeDestino.Clave("u-ana-perez-1234");
        var resumen = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes("u-ana-perez-1234")))[..16];
        Assert.Equal("reportes.ultima_carpeta." + resumen, clave);
        Assert.Equal("reportes.ultima_carpeta.", PreferenciasDeDestino.PrefijoDeClave);
        Assert.DoesNotContain("ana", clave);
        Assert.Matches("^reportes\\.ultima_carpeta\\.[0-9a-f]{16}$", clave);
        Assert.NotEqual(clave, PreferenciasDeDestino.Clave("u-luis"));
        Assert.Equal(clave, PreferenciasDeDestino.Clave("u-ana-perez-1234"));      // estable
        Assert.Matches("^reportes\\.ultima_carpeta\\.[0-9a-f]{16}$", PreferenciasDeDestino.Clave(null));       // sin sesión también hay clave

        var almacen = new AlmacenFalso();
        new PreferenciasDeDestino(almacen).RecordarCarpeta("u-ana-perez-1234", CarpetaReal("x"));
        Assert.Equal([clave], almacen.Valores.Keys.ToArray());                       // y es la única que se escribe
    }

    [Fact]
    public void UnaRutaVaciaNoSeAnota_NiUnaNoGuardadaSeOfrece()
    {
        var almacen = new AlmacenFalso();
        var preferencias = new PreferenciasDeDestino(almacen);
        preferencias.RecordarCarpeta("u-ana", "");
        preferencias.RecordarCarpeta("u-ana", "   ");
        Assert.Empty(almacen.Valores);

        almacen.Valores[PreferenciasDeDestino.Clave("u-ana")] = "  ";
        Assert.Null(preferencias.UltimaCarpeta("u-ana"));
    }

    [Fact]
    public void UnAlmacenQueFalla_NoHaceFallarNada()
    {
        var almacen = new AlmacenFalso { LanzaAlLeer = true, LanzaAlGuardar = true };
        var preferencias = new PreferenciasDeDestino(almacen);
        preferencias.RecordarCarpeta("u-ana", CarpetaReal("x"));                    // no lanza
        Assert.Null(preferencias.UltimaCarpeta("u-ana"));                           // tampoco
        Assert.Throws<ArgumentNullException>(() => new PreferenciasDeDestino(null!));
    }

    [Fact]
    public void UnaCarpetaQueNoContestaAlPreguntarSiExiste_SeTomaPorQueNoEsta_SinEsperarlaParaSiempre()
    {
        var almacen = new AlmacenFalso();
        using var colgada = new ManualResetEventSlim(false);
        try
        {
            // «existe» no vuelve nunca (un servidor apagado): con un plazo de 100 ms la respuesta llega igual
            var preferencias = new PreferenciasDeDestino(almacen, TimeSpan.FromMilliseconds(100), ruta => { colgada.Wait(); return true; });
            almacen.Valores[PreferenciasDeDestino.Clave("u-ana")] = @"\\servidor\reportes";
            var reloj = System.Diagnostics.Stopwatch.StartNew();
            Assert.Null(preferencias.UltimaCarpeta("u-ana"));
            Assert.True(reloj.Elapsed < TimeSpan.FromSeconds(10), $"tardó {reloj.Elapsed}");
        }
        finally { colgada.Set(); }

        // y si contesta a tiempo, se ofrece
        var rapida = new PreferenciasDeDestino(almacen, TimeSpan.FromSeconds(10), _ => true);
        Assert.Equal(@"\\servidor\reportes", rapida.UltimaCarpeta("u-ana"));
    }
}

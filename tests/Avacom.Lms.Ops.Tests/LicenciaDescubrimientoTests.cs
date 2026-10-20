using System.Text;
using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Ops.Licencia;
using Avacom.Lms.Ops.Reportes;

namespace Avacom.Lms.Ops.Tests;

/// <summary>
/// Qué tarjetas salen en el paso 3 (P-18) y en qué orden: los <c>.avlic</c> de la raíz de cada unidad y de las carpetas conocidas (sin bajar a subcarpetas), con la marca <c>AVLC</c> o la forma
/// de texto, de 5 bytes a 16 KiB, el mismo archivo una sola vez, los más recientes primero y como mucho 50. Con un sistema de archivos falso: memorias retiradas, carpetas que no existen o que se
/// cuelgan, archivos enormes, basura con la extensión correcta y duplicados. Y una vez con el sistema de archivos de verdad.
/// </summary>
public sealed class LicenciaDescubrimientoTests
{
    private static readonly DateTime Hoy = new(2026, 10, 20, 15, 0, 0, DateTimeKind.Utc);
    private static readonly byte[] Binaria = FixturesDeLicencia.Bytes("ejemplo.avlic");
    private static readonly byte[] Texto = FixturesDeLicencia.Bytes("ejemplo-texto.avlic");

    private const string Documentos = @"C:\Users\ana\Documents";
    private const string Escritorio = @"C:\Users\ana\Desktop";
    private const string Descargas = @"C:\Users\ana\Downloads";

    private static UnidadInfo Memoria(string raiz = @"X:\", string etiqueta = "MEMORIA", bool lista = true) => new(raiz, etiqueta, TipoDeUnidad.Extraible, lista, 1_000_000, 2_000_000, false);
    private static UnidadInfo Disco(string raiz = @"C:\") => new(raiz, "", TipoDeUnidad.Fija, true, 1_000_000, 2_000_000, false);

    /// <summary>Una licencia distinta de las demás (cambia su último byte), con la marca binaria.</summary>
    private static byte[] Licencia(int n)
    {
        var b = Binaria.ToArray();
        b[^1] = (byte)n;
        b[^2] = (byte)(n >> 8);
        return b;
    }

    private static BuscadorDeLicencias Buscador(LectorFalso lector, IProveedorDeUnidades? unidades = null, ICarpetasConocidas? carpetas = null, string? ultima = null, TimeSpan? plazo = null) =>
        new(unidades ?? new UnidadesFalsas(Memoria(), Disco()), carpetas ?? new CarpetasFalsas(Documentos, Escritorio, Descargas), lector, () => ultima, plazo);

    [Fact]
    public void ListaLaRaizDeLasUnidadesYLasCarpetasConocidas_SinBajarASubcarpetas()
    {
        var lector = new LectorFalso()
            .Archivo(@"X:\licencia-serie1.avlic", Licencia(1), Hoy.AddDays(-1))
            .Archivo(@"X:\respaldo\licencia-serie0.avlic", Licencia(2), Hoy)                     // en una subcarpeta: no se mira
            .Archivo(Documentos + @"\licencia-texto.avlic", Texto, Hoy.AddDays(-2))
            .Carpeta(Escritorio).Carpeta(Descargas).Carpeta(@"C:\");
        var r = Buscador(lector).Buscar();
        Assert.Equal(new[] { "licencia-serie1.avlic", "licencia-texto.avlic" }, r.Candidatos.Select(c => c.Nombre).ToArray());
        var memoria = r.Candidatos[0];
        Assert.Equal(("MEMORIA (X:)", OrigenDeCandidato.Unidad, FormaDeLicencia.Binaria, @"X:\"), (memoria.Lugar, memoria.Origen, memoria.Forma, memoria.Carpeta));
        var documentos = r.Candidatos[1];
        Assert.Equal(("Documentos", OrigenDeCandidato.Atajo, FormaDeLicencia.Texto), (documentos.Lugar, documentos.Origen, documentos.Forma));
        Assert.DoesNotContain(lector.Listadas, c => c.Contains("respaldo"));
        Assert.Equal(5, r.LugaresRevisados);                                             // X:, C:, Documentos, Escritorio, Descargas
        Assert.False(r.Recortada);
    }

    [Fact]
    public void LosMasRecientesVanPrimero_YAIgualFecha_ManaElOrdenDeLosLugares()
    {
        var lector = new LectorFalso()
            .Archivo(Documentos + @"\vieja.avlic", Licencia(1), Hoy.AddDays(-30))
            .Archivo(@"X:\nueva.avlic", Licencia(2), Hoy)
            .Archivo(Descargas + @"\media.avlic", Licencia(3), Hoy.AddDays(-3))
            .Archivo(Escritorio + @"\empate.avlic", Licencia(4), Hoy.AddDays(-3))
            .Archivo(@"X:\empate.avlic", Licencia(5), Hoy.AddDays(-3));
        var r = Buscador(lector).Buscar();
        Assert.Equal(new[] { @"X:\nueva.avlic", @"X:\empate.avlic", Escritorio + @"\empate.avlic", Descargas + @"\media.avlic", Documentos + @"\vieja.avlic" },
            r.Candidatos.Select(c => c.Ruta).ToArray());
    }

    [Fact]
    public void LoQueNoEsUnaLicencia_NoSeLista()
    {
        var grande = new byte[MarcaDeLicencia.TamanoMaximo + 1];
        "AVLC"u8.CopyTo(grande);
        var lector = new LectorFalso()
            .Archivo(@"X:\buena.avlic", Licencia(1), Hoy)
            .Archivo(@"X:\enorme.avlic", grande, Hoy)                                           // más de 16 KiB
            .Archivo(@"X:\vacia.avlic", [], Hoy)
            .Archivo(@"X:\corta.avlic", "AVLC"u8.ToArray(), Hoy)                                // 4 bytes: ni una cabecera
            .Archivo(@"X:\foto.avlic", Encoding.ASCII.GetBytes("\x89PNG nada que ver aquí"), Hoy)   // sin la marca
            .Archivo(@"X:\solicitud.avlic", FixturesDeLicencia.Bytes("ejemplo.avreq"), Hoy)    // una solicitud renombrada
            .Archivo(@"X:\liberacion.avlic", FixturesDeLicencia.Bytes("ejemplo.avrel"), Hoy)   // una liberación renombrada
            .Archivo(@"X:\.temporal.avlic", Licencia(2), Hoy)                                  // los temporales empiezan por punto
            .Archivo(@"X:\licencia.avlic.txt", Licencia(3), Hoy)                               // otra extensión
            .Archivo(@"X:\licencia.avreq", Licencia(4), Hoy);
        var r = Buscador(lector).Buscar();
        Assert.Equal("buena.avlic", Assert.Single(r.Candidatos).Nombre);
        Assert.Equal(9, r.Descartados);
    }

    [Fact]
    public void LaLicenciaAlterada_SiSeLista_PorqueQuienVerificaEsElNodo()
    {
        var lector = new LectorFalso().Archivo(@"X:\alterada.avlic", FixturesDeLicencia.Bytes("ejemplo-alterada.avlic"), Hoy);
        Assert.Equal(FormaDeLicencia.Binaria, Assert.Single(Buscador(lector).Buscar().Candidatos).Forma);
    }

    [Fact]
    public void UnaUnidadRetirada_UnaQueNoEstaLista_YUnaCarpetaQueNoExiste_NoTumbanLaBusqueda()
    {
        var lector = new LectorFalso()
            .Archivo(@"X:\en-la-memoria.avlic", Licencia(1), Hoy)
            .Archivo(@"Y:\en-la-otra.avlic", Licencia(2), Hoy)
            .Archivo(Documentos + @"\en-documentos.avlic", Licencia(3), Hoy.AddDays(-1));
        lector.Retiradas.Add(@"X:\");                                                           // se retiró justo al listarla
        var unidades = new UnidadesFalsas(Memoria(), Memoria(@"Y:\", "OTRA"), Memoria(@"E:\", "LECTOR", lista: false));
        var r = Buscador(lector, unidades, new CarpetasFalsas(Documentos, @"C:\no\existe", null)).Buscar();
        Assert.Equal(new[] { "en-la-otra.avlic", "en-documentos.avlic" }, r.Candidatos.Select(c => c.Nombre).ToArray());
        Assert.DoesNotContain(@"E:\", lector.Listadas);                                         // una unidad que no está lista ni se mira
        Assert.DoesNotContain(@"C:\no\existe", lector.Listadas);
    }

    [Fact]
    public void UnArchivoQueNoSeDejaLeer_SeSalta_YLosDemasSalen()
    {
        var lector = new LectorFalso().Archivo(@"X:\bloqueado.avlic", Licencia(1), Hoy).Archivo(@"X:\libre.avlic", Licencia(2), Hoy);
        lector.QueNoSeLeen.Add(@"X:\bloqueado.avlic");
        Assert.Equal("libre.avlic", Assert.Single(Buscador(lector).Buscar().Candidatos).Nombre);
    }

    [Fact]
    public void UnaCarpetaQueSeCuelga_SeAbandonaPorPlazo_YLasDemasSalen()
    {
        var lector = new LectorFalso().Archivo(@"Z:\en-la-red.avlic", Licencia(1), Hoy).Archivo(@"X:\en-la-memoria.avlic", Licencia(2), Hoy);
        lector.Colgadas[@"Z:\"] = TimeSpan.FromSeconds(3);
        var unidades = new UnidadesFalsas(Memoria(), new UnidadInfo(@"Z:\", "RED", TipoDeUnidad.Red, true, 0, 0, false));
        var reloj = System.Diagnostics.Stopwatch.StartNew();
        var r = Buscador(lector, unidades, new CarpetasFalsas(), plazo: TimeSpan.FromMilliseconds(300)).Buscar();
        Assert.True(reloj.Elapsed < TimeSpan.FromSeconds(2.5), $"la búsqueda esperó {reloj.Elapsed}");
        Assert.Equal("en-la-memoria.avlic", Assert.Single(r.Candidatos).Nombre);
        Assert.Equal(1, r.LugaresSinRespuesta);
    }

    [Fact]
    public void ComoMucho50_LosMasRecientes()
    {
        var lector = new LectorFalso();
        for (var i = 0; i < 60; i++) lector.Archivo($@"X:\licencia-{i:00}.avlic", Licencia(i + 1), Hoy.AddMinutes(-i));
        var r = Buscador(lector).Buscar();
        Assert.Equal(BuscadorDeLicencias.Tope, r.Candidatos.Count);
        Assert.True(r.Recortada);
        Assert.Equal("licencia-00.avlic", r.Candidatos[0].Nombre);
        Assert.Equal("licencia-49.avlic", r.Candidatos[^1].Nombre);
    }

    [Fact]
    public void ElMismoArchivoEnDosLugares_SaleUnaVez_ElMasReciente_ConCuantosLugaresMas()
    {
        var misma = Licencia(7);
        var lector = new LectorFalso()
            .Archivo(@"X:\licencia.avlic", misma, Hoy.AddHours(-5))
            .Archivo(Documentos + @"\licencia (copia).avlic", misma, Hoy)
            .Archivo(Descargas + @"\licencia.avlic", misma, Hoy.AddDays(-9))
            .Archivo(@"X:\otra.avlic", Licencia(8), Hoy.AddDays(-1));
        var r = Buscador(lector).Buscar();
        Assert.Equal(2, r.Candidatos.Count);
        var unica = r.Candidatos[0];
        Assert.Equal((Documentos + @"\licencia (copia).avlic", 2), (unica.Ruta, unica.OtrosLugares));
        Assert.Equal(0, r.Candidatos[1].OtrosLugares);
    }

    [Fact]
    public void LaUltimaCarpetaUsada_SeMira_YNoSeRepiteSiYaEsUnaConocida()
    {
        var lector = new LectorFalso().Archivo(@"X:\licencias\entregada.avlic", Licencia(1), Hoy).Carpeta(Documentos);
        var r = Buscador(lector, ultima: @"X:\licencias\").Buscar();
        var c = Assert.Single(r.Candidatos);
        Assert.Equal((OrigenDeCandidato.UltimaCarpeta, @"X:\licencias\"), (c.Origen, c.Lugar));

        var otro = new LectorFalso().Carpeta(Documentos);
        Buscador(otro, ultima: Documentos + @"\").Buscar();
        Assert.Equal(1, otro.Listadas.Count(l => string.Equals(l, Documentos, StringComparison.OrdinalIgnoreCase)));      // Documentos una sola vez
    }

    [Fact]
    public void LosNombresDeLosLugares_DicenQueClaseDeUnidadEs()
    {
        Assert.Equal("MEMORIA (X:)", BuscadorDeLicencias.NombreDeUnidad(Memoria()));
        Assert.Equal("Memoria USB (E:)", BuscadorDeLicencias.NombreDeUnidad(Memoria(@"E:\", "")));
        Assert.Equal("Disco local (C:)", BuscadorDeLicencias.NombreDeUnidad(Disco()));
        Assert.Equal("Unidad de red (Z:)", BuscadorDeLicencias.NombreDeUnidad(new UnidadInfo(@"Z:\", " ", TipoDeUnidad.Red, true, 0, 0, false)));
        Assert.Equal("Memoria USB (F:)", BuscadorDeLicencias.NombreDeUnidad(new UnidadInfo(@"F:\", "", TipoDeUnidad.Fija, true, 0, 0, EsUsb: true)));     // un disco USB «fijo» es extraíble
    }

    [Fact]
    public void LasUnidadesOpticasYSinRaiz_NoSeMiran_YSiLasUnidadesFallan_QuedanLasCarpetas()
    {
        var lector = new LectorFalso().Archivo(@"D:\licencia.avlic", Licencia(1), Hoy).Archivo(Documentos + @"\licencia.avlic", Licencia(2), Hoy);
        var unidades = new UnidadesFalsas(new UnidadInfo(@"D:\", "DVD", TipoDeUnidad.Optica, true, 0, 0, false));
        Assert.Equal("Documentos", Assert.Single(Buscador(lector, unidades).Buscar().Candidatos).Lugar);
        Assert.Equal("Documentos", Assert.Single(Buscador(lector, new UnidadesFalsas { Lanzar = true }).Buscar().Candidatos).Lugar);
    }

    [Fact]
    public void ConElSistemaDeArchivosDeVerdad_SoloLaRaiz_YLeeSinCambiarNada()
    {
        using var tmp = new CarpetaTemporal();
        var sub = tmp.Sub("respaldo");
        File.WriteAllBytes(Path.Combine(tmp.Ruta, "licencia.avlic"), Binaria);
        File.WriteAllBytes(Path.Combine(tmp.Ruta, "LICENCIA-TEXTO.AVLIC"), Texto);
        File.WriteAllBytes(Path.Combine(tmp.Ruta, "notas.txt"), Binaria);
        File.WriteAllBytes(Path.Combine(sub, "abajo.avlic"), Licencia(9));
        var antes = File.GetLastWriteTimeUtc(Path.Combine(tmp.Ruta, "licencia.avlic"));
        var buscador = new BuscadorDeLicencias(new UnidadesFalsas(), new CarpetasFalsas(tmp.Ruta), new LectorDeArchivosDelSistema());
        var r = buscador.Buscar();
        Assert.Equal(new[] { "LICENCIA-TEXTO.AVLIC", "licencia.avlic" }, r.Candidatos.Select(c => c.Nombre).OrderBy(n => n, StringComparer.Ordinal).ToArray());
        Assert.Equal(antes, File.GetLastWriteTimeUtc(Path.Combine(tmp.Ruta, "licencia.avlic")));
        Assert.Equal(Binaria.Length, r.Candidatos.Single(c => c.Forma == FormaDeLicencia.Binaria).Bytes);
        var lector = new LectorDeArchivosDelSistema();
        Assert.Equal("AVLC"u8.ToArray(), lector.LeerInicio(Path.Combine(tmp.Ruta, "licencia.avlic"), 4));
        Assert.Null(lector.LeerCompleto(Path.Combine(tmp.Ruta, "licencia.avlic"), 10));
    }
}

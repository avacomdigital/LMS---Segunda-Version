using System.Text.Json;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Ops.Reportes;

namespace Avacom.Lms.Ops.Tests;

/// <summary>
/// Lo que las pantallas de Reportes (MOD-013) deciden sin interfaz: quién entra, qué ficha de periodo es cuál, qué ruta abre cada reporte reciente, qué grupo queda elegido, qué dice
/// la confirmación antes de guardar. Sin MAUI: se compilan los mismos archivos que corren en el equipo del aula, y los datos son las respuestas REALES del backend que capturó Core.
/// </summary>
public sealed class ReportesLogicaTests
{
    private static readonly JsonSerializerOptions Web = new(JsonSerializerDefaults.Web);

    private static T Cargar<T>(string nombre) =>
        JsonSerializer.Deserialize<T>(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "reportes", nombre + ".json")), Web)
        ?? throw new InvalidOperationException($"{nombre}.json no se pudo leer como {typeof(T).Name}.");

    // ================================================================================================== quién entra

    [Theory]
    [InlineData("TEACHER", true)]
    [InlineData("ADMIN", true)]
    [InlineData("REPORTS", true)]
    [InlineData("TECHNICIAN", false)]
    [InlineData("STUDENT", false)]
    [InlineData(null, false)]
    public void ConSesion_SoloProfesoradoAdministracionYReportesVenLaTesela(string? rol, bool entra) => Assert.Equal(entra, AccesoAReportes.Leer(haySesion: true, rol));

    [Fact]
    public void SinSesion_ElPrototipoDejaVer_YElNodoDecide() => Assert.True(AccesoAReportes.Leer(haySesion: false, rol: null));

    [Fact]
    public void ElTecnicoLeeQueNoAccedeADatosAcademicos_SinCitarDatosDeNadie()
    {
        var texto = AccesoAReportes.SinAcceso("TECHNICIAN");
        Assert.Contains("soporte técnico", texto);
        Assert.Contains("no accede a datos académicos", texto);
        Assert.Contains("administración", texto);
        Assert.NotEqual(texto, AccesoAReportes.SinAcceso("STUDENT"));
    }

    // ================================================================================================== periodos de uso

    private static readonly TimeSpan Bogota = TimeSpan.FromHours(-5);

    private static long Ms(int anio, int mes, int dia, int hora, int minuto, TimeSpan zona) => new DateTimeOffset(anio, mes, dia, hora, minuto, 0, zona).ToUnixTimeMilliseconds();

    [Fact]
    public void LasFichasDeUso_SonCincoYLaPrimeraEsTodo()
    {
        Assert.Equal(new[] { "todo", "anio", "30d", "7d", "hoy" }, PeriodosDeUso.Fichas.Select(f => f.Clave).ToArray());
        Assert.All(PeriodosDeUso.Fichas, f => Assert.False(string.IsNullOrWhiteSpace(f.Rotulo)));
        Assert.Equal("Todo el tiempo", PeriodosDeUso.Rotulo(null));
        Assert.Equal("Todo el tiempo", PeriodosDeUso.Rotulo("algo-raro"));
        Assert.Equal("Últimos 7 días", PeriodosDeUso.Rotulo("7d"));
    }

    [Fact]
    public void CadaFichaCuentaDiasDelCalendarioDelEquipo_NoBloquesDe24Horas()
    {
        var ahora = new DateTimeOffset(2026, 10, 15, 10, 42, 0, Bogota);                        // jueves 15 de octubre, 10:42 en Bogotá
        Assert.Equal(new PeriodoPedido(null, null), PeriodosDeUso.Resolver("todo", ahora));
        Assert.Equal(new PeriodoPedido(Ms(2026, 10, 15, 0, 0, Bogota), null), PeriodosDeUso.Resolver("hoy", ahora));
        Assert.Equal(new PeriodoPedido(Ms(2026, 10, 9, 0, 0, Bogota), null), PeriodosDeUso.Resolver("7d", ahora));         // hoy y los seis anteriores
        Assert.Equal(new PeriodoPedido(Ms(2026, 9, 16, 0, 0, Bogota), null), PeriodosDeUso.Resolver("30d", ahora));         // hoy y los 29 anteriores
        Assert.Equal(new PeriodoPedido(Ms(2026, 1, 1, 0, 0, Bogota), null), PeriodosDeUso.Resolver("anio", ahora));
        Assert.Equal(new PeriodoPedido(null, null), PeriodosDeUso.Resolver("no-existe", ahora));
    }

    [Fact]
    public void LaMedianocheEsLaLocal_NoLaUtc()
    {
        // 02:00 UTC del 15 es todavía el 14 en Bogotá (21:00): «hoy» empieza el 14 a medianoche local.
        var ahora = new DateTimeOffset(2026, 10, 15, 2, 0, 0, TimeSpan.Zero).ToOffset(Bogota);
        Assert.Equal(new PeriodoPedido(Ms(2026, 10, 14, 0, 0, Bogota), null), PeriodosDeUso.Resolver("hoy", ahora));
    }

    [Fact]
    public void UnPeriodoYaResuelto_VuelveASuFicha()
    {
        var ahora = new DateTimeOffset(2026, 10, 15, 10, 42, 0, Bogota);
        foreach (var (clave, _) in PeriodosDeUso.Fichas)
            Assert.Equal(clave, PeriodosDeUso.ClaveDe(PeriodosDeUso.Resolver(clave, ahora), ahora));
        Assert.Null(PeriodosDeUso.ClaveDe(new PeriodoPedido(1000, 2000), ahora));
        Assert.Null(PeriodosDeUso.ClaveDe(new PeriodoPedido(Ms(2026, 10, 15, 0, 0, Bogota), 5), ahora));
    }

    // ================================================================================================== rutas

    [Fact]
    public void LasRutasSoloLlevanIdentificadores_EscapadosYSinVacios()
    {
        Assert.Equal("reporte-clase?sesion=s-1", RutasDeReportes.DeClase("s-1"));
        Assert.Equal("reporte-clase?sesion=a%20b%26c", RutasDeReportes.DeClase("a b&c"));
        Assert.Equal("reporte-grupo?grupo=g-1", RutasDeReportes.DeGrupo("g-1"));
        Assert.Equal("reporte-grupo?grupo=g-1&country=CO&grade=8", RutasDeReportes.DeGrupo("g-1", new NodoAcademico(Country: "CO", Grade: "8")));
        Assert.Equal("reporte-alumno?alumno=al-1", RutasDeReportes.DeAlumno("al-1"));
        Assert.Equal("reporte-alumno?alumno=al-1&grupo=g-1", RutasDeReportes.DeAlumno("al-1", "g-1"));
        Assert.Equal("reporte-alumno?alumno=al-1&grupo=g-1&subject=MAT", RutasDeReportes.DeAlumno("al-1", "g-1", new NodoAcademico(Subject: "MAT")));
        Assert.Equal("reporte-uso", RutasDeReportes.DeUso());
        Assert.Equal("reporte-uso?desde=1000&grupo=g-1", RutasDeReportes.DeUso(new PeriodoPedido(1000, null), "g-1"));
        Assert.Equal("reporte-uso?desde=1000&hasta=2000", RutasDeReportes.DeUso(new PeriodoPedido(1000, 2000)));
        Assert.Equal("reportes-elegir?que=alumno", RutasDeReportes.DeElegir(RutasDeReportes.ElegirAlumno));
        Assert.Equal("reportes-elegir?que=clase&level=SEC", RutasDeReportes.DeElegir(RutasDeReportes.ElegirClase, new NodoAcademico(Level: "SEC")));
        Assert.Equal("reporte-clase?sesion=s-1", RutasDeReportes.DeClase("s-1"));
    }

    [Fact]
    public void ElNodoDeUnaRuta_SeRecuperaTalCualYUnaConsultaVaciaNoEsNodo()
    {
        var nodo = new NodoAcademico("CO", "SEC", "8", "MAT", "ALG");
        var consulta = nodo.Pares().ToDictionary(p => p.Clave, p => p.Valor);
        Assert.Equal(nodo, RutasDeReportes.NodoDe(c => consulta.GetValueOrDefault(c)));
        Assert.Null(RutasDeReportes.NodoDe(_ => null));
        Assert.Null(RutasDeReportes.NodoDe(_ => "  "));
        Assert.Equal(1234L, RutasDeReportes.NumeroDe("1234"));
        Assert.Null(RutasDeReportes.NumeroDe("mil"));
        Assert.Null(RutasDeReportes.NumeroDe(null));
    }

    [Fact]
    public void CadaReporteReciente_ReabreSuPantallaConSusParametros()
    {
        var recientes = Cargar<RecientesDeReportes>("recientes").Recientes;
        var porTipo = recientes.ToDictionary(r => r.Tipo + (r.Tipo == "clase" ? r.Parametro("sesion_id") : ""), r => RutasDeReportes.DeReciente(r));
        var alumno = recientes.First(r => r.Tipo == TiposDeReporte.Alumno);
        Assert.Equal($"reporte-alumno?alumno={alumno.Parametro("alumno_id")}", RutasDeReportes.DeReciente(alumno));
        var grupo = recientes.First(r => r.Tipo == TiposDeReporte.Grupo);
        Assert.Equal($"reporte-grupo?grupo={grupo.Parametro("grupo_id")}", RutasDeReportes.DeReciente(grupo));
        foreach (var clase in recientes.Where(r => r.Tipo == TiposDeReporte.Clase))
            Assert.Equal($"reporte-clase?sesion={clase.Parametro("sesion_id")}", RutasDeReportes.DeReciente(clase));
        Assert.All(porTipo.Values, ruta => Assert.False(string.IsNullOrEmpty(ruta)));
    }

    [Fact]
    public void UnRecienteSinLoEsencial_OReservado_NoSeReabre()
    {
        ReporteReciente De(string tipo, string json) => new(tipo, JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(json, Web)!, "x", 1, 1, null);
        Assert.Null(RutasDeReportes.DeReciente(De("clase", "{}")));
        Assert.Null(RutasDeReportes.DeReciente(De("grupo", """{"grupo_id":""}""")));
        Assert.Null(RutasDeReportes.DeReciente(De("alumno", """{"grupo_id":"g-1"}""")));
        Assert.Null(RutasDeReportes.DeReciente(De("comparacion", """{"grupo_id":"g-1"}""")));
        Assert.Null(RutasDeReportes.DeReciente(De("cobertura", "{}")));
        Assert.Equal("reporte-uso?desde=1000&hasta=2000&grupo=g-1&country=CO", RutasDeReportes.DeReciente(De("uso", """{"desde":1000,"hasta":2000,"grupo_id":"g-1","country":"CO"}""")));
        Assert.Equal("reporte-uso", RutasDeReportes.DeReciente(De("uso", "{}")));
        // el boletín: de un estudiante (con alumno) o de todo el grupo (sin él); sin grupo no hay boletín que reabrir
        Assert.Equal("reporte-boletin?alumno=al-1&grupo=g-1", RutasDeReportes.DeReciente(De("boletin", """{"alumno_id":"al-1","grupo_id":"g-1"}""")));
        Assert.Equal("reporte-boletines?grupo=g-1&subject=math", RutasDeReportes.DeReciente(De("boletin", """{"grupo_id":"g-1","subject":"math"}""")));
        Assert.Null(RutasDeReportes.DeReciente(De("boletin", """{"alumno_id":"al-1"}""")));
        Assert.Equal("reportes-elegir?que=boletin", RutasDeReportes.DeElegir(RutasDeReportes.ElegirBoletin));
        Assert.Equal("reporte-alumno?alumno=a&grupo=g&level=SEC", RutasDeReportes.DeReciente(De("alumno", """{"alumno_id":"a","grupo_id":"g","level":"SEC"}""")));
    }

    // ================================================================================================== grupos, periodos, iniciales

    private static GrupoParaFiltro G(string id, string codigo, string periodo, int? alumnos = 10, int? atencion = 0, bool desactualizado = false, string? nombre = null) =>
        new(id, codigo, nombre ?? $"Grupo {codigo}", periodo, "secundaria", alumnos, atencion, desactualizado);

    private static readonly IReadOnlyList<GrupoParaFiltro> Grupos =
    [
        G("a", "8A", "2026"), G("b", "8B", "2026"), G("c", "7A", "2025"), G("d", "9A", ""),
    ];

    [Fact]
    public void LosPeriodosSonLosDeLosGrupos_ElMasRecientePrimero_SinVacios() =>
        Assert.Equal(new[] { "2026", "2025" }, ListasDeReportes.Periodos(Grupos).ToArray());

    [Fact]
    public void LosGruposDeUnPeriodo_VanPorCodigo_YSinPeriodoSonTodos()
    {
        Assert.Equal(new[] { "8A", "8B" }, ListasDeReportes.Grupos(Grupos, "2026").Select(g => g.Codigo).ToArray());
        Assert.Equal(new[] { "7A", "8A", "8B", "9A" }, ListasDeReportes.Grupos(Grupos, null).Select(g => g.Codigo).ToArray());
        Assert.Empty(ListasDeReportes.Grupos(Grupos, "1999"));
    }

    [Fact]
    public void LoElegidoQueYaNoExiste_SeSuelta()
    {
        var e = ListasDeReportes.Resolver(Grupos, "1999", "a", grupoObligatorio: false);
        Assert.Null(e.Periodo);                                                              // ese periodo no existe: se suelta
        Assert.Equal("a", e.Grupo?.Id);                                                      // pero el grupo sigue valiendo (sin periodo, vale cualquiera)
        var f = ListasDeReportes.Resolver(Grupos, "2025", "a", grupoObligatorio: false);
        Assert.Equal("2025", f.Periodo);
        Assert.Null(f.Grupo);                                                                // «8A» no es de 2025: se suelta
        Assert.Null(ListasDeReportes.Resolver(Grupos, null, "no-existe", false).Grupo);
    }

    [Fact]
    public void ConGrupoObligatorio_UnicoGrupoPosible_QuedaElegidoSolo()
    {
        Assert.Equal("c", ListasDeReportes.Resolver(Grupos, "2025", null, grupoObligatorio: true).Grupo?.Id);
        Assert.Null(ListasDeReportes.Resolver(Grupos, "2026", null, grupoObligatorio: true).Grupo);          // hay dos: elige la persona
        Assert.Null(ListasDeReportes.Resolver(Grupos, "2025", null, grupoObligatorio: false).Grupo);         // no es obligatorio: «todos»
        Assert.Null(ListasDeReportes.Resolver([], null, null, grupoObligatorio: true).Grupo);
    }

    [Fact]
    public void LosAlumnosSeFiltranPorInicial_SinDistinguirMayusculas()
    {
        var alumnos = Cargar<AlumnosParaElegir>("alumnos");
        Assert.Equal(alumnos.Alumnos.Count, ListasDeReportes.PorInicial(alumnos.Alumnos, null).Count);
        Assert.Equal(alumnos.Alumnos.Count, ListasDeReportes.PorInicial(alumnos.Alumnos, "").Count);
        Assert.Equal(6, ListasDeReportes.PorInicial(alumnos.Alumnos, "A").Count);
        Assert.Equal(6, ListasDeReportes.PorInicial(alumnos.Alumnos, "a").Count);
        Assert.Equal("Juan P.", Assert.Single(ListasDeReportes.PorInicial(alumnos.Alumnos, "J")).Rotulo);
        Assert.Empty(ListasDeReportes.PorInicial(alumnos.Alumnos, "Z"));
        Assert.Equal("J", ListasDeReportes.InicialValida(alumnos.Iniciales, "j"));
        Assert.Null(ListasDeReportes.InicialValida(alumnos.Iniciales, "Z"));
        Assert.Null(ListasDeReportes.InicialValida(alumnos.Iniciales, null));
    }

    [Fact]
    public void LaTarjetaDeUnGrupo_DiceCuantosAlumnosYCuantosNecesitanAtencion()
    {
        Assert.Equal("10 alumnos", ListasDeReportes.ResumenDeGrupo(G("a", "8A", "2026")));
        Assert.Equal("1 alumno · 1 necesita atención", ListasDeReportes.ResumenDeGrupo(G("a", "8A", "2026", alumnos: 1, atencion: 1)));
        Assert.Equal("24 alumnos · 3 necesitan atención · se está actualizando", ListasDeReportes.ResumenDeGrupo(G("a", "8A", "2026", alumnos: 24, atencion: 3, desactualizado: true)));
        Assert.Equal("Sin datos todavía", ListasDeReportes.ResumenDeGrupo(G("a", "8A", "2026", alumnos: null, atencion: null)));
        Assert.Equal("8A · Octavo A", ListasDeReportes.RotuloLargo(G("a", "8A", "2026", nombre: "Octavo A")));
        Assert.Equal("8A", ListasDeReportes.RotuloLargo(G("a", "8A", "2026", nombre: "8a")));
    }

    // ================================================================================================== el árbol académico como fichas

    private static NodoDelArbol N(string kind, string code, string name, params NodoDelArbol[] hijos) => new(kind, code, name, hijos.Length, hijos);

    private static readonly IReadOnlyList<NodoDelArbol> Arbol =
    [
        N("country", "CO", "Colombia",
            N("level", "PRI", "Primaria", N("grade", "4", "4.º", N("subject", "MAT", "Matemáticas"))),
            N("level", "SEC", "Secundaria",
                N("grade", "8", "8.º", N("subject", "MAT", "Matemáticas", N("topic", "ALG", "Álgebra")), N("subject", "CIE", "Ciencias")),
                N("grade", "9", "9.º"))),
        N("country", "PE", "Perú"),
    ];

    [Fact]
    public void SinEleccion_SoloHayLaFilaDeLosPaises()
    {
        var filas = ArbolDeNodos.Filas(Arbol, null);
        var fila = Assert.Single(filas);
        Assert.Equal(("country", null), (fila.Nivel, fila.Elegido));
        Assert.Equal(new[] { "CO", "PE" }, fila.Opciones.Select(o => o.Code).ToArray());
    }

    [Fact]
    public void ElegirUnNodo_AbreLaFilaDeSusHijos_YAsiHastaElFinal()
    {
        var filas = ArbolDeNodos.Filas(Arbol, new NodoAcademico("CO", "SEC", "8", "MAT"));
        Assert.Equal(new[] { "country", "level", "grade", "subject", "topic" }, filas.Select(f => f.Nivel).ToArray());
        Assert.Equal(new string?[] { "CO", "SEC", "8", "MAT", null }, filas.Select(f => f.Elegido).ToArray());
        Assert.Equal(new[] { "ALG" }, filas[^1].Opciones.Select(o => o.Code).ToArray());
        Assert.Equal(new[] { "MAT", "CIE" }, filas[3].Opciones.Select(o => o.Code).ToArray());
        Assert.Equal(2, ArbolDeNodos.Filas(Arbol, new NodoAcademico("CO")).Count);
        Assert.Single(ArbolDeNodos.Filas(Arbol, new NodoAcademico("PE")));                          // Perú no trae hijos: no hay fila de abajo
    }

    [Fact]
    public void UnaEleccionQueYaNoExiste_CortaLaCadenaAhi()
    {
        var filas = ArbolDeNodos.Filas(Arbol, new NodoAcademico("XX", "SEC"));
        var fila = Assert.Single(filas);
        Assert.Null(fila.Elegido);
        Assert.Empty(ArbolDeNodos.Filas([], new NodoAcademico("CO")));
    }

    [Fact]
    public void CambiarUnNivel_SueltaLoQueHabiaMasAbajo_YLimpiarLoDejaSinFiltro()
    {
        var actual = new NodoAcademico("CO", "SEC", "8", "MAT");
        Assert.Equal(new NodoAcademico("CO", "PRI"), ArbolDeNodos.Con(actual, "level", "PRI"));
        Assert.Equal(new NodoAcademico("PE"), ArbolDeNodos.Con(actual, "country", "PE"));
        Assert.Equal(new NodoAcademico("CO", "SEC"), ArbolDeNodos.Con(actual, "grade", null));
        Assert.Equal(new NodoAcademico("CO", "SEC", "9"), ArbolDeNodos.Con(actual, "grade", "9"));
        Assert.Null(ArbolDeNodos.Con(actual, "country", null));
        Assert.Null(ArbolDeNodos.Con(actual, "country", " "));
        Assert.Equal(new NodoAcademico("CO"), ArbolDeNodos.Con(null, "country", "CO"));
        Assert.Equal(actual, ArbolDeNodos.Con(actual, "no-es-un-nivel", "X"));
    }

    [Fact]
    public void LoElegido_SeLeeEnPalabras_YUnCodigoQueYaNoEstaSeMuestraTalCual()
    {
        Assert.Equal("Colombia › Secundaria › 8.º › Matemáticas", ArbolDeNodos.Resumen(Arbol, new NodoAcademico("CO", "SEC", "8", "MAT")));
        Assert.Equal("Colombia › Secundaria", ArbolDeNodos.Resumen(Arbol, new NodoAcademico("CO", "SEC")));
        Assert.Equal("ZZ", ArbolDeNodos.Resumen(Arbol, new NodoAcademico("ZZ")));
        Assert.Equal(string.Empty, ArbolDeNodos.Resumen(Arbol, null));
        Assert.Equal(string.Empty, ArbolDeNodos.Resumen(Arbol, new NodoAcademico()));
        Assert.Equal("País", ArbolDeNodos.RotuloDeNivel("country"));
        Assert.Equal("Materia", ArbolDeNodos.RotuloDeNivel("subject"));
        Assert.Equal("Más filtros", ArbolDeNodos.RotuloDeNivel("otro"));
        Assert.Equal("Colombia", ArbolDeNodos.Rotulo(Arbol[0]));
        Assert.Equal("X", ArbolDeNodos.Rotulo(new NodoDelArbol("country", "X", null, null, null)));
    }

    // ================================================================================================== la confirmación antes de guardar

    private static DestinoDeExportacion Unidad(string nombre, string letra, long? libre, TipoDeDestino tipo = TipoDeDestino.Extraible) =>
        new($"unidad:{letra[0]}", nombre, letra + "\\", tipo, letra, libre, libre is null ? null : libre * 2, EsAtajo: false, Listo: true);

    [Fact]
    public void ElDestinoSeNombraConSuLetraEtiquetaYEspacioLibre()
    {
        Assert.Equal("E: · MEMORIA (14 GB libres)", TextoDeExportacion.DescribirDestino(Unidad("MEMORIA", "E:", 15_032_385_536)));
        Assert.Equal("Memoria USB (F:) (1,0 GB libres)", TextoDeExportacion.DescribirDestino(Unidad("Memoria USB (F:)", "F:", 1_073_741_824)));
        Assert.Equal("D: · Datos", TextoDeExportacion.DescribirDestino(Unidad("Datos", "D:", null, TipoDeDestino.CarpetaLocal)));
        Assert.Equal("Documentos", TextoDeExportacion.DescribirDestino(new DestinoDeExportacion("atajo:documentos", "Documentos", @"C:\Users\x\Documents", TipoDeDestino.CarpetaLocal, null, null, null, true, true)));
        Assert.Equal(@"\\colegio\reportes", TextoDeExportacion.DescribirDestino(new DestinoDeExportacion(@"carpeta:\\colegio\reportes", "reportes", @"\\colegio\reportes", TipoDeDestino.Red, null, null, null, false, true)));
    }

    [Fact]
    public void SoloLoExtraibleYLoDeRedLlevanMarca()
    {
        Assert.Equal("Extraíble", TextoDeExportacion.Marca(TipoDeDestino.Extraible));
        Assert.Equal("Red", TextoDeExportacion.Marca(TipoDeDestino.Red));
        Assert.Null(TextoDeExportacion.Marca(TipoDeDestino.CarpetaLocal));
    }

    [Fact]
    public void LaConfirmacionDeUnReporteNominal_DeclaraElAlcanceElLugarYLaAdvertencia()
    {
        var alcance = Cargar<AlcanceDeExportacion>("exportacion_alcance");
        var t = TextoDeExportacion.Confirmacion(alcance, Unidad("MEMORIA", "E:", 15_032_385_536));
        Assert.StartsWith("Vas a guardar el reporte del grupo 8A (7 alumnos", t.Frase);
        Assert.EndsWith("en E: · MEMORIA (14 GB libres).", t.Frase);
        Assert.Contains("incluirá nombres de alumnos", t.Advertencia);
        Assert.Contains("el colegio ya no controla quién lo abre", t.Advertencia);
        Assert.True(t.Nominal);
        Assert.Null(t.Privacidad);
    }

    [Fact]
    public void LaConfirmacionDeUnReporteSinPersonas_Lo_Dice()
    {
        var alcance = Cargar<AlcanceDeExportacion>("exportacion_alcance") with { Nominal = false, Advertencia = "Sin datos de personas." };
        var t = TextoDeExportacion.Confirmacion(alcance, Unidad("MEMORIA", "E:", 1_000_000_000));
        Assert.Equal("Sin datos de personas.", t.Advertencia);
        Assert.False(t.Nominal);
    }

    [Fact]
    public void ConLaPrivacidadAplicada_LaConfirmacionTambienLoDice()
    {
        var baseAlcance = Cargar<AlcanceDeExportacion>("exportacion_alcance");
        var alcance = baseAlcance with { UmbralAplicado = true, Privacidad = baseAlcance.Privacidad with { Aplicada = true, Aviso = "Este reporte abarca 2 alumnos, menos de 5." } };
        Assert.Equal("Este reporte abarca 2 alumnos, menos de 5.", TextoDeExportacion.Confirmacion(alcance, Unidad("M", "E:", 1)).Privacidad);
    }

    [Fact]
    public void LasFichasDeFormato_ExplicanQueTraeCadaUno()
    {
        Assert.Equal("Excel (.xlsx)", TextoDeExportacion.Formato("xlsx").Titulo);
        Assert.Contains("resumen", TextoDeExportacion.Formato("xlsx").Descripcion);
        Assert.Equal("CSV (.csv)", TextoDeExportacion.Formato("csv").Titulo);
        Assert.Contains("Excel en español", TextoDeExportacion.Formato("csv").Descripcion);
    }

    [Fact]
    public void ElExito_DiceDondeQuedoYSoloRecuerdaEsperarEnUnaMemoria()
    {
        var (titulo, detalle, recordatorio) = TextoDeExportacion.Exito(@"E:\Reportes\reporte-grupo-8A-2026-10-15-1042.xlsx", 2025, TipoDeDestino.Extraible);
        Assert.Equal(@"Guardado en E:\Reportes\reporte-grupo-8A-2026-10-15-1042.xlsx", titulo);
        Assert.Contains("2,0 KB", detalle);
        Assert.Equal("Espera un momento antes de retirar la memoria.", recordatorio);
        Assert.Null(TextoDeExportacion.Exito(@"C:\x\a.csv", 10, TipoDeDestino.CarpetaLocal).Recordatorio);
        Assert.Null(TextoDeExportacion.Exito(@"\\s\r\a.csv", 10, TipoDeDestino.Red).Recordatorio);
    }

    // ================================================================================================== los botones de un fallo

    private static ResultadoDelGuardado Fallo(EstadoDelGuardado estado, MotivoDeEscritura? motivo = null, string? codigoDelNodo = null) =>
        new(estado, "No se pudo.", "Haz algo.",
            Fallo: motivo is { } m ? MotivosDeEscritura.De(m) : null,
            ErrorDelNodo: codigoDelNodo is null ? null : new Avacom.Lms.Core.Models.ErrorAula(codigoDelNodo == "sin_conexion" ? 0 : 403, codigoDelNodo, "x", null, null));

    [Theory]
    // lo que se arregla afuera: se puede repetir sobre el mismo destino Y elegir otro
    [InlineData(MotivoDeEscritura.MedioRetirado, true)]
    [InlineData(MotivoDeEscritura.SinEspacio, true)]
    [InlineData(MotivoDeEscritura.ProtegidoContraEscritura, true)]
    [InlineData(MotivoDeEscritura.RutaDeRedInalcanzable, true)]
    [InlineData(MotivoDeEscritura.ArchivoEnUso, true)]
    [InlineData(MotivoDeEscritura.VerificacionFallida, true)]
    [InlineData(MotivoDeEscritura.BloqueadoPorAntivirus, true)]
    // lo que repetir no cambia: sólo elegir otro destino
    [InlineData(MotivoDeEscritura.SinPermiso, false)]
    [InlineData(MotivoDeEscritura.NombreInvalido, false)]
    [InlineData(MotivoDeEscritura.Otro, false)]
    public void UnaEscrituraQueFallo_OfreceLosBotonesQueNombraSuFrase(MotivoDeEscritura motivo, bool sePuedeRepetir)
    {
        var botones = TextoDeExportacion.BotonesPara(Fallo(EstadoDelGuardado.NoSePudoEscribir, motivo));
        Assert.Equal(sePuedeRepetir, botones.GuardarOtraVez);
        Assert.True(botones.ElegirOtroDestino);                       // siempre hay otro destino que elegir, sin generar de nuevo
        Assert.False(botones.ReleerLaPolitica);                       // no cambió nada del aula: sólo falló el destino
        // y la frase que lee la persona nombra «Guardar otra vez» sólo si el botón existe
        var accion = MotivosDeEscritura.De(motivo).Accion;
        if (!sePuedeRepetir) Assert.DoesNotContain("Guardar otra vez", accion);
    }

    [Theory]
    [InlineData(MotivoDeEscritura.MedioRetirado)]
    [InlineData(MotivoDeEscritura.ArchivoEnUso)]
    public void LaFraseQueDiceTocarGuardarOtraVez_TieneEseBoton(MotivoDeEscritura motivo)
    {
        Assert.Contains("Guardar otra vez", MotivosDeEscritura.De(motivo).Accion);
        Assert.True(TextoDeExportacion.BotonesPara(Fallo(EstadoDelGuardado.NoSePudoEscribir, motivo)).GuardarOtraVez);
    }

    [Theory]
    [InlineData(EstadoDelGuardado.SinConexion)]
    [InlineData(EstadoDelGuardado.ArchivoDanado)]
    public void SinConexionOArchivoDanado_SoloSeRepite(EstadoDelGuardado estado)
    {
        var botones = TextoDeExportacion.BotonesPara(Fallo(estado));
        Assert.True(botones.GuardarOtraVez);
        Assert.False(botones.ElegirOtroDestino);                      // todavía no hay archivo bajado que llevar a otro destino
        Assert.False(botones.ReleerLaPolitica);
    }

    [Theory]
    [InlineData("destino_no_permitido")]
    [InlineData("razon_requerida")]
    public void SiElAulaRechazaElDestinoOPideUnaRazon_SeEligeDeNuevoLeyendoLaPoliticaOtraVez(string codigo)
    {
        var botones = TextoDeExportacion.BotonesPara(Fallo(EstadoDelGuardado.NoAutorizado, codigoDelNodo: codigo));
        Assert.True(botones.ElegirOtroDestino);
        Assert.True(botones.ReleerLaPolitica);                        // lo que valía al abrir la hoja cambió: no se repite el mismo rechazo
        Assert.False(botones.GuardarOtraVez);
    }

    [Theory]
    [InlineData("sin_permiso")]
    [InlineData("fuera_de_alcance")]
    public void UnPermisoNegadoDelReporte_NoSeArreglaCambiandoDeCarpeta_SoloSeCierra(string codigo)
    {
        var botones = TextoDeExportacion.BotonesPara(Fallo(EstadoDelGuardado.NoAutorizado, codigoDelNodo: codigo));
        Assert.Equal(new TextoDeExportacion.BotonesDelFallo(false, false, false), botones);
    }

    [Fact]
    public void UnaNegativaDesconocidaDelAula_PermiteVolverAIntentar_SinInventarOtroDestino()
    {
        var botones = TextoDeExportacion.BotonesPara(Fallo(EstadoDelGuardado.NoAutorizado, codigoDelNodo: "algo_nuevo"));
        Assert.True(botones.GuardarOtraVez);
        Assert.False(botones.ElegirOtroDestino);
    }
}

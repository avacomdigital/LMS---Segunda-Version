using System.Text.Json;
using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Calificaciones;

namespace Avacom.Lms.Ops.Tests;

/// <summary>
/// Lo que las pantallas de Calificaciones (MOD-011) deciden sin interfaz: qué enseña cada celda del libro según el modo, cómo se filtra, cómo se eligen nivel, periodo y grupo,
/// cómo se ordena la bandeja, con qué pasos se puntúa sin teclado, qué reintento reutiliza su <c>solicitud_id</c> y cómo se marca el teclado numérico. Se usan las respuestas REALES del
/// backend capturadas en <c>tests/Avacom.Lms.Core.Tests/Fixtures/gradebook</c> (vinculadas, no copiadas). OPS es una app MAUI y no se puede referenciar desde aquí: se COMPILAN sus archivos
/// puros, los mismos que corren en el equipo del aula.
/// </summary>
public sealed class CalificacionesTests
{
    private static readonly JsonSerializerOptions Web = new(JsonSerializerDefaults.Web);

    private static T Cargar<T>(string nombre) =>
        JsonSerializer.Deserialize<T>(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "gradebook", nombre + ".json")), Web)
        ?? throw new InvalidOperationException($"{nombre}.json no se pudo leer como {typeof(T).Name}.");

    private static CeldaDelLibro PrimeraCelda(LibroDelGrupo l) => l.Alumnos[0].Celdas.Values.First();

    // ============================================================================================== el libro

    [Fact]
    public void Una_calificacion_revisada_muestra_la_nota_presentada_y_el_interno_en_pequeno()
    {
        var libro = Cargar<LibroDelGrupo>("libro");
        var c = VistaDelLibro.Describir(PrimeraCelda(libro), modoCalificaciones: true);
        Assert.Equal("Revisado", c.Estado);
        Assert.Equal(Matiz.Info, c.Matiz);
        Assert.Equal("4,8", c.Principal);
        Assert.Equal("interno 95,24 de 100", c.Secundario);
        Assert.Contains("provisional", c.Marcas);          // la presentación aún no se publicó
        Assert.Contains("sin publicar", c.Marcas);
        Assert.DoesNotContain("publicada", c.Marcas);
        Assert.NotNull(c.CalificacionId);
        Assert.Null(c.Simbolo);
    }

    [Fact]
    public void Lo_provisional_o_pendiente_jamas_se_pinta_como_cero()
    {
        var libro = Cargar<LibroDelGrupo>("libro_con_revision");
        var c = VistaDelLibro.Describir(PrimeraCelda(libro), true);
        Assert.Equal("Provisional", c.Estado);
        Assert.Equal(Matiz.Violeta, c.Matiz);
        Assert.Equal("—", c.Principal);
        Assert.Null(c.Secundario);
        Assert.Null(c.CalificacionId);

        var sinCelda = VistaDelLibro.Describir(null, true);
        Assert.Equal("Pendiente", sinCelda.Estado);
        Assert.Equal("—", sinCelda.Principal);
        Assert.NotEqual("0", sinCelda.Principal);
    }

    [Fact]
    public void En_modo_simple_la_celda_no_lleva_ni_una_cifra_ni_una_letra()
    {
        var libro = Cargar<LibroDelGrupo>("libro_simple");
        Assert.False(libro.EnModoCalificaciones);
        var c = VistaDelLibro.Describir(PrimeraCelda(libro), modoCalificaciones: false);
        Assert.Equal("Completado", c.Estado);
        Assert.Equal("●", c.Simbolo);
        Assert.Null(c.Principal);
        Assert.Null(c.Secundario);
        Assert.Empty(c.Marcas);
        Assert.Null(c.CalificacionId);                       // en modo simple no se abre ningún detalle de calificación

        // Aunque el nodo mande una cifra técnica o una presentación, el modo simple no la enseña.
        var conCifra = PrimeraCelda(libro) with { PuntajeEfectivo = 90m, EstadoSimple = EstadosSimples.EnProgreso, CalificacionId = "x" };
        var d = VistaDelLibro.Describir(conCifra, false);
        Assert.Null(d.Principal);
        Assert.Null(d.Secundario);
        Assert.Equal("◐", d.Simbolo);
        Assert.Equal("○", VistaDelLibro.Describir(null, false).Simbolo);
    }

    [Theory]
    [InlineData("pendiente", "Neutro")]
    [InlineData("provisional", "Violeta")]
    [InlineData("revisado", "Info")]
    [InlineData("definitivo", "Exito")]
    [InlineData("reabierto", "Ambar")]
    [InlineData("anulado", "Gris")]
    [InlineData("sin_registro", "Neutro")]
    public void Cada_estado_tiene_su_tono_y_su_texto(string estado, string esperado)
    {
        Assert.Equal(Enum.Parse<Matiz>(esperado), VistaDelLibro.MatizDeEstado(estado));
        Assert.False(string.IsNullOrWhiteSpace(GradebookTexto.Estado(estado)));
    }

    [Fact]
    public void Una_calificacion_publicada_y_ajustada_lo_dice_y_no_es_provisional()
    {
        var libro = Cargar<LibroDelGrupo>("libro");
        var celda = PrimeraCelda(libro);
        var publicada = celda with { Estado = "definitivo", Publicada = true, Ajustada = true, Presentacion = celda.Presentacion! with { Provisional = false } };
        var c = VistaDelLibro.Describir(publicada, true);
        Assert.Equal(Matiz.Exito, c.Matiz);
        Assert.Equal(new[] { "ajustada", "publicada" }, c.Marcas);
    }

    [Fact]
    public void Lo_que_solo_tiene_cifra_tecnica_o_esta_reabierto_no_muestra_resultado_interno()
    {
        var celda = PrimeraCelda(Cargar<LibroDelGrupo>("libro"));
        foreach (var estado in new[] { "sin_registro", "reabierto", "anulado", "pendiente" })
            Assert.Null(VistaDelLibro.Describir(celda with { Estado = estado, Presentacion = null }, true).Secundario);
    }

    [Fact]
    public void El_buscador_es_opcional_y_no_distingue_tildes_ni_mayusculas()
    {
        var libro = Cargar<LibroDelGrupo>("libro");
        Assert.Single(VistaDelLibro.Filas(libro, null));
        Assert.Single(VistaDelLibro.Filas(libro, "   "));
        Assert.Single(VistaDelLibro.Filas(libro, "JUAN"));
        Assert.Single(VistaDelLibro.Filas(libro, "juan p"));
        Assert.Empty(VistaDelLibro.Filas(libro, "maría"));

        var varios = libro with
        {
            Alumnos = [libro.Alumnos[0] with { Rotulo = "María José" }, libro.Alumnos[0] with { Rotulo = "Mario" }],
        };
        Assert.Single(VistaDelLibro.Filas(varios, "maria jose"));
        Assert.Equal(2, VistaDelLibro.Filas(varios, "mari").Count);
    }

    [Fact]
    public void El_filtro_de_evaluacion_deja_una_columna_o_todas()
    {
        var libro = Cargar<LibroDelGrupo>("libro");
        var id = libro.Asignaciones[0].Id;
        Assert.Single(VistaDelLibro.Columnas(libro, null));
        Assert.Single(VistaDelLibro.Columnas(libro, ""));
        Assert.Single(VistaDelLibro.Columnas(libro, id));
        Assert.Empty(VistaDelLibro.Columnas(libro, "otra"));
    }

    [Fact]
    public void Las_revisiones_pendientes_suman_lo_por_revisar_y_lo_reabierto()
    {
        var conRevision = Cargar<LibroDelGrupo>("libro_con_revision");
        Assert.Equal(1, VistaDelLibro.RevisionesPendientes(conRevision));
        var celda = PrimeraCelda(conRevision);
        var reabierta = conRevision with
        {
            Alumnos = [conRevision.Alumnos[0] with { Celdas = new() { ["a"] = celda with { Estado = "reabierto" } } }],
        };
        Assert.Equal(1, VistaDelLibro.Reabiertas(reabierta));
        Assert.Equal(2, VistaDelLibro.RevisionesPendientes(reabierta));
    }

    [Fact]
    public void Publicar_lo_revisado_cuenta_las_revisadas_sin_publicar_de_cada_columna()
    {
        var libro = Cargar<LibroDelGrupo>("libro");
        var columna = libro.Asignaciones[0].Id;
        Assert.Equal(1, VistaDelLibro.PorPublicar(libro, columna));
        Assert.Equal(0, VistaDelLibro.PorPublicar(libro, "otra"));
        var publicado = libro with { Alumnos = [libro.Alumnos[0] with { Celdas = new() { [columna] = PrimeraCelda(libro) with { Estado = "definitivo", Publicada = true } } }] };
        Assert.Equal(0, VistaDelLibro.PorPublicar(publicado, columna));
    }

    [Fact]
    public void La_firma_no_cuenta_el_reloj_del_nodo()
    {
        var libro = Cargar<LibroDelGrupo>("libro");
        Assert.Equal(VistaDelLibro.Firma(libro), VistaDelLibro.Firma(libro with { ServidorEn = libro.ServidorEn + 5000 }));
        Assert.NotEqual(VistaDelLibro.Firma(libro), VistaDelLibro.Firma(libro with { Modo = "simple" }));
    }

    [Fact]
    public void El_promedio_es_el_del_nodo_y_sin_calificaciones_es_un_guion()
    {
        var libro = Cargar<LibroDelGrupo>("libro");
        var curso = Assert.Single(VistaDelLibro.Cursos(libro.Asignaciones));
        Assert.Equal("Estados de la materia y sus cambios", curso.Rotulo);
        var agregado = VistaDelLibro.Agregado(libro.Alumnos[0], curso.CursoRef);
        Assert.Equal("95,24", VistaDelLibro.PromedioSimple(agregado));
        Assert.Equal("1 calificación", VistaDelLibro.DetalleDeAgregado(agregado));
        Assert.Equal("—", VistaDelLibro.PromedioSimple(null));
        var sin = Cargar<LibroDelGrupo>("libro_con_revision");
        var vacio = VistaDelLibro.Agregado(sin.Alumnos[0], curso.CursoRef);
        Assert.Equal("—", VistaDelLibro.PromedioSimple(vacio));
        Assert.Equal("0 calificaciones · 1 por completar", VistaDelLibro.DetalleDeAgregado(vacio));
    }

    // ----------------------------------------------------------------------------------- publicar lo revisado

    [Fact]
    public void Publicar_una_asignacion_dice_cuantas_se_publicaron()
    {
        var r = Cargar<PublicacionDeAsignacion>("publicar_asignacion");
        var (titulo, detalle, problemas) = VistaDelLibro.DescribirPublicacion(r, id => "Juan P.");
        Assert.Equal("Se publicó 1 calificación", titulo);
        Assert.False(problemas);
        Assert.Contains("ya pueden ver", detalle);
    }

    [Fact]
    public void Lo_omitido_se_dice_con_quien_y_por_que()
    {
        using var doc = JsonDocument.Parse("""
            [{"calificacion_id":"c1","alumno_id":"a1","estado":"revisada","codigo":"no_publicable","motivos":["Tiene respuestas por revisar."]},
             {"calificacion_id":"c2","alumno_id":"a2","estado":"revisada","codigo":"modo_simple","motivos":[]}]
            """);
        var r = new PublicacionDeAsignacion("asg", 2, 1, doc.RootElement.EnumerateArray().Select(e => e.Clone()).ToList());
        var omisiones = VistaDelLibro.Omisiones(r);
        Assert.Equal(2, omisiones.Count);
        Assert.Equal(["Tiene respuestas por revisar."], omisiones[0].Motivos);
        var (titulo, detalle, problemas) = VistaDelLibro.DescribirPublicacion(r, id => id == "a1" ? "Juan P." : "Ana");
        Assert.True(problemas);
        Assert.Equal("Se publicaron 2; 2 se omitieron", titulo);
        Assert.Contains("1 ya estaba publicada.", detalle);
        Assert.Contains("Omitida: Juan P. · Tiene respuestas por revisar.", detalle);
        Assert.Contains("Omitida: Ana · el nivel está en modo simple", detalle);
    }

    [Fact]
    public void Si_no_habia_nada_por_publicar_se_dice_asi()
    {
        var r = new PublicacionDeAsignacion("asg", 0, 0, []);
        var (titulo, detalle, problemas) = VistaDelLibro.DescribirPublicacion(r, id => id);
        Assert.Equal("No había nada por publicar", titulo);
        Assert.Null(detalle);
        Assert.False(problemas);
    }

    // =================================================================================== nivel, periodo y grupo

    private static GrupoPadron G(string id, string nombre, string? nivel, string? periodo, bool activo = true) =>
        new(id, id.ToUpperInvariant(), nombre, periodo, nivel, activo, []);

    private static readonly IReadOnlyList<GrupoPadron> Grupos =
    [
        G("g1", "Octavo A", "secundaria", "2026"),
        G("g2", "Octavo B", "secundaria", "2025"),
        G("g3", "Párvulos", "preescolar", "2026"),
        G("g4", "Décimo", "bachillerato", "2026"),
        G("g5", "Octavo C", "secundaria", "2026", activo: false),
    ];

    [Fact]
    public void Los_niveles_salen_en_el_orden_de_la_escuela()
    {
        Assert.Equal(["preescolar", "secundaria", "bachillerato"], SelectorDeGrupo.Niveles(Grupos));
        Assert.Equal("Secundaria", SelectorDeGrupo.RotuloDeNivel("secundaria"));
        Assert.Equal("Sin nivel", SelectorDeGrupo.RotuloDeNivel(null));
        Assert.Equal("Taller", SelectorDeGrupo.RotuloDeNivel("taller"));
    }

    [Fact]
    public void Los_periodos_de_un_nivel_van_del_mas_reciente_al_mas_antiguo()
    {
        Assert.Equal(["2026", "2025"], SelectorDeGrupo.Periodos(Grupos, "secundaria"));
        Assert.Equal(["2026"], SelectorDeGrupo.Periodos(Grupos, "preescolar"));
        Assert.Empty(SelectorDeGrupo.Periodos(Grupos, "primaria"));
    }

    [Fact]
    public void Los_grupos_se_acotan_por_nivel_y_periodo_con_los_activos_primero()
    {
        Assert.Equal(["g1", "g2", "g5"], SelectorDeGrupo.Grupos(Grupos, "secundaria", null).Select(g => g.Id));
        Assert.Equal(["g1", "g5"], SelectorDeGrupo.Grupos(Grupos, "secundaria", "2026").Select(g => g.Id));
    }

    [Fact]
    public void La_eleccion_se_corrige_sola_si_lo_pedido_ya_no_existe()
    {
        var e = SelectorDeGrupo.Resolver(Grupos, "secundaria", "2025", "g2");
        Assert.Equal(("secundaria", "2025", "g2"), (e.Nivel, e.Periodo, e.Grupo!.Id));

        // El grupo pedido no es del periodo elegido: se queda el primero del periodo.
        e = SelectorDeGrupo.Resolver(Grupos, "secundaria", "2025", "g1");
        Assert.Equal("g2", e.Grupo!.Id);

        // El periodo no es del nivel: vuelve a «todos».
        e = SelectorDeGrupo.Resolver(Grupos, "preescolar", "2025", null);
        Assert.Null(e.Periodo);
        Assert.Equal("g3", e.Grupo!.Id);

        // Sin nivel pedido, se usa el del grupo pedido.
        e = SelectorDeGrupo.Resolver(Grupos, null, null, "g4");
        Assert.Equal(("bachillerato", "g4"), (e.Nivel, e.Grupo!.Id));

        // Sin nada pedido, el primer nivel y su primer grupo.
        e = SelectorDeGrupo.Resolver(Grupos, null, null, null);
        Assert.Equal(("preescolar", "g3"), (e.Nivel, e.Grupo!.Id));

        Assert.Null(SelectorDeGrupo.Resolver([], "secundaria", null, null).Grupo);
    }

    [Fact]
    public void Si_el_padron_no_trae_el_nivel_se_agrupa_solo_por_grupo()
    {
        var sinNivel = new[] { G("a", "Uno", null, "2026"), G("b", "Dos", "", "2026") };
        Assert.Equal([SelectorDeGrupo.SinNivel], SelectorDeGrupo.Niveles(sinNivel));
        var e = SelectorDeGrupo.Resolver(sinNivel, null, null, null);
        Assert.Equal("b", e.Grupo!.Id);                       // por nombre: «Dos» antes que «Uno»
        Assert.Equal(2, SelectorDeGrupo.Grupos(sinNivel, e.Nivel, null).Count);
    }

    // ================================================================================================ la bandeja

    [Fact]
    public void La_bandeja_pone_primero_lo_pendiente_y_lo_mas_antiguo()
    {
        var pendiente = Cargar<BandejaDeRevision>("bandeja").Items[0];
        var reabierta = Cargar<BandejaDeRevision>("bandeja_reabierta").Items[0];
        var masNueva = pendiente with { IntentoId = "n", EntregadoEn = pendiente.EntregadoEn + 10_000, AlumnoRotulo = "Ana" };
        var orden = OrdenDeBandeja.Ordenar([reabierta, masNueva, pendiente]);
        Assert.Equal([pendiente.IntentoId, "n", reabierta.IntentoId], orden.Select(i => i.IntentoId));
    }

    [Fact]
    public void La_bandeja_se_filtra_por_grupo_y_ofrece_solo_los_grupos_que_tiene()
    {
        var pendiente = Cargar<BandejaDeRevision>("bandeja").Items[0];
        var otro = pendiente with { IntentoId = "z", GrupoId = "g-otro", GrupoRotulo = "Noveno" };
        Assert.Single(OrdenDeBandeja.Filtrar([pendiente, otro], pendiente.GrupoId));
        Assert.Equal(2, OrdenDeBandeja.Filtrar([pendiente, otro], null).Count);
        Assert.Equal(2, OrdenDeBandeja.Filtrar([pendiente, otro], "").Count);
        Assert.Empty(OrdenDeBandeja.Filtrar([pendiente, otro], "nadie"));
        Assert.Equal(["Noveno", "Octavo A"], OrdenDeBandeja.Grupos([pendiente, otro]).Select(g => g.Rotulo));
    }

    [Fact]
    public void Cada_renglon_de_la_bandeja_dice_que_falta_y_la_cifra_nunca_se_presenta_como_nota()
    {
        var pendiente = Cargar<BandejaDeRevision>("bandeja").Items[0];
        Assert.Equal("Pendiente de revisión", OrdenDeBandeja.Motivo(pendiente));
        Assert.Equal("Faltan 2 respuestas", OrdenDeBandeja.Falta(pendiente));
        Assert.Equal("Faltan 1 respuesta", OrdenDeBandeja.Falta(pendiente with { NPendientes = 1 }));
        var cifra = OrdenDeBandeja.CifraProvisional(pendiente);
        Assert.Contains("provisional", cifra);
        Assert.Contains("aún no es la calificación", cifra);
        Assert.Null(OrdenDeBandeja.CifraProvisional(pendiente with { PorcentajeProvisional = null }));

        var reabierta = Cargar<BandejaDeRevision>("bandeja_reabierta").Items[0];
        Assert.True(reabierta.EsReapertura);
        Assert.Equal("Reabierta para recalificar", OrdenDeBandeja.Motivo(reabierta));
        Assert.StartsWith("Reabierta", OrdenDeBandeja.Falta(reabierta));
    }

    // ============================================================================== puntuar sin teclado

    [Fact]
    public void Sin_rubrica_se_puntua_en_pasos_de_cero_a_cien_por_ciento_del_maximo()
    {
        var pasos = PuntuacionDeRevision.Porcentuales(3m);
        Assert.Equal([0m, 0.75m, 1.5m, 2.25m, 3m], pasos.Select(p => p.Valor));
        Assert.Equal(["0", "25 %", "50 %", "75 %", "100 %"], pasos.Select(p => p.Rotulo));
        Assert.Equal([0m, 0.25m, 0.5m, 0.75m, 1m], PuntuacionDeRevision.Porcentuales(1m).Select(p => p.Valor));
        Assert.Equal(1.75m, PuntuacionDeRevision.Porcentuales(7m)[1].Valor);
        Assert.Empty(PuntuacionDeRevision.Porcentuales(0m));
        Assert.All(PuntuacionDeRevision.Porcentuales(2.33m), p => Assert.Equal(p.Valor, decimal.Round(p.Valor, 2)));
    }

    [Theory]
    [InlineData(1, "0;0,25;0,5;0,75;1")]
    [InlineData(2, "0;0,5;1;1,5;2")]
    [InlineData(3, "0;0,5;1;1,5;2;2,5;3")]
    [InlineData(5, "0;1;2;3;4;5")]
    [InlineData(10, "0;2;4;6;8;10")]
    public void Los_pasos_de_un_criterio_son_pocos_y_siempre_terminan_en_el_maximo(int maximo, string esperados)
    {
        var pasos = PuntuacionDeRevision.Pasos(maximo);
        Assert.Equal(esperados, string.Join(";", pasos.Select(p => GradebookTexto.Puntaje(p))));
        Assert.Equal(maximo, pasos[^1]);
        Assert.InRange(pasos.Count, 2, 8);
    }

    [Fact]
    public void Un_maximo_enorme_o_raro_tambien_da_pocos_pasos_validos()
    {
        var raro = PuntuacionDeRevision.Pasos(2.5m);
        Assert.Equal(2.5m, raro[^1]);
        Assert.All(raro, p => Assert.Equal(p, decimal.Round(p, 2)));
        var grande = PuntuacionDeRevision.Pasos(1000m);
        Assert.InRange(grande.Count, 2, 9);
        Assert.Equal(1000m, grande[^1]);
        Assert.Equal([0m], PuntuacionDeRevision.Pasos(0m));
    }

    private static readonly IReadOnlyList<CriterioDeRubrica> Rubrica = [new("r1", "Diferencia de altura", 1m), new("r2", "Relaciona presión y ebullición", 2m)];

    [Fact]
    public void La_rubrica_exige_todos_los_criterios_y_suma_en_vivo()
    {
        Assert.Equal(3m, PuntuacionDeRevision.MaximoDeRubrica(Rubrica));
        var parcial = new Dictionary<string, decimal> { ["r1"] = 1m };
        Assert.False(PuntuacionDeRevision.Completa(Rubrica, parcial));
        Assert.Null(PuntuacionDeRevision.Armar(Rubrica, parcial));
        Assert.Equal(1m, PuntuacionDeRevision.Total(parcial.Values));

        var completa = new Dictionary<string, decimal> { ["r2"] = 1.5m, ["r1"] = 0.5m };
        Assert.True(PuntuacionDeRevision.Completa(Rubrica, completa));
        var armada = PuntuacionDeRevision.Armar(Rubrica, completa)!;
        Assert.Equal(["r1", "r2"], armada.Select(c => c.CriterioId));         // en el orden de la rúbrica
        Assert.Equal(2m, PuntuacionDeRevision.Total(completa.Values));
        Assert.False(PuntuacionDeRevision.Completa([], new Dictionary<string, decimal>()));
    }

    [Fact]
    public void Un_valor_que_se_sale_de_lo_que_vale_el_criterio_no_se_arma()
    {
        Assert.Null(PuntuacionDeRevision.Armar(Rubrica, new Dictionary<string, decimal> { ["r1"] = 1.5m, ["r2"] = 1m }));
        Assert.Null(PuntuacionDeRevision.Armar(Rubrica, new Dictionary<string, decimal> { ["r1"] = -1m, ["r2"] = 1m }));
    }

    [Fact]
    public void Un_cambio_de_valor_o_de_motivo_es_otra_peticion_y_lo_mismo_es_un_reintento()
    {
        var a = PuntuacionDeRevision.FirmaManual("i", "q1", 2m, "bien", null);
        Assert.Equal(a, PuntuacionDeRevision.FirmaManual("i", "q1", 2m, "bien", null));
        Assert.NotEqual(a, PuntuacionDeRevision.FirmaManual("i", "q1", 3m, "bien", null));
        Assert.NotEqual(a, PuntuacionDeRevision.FirmaManual("i", "q1", 2m, "bien", "Me equivoqué al puntuar"));
        var criterios = new[] { new CriterioPuntuado("r1", 1m), new CriterioPuntuado("r2", 2m) };
        Assert.Equal(PuntuacionDeRevision.FirmaRubrica("i", "q1", criterios, null, null), PuntuacionDeRevision.FirmaRubrica("i", "q1", criterios, null, null));
        Assert.NotEqual(PuntuacionDeRevision.FirmaRubrica("i", "q1", criterios, null, null), PuntuacionDeRevision.FirmaRubrica("i", "q1", [new CriterioPuntuado("r1", 0m), criterios[1]], null, null));
    }

    // ============================================================================== idempotencia (solicitud_id)

    [Fact]
    public void Reintentar_lo_mismo_reutiliza_la_solicitud_y_cambiarlo_estrena_otra()
    {
        var s = new SolicitudReintentable();
        var primera = s.Para("ajuste|c1|3|90|motivo");
        Assert.False(string.IsNullOrWhiteSpace(primera));
        Assert.True(primera.Length <= 64);                                  // el nodo corta a 64
        Assert.True(s.EsReintento("ajuste|c1|3|90|motivo"));
        Assert.Equal(primera, s.Para("ajuste|c1|3|90|motivo"));             // reintento tras perder la señal: la misma
        var otra = s.Para("ajuste|c1|3|95|motivo");
        Assert.NotEqual(primera, otra);                                     // el profesor cambió el valor: otra operación
        Assert.False(s.EsReintento("ajuste|c1|3|90|motivo"));
    }

    [Fact]
    public void Al_confirmarse_la_siguiente_operacion_igual_es_otra()
    {
        var s = new SolicitudReintentable();
        var primera = s.Para("x");
        s.Soltar();
        Assert.False(s.EsReintento("x"));
        Assert.NotEqual(primera, s.Para("x"));
    }

    // ================================================================================== el teclado numérico

    private static string Marcar(string pulsaciones)
    {
        var e = new EntradaDecimal();
        foreach (var c in pulsaciones)
        {
            if (c == ',') e.Separador();
            else if (c == '<') e.Borrar();
            else e.Digito(c);
        }
        return e.Texto;
    }

    [Theory]
    [InlineData("85", "85")]
    [InlineData("85,5", "85.5")]
    [InlineData("85,25", "85.25")]
    [InlineData("85,255", "85.25")]            // a lo sumo dos decimales
    [InlineData("1000", "100")]                // a lo sumo tres cifras enteras
    [InlineData("007", "7")]                   // sin ceros a la izquierda
    [InlineData("000", "0")]
    [InlineData(",5", "0.5")]                  // el separador solo empieza en «0.»
    [InlineData("8,5,5", "8.55")]              // un solo separador
    [InlineData("85<", "8")]
    [InlineData("85<<<", "")]
    [InlineData("8,<<", "")]
    public void El_teclado_marca_solo_lo_que_puede_ser_una_puntuacion(string pulsaciones, string esperado) => Assert.Equal(esperado, Marcar(pulsaciones));

    [Fact]
    public void El_teclado_muestra_con_coma_y_lo_marcado_lo_lee_la_validacion_de_core()
    {
        var e = new EntradaDecimal();
        foreach (var c in "92") e.Digito(c);
        e.Separador();
        e.Digito('5');
        Assert.Equal("92,5", e.Mostrado);
        Assert.Equal(92.5m, GradebookTexto.LeerPuntaje(e.Texto).Valor);
        e.Limpiar();
        Assert.True(e.EstaVacia);
        Assert.NotNull(GradebookTexto.LeerPuntaje(e.Texto).Error);               // vacío: lo dice con palabras
        e.Poner("100,0");
        Assert.Equal("100.0", e.Texto);
        Assert.Equal(100m, GradebookTexto.LeerPuntaje(e.Texto).Valor);
        e.Poner("abc");
        Assert.True(e.EstaVacia);
    }

    [Fact]
    public void Los_errores_de_forma_se_dicen_como_se_hace_en_una_pantalla_sin_teclado()
    {
        // Si Core cambia estas frases, esta prueba avisa: el mapa a lenguaje táctil tendría que seguirlas.
        var errores = GradebookTexto.ErroresDeAjuste("", "");
        Assert.Equal(2, errores.Count);
        Assert.Equal("Marca la nueva puntuación en el teclado.", TextoDeCalificaciones.ErrorTactil(errores[0]));
        Assert.Equal("Elige el motivo del cambio: queda en el historial.", TextoDeCalificaciones.ErrorTactil(errores[1]));
        Assert.Equal("La puntuación va de 0 a 100.", TextoDeCalificaciones.ErrorTactil("La puntuación va de 0 a 100."));
        Assert.All(GradebookTexto.ErroresDeAjuste("", ""), e => Assert.DoesNotContain("Escribe", TextoDeCalificaciones.ErrorTactil(e)));
    }

    [Fact]
    public void Lo_que_se_pasa_de_cien_lo_dice_la_validacion_con_palabras()
    {
        var e = new EntradaDecimal();
        foreach (var c in "101") e.Digito(c);
        var errores = GradebookTexto.ErroresDeAjuste(e.Texto, "Error de transcripción o de captura");
        Assert.Contains("La puntuación va de 0 a 100.", errores);
    }

    // =============================================================================================== frases

    [Fact]
    public void El_motivo_es_la_frase_elegida_y_otro_motivo_funciona_con_o_sin_texto()
    {
        Assert.Null(FrasesDeCalificaciones.MotivoFinal(null, "algo"));
        Assert.Null(FrasesDeCalificaciones.MotivoFinal("  ", null));
        Assert.Equal("Error de transcripción o de captura", FrasesDeCalificaciones.MotivoFinal("Error de transcripción o de captura", "ignorado"));
        Assert.Equal("Otro motivo", FrasesDeCalificaciones.MotivoFinal(FrasesDeCalificaciones.OtroMotivo, null));
        Assert.Equal("Otro motivo", FrasesDeCalificaciones.MotivoFinal(FrasesDeCalificaciones.OtroMotivo, "  "));
        Assert.Equal("Otro motivo: lo pidió la madre", FrasesDeCalificaciones.MotivoFinal(FrasesDeCalificaciones.OtroMotivo, " lo pidió la madre "));
        // Ningún motivo que se pueda tocar deja pasar uno que el nodo rechazaría por corto.
        foreach (var frase in FrasesDeCalificaciones.MotivosDeAjuste.Concat(FrasesDeCalificaciones.MotivosDeReapertura).Concat(FrasesDeCalificaciones.MotivosDeRetiro)
                     .Concat(FrasesDeCalificaciones.MotivosDeValoracion).Concat(FrasesDeCalificaciones.MotivosDeCambioDePuntaje))
            Assert.Null(GradebookTexto.ValidarMotivo(FrasesDeCalificaciones.MotivoFinal(frase, null)));
    }

    [Fact]
    public void Los_motivos_de_ajuste_incluyen_las_frases_del_producto()
    {
        Assert.Contains("Se reconoció una respuesta correcta que la rúbrica inicial no contemplaba", FrasesDeCalificaciones.MotivosDeAjuste);
        Assert.Contains("Error de transcripción o de captura", FrasesDeCalificaciones.MotivosDeAjuste);
        Assert.Contains("Corrección tras revisar con el estudiante", FrasesDeCalificaciones.MotivosDeAjuste);
        Assert.Contains("Ajuste razonable por una necesidad de apoyo", FrasesDeCalificaciones.MotivosDeAjuste);
        Assert.Contains("Corrección solicitada por la coordinación", FrasesDeCalificaciones.MotivosDeAjuste);
    }

    [Fact]
    public void Las_frases_de_un_apartado_se_juntan_con_lo_escrito()
    {
        Assert.Null(FrasesDeCalificaciones.Juntar([]));
        Assert.Equal("Explica con claridad. Usa bien el vocabulario.", FrasesDeCalificaciones.Juntar(["Explica con claridad", "Usa bien el vocabulario."]));
        Assert.Equal("Explica con claridad. Muy buen trabajo", FrasesDeCalificaciones.Juntar(["Explica con claridad"], " Muy buen trabajo "));
        Assert.Equal("Solo texto", FrasesDeCalificaciones.Juntar([], "Solo texto"));
    }

    // =========================================================================== la respuesta del alumno

    [Fact]
    public void De_una_respuesta_abierta_se_muestra_lo_escrito()
    {
        var revision = Cargar<RevisionParaDocente>("revision");
        var abierta = revision.Filas.Single(f => f.PreguntaRef == "l3-q5");
        Assert.True(abierta.RequiereRevision);
        Assert.StartsWith("Porque al enfriarse", RespuestaDeRevision.Para(abierta));
        Assert.Empty(RespuestaDeRevision.Evidencias(abierta));
        Assert.Equal(2, revision.Filas.Count(f => f.RequiereRevision));
        Assert.Equal(10, revision.Filas.Count(f => !f.RequiereRevision));
    }

    [Fact]
    public void Un_dibujo_o_un_audio_se_rotulan_con_su_referencia_y_no_se_pintan()
    {
        var abierta = Cargar<RevisionParaDocente>("revision").Filas.Single(f => f.PreguntaRef == "l3-q5");
        var dibujo = abierta with { Respuesta = null, Evidencias = [new EvidenciaDeRespuesta("drawing", "ev-1"), new EvidenciaDeRespuesta("audio", "ev-2"), new EvidenciaDeRespuesta("otra", "ev-3")] };
        Assert.Equal(["Dibujo: referencia ev-1", "Audio: referencia ev-2", "Evidencia: referencia ev-3"], RespuestaDeRevision.Evidencias(dibujo));
        Assert.Contains("referencia", RespuestaDeRevision.Para(dibujo));
        Assert.Equal("No respondió", RespuestaDeRevision.Para(abierta with { Respuesta = null, Respondida = false }));
    }

    [Fact]
    public void Lo_que_el_sistema_ya_califico_se_resume_en_una_linea()
    {
        var filas = Cargar<RevisionParaDocente>("revision").Filas;
        Assert.Equal("Marcó 1 opción", RespuestaDeRevision.Resumen(filas.Single(f => f.PreguntaRef == "l3-q1")));
        Assert.Equal("Verdadero", RespuestaDeRevision.Resumen(filas.Single(f => f.PreguntaRef == "l3-q2")));
        Assert.Equal("líquido", RespuestaDeRevision.Resumen(filas.Single(f => f.PreguntaRef == "l3-q3")));
        Assert.Equal("Ordenó 3 elementos", RespuestaDeRevision.Resumen(filas.Single(f => f.PreguntaRef == "l3-q4")));
        Assert.Equal("Relacionó 3 pares", RespuestaDeRevision.Resumen(filas.Single(f => f.PreguntaRef == "l3-q9")));
    }

    // ============================================================================================= escalas

    [Fact]
    public void Los_tramos_de_una_escala_se_leen_de_su_definicion_en_orden()
    {
        var escala = Cargar<EscalaAdoptada>("escala");
        var version = Assert.Single(escala.Versiones!);
        var tramos = TramosDeEscala.Leer(version.Definicion);
        Assert.Equal(["bajo", "basico", "alto", "superior"], tramos.Select(t => t.Clave));
        Assert.Equal(["Bajo", "Básico", "Alto", "Superior"], tramos.Select(t => t.Etiqueta));
        Assert.Equal("de 1 a 5 · el criterio de aprobación empieza en 3", TramosDeEscala.Rango(version.Definicion));
        Assert.Equal("Numérica", TramosDeEscala.TipoLegible(escala.Tipo));
        Assert.Empty(TramosDeEscala.Leer(null));
        Assert.Empty(TramosDeEscala.Leer(JsonDocument.Parse("{}").RootElement));
        Assert.Null(TramosDeEscala.Rango(null));
    }

    [Fact]
    public void La_configuracion_no_trae_las_versiones_de_las_escalas_y_por_eso_hay_un_lector_propio()
    {
        // Lo que Core no modela: en /configuracion/ una escala trae «ultima_version», no «versiones». Si esto cambiara, el lector propio de OPS dejaría de hacer falta.
        var configuracion = Cargar<ConfiguracionAcademica>("configuracion");
        Assert.All(configuracion.Escalas, e => Assert.Null(e.Versiones));
    }

    [Fact]
    public void Las_plantillas_se_filtran_por_pais_y_las_genericas_van_aparte()
    {
        var catalogo = Cargar<PlantillasDeEscalas>("plantillas");
        var todas = catalogo.Plantillas;
        Assert.NotEmpty(todas);
        Assert.All(todas, p => Assert.False(string.IsNullOrWhiteSpace(p.Advertencia)));          // toda plantilla trae su advertencia: orientativa, la institución debe revisarla
        Assert.Contains("orientativa", catalogo.Advertencia, StringComparison.OrdinalIgnoreCase);

        Assert.Equal(todas.Count, FiltroDePlantillas.Filtrar(todas, null).Count);
        Assert.Equal(todas.Count, FiltroDePlantillas.Filtrar(todas, "").Count);
        var paises = FiltroDePlantillas.Paises(todas);
        Assert.Contains("CO", paises);
        Assert.DoesNotContain("", paises);
        Assert.True(FiltroDePlantillas.HayGenericas(todas));
        var genericas = FiltroDePlantillas.Filtrar(todas, FiltroDePlantillas.Genericas);
        Assert.All(genericas, p => Assert.True(string.IsNullOrWhiteSpace(p.Pais)));
        var colombia = FiltroDePlantillas.Filtrar(todas, "co");
        Assert.NotEmpty(colombia);
        Assert.All(colombia, p => Assert.Equal("CO", p.Pais!.ToUpperInvariant()));
        Assert.Equal(todas.Count, genericas.Count + paises.Sum(c => FiltroDePlantillas.Filtrar(todas, c).Count));
        Assert.Equal("Colombia", FiltroDePlantillas.NombreDePais("CO"));
        Assert.Equal("Genérica", FiltroDePlantillas.Origen(genericas[0]));
        Assert.StartsWith("Colombia", FiltroDePlantillas.Origen(colombia[0]));
    }

    [Fact]
    public void La_vista_previa_dice_cuatro_cosas_por_muestra_y_la_nota_en_el_formato_del_aula()
    {
        var vista = Cargar<VistaPreviaDeEscala>("vista_previa");
        Assert.Equal(6, vista.Conversiones.Count);
        var cuarenta = vista.Conversiones.First(c => c.Interno == 49.99m);
        Assert.Equal("2,9", TextoDeCalificaciones.Presentada(cuarenta.Presentada));
        Assert.Equal("Bajo", cuarenta.Desempeno.Nivel);
        Assert.Equal("No cumple el criterio", GradebookTexto.Aprobacion(cuarenta.Aprobacion));
        Assert.Equal("—", TextoDeCalificaciones.Presentada(null));
        Assert.Equal("B", TextoDeCalificaciones.Presentada(new ValorPresentado(null, "B", "b")));
        Assert.Equal([0m, 40m, 60m, 80m, 100m], TextoDeCalificaciones.MuestrasDeVistaPrevia);
    }

    // ======================================================================================= la calificación

    [Fact]
    public void El_estado_guardado_de_una_calificacion_se_dice_con_palabras_y_su_tono()
    {
        var c = Cargar<DetalleDeCalificacion>("calificacion").Calificacion;
        Assert.Equal("Revisada · sin publicar", TextoDeCalificaciones.Estado(c));
        Assert.Equal(Matiz.Info, TextoDeCalificaciones.MatizDeEstado(c));
        Assert.Equal("Publicada · el alumno la ve", TextoDeCalificaciones.Estado(c with { Estado = "definitiva" }));
        Assert.Equal(Matiz.Exito, TextoDeCalificaciones.MatizDeEstado(c with { Estado = "definitiva" }));
        Assert.Equal(Matiz.Ambar, TextoDeCalificaciones.MatizDeEstado(c with { Estado = "reabierta" }));
        Assert.Equal(Matiz.Gris, TextoDeCalificaciones.MatizDeEstado(c with { Estado = "anulada" }));
        Assert.Equal("Revisión del profesor sobre la evaluación", TextoDeCalificaciones.Regla(c.ReglaPuntuacion));
        Assert.Equal("Superior", TextoDeCalificaciones.Desempeno(c.Presentacion));
        Assert.Equal("Superior · valorado por el profesor",
            TextoDeCalificaciones.Desempeno(c.Presentacion! with { Desempeno = c.Presentacion.Desempeno with { Origen = "docente" } }));
        Assert.Equal("—", TextoDeCalificaciones.Desempeno(null));
    }

    [Fact]
    public void El_historial_dice_que_cambio_sin_inventar_cifras()
    {
        var historial = Cargar<DetalleDeCalificacion>("calificacion").Historial;
        Assert.Equal("Se registró 95,24", TextoDeCalificaciones.Cambio(historial[0]));
        var ajuste = new VersionDeCalificacion(2, "ajuste", 95.24m, 90m, "revisada", "revisada", "Error de captura", "u", 1, null);
        Assert.Equal("95,24 → 90", TextoDeCalificaciones.Cambio(ajuste));
        var reapertura = new VersionDeCalificacion(3, "reapertura", 90m, 90m, "revisada", "reabierta", "x", "u", 1, null);
        Assert.Equal("Revisada → Reabierta", TextoDeCalificaciones.Cambio(reapertura));
        var valoracion = new VersionDeCalificacion(4, "valoracion", 90m, 90m, "revisada", "revisada", "x", "u", 1, null);
        Assert.Null(TextoDeCalificaciones.Cambio(valoracion));
    }

    [Fact]
    public void La_retroalimentacion_ya_escrita_se_lee_por_apartado()
    {
        var c = Cargar<DetalleDeCalificacion>("calificacion").Calificacion with { Retroalimentacion = new() { ["fortalezas"] = "Explica con claridad.", ["comentario"] = " " } };
        Assert.Equal("Explica con claridad.", TextoDeCalificaciones.Retroalimentacion(c, "fortalezas"));
        Assert.Null(TextoDeCalificaciones.Retroalimentacion(c, "comentario"));
        Assert.Null(TextoDeCalificaciones.Retroalimentacion(c, "dificultades"));
    }

    // ======================================================================================= los permisos

    [Theory]
    [InlineData(false, null, true, true, true)]                    // sin sesión (prototipo): se deja ver y el nodo decide
    [InlineData(true, "TEACHER", true, true, false)]
    [InlineData(true, "ADMIN", true, false, true)]                 // la administración no califica directamente
    [InlineData(true, "REPORTS", true, false, false)]              // reportes sólo lee
    [InlineData(true, "TECHNICIAN", false, false, false)]          // el técnico no ve datos académicos (TST-069)
    public void Cada_rol_ve_lo_que_le_toca(bool haySesion, string? rol, bool leer, bool calificar, bool configurar)
    {
        Assert.Equal(leer, PermisosDeCalificaciones.Leer(haySesion, rol));
        Assert.Equal(calificar, PermisosDeCalificaciones.Calificar(haySesion, rol));
        Assert.Equal(configurar, PermisosDeCalificaciones.Configurar(haySesion, rol));
    }

    [Fact]
    public void El_rol_tecnico_lee_que_no_accede_a_datos_academicos()
    {
        Assert.Contains("no accede a datos académicos", PermisosDeCalificaciones.SinAccesoAcademico("TECHNICIAN"));
        Assert.False(string.IsNullOrWhiteSpace(PermisosDeCalificaciones.SinAccesoAcademico("OTRO")));
    }

    [Fact]
    public void Tras_un_conflicto_de_version_se_lee_el_valor_vigente_que_el_nodo_mando()
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "gradebook", "ajuste_conflicto.json")));
        var error = new Avacom.Lms.Core.Models.ErrorAula(409, "conflicto_de_version", "x", null, doc.RootElement.Clone());
        var (version, puntaje) = TextoDeCalificaciones.ValorActualDelConflicto(error);
        Assert.NotNull(version);
        Assert.NotNull(puntaje);
        Assert.Equal(version, GradebookTexto.VersionActual(error));
        Assert.True(GradebookTexto.EsConflictoDeVersion(error));
        Assert.Equal(((int?)null, (decimal?)null), TextoDeCalificaciones.ValorActualDelConflicto(null));
        Assert.Equal(((int?)null, (decimal?)null), TextoDeCalificaciones.ValorActualDelConflicto(new Avacom.Lms.Core.Models.ErrorAula(0, "sin_conexion", "x", null, null)));
    }

    [Fact]
    public void Las_evaluaciones_en_curso_se_dicen_con_su_cuenta()
    {
        using var doc = JsonDocument.Parse("""{"codigo":"evaluaciones_en_curso","detail":"x","en_curso":3,"nivel_clave":"secundaria"}""");
        var error = new Avacom.Lms.Core.Models.ErrorAula(409, "evaluaciones_en_curso", "x", null, doc.RootElement.Clone());
        Assert.Equal(3, TextoDeCalificaciones.EnCurso(error));
        Assert.Contains("3 evaluaciones en curso", TextoDeCalificaciones.ErrorDeNivel(error, null));
        var sinCuenta = new Avacom.Lms.Core.Models.ErrorAula(409, "evaluaciones_en_curso", "x", null, null);
        Assert.Null(TextoDeCalificaciones.EnCurso(sinCuenta));
        Assert.Contains("evaluaciones en curso", TextoDeCalificaciones.ErrorDeNivel(sinCuenta, null));
    }
}

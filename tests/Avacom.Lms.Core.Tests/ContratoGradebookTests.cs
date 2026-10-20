using System.Text.Json;
using Avacom.Lms.Core.Gradebook;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// Los DTOs de <c>/api/gradebook/</c> contra respuestas REALES del backend, capturadas por <c>backend/gradebook/tests/test_capturar_contrato.py</c> en
/// <c>Fixtures/gradebook/</c>. Un campo mal escrito en un DTO se descubre aquí y no en una pantalla. Se comprueba la FORMA y los valores que no cambian entre
/// corridas (los identificadores y las horas sí cambian).
/// </summary>
public sealed class ContratoGradebookTests
{
    private static string Leer(string nombre) =>
        File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "gradebook", nombre + ".json"));

    private static T Cargar<T>(string nombre) =>
        JsonSerializer.Deserialize<T>(Leer(nombre), Ayudas.Web) ?? throw new InvalidOperationException($"{nombre}.json no se pudo leer como {typeof(T).Name}.");

    // ------------------------------------------------------------------------------------------------ el libro

    [Fact]
    public void Libro_TraeColumnasFilasCeldasYLaEscalaDelNivel()
    {
        var l = Cargar<LibroDelGrupo>("libro");
        Assert.True(l.EnModoCalificaciones);
        Assert.Equal(("Octavo A", "secundaria", "2026"), (l.Grupo.Nombre, l.Grupo.NivelClave, l.Grupo.Periodo));
        Assert.Equal("co-1-5", l.Escala!.Codigo);
        Assert.Equal("ultimo", l.PoliticaIntentos);
        var fila = l.Alumnos.Single(a => a.Rotulo == "Juan P.");
        var columna = l.Asignaciones.First();
        var celda = fila.Celdas[columna.Id];
        Assert.Equal((EstadosDeResultado.Revisado, EstadosSimples.Completado, false), (celda.Estado, celda.EstadoSimple, celda.Publicada));
        Assert.NotNull(celda.CalificacionId);
        Assert.Equal(celda.PuntajeOriginal, celda.PuntajeEfectivo);
        Assert.True(celda.Presentacion!.Provisional);                                  // sin publicar: la presentación es provisional
        Assert.Equal("co-1-5", celda.Presentacion.Escala!.Codigo);
        // El sistema del nivel a la vista del profesor: país, rango, desde dónde se aprueba y sus niveles.
        Assert.Equal(("CO", 1m, 5m, 3m, "Básico"), (l.Escala.Pais, l.Escala.ValorMin, l.Escala.ValorMax, l.Escala.AprobacionMinima, l.Escala.ApruebaDesde));
        Assert.Equal(new[] { "Bajo", "Básico", "Alto", "Superior" }, l.Escala.Tramos!.Select(t => t.Etiqueta).ToArray());
        Assert.Equal(new bool?[] { false, true, true, true }, l.Escala.Tramos!.Select(t => t.Aprueba).ToArray());
        Assert.Equal("De 1 a 5 · Se aprueba con 3 o más", GradebookTexto.ResumenDelSistema(l.Escala));
        var agregado = Assert.Single(fila.Agregados);
        Assert.False(agregado.Oficial);
        Assert.False(agregado.Ponderado);                                              // el promedio es simple e informativo
    }

    [Fact]
    public void LibroConRevision_LoPendienteNoEsUnCero()
    {
        var l = Cargar<LibroDelGrupo>("libro_con_revision");
        var celda = l.Alumnos.Single().Celdas.Values.Single();
        Assert.Equal(EstadosDeResultado.Provisional, celda.Estado);
        Assert.Null(celda.PuntajeEfectivo);                                            // nunca un cero para lo que no tiene calificación
        Assert.Null(celda.CalificacionId);
        Assert.Equal(1, l.Totales.PorRevisar);
    }

    [Fact]
    public void LibroSimple_NoTienePresentacionNiEscala()
    {
        var l = Cargar<LibroDelGrupo>("libro_simple");
        Assert.False(l.EnModoCalificaciones);
        Assert.Null(l.Escala);
        var celda = l.Alumnos.Single().Celdas.Values.Single();
        Assert.Equal((EstadosDeResultado.SinRegistro, EstadosSimples.Completado), (celda.Estado, celda.EstadoSimple));
        Assert.Null(celda.Presentacion);
    }

    // -------------------------------------------------------------------------------------- la revisión docente

    [Fact]
    public void Bandeja_ListaLoQueEsperaAlProfesor()
    {
        var b = Cargar<BandejaDeRevision>("bandeja");
        var item = Assert.Single(b.Items);
        Assert.Equal(("pendiente", "en_revision_docente", 2), (item.Motivo, item.EstadoIntento, item.NPendientes));
        Assert.Equal(2, item.Pendientes.Count);
        Assert.False(item.EsReapertura);
        Assert.Equal((1, 0), (b.Pendientes, b.Reabiertas));
        var reabierta = Cargar<BandejaDeRevision>("bandeja_reabierta").Items.Single(i => i.EsReapertura);
        Assert.NotNull(reabierta.CalificacionId);
        Assert.Equal(0, reabierta.NPendientes);
    }

    [Fact]
    public void Revision_TraeLasPreguntasLaRubricaYLoQueFaltaParaConfirmar()
    {
        var r = Cargar<RevisionParaDocente>("revision");
        Assert.False(r.PuedeConfirmar);
        Assert.Equal(2, r.Intento.Pendientes.Count);
        var abiertas = r.Filas.Where(f => f.RequiereRevision).ToList();
        Assert.Equal(2, abiertas.Count);
        Assert.All(abiertas, f =>
        {
            Assert.True(f.Pendiente);
            Assert.Equal("abierta", f.Forma);
            Assert.NotEmpty(f.Rubrica!.Criterios);
            Assert.Equal(f.PuntajeMaximo, f.Rubrica.Criterios.Sum(c => c.PuntosMax));
        });
        Assert.All(r.Filas.Where(f => !f.RequiereRevision), f => Assert.Null(f.Rubrica));
    }

    [Fact]
    public void RevisionAplicada_ManualYPorRubrica()
    {
        var manual = Cargar<RevisionAplicada>("revision_manual");
        Assert.Equal(("manual", 1, false), (manual.Tipo, manual.Numero, manual.ListoParaConfirmar));
        Assert.Single(manual.Pendientes);
        var rubrica = Cargar<RevisionAplicada>("revision_rubrica");
        Assert.Equal(("rubrica", true, 3m), (rubrica.Tipo, rubrica.ListoParaConfirmar, rubrica.Puntaje));
        Assert.Empty(rubrica.Pendientes);
        var confirmada = Cargar<RevisionConfirmada>("revision_confirmada");
        Assert.Equal(("calificado", "creada", true), (confirmada.Estado, confirmada.Resultado, confirmada.Registrada));
        Assert.Equal(("docente", EstadosDeCalificacion.Revisada), (confirmada.Calificacion!.Origen, confirmada.Calificacion.Estado));
    }

    // ------------------------------------------------------------------------------------ la calificación

    [Fact]
    public void Calificacion_ConservaElOriginalYTraeSuTrazabilidad()
    {
        var d = Cargar<DetalleDeCalificacion>("calificacion");
        var c = d.Calificacion;
        Assert.Equal((EstadosDeCalificacion.Revisada, 1, false), (c.Estado, c.Version, c.Publicada));
        Assert.Equal(c.PuntajeOriginal, c.PuntajeEfectivo);
        Assert.Equal(("docente", "mod10.revision_docente.v1"), (c.Origen, c.ReglaPuntuacion));
        Assert.NotEmpty(c.EvaluadorId);
        Assert.Equal("registro", Assert.Single(d.Historial).Tipo);
        Assert.Equal(2, d.Revisiones.Count);                                           // las dos revisiones del profesor, con su traza
        Assert.Equal("calificado", d.Intento!.Estado);
        Assert.False(c.DesfaseConEvaluacion);
        Assert.Equal(("co-1-5", "CO", "Se aprueba con 3 o más"), (d.Sistema!.Codigo, d.Sistema.Pais, GradebookTexto.MinimoParaAprobar(d.Sistema)));
    }

    [Fact]
    public void Ajuste_ConservaElOriginalYElMotivo()
    {
        var r = Cargar<CambioDeCalificacion>("ajuste");
        var c = r.Calificacion;
        Assert.Equal(85m, c.PuntajeEfectivo);
        Assert.NotEqual(c.PuntajeEfectivo, c.PuntajeOriginal);
        Assert.True(c.Ajustada);
        Assert.Equal(2, c.Version);
        var ultimo = r.Historial.Last();
        Assert.Equal(("ajuste", 85m), (ultimo.Tipo, ultimo.PuntajeNuevo));
        Assert.Equal(c.PuntajeOriginal, ultimo.PuntajeAnterior);
        Assert.False(string.IsNullOrWhiteSpace(ultimo.Motivo));
        Assert.Equal("cap-aj-1", ultimo.SolicitudId);
        Assert.False(r.Reintento);
    }

    [Fact]
    public void ValoracionYRetroalimentacion()
    {
        var v = Cargar<CambioDeCalificacion>("valoracion").Calificacion;
        Assert.Equal("alto", v.DesempenoDocente);
        Assert.True(v.Presentacion!.Desempeno.ValoradoPorElDocente);
        var r = Cargar<CambioDeCalificacion>("retroalimentacion").Calificacion;
        Assert.Equal("Razona bien los cambios de estado.", r.Retroalimentacion!["fortalezas"]);
        Assert.Equal("Tiempo adicional del 25 %", r.Adaptacion);
    }

    // ------------------------------------------------------------------------------------- el boletín

    [Fact]
    public void Boletin_TraeLoQueLlevaPorCursoSusInsightsYUnaPaginaDeEvaluaciones()
    {
        var b = Cargar<BoletinDelEstudiante>("boletin");
        Assert.Equal(("Juan P.", "secundaria", true), (b.Alumno.Rotulo, b.Grupo.NivelClave, b.EnModoCalificaciones));
        Assert.Equal("co-1-5", b.Sistema!.Codigo);
        Assert.Equal((2, 1, 1, 1, 0), (b.Resumen.Evaluaciones, b.Resumen.Conteo.ConNota, b.Resumen.Conteo.PorRevisar, b.Resumen.Conteo.Aprobadas, b.Resumen.Conteo.SinRegistro));
        Assert.False(b.Resumen.Oficial);
        Assert.False(b.Resumen.Ponderado);                                                      // el promedio es simple e informativo
        Assert.Equal(71.43m, b.Resumen.PromedioSimple);
        Assert.Equal(("3.8", "Básico", true), (b.Resumen.Presentado!.Etiqueta, b.Resumen.Presentado.Desempeno, b.Resumen.Presentado.CumpleCriterio));
        var curso = Assert.Single(b.Cursos);
        Assert.Equal(("Estados de la materia y sus cambios", 2), (curso.CursoRotulo, curso.Evaluaciones));
        Assert.Equal("insuficiente", b.Insights.Tendencia.Direccion);                           // con una sola nota no se dice hacia dónde va
        Assert.Equal((2, 2), (b.Insights.Constancia.Completadas, b.Insights.Constancia.Evaluaciones));
        Assert.True(b.Insights.Informativo);
        Assert.Equal("Razona bien los cambios de estado.", Assert.Single(b.Insights.Comentarios.Fortalezas).Texto);
        Assert.Equal((2, 2, 0, false), (b.Evaluaciones.Total, b.Evaluaciones.Items.Count, b.Evaluaciones.Desde, b.Evaluaciones.HayMas));
        var calificada = b.Evaluaciones.Items.Single(e => e.Estado == EstadosDeResultado.Definitivo);
        Assert.Equal(("Publicada", "3,8", true), (BoletinTexto.Estado(calificada), BoletinTexto.Nota(calificada), BoletinTexto.Cumple(calificada)));
        var reabierta = b.Evaluaciones.Items.Single(e => e.Estado == EstadosDeResultado.Reabierto);
        Assert.Equal(("En recalificación", "—", null), (BoletinTexto.Estado(reabierta), BoletinTexto.Nota(reabierta), BoletinTexto.Cumple(reabierta)));     // lo que se recalifica no tiene nota ni cero
    }

    [Fact]
    public void Boletin_LaNotaSeLeeConLosPuntosElPorcentajeYElSistema_YTraeMateriasYRecomendaciones()
    {
        var b = Cargar<BoletinDelEstudiante>("boletin");
        // los puntos brutos que contó la evaluación, sumados en el resumen y en el curso
        Assert.Equal((15m, 21m, 71.43m, 1), (b.Resumen.Bruto!.Puntos, b.Resumen.Bruto.PuntosMaximos, b.Resumen.Bruto.Porcentaje, b.Resumen.Bruto.Evaluaciones));
        var curso = Assert.Single(b.Cursos);
        Assert.Equal(("science", 15m), (curso.Materia, curso.Bruto!.Puntos));
        var conNota = b.Evaluaciones.Items.Single(i => i.Bruto is not null);
        Assert.Equal((15m, 21m, 10, 12, 71.43m), (conNota.Bruto!.Puntos, conNota.Bruto.PuntosMaximos, conNota.Bruto.Aciertos, conNota.Bruto.Preguntas, conNota.Bruto.Porcentaje));
        Assert.Equal("15 de 21 puntos · 71,43 %", GradebookTexto.Bruto(conNota.Bruto));
        Assert.Null(b.Evaluaciones.Items.Single(i => i.Estado == EstadosDeResultado.Reabierto).Bruto);        // lo que no cuenta (reabierto, pendiente) no tiene cifras
        // las materias del grupo (por el identificador del curso) para segmentar, y el filtro aplicado (ninguno)
        var materia = Assert.Single(b.Materias!);
        Assert.Equal(("science", "Science", 2), (materia.Codigo, materia.Rotulo, materia.Evaluaciones));
        Assert.Equal("Estados de la materia y sus cambios", Assert.Single(materia.Cursos).Rotulo);
        Assert.Null(b.Filtro!.Subject);
        // las recomendaciones del profesor (la cuarta pregunta) y el catálogo con que se eligen sin teclado
        var general = Assert.Single(b.Observaciones!);
        Assert.True(general.EsGeneral);
        Assert.Equal(new[] { "practicar_ejercicios", "pedir_ayuda" }, general.Recomendaciones.Select(r => r.Codigo).ToArray());
        Assert.Equal("Va mejorando.", general.Texto);
        Assert.Equal(1, general.Version);
        Assert.Equal(14, b.RecomendacionesDisponibles!.Count);
        Assert.All(b.RecomendacionesDisponibles, r => Assert.False(string.IsNullOrWhiteSpace(r.Texto)));
        Assert.Contains("Practicar", BoletinTexto.Recomendaciones(general));
    }

    [Fact]
    public void Boletin_PorMateria_RecortaYDiceElFiltro()
    {
        var b = Cargar<BoletinDelEstudiante>("boletin_por_materia");
        Assert.Equal("science", b.Filtro!.Subject);
        Assert.Equal(2, b.Resumen.Evaluaciones);
        var libro = Cargar<LibroDelGrupo>("libro_sin_materia");
        Assert.Equal("math", libro.Filtro!.Subject);
        Assert.Empty(libro.Asignaciones);                                                       // ninguna evaluación de esa materia…
        Assert.Single(libro.Materias!);                                                         // …pero las fichas siguen ofreciendo las del grupo
        Assert.Equal("science", Cargar<LibroDelGrupo>("libro_por_materia").Filtro!.Subject);
    }

    [Fact]
    public void Observacion_CrearRepetirYLoQueNoVale()
    {
        var r = Cargar<RespuestaDeObservacion>("observacion");
        Assert.True(r.Cambiado);
        Assert.Equal((1, "", "2026"), (r.Observacion.Version, r.Observacion.CursoRef, r.Observacion.Periodo));
        Assert.Equal("Practicar más ejercicios del tema con el modo estudio", r.Observacion.Recomendaciones[0].Texto);
        Assert.False(Cargar<RespuestaDeObservacion>("observacion_repetida").Cambiado);          // repetir lo mismo no deja rastro
        Assert.Equal("datos_invalidos", Ayudas.Json(Leer("observacion_invalida")).GetProperty("codigo").GetString());
    }

    [Fact]
    public void Libro_CadaCeldaConNotaTraeSuBrutoYElLibroSusMaterias()
    {
        var l = Cargar<LibroDelGrupo>("libro");
        var celda = l.Alumnos.SelectMany(a => a.Celdas.Values).Single(c => c.CalificacionId is not null);
        Assert.Equal((20m, 21m, 11, 12, 95.24m), (celda.Bruto!.Puntos, celda.Bruto.PuntosMaximos, celda.Bruto.Aciertos, celda.Bruto.Preguntas, celda.Bruto.Porcentaje));
        Assert.Equal("science", l.Asignaciones[0].Materia);
        Assert.Equal("science", Assert.Single(l.Materias!).Codigo);
        var cal = Cargar<DetalleDeCalificacion>("calificacion").Calificacion;
        Assert.Equal((20m, 21m, "science"), (cal.Puntos, cal.PuntosMaximos, cal.Materia));
        Assert.Equal(cal.PuntajeEfectivo, cal.Bruto!.Porcentaje);
    }

    [Fact]
    public void Boletin_UnaPaginaDiceDesdeDondeVieneYCuantasHay()
    {
        var p = Cargar<BoletinDelEstudiante>("boletin_pagina").Evaluaciones;
        Assert.Equal((2, 1, 1, 1), (p.Total, p.Desde, p.Limite, p.Items.Count));
        Assert.False(p.HayMas);
    }

    [Fact]
    public void Boletin_EnModoSimpleNoTieneSistemaNiCifras()
    {
        var b = Cargar<BoletinDelEstudiante>("boletin_simple");
        Assert.False(b.EnModoCalificaciones);
        Assert.Null(b.Sistema);
        Assert.Null(b.Resumen.PromedioSimple);
        Assert.Null(b.Resumen.Presentado);
        Assert.All(b.Evaluaciones.Items, e => Assert.Null(e.Presentacion));
        Assert.All(b.Evaluaciones.Items, e => Assert.Null(e.PuntajeEfectivo));
        Assert.False(b.Insights.Comentarios.HayAlgo);
    }

    [Fact]
    public void LibroEnResumen_NoMandaLasCeldasPeroSiLoQueLlevaCadaEstudianteYCadaEvaluacion()
    {
        var l = Cargar<LibroDelGrupo>("libro_resumen");
        Assert.All(l.Alumnos, a => Assert.Empty(a.Celdas));
        var juan = l.Alumnos.Single(a => a.Rotulo == "Juan P.").Resumen!;
        Assert.Equal((2, 1), (juan.Evaluaciones, juan.Conteo.ConNota));
        Assert.NotNull(juan.PromedioSimple);
        Assert.All(l.Asignaciones, c => Assert.NotNull(c.Conteo));
    }

    [Fact]
    public void RegistrarLoCalificado_DiceCuantasSeRegistraronCuantasYaEstabanYLoQueAunNoSePuede()
    {
        var ya = Cargar<RegistroDeAsignacion>("registrar_ya_registrada");
        Assert.Equal((0, 1, 0, 0), (ya.Registradas, ya.YaRegistradas, ya.NoRegistrables.Count, ya.EnModoSimple));
        var simple = Cargar<RegistroDeAsignacion>("registrar_modo_simple");
        Assert.Equal((0, 0, 1), (simple.Registradas, simple.YaRegistradas, simple.EnModoSimple));
        var pendiente = Assert.Single(Cargar<RegistroDeAsignacion>("registrar_con_pendientes").NoRegistrables);
        Assert.Equal("revision_pendiente", pendiente.Motivo);
        Assert.Contains("respuestas por revisar", pendiente.Detalle);
        Assert.NotEmpty(pendiente.IntentoId);
        Assert.NotEmpty(pendiente.AlumnoId);
    }

    [Fact]
    public void Publicacion_EstampaLaPresentacionYSeRetiraConMotivo()
    {
        var p = Cargar<CambioDeCalificacion>("publicada").Calificacion;
        Assert.Equal((EstadosDeCalificacion.Definitiva, true), (p.Estado, p.Publicada));
        Assert.False(p.Presentacion!.Provisional);
        Assert.Equal("co-1-5", p.Presentacion.Escala!.Codigo);
        Assert.NotNull(p.PublicadaEn);
        var retirada = Cargar<CambioDeCalificacion>("retirada");
        Assert.Equal(("retiro_publicacion", EstadosDeCalificacion.Revisada), (retirada.Historial.Last().Tipo, retirada.Calificacion.Estado));
        var reabierta = Cargar<CambioDeCalificacion>("reabierta");
        Assert.True(reabierta.Calificacion.EstaReabierta);
        Assert.False(GradebookTexto.PuedeAjustar(reabierta.Calificacion));
        var masiva = Cargar<PublicacionDeAsignacion>("publicar_asignacion");
        Assert.Equal((1, 0), (masiva.TotalPublicadas, masiva.YaPublicadas));
    }

    [Fact]
    public void LosErroresTraenSuCodigoYSusDatos()
    {
        var conflicto = JsonSerializer.Deserialize<JsonElement>(Leer("ajuste_conflicto"));
        Assert.Equal("conflicto_de_version", conflicto.GetProperty("codigo").GetString());
        Assert.Equal(2, conflicto.GetProperty("version_actual").GetInt32());
        Assert.Equal(85m, conflicto.GetProperty("puntaje_efectivo").GetDecimal());
        Assert.Equal("puntaje_invalido", JsonSerializer.Deserialize<JsonElement>(Leer("ajuste_invalido")).GetProperty("codigo").GetString());
        var sinPermiso = JsonSerializer.Deserialize<JsonElement>(Leer("sin_permiso"));
        Assert.Equal(("sin_permiso", "grades.mode.set"), (sinPermiso.GetProperty("codigo").GetString(), sinPermiso.GetProperty("permiso").GetString()));
        var invalida = JsonSerializer.Deserialize<JsonElement>(Leer("escala_invalida"));
        Assert.Equal("escala_invalida", invalida.GetProperty("codigo").GetString());
        Assert.Contains(invalida.GetProperty("problemas").EnumerateArray(), p => p.GetString()!.Contains("Hueco"));
    }

    // --------------------------------------------------------------------------------------- el alumno

    [Fact]
    public void MiasSinPublicar_SoloElEstadoDeLaEntrega_SinNingunaCifra()
    {
        var m = Cargar<MisResultados>("mias_sin_publicar");
        var item = Assert.Single(m.Items);
        Assert.Equal(("calificaciones", "resultado_no_publicado", EstadosSimples.Completado), (item.Modo, item.Estado, item.EstadoSimple));
        Assert.False(item.TieneNota);
        Assert.Null(item.Calificacion);
        Assert.DoesNotContain("puntaje", Leer("mias_sin_publicar"));
        Assert.DoesNotContain("porcentaje", Leer("mias_sin_publicar"));
    }

    [Fact]
    public void MiasPublicada_LaNotaPresentadaPorLaEscalaSinElResultadoInterno()
    {
        var item = Assert.Single(Cargar<MisResultados>("mias_publicada").Items);
        Assert.True(item.TieneNota);
        Assert.Equal("publicado", item.Estado);
        Assert.Equal(4.4m, item.Calificacion!.Presentada!.Valor);
        Assert.Equal("Alto", item.Calificacion.Desempeno!.Nivel);
        Assert.NotEmpty(item.Calificacion.Retroalimentacion!);
        // Junto a su nota, el alumno lee con qué sistema se presentó (el de la versión con que se publicó) y desde dónde se aprueba.
        var sistema = item.Calificacion.Escala!;
        Assert.Equal(("co-1-5", "CO", 3m, "Básico"), (sistema.Codigo, sistema.Pais, sistema.AprobacionMinima, sistema.ApruebaDesde));
        Assert.Equal("De 1 a 5 · Se aprueba con 3 o más", GradebookTexto.ResumenDelSistema(sistema));
        Assert.DoesNotContain("interno", Leer("mias_publicada"));
        Assert.DoesNotContain("puntaje_efectivo", Leer("mias_publicada"));
    }

    [Fact]
    public void MiasSimple_TST075_SimbolosYNingunNumero()
    {
        foreach (var nombre in new[] { "mias_simple", "mias_simple_sin_empezar" })
        {
            var m = Cargar<MisResultados>(nombre);
            var item = Assert.Single(m.Items);
            Assert.True(item.EsSimple);
            Assert.Null(item.Calificacion);
            Assert.Null(item.Estado);
            // En lo que ve el alumno no hay un solo número fuera de `nota` (sólo el reloj del nodo, que la pantalla no muestra). `nota` —el porcentaje del examen, sin escala, con sus aciertos—
            // sólo viaja cuando el profesor liberó el resultado (decisión del 2026-10-19): sin liberar, ni eso.
            using var doc = JsonDocument.Parse(Leer(nombre));
            var item0 = doc.RootElement.GetProperty("items")[0];
            var sinNota = item0.EnumerateObject().Where(p => p.Name != "nota").SelectMany(p => Numeros(p.Value));
            Assert.Empty(sinNota);
            if (nombre == "mias_simple_sin_empezar") Assert.Null(item.Nota);
            else Assert.Equal((10, 12), (item.Nota!.Aciertos, item.Nota.Preguntas));
        }
        Assert.Equal(EstadosSimples.NoIniciado, Cargar<MisResultados>("mias_simple_sin_empezar").Items.Single().EstadoSimple);
        var completado = Cargar<MisResultados>("mias_simple").Items.Single();
        Assert.Equal((EstadosSimples.Completado, "lleno"), (completado.EstadoSimple, completado.Simbolo));
        Assert.All(completado.Aciertos!.Simbolos, s => Assert.Contains(s, new[] { "acierto", "fallo" }));
    }

    private static IEnumerable<JsonElement> Numeros(JsonElement e)
    {
        switch (e.ValueKind)
        {
            case JsonValueKind.Number: yield return e; break;
            case JsonValueKind.Object: foreach (var p in e.EnumerateObject()) foreach (var n in Numeros(p.Value)) yield return n; break;
            case JsonValueKind.Array: foreach (var x in e.EnumerateArray()) foreach (var n in Numeros(x)) yield return n; break;
        }
    }

    // ------------------------------------------------------------------------------------- configuración

    [Fact]
    public void Configuracion_LosCincoNivelesLaPoliticaYLasEscalas()
    {
        var inicial = Cargar<ConfiguracionAcademica>("configuracion_inicial");
        Assert.Equal(NivelesEducativos.Todos, inicial.Niveles.Select(n => n.NivelClave).ToArray());
        Assert.All(inicial.Niveles, n => Assert.True(n.PorDefecto && n.Modo == ModosDeNivel.Simple));       // el modo simple es el valor por defecto
        Assert.Empty(inicial.Escalas);
        Assert.True(inicial.Politica.PoliticaProvisional);
        Assert.False(inicial.Politica.PonderacionesAplicadas);
        var c = Cargar<ConfiguracionAcademica>("configuracion");
        Assert.True(c.Niveles.Single(n => n.NivelClave == "secundaria").EnModoCalificaciones);
        Assert.Equal("co-1-5", Assert.Single(c.Escalas).Codigo);
        Assert.Equal(("CO", "ultimo"), (c.Politica.Pais, c.Politica.PoliticaIntentos));
    }

    [Fact]
    public void ConfigurarPolitica_DiceSiCambioYRepetirNoCambiaNada()
    {
        var cambiada = Cargar<PoliticaConfigurada>("politica_mejor");
        Assert.True(cambiada.Cambiado);
        Assert.Equal("mejor", cambiada.Politica.PoliticaIntentos);
        Assert.False(cambiada.Politica.PoliticaProvisional);                  // ya la configuró la institución
        var repetida = Cargar<PoliticaConfigurada>("politica_repetida");
        Assert.False(repetida.Cambiado);
        Assert.Equal(cambiada.Politica.Version, repetida.Politica.Version);   // repetir no sube la versión de la política
    }

    [Fact]
    public void ConfirmarRevision_DiceSiRecalificarDescartoUnAjuste()
    {
        var sinAjuste = Cargar<RevisionConfirmada>("revision_confirmada");
        Assert.False(sinAjuste.AjusteDescartado);
        Assert.Null(sinAjuste.AjusteAnterior);
        var conAjuste = JsonSerializer.Deserialize<RevisionConfirmada>(
            """{"intento_id":"i","estado":"calificado","resultado":"recalculada","registrada":true,"ajuste_descartado":true,"ajuste_anterior":99.0}""", Ayudas.Web)!;
        Assert.True(conAjuste.AjusteDescartado);
        Assert.Equal(99m, conAjuste.AjusteAnterior);
    }

    [Fact]
    public void PlantillasYEscalas()
    {
        var p = Cargar<PlantillasDeEscalas>("plantillas");
        Assert.True(p.Plantillas.Count >= 15);
        Assert.All(p.Plantillas, x => Assert.Contains("orientativa", x.Advertencia));
        Assert.Equal(new[] { "CL", "CO", "EC", "ES", "MX", "PE", "US" }, p.Plantillas.Select(x => x.Pais).Where(x => !string.IsNullOrEmpty(x)).Distinct().OrderBy(x => x, StringComparer.Ordinal).ToArray());
        // Los sistemas de la tabla internacional, cada uno con su resumen listo para leerse.
        var porCodigo = p.Plantillas.ToDictionary(x => x.Codigo);
        Assert.Equal(("Se aprueba desde Suficiente", ""), (GradebookTexto.MinimoParaAprobar(porCodigo["es-terminos"].Sistema), GradebookTexto.Rango(porCodigo["es-terminos"].Sistema)));
        Assert.Equal("Insuficiente · Suficiente · Bien · Notable · Sobresaliente", GradebookTexto.Niveles(porCodigo["es-terminos"].Sistema));
        Assert.Equal("De 0 a 4 · Se aprueba con 1 o más", GradebookTexto.ResumenDelSistema(porCodigo["us-gpa"].Sistema));
        Assert.Equal("De 5 a 10 · Se aprueba con 6 o más", GradebookTexto.ResumenDelSistema(porCodigo["mx-5-10"].Sistema));
        Assert.Equal("De 1 a 7 · Se aprueba con 4 o más", GradebookTexto.ResumenDelSistema(porCodigo["cl-1-7"].Sistema));
        Assert.Equal("De 0 a 20 · Se aprueba con 11 o más", GradebookTexto.ResumenDelSistema(porCodigo["pe-0-20"].Sistema));
        Assert.Equal("C · B · A · AD", GradebookTexto.Niveles(porCodigo["pe-literal"].Sistema));
        Assert.Null(GradebookTexto.MinimoParaAprobar(porCodigo["pe-literal"].Sistema));                    // las competencias no fijan un umbral: no se inventa uno
        Assert.Equal("De 0 a 10 · Se aprueba con 7 o más", GradebookTexto.ResumenDelSistema(porCodigo["ec-0-10"].Sistema));
        var e = Cargar<EscalaAdoptada>("escala");
        Assert.Equal(("co-1-5", "numerica", "co-1-5"), (e.Codigo, e.Tipo, e.PlantillaOrigen));
        var v = Assert.Single(e.Versiones!);
        Assert.Equal(1, v.Numero);
        Assert.Equal(64, v.Huella.Length);
        Assert.Equal(JsonValueKind.Object, v.Definicion!.Value.ValueKind);
    }

    [Fact]
    public void VistaPrevia_SeparaLasCuatroCosas()
    {
        var v = Cargar<VistaPreviaDeEscala>("vista_previa");
        Assert.Equal(6, v.Conversiones.Count);
        var cincuenta = v.Conversiones.Single(c => c.Interno == 50m);
        Assert.Equal(3.0m, cincuenta.Presentada.Valor);
        Assert.Equal("Básico", cincuenta.Desempeno.Nivel);
        Assert.True(cincuenta.Aprobacion.CumpleCriterio);
        Assert.False(v.Conversiones.Single(c => c.Interno == 49.99m).Aprobacion.CumpleCriterio);
    }

    [Fact]
    public void CambioDeModo_ValidarYConfigurar()
    {
        var v = Cargar<ValidacionDeNivel>("nivel_validado");
        Assert.True(v.Permitido);
        Assert.Equal(("simple", "calificaciones", 0), (v.De, v.A, v.EnCurso));
        Assert.NotEmpty(v.Advertencias);
        var c = Cargar<NivelCambiado>("nivel_cambiado");
        Assert.True(c.Cambiado);
        Assert.True(c.Nivel.EnModoCalificaciones);
        Assert.Equal("co-1-5", c.Nivel.Escala!.Codigo);
    }

    [Fact]
    public void ResumenDelPeriodo_EsInformativoYNoOficial()
    {
        var r = Cargar<ResumenDePeriodo>("resumen");
        Assert.False(r.Oficial);
        Assert.False(r.Ponderado);
        Assert.Contains("No es una calificación oficial", r.Aviso);
        var curso = Assert.Single(r.Cursos);
        Assert.False(curso.DatosSuficientes);                                          // con menos de tres alumnos no hay promedio de grupo
        Assert.Null(curso.PromedioDelGrupo);
    }
}

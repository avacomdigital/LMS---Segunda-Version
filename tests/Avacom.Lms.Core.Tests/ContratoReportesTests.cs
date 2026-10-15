using System.Text.Json;
using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Reporting;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// Los DTOs de <c>/api/reportes/</c> contra respuestas REALES del backend, capturadas por <c>backend/reporting/tests/test_capturar_contrato.py</c> en <c>Fixtures/reportes/</c>. Un campo
/// mal escrito en un DTO se descubre aquí y no en una pantalla. Se comprueba la FORMA y los valores que no cambian entre corridas (los identificadores y las horas sí cambian).
/// </summary>
public sealed class ContratoReportesTests
{
    private static string Ruta(string nombre, string extension = ".json") => Path.Combine(AppContext.BaseDirectory, "Fixtures", "reportes", nombre + extension);

    private static T Cargar<T>(string nombre) =>
        JsonSerializer.Deserialize<T>(File.ReadAllText(Ruta(nombre)), Ayudas.Web) ?? throw new InvalidOperationException($"{nombre}.json no se pudo leer como {typeof(T).Name}.");

    private static JsonElement Error(string nombre) => Ayudas.Json(File.ReadAllText(Ruta(nombre)));

    // ----------------------------------------------------------------------------------------------- una clase (CAP-081)

    [Fact]
    public void ReporteDeClase_TraeFilasTotalesYElCorteDeBr083()
    {
        var r = Cargar<ReporteDeClase>("clase");
        Assert.Equal((TiposDeReporte.Clase, "Reporte de la clase", true), (r.Tipo, r.Titulo, r.Nominal));
        Assert.Equal(5, r.Filas.Count);
        Assert.Equal((5, 1), (r.Totales.Participantes, r.Totales.Actividades));
        Assert.Equal(61.11m, r.Totales.PromedioAciertos);
        Assert.Equal(80m, r.Totales.PromedioParticipacion);
        Assert.Equal("Estados de la materia y sus cambios", r.Clase.CursoRotulo);
        Assert.Equal(("8A", "Octavo A", "2026"), (r.Clase.Grupo!.Codigo, r.Clase.Grupo.Nombre, r.Clase.Grupo.Periodo));
        Assert.False(r.Objetivos.Disponible);
        Assert.Equal(EstadosDeProyeccion.AlDia, r.Corte.Estado);
        Assert.False(r.Corte.Incompleto);
        Assert.Equal(("completa", 5, 0), (r.Corte.Integracion.Estado, r.Corte.Integracion.Equipos, r.Corte.Integracion.SinSincronizar));
        Assert.StartsWith("Datos al ", r.Corte.Texto);
        Assert.Equal("Esto es lo que había en el nodo a esa hora.", r.Corte.Explicacion);
        Assert.False(r.Privacidad.Aplicada);
        Assert.False(string.IsNullOrEmpty(r.GeneradoPor.Id));
    }

    [Fact]
    public void UnAlumnoQueNoEntrego_NoTieneCeroPorCientoDeAciertos_TieneNull()
    {
        var r = Cargar<ReporteDeClase>("clase");
        var sinEntregar = r.Filas.Single(f => f.ActividadesEntregadas == 0);
        Assert.Null(sinEntregar.PorcentajeAciertos);
        Assert.Equal(0m, sinEntregar.PorcentajeParticipacion);
        Assert.Equal(FormatoDeReportes.SinDato, FormatoDeReportes.Porcentaje(sinEntregar.PorcentajeAciertos));
        var conTodo = r.Filas.First(f => f.PorcentajeAciertos == 100m);
        Assert.Equal((5, 5, "conectado"), (conTodo.Aciertos, conTodo.Calificadas, conTodo.Estado));
    }

    [Fact]
    public void UnaClaseIncompleta_DiceCuantasTabletasFaltanYPorQue()
    {
        var r = Cargar<ReporteDeClase>("clase_incompleta");
        Assert.True(r.Corte.Incompleto);
        Assert.Equal(("incompleta", 1), (r.Corte.Integracion.Estado, r.Corte.Integracion.SinSincronizar));
        Assert.True(r.Corte.Integracion.Incompleta);
        Assert.Equal("conexion_perdida", r.Corte.Integracion.Motivos.Single().Codigo);
        Assert.Equal("1 tableta aún no sincroniza", r.Corte.Integracion.MotivoLinea);
        Assert.EndsWith("· 1 tableta sin sincronizar", r.Corte.Texto);
        Assert.Contains(r.Filas, f => f.Estado == "reconectando");
        Assert.Equal("Sin conexión al cerrar", FormatoDeReportes.Presencia("reconectando"));
    }

    [Fact]
    public void ConLaPrivacidadAplicada_NoHayFilasIdentificablesYSeDice()
    {
        var r = Cargar<ReporteDeClase>("clase_privacidad");
        Assert.True(r.Privacidad.UmbralActivo);
        Assert.True(r.Privacidad.Aplicada);
        Assert.Equal((2, 5), (r.Privacidad.Alumnos, r.Privacidad.Minimo));
        Assert.Empty(r.Filas);
        Assert.False(r.Nominal);
        Assert.Equal(2, r.Totales.Participantes);                                    // el agregado sí
        Assert.Contains("menos de 5", r.Privacidad.Aviso);
        Assert.Equal(r.Privacidad.Aviso, EstadosVaciosDeReportes.SinAlumnosVisibles(r.Privacidad));
    }

    // ----------------------------------------------------------------------------------------------- listados y filtros

    [Fact]
    public void ListaDeClases_TraeLoQueHaceFaltaParaElegirUna()
    {
        var l = Cargar<ListaDeClases>("clases");
        Assert.Equal((2, EstadosDeProyeccion.AlDia), (l.Total, l.Estado));
        Assert.All(l.Clases, c => Assert.False(string.IsNullOrEmpty(c.SesionId)));
        Assert.Contains(l.Clases, c => c.Incompleta);
        Assert.Equal("8A", l.Clases[0].Grupo!.Rotulo);
    }

    [Fact]
    public void Filtros_OfreceGruposPeriodosArbolYLoQuePuedeHacerQuienPregunta()
    {
        var f = Cargar<FiltrosDeReportes>("filtros");
        Assert.Equal("8A", Assert.Single(f.Grupos).Rotulo);
        Assert.Equal(new[] { "2026" }, f.Periodos);
        Assert.True(f.Nodos.Disponible);
        Assert.Equal("Colombia", f.Nodos.Arbol[0].Name);
        Assert.False(f.Objetivos.Disponible);
        Assert.Equal(("profesor", true, true, true, false, true, false), ("profesor", f.Puede.Clase, f.Puede.Grupo, f.Puede.Alumno, f.Puede.Uso, f.Puede.Exportar, f.Puede.Reconstruir));
        Assert.True(f.Puede.PuedeVerAlgo);
    }

    [Fact]
    public void AlumnosParaElegir_TraeLaInicialDeCadaUno()
    {
        var a = Cargar<AlumnosParaElegir>("alumnos");
        Assert.NotEmpty(a.Alumnos);
        Assert.All(a.Alumnos, x => Assert.Equal(1, x.Inicial.Length));
        Assert.Equal(a.Alumnos.Count, a.Iniciales.Sum(i => i.Cantidad));
    }

    [Fact]
    public void Recientes_TraenSusParametrosParaVolverAAbrirlos()
    {
        var r = Cargar<RecientesDeReportes>("recientes");
        Assert.NotEmpty(r.Recientes);
        var alumno = r.Recientes.First(x => x.Tipo == TiposDeReporte.Alumno);
        Assert.False(string.IsNullOrEmpty(alumno.Parametro("alumno_id")));
        Assert.Null(alumno.Parametro("no_existe"));
        Assert.All(r.Recientes, x => Assert.False(string.IsNullOrEmpty(x.Titulo)));
    }

    // ----------------------------------------------------------------------------------------------- grupo y alumno

    [Fact]
    public void ReporteDeGrupo_PoneLosTotalesLasClasesYLasEvaluacionesConConteos()
    {
        var g = Cargar<ReporteDeGrupo>("grupo");
        Assert.Equal(("grupo", "simple", false), (g.Tipo, g.Modo, g.EnModoCalificaciones));
        Assert.Null(g.Escala);
        Assert.Equal(g.Totales.Alumnos, g.Alumnos.Count);
        Assert.Equal(g.Totales.EnAtencion, g.Atencion.Count);
        Assert.Equal(g.Totales.Clases, g.Clases.Count);
        Assert.Equal("Examen de los estados", Assert.Single(g.Evaluaciones).Titulo);
        Assert.False(g.Objetivos.Disponible);
        Assert.True(g.Corte.Incompleto);
        Assert.Contains(g.Clases, c => c.Incompleta);
        Assert.All(g.Alumnos, a => Assert.Equal(a.Atencion.Count > 0, a.NecesitaAtencion));
    }

    [Fact]
    public void ReporteDeGrupoConPrivacidad_NoTrae_Alumnos_NiAtencion()
    {
        var g = Cargar<ReporteDeGrupo>("grupo_privacidad");                                   // el 9B de Prof. Ruiz: dos alumnos y el umbral activo
        Assert.True(g.Privacidad.Aplicada);
        Assert.Equal((2, 5), (g.Privacidad.Alumnos, g.Privacidad.Minimo));
        Assert.Empty(g.Alumnos);
        Assert.Empty(g.Atencion);
        Assert.Equal(0, g.Totales.EnAtencion);
        Assert.Equal(2, g.Totales.Alumnos);                                                   // el agregado sí
        Assert.Null(g.Totales.PromedioAciertos);                                              // sin clases todavía: sin dato, no cero
        Assert.False(g.Nominal);
        Assert.Equal("9B", g.Grupo.Codigo);
    }

    [Fact]
    public void ReporteDeAlumno_DiceClasesEvaluacionesYEstudioSinNotasEnModoSimple()
    {
        var a = Cargar<ReporteDeAlumno>("alumno");
        Assert.True(a.Nominal);
        var g = Assert.Single(a.Grupos);
        Assert.Equal(("simple", false), (g.Modo, g.EnModoCalificaciones));
        Assert.Equal(2, g.Resumen.ClasesTotal);
        var e = Assert.Single(g.Evaluaciones);
        Assert.Null(e.Presentacion);
        Assert.Equal(("vacio", "Aún sin presentar", "○"), (e.Simbolo, PresentacionDeNotas.Texto(e), PresentacionDeNotas.Simbolo(e.Simbolo)));
        Assert.Equal("Leer la lección", Assert.Single(g.Estudios).Titulo);
        Assert.Equal(2, g.Clases.Count);
        Assert.Equal(string.Empty, g.MotivoDeAtencion);
    }

    // ----------------------------------------------------------------------------------------------- uso de equipos

    [Fact]
    public void ReporteDeUso_NoLlevaPersonasYTrae_EquiposYClases()
    {
        var u = Cargar<ReporteDeUso>("uso");
        Assert.False(u.Nominal);
        Assert.Equal(2, u.Totales.Clases);
        Assert.Equal(u.Totales.Equipos, u.Equipos.Count);
        Assert.All(u.Equipos, e => { Assert.False(string.IsNullOrEmpty(e.Nombre)); Assert.True(e.Clases >= 1); });
        Assert.Null(u.Periodo.Desde);
        Assert.Null(u.Periodo.Hasta);
        Assert.Equal(u.Totales.TiempoTotalMs, u.Clases.Sum(c => c.DuracionMs));
    }

    // ----------------------------------------------------------------------------------- configuración y agregados

    [Fact]
    public void Configuracion_DeFabrica_PermiteTodoYNoPideRazon()
    {
        var c = Cargar<RespuestaDeConfiguracion>("configuracion").Configuracion;
        Assert.Equal((false, true, false, 0, 5), (c.UmbralPrivacidad, c.ExtraiblesPermitidos, c.ExigirRazon, c.Version, c.MinimoDeAlumnos));
        Assert.Equal(new[] { "extraible", "carpeta_local", "red" }, c.Destinos);
        Assert.Equal(new[] { "xlsx", "csv" }, c.Formatos);
        Assert.Contains(c.Razones, r => r.Codigo == "entrega_a_familias");
    }

    [Fact]
    public void CambiarLaConfiguracion_DiceQueCambioYSubeLaVersion()
    {
        var r = Cargar<RespuestaDeConfiguracion>("configuracion_cambiada");
        Assert.True(r.Cambiado);
        Assert.True(r.Configuracion.UmbralPrivacidad);
        Assert.Equal(1, r.Configuracion.Version);
        Assert.False(string.IsNullOrEmpty(r.Configuracion.ActualizadaPor));
    }

    [Fact]
    public void EstadoDeAgregados_MuestraAntiguedadFuentesYReconstruccion()
    {
        var e = Cargar<EstadoDeAgregados>("estado");
        Assert.Equal(EstadosDeProyeccion.AlDia, e.Estado);
        Assert.Equal(new[] { "aula", "evaluacion", "calificacion", "estudio" }, e.Fuentes.Select(f => f.Fuente).ToArray());
        Assert.Equal(2, e.Grupos.Total);
        Assert.False(e.Reconstruccion.EnCurso);
        Assert.False(e.PuedeReconstruir);                                                     // había una clase abierta cuando se capturó
        Assert.True(e.ClaseEnCurso);
    }

    [Fact]
    public void Reconstruir_DiceCuantoBorroYCuantoRehizo()
    {
        var r = Cargar<ResultadoDeReconstruccion>("reconstruir");
        Assert.True(r.Eventos > 0);
        Assert.Equal(2, r.Grupos);
        Assert.Empty(r.GruposFallidos);
        Assert.Equal(2, r.Borradas["m13_clase"]);
        Assert.All(r.Borradas.Keys, k => Assert.StartsWith("m13_", k));
        var a = Cargar<ResultadoDeActualizacion>("actualizar");
        Assert.Equal(0, a.Eventos);
    }

    // ----------------------------------------------------------------------------------------------- exportar

    [Fact]
    public void AlcanceDeExportacion_DiceQueSeVaAGuardarYSiLlevaNombres()
    {
        var a = Cargar<AlcanceDeExportacion>("exportacion_alcance");
        Assert.Equal(("grupo", "xlsx", true, false), (a.Tipo, a.Formato, a.Nominal, a.UmbralAplicado));
        Assert.StartsWith("Vas a guardar el reporte del grupo 8A (", a.TextoAlcance);
        Assert.Equal("El archivo incluirá nombres de alumnos. Una vez fuera de este equipo, el colegio ya no controla quién lo abre.", a.Advertencia);
        Assert.Matches(@"^reporte-grupo-8A-\d{4}-\d\d-\d\d-\d{4}\.xlsx$", a.NombreSugerido);
        Assert.Equal(new[] { "xlsx", "csv" }, a.Formatos);
        Assert.True(a.Politica.ExtraiblesPermitidos);
        Assert.False(a.Politica.ExigirRazon);
        Assert.NotEmpty(a.Politica.Razones);
    }

    [Fact]
    public void LaExportacionConfirmada_CuentaSusIntentosYNuncaLleva_LaRuta()
    {
        var r = Cargar<RespuestaDeExportacion>("confirmacion_guardado");
        Assert.False(r.Reintento);
        var e = r.Exportacion;
        Assert.Equal((EstadosDeExportacion.Entregada, "carpeta_local", "extraible"), (e.Estado, e.DestinoTipo, e.DestinoAutorizado));
        Assert.Equal(new[] { "fallido", "fallido", "guardado" }, e.Intentos.Select(i => i.Resultado).ToArray());
        Assert.Equal(("fallido", "medio_retirado", "extraible"), (e.Intentos[0].Resultado, e.Intentos[0].Motivo, e.Intentos[0].DestinoTipo));
        Assert.Equal("verificacion_fallida", e.Intentos[1].Motivo);
        Assert.Matches("^[0-9a-f]{64}$", e.Huella);
        Assert.DoesNotContain(":\\", File.ReadAllText(Ruta("confirmacion_guardado")));
        Assert.Equal(e.Huella, Cargar<RespuestaDeExportacion>("exportacion").Exportacion.Huella);
        Assert.Equal(EstadosDeExportacion.Entregada, Cargar<ListaDeExportaciones>("exportaciones").Exportaciones[0].Estado);
    }

    [Fact]
    public void LaConfirmacionFallida_NoCierraLaExportacion()
    {
        var e = Cargar<RespuestaDeExportacion>("confirmacion_fallida").Exportacion;
        Assert.Equal(EstadosDeExportacion.Autorizada, e.Estado);
        Assert.Null(e.DestinoTipo);
        Assert.Null(e.ConfirmadaEn);
        Assert.Single(e.Intentos);
    }

    [Fact]
    public void LosEncabezadosDelArchivoSonLosQueElClienteLee_YLaHuellaEsLaDelCuerpo()
    {
        var encabezados = Ayudas.Json(File.ReadAllText(Ruta("exportacion_encabezados")));
        var cuerpo = File.ReadAllBytes(Ruta("exportacion_cuerpo", ".csv"));
        Assert.Equal(Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(cuerpo)), encabezados.GetProperty("X-Avacom-Export-Huella").GetString());
        Assert.Equal(cuerpo.Length.ToString(), encabezados.GetProperty("X-Avacom-Export-Bytes").GetString());
        Assert.Equal("text/csv; charset=utf-8", encabezados.GetProperty("Content-Type").GetString());
        Assert.StartsWith("reporte-grupo-8A-", encabezados.GetProperty("X-Avacom-Export-Nombre").GetString());
        Assert.Equal(new byte[] { 0xEF, 0xBB, 0xBF }, cuerpo[..3]);                              // UTF-8 con BOM
        Assert.Contains("Datos al corte;", System.Text.Encoding.UTF8.GetString(cuerpo));
    }

    // ----------------------------------------------------------------------------------------------- errores reales

    [Theory]
    [InlineData("error_sin_permiso", "sin_permiso")]
    [InlineData("error_fuera_de_alcance", "fuera_de_alcance")]
    [InlineData("error_no_encontrado", "no_encontrado")]
    [InlineData("error_clase_en_curso", "clase_en_curso")]
    [InlineData("error_sin_clases_finalizadas", "sin_sesiones_finalizadas")]
    [InlineData("error_reservada", "capacidad_reservada")]
    [InlineData("error_reconstruir_sesion_activa", "sesion_activa")]
    [InlineData("error_configuracion_conflicto", "conflicto_de_version")]
    [InlineData("error_huella_distinta", "huella_distinta")]
    [InlineData("error_exportacion_caducada", "exportacion_caducada")]
    [InlineData("error_razon_requerida", "razon_requerida")]
    [InlineData("error_destino_no_permitido", "destino_no_permitido")]
    [InlineData("error_reconstruir_sin_permiso", "sin_permiso")]
    public void CadaErrorDelNodo_TraeSuCodigoYUnMensajeParaLaPersona(string archivo, string codigo)
    {
        var json = Error(archivo);
        Assert.Equal(codigo, json.GetProperty("codigo").GetString());
        var detalle = json.GetProperty("detail").GetString()!;
        Assert.False(string.IsNullOrWhiteSpace(detalle));
        var error = new ErrorAula(409, codigo, detalle, null, json);
        var mensaje = MensajesDeReportes.De(error);
        Assert.False(string.IsNullOrWhiteSpace(mensaje));
        Assert.DoesNotContain("excepción", mensaje, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(codigo, mensaje.Replace(" ", "_"), StringComparison.OrdinalIgnoreCase);
    }
}

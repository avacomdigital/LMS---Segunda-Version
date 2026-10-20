using System.Text.Json.Serialization;

namespace Avacom.Lms.Core.Gradebook;

// El boletín de un estudiante (vista del PROFESOR) y los resúmenes que alimentan las listas de estudiantes y de evaluaciones. Todo lo calcula el nodo: aquí sólo se leen las respuestas.
// El promedio es SIMPLE e INFORMATIVO (no ponderado, no oficial); lo pendiente no es un cero (su promedio es nulo); en modo simple no hay cifras.

/// <summary>Cuántas evaluaciones hay en cada situación: lo que ya tiene nota, lo que falta publicar, lo que espera revisión, lo calificado sin registrar y lo que aún no se hizo.</summary>
public sealed record ConteoDeEvaluaciones(
    [property: JsonPropertyName("completadas")] int Completadas,
    [property: JsonPropertyName("con_nota")] int ConNota,
    [property: JsonPropertyName("publicadas")] int Publicadas,
    [property: JsonPropertyName("sin_publicar")] int SinPublicar,
    [property: JsonPropertyName("por_revisar")] int PorRevisar,
    [property: JsonPropertyName("sin_registro")] int SinRegistro,
    [property: JsonPropertyName("pendientes")] int Pendientes,
    [property: JsonPropertyName("aprobadas")] int Aprobadas,
    [property: JsonPropertyName("no_aprobadas")] int NoAprobadas)
{
    /// <summary>Lo que le falta al profesor por hacer con esas evaluaciones: revisar, registrar o publicar.</summary>
    public int PorAtender => PorRevisar + SinRegistro + SinPublicar;
}

/// <summary>Un promedio visto con el sistema de calificación del nivel: «3,8 · Básico · cumple el criterio».</summary>
public sealed record PromedioPresentado(
    [property: JsonPropertyName("etiqueta")] string Etiqueta,
    [property: JsonPropertyName("valor")] decimal? Valor,
    [property: JsonPropertyName("clave")] string Clave,
    [property: JsonPropertyName("desempeno")] string? Desempeno,
    [property: JsonPropertyName("cumple_criterio")] bool? CumpleCriterio);

/// <summary>Los puntos brutos sumados de unas evaluaciones con nota: lo obtenido sobre lo posible y el porcentaje que resulta. Sin ninguna con puntos, todo nulo.</summary>
public sealed record SumaBruta(
    [property: JsonPropertyName("puntos")] decimal? Puntos,
    [property: JsonPropertyName("puntos_maximos")] decimal? PuntosMaximos,
    [property: JsonPropertyName("porcentaje")] decimal? Porcentaje,
    [property: JsonPropertyName("evaluaciones")] int Evaluaciones)
{
    public bool TienePuntos => Puntos is not null && PuntosMaximos is > 0;
}

/// <summary>Lo que lleva un estudiante en un grupo: en el libro en modo resumen (la lista de estudiantes) y en su boletín.</summary>
public sealed record ResumenDeEstudiante(
    [property: JsonPropertyName("evaluaciones")] int Evaluaciones,
    [property: JsonPropertyName("conteo")] ConteoDeEvaluaciones Conteo,
    [property: JsonPropertyName("promedio_simple")] decimal? PromedioSimple = null,
    [property: JsonPropertyName("presentado")] PromedioPresentado? Presentado = null,
    [property: JsonPropertyName("oficial")] bool Oficial = false,
    [property: JsonPropertyName("ponderado")] bool Ponderado = false,
    [property: JsonPropertyName("bruto")] SumaBruta? Bruto = null);

public sealed record CursoDelBoletin(
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("curso_rotulo")] string CursoRotulo,
    [property: JsonPropertyName("evaluaciones")] int Evaluaciones,
    [property: JsonPropertyName("conteo")] ConteoDeEvaluaciones Conteo,
    [property: JsonPropertyName("promedio_simple")] decimal? PromedioSimple = null,
    [property: JsonPropertyName("presentado")] PromedioPresentado? Presentado = null,
    [property: JsonPropertyName("bruto")] SumaBruta? Bruto = null,
    [property: JsonPropertyName("materia")] string? Materia = null);

/// <summary>Una recomendación del catálogo cerrado del nodo (se toca, no se escribe).</summary>
public sealed record RecomendacionDelCatalogo(
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("texto")] string Texto);

/// <summary>Lo que el profesor recomienda a un estudiante en el periodo del grupo, en general (<see cref="CursoRef"/> vacío) o sobre un curso. Cada cambio queda en la bitácora.</summary>
public sealed record ObservacionDelDocente(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("grupo_id")] string GrupoId,
    [property: JsonPropertyName("periodo")] string Periodo,
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("recomendaciones")] IReadOnlyList<RecomendacionDelCatalogo> Recomendaciones,
    [property: JsonPropertyName("texto")] string Texto,
    [property: JsonPropertyName("version")] int Version,
    [property: JsonPropertyName("actualizada_en")] long ActualizadaEn,
    [property: JsonPropertyName("actualizada_por")] string ActualizadaPor)
{
    public bool EsGeneral => string.IsNullOrEmpty(CursoRef);
}

public sealed record RespuestaDeObservacion(
    [property: JsonPropertyName("observacion")] ObservacionDelDocente Observacion,
    [property: JsonPropertyName("cambiado")] bool Cambiado,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

/// <summary>Hacia dónde va: <c>sube</c>, <c>baja</c>, <c>estable</c> o <c>insuficiente</c> (con menos de cuatro calificaciones no se dice).</summary>
public sealed record TendenciaDelEstudiante(
    [property: JsonPropertyName("direccion")] string Direccion,
    [property: JsonPropertyName("calificaciones")] int Calificaciones,
    [property: JsonPropertyName("minimo")] int? Minimo = null,
    [property: JsonPropertyName("de")] decimal? De = null,
    [property: JsonPropertyName("a")] decimal? A = null,
    [property: JsonPropertyName("diferencia")] decimal? Diferencia = null,
    [property: JsonPropertyName("comparadas")] int? Comparadas = null);

public sealed record CursoDestacado(
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("curso_rotulo")] string CursoRotulo,
    [property: JsonPropertyName("promedio_simple")] decimal? PromedioSimple,
    [property: JsonPropertyName("presentado")] PromedioPresentado? Presentado = null);

public sealed record ConstanciaDelEstudiante(
    [property: JsonPropertyName("completadas")] int Completadas,
    [property: JsonPropertyName("evaluaciones")] int Evaluaciones);

/// <summary>Una cosa que el profesor escribió del estudiante, con la evaluación y la fecha de la que sale.</summary>
public sealed record ComentarioDelProfesor(
    [property: JsonPropertyName("texto")] string Texto,
    [property: JsonPropertyName("titulo")] string? Titulo = null,
    [property: JsonPropertyName("fecha")] long? Fecha = null);

public sealed record ComentariosDelEstudiante(
    [property: JsonPropertyName("fortalezas")] IReadOnlyList<ComentarioDelProfesor> Fortalezas,
    [property: JsonPropertyName("dificultades")] IReadOnlyList<ComentarioDelProfesor> Dificultades,
    [property: JsonPropertyName("oportunidades")] IReadOnlyList<ComentarioDelProfesor> Oportunidades)
{
    public bool HayAlgo => Fortalezas.Count + Dificultades.Count + Oportunidades.Count > 0;
}

public sealed record InsightsDelEstudiante(
    [property: JsonPropertyName("tendencia")] TendenciaDelEstudiante Tendencia,
    [property: JsonPropertyName("constancia")] ConstanciaDelEstudiante Constancia,
    [property: JsonPropertyName("comentarios")] ComentariosDelEstudiante Comentarios,
    [property: JsonPropertyName("mejor_curso")] CursoDestacado? MejorCurso = null,
    [property: JsonPropertyName("curso_a_reforzar")] CursoDestacado? CursoAReforzar = null,
    [property: JsonPropertyName("informativo")] bool Informativo = true);

/// <summary>Una evaluación del estudiante en el boletín: su estado, y la nota presentada (provisional mientras no se publique) con el resultado interno que sólo ve el profesor.</summary>
public sealed record EvaluacionDelBoletin(
    [property: JsonPropertyName("asignacion_id")] string AsignacionId,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("estado_simple")] string EstadoSimple,
    [property: JsonPropertyName("publicada")] bool Publicada,
    [property: JsonPropertyName("curso_rotulo")] string? CursoRotulo = null,
    [property: JsonPropertyName("tipo_evaluacion")] string? TipoEvaluacion = null,
    [property: JsonPropertyName("fecha")] long? Fecha = null,
    [property: JsonPropertyName("calificacion_id")] string? CalificacionId = null,
    [property: JsonPropertyName("version")] int? Version = null,
    [property: JsonPropertyName("puntaje_efectivo")] decimal? PuntajeEfectivo = null,
    [property: JsonPropertyName("ajustada")] bool Ajustada = false,
    [property: JsonPropertyName("presentacion")] Presentacion? Presentacion = null,
    [property: JsonPropertyName("numero_intento")] int? NumeroIntento = null,
    [property: JsonPropertyName("intentos")] int Intentos = 0,
    [property: JsonPropertyName("bruto")] NotaEnBruto? Bruto = null,
    [property: JsonPropertyName("materia")] string? Materia = null);

public sealed record PaginaDeEvaluaciones(
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("desde")] int Desde,
    [property: JsonPropertyName("limite")] int Limite,
    [property: JsonPropertyName("items")] IReadOnlyList<EvaluacionDelBoletin> Items,
    [property: JsonPropertyName("curso_ref")] string? CursoRef = null)
{
    public bool HayMas => Desde + Items.Count < Total;
}

public sealed record AlumnoDelBoletin(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("rotulo")] string Rotulo);

public sealed record BoletinDelEstudiante(
    [property: JsonPropertyName("alumno")] AlumnoDelBoletin Alumno,
    [property: JsonPropertyName("grupo")] GrupoDelLibro Grupo,
    [property: JsonPropertyName("modo")] string Modo,
    [property: JsonPropertyName("resumen")] ResumenDeEstudiante Resumen,
    [property: JsonPropertyName("cursos")] IReadOnlyList<CursoDelBoletin> Cursos,
    [property: JsonPropertyName("insights")] InsightsDelEstudiante Insights,
    [property: JsonPropertyName("evaluaciones")] PaginaDeEvaluaciones Evaluaciones,
    [property: JsonPropertyName("servidor_en")] long ServidorEn,
    [property: JsonPropertyName("sistema")] EscalaResumen? Sistema = null,
    [property: JsonPropertyName("materias")] IReadOnlyList<MateriaDelLibro>? Materias = null,
    [property: JsonPropertyName("filtro")] FiltroDelLibro? Filtro = null,
    [property: JsonPropertyName("observaciones")] IReadOnlyList<ObservacionDelDocente>? Observaciones = null,
    [property: JsonPropertyName("recomendaciones_disponibles")] IReadOnlyList<RecomendacionDelCatalogo>? RecomendacionesDisponibles = null)
{
    public bool EnModoCalificaciones => Modo == ModosDeNivel.Calificaciones;
}

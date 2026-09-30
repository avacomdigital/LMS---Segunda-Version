using System.Text.Json;
using System.Text.Json.Serialization;

namespace Avacom.Lms.Core.Models;

// Contratos de /api/modo-estudio/ (MOD-008 · Modo Estudio), tal como los define
// spec-driven/04-modo-estudio/02-modelo-y-api.md. Los nombres JSON son los del backend (snake_case).
// Ningún tipo de aquí contiene una clave de corrección: el backend las elimina para todos los roles.
// La lección, la práctica y los medios reutilizan los tipos del aula (LeccionAula, ObjetoAula, FichaCurso…).

// ------------------------------------------------------------------ estado y sesión

public sealed record AlumnoEstudio(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("rotulo")] string? Rotulo);

public sealed record DispositivoEstudio(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("nombre")] string? Nombre,
    [property: JsonPropertyName("identificador_hw")] string? IdentificadorHw);

/// <summary><c>GET /estado/</c>: la pregunta del menú. <c>Disponible</c> sólo si el aparato es del alumno y se puede usar (008-01).</summary>
public sealed record EstadoEstudio(
    [property: JsonPropertyName("disponible")] bool Disponible,
    [property: JsonPropertyName("motivo")] string? Motivo,
    [property: JsonPropertyName("perfil")] string? Perfil,
    [property: JsonPropertyName("alumno")] AlumnoEstudio? Alumno,
    [property: JsonPropertyName("dispositivo")] DispositivoEstudio? Dispositivo,
    [property: JsonPropertyName("descarga_permitida")] bool DescargaPermitida,
    [property: JsonPropertyName("servidor_en")] long ServidorEn,
    [property: JsonPropertyName("dueno")] AlumnoEstudio? Dueno = null)
{
    public static readonly EstadoEstudio NoDisponible = new(false, "sin_conexion", null, null, null, false, 0);
}

/// <summary>Un grupo de la pantalla «¿Quién eres?»: quienes tienen lecciones asignadas y, dentro, los nombres que se pueden elegir.</summary>
public sealed record GrupoParaElegir(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("codigo")] string? Codigo,
    [property: JsonPropertyName("nombre")] string? Nombre,
    [property: JsonPropertyName("alumnos")] IReadOnlyList<AlumnoDeGrupo> Alumnos);

/// <summary>
/// <c>GET /estudiantes/</c>: los nombres entre los que el alumno se elige (D-15). El LMS es offline y no hay sistema central que verifique quién es
/// quién: la persona dice su nombre y ya. <c>Dueno</c> es a quién está asignada la tableta, si lo está (se ofrece primero, pero no obliga).
/// </summary>
public sealed record EstudiantesEstudio(
    [property: JsonPropertyName("disponible")] bool Disponible,
    [property: JsonPropertyName("motivo")] string? Motivo,
    [property: JsonPropertyName("grupos")] IReadOnlyList<GrupoParaElegir> Grupos,
    [property: JsonPropertyName("dueno")] AlumnoEstudio? Dueno,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

public sealed record SesionEstudio(
    [property: JsonPropertyName("sesion_id")] string SesionId,
    [property: JsonPropertyName("alumno")] AlumnoEstudio Alumno,
    [property: JsonPropertyName("dispositivo")] DispositivoEstudio? Dispositivo,
    [property: JsonPropertyName("perfil")] string? Perfil,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

// ----------------------------------------------------------------- asignación y tarea

public sealed record UltimoBloque(
    [property: JsonPropertyName("ref")] string Ref,
    [property: JsonPropertyName("indice")] int Indice,
    [property: JsonPropertyName("titulo")] string? Titulo,
    [property: JsonPropertyName("tipo")] string? Tipo,
    [property: JsonPropertyName("posicion_seg")] int? PosicionSeg);

/// <summary>El estado de la tarea del alumno. <c>Vencida</c> es derivada: la fecha pasó y no está completada.</summary>
public sealed record TareaEstudio(
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("vencida")] bool Vencida,
    [property: JsonPropertyName("fuera_de_plazo")] bool FueraDePlazo,
    [property: JsonPropertyName("avance_pct")] double AvancePct,
    [property: JsonPropertyName("bloques_total")] int BloquesTotal,
    [property: JsonPropertyName("bloques_obligatorios")] int BloquesObligatorios,
    [property: JsonPropertyName("bloques_atendidos")] int BloquesAtendidos,
    [property: JsonPropertyName("ultimo_bloque")] UltimoBloque? UltimoBloque,
    [property: JsonPropertyName("puede_reanudar")] bool PuedeReanudar,
    [property: JsonPropertyName("abierta_en")] long? AbiertaEn,
    [property: JsonPropertyName("ultimo_avance_en")] long? UltimoAvanceEn,
    [property: JsonPropertyName("completada_en")] long? CompletadaEn)
{
    public bool Completada => Estado == "completada";
    public bool EnCurso => Estado == "en_curso";
}

public sealed record BloqueEstudio(
    [property: JsonPropertyName("ref")] string Ref,
    [property: JsonPropertyName("indice")] int Indice,
    [property: JsonPropertyName("tipo")] string? Tipo,
    [property: JsonPropertyName("titulo")] string? Titulo,
    [property: JsonPropertyName("obligatorio")] bool Obligatorio,
    [property: JsonPropertyName("atendido")] bool Atendido = false,
    [property: JsonPropertyName("objeto_ref")] string? ObjetoRef = null);

public sealed record PracticaResumen(
    [property: JsonPropertyName("disponible")] bool Disponible,
    [property: JsonPropertyName("objeto_ref")] string? ObjetoRef,
    [property: JsonPropertyName("titulo")] string? Titulo,
    [property: JsonPropertyName("total_preguntas")] int TotalPreguntas,
    [property: JsonPropertyName("intentos")] int Intentos,
    [property: JsonPropertyName("mejor_correctas")] int? MejorCorrectas,
    [property: JsonPropertyName("ultima_correctas")] int? UltimaCorrectas,
    [property: JsonPropertyName("en_curso")] bool EnCurso);

/// <summary>La evaluación formal de la lección: sólo informativa. Nunca se practica aquí (BR-055).</summary>
public sealed record EvaluacionInformativa(
    [property: JsonPropertyName("objeto_ref")] string? ObjetoRef,
    [property: JsonPropertyName("titulo")] string? Titulo);

public sealed record PaqueteResumen(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("motivo")] string? Motivo,
    [property: JsonPropertyName("bytes_total")] long BytesTotal,
    [property: JsonPropertyName("bytes_estimados")] long? BytesEstimados,
    [property: JsonPropertyName("vigente_hasta")] long? VigenteHasta,
    [property: JsonPropertyName("huella")] string? Huella);

public sealed record DescargaPermitida(
    [property: JsonPropertyName("permitida")] bool Permitida,
    [property: JsonPropertyName("motivo")] string? Motivo);

public sealed record CursoDeAsignacion(
    [property: JsonPropertyName("fuente")] string? Fuente,
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("version")] string? Version,
    [property: JsonPropertyName("titulo")] string? Titulo);

/// <summary>Una asignación tal como la ve el alumno en un aparato concreto (§4.2 del contrato).</summary>
public sealed record AsignacionAlumno(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("consigna")] string? Consigna,
    [property: JsonPropertyName("descripcion")] string? Descripcion,
    [property: JsonPropertyName("asignatura")] string? Asignatura,
    [property: JsonPropertyName("unidad")] string? Unidad,
    [property: JsonPropertyName("curso")] CursoDeAsignacion? Curso,
    [property: JsonPropertyName("leccion_ref")] string? LeccionRef,
    [property: JsonPropertyName("fecha_limite")] long? FechaLimite,
    [property: JsonPropertyName("plazo")] string? Plazo,
    [property: JsonPropertyName("gracia_ms")] long? GraciaMs,
    [property: JsonPropertyName("estado_asignacion")] string? EstadoAsignacion,
    [property: JsonPropertyName("profesor")] string? Profesor,
    [property: JsonPropertyName("asignada_en")] long? AsignadaEn,
    [property: JsonPropertyName("tarea")] TareaEstudio? Tarea,
    [property: JsonPropertyName("practica")] PracticaResumen? Practica,
    [property: JsonPropertyName("evaluacion")] EvaluacionInformativa? Evaluacion,
    [property: JsonPropertyName("paquete")] PaqueteResumen? Paquete,
    [property: JsonPropertyName("descarga")] DescargaPermitida? Descarga,
    [property: JsonPropertyName("bloques")] IReadOnlyList<BloqueEstudio>? Bloques)
{
    /// <summary>Verdadero cuando el profesor ya la cerró: se puede leer, no registrar avance.</summary>
    public bool Cerrada => EstadoAsignacion == "cerrada";
}

public sealed record ResumenEstudio(
    [property: JsonPropertyName("pendientes")] int Pendientes,
    [property: JsonPropertyName("descargadas")] int Descargadas,
    [property: JsonPropertyName("completadas")] int Completadas);

public sealed record AsignacionesEstudio(
    [property: JsonPropertyName("alumno")] AlumnoEstudio? Alumno,
    [property: JsonPropertyName("asignaciones")] IReadOnlyList<AsignacionAlumno> Asignaciones,
    [property: JsonPropertyName("resumen")] ResumenEstudio? Resumen,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

// ------------------------------------------------------------------------ la lección

public sealed record ReanudarEstudio(
    [property: JsonPropertyName("bloque_ref")] string? BloqueRef,
    [property: JsonPropertyName("indice")] int? Indice,
    [property: JsonPropertyName("posicion_seg")] int? PosicionSeg,
    [property: JsonPropertyName("puede")] bool Puede);

/// <summary><c>GET /lecciones/{id}/</c>: la lección sin claves, con su estructura de bloques y desde dónde reanudar.</summary>
public sealed record LeccionEstudio(
    [property: JsonPropertyName("asignacion")] AsignacionAlumno Asignacion,
    [property: JsonPropertyName("curso")] FichaCurso? Curso,
    [property: JsonPropertyName("leccion")] LeccionAula Leccion,
    [property: JsonPropertyName("bloques")] IReadOnlyList<BloqueEstudio> Bloques,
    [property: JsonPropertyName("reanudar")] ReanudarEstudio? Reanudar,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

public sealed record ProgresoEstudio(
    [property: JsonPropertyName("tarea")] TareaEstudio Tarea,
    [property: JsonPropertyName("aceptados")] IReadOnlyList<string>? Aceptados,
    [property: JsonPropertyName("desconocidos")] IReadOnlyList<string>? Desconocidos);

public sealed record CompletadaEstudio(
    [property: JsonPropertyName("tarea")] TareaEstudio Tarea);

// ---------------------------------------------------------------------- la práctica

public sealed record VeredictoEstudio(
    [property: JsonPropertyName("pregunta_ref")] string PreguntaRef,
    [property: JsonPropertyName("correcta")] bool? Correcta,
    [property: JsonPropertyName("puntaje")] double? Puntaje,
    [property: JsonPropertyName("puntaje_maximo")] double? PuntajeMaximo,
    [property: JsonPropertyName("pendiente")] bool Pendiente,
    [property: JsonPropertyName("retroalimentacion")] IReadOnlyList<string>? Retroalimentacion);

public sealed record RespondidaEstudio(
    [property: JsonPropertyName("respuesta")] JsonElement Respuesta,
    [property: JsonPropertyName("veredicto")] VeredictoEstudio? Veredicto);

public sealed record PracticaEstudio(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("numero")] int Numero,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("objeto_ref")] string? ObjetoRef,
    [property: JsonPropertyName("titulo")] string? Titulo,
    [property: JsonPropertyName("total_preguntas")] int TotalPreguntas,
    [property: JsonPropertyName("respondidas")] Dictionary<string, RespondidaEstudio>? Respondidas,
    [property: JsonPropertyName("aciertos")] int Aciertos,
    [property: JsonPropertyName("iniciada_en")] long IniciadaEn,
    [property: JsonPropertyName("reanudada")] bool Reanudada)
{
    public bool Terminada => Estado == "terminada";
}

/// <summary><c>POST /lecciones/{id}/practica/</c>: la práctica en curso (o la nueva) y la actividad con sus preguntas sin claves.</summary>
public sealed record PracticaAbierta(
    [property: JsonPropertyName("practica")] PracticaEstudio Practica,
    [property: JsonPropertyName("objeto")] ObjetoAula Objeto);

public sealed record RevisionPregunta(
    [property: JsonPropertyName("pregunta_ref")] string PreguntaRef,
    [property: JsonPropertyName("correcta")] bool? Correcta,
    [property: JsonPropertyName("retroalimentacion")] IReadOnlyList<string>? Retroalimentacion);

/// <summary>Lo que se le dice al alumno al terminar: «7 de 8 correctas». Nunca «nota» ni «evaluación».</summary>
public sealed record ResultadoPractica(
    [property: JsonPropertyName("correctas")] int Correctas,
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("porcentaje")] double? Porcentaje,
    [property: JsonPropertyName("mensaje")] string? Mensaje,
    [property: JsonPropertyName("sin_calificar")] int SinCalificar,
    [property: JsonPropertyName("revision")] IReadOnlyList<RevisionPregunta>? Revision);

public sealed record ResumenPractica(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("respondidas")] int Respondidas,
    [property: JsonPropertyName("aciertos")] int Aciertos,
    [property: JsonPropertyName("total_preguntas")] int TotalPreguntas,
    [property: JsonPropertyName("sin_calificar")] int SinCalificar);

public sealed record RechazoPractica(
    [property: JsonPropertyName("pregunta_ref")] string? PreguntaRef,
    [property: JsonPropertyName("motivo")] string? Motivo);

/// <summary>Respuesta de <c>POST /practicas/{id}/respuestas/</c> y de <c>…/terminar/</c> (esta última sin veredictos nuevos).</summary>
public sealed record AcusePractica(
    [property: JsonPropertyName("acuse")] bool Acuse,
    [property: JsonPropertyName("veredictos")] IReadOnlyList<VeredictoEstudio>? Veredictos,
    [property: JsonPropertyName("aceptadas")] IReadOnlyList<string>? Aceptadas,
    [property: JsonPropertyName("duplicadas")] IReadOnlyList<string>? Duplicadas,
    [property: JsonPropertyName("superadas")] IReadOnlyList<string>? Superadas,
    [property: JsonPropertyName("rechazadas")] IReadOnlyList<RechazoPractica>? Rechazadas,
    [property: JsonPropertyName("practica")] ResumenPractica? Practica,
    [property: JsonPropertyName("resultado")] ResultadoPractica? Resultado,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

/// <summary>Una respuesta de práctica capturada en la tableta. <c>Secuencia</c> es monotónica por práctica y aparato.</summary>
public sealed record RespuestaPractica(
    [property: JsonPropertyName("pregunta_ref")] string PreguntaRef,
    [property: JsonPropertyName("respuesta")] JsonElement Respuesta,
    [property: JsonPropertyName("secuencia")] int Secuencia,
    [property: JsonPropertyName("capturada_en")] long? CapturadaEn = null);

// ------------------------------------------------------------------------ el paquete

public sealed record ArchivoPaquete(
    [property: JsonPropertyName("media_ref")] string MediaRef,
    [property: JsonPropertyName("clase")] string? Clase,
    [property: JsonPropertyName("mime")] string? Mime,
    [property: JsonPropertyName("bytes")] long Bytes,
    [property: JsonPropertyName("sha256")] string? Sha256);

public sealed record ArchivoNoIncluido(
    [property: JsonPropertyName("media_ref")] string MediaRef,
    [property: JsonPropertyName("motivo")] string? Motivo);

/// <summary>El paquete de estudio de un aparato. <c>Estado</c>: solicitado · descargandose · disponible · vencido · denegado.</summary>
public sealed record PaqueteEstudio(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("asignacion_id")] string AsignacionId,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("motivo")] string? Motivo,
    [property: JsonPropertyName("curso_version")] string? CursoVersion,
    [property: JsonPropertyName("bytes_total")] long BytesTotal,
    [property: JsonPropertyName("huella")] string? Huella,
    [property: JsonPropertyName("vigente_hasta")] long? VigenteHasta,
    [property: JsonPropertyName("solicitado_en")] long? SolicitadoEn,
    [property: JsonPropertyName("disponible_en")] long? DisponibleEn,
    [property: JsonPropertyName("archivos")] IReadOnlyList<ArchivoPaquete>? Archivos,
    [property: JsonPropertyName("no_incluidos")] IReadOnlyList<ArchivoNoIncluido>? NoIncluidos,
    [property: JsonPropertyName("servidor_en")] long ServidorEn)
{
    public bool Denegado => Estado == "denegado";
    public bool Vencido => Estado == "vencido";
}

public sealed record RespuestaPaquete(
    [property: JsonPropertyName("paquete")] PaqueteEstudio Paquete);

public sealed record ListaPaquetes(
    [property: JsonPropertyName("paquetes")] IReadOnlyList<PaqueteEstudio> Paquetes);

/// <summary>
/// El manifiesto que baja el aparato. <c>Huella</c> es el SHA-256 hexadecimal del JSON canónico del manifiesto SIN el campo <c>huella</c>
/// (claves ordenadas, sin espacios, UTF-8). La lección viaja como JSON crudo: es la misma vista de aula sin claves que <see cref="LeccionAula"/>.
/// </summary>
public sealed record ManifiestoPaquete(
    [property: JsonPropertyName("paquete_id")] string PaqueteId,
    [property: JsonPropertyName("asignacion")] AsignacionAlumno? Asignacion,
    [property: JsonPropertyName("curso")] FichaCurso? Curso,
    [property: JsonPropertyName("leccion_ref")] string? LeccionRef,
    [property: JsonPropertyName("vigente_hasta")] long? VigenteHasta,
    [property: JsonPropertyName("generado_en")] long GeneradoEn,
    [property: JsonPropertyName("leccion")] JsonElement Leccion,
    [property: JsonPropertyName("archivos")] IReadOnlyList<ArchivoPaquete> Archivos,
    [property: JsonPropertyName("no_incluidos")] IReadOnlyList<ArchivoNoIncluido>? NoIncluidos,
    [property: JsonPropertyName("huella")] string Huella);

// ------------------------------------------------------------------- trabajo sin red

/// <summary>Un evento de la cola local: <c>Secuencia</c> monotónica por instalación (<c>emisor_id</c>), persistida antes de enviar.</summary>
public sealed record EventoEstudio(
    [property: JsonPropertyName("secuencia")] long Secuencia,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("ocurrido_en")] long OcurridoEn,
    [property: JsonPropertyName("ocurrido_en_tableta")] long? OcurridoEnTableta,
    [property: JsonPropertyName("carga")] JsonElement Carga);

public static class TiposEventoEstudio
{
    public const string BloqueVisto = "study.block.viewed";
    public const string RespuestaEnviada = "study.answer.submitted";
    public const string PracticaTerminada = "study.practice.finished";
    public const string LeccionCompletada = "study.lesson.completed";
}

public sealed record ResultadoEvento(
    [property: JsonPropertyName("secuencia")] long Secuencia,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("motivo")] string? Motivo,
    [property: JsonPropertyName("detalle")] JsonElement? Detalle)
{
    public bool Integrado => Estado is "integrado" or "duplicado";
}

public sealed record ResumenSync(
    [property: JsonPropertyName("integrados")] int Integrados,
    [property: JsonPropertyName("duplicados")] int Duplicados,
    [property: JsonPropertyName("rechazados")] int Rechazados,
    [property: JsonPropertyName("pendientes_decision")] int PendientesDecision);

public sealed record TareaDeAsignacion(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("tarea")] TareaEstudio? Tarea);

public sealed record VeredictoIntegrado(
    [property: JsonPropertyName("asignacion_id")] string AsignacionId,
    [property: JsonPropertyName("objeto_ref")] string? ObjetoRef,
    [property: JsonPropertyName("numero")] int Numero,
    [property: JsonPropertyName("pregunta_ref")] string PreguntaRef,
    [property: JsonPropertyName("veredicto")] VeredictoEstudio? Veredicto);

public sealed record AcuseSync(
    [property: JsonPropertyName("acuse")] bool Acuse,
    [property: JsonPropertyName("servidor_en")] long ServidorEn,
    [property: JsonPropertyName("resultados")] IReadOnlyList<ResultadoEvento> Resultados,
    [property: JsonPropertyName("resumen")] ResumenSync? Resumen,
    [property: JsonPropertyName("asignaciones")] IReadOnlyList<TareaDeAsignacion>? Asignaciones,
    [property: JsonPropertyName("veredictos")] IReadOnlyList<VeredictoIntegrado>? Veredictos);

public sealed record PendienteDeDecision(
    [property: JsonPropertyName("secuencia")] long Secuencia,
    [property: JsonPropertyName("tipo")] string? Tipo,
    [property: JsonPropertyName("asignacion_id")] string? AsignacionId,
    [property: JsonPropertyName("motivo")] string? Motivo);

public sealed record ConteosSync(
    [property: JsonPropertyName("synced")] int Synced,
    [property: JsonPropertyName("rejected")] int Rejected,
    [property: JsonPropertyName("conflict")] int Conflict);

public sealed record EstadoSync(
    [property: JsonPropertyName("emisor_id")] string? EmisorId,
    [property: JsonPropertyName("ultima_secuencia")] long UltimaSecuencia,
    [property: JsonPropertyName("conteos")] ConteosSync? Conteos,
    [property: JsonPropertyName("pendientes_decision")] IReadOnlyList<PendienteDeDecision>? PendientesDecision);

// -------------------------------------------------------------------- profesor (OPS)

public sealed record AlumnoDeGrupo(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("rotulo")] string? Rotulo);

public sealed record GrupoDocente(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("codigo")] string? Codigo,
    [property: JsonPropertyName("nombre")] string? Nombre,
    [property: JsonPropertyName("nivel_clave")] string? NivelClave,
    [property: JsonPropertyName("alumnos")] IReadOnlyList<AlumnoDeGrupo> Alumnos);

public sealed record GruposDocente(
    [property: JsonPropertyName("instalado")] bool Instalado,
    [property: JsonPropertyName("grupos")] IReadOnlyList<GrupoDocente> Grupos);

public sealed record PracticaDeAlumno(
    [property: JsonPropertyName("intentos")] int Intentos,
    [property: JsonPropertyName("mejor_correctas")] int? MejorCorrectas,
    [property: JsonPropertyName("total")] int? Total);

public sealed record PaqueteDeAlumno(
    [property: JsonPropertyName("estado")] string? Estado);

public sealed record DispositivoDeAlumno(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("nombre")] string? Nombre,
    [property: JsonPropertyName("perfil")] string? Perfil);

/// <summary>Un envío que llegó fuera de la ventana de gracia y espera al profesor (BR-074): nunca se descarta en silencio.</summary>
public sealed record DecisionPendiente(
    [property: JsonPropertyName("emisor_id")] string EmisorId,
    [property: JsonPropertyName("secuencia")] long Secuencia,
    [property: JsonPropertyName("tipo")] string? Tipo,
    [property: JsonPropertyName("motivo")] string? Motivo,
    [property: JsonPropertyName("ocurrido_en")] long? OcurridoEn,
    [property: JsonPropertyName("recibido_en")] long? RecibidoEn);

/// <summary>Una fila de «quién completó» (CAP-051): un destinatario con o sin tarea.</summary>
public sealed record FilaDeAlumno(
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("rotulo")] string? Rotulo,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("vencida")] bool Vencida,
    [property: JsonPropertyName("fuera_de_plazo")] bool FueraDePlazo,
    [property: JsonPropertyName("avance_pct")] double AvancePct,
    [property: JsonPropertyName("bloques_atendidos")] int BloquesAtendidos,
    [property: JsonPropertyName("bloques_total")] int BloquesTotal,
    [property: JsonPropertyName("ultimo_avance_en")] long? UltimoAvanceEn,
    [property: JsonPropertyName("completada_en")] long? CompletadaEn,
    [property: JsonPropertyName("practica")] PracticaDeAlumno? Practica,
    [property: JsonPropertyName("paquete")] PaqueteDeAlumno? Paquete,
    [property: JsonPropertyName("dispositivo")] DispositivoDeAlumno? Dispositivo,
    [property: JsonPropertyName("pendientes_decision")] int PendientesDecision,
    [property: JsonPropertyName("decisiones")] IReadOnlyList<DecisionPendiente>? Decisiones = null);

/// <summary>Una asignación vista por el profesor, con sus totales (lista) y, en el detalle, la tabla de alumnos.</summary>
public sealed record AsignacionDocente(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("consigna")] string? Consigna,
    [property: JsonPropertyName("asignatura")] string? Asignatura,
    [property: JsonPropertyName("unidad")] string? Unidad,
    [property: JsonPropertyName("grupo_id")] string? GrupoId,
    [property: JsonPropertyName("grupo_rotulo")] string? GrupoRotulo,
    [property: JsonPropertyName("curso")] CursoDeAsignacion? Curso,
    [property: JsonPropertyName("leccion_ref")] string? LeccionRef,
    [property: JsonPropertyName("fecha_limite")] long? FechaLimite,
    [property: JsonPropertyName("plazo")] string? Plazo,
    [property: JsonPropertyName("gracia_ms")] long? GraciaMs,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("alcance")] string? Alcance,
    [property: JsonPropertyName("paquete_permitido")] bool PaquetePermitido,
    [property: JsonPropertyName("destinatarios_total")] int DestinatariosTotal,
    [property: JsonPropertyName("completaron")] int Completaron,
    [property: JsonPropertyName("en_curso")] int EnCurso,
    [property: JsonPropertyName("pendientes")] int Pendientes,
    [property: JsonPropertyName("fuera_de_plazo")] int FueraDePlazo,
    [property: JsonPropertyName("pendientes_decision")] int PendientesDecision,
    [property: JsonPropertyName("creada_en")] long CreadaEn,
    [property: JsonPropertyName("alumnos")] IReadOnlyList<FilaDeAlumno>? Alumnos = null)
{
    public bool Cerrada => Estado == "cerrada";
}

public sealed record ListaAsignacionesDocente(
    [property: JsonPropertyName("asignaciones")] IReadOnlyList<AsignacionDocente> Asignaciones);

/// <summary>Lo que OPS manda para asignar una lección a un grupo o a alumnos concretos. La fecha límite y la consigna son opcionales.</summary>
public sealed record NuevaAsignacion(
    string Alcance, string? GrupoId, IReadOnlyList<string>? Alumnos, string CursoRef, string? Fuente, string LeccionRef,
    string? Titulo = null, string? Consigna = null, long? FechaLimite = null, string? Plazo = null, int? GraciaMin = null,
    bool PaquetePermitido = true);

public sealed record CambiosAsignacion(
    long? FechaLimite = null, bool QuitarFecha = false, string? Plazo = null, int? GraciaMin = null, string? Titulo = null,
    string? Consigna = null, bool? PaquetePermitido = null);

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Avacom.Lms.Core.Gradebook;

// Contratos de /api/gradebook/ (MOD-011 · Gradebook), tal como los define spec-driven/12-gradebook/02-api.md. Los nombres JSON son los del backend (snake_case).
// Las puntuaciones internas viajan como números de a lo sumo dos decimales (escala 0–100): se leen como decimal, nunca como double, para que 70,10 sea 70,10.
// Lo que el alumno ve (MisResultados) NO lleva el resultado interno ni una nota sin publicar: el backend no se los manda.

// ------------------------------------------------------------------------------------------------ catálogos

/// <summary>Los estados guardados de una calificación (revisada → definitiva; reabierta; anulada).</summary>
public static class EstadosDeCalificacion
{
    public const string Revisada = "revisada";
    public const string Definitiva = "definitiva";
    public const string Reabierta = "reabierta";
    public const string Anulada = "anulada";

    /// <summary>Las que cuentan para el resultado aplicable y los agregados.</summary>
    public static bool Cuenta(string? estado) => estado is Revisada or Definitiva;
}

/// <summary>Cómo ve el docente el estado de un resultado: lo guardado más lo que se deduce del intento. Una actividad pendiente NO es un cero.</summary>
public static class EstadosDeResultado
{
    public const string Pendiente = "pendiente";
    public const string Provisional = "provisional";
    public const string Revisado = "revisado";
    public const string Definitivo = "definitivo";
    public const string Reabierto = "reabierto";
    public const string Anulado = "anulado";
    public const string SinRegistro = "sin_registro";
}

public static class ModosDeNivel
{
    public const string Simple = "simple";
    public const string Calificaciones = "calificaciones";
}

public static class EstadosSimples
{
    public const string NoIniciado = "no_iniciado";
    public const string EnProgreso = "en_progreso";
    public const string Completado = "completado";
}

public static class NivelesEducativos
{
    public static readonly IReadOnlyList<string> Todos = ["preescolar", "primaria", "secundaria", "bachillerato", "preuniversitario"];
}

// ------------------------------------------------------------------------------------------- la presentación

/// <summary>La presentación de una calificación con una escala: el resultado interno, lo presentado, el desempeño y el criterio de aprobación, cuatro cosas SEPARADAS.</summary>
public sealed record Presentacion(
    [property: JsonPropertyName("interno")] decimal Interno,
    [property: JsonPropertyName("presentada")] ValorPresentado Presentada,
    [property: JsonPropertyName("desempeno")] Desempeno Desempeno,
    [property: JsonPropertyName("aprobacion")] CriterioDeAprobacion Aprobacion,
    [property: JsonPropertyName("escala")] EscalaDePresentacion? Escala = null,
    [property: JsonPropertyName("provisional")] bool Provisional = false);

public sealed record ValorPresentado(
    [property: JsonPropertyName("valor")] decimal? Valor,
    [property: JsonPropertyName("etiqueta")] string Etiqueta,
    [property: JsonPropertyName("clave")] string Clave);

public sealed record Desempeno(
    [property: JsonPropertyName("nivel")] string? Nivel,
    [property: JsonPropertyName("clave")] string? Clave,
    [property: JsonPropertyName("tramo")] int? Tramo,
    [property: JsonPropertyName("origen")] string? Origen = null)
{
    /// <summary>El profesor fijó este nivel con su criterio pedagógico (no salió sólo de la cuenta).</summary>
    public bool ValoradoPorElDocente => Origen == "docente";
}

/// <summary>El CRITERIO de aprobación de la escala; aprobar o promover es una decisión institucional y humana que el libro no toma.</summary>
public sealed record CriterioDeAprobacion([property: JsonPropertyName("cumple_criterio")] bool? CumpleCriterio);

public sealed record EscalaDePresentacion(
    [property: JsonPropertyName("escala_id")] string EscalaId,
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("version_id")] string VersionId,
    [property: JsonPropertyName("numero")] int Numero,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("huella")] string? Huella = null);

// ------------------------------------------------------------------------------------------ la calificación

public sealed record Calificacion(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("intento_id")] string IntentoId,
    [property: JsonPropertyName("asignacion_id")] string AsignacionId,
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("grupo_id")] string GrupoId,
    [property: JsonPropertyName("nivel_clave")] string NivelClave,
    [property: JsonPropertyName("periodo")] string Periodo,
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("numero_intento")] int NumeroIntento,
    [property: JsonPropertyName("puntaje_original")] decimal PuntajeOriginal,
    [property: JsonPropertyName("puntaje_efectivo")] decimal PuntajeEfectivo,
    [property: JsonPropertyName("ajustada")] bool Ajustada,
    [property: JsonPropertyName("regla_puntuacion")] string ReglaPuntuacion,
    [property: JsonPropertyName("origen")] string Origen,
    [property: JsonPropertyName("evaluador_id")] string EvaluadorId,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("version")] int Version,
    [property: JsonPropertyName("publicada")] bool Publicada,
    [property: JsonPropertyName("registrada_en")] long RegistradaEn,
    [property: JsonPropertyName("actualizada_en")] long ActualizadaEn,
    [property: JsonPropertyName("aciertos")] int? Aciertos = null,
    [property: JsonPropertyName("preguntas")] int? Preguntas = null,
    [property: JsonPropertyName("publicada_en")] long? PublicadaEn = null,
    [property: JsonPropertyName("publicada_por")] string? PublicadaPor = null,
    [property: JsonPropertyName("desempeno_docente")] string? DesempenoDocente = null,
    [property: JsonPropertyName("desempeno_motivo")] string? DesempenoMotivo = null,
    [property: JsonPropertyName("retroalimentacion")] Dictionary<string, string>? Retroalimentacion = null,
    [property: JsonPropertyName("adaptacion")] string? Adaptacion = null,
    [property: JsonPropertyName("presentacion")] Presentacion? Presentacion = null,
    [property: JsonPropertyName("desfase_con_evaluacion")] bool DesfaseConEvaluacion = false)
{
    public bool EsEditable => EstadosDeCalificacion.Cuenta(Estado);
    public bool EstaReabierta => Estado == EstadosDeCalificacion.Reabierta;
}

/// <summary>Una fila del historial de una calificación: cada cambio con su valor anterior, el nuevo, el motivo, quién y cuándo (reloj del NODO).</summary>
public sealed record VersionDeCalificacion(
    [property: JsonPropertyName("numero")] int Numero,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("puntaje_anterior")] decimal? PuntajeAnterior,
    [property: JsonPropertyName("puntaje_nuevo")] decimal? PuntajeNuevo,
    [property: JsonPropertyName("estado_anterior")] string? EstadoAnterior,
    [property: JsonPropertyName("estado_nuevo")] string? EstadoNuevo,
    [property: JsonPropertyName("motivo")] string? Motivo,
    [property: JsonPropertyName("actor_id")] string ActorId,
    [property: JsonPropertyName("en")] long En,
    [property: JsonPropertyName("solicitud_id")] string? SolicitudId);

/// <summary>Lo que responde cualquier cambio a una calificación (ajustar, reabrir, valorar, retroalimentar, publicar, retirar): la calificación nueva y su historial.</summary>
public sealed record CambioDeCalificacion(
    [property: JsonPropertyName("calificacion")] Calificacion Calificacion,
    [property: JsonPropertyName("historial")] IReadOnlyList<VersionDeCalificacion> Historial,
    [property: JsonPropertyName("reintento")] bool Reintento,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

public sealed record RevisionRegistrada(
    [property: JsonPropertyName("pregunta_ref")] string PreguntaRef,
    [property: JsonPropertyName("numero")] int Numero,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("puntaje")] decimal Puntaje,
    [property: JsonPropertyName("puntaje_maximo")] decimal? PuntajeMaximo,
    [property: JsonPropertyName("criterios")] JsonElement? Criterios,
    [property: JsonPropertyName("comentario")] string? Comentario,
    [property: JsonPropertyName("revisor_id")] string RevisorId,
    [property: JsonPropertyName("revisada_en")] long RevisadaEn);

public sealed record IntentoResumen(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("numero")] int Numero,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("porcentaje")] double? Porcentaje,
    [property: JsonPropertyName("calificado_por")] string? CalificadoPor,
    [property: JsonPropertyName("entregado_en")] long? EntregadoEn);

public sealed record DetalleDeCalificacion(
    [property: JsonPropertyName("calificacion")] Calificacion Calificacion,
    [property: JsonPropertyName("historial")] IReadOnlyList<VersionDeCalificacion> Historial,
    [property: JsonPropertyName("revisiones")] IReadOnlyList<RevisionRegistrada> Revisiones,
    [property: JsonPropertyName("intento")] IntentoResumen? Intento,
    [property: JsonPropertyName("servidor_en")] long ServidorEn,
    [property: JsonPropertyName("sistema")] EscalaResumen? Sistema = null);

// ------------------------------------------------------------------------------------------------- el libro

public sealed record GrupoDelLibro(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("periodo")] string Periodo,
    [property: JsonPropertyName("nivel_clave")] string? NivelClave);

public sealed record ColumnaDelLibro(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("tipo_evaluacion")] string TipoEvaluacion,
    [property: JsonPropertyName("afecta_oficial")] bool AfectaOficial,
    [property: JsonPropertyName("por_revisar")] int PorRevisar,
    [property: JsonPropertyName("curso_rotulo")] string? CursoRotulo = null,
    [property: JsonPropertyName("resultados")] string? Resultados = null);

public sealed record IntentosDeCelda(
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("registrados")] int Registrados);

/// <summary>Un alumno en una evaluación. Sin calificación, <see cref="PuntajeEfectivo"/> es nulo: lo pendiente nunca se pinta como cero.</summary>
public sealed record CeldaDelLibro(
    [property: JsonPropertyName("estado_simple")] string EstadoSimple,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("publicada")] bool Publicada,
    [property: JsonPropertyName("ajustada")] bool Ajustada,
    [property: JsonPropertyName("intentos")] IntentosDeCelda Intentos,
    [property: JsonPropertyName("calificacion_id")] string? CalificacionId = null,
    [property: JsonPropertyName("version")] int? Version = null,
    [property: JsonPropertyName("puntaje_efectivo")] decimal? PuntajeEfectivo = null,
    [property: JsonPropertyName("puntaje_original")] decimal? PuntajeOriginal = null,
    [property: JsonPropertyName("presentacion")] Presentacion? Presentacion = null,
    [property: JsonPropertyName("politica_intentos")] string? PoliticaIntentos = null);

public sealed record AgregadoDeCurso(
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("periodo")] string Periodo,
    [property: JsonPropertyName("calificaciones")] int Calificaciones,
    [property: JsonPropertyName("promedio_simple")] decimal? PromedioSimple,
    [property: JsonPropertyName("pendientes")] int Pendientes,
    [property: JsonPropertyName("provisionales")] int Provisionales,
    [property: JsonPropertyName("publicadas")] int Publicadas,
    [property: JsonPropertyName("oficial")] bool Oficial = false,
    [property: JsonPropertyName("ponderado")] bool Ponderado = false);

public sealed record FilaDelLibro(
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("rotulo")] string Rotulo,
    [property: JsonPropertyName("celdas")] Dictionary<string, CeldaDelLibro> Celdas,
    [property: JsonPropertyName("agregados")] IReadOnlyList<AgregadoDeCurso> Agregados);

public sealed record TotalesDelLibro(
    [property: JsonPropertyName("alumnos")] int Alumnos,
    [property: JsonPropertyName("asignaciones")] int Asignaciones,
    [property: JsonPropertyName("pendientes")] int Pendientes,
    [property: JsonPropertyName("por_revisar")] int PorRevisar,
    [property: JsonPropertyName("sin_publicar")] int SinPublicar);

public sealed record LibroDelGrupo(
    [property: JsonPropertyName("grupo")] GrupoDelLibro Grupo,
    [property: JsonPropertyName("modo")] string Modo,
    [property: JsonPropertyName("escala")] EscalaResumen? Escala,
    [property: JsonPropertyName("politica_intentos")] string PoliticaIntentos,
    [property: JsonPropertyName("asignaciones")] IReadOnlyList<ColumnaDelLibro> Asignaciones,
    [property: JsonPropertyName("alumnos")] IReadOnlyList<FilaDelLibro> Alumnos,
    [property: JsonPropertyName("totales")] TotalesDelLibro Totales,
    [property: JsonPropertyName("servidor_en")] long ServidorEn)
{
    public bool EnModoCalificaciones => Modo == ModosDeNivel.Calificaciones;
}

/// <summary>
/// El sistema de calificación de un nivel: quién es (con su versión) y lo que hace falta para leer una nota suya — de qué país, su rango, desde dónde se aprueba y sus tramos.
/// Lo calcula el nodo; los campos de después de <see cref="Tipo"/> son opcionales porque una calificación ya publicada puede venir de una versión que ya no se lee.
/// </summary>
public sealed record EscalaResumen(
    [property: JsonPropertyName("escala_id")] string EscalaId,
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("version_id")] string VersionId,
    [property: JsonPropertyName("numero")] int Numero,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("pais")] string? Pais = null,
    [property: JsonPropertyName("jurisdiccion")] string? Jurisdiccion = null,
    [property: JsonPropertyName("valor_min")] decimal? ValorMin = null,
    [property: JsonPropertyName("valor_max")] decimal? ValorMax = null,
    [property: JsonPropertyName("aprobacion_minima")] decimal? AprobacionMinima = null,
    [property: JsonPropertyName("aprueba_desde")] string? ApruebaDesde = null,
    [property: JsonPropertyName("tramos")] IReadOnlyList<TramoResumen>? Tramos = null);

/// <summary>Un nivel de desempeño del sistema (un tramo): su clave corta («SU»), su nombre («Suficiente») y si con él se aprueba (nulo: el sistema no lo dice).</summary>
public sealed record TramoResumen(
    [property: JsonPropertyName("clave")] string Clave,
    [property: JsonPropertyName("etiqueta")] string Etiqueta,
    [property: JsonPropertyName("aprueba")] bool? Aprueba);

// ------------------------------------------------------------------------------------ la revisión docente

public sealed record ItemDeBandeja(
    [property: JsonPropertyName("intento_id")] string IntentoId,
    [property: JsonPropertyName("asignacion_id")] string AsignacionId,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("grupo_id")] string GrupoId,
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("alumno_rotulo")] string AlumnoRotulo,
    [property: JsonPropertyName("estado_intento")] string EstadoIntento,
    [property: JsonPropertyName("motivo")] string Motivo,
    [property: JsonPropertyName("pendientes")] IReadOnlyList<string> Pendientes,
    [property: JsonPropertyName("n_pendientes")] int NPendientes,
    [property: JsonPropertyName("curso_rotulo")] string? CursoRotulo = null,
    [property: JsonPropertyName("grupo_rotulo")] string? GrupoRotulo = null,
    [property: JsonPropertyName("porcentaje_provisional")] decimal? PorcentajeProvisional = null,
    [property: JsonPropertyName("entregado_en")] long? EntregadoEn = null,
    [property: JsonPropertyName("calificacion_id")] string? CalificacionId = null,
    [property: JsonPropertyName("version")] int? Version = null)
{
    public bool EsReapertura => Motivo == "reabierta";
}

public sealed record BandejaDeRevision(
    [property: JsonPropertyName("items")] IReadOnlyList<ItemDeBandeja> Items,
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("pendientes")] int Pendientes,
    [property: JsonPropertyName("reabiertas")] int Reabiertas,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

public sealed record CriterioDeRubrica(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("criterio")] string Criterio,
    [property: JsonPropertyName("puntos_max")] decimal PuntosMax);

public sealed record RubricaDePregunta(
    [property: JsonPropertyName("criterios")] IReadOnlyList<CriterioDeRubrica> Criterios,
    [property: JsonPropertyName("respuesta_modelo")] string? RespuestaModelo,
    [property: JsonPropertyName("puntos")] decimal? Puntos,
    [property: JsonPropertyName("formato")] string? Formato);

public sealed record EvidenciaDeRespuesta(
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("ref")] string Ref);

public sealed record ReactivoParaRevisar(
    [property: JsonPropertyName("pregunta_ref")] string PreguntaRef,
    [property: JsonPropertyName("tipo")] string? Tipo,
    [property: JsonPropertyName("forma")] string Forma,
    [property: JsonPropertyName("requiere_revision")] bool RequiereRevision,
    [property: JsonPropertyName("pendiente")] bool Pendiente,
    [property: JsonPropertyName("revisada")] bool Revisada,
    [property: JsonPropertyName("enunciado")] string? Enunciado = null,
    [property: JsonPropertyName("puntaje_maximo")] decimal? PuntajeMaximo = null,
    [property: JsonPropertyName("respuesta")] JsonElement? Respuesta = null,
    [property: JsonPropertyName("respondida")] bool Respondida = false,
    [property: JsonPropertyName("evidencias")] IReadOnlyList<EvidenciaDeRespuesta>? Evidencias = null,
    [property: JsonPropertyName("puntaje_actual")] decimal? PuntajeActual = null,
    [property: JsonPropertyName("comentario")] string? Comentario = null,
    [property: JsonPropertyName("revisada_por")] string? RevisadaPor = null,
    [property: JsonPropertyName("revisada_en")] long? RevisadaEn = null,
    [property: JsonPropertyName("rubrica")] RubricaDePregunta? Rubrica = null);

public sealed record IntentoEnRevision(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("asignacion_id")] string AsignacionId,
    [property: JsonPropertyName("titulo")] string? Titulo,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("alumno_rotulo")] string? AlumnoRotulo,
    [property: JsonPropertyName("pendientes")] IReadOnlyList<string> Pendientes,
    [property: JsonPropertyName("reabierta")] bool Reabierta,
    [property: JsonPropertyName("porcentaje_provisional")] decimal? PorcentajeProvisional = null,
    [property: JsonPropertyName("calificacion_id")] string? CalificacionId = null,
    [property: JsonPropertyName("calificacion_version")] int? CalificacionVersion = null);

public sealed record RevisionParaDocente(
    [property: JsonPropertyName("intento")] IntentoEnRevision Intento,
    [property: JsonPropertyName("puede_confirmar")] bool PuedeConfirmar,
    [property: JsonPropertyName("filas")] IReadOnlyList<ReactivoParaRevisar> Filas,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

/// <summary>Un criterio de rúbrica ya puntuado por el profesor.</summary>
public sealed record CriterioPuntuado(
    [property: JsonPropertyName("criterio_id")] string CriterioId,
    [property: JsonPropertyName("puntos")] decimal Puntos);

public sealed record RevisionAplicada(
    [property: JsonPropertyName("intento_id")] string IntentoId,
    [property: JsonPropertyName("pregunta_ref")] string PreguntaRef,
    [property: JsonPropertyName("numero")] int Numero,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("puntaje")] decimal Puntaje,
    [property: JsonPropertyName("pendientes")] IReadOnlyList<string> Pendientes,
    [property: JsonPropertyName("listo_para_confirmar")] bool ListoParaConfirmar,
    [property: JsonPropertyName("reintento")] bool Reintento,
    [property: JsonPropertyName("puntaje_maximo")] decimal? PuntajeMaximo = null,
    [property: JsonPropertyName("comentario")] string? Comentario = null,
    [property: JsonPropertyName("porcentaje_provisional")] decimal? PorcentajeProvisional = null);

public sealed record RevisionConfirmada(
    [property: JsonPropertyName("intento_id")] string IntentoId,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("resultado")] string Resultado,
    [property: JsonPropertyName("registrada")] bool Registrada,
    [property: JsonPropertyName("calificacion")] Calificacion? Calificacion = null,
    // Al confirmar la recalificación de una calificación reabierta: si había un ajuste del profesor y recalificar cambió la puntuación, el ajuste dejó de tener base y se descartó.
    [property: JsonPropertyName("ajuste_descartado")] bool AjusteDescartado = false,
    [property: JsonPropertyName("ajuste_anterior")] decimal? AjusteAnterior = null);

// -------------------------------------------------------------------------------------- la configuración

public sealed record NivelConfigurado(
    [property: JsonPropertyName("nivel_clave")] string NivelClave,
    [property: JsonPropertyName("modo")] string Modo,
    [property: JsonPropertyName("por_defecto")] bool PorDefecto,
    [property: JsonPropertyName("version")] int Version,
    [property: JsonPropertyName("escala")] EscalaResumen? Escala = null)
{
    public bool EnModoCalificaciones => Modo == ModosDeNivel.Calificaciones;
}

public sealed record PoliticaInstitucional(
    [property: JsonPropertyName("politica_intentos")] string PoliticaIntentos,
    [property: JsonPropertyName("politica_provisional")] bool PoliticaProvisional,
    [property: JsonPropertyName("ponderaciones_aplicadas")] bool PonderacionesAplicadas,
    [property: JsonPropertyName("version")] int Version,
    [property: JsonPropertyName("pais")] string? Pais = null,
    [property: JsonPropertyName("jurisdiccion")] string? Jurisdiccion = null,
    [property: JsonPropertyName("institucion")] string? Institucion = null);

/// <summary>Lo que responde configurar la política: la política vigente y si cambió (repetir la misma no cambia nada ni deja evento).</summary>
public sealed record PoliticaConfigurada(
    [property: JsonPropertyName("politica")] PoliticaInstitucional Politica,
    [property: JsonPropertyName("cambiado")] bool Cambiado = true);

public sealed record EscalaAdoptada(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("activa")] bool Activa,
    [property: JsonPropertyName("pais")] string? Pais = null,
    [property: JsonPropertyName("jurisdiccion")] string? Jurisdiccion = null,
    [property: JsonPropertyName("plantilla_origen")] string? PlantillaOrigen = null,
    [property: JsonPropertyName("versiones")] IReadOnlyList<VersionDeEscala>? Versiones = null);

public sealed record VersionDeEscala(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("numero")] int Numero,
    [property: JsonPropertyName("huella")] string Huella,
    [property: JsonPropertyName("definicion")] JsonElement? Definicion = null,
    [property: JsonPropertyName("nota")] string? Nota = null);

public sealed record ConfiguracionAcademica(
    [property: JsonPropertyName("niveles")] IReadOnlyList<NivelConfigurado> Niveles,
    [property: JsonPropertyName("politica")] PoliticaInstitucional Politica,
    [property: JsonPropertyName("escalas")] IReadOnlyList<EscalaAdoptada> Escalas,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

public sealed record PlantillaDeEscala(
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("advertencia")] string Advertencia,
    [property: JsonPropertyName("pais")] string? Pais = null,
    [property: JsonPropertyName("jurisdiccion")] string? Jurisdiccion = null,
    [property: JsonPropertyName("niveles")] IReadOnlyList<string>? Niveles = null,
    [property: JsonPropertyName("referencia")] string? Referencia = null,
    [property: JsonPropertyName("sistema")] EscalaResumen? Sistema = null);

public sealed record PlantillasDeEscalas(
    [property: JsonPropertyName("plantillas")] IReadOnlyList<PlantillaDeEscala> Plantillas,
    [property: JsonPropertyName("advertencia")] string Advertencia);

public sealed record ConversionDeMuestra(
    [property: JsonPropertyName("interno")] decimal Interno,
    [property: JsonPropertyName("presentada")] ValorPresentado Presentada,
    [property: JsonPropertyName("desempeno")] Desempeno Desempeno,
    [property: JsonPropertyName("aprobacion")] CriterioDeAprobacion Aprobacion);

public sealed record VistaPreviaDeEscala(
    [property: JsonPropertyName("conversiones")] IReadOnlyList<ConversionDeMuestra> Conversiones);

/// <summary>Lo que responde «validar» un cambio de modo: si se puede, qué lo impide y qué advertencias hay. No cambia nada.</summary>
public sealed record ValidacionDeNivel(
    [property: JsonPropertyName("permitido")] bool Permitido,
    [property: JsonPropertyName("bloqueos")] IReadOnlyList<string> Bloqueos,
    [property: JsonPropertyName("advertencias")] IReadOnlyList<string> Advertencias,
    [property: JsonPropertyName("en_curso")] int EnCurso,
    [property: JsonPropertyName("de")] string De,
    [property: JsonPropertyName("a")] string A);

public sealed record NivelCambiado(
    [property: JsonPropertyName("cambiado")] bool Cambiado,
    [property: JsonPropertyName("nivel")] NivelConfigurado Nivel,
    [property: JsonPropertyName("advertencias")] IReadOnlyList<string> Advertencias);

// --------------------------------------------------------------------------------------- el alumno

/// <summary>
/// Lo que ve el ALUMNO de una evaluación. En modo simple sólo hay un estado, un símbolo y, si el profesor liberó el resultado, símbolos de aciertos: ningún número.
/// En modo calificaciones, una nota sólo existe cuando se publicó (<see cref="Calificacion"/>); antes, sólo el estado de su entrega (<see cref="Estado"/>).
/// </summary>
public sealed record ResultadoDelAlumno(
    [property: JsonPropertyName("asignacion_id")] string AsignacionId,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("estado_simple")] string EstadoSimple,
    [property: JsonPropertyName("simbolo")] string Simbolo,
    [property: JsonPropertyName("modo")] string Modo,
    [property: JsonPropertyName("curso_rotulo")] string? CursoRotulo = null,
    [property: JsonPropertyName("estado")] string? Estado = null,
    [property: JsonPropertyName("calificacion")] NotaPublicada? Calificacion = null,
    [property: JsonPropertyName("aciertos")] AciertosEnSimbolos? Aciertos = null)
{
    public bool EsSimple => Modo == ModosDeNivel.Simple;
    public bool TieneNota => Calificacion is not null;
}

/// <summary>Lo mínimo de <c>GET /gradebook/asignaciones/{id}/</c> para pintar la nota de cada intento de una evaluación con la escala del nivel.</summary>
public sealed record NotasDeAsignacion(
    [property: JsonPropertyName("alumnos")] IReadOnlyList<NotasDeAlumno> Alumnos)
{
    /// <summary>La presentación de la calificación de un intento (null si no hay: modo simple, sin registrar o anulada).</summary>
    public Presentacion? DeIntento(string? intentoId) =>
        string.IsNullOrEmpty(intentoId) ? null : Alumnos.SelectMany(a => a.Intentos).FirstOrDefault(i => i.Id == intentoId)?.Calificacion?.Presentacion;
}

public sealed record NotasDeAlumno(
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("intentos")] IReadOnlyList<NotaDeIntento> Intentos);

public sealed record NotaDeIntento(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("calificacion")] CalificacionDeIntento? Calificacion = null);

public sealed record CalificacionDeIntento(
    [property: JsonPropertyName("presentacion")] Presentacion? Presentacion = null,
    [property: JsonPropertyName("publicada")] bool Publicada = false);

public sealed record AciertosEnSimbolos([property: JsonPropertyName("simbolos")] IReadOnlyList<string> Simbolos);

/// <summary>La nota publicada tal como la presenta la escala del nivel. No incluye el resultado interno.</summary>
public sealed record NotaPublicada(
    [property: JsonPropertyName("presentada")] ValorPresentado? Presentada,
    [property: JsonPropertyName("desempeno")] Desempeno? Desempeno,
    [property: JsonPropertyName("aprobacion")] CriterioDeAprobacion? Aprobacion,
    [property: JsonPropertyName("retroalimentacion")] Dictionary<string, string>? Retroalimentacion = null,
    [property: JsonPropertyName("publicada_en")] long? PublicadaEn = null,
    [property: JsonPropertyName("numero_intento")] int? NumeroIntento = null,
    [property: JsonPropertyName("escala")] EscalaResumen? Escala = null);

public sealed record MisResultados(
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("items")] IReadOnlyList<ResultadoDelAlumno> Items,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

// ------------------------------------------------------------------------------------------ el periodo

public sealed record AlumnoDelResumen(
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("rotulo")] string Rotulo,
    [property: JsonPropertyName("calificaciones")] int Calificaciones,
    [property: JsonPropertyName("promedio_simple")] decimal? PromedioSimple,
    [property: JsonPropertyName("pendientes")] int Pendientes,
    [property: JsonPropertyName("provisionales")] int Provisionales,
    [property: JsonPropertyName("publicadas")] int Publicadas);

public sealed record CursoDelResumen(
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("alumnos")] IReadOnlyList<AlumnoDelResumen> Alumnos,
    [property: JsonPropertyName("promedio_del_grupo")] decimal? PromedioDelGrupo,
    [property: JsonPropertyName("datos_suficientes")] bool DatosSuficientes,
    [property: JsonPropertyName("curso_rotulo")] string? CursoRotulo = null);

/// <summary>Lo que lleva cada alumno en cada curso durante el periodo: promedio SIMPLE e INFORMATIVO, nunca una calificación oficial ni ponderada.</summary>
public sealed record ResumenDePeriodo(
    [property: JsonPropertyName("grupo")] GrupoDelLibro Grupo,
    [property: JsonPropertyName("cursos")] IReadOnlyList<CursoDelResumen> Cursos,
    [property: JsonPropertyName("oficial")] bool Oficial,
    [property: JsonPropertyName("ponderado")] bool Ponderado,
    [property: JsonPropertyName("aviso")] string Aviso);

/// <summary>
/// Lo que responde «registrar lo calificado» de una evaluación: cuántas calificaciones se registraron, cuántas ya lo estaban, qué intentos aún no se pueden registrar (con su motivo) y cuántos
/// son de un nivel en modo simple (ahí no se registra nada).
/// </summary>
public sealed record RegistroDeAsignacion(
    [property: JsonPropertyName("asignacion_id")] string AsignacionId,
    [property: JsonPropertyName("registradas")] int Registradas,
    [property: JsonPropertyName("ya_registradas")] int YaRegistradas,
    [property: JsonPropertyName("no_registrables")] IReadOnlyList<IntentoNoRegistrable> NoRegistrables,
    [property: JsonPropertyName("en_modo_simple")] int EnModoSimple);

public sealed record IntentoNoRegistrable(
    [property: JsonPropertyName("intento_id")] string IntentoId,
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("motivo")] string? Motivo,
    [property: JsonPropertyName("detalle")] string? Detalle);

public sealed record PublicacionDeAsignacion(
    [property: JsonPropertyName("asignacion_id")] string AsignacionId,
    [property: JsonPropertyName("total_publicadas")] int TotalPublicadas,
    [property: JsonPropertyName("ya_publicadas")] int YaPublicadas,
    [property: JsonPropertyName("omitidas")] IReadOnlyList<JsonElement> Omitidas);

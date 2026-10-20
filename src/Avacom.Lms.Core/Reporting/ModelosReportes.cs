using System.Text.Json;
using System.Text.Json.Serialization;
using Avacom.Lms.Core.Gradebook;

namespace Avacom.Lms.Core.Reporting;

// Contratos de /api/reportes/ (MOD-013 · Reporting), tal como los define spec-driven/14-reporting/02-api.md. Los nombres JSON son los del backend (snake_case).
// Todo lo que llega es lo que la persona puede VER (el nodo recorta por su alcance): el cliente no filtra permisos, sólo pinta. Las cifras sin dato llegan como null: un promedio sin
// valores NO es un cero, y así se pinta («—»). Los porcentajes viajan de 0 a 100 con a lo sumo dos decimales; se leen como decimal para que 22,22 sea 22,22.

// ------------------------------------------------------------------------------------------------ catálogos

/// <summary>Los reportes que existen y los reservados para V1.</summary>
public static class TiposDeReporte
{
    public const string Clase = "clase";
    public const string Alumno = "alumno";
    public const string Grupo = "grupo";
    public const string Uso = "uso";
    public const string Boletin = "boletin";               // el boletín académico individual (uno por estudiante)
    public const string Comparacion = "comparacion";       // reservado (V1)
    public const string Cobertura = "cobertura";           // reservado (V1)
}

/// <summary>Las plantillas del boletín académico: <c>auto</c> elige por el país de la política del libro y el nivel del grupo.</summary>
public static class PlantillasDeBoletin
{
    public const string Auto = "auto";
    public const string Colombia = "co";
    public const string Mexico = "mx";
    public const string Generica = "generica";

    public static string Rotulo(string? codigo) => codigo switch
    {
        Colombia => "Colombia · áreas y asignaturas",
        Mexico => "México · campos formativos / disciplinas",
        Generica => "Genérica · asignaturas",
        _ => "Automática (según el país del colegio)",
    };
}

/// <summary>El estado técnico de las proyecciones; la pantalla lo muestra como antigüedad del dato, no como estado interno.</summary>
public static class EstadosDeProyeccion
{
    public const string AlDia = "al_dia";
    public const string Reconstruyendose = "reconstruyendose";
    public const string Rezagada = "rezagada";
}

public static class FormatosDeExportacion
{
    public const string Xlsx = "xlsx";
    public const string Csv = "csv";
    /// <summary>Lo que el nodo ENTREGA cuando va un archivo por estudiante (los boletines de un grupo): un zip con un xlsx o un csv por cada uno. No se pide; se recibe.</summary>
    public const string Zip = "zip";

    public static string Extension(string formato) => formato switch { Csv => "csv", Zip => "zip", _ => "xlsx" };
}

/// <summary>Los tipos de destino con que el backend aplica la política del administrador (contrato con <see cref="Avacom.Lms.Core.Reporting.MotivosDeEscritura"/> y con la lista de destinos de OPS).</summary>
public static class TiposDeDestinoDeExportacion
{
    public const string Extraible = "extraible";
    public const string CarpetaLocal = "carpeta_local";
    public const string Red = "red";
}

public static class EstadosDeExportacion
{
    public const string Autorizada = "autorizada";       // «sin confirmar»
    public const string Entregada = "entregada";
    public const string Caducada = "caducada";
}

// ------------------------------------------------------------------------------------------------ lo que todo reporte lleva (BR-083, BR-086, art. 14)

/// <summary>El estado de integración de los equipos en el instante del corte (BR-083): cuántas tabletas aún tienen algo por enviar y por qué.</summary>
public sealed record IntegracionDeEquipos(
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("equipos")] int Equipos,
    [property: JsonPropertyName("sin_sincronizar")] int SinSincronizar,
    [property: JsonPropertyName("motivos")] IReadOnlyList<MotivoDeIntegracion> Motivos,
    [property: JsonPropertyName("texto")] string Texto,
    [property: JsonPropertyName("motivo_linea")] string MotivoLinea)
{
    public bool Incompleta => Estado == "incompleta";
}

public sealed record MotivoDeIntegracion(
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("equipos")] int Equipos,
    [property: JsonPropertyName("texto")] string Texto);

/// <summary>El instante de corte de los datos y qué tan viejos son (BR-083): «Datos al 15 oct · 10:42 · 2 tabletas sin sincronizar».</summary>
public sealed record CorteDeDatos(
    [property: JsonPropertyName("en")] long En,
    [property: JsonPropertyName("antiguedad_ms")] long AntiguedadMs,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("incompleto")] bool Incompleto,
    [property: JsonPropertyName("integracion")] IntegracionDeEquipos Integracion,
    [property: JsonPropertyName("texto")] string Texto,
    [property: JsonPropertyName("explicacion")] string Explicacion);

/// <summary>El umbral de privacidad (BR-086): con menos de cinco alumnos y el umbral activo, el reporte sólo muestra los totales.</summary>
public sealed record Privacidad(
    [property: JsonPropertyName("umbral_activo")] bool UmbralActivo,
    [property: JsonPropertyName("aplicada")] bool Aplicada,
    [property: JsonPropertyName("minimo")] int Minimo,
    [property: JsonPropertyName("alumnos")] int Alumnos,
    [property: JsonPropertyName("aviso")] string Aviso);

/// <summary>El dominio por objetivo (MOD-012) aún no existe: <c>Disponible</c> es falso y se pinta «Aún no disponible», nunca un cero.</summary>
public sealed record DominioPorObjetivo(
    [property: JsonPropertyName("disponible")] bool Disponible,
    [property: JsonPropertyName("texto")] string Texto);

/// <summary>Algo que el reporte quiere avisar (por ejemplo, que el filtro por nodo académico no se pudo aplicar porque la biblioteca no respondió).</summary>
public sealed record AvisoDeReporte(
    [property: JsonPropertyName("filtro")] string Filtro,
    [property: JsonPropertyName("aplicado")] bool Aplicado,
    [property: JsonPropertyName("texto")] string Texto);

public sealed record QuienGenero(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("rotulo")] string Rotulo);

public sealed record GrupoResumido(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("periodo")] string Periodo,
    [property: JsonPropertyName("nivel_clave")] string NivelClave)
{
    public string Rotulo => !string.IsNullOrWhiteSpace(Codigo) ? Codigo : Nombre;
}

/// <summary>La escala de calificación del nivel del grupo (la que el libro de MOD-011 resolvió); null en modo simple.</summary>
public sealed record EscalaResumida(
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("numero")] int Numero);

public sealed record MotivoDeAtencion(
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("cantidad")] int Cantidad,
    [property: JsonPropertyName("texto")] string Texto);

// ------------------------------------------------------------------------------------------------ una clase (CAP-081)

public sealed record ClaseReportada(
    [property: JsonPropertyName("sesion_id")] string SesionId,
    [property: JsonPropertyName("grupo")] GrupoResumido? Grupo,
    [property: JsonPropertyName("curso_rotulo")] string CursoRotulo,
    [property: JsonPropertyName("leccion_rotulo")] string LeccionRotulo,
    [property: JsonPropertyName("iniciada_en")] long? IniciadaEn,
    [property: JsonPropertyName("finalizada_en")] long FinalizadaEn,
    [property: JsonPropertyName("duracion_ms")] long DuracionMs,
    [property: JsonPropertyName("participantes")] int Participantes,
    [property: JsonPropertyName("actividades")] int Actividades,
    [property: JsonPropertyName("equipos")] int Equipos);

/// <summary>Lo que hizo un alumno en la clase. Los porcentajes son null cuando no hay dato (sin actividades, o sin nada entregado): no son un 0 %.</summary>
public sealed record FilaDeClase(
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("alumno")] string Alumno,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("presente_ms")] long PresenteMs,
    [property: JsonPropertyName("actividades_recibidas")] int ActividadesRecibidas,
    [property: JsonPropertyName("actividades_entregadas")] int ActividadesEntregadas,
    [property: JsonPropertyName("calificadas")] int Calificadas,
    [property: JsonPropertyName("aciertos")] int Aciertos,
    [property: JsonPropertyName("porcentaje_participacion")] decimal? PorcentajeParticipacion,
    [property: JsonPropertyName("porcentaje_aciertos")] decimal? PorcentajeAciertos,
    [property: JsonPropertyName("entregas_por_cola")] int EntregasPorCola);

public sealed record TotalesDeClase(
    [property: JsonPropertyName("participantes")] int Participantes,
    [property: JsonPropertyName("actividades")] int Actividades,
    [property: JsonPropertyName("promedio_participacion")] decimal? PromedioParticipacion,
    [property: JsonPropertyName("promedio_aciertos")] decimal? PromedioAciertos);

public sealed record ReporteDeClase(
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("generado_en")] long GeneradoEn,
    [property: JsonPropertyName("generado_por")] QuienGenero GeneradoPor,
    [property: JsonPropertyName("corte")] CorteDeDatos Corte,
    [property: JsonPropertyName("privacidad")] Privacidad Privacidad,
    [property: JsonPropertyName("nominal")] bool Nominal,
    [property: JsonPropertyName("objetivos")] DominioPorObjetivo Objetivos,
    [property: JsonPropertyName("avisos")] IReadOnlyList<AvisoDeReporte> Avisos,
    [property: JsonPropertyName("servidor_en")] long ServidorEn,
    [property: JsonPropertyName("clase")] ClaseReportada Clase,
    [property: JsonPropertyName("filas")] IReadOnlyList<FilaDeClase> Filas,
    [property: JsonPropertyName("totales")] TotalesDeClase Totales);

// ------------------------------------------------------------------------------------------------ un grupo (FUN-139)

public sealed record TotalesDeGrupo(
    [property: JsonPropertyName("alumnos")] int Alumnos,
    [property: JsonPropertyName("clases")] int Clases,
    [property: JsonPropertyName("evaluaciones")] int Evaluaciones,
    [property: JsonPropertyName("estudios")] int Estudios,
    [property: JsonPropertyName("en_atencion")] int EnAtencion,
    [property: JsonPropertyName("promedio_participacion")] decimal? PromedioParticipacion,
    [property: JsonPropertyName("promedio_aciertos")] decimal? PromedioAciertos);

/// <summary>Un alumno en el reporte de su grupo. Con <see cref="Atencion"/> vacío no necesita atención; el nodo ya los trae ordenados (quien necesita atención, primero).</summary>
public sealed record AlumnoEnGrupo(
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("alumno")] string Alumno,
    [property: JsonPropertyName("clases_asistidas")] int ClasesAsistidas,
    [property: JsonPropertyName("clases_total")] int ClasesTotal,
    [property: JsonPropertyName("porcentaje_participacion")] decimal? PorcentajeParticipacion,
    [property: JsonPropertyName("porcentaje_aciertos")] decimal? PorcentajeAciertos,
    [property: JsonPropertyName("evaluaciones_presentadas")] int EvaluacionesPresentadas,
    [property: JsonPropertyName("evaluaciones_total")] int EvaluacionesTotal,
    [property: JsonPropertyName("evaluaciones_sin_presentar")] int EvaluacionesSinPresentar,
    [property: JsonPropertyName("estudios_completados")] int EstudiosCompletados,
    [property: JsonPropertyName("estudios_total")] int EstudiosTotal,
    [property: JsonPropertyName("atencion")] IReadOnlyList<MotivoDeAtencion> Atencion,
    [property: JsonPropertyName("motivo")] string Motivo)
{
    public bool NecesitaAtencion => Atencion.Count > 0;
}

public sealed record ClaseDeGrupo(
    [property: JsonPropertyName("sesion_id")] string SesionId,
    [property: JsonPropertyName("iniciada_en")] long? IniciadaEn,
    [property: JsonPropertyName("finalizada_en")] long FinalizadaEn,
    [property: JsonPropertyName("curso_rotulo")] string CursoRotulo,
    [property: JsonPropertyName("leccion_rotulo")] string LeccionRotulo,
    [property: JsonPropertyName("participantes")] int Participantes,
    [property: JsonPropertyName("promedio_participacion")] decimal? PromedioParticipacion,
    [property: JsonPropertyName("promedio_aciertos")] decimal? PromedioAciertos,
    [property: JsonPropertyName("incompleta")] bool Incompleta);

/// <summary>Cuántos presentaron, cuántos faltan y cuántas ya tienen su calificación publicada: conteos, sin promedio.</summary>
public sealed record EvaluacionEnGrupo(
    [property: JsonPropertyName("asignacion_id")] string AsignacionId,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("curso_rotulo")] string CursoRotulo,
    [property: JsonPropertyName("alumnos")] int Alumnos,
    [property: JsonPropertyName("presentaron")] int Presentaron,
    [property: JsonPropertyName("pendientes")] int Pendientes,
    [property: JsonPropertyName("por_revisar")] int PorRevisar,
    [property: JsonPropertyName("publicadas")] int Publicadas);

public sealed record ReporteDeGrupo(
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("generado_en")] long GeneradoEn,
    [property: JsonPropertyName("generado_por")] QuienGenero GeneradoPor,
    [property: JsonPropertyName("corte")] CorteDeDatos Corte,
    [property: JsonPropertyName("privacidad")] Privacidad Privacidad,
    [property: JsonPropertyName("nominal")] bool Nominal,
    [property: JsonPropertyName("objetivos")] DominioPorObjetivo Objetivos,
    [property: JsonPropertyName("avisos")] IReadOnlyList<AvisoDeReporte> Avisos,
    [property: JsonPropertyName("servidor_en")] long ServidorEn,
    [property: JsonPropertyName("grupo")] GrupoResumido Grupo,
    [property: JsonPropertyName("modo")] string Modo,
    [property: JsonPropertyName("escala")] EscalaResumida? Escala,
    [property: JsonPropertyName("totales")] TotalesDeGrupo Totales,
    [property: JsonPropertyName("atencion")] IReadOnlyList<AlumnoEnGrupo> Atencion,
    [property: JsonPropertyName("alumnos")] IReadOnlyList<AlumnoEnGrupo> Alumnos,
    [property: JsonPropertyName("clases")] IReadOnlyList<ClaseDeGrupo> Clases,
    [property: JsonPropertyName("evaluaciones")] IReadOnlyList<EvaluacionEnGrupo> Evaluaciones)
{
    public bool EnModoCalificaciones => Modo == ModosDeNivel.Calificaciones;
}

// ------------------------------------------------------------------------------------------------ un alumno (CAP-082, FUN-140)

public sealed record AlumnoDelReporte(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("rotulo")] string Rotulo);

public sealed record ResumenDeAlumno(
    [property: JsonPropertyName("clases_total")] int ClasesTotal,
    [property: JsonPropertyName("clases_asistidas")] int ClasesAsistidas,
    [property: JsonPropertyName("porcentaje_asistencia")] decimal? PorcentajeAsistencia,
    [property: JsonPropertyName("actividades_recibidas")] int ActividadesRecibidas,
    [property: JsonPropertyName("actividades_entregadas")] int ActividadesEntregadas,
    [property: JsonPropertyName("porcentaje_participacion")] decimal? PorcentajeParticipacion,
    [property: JsonPropertyName("porcentaje_aciertos")] decimal? PorcentajeAciertos,
    [property: JsonPropertyName("evaluaciones_total")] int EvaluacionesTotal,
    [property: JsonPropertyName("evaluaciones_presentadas")] int EvaluacionesPresentadas,
    [property: JsonPropertyName("evaluaciones_sin_presentar")] int EvaluacionesSinPresentar,
    [property: JsonPropertyName("estudios_total")] int EstudiosTotal,
    [property: JsonPropertyName("estudios_completados")] int EstudiosCompletados,
    [property: JsonPropertyName("estudios_vencidos")] int EstudiosVencidos,
    [property: JsonPropertyName("avance_estudio")] decimal? AvanceEstudio,
    [property: JsonPropertyName("ultima_actividad_en")] long? UltimaActividadEn,
    [property: JsonPropertyName("atencion")] IReadOnlyList<MotivoDeAtencion> Atencion);

/// <summary>Una evaluación de un alumno. <see cref="Presentacion"/> es la calificación YA presentada por el libro (con la escala del nivel); en modo simple es null y se pinta el símbolo.</summary>
public sealed record EvaluacionDeAlumno(
    [property: JsonPropertyName("asignacion_id")] string AsignacionId,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("estado_asignacion")] string EstadoAsignacion,
    [property: JsonPropertyName("presento")] bool Presento,
    [property: JsonPropertyName("sin_presentar")] bool SinPresentar,
    [property: JsonPropertyName("estado_intento")] string EstadoIntento,
    [property: JsonPropertyName("estado_simple")] string EstadoSimple,
    [property: JsonPropertyName("simbolo")] string Simbolo,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("publicada")] bool Publicada,
    [property: JsonPropertyName("presentacion")] Presentacion? Presentacion);

public sealed record EstudioDeAlumno(
    [property: JsonPropertyName("asignacion_id")] string AsignacionId,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("avance_pct")] decimal? AvancePct,
    [property: JsonPropertyName("vencida")] bool Vencida,
    [property: JsonPropertyName("completada")] bool Completada);

public sealed record ClaseDeAlumno(
    [property: JsonPropertyName("sesion_id")] string SesionId,
    [property: JsonPropertyName("finalizada_en")] long FinalizadaEn,
    [property: JsonPropertyName("asistio")] bool Asistio,
    [property: JsonPropertyName("recibidas")] int Recibidas,
    [property: JsonPropertyName("entregadas")] int Entregadas,
    [property: JsonPropertyName("porcentaje_aciertos")] decimal? PorcentajeAciertos);

public sealed record AvanceEnGrupo(
    [property: JsonPropertyName("grupo")] GrupoResumido Grupo,
    [property: JsonPropertyName("modo")] string Modo,
    [property: JsonPropertyName("escala")] EscalaResumida? Escala,
    [property: JsonPropertyName("resumen")] ResumenDeAlumno Resumen,
    [property: JsonPropertyName("motivo_de_atencion")] string MotivoDeAtencion,
    [property: JsonPropertyName("evaluaciones")] IReadOnlyList<EvaluacionDeAlumno> Evaluaciones,
    [property: JsonPropertyName("estudios")] IReadOnlyList<EstudioDeAlumno> Estudios,
    [property: JsonPropertyName("clases")] IReadOnlyList<ClaseDeAlumno> Clases)
{
    public bool EnModoCalificaciones => Modo == ModosDeNivel.Calificaciones;
}

public sealed record ReporteDeAlumno(
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("generado_en")] long GeneradoEn,
    [property: JsonPropertyName("generado_por")] QuienGenero GeneradoPor,
    [property: JsonPropertyName("corte")] CorteDeDatos Corte,
    [property: JsonPropertyName("privacidad")] Privacidad Privacidad,
    [property: JsonPropertyName("nominal")] bool Nominal,
    [property: JsonPropertyName("objetivos")] DominioPorObjetivo Objetivos,
    [property: JsonPropertyName("avisos")] IReadOnlyList<AvisoDeReporte> Avisos,
    [property: JsonPropertyName("servidor_en")] long ServidorEn,
    [property: JsonPropertyName("alumno")] AlumnoDelReporte Alumno,
    [property: JsonPropertyName("grupos")] IReadOnlyList<AvanceEnGrupo> Grupos);

// ------------------------------------------------------------------------------------------------ uso de equipos (FUN-142)

public sealed record PeriodoDeUso(
    [property: JsonPropertyName("desde")] long? Desde,
    [property: JsonPropertyName("hasta")] long? Hasta);

public sealed record TotalesDeUso(
    [property: JsonPropertyName("clases")] int Clases,
    [property: JsonPropertyName("equipos")] int Equipos,
    [property: JsonPropertyName("tiempo_total_ms")] long TiempoTotalMs,
    [property: JsonPropertyName("duracion_media_ms")] long DuracionMediaMs);

public sealed record EquipoDeUso(
    [property: JsonPropertyName("dispositivo_id")] string DispositivoId,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("plataforma")] string Plataforma,
    [property: JsonPropertyName("version_app")] string VersionApp,
    [property: JsonPropertyName("clases")] int Clases,
    [property: JsonPropertyName("tiempo_total_ms")] long TiempoTotalMs,
    [property: JsonPropertyName("alumnos")] int Alumnos,
    [property: JsonPropertyName("ultimo_uso_en")] long? UltimoUsoEn,
    [property: JsonPropertyName("activo")] bool Activo,
    [property: JsonPropertyName("bloqueado")] bool Bloqueado);

public sealed record ClaseDeUso(
    [property: JsonPropertyName("sesion_id")] string SesionId,
    [property: JsonPropertyName("grupo")] GrupoResumido? Grupo,
    [property: JsonPropertyName("iniciada_en")] long? IniciadaEn,
    [property: JsonPropertyName("finalizada_en")] long FinalizadaEn,
    [property: JsonPropertyName("duracion_ms")] long DuracionMs,
    [property: JsonPropertyName("participantes")] int Participantes,
    [property: JsonPropertyName("equipos")] int Equipos,
    [property: JsonPropertyName("incompleta")] bool Incompleta);

public sealed record ReporteDeUso(
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("generado_en")] long GeneradoEn,
    [property: JsonPropertyName("generado_por")] QuienGenero GeneradoPor,
    [property: JsonPropertyName("corte")] CorteDeDatos Corte,
    [property: JsonPropertyName("privacidad")] Privacidad Privacidad,
    [property: JsonPropertyName("nominal")] bool Nominal,
    [property: JsonPropertyName("objetivos")] DominioPorObjetivo Objetivos,
    [property: JsonPropertyName("avisos")] IReadOnlyList<AvisoDeReporte> Avisos,
    [property: JsonPropertyName("servidor_en")] long ServidorEn,
    [property: JsonPropertyName("periodo")] PeriodoDeUso Periodo,
    [property: JsonPropertyName("totales")] TotalesDeUso Totales,
    [property: JsonPropertyName("equipos")] IReadOnlyList<EquipoDeUso> Equipos,
    [property: JsonPropertyName("clases")] IReadOnlyList<ClaseDeUso> Clases);

// ------------------------------------------------------------------------------------------------ para llegar a un reporte sin escribir

public sealed record ClaseDeLista(
    [property: JsonPropertyName("sesion_id")] string SesionId,
    [property: JsonPropertyName("grupo")] GrupoResumido? Grupo,
    [property: JsonPropertyName("curso_rotulo")] string CursoRotulo,
    [property: JsonPropertyName("leccion_rotulo")] string LeccionRotulo,
    [property: JsonPropertyName("iniciada_en")] long? IniciadaEn,
    [property: JsonPropertyName("finalizada_en")] long FinalizadaEn,
    [property: JsonPropertyName("duracion_ms")] long DuracionMs,
    [property: JsonPropertyName("participantes")] int Participantes,
    [property: JsonPropertyName("actividades")] int Actividades,
    [property: JsonPropertyName("promedio_participacion")] decimal? PromedioParticipacion,
    [property: JsonPropertyName("promedio_aciertos")] decimal? PromedioAciertos,
    [property: JsonPropertyName("incompleta")] bool Incompleta);

public sealed record ListaDeClases(
    [property: JsonPropertyName("clases")] IReadOnlyList<ClaseDeLista> Clases,
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("avisos")] IReadOnlyList<AvisoDeReporte> Avisos,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("corte_en")] long CorteEn,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

public sealed record GrupoParaFiltro(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("periodo")] string Periodo,
    [property: JsonPropertyName("nivel_clave")] string NivelClave,
    [property: JsonPropertyName("alumnos")] int? Alumnos,
    [property: JsonPropertyName("en_atencion")] int? EnAtencion,
    [property: JsonPropertyName("desactualizado")] bool Desactualizado)
{
    public string Rotulo => !string.IsNullOrWhiteSpace(Codigo) ? Codigo : Nombre;
}

public sealed record NodoDelArbol(
    [property: JsonPropertyName("kind")] string? Kind,
    [property: JsonPropertyName("code")] string? Code,
    [property: JsonPropertyName("name")] string? Name,
    [property: JsonPropertyName("count")] int? Count,
    [property: JsonPropertyName("children")] IReadOnlyList<NodoDelArbol>? Children);

public sealed record NodosAcademicos(
    [property: JsonPropertyName("disponible")] bool Disponible,
    [property: JsonPropertyName("motivo")] string Motivo,
    [property: JsonPropertyName("arbol")] IReadOnlyList<NodoDelArbol> Arbol);

/// <summary>Qué puede hacer esta persona con los reportes (el nodo lo decide por su rol): la pantalla sólo ofrece lo que el nodo va a conceder.</summary>
public sealed record PermisosDeReportes(
    [property: JsonPropertyName("clase")] bool Clase,
    [property: JsonPropertyName("grupo")] bool Grupo,
    [property: JsonPropertyName("alumno")] bool Alumno,
    [property: JsonPropertyName("uso")] bool Uso,
    [property: JsonPropertyName("exportar")] bool Exportar,
    [property: JsonPropertyName("reconstruir")] bool Reconstruir,
    [property: JsonPropertyName("configurar")] bool Configurar)
{
    public bool PuedeVerAlgo => Clase || Grupo || Alumno || Uso;
}

public sealed record FiltrosDeReportes(
    [property: JsonPropertyName("grupos")] IReadOnlyList<GrupoParaFiltro> Grupos,
    [property: JsonPropertyName("periodos")] IReadOnlyList<string> Periodos,
    [property: JsonPropertyName("nodos")] NodosAcademicos Nodos,
    [property: JsonPropertyName("objetivos")] DominioPorObjetivo Objetivos,
    [property: JsonPropertyName("puede")] PermisosDeReportes Puede,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

public sealed record AlumnoParaElegir(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("rotulo")] string Rotulo,
    [property: JsonPropertyName("inicial")] string Inicial,
    [property: JsonPropertyName("necesita_atencion")] bool NecesitaAtencion);

public sealed record InicialConCantidad(
    [property: JsonPropertyName("inicial")] string Inicial,
    [property: JsonPropertyName("cantidad")] int Cantidad);

public sealed record AlumnosParaElegir(
    [property: JsonPropertyName("grupo_id")] string GrupoId,
    [property: JsonPropertyName("alumnos")] IReadOnlyList<AlumnoParaElegir> Alumnos,
    [property: JsonPropertyName("iniciales")] IReadOnlyList<InicialConCantidad> Iniciales);

/// <summary>Un reporte que esta persona abrió hace poco: sus parámetros (qué reporte, de qué grupo, de qué periodo), para volver a abrirlo y exportarlo sin repetir los filtros.</summary>
public sealed record ReporteReciente(
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("parametros")] IReadOnlyDictionary<string, JsonElement> Parametros,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("ultima_vez_en")] long UltimaVezEn,
    [property: JsonPropertyName("veces")] int Veces,
    [property: JsonPropertyName("ultima_exportacion_en")] long? UltimaExportacionEn)
{
    /// <summary>El texto de un parámetro (los identificadores y las fechas viajan como texto o como número).</summary>
    public string? Parametro(string clave) => Parametros.TryGetValue(clave, out var v) ? (v.ValueKind == JsonValueKind.String ? v.GetString() : v.ToString()) : null;
}

public sealed record RecientesDeReportes(
    [property: JsonPropertyName("recientes")] IReadOnlyList<ReporteReciente> Recientes,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

// ------------------------------------------------------------------------------------------------ configuración y estado de los agregados

public sealed record RazonDeExportacion(
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("etiqueta")] string Etiqueta);

public sealed record ConfiguracionDeReportes(
    [property: JsonPropertyName("umbral_privacidad")] bool UmbralPrivacidad,
    [property: JsonPropertyName("extraibles_permitidos")] bool ExtraiblesPermitidos,
    [property: JsonPropertyName("exigir_razon")] bool ExigirRazon,
    [property: JsonPropertyName("version")] int Version,
    [property: JsonPropertyName("actualizada_en")] long? ActualizadaEn,
    [property: JsonPropertyName("actualizada_por")] string? ActualizadaPor,
    [property: JsonPropertyName("minimo_de_alumnos")] int MinimoDeAlumnos,
    [property: JsonPropertyName("razones")] IReadOnlyList<RazonDeExportacion> Razones,
    [property: JsonPropertyName("formatos")] IReadOnlyList<string> Formatos,
    [property: JsonPropertyName("destinos")] IReadOnlyList<string> Destinos,
    [property: JsonPropertyName("plantilla_boletin")] string? PlantillaBoletin = null,
    [property: JsonPropertyName("periodos_boletin")] IReadOnlyList<string>? PeriodosBoletin = null,
    [property: JsonPropertyName("leyenda_boletin")] string? LeyendaBoletin = null,
    [property: JsonPropertyName("plantillas_de_boletin")] IReadOnlyList<string>? PlantillasDeBoletin = null);

public sealed record RespuestaDeConfiguracion(
    [property: JsonPropertyName("configuracion")] ConfiguracionDeReportes Configuracion,
    [property: JsonPropertyName("cambiado")] bool? Cambiado,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

/// <summary>Lo que se cambia de la configuración: lo que vale null no viaja.</summary>
public sealed record CambioDeConfiguracion(bool? UmbralPrivacidad = null, bool? ExtraiblesPermitidos = null, bool? ExigirRazon = null, int? VersionEsperada = null,
                                           string? PlantillaBoletin = null, IReadOnlyList<string>? PeriodosBoletin = null, string? LeyendaBoletin = null);

// ------------------------------------------------------------------------------------------------ el boletín académico individual

/// <summary>La plantilla con que se armó un boletín: país, marco de referencia, cómo se organizan las áreas, los periodos de la institución y si lleva cifras.</summary>
public sealed record PlantillaDeBoletin(
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("pais")] string Pais,
    [property: JsonPropertyName("marco")] string Marco,
    [property: JsonPropertyName("organizacion")] string Organizacion,
    [property: JsonPropertyName("rotulo_de_area")] string RotuloDeArea,
    [property: JsonPropertyName("periodos")] IReadOnlyList<string> Periodos,
    [property: JsonPropertyName("sin_cifras")] bool SinCifras,
    [property: JsonPropertyName("desempenos_nacionales")] IReadOnlyList<string>? DesempenosNacionales = null,
    [property: JsonPropertyName("evaluacion_cualitativa")] string? EvaluacionCualitativa = null,
    [property: JsonPropertyName("referentes")] string? Referentes = null,
    [property: JsonPropertyName("leyenda")] string? Leyenda = null);

public sealed record InstitucionDelBoletin(
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("pais")] string Pais,
    [property: JsonPropertyName("jurisdiccion")] string Jurisdiccion);

/// <summary>Un curso dentro de un área del boletín, con su nota en bruto (puntos sumados), su promedio simple y lo presentado con el sistema configurado.</summary>
public sealed record CursoDelArea(
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("curso_rotulo")] string CursoRotulo,
    [property: JsonPropertyName("evaluaciones")] int Evaluaciones,
    [property: JsonPropertyName("con_nota")] int ConNota,
    [property: JsonPropertyName("completadas")] int Completadas,
    [property: JsonPropertyName("aprobadas")] int Aprobadas,
    [property: JsonPropertyName("no_aprobadas")] int NoAprobadas,
    [property: JsonPropertyName("pendientes")] int Pendientes,
    [property: JsonPropertyName("bruto")] SumaBruta Bruto,
    [property: JsonPropertyName("promedio_simple")] decimal? PromedioSimple = null,
    [property: JsonPropertyName("presentado")] PromedioPresentado? Presentado = null,
    [property: JsonPropertyName("desempeno")] string? Desempeno = null,
    [property: JsonPropertyName("cumple_criterio")] bool? CumpleCriterio = null,
    [property: JsonPropertyName("desempeno_nacional")] string? DesempenoNacional = null);

/// <summary>Un área, asignatura, campo formativo o disciplina del boletín (según la plantilla), con sus cursos: la primera pregunta, «¿qué aprendió?».</summary>
public sealed record AreaDelBoletin(
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("rotulo")] string Rotulo,
    [property: JsonPropertyName("materia")] string Materia,
    [property: JsonPropertyName("cursos")] IReadOnlyList<CursoDelArea> Cursos,
    [property: JsonPropertyName("evaluaciones")] int Evaluaciones,
    [property: JsonPropertyName("con_nota")] int ConNota,
    [property: JsonPropertyName("aprobadas")] int Aprobadas,
    [property: JsonPropertyName("no_aprobadas")] int NoAprobadas,
    [property: JsonPropertyName("completadas")] int Completadas,
    [property: JsonPropertyName("bruto")] SumaBruta Bruto,
    [property: JsonPropertyName("campo_formativo")] string? CampoFormativo = null,
    [property: JsonPropertyName("promedio_simple")] decimal? PromedioSimple = null,
    [property: JsonPropertyName("presentado")] PromedioPresentado? Presentado = null,
    [property: JsonPropertyName("desempeno")] string? Desempeno = null,
    [property: JsonPropertyName("desempeno_nacional")] string? DesempenoNacional = null);

public sealed record EvaluacionDelBoletinAcademico(
    [property: JsonPropertyName("asignacion_id")] string AsignacionId,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("curso_rotulo")] string CursoRotulo,
    [property: JsonPropertyName("area")] string Area,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("estado_simple")] string EstadoSimple,
    [property: JsonPropertyName("publicada")] bool Publicada,
    [property: JsonPropertyName("provisional")] bool Provisional,
    [property: JsonPropertyName("ajustada")] bool Ajustada,
    [property: JsonPropertyName("tipo_evaluacion")] string? TipoEvaluacion = null,
    [property: JsonPropertyName("fecha")] long? Fecha = null,
    [property: JsonPropertyName("bruto")] NotaEnBruto? Bruto = null,
    [property: JsonPropertyName("presentada")] string? Presentada = null,
    [property: JsonPropertyName("desempeno")] string? Desempeno = null,
    [property: JsonPropertyName("cumple_criterio")] bool? CumpleCriterio = null);

/// <summary>La segunda pregunta, «¿qué competencias alcanzó?»: logros (fortalezas anotadas), aprendizajes pendientes (dificultades) y las evaluaciones que cumplen o no el criterio.</summary>
public sealed record CompetenciasDelBoletin(
    [property: JsonPropertyName("logros")] IReadOnlyList<ComentarioDelProfesor> Logros,
    [property: JsonPropertyName("pendientes")] IReadOnlyList<ComentarioDelProfesor> Pendientes,
    [property: JsonPropertyName("evaluaciones_no_aprobadas")] IReadOnlyList<string> EvaluacionesNoAprobadas,
    [property: JsonPropertyName("evaluaciones_aprobadas")] IReadOnlyList<string> EvaluacionesAprobadas,
    [property: JsonPropertyName("objetivos")] DominioPorObjetivo Objetivos);

public sealed record FilaDeProgreso(
    [property: JsonPropertyName("periodo")] string Periodo,
    [property: JsonPropertyName("grupo_codigo")] string GrupoCodigo,
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("curso_rotulo")] string CursoRotulo,
    [property: JsonPropertyName("calificaciones")] int Calificaciones,
    [property: JsonPropertyName("actual")] bool Actual,
    [property: JsonPropertyName("promedio_simple")] decimal? PromedioSimple = null,
    [property: JsonPropertyName("presentado")] PromedioPresentado? Presentado = null);

/// <summary>La tercera pregunta, «¿cómo ha progresado?»: el promedio simple por curso en cada periodo en que estuvo, y la tendencia.</summary>
public sealed record ProgresoDelBoletin(
    [property: JsonPropertyName("periodos")] IReadOnlyList<string> Periodos,
    [property: JsonPropertyName("filas")] IReadOnlyList<FilaDeProgreso> Filas,
    [property: JsonPropertyName("tendencia")] TendenciaDelEstudiante? Tendencia = null);

public sealed record ObservacionEnBoletin(
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("curso_rotulo")] string CursoRotulo,
    [property: JsonPropertyName("recomendaciones")] IReadOnlyList<string> Recomendaciones,
    [property: JsonPropertyName("texto")] string Texto,
    [property: JsonPropertyName("actualizada_en")] long? ActualizadaEn = null);

/// <summary>La cuarta pregunta, «¿qué debe mejorar?»: lo que el profesor recomendó, las oportunidades que anotó y el curso que conviene reforzar.</summary>
public sealed record RecomendacionesDelBoletin(
    [property: JsonPropertyName("del_docente")] IReadOnlyList<ObservacionEnBoletin> DelDocente,
    [property: JsonPropertyName("oportunidades")] IReadOnlyList<ComentarioDelProfesor> Oportunidades,
    [property: JsonPropertyName("curso_a_reforzar")] CursoDestacado? CursoAReforzar = null,
    [property: JsonPropertyName("mejor_curso")] CursoDestacado? MejorCurso = null);

public sealed record ResumenDelBoletin(
    [property: JsonPropertyName("evaluaciones")] int Evaluaciones,
    [property: JsonPropertyName("con_nota")] int ConNota,
    [property: JsonPropertyName("aprobadas")] int Aprobadas,
    [property: JsonPropertyName("no_aprobadas")] int NoAprobadas,
    [property: JsonPropertyName("completadas")] int Completadas,
    [property: JsonPropertyName("pendientes")] int Pendientes,
    [property: JsonPropertyName("bruto")] SumaBruta Bruto,
    [property: JsonPropertyName("oficial")] bool Oficial,
    [property: JsonPropertyName("ponderado")] bool Ponderado,
    [property: JsonPropertyName("promedio_simple")] decimal? PromedioSimple = null,
    [property: JsonPropertyName("presentado")] PromedioPresentado? Presentado = null);

/// <summary>El modelo de información común del boletín académico de UN estudiante: responde las cuatro preguntas con lo que el libro ya presentó. No es un documento oficial.</summary>
public sealed record ModeloDeBoletin(
    [property: JsonPropertyName("plantilla")] PlantillaDeBoletin Plantilla,
    [property: JsonPropertyName("institucion")] InstitucionDelBoletin Institucion,
    [property: JsonPropertyName("estudiante")] AlumnoDelReporte Estudiante,
    [property: JsonPropertyName("grupo")] GrupoResumido Grupo,
    [property: JsonPropertyName("periodo")] string Periodo,
    [property: JsonPropertyName("nivel_clave")] string NivelClave,
    [property: JsonPropertyName("modo")] string Modo,
    [property: JsonPropertyName("sin_cifras")] bool SinCifras,
    [property: JsonPropertyName("areas")] IReadOnlyList<AreaDelBoletin> Areas,
    [property: JsonPropertyName("evaluaciones")] IReadOnlyList<EvaluacionDelBoletinAcademico> Evaluaciones,
    [property: JsonPropertyName("competencias")] CompetenciasDelBoletin Competencias,
    [property: JsonPropertyName("progreso")] ProgresoDelBoletin Progreso,
    [property: JsonPropertyName("recomendaciones")] RecomendacionesDelBoletin Recomendaciones,
    [property: JsonPropertyName("resumen")] ResumenDelBoletin Resumen,
    [property: JsonPropertyName("leyenda")] string Leyenda,
    [property: JsonPropertyName("preguntas")] IReadOnlyList<string> Preguntas,
    [property: JsonPropertyName("sistema")] EscalaResumen? Sistema = null);

public sealed record ReporteDeBoletin(
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("generado_en")] long GeneradoEn,
    [property: JsonPropertyName("generado_por")] QuienGenero GeneradoPor,
    [property: JsonPropertyName("corte")] CorteDeDatos Corte,
    [property: JsonPropertyName("privacidad")] Privacidad Privacidad,
    [property: JsonPropertyName("nominal")] bool Nominal,
    [property: JsonPropertyName("objetivos")] DominioPorObjetivo Objetivos,
    [property: JsonPropertyName("avisos")] IReadOnlyList<AvisoDeReporte> Avisos,
    [property: JsonPropertyName("servidor_en")] long ServidorEn,
    [property: JsonPropertyName("alumno")] AlumnoDelReporte Alumno,
    [property: JsonPropertyName("grupo")] GrupoResumido Grupo,
    [property: JsonPropertyName("plantilla")] PlantillaDeBoletin Plantilla,
    [property: JsonPropertyName("boletin")] ModeloDeBoletin Boletin);

public sealed record TotalesDeBoletines(
    [property: JsonPropertyName("estudiantes")] int Estudiantes,
    [property: JsonPropertyName("boletines")] int Boletines,
    [property: JsonPropertyName("con_nota")] int ConNota);

/// <summary>Los boletines de un grupo: uno por estudiante, en orden alfabético. Se exportan como un zip con un archivo por estudiante.</summary>
public sealed record ReporteDeBoletines(
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("generado_en")] long GeneradoEn,
    [property: JsonPropertyName("generado_por")] QuienGenero GeneradoPor,
    [property: JsonPropertyName("corte")] CorteDeDatos Corte,
    [property: JsonPropertyName("privacidad")] Privacidad Privacidad,
    [property: JsonPropertyName("nominal")] bool Nominal,
    [property: JsonPropertyName("objetivos")] DominioPorObjetivo Objetivos,
    [property: JsonPropertyName("avisos")] IReadOnlyList<AvisoDeReporte> Avisos,
    [property: JsonPropertyName("servidor_en")] long ServidorEn,
    [property: JsonPropertyName("grupo")] GrupoResumido Grupo,
    [property: JsonPropertyName("plantilla")] PlantillaDeBoletin Plantilla,
    [property: JsonPropertyName("boletines")] IReadOnlyList<ModeloDeBoletin> Boletines,
    [property: JsonPropertyName("totales")] TotalesDeBoletines Totales);

public sealed record FuenteDeAgregados(
    [property: JsonPropertyName("fuente")] string Fuente,
    [property: JsonPropertyName("marca")] long Marca,
    [property: JsonPropertyName("ultima")] long Ultima,
    [property: JsonPropertyName("pendientes")] bool Pendientes,
    [property: JsonPropertyName("fallos_seguidos")] int FallosSeguidos);

public sealed record GruposDeAgregados(
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("desactualizados")] int Desactualizados);

public sealed record ReconstruccionDeAgregados(
    [property: JsonPropertyName("en_curso")] bool EnCurso,
    [property: JsonPropertyName("ultima_en")] long? UltimaEn,
    [property: JsonPropertyName("por")] string? Por,
    [property: JsonPropertyName("error")] string? Error);

public sealed record EstadoDeAgregados(
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("corte_en")] long CorteEn,
    [property: JsonPropertyName("antiguedad_ms")] long AntiguedadMs,
    [property: JsonPropertyName("clase_en_curso")] bool ClaseEnCurso,
    [property: JsonPropertyName("fuentes")] IReadOnlyList<FuenteDeAgregados> Fuentes,
    [property: JsonPropertyName("grupos")] GruposDeAgregados Grupos,
    [property: JsonPropertyName("clases")] int Clases,
    [property: JsonPropertyName("reconstruccion")] ReconstruccionDeAgregados Reconstruccion,
    [property: JsonPropertyName("actualizada_en")] long? ActualizadaEn,
    [property: JsonPropertyName("puede_reconstruir")] bool PuedeReconstruir,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

public sealed record ResultadoDeActualizacion(
    [property: JsonPropertyName("eventos")] int? Eventos,
    [property: JsonPropertyName("grupos")] int? Grupos,
    [property: JsonPropertyName("clases_limpiadas")] int? ClasesLimpiadas,
    [property: JsonPropertyName("exportaciones_caducadas")] int? ExportacionesCaducadas,
    [property: JsonPropertyName("omitido")] string? Omitido);

public sealed record ResultadoDeReconstruccion(
    [property: JsonPropertyName("eventos")] int? Eventos,
    [property: JsonPropertyName("grupos")] int Grupos,
    [property: JsonPropertyName("grupos_fallidos")] IReadOnlyList<string> GruposFallidos,
    [property: JsonPropertyName("borradas")] IReadOnlyDictionary<string, int> Borradas,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

// ------------------------------------------------------------------------------------------------ exportar a archivo (FUN-146)

/// <summary>La política del administrador que la hoja de confirmación respeta: si los extraíbles están cerrados y si hay que elegir una razón de la lista.</summary>
public sealed record PoliticaDeExportacion(
    [property: JsonPropertyName("extraibles_permitidos")] bool ExtraiblesPermitidos,
    [property: JsonPropertyName("exigir_razon")] bool ExigirRazon,
    [property: JsonPropertyName("razones")] IReadOnlyList<RazonDeExportacion> Razones);

/// <summary>El alcance declarado ANTES de confirmar: qué se va a guardar, a cuántos alumnos toca, si lleva nombres y hasta qué instante llegan los datos.</summary>
public sealed record AlcanceDeExportacion(
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("formato")] string Formato,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("alumnos")] int Alumnos,
    [property: JsonPropertyName("filas")] int Filas,
    [property: JsonPropertyName("incluye")] IReadOnlyList<string> Incluye,
    [property: JsonPropertyName("nominal")] bool Nominal,
    [property: JsonPropertyName("umbral_aplicado")] bool UmbralAplicado,
    [property: JsonPropertyName("texto_alcance")] string TextoAlcance,
    [property: JsonPropertyName("advertencia")] string Advertencia,
    [property: JsonPropertyName("corte")] CorteDeDatos Corte,
    [property: JsonPropertyName("privacidad")] Privacidad Privacidad,
    [property: JsonPropertyName("nombre_sugerido")] string NombreSugerido,
    [property: JsonPropertyName("formatos")] IReadOnlyList<string> Formatos,
    [property: JsonPropertyName("politica")] PoliticaDeExportacion Politica,
    [property: JsonPropertyName("servidor_en")] long ServidorEn,
    [property: JsonPropertyName("formato_de_entrega")] string? FormatoDeEntrega = null,
    [property: JsonPropertyName("archivos")] int Archivos = 1,
    [property: JsonPropertyName("plantilla")] string? Plantilla = null)
{
    /// <summary>Lo que se va a escribir: un zip cuando va un archivo por estudiante; si no, el formato pedido.</summary>
    public bool Empaquetado => FormatoDeEntrega == FormatosDeExportacion.Zip;
}

public sealed record IntentoDeExportacion(
    [property: JsonPropertyName("en")] long En,
    [property: JsonPropertyName("resultado")] string Resultado,
    [property: JsonPropertyName("motivo")] string Motivo,
    [property: JsonPropertyName("destino_tipo")] string DestinoTipo);

/// <summary>Una exportación tal como la tiene el nodo: autorizada (sin confirmar), entregada o caducada. Nunca lleva la ruta donde quedó.</summary>
public sealed record Exportacion(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("formato")] string Formato,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("nominal")] bool Nominal,
    [property: JsonPropertyName("umbral_aplicado")] bool UmbralAplicado,
    [property: JsonPropertyName("filas")] int Filas,
    [property: JsonPropertyName("bytes")] long Bytes,
    [property: JsonPropertyName("huella")] string Huella,
    [property: JsonPropertyName("nombre_archivo")] string NombreArchivo,
    [property: JsonPropertyName("corte_en")] long CorteEn,
    [property: JsonPropertyName("autorizada_en")] long AutorizadaEn,
    [property: JsonPropertyName("expira_en")] long ExpiraEn,
    [property: JsonPropertyName("confirmada_en")] long? ConfirmadaEn,
    [property: JsonPropertyName("destino_autorizado")] string DestinoAutorizado,
    [property: JsonPropertyName("destino_tipo")] string? DestinoTipo,
    [property: JsonPropertyName("razon_codigo")] string? RazonCodigo,
    [property: JsonPropertyName("intentos")] IReadOnlyList<IntentoDeExportacion> Intentos);

public sealed record RespuestaDeExportacion(
    [property: JsonPropertyName("exportacion")] Exportacion Exportacion,
    [property: JsonPropertyName("reintento")] bool? Reintento,
    [property: JsonPropertyName("servidor_en")] long? ServidorEn);

public sealed record ListaDeExportaciones(
    [property: JsonPropertyName("exportaciones")] IReadOnlyList<Exportacion> Exportaciones,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

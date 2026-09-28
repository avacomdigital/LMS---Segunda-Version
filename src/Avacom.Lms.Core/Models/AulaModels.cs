using System.Text.Json;
using System.Text.Json.Serialization;

namespace Avacom.Lms.Core.Models;

// Contratos de /api/aula/ (MOD-007 · Classroom Engine). Los nombres JSON son los del
// backend (snake_case); los códigos de la biblioteca viajan en `tipo` y el control
// MAUI que los pinta en `componente`. Ningún tipo de aquí contiene una clave de
// corrección: el backend las elimina para todos los roles.

public sealed record Tramo([property: JsonPropertyName("texto")] string Texto, [property: JsonPropertyName("negrita")] bool Negrita);

public sealed record NodoClasificacion(
    [property: JsonPropertyName("codigo")] string? Codigo,
    [property: JsonPropertyName("nombre")] string? Nombre,
    [property: JsonPropertyName("orden")] int? Orden);

public sealed record Clasificacion(
    [property: JsonPropertyName("pais")] string? Pais,
    [property: JsonPropertyName("idioma")] string? Idioma,
    [property: JsonPropertyName("nivel")] NodoClasificacion? Nivel,
    [property: JsonPropertyName("grado")] NodoClasificacion? Grado,
    [property: JsonPropertyName("asignatura")] NodoClasificacion? Asignatura,
    [property: JsonPropertyName("tema")] NodoClasificacion? Tema)
{
    public string Resumen => string.Join(" · ", new[] { Nivel?.Nombre, Grado?.Nombre, Tema?.Nombre }.Where(x => !string.IsNullOrWhiteSpace(x)));
}

public sealed record FichaCurso(
    [property: JsonPropertyName("fuente")] string? Fuente,
    [property: JsonPropertyName("esquema")] string? Esquema,
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("version")] string? Version,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("subtitulo")] string? Subtitulo,
    [property: JsonPropertyName("descripcion")] string? Descripcion,
    [property: JsonPropertyName("idioma")] string? Idioma,
    [property: JsonPropertyName("clasificacion")] Clasificacion? Clasificacion,
    [property: JsonPropertyName("duracion_estimada_min")] int? DuracionEstimadaMin,
    [property: JsonPropertyName("modos")] IReadOnlyList<string>? Modos,
    [property: JsonPropertyName("portada_url")] string? PortadaUrl,
    [property: JsonPropertyName("lecciones")] int Lecciones,
    [property: JsonPropertyName("objetos")] int Objetos,
    [property: JsonPropertyName("medios")] int? Medios)
{
    public string Detalle => string.Join(" · ", new[]
    {
        Clasificacion?.Resumen,
        $"{Lecciones} lección(es)",
        DuracionEstimadaMin is > 0 ? $"{DuracionEstimadaMin} min" : null,
    }.Where(x => !string.IsNullOrWhiteSpace(x)));
}

public sealed record AsignaturaAula(
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("cursos")] IReadOnlyList<FichaCurso> Cursos);

public sealed record CatalogoAula(
    [property: JsonPropertyName("fuente")] string? Fuente,
    [property: JsonPropertyName("disponible")] bool Disponible,
    [property: JsonPropertyName("asignaturas")] IReadOnlyList<AsignaturaAula> Asignaturas,
    [property: JsonPropertyName("cursos")] IReadOnlyList<FichaCurso> Cursos);

public sealed record SimulacionAula(
    [property: JsonPropertyName("entrada")] string? Entrada,
    [property: JsonPropertyName("proveedor")] string? Proveedor,
    [property: JsonPropertyName("tecnologia")] string? Tecnologia,
    [property: JsonPropertyName("orientacion")] string? Orientacion,
    [property: JsonPropertyName("ajustes")] IReadOnlyList<string>? Ajustes,
    [property: JsonPropertyName("destinos")] IReadOnlyList<string>? Destinos,
    [property: JsonPropertyName("ancho_diseno")] int? AnchoDiseno,
    [property: JsonPropertyName("alto_diseno")] int? AltoDiseno)
{
    public bool BloqueaRed => Ajustes?.Contains("block_network") == true;
    public bool EscalaAlViewport => Ajustes?.Contains("scale_to_fit") == true;
    public bool SirveEnTableta => Destinos is null || Destinos.Count == 0 || Destinos.Contains("tablet");
    public bool Horizontal => string.Equals(Orientacion, "landscape", StringComparison.OrdinalIgnoreCase);
}

public sealed record LicenciaAula(
    [property: JsonPropertyName("tipo")] string? Tipo,
    [property: JsonPropertyName("atribucion")] string? Atribucion,
    [property: JsonPropertyName("fuente_url")] string? FuenteUrl);

public sealed record MedioAula(
    [property: JsonPropertyName("media_ref")] string MediaRef,
    [property: JsonPropertyName("clase")] string? Clase,
    [property: JsonPropertyName("componente")] string? Componente,
    [property: JsonPropertyName("titulo")] string? Titulo,
    [property: JsonPropertyName("mime")] string? Mime,
    [property: JsonPropertyName("url")] string? Url,
    [property: JsonPropertyName("base_url")] string? BaseUrl,
    [property: JsonPropertyName("ancho")] int? Ancho,
    [property: JsonPropertyName("alto")] int? Alto,
    [property: JsonPropertyName("duracion_seg")] double? DuracionSeg,
    [property: JsonPropertyName("paginas")] int? Paginas,
    [property: JsonPropertyName("texto_alternativo")] string? TextoAlternativo,
    [property: JsonPropertyName("subtitulos_url")] string? SubtitulosUrl,
    [property: JsonPropertyName("transcripcion_url")] string? TranscripcionUrl,
    [property: JsonPropertyName("simulacion")] SimulacionAula? Simulacion,
    [property: JsonPropertyName("licencia")] LicenciaAula? Licencia,
    [property: JsonPropertyName("ausente")] bool Ausente);

public sealed record BloqueAula(
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("componente")] string Componente,
    [property: JsonPropertyName("texto")] string? Texto,
    [property: JsonPropertyName("nivel")] int? Nivel,
    [property: JsonPropertyName("estilo")] string? Estilo,
    [property: JsonPropertyName("tramos")] IReadOnlyList<Tramo>? Tramos,
    [property: JsonPropertyName("ordenada")] bool? Ordenada,
    [property: JsonPropertyName("items")] IReadOnlyList<string>? Items,
    [property: JsonPropertyName("items_tramos")] IReadOnlyList<IReadOnlyList<Tramo>>? ItemsTramos,
    [property: JsonPropertyName("media_ref")] string? MediaRef,
    [property: JsonPropertyName("url")] string? Url,
    [property: JsonPropertyName("pie")] string? Pie,
    [property: JsonPropertyName("mime")] string? Mime,
    [property: JsonPropertyName("titulo")] string? Titulo,
    [property: JsonPropertyName("texto_alternativo")] string? TextoAlternativo,
    [property: JsonPropertyName("ancho")] int? Ancho,
    [property: JsonPropertyName("alto")] int? Alto,
    [property: JsonPropertyName("desde_seg")] double? DesdeSeg,
    [property: JsonPropertyName("hasta_seg")] double? HastaSeg,
    [property: JsonPropertyName("autoplay")] bool? Autoplay,
    [property: JsonPropertyName("duracion_seg")] double? DuracionSeg,
    [property: JsonPropertyName("subtitulos_url")] string? SubtitulosUrl,
    [property: JsonPropertyName("transcripcion_url")] string? TranscripcionUrl,
    [property: JsonPropertyName("desde_pagina")] int? DesdePagina,
    [property: JsonPropertyName("hasta_pagina")] int? HastaPagina,
    [property: JsonPropertyName("paginas")] int? Paginas,
    [property: JsonPropertyName("url_pagina_inicial")] string? UrlPaginaInicial);

public sealed record NotasDocente(
    [property: JsonPropertyName("summary")] string? Summary,
    [property: JsonPropertyName("tips")] IReadOnlyList<string>? Tips,
    [property: JsonPropertyName("timing")] string? Timing,
    [property: JsonPropertyName("commonMistakes")] IReadOnlyList<string>? CommonMistakes,
    [property: JsonPropertyName("differentiation")] string? Differentiation,
    [property: JsonPropertyName("materials")] IReadOnlyList<string>? Materials)
{
    public IEnumerable<string> Lineas()
    {
        if (!string.IsNullOrWhiteSpace(Summary)) yield return Summary!;
        if (!string.IsNullOrWhiteSpace(Timing)) yield return $"Tiempos: {Timing}";
        foreach (var t in Tips ?? []) yield return $"Consejo: {t}";
        foreach (var e in CommonMistakes ?? []) yield return $"Error frecuente: {e}";
        if (!string.IsNullOrWhiteSpace(Differentiation)) yield return $"Diferenciación: {Differentiation}";
        foreach (var m in Materials ?? []) yield return $"Material: {m}";
    }
}

public sealed record UnidadAula(
    [property: JsonPropertyName("unidad_ref")] string UnidadRef,
    [property: JsonPropertyName("indice")] int Indice,
    [property: JsonPropertyName("titulo")] string? Titulo,
    [property: JsonPropertyName("duracion_seg")] int? DuracionSeg,
    [property: JsonPropertyName("bloques")] IReadOnlyList<BloqueAula> Bloques,
    [property: JsonPropertyName("notas_docente")] NotasDocente? NotasDocente);

public sealed record OpcionAula(
    [property: JsonPropertyName("opcion_ref")] string OpcionRef,
    [property: JsonPropertyName("texto")] string? Texto,
    [property: JsonPropertyName("tramos")] IReadOnlyList<Tramo>? Tramos);

public sealed record ElementoAula([property: JsonPropertyName("ref")] string Ref, [property: JsonPropertyName("texto")] string? Texto);

public sealed record EspacioAula(
    [property: JsonPropertyName("espacio_ref")] string EspacioRef,
    [property: JsonPropertyName("modo_entrada")] string? ModoEntrada,
    [property: JsonPropertyName("opciones")] IReadOnlyList<string>? Opciones);

public sealed record PreguntaAula(
    [property: JsonPropertyName("pregunta_ref")] string PreguntaRef,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("componente")] string Componente,
    [property: JsonPropertyName("enunciado")] string? Enunciado,
    [property: JsonPropertyName("enunciado_tramos")] IReadOnlyList<Tramo>? EnunciadoTramos,
    [property: JsonPropertyName("puntos")] int? Puntos,
    [property: JsonPropertyName("dificultad")] int? Dificultad,
    [property: JsonPropertyName("duracion_estimada_seg")] int? DuracionEstimadaSeg,
    [property: JsonPropertyName("credito_parcial")] bool CreditoParcial,
    [property: JsonPropertyName("permite_varias")] bool? PermiteVarias,
    [property: JsonPropertyName("opciones")] IReadOnlyList<OpcionAula>? Opciones,
    [property: JsonPropertyName("plantilla")] string? Plantilla,
    [property: JsonPropertyName("espacios")] IReadOnlyList<EspacioAula>? Espacios,
    [property: JsonPropertyName("izquierda")] IReadOnlyList<ElementoAula>? Izquierda,
    [property: JsonPropertyName("derecha")] IReadOnlyList<ElementoAula>? Derecha,
    [property: JsonPropertyName("elementos")] IReadOnlyList<ElementoAula>? Elementos,
    [property: JsonPropertyName("formato_respuesta")] string? FormatoRespuesta,
    [property: JsonPropertyName("longitud_maxima")] int? LongitudMaxima)
{
    public string TipoLegible => Componente switch
    {
        "opcion_multiple" => "Opción múltiple",
        "verdadero_falso" => "Verdadero o falso",
        "completar" => "Completar",
        "relacionar" => "Relacionar",
        "ordenar" => "Ordenar",
        "abierta" => "Respuesta abierta",
        _ => Tipo,
    };
}

public sealed record AjustesActividad(
    [property: JsonPropertyName("retroalimentacion")] string? Retroalimentacion,
    [property: JsonPropertyName("intentos_permitidos")] int? IntentosPermitidos,
    [property: JsonPropertyName("barajar_preguntas")] bool BarajarPreguntas,
    [property: JsonPropertyName("barajar_opciones")] bool BarajarOpciones);

public sealed record ObjetoAula(
    [property: JsonPropertyName("objeto_ref")] string ObjetoRef,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("componente")] string Componente,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("modos")] IReadOnlyList<string>? Modos,
    [property: JsonPropertyName("tema_ref")] string? TemaRef,
    [property: JsonPropertyName("duracion_estimada_seg")] int? DuracionEstimadaSeg,
    [property: JsonPropertyName("fuera_de_alcance")] bool FueraDeAlcance,
    [property: JsonPropertyName("modulo")] string? Modulo,
    [property: JsonPropertyName("notas_docente")] NotasDocente? NotasDocente,
    [property: JsonPropertyName("total_unidades")] int? TotalUnidades,
    [property: JsonPropertyName("laminas")] IReadOnlyList<UnidadAula>? Laminas,
    [property: JsonPropertyName("paginas")] IReadOnlyList<UnidadAula>? Paginas,
    [property: JsonPropertyName("simulacion")] MedioAula? Simulacion,
    [property: JsonPropertyName("url_lanzamiento")] string? UrlLanzamiento,
    [property: JsonPropertyName("parametros_lanzamiento")] Dictionary<string, JsonElement>? ParametrosLanzamiento,
    [property: JsonPropertyName("objetivo_aprendizaje")] string? ObjetivoAprendizaje,
    [property: JsonPropertyName("instrucciones")] string? Instrucciones,
    [property: JsonPropertyName("instrucciones_tramos")] IReadOnlyList<Tramo>? InstruccionesTramos,
    [property: JsonPropertyName("pasos")] IReadOnlyList<string>? Pasos,
    [property: JsonPropertyName("preguntas_guia")] IReadOnlyList<string>? PreguntasGuia,
    [property: JsonPropertyName("ajustes")] AjustesActividad? Ajustes,
    [property: JsonPropertyName("preguntas")] IReadOnlyList<PreguntaAula>? Preguntas,
    [property: JsonPropertyName("puntos_totales")] int? PuntosTotales,
    [property: JsonPropertyName("total_preguntas_banco")] int? TotalPreguntasBanco)
{
    public IReadOnlyList<UnidadAula> Unidades => Laminas ?? Paginas ?? [];
    public bool EsActividad => Componente == "actividad";
    public string ComponenteLegible => Componente switch
    {
        "presentacion" => "Presentación",
        "lectura" => "Lectura",
        "laboratorio_web" => "Laboratorio",
        "actividad" => "Actividad",
        "examen" => "Examen",
        _ => Tipo,
    };
    public string DuracionTexto => DuracionEstimadaSeg is > 0 ? $"~{Math.Max(1, DuracionEstimadaSeg.Value / 60)} min" : string.Empty;
}

public sealed record LeccionAula(
    [property: JsonPropertyName("leccion_ref")] string LeccionRef,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("resumen")] string? Resumen,
    [property: JsonPropertyName("objetivos")] IReadOnlyList<string>? Objetivos,
    [property: JsonPropertyName("duracion_estimada_min")] int? DuracionEstimadaMin,
    [property: JsonPropertyName("modos")] IReadOnlyList<string>? Modos,
    [property: JsonPropertyName("objetos")] IReadOnlyList<ObjetoAula>? Objetos,
    [property: JsonPropertyName("notas_docente")] NotasDocente? NotasDocente)
{
    public IReadOnlyList<ObjetoAula> ObjetosDelAula => (Objetos ?? []).Where(o => !o.FueraDeAlcance).ToList();
    public bool SoloExamen => Objetos is { Count: > 0 } && Objetos.All(o => o.FueraDeAlcance);
}

public sealed record ResumenVista(
    [property: JsonPropertyName("lecciones")] int Lecciones,
    [property: JsonPropertyName("objetos")] int Objetos,
    [property: JsonPropertyName("medios")] int Medios,
    [property: JsonPropertyName("preguntas")] int Preguntas);

public sealed record VistaCurso(
    [property: JsonPropertyName("fuente")] string? Fuente,
    [property: JsonPropertyName("esquema")] string? Esquema,
    [property: JsonPropertyName("curso_ref")] string CursoRef,
    [property: JsonPropertyName("version")] string? Version,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("subtitulo")] string? Subtitulo,
    [property: JsonPropertyName("descripcion")] string? Descripcion,
    [property: JsonPropertyName("idioma")] string? Idioma,
    [property: JsonPropertyName("clasificacion")] Clasificacion? Clasificacion,
    [property: JsonPropertyName("duracion_estimada_min")] int? DuracionEstimadaMin,
    [property: JsonPropertyName("modos")] IReadOnlyList<string>? Modos,
    [property: JsonPropertyName("portada_url")] string? PortadaUrl,
    [property: JsonPropertyName("rol")] string? Rol,
    [property: JsonPropertyName("medios")] IReadOnlyList<MedioAula>? Medios,
    [property: JsonPropertyName("lecciones")] IReadOnlyList<LeccionAula> Lecciones,
    [property: JsonPropertyName("resumen")] ResumenVista? Resumen,
    [property: JsonPropertyName("notas_docente")] NotasDocente? NotasDocente)
{
    public ObjetoAula? Objeto(string objetoRef) => Lecciones.SelectMany(l => l.Objetos ?? []).FirstOrDefault(o => o.ObjetoRef == objetoRef);
    public LeccionAula? Leccion(string leccionRef) => Lecciones.FirstOrDefault(l => l.LeccionRef == leccionRef);
}

public sealed record ObjetoSuelto(
    [property: JsonPropertyName("curso")] FichaCurso? Curso,
    [property: JsonPropertyName("leccion")] LeccionAula? Leccion,
    [property: JsonPropertyName("objeto")] ObjetoAula Objeto);

// ------------------------------------------------------------------ sesión

/// <summary>Lo que el profesor tiene seleccionado para proyectar: un objeto y, si aplica, su lámina o página. No es un lanzamiento.</summary>
public sealed record SelectorAula(
    [property: JsonPropertyName("id")] string? Id,
    [property: JsonPropertyName("curso_ref")] string? CursoRef,
    [property: JsonPropertyName("leccion_ref")] string? LeccionRef,
    [property: JsonPropertyName("objeto_ref")] string? ObjetoRef,
    [property: JsonPropertyName("objeto_tipo")] string? ObjetoTipo,
    [property: JsonPropertyName("unidad_ref")] string? UnidadRef,
    [property: JsonPropertyName("unidad_indice")] int? UnidadIndice,
    [property: JsonPropertyName("media_ref")] string? MediaRef,
    [property: JsonPropertyName("rotulo")] string? Rotulo,
    [property: JsonPropertyName("declarado_en")] long DeclaradoEn);

public sealed record ParticipanteAula(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("persona_id")] string PersonaId,
    [property: JsonPropertyName("persona_rotulo")] string? PersonaRotulo,
    [property: JsonPropertyName("dispositivo")] string? Dispositivo,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("admision_nominal")] bool AdmisionNominal,
    [property: JsonPropertyName("ingreso")] long Ingreso,
    [property: JsonPropertyName("ultimo_latido_en")] long? UltimoLatidoEn,
    // MOD-009: la tableta reconocida por el inventario y si está bloqueada (no recibe lanzamientos).
    [property: JsonPropertyName("dispositivo_id")] string? DispositivoId = null,
    [property: JsonPropertyName("dispositivo_bloqueado")] bool? DispositivoBloqueado = null)
{
    public string Nombre => string.IsNullOrWhiteSpace(PersonaRotulo) ? PersonaId : PersonaRotulo!;
    public bool TieneTableta => !string.IsNullOrWhiteSpace(DispositivoId);
    public bool TabletaBloqueada => DispositivoBloqueado == true;
    public string Iniciales => Identidad.InicialesDe(Nombre);
    public string EstadoLegible => Estado switch
    {
        "esperando" => "Esperando",
        "conectado" => "Conectado",
        "reconectando" => "Reconectando",
        "salio" => "Salió",
        "rechazado" => "Rechazado",
        "expulsado" => "Expulsado",
        _ => Estado,
    };
    public bool Admitido => Estado is "conectado" or "reconectando";
}

public sealed record ConteoSesion(
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("conectados")] int Conectados,
    [property: JsonPropertyName("reconectando")] int Reconectando,
    [property: JsonPropertyName("esperando")] int Esperando,
    [property: JsonPropertyName("salieron")] int Salieron);

public sealed record EntregaDetalle(
    [property: JsonPropertyName("participante_id")] string ParticipanteId,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("confirmada_en")] long? ConfirmadaEn);

public sealed record EntregasAula(
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("entregadas")] int Entregadas,
    [property: JsonPropertyName("pendientes")] int Pendientes,
    [property: JsonPropertyName("fallidas")] int Fallidas,
    [property: JsonPropertyName("detalle")] IReadOnlyList<EntregaDetalle>? Detalle);

public sealed record DistribucionAula(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("clase")] string Clase,
    [property: JsonPropertyName("curso_ref")] string? CursoRef,
    [property: JsonPropertyName("leccion_ref")] string? LeccionRef,
    [property: JsonPropertyName("objeto_ref")] string? ObjetoRef,
    [property: JsonPropertyName("objeto_tipo")] string? ObjetoTipo,
    [property: JsonPropertyName("media_ref")] string? MediaRef,
    [property: JsonPropertyName("rotulo")] string? Rotulo,
    [property: JsonPropertyName("alcance")] string? Alcance,
    [property: JsonPropertyName("disponible_estudio")] bool DisponibleEstudio,
    [property: JsonPropertyName("abierta_en")] long AbiertaEn,
    [property: JsonPropertyName("cerrada_en")] long? CerradaEn,
    [property: JsonPropertyName("abierta")] bool? Abierta,
    [property: JsonPropertyName("entregas")] EntregasAula? Entregas,
    // Sólo en el estado de la tableta: la entrega de este participante.
    [property: JsonPropertyName("entrega")] string? Entrega,
    // El lanzamiento (segunda versión del modelo): a quién llegó, a quién dejó fuera por tableta bloqueada y con qué reglas.
    [property: JsonPropertyName("destinatarios")] IReadOnlyList<string>? Destinatarios = null,
    [property: JsonPropertyName("excluidos_bloqueados")] IReadOnlyList<string>? ExcluidosBloqueados = null,
    [property: JsonPropertyName("intentos_permitidos")] int? IntentosPermitidos = null,
    [property: JsonPropertyName("tiempo_limite_seg")] int? TiempoLimiteSeg = null)
{
    public bool EstaAbierta => Abierta ?? CerradaEn is null;
    public string EntregasTexto => Entregas is null ? string.Empty : $"{Entregas.Entregadas} de {Entregas.Total} entregadas";
    public int Excluidos => ExcluidosBloqueados?.Count ?? 0;
    public string ReglasTexto => string.Join(" · ", new[]
    {
        IntentosPermitidos is { } i ? (i == 1 ? "1 intento" : $"{i} intentos") : null,
        TiempoLimiteSeg is { } t ? (t % 60 == 0 ? $"{t / 60} min" : $"{t} s") : null,
    }.Where(x => x is not null));
}

public sealed record AvisoAula(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("participante_id")] string? ParticipanteId,
    [property: JsonPropertyName("texto")] string Texto,
    [property: JsonPropertyName("enviado_en")] long EnviadoEn);

public sealed record ResumenSesion(
    [property: JsonPropertyName("participantes")] int Participantes,
    [property: JsonPropertyName("conectados_maximo")] int ConectadosMaximo,
    [property: JsonPropertyName("admitidos_nominal")] int AdmitidosNominal,
    [property: JsonPropertyName("selectores")] int Selectores,
    [property: JsonPropertyName("distribuciones")] int Distribuciones,
    [property: JsonPropertyName("actividades")] int Actividades,
    [property: JsonPropertyName("avisos")] int Avisos,
    [property: JsonPropertyName("pendientes")] int Pendientes,
    [property: JsonPropertyName("duracion_ms")] long DuracionMs,
    [property: JsonPropertyName("origen_cierre")] string? OrigenCierre)
{
    public string DuracionTexto => DuracionMs < 60_000 ? $"{DuracionMs / 1000} s" : $"{DuracionMs / 60_000} min";
}

public sealed record SesionDeClase(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("activa")] bool Activa,
    [property: JsonPropertyName("codigo_union")] string? CodigoUnion,
    [property: JsonPropertyName("via_origen")] string? ViaOrigen,
    [property: JsonPropertyName("fuente_curso")] string? FuenteCurso,
    [property: JsonPropertyName("curso_ref")] string? CursoRef,
    [property: JsonPropertyName("curso_version")] string? CursoVersion,
    [property: JsonPropertyName("curso_rotulo")] string? CursoRotulo,
    [property: JsonPropertyName("leccion_ref")] string? LeccionRef,
    [property: JsonPropertyName("leccion_rotulo")] string? LeccionRotulo,
    [property: JsonPropertyName("profesor_id")] string? ProfesorId,
    [property: JsonPropertyName("profesor_rotulo")] string? ProfesorRotulo,
    [property: JsonPropertyName("iniciada_en")] long? IniciadaEn,
    [property: JsonPropertyName("finalizada_en")] long? FinalizadaEn,
    [property: JsonPropertyName("selector")] SelectorAula? Selector,
    [property: JsonPropertyName("seguimiento")] bool Seguimiento,
    [property: JsonPropertyName("pantallas_bloqueadas")] bool PantallasBloqueadas,
    [property: JsonPropertyName("participantes")] IReadOnlyList<ParticipanteAula>? Participantes,
    [property: JsonPropertyName("conteo")] ConteoSesion? Conteo,
    [property: JsonPropertyName("distribuciones")] IReadOnlyList<DistribucionAula>? Distribuciones,
    [property: JsonPropertyName("avisos")] IReadOnlyList<AvisoAula>? Avisos,
    [property: JsonPropertyName("resumen")] ResumenSesion? Resumen,
    [property: JsonPropertyName("servidor_en")] long ServidorEn)
{
    public DistribucionAula? ActividadAbierta => Distribuciones?.LastOrDefault(d => d.Clase == "actividad" && d.EstaAbierta);

    /// <summary>El último recurso enviado a las tabletas que sigue abierto (CAP-040: lanzar un recurso, no sólo una actividad).</summary>
    public DistribucionAula? RecursoAbierto => Distribuciones?.LastOrDefault(d => d.Clase == "recurso" && d.EstaAbierta);
}

public sealed record SesionTableta(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("fuente_curso")] string? FuenteCurso,
    [property: JsonPropertyName("curso_ref")] string? CursoRef,
    [property: JsonPropertyName("curso_rotulo")] string? CursoRotulo,
    [property: JsonPropertyName("leccion_ref")] string? LeccionRef,
    [property: JsonPropertyName("leccion_rotulo")] string? LeccionRotulo,
    [property: JsonPropertyName("grupo_rotulo")] string? GrupoRotulo,
    [property: JsonPropertyName("profesor_rotulo")] string? ProfesorRotulo);

public sealed record EstadoTableta(
    [property: JsonPropertyName("sesion")] SesionTableta Sesion,
    [property: JsonPropertyName("activa")] bool Activa,
    [property: JsonPropertyName("participante")] ParticipanteAula? Participante,
    [property: JsonPropertyName("selector")] SelectorAula? Selector,
    [property: JsonPropertyName("seguimiento")] bool Seguimiento,
    [property: JsonPropertyName("pantallas_bloqueadas")] bool PantallasBloqueadas,
    [property: JsonPropertyName("pendientes")] IReadOnlyList<DistribucionAula>? Pendientes,
    [property: JsonPropertyName("avisos")] IReadOnlyList<AvisoAula>? Avisos,
    [property: JsonPropertyName("servidor_en")] long ServidorEn,
    [property: JsonPropertyName("intervalo_sondeo_ms")] int? IntervaloSondeoMs,
    [property: JsonPropertyName("nuevo")] bool? Nuevo,
    [property: JsonPropertyName("en_espera")] bool? EnEspera);

// ---------------------------------------------------------------- solicitudes

public sealed record IniciarSesionSolicitud(
    string Via, string? CursoRef, string? LeccionRef, string? ObjetoRef, string Fuente,
    string ProfesorId, string? ProfesorRotulo, string Superficie);

/// <summary>El lanzamiento: a todo el grupo (<c>Alcance</c> nulo o «grupo») o a una selección de participantes, con sus reglas opcionales.</summary>
public sealed record DistribuirSolicitud(string Clase, string? ObjetoRef, string? MediaRef, string? Rotulo, bool DisponibleEstudio,
                                         string? Alcance = null, IReadOnlyList<string>? Participantes = null,
                                         int? IntentosPermitidos = null, int? TiempoLimiteSeg = null);

// ------------------------------------------------------- dispositivos (MOD-009)

public sealed record SesionAbiertaDispositivo(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("iniciada_en")] long IniciadaEn);

/// <summary>Una tableta del inventario del aula con su estado en vivo (<c>/api/dispositivos/</c>).</summary>
public sealed record DispositivoAula(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("identificador_hw")] string? IdentificadorHw,
    [property: JsonPropertyName("nombre")] string? Nombre,
    [property: JsonPropertyName("tipo")] string? Tipo,
    [property: JsonPropertyName("plataforma")] string? Plataforma,
    [property: JsonPropertyName("version_app")] string? VersionApp,
    [property: JsonPropertyName("activo")] bool Activo,
    [property: JsonPropertyName("bloqueado")] bool Bloqueado,
    [property: JsonPropertyName("en_linea")] bool EnLinea,
    [property: JsonPropertyName("registrado_en")] long RegistradoEn,
    [property: JsonPropertyName("ultimo_latido_en")] long? UltimoLatidoEn,
    [property: JsonPropertyName("sesion_abierta")] SesionAbiertaDispositivo? SesionAbierta)
{
    public string NombreVisible => string.IsNullOrWhiteSpace(Nombre) ? IdentificadorHw ?? Id : Nombre!;
    public string PlataformaLegible => Plataforma switch
    {
        "android" => "Android",
        "windows" => "Windows",
        _ => "Plataforma sin declarar",
    };
    public string EstadoLegible => !Activo ? "Retirada" : Bloqueado ? "Bloqueada" : EnLinea ? "En línea" : "Sin señal";
    public string Detalle => string.Join(" · ", new[]
    {
        PlataformaLegible,
        string.IsNullOrWhiteSpace(VersionApp) ? null : $"app {VersionApp}",
        SesionAbierta is { } s ? $"en uso por {s.AlumnoId}" : "libre",
    }.Where(x => x is not null));
}

/// <summary>Un error del backend de aula con su código de negocio (`sesion_activa_existente`, `actividades_abiertas`…).</summary>
public sealed record ErrorAula(int Estado, string? Codigo, string Detalle, string? Sugerencia, JsonElement? Extra)
{
    public string? Texto(string clave) =>
        Extra is { ValueKind: JsonValueKind.Object } e && e.TryGetProperty(clave, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
}

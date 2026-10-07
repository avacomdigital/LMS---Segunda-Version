using System.Text.Json;
using System.Text.Json.Serialization;

namespace Avacom.Lms.Core.Models;

// Contratos de /api/aula/ (MOD-007 · Classroom Engine). Los nombres JSON son los del
// backend (snake_case); los códigos de la biblioteca viajan en `tipo` y el control
// MAUI que los pinta en `componente`. Ningún tipo de aquí contiene una clave de
// corrección: el backend las elimina para todos los roles.

/// <summary>
/// Un tramo del «AVACOM Markdown» de RichText (course.schema.json): <c>**negrita**</c>, <c>*cursiva*</c> y
/// matemática en línea <c>$…$</c>, que el backend entrega ya legible («1/3 × 2») y marcada con <see cref="Matematica"/>.
/// Los dos últimos son opcionales en el JSON: un backend anterior sólo manda <c>negrita</c>.
/// </summary>
public sealed record Tramo(
    [property: JsonPropertyName("texto")] string Texto,
    [property: JsonPropertyName("negrita")] bool Negrita,
    [property: JsonPropertyName("cursiva")] bool Cursiva = false,
    [property: JsonPropertyName("matematica")] bool Matematica = false);

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
    [property: JsonPropertyName("medios")] int? Medios,
    [property: JsonPropertyName("no_disponible")] NoDisponibleAula? NoDisponible = null)
{
    public string Detalle => NoDisponible is not null
        ? "No disponible · el paquete no pasa la verificación de AVACOM Contenido"
        : string.Join(" · ", new[]
        {
            Clasificacion?.Resumen,
            $"{Lecciones} lección(es)",
            DuracionEstimadaMin is > 0 ? $"{DuracionEstimadaMin} min" : null,
        }.Where(x => !string.IsNullOrWhiteSpace(x)));
}

/// <summary>La biblioteca lista el curso pero no lo sirve (paquete que no pasa su verificación, E-PKG-*).</summary>
public sealed record NoDisponibleAula(
    [property: JsonPropertyName("codigo")] string? Codigo,
    [property: JsonPropertyName("detalle")] string? Detalle,
    [property: JsonPropertyName("codigo_biblioteca")] string? CodigoBiblioteca,
    [property: JsonPropertyName("sugerencia")] string? Sugerencia);

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
    [property: JsonPropertyName("ausente")] bool Ausente,
    // Contrato 2 (2026-10-07): página de entrada de una simulación o de una lección `html`; póster y pausas para pensar de un video.
    [property: JsonPropertyName("entrada")] string? Entrada = null,
    [property: JsonPropertyName("poster_url")] string? PosterUrl = null,
    [property: JsonPropertyName("pausas")] IReadOnlyList<PausaAula>? Pausas = null);

/// <summary>Contrato 2: la cátedra o explicación maquetada por el curso (`html {mediaId, entry}`): su página de entrada y su carpeta.</summary>
public sealed record HtmlAula(
    [property: JsonPropertyName("media_ref")] string MediaRef,
    [property: JsonPropertyName("entrada")] string? Entrada,
    [property: JsonPropertyName("url")] string? Url,
    [property: JsonPropertyName("base_url")] string? BaseUrl,
    [property: JsonPropertyName("ausente")] bool Ausente);

/// <summary>Una opción de una pausa para pensar de un video. Es formativa: la respuesta y su razón SÍ llegan, para mostrarlas al elegir.</summary>
public sealed record OpcionPausaAula(
    [property: JsonPropertyName("opcion_ref")] string OpcionRef,
    [property: JsonPropertyName("texto")] string? Texto,
    [property: JsonPropertyName("tramos")] IReadOnlyList<Tramo>? Tramos,
    [property: JsonPropertyName("es_respuesta")] bool EsRespuesta,
    [property: JsonPropertyName("explicacion")] string? Explicacion);

/// <summary>Contrato 2: una pausa para pensar (`interactions`) de un video: en `EnSeg` el reproductor se detiene y pregunta.</summary>
public sealed record PausaAula(
    [property: JsonPropertyName("pausa_ref")] string PausaRef,
    [property: JsonPropertyName("en_seg")] double EnSeg,
    [property: JsonPropertyName("enunciado")] string? Enunciado,
    [property: JsonPropertyName("enunciado_tramos")] IReadOnlyList<Tramo>? EnunciadoTramos,
    [property: JsonPropertyName("opciones")] IReadOnlyList<OpcionPausaAula>? Opciones,
    [property: JsonPropertyName("consejo_docente")] string? ConsejoDocente = null);

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
    [property: JsonPropertyName("url_pagina_inicial")] string? UrlPaginaInicial,
    [property: JsonPropertyName("poster_url")] string? PosterUrl = null,
    [property: JsonPropertyName("pausas")] IReadOnlyList<PausaAula>? Pausas = null);

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
    [property: JsonPropertyName("notas_docente")] NotasDocente? NotasDocente,
    /// <summary>Contrato 2: la misma lámina o página en el html del curso (`entry#s{n}`), cuando el objeto está maquetado.</summary>
    [property: JsonPropertyName("url_html")] string? UrlHtml = null);

/// <summary>Una opción de selección múltiple: texto (RichText) o imagen (<c>mediaId</c> del esquema 1.0), o ambos.</summary>
public sealed record OpcionAula(
    [property: JsonPropertyName("opcion_ref")] string OpcionRef,
    [property: JsonPropertyName("texto")] string? Texto,
    [property: JsonPropertyName("tramos")] IReadOnlyList<Tramo>? Tramos,
    [property: JsonPropertyName("media_ref")] string? MediaRef = null,
    [property: JsonPropertyName("url")] string? Url = null,
    [property: JsonPropertyName("texto_alternativo")] string? TextoAlternativo = null);

/// <summary>Un ítem de relacionar u ordenar (<c>ChoiceItem</c> del esquema 1.0): texto o imagen.</summary>
public sealed record ElementoAula(
    [property: JsonPropertyName("ref")] string Ref,
    [property: JsonPropertyName("texto")] string? Texto,
    [property: JsonPropertyName("tramos")] IReadOnlyList<Tramo>? Tramos = null,
    [property: JsonPropertyName("media_ref")] string? MediaRef = null,
    [property: JsonPropertyName("url")] string? Url = null,
    [property: JsonPropertyName("texto_alternativo")] string? TextoAlternativo = null);

/// <summary>Contrato 2: una zona de «arrastrar y soltar» (<c>DragTarget</c>): un rótulo o una imagen donde caen las piezas.</summary>
public sealed record ZonaAula(
    [property: JsonPropertyName("zona_ref")] string ZonaRef,
    [property: JsonPropertyName("rotulo")] string? Rotulo,
    [property: JsonPropertyName("media_ref")] string? MediaRef = null,
    [property: JsonPropertyName("url")] string? Url = null,
    [property: JsonPropertyName("texto_alternativo")] string? TextoAlternativo = null);

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
    [property: JsonPropertyName("medios")] IReadOnlyList<MedioAula>? Medios,
    [property: JsonPropertyName("puntos")] double? Puntos,
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
    [property: JsonPropertyName("longitud_maxima")] int? LongitudMaxima,
    /// <summary>Contrato 2: las zonas de «arrastrar» (las piezas van en <see cref="Elementos"/>).</summary>
    [property: JsonPropertyName("zonas")] IReadOnlyList<ZonaAula>? Zonas = null)
{
    public string TipoLegible => Componente switch
    {
        "opcion_multiple" => "Opción múltiple",
        "verdadero_falso" => "Verdadero o falso",
        "completar" => "Completar",
        "relacionar" => "Relacionar",
        "ordenar" => "Ordenar",
        "abierta" => "Respuesta abierta",
        "arrastrar" => "Arrastrar y soltar",
        _ => Tipo,
    };
}

public sealed record AjustesActividad(
    [property: JsonPropertyName("retroalimentacion")] string? Retroalimentacion,
    [property: JsonPropertyName("intentos_permitidos")] int? IntentosPermitidos,
    [property: JsonPropertyName("barajar_preguntas")] bool BarajarPreguntas,
    [property: JsonPropertyName("barajar_opciones")] bool BarajarOpciones,
    [property: JsonPropertyName("tiempo_limite_seg")] int? TiempoLimiteSeg = null);

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
    [property: JsonPropertyName("puntos_totales")] double? PuntosTotales,
    [property: JsonPropertyName("total_preguntas_banco")] int? TotalPreguntasBanco,
    [property: JsonPropertyName("html")] HtmlAula? Html = null)
{
    public IReadOnlyList<UnidadAula> Unidades => Laminas ?? Paginas ?? [];
    /// <summary>La cátedra o explicación viene maquetada por el curso y su html está en la biblioteca: el visor la carga en un marco.</summary>
    public bool TieneHtml => Html is { Ausente: false, Url.Length: > 0 };
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
    [property: JsonPropertyName("dispositivo_bloqueado")] bool? DispositivoBloqueado = null,
    // 007-13: la mano levantada (instante en que pidió ayuda) y la proyección de su pantalla (DEC-034).
    [property: JsonPropertyName("ayuda_en")] long? AyudaEn = null,
    [property: JsonPropertyName("proyectado_desde")] long? ProyectadoDesde = null)
{
    public bool ManoLevantada => AyudaEn is not null;
    public bool Proyectado => ProyectadoDesde is not null;
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
    [property: JsonPropertyName("tiempo_limite_seg")] int? TiempoLimiteSeg = null,
    // 007-05/06/09: lo que hace falta para el avance vivo, el cronómetro y el intento de esta tableta.
    [property: JsonPropertyName("total_preguntas")] int TotalPreguntas = 0,
    [property: JsonPropertyName("puntos_totales")] double PuntosTotales = 0,
    [property: JsonPropertyName("estudio_hasta")] long? EstudioHasta = null,
    [property: JsonPropertyName("avance")] AvanceActividad? Avance = null,
    [property: JsonPropertyName("cronometro")] CronometroAula? Cronometro = null,
    [property: JsonPropertyName("intentos_usados")] int? IntentosUsados = null,
    [property: JsonPropertyName("intento")] IntentoTableta? Intento = null)
{
    public bool EstaAbierta => Abierta ?? CerradaEn is null;
    public bool EsActividad => Clase == "actividad";
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
    [property: JsonPropertyName("origen_cierre")] string? OrigenCierre,
    [property: JsonPropertyName("detalle")] DetalleResumen? Detalle = null)
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
    [property: JsonPropertyName("servidor_en")] long ServidorEn,
    [property: JsonPropertyName("origen_cierre")] string? OrigenCierre = null,
    [property: JsonPropertyName("causa_suspension")] string? CausaSuspension = null,
    [property: JsonPropertyName("suspendida_en")] long? SuspendidaEn = null,
    [property: JsonPropertyName("anclajes")] IReadOnlyList<NodoAnclaje>? Anclajes = null,
    [property: JsonPropertyName("capacidad")] CapacidadAula? Capacidad = null,
    [property: JsonPropertyName("manos_levantadas")] int ManosLevantadas = 0,
    [property: JsonPropertyName("recuperacion")] RecuperacionAula? Recuperacion = null,
    [property: JsonPropertyName("tiempo_real")] TiempoRealAula? TiempoReal = null)
{
    public bool Suspendida => Estado == "suspendida";
    public bool Cerrada => Estado is "cerrada" or "archivada";
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
    [property: JsonPropertyName("profesor_rotulo")] string? ProfesorRotulo,
    [property: JsonPropertyName("origen_cierre")] string? OrigenCierre = null,
    [property: JsonPropertyName("finalizada_en")] long? FinalizadaEn = null);

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
    [property: JsonPropertyName("en_espera")] bool? EnEspera,
    // DEC-034 · CMP-063: su pantalla se está proyectando al grupo. 007-13: ya pidió ayuda. MSG-003/004: la clase está en pausa.
    [property: JsonPropertyName("proyectando")] bool Proyectando = false,
    [property: JsonPropertyName("ayuda_pedida")] bool AyudaPedida = false,
    [property: JsonPropertyName("recuperacion")] RecuperacionAula? Recuperacion = null,
    [property: JsonPropertyName("cierre")] CierreAlumno? Cierre = null,
    [property: JsonPropertyName("tiempo_real")] TiempoRealAula? TiempoReal = null);

// ---------------------------------------------------------------- solicitudes

public sealed record IniciarSesionSolicitud(
    string Via, string? CursoRef, string? LeccionRef, string? ObjetoRef, string Fuente,
    string ProfesorId, string? ProfesorRotulo, string Superficie);

/// <summary>El lanzamiento: a todo el grupo (<c>Alcance</c> nulo o «grupo») o a una selección de participantes, con sus reglas opcionales.</summary>
public sealed record DistribuirSolicitud(string Clase, string? ObjetoRef, string? MediaRef, string? Rotulo, bool DisponibleEstudio,
                                         string? Alcance = null, IReadOnlyList<string>? Participantes = null,
                                         int? IntentosPermitidos = null, int? TiempoLimiteSeg = null);

/// <summary>Una respuesta capturada en la tableta. <c>Secuencia</c> es monotónica por intento; <c>CapturadaEn</c> ya va normalizada al reloj del nodo.</summary>
public sealed record RespuestaEnviada(
    [property: JsonPropertyName("pregunta_ref")] string PreguntaRef,
    [property: JsonPropertyName("secuencia")] int Secuencia,
    [property: JsonPropertyName("respuesta")] JsonElement Respuesta,
    [property: JsonPropertyName("capturada_en")] long? CapturadaEn = null,
    [property: JsonPropertyName("capturada_en_tableta")] long? CapturadaEnTableta = null);

/// <summary>Un envío a <c>…/distribuciones/{id}/respuestas/</c>: respuestas sueltas y, si se pide, la entrega del intento.</summary>
public sealed record EnvioRespuestas(
    string ParticipanteId, IReadOnlyList<RespuestaEnviada> Respuestas, bool Entregar = false, int? IntentoNumero = null, string Origen = "directo");

// ------------------------------------------------------- tiempo real y actividad (MOD-007)

/// <summary>BR-063: 50 dispositivos en operación normal, 100 en pico. <c>Nivel</c>: normal · pico · lleno.</summary>
public sealed record CapacidadAula(
    [property: JsonPropertyName("normal")] int Normal,
    [property: JsonPropertyName("pico")] int Pico,
    [property: JsonPropertyName("activos")] int Activos,
    [property: JsonPropertyName("nivel")] string Nivel);

/// <summary>PAN-006 / MSG-004: dónde iba la clase cuando se cortó. La ventana de 3 minutos se mide y se informa; nunca impide reanudar.</summary>
public sealed record RecuperacionAula(
    [property: JsonPropertyName("causa")] string? Causa,
    [property: JsonPropertyName("suspendida_en")] long SuspendidaEn,
    [property: JsonPropertyName("transcurrido_ms")] long TranscurridoMs,
    [property: JsonPropertyName("ventana_ms")] long VentanaMs,
    [property: JsonPropertyName("dentro_de_ventana")] bool DentroDeVentana,
    [property: JsonPropertyName("bloque")] int? Bloque,
    [property: JsonPropertyName("bloque_rotulo")] string? BloqueRotulo,
    [property: JsonPropertyName("minuto")] long Minuto)
{
    /// <summary>MSG-004: «Clase recuperada. Ibas en el bloque {n}, minuto {m}. Puedes continuar.»</summary>
    public string Texto => Bloque is { } b
        ? $"Ibas en el bloque {b}, minuto {Minuto}."
        : string.IsNullOrWhiteSpace(BloqueRotulo) ? $"Ibas en el minuto {Minuto}." : $"Ibas en «{BloqueRotulo}», minuto {Minuto}.";
}

public sealed record TiempoRealAula(
    [property: JsonPropertyName("latido_ms")] int LatidoMs,
    [property: JsonPropertyName("respaldo_ms")] int RespaldoMs);

/// <summary>CMP-003: en_curso · congelado · vencido_con_gracia · vencido. Los milisegundos son del reloj del nodo en <c>servidor_en</c>.</summary>
public sealed record CronometroAula(
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("limite_ms")] long LimiteMs,
    [property: JsonPropertyName("restante_ms")] long RestanteMs,
    [property: JsonPropertyName("transcurrido_ms")] long TranscurridoMs);

public sealed record AvanceActividad(
    [property: JsonPropertyName("destinatarios")] int Destinatarios,
    [property: JsonPropertyName("entregaron")] int Entregaron,
    [property: JsonPropertyName("respondiendo")] int Respondiendo,
    [property: JsonPropertyName("por_decidir")] int PorDecidir,
    [property: JsonPropertyName("sin_empezar")] int SinEmpezar);

/// <summary>El intento de esta tableta en una actividad lanzada: sin puntajes (el alumno no ve una nota que el profesor no publicó, DEC-032).</summary>
public sealed record IntentoTableta(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("numero")] int Numero,
    [property: JsonPropertyName("respondidas")] int Respondidas,
    [property: JsonPropertyName("secuencia_maxima")] int SecuenciaMaxima,
    [property: JsonPropertyName("recuperado_de_cola")] bool? RecuperadoDeCola = null,
    // Las preguntas que ya tienen respuesta guardada en el nodo (sólo la referencia): al reabrir la actividad, la tableta no las repite.
    [property: JsonPropertyName("respondidas_refs")] IReadOnlyList<string>? RespondidasRefs = null);

public sealed record RechazoRespuesta(
    [property: JsonPropertyName("pregunta_ref")] string? PreguntaRef,
    [property: JsonPropertyName("motivo")] string Motivo);

/// <summary>El acuse de un envío de respuestas: qué quedó guardado y qué era un reenvío. Con acuse positivo, la tableta borra de su cola lo enviado.</summary>
public sealed record AcuseRespuestas(
    [property: JsonPropertyName("acuse")] bool Acuse,
    [property: JsonPropertyName("politica")] string? Politica,
    [property: JsonPropertyName("intento")] IntentoTableta Intento,
    [property: JsonPropertyName("aceptadas")] IReadOnlyList<string>? Aceptadas,
    [property: JsonPropertyName("duplicadas")] IReadOnlyList<string>? Duplicadas,
    [property: JsonPropertyName("superadas")] IReadOnlyList<string>? Superadas,
    [property: JsonPropertyName("rechazadas")] IReadOnlyList<RechazoRespuesta>? Rechazadas,
    [property: JsonPropertyName("recibida_en")] long RecibidaEn,
    [property: JsonPropertyName("servidor_en")] long ServidorEn)
{
    /// <summary>Lo que ya quedó en el nodo (aceptado o repetido): se puede borrar de la cola de la tableta.</summary>
    public bool Definitivo => Acuse;
}

public sealed record FilaResultado(
    [property: JsonPropertyName("participante_id")] string ParticipanteId,
    [property: JsonPropertyName("persona_id")] string PersonaId,
    [property: JsonPropertyName("rotulo")] string? Rotulo,
    [property: JsonPropertyName("presencia")] string? Presencia,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("respondidas")] int Respondidas,
    [property: JsonPropertyName("total_preguntas")] int TotalPreguntas,
    [property: JsonPropertyName("avance")] double Avance,
    [property: JsonPropertyName("puntaje")] double? Puntaje,
    [property: JsonPropertyName("puntaje_maximo")] double? PuntajeMaximo,
    [property: JsonPropertyName("porcentaje")] double? Porcentaje,
    [property: JsonPropertyName("sin_calificar")] int SinCalificar,
    [property: JsonPropertyName("intento_id")] string? IntentoId,
    [property: JsonPropertyName("origen_envio")] string? OrigenEnvio,
    [property: JsonPropertyName("recuperado_de_cola")] bool RecuperadoDeCola,
    [property: JsonPropertyName("entregado_en")] long? EntregadoEn,
    [property: JsonPropertyName("rezagado")] bool Rezagado)
{
    public string Nombre => string.IsNullOrWhiteSpace(Rotulo) ? PersonaId : Rotulo!;
    public string EstadoLegible => Estado switch
    {
        "entregado" => "Entregó",
        "respondiendo" => "Respondiendo",
        "sin_empezar" => "Sin empezar",
        "pendiente_decision" => "Por decidir",
        _ => Estado,
    };
}

public sealed record TotalesResultado(
    [property: JsonPropertyName("destinatarios")] int Destinatarios,
    [property: JsonPropertyName("entregaron")] int Entregaron,
    [property: JsonPropertyName("respondiendo")] int Respondiendo,
    [property: JsonPropertyName("sin_empezar")] int SinEmpezar,
    [property: JsonPropertyName("por_decidir")] int PorDecidir,
    [property: JsonPropertyName("rezagados")] int Rezagados,
    [property: JsonPropertyName("promedio_porcentaje")] double? PromedioPorcentaje,
    [property: JsonPropertyName("datos_suficientes")] bool DatosSuficientes);

public sealed record ResultadosActividadAula(
    [property: JsonPropertyName("sesion_id")] string SesionId,
    [property: JsonPropertyName("cronometro")] CronometroAula? Cronometro,
    [property: JsonPropertyName("totales")] TotalesResultado Totales,
    [property: JsonPropertyName("filas")] IReadOnlyList<FilaResultado> Filas,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

public sealed record NodoAnclaje(
    [property: JsonPropertyName("ref")] string Ref,
    [property: JsonPropertyName("rotulo")] string? Rotulo,
    [property: JsonPropertyName("origen")] string? Origen = null)
{
    public string Texto => string.IsNullOrWhiteSpace(Rotulo) ? Ref : Rotulo!;
}

public sealed record AnclajeAula(
    [property: JsonPropertyName("sesion_id")] string SesionId,
    [property: JsonPropertyName("anclajes")] IReadOnlyList<NodoAnclaje>? Anclajes,
    [property: JsonPropertyName("sugerencias")] IReadOnlyList<NodoAnclaje>? Sugerencias,
    [property: JsonPropertyName("motivo")] string? Motivo);

public sealed record FichaCierre(
    [property: JsonPropertyName("distribucion_id")] string DistribucionId,
    [property: JsonPropertyName("rotulo")] string? Rotulo,
    [property: JsonPropertyName("clase")] string? Clase,
    [property: JsonPropertyName("entregado")] bool Entregado,
    [property: JsonPropertyName("hasta")] long? Hasta = null);

/// <summary>007-09: lo que la tableta sabe al terminar la clase: qué le quedó pendiente y qué se dejó para estudiar.</summary>
public sealed record CierreAlumno(
    [property: JsonPropertyName("origen_cierre")] string? OrigenCierre,
    [property: JsonPropertyName("finalizada_en")] long? FinalizadaEn,
    [property: JsonPropertyName("pendientes")] IReadOnlyList<FichaCierre>? Pendientes,
    [property: JsonPropertyName("estudio")] IReadOnlyList<FichaCierre>? Estudio);

public sealed record ActividadDeAlumno(
    [property: JsonPropertyName("distribucion_id")] string DistribucionId,
    [property: JsonPropertyName("rotulo")] string? Rotulo,
    [property: JsonPropertyName("entregado")] bool Entregado,
    [property: JsonPropertyName("estado")] string? Estado,
    [property: JsonPropertyName("porcentaje")] double? Porcentaje,
    [property: JsonPropertyName("origen_envio")] string? OrigenEnvio);

public sealed record AlumnoDelResumen(
    [property: JsonPropertyName("participante_id")] string ParticipanteId,
    [property: JsonPropertyName("persona_id")] string PersonaId,
    [property: JsonPropertyName("rotulo")] string? Rotulo,
    [property: JsonPropertyName("estado")] string? Estado,
    [property: JsonPropertyName("admision_nominal")] bool AdmisionNominal,
    [property: JsonPropertyName("ingreso")] long Ingreso,
    [property: JsonPropertyName("salida")] long? Salida,
    [property: JsonPropertyName("presente_ms")] long PresenteMs,
    [property: JsonPropertyName("actividades")] IReadOnlyList<ActividadDeAlumno>? Actividades)
{
    public string Nombre => string.IsNullOrWhiteSpace(Rotulo) ? PersonaId : Rotulo!;
    public string PresenteTexto => PresenteMs < 60_000 ? $"{PresenteMs / 1000} s" : $"{PresenteMs / 60_000} min";
}

public sealed record PendienteDelResumen(
    [property: JsonPropertyName("participante_id")] string ParticipanteId,
    [property: JsonPropertyName("rotulo")] string? Rotulo,
    [property: JsonPropertyName("distribucion_id")] string DistribucionId,
    [property: JsonPropertyName("actividad")] string? Actividad);

public sealed record RecursoDelResumen(
    [property: JsonPropertyName("distribucion_id")] string DistribucionId,
    [property: JsonPropertyName("rotulo")] string? Rotulo,
    [property: JsonPropertyName("disponible_estudio")] bool DisponibleEstudio);

/// <summary>PAN-008: la participación por alumno con lo que entregó y lo que le quedó pendiente.</summary>
public sealed record DetalleResumen(
    [property: JsonPropertyName("participantes")] IReadOnlyList<AlumnoDelResumen>? Participantes,
    [property: JsonPropertyName("pendientes")] IReadOnlyList<PendienteDelResumen>? Pendientes,
    [property: JsonPropertyName("recursos")] IReadOnlyList<RecursoDelResumen>? Recursos);

// -------------------------------------------------- mensajes del WebSocket (007-01, 007-04)

/// <summary>
/// Un mensaje del canal en tiempo real (<c>ws/aula/sesiones/{id}/</c>). <c>Tipo</c>: <c>hola</c> · <c>conteo</c> · <c>cambio</c> · <c>pong</c> · <c>error</c>.
/// Un <c>cambio</c> dice QUÉ cambió (<c>Que</c>: selector · controles · distribucion · aviso · presencia · codigo · sesion · resultados · entregas · ayuda ·
/// proyeccion) y nunca lleva contenido académico: el cliente pide el estado por HTTP.
/// </summary>
public sealed record MensajeAula(
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("que")] string? Que = null,
    [property: JsonPropertyName("sesion_id")] string? SesionId = null,
    [property: JsonPropertyName("emitido_en")] long? EmitidoEn = null,
    [property: JsonPropertyName("servidor_en")] long? ServidorEn = null,
    [property: JsonPropertyName("t")] JsonElement? T = null,
    [property: JsonPropertyName("codigo")] string? Codigo = null,
    [property: JsonPropertyName("detalle")] string? Detalle = null,
    [property: JsonPropertyName("carga")] JsonElement? Carga = null,
    // «conteo»: lo que pinta el recuadro verde del profesor
    [property: JsonPropertyName("total")] int? Total = null,
    [property: JsonPropertyName("conectados")] int? Conectados = null,
    [property: JsonPropertyName("reconectando")] int? Reconectando = null,
    [property: JsonPropertyName("esperando")] int? Esperando = null,
    [property: JsonPropertyName("salieron")] int? Salieron = null,
    // «hola»
    [property: JsonPropertyName("rol")] string? Rol = null,
    [property: JsonPropertyName("latido_ms")] int? LatidoMs = null,
    [property: JsonPropertyName("respaldo_ms")] int? RespaldoMs = null,
    [property: JsonPropertyName("conteo")] ConteoSesion? Conteo = null,
    [property: JsonPropertyName("capacidad")] CapacidadAula? Capacidad = null)
{
    public bool EsCambio(string que) => Tipo == "cambio" && Que == que;

    /// <summary>El conteo de un mensaje «conteo» o del saludo del profesor.</summary>
    public ConteoSesion? ConteoDelMensaje => Tipo switch
    {
        "conteo" when Total is not null => new ConteoSesion(Total ?? 0, Conectados ?? 0, Reconectando ?? 0, Esperando ?? 0, Salieron ?? 0),
        "hola" => Conteo,
        _ => null,
    };

    public string? CargaTexto(string clave) =>
        Carga is { ValueKind: JsonValueKind.Object } c && c.TryGetProperty(clave, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
}

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
    [property: JsonPropertyName("sesion_abierta")] SesionAbiertaDispositivo? SesionAbierta,
    [property: JsonPropertyName("espacio_libre_mb")] int? EspacioLibreMb = null,
    [property: JsonPropertyName("bateria_pct")] int? BateriaPct = null,
    // MOD-008 · 008-01: el aparato asignado a una persona (perfil «asignado») es el único donde existe el modo de estudio.
    [property: JsonPropertyName("perfil")] string? Perfil = null,
    [property: JsonPropertyName("asignado_a")] AlumnoEstudio? AsignadoA = null,
    // MOD-010: lo que la tableta DECLARA poder garantizar en un examen (abierto · supervisado · controlado). Vacío = no la declaró.
    [property: JsonPropertyName("capacidad_control")] string? CapacidadControl = null)
{
    public bool Asignado => string.Equals(Perfil, "asignado", StringComparison.OrdinalIgnoreCase);
    /// <summary>Verdadero si la tableta declaró su capacidad de control. Sin declarar cuenta como «abierto» frente a un examen (BR-075).</summary>
    public bool CapacidadDeclarada => !string.IsNullOrWhiteSpace(CapacidadControl);
    /// <summary>La capacidad en palabras de aula: «Controlado», «Supervisado», «Abierto» o «No declarada».</summary>
    public string CapacidadLegible => !CapacidadDeclarada ? "No declarada" : CapacidadControl!.Trim().ToLowerInvariant() switch
    {
        "controlado" => "Controlado",
        "supervisado" => "Supervisado",
        "abierto" => "Abierto",
        _ => "No declarada",
    };
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
    /// <summary>401 con un código <c>sesion_*</c>: hay que volver a identificarse (PAN-101).</summary>
    public bool SesionPerdida => Estado == 401 && Codigo is { } c && c.StartsWith("sesion_", StringComparison.Ordinal);
    /// <summary>PAN-103: la sesión se cerró porque la misma persona entró desde otro dispositivo (sesión única, DEC-023).</summary>
    public bool CerradaEnOtroDispositivo => Codigo == "sesion_cerrada_otro_dispositivo";
    /// <summary>007-10: demasiados códigos equivocados desde esta tableta.</summary>
    public bool Frenado => Estado == 429 || Codigo == "demasiados_intentos";
    /// <summary>BR-063: el aula llegó a su capacidad máxima; las conexiones nuevas esperan.</summary>
    public bool AulaLlena => Codigo == "aula_llena";
    /// <summary>INV-011: esta sesión habló por el participante de otra persona (tableta compartida); lo que esa persona dejó en la cola no se descarta.</summary>
    public bool PersonaAjena => Codigo == "persona_ajena";
    // --- MOD-001 · PIN maestro, alumnos y visitantes (requisitos de acceso 2026-10-05): los códigos del §C.4.3 ---
    /// <summary>RN-35: el alumno todavía no eligió su PIN; hay que mandarlo a elegirlo, no a corregir.</summary>
    public bool PinPendiente => Codigo == "pin_pendiente";
    /// <summary>La administración exige además el PIN maestro. Se dice DESPUÉS de comprobar la contraseña.</summary>
    public bool PinMaestroRequerido => Codigo == "pin_maestro_requerido";
    public bool PinMaestroInvalido => Codigo == "pin_maestro_invalido";
    /// <summary>RN-10: demasiados intentos desde este equipo (<see cref="ReintentarEnSeg"/>).</summary>
    public bool PinMaestroBloqueado => Codigo == "pin_maestro_bloqueado";
    /// <summary>RN-09: venció; ya no acepta altas ni restablecimientos de profesores.</summary>
    public bool PinMaestroVencido => Codigo == "pin_maestro_vencido";
    public bool PinMaestroNoConfigurado => Codigo == "pin_maestro_no_configurado";
    /// <summary>RN-33: la tableta espera tras varios PIN equivocados; entrar como visitante nunca se bloquea.</summary>
    public bool DispositivoEnPausa => Codigo == "dispositivo_en_pausa";
    /// <summary>RN-11 y BR-056: el PIN maestro no se acepta desde una tableta de alumno; la lista de nombres sólo sale a un equipo registrado.</summary>
    public bool DispositivoNoAutorizado => Codigo == "dispositivo_no_autorizado";
    /// <summary>RN-34: ya hay alguien con ese alias en el grupo; <see cref="Sugerencia"/> (o el extra <c>sugerencia</c>) trae una letra más.</summary>
    public bool AliasDuplicado => Codigo == "alias_duplicado";
    public bool RegistroCerrado => Codigo == "registro_cerrado";
    public bool VisitanteNoPermitido => Codigo == "visitante_no_permitido";
    /// <summary>RN-42 y RN-43: una visita sólo puede seguir la clase y practicar.</summary>
    public bool SesionVisitanteLimitada => Codigo == "sesion_visitante_limitada";
    public long? ReintentarEnSeg => Numero("reintentar_en_seg");
    public long? IntentosRestantes => Numero("intentos_restantes");
    /// <summary>Las reglas que una clave no cumplió (<c>secreto_debil</c>), en palabras del nodo.</summary>
    public IReadOnlyList<string> Reglas =>
        Extra is { ValueKind: JsonValueKind.Object } e && e.TryGetProperty("reglas", out var v) && v.ValueKind == JsonValueKind.Array
            ? v.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!).ToArray()
            : [];

    public long? Numero(string clave) =>
        Extra is { ValueKind: JsonValueKind.Object } e && e.TryGetProperty(clave, out var v) && v.ValueKind == JsonValueKind.Number && v.TryGetInt64(out var n) ? n : null;
    public string? Texto(string clave) =>
        Extra is { ValueKind: JsonValueKind.Object } e && e.TryGetProperty(clave, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
}

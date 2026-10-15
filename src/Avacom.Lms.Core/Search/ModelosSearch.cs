using System.Text.Json.Serialization;

namespace Avacom.Lms.Core.Search;

// Contratos de /api/search/ (MOD-021 · Search), tal como los define spec-driven/13-search/02-api.md. Los nombres JSON son los del backend.
// Lo que llega ya viene filtrado por lo que la persona puede LEER (BR-088): el cliente no filtra permisos, sólo pinta.

/// <summary>Los tipos de resultado de la búsqueda: tres del catálogo de AVACOM Biblioteca (en vivo) y tres del LMS (índice local).</summary>
public static class TiposDeBusqueda
{
    public const string Curso = "course";
    public const string Leccion = "lesson";
    public const string Recurso = "resource";
    public const string Evaluacion = "assessment";
    public const string Estudio = "study";
    public const string Clase = "class";

    public static readonly IReadOnlyList<string> Todos = [Curso, Leccion, Recurso, Evaluacion, Estudio, Clase];

    public static bool EsDelCatalogo(string? tipo) => tipo is Curso or Leccion or Recurso;
}

/// <summary>Los estados del índice de búsqueda (los guardados y el derivado «rezagado»).</summary>
public static class EstadosDelIndice
{
    public const string Construyendose = "construyendose";
    public const string Consultable = "consultable";
    public const string Rezagado = "rezagado";
    public const string Reconstruyendose = "reconstruyendose";
}

/// <summary>Lo que se busca: el texto y los filtros. Los valores vacíos no viajan.</summary>
public sealed record ConsultaDeBusqueda(
    string Texto,
    IReadOnlyList<string>? Tipos = null,
    string? Pais = null,
    string? Nivel = null,
    string? Grado = null,
    string? Materia = null,
    string? Tema = null,
    string? Periodo = null,
    string? GrupoId = null,
    int Pagina = 1,
    int Limite = 20);

// ------------------------------------------------------------------------------------------------ GET /api/search/

public sealed record RespuestaDeBusqueda(
    [property: JsonPropertyName("query")] string Consulta,
    [property: JsonPropertyName("normalized")] string Normalizada,
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("total_exact")] bool TotalExacto,
    [property: JsonPropertyName("page")] int Pagina,
    [property: JsonPropertyName("page_size")] int Tamano,
    [property: JsonPropertyName("has_more")] bool HayMas,
    [property: JsonPropertyName("results")] IReadOnlyList<Hallazgo> Resultados,
    [property: JsonPropertyName("match_mode")] string ModoDeCoincidencia,
    [property: JsonPropertyName("index_status")] string EstadoDelIndice,
    [property: JsonPropertyName("index_notice")] string AvisoDelIndice,
    [property: JsonPropertyName("sources")] FuentesDeBusqueda? Fuentes = null,
    [property: JsonPropertyName("notice")] string? Aviso = null)
{
    /// <summary>Ninguna entidad tenía TODAS las palabras: el nodo relajó la búsqueda a «alguna de ellas».</summary>
    public bool Relajada => ModoDeCoincidencia == "any";

    /// <summary>El catálogo de la biblioteca no pudo responder (la búsqueda siguió con lo del LMS).</summary>
    public bool CatalogoNoDisponible => Fuentes?.Catalogo?.Estado == "unavailable";
}

/// <summary>Un resultado. <see cref="Id"/> es el de la entidad original; con <see cref="Tipo"/> la identifica.</summary>
public sealed record Hallazgo(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("entity_type")] string Tipo,
    [property: JsonPropertyName("entity_id")] string EntidadId,
    [property: JsonPropertyName("title")] string Titulo,
    [property: JsonPropertyName("score")] double Puntaje,
    [property: JsonPropertyName("source")] string Origen,
    [property: JsonPropertyName("navigation_target")] DestinoDeNavegacion Destino,
    [property: JsonPropertyName("subtype")] string? Subtipo = null,
    [property: JsonPropertyName("description")] string? Descripcion = null,
    [property: JsonPropertyName("snippet")] string? Fragmento = null,
    [property: JsonPropertyName("highlights")] IReadOnlyList<IReadOnlyList<int>>? Resaltados = null,
    [property: JsonPropertyName("match")] string? Coincidencia = null,
    [property: JsonPropertyName("status")] string? Estado = null,
    [property: JsonPropertyName("context")] ContextoDeHallazgo? Contexto = null);

public sealed record ContextoDeHallazgo(
    [property: JsonPropertyName("group_id")] string? GrupoId = null,
    [property: JsonPropertyName("group_name")] string? Grupo = null,
    [property: JsonPropertyName("period")] string? Periodo = null,
    [property: JsonPropertyName("course_ref")] string? CursoRef = null,
    [property: JsonPropertyName("course_label")] string? Curso = null,
    [property: JsonPropertyName("lesson_label")] string? Leccion = null,
    [property: JsonPropertyName("tree_path")] IReadOnlyList<string>? Ruta = null);

/// <summary>Lo que el cliente necesita para abrir la entidad en SU módulo: no hay una pantalla paralela de Search.</summary>
public sealed record DestinoDeNavegacion(
    [property: JsonPropertyName("entity_type")] string Tipo,
    [property: JsonPropertyName("entity_id")] string EntidadId,
    [property: JsonPropertyName("group_id")] string? GrupoId = null,
    [property: JsonPropertyName("course_ref")] string? CursoRef = null,
    [property: JsonPropertyName("lesson_ref")] string? LeccionRef = null,
    [property: JsonPropertyName("object_ref")] string? ObjetoRef = null,
    [property: JsonPropertyName("source")] string? Fuente = null);

public sealed record FuentesDeBusqueda(
    [property: JsonPropertyName("local")] EstadoDeFuente? Local = null,
    [property: JsonPropertyName("catalog")] EstadoDeFuente? Catalogo = null);

public sealed record EstadoDeFuente(
    [property: JsonPropertyName("status")] string Estado,
    [property: JsonPropertyName("reason")] string? Motivo = null,
    [property: JsonPropertyName("hint")] string? Sugerencia = null);

// ------------------------------------------------------------------------------------------------ GET /api/search/filters/

/// <summary>Las opciones de filtro VÁLIDAS para quien consulta: sus tipos, sus grupos (los que enseña) y lo que la biblioteca ofrece en su árbol académico.</summary>
public sealed record OpcionesDeFiltros(
    [property: JsonPropertyName("types")] IReadOnlyList<OpcionDeTipo> Tipos,
    [property: JsonPropertyName("groups")] IReadOnlyList<GrupoDeFiltro> Grupos,
    [property: JsonPropertyName("periods")] IReadOnlyList<string> Periodos,
    [property: JsonPropertyName("current_period")] string? PeriodoVigente = null,
    [property: JsonPropertyName("countries")] IReadOnlyList<NodoDeArbol>? Paises = null,
    [property: JsonPropertyName("levels")] IReadOnlyList<NodoDeArbol>? Niveles = null,
    [property: JsonPropertyName("grades")] IReadOnlyList<NodoDeArbol>? Grados = null,
    [property: JsonPropertyName("subjects")] IReadOnlyList<NodoDeArbol>? Materias = null,
    [property: JsonPropertyName("topics")] IReadOnlyList<NodoDeArbol>? Temas = null,
    [property: JsonPropertyName("catalog")] EstadoDeFuente? Catalogo = null);

public sealed record OpcionDeTipo(
    [property: JsonPropertyName("value")] string Valor,
    [property: JsonPropertyName("label")] string Rotulo);

public sealed record GrupoDeFiltro(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("name")] string Nombre,
    [property: JsonPropertyName("period")] string? Periodo = null,
    [property: JsonPropertyName("code")] string? Codigo = null,
    [property: JsonPropertyName("level")] string? Nivel = null);

public sealed record NodoDeArbol(
    [property: JsonPropertyName("code")] string Codigo,
    [property: JsonPropertyName("name")] string Nombre);

// ------------------------------------------------------------------------------------------------ GET /api/search/status/ y POST /api/search/open/

public sealed record EstadoDeBusqueda(
    [property: JsonPropertyName("index_status")] string EstadoDelIndice,
    [property: JsonPropertyName("index_notice")] string AvisoDelIndice,
    [property: JsonPropertyName("queryable")] bool Consultable = true);

/// <summary>El permiso sobre el recurso original se volvió a comprobar con lo vigente: <see cref="Destino"/> es adonde se navega.</summary>
public sealed record AperturaDeResultado(
    [property: JsonPropertyName("allowed")] bool Permitido,
    [property: JsonPropertyName("navigation_target")] DestinoDeNavegacion Destino,
    [property: JsonPropertyName("verified")] bool Verificado = true);

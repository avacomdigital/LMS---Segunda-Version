using System.Globalization;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Gradebook;

/// <summary>
/// Lo que las pantallas del Gradebook dicen y comprueban, sin pintar nada (se prueba sin interfaz). NINGUNA regla académica vive aquí: el backend es la fuente
/// autoritativa del cálculo, de los permisos y de los estados. Esto sólo traduce a palabras lo que el nodo respondió y valida la FORMA de lo que se escribe
/// ANTES de mandarlo (rango, decimales y motivo), con las mismas reglas que el nodo, para no gastar un viaje; el nodo vuelve a comprobarlo siempre.
/// </summary>
public static class GradebookTexto
{
    public static readonly CultureInfo Cultura = new("es-CO");

    // ------------------------------------------------------------------------------------------ estados

    public static string Estado(string? estado) => estado switch
    {
        EstadosDeResultado.Pendiente => "Pendiente",
        EstadosDeResultado.Provisional => "Provisional",
        EstadosDeResultado.Revisado => "Revisado",
        EstadosDeResultado.Definitivo => "Definitivo",
        EstadosDeResultado.Reabierto => "En recalificación",
        EstadosDeResultado.Anulado => "Anulado",
        EstadosDeResultado.SinRegistro => "Sin registro",
        _ => estado ?? "—",
    };

    /// <summary>Qué significa cada estado para el profesor, en una frase (ayuda en pantalla).</summary>
    public static string EstadoExplicado(string? estado) => estado switch
    {
        EstadosDeResultado.Pendiente => "Todavía no hay una calificación. No es un cero.",
        EstadosDeResultado.Provisional => "Tiene respuestas por revisar: la cifra parcial no es una calificación.",
        EstadosDeResultado.Revisado => "Calificada, aún sin publicar: el alumno no la ve.",
        EstadosDeResultado.Definitivo => "Publicada: el alumno la ve.",
        EstadosDeResultado.Reabierto => "Reabierta para recalificar: no cuenta hasta confirmar la revisión.",
        EstadosDeResultado.Anulado => "El intento fue anulado y no cuenta.",
        EstadosDeResultado.SinRegistro => "Calificada en la evaluación, sin calificación registrada (nivel en modo simple o anterior al cambio de modo).",
        _ => string.Empty,
    };

    public static string EstadoSimple(string? estado) => estado switch
    {
        EstadosSimples.NoIniciado => "No iniciado",
        EstadosSimples.EnProgreso => "En progreso",
        EstadosSimples.Completado => "Completado",
        _ => estado ?? "—",
    };

    /// <summary>El símbolo del estado simple (un alumno de preescolar no lee números ni letras): vacío, medio, lleno.</summary>
    public static string Simbolo(string? simbolo) => simbolo switch
    {
        "vacio" => "○",
        "medio" => "◐",
        "lleno" => "●",
        _ => "○",
    };

    public static string SimboloDeAcierto(string? simbolo) => simbolo == "acierto" ? "★" : "☆";

    /// <summary>Lo que el alumno sabe de una evaluación SIN nota publicada: sólo en qué va su entrega.</summary>
    public static string EstadoDeEntrega(string? estado) => estado switch
    {
        "no_iniciado" => "Aún no empiezas",
        "en_progreso" => "En progreso",
        "entregado" => "Entregado",
        "en_revision" => "Tu profesor la está revisando",
        "resultado_no_publicado" => "Calificada: tu profesor aún no publica el resultado",
        "publicado" => "Resultado publicado",
        _ => estado ?? "—",
    };

    public static string Modo(string? modo) => modo == ModosDeNivel.Calificaciones ? "Calificaciones" : "Simple";

    public static string TipoDeEvaluacion(string? tipo) => tipo switch
    {
        "diagnostica" => "Diagnóstica",
        "formativa" => "Formativa",
        "sumativa" => "Sumativa",
        _ => tipo ?? "—",
    };

    public static string Politica(string? politica) => politica switch
    {
        "ultimo" => "El último intento",
        "mejor" => "El mejor intento",
        "primero" => "El primer intento",
        "promedio" => "El promedio de los intentos",
        _ => politica ?? "—",
    };

    /// <summary>Las cuatro políticas de intentos que el nodo admite, en el orden en que se ofrecen.</summary>
    public static IReadOnlyList<string> PoliticasDeIntentos { get; } = ["ultimo", "mejor", "primero", "promedio"];

    /// <summary>Lo que significa cada política en una frase corta: qué cuenta cuando un estudiante presenta una evaluación más de una vez.</summary>
    public static string PoliticaExplicada(string? politica) => politica switch
    {
        "ultimo" => "Cuenta el último intento que presentó, haya salido mejor o peor.",
        "mejor" => "Cuenta el intento con la puntuación más alta.",
        "primero" => "Cuenta sólo el primer intento; los demás son práctica.",
        "promedio" => "Cuenta el promedio de todos los intentos (sólo se muestra al estudiante cuando todos están publicados).",
        _ => string.Empty,
    };

    public static string Forma(string? forma) => forma switch
    {
        "dibujo" => "Dibujo",
        "proyecto" => "Proyecto o entrega",
        _ => "Respuesta abierta",
    };

    public static string TipoDeCambio(string? tipo) => tipo switch
    {
        "registro" => "Registrada",
        "recalculo" => "Recalificada",
        "ajuste" => "Ajuste",
        "valoracion" => "Valoración del desempeño",
        "reapertura" => "Reabierta",
        "publicacion" => "Publicada",
        "retiro_publicacion" => "Publicación retirada",
        "anulacion" => "Anulada",
        "retroalimentacion" => "Retroalimentación",
        _ => tipo ?? "—",
    };

    public static string Origen(string? origen) => origen == "docente" ? "Revisada por el profesor" : "Calificada por el sistema";

    // ------------------------------------------------------------------------------------------ números

    /// <summary>Una puntuación interna sin ceros que sobren: 70 · 70,5 · 85,25. Nunca un cero para lo que no existe: lo pendiente es «—».</summary>
    public static string Puntaje(decimal? valor) => valor is { } v ? v.ToString("0.##", Cultura) : "—";

    /// <summary>Lo presentado por la escala: el valor de una escala numérica o la etiqueta (letra, concepto, nivel).</summary>
    public static string Presentada(Presentacion? p) => p is null ? "—" : Valor(p.Presentada);

    /// <summary>
    /// Lo que ve quien lee la escala: «4,0», no «4». El nodo ya formatea el valor con los decimales que la escala fija (<c>etiqueta</c>, con punto decimal) y sólo él los conoce: aquí se pone
    /// la coma de la cultura y no se vuelve a formatear el número (que perdería el cero final de una nota de 4,0 o de 10,00). En una escala sin números es la etiqueta («A», «Notable»).
    /// </summary>
    public static string Valor(ValorPresentado? v) =>
        v is null ? "—"
        : v.Valor is not null && !string.IsNullOrEmpty(v.Etiqueta) ? v.Etiqueta.Replace(".", Cultura.NumberFormat.NumberDecimalSeparator)
        : v.Valor is { } x ? x.ToString("0.####", Cultura)
        : v.Etiqueta;

    public static string Aprobacion(CriterioDeAprobacion? c) => c?.CumpleCriterio switch { true => "Cumple el criterio", false => "No cumple el criterio", _ => "Sin criterio de aprobación" };

    public static string Hora(long ms) => DateTimeOffset.FromUnixTimeMilliseconds(ms).ToLocalTime().ToString("g", Cultura);

    // --------------------------------------------------------------------------------------- validar lo escrito

    public const int MinimoDeMotivo = 3;

    /// <summary>La puntuación que escribió el profesor, ya leída: o un valor válido (0–100 con a lo sumo dos decimales) o lo que está mal.</summary>
    public sealed record PuntajeEscrito(decimal? Valor, string? Error)
    {
        public bool EsValido => Valor is not null && Error is null;
    }

    /// <summary>Lee «85», «85,5» o «85.25». Rechaza lo vacío, lo que no es número, lo fuera de 0–100 y lo de más de dos decimales (las mismas reglas del nodo).</summary>
    public static PuntajeEscrito LeerPuntaje(string? texto)
    {
        var limpio = (texto ?? string.Empty).Trim().Replace(',', '.');
        if (limpio.Length == 0) return new(null, "Escribe la nueva puntuación.");
        if (!decimal.TryParse(limpio, NumberStyles.AllowDecimalPoint | NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var valor)) return new(null, "La puntuación debe ser un número.");
        if (valor < 0 || valor > 100) return new(null, "La puntuación va de 0 a 100.");
        if (decimal.Round(valor, 2) != valor) return new(null, "La puntuación admite a lo sumo dos decimales.");
        return new(valor, null);
    }

    /// <summary>El motivo de un cambio: de al menos tres letras. Queda en el historial junto al valor anterior.</summary>
    public static string? ValidarMotivo(string? motivo) =>
        string.IsNullOrWhiteSpace(motivo) || motivo.Trim().Length < MinimoDeMotivo ? "Escribe el motivo del cambio: queda en el historial." : null;

    /// <summary>Lo único que impide mandar un ajuste. Vacío: se puede confirmar. (El nodo vuelve a comprobarlo todo.)</summary>
    public static IReadOnlyList<string> ErroresDeAjuste(string? puntaje, string? motivo, decimal? efectivoActual = null)
    {
        var errores = new List<string>();
        var leido = LeerPuntaje(puntaje);
        if (leido.Error is { } e) errores.Add(e);
        else if (efectivoActual is { } actual && leido.Valor == actual) errores.Add("El valor nuevo es igual al vigente.");
        if (ValidarMotivo(motivo) is { } m) errores.Add(m);
        return errores;
    }

    /// <summary>Los puntos de un criterio de rúbrica: de 0 a lo que vale, con a lo sumo dos decimales.</summary>
    public static string? ErrorDePuntosDeCriterio(string? texto, decimal maximo)
    {
        var limpio = (texto ?? string.Empty).Trim().Replace(',', '.');
        if (!decimal.TryParse(limpio, NumberStyles.AllowDecimalPoint | NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var v)) return "Escribe los puntos de este criterio.";
        if (v < 0 || v > maximo) return $"Este criterio vale de 0 a {Puntaje(maximo)} puntos.";
        return decimal.Round(v, 2) != v ? "A lo sumo dos decimales." : null;
    }

    public static decimal? LeerDecimal(string? texto) =>
        decimal.TryParse((texto ?? string.Empty).Trim().Replace(',', '.'), NumberStyles.AllowDecimalPoint | NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var v) ? v : null;

    // ------------------------------------------------------------------------------------------- errores

    /// <summary>
    /// Lo que el profesor lee cuando el nodo rechazó algo. Sin conexión con el nodo se dice así, sin culpar a la calificación; con un conflicto de versión se dice
    /// que otra persona la cambió, no que «falló».
    /// </summary>
    public static string Error(ErrorAula? error, string? motivo) => error switch
    {
        null => motivo ?? "No se pudo completar la operación.",
        { Estado: 0 } => "Sin conexión con el nodo del aula: nada se confirmó. Puedes reintentar sin duplicar el cambio.",
        { Codigo: "conflicto_de_version" } => "Otra persona cambió esta calificación mientras la editabas. Se volvió a leer: revisa el valor actual y repite el cambio.",
        { Codigo: "sin_permiso" or "fuera_de_alcance" } => "Tu rol no puede hacer esto, o este grupo no es tuyo.",
        { Codigo: "modo_simple" } => "El nivel de este grupo está en modo simple: no hay calificaciones que registrar ni publicar.",
        { Codigo: "no_publicable" } => "Todavía no se puede publicar: " + (Motivos(error) is { Length: > 0 } m ? m : error.Detalle),
        { Codigo: "evaluaciones_en_curso" } => "No se puede alternar el modo mientras haya evaluaciones en curso en ese nivel.",
        { Codigo: "reactivos_pendientes" } => "Quedan respuestas por puntuar: termina la revisión antes de confirmarla.",
        { Codigo: "intento_no_calificable" } => "El intento todavía no está calificado del todo.",
        { Codigo: "rubrica_no_disponible" } => "La biblioteca no entregó la rúbrica de esta pregunta: puntúala a mano.",
        { Codigo: "puntaje_invalido" or "datos_invalidos" or "escala_invalida" } => error.Detalle,
        _ => error.Detalle,
    };

    /// <summary>El valor actual de la calificación que el nodo devolvió con un conflicto de versión (para volver a leerla sin otra petición).</summary>
    public static int? VersionActual(ErrorAula? error) =>
        error?.Extra is { ValueKind: System.Text.Json.JsonValueKind.Object } extra && extra.TryGetProperty("version_actual", out var v) && v.TryGetInt32(out var n) ? n : null;

    public static bool EsConflictoDeVersion(ErrorAula? error) => error?.Codigo == "conflicto_de_version";
    public static bool SinConexion(ErrorAula? error) => error is { Estado: 0 };

    private static string Motivos(ErrorAula error) =>
        error.Extra is { ValueKind: System.Text.Json.JsonValueKind.Object } extra && extra.TryGetProperty("motivos", out var m) && m.ValueKind == System.Text.Json.JsonValueKind.Array
            ? string.Join(" ", m.EnumerateArray().Select(x => x.GetString()).Where(x => !string.IsNullOrWhiteSpace(x)))
            : string.Empty;

    // ------------------------------------------------------------------------------------------ acciones

    /// <summary>¿Qué se puede hacer con una calificación en este estado? (La autorización de verdad la decide el nodo; esto sólo evita ofrecer lo que no aplica.)</summary>
    public static bool PuedeAjustar(Calificacion c) => c.EsEditable;
    public static bool PuedeReabrir(Calificacion c) => c.EsEditable;
    public static bool PuedePublicar(Calificacion c) => c.Estado == EstadosDeCalificacion.Revisada;
    public static bool PuedeRetirar(Calificacion c) => c.Estado == EstadosDeCalificacion.Definitiva;

    /// <summary>
    /// El rol técnico no ve ni toca datos académicos; la administración configura pero no califica; el profesor califica. Es una AYUDA para no ofrecer lo que el nodo
    /// va a denegar (TST-069 «tanto en la interfaz como en el backend»): el backend sigue siendo quien lo impide.
    /// </summary>
    public static bool PuedeCalificar(string? rolCodigo) => rolCodigo is "TEACHER";
    public static bool PuedeConfigurar(string? rolCodigo) => rolCodigo is "ADMIN";
    public static bool PuedeLeerElLibro(string? rolCodigo) => rolCodigo is "TEACHER" or "ADMIN" or "REPORTS";
}

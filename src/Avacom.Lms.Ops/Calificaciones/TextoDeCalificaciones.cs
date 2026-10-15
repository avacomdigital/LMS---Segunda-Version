using System.Text.Json;
using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>
/// Las palabras de Calificaciones que <c>GradebookTexto</c> (Core) no trae: el estado GUARDADO de una calificación (revisada, definitiva, reabierta, anulada), la regla con
/// que se calificó, el renglón de cada cambio del historial y los datos extra de los errores. Ninguna regla académica: sólo traduce a palabras lo que el nodo respondió. Sin MAUI.
/// </summary>
internal static class TextoDeCalificaciones
{
    // ------------------------------------------------------------------------------------- la calificación

    /// <summary>El estado de una calificación como lo lee el profesor: lo guardado más si el alumno ya la ve.</summary>
    public static string Estado(Calificacion c) => c.Estado switch
    {
        EstadosDeCalificacion.Definitiva => "Publicada · el alumno la ve",
        EstadosDeCalificacion.Revisada => "Revisada · sin publicar",
        EstadosDeCalificacion.Reabierta => "Reabierta · en recalificación",
        EstadosDeCalificacion.Anulada => "Anulada",
        _ => c.Estado,
    };

    public static Matiz MatizDeEstado(Calificacion c) => c.Estado switch
    {
        EstadosDeCalificacion.Definitiva => Matiz.Exito,
        EstadosDeCalificacion.Revisada => Matiz.Info,
        EstadosDeCalificacion.Reabierta => Matiz.Ambar,
        _ => Matiz.Gris,
    };

    /// <summary>Qué significa ese estado para el profesor, en una frase.</summary>
    public static string EstadoExplicado(Calificacion c) => c.Estado switch
    {
        EstadosDeCalificacion.Definitiva => "El alumno ya ve la calificación presentada. Un ajuste posterior queda marcado en el historial.",
        EstadosDeCalificacion.Revisada => "Está calificada pero el alumno todavía no la ve: la publicas tú.",
        EstadosDeCalificacion.Reabierta => "No cuenta mientras se recalifica: termina la revisión y confírmala para volver a registrarla.",
        EstadosDeCalificacion.Anulada => "El intento fue anulado: la calificación no cuenta.",
        _ => string.Empty,
    };

    /// <summary>La regla con que se calificó, en palabras.</summary>
    public static string Regla(string? regla) => regla switch
    {
        "mod10.porcentaje.v1" => "Porcentaje de aciertos de la evaluación",
        "mod10.revision_docente.v1" => "Revisión del profesor sobre la evaluación",
        null or "" => "—",
        _ => regla,
    };

    public static bool EsDelSistema(string? actorId) => string.IsNullOrWhiteSpace(actorId) || actorId == "sistema";

    /// <summary>Lo presentado por una escala (el valor de una numérica, o la etiqueta: letra, concepto, nivel), en el formato del aula. «—» si no hay.</summary>
    public static string Presentada(ValorPresentado? v) => GradebookTexto.Valor(v);

    /// <summary>Los resultados internos con los que la vista previa de una escala muestra cómo convierte (no guarda nada).</summary>
    public static readonly IReadOnlyList<decimal> MuestrasDeVistaPrevia = [0m, 40m, 60m, 80m, 100m];

    /// <summary>El nivel de desempeño con su origen: valorado por el profesor o salido de la cuenta de la escala.</summary>
    public static string Desempeno(Presentacion? p) => p?.Desempeno is { Nivel: { Length: > 0 } nivel } d
        ? d.ValoradoPorElDocente ? $"{nivel} · valorado por el profesor" : nivel
        : "—";

    // ---------------------------------------------------------------------------------------- historial

    public static string EstadoGuardado(string? estado) => estado switch
    {
        EstadosDeCalificacion.Revisada => "Revisada",
        EstadosDeCalificacion.Definitiva => "Publicada",
        EstadosDeCalificacion.Reabierta => "Reabierta",
        EstadosDeCalificacion.Anulada => "Anulada",
        null or "" => "—",
        _ => estado,
    };

    /// <summary>
    /// El renglón de lo que cambió: «90 → 85» si cambió el resultado interno, «Se registró 95,24» si es el primero, y «Revisada → Reabierta» si cambió el estado. Nulo si el
    /// cambio no movió ninguna cifra ni el estado (una valoración o una retroalimentación).
    /// </summary>
    public static string? Cambio(VersionDeCalificacion v)
    {
        var partes = new List<string>();
        if (v is { PuntajeAnterior: { } antes, PuntajeNuevo: { } despues } && antes != despues) partes.Add($"{GradebookTexto.Puntaje(antes)} → {GradebookTexto.Puntaje(despues)}");
        else if (v is { PuntajeAnterior: null, PuntajeNuevo: { } primero }) partes.Add($"Se registró {GradebookTexto.Puntaje(primero)}");
        if (!string.IsNullOrEmpty(v.EstadoAnterior) && !string.IsNullOrEmpty(v.EstadoNuevo) && v.EstadoAnterior != v.EstadoNuevo)
            partes.Add($"{EstadoGuardado(v.EstadoAnterior)} → {EstadoGuardado(v.EstadoNuevo)}");
        return partes.Count == 0 ? null : string.Join(" · ", partes);
    }

    // ------------------------------------------------------------------------------ retroalimentación

    public static readonly (string Clave, string Rotulo)[] ApartadosDeRetroalimentacion =
    [
        ("fortalezas", "Fortalezas"),
        ("dificultades", "Dificultades"),
        ("oportunidades", "Oportunidades de mejora"),
        ("comentario", "Comentario"),
    ];

    /// <summary>Lo que el profesor ya escribió en un apartado de la retroalimentación, o nulo.</summary>
    public static string? Retroalimentacion(Calificacion c, string clave) =>
        c.Retroalimentacion is { } r && r.TryGetValue(clave, out var texto) && !string.IsNullOrWhiteSpace(texto) ? texto : null;

    // -------------------------------------------------------------------------------------------- errores

    /// <summary>
    /// Los errores de forma de <c>GradebookTexto.ErroresDeAjuste</c> dicen «escribe…»; el nodo principal no tiene teclado, así que en pantalla se dicen con lo que de verdad se hace: marcar en el
    /// teclado numérico y elegir una frase. El resto de los mensajes (fuera de 0–100, más de dos decimales, igual al vigente) se dejan como están.
    /// </summary>
    public static string ErrorTactil(string error) => error switch
    {
        "Escribe la nueva puntuación." => "Marca la nueva puntuación en el teclado.",
        "Escribe el motivo del cambio: queda en el historial." => "Elige el motivo del cambio: queda en el historial.",
        _ => error,
    };

    /// <summary>
    /// Lo que el nodo dice de la calificación tras un conflicto de versión (<c>version_actual</c> y <c>puntaje_efectivo</c> viajan con el error): sirve para mostrar el valor vigente sin otra
    /// petición si la lectura siguiente falla. Cada dato es nulo si no vino.
    /// </summary>
    public static (int? Version, decimal? Puntaje) ValorActualDelConflicto(ErrorAula? error)
    {
        if (error?.Extra is not { ValueKind: JsonValueKind.Object } e) return (null, null);
        int? version = e.TryGetProperty("version_actual", out var v) && v.ValueKind == JsonValueKind.Number && v.TryGetInt32(out var n) ? n : null;
        decimal? puntaje = e.TryGetProperty("puntaje_efectivo", out var p) && p.ValueKind == JsonValueKind.Number && p.TryGetDecimal(out var d) ? d : null;
        return (version, puntaje);
    }

    /// <summary>Cuántas evaluaciones en curso impidieron cambiar el modo (el nodo lo manda como <c>en_curso</c>), o nulo.</summary>
    public static int? EnCurso(ErrorAula? error) =>
        error?.Extra is { ValueKind: JsonValueKind.Object } e && e.TryGetProperty("en_curso", out var n) && n.ValueKind == JsonValueKind.Number && n.TryGetInt32(out var v) ? v : null;

    /// <summary>El error de configurar un nivel, en palabras de aula: las evaluaciones en curso se dicen con su cuenta; lo demás lo dice <c>GradebookTexto</c>.</summary>
    public static string ErrorDeNivel(ErrorAula? error, string? motivo)
    {
        if (error is { Codigo: "evaluaciones_en_curso" })
        {
            var n = EnCurso(error);
            return n is { } cuantas and > 0
                ? $"No se puede cambiar el modo de este nivel: hay {(cuantas == 1 ? "1 evaluación en curso" : $"{cuantas} evaluaciones en curso")}. Espera a que terminen y vuelve a intentarlo."
                : GradebookTexto.Error(error, motivo);
        }
        return GradebookTexto.Error(error, motivo);
    }
}

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>
/// Las frases prehechas de Calificaciones. El nodo principal no tiene teclado: todo motivo y todo comentario que el nodo pide se ofrece como una frase que se toca; un
/// campo de texto es sólo un extra opcional. Ninguna frase usa jerga ni nombres de módulo. Los motivos quedan en el historial de la calificación junto al valor anterior
/// y el nuevo, así que dicen qué pasó y no a quién se culpa.
/// </summary>
internal static class FrasesDeCalificaciones
{
    /// <summary>«Otro motivo»: la opción que abre un campo de texto opcional. Sola, ya es un motivo válido (el nodo pide al menos tres letras).</summary>
    public const string OtroMotivo = "Otro motivo";

    public static readonly string[] MotivosDeAjuste =
    [
        "Se reconoció una respuesta correcta que la rúbrica inicial no contemplaba",
        "Error de transcripción o de captura",
        "Corrección tras revisar con el estudiante",
        "Ajuste razonable por una necesidad de apoyo",
        "Corrección solicitada por la coordinación",
    ];

    public static readonly string[] MotivosDeReapertura =
    [
        "Hay que volver a revisar las respuestas",
        "El estudiante pidió una revisión",
        "Se detectó un error en la puntuación",
        "Corrección solicitada por la coordinación",
        OtroMotivo,
    ];

    public static readonly string[] MotivosDeRetiro =
    [
        "Se publicó antes de tiempo",
        "Hay que corregir la calificación antes de que se vea",
        "Se publicó con un error",
        OtroMotivo,
    ];

    public static readonly string[] MotivosDeValoracion =
    [
        "El desempeño observado en clase es distinto del que sale de la cuenta",
        "Reconozco el esfuerzo y el progreso del estudiante",
        "La respuesta muestra un nivel de comprensión mayor",
        "La respuesta muestra un nivel de comprensión menor",
        OtroMotivo,
    ];

    public static readonly string[] MotivosDeCambioDePuntaje =
    [
        "Volví a leer la respuesta",
        "Me equivoqué al puntuar",
        "Apliqué mejor la rúbrica",
        OtroMotivo,
    ];

    public static readonly string[] ComentariosDeRevision =
    [
        "Respuesta completa y bien argumentada",
        "Falta justificar la respuesta",
        "Revisa el procedimiento",
        "Buena idea, falta precisión",
        "Responde a lo que se pregunta",
        "No responde a lo que se pregunta",
    ];

    public static readonly string[] Fortalezas =
    [
        "Explica con claridad",
        "Usa bien el vocabulario",
        "Argumenta con ejemplos",
        "Muestra buen procedimiento",
    ];

    public static readonly string[] Dificultades =
    [
        "Le cuesta justificar sus respuestas",
        "Confunde algunos conceptos",
        "Se le olvidan pasos del procedimiento",
        "Responde sin leer toda la pregunta",
    ];

    public static readonly string[] Oportunidades =
    [
        "Practicar con más ejemplos",
        "Repasar el tema con el material de la clase",
        "Pedir ayuda cuando algo no quede claro",
        "Revisar su respuesta antes de entregarla",
    ];

    /// <summary>
    /// El motivo final: la frase elegida o, con «Otro motivo», lo que se escribió (si algo se escribió). Con «Otro motivo» y sin texto, la propia frase ya es un
    /// motivo válido. Nulo si no se eligió nada.
    /// </summary>
    public static string? MotivoFinal(string? elegida, string? textoLibre)
    {
        if (string.IsNullOrWhiteSpace(elegida)) return null;
        if (elegida != OtroMotivo) return elegida;
        var texto = textoLibre?.Trim();
        return string.IsNullOrEmpty(texto) ? OtroMotivo : $"{OtroMotivo}: {texto}";
    }

    /// <summary>Junta las frases elegidas de un apartado con lo que se escribió (si algo se escribió), en un solo texto.</summary>
    public static string? Juntar(IEnumerable<string> frases, string? textoLibre = null)
    {
        var partes = frases.Select(f => f.Trim().TrimEnd('.')).Where(f => f.Length > 0).Select(f => f + ".").ToList();
        if (!string.IsNullOrWhiteSpace(textoLibre)) partes.Add(textoLibre.Trim());
        return partes.Count == 0 ? null : string.Join(" ", partes);
    }
}

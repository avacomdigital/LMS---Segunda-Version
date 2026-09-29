using System.Text.Json;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Student.ModoEstudio.Models;

/// <summary>
/// La práctica de una lección tal como la muestra la tarjeta: «Comprueba lo aprendido · 8 preguntas · Autocalificable».
/// Es una actividad de aprendizaje separada (BR-055): nunca se llama examen ni evaluación, se puede intentar otra vez
/// las veces que se quiera y no cuenta como nota.
/// </summary>
public sealed record StudyPractice(
    string ObjetoRef,
    string Title,
    int QuestionCount,
    int Attempts,
    int? BestCorrect,
    int? LastCorrect,
    bool InProgress)
{
    public bool HasAttempts => Attempts > 0;
}

/// <summary>Lo que se le dice al alumno al terminar una práctica: «7 de 8 correctas · ¡Muy bien!».</summary>
public sealed record StudyPracticeResult(
    int Correct,
    int Total,
    string Message,
    int Ungraded,
    IReadOnlyList<StudyPracticeReview> Review)
{
    /// <summary>Sin calificar: se guardó en la tableta y se calificará al volver al aula (no hay veredicto todavía).</summary>
    public bool IsPendingGrade => Ungraded > 0 && Correct == 0 && Total > 0;

    public string Headline => IsPendingGrade
        ? "Práctica guardada"
        : $"{Correct} de {Total} {(Total == 1 ? "correcta" : "correctas")}";
}

/// <summary>Una pregunta de «Revisar respuestas»: si acertó y lo que dijo la retroalimentación. Sin claves.</summary>
public sealed record StudyPracticeReview(string QuestionRef, int Number, string? Prompt, bool? Correct, IReadOnlyList<string> Feedback);

/// <summary>El veredicto de una respuesta ya traducido para pintarlo: acertó, no acertó o aún no se sabe (sin red).</summary>
public sealed record StudyAnswerVerdict(string QuestionRef, bool? Correct, bool Pending, IReadOnlyList<string> Feedback)
{
    public bool Known => Correct is not null && !Pending;
}

/// <summary>
/// Una práctica abierta: la actividad con sus preguntas (sin claves), lo que ya se respondió y cómo comprobar y terminar. Lo implementa el
/// servicio real (nodo + cola local) y la versión de demostración (calificación simulada). La pantalla de práctica no sabe cuál es.
/// </summary>
public interface IStudyPracticeSession
{
    string Title { get; }
    ObjetoAula Activity { get; }
    int Number { get; }

    /// <summary>Las respuestas de este intento que ya estaban (al reanudar), con su veredicto si lo hay.</summary>
    IReadOnlyDictionary<string, (JsonElement Answer, StudyAnswerVerdict? Verdict)> Previous { get; }

    /// <summary>Verdadero si ahora mismo se puede calificar con el aula; falso: la respuesta se guarda y se califica al volver.</summary>
    bool CanGradeNow { get; }

    /// <summary>Guarda la respuesta (siempre en la tableta primero) y, si hay aula, devuelve el veredicto en ≤ 2 s.</summary>
    Task<StudyAnswerVerdict> SubmitAsync(PreguntaAula question, JsonElement answer, CancellationToken ct = default);

    /// <summary>Cierra el intento y devuelve el resultado que ve el alumno.</summary>
    Task<StudyPracticeResult> FinishAsync(CancellationToken ct = default);
}

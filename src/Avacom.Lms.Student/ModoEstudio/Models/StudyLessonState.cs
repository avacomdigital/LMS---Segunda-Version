namespace Avacom.Lms.Student.ModoEstudio.Models;

/// <summary>El estado de una tarea de estudio del alumno. «Vencida» es derivada: la fecha pasó y no está completada.</summary>
public enum StudyLessonState
{
    Pending,
    InProgress,
    Completed,
    Expired,
}

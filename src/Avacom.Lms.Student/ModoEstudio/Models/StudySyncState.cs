namespace Avacom.Lms.Student.ModoEstudio.Models;

/// <summary>Lo único que el alumno lee sobre el guardado (CMP-002): sin estado de error, sin conceptos técnicos.</summary>
public enum StudySyncState
{
    /// <summary>✓ Guardado: lo que hizo está en el aula.</summary>
    Saved,

    /// <summary>↑ Pendiente de enviar: guardado en la tableta; sale solo cuando vuelva al aula.</summary>
    PendingSend,

    /// <summary>↻ Sincronizando: se está enviando ahora.</summary>
    Syncing,
}

/// <summary>Las tres vistas de «Mis lecciones».</summary>
public enum StudyFilter
{
    Pending,
    Downloaded,
    Completed,
}

using Avacom.Lms.Core.Evaluacion;

namespace Avacom.Lms.Student.Examen;

/// <summary>Los estados visuales de una evaluación en la tableta (RF-006). Nunca llevan una nota: sólo en qué punto va y cuándo verá su resultado.</summary>
public enum EstadoVisual
{
    /// <summary>Todavía no abre.</summary>
    Programada,
    /// <summary>Se puede comenzar (o la tableta espera la decisión del profesor para hacerlo).</summary>
    Disponible,
    /// <summary>Hay un intento abierto (en curso, en pausa o restaurándose).</summary>
    EnCurso,
    /// <summary>La entrega (o respuestas de último momento) sigue guardada en esta tableta a la espera de la red.</summary>
    EntregaPendienteDeSincronizacion,
    /// <summary>Entregada y en cola para calificarse (la biblioteca no estaba) o con respuestas que revisa el profesor.</summary>
    PendienteDeCalificacion,
    /// <summary>Calificada por completo, pero el profesor (o su política) todavía no la publica.</summary>
    CalificadaNoPublicada,
    /// <summary>El resultado está publicado y se puede ver.</summary>
    ResultadoPublicado,
    /// <summary>Entregada sin más que decir (intento anulado, política «nunca», examen cerrado sin presentar…).</summary>
    Cerrada,
}

public enum AccionDeEvaluacion { Comenzar, Continuar, VerResultado, Nada }

/// <summary>Lo que la tarjeta de una evaluación muestra: el estado, el botón (si hay) y la frase, siempre en palabras de aula.</summary>
public sealed record VistaDeEvaluacion(EstadoVisual Estado, AccionDeEvaluacion Accion, string Boton, string Frase)
{
    public bool TieneBoton => Accion != AccionDeEvaluacion.Nada;
}

/// <summary>
/// Decide, sin interfaz, cómo se ve cada evaluación en «Mis evaluaciones» (RF-005/RF-006): lo que dice el nodo (<see cref="EvaluacionDelAlumno"/>) más lo que
/// esta tableta sabe de su propia cola cifrada (<paramref name="pendientesEnDispositivo"/>: cosas guardadas aquí que aún no llegaron al nodo). Las frases de
/// los estados académicos reservados no revelan la nota ni si aprobó; sólo CUÁNDO la verá, según la política de publicación (RF-004).
/// </summary>
public static class EstadoDeEvaluacion
{
    /// <summary>La hora del nodo en la hora local de la tableta («hoy 10:30» / «mañana 08:00» / «12/10 10:30»), igual que la pinta la antesala.</summary>
    public static string Hora(long milisegundos)
    {
        var fecha = DateTimeOffset.FromUnixTimeMilliseconds(milisegundos).ToLocalTime();
        var hoy = DateTimeOffset.Now.Date;
        var dia = fecha.Date == hoy ? "hoy" : fecha.Date == hoy.AddDays(1) ? "mañana" : fecha.ToString("dd/MM");
        return $"{dia} {fecha:HH:mm}";
    }

    public static VistaDeEvaluacion Calcular(EvaluacionDelAlumno e, int pendientesEnDispositivo = 0, Func<long, string>? hora = null)
    {
        hora ??= Hora;
        var intento = e.MiIntento;
        if (intento is not null)
        {
            switch (intento.Estado)
            {
                case EstadosIntento.EnCurso or EstadosIntento.EnCursoFueraDePlazo or EstadosIntento.Pausado or EstadosIntento.Restaurando:
                    return new(EstadoVisual.EnCurso, AccionDeEvaluacion.Continuar, "Continuar",
                        EstadosIntento.Suspendido(intento.Estado) ? "Tu examen está en pausa: avisa a tu profesor" : "Tienes un examen en curso");
                case EstadosIntento.Entregado or EstadosIntento.EnRevision:
                    if (pendientesEnDispositivo > 0)
                        return new(EstadoVisual.EntregaPendienteDeSincronizacion, AccionDeEvaluacion.Nada, string.Empty,
                            "Entregado · algo quedó guardado en esta tableta y se enviará solo cuando haya conexión");
                    return new(EstadoVisual.PendienteDeCalificacion, AccionDeEvaluacion.Nada, string.Empty,
                        intento.Estado == EstadosIntento.EnRevision || intento.RequiereRevision
                            ? "Entregado · algunas respuestas las revisa tu profesor"
                            : "Entregado · pendiente de calificación");
                case EstadosIntento.Calificado:
                    if (intento.ResultadoDisponible)
                        return new(EstadoVisual.ResultadoPublicado, AccionDeEvaluacion.VerResultado, "Ver resultado", "Ya puedes ver tu resultado");
                    if (pendientesEnDispositivo > 0)
                        return new(EstadoVisual.EntregaPendienteDeSincronizacion, AccionDeEvaluacion.Nada, string.Empty,
                            "Entregado · algo quedó guardado en esta tableta y se enviará solo cuando haya conexión");
                    // Si lo retiene el libro de calificaciones (la política de la evaluación ya lo mostraría), lo que falta es que el profesor publique la calificación.
                    return new(EstadoVisual.CalificadaNoPublicada, AccionDeEvaluacion.Nada, string.Empty,
                        "Calificado · " + (intento.RetenidoPor is { Length: > 0 } ? "tu profesor publicará tu calificación" : CuandoSePublica(e, hora)));
                case EstadosIntento.Anulado:
                    return new(EstadoVisual.Cerrada, AccionDeEvaluacion.Nada, string.Empty, "Este intento no cuenta: habla con tu profesor");
            }
        }
        if (e.PuedeComenzar) return new(EstadoVisual.Disponible, AccionDeEvaluacion.Comenzar, "Comenzar", "Lee las condiciones antes de empezar");
        return e.Motivo switch
        {
            "espera_admision" => new(EstadoVisual.Disponible, AccionDeEvaluacion.Comenzar, "Ver", "Esperando que tu profesor decida sobre esta tableta"),
            "rechazada" => new(EstadoVisual.Cerrada, AccionDeEvaluacion.Nada, string.Empty, "Tu profesor no admitió esta tableta: pídele que te indique cómo continuar"),
            "no_abierta" when e.Estado == "programada" => new(EstadoVisual.Programada, AccionDeEvaluacion.Nada, string.Empty,
                e.AbreEn is { } abre ? $"Abre {hora(abre)}" : "Todavía no abre"),
            "no_abierta" => new(EstadoVisual.Cerrada, AccionDeEvaluacion.Nada, string.Empty, "Este examen ya cerró"),
            "ya_entregado" or "intentos_agotados" => new(EstadoVisual.Cerrada, AccionDeEvaluacion.Nada, string.Empty, "Ya presentaste este examen"),
            _ => new(EstadoVisual.Cerrada, AccionDeEvaluacion.Nada, string.Empty, "Por ahora no puedes presentarlo"),
        };
    }

    /// <summary>Cuándo verá el alumno su resultado, según la política de publicación (RF-004). Sin la nota.</summary>
    public static string CuandoSePublica(EvaluacionDelAlumno e, Func<long, string>? hora = null)
    {
        hora ??= Hora;
        return PoliticasDeResultados.Normalizar(e.Resultados) switch
        {
            PoliticasDeResultados.Nunca => "este examen no muestra el resultado en la tableta",
            PoliticasDeResultados.AlEntregar => "tu resultado estará disponible en cuanto termine de calificarse",
            PoliticasDeResultados.AlFinalizarGrupo => "verás tu resultado cuando todo el grupo haya terminado",
            PoliticasDeResultados.Programada => e.PublicarEn is { } cuando ? $"verás tu resultado {hora(cuando)}" : "verás tu resultado en la fecha que fijó tu profesor",
            _ => "tu profesor publicará los resultados",
        };
    }
}

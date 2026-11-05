using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.AgenteIa;

/// <summary>
/// Cliente de <c>/api/agente-ia/</c> (AI Agent) para el PERSONAL (OPS): preguntarle al modelo local, pedir la voz de una respuesta y saber si el servicio de IA está disponible.
///
/// Mismas reglas de degradación que el resto de clientes del LMS: un error HTTP o de red NO es una excepción, devuelve <c>null</c> y deja el motivo en <see cref="UltimoMotivo"/> y el
/// <c>codigo</c> del backend en <see cref="UltimoError"/> (<c>ai_unreachable</c>, <c>ai_timeout</c>, <c>llm_model_missing</c>, <c>tts_busy</c>…). Con <see cref="UltimoError"/>.Estado == 0 no
/// hay conexión con el nodo; con -1 el fallo es del propio cliente (tiempo agotado, audio dañado). El texto de <c>UltimoMotivo</c> ya está en español para la persona.
///
/// El modelo puede tardar minutos en un equipo lento (≈150 s en el peor caso medido por el servicio): este cliente espera hasta <c>AgenteIaApi.TiempoDePregunta</c> y se puede cancelar.
/// </summary>
public interface IAgenteIaApi
{
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }

    /// <summary>Pasos 1 y 2: la pregunta al modelo. <paramref name="conversacion"/> es un id opaco de la pantalla (con él el modelo recuerda lo anterior; sin él no).</summary>
    Task<RespuestaDelAgente?> PreguntarAsync(string actor, string pregunta, string? conversacion, CancellationToken ct = default);

    /// <summary>Pasos 3 y 4: la voz de un texto (el nodo lo trocea, sintetiza y une). Null si no se pudo; el texto ya se mostró, así que un fallo de voz no pierde la respuesta.</summary>
    Task<VozDelAgente?> HablarAsync(string actor, string texto, double velocidad, CancellationToken ct = default);

    /// <summary>Si el servicio de IA está disponible (y la voz). Siempre responde mientras el nodo esté; null sólo si el nodo no contesta.</summary>
    Task<EstadoDelAgente?> EstadoAsync(string actor, CancellationToken ct = default);
}

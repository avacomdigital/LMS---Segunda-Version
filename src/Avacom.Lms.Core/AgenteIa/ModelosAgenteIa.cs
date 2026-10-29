using System.Text.Json.Serialization;

namespace Avacom.Lms.Core.AgenteIa;

// Contratos de /api/agente-ia/ (AI Agent) tal como los entrega el nodo (backend/agente_ia). Los nombres JSON son los del backend (snake_case). El cliente NO habla con el servicio de IA: habla
// con el nodo, que es el único cliente de AVACOM Local AI (contrato-api-ai-lms.md, §1).

/// <summary>La respuesta del modelo a una pregunta (<c>POST /api/agente-ia/preguntar/</c>). <see cref="Texto"/> es texto plano en español: no se interpreta como HTML ni Markdown.</summary>
public sealed record RespuestaDelAgente(
    [property: JsonPropertyName("conversacion")] string Conversacion,
    [property: JsonPropertyName("texto")] string Texto,
    [property: JsonPropertyName("modelo")] string? Modelo,
    [property: JsonPropertyName("contexto_usado")] bool ContextoUsado,
    [property: JsonPropertyName("ms")] long Ms);

/// <summary>Lo que el nodo sabe del servicio de IA (<c>GET /api/agente-ia/estado/</c>). Siempre 200: «no disponible» es una respuesta, no un error.</summary>
public sealed record EstadoDelAgente(
    [property: JsonPropertyName("habilitada")] bool Habilitada,
    [property: JsonPropertyName("servicio_activo")] bool ServicioActivo,
    [property: JsonPropertyName("disponible")] bool Disponible,
    [property: JsonPropertyName("voz_disponible")] bool VozDisponible,
    [property: JsonPropertyName("codigo")] string? Codigo,
    [property: JsonPropertyName("motivo")] string? Motivo,
    [property: JsonPropertyName("motivo_voz")] string? MotivoVoz,
    [property: JsonPropertyName("sugerencia")] string? Sugerencia,
    [property: JsonPropertyName("modelo")] string? Modelo);

/// <summary>La voz de un texto (<c>POST /api/agente-ia/hablar/</c>): un WAV PCM 16 bits ya unido, con su duración.</summary>
public sealed record VozDelAgente(byte[] Wav, int DuracionMs, int Trozos);

/// <summary>Los estados que el avatar puede mostrar (contrato §3): reposo, pensando (esperando al modelo y a la voz), hablando y error.</summary>
public enum EstadoDelAvatar { Reposo, Pensando, Hablando, Error }

/// <summary>Qué pasó con un turno de conversación. Nunca lanza: todo fallo llega aquí, con un texto para la persona y un código para los logs.</summary>
public sealed record ResultadoDelTurno(
    bool Respondio,
    string? Texto,
    bool Hablo,
    string? Aviso,
    string? Codigo,
    bool Reintentable,
    bool Cancelado = false)
{
    public static ResultadoDelTurno Cancelada(string? texto = null) => new(texto is not null, texto, false, null, null, false, true);
}

using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.AgenteIa;

/// <summary>
/// Los textos que la persona lee cuando el agente de IA no responde, y si tiene sentido ofrecerle «Reintentar». El nodo ya manda el texto en español (<c>detail</c>) para cada código de
/// <c>backend/agente_ia/dominio/errores.py</c>; aquí sólo se completan los casos en que el nodo no contestó (no hay conexión, tiempo agotado del cliente) o contestó algo que no es de este módulo
/// (sesión, licencia, permisos). Nunca se muestra un detalle técnico (rutas, puertos, excepciones): eso va al log.
/// </summary>
public static class TextoDelAgente
{
    public const string SinNodo = "No hay conexión con el aula. Revisa que el equipo del aula esté encendido.";
    public const string Generico = "El asistente no pudo completar la tarea. Intenta de nuevo.";

    /// <summary>El texto para la persona. <paramref name="motivo"/> es <c>UltimoMotivo</c> del cliente (ya en español); <paramref name="error"/> el <c>UltimoError</c>.</summary>
    public static string Para(ErrorAula? error, string? motivo)
    {
        if (error is null) return string.IsNullOrWhiteSpace(motivo) ? Generico : motivo;
        return error.Codigo switch
        {
            "sin_conexion" => SinNodo,
            "sin_permiso" => "Tu rol no puede usar el asistente.",
            _ when error.Estado == 0 => SinNodo,
            _ when !string.IsNullOrWhiteSpace(error.Detalle) && error.Estado != 500 => error.Detalle,
            _ => Generico,
        };
    }

    /// <summary>
    /// ¿Tiene sentido ofrecer «Reintentar»? Sí cuando el nodo lo dice (<c>reintentable</c>), cuando no hubo conexión con el nodo (Estado 0) o se agotó el tiempo del cliente (código
    /// <c>tiempo_agotado</c>). No cuando falta configurar el asistente, está desactivado o la persona no tiene permiso: reintentar no cambia nada.
    /// </summary>
    public static bool Reintentable(ErrorAula? error)
    {
        if (error is null) return false;
        if (error.Estado == 0 || error.Codigo is "tiempo_agotado" or "audio_cortado") return true;
        if (error.Extra is { ValueKind: System.Text.Json.JsonValueKind.Object } extra && extra.TryGetProperty("reintentable", out var r))
            return r.ValueKind == System.Text.Json.JsonValueKind.True;
        return error.Estado >= 500 && error.Codigo is null;     // un 5xx sin código (el nodo se cayó a medias): puede ser pasajero
    }

    /// <summary>El texto del estado del servicio para la tarjeta de «el asistente no está disponible».</summary>
    public static string ParaEstado(EstadoDelAgente? estado) => estado switch
    {
        null => SinNodo,
        { Disponible: true, VozDisponible: false } => estado.MotivoVoz ?? "La voz del asistente no está disponible; podrás leer las respuestas.",
        { Disponible: true } => string.Empty,
        _ => string.IsNullOrWhiteSpace(estado.Motivo) ? "El asistente no está disponible en este momento." : estado.Motivo,
    };
}

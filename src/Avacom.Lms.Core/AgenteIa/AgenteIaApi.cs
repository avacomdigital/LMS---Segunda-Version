using System.Net.Http.Headers;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.AgenteIa;

/// <summary>
/// Cliente de <c>/api/agente-ia/</c> (AI Agent). Las rutas y los cuerpos son los de <c>backend/agente_ia/interfaces/views.py</c>. Un error HTTP o de red no es una excepción: devuelve null y deja el
/// motivo (en español, para la persona) y el <c>codigo</c> en <see cref="ClienteJson.UltimoMotivo"/> y <see cref="ClienteJson.UltimoError"/>.
///
/// <b>Tiempos.</b> El modelo puede tardar ≈150 s en el peor caso medido por el servicio de IA y el nodo espera hasta 160 s por él: este cliente espera <see cref="TiempoDePregunta"/> (185 s). El
/// <see cref="HttpClient"/> que se le dé debe tener un <see cref="HttpClient.Timeout"/> MAYOR (o infinito): con el de 15 s de los demás clientes, toda pregunta fallaría. Cada llamada además
/// acepta cancelación (la persona puede dejar de esperar).
/// </summary>
public sealed class AgenteIaApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri), IAgenteIaApi
{
    private const string Base = "api/agente-ia/";

    /// <summary>Cuánto se espera por la respuesta del modelo (160 s del nodo + margen). Contrato §5, paso 1.</summary>
    public static readonly TimeSpan TiempoDePregunta = TimeSpan.FromSeconds(185);
    /// <summary>Cuánto se espera por la voz de un texto (el nodo se rinde a los 120 s de síntesis + hasta 45 s de turno).</summary>
    public static readonly TimeSpan TiempoDeVoz = TimeSpan.FromSeconds(185);
    public static readonly TimeSpan TiempoDeEstado = TimeSpan.FromSeconds(15);

    /// <summary>Lo que ESTA instancia espera (por omisión, los tiempos de arriba; las pruebas los acortan).</summary>
    public TimeSpan EsperaDePregunta { get; set; } = TiempoDePregunta;
    public TimeSpan EsperaDeVoz { get; set; } = TiempoDeVoz;
    public TimeSpan EsperaDeEstado { get; set; } = TiempoDeEstado;

    public Task<RespuestaDelAgente?> PreguntarAsync(string actor, string pregunta, string? conversacion, CancellationToken ct = default) =>
        ConTiempoAsync(() => EsperaDePregunta, ct, "El asistente tardó demasiado en responder. Prueba con una pregunta más corta.", async limite =>
        {
            var cuerpo = new Dictionary<string, object?> { ["pregunta"] = pregunta, ["actor"] = actor };
            if (!string.IsNullOrEmpty(conversacion)) cuerpo["conversacion"] = conversacion;
            var respuesta = await EnviarAsync<RespuestaDelAgente>(Base + "preguntar/", cuerpo, limite);
            if (respuesta is not null && string.IsNullOrWhiteSpace(respuesta.Texto))
            {
                AnotarMotivo("respuesta_vacia", "El asistente no dio una respuesta. Intenta de nuevo.");
                return null;
            }
            return respuesta;
        });

    public Task<EstadoDelAgente?> EstadoAsync(string actor, CancellationToken ct = default) =>
        ConTiempoAsync(() => EsperaDeEstado, ct, "El nodo no contestó a tiempo sobre el estado del asistente.", limite =>
            ObtenerAsync<EstadoDelAgente>(Base + "estado/" + (string.IsNullOrEmpty(actor) ? string.Empty : "?actor=" + Uri.EscapeDataString(actor)), limite));

    public Task<VozDelAgente?> HablarAsync(string actor, string texto, double velocidad, CancellationToken ct = default) =>
        ConTiempoAsync(() => EsperaDeVoz, ct, "La voz del asistente tardó demasiado. Puedes leer la respuesta.", async limite =>
        {
            using var respuesta = await EnviarParaRespuestaAsync(Base + "hablar/", new { texto, velocidad, actor }, limite);
            if (respuesta is null) return null;
            try
            {
                var wav = await respuesta.Content.ReadAsByteArrayAsync(limite);
                var formato = FormatoWav.Leer(wav);
                if (formato is null)
                {
                    AnotarMotivo("audio_invalido", "La voz del asistente llegó dañada. Puedes leer la respuesta.");
                    RegistroLocal.Error(Canal.Comunicacion, "aiagent.audio_invalido", "El nodo contestó 200 a «hablar» pero el cuerpo no es un WAV válido.",
                                        new { bytes = wav.Length, tipo = respuesta.Content.Headers.ContentType?.MediaType }, corr: UltimoCorr);
                    return null;
                }
                var duracion = EnteroDeCabecera(respuesta.Headers, "X-Audio-Duration-Ms") ?? formato.DuracionMs;
                var trozos = EnteroDeCabecera(respuesta.Headers, "X-Audio-Chunks") ?? 1;
                return new VozDelAgente(wav, duracion, trozos);
            }
            catch (Exception ex) when (ex is HttpRequestException or IOException or OperationCanceledException)
            {
                if (limite.IsCancellationRequested) throw;      // tiempo o cancelación: lo resuelve ConTiempoAsync
                AnotarMotivo("audio_cortado", "La voz del asistente se cortó. Puedes leer la respuesta.");
                RegistroLocal.Advertencia(Canal.Comunicacion, "aiagent.audio_cortado", "La respuesta de «hablar» se cortó a medias.", new { tipo = ex.GetType().Name }, corr: UltimoCorr);
                return null;
            }
        });

    private static int? EnteroDeCabecera(HttpResponseHeaders cabeceras, string nombre) =>
        cabeceras.TryGetValues(nombre, out var valores) && int.TryParse(valores.FirstOrDefault(), out var n) && n >= 0 ? n : null;

    /// <summary>
    /// Corre la llamada con su tope de tiempo. Si la llamada devolvió null porque se agotó NUESTRO tope (no porque la persona canceló), el motivo es «tardó demasiado», no «no hay conexión» (que es
    /// lo que el cliente base deduce de cualquier cancelación). Una cancelación de la persona deja el motivo en blanco: no es un fallo.
    /// </summary>
    private async Task<T?> ConTiempoAsync<T>(Func<TimeSpan> tiempo, CancellationToken ct, string motivoSiVence, Func<CancellationToken, Task<T?>> llamada) where T : class
    {
        using var limite = CancellationTokenSource.CreateLinkedTokenSource(ct);
        limite.CancelAfter(tiempo());
        try
        {
            var resultado = await llamada(limite.Token);
            if (resultado is null) ReinterpretarCancelacion(limite, ct, motivoSiVence);
            return resultado;
        }
        catch (OperationCanceledException)
        {
            ReinterpretarCancelacion(limite, ct, motivoSiVence);
            return null;
        }
    }

    private void ReinterpretarCancelacion(CancellationTokenSource limite, CancellationToken ct, string motivoSiVence)
    {
        if (ct.IsCancellationRequested) { AnotarMotivo("cancelado", "Cancelado."); return; }
        if (limite.IsCancellationRequested) AnotarMotivo("tiempo_agotado", motivoSiVence);
    }
}

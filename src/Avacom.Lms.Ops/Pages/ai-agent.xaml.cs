using System.Text.Json;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// AI Agent (sólo visual): aloja el HybridWebView con la tableta 3D y su rostro animado. El renderizador es JavaScript (Resources/Raw/wwwroot/ai-agent) y habla con esta página por
/// mensajes JSON: <c>ready</c> (listo, con diagnóstico), <c>error</c> (WebGL ausente, GLB incompleto, atlas que no carga…), <c>log</c> (avisos) y <c>state</c> (cambios del rostro).
/// Hacia la página van órdenes <c>{cmd:'play'|'stop'|'expression'|'fps'|'text'|'pause'|'resume'|'dispose'}</c> por <see cref="HybridWebView.SendRawMessage"/>.
/// La conversación con el modelo local y su voz (el chat) vive en <c>AiAgentPage.Chat.cs</c> y <c>ConversacionConAgente</c> (Core); esta parte sólo aloja el visor y le manda órdenes con
/// <see cref="ReproducirAsync"/>, <see cref="TextoAsync"/> y compañía. El chat funciona aunque el visor 3D no arranque.
/// </summary>
public partial class AiAgentPage : ContentPage
{
    private static readonly TimeSpan LimiteDeArranque = TimeSpan.FromSeconds(25);
    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };

    private int _versionArranque;
    private bool _liberado;
    private bool _visorListo;
    private readonly List<string> _ordenesEnEspera = [];          // lo que se mandó al visor antes de que su JavaScript estuviera escuchando: un mensaje a una página que aún no carga se pierde

    public AiAgentPage()
    {
        InitializeComponent();
        IniciarChat();
    }

    protected override void OnAppearing()
    {
        base.OnAppearing();
        if (_liberado) return;
        _ = VigilarArranqueAsync();
        AjustarChat();
        _ = ComprobarServicioAsync();                            // el chat funciona aunque el renderizador 3D no arranque
    }

    /// <summary>Se sale de la pantalla: se detiene el dibujo y se libera la WebView (WebGL incluido). Volver a entrar abre una página nueva, nunca reutiliza esta.</summary>
    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _ = LiberarAsync();
    }

    private async Task LiberarAsync()
    {
        if (_liberado) return;
        _liberado = true;
        _versionArranque++;
        try { _conversacion?.Detener(); }                        // corta la espera del modelo y el sonido: nada debe seguir hablando en otra pantalla
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "AiAgentPage.Detener", ex); }
        try
        {
            Orden("dispose");                                    // cancela el bucle, quita los listeners y suelta geometrías, texturas y el contexto WebGL
            await Task.Delay(120);                               // deja que la orden llegue antes de soltar el control
            Visor.RawMessageReceived -= OnMensajeDelVisor;
            Visor.Handler?.DisconnectHandler();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "AiAgentPage.Liberar", ex); }
    }

    // ---- arranque ----------------------------------------------------------------------------------------------------

    private async Task VigilarArranqueAsync()
    {
        var version = ++_versionArranque;
        MostrarCargando("Preparando a AI Agent…");
        await Task.Delay(LimiteDeArranque);
        if (version != _versionArranque || _liberado || !EstadoPanel.IsVisible || ReintentarButton.IsVisible) return;
        MostrarError("El renderizador no respondió a tiempo. Si el equipo no tiene aceleración gráfica, AI Agent no se puede mostrar.");
        RegistroLocal.Error(Canal.Dispositivo, "aiagent.sin_respuesta", "AI Agent: el visor no avisó que estuviera listo.", new { segundos = LimiteDeArranque.TotalSeconds });
    }

    private void MostrarCargando(string texto)
    {
        EstadoLabel.Text = texto;
        EstadoLabel.TextColor = Color.FromArgb("#52525B");
        Cargando.IsRunning = true;
        Cargando.IsVisible = true;
        ReintentarButton.IsVisible = false;
        EstadoPanel.IsVisible = true;
    }

    private void MostrarError(string texto)
    {
        EstadoLabel.Text = texto;
        EstadoLabel.TextColor = Color.FromArgb("#B42318");
        Cargando.IsRunning = false;
        Cargando.IsVisible = false;
        ReintentarButton.IsVisible = true;
        EstadoPanel.IsVisible = true;
    }

    private void OnMensajeDelVisor(object? sender, HybridWebViewRawMessageReceivedEventArgs e)
    {
        try
        {
            using var doc = JsonDocument.Parse(e.Message ?? "{}");
            var raiz = doc.RootElement;
            var tipo = raiz.TryGetProperty("type", out var t) ? t.GetString() : null;
            switch (tipo)
            {
                case "ready":
                    _versionArranque++;
                    EstadoPanel.IsVisible = false;
                    VaciarOrdenesEnEspera();
                    var diagnostico = raiz.TryGetProperty("diagnostics", out var d) ? d.GetRawText() : null;
                    RegistroLocal.Info(Canal.Aplicacion, "aiagent.listo", "AI Agent: renderizador listo.", diagnostico is null ? null : JsonDocument.Parse(diagnostico).RootElement.Clone());
                    break;
                case "error":
                    var mensaje = raiz.TryGetProperty("message", out var m) ? m.GetString() : "El renderizador no pudo iniciar.";
                    var codigo = raiz.TryGetProperty("code", out var c) ? c.GetString() : null;
                    var detalle = raiz.TryGetProperty("detail", out var dt) ? dt.GetString() : null;
                    _versionArranque++;
                    MostrarError(mensaje ?? "El renderizador no pudo iniciar.");
                    RegistroLocal.Error(Canal.Dispositivo, "aiagent.error", $"AI Agent: {mensaje}", new { codigo, detalle });
                    break;
                case "log":
                    var nivel = raiz.TryGetProperty("level", out var n) ? n.GetString() : "info";
                    var texto = raiz.TryGetProperty("message", out var l) ? l.GetString() ?? "" : "";
                    if (nivel == "error") RegistroLocal.Error(Canal.Aplicacion, "aiagent.js", texto);
                    else if (nivel == "warn") RegistroLocal.Advertencia(Canal.Aplicacion, "aiagent.aviso", texto);
                    break;
                // «state» (cambios de animación) no se registra: es ruido; el agente real lo usará para sincronizar el habla.
            }
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "AiAgentPage.Mensaje", ex); }
    }

    // ---- botones -----------------------------------------------------------------------------------------------------

    private async void OnVolverClicked(object? sender, EventArgs e)
    {
        try { await Shell.Current.GoToAsync(".."); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "AiAgentPage.Volver", ex); }
    }

    private async void OnReintentarClicked(object? sender, EventArgs e)
    {
        try
        {
            MostrarCargando("Preparando a AI Agent…");
            _visorListo = false;                                  // la página se recarga: hasta que avise «ready» las órdenes esperan
            _ = VigilarArranqueAsync();
            await Visor.EvaluateJavaScriptAsync("location.reload()");
        }
        catch (Exception ex)
        {
            MostrarError("No se pudo reiniciar el renderizador. Sal de la pantalla y vuelve a entrar.");
            RegistroDeFallos.Escribir("ops", "AiAgentPage.Reintentar", ex);
        }
    }

    // ---- control desde C# (para cuando haya un agente real) ------------------------------------------------------------

    /// <summary>Reproduce una animación del rostro: idle, blink, happy, tender, talking o thinking.</summary>
    public Task ReproducirAsync(string nombre) => EnviarAsync(new { cmd = "play", name = nombre });
    /// <summary>Detiene la animación en curso y vuelve a idle.</summary>
    public Task DetenerAsync() => EnviarAsync(new { cmd = "stop" });
    /// <summary>Muestra una expresión fija, sin animar.</summary>
    public Task ExpresionAsync(string nombre) => EnviarAsync(new { cmd = "expression", name = nombre });
    /// <summary>Velocidad de las secuencias (1 a 30 cuadros por segundo).</summary>
    public Task FpsAsync(double fps) => EnviarAsync(new { cmd = "fps", fps });
    /// <summary>El texto que se ve bajo el personaje.</summary>
    public Task TextoAsync(string texto) => EnviarAsync(new { cmd = "text", text = texto });

    private Task EnviarAsync(object orden)
    {
        if (_liberado) return Task.CompletedTask;
        try
        {
            var texto = JsonSerializer.Serialize(orden, Json);
            if (!_visorListo)
            {
                // Se conservan las últimas 16 (una animación vieja no importa; el texto y el último estado sí).
                _ordenesEnEspera.Add(texto);
                if (_ordenesEnEspera.Count > 16) _ordenesEnEspera.RemoveAt(0);
                return Task.CompletedTask;
            }
            Visor.SendRawMessage(texto);
        }
        catch (Exception ex)
        {
            // El personaje es un acompañante: si el visor no está listo o falló, el chat sigue sin él (la causa ya la contó el arranque).
            RegistroLocal.Advertencia(Canal.Aplicacion, "aiagent.orden_no_enviada", "AI Agent: no se pudo mandar una orden al visor.", new { tipo = ex.GetType().Name });
        }
        return Task.CompletedTask;
    }

    /// <summary>El visor avisó que está listo: se le manda, en orden, lo que quedó esperando.</summary>
    private void VaciarOrdenesEnEspera()
    {
        _visorListo = true;
        try
        {
            foreach (var orden in _ordenesEnEspera) Visor.SendRawMessage(orden);
        }
        catch (Exception ex) { RegistroLocal.Advertencia(Canal.Aplicacion, "aiagent.orden_no_enviada", "AI Agent: no se pudieron mandar las órdenes en espera al visor.", new { tipo = ex.GetType().Name }); }
        finally { _ordenesEnEspera.Clear(); }
    }

    private void Orden(string cmd) => Visor.SendRawMessage(JsonSerializer.Serialize(new { cmd }, Json));
}

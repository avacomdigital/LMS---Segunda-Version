using System.Text.Json;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// AI Agent (sólo visual): aloja el HybridWebView con la tableta 3D y su rostro animado. El renderizador es JavaScript (Resources/Raw/wwwroot/ai-agent) y habla con esta página por
/// mensajes JSON: <c>ready</c> (listo, con diagnóstico), <c>error</c> (WebGL ausente, GLB incompleto, atlas que no carga…), <c>log</c> (avisos) y <c>state</c> (cambios del rostro).
/// Hacia la página van órdenes <c>{cmd:'play'|'stop'|'expression'|'fps'|'text'|'pause'|'resume'|'dispose'}</c> por <see cref="HybridWebView.SendRawMessage"/>.
/// Sin LLM, sin voz y sin red: el agente real se conectará llamando a <see cref="ReproducirAsync"/>, <see cref="TextoAsync"/> y compañía.
/// </summary>
public partial class AiAgentPage : ContentPage
{
    private static readonly TimeSpan LimiteDeArranque = TimeSpan.FromSeconds(25);
    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };

    private int _versionArranque;
    private bool _liberado;

    public AiAgentPage() => InitializeComponent();

    protected override void OnAppearing()
    {
        base.OnAppearing();
        if (_liberado) return;
        _ = VigilarArranqueAsync();
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
        Visor.SendRawMessage(JsonSerializer.Serialize(orden, Json));
        return Task.CompletedTask;
    }

    private void Orden(string cmd) => Visor.SendRawMessage(JsonSerializer.Serialize(new { cmd }, Json));
}

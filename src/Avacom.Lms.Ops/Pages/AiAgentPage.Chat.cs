using Avacom.Lms.Core.AgenteIa;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.AgenteIa;
using Avacom.Lms.Ui.Controls;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// El chat de AI Agent: la persona escribe (o toca una sugerencia), el asistente responde por escrito y, si la persona quiere, en voz alta mientras el personaje 3D «piensa» y «habla».
///
/// Esta pantalla es SÓLO la interfaz. Hablar con la IA —el nodo, el modelo, la voz, el audio, los reintentos, el registro de los fallos— lo hace <see cref="ConversacionConAgente"/> (Core), que
/// jamás lanza una excepción; aquí se pinta lo que devuelve. Si la IA no responde, la pantalla lo dice con un texto claro y un botón (Reintentar / Escuchar de nuevo) y todo lo demás sigue
/// funcionando: el nodo ya asentó el fallo en la bitácora y en su log, y esta app en su log local. Ni un 503, ni un audio dañado, ni un reproductor roto cierran la aplicación.
///
/// <b>Sin teclado.</b> El equipo principal puede no tenerlo: las preguntas sugeridas se tocan, y el campo usa el teclado táctil del sistema cuando hace falta.
/// </summary>
public partial class AiAgentPage
{
    private const string ClaveVoz = "ai_agent_voz";
    private static readonly string[] Sugerencias =
    [
        "¿Qué puedes hacer por mí?",
        "¿Qué es AVACOM?",
        "Dame una idea para empezar una clase",
        "Explícame las fracciones de forma sencilla",
    ];

    private ConversacionConAgente? _conversacion;
    private IReproductorDeAudio? _reproductor;
    private Border? _pensando;                       // la burbuja «Pensando…» mientras el modelo trabaja
    private string? _preguntaPendiente;              // lo que se vuelve a enviar con «Reintentar»
    private string? _textoParaEscuchar;              // lo que se vuelve a leer con «Escuchar de nuevo»
    private Func<Task>? _accionDelAviso;
    private bool _enviando, _servicioListo, _chatDeshabilitado, _esperandoRespuesta, _vozDisponible = true;
    private int _versionServicio;

    private static string Actor => Sesion.ProfesorId;

    static AiAgentPage() => NeumoChrome.Registrar();          // el campo de texto sin el borde nativo de Windows (el aspecto lo da la cápsula que lo envuelve)

    private void IniciarChat()
    {
        try
        {
            _reproductor = new ReproductorWindows { Volumen = Ajustes.VolumenDePrueba ?? 1.0 };
        }
        catch (Exception ex)
        {
            // Sin reproductor la conversación sigue siendo por escrito (la voz se avisa como no disponible).
            RegistroLocal.Error(Canal.Dispositivo, "aiagent.sin_reproductor", "No se pudo preparar el reproductor de audio del asistente.", ex: ex);
            _reproductor = new SinReproductor();
        }
        _conversacion = new ConversacionConAgente(Sesion.AgenteIa, _reproductor, () => Actor);
        _conversacion.EstadoCambiado += (estado, mensaje) => EnHiloDeInterfaz(() => AplicarEstadoDelAvatar(estado, mensaje));
        _conversacion.TextoListo += texto => EnHiloDeInterfaz(() => MostrarRespuesta(texto));

        PreguntaEntry.ClassId = NeumoChrome.Clase;
        VozSwitch.IsToggled = Ajustes.Get(ClaveVoz, true);
        foreach (var sugerencia in Sugerencias)
            SugerenciasHost.Add(NuevaSugerencia(sugerencia));
        SizeChanged += (_, _) => AjustarChat();
    }

    private static void EnHiloDeInterfaz(Action accion)
    {
        try
        {
            if (MainThread.IsMainThread) accion();
            else MainThread.BeginInvokeOnMainThread(() => { try { accion(); } catch (Exception ex) { RegistroDeFallos.Escribir("ops", "AiAgentPage.Chat", ex); } });
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "AiAgentPage.Chat", ex); }
    }

    /// <summary>El panel ocupa el tercio derecho (menos un margen) para que el personaje quede libre en el centro; nunca menos de 300 ni más de 440 px.</summary>
    private void AjustarChat()
    {
        if (Width <= 0) return;
        ChatPanel.WidthRequest = Math.Clamp(Width / 3 - 32, 300, 440);
    }

    // ---------------------------------------------------------------------------------------------- el servicio

    /// <summary>Pregunta al nodo si el asistente está disponible y lo dice en la cabecera. No impide escribir (el servicio puede levantarse): sólo avisa.</summary>
    private async Task ComprobarServicioAsync()
    {
        var version = ++_versionServicio;
        try
        {
            ServicioLabel.Text = "Comprobando el asistente…";
            ServicioLabel.TextColor = Color.FromArgb("#71717A");
            var estado = await _conversacion!.ConsultarEstadoAsync();
            if (version != _versionServicio || _liberado) return;
            if (Ajustes.TomarPreguntaDePrueba() is { } deprueba) _ = EnviarAsync(deprueba, nueva: true);     // sólo con el perfil de pruebas
            var texto = TextoDelAgente.ParaEstado(estado);
            _servicioListo = estado is { Disponible: true };
            if (_servicioListo)
            {
                ServicioLabel.Text = estado!.VozDisponible ? "Asistente listo" : "Asistente listo (sin voz)";
                ServicioLabel.TextColor = Color.FromArgb("#067647");
                PonerVozDisponible(estado.VozDisponible);
                QuitarAviso();
                Deshabilitar(false);
                return;
            }
            ServicioLabel.Text = estado is null ? "Sin conexión con el aula" : "Asistente no disponible";
            ServicioLabel.TextColor = Color.FromArgb("#B42318");
            // Si reintentar no cambia nada (desactivado, sin configurar) no se deja escribir; si puede levantarse solo, se deja y se avisa.
            var sinRemedio = estado is { Codigo: "ai_disabled" or "llm_model_missing" or "context_unavailable" };
            MostrarAviso(texto + (estado?.Sugerencia is { Length: > 0 } s ? " " + s : string.Empty), "Comprobar de nuevo", ComprobarServicioAsync);
            Deshabilitar(sinRemedio);
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("ops", "AiAgentPage.ComprobarServicio", ex);
            if (version == _versionServicio && !_liberado) MostrarAviso(TextoDelAgente.Generico, "Comprobar de nuevo", ComprobarServicioAsync);
        }
    }

    /// <summary>Si el servicio no tiene voz, el interruptor se apaga y se deshabilita SIN tocar la preferencia guardada de la persona (cuando la voz vuelva, vuelve a estar como la dejó).</summary>
    private void PonerVozDisponible(bool si)
    {
        _vozDisponible = si;
        VozSwitch.IsEnabled = si;
        VozLabel.Text = si ? "Leer las respuestas en voz alta" : "La voz del asistente no está disponible";
    }

    private bool HablarEnVoz => VozSwitch.IsToggled && _vozDisponible;

    private void Deshabilitar(bool si)
    {
        _chatDeshabilitado = si;
        PreguntaEntry.IsEnabled = !si;
        EnviarButton.IsEnabled = !si;
        foreach (var chip in SugerenciasHost.Children.OfType<Button>()) chip.IsEnabled = !si;
    }

    // ---------------------------------------------------------------------------------------------- enviar

    private async void OnEnviarClicked(object? sender, EventArgs e)
    {
        try
        {
            if (_enviando) { _conversacion?.Detener(); return; }          // el mismo botón es «Detener» mientras el asistente trabaja
            await EnviarAsync(PreguntaEntry.Text, nueva: true);
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "AiAgentPage.Enviar", ex); }
    }

    private async void OnPreguntaCompleted(object? sender, EventArgs e)
    {
        try { if (!_enviando) await EnviarAsync(PreguntaEntry.Text, nueva: true); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "AiAgentPage.Enviar", ex); }
    }

    private async Task EnviarAsync(string? pregunta, bool nueva)
    {
        if (_conversacion is null || _enviando || _chatDeshabilitado || _liberado) return;
        var texto = (pregunta ?? string.Empty).Trim();
        if (texto.Length == 0) { MostrarAviso("Escribe una pregunta.", null, null); return; }
        if (texto.Length > ConversacionConAgente.MaximoDePregunta) { MostrarAviso($"La pregunta es demasiado larga (máximo {ConversacionConAgente.MaximoDePregunta} caracteres).", null, null); return; }

        QuitarAviso();
        _preguntaPendiente = texto;
        _textoParaEscuchar = null;
        if (nueva)
        {
            AgregarPregunta(texto);
            PreguntaEntry.Text = string.Empty;
        }
        PonerEnviando(true);
        try
        {
            _esperandoRespuesta = true;
            var resultado = await _conversacion.PreguntarAsync(texto, hablar: HablarEnVoz);
            if (_liberado) return;
            _esperandoRespuesta = false;
            QuitarPensando();
            ResolverResultado(resultado);
        }
        catch (Exception ex)
        {
            // ConversacionConAgente no lanza; esto es la última red por si algo de ESTA pantalla falla.
            RegistroDeFallos.Escribir("ops", "AiAgentPage.EnviarAsync", ex);
            _esperandoRespuesta = false;
            QuitarPensando();
            if (!_liberado) MostrarAviso(TextoDelAgente.Generico, "Reintentar", () => EnviarAsync(_preguntaPendiente, nueva: false));
        }
        finally { _esperandoRespuesta = false; PonerEnviando(false); }
    }

    private void ResolverResultado(ResultadoDelTurno r)
    {
        if (r.Cancelado) return;
        if (!r.Respondio)
        {
            // La IA no respondió: el aviso dice por qué (en español, sin detalles técnicos) y, si reintentar sirve, deja el botón.
            var pregunta = _preguntaPendiente;
            MostrarAviso(r.Aviso ?? TextoDelAgente.Generico, r.Reintentable ? "Reintentar" : null, r.Reintentable ? () => EnviarAsync(pregunta, nueva: false) : null);
            return;
        }
        if (!r.Hablo && r.Aviso is not null)
        {
            // La respuesta escrita ya está en pantalla; sólo falló la voz.
            var texto = r.Texto;
            MostrarAviso(r.Aviso, r.Reintentable ? "Escuchar de nuevo" : null, r.Reintentable ? () => EscucharAsync(texto) : null);
        }
    }

    private async Task EscucharAsync(string? texto)
    {
        if (_conversacion is null || _enviando || _liberado || string.IsNullOrWhiteSpace(texto)) return;
        QuitarAviso();
        PonerEnviando(true);
        try
        {
            var r = await _conversacion.EscucharAsync(texto);
            if (!_liberado && !r.Cancelado && !r.Hablo && r.Aviso is not null)
                MostrarAviso(r.Aviso, r.Reintentable ? "Escuchar de nuevo" : null, r.Reintentable ? () => EscucharAsync(texto) : null);
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "AiAgentPage.Escuchar", ex); }
        finally { PonerEnviando(false); }
    }

    private void PonerEnviando(bool si)
    {
        _enviando = si;
        EnviarButton.Text = si ? "Detener" : "Enviar";
        EnviarButton.BackgroundColor = si ? Color.FromArgb("#B42318") : Color.FromArgb("#18181B");
        PreguntaEntry.IsEnabled = !si && !_chatDeshabilitado;
        NuevaButton.IsEnabled = !si;
        foreach (var chip in SugerenciasHost.Children.OfType<Button>()) chip.IsEnabled = !si && !_chatDeshabilitado;
    }

    // ---------------------------------------------------------------------------------------------- el personaje

    /// <summary>Pensando → «thinking»; hablando → «talking»; error → «tender» (una expresión amable); reposo → idle. El visor ignora las órdenes si no está listo: la conversación no depende de él.</summary>
    private void AplicarEstadoDelAvatar(EstadoDelAvatar estado, string? mensaje)
    {
        if (_liberado) return;
        switch (estado)
        {
            case EstadoDelAvatar.Pensando:
                _ = ReproducirAsync("thinking");
                if (_esperandoRespuesta && _pensando is null) MostrarPensando();
                break;
            case EstadoDelAvatar.Hablando:
                _ = ReproducirAsync("talking");
                break;
            case EstadoDelAvatar.Error:
                _ = ReproducirAsync("tender");
                break;
            default:
                _ = DetenerAsync();
                break;
        }
    }

    // ---------------------------------------------------------------------------------------------- mensajes

    private void MostrarRespuesta(string texto)
    {
        if (_liberado) return;
        QuitarPensando();
        _textoParaEscuchar = texto;
        AgregarRespuesta(texto);
        _ = TextoAsync(Subtitulo(texto));                // el texto también bajo el personaje (subtítulo para toda la clase)
    }

    /// <summary>
    /// Lo que se ve bajo el personaje: el principio de la respuesta, cortado en una frase o una palabra y con «…». Una respuesta de 600 caracteres ahí encogería al personaje; la respuesta
    /// completa está en la conversación.
    /// </summary>
    internal static string Subtitulo(string texto, int maximo = 220)
    {
        var t = texto.Trim();
        if (t.Length <= maximo) return t;
        var corte = t.LastIndexOfAny(['.', '!', '?', '…'], maximo - 1);
        if (corte < maximo / 2) corte = t.LastIndexOf(' ', maximo - 1);
        if (corte <= 0) corte = maximo - 1;
        var recorte = t[..(corte + 1)].TrimEnd();
        return recorte.EndsWith('.') || recorte.EndsWith('!') || recorte.EndsWith('?') || recorte.EndsWith('…') ? recorte + " …" : recorte + "…";
    }

    private void AgregarPregunta(string texto)
    {
        OcultarInicio();
        MensajesHost.Add(Burbuja(texto, propia: true));
        Desplazar();
    }

    private void AgregarRespuesta(string texto)
    {
        OcultarInicio();
        var burbuja = Burbuja(texto, propia: false);
        var escuchar = new Button
        {
            Text = "Escuchar", AutomationId = "ai-agent-escuchar", HeightRequest = 40, MinimumWidthRequest = 96, Padding = new Thickness(14, 0), CornerRadius = 12, FontSize = 13,
            BackgroundColor = Colors.White, TextColor = Color.FromArgb("#18181B"), BorderColor = Color.FromArgb("#17000000"), BorderWidth = 1, HorizontalOptions = LayoutOptions.Start,
        };
        escuchar.Clicked += async (_, _) => { try { await EscucharAsync(texto); } catch (Exception ex) { RegistroDeFallos.Escribir("ops", "AiAgentPage.Escuchar", ex); } };
        MensajesHost.Add(new VerticalStackLayout { Spacing = 4, Children = { burbuja, escuchar }, HorizontalOptions = LayoutOptions.Start });
        Desplazar();
    }

    private void MostrarPensando()
    {
        OcultarInicio();
        _pensando = Burbuja("Pensando…", propia: false, suave: true);
        MensajesHost.Add(_pensando);
        Desplazar();
    }

    private void QuitarPensando()
    {
        if (_pensando is null) return;
        MensajesHost.Remove(_pensando);
        _pensando = null;
    }

    private Border Burbuja(string texto, bool propia, bool suave = false)
    {
        var ancho = Math.Max(220, ChatPanel.WidthRequest * 0.84);
        return new Border
        {
            HorizontalOptions = propia ? LayoutOptions.End : LayoutOptions.Start,
            BackgroundColor = Color.FromArgb(propia ? "#18181B" : "#F4F4F5"),
            StrokeThickness = 0,
            Padding = new Thickness(14, 10),
            MaximumWidthRequest = ancho,
            StrokeShape = new RoundRectangle { CornerRadius = new CornerRadius(16) },
            Content = new Label
            {
                Text = texto, FontSize = 15, LineBreakMode = LineBreakMode.WordWrap, TextType = TextType.Text,
                TextColor = Color.FromArgb(propia ? "#FFFFFF" : suave ? "#71717A" : "#18181B"),
                FontAttributes = suave ? FontAttributes.Italic : FontAttributes.None,
            },
        };
    }

    private Button NuevaSugerencia(string texto)
    {
        var chip = new Button
        {
            Text = texto, AutomationId = "ai-agent-sugerencia", HeightRequest = 48, Padding = new Thickness(16, 0), CornerRadius = 14, FontSize = 14,
            BackgroundColor = Colors.White, TextColor = Color.FromArgb("#18181B"), BorderColor = Color.FromArgb("#17000000"), BorderWidth = 1, Margin = new Thickness(0, 0, 8, 8),
        };
        chip.Clicked += async (_, _) => { try { await EnviarAsync(texto, nueva: true); } catch (Exception ex) { RegistroDeFallos.Escribir("ops", "AiAgentPage.Sugerencia", ex); } };
        return chip;
    }

    private void OcultarInicio()
    {
        VacioLabel.IsVisible = false;
        SugerenciasHost.IsVisible = false;
    }

    private async void Desplazar()
    {
        try
        {
            await Task.Delay(60);                         // deja que el diseño mida la burbuja nueva antes de bajar
            if (!_liberado) await MensajesScroll.ScrollToAsync(MensajesHost, ScrollToPosition.End, animated: false);
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "AiAgentPage.Desplazar", ex); }
    }

    // ---------------------------------------------------------------------------------------------- aviso y botones

    private void MostrarAviso(string texto, string? accion, Func<Task>? alAccionar)
    {
        AvisoLabel.Text = texto;
        _accionDelAviso = alAccionar;
        AvisoAccionButton.Text = accion ?? string.Empty;
        AvisoAccionButton.IsVisible = accion is not null && alAccionar is not null;
        AvisoBorder.IsVisible = true;
    }

    private void QuitarAviso()
    {
        AvisoBorder.IsVisible = false;
        _accionDelAviso = null;
    }

    private async void OnAvisoAccionClicked(object? sender, EventArgs e)
    {
        try
        {
            var accion = _accionDelAviso;
            if (accion is null) return;
            QuitarAviso();
            await accion();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "AiAgentPage.AvisoAccion", ex); }
    }

    private void OnAvisoCerrarClicked(object? sender, EventArgs e) => QuitarAviso();

    private void OnNuevaClicked(object? sender, EventArgs e)
    {
        try
        {
            _conversacion?.NuevaConversacion();               // el modelo deja de acordarse de lo anterior
            MensajesHost.Children.Clear();
            MensajesHost.Add(VacioLabel);
            MensajesHost.Add(SugerenciasHost);
            VacioLabel.IsVisible = true;
            SugerenciasHost.IsVisible = true;
            _pensando = null;
            _preguntaPendiente = _textoParaEscuchar = null;
            QuitarAviso();
            _ = TextoAsync(string.Empty);
            _ = DetenerAsync();
            PreguntaEntry.Text = string.Empty;
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "AiAgentPage.Nueva", ex); }
    }

    private void OnVozToggled(object? sender, ToggledEventArgs e)
    {
        try
        {
            Ajustes.Set(ClaveVoz, e.Value);
            if (!e.Value) _reproductor?.Detener();            // al apagar la voz se corta lo que suene (la respuesta escrita se conserva)
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "AiAgentPage.Voz", ex); }
    }
}

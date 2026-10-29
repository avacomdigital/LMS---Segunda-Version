using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.AgenteIa;

/// <summary>
/// Un turno de conversación con el agente de IA, de la pregunta al sonido: pregunta al modelo (pasos 1 y 2) → muestra el texto → pide la voz (3 y 4) → la reproduce (5), con los estados del
/// avatar (reposo → pensando → hablando → reposo) y sin conocer ninguna pantalla: la UI se suscribe a <see cref="EstadoCambiado"/> y <see cref="TextoListo"/>.
///
/// <b>Regla de oro: nada de lo que pase aquí rompe la aplicación.</b> Ni el nodo apagado, ni el servicio de IA caído, ni un tiempo agotado, ni un audio dañado, ni un reproductor que falla, ni un
/// defecto propio: <see cref="PreguntarAsync"/> y <see cref="EscucharAsync"/> NUNCA lanzan; devuelven un <see cref="ResultadoDelTurno"/> con el texto para la persona y el código para quien
/// diagnostica. Cada fallo queda en el log local (<see cref="RegistroLocal"/>: archivo del equipo y, desde WARNING, entrega al nodo) y el NODO ya lo asentó en la bitácora (el cliente sólo ve un
/// código). Ni la pregunta ni la respuesta se escriben en ningún log: sólo longitudes, tiempos y códigos.
///
/// <b>El texto no depende de la voz.</b> Si el modelo respondió y la voz falla, la respuesta ya está en pantalla (<see cref="TextoListo"/> se dispara antes de pedir la voz) y el resultado dice
/// <c>Respondio = true, Hablo = false</c> con el aviso: la persona puede «Escuchar de nuevo» con <see cref="EscucharAsync"/>.
///
/// Un turno a la vez: una pregunta mientras hay otra en curso se rechaza con el código <c>ocupado</c> (no se encola ni se pisa).
/// </summary>
public sealed class ConversacionConAgente(IAgenteIaApi api, IReproductorDeAudio reproductor, Func<string> actor)
{
    public const int MaximoDePregunta = 2000;
    /// <summary>Cuánto se queda el avatar en «error» antes de volver al reposo si nadie lo cambia antes.</summary>
    public static TimeSpan DuracionDelError { get; set; } = TimeSpan.FromSeconds(3);
    /// <summary>Velocidad de la voz (1,0 = normal). Contrato §5, paso 3: entre 0,5 y 2,0.</summary>
    public double Velocidad { get; set; } = 1.0;

    private readonly object _cerrojo = new();
    private CancellationTokenSource? _turno;
    private int _generacion;

    /// <summary>El id opaco de esta conversación (con él el modelo recuerda lo anterior). Cambia con <see cref="NuevaConversacion"/>.</summary>
    public string IdDePantalla { get; private set; } = NuevoId();
    public EstadoDelAvatar Estado { get; private set; } = EstadoDelAvatar.Reposo;
    public bool Ocupada { get { lock (_cerrojo) return _turno is not null; } }

    /// <summary>El avatar cambió de estado (y, en <see cref="EstadoDelAvatar.Error"/>, el texto para la persona). Se dispara desde el hilo que trabaja: la UI debe pasarlo al suyo.</summary>
    public event Action<EstadoDelAvatar, string?>? EstadoCambiado;
    /// <summary>La respuesta del modelo llegó (antes de pedir la voz). Texto plano.</summary>
    public event Action<string>? TextoListo;

    private static string NuevoId() => "ops-" + Guid.NewGuid().ToString("N")[..16];

    /// <summary>Empieza otra conversación: el modelo deja de acordarse de la anterior.</summary>
    public void NuevaConversacion()
    {
        Detener();
        IdDePantalla = NuevoId();
    }

    /// <summary>La persona dejó de esperar: cancela la petición en curso y corta el sonido.</summary>
    public void Detener()
    {
        CancellationTokenSource? turno;
        lock (_cerrojo) turno = _turno;
        try { turno?.Cancel(); } catch (ObjectDisposedException) { }
        try { reproductor.Detener(); } catch (Exception ex) { RegistroLocal.Advertencia(Canal.Dispositivo, "aiagent.detener_fallo", "No se pudo cortar el audio.", new { tipo = ex.GetType().Name }); }
    }

    /// <summary>Qué dice el nodo del servicio de IA. Null sólo si el nodo no contesta (el texto para la persona está en <see cref="TextoDelAgente.SinNodo"/>).</summary>
    public async Task<EstadoDelAgente?> ConsultarEstadoAsync(CancellationToken ct = default)
    {
        try
        {
            var estado = await api.EstadoAsync(actor(), ct);
            if (estado is { Disponible: false } && ct.IsCancellationRequested == false)
                RegistroLocal.Advertencia(Canal.Comunicacion, "aiagent.no_disponible", "El asistente de IA no está disponible.", new { codigo = estado.Codigo, servicio_activo = estado.ServicioActivo });
            else if (estado is null && !ct.IsCancellationRequested)
                RegistroLocal.Advertencia(Canal.Comunicacion, "aiagent.estado_sin_respuesta", "El nodo no dijo el estado del asistente.", new { codigo = api.UltimoError?.Codigo, estado = api.UltimoError?.Estado });
            return estado;
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            RegistroDeFallos.Escribir("ops", "ConversacionConAgente.Estado", ex);
            return null;
        }
        catch (OperationCanceledException) { return null; }
    }

    // ---------------------------------------------------------------------------------------------- un turno

    /// <summary>La pregunta de la persona: modelo → texto → (si <paramref name="hablar"/>) voz → sonido.</summary>
    public async Task<ResultadoDelTurno> PreguntarAsync(string? pregunta, bool hablar = true, CancellationToken ct = default)
    {
        var texto = (pregunta ?? string.Empty).Trim();
        if (texto.Length == 0) return Rechazo("Escribe una pregunta.", "question_required");
        if (texto.Length > MaximoDePregunta) return Rechazo($"La pregunta es demasiado larga (máximo {MaximoDePregunta} caracteres).", "question_too_long");
        var (turno, generacion) = Empezar(ct, out var rechazo);
        if (turno is null) return rechazo!;
        string? respuesta = null;
        try
        {
            Cambiar(EstadoDelAvatar.Pensando, null, generacion);
            var reloj = System.Diagnostics.Stopwatch.StartNew();
            var datos = await api.PreguntarAsync(actor(), texto, IdDePantalla, turno.Token);
            if (turno.IsCancellationRequested) return Terminar(ResultadoDelTurno.Cancelada(), generacion);
            if (datos is null) return Fallar("aiagent.consulta_fallida", "El agente de IA no respondió.", generacion, turno.Token, new { longitud_pregunta = texto.Length, ms = reloj.ElapsedMilliseconds });
            respuesta = datos.Texto;
            RegistroLocal.Info(Canal.Aplicacion, "aiagent.consulta", "El agente de IA respondió.", new { longitud_pregunta = texto.Length, longitud_texto = respuesta.Length, ms = reloj.ElapsedMilliseconds, modelo = datos.Modelo });
            AvisarTexto(respuesta);
            if (!hablar) return Terminar(new ResultadoDelTurno(true, respuesta, false, null, null, false), generacion);
            return await HablarElTextoAsync(respuesta, generacion, turno.Token);
        }
        catch (OperationCanceledException) { return Terminar(ResultadoDelTurno.Cancelada(respuesta), generacion); }
        catch (Exception ex)
        {
            // Un defecto nuestro: se registra completo (la persona sólo ve un texto) y la app sigue.
            RegistroDeFallos.Escribir("ops", "ConversacionConAgente.Preguntar", ex);
            return Fallar("aiagent.defecto", "Falló el turno de conversación.", generacion, CancellationToken.None, new { tipo = ex.GetType().Name }, TextoDelAgente.Generico, "ai_cliente", true, respuesta);
        }
        finally { Liberar(turno); }
    }

    /// <summary>«Escuchar de nuevo»: la voz de un texto que ya se mostró (o la que falló). No vuelve a preguntarle al modelo.</summary>
    public async Task<ResultadoDelTurno> EscucharAsync(string? texto, CancellationToken ct = default)
    {
        var limpio = (texto ?? string.Empty).Trim();
        if (limpio.Length == 0) return Rechazo("No hay nada que leer en voz alta.", "text_required");
        var (turno, generacion) = Empezar(ct, out var rechazo);
        if (turno is null) return rechazo!;
        try
        {
            Cambiar(EstadoDelAvatar.Pensando, null, generacion);
            return await HablarElTextoAsync(limpio, generacion, turno.Token);
        }
        catch (OperationCanceledException) { return Terminar(ResultadoDelTurno.Cancelada(limpio), generacion); }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("ops", "ConversacionConAgente.Escuchar", ex);
            return Fallar("aiagent.defecto", "Falló la lectura en voz alta.", generacion, CancellationToken.None, new { tipo = ex.GetType().Name }, TextoDelAgente.Generico, "ai_cliente", true, limpio);
        }
        finally { Liberar(turno); }
    }

    /// <summary>Pasos 3, 4 y 5. El texto ya está en pantalla: aquí NADA lo quita; un fallo sólo cambia el aviso.</summary>
    private async Task<ResultadoDelTurno> HablarElTextoAsync(string texto, int generacion, CancellationToken ct)
    {
        var reloj = System.Diagnostics.Stopwatch.StartNew();
        var voz = await api.HablarAsync(actor(), texto, Math.Clamp(Velocidad, 0.5, 2.0), ct);
        if (ct.IsCancellationRequested) return Terminar(ResultadoDelTurno.Cancelada(texto), generacion);
        if (voz is null)
        {
            var (aviso, codigo, reintentable) = Motivo(api);
            RegistroLocal.Advertencia(Canal.Comunicacion, "aiagent.voz_fallida", "No se pudo obtener la voz del asistente.",
                                      new { codigo, longitud_texto = texto.Length, ms = reloj.ElapsedMilliseconds, estado = api.UltimoError?.Estado });
            return Terminar(new ResultadoDelTurno(true, texto, false, aviso, codigo, reintentable), generacion);
        }
        try
        {
            Cambiar(EstadoDelAvatar.Hablando, null, generacion);
            await reproductor.ReproducirAsync(voz.Wav, voz.DuracionMs, ct);
        }
        catch (OperationCanceledException) { return Terminar(ResultadoDelTurno.Cancelada(texto), generacion); }
        catch (Exception ex)
        {
            RegistroLocal.Error(Canal.Dispositivo, "aiagent.reproduccion_fallida", "El equipo no pudo reproducir la voz del asistente.", new { tipo = ex.GetType().Name, duracion_ms = voz.DuracionMs, bytes = voz.Wav.Length }, ex);
            return Terminar(new ResultadoDelTurno(true, texto, false, "No se pudo reproducir la voz en este equipo. Puedes leer la respuesta.", "reproduccion_fallida", true), generacion);
        }
        return Terminar(new ResultadoDelTurno(true, texto, true, null, null, false), generacion);
    }

    // ---------------------------------------------------------------------------------------------- apoyo

    private (CancellationTokenSource? Turno, int Generacion) Empezar(CancellationToken ct, out ResultadoDelTurno? rechazo)
    {
        lock (_cerrojo)
        {
            if (_turno is not null)
            {
                rechazo = Rechazo("Estoy atendiendo tu pregunta anterior. Espera a que termine.", "ocupado", reintentable: true);
                return (null, 0);
            }
            rechazo = null;
            _turno = CancellationTokenSource.CreateLinkedTokenSource(ct);
            return (_turno, ++_generacion);
        }
    }

    private void Liberar(CancellationTokenSource turno)
    {
        lock (_cerrojo)
        {
            if (ReferenceEquals(_turno, turno)) _turno = null;
        }
        turno.Dispose();
    }

    private static ResultadoDelTurno Rechazo(string aviso, string codigo, bool reintentable = false) => new(false, null, false, aviso, codigo, reintentable);

    private ResultadoDelTurno Terminar(ResultadoDelTurno resultado, int generacion)
    {
        Cambiar(EstadoDelAvatar.Reposo, null, generacion);
        return resultado;
    }

    /// <summary>Un fallo: se registra, el avatar pasa a «error» unos segundos con el texto para la persona y vuelve solo al reposo.</summary>
    private ResultadoDelTurno Fallar(string evento, string mensaje, int generacion, CancellationToken ct, object detalle, string? aviso = null, string? codigo = null, bool reintentable = false, string? texto = null)
    {
        if (ct.IsCancellationRequested) return Terminar(ResultadoDelTurno.Cancelada(), generacion);
        var (avisoNodo, codigoNodo, reintentableNodo) = Motivo(api);
        aviso ??= avisoNodo;
        codigo ??= codigoNodo;
        if (codigo != "ai_cliente") reintentable = reintentableNodo;
        RegistroLocal.Advertencia(Canal.Comunicacion, evento, mensaje, new { codigo, estado = api.UltimoError?.Estado, reintentable, detalle });
        Cambiar(EstadoDelAvatar.Error, aviso, generacion);
        _ = VolverAlReposoAsync(generacion);
        return new ResultadoDelTurno(texto is not null, texto, false, aviso, codigo, reintentable);
    }

    private static (string Aviso, string? Codigo, bool Reintentable) Motivo(IAgenteIaApi api)
    {
        var aviso = TextoDelAgente.Para(api.UltimoError, api.UltimoMotivo);
        // La sugerencia del nodo («avisa a quien administra el equipo…») es lo que la persona puede HACER: se le dice junto al motivo.
        if (api.UltimoError?.Sugerencia is { Length: > 0 } sugerencia && !aviso.Contains(sugerencia)) aviso += " " + sugerencia;
        return (aviso, api.UltimoError?.Codigo ?? (api.UltimoError is { Estado: 0 } ? "sin_conexion" : null), TextoDelAgente.Reintentable(api.UltimoError));
    }

    private async Task VolverAlReposoAsync(int generacion)
    {
        try
        {
            await Task.Delay(DuracionDelError);
            Cambiar(EstadoDelAvatar.Reposo, null, generacion, soloSiError: true);
        }
        catch { /* nunca rompe */ }
    }

    private void Cambiar(EstadoDelAvatar nuevo, string? mensaje, int generacion, bool soloSiError = false)
    {
        lock (_cerrojo)
        {
            if (generacion != _generacion) return;                       // un turno más nuevo ya manda: este no pisa su estado
            if (soloSiError && Estado != EstadoDelAvatar.Error) return;
            Estado = nuevo;
        }
        try { EstadoCambiado?.Invoke(nuevo, mensaje); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "ConversacionConAgente.EstadoCambiado", ex); }      // un suscriptor con un defecto no estropea el turno
    }

    private void AvisarTexto(string texto)
    {
        try { TextoListo?.Invoke(texto); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "ConversacionConAgente.TextoListo", ex); }
    }
}

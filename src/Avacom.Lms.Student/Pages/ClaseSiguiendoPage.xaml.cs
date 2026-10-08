using System.Diagnostics;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Student.Pages;

/// <summary>
/// S2 · Siguiendo la clase (PAN-102). Desde el 2026-09-29 (007-01) vive del canal en tiempo real (<see cref="AulaSocketClient"/>,
/// rol «estudiante»): el profesor cambia el selector, bloquea, lanza o avisa y la tableta lo sabe en milisegundos; el aviso dice QUÉ
/// cambió y la tableta pide el estado por HTTP, que sigue siendo la fuente de verdad. Con el canal vivo el sondeo sólo es una red de
/// seguridad (15 s); sin canal vuelve a sondear cada 2 s como antes (BR-049: el selector llega en ≤ 3 s).
///
/// El mismo canal lleva el latido de la tableta (007-04): el nodo sabe si está conectada, reconectando o si salió, sin que el
/// alumno haga nada. La conexión se ve con tres valores y nada más (UXR-003): Conectado · Reconectando · Trabajando en tu tableta.
///
/// Lo que la pantalla ofrece al alumno:
/// · Lo que el profesor proyecta (con seguimiento activo no hay navegación propia; al liberarlo aparecen anterior/siguiente).
/// · Las actividades lanzadas se RESPONDEN aquí (007-05): cada respuesta se guarda primero en la cola del dispositivo y sale sola,
///   con o sin red; el alumno nunca ve una nota (DEC-032) ni un estado de error de guardado (UXR-004).
/// · «Pedir ayuda» levanta la mano (007-13) y «Proyectando tu pantalla» avisa, siempre con texto, cuando el profesor la proyecta (DEC-034).
/// · La pausa (corte de luz, reinicio del nodo) es una tarjeta serena que se quita sola al reanudar (007-02, MSG-003).
/// · Al terminar la clase: qué se conservó, qué falta y qué sigue para estudiar (007-09).
/// </summary>
[QueryProperty(nameof(SesionId), "sesion")]
[QueryProperty(nameof(ParticipanteId), "participante")]
public partial class ClaseSiguiendoPage : ContentPage
{
    private const int SondeoSinCanalMs = 2000;
    private const int SondeoConCanalMs = 15000;
    /// <summary>UXR-003: sin nodo más de este tiempo, «reconectando» pasa a «trabajando en tu tableta».</summary>
    private static readonly TimeSpan SinNodoParaTrabajarSolo = TimeSpan.FromSeconds(10);

    private IDispatcherTimer? _temporizador;
    private EstadoTableta? _estado;
    private ObjetoAula? _objeto;
    private string? _selectorPintado;
    private long _ultimoAvisoVisto;
    private bool _refrescando, _refrescoPendiente, _saliendo, _httpOk = true;
    private bool _abriendoLanzada;
    private bool _mostrandoPendiente;
    private readonly Stopwatch _sinNodo = new();
    private AulaSocketClient? _socket;
    private int _respaldoMs = SondeoConCanalMs;
    private readonly Button _ayudaBtn;

    // La actividad que se está respondiendo (si la hay).
    private DistribucionAula? _actividad;
    private int _numeroIntento;
    private bool _soloLecturaBase;
    private int _entrega;   // 0: sin entregar · 1: entregada en la tableta (falta llegar al nodo) · 2: recibida por el nodo

    public string SesionId { get; set; } = string.Empty;
    public string ParticipanteId { get; set; } = string.Empty;

    public ClaseSiguiendoPage()
    {
        InitializeComponent();
        Visor.Absoluta = ruta => Sesion.Aula.Absoluta(ruta);
        Visor.PuedeNavegar = false;
        Visor.UnidadPedida += (_, unidad) => { if (_objeto is not null) Visor.Mostrar(_objeto, unidad); };
        Visor.MostrarVacio("Esperando a tu profesor", "Cuando proyecte algo, aparecerá aquí.");
        _ayudaBtn = Ds.Boton("✋ Pedir ayuda", Ds.Rango.Secondary, OnAyuda, 52);
        _ayudaBtn.FontSize = 15;
        SemanticProperties.SetDescription(_ayudaBtn, "Levantar la mano para pedir ayuda a tu profesor");
        AyudaSlot.Content = Ds.Capsula(_ayudaBtn);
        Responder.EntregaSolicitada += () => MainThread.BeginInvokeOnMainThread(async () => await TrasEntregaAsync());
        PausaHost.Add(Ds.Titulo("La clase está en pausa", 24));
        PausaHost.Add(Ds.Cuerpo("Tu trabajo está guardado. Cuando tu profesor la reanude, seguimos solos.", 18));
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _saliendo = false;
        _ultimoAvisoVisto = 0;
        Sesion.Cola.Cambio += OnColaCambio;
        await RefrescarAsync();
        if (_saliendo) return;
        IniciarCanal();
        _temporizador ??= Dispatcher.CreateTimer();
        _temporizador.Tick -= OnTick;
        _temporizador.Tick += OnTick;
        AjustarSondeo();
        _ = Sesion.Sincronizador.VaciarAsync();   // lo que quedó en la cola de antes sale ahora
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        Sesion.Cola.Cambio -= OnColaCambio;
        _temporizador?.Stop();
        _ = DetenerCanalAsync();
    }

    private async void OnTick(object? sender, EventArgs e)
    {
        await RefrescarAsync();
        // Red de seguridad: si algo quedó esperando en la cola, se vuelve a intentar sin que nadie lo pida.
        if (!_saliendo && Sesion.Cola.CantidadPendiente() > 0) _ = Sesion.Sincronizador.VaciarAsync();
    }

    /// <summary>Con el canal vivo el sondeo es sólo una red de seguridad; sin canal, la tableta vuelve a sondear cada 2 s (BR-049).</summary>
    private void AjustarSondeo()
    {
        if (_temporizador is null || _saliendo) return;
        var ms = _socket?.Conectado == true ? _respaldoMs : _estado?.IntervaloSondeoMs ?? SondeoSinCanalMs;
        var interval = TimeSpan.FromMilliseconds(ms);
        if (_temporizador.IsRunning && _temporizador.Interval == interval) return;
        _temporizador.Stop();
        _temporizador.Interval = interval;
        _temporizador.Start();
    }

    // ------------------------------------------------------ canal en tiempo real (007-01, 007-04)

    private void IniciarCanal()
    {
        if (_socket is not null || _saliendo || string.IsNullOrWhiteSpace(SesionId) || string.IsNullOrWhiteSpace(ParticipanteId)) return;
        var canal = new AulaSocketClient(Sesion.BaseUri, SesionId, "estudiante", ParticipanteId, ClienteJson.Token, Sesion.Telemetria);
        canal.Mensaje += OnMensajeCanal;
        canal.ConexionCambio += OnConexionCanal;
        _socket = canal;
        Sesion.SocketActual = canal;   // el ciclo de vida de la app lo usa para declarar «reconectando» y «salió»
        canal.Iniciar();
    }

    private async Task DetenerCanalAsync()
    {
        var canal = _socket;
        _socket = null;
        if (canal is null) return;
        canal.Mensaje -= OnMensajeCanal;
        canal.ConexionCambio -= OnConexionCanal;
        if (ReferenceEquals(Sesion.SocketActual, canal)) Sesion.SocketActual = null;
        try { await canal.DetenerAsync(); } catch { /* el nodo lo verá como una desconexión más */ }
    }

    // Los eventos del canal llegan en un hilo de fondo.
    private void OnMensajeCanal(MensajeAula mensaje) => MainThread.BeginInvokeOnMainThread(() => TratarMensaje(mensaje));

    private void OnConexionCanal(ConexionAula estado) => MainThread.BeginInvokeOnMainThread(() =>
    {
        AjustarSondeo();
        PintarConexion();
        ActualizarEnvio();
        if (estado != ConexionAula.Conectado) return;
        // Al volver el canal: el estado completo (pudo cambiar algo sin aviso) y lo que esperaba en la cola.
        PedirRefresco();
        _ = Sesion.Sincronizador.VaciarAsync();
    });

    private void TratarMensaje(MensajeAula m)
    {
        if (_saliendo) return;
        switch (m.Tipo)
        {
            case "hola":
                if (m.RespaldoMs is int respaldo and > 0) _respaldoMs = respaldo;
                AjustarSondeo();
                PintarConexion();
                PedirRefresco();
                break;
            case "cambio":
                PedirRefresco();
                break;
        }
    }

    // ------------------------------------------------------------- refresco

    private void PedirRefresco() => _ = RefrescarAsync();

    private async Task RefrescarAsync()
    {
        if (string.IsNullOrWhiteSpace(SesionId) || string.IsNullOrWhiteSpace(ParticipanteId) || _saliendo) return;
        if (_refrescando) { _refrescoPendiente = true; return; }
        _refrescando = true;
        try
        {
            do
            {
                _refrescoPendiente = false;
                await RefrescarUnaVezAsync();
            }
            while (_refrescoPendiente && !_saliendo);
        }
        finally { _refrescando = false; }
    }

    private async Task RefrescarUnaVezAsync()
    {
        var aula = Sesion.Aula;
        var estado = await aula.EstadoAsync(SesionId, ParticipanteId);
        if (estado is null)
        {
            if (_httpOk) { _httpOk = false; _sinNodo.Restart(); }
            PintarConexion();
            ActualizarEnvio();
            return;
        }
        _httpOk = true;
        _sinNodo.Reset();
        RelojNodo.Aprender(estado.ServidorEn);
        if (estado.TiempoReal is { RespaldoMs: > 0 } tiempoReal) _respaldoMs = tiempoReal.RespaldoMs;
        var anterior = _estado;
        _estado = estado;
        TituloLabel.Text = estado.Sesion.LeccionRotulo ?? estado.Sesion.CursoRotulo ?? "Clase";
        SubtituloLabel.Text = string.Join(" · ", new[] { estado.Sesion.CursoRotulo, estado.Sesion.ProfesorRotulo }.Where(x => !string.IsNullOrWhiteSpace(x)));
        PintarConexion();

        if (estado.Sesion.Estado is "cerrada" or "archivada")
        {
            await MostrarCierreAsync(estado);
            return;
        }
        if (estado.Participante?.Estado is "expulsado" or "rechazado")
        {
            _saliendo = true;
            _temporizador?.Stop();
            await DetenerCanalAsync();
            Sesion.OlvidarClase();
            await DisplayAlertAsync("Saliste de la clase", "Habla con tu profesor para volver a entrar.", "Entendido");
            await Shell.Current.GoToAsync("..");
            return;
        }

        // 007-02 · MSG-003: la pausa es una tarjeta serena; al reanudar se quita sola y todo sigue donde estaba.
        PausaPanel.IsVisible = estado.Sesion.Estado == "suspendida";
        ProyectandoBanda.IsVisible = estado.Proyectando;
        PintarAyuda(estado.AyudaPedida);
        if (anterior?.AyudaPedida == true && !estado.AyudaPedida)
            MostrarBanda("Tu profesor vio tu mano", "Ya va hacia ti.", Ds.InfoSuave, Ds.Tinta);

        if (estado.PantallasBloqueadas) Bloqueo.Mostrar(); else Bloqueo.Ocultar();
        // Con seguimiento activo la tableta no navega sola; pero lo que el profesor le envió (un recurso
        // lanzado) sí se recorre a su ritmo mientras lo tenga abierto.
        Visor.PuedeNavegar = _mostrandoPendiente || !estado.Seguimiento;
        await PintarSelectorAsync(estado);
        PintarPendientes(estado);
        ActualizarActividad(estado);
        PintarAvisos(estado);
        _ = RefrescarExamenesAsync();
    }

    // ----------------------------------------------------------------- el examen de la clase (MOD-010)

    private long _ultimoSondeoDeExamenes;
    private string? _firmaExamenes;

    /// <summary>
    /// Cada ~3 s, si se sabe quién presenta, pregunta qué evaluaciones le alcanzan y ofrece las que el profesor aplicó a ESTA clase. Un examen no se responde dentro de la clase:
    /// tiene su antesala, su bloqueo y su reloj, así que la tarjeta lleva a ellos. Sin saber quién presenta (sin sesión y sin haberse elegido en «Exámenes») no se puede
    /// preguntar al nodo; si hay algo abierto en algún grupo, la tarjeta lleva a «Mis evaluaciones», donde se elige quién eres.
    /// </summary>
    private async Task RefrescarExamenesAsync()
    {
        if (_saliendo || Environment.TickCount64 - _ultimoSondeoDeExamenes < 3000) return;
        _ultimoSondeoDeExamenes = Environment.TickCount64;
        try
        {
            var tarjetas = new List<(string Titulo, string Detalle, string Boton, string Ruta)>();
            if (Sesion.SabeQuienEvalua)
            {
                var mis = await Sesion.Evaluacion.MisAsync(Sesion.Dispositivo, Sesion.AlumnoParaEvaluar);
                if (mis is null) return;                            // sin red: la tarjeta que ya está se queda
                foreach (var e in mis.Pendientes.Where(x => x.SesionId == SesionId && x.Estado is "activa" or "activa_fuera_de_plazo"))
                {
                    var sigue = e.MiIntento is { Estado: "en_curso" or "en_curso_fuera_de_plazo" or "pausado_desconexion" or "restaurando" };
                    if (e.MiIntento is { Estado: "entregado" or "en_revision_docente" or "calificado" or "anulado" }) continue;
                    tarjetas.Add((e.Titulo, sigue ? "Tienes un examen en curso" : "Tu profesor abrió un examen para la clase", sigue ? "Continuar" : "Ver el examen",
                                  $"examen-antesala?asignacion={Uri.EscapeDataString(e.Id)}&reanudar={(sigue ? 1 : 0)}"));
                }
            }
            else
            {
                var quien = await Sesion.Evaluacion.EstudiantesAsync();
                if (quien is { Disponible: true }) tarjetas.Add(("Hay una evaluación abierta", "Elige quién eres para presentarla", "Ir a Exámenes", "evaluaciones"));
            }
            var firma = string.Join("|", tarjetas.Select(t => t.Ruta));
            if (firma == _firmaExamenes) return;
            _firmaExamenes = firma;
            ExamenesHost.Clear();
            foreach (var (titulo, detalle, boton, ruta) in tarjetas)
            {
                var grid = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
                grid.Add(Ds.IconoCategoria("examen", 48), 0, 0);
                var textos = new VerticalStackLayout { VerticalOptions = LayoutOptions.Center };
                textos.Add(Ds.Cuerpo(titulo, 17));
                textos.Add(Ds.Secundario(detalle, 13));
                grid.Add(textos, 1, 0);
                var abrir = Ds.Boton(boton, Ds.Rango.Primary, async (_, _) => await Shell.Current.GoToAsync(ruta), 56);
                abrir.FontSize = 16;
                abrir.AutomationId = "clase-examen-abrir";
                grid.Add(abrir, 2, 0);
                ExamenesHost.Add(Ds.Tarjeta(grid, Ds.RadioInterno, new Thickness(14, 12), Ds.InfoSuave));
            }
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "ClaseSiguiendoPage.Examenes", ex); }
    }

    /// <summary>
    /// UXR-003: tres valores y nada más. Si el canal o el HTTP contestan, «Conectado»; sin ninguno de los dos, «Reconectando» durante 10 s
    /// y después «Trabajando en tu tableta» (lo que el alumno responde se guarda aquí y sale solo). Nunca una calidad de señal.
    /// </summary>
    private ConexionAula ConexionEfectiva() =>
        _httpOk || _socket?.Conectado == true ? ConexionAula.Conectado
        : _sinNodo.Elapsed >= SinNodoParaTrabajarSolo ? ConexionAula.TrabajandoEnElDispositivo
        : ConexionAula.Reconectando;

    private void PintarConexion()
    {
        switch (ConexionEfectiva())
        {
            case ConexionAula.Conectado: Conexion("Conectado", Ds.Exito, Ds.ExitoSuave); break;
            case ConexionAula.Reconectando: Conexion("Reconectando con el aula", Ds.Alerta, Ds.AlertaSuave); break;
            default: Conexion("Trabajando en tu tableta", Ds.Info, Ds.InfoSuave); break;
        }
    }

    /// <summary>El punto lleva el color y el texto la tinta: el estado nunca depende sólo del color (UXR-011).</summary>
    private void Conexion(string texto, Color color, Color fondo)
    {
        ConexionLabel.FormattedText = new FormattedString
        {
            Spans = { new Span { Text = "●  ", TextColor = color }, new Span { Text = texto, TextColor = Ds.Tinta } },
        };
        ConexionChip.BackgroundColor = fondo;
        SemanticProperties.SetDescription(ConexionChip, $"Conexión con el aula: {texto}");
    }

    private async Task PintarSelectorAsync(EstadoTableta estado)
    {
        if (_mostrandoPendiente) return;
        var selector = estado.Selector;
        if (selector is null || string.IsNullOrWhiteSpace(selector.ObjetoRef))
        {
            if (_selectorPintado is not null) { Visor.MostrarVacio("Esperando a tu profesor", "Cuando proyecte algo, aparecerá aquí."); _selectorPintado = null; _objeto = null; }
            return;
        }
        var llave = $"{selector.ObjetoRef}|{selector.UnidadRef}";
        if (llave == _selectorPintado) return;
        if (_objeto?.ObjetoRef != selector.ObjetoRef)
        {
            var suelto = await Sesion.Aula.ObjetoAsync(estado.Sesion.CursoRef ?? selector.CursoRef ?? string.Empty, selector.ObjetoRef!, docente: false);
            if (suelto is null)
            {
                Visor.MostrarVacio("No se pudo abrir lo proyectado", Sesion.Aula.UltimoMotivo ?? selector.Rotulo ?? string.Empty);
                return;
            }
            _objeto = suelto.Objeto;
        }
        Visor.Mostrar(_objeto!, string.IsNullOrWhiteSpace(selector.UnidadRef) ? null : selector.UnidadRef);
        _selectorPintado = llave;
    }

    // ---------------------------------------------------------------- ayuda (007-13)

    private void PintarAyuda(bool pedida)
    {
        // La cabecera es clara: en reposo el botón es blanco con tinta (el estilo de «interruptor» del kit es para la barra oscura del profesor).
        if (pedida) Ds.PintarRelieve(_ayudaBtn, Ds.Info, Colors.White);
        else Ds.PintarRelieve(_ayudaBtn, Colors.White, Ds.Tinta);
        _ayudaBtn.Text = pedida ? "✋ Ayuda pedida · bajar la mano" : "✋ Pedir ayuda";
    }

    private async void OnAyuda(object? sender, EventArgs e)
    {
        if (_estado is null) return;
        var activa = !_estado.AyudaPedida;
        if (!await Sesion.Aula.AyudaAsync(SesionId, ParticipanteId, activa))
        {
            MostrarBanda("No pudimos avisar a tu profesor ahora", "Levanta la mano como siempre; lo intentamos de nuevo en un momento.", Ds.AlertaSuave, Ds.Tinta);
            return;
        }
        _estado = _estado with { AyudaPedida = activa };
        PintarAyuda(activa);
    }

    // -------------------------------------------------------------- pendientes

    private string? _firmaPendientes;

    private void PintarPendientes(EstadoTableta estado)
    {
        // Lo que el profesor lanzó y sigue abierto: actividades (se responden) y recursos (se abren y se recorren).
        var pendientes = (estado.Pendientes ?? []).Where(p => p.Clase is "actividad" or "recurso").ToList();
        if (pendientes.Count == 0 && _mostrandoPendiente && _actividad is null)
        {
            // Lo que estaba abierto se retiró: se vuelve a lo que el profesor proyecta.
            _mostrandoPendiente = false;
            _selectorPintado = null;
            Visor.PuedeNavegar = !estado.Seguimiento;
        }
        // Las tarjetas sólo se reconstruyen cuando cambia algo (ids, entrega, intento, si hay una abierta): rehacerlas en
        // cada sondeo parpadea y deja a la accesibilidad sin el botón entre una y otra.
        var firma = string.Join("|", pendientes.Select(p => $"{p.Id}:{p.Entrega}:{p.Rotulo}:{p.Intento?.Estado}:{p.Intento?.Respondidas}:{p.IntentosUsados}")) + $"#{_mostrandoPendiente}";
        if (firma == _firmaPendientes) return;
        _firmaPendientes = firma;
        PendientesHost.Clear();
        if (pendientes.Count == 0) return;
        // QA 2026-10-07 («las preguntas no se podían seleccionar»): la actividad que el profesor acaba de lanzar se abre sola para responder, sin
        // que el alumno tenga que descubrir la tarjeta de abajo. Sólo la recién llegada (sin recibir todavía), sólo si no hay otra cosa abierta.
        var recienLanzada = pendientes.FirstOrDefault(p => p.Clase == "actividad" && p.Entrega != "entregado" && p.Intento is null);
        if (recienLanzada is not null && !_mostrandoPendiente && !_abriendoLanzada)
        {
            _abriendoLanzada = true;
            MainThread.BeginInvokeOnMainThread(async () =>
            {
                try { await AbrirPendienteAsync(recienLanzada); }
                catch (Exception ex) { RegistroDeFallos.Escribir("student", "ClaseSiguiendoPage.AbrirLanzada", ex); }
                finally { _abriendoLanzada = false; }
            });
        }
        foreach (var d in pendientes)
        {
            var esActividad = d.Clase == "actividad";
            var grid = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
            grid.Add(Ds.IconoCategoria(esActividad ? "actividad" : CategoriaDe(d.ObjetoTipo), 48), 0, 0);
            var textos = new VerticalStackLayout { VerticalOptions = LayoutOptions.Center };
            textos.Add(Ds.Cuerpo(d.Rotulo ?? (esActividad ? "Actividad" : "Recurso"), 17));
            textos.Add(Ds.Secundario(DetalleDe(d, esActividad), 13));
            grid.Add(textos, 1, 0);
            var abrir = Ds.Boton(_mostrandoPendiente ? "Volver a la clase" : EtiquetaDeAbrir(d, esActividad), _mostrandoPendiente ? Ds.Rango.Quiet : Ds.Rango.Primary, async (_, _) => await AbrirPendienteAsync(d), 56);
            abrir.FontSize = 16;
            grid.Add(abrir, 2, 0);
            PendientesHost.Add(Ds.Tarjeta(grid, Ds.RadioInterno, new Thickness(14, 12), esActividad ? Ds.ExitoSuave : Ds.InfoSuave));
        }
    }

    private static string DetalleDe(DistribucionAula d, bool esActividad)
    {
        if (!esActividad) return d.Entrega == "entregado" ? "Recibido · ábrelo cuando quieras" : "Tu profesor te lo acaba de enviar";
        var reglas = d.ReglasTexto;
        var base_ = d.Intento switch
        {
            { Estado: "entregado" } => "Ya la entregaste",
            { Estado: "pendiente_decision" } => "Llegó fuera de tiempo · tu profesor decidirá si la recibe",
            { Estado: "en_curso", Respondidas: > 0 } i => $"Llevas {i.Respondidas} respuesta{(i.Respondidas == 1 ? "" : "s")} guardada{(i.Respondidas == 1 ? "" : "s")} · continúa cuando quieras",
            _ => d.Entrega == "entregado" ? "Recibida · puedes empezar cuando quieras" : "Tu profesor te la acaba de enviar",
        };
        return string.IsNullOrEmpty(reglas) ? base_ : $"{base_} · {reglas}";
    }

    private static string EtiquetaDeAbrir(DistribucionAula d, bool esActividad)
    {
        if (!esActividad) return "Abrir";
        return d.Intento switch
        {
            { Estado: "en_curso", Respondidas: > 0 } => "Continuar",
            { Estado: "entregado" } => QuedanIntentos(d) ? "Otro intento" : "Ver",
            { Estado: "pendiente_decision" } => "Ver",
            _ => "Empezar",
        };
    }

    private static bool QuedanIntentos(DistribucionAula d) =>
        d.EstaAbierta && (d.IntentosPermitidos is not > 0 || (d.IntentosUsados ?? 0) < d.IntentosPermitidos);

    /// <summary>El tipo de objeto de la biblioteca, en la categoría visual del kit.</summary>
    private static string CategoriaDe(string? objetoTipo) => objetoTipo switch
    {
        "lecture" => "presentacion",
        "explanation" => "lectura",
        "simulation_lab" => "laboratorio_web",
        "activity" => "actividad",
        _ => "lectura",
    };

    private async Task AbrirPendienteAsync(DistribucionAula d)
    {
        if (_mostrandoPendiente)
        {
            // «Volver a la clase»: se vuelve a lo proyectado y, con seguimiento activo, sin mandos.
            CerrarPendiente();
            if (_estado is not null) { await PintarSelectorAsync(_estado); PintarPendientes(_estado); }
            return;
        }
        if (string.IsNullOrWhiteSpace(d.ObjetoRef))
        {
            // Un lanzamiento sólo de medio (sin objeto del curso) lo abre el profesor en la pantalla del aula.
            MostrarBanda("Tu profesor lo abre en la pantalla del aula", "Míralo allí; tu tableta sigue en la clase.", Ds.InfoSuave, Ds.Tinta);
            return;
        }
        var aula = Sesion.Aula;
        var suelto = await aula.ObjetoAsync(_estado?.Sesion.CursoRef ?? d.CursoRef ?? string.Empty, d.ObjetoRef, docente: false);
        if (suelto is null)
        {
            // Nada se confirma si no se pudo abrir: el profesor no debe ver «recibido» de algo que la tableta no pudo mostrar.
            MostrarBanda(d.Clase == "actividad" ? "Todavía no se pudo abrir la actividad" : "Todavía no se pudo abrir lo que te enviaron",
                "Prueba de nuevo en un momento. Tu trabajo está a salvo.", Ds.AlertaSuave, Ds.Tinta);
            return;
        }
        if (d.Entrega != "entregado") await aula.ConfirmarEntregaAsync(SesionId, d.Id, ParticipanteId);
        _mostrandoPendiente = true;
        if (d.Clase == "actividad") AbrirActividad(d, suelto.Objeto);
        else
        {
            Visor.PuedeNavegar = true;
            Visor.Mostrar(suelto.Objeto, null);
        }
        if (_estado is not null) PintarPendientes(_estado);
    }

    private void CerrarPendiente()
    {
        _mostrandoPendiente = false;
        _selectorPintado = null;
        _actividad = null;
        Responder.IsVisible = false;
        Visor.IsVisible = true;
        Visor.PuedeNavegar = !(_estado?.Seguimiento ?? true);
    }

    // ----------------------------------------------------- responder la actividad (007-05, 007-06, 007-08)

    private void AbrirActividad(DistribucionAula d, ObjetoAula objeto)
    {
        var intento = d.Intento;
        var entregado = intento?.Estado == "entregado";
        var porDecidir = intento?.Estado == "pendiente_decision";
        var otroIntento = entregado && QuedanIntentos(d);
        // El número de intento lo decide el nodo con lo que ya pasó: uno nuevo sólo si el anterior se entregó y quedan.
        _numeroIntento = intento is null ? 1 : otroIntento ? intento.Numero + 1 : intento.Numero;
        _soloLecturaBase = porDecidir || (entregado && !otroIntento);
        _actividad = d;
        _entrega = _soloLecturaBase ? 2 : 0;

        // Lo que ya está guardado (en el nodo o esperando en la cola de esta tableta) no se vuelve a pedir.
        var respondidas = new HashSet<string>();
        if (intento is { Estado: "en_curso" } && !otroIntento && intento.RespondidasRefs is { } refs)
            foreach (var r in refs) respondidas.Add(r);
        foreach (var paquete in Sesion.Cola.Pendientes(SesionId).Where(p => p.DistribucionId == d.Id && p.IntentoNumero == _numeroIntento))
            foreach (var r in paquete.Respuestas) respondidas.Add(r.PreguntaRef);

        var contexto = new ContextoActividad(SesionId, d.Id, ParticipanteId, _numeroIntento, d.IntentosPermitidos, Sesion.Cola,
                                             async () => { await Sesion.Sincronizador.VaciarAsync(); }, ruta => Sesion.Aula.Absoluta(ruta));
        Responder.SoloLectura = _soloLecturaBase || PausaPanel.IsVisible;
        Responder.Cargar(objeto, contexto, respondidas);
        Responder.ActualizarCronometro(d.Cronometro, _estado?.ServidorEn ?? RelojNodo.AhoraMs);
        ActualizarEnvio();
        if (_soloLecturaBase) Responder.Entregado(true);
        Visor.IsVisible = false;
        Responder.IsVisible = true;
    }

    /// <summary>Con cada estado nuevo: el cronómetro del nodo, la pausa y si el nodo ya recibió la entrega.</summary>
    private void ActualizarActividad(EstadoTableta estado)
    {
        if (_actividad is null) return;
        var d = estado.Pendientes?.FirstOrDefault(p => p.Id == _actividad.Id);
        if (d is null)
        {
            // Ya no está entre lo pendiente: se cerró y no queda nada por entregar. Lo capturado quedó guardado.
            CerrarPendiente();
            _firmaPendientes = null;
            PintarPendientes(estado);
            MostrarBanda("La actividad terminó", "Tu trabajo quedó guardado.", Ds.InfoSuave, Ds.Tinta);
            return;
        }
        _actividad = d;
        Responder.SoloLectura = _soloLecturaBase || estado.Sesion.Estado == "suspendida";
        Responder.ActualizarCronometro(d.Cronometro, estado.ServidorEn);
        if (d.Intento is { Estado: "entregado" } it && it.Numero == _numeroIntento && _entrega < 2)
        {
            _entrega = 2;
            _soloLecturaBase = true;
            Responder.Entregado(true);
        }
    }

    /// <summary>El alumno pidió entregar: la cola ya lo marcó. Se intenta enviar ya; si no hay red, queda «entregado en tu tableta» y sale solo (PAN-132).</summary>
    private async Task TrasEntregaAsync()
    {
        _soloLecturaBase = true;
        try { await Sesion.Sincronizador.VaciarAsync(); } catch { /* la cola conserva todo */ }
        var enviado = Sesion.Cola.CantidadPendiente(SesionId) == 0;
        _entrega = enviado ? 2 : 1;
        Responder.Entregado(enviado);
        PedirRefresco();
    }

    private void OnColaCambio() => MainThread.BeginInvokeOnMainThread(() =>
    {
        ActualizarEnvio();
        // La entrega que esperaba en la tableta llegó al nodo cuando ya no queda nada en la cola.
        if (_entrega == 1 && Sesion.Cola.CantidadPendiente(SesionId) == 0)
        {
            _entrega = 2;
            Responder.Entregado(true);
        }
    });

    private void ActualizarEnvio()
    {
        if (!Responder.IsVisible) return;
        Responder.ActualizarEnvio(Sesion.Cola.CantidadPendiente(SesionId), ConexionEfectiva() == ConexionAula.Conectado);
    }

    // ------------------------------------------------------------------ avisos

    private void PintarAvisos(EstadoTableta estado)
    {
        // Lo que se envió antes de abrir esta pantalla no se repite: se cuenta desde la hora del nodo (BR-062), nunca la del aparato.
        if (_ultimoAvisoVisto == 0) { _ultimoAvisoVisto = estado.ServidorEn; return; }
        foreach (var aviso in (estado.Avisos ?? []).Where(a => a.EnviadoEn > _ultimoAvisoVisto).OrderBy(a => a.EnviadoEn))
        {
            _ultimoAvisoVisto = Math.Max(_ultimoAvisoVisto, aviso.EnviadoEn);
            MostrarBanda(aviso.ParticipanteId is null ? "Aviso de tu profesor" : "Aviso para ti", aviso.Texto, Ds.InfoSuave, Ds.Tinta);
        }
    }

    private void MostrarBanda(string titulo, string? detalle, Color fondo, Color tinta)
    {
        var banda = Ds.Alerta_(titulo, detalle, fondo, tinta);
        AvisosHost.Add(banda);
        Dispatcher.StartTimer(TimeSpan.FromSeconds(8), () => { AvisosHost.Remove(banda); return false; });
    }

    // ------------------------------------------------------------ fin de la clase (007-09)

    /// <summary>
    /// UXR-005: qué se conservó, qué falta, qué sigue. Lo que quedó sin entregar sale solo desde la cola de la tableta (BR-052:
    /// una clase cerrada acepta lo capturado mientras estuvo abierta) y lo que el profesor dejó para estudiar se ve con su fecha.
    /// </summary>
    private async Task MostrarCierreAsync(EstadoTableta estado)
    {
        _saliendo = true;
        _temporizador?.Stop();
        await DetenerCanalAsync();
        Responder.IsVisible = false;
        PausaPanel.IsVisible = false;
        ProyectandoBanda.IsVisible = false;
        _ = Sesion.Sincronizador.VaciarAsync();
        var cierre = estado.Cierre;
        var pendientes = cierre?.Pendientes ?? [];
        var estudio = cierre?.Estudio ?? [];
        Sesion.OlvidarClase();

        CierreHost.Clear();
        CierreHost.Add(Ds.Titulo("La clase terminó", 26));
        CierreHost.Add(Ds.Cuerpo(estado.Sesion.OrigenCierre == "inactividad"
            ? "La clase se cerró sola porque llevaba mucho tiempo sin actividad. Tu trabajo quedó guardado."
            : "Tu profesor cerró la clase. Tu trabajo quedó guardado.", 18));
        if (pendientes.Count > 0)
        {
            CierreHost.Add(Ds.Cuerpo("Te falta entregar", 17, Ds.Tinta));
            foreach (var p in pendientes) CierreHost.Add(Ds.Secundario($"•  {p.Rotulo ?? "Actividad"}", 16));
            CierreHost.Add(Ds.Secundario(Sesion.Cola.CantidadPendiente() > 0
                ? "Lo que ya respondiste se enviará solo en cuanto tu tableta esté conectada."
                : "Si quieres entregarla, habla con tu profesor.", 15));
        }
        if (estudio.Count > 0)
        {
            CierreHost.Add(Ds.Cuerpo("Para estudiar en casa", 17, Ds.Tinta));
            foreach (var e in estudio)
                CierreHost.Add(Ds.Secundario($"•  {e.Rotulo ?? "Recurso"}{(e.Hasta is { } hasta ? $" · hasta el {DateTimeOffset.FromUnixTimeMilliseconds(hasta).ToLocalTime():dd/MM}" : string.Empty)}", 16));
        }
        var volver = Ds.Boton("Volver al menú", Ds.Rango.Primary, async (_, _) => await Shell.Current.GoToAsync(".."), 64);
        volver.Margin = new Thickness(0, 12, 0, 0);
        CierreHost.Add(Ds.Capsula(volver));
        CierreHoja.IsVisible = true;
    }

    private async void OnSalir(object? sender, EventArgs e)
    {
        if (!await DisplayAlertAsync("¿Salir de la clase?", "Tu trabajo queda guardado. Puedes volver con el mismo código.", "Salir", "Seguir en clase")) return;
        _saliendo = true;
        _temporizador?.Stop();
        await Sesion.Aula.PresenciaAsync(SesionId, ParticipanteId, "salio", Sesion.Dispositivo);
        await DetenerCanalAsync();
        _ = Sesion.Sincronizador.VaciarAsync();   // lo que falte por enviar sale solo, con o sin clase abierta
        Sesion.OlvidarClase();
        await Shell.Current.GoToAsync("..");
    }
}

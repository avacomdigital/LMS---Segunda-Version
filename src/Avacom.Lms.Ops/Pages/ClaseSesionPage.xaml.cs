using System.Diagnostics;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Controls;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;
using Microsoft.Maui.Layouts;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// P3 · Clase en curso: PAN-001 y PAN-022 en una sola superficie táctil. El profesor ve lo que
/// se proyecta y lo controla desde aquí: código de unión, conectados, secuencia de la lección,
/// proyección (el selector), y la barra de controles (bloquear, seguimiento, lanzar actividad,
/// aviso, terminar). Nada exige teclado: los avisos son frases prehechas.
///
/// Desde el 2026-09-29 (007-01) la pantalla vive del canal en tiempo real (<see cref="AulaSocketClient"/>, rol «docente»):
/// el recuadro verde de la esquina superior derecha se mueve con cada mensaje «conteo» y cualquier cambio del aula
/// (selector, controles, presencia, manos, entregas…) llega como un aviso que dice QUÉ cambió; la pantalla pide entonces
/// el estado por HTTP, que sigue siendo la fuente de verdad. Si el canal no está (nodo sin ASGI, corte), la pantalla sondea
/// cada 3 s como antes; con el canal vivo sólo sondea cada 15 s como red de seguridad.
///
/// Dos cosas distintas para el profesor, aunque las dos «envíen algo a las tabletas»: el selector
/// (lo que se proyecta; cambia muchas veces por clase, no espera confirmación) y el lanzamiento
/// (una actividad que las tabletas confirman y responden). La lista de participantes muestra la
/// tableta de cada uno, permite bloquearla (MOD-009) y —007-13— muestra quién levantó la mano.
/// </summary>
[QueryProperty(nameof(SesionId), "sesion")]
public partial class ClaseSesionPage : ContentPage
{
    private static readonly string[] Frases = ["Miren al frente", "Dos minutos", "Guarden lo que llevan", "Levanten la mano si terminaron", "Vamos a cerrar"];
    private static readonly Color TintaPeligro = Color.FromArgb("#8A1C1F");

    /// <summary>MSG-045: por debajo de este espacio libre una tableta puede no poder guardar el paquete de una actividad.</summary>
    private const int EspacioMinimoMb = 500;
    /// <summary>UXR-003: sin nodo más de este tiempo, «reconectando» pasa a «trabajando en el dispositivo».</summary>
    private static readonly TimeSpan SinNodoParaTrabajarSolo = TimeSpan.FromSeconds(10);
    private const int SondeoSinCanalMs = 3000;
    private const int SondeoConCanalMs = 15000;

    private IDispatcherTimer? _temporizador;
    private SesionDeClase? _sesion;
    private VistaCurso? _vista;
    private string? _selectorPintado;
    private bool _refrescando, _refrescoPendiente, _saliendo, _httpOk = true, _avisoDeAccesoDado;
    private readonly Stopwatch _sinNodo = new();
    private AulaSocketClient? _socket;
    private int _respaldoMs = SondeoConCanalMs;
    private int _versionConteo;
    private ConteoSesion? _conteo;
    private CapacidadAula? _capacidad;
    private string? _avisosLlave, _avisoCodigo, _actividadLlave;
    private ParticipanteAula? _avisoPara;
    private Button? _bloqueoBtn, _seguimientoBtn, _actividadBtn, _avisoBtn, _pantallaBtn, _terminarBtn, _reanudarBtn, _rotarBtn;
    private readonly Button _participantesBtn;
    private Task<DistribuirSolicitud?>? _lanzamientoEnCurso;
    // MOD-010: los exámenes que ya se aplicaron en esta clase (para mostrar «Ver panel del examen» en vez de «Aplicar examen»).
    private IReadOnlyList<AsignacionConReferencias> _examenes = [];
    private string _examenesLlave = string.Empty;

    public string SesionId { get; set; } = string.Empty;

    public ClaseSesionPage()
    {
        InitializeComponent();
        Proyeccion.PuedeNavegar = true;
        Proyeccion.Escala = 1.15;
        SelectorPantalla.Cerrado += (_, _) => CerrarPantalla();
        Proyeccion.Absoluta = ruta => Sesion.Aula.Absoluta(ruta);
        Proyeccion.UnidadPedida += async (_, unidad) => { if (Proyeccion.Objeto is { } o) await ProyectarAsync(o.ObjetoRef, unidad); };
        // El botón de participantes se fabrica con el kit para compartir relieve, bisel y hundimiento con la barra de controles.
        _participantesBtn = Ds.Boton("Participantes", Ds.Rango.Secondary, OnParticipantes, 56);
        _participantesBtn.FontSize = 16;
        ParticipantesSlot.Content = Ds.Capsula(_participantesBtn);
        PintarControles();
        foreach (var frase in Frases)
        {
            var b = Ds.Boton(frase, Ds.Rango.Secondary, async (_, _) => await AvisarAsync(frase), 64);
            b.Margin = new Thickness(0, 0, 10, 10);
            FrasesHost.Add(Ds.Capsula(b));
        }
        var cerrarAviso = Ds.Boton("Cerrar", Ds.Rango.Quiet, (_, _) => CerrarAviso(), 64);
        FrasesHost.Add(cerrarAviso);

        // 007-12 · el código en grande: se abre tocando el código; el profesor puede cambiarlo o volver a la clase.
        Ds.Tocable(CodigoCard, () => { AbrirCodigoGrande(); return Task.CompletedTask; });
        _rotarBtn = Ds.Boton("Cambiar el código", Ds.Rango.Secondary, async (_, _) => await RotarCodigoAsync(), 64);
        CodigoGrandeAcciones.Add(Ds.Capsula(_rotarBtn));
        CodigoGrandeAcciones.Add(Ds.Capsula(Ds.Boton("Volver a la clase", Ds.Rango.Primary, (_, _) => CerrarCodigoGrande(), 64)));

        // 007-02 · PAN-006: una sola acción, grande.
        _reanudarBtn = Ds.Boton("Reanudar clase", Ds.Rango.Primary, async (_, _) => await ReanudarAsync(), 64);
        ReanudarSlot.Content = Ds.Capsula(_reanudarBtn);

        // 007-05 · el avance vivo se abre sobre la proyección y se cierra con un toque.
        ResultadosCerrarSlot.Content = Ds.Capsula(Ds.Boton("Volver a la clase", Ds.Rango.Secondary, (_, _) => CerrarResultados(), 52));
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _saliendo = false;
        await RefrescarAsync();
        if (_saliendo) return;
        await CargarExamenesAsync();
        IniciarCanal();
        _temporizador ??= Dispatcher.CreateTimer();
        _temporizador.Tick -= OnTick;
        _temporizador.Tick += OnTick;
        AjustarSondeo();
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _temporizador?.Stop();
        ResultadosPanel.Detener();
        _ = DetenerCanalAsync();
    }

    private async void OnTick(object? sender, EventArgs e)
    {
        await RefrescarAsync();
        if (ResultadosHost.IsVisible) await ResultadosPanel.RefrescarAsync();
    }

    /// <summary>Con el canal vivo el sondeo es sólo una red de seguridad (15 s); sin canal, la pantalla vuelve a sondear cada 3 s.</summary>
    private void AjustarSondeo()
    {
        if (_temporizador is null || _saliendo) return;
        var ms = _socket?.Conectado == true ? _respaldoMs : SondeoSinCanalMs;
        var interval = TimeSpan.FromMilliseconds(ms);
        if (_temporizador.IsRunning && _temporizador.Interval == interval) return;
        _temporizador.Stop();
        _temporizador.Interval = interval;
        _temporizador.Start();
    }

    // ------------------------------------------------------ canal en tiempo real (007-01)

    private void IniciarCanal()
    {
        if (_socket is not null || _saliendo || string.IsNullOrWhiteSpace(SesionId)) return;
        var canal = new AulaSocketClient(Sesion.BaseUri, SesionId, "docente", token: ClienteJson.Token);
        canal.Mensaje += OnMensajeCanal;
        canal.ConexionCambio += OnConexionCanal;
        _socket = canal;
        canal.Iniciar();
    }

    private async Task DetenerCanalAsync()
    {
        var canal = _socket;
        _socket = null;
        if (canal is null) return;
        canal.Mensaje -= OnMensajeCanal;
        canal.ConexionCambio -= OnConexionCanal;
        try { await canal.DetenerAsync(); } catch { /* el aula lo verá como una desconexión más */ }
    }

    // Los eventos del canal llegan en un hilo de fondo.
    private void OnMensajeCanal(MensajeAula mensaje) => MainThread.BeginInvokeOnMainThread(() => TratarMensaje(mensaje));

    private void OnConexionCanal(ConexionAula estado) => MainThread.BeginInvokeOnMainThread(() =>
    {
        AjustarSondeo();
        PintarConexion();
        // Al volver el canal se pide el estado completo: pudo cambiar algo mientras no había aviso.
        if (estado == ConexionAula.Conectado) PedirRefresco();
    });

    private void TratarMensaje(MensajeAula m)
    {
        if (_saliendo) return;
        switch (m.Tipo)
        {
            case "hola":
                if (m.RespaldoMs is int respaldo and > 0) _respaldoMs = respaldo;
                if (m.Capacidad is { } capacidad) { _capacidad = capacidad; PintarAvisosDeEstado(); }
                if (m.ConteoDelMensaje is { } inicial) PintarConteo(inicial, delCanal: true);
                AjustarSondeo();
                PintarConexion();
                PedirRefresco();
                break;
            case "conteo":
                // El recuadro verde: no espera al sondeo, se mueve con cada mensaje.
                if (m.ConteoDelMensaje is { } conteo) PintarConteo(conteo, delCanal: true);
                break;
            case "cambio":
                if (m.Que is "resultados" or "entregas" or "distribucion" && ResultadosHost.IsVisible)
                    _ = ResultadosPanel.RefrescarAsync();
                if (m.Que == "evaluacion") _ = CargarExamenesAsync();
                PedirRefresco();
                break;
        }
    }

    // ------------------------------------------------------------- refresco

    /// <summary>Pide el estado ya: si hay un refresco en curso, lo repite al terminar (sin encolar uno por mensaje).</summary>
    private void PedirRefresco() => _ = RefrescarAsync();

    private async Task RefrescarAsync()
    {
        if (string.IsNullOrWhiteSpace(SesionId) || _saliendo) return;
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
        var versionConteo = _versionConteo;
        var sesion = await aula.SesionAsync(SesionId);
        if (sesion is null)
        {
            // Otra persona lleva esta clase, o no existe: se dice una vez y sereno, y se vuelve.
            if (aula.UltimoError is { Estado: 403 or 404 } sinAcceso && !_avisoDeAccesoDado)
            {
                _avisoDeAccesoDado = true;
                _saliendo = true;
                _temporizador?.Stop();
                await DetenerCanalAsync();
                await Aviso("Esta clase no está disponible", TextoDeError(sinAcceso, null));
                await Shell.Current.GoToAsync("..");
                return;
            }
            if (_httpOk) { _httpOk = false; _sinNodo.Restart(); }
            PintarConexion();
            HabilitarControles(false);
            return;
        }
        _httpOk = true;
        _sinNodo.Reset();
        var primeraVez = _sesion is null;
        _sesion = sesion;
        _capacidad = sesion.Capacidad ?? _capacidad;
        PintarConexion();
        if (sesion.Estado is "cerrada" or "archivada")
        {
            _saliendo = true;
            _temporizador?.Stop();
            ResultadosPanel.Detener();
            await DetenerCanalAsync();
            Sesion.ClaseAbiertaId = null;
            await Shell.Current.GoToAsync($"clase-cierre?sesion={Uri.EscapeDataString(sesion.Id)}");
            return;
        }
        if (_vista is null && !string.IsNullOrWhiteSpace(sesion.CursoRef))
        {
            _vista = await aula.CursoAsync(sesion.CursoRef!, docente: true);
            PintarSecuencia();
        }
        else if (primeraVez) PintarSecuencia();

        CodigoLabel.Text = sesion.CodigoUnion ?? "······";
        CodigoGrandeLabel.Text = sesion.CodigoUnion ?? "······";
        // El conteo del canal es más nuevo que esta respuesta si llegó mientras se pedía: en ese caso no se pisa.
        if (versionConteo == _versionConteo) PintarConteo(sesion.Conteo ?? new ConteoSesion(0, 0, 0, 0, 0), delCanal: false);
        LeccionLabel.Text = sesion.LeccionRotulo ?? sesion.CursoRotulo ?? "Clase libre";
        CursoLabel.Text = string.Join(" · ", new[] { sesion.CursoRotulo, sesion.Estado == "suspendida" ? "suspendida · mismo código" : null }.Where(x => !string.IsNullOrWhiteSpace(x)));
        HabilitarControles(sesion.Estado == "abierta");
        PintarEstadoControles(sesion);
        PintarSelector(sesion.Selector);
        PintarActividad(sesion);
        PintarReanudar(sesion);
        PintarAvisoDelCodigo();
        PintarAvisosDeEstado();
        ActualizarBotonParticipantes();
        if (ParticipantesPanel.IsVisible) PintarParticipantes(sesion);
    }

    /// <summary>
    /// UXR-003: tres valores y nada más. Si el canal o el HTTP contestan, está «Conectado» (el HTTP sigue de respaldo);
    /// sin ninguno de los dos, «Reconectando» durante 10 s y después «Trabajando en el dispositivo». Nunca una calidad de señal.
    /// </summary>
    private ConexionAula ConexionEfectiva() =>
        _httpOk || _socket?.Conectado == true ? ConexionAula.Conectado
        : _sinNodo.Elapsed >= SinNodoParaTrabajarSolo ? ConexionAula.TrabajandoEnElDispositivo
        : ConexionAula.Reconectando;

    private void PintarConexion()
    {
        var suspendida = _sesion?.Estado == "suspendida";
        switch (ConexionEfectiva())
        {
            case ConexionAula.Conectado:
                Conexion(suspendida ? "Clase suspendida" : "Conectado", suspendida ? Ds.Alerta : Ds.Exito);
                break;
            case ConexionAula.Reconectando:
                Conexion("Reconectando…", Ds.Alerta);
                break;
            default:
                Conexion("Trabajando en el dispositivo", Ds.Info);
                break;
        }
    }

    /// <summary>El chip va sobre glass chrome: el punto lleva el color semántico y el fondo su versión suave; el texto queda en tinta.</summary>
    private void Conexion(string texto, Color color)
    {
        ConexionLabel.Text = texto;
        ConexionPunto.Fill = new SolidColorBrush(color);
        ConexionChip.BackgroundColor = color == Ds.Exito ? Ds.ExitoSuave : color == Ds.Peligro ? Ds.PeligroSuave : color == Ds.Info ? Ds.InfoSuave : Ds.AlertaSuave;
        SemanticProperties.SetDescription(ConexionChip, $"Conexión con el aula: {texto}");
    }

    // ------------------------------------------------ el recuadro verde de conectados

    /// <summary>Cuántos estudiantes están conectados a la sesión AHORA. Lo llama cada mensaje «conteo» del canal (y el sondeo, de respaldo).</summary>
    private void PintarConteo(ConteoSesion conteo, bool delCanal)
    {
        if (delCanal) _versionConteo++;
        _conteo = conteo;
        var n = conteo.Conectados;
        ConectadosLabel.Text = n.ToString();
        ConectadosGrandeLabel.Text = n.ToString();
        ConectadosRotulo.Text = n == 1 ? "conectado" : "conectados";
        SemanticProperties.SetDescription(ConteoBox, n == 1 ? "1 estudiante conectado" : $"{n} estudiantes conectados");
        ActualizarBotonParticipantes();
        PintarAvisosDeEstado();
    }

    private void ActualizarBotonParticipantes()
    {
        var bloqueadas = _sesion?.Participantes?.Count(p => p.Admitido && p.TabletaBloqueada) ?? 0;
        _participantesBtn.Text = _conteo is { Esperando: > 0 } c ? $"Participantes · {c.Esperando} esperando"
            : bloqueadas > 0 ? $"Participantes · {bloqueadas} tableta{(bloqueadas == 1 ? "" : "s")} bloqueada{(bloqueadas == 1 ? "" : "s")}"
            : "Participantes";
    }

    /// <summary>
    /// 007-11 (capacidad) y 007-13 (manos levantadas): avisos que informan sin alarmar. Sólo aparecen cuando hay algo que decir y
    /// nunca dependen del color: cada uno lleva su texto.
    /// </summary>
    private void PintarAvisosDeEstado()
    {
        var llaves = new List<string>();
        if (_capacidad is { Nivel: "pico" or "lleno" } cap) llaves.Add($"cap|{cap.Nivel}|{cap.Activos}|{cap.Pico}");
        var manos = _sesion?.ManosLevantadas ?? 0;
        if (manos > 0) llaves.Add($"manos|{manos}");
        if (_conteo is { Reconectando: > 0 } c) llaves.Add($"rec|{c.Reconectando}");
        var llave = string.Join(";", llaves);
        if (llave == _avisosLlave) return;
        _avisosLlave = llave;
        AvisosDeEstado.Clear();
        if (_capacidad is { Nivel: "pico" } pico)
            AvisosDeEstado.Add(Ds.Pildora($"Aula en pico · {pico.Activos} de {pico.Pico}", Ds.AlertaSuave, Ds.Tinta, 13));
        else if (_capacidad is { Nivel: "lleno" } lleno)
            AvisosDeEstado.Add(Ds.Pildora($"Aula llena · {lleno.Activos} de {lleno.Pico} · las nuevas tabletas esperan", Ds.AlertaSuave, Ds.Tinta, 13));
        if (manos > 0)
        {
            var mano = Ds.Pildora(manos == 1 ? "✋ 1 alumno pide ayuda" : $"✋ {manos} alumnos piden ayuda", Ds.InfoSuave, Ds.Tinta, 14);
            Ds.Tocable(mano, () => { AbrirParticipantes(); return Task.CompletedTask; });
            SemanticProperties.SetDescription(mano, "Ver quién pide ayuda");
            AvisosDeEstado.Add(mano);
        }
        if (_conteo is { Reconectando: > 0 } reconectando)
            AvisosDeEstado.Add(Ds.Pildora(reconectando.Reconectando == 1 ? "1 reconectando" : $"{reconectando.Reconectando} reconectando", Ds.AlertaSuave, Ds.Tinta, 13));
    }

    // ------------------------------------------------- reanudar tras una caída (007-02)

    /// <summary>PAN-006: sereno, sin cuenta atrás de fracaso. Dice dónde iba la clase, cuántos alumnos ya volvieron y se reanuda con un toque.</summary>
    private void PintarReanudar(SesionDeClase s)
    {
        var suspendida = s.Estado == "suspendida";
        ReanudarPanel.IsVisible = suspendida;
        if (!suspendida) return;
        ReanudarTitulo.Text = s.CausaSuspension == "reinicio" ? "Clase recuperada" : "Clase en pausa";
        var donde = s.Recuperacion?.Texto;
        ReanudarTexto.Text = string.IsNullOrWhiteSpace(donde) ? "La clase está en pausa. Puedes continuar cuando quieras." : $"{donde} Puedes continuar cuando quieras.";
        var alumnos = s.Participantes?.Count(p => p.Estado is "conectado" or "reconectando" or "salio") ?? 0;
        var volvieron = s.Conteo?.Conectados ?? 0;
        ReanudarProgreso.Text = alumnos == 0 ? "Todavía no hay alumnos en esta clase."
            : volvieron == 0 ? $"Las tabletas se reconectan solas; todavía no vuelve ninguna de {alumnos}."
            : $"{volvieron} de {alumnos} alumnos ya volvieron a la clase.";
    }

    private async Task ReanudarAsync()
    {
        if (_sesion is null) return;
        if (await Sesion.Aula.ReanudarAsync(_sesion.Id, Sesion.ProfesorId) is null)
        {
            await Aviso("No se pudo reanudar la clase", TextoDeError(Sesion.Aula.UltimoError, Sesion.Aula.UltimoMotivo));
            return;
        }
        await RefrescarAsync();
    }

    // -------------------------------------------------------- código grande (007-12)

    private void AbrirCodigoGrande()
    {
        if (_sesion is null) return;
        CodigoGrandeLabel.Text = _sesion.CodigoUnion ?? "······";
        ConectadosGrandeLabel.Text = (_conteo?.Conectados ?? 0).ToString();
        PintarAvisoDelCodigo();
        CodigoGrande.IsVisible = true;
    }

    private void CerrarCodigoGrande()
    {
        CodigoGrande.IsVisible = false;
        _avisoCodigo = null;
    }

    /// <summary>PAN-007: con la clase suspendida el grupo ve un aviso sereno; aquí el profesor lo sabe. Tras cambiar el código, lo que sigue.</summary>
    private void PintarAvisoDelCodigo()
    {
        var texto = _sesion?.Estado == "suspendida" ? "La clase está en pausa. Las tabletas esperan sin perder nada hasta que la reanudes." : _avisoCodigo;
        CodigoGrandeAviso.Text = texto;
        CodigoGrandeAviso.IsVisible = !string.IsNullOrWhiteSpace(texto);
    }

    private async Task RotarCodigoAsync()
    {
        if (_sesion is null || _rotarBtn is null) return;
        Ds.Habilitar(_rotarBtn, false);
        try
        {
            var nuevo = await Sesion.Aula.RotarCodigoAsync(_sesion.Id, Sesion.ProfesorId);
            if (nuevo is null)
            {
                await Aviso("No se pudo cambiar el código", TextoDeError(Sesion.Aula.UltimoError, Sesion.Aula.UltimoMotivo));
                return;
            }
            CodigoLabel.Text = nuevo;
            CodigoGrandeLabel.Text = nuevo;
            _avisoCodigo = "Código nuevo. Las tabletas que ya están dentro siguen en la clase.";
            PintarAvisoDelCodigo();
            await RefrescarAsync();
        }
        finally { Ds.Habilitar(_rotarBtn, true); }
    }

    // ------------------------------------------------------------- secuencia

    private void PintarSecuencia()
    {
        SecuenciaHost.Clear();
        if (_vista is null || _sesion is null)
        {
            SecuenciaHost.Add(Ds.Secundario(_sesion?.ViaOrigen == "libre" ? "Clase libre: proyecta desde el curso que quieras." : "Sin curso.", 15));
            return;
        }
        var lecciones = string.IsNullOrWhiteSpace(_sesion.LeccionRef) ? _vista.Lecciones : _vista.Lecciones.Where(l => l.LeccionRef == _sesion.LeccionRef).ToList();
        foreach (var leccion in lecciones)
        {
            if (lecciones.Count > 1) SecuenciaHost.Add(Ds.Secundario(leccion.Titulo, 14));
            foreach (var objeto in leccion.Objetos ?? [])
                SecuenciaHost.Add(FilaObjeto(objeto));
        }
    }

    private View FilaObjeto(ObjetoAula objeto)
    {
        var seleccionado = _sesion?.Selector?.ObjetoRef == objeto.ObjetoRef;
        // MOD-010: el examen no se proyecta, se APLICA al grupo (o, si ya se aplicó, se vigila desde su panel).
        var esExamen = EsExamen(objeto);
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(40), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 12 };
        fila.Add(Ds.IconoCategoria(objeto.Componente, 40), 0, 0);
        var textos = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        textos.Add(Ds.Cuerpo(objeto.Titulo, 15));
        textos.Add(Ds.Secundario(string.Join(" · ", new[] { objeto.ComponenteLegible, objeto.DuracionTexto, esExamen ? (ExamenDe(objeto) is null ? "Aplicar examen" : "Ver panel del examen") : objeto.FueraDeAlcance ? "lo aplica MOD-010" : null }.Where(x => !string.IsNullOrWhiteSpace(x))), 13));
        fila.Add(textos, 1, 0);
        var pila = new VerticalStackLayout { Spacing = 6 };
        pila.Add(fila);
        if (seleccionado && objeto.Unidades.Count > 0)
        {
            var laminas = new FlexLayout { Wrap = FlexWrap.Wrap, Direction = FlexDirection.Row, JustifyContent = FlexJustify.Start, AlignItems = FlexAlignItems.Center };
            foreach (var u in objeto.Unidades)
            {
                var activa = _sesion?.Selector?.UnidadRef == u.UnidadRef;
                // Ficha de lámina en relieve: degradado, bisel y una sombra corta (la tarjeta recorta lo que sobresale).
                var chip = new Border
                {
                    Background = Ds.Degradado(activa ? Ds.Rojo : Colors.White), Stroke = Ds.Bisel(), StrokeThickness = 1,
                    WidthRequest = 46, HeightRequest = 46, Margin = new Thickness(0, 0, 8, 8),
                    StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioControl },
                    Shadow = new Shadow { Brush = new SolidColorBrush(activa ? Ds.Rojo : Ds.Tinta), Offset = new Point(0, 4), Radius = 10, Opacity = activa ? 0.35f : 0.12f },
                    Content = new Label { Text = u.Indice.ToString(), FontSize = 17, FontFamily = Ds.FuenteMedia, TextColor = activa ? Colors.White : Ds.Tinta, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
                };
                Ds.Tocable(chip, () => ProyectarAsync(objeto.ObjetoRef, u.UnidadRef));
                laminas.Add(chip);
            }
            pila.Add(laminas);
        }
        var tarjeta = new Border
        {
            BackgroundColor = seleccionado ? Ds.VioletaSuave : Colors.Transparent,
            Stroke = new SolidColorBrush(seleccionado ? Ds.CatClaseEnVivo : Colors.Transparent), StrokeThickness = seleccionado ? 2 : 0,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Padding = new Thickness(10, 8), Content = pila,
            Opacity = objeto.FueraDeAlcance && !esExamen ? 0.6 : 1,
        };
        if (!objeto.FueraDeAlcance) Ds.Tocable(tarjeta, () => ProyectarAsync(objeto.ObjetoRef, null));
        else if (esExamen) Ds.Tocable(tarjeta, () => AbrirExamenAsync(objeto));
        return tarjeta;
    }

    // ----------------------------------------------------------------- exámenes de la clase (MOD-010)

    private static bool EsExamen(ObjetoAula objeto) => objeto.FueraDeAlcance && (objeto.Componente == "examen" || objeto.Tipo == "exam");

    /// <summary>El examen de esta clase que corresponde a ese objeto del curso, si ya se aplicó (abierto o cerrado).</summary>
    private AsignacionConReferencias? ExamenDe(ObjetoAula objeto) =>
        _examenes.Where(a => a.ObjetoRef == objeto.ObjetoRef)
            .OrderByDescending(a => a.Estado is "activa" or "activa_fuera_de_plazo").ThenByDescending(a => a.CreadaEn ?? 0).FirstOrDefault();

    /// <summary>Lee los exámenes aplicados en esta clase. Si el nodo no contesta se conserva lo que ya se sabía; sólo se repinta la secuencia si algo cambió.</summary>
    private async Task CargarExamenesAsync()
    {
        if (_sesion is null || _saliendo) return;
        var lista = await ExamenExtra.Api.AsignacionesDeClaseAsync(Sesion.ProfesorId, _sesion.Id);
        if (lista is null || _saliendo) return;
        var visibles = lista.Asignaciones.Where(a => a.CuentaEnLaClase).ToList();
        var llave = string.Join("|", visibles.Select(a => $"{a.Id}:{a.Estado}:{a.ObjetoRef}"));
        if (llave == _examenesLlave) return;
        _examenesLlave = llave;
        _examenes = visibles;
        PintarSecuencia();
    }

    /// <summary>Un toque en el examen: si ya se aplicó, su panel; si no, la pantalla para aplicarlo (nivel, tiempo, fecha, intentos…).</summary>
    private async Task AbrirExamenAsync(ObjetoAula objeto)
    {
        if (_sesion is null) return;
        if (ExamenDe(objeto) is { } aplicado)
        {
            await Shell.Current.GoToAsync($"examen-panel?asignacion={Uri.EscapeDataString(aplicado.Id)}");
            return;
        }
        var curso = _sesion.CursoRef ?? _vista?.CursoRef;
        if (string.IsNullOrWhiteSpace(curso))
        {
            await Aviso("Este examen no se puede aplicar desde aquí", "La clase no tiene un curso. Inicia una clase desde un curso para aplicar su examen.");
            return;
        }
        var consulta = new (string Clave, string? Valor)[]
        {
            ("curso", curso), ("objeto", objeto.ObjetoRef), ("fuente", string.IsNullOrWhiteSpace(_sesion.FuenteCurso) ? Sesion.FuenteAula : _sesion.FuenteCurso),
            ("sesion", _sesion.Id), ("titulo", objeto.Titulo), ("curso_titulo", _vista?.Titulo ?? _sesion.CursoRotulo),
        };
        await Shell.Current.GoToAsync("examen-aplicar?" + string.Join("&", consulta.Select(c => $"{c.Clave}={Uri.EscapeDataString(c.Valor ?? string.Empty)}")));
    }

    // -------------------------------------------------------------- selector

    private void PintarSelector(SelectorAula? selector)
    {
        if (selector is null || string.IsNullOrWhiteSpace(selector.ObjetoRef))
        {
            if (_selectorPintado is not null) { Proyeccion.MostrarVacio(); _selectorPintado = null; PintarSecuencia(); }
            return;
        }
        var llave = $"{selector.ObjetoRef}|{selector.UnidadRef}";
        if (llave == _selectorPintado) return;
        var objeto = _vista?.Objeto(selector.ObjetoRef!);
        if (objeto is null)
        {
            Proyeccion.MostrarVacio("Objeto fuera de este curso", selector.Rotulo ?? selector.ObjetoRef!);
        }
        else Proyeccion.Mostrar(objeto, string.IsNullOrWhiteSpace(selector.UnidadRef) ? null : selector.UnidadRef);
        _selectorPintado = llave;
        PintarSecuencia();
        PintarEstadoControles(_sesion);
    }

    private async Task ProyectarAsync(string objetoRef, string? unidadRef)
    {
        if (_sesion is null) return;
        var selector = await Sesion.Aula.ProyectarAsync(_sesion.Id, Sesion.ProfesorId, objetoRef, unidadRef);
        if (selector is null)
        {
            await Aviso("No se pudo proyectar", TextoDeError(Sesion.Aula.UltimoError, Sesion.Aula.UltimoMotivo));
            return;
        }
        _sesion = _sesion with { Selector = selector };
        PintarSelector(selector);
    }

    // -------------------------------------------------------------- controles

    private void PintarControles()
    {
        ControlesHost.Clear();
        // Bloqueo y aviso son la acción secundaria de siempre en clase: van sólo con ícono, redondos y juntos,
        // para no competir en tamaño con lanzar actividad y terminar clase.
        _bloqueoBtn = Ds.BotonIcono("🔓", false, Ds.Alerta, async (_, _) => await ControlAsync("bloqueo", !(_sesion?.PantallasBloqueadas ?? false)), "Bloquear pantallas");
        _avisoBtn = Ds.BotonIcono("⚠", false, Ds.Info, OnAlternarAviso, "Enviar un aviso");
        _seguimientoBtn = Ds.Interruptor("Seguimiento", true, Ds.Info, async (_, _) => await ControlAsync("seguimiento", !(_sesion?.Seguimiento ?? true)), 46);
        _actividadBtn = Ds.Boton("Lanzar actividad", Ds.Rango.Secondary, async (_, _) => await LanzarOCerrarAsync(), 46);
        _terminarBtn = Ds.Boton("Terminar clase", Ds.Rango.Destructive, async (_, _) => await TerminarAsync(), 46);

        _pantallaBtn = Ds.BotonIcono("🖵", false, Ds.Info, OnAlternarPantalla, "Pantalla de proyección: resolución y escala");

        var bloqueoYAviso = new HorizontalStackLayout { Spacing = 8 };
        bloqueoYAviso.Add(Ds.Capsula(_bloqueoBtn));
        bloqueoYAviso.Add(Ds.Capsula(_avisoBtn));
        bloqueoYAviso.Add(Ds.Capsula(_pantallaBtn));

        ControlesHost.Add(bloqueoYAviso);
        ControlesHost.Add(Ds.Capsula(_seguimientoBtn));
        ControlesHost.Add(Ds.Capsula(_actividadBtn));
        ControlesHost.Add(new BoxView { WidthRequest = 14, Color = Colors.Transparent });
        ControlesHost.Add(Ds.Capsula(_terminarBtn));
    }

    /// <summary>El botón de pantalla abre la hoja del perfil de proyección (resolución × escala); comparte lugar con la hoja de avisos, así que abrir una cierra la otra.</summary>
    private void OnAlternarPantalla(object? sender, EventArgs e)
    {
        if (PantallaPanel.IsVisible) { CerrarPantalla(); return; }
        if (AvisoPanel.IsVisible) CerrarAviso();
        PantallaPanel.IsVisible = true;
        if (_pantallaBtn is not null) Ds.PintarInterruptor(_pantallaBtn, true, Ds.Info);
    }

    private void CerrarPantalla()
    {
        PantallaPanel.IsVisible = false;
        if (_pantallaBtn is not null) Ds.PintarInterruptor(_pantallaBtn, false, Ds.Info);
    }

    /// <summary>El botón del aviso abre la hoja para todo el grupo; el aviso a una sola persona nace en la lista de participantes.</summary>
    private void OnAlternarAviso(object? sender, EventArgs e)
    {
        if (AvisoPanel.IsVisible) { CerrarAviso(); return; }
        AbrirAviso(null);
    }

    private void AbrirAviso(ParticipanteAula? para)
    {
        if (PantallaPanel.IsVisible) CerrarPantalla();
        _avisoPara = para;
        AvisoTitulo.Text = para is null ? "Enviar un aviso al grupo" : $"Aviso para {para.Nombre}";
        AvisoPanel.IsVisible = true;
        if (_avisoBtn is not null) Ds.PintarInterruptor(_avisoBtn, true, Ds.Info);
    }

    private void CerrarAviso()
    {
        AvisoPanel.IsVisible = false;
        _avisoPara = null;
        AvisoTitulo.Text = "Enviar un aviso al grupo";
        if (_avisoBtn is not null) Ds.PintarInterruptor(_avisoBtn, false, Ds.Info);
    }

    /// <summary>La asa «︿/﹀» sobre la barra: la oculta o la muestra. Nunca desaparece del todo, así siempre hay
    /// forma de volver a Terminar clase sin un gesto escondido (regla del kit: nada oculto detrás de un swipe).</summary>
    private void OnAlternarControles(object? sender, EventArgs e)
    {
        ControlesBarra.IsVisible = !ControlesBarra.IsVisible;
        ControlesAsa.Text = ControlesBarra.IsVisible ? "︿" : "﹀";
    }

    private void HabilitarControles(bool activo)
    {
        foreach (var b in new[] { _bloqueoBtn, _seguimientoBtn, _actividadBtn, _avisoBtn })
            if (b is not null) Ds.Habilitar(b, activo);
        if (_terminarBtn is not null) Ds.Habilitar(_terminarBtn, _sesion is not null);
    }

    private void PintarEstadoControles(SesionDeClase? s)
    {
        if (s is null) return;
        if (_bloqueoBtn is not null)
        {
            Ds.PintarInterruptor(_bloqueoBtn, s.PantallasBloqueadas, Ds.Alerta);
            _bloqueoBtn.Text = s.PantallasBloqueadas ? "🔒" : "🔓";
            SemanticProperties.SetDescription(_bloqueoBtn, s.PantallasBloqueadas ? "Pantallas bloqueadas · liberar" : "Bloquear pantallas");
        }
        if (_seguimientoBtn is not null)
        {
            Ds.PintarInterruptor(_seguimientoBtn, s.Seguimiento, Ds.Info);
            _seguimientoBtn.Text = s.Seguimiento ? "Seguimiento activo" : "Navegación libre";
        }
        if (_actividadBtn is not null)
        {
            // Un solo botón para el lanzamiento (CAP-040): lo que está en el selector se envía a las tabletas.
            // Si es una actividad, se lanza como actividad (a quién, tiempo, intentos); si es una lámina, lectura o
            // laboratorio, se envía como recurso para que cada tableta lo abra y lo recorra a su ritmo.
            // Con una actividad abierta el mismo botón cierra la recepción.
            var abierta = s.ActividadAbierta;
            var selectorEsActividad = s.Selector?.ObjetoTipo == "activity";
            var haySelector = !string.IsNullOrWhiteSpace(s.Selector?.ObjetoRef);
            _actividadBtn.Text = abierta is not null ? "Cerrar recepción" : selectorEsActividad ? "Lanzar actividad" : "Enviar a tabletas";
            var puede = s.Estado == "abierta" && (abierta is not null || haySelector);
            Ds.Habilitar(_actividadBtn, puede);
        }
    }

    private async Task ControlAsync(string tipo, bool activo)
    {
        if (_sesion is null) return;
        if (!await Sesion.Aula.ControlAsync(_sesion.Id, Sesion.ProfesorId, tipo, activo))
        {
            await Aviso("No se pudo cambiar el control", TextoDeError(Sesion.Aula.UltimoError, Sesion.Aula.UltimoMotivo));
            return;
        }
        _sesion = tipo == "bloqueo" ? _sesion with { PantallasBloqueadas = activo } : _sesion with { Seguimiento = activo };
        PintarEstadoControles(_sesion);
    }

    // ------------------------------------------------------------ lanzamiento (007-06)

    private async Task LanzarOCerrarAsync()
    {
        if (_sesion is null) return;
        var aula = Sesion.Aula;
        if (_sesion.ActividadAbierta is { } abierta)
        {
            var cerrada = await aula.CerrarDistribucionAsync(_sesion.Id, Sesion.ProfesorId, abierta.Id);
            if (cerrada is null) await Aviso("No se pudo cerrar la recepción", TextoDeError(aula.UltimoError, aula.UltimoMotivo));
            await RefrescarAsync();
            return;
        }
        if (_sesion.Selector?.ObjetoRef is not { } objetoRef || string.IsNullOrWhiteSpace(objetoRef)) return;
        var esActividad = _sesion.Selector.ObjetoTipo == "activity";
        DistribuirSolicitud solicitud;
        if (esActividad)
        {
            // PAN-050: a quién, cuánto tiempo y cuántos intentos, con toques. Cancelar no lanza nada.
            var elegida = await PedirLanzamientoAsync(objetoRef);
            if (elegida is null) return;
            solicitud = elegida;
        }
        else
        {
            // Un recurso nuevo sustituye al anterior en las tabletas: se retira el que siga abierto antes de enviar.
            if (_sesion.RecursoAbierto is { } anterior)
                await aula.CerrarDistribucionAsync(_sesion.Id, Sesion.ProfesorId, anterior.Id);
            // Se envía a todo el grupo admitido; el backend deja fuera las tabletas bloqueadas y lo dice en «excluidos».
            solicitud = new DistribuirSolicitud("recurso", objetoRef, null, _sesion.Selector.Rotulo, false);
        }
        var distribucion = await aula.DistribuirAsync(_sesion.Id, Sesion.ProfesorId, solicitud);
        if (distribucion is null)
        {
            var error = aula.UltimoError;
            var titulo = error?.Codigo == "sin_participantes_admitidos"
                ? (error.Texto("excluidos_bloqueados") is null && error.Extra is { } e && e.TryGetProperty("excluidos_bloqueados", out var ex) && ex.GetArrayLength() > 0
                    ? "Todas las tabletas conectadas están bloqueadas" : "Todavía no hay tabletas conectadas")
                : error?.AulaLlena == true ? "El aula está llena"
                : esActividad ? "No se pudo lanzar la actividad" : "No se pudo enviar a las tabletas";
            await Aviso(titulo, TextoDeError(error, aula.UltimoMotivo));
            return;
        }
        await RefrescarAsync();
    }

    /// <summary>Abre el panel de lanzamiento con lo que la actividad propone (intentos y tiempo del curso) y las tabletas con poco espacio (MSG-045).</summary>
    private async Task<DistribuirSolicitud?> PedirLanzamientoAsync(string objetoRef)
    {
        if (_sesion is null || _lanzamientoEnCurso is not null) return null;
        var objeto = _vista?.Objeto(objetoRef);
        var admitidos = (_sesion.Participantes ?? []).Where(p => p.Admitido).OrderBy(p => p.Nombre).ToList();
        var pocoEspacio = await TabletasConPocoEspacioAsync(admitidos);
        var propuesta = new LanzamientoPropuesto(
            "actividad", objetoRef, null, _sesion.Selector?.Rotulo ?? objeto?.Titulo ?? "Actividad", admitidos,
            objeto?.Ajustes?.IntentosPermitidos, objeto?.Ajustes?.TiempoLimiteSeg, pocoEspacio);
        LanzarPanel.IsVisible = true;
        try
        {
            _lanzamientoEnCurso = LanzarPanel.PedirAsync(propuesta);
            return await _lanzamientoEnCurso;
        }
        finally
        {
            _lanzamientoEnCurso = null;
            LanzarPanel.IsVisible = false;
        }
    }

    private static async Task<IReadOnlyList<string>> TabletasConPocoEspacioAsync(IReadOnlyList<ParticipanteAula> admitidos)
    {
        try
        {
            var inventario = await Sesion.Dispositivos.ListarAsync();
            if (inventario is null) return [];
            var escasas = inventario.Where(d => d.EspacioLibreMb is { } mb && mb < EspacioMinimoMb).Select(d => d.Id).ToHashSet();
            return admitidos.Where(p => p.DispositivoId is { } id && escasas.Contains(id)).Select(p => p.Nombre).ToList();
        }
        catch { return []; }   // el aviso es informativo: sin inventario, se lanza igual
    }

    /// <summary>Retirar de las tabletas el recurso enviado: cierra la distribución; las tabletas vuelven a seguir el selector.</summary>
    private async Task RetirarRecursoAsync(DistribucionAula recurso)
    {
        if (_sesion is null) return;
        if (await Sesion.Aula.CerrarDistribucionAsync(_sesion.Id, Sesion.ProfesorId, recurso.Id) is null)
            await Aviso("No se pudo retirar el recurso", TextoDeError(Sesion.Aula.UltimoError, Sesion.Aula.UltimoMotivo));
        await RefrescarAsync();
    }

    private void PintarActividad(SesionDeClase s)
    {
        // Sólo se reconstruye si cambió algo que se ve: con el canal vivo llegan muchos avisos y la columna no debe parpadear.
        var recurso = s.RecursoAbierto;
        var actividad = s.Distribuciones?.LastOrDefault(d => d.Clase == "actividad");
        var llave = string.Join("|", recurso?.Id, recurso?.Entregas?.Entregadas, recurso?.Entregas?.Total, recurso?.Excluidos,
            actividad?.Id, actividad?.EstaAbierta, actividad?.Entregas?.Entregadas, actividad?.Entregas?.Total, actividad?.Excluidos,
            actividad?.Avance?.Entregaron, actividad?.Avance?.Respondiendo, actividad?.Avance?.PorDecidir);
        if (llave == _actividadLlave) return;
        _actividadLlave = llave;

        ActividadHost.Clear();
        // El recurso enviado a las tabletas (si lo hay) y la actividad en curso (si la hay) se ven en el mismo rincón.
        if (recurso is not null)
        {
            var pilaRecurso = new VerticalStackLayout { Spacing = 8 };
            pilaRecurso.Add(Ds.Pildora("Enviado a las tabletas", Ds.Info));
            pilaRecurso.Add(Ds.Cuerpo(recurso.Rotulo ?? recurso.ObjetoRef ?? "Recurso", 16));
            var totalR = recurso.Entregas?.Total ?? 0;
            var abiertasR = recurso.Entregas?.Entregadas ?? 0;
            pilaRecurso.Add(Ds.Secundario(totalR == 0 ? "Sin destinatarios" : $"{abiertasR} de {totalR} tabletas lo abrieron", 14));
            if (recurso.Excluidos > 0)
                pilaRecurso.Add(Ds.Pildora(recurso.Excluidos == 1 ? "1 tableta bloqueada no lo recibió" : $"{recurso.Excluidos} tabletas bloqueadas no lo recibieron", Ds.PeligroSuave, TintaPeligro));
            var retirar = Ds.Boton("Retirar de las tabletas", Ds.Rango.Quiet, async (_, _) => await RetirarRecursoAsync(recurso), 48);
            retirar.FontSize = 14;
            retirar.HorizontalOptions = LayoutOptions.Start;
            pilaRecurso.Add(Ds.Capsula(retirar));
            ActividadHost.Add(Ds.Tarjeta(pilaRecurso, Ds.RadioInterno, new Thickness(14), Ds.InfoSuave));
        }
        if (actividad is null) return;
        var abierta = actividad.EstaAbierta;
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(Ds.Pildora(abierta ? "Actividad en curso" : "Última actividad", abierta ? Ds.CatQuiz : Ds.TintaSuave));
        pila.Add(Ds.Cuerpo(actividad.Rotulo ?? actividad.ObjetoRef ?? "Actividad", 16));
        var avance = actividad.Avance;
        var total = avance?.Destinatarios ?? actividad.Entregas?.Total ?? 0;
        var entregadas = avance?.Entregaron ?? actividad.Entregas?.Entregadas ?? 0;
        pila.Add(new ProgressBar { Progress = total == 0 ? 0 : (double)entregadas / total, ProgressColor = Ds.CatQuiz });
        pila.Add(Ds.Secundario(total == 0 ? "Sin destinatarios"
            : abierta ? $"{entregadas} de {total} entregaron" + (avance is { Respondiendo: > 0 } ? $" · {avance.Respondiendo} respondiendo" : string.Empty)
            : $"{entregadas} de {total} entregaron", 14));
        if (avance is { PorDecidir: > 0 })
            pila.Add(Ds.Pildora(avance.PorDecidir == 1 ? "1 entrega espera tu decisión" : $"{avance.PorDecidir} entregas esperan tu decisión", Ds.AlertaSuave, Ds.Tinta, 13));
        if (actividad.Excluidos > 0)
            pila.Add(Ds.Pildora(actividad.Excluidos == 1 ? "1 tableta bloqueada no la recibió" : $"{actividad.Excluidos} tabletas bloqueadas no la recibieron", Ds.PeligroSuave, TintaPeligro));
        if (!string.IsNullOrEmpty(actividad.ReglasTexto)) pila.Add(Ds.Secundario(actividad.ReglasTexto, 13));
        var resultados = Ds.Boton(abierta ? "Ver avance en vivo" : "Ver resultados", Ds.Rango.Secondary, async (_, _) => await AbrirResultadosAsync(actividad), 48);
        resultados.FontSize = 14;
        resultados.HorizontalOptions = LayoutOptions.Start;
        pila.Add(Ds.Capsula(resultados));
        ActividadHost.Add(Ds.Tarjeta(pila, Ds.RadioInterno, new Thickness(14), abierta ? Ds.ExitoSuave : Colors.White));
    }

    // ------------------------------------------------------------ resultados en vivo (007-05)

    private async Task AbrirResultadosAsync(DistribucionAula actividad)
    {
        if (_sesion is null) return;
        ResultadosPanel.Configurar(_sesion.Id, Sesion.ProfesorId, actividad);
        ResultadosPanel.IsVisible = true;
        ResultadosHost.IsVisible = true;
        await ResultadosPanel.RefrescarAsync();
    }

    private void CerrarResultados()
    {
        ResultadosHost.IsVisible = false;
        ResultadosPanel.Detener();
    }

    // -------------------------------------------------------------- avisos y cierre

    private async Task AvisarAsync(string texto)
    {
        if (_sesion is null) return;
        var para = _avisoPara;
        CerrarAviso();
        if (!await Sesion.Aula.AvisarAsync(_sesion.Id, Sesion.ProfesorId, texto, para?.Id))
            await Aviso("No se pudo enviar el aviso", TextoDeError(Sesion.Aula.UltimoError, Sesion.Aula.UltimoMotivo));
    }

    private async Task TerminarAsync()
    {
        if (_sesion is null) return;
        var aula = Sesion.Aula;
        if (!await DisplayAlertAsync("¿Terminar la clase?", "Se libera la sala y se consolida el resumen. Una clase cerrada no se reabre.", "Terminar", "Seguir en clase")) return;
        var cerrada = await aula.CerrarAsync(_sesion.Id, Sesion.ProfesorId, forzar: false);
        if (cerrada is null && aula.UltimoError?.Codigo == "actividades_abiertas")
        {
            // JRN-011: quien sigue respondiendo tiene 60 s; luego se entrega lo capturado (nada se pierde).
            EsperaPanel.IsVisible = true;
            bool cerrarYa;
            try { cerrarYa = await EsperaPanel.EsperarAsync(_sesion.Id, Sesion.ProfesorId, 60); }
            finally { EsperaPanel.IsVisible = false; }
            if (!cerrarYa) return;
            cerrada = await aula.CerrarAsync(_sesion.Id, Sesion.ProfesorId, forzar: true);
        }
        if (cerrada is null)
        {
            await Aviso("No se pudo cerrar la clase", TextoDeError(aula.UltimoError, aula.UltimoMotivo));
            return;
        }
        _saliendo = true;
        _temporizador?.Stop();
        await DetenerCanalAsync();
        Sesion.ClaseAbiertaId = null;
        await Shell.Current.GoToAsync($"clase-cierre?sesion={Uri.EscapeDataString(cerrada.Id)}");
    }

    // ---------------------------------------------------------- participantes

    private void OnParticipantes(object? sender, EventArgs e)
    {
        if (ParticipantesPanel.IsVisible) ParticipantesPanel.IsVisible = false;
        else AbrirParticipantes();
    }

    private void AbrirParticipantes()
    {
        ParticipantesPanel.IsVisible = true;
        if (_sesion is not null) PintarParticipantes(_sesion);
    }

    private void PintarParticipantes(SesionDeClase s)
    {
        ParticipantesHost.Clear();
        var lista = s.Participantes ?? [];
        if (lista.Count == 0)
        {
            ParticipantesHost.Add(Ds.Secundario("Todavía nadie ha escrito el código.", 16));
            return;
        }
        // Primero quien espera admisión, luego quien levantó la mano, después el resto de los admitidos.
        foreach (var p in lista.OrderBy(p => p.Estado == "esperando" ? 0 : p.ManoLevantada ? 1 : p.Admitido ? 2 : 3).ThenBy(p => p.Nombre))
        {
            // Dos renglones en el ancho del panel (420): arriba el nombre con su estado y su tableta, abajo los botones.
            // Así el texto no compite con los botones por el mismo ancho.
            var fila = new Grid
            {
                ColumnDefinitions = [new ColumnDefinition(48), new ColumnDefinition(GridLength.Star)],
                RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Auto)],
                ColumnSpacing = 12, RowSpacing = 8,
            };
            var avatar = new Border
            {
                BackgroundColor = p.Admitido ? Ds.Exito : p.Estado == "esperando" ? Ds.Alerta : Ds.TintaSuave, StrokeThickness = 0, WidthRequest = 48, HeightRequest = 48,
                StrokeShape = new RoundRectangle { CornerRadius = 999 }, VerticalOptions = LayoutOptions.Start,
                Content = new Label { Text = p.Iniciales, FontFamily = Ds.FuenteMedia, TextColor = p.Estado == "esperando" ? Ds.Tinta : Colors.White, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
            };
            fila.Add(avatar, 0, 0);
            Grid.SetRowSpan(avatar, 2);
            // Nombre (con la mano levantada al lado), estado y la tableta con la que entró (MOD-009); lo importante se ve de un vistazo.
            var textos = new VerticalStackLayout { VerticalOptions = LayoutOptions.Center, Spacing = 2 };
            textos.Add(Ds.Cuerpo(p.ManoLevantada ? $"✋ {p.Nombre}" : p.Nombre, 16));
            textos.Add(Ds.Secundario(string.Join(" · ", new[] { p.EstadoLegible, SinSenalTexto(p, s.ServidorEn), p.AdmisionNominal ? "invitado" : null, string.IsNullOrWhiteSpace(p.Dispositivo) ? null : p.Dispositivo }.Where(x => x is not null)), 13));
            if (p.ManoLevantada) textos.Add(EtiquetaDeFila(Ds.Pildora("Pide ayuda", Ds.InfoSuave, Ds.Tinta, 13)));
            if (p.Proyectado) textos.Add(EtiquetaDeFila(Ds.Pildora("Su pantalla se proyecta", Ds.VioletaSuave, Ds.Tinta, 13)));
            if (p.TabletaBloqueada) textos.Add(EtiquetaDeFila(Ds.Pildora("Tableta bloqueada · sin lanzamientos", Ds.PeligroSuave, TintaPeligro, 13)));
            fila.Add(textos, 1, 0);
            var acciones = new FlexLayout { Wrap = FlexWrap.Wrap, Direction = FlexDirection.Row, AlignItems = FlexAlignItems.Center, JustifyContent = FlexJustify.Start };
            void Agregar(Button b) { b.FontSize = 15; var c = Ds.Capsula(b); c.Margin = new Thickness(0, 0, 8, 8); acciones.Add(c); }
            if (p.ManoLevantada) Agregar(Ds.Boton("Atender", Ds.Rango.Secondary, async (_, _) => await AtenderAsync(p), 52));
            if (p.Admitido)
            {
                Agregar(Ds.Boton("Aviso", Ds.Rango.Quiet, (_, _) => AbrirAviso(p), 52));
                var proyectar = Ds.Boton(p.Proyectado ? "Dejar de proyectar" : "Proyectar", Ds.Rango.Quiet, async (_, _) => await ProyectarAlumnoAsync(p), 52);
                SemanticProperties.SetDescription(proyectar, p.Proyectado ? $"Dejar de proyectar la pantalla de {p.Nombre}" : $"Proyectar la pantalla de {p.Nombre}");
                Agregar(proyectar);
            }
            if (p.TieneTableta)
                Agregar(Ds.Boton(p.TabletaBloqueada ? "Desbloquear" : "Bloquear tableta", Ds.Rango.Quiet, async (_, _) => await BloqueoTabletaAsync(p), 52));
            Button accion = p.Estado == "esperando"
                ? Ds.Boton("Admitir", Ds.Rango.Secondary, async (_, _) => await ParticipanteAsync(p.Id, "admitir"), 52)
                : p.Admitido
                    ? Ds.Boton("Expulsar", Ds.Rango.Quiet, async (_, _) => { if (await DisplayAlertAsync("¿Expulsar de la clase?", $"{p.Nombre} saldrá de la sesión. Sus respuestas se conservan.", "Expulsar", "Cancelar")) await ParticipanteAsync(p.Id, "expulsar"); }, 52)
                    : Ds.Boton("Readmitir", Ds.Rango.Quiet, async (_, _) => await ParticipanteAsync(p.Id, "admitir"), 52);
            Agregar(accion);
            fila.Add(acciones, 1, 1);
            ParticipantesHost.Add(fila);
            ParticipantesHost.Add(Ds.Separador());
        }
    }

    private static View EtiquetaDeFila(Border pildora)
    {
        pildora.HorizontalOptions = LayoutOptions.Start;
        pildora.Margin = new Thickness(0, 4, 0, 0);
        return pildora;
    }

    /// <summary>007-04: quien se quedó sin latido lo dice el nodo («reconectando»); aquí, hace cuánto (con el reloj del nodo, nunca el de este equipo).</summary>
    private static string? SinSenalTexto(ParticipanteAula p, long servidorEn)
    {
        if (p.Estado != "reconectando" || p.UltimoLatidoEn is not { } ultimo || servidorEn <= ultimo) return null;
        var seg = (servidorEn - ultimo) / 1000;
        return seg < 60 ? $"sin señal hace {seg} s" : $"sin señal hace {seg / 60} min";
    }

    private async Task ParticipanteAsync(string participanteId, string accion)
    {
        if (_sesion is null) return;
        if (await Sesion.Aula.ParticipanteAsync(_sesion.Id, Sesion.ProfesorId, participanteId, accion) is null)
        {
            var error = Sesion.Aula.UltimoError;
            await Aviso(error?.Codigo == "dispositivo_bloqueado" ? "La tableta está bloqueada" : error?.AulaLlena == true ? "El aula está llena" : "No se pudo aplicar",
                TextoDeError(error, Sesion.Aula.UltimoMotivo));
        }
        await RefrescarAsync();
    }

    /// <summary>007-13: el profesor baja la mano cuando ya atendió al alumno.</summary>
    private async Task AtenderAsync(ParticipanteAula p)
    {
        if (_sesion is null) return;
        if (!await Sesion.Aula.AtenderAyudaAsync(_sesion.Id, Sesion.ProfesorId, p.Id))
            await Aviso("No se pudo atender la ayuda", TextoDeError(Sesion.Aula.UltimoError, Sesion.Aula.UltimoMotivo));
        await RefrescarAsync();
    }

    /// <summary>
    /// 007-13 · DEC-034: proyectar la pantalla de un alumno al grupo. Deja constancia (el alumno ve el indicador «Proyectando tu pantalla» mientras dure)
    /// y sólo una a la vez. Aquí vive el estado; la captura de la pantalla la aportará el cliente en una entrega posterior.
    /// </summary>
    private async Task ProyectarAlumnoAsync(ParticipanteAula p)
    {
        if (_sesion is null) return;
        if (!await Sesion.Aula.ProyeccionAsync(_sesion.Id, Sesion.ProfesorId, p.Id, !p.Proyectado))
            await Aviso("No se pudo proyectar su pantalla", TextoDeError(Sesion.Aula.UltimoError, Sesion.Aula.UltimoMotivo));
        await RefrescarAsync();
    }

    /// <summary>Bloquear o desbloquear la tableta del participante (MOD-009). Reversible; el alumno no pierde nada.</summary>
    private async Task BloqueoTabletaAsync(ParticipanteAula p)
    {
        if (_sesion is null || !p.TieneTableta) return;
        var api = Sesion.Dispositivos;
        var resultado = p.TabletaBloqueada
            ? await api.DesbloquearAsync(p.DispositivoId!, Sesion.ProfesorId)
            : await api.BloquearAsync(p.DispositivoId!, Sesion.ProfesorId, "desde la clase");
        if (resultado is null) await Aviso(p.TabletaBloqueada ? "No se pudo desbloquear la tableta" : "No se pudo bloquear la tableta", api.UltimoMotivo);
        await RefrescarAsync();
        if (ParticipantesPanel.IsVisible && _sesion is not null) PintarParticipantes(_sesion);
    }

    // ------------------------------------------------------------------ mensajes

    /// <summary>UXR-009: sin códigos ni nombres de módulo. Sin permiso o sin ser el titular, se dice quién lleva la clase y qué hacer.</summary>
    private string TextoDeError(ErrorAula? error, string? motivo)
    {
        if (Sesion.MensajeDePermiso(error, _sesion?.ProfesorRotulo) is { } permiso) return permiso;
        if (error?.Estado == 403) return "Esta clase la lleva otra persona. Sólo su profesor o la administración puede hacerlo.";
        if (error?.Frenado == true) return "Demasiados intentos seguidos. Espera un momento y vuelve a probar.";
        if (error?.AulaLlena == true) return "El aula llegó a su capacidad máxima. Las tabletas nuevas esperan hasta que alguien salga.";
        return error?.Detalle ?? motivo ?? "Sin detalle.";
    }

    private Task Aviso(string titulo, string? detalle) => DisplayAlertAsync(titulo, detalle ?? "Sin detalle.", "Entendido");
}

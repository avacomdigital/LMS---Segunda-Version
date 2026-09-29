using System.Runtime.CompilerServices;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Controls;

/// <summary>
/// Lo que el host propone lanzar (007-06): un objeto de la clase con sus reglas por defecto. <c>Clase</c> es «actividad» o «recurso».
/// <c>Admitidos</c> son los participantes que ya entraron a la clase (los que no están admitidos se ignoran). <c>IntentosDelObjeto</c> y
/// <c>TiempoDelObjetoSeg</c> son los valores que el curso trae en sus ajustes (nulos si no trae ninguno) y quedan preseleccionados.
/// <c>ConPocoEspacio</c> son los nombres de las tabletas que declararon poco espacio libre (007-07): se avisa, no se bloquea.
/// </summary>
public sealed record LanzamientoPropuesto(
    string Clase, string? ObjetoRef, string? MediaRef, string Rotulo, IReadOnlyList<ParticipanteAula> Admitidos,
    int? IntentosDelObjeto, int? TiempoDelObjetoSeg, IReadOnlyList<string> ConPocoEspacio);

/// <summary>
/// Lanzar una actividad o un recurso a las tabletas (007-06 · PAN-050 · FUN-070). Overlay sobre la clase (P3): el profesor decide
/// «a quién, tiempo e intentos» SIN TECLADO, sólo con toques. <see cref="PedirAsync"/> muestra la tarjeta y devuelve el
/// <see cref="DistribuirSolicitud"/> ya armado, o <c>null</c> si el profesor cancela (botón «Cancelar» o tocar fuera).
///
/// A quién: «Todo el grupo (N tabletas)» o «Elegir alumnos» (cuadrícula de fichas; las tabletas bloqueadas salen deshabilitadas
/// con el rótulo «tableta bloqueada», MOD-009). Una actividad lleva además tiempo (Sin límite · 5 · 10 · 15 · 20 · 30 min) e
/// intentos (1 · 2 · 3 · Sin límite), preseleccionados con lo que trae el objeto; un recurso lleva el interruptor «Dejar
/// disponible para estudiar en casa». «Sin límite» viaja como <c>null</c>: el lanzamiento no impone regla y, como hoy, no hay tope.
///
/// Otras reglas: el estado de cada ficha se lee también en el texto (● / ○ elige uno, ☑ / ☐ elige varios), nunca sólo por color;
/// «Lanzar» queda deshabilitado si no habría destinatarios; la nota de poco espacio es informativa (MSG-045); una segunda llamada
/// a <see cref="PedirAsync"/> cancela la anterior devolviéndole <c>null</c>, y ocultar el panel desde fuera (<c>IsVisible = false</c>)
/// también la cancela. Llamar y usar desde el hilo de interfaz.
/// </summary>
public partial class LanzarActividadPanel : ContentView
{
    private const int MaximoNombresEnNota = 5;
    private static readonly Color FondoFicha = Color.FromArgb("#F4F4F5");
    private static readonly Color FiloFicha = Color.FromArgb("#26000000");
    private static readonly int?[] MinutosBase = [null, 5, 10, 15, 20, 30];
    private static readonly int?[] IntentosBase = [1, 2, 3, null];

    private readonly Button _fichaGrupo, _fichaElegir, _lanzar;
    private readonly HashSet<string> _elegidos = [];
    private readonly Dictionary<string, Button> _fichasAlumno = [];
    private readonly List<(int? Valor, string Texto, Button Boton)> _fichasTiempo = [], _fichasIntentos = [];

    private LanzamientoPropuesto? _propuesta;
    private List<ParticipanteAula> _admitidos = [];
    private int _tabletasDelGrupo, _tabletasBloqueadas;
    private bool _porSeleccion, _estudio;
    private int? _minutos, _intentos;               // nulo = sin límite
    private TaskCompletionSource<DistribuirSolicitud?>? _pendiente;
    private CancellationTokenRegistration _registro;

    public LanzarActividadPanel()
    {
        InitializeComponent();

        // Las dos opciones grandes de «¿A quién?» comparten fila; el resto de fichas nace en PedirAsync.
        _fichaGrupo = NuevaFicha((_, _) => ElegirAlcance(false), alto: 76, fuente: 19);
        _fichaElegir = NuevaFicha((_, _) => ElegirAlcance(true), alto: 76, fuente: 19);
        _fichaGrupo.Margin = _fichaElegir.Margin = 0;
        AQuienHost.Add(_fichaGrupo, 0, 0);
        AQuienHost.Add(_fichaElegir, 1, 0);

        var todos = Ds.Boton("Elegir todos", Ds.Rango.Secondary, (_, _) => ElegirATodos(true), 48);
        var ninguno = Ds.Boton("Quitar todos", Ds.Rango.Secondary, (_, _) => ElegirATodos(false), 48);
        todos.FontSize = ninguno.FontSize = 15;
        TodosSlot.Content = Ds.Capsula(todos);
        NingunoSlot.Content = Ds.Capsula(ninguno);

        var cancelar = Ds.Boton("Cancelar", Ds.Rango.Secondary, (_, _) => Completar(null, ocultar: true), 64, 190);
        _lanzar = Ds.Boton("Lanzar", Ds.Rango.Primary, OnLanzar, 64, 240);
        CancelarSlot.Content = Ds.Capsula(cancelar);
        LanzarSlot.Content = Ds.Capsula(_lanzar);
    }

    // ------------------------------------------------------------------ API pública

    /// <summary>
    /// Muestra la tarjeta con la propuesta y espera la decisión del profesor. Devuelve el lanzamiento armado o <c>null</c> si cancela
    /// (botón, tocar fuera, <paramref name="ct"/>, otra llamada a este método u ocultar el panel). El panel se oculta solo al terminar.
    /// </summary>
    public Task<DistribuirSolicitud?> PedirAsync(LanzamientoPropuesto propuesta, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(propuesta);
        // Sólo una petición a la vez: la anterior se cancela (su tarea termina con null) sin ocultar el panel, que se reutiliza.
        Completar(null, ocultar: false);
        if (ct.IsCancellationRequested) return Task.FromResult<DistribuirSolicitud?>(null);

        Preparar(propuesta);
        var espera = new TaskCompletionSource<DistribuirSolicitud?>(TaskCreationOptions.RunContinuationsAsynchronously);
        _pendiente = espera;
        _registro = ct.Register(() => MainThread.BeginInvokeOnMainThread(() =>
        {
            if (ReferenceEquals(_pendiente, espera)) Completar(null, ocultar: true);
        }));
        Pintar();
        IsVisible = true;
        return espera.Task;
    }

    // ------------------------------------------------------------------ ciclo de vida

    /// <summary>Si el host oculta el panel mientras hay una petición abierta, la petición termina en cancelación.</summary>
    protected override void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        base.OnPropertyChanged(propertyName);
        if (propertyName == nameof(IsVisible) && !IsVisible) Completar(null, ocultar: false);
    }

    /// <summary>Si el panel sale del árbol visual (la pantalla se cierra), nadie se queda esperando.</summary>
    protected override void OnHandlerChanging(HandlerChangingEventArgs args)
    {
        base.OnHandlerChanging(args);
        if (args.NewHandler is null) Completar(null, ocultar: false);
    }

    /// <summary>Cierra la petición abierta (si la hay) con el resultado dado. Idempotente: la segunda llamada no hace nada.</summary>
    private void Completar(DistribuirSolicitud? resultado, bool ocultar)
    {
        var espera = Interlocked.Exchange(ref _pendiente, null);
        _registro.Dispose();
        _registro = default;
        if (espera is null) return;
        if (ocultar) IsVisible = false;
        espera.TrySetResult(resultado);
    }

    private void OnVeloTocado(object? sender, TappedEventArgs e) => Completar(null, ocultar: true);

    private void OnLanzar(object? sender, EventArgs e)
    {
        if (!HayDestinatarios) return;
        Completar(Armar(), ocultar: true);
    }

    /// <summary>La tarjeta nunca pasa del alto de la ventana: el cuerpo se desplaza y la cabecera y el pie quedan a la vista.</summary>
    private void OnRaizSizeChanged(object? sender, EventArgs e)
    {
        if (Raiz.Width <= 0 || Raiz.Height <= 0) return;
        Tarjeta.WidthRequest = Math.Min(860, Math.Max(360, Raiz.Width - 64));
        Cuerpo.MaximumHeightRequest = Math.Max(160, Raiz.Height - 64 - 350);
    }

    // ------------------------------------------------------------------ preparación

    private bool EsActividad => string.Equals(_propuesta?.Clase, "actividad", StringComparison.OrdinalIgnoreCase);
    private int Destinatarios => _porSeleccion ? _elegidos.Count : _tabletasDelGrupo;
    private bool HayDestinatarios => Destinatarios > 0;

    /// <summary>Deja el panel como nuevo: alcance «todo el grupo», sin selección y con las reglas del objeto preseleccionadas.</summary>
    private void Preparar(LanzamientoPropuesto propuesta)
    {
        _propuesta = propuesta;
        _admitidos = (propuesta.Admitidos ?? []).Where(p => p.Admitido)
            .OrderBy(p => p.Nombre, StringComparer.CurrentCultureIgnoreCase).ToList();
        _tabletasDelGrupo = _admitidos.Count(p => !p.TabletaBloqueada);
        _tabletasBloqueadas = _admitidos.Count(p => p.TabletaBloqueada);
        _elegidos.Clear();
        _porSeleccion = false;
        _estudio = false;

        var actividad = EsActividad;
        EtiquetaLabel.Text = actividad ? "LANZAR ACTIVIDAD" : "ENVIAR A LAS TABLETAS";
        TituloLabel.Text = string.IsNullOrWhiteSpace(propuesta.Rotulo) ? (actividad ? "Actividad" : "Recurso") : propuesta.Rotulo;
        TiempoSeccion.IsVisible = actividad;
        IntentosSeccion.IsVisible = actividad;
        EstudioFila.IsVisible = !actividad;

        // Lo que trae el objeto queda preseleccionado; un valor fuera de las opciones habituales entra como ficha propia.
        _minutos = propuesta.TiempoDelObjetoSeg is int seg and > 0 ? Math.Max(1, (int)Math.Ceiling(seg / 60.0)) : null;
        _intentos = propuesta.IntentosDelObjeto is int intentos and > 0 ? intentos : null;
        ConstruirFichas(TiempoHost, _fichasTiempo, MinutosBase, _minutos, m => $"{m} min", m => { _minutos = m; Pintar(); },
                        orden: m => m ?? -1);
        ConstruirFichas(IntentosHost, _fichasIntentos, IntentosBase, _intentos, i => i.ToString()!, i => { _intentos = i; Pintar(); },
                        orden: i => i ?? int.MaxValue);

        AlumnosHost.Clear();
        _fichasAlumno.Clear();
        foreach (var p in _admitidos)
        {
            var participante = p;
            var ficha = NuevaFicha((_, _) => AlternarAlumno(participante));
            _fichasAlumno[p.Id] = ficha;
            AlumnosHost.Add(ficha);
        }
    }

    private static void ConstruirFichas(FlexLayout host, List<(int? Valor, string Texto, Button Boton)> destino, int?[] baseOpciones,
                                        int? preseleccion, Func<int, string> texto, Action<int?> alElegir, Func<int?, int> orden)
    {
        host.Clear();
        destino.Clear();
        var opciones = baseOpciones.ToList();
        if (preseleccion is { } p && !opciones.Contains(p)) opciones.Add(p);
        foreach (var valor in opciones.OrderBy(orden))
        {
            var v = valor;
            var ficha = NuevaFicha((_, _) => alElegir(v));
            destino.Add((v, v is { } n ? texto(n) : "Sin límite", ficha));
            host.Add(ficha);
        }
    }

    // ------------------------------------------------------------------ interacción

    private void ElegirAlcance(bool seleccion)
    {
        if (seleccion && _tabletasDelGrupo == 0) return;
        _porSeleccion = seleccion;
        Pintar();
    }

    private void AlternarAlumno(ParticipanteAula p)
    {
        if (p.TabletaBloqueada) return;
        if (!_elegidos.Remove(p.Id)) _elegidos.Add(p.Id);
        Pintar();
    }

    private void ElegirATodos(bool todos)
    {
        _elegidos.Clear();
        if (todos)
            foreach (var p in _admitidos.Where(p => !p.TabletaBloqueada)) _elegidos.Add(p.Id);
        Pintar();
    }

    private void OnEstudioTocado(object? sender, TappedEventArgs e)
    {
        _estudio = !_estudio;
        Pintar();
    }

    /// <summary>El lanzamiento tal como lo pidió el profesor. «Sin límite» es <c>null</c>; el tiempo viaja en segundos (minutos × 60).</summary>
    private DistribuirSolicitud Armar()
    {
        var p = _propuesta!;
        var actividad = EsActividad;
        var ids = _porSeleccion
            ? _admitidos.Where(a => !a.TabletaBloqueada && _elegidos.Contains(a.Id)).Select(a => a.Id).ToList()
            : null;
        return new DistribuirSolicitud(
            p.Clase, p.ObjetoRef, p.MediaRef, p.Rotulo,
            DisponibleEstudio: !actividad && _estudio,
            Alcance: _porSeleccion ? "seleccion" : "grupo",
            Participantes: ids,
            IntentosPermitidos: actividad ? _intentos : null,
            TiempoLimiteSeg: actividad && _minutos is { } m ? m * 60 : null);
    }

    // ------------------------------------------------------------------ pintado

    /// <summary>Repinta todo lo que depende de lo elegido. Las fichas se reutilizan: sólo cambia su texto y su relieve.</summary>
    private void Pintar()
    {
        if (_propuesta is null) return;
        var actividad = EsActividad;

        Vestir(_fichaGrupo, $"Todo el grupo ({Tabletas(_tabletasDelGrupo)})", !_porSeleccion, true, "●", "○");
        Vestir(_fichaElegir, "Elegir alumnos", _porSeleccion, _tabletasDelGrupo > 0, "●", "○");
        BloqueadasLabel.IsVisible = _tabletasBloqueadas > 0;
        if (_tabletasBloqueadas > 0)
            BloqueadasLabel.Text = _tabletasBloqueadas == 1
                ? "Hay 1 tableta bloqueada: no recibirá el lanzamiento."
                : $"Hay {_tabletasBloqueadas} tabletas bloqueadas: no recibirán el lanzamiento.";

        ElegirHost.IsVisible = _porSeleccion;
        if (_porSeleccion)
        {
            ContadorLabel.Text = $"{_elegidos.Count} de {_tabletasDelGrupo} alumnos elegidos";
            foreach (var p in _admitidos)
            {
                var ficha = _fichasAlumno[p.Id];
                if (p.TabletaBloqueada) Vestir(ficha, $"{p.Nombre} · tableta bloqueada", false, false, "☑", "☐");
                else Vestir(ficha, p.Nombre, _elegidos.Contains(p.Id), true, "☑", "☐");
            }
        }

        if (actividad)
        {
            foreach (var (valor, texto, boton) in _fichasTiempo) Vestir(boton, texto, valor == _minutos, true, "●", "○");
            foreach (var (valor, texto, boton) in _fichasIntentos) Vestir(boton, texto, valor == _intentos, true, "●", "○");
        }
        else PintarEstudio();

        ResumenLabel.Text = Resumen(actividad);
        PintarNota();
        Ds.Habilitar(_lanzar, HayDestinatarios);
    }

    /// <summary>«12 tabletas · 10 min · 2 intentos»; sin destinatarios dice qué falta y qué sigue (UXR-005).</summary>
    private string Resumen(bool actividad)
    {
        if (!HayDestinatarios)
        {
            if (_porSeleccion) return "Elige al menos un alumno para poder lanzar.";
            return _admitidos.Count == 0
                ? "Todavía no hay alumnos conectados · espera a que entren a la clase."
                : "Todas las tabletas conectadas están bloqueadas · desbloquea alguna para poder lanzar.";
        }
        var partes = new List<string> { Tabletas(Destinatarios) };
        if (actividad)
        {
            partes.Add(_minutos is { } m ? $"{m} min" : "sin límite de tiempo");
            partes.Add(_intentos is { } i ? (i == 1 ? "1 intento" : $"{i} intentos") : "intentos sin límite");
        }
        else partes.Add(_estudio ? "disponible para estudiar en casa" : "sólo durante la clase");
        return string.Join(" · ", partes);
    }

    /// <summary>El interruptor de «estudiar en casa»: la pista y la perilla dibujadas con Border (nada de Path ni Ellipse) y el estado también en texto.</summary>
    private void PintarEstudio()
    {
        EstudioPista.BackgroundColor = _estudio ? Ds.Exito : Color.FromArgb("#A1A1AA");
        EstudioPerilla.HorizontalOptions = _estudio ? LayoutOptions.End : LayoutOptions.Start;
        EstudioDetalleLabel.Text = _estudio
            ? "Sí · los alumnos podrán abrirlo después de la clase."
            : "No · sólo lo verán durante la clase.";
        SemanticProperties.SetDescription(EstudioFila, $"Dejar disponible para estudiar en casa: {(_estudio ? "activado" : "desactivado")}");
    }

    /// <summary>MSG-045: aviso informativo, no bloquea. Si se eligieron alumnos sólo cuenta a quienes recibirían el lanzamiento.</summary>
    private void PintarNota()
    {
        IEnumerable<string> nombres = (_propuesta?.ConPocoEspacio ?? []).Where(n => !string.IsNullOrWhiteSpace(n)).Distinct();
        static IEnumerable<string> Claves(ParticipanteAula p) => [p.Nombre, p.PersonaId, p.Id];
        var bloqueados = _admitidos.Where(p => p.TabletaBloqueada).SelectMany(Claves).ToHashSet();
        var conocidos = _admitidos.SelectMany(Claves).ToHashSet();
        var elegidos = _admitidos.Where(p => _elegidos.Contains(p.Id)).SelectMany(Claves).ToHashSet();
        nombres = nombres.Where(n => !bloqueados.Contains(n) && (!_porSeleccion || elegidos.Contains(n) || !conocidos.Contains(n)));
        var lista = nombres.ToList();

        NotaHost.IsVisible = lista.Count > 0;
        if (lista.Count == 0) { NotaHost.Content = null; return; }
        var visibles = string.Join(", ", lista.Take(MaximoNombresEnNota));
        if (lista.Count > MaximoNombresEnNota) visibles += $" y {lista.Count - MaximoNombresEnNota} más";
        NotaHost.Content = Ds.Alerta_(
            $"{lista.Count} {(lista.Count == 1 ? "tableta tiene" : "tabletas tienen")} poco espacio: {visibles}.",
            "Se lanza igual; las que no puedan guardarlo lo verán al abrirlo.",
            Ds.AlertaSuave, Ds.Tinta);
    }

    // ------------------------------------------------------------------ fichas

    private static string Tabletas(int n) => n == 1 ? "1 tableta" : $"{n} tabletas";

    /// <summary>Una ficha táctil (≥ 44 pt): botón real, para que también se pueda activar con accesibilidad. El estilo lo pone <see cref="Vestir"/>.</summary>
    private static Button NuevaFicha(EventHandler alPulsar, double alto = 54, double fuente = 16)
    {
        var ficha = new Button
        {
            HeightRequest = alto, MinimumHeightRequest = alto, CornerRadius = Ds.RadioBoton, FontFamily = Ds.FuenteMedia, FontSize = fuente,
            Padding = new Thickness(20, 0), BorderWidth = 1.5, Margin = new Thickness(0, 0, 10, 10),
        };
        Ds.Hundir(ficha);
        ficha.Clicked += alPulsar;
        return ficha;
    }

    /// <summary>
    /// Activa: tinta oscura con texto blanco (cambia la luminosidad, no sólo el tono) y la marca de estado en el texto. Inactiva: gris
    /// claro con filo. Deshabilitada: atenuada. Las dos marcas ocupan el mismo ancho para que la cuadrícula no salte al tocar.
    /// </summary>
    private static void Vestir(Button ficha, string texto, bool activa, bool habilitada, string marcaSi, string marcaNo)
    {
        ficha.Text = $"{(activa ? marcaSi : marcaNo)}  {texto}";
        ficha.BackgroundColor = activa ? Ds.Tinta : FondoFicha;
        ficha.TextColor = activa ? Colors.White : Ds.Tinta;
        ficha.BorderColor = activa ? Ds.Tinta : FiloFicha;
        ficha.IsEnabled = habilitada;
        ficha.Opacity = habilitada ? 1 : 0.5;
        SemanticProperties.SetDescription(ficha, $"{texto}, {(activa ? "elegido" : "sin elegir")}");
    }
}

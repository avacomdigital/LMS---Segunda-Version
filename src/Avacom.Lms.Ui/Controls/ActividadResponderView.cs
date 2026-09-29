using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// CMP-002 / UXR-004: lo único que el alumno lee sobre el guardado. Jamás hay un estado de error: si el nodo no responde, lo que
/// respondió está a salvo en la tableta y sale solo cuando vuelva al aula.
/// </summary>
public enum EstadoGuardado { Guardado, Guardando, GuardadoEnElDispositivo }

/// <summary>
/// Lo que <see cref="ActividadResponderView"/> necesita saber del intento en curso y de cómo mandar lo que responde. <c>Cola</c> es la cola
/// local durable de la tableta (BR-071: cada respuesta se guarda por separado, sin esperar a la entrega) y <c>Sincronizar</c> la orden de
/// vaciarla hacia el nodo (el control no sabe nada de HTTP). <c>ResolverUrl</c> convierte las rutas relativas de las imágenes en URL absolutas.
/// </summary>
public sealed record ContextoActividad(
    string SesionId, string DistribucionId, string ParticipanteId, int IntentoNumero, int? IntentosPermitidos,
    ColaRespuestas Cola, Func<Task> Sincronizar, Func<string, Uri>? ResolverUrl = null);

/// <summary>
/// El control con el que el alumno RESPONDE una actividad lanzada por el profesor (007-05, 007-06, 007-08 · PAN-110/111/112/123/132).
///
/// Una pregunta a la vez, con «Anterior» / «Siguiente», una tira de números tocables con marca de contestada y «Entregar» siempre a la mano.
/// Cada respuesta se guarda en la cola del dispositivo apenas el alumno la confirma y se dispara el sincronizador sin esperar; una pregunta
/// cuenta como «respondida» al guardarse localmente, nunca depende de la red. Volver a una pregunta muestra lo elegido y deja cambiarlo (la
/// secuencia mayor gana en el nodo). No hay «Comprobar» ni corrección: el alumno no ve si acertó ni recibe una nota (DEC-032).
///
/// Cubre <c>opcion_multiple</c>, <c>verdadero_falso</c>, <c>completar</c>, <c>relacionar</c>, <c>ordenar</c> y <c>abierta</c> (texto); cualquier otro
/// tipo dice «Esta pregunta se responde con tu profesor.» y no bloquea la entrega. Ver <c>ActividadEditores.cs</c>.
///
/// Cronómetro CMP-003 con sus cuatro estados (<c>ActividadCronometro.cs</c>): el control cuenta hacia atrás sólo entre un aviso del host y el
/// siguiente. Sin tiempo (congelado, vencido) la actividad queda de sólo lectura; en la gracia sólo se puede entregar lo que hay.
///
/// Todos los métodos públicos se pueden llamar desde cualquier hilo (pasan al de la interfaz) y los eventos salen siempre en el hilo de la
/// interfaz. El único temporizador vivo (cronómetro y espera de escritura) se detiene al quitar el control del árbol visual (Unloaded).
/// </summary>
public sealed class ActividadResponderView : ContentView
{
    static ActividadResponderView() => NeumoChrome.Registrar();

    private static readonly Brush BrochaInfo = new SolidColorBrush(Ds.Info);

    private sealed record Chip(Border Caja, Label Numero, Label Marca);

    // ------------------------------------------------------------------------------ estado
    private ObjetoAula? _actividad;
    private ContextoActividad? _ctx;
    private IReadOnlyList<PreguntaAula> _preguntas = [];
    private int _indice;
    private readonly HashSet<string> _respondidas = [];
    private readonly HashSet<string> _marcadas = [];
    private readonly Dictionary<string, JsonElement> _respuestas = [];       // lo último guardado, para volver a verlo
    private readonly Dictionary<string, JsonElement> _sinGuardar = [];       // lo que el disco no pudo escribir: se reintenta en la siguiente acción
    private EditorPregunta? _editor;
    private bool _confirmando;
    private bool _entregaPedida;
    private bool _entregado;
    private bool? _enviadoAlNodo;
    private string? _avisoEntrega;
    private bool _soloLectura;
    private double _area = 56;
    private double _escala = 1;
    private bool _editableVisto;
    private bool _entregableVisto;

    private int _sincronizando;
    private int _pendientes;
    private bool _conectado = true;
    private EstadoGuardado _estadoGuardado = EstadoGuardado.Guardado;

    private readonly CronometroLocal _crono = new();
    private IDispatcherTimer? _reloj;

    // --------------------------------------------------------------------------- elementos
    private readonly Grid _raiz;
    private readonly Label _titulo;
    private readonly Label _intento;
    private readonly Label _posicion;
    private readonly Label _contestadas;
    private readonly Border _barra;
    private readonly Grid _barraRejilla;
    private readonly Border _pildoraGuardado;
    private readonly Label _textoGuardado;
    private readonly Border _banner;
    private readonly Label _textoCrono;
    private readonly Label _detalleCrono;
    private readonly ScrollView _scroll;
    private readonly Grid _nav = new() { ColumnSpacing = 12, RowSpacing = 10 };
    private readonly Grid _filaBotones = new() { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
    private readonly List<Chip> _chips = [];
    private ScrollView _tira = null!;
    private HorizontalStackLayout _tiraPila = null!;
    private Button _btnAnterior = null!, _btnSiguiente = null!, _btnEntregar = null!;
    private View _capAnterior = null!, _capSiguiente = null!, _capEntregar = null!;
    private bool _navAncha;

    public ActividadResponderView()
    {
        _titulo = Ds.Titulo(string.Empty, 22);
        _titulo.MaxLines = 2;
        _titulo.LineBreakMode = LineBreakMode.TailTruncation;
        _titulo.AutomationId = "act-titulo";
        _intento = Ds.Secundario(string.Empty, 15);
        _intento.IsVisible = false;
        _intento.AutomationId = "act-intento";

        _textoGuardado = new Label { FontFamily = Ds.FuenteMedia, FontSize = 15, TextColor = Ds.Tinta, VerticalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.NoWrap };
        _pildoraGuardado = new Border
        {
            StrokeThickness = 0, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioPildora }, Padding = new Thickness(14, 8),
            Content = _textoGuardado, VerticalOptions = LayoutOptions.Center, AutomationId = "act-guardado",
        };

        var titulos = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center, Children = { _titulo, _intento } };
        var fila0 = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
        fila0.Add(titulos, 0, 0);
        fila0.Add(_pildoraGuardado, 1, 0);

        _posicion = new Label { FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, VerticalTextAlignment = TextAlignment.Center, AutomationId = "act-posicion" };
        _contestadas = Ds.Secundario(string.Empty, 15);
        _contestadas.VerticalTextAlignment = TextAlignment.Center;
        _contestadas.AutomationId = "act-contestadas";
        _barraRejilla = new Grid { ColumnDefinitions = [new ColumnDefinition(new GridLength(0, GridUnitType.Star)), new ColumnDefinition(GridLength.Star)], HeightRequest = 10 };
        _barraRejilla.Add(new BoxView { Color = Ds.Info, CornerRadius = 5 }, 0, 0);
        _barra = new Border
        {
            BackgroundColor = Color.FromArgb("#E4E4E7"), StrokeThickness = 0, HeightRequest = 10, VerticalOptions = LayoutOptions.Center,
            StrokeShape = new RoundRectangle { CornerRadius = 5 }, Content = _barraRejilla, AutomationId = "act-progreso",
        };
        var fila1 = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 14 };
        fila1.Add(_posicion, 0, 0);
        fila1.Add(_barra, 1, 0);
        fila1.Add(_contestadas, 2, 0);

        _textoCrono = new Label { FontFamily = Ds.FuenteMedia, FontSize = 19, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap };
        _detalleCrono = Ds.Secundario(string.Empty, 15);
        _detalleCrono.TextColor = Ds.Tinta;
        _banner = new Border
        {
            StrokeThickness = 0, Padding = new Thickness(16, 10), IsVisible = false, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno },
            Content = new VerticalStackLayout { Spacing = 2, Children = { _textoCrono, _detalleCrono } }, AutomationId = "act-cronometro",
        };

        var cabecera = Ds.Tarjeta(new VerticalStackLayout { Spacing = 10, Children = { fila0, fila1, _banner } }, Ds.RadioTarjeta, new Thickness(18, 14));

        _scroll = new ScrollView { Orientation = ScrollOrientation.Vertical };

        _raiz = new Grid { RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Star), new RowDefinition(GridLength.Auto)], RowSpacing = 12 };
        _raiz.Add(cabecera, 0, 0);
        _raiz.Add(_scroll, 0, 1);
        _raiz.Add(_nav, 0, 2);
        Content = _raiz;

        Loaded += (_, _) => AjustarReloj();
        Unloaded += (_, _) =>
        {
            // Quien se va deja guardado lo que estaba escribiendo y no deja ningún temporizador vivo.
            try { _editor?.Vaciar(); } catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "actividad · al salir", ex); }
            DetenerReloj();
        };
        SizeChanged += (_, _) =>
        {
            var ancha = Width >= 900;
            if (ancha == _navAncha) return;
            _navAncha = ancha;
            if (_capAnterior is not null) AcomodarNavegacion();
        };

        ConstruirNavegacion();
        MostrarVacio();
        PintarGuardado(_estadoGuardado);
    }

    // ===================================================================================== API pública

    /// <summary>Se ha respondido la pregunta: se guardó en la cola del dispositivo (no quiere decir que ya llegó al nodo).</summary>
    public event Action<string>? RespuestaGuardada;

    /// <summary>Cambió lo que se le dice al alumno sobre el guardado (CMP-002). Sale también al cargar.</summary>
    public event Action<EstadoGuardado>? GuardadoCambio;

    /// <summary>El alumno confirmó la entrega: ya se marcó en la cola (<see cref="ColaRespuestas.Entregar"/>) y se disparó la sincronización.</summary>
    public event Action? EntregaSolicitada;

    /// <summary>Sin tiempo o entregado: se ve todo y no se edita ni se entrega. El cronómetro y la entrega ya lo ponen solos; esto es para el host.</summary>
    public bool SoloLectura
    {
        get => _soloLectura;
        set
        {
            if (_soloLectura == value) return;
            EnHiloUi(() =>
            {
                try { _editor?.Vaciar(); } catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "actividad · solo lectura", ex); }
                _soloLectura = value;
                if (_actividad is not null) MostrarPregunta();
            });
        }
    }

    /// <summary>Alto y ancho mínimo de lo que se toca, en puntos. 56 por defecto; la tableta de preescolar y primaria pide 60 a 72. Nunca baja de 44.</summary>
    public double AreaTactil
    {
        get => _area;
        set
        {
            if (Math.Abs(_area - value) < 0.01) return;
            _area = value;
            if (_actividad is not null) Reconstruir();
        }
    }

    /// <summary>Tamaño del texto respecto del base (1 = tableta; algo más grande para la pantalla del aula).</summary>
    public double Escala
    {
        get => _escala;
        set
        {
            if (Math.Abs(_escala - value) < 0.001) return;
            _escala = value;
            if (_actividad is not null) Reconstruir();
        }
    }

    /// <summary>Cuántas preguntas ya están guardadas en la tableta.</summary>
    public int Respondidas => _respondidas.Count;

    /// <summary>Lo que ve ahora el alumno sobre el guardado.</summary>
    public EstadoGuardado EstadoDeGuardado => _estadoGuardado;

    /// <summary>La entrega ya se pidió (o el nodo ya la tiene): no se edita más.</summary>
    public bool Entregada => _entregaPedida || _entregado;

    /// <summary>
    /// Pinta la actividad desde la primera pregunta sin responder (o desde la última, si ya están todas). <paramref name="preguntasRespondidas"/> son
    /// las que el nodo ya tiene de este intento; las que esperan en la cola del dispositivo se recuperan solas, con lo que se eligió.
    /// </summary>
    public void Cargar(ObjetoAula actividad, ContextoActividad contexto, IReadOnlySet<string>? preguntasRespondidas = null) =>
        EnHiloUi(() => CargarEnUi(actividad, contexto, preguntasRespondidas));

    /// <summary>
    /// El host trae un estado nuevo del cronómetro (CMP-003). Nulo: la actividad no tiene límite de tiempo. Entre un estado y otro cuenta el control.
    /// Se llama DESPUÉS de <see cref="Cargar"/>: cargar otra actividad (o otro intento) olvida el cronómetro anterior.
    /// </summary>
    public void ActualizarCronometro(CronometroAula? cronometro, long servidorEnMs) =>
        EnHiloUi(() =>
        {
            _crono.Fijar(cronometro, servidorEnMs);
            AplicarCronometro();
        });

    /// <summary>El host informa cuánto espera en la cola de la tableta y si hay conexión con el nodo: con eso se decide «Guardado», «Guardando…» o «Guardado en tu tableta».</summary>
    public void ActualizarEnvio(int pendientesEnCola, bool conectado) =>
        EnHiloUi(() =>
        {
            _pendientes = Math.Max(0, pendientesEnCola);
            _conectado = conectado;
            RecalcularGuardado();
        });

    /// <summary>
    /// El intento quedó entregado (PAN-123). <paramref name="enviadoAlNodo"/>: el nodo ya lo tiene (MSG-012) o sólo está guardado en la tableta y se enviará solo
    /// cuando vuelva al aula (MSG-013). El control NO abre otro intento aunque haya: eso lo decide quien lo aloja.
    /// </summary>
    public void Entregado(bool enviadoAlNodo) =>
        EnHiloUi(() =>
        {
            try { _editor?.Vaciar(); } catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "actividad · entregado", ex); }
            _entregado = true;
            _entregaPedida = true;
            _confirmando = false;
            _enviadoAlNodo = enviadoAlNodo;
            MostrarPregunta();
        });

    // ===================================================================================== carga

    private void EnHiloUi(Action accion)
    {
        var d = Dispatcher;
        if (d is not null && d.IsDispatchRequired) d.Dispatch(accion);
        else accion();
    }

    private void CargarEnUi(ObjetoAula actividad, ContextoActividad contexto, IReadOnlySet<string>? previas)
    {
        try { _editor?.Vaciar(); } catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "actividad · al recargar", ex); }
        _editor = null;
        // Otra actividad u otro intento: el tiempo de la anterior no vale. El host manda el estado del cronómetro DESPUÉS de cargar.
        // Un refresco de la misma actividad conserva el que ya tenía para que el aviso de tiempo no parpadee.
        var mismoIntento = _ctx is not null && _ctx.DistribucionId == contexto.DistribucionId && _ctx.IntentoNumero == contexto.IntentoNumero;
        if (!mismoIntento) _crono.Fijar(null, 0);
        _actividad = actividad;
        _ctx = contexto;
        _preguntas = actividad.Preguntas ?? [];
        _respondidas.Clear();
        _respuestas.Clear();
        _sinGuardar.Clear();
        _marcadas.Clear();
        _confirmando = false;
        _entregaPedida = false;
        _entregado = false;
        _enviadoAlNodo = null;
        _avisoEntrega = null;

        var validas = _preguntas.Select(p => p.PreguntaRef).ToHashSet();
        if (previas is not null)
            foreach (var r in previas)
                if (validas.Contains(r)) _respondidas.Add(r);
        // Lo que esperaba en la cola cuando se abrió la pantalla (la app se cerró, la tableta se reinició): sigue contando y se vuelve a ver.
        foreach (var paquete in contexto.Cola.Pendientes(contexto.SesionId))
        {
            if (paquete.DistribucionId != contexto.DistribucionId || paquete.ParticipanteId != contexto.ParticipanteId || paquete.IntentoNumero != contexto.IntentoNumero) continue;
            foreach (var r in paquete.Respuestas)
                if (validas.Contains(r.PreguntaRef))
                {
                    _respondidas.Add(r.PreguntaRef);
                    _respuestas[r.PreguntaRef] = r.Respuesta;
                }
            if (paquete.Entregar) _entregaPedida = true;   // la entrega ya se pidió y sólo falta que salga
        }
        _pendientes = contexto.Cola.CantidadPendiente(contexto.SesionId);
        var primera = _preguntas.ToList().FindIndex(p => !_respondidas.Contains(p.PreguntaRef));
        _indice = primera >= 0 ? primera : Math.Max(0, _preguntas.Count - 1);

        _titulo.Text = actividad.Titulo;
        PintarIntento();
        ConstruirNavegacion();
        MostrarPregunta();
        RecalcularGuardado(forzar: true);
    }

    private void Reconstruir()
    {
        try { _editor?.Vaciar(); } catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "actividad · al redibujar", ex); }
        ConstruirNavegacion();
        MostrarPregunta();
    }

    // ============================================================================= editable y entregable

    private bool Editable => !_soloLectura && !_entregado && !_entregaPedida && _crono.PermiteEditar;
    private bool PuedeEntregar => !_soloLectura && !_entregado && !_entregaPedida && _crono.PermiteEntregar && _preguntas.Count > 0;
    private double Alto => Math.Max(44, _area);

    // ========================================================================================= cuerpo

    /// <summary>Repinta el cuerpo según en qué punto va el alumno: pregunta, confirmación de la entrega o pantalla de entregado.</summary>
    private void MostrarPregunta()
    {
        try { _editor?.Vaciar(); } catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "actividad · al cambiar", ex); }
        _editor = null;
        _editableVisto = Editable;
        _entregableVisto = PuedeEntregar;
        if (_actividad is null || _ctx is null)
        {
            MostrarVacio();
            return;
        }
        if (_preguntas.Count == 0)
            PonerCuerpo(TarjetaMensaje("Esta actividad todavía no tiene preguntas.", "Avísale a tu profesor.", "act-sin-preguntas"));
        else if (_entregado || _entregaPedida)
            PonerCuerpo(TarjetaEntrega());
        else if (_confirmando && PuedeEntregar)
            PonerCuerpo(TarjetaConfirmar());
        else
        {
            _confirmando = false;
            _avisoEntrega = null;
            PintarPregunta();
        }
        PintarCabecera();
        PintarChips(centrar: true);
        ActualizarNavegacion();
        PintarBanner();
        AjustarReloj();
    }

    private void MostrarVacio()
    {
        _titulo.Text = string.Empty;
        _intento.IsVisible = false;
        PonerCuerpo(TarjetaMensaje("Aquí aparecerá tu actividad.", null, "act-vacio"));
        PintarCabecera();
        ActualizarNavegacion();
        PintarBanner();
    }

    private void PonerCuerpo(View contenido)
    {
        // El margen deja sitio a la sombra de la tarjeta, que el ScrollView recortaría.
        _scroll.Content = new VerticalStackLayout { Padding = new Thickness(4, 4, 4, 20), Children = { contenido } };
        if (_scroll.Handler is not null)
            Dispatcher.Dispatch(async () =>
            {
                try { await _scroll.ScrollToAsync(0, 0, false); } catch { /* sin diseño todavía: queda arriba */ }
            });
    }

    private void PintarPregunta()
    {
        var p = _preguntas[Math.Clamp(_indice, 0, _preguntas.Count - 1)];
        var cx = new ContextoEditor
        {
            AreaTactil = _area, Escala = _escala, ResolverUrl = _ctx!.ResolverUrl, Editable = Editable, Dispatcher = Dispatcher,
            Confirmar = respuesta => GuardarRespuesta(p.PreguntaRef, respuesta),
        };
        _editor = EditorPregunta.Crear(p, cx);
        var conContenido = _respuestas.TryGetValue(p.PreguntaRef, out var previa);
        if (conContenido)
        {
            try { _editor.Aplicar(previa); } catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, $"actividad · pregunta {p.PreguntaRef} · repintar lo respondido", ex); }
        }
        PonerCuerpo(TarjetaPregunta(p, cx, _editor, _respondidas.Contains(p.PreguntaRef) && !conContenido));
    }

    private View TarjetaPregunta(PreguntaAula p, ContextoEditor cx, EditorPregunta editor, bool respondidaSinContenido)
    {
        var pila = new VerticalStackLayout { Spacing = 18 };
        if (_indice == 0 && _actividad is { } a && !string.IsNullOrWhiteSpace(a.Instrucciones))
            pila.Add(Ds.ConTramos(a.InstruccionesTramos, a.Instrucciones, 17 * _escala, Ds.TintaSuave));
        if (_soloLectura && _crono.PermiteEditar) pila.Add(Nota("Por ahora sólo puedes mirar tus respuestas. Lo que llevas está guardado."));
        if (!string.IsNullOrWhiteSpace(p.Enunciado) || p.EnunciadoTramos is { Count: > 0 })
            pila.Add(Ds.ConTramos(p.EnunciadoTramos, p.Enunciado, 25 * _escala));
        foreach (var m in p.Medios ?? [])
        {
            if (m.Ausente) continue;
            if (m.Componente == "imagen" && !string.IsNullOrWhiteSpace(m.Url))
                pila.Add(VistasActividad.Imagen(cx, m.Url, m.TextoAlternativo, 260 * _escala));
            else
            {
                var rotulo = m.Titulo ?? m.TextoAlternativo;
                pila.Add(Ds.Pildora(string.IsNullOrWhiteSpace(rotulo) ? MedioLegible(m) : $"{MedioLegible(m)} · {rotulo}", Ds.InfoSuave, Ds.Tinta, 15 * _escala));
            }
        }
        pila.Add(editor.Vista);
        if (respondidaSinContenido) pila.Add(Ds.Secundario("Ya respondiste esta pregunta. Si respondes otra vez, cambia tu respuesta.", 15 * _escala));
        pila.Add(BotonMarcar(p));
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(24, 22));
    }

    private static string MedioLegible(MedioAula m) => m.Componente switch
    {
        "video" => "Video", "audio" => "Audio", "pdf" => "Documento", "imagen" => "Imagen", _ => "Material",
    };

    private static View Nota(string texto) => new Border
    {
        BackgroundColor = Ds.Lienzo, StrokeThickness = 0, Padding = new Thickness(14, 10), StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno },
        Content = Ds.Secundario(texto, 15),
    };

    /// <summary>«Marcar para revisar» (CMP-030): una ayuda para el alumno. No cambia lo que se guarda ni lo que se envía.</summary>
    private View BotonMarcar(PreguntaAula p)
    {
        string Texto() => _marcadas.Contains(p.PreguntaRef) ? "★  Marcada para revisar" : "☆  Marcar para revisar";
        var boton = Ds.Boton(Texto(), Ds.Rango.Secondary, null, Math.Max(44, _area * 0.85));
        boton.HorizontalOptions = LayoutOptions.End;
        boton.AutomationId = "act-marcar";
        boton.Clicked += (_, _) =>
        {
            if (!_marcadas.Remove(p.PreguntaRef)) _marcadas.Add(p.PreguntaRef);
            boton.Text = Texto();
            PintarChips();
        };
        return Ds.Capsula(boton);
    }

    private View TarjetaMensaje(string principal, string? detalle, string id)
    {
        var pila = new VerticalStackLayout { Spacing = 8, HorizontalOptions = LayoutOptions.Center, AutomationId = id };
        var titulo = Ds.Titulo(principal, 23 * _escala);
        titulo.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(titulo);
        if (!string.IsNullOrWhiteSpace(detalle))
        {
            var d = Ds.Secundario(detalle!, 17 * _escala);
            d.HorizontalTextAlignment = TextAlignment.Center;
            pila.Add(d);
        }
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(28, 36));
    }

    // ----------------------------------------------------------------------------- entrega (PAN-123)

    private View TarjetaConfirmar()
    {
        var faltan = new List<int>();
        for (var i = 0; i < _preguntas.Count; i++)
            if (!_respondidas.Contains(_preguntas[i].PreguntaRef)) faltan.Add(i + 1);

        string principal, secundaria, entregar;
        if (faltan.Count == 0)
        {
            principal = "Ya respondiste todas las preguntas.";
            secundaria = "Cuando entregues, ya no podrás cambiar nada.";
            entregar = "Entregar";
        }
        else
        {
            principal = faltan.Count == 1 ? "Te falta 1 pregunta. Puedes entregar igual." : $"Te faltan {faltan.Count} preguntas. Puedes entregar igual.";
            secundaria = faltan.Count <= 10 ? $"Sin responder: {string.Join(", ", faltan)}." : string.Empty;
            entregar = "Entregar igual";
        }

        var pila = new VerticalStackLayout { Spacing = 14, AutomationId = "act-confirmar" };
        var titulo = Ds.Titulo(principal, 24 * _escala);
        titulo.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(titulo);
        if (!string.IsNullOrWhiteSpace(secundaria))
        {
            var s = Ds.Secundario(secundaria, 17 * _escala);
            s.HorizontalTextAlignment = TextAlignment.Center;
            pila.Add(s);
        }
        if (!string.IsNullOrWhiteSpace(_avisoEntrega))
        {
            var aviso = Ds.Cuerpo(_avisoEntrega!, 17 * _escala);
            aviso.HorizontalTextAlignment = TextAlignment.Center;
            pila.Add(aviso);
        }
        var alto = Math.Max(56, _area);
        var volver = Ds.Boton("Volver", Ds.Rango.Secondary, (_, _) => VolverDeConfirmar(), alto);
        volver.AutomationId = "act-volver";
        var confirmar = Ds.Boton(entregar, Ds.Rango.Primary, (_, _) => ConfirmarEntrega(), alto);
        confirmar.AutomationId = "act-entregar-igual";
        var botones = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 14, Margin = new Thickness(0, 6, 0, 0) };
        botones.Add(Ds.Capsula(volver), 0, 0);
        botones.Add(Ds.Capsula(confirmar), 1, 0);
        pila.Add(botones);
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(28, 30));
    }

    private View TarjetaEntrega()
    {
        string principal;
        string? secundaria = null;
        var respondidas = $"Respondiste {_respondidas.Count} de {_preguntas.Count} {(_preguntas.Count == 1 ? "pregunta" : "preguntas")}.";
        if (_enviadoAlNodo == true)
        {
            principal = "Entregado. Tu profesor ya lo tiene.";                                              // MSG-012
            secundaria = respondidas;
        }
        else if (_enviadoAlNodo == false)
        {
            principal = "Terminado y guardado. Se enviará solo cuando tu tableta vuelva a estar en el aula."; // MSG-013
            secundaria = respondidas;
        }
        else
        {
            principal = "Tu entrega quedó guardada.";
            secundaria = "Se la estamos enviando a tu profesor.";
        }
        var visto = new Border
        {
            WidthRequest = 84, HeightRequest = 84, BackgroundColor = Ds.InfoSuave, StrokeThickness = 0, HorizontalOptions = LayoutOptions.Center,
            StrokeShape = new RoundRectangle { CornerRadius = 42 },
            Content = new Label { Text = "✓", FontSize = 42, FontFamily = Ds.FuenteMedia, TextColor = Ds.Tinta, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
        };
        var pila = new VerticalStackLayout { Spacing = 14, HorizontalOptions = LayoutOptions.Center, AutomationId = "act-entregado" };
        pila.Add(visto);
        var titulo = Ds.Titulo(principal, 25 * _escala);
        titulo.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(titulo);
        var s = Ds.Secundario(secundaria, 18 * _escala);
        s.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(s);
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(28, 40));
    }

    private void PedirEntrega()
    {
        if (!PuedeEntregar) return;
        try { _editor?.Vaciar(); } catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "actividad · antes de entregar", ex); }
        _confirmando = true;
        _avisoEntrega = null;
        MostrarPregunta();
    }

    private void VolverDeConfirmar()
    {
        _confirmando = false;
        _avisoEntrega = null;
        MostrarPregunta();
    }

    private void ConfirmarEntrega()
    {
        var ctx = _ctx;
        if (ctx is null || !PuedeEntregar)
        {
            VolverDeConfirmar();
            return;
        }
        // Lo que estuviera sin escribir en el disco se reintenta antes de marcar la entrega: la entrega va detrás de sus respuestas.
        ReintentarPendientes();
        try
        {
            ctx.Cola.Entregar(ctx.SesionId, ctx.DistribucionId, ctx.ParticipanteId, ctx.IntentoNumero);
        }
        catch (Exception ex)
        {
            // Guardar no falla de cara al alumno (UXR-004): se dice qué se conservó y qué sigue, sin códigos.
            RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "actividad · marcar la entrega", ex);
            _avisoEntrega = "Tus respuestas siguen aquí. Toca «Entregar» otra vez.";
            MostrarPregunta();
            return;
        }
        _entregaPedida = true;
        _confirmando = false;
        _avisoEntrega = null;
        _pendientes = ctx.Cola.CantidadPendiente(ctx.SesionId);
        DispararSincronizacion();
        MostrarPregunta();
        EntregaSolicitada?.Invoke();
    }

    // ====================================================================================== guardado

    /// <summary>
    /// El alumno confirmó una respuesta: se escribe en la cola del dispositivo y se marca «respondida» sin esperar a la red (BR-071). Enseguida
    /// se pide al sincronizador que la envíe, sin esperar. Si el disco no deja escribir, lo dicho se conserva en pantalla y se reintenta
    /// en la siguiente acción: el alumno nunca ve un error de guardado.
    /// </summary>
    private void GuardarRespuesta(string preguntaRef, JsonElement respuesta)
    {
        var ctx = _ctx;
        if (ctx is null || _entregado || _entregaPedida) return;
        var clon = respuesta.Clone();
        ReintentarPendientes(salvo: preguntaRef);
        if (Escribir(ctx, preguntaRef, clon)) _sinGuardar.Remove(preguntaRef);
        else _sinGuardar[preguntaRef] = clon;
        _respondidas.Add(preguntaRef);
        _respuestas[preguntaRef] = clon;
        _pendientes = ctx.Cola.CantidadPendiente(ctx.SesionId);
        DispararSincronizacion();
        PintarCabecera();
        PintarChips();
        RespuestaGuardada?.Invoke(preguntaRef);
    }

    private static bool Escribir(ContextoActividad ctx, string preguntaRef, JsonElement respuesta)
    {
        try
        {
            ctx.Cola.Guardar(ctx.SesionId, ctx.DistribucionId, ctx.ParticipanteId, ctx.IntentoNumero, preguntaRef, respuesta);
            return true;
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "actividad · guardar respuesta en el dispositivo", ex);
            return false;
        }
    }

    private void ReintentarPendientes(string? salvo = null)
    {
        var ctx = _ctx;
        if (ctx is null || _sinGuardar.Count == 0) return;
        foreach (var (k, v) in _sinGuardar.ToList())
            if (k != salvo && Escribir(ctx, k, v)) _sinGuardar.Remove(k);
    }

    /// <summary>Pide al host que vacíe la cola. No espera: mientras corre el estado es «Guardando…» y al terminar se recalcula con lo que quedó en la cola.</summary>
    private async void DispararSincronizacion()
    {
        var ctx = _ctx;
        if (ctx is null) return;
        _sincronizando++;
        RecalcularGuardado();
        try
        {
            await ctx.Sincronizar();
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "actividad · sincronizar", ex);   // la cola conserva todo: se reintentará
        }
        finally
        {
            _sincronizando = Math.Max(0, _sincronizando - 1);
            if (ReferenceEquals(_ctx, ctx)) _pendientes = ctx.Cola.CantidadPendiente(ctx.SesionId);
            RecalcularGuardado();
        }
    }

    /// <summary>Envío en curso → Guardando; cola vacía y con conexión → Guardado; cola con cosas o sin conexión → Guardado en tu tableta. Nunca un error.</summary>
    private void RecalcularGuardado(bool forzar = false)
    {
        var nuevo = _sincronizando > 0 || _sinGuardar.Count > 0 ? EstadoGuardado.Guardando
            : _pendientes == 0 && _conectado ? EstadoGuardado.Guardado
            : EstadoGuardado.GuardadoEnElDispositivo;
        PintarGuardado(nuevo);
        if (nuevo == _estadoGuardado && !forzar) return;
        _estadoGuardado = nuevo;
        GuardadoCambio?.Invoke(nuevo);
    }

    private void PintarGuardado(EstadoGuardado estado)
    {
        var (texto, fondo) = estado switch
        {
            EstadoGuardado.Guardando => ("●  Guardando…", Ds.Lienzo),
            EstadoGuardado.GuardadoEnElDispositivo => ("●  Guardado en tu tableta", Ds.InfoSuave),
            _ => ("✓  Guardado", Ds.InfoSuave),
        };
        _textoGuardado.Text = texto;
        _pildoraGuardado.BackgroundColor = fondo;
        SemanticProperties.SetDescription(_pildoraGuardado, texto[3..]);
    }

    // ===================================================================================== cabecera

    private void PintarIntento()
    {
        var tope = _ctx?.IntentosPermitidos;
        _intento.IsVisible = tope is > 0;
        _intento.Text = tope is > 0 ? $"Intento {_ctx!.IntentoNumero} de {tope}" : string.Empty;
    }

    private void PintarCabecera()
    {
        var total = _preguntas.Count;
        var respondidas = Math.Min(_respondidas.Count, total);
        _posicion.Text = _actividad is null ? string.Empty
            : total == 0 ? string.Empty
            : _entregado || _entregaPedida ? "Actividad terminada"
            : $"Pregunta {Math.Clamp(_indice + 1, 1, total)} de {total}";
        _contestadas.Text = total == 0 ? string.Empty : $"{respondidas} de {total} contestadas";
        _barraRejilla.ColumnDefinitions[0].Width = new GridLength(respondidas, GridUnitType.Star);
        _barraRejilla.ColumnDefinitions[1].Width = new GridLength(Math.Max(0, total - respondidas), GridUnitType.Star);
        _barra.IsVisible = total > 0;
        SemanticProperties.SetDescription(_barra, $"{respondidas} de {total} preguntas contestadas");
    }

    // ---------------------------------------------------------------- cronómetro (CMP-003, 007-06)

    private void AplicarCronometro()
    {
        // El paso de «se puede editar» a «ya no» guarda lo que quedaba a medias ANTES de cerrar la edición, y sólo entonces se repinta.
        // Mientras sea lo mismo, el cronómetro sólo cambia su texto: no se rehace la pregunta que el alumno está escribiendo.
        if (_actividad is not null && (Editable != _editableVisto || PuedeEntregar != _entregableVisto))
        {
            try { _editor?.Vaciar(); } catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "actividad · al cerrar el tiempo", ex); }
            MostrarPregunta();
            return;
        }
        PintarBanner();
        AjustarReloj();
    }

    private void PintarBanner()
    {
        var estado = _crono.Estado;
        if (estado is null || _actividad is null || _entregado || _entregaPedida)
        {
            _banner.IsVisible = false;
            return;
        }
        var (titulo, detalle) = _crono.Texto();
        _textoCrono.Text = titulo;
        _textoCrono.FontSize = (estado == CronometroLocal.EnCurso ? 22 : 18) * _escala;
        _detalleCrono.Text = detalle ?? string.Empty;
        _detalleCrono.IsVisible = !string.IsNullOrEmpty(detalle);
        // Nada de rojo ni de alarma, tampoco en el último minuto: azul suave para lo detenido, ámbar suave para la gracia, neutro para el resto.
        _banner.BackgroundColor = estado switch
        {
            CronometroLocal.Congelado => Ds.InfoSuave,
            CronometroLocal.ConGracia => Ds.AlertaSuave,
            _ => Ds.Lienzo,
        };
        _banner.IsVisible = true;
    }

    private void AjustarReloj()
    {
        var hace = IsLoaded && _actividad is not null && !_entregado && !_entregaPedida && _crono.Estado == CronometroLocal.EnCurso;
        if (!hace)
        {
            DetenerReloj();
            return;
        }
        try
        {
            if (_reloj is null)
            {
                _reloj = Dispatcher.CreateTimer();
                _reloj.Interval = TimeSpan.FromSeconds(1);
                _reloj.IsRepeating = true;
                _reloj.Tick += (_, _) => AplicarCronometro();
            }
            if (!_reloj.IsRunning) _reloj.Start();
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "actividad · reloj del cronómetro", ex);
        }
    }

    private void DetenerReloj()
    {
        try { _reloj?.Stop(); } catch { /* ya está parado */ }
    }

    // ================================================================================== navegación

    private void ConstruirNavegacion()
    {
        var alto = Alto;
        _btnAnterior = Ds.Boton("◀  Anterior", Ds.Rango.Secondary, (_, _) => Ir(_indice - 1), alto);
        _btnAnterior.AutomationId = "act-anterior";
        _capAnterior = Ds.Capsula(_btnAnterior);
        _btnSiguiente = Ds.Boton("Siguiente  ▶", Ds.Rango.Primary, (_, _) => Ir(_indice + 1), alto);
        _btnSiguiente.AutomationId = "act-siguiente";
        _capSiguiente = Ds.Capsula(_btnSiguiente);
        _btnEntregar = Ds.Boton("Entregar", Ds.Rango.Secondary, (_, _) => PedirEntrega(), alto);
        _btnEntregar.AutomationId = "act-entregar";
        _capEntregar = Ds.Capsula(_btnEntregar);

        _tiraPila = new HorizontalStackLayout { Spacing = 8, Padding = new Thickness(4, 8), VerticalOptions = LayoutOptions.Center };
        _tira = new ScrollView
        {
            Orientation = ScrollOrientation.Horizontal, HorizontalScrollBarVisibility = ScrollBarVisibility.Never, Content = _tiraPila,
            VerticalOptions = LayoutOptions.Center,
        };
        _chips.Clear();
        for (var i = 0; i < _preguntas.Count; i++)
        {
            var chip = NuevoChip(i);
            _chips.Add(chip);
            _tiraPila.Add(chip.Caja);
        }
        _navAncha = Width >= 900;
        AcomodarNavegacion();
    }

    private Chip NuevoChip(int i)
    {
        var lado = Alto;
        var numero = new Label
        {
            Text = (i + 1).ToString(), FontFamily = Ds.FuenteMedia, FontSize = (lado >= 52 ? 19 : 16) * _escala, HorizontalOptions = LayoutOptions.Center,
            VerticalOptions = LayoutOptions.Center,
        };
        var marca = new Label
        {
            FontFamily = Ds.FuenteMedia, FontSize = 12, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Start,
        };
        var rejilla = new Grid { RowDefinitions = [new RowDefinition(GridLength.Star), new RowDefinition(new GridLength(16))], RowSpacing = 0, Padding = new Thickness(0, 4, 0, 0) };
        rejilla.Add(numero, 0, 0);
        rejilla.Add(marca, 0, 1);
        var caja = new Border
        {
            WidthRequest = lado, HeightRequest = lado, StrokeThickness = 1.5, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioControl },
            Content = rejilla, AutomationId = $"act-pregunta-{i + 1}",
        };
        var indice = i;
        var toque = new TapGestureRecognizer();
        toque.Tapped += (_, _) => Ir(indice);
        caja.GestureRecognizers.Add(toque);
        return new Chip(caja, numero, marca);
    }

    /// <summary>
    /// Ancho (≥ 900): anterior · tira · entregar · siguiente en una sola fila. Angosto: la tira con «Entregar» arriba y anterior / siguiente
    /// debajo. Los mismos botones se reacomodan; ningún contenedor conserva un botón que ya está en otro.
    /// </summary>
    private void AcomodarNavegacion()
    {
        _filaBotones.Children.Clear();
        _nav.Children.Clear();
        _nav.RowDefinitions.Clear();
        _nav.ColumnDefinitions.Clear();
        if (_navAncha)
        {
            _nav.ColumnDefinitions.Add(new ColumnDefinition(GridLength.Auto));
            _nav.ColumnDefinitions.Add(new ColumnDefinition(GridLength.Star));
            _nav.ColumnDefinitions.Add(new ColumnDefinition(GridLength.Auto));
            _nav.ColumnDefinitions.Add(new ColumnDefinition(GridLength.Auto));
            _nav.Add(_capAnterior, 0, 0);
            _nav.Add(_tira, 1, 0);
            _nav.Add(_capEntregar, 2, 0);
            _nav.Add(_capSiguiente, 3, 0);
        }
        else
        {
            _nav.RowDefinitions.Add(new RowDefinition(GridLength.Auto));
            _nav.RowDefinitions.Add(new RowDefinition(GridLength.Auto));
            _nav.ColumnDefinitions.Add(new ColumnDefinition(GridLength.Star));
            _nav.ColumnDefinitions.Add(new ColumnDefinition(GridLength.Auto));
            _nav.Add(_tira, 0, 0);
            _nav.Add(_capEntregar, 1, 0);
            _filaBotones.Add(_capAnterior, 0, 0);
            _filaBotones.Add(_capSiguiente, 2, 0);
            _nav.Add(_filaBotones, 0, 1);
            Grid.SetColumnSpan(_filaBotones, 2);
        }
    }

    private void Ir(int destino)
    {
        if (destino < 0 || destino >= _preguntas.Count || destino == _indice) return;
        try { _editor?.Vaciar(); } catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "actividad · al cambiar de pregunta", ex); }
        _confirmando = false;
        _indice = destino;
        MostrarPregunta();
    }

    private void ActualizarNavegacion()
    {
        var hay = _actividad is not null && _preguntas.Count > 0 && !_entregado && !_entregaPedida && !_confirmando;
        _nav.IsVisible = hay;
        if (!hay) return;
        var ultima = _indice >= _preguntas.Count - 1;
        Ds.Habilitar(_btnAnterior, _indice > 0, 0.45);
        _capSiguiente.IsVisible = !ultima;
        // Un solo Primary por pantalla: «Siguiente» mientras quedan preguntas y «Entregar» cuando ya no hay más.
        _capEntregar.IsVisible = PuedeEntregar;
        if (PuedeEntregar) Ds.PintarRelieve(_btnEntregar, ultima ? Ds.Rojo : Colors.White, ultima ? Colors.White : Ds.Tinta);
    }

    private void PintarChips(bool centrar = false)
    {
        for (var i = 0; i < _chips.Count && i < _preguntas.Count; i++)
        {
            var c = _chips[i];
            var id = _preguntas[i].PreguntaRef;
            var actual = i == _indice && !_entregado && !_entregaPedida;
            var respondida = _respondidas.Contains(id);
            var marcada = _marcadas.Contains(id);
            c.Caja.BackgroundColor = actual ? Ds.Tinta : respondida ? Ds.InfoSuave : Colors.White;
            c.Caja.Stroke = actual ? VistasActividad.BrochaTinta : respondida ? BrochaInfo : VistasActividad.BrochaReposo;
            c.Numero.TextColor = actual ? Colors.White : Ds.Tinta;
            c.Marca.TextColor = actual ? Colors.White : Ds.Tinta;
            c.Marca.Text = (respondida ? "✓" : string.Empty) + (marcada ? "★" : string.Empty);
            SemanticProperties.SetDescription(c.Caja, $"Pregunta {i + 1}{(respondida ? ", contestada" : ", sin contestar")}{(marcada ? ", marcada para revisar" : string.Empty)}{(actual ? ", la que estás viendo" : string.Empty)}");
        }
        if (centrar && _indice >= 0 && _indice < _chips.Count) CentrarChipActual();
    }

    private void CentrarChipActual()
    {
        if (_tira.Handler is null) return;
        var caja = _chips[_indice].Caja;
        Dispatcher.Dispatch(async () =>
        {
            try { await _tira.ScrollToAsync(caja, ScrollToPosition.Center, false); } catch { /* sin diseño todavía: la tira queda donde está */ }
        });
    }
}

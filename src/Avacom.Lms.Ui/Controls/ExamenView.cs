using System.Text.Json;
using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// El control con el que el alumno PRESENTA un examen (MOD-010 · PAN-121, PAN-122). Pinta lo que le dice una <see cref="SesionDeExamen"/> —que es quien guarda las
/// respuestas, da señal al nodo, sigue el bloqueo y entrega— y no sabe nada de HTTP, de la cola ni del kiosco. Usa los MISMOS editores de pregunta que la actividad del
/// aula y la práctica de estudio (opción múltiple, verdadero o falso, completar, relacionar, ordenar y abierta), pero con las reglas de un examen:
///
///  · Una pregunta a la vez, tira de números tocables con marca de contestada, «Anterior» / «Siguiente» y «Entregar» siempre a la mano. Si el profesor apagó el retroceso
///    (<c>allowBackNavigation</c>) las anteriores se ven pero no se tocan.
///  · Cada respuesta se guarda PRIMERO en la tableta (cola cifrada) y sólo después se intenta enviar; el alumno ve «Guardado» o «Guardado en tu tableta», nunca un error de red.
///  · Sin corrección ni nota: el alumno no sabe si acertó (DEC-032). La entrega nunca dice «calificado».
///  · El cronómetro es el del nodo: aquí sólo se pinta. <b>Nunca cambia de color ni suena</b>, tampoco en el último minuto (Guion, paso 5).
///  · Suspendido (PAN-122): una tarjeta serena dice que todo está guardado y que se espera al profesor. El bloqueo no se suelta.
///  · Un bloqueo incompleto se muestra siempre (ámbar, con texto) y ningún mensaje de red lo pisa (kiosk.md §5.2).
///
/// Todos los métodos públicos se pueden llamar desde cualquier hilo; los eventos salen en el hilo de la interfaz. El único temporizador (el reloj) se detiene al
/// quitar el control del árbol visual.
/// </summary>
public sealed class ExamenView : ContentView
{
    static ExamenView() => NeumoChrome.Registrar();

    private static readonly Brush BrochaInfo = new SolidColorBrush(Ds.Info);

    private sealed record Chip(Border Caja, Label Numero, Label Marca);

    // ------------------------------------------------------------------------------ estado
    private SesionDeExamen? _sesion;
    private IReadOnlyList<PreguntaAula> _preguntas = [];
    private int _indice;
    private EditorPregunta? _editor;
    private bool _confirmando;
    private bool _terminadoAvisado;
    private string? _aviso;
    private string? _claveCuerpo;
    private readonly HashSet<string> _marcadas = [];
    private double _area = 56;
    private double _escala = 1;
    private bool _navAncha;
    private int _centrado = -1;
    private IDispatcherTimer? _reloj;

    // --------------------------------------------------------------------------- elementos
    private readonly Grid _raiz;
    private readonly Label _titulo;
    private readonly Label _posicion;
    private readonly Label _contestadas;
    private readonly Label _textoReloj;
    private readonly Label _detalleReloj;
    private readonly Border _barra;
    private readonly Grid _barraRejilla;
    private readonly Border _pildoraGuardado;
    private readonly Label _textoGuardado;
    private readonly VerticalStackLayout _banners = new() { Spacing = 8 };
    private readonly ScrollView _scroll;
    private readonly Grid _nav = new() { ColumnSpacing = 12, RowSpacing = 10 };
    private readonly Grid _filaBotones = new() { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
    private readonly List<Chip> _chips = [];
    private ScrollView _tira = null!;
    /// <summary>En una ventana de escritorio los estados (pausa, confirmar entrega, entregando…) son una tarjeta anclada a los tercios del encuadre completo.</summary>
    private readonly ContentView _estado = new() { IsVisible = false };
    private const double AnchoDeEscritorio = 1500;
    private bool _escritorio, _cuerpoEsEstado;
    private HorizontalStackLayout _tiraPila = null!;
    private Button _btnAnterior = null!, _btnSiguiente = null!, _btnEntregar = null!;
    private View _capAnterior = null!, _capSiguiente = null!, _capEntregar = null!;

    public ExamenView()
    {
        _titulo = Ds.Titulo(string.Empty, 22);
        _titulo.MaxLines = 2;
        _titulo.LineBreakMode = LineBreakMode.TailTruncation;
        _titulo.AutomationId = "exa-titulo";

        _textoGuardado = new Label { FontFamily = Ds.FuenteMedia, FontSize = 15, TextColor = Ds.Tinta, VerticalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.NoWrap };
        _pildoraGuardado = new Border
        {
            StrokeThickness = 0, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioPildora }, Padding = new Thickness(14, 8),
            Content = _textoGuardado, VerticalOptions = LayoutOptions.Center, AutomationId = "exa-guardado",
        };

        // El reloj del nodo: neutro siempre. Sin límite dice «Sin límite de tiempo».
        _textoReloj = new Label { FontFamily = Ds.FuenteMedia, FontSize = 24, TextColor = Ds.Tinta, VerticalTextAlignment = TextAlignment.Center, HorizontalTextAlignment = TextAlignment.End, AutomationId = "exa-reloj" };
        _detalleReloj = Ds.Secundario(string.Empty, 13);
        _detalleReloj.HorizontalTextAlignment = TextAlignment.End;
        _detalleReloj.AutomationId = "exa-reloj-detalle";
        var reloj = new VerticalStackLayout { Spacing = 0, VerticalOptions = LayoutOptions.Center, Children = { _textoReloj, _detalleReloj } };

        var fila0 = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 14 };
        fila0.Add(_titulo, 0, 0);
        fila0.Add(_pildoraGuardado, 1, 0);
        fila0.Add(reloj, 2, 0);

        _posicion = new Label { FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, VerticalTextAlignment = TextAlignment.Center, AutomationId = "exa-posicion" };
        _contestadas = Ds.Secundario(string.Empty, 15);
        _contestadas.VerticalTextAlignment = TextAlignment.Center;
        _contestadas.AutomationId = "exa-contestadas";
        _barraRejilla = new Grid { ColumnDefinitions = [new ColumnDefinition(new GridLength(0, GridUnitType.Star)), new ColumnDefinition(GridLength.Star)], HeightRequest = 10 };
        _barraRejilla.Add(new BoxView { Color = Ds.Info, CornerRadius = 5 }, 0, 0);
        _barra = new Border
        {
            BackgroundColor = Color.FromArgb("#E4E4E7"), StrokeThickness = 0, HeightRequest = 10, VerticalOptions = LayoutOptions.Center,
            StrokeShape = new RoundRectangle { CornerRadius = 5 }, Content = _barraRejilla, AutomationId = "exa-progreso",
        };
        var fila1 = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 14 };
        fila1.Add(_posicion, 0, 0);
        fila1.Add(_barra, 1, 0);
        fila1.Add(_contestadas, 2, 0);

        var cabecera = Ds.Tarjeta(new VerticalStackLayout { Spacing = 10, Children = { fila0, fila1, _banners } }, Ds.RadioTarjeta, new Thickness(18, 14));
        _scroll = new ScrollView { Orientation = ScrollOrientation.Vertical };

        _raiz = new Grid { RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Star), new RowDefinition(GridLength.Auto)], RowSpacing = 12 };
        _raiz.Add(cabecera, 0, 0);
        _raiz.Add(_scroll, 0, 1);
        _raiz.Add(_nav, 0, 2);
        // El margen de la pantalla es de la raíz; la capa de estado ocupa el encuadre completo para que los tercios sean los de la ventana.
        _raiz.Margin = new Thickness(16, 12);
        Content = new Grid { Children = { _raiz, _estado } };

        Loaded += (_, _) => AjustarReloj();
        Unloaded += (_, _) =>
        {
            Vaciar("al salir");
            DetenerReloj();
        };
        SizeChanged += (_, _) =>
        {
            var escritorio = Width >= AnchoDeEscritorio;
            if (escritorio != _escritorio)
            {
                _escritorio = escritorio;
                if (_cuerpoEsEstado && _sesion is not null) MostrarCuerpo(_sesion);      // la tarjeta de estado se recoloca; una pregunta en curso no se toca
            }
            var ancha = Width >= 900;
            if (ancha == _navAncha) return;
            _navAncha = ancha;
            if (_capAnterior is not null) AcomodarNavegacion();
        };
        ConstruirNavegacion();
        PonerCuerpo(Tarjeta("Aquí aparecerá tu examen.", null, "exa-vacio"), estado: true);
    }

    // ===================================================================================== API pública

    /// <summary>El alumno terminó: el nodo confirmó la entrega (o el nodo ya había entregado). La pantalla de entrega la abre quien aloja el control.</summary>
    public event Action? EntregaTerminada;

    /// <summary>El examen ya no es de esta tableta (continúa en otra, o un administrador la liberó) y el alumno tocó «Volver».</summary>
    public event Action? SalidaPedida;

    /// <summary>Convierte la ruta de un medio de una pregunta en URL absoluta (la del nodo).</summary>
    public Func<string, Uri>? ResolverUrl { get; set; }

    /// <summary>Alto y ancho mínimo de lo que se toca, en puntos. Nunca baja de 44.</summary>
    public double AreaTactil
    {
        get => _area;
        set
        {
            if (Math.Abs(_area - value) < 0.01) return;
            _area = value;
            if (_sesion is not null) EnHiloUi(Reconstruir);
        }
    }

    /// <summary>Conecta el control a la sesión del examen. Los cambios de la sesión repintan solos.</summary>
    public void Cargar(SesionDeExamen sesion)
    {
        ArgumentNullException.ThrowIfNull(sesion);
        EnHiloUi(() =>
        {
            if (_sesion is not null) _sesion.Cambio -= AlCambiar;
            Vaciar("al cargar otra sesión");
            _sesion = sesion;
            _sesion.Cambio += AlCambiar;
            _preguntas = [];
            _indice = 0;
            _confirmando = false;
            _terminadoAvisado = false;
            _aviso = null;
            _claveCuerpo = null;
            _marcadas.Clear();
            Refrescar();
        });
    }

    /// <summary>Quita la suscripción a la sesión (al irse de la pantalla).</summary>
    public void Soltar()
    {
        EnHiloUi(() =>
        {
            Vaciar("al soltar");
            if (_sesion is not null) _sesion.Cambio -= AlCambiar;
            _sesion = null;
            DetenerReloj();
        });
    }

    /// <summary>Vuelve a leer la sesión y repinta lo que cambió. Se puede llamar desde cualquier hilo y tantas veces como se quiera.</summary>
    public void Refrescar() => EnHiloUi(RefrescarEnUi);

    private void AlCambiar() => Refrescar();

    private void EnHiloUi(Action accion)
    {
        var d = Dispatcher;
        if (d is not null && d.IsDispatchRequired) d.Dispatch(accion);
        else accion();
    }

    // ===================================================================================== repintado

    private void RefrescarEnUi()
    {
        var s = _sesion;
        if (s is null) return;
        try
        {
            if (_preguntas.Count == 0 && s.Preguntas is { Preguntas.Count: > 0 } p)
            {
                _preguntas = p.Preguntas;
                var actual = s.PreguntaActual is { Length: > 0 } r ? _preguntas.ToList().FindIndex(x => x.PreguntaRef == r) : -1;
                var primera = _preguntas.ToList().FindIndex(x => !s.Respondida(x.PreguntaRef));
                _indice = actual >= 0 ? actual : primera >= 0 ? primera : 0;
                _titulo.Text = string.IsNullOrWhiteSpace(p.Titulo) ? "Examen" : p.Titulo;
                ConstruirNavegacion();
                _claveCuerpo = null;
            }
            PintarBanners(s);
            PintarCabecera(s);
            var clave = $"{s.Fase}|{_indice}|{_confirmando}|{_aviso}|{_preguntas.Count}";
            if (clave != _claveCuerpo)
            {
                _claveCuerpo = clave;
                MostrarCuerpo(s);
            }
            PintarChips(s);
            ActualizarNavegacion(s);
            AjustarReloj();
            if (s.Fase == FaseDeExamen.Terminado && !_terminadoAvisado)
            {
                _terminadoAvisado = true;
                EntregaTerminada?.Invoke();
            }
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "examen · repintar", ex);
        }
    }

    private bool Editable(SesionDeExamen s) => s.Fase == FaseDeExamen.EnCurso;

    private void Reconstruir()
    {
        Vaciar("al redibujar");
        ConstruirNavegacion();
        _claveCuerpo = null;
        RefrescarEnUi();
    }

    private void Vaciar(string cuando)
    {
        try { _editor?.Vaciar(); }
        catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, $"examen · {cuando}", ex); }
    }

    // ---- el cuerpo

    private void MostrarCuerpo(SesionDeExamen s)
    {
        Vaciar("al cambiar");
        _editor = null;
        switch (s.Fase)
        {
            case FaseDeExamen.Suspendido:
                PonerCuerpo(TarjetaSuspendido(s), estado: true);
                return;
            case FaseDeExamen.EnOtraTableta:
                PonerCuerpo(TarjetaDeSalida("Este examen continúa en otra tableta.", "Puedes cerrar esta pantalla: lo que respondiste está guardado.", "exa-otra-tableta"), estado: true);
                return;
            case FaseDeExamen.Liberada:
                PonerCuerpo(TarjetaDeSalida("Esta tableta se liberó del examen.", "Habla con tu profesor para continuar.", "exa-liberada"), estado: true);
                return;
            case FaseDeExamen.Entregando:
                PonerCuerpo(TarjetaEntregando(s), estado: true);
                return;
            case FaseDeExamen.Terminado:
                PonerCuerpo(Tarjeta("Entregado.", "Un momento, abriendo la confirmación…", "exa-terminado"), estado: true);
                return;
        }
        if (_preguntas.Count == 0)
        {
            PonerCuerpo(Tarjeta("Estamos preparando tu examen.", "Un momento…", "exa-cargando"), estado: true);
            return;
        }
        if (_confirmando) PonerCuerpo(TarjetaConfirmar(s), estado: true);
        else PintarPregunta(s);
    }

    private void PonerCuerpo(View contenido, bool estado = false)
    {
        _cuerpoEsEstado = estado;
        if (estado && _escritorio)
        {
            // Regla de tercios del encuadre completo: la tarjeta ocupa el tercio central en X y va de 1/6 a 5/6 en Y (Grid *,*,* / *,4*,*, celda central con Fill).
            if (contenido is Border tarjeta)
            {
                tarjeta.HorizontalOptions = LayoutOptions.Fill;
                tarjeta.VerticalOptions = LayoutOptions.Fill;
                if (tarjeta.Content is View interior) interior.VerticalOptions = LayoutOptions.Center;
            }
            var rejilla = new Grid
            {
                ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)],
                RowDefinitions = [new RowDefinition(GridLength.Star), new RowDefinition(new GridLength(4, GridUnitType.Star)), new RowDefinition(GridLength.Star)],
            };
            rejilla.Add(contenido, 1, 1);
            _scroll.Content = null;
            _scroll.IsVisible = false;
            _estado.Content = rejilla;
            _estado.IsVisible = true;
            return;
        }
        _estado.IsVisible = false;
        _estado.Content = null;
        _scroll.IsVisible = true;
        // El margen deja sitio a la sombra de la tarjeta, que el ScrollView recortaría.
        _scroll.Content = new VerticalStackLayout { Padding = new Thickness(4, 4, 4, 20), Children = { contenido } };
        if (_scroll.Handler is not null)
            Dispatcher.Dispatch(async () =>
            {
                try { await _scroll.ScrollToAsync(0, 0, false); } catch { /* sin diseño todavía: queda arriba */ }
            });
    }

    private void PintarPregunta(SesionDeExamen s)
    {
        var p = _preguntas[Math.Clamp(_indice, 0, _preguntas.Count - 1)];
        var cx = new ContextoEditor
        {
            AreaTactil = _area, Escala = _escala, ResolverUrl = ResolverUrl, Editable = Editable(s), Dispatcher = Dispatcher,
            Confirmar = respuesta => GuardarRespuesta(p.PreguntaRef, respuesta),
        };
        _editor = EditorPregunta.Crear(p, cx);
        if (s.RespuestaDe(p.PreguntaRef) is { } previa)
        {
            try { _editor.Aplicar(previa); }
            catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, $"examen · pregunta {p.PreguntaRef} · repintar lo respondido", ex); }
        }
        s.IrA(p.PreguntaRef);
        PonerCuerpo(TarjetaPregunta(s, p, cx, _editor));
    }

    private View TarjetaPregunta(SesionDeExamen s, PreguntaAula p, ContextoEditor cx, EditorPregunta editor)
    {
        var pila = new VerticalStackLayout { Spacing = 18 };
        if (_indice == 0 && s.Preguntas is { } datos && !string.IsNullOrWhiteSpace(datos.Instrucciones))
            pila.Add(Ds.ConTramos(datos.InstruccionesTramos, datos.Instrucciones, 17 * _escala, Ds.TintaSuave));
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
                var tipo = m.Componente switch { "video" => "Video", "audio" => "Audio", "pdf" => "Documento", "imagen" => "Imagen", _ => "Material" };
                pila.Add(Ds.Pildora(string.IsNullOrWhiteSpace(rotulo) ? tipo : $"{tipo} · {rotulo}", Ds.InfoSuave, Ds.Tinta, 15 * _escala));
            }
        }
        pila.Add(editor.Vista);
        if (!string.IsNullOrWhiteSpace(_aviso)) pila.Add(Ds.Secundario(_aviso!, 15 * _escala));
        pila.Add(BotonMarcar(p));
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(24, 22));
    }

    /// <summary>«Marcar para revisar»: una ayuda del alumno. No cambia lo que se guarda ni lo que se envía.</summary>
    private View BotonMarcar(PreguntaAula p)
    {
        string Texto() => _marcadas.Contains(p.PreguntaRef) ? "★  Marcada para revisar" : "☆  Marcar para revisar";
        var boton = Ds.Boton(Texto(), Ds.Rango.Secondary, null, Math.Max(44, _area * 0.85));
        boton.HorizontalOptions = LayoutOptions.End;
        boton.AutomationId = "exa-marcar";
        boton.Clicked += (_, _) =>
        {
            if (!_marcadas.Remove(p.PreguntaRef)) _marcadas.Add(p.PreguntaRef);
            boton.Text = Texto();
            if (_sesion is not null) PintarChips(_sesion);
        };
        return Ds.Capsula(boton);
    }

    private View Tarjeta(string principal, string? detalle, string id)
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

    // ---- PAN-122: esperando al profesor

    private View TarjetaSuspendido(SesionDeExamen s)
    {
        var pila = new VerticalStackLayout { Spacing = 14, HorizontalOptions = LayoutOptions.Center, AutomationId = "exa-suspendido" };
        var pausa = new Border
        {
            WidthRequest = 84, HeightRequest = 84, BackgroundColor = Ds.InfoSuave, StrokeThickness = 0, HorizontalOptions = LayoutOptions.Center,
            StrokeShape = new RoundRectangle { CornerRadius = 42 },
            Content = new Label { Text = "II", FontSize = 34, FontFamily = Ds.FuenteMedia, TextColor = Ds.Tinta, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
        };
        pila.Add(pausa);
        var titulo = Ds.Titulo("Tu examen está en pausa", 25 * _escala);
        titulo.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(titulo);
        var cuerpo = Ds.Cuerpo(s.Mensaje?.Texto ?? "Todo lo que respondiste está guardado y el tiempo está detenido. Avisa a tu profesor para continuar.", 19 * _escala);
        cuerpo.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(cuerpo);
        var nota = Ds.Secundario("No necesitas hacer nada más: cuando tu profesor te reactive, sigues justo donde ibas.", 16 * _escala);
        nota.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(nota);
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(28, 40));
    }

    private View TarjetaDeSalida(string principal, string detalle, string id)
    {
        var pila = new VerticalStackLayout { Spacing = 14, HorizontalOptions = LayoutOptions.Center, AutomationId = id };
        var titulo = Ds.Titulo(principal, 24 * _escala);
        titulo.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(titulo);
        var d = Ds.Secundario(detalle, 18 * _escala);
        d.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(d);
        var volver = Ds.Boton("Volver", Ds.Rango.Primary, (_, _) => SalidaPedida?.Invoke(), Math.Max(56, _area));
        volver.AutomationId = "exa-salir";
        pila.Add(Ds.Capsula(volver));
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(28, 36));
    }

    // ---- entrega (PAN-123)

    private View TarjetaConfirmar(SesionDeExamen s)
    {
        var faltan = new List<int>();
        for (var i = 0; i < _preguntas.Count; i++)
            if (!s.Respondida(_preguntas[i].PreguntaRef)) faltan.Add(i + 1);

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
        var pila = new VerticalStackLayout { Spacing = 14, AutomationId = "exa-confirmar" };
        var titulo = Ds.Titulo(principal, 24 * _escala);
        titulo.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(titulo);
        if (!string.IsNullOrWhiteSpace(secundaria))
        {
            var t = Ds.Secundario(secundaria, 17 * _escala);
            t.HorizontalTextAlignment = TextAlignment.Center;
            pila.Add(t);
        }
        if (!string.IsNullOrWhiteSpace(_aviso))
        {
            var aviso = Ds.Cuerpo(_aviso!, 17 * _escala);
            aviso.HorizontalTextAlignment = TextAlignment.Center;
            pila.Add(aviso);
        }
        var alto = Math.Max(56, _area);
        var volver = Ds.Boton("Volver", Ds.Rango.Secondary, (_, _) => VolverDeConfirmar(), alto);
        volver.AutomationId = "exa-volver";
        var confirmar = Ds.Boton(entregar, Ds.Rango.Primary, (_, _) => ConfirmarEntrega(), alto);
        confirmar.AutomationId = "exa-entregar-igual";
        var botones = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 14, Margin = new Thickness(0, 6, 0, 0) };
        botones.Add(Ds.Capsula(volver), 0, 0);
        botones.Add(Ds.Capsula(confirmar), 1, 0);
        pila.Add(botones);
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(28, 30));
    }

    private View TarjetaEntregando(SesionDeExamen s)
    {
        var pila = new VerticalStackLayout { Spacing = 10, HorizontalOptions = LayoutOptions.Center, AutomationId = "exa-entregando" };
        var titulo = Ds.Titulo(s.SinConexion || s.PendientesEnDispositivo > 0 ? "Tu entrega quedó guardada en esta tableta." : "Entregando…", 24 * _escala);
        titulo.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(titulo);
        var detalle = Ds.Secundario(s.SinConexion || s.PendientesEnDispositivo > 0
            ? "Se enviará en cuanto haya conexión con el aula. No cierres el examen."
            : "Un momento: estamos enviando tus respuestas a tu profesor.", 17 * _escala);
        detalle.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(detalle);
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(28, 40));
    }

    private void PedirEntrega()
    {
        if (_sesion is null || !Editable(_sesion)) return;
        Vaciar("antes de entregar");
        _confirmando = true;
        _aviso = null;
        _claveCuerpo = null;
        RefrescarEnUi();
    }

    private void VolverDeConfirmar()
    {
        _confirmando = false;
        _aviso = null;
        _claveCuerpo = null;
        RefrescarEnUi();
    }

    private async void ConfirmarEntrega()
    {
        var s = _sesion;
        if (s is null) return;
        try
        {
            var salida = await s.EntregarAsync(confirmar: true);
            switch (salida.Resultado)
            {
                case ResultadoDeEntrega.Entregado:
                    return;                                   // la sesión pasa a Terminado y el repintado avisa
                case ResultadoDeEntrega.GuardadaSinRed:
                    _confirmando = false;
                    _aviso = salida.Mensaje;
                    break;
                case ResultadoDeEntrega.Suspendido:
                    _confirmando = false;
                    _aviso = null;
                    break;
                default:
                    _aviso = salida.Mensaje ?? "No pudimos entregar ahora. Tus respuestas siguen aquí; inténtalo de nuevo.";
                    break;
            }
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "examen · entregar", ex);
            _aviso = "No pudimos entregar ahora. Tus respuestas siguen aquí; inténtalo de nuevo.";
        }
        _claveCuerpo = null;
        Refrescar();
    }

    // ====================================================================================== guardado

    /// <summary>
    /// El alumno confirmó una respuesta: se escribe en la cola del dispositivo ANTES de intentar enviarla. Si el disco no deja escribir se lo dice en voz baja, sin
    /// códigos, y la pregunta no cuenta como respondida (la sesión no la marca) para que no crea que está guardada.
    /// </summary>
    private void GuardarRespuesta(string preguntaRef, JsonElement respuesta)
    {
        var s = _sesion;
        if (s is null || !Editable(s)) return;
        try
        {
            s.Responder(preguntaRef, respuesta);
            _ = EnviarSinEsperarAsync(s);
            _aviso = null;
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "examen · guardar respuesta en el dispositivo", ex);
            _aviso = "Tu tableta no pudo guardar esta respuesta. Inténtalo otra vez o avisa a tu profesor.";
            _claveCuerpo = null;
        }
        Refrescar();
    }

    private static async Task EnviarSinEsperarAsync(SesionDeExamen s)
    {
        try { await s.VaciarAsync(); }
        catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "examen · enviar", ex); }   // la cola conserva todo: se reintenta sola
    }

    // ===================================================================================== cabecera

    private void PintarCabecera(SesionDeExamen s)
    {
        var total = _preguntas.Count;
        var respondidas = _preguntas.Count(p => s.Respondida(p.PreguntaRef));
        _posicion.Text = total == 0 ? string.Empty : $"Pregunta {Math.Clamp(_indice + 1, 1, total)} de {total}";
        _contestadas.Text = total == 0 ? string.Empty : $"{respondidas} de {total} contestadas";
        _barraRejilla.ColumnDefinitions[0].Width = new GridLength(respondidas, GridUnitType.Star);
        _barraRejilla.ColumnDefinitions[1].Width = new GridLength(Math.Max(0, total - respondidas), GridUnitType.Star);
        _barra.IsVisible = total > 0;
        SemanticProperties.SetDescription(_barra, $"{respondidas} de {total} preguntas contestadas");

        // Guardado (CMP-002): nunca un error. Con algo esperando en la tableta o sin conexión, «Guardado en tu tableta».
        var enDispositivo = s.Guardado == EstadoDeGuardado.GuardadoEnDispositivo || s.SinConexion;
        _textoGuardado.Text = enDispositivo ? "●  Guardado en tu tableta" : "✓  Guardado";
        _pildoraGuardado.BackgroundColor = Ds.InfoSuave;
        SemanticProperties.SetDescription(_pildoraGuardado, enDispositivo ? "Guardado en tu tableta" : "Guardado");
        PintarReloj();
    }

    /// <summary>El cronómetro del nodo, sólo para mirar: neutro siempre (Guion, paso 5: no se pone rojo, no parpadea, no suena).</summary>
    private void PintarReloj()
    {
        var s = _sesion;
        if (s is null) return;
        var restante = s.RestanteMs;
        if (restante is null)
        {
            _textoReloj.Text = "Sin límite";
            _detalleReloj.Text = "de tiempo";
            return;
        }
        var t = TimeSpan.FromMilliseconds(restante.Value);
        _textoReloj.Text = t.TotalHours >= 1 ? $"{(int)t.TotalHours}:{t.Minutes:00}:{t.Seconds:00}" : $"{t.Minutes:00}:{t.Seconds:00}";
        _detalleReloj.Text = s.Fase == FaseDeExamen.Suspendido ? "tiempo detenido" : "te quedan";
    }

    /// <summary>
    /// Los avisos que no se pisan entre sí: el de seguridad (bloqueo parcial o fallido) vive mientras dure el bloqueo incompleto; el de conexión sólo mientras no hay
    /// red. Ámbar y azul suaves, con texto: nunca rojo y nunca sólo color (UXR-011).
    /// </summary>
    private void PintarBanners(SesionDeExamen s)
    {
        _banners.Clear();
        if (!string.IsNullOrWhiteSpace(s.AvisoDeSeguridad))
        {
            var seguridad = Ds.Alerta_("Aviso sobre el bloqueo de esta tableta", s.AvisoDeSeguridad, Ds.AlertaSuave, Ds.Tinta);
            seguridad.AutomationId = "exa-seguridad";
            _banners.Add(seguridad);
        }
        if (s.SinConexion && s.Fase is FaseDeExamen.EnCurso or FaseDeExamen.Suspendido or FaseDeExamen.Entregando)
        {
            var red = Ds.Alerta_("Sin conexión con el aula", "Tus respuestas se guardan en esta tableta y se enviarán solas.", Ds.InfoSuave, Ds.Tinta);
            red.AutomationId = "exa-sinconexion";
            _banners.Add(red);
        }
        _banners.IsVisible = _banners.Count > 0;
    }

    // ---- el reloj de 1 s (sólo repinta el cronómetro)

    private void AjustarReloj()
    {
        var hace = IsLoaded && _sesion is { Fase: FaseDeExamen.EnCurso or FaseDeExamen.Entregando or FaseDeExamen.Suspendido };
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
                _reloj.Tick += (_, _) => PintarReloj();
            }
            if (!_reloj.IsRunning) _reloj.Start();
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "examen · reloj", ex);
        }
    }

    private void DetenerReloj()
    {
        try { _reloj?.Stop(); } catch { /* ya está parado */ }
    }

    // ================================================================================== navegación

    private double Alto => Math.Max(44, _area);

    private bool Retroceso => _sesion?.Preguntas?.NavegacionAtras ?? true;

    private void ConstruirNavegacion()
    {
        var alto = Alto;
        _btnAnterior = Ds.Boton("◀  Anterior", Ds.Rango.Secondary, (_, _) => Ir(_indice - 1), alto);
        _btnAnterior.AutomationId = "exa-anterior";
        _capAnterior = Ds.Capsula(_btnAnterior);
        _btnSiguiente = Ds.Boton("Siguiente  ▶", Ds.Rango.Primary, (_, _) => Ir(_indice + 1), alto);
        _btnSiguiente.AutomationId = "exa-siguiente";
        _capSiguiente = Ds.Capsula(_btnSiguiente);
        _btnEntregar = Ds.Boton("Entregar", Ds.Rango.Secondary, (_, _) => PedirEntrega(), alto);
        _btnEntregar.AutomationId = "exa-entregar";
        _capEntregar = Ds.Capsula(_btnEntregar);

        _tiraPila = new HorizontalStackLayout { Spacing = 8, Padding = new Thickness(4, 8), VerticalOptions = LayoutOptions.Center };
        _tira = new ScrollView
        {
            Orientation = ScrollOrientation.Horizontal, HorizontalScrollBarVisibility = ScrollBarVisibility.Never, Content = _tiraPila,
            VerticalOptions = LayoutOptions.Center,
        };
        _chips.Clear();
        _centrado = -1;
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
            Text = (i + 1).ToString(), FontFamily = Ds.FuenteMedia, FontSize = (lado >= 52 ? 19 : 16) * _escala, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center,
        };
        var marca = new Label { FontFamily = Ds.FuenteMedia, FontSize = 12, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Start };
        var rejilla = new Grid { RowDefinitions = [new RowDefinition(GridLength.Star), new RowDefinition(new GridLength(16))], RowSpacing = 0, Padding = new Thickness(0, 4, 0, 0) };
        rejilla.Add(numero, 0, 0);
        rejilla.Add(marca, 0, 1);
        var caja = new Border
        {
            WidthRequest = lado, HeightRequest = lado, StrokeThickness = 1.5, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioControl },
            Content = rejilla, AutomationId = $"exa-pregunta-{i + 1}",
        };
        var indice = i;
        var toque = new TapGestureRecognizer();
        toque.Tapped += (_, _) => Ir(indice);
        caja.GestureRecognizers.Add(toque);
        return new Chip(caja, numero, marca);
    }

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
        var s = _sesion;
        if (s is null || s.Fase != FaseDeExamen.EnCurso || destino < 0 || destino >= _preguntas.Count || destino == _indice) return;
        if (destino < _indice && !Retroceso) return;                       // el profesor apagó el retroceso (allowBackNavigation)
        Vaciar("al cambiar de pregunta");
        _confirmando = false;
        _aviso = null;
        _indice = destino;
        _claveCuerpo = null;
        RefrescarEnUi();
    }

    private void ActualizarNavegacion(SesionDeExamen s)
    {
        var hay = _preguntas.Count > 0 && s.Fase == FaseDeExamen.EnCurso && !_confirmando;
        _nav.IsVisible = hay;
        if (!hay) return;
        var ultima = _indice >= _preguntas.Count - 1;
        _capAnterior.IsVisible = Retroceso;
        Ds.Habilitar(_btnAnterior, _indice > 0, 0.45);
        _capSiguiente.IsVisible = !ultima;
        // Un solo Primary por pantalla: «Siguiente» mientras quedan preguntas y «Entregar» cuando ya no hay más.
        _capEntregar.IsVisible = true;
        Ds.PintarRelieve(_btnEntregar, ultima ? Ds.Rojo : Colors.White, ultima ? Colors.White : Ds.Tinta);
    }

    private void PintarChips(SesionDeExamen s)
    {
        for (var i = 0; i < _chips.Count && i < _preguntas.Count; i++)
        {
            var c = _chips[i];
            var id = _preguntas[i].PreguntaRef;
            var actual = i == _indice && s.Fase == FaseDeExamen.EnCurso;
            var respondida = s.Respondida(id);
            var marcada = _marcadas.Contains(id);
            var bloqueada = !Retroceso && i < _indice;
            c.Caja.BackgroundColor = actual ? Ds.Tinta : respondida ? Ds.InfoSuave : Colors.White;
            c.Caja.Stroke = actual ? VistasActividad.BrochaTinta : respondida ? BrochaInfo : VistasActividad.BrochaReposo;
            c.Caja.Opacity = bloqueada ? 0.5 : 1;
            c.Numero.TextColor = actual ? Colors.White : Ds.Tinta;
            c.Marca.TextColor = actual ? Colors.White : Ds.Tinta;
            c.Marca.Text = (respondida ? "✓" : string.Empty) + (marcada ? "★" : string.Empty);
            SemanticProperties.SetDescription(c.Caja, $"Pregunta {i + 1}{(respondida ? ", contestada" : ", sin contestar")}{(marcada ? ", marcada para revisar" : string.Empty)}{(actual ? ", la que estás viendo" : string.Empty)}");
        }
        if (_indice >= 0 && _indice < _chips.Count && _tira.Handler is not null && _centrado != _indice)
        {
            _centrado = _indice;        // sólo al cambiar de pregunta: centrar en cada repintado pelea con el alumno que desliza la tira a mano
            var caja = _chips[_indice].Caja;
            Dispatcher.Dispatch(async () =>
            {
                try { await _tira.ScrollToAsync(caja, ScrollToPosition.Center, false); } catch { /* sin diseño todavía: la tira queda donde está */ }
            });
        }
    }
}

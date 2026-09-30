using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Controls;

/// <summary>El veredicto de una respuesta de práctica, ya traducido para pintarlo. Sin claves. <c>Pendiente</c>: todavía no se sabe (sin el aula).</summary>
public sealed record VeredictoPractica(bool? Correcta, bool Pendiente, IReadOnlyList<string> Retroalimentacion)
{
    public bool Conocido => Correcta is not null && !Pendiente;
}

/// <summary>Una pregunta en «Revisar respuestas».</summary>
public sealed record RevisionPractica(string PreguntaRef, int Numero, string? Enunciado, bool? Correcta, IReadOnlyList<string> Retroalimentacion);

/// <summary>Lo que se le dice al alumno al terminar: «7 de 8 correctas · ¡Muy bien!». Nunca «nota» ni «evaluación».</summary>
public sealed record ResultadoDePractica(int Correctas, int Total, string Mensaje, int SinCalificar, IReadOnlyList<RevisionPractica> Revision)
{
    /// <summary>Todo se guardó pero el aula aún no calificó nada (se trabajó sin conexión).</summary>
    public bool PendienteDeCalificar => SinCalificar > 0 && Correctas == 0 && Total > 0;
}

/// <summary>
/// El control con el que el alumno PRACTICA una actividad en el modo de estudio (MOD-008 · FUN-083). Es hermano de
/// <see cref="ActividadResponderView"/> y usa los mismos editores de pregunta (opción múltiple, verdadero o falso, completar, relacionar,
/// ordenar y abierta), pero con lo contrario de su regla más importante: aquí SÍ hay corrección inmediata, porque es práctica, no
/// evaluación (BR-055). El alumno elige, toca «Comprobar» y en menos de dos segundos (NFR-012) ve si acertó y por qué.
///
/// Reglas que hace cumplir:
///  · Nunca se llama examen, evaluación ni nota; «Puedes intentarlo nuevamente» siempre está a la vista (spec §14).
///  · Un error de la red no es un error del alumno (UXR-004): si no se puede calificar ahora, la respuesta se guarda y se dice «Guardada
///    en tu tableta; verás si acertaste cuando vuelvas al aula». Jamás hay un estado de error.
///  · Acertar y fallar se ven con icono, texto y color (UXR-011); fallar es ámbar y amable, nunca rojo alarmista.
///  · Comprobar y terminar los pone quien aloja el control (<see cref="Comprobar"/>, <see cref="Terminar"/>): el control no sabe de HTTP.
/// </summary>
public sealed class PracticaEstudioView : ContentView
{
    static PracticaEstudioView() => NeumoChrome.Registrar();

    private static readonly Color VerdeSuave = Color.FromArgb("#E5F6ED"), VerdeTinta = Color.FromArgb("#017A48");
    private static readonly Color AmbarSuave = Color.FromArgb("#FFF7D6"), AmbarTinta = Color.FromArgb("#806600");
    private static readonly Color AzulSuave = Color.FromArgb("#E5F5FB"), AzulTinta = Color.FromArgb("#02739E");
    private static readonly Color TintaEstudio = Color.FromArgb("#1D1D1F"), GrisTexto = Color.FromArgb("#6E6E73");

    // ------------------------------------------------------------------------------------ estado
    private ObjetoAula? _actividad;
    private IReadOnlyList<PreguntaAula> _preguntas = [];
    private int _indice;
    private int _numero = 1;
    private readonly Dictionary<string, JsonElement> _respuestas = [];
    private readonly Dictionary<string, VeredictoPractica> _veredictos = [];
    private EditorPregunta? _editor;
    private bool _comprobando;
    private bool _revision;
    private bool _confirmandoFin;
    private ResultadoDePractica? _resultado;
    private EstadoGuardado _guardado = EstadoGuardado.Guardado;

    // ------------------------------------------------------------------------------- elementos
    private readonly Grid _raiz;
    private readonly Label _titulo;
    private readonly Label _posicion;
    private readonly Label _contestadas;
    private readonly Grid _barraRejilla;
    private readonly Border _pildoraGuardado;
    private readonly Label _textoGuardado;
    private readonly ScrollView _scroll;
    private readonly Grid _nav = new() { ColumnSpacing = 12, RowSpacing = 10 };
    private readonly HorizontalStackLayout _puntos = new() { Spacing = 8, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center };
    private Button _btnAnterior = null!, _btnPrincipal = null!, _btnTerminar = null!;

    public PracticaEstudioView()
    {
        _titulo = Ds.Titulo(string.Empty, 22);
        _titulo.MaxLines = 2;
        _titulo.LineBreakMode = LineBreakMode.TailTruncation;
        _titulo.AutomationId = "practica-titulo";

        _textoGuardado = new Label { FontFamily = Ds.FuenteMedia, FontSize = 14, TextColor = Ds.Tinta, VerticalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.NoWrap };
        _pildoraGuardado = new Border
        {
            StrokeThickness = 0, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioPildora }, Padding = new Thickness(14, 8),
            Content = _textoGuardado, VerticalOptions = LayoutOptions.Center, AutomationId = "practica-guardado",
        };

        var etiquetaPractica = Ds.Pildora("Práctica de estudio · puedes intentarlo nuevamente", AzulSuave, AzulTinta, 13);
        etiquetaPractica.HorizontalOptions = LayoutOptions.Start;

        var titulos = new VerticalStackLayout { Spacing = 6, VerticalOptions = Microsoft.Maui.Controls.LayoutOptions.Center, Children = { _titulo, etiquetaPractica } };
        var fila0 = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
        fila0.Add(titulos, 0, 0);
        fila0.Add(_pildoraGuardado, 1, 0);

        _posicion = new Label { FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta, VerticalTextAlignment = TextAlignment.Center, AutomationId = "practica-posicion" };
        _contestadas = Ds.Secundario(string.Empty, 14);
        _contestadas.VerticalTextAlignment = TextAlignment.Center;
        _barraRejilla = new Grid { ColumnDefinitions = [new ColumnDefinition(new GridLength(0.0001, GridUnitType.Star)), new ColumnDefinition(GridLength.Star)], HeightRequest = 8 };
        _barraRejilla.Add(new BoxView { Color = Color.FromArgb("#019D60"), CornerRadius = 4 }, 0, 0);
        var barra = new Border
        {
            BackgroundColor = Color.FromArgb("#E9E9E9"), StrokeThickness = 0, HeightRequest = 8, VerticalOptions = LayoutOptions.Center,
            StrokeShape = new RoundRectangle { CornerRadius = 4 }, Content = _barraRejilla, Padding = 0,
        };
        var fila1 = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 14 };
        fila1.Add(_posicion, 0, 0);
        fila1.Add(barra, 1, 0);
        fila1.Add(_contestadas, 2, 0);

        var cabecera = Ds.Tarjeta(new VerticalStackLayout { Spacing = 12, Children = { fila0, fila1 } }, Ds.RadioTarjeta, new Thickness(20, 16));
        _scroll = new ScrollView { Orientation = ScrollOrientation.Vertical };

        _raiz = new Grid { RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Star), new RowDefinition(GridLength.Auto)], RowSpacing = 12 };
        _raiz.Add(cabecera, 0, 0);
        _raiz.Add(_scroll, 0, 1);
        _raiz.Add(_nav, 0, 2);
        Content = _raiz;

        ConstruirNavegacion();
        PintarGuardado(_guardado);
        Unloaded += (_, _) => { try { _editor?.Vaciar(); } catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "práctica · al salir", ex); } };
    }

    // ================================================================================= API pública

    /// <summary>Califica una respuesta (en ≤ 2 s con el aula; sin ella devuelve «pendiente»). Nunca lanza hacia el alumno.</summary>
    public Func<PreguntaAula, JsonElement, CancellationToken, Task<VeredictoPractica>>? Comprobar { get; set; }

    /// <summary>Cierra el intento y devuelve el resultado.</summary>
    public Func<CancellationToken, Task<ResultadoDePractica>>? Terminar { get; set; }

    /// <summary>Convierte una ruta de imagen del contenido en URL (en línea o del paquete descargado).</summary>
    public Func<string, Uri>? ResolverUrl { get; set; }

    /// <summary>Falso: no hay aula ahora; «Comprobar» pasa a «Guardar respuesta» y el veredicto llega al volver.</summary>
    public bool PuedeCalificarAhora { get; set; } = true;

    /// <summary>Alto y ancho mínimo de lo que se toca, en puntos. Nunca baja de 44.</summary>
    public double AreaTactil { get; set; } = 56;

    /// <summary>El alumno pidió «Intentar nuevamente»: el host abre otro intento.</summary>
    public event Action? IntentarNuevamente;

    /// <summary>El alumno quiere volver a la lección.</summary>
    public event Action? VolverALaLeccion;

    /// <summary>La práctica terminó (con su resultado): el host actualiza la tarjeta.</summary>
    public event Action<ResultadoDePractica>? Terminada;

    public void PonerGuardado(EstadoGuardado estado) => EnHiloUi(() => { _guardado = estado; PintarGuardado(estado); });

    /// <summary>Pinta la práctica desde la primera pregunta sin responder. <paramref name="previas"/> son las respuestas de este intento que ya estaban.</summary>
    public void Cargar(ObjetoAula actividad, int numeroDeIntento, IReadOnlyDictionary<string, (JsonElement Respuesta, VeredictoPractica? Veredicto)>? previas = null) =>
        EnHiloUi(() => CargarEnUi(actividad, numeroDeIntento, previas));

    // ====================================================================================== carga

    private void EnHiloUi(Action accion)
    {
        var d = Dispatcher;
        if (d is not null && d.IsDispatchRequired) d.Dispatch(accion);
        else accion();
    }

    private void CargarEnUi(ObjetoAula actividad, int numero, IReadOnlyDictionary<string, (JsonElement Respuesta, VeredictoPractica? Veredicto)>? previas)
    {
        try { _editor?.Vaciar(); } catch { }
        _editor = null;
        _actividad = actividad;
        _preguntas = actividad.Preguntas ?? [];
        _numero = numero;
        _respuestas.Clear();
        _veredictos.Clear();
        _resultado = null;
        _revision = false;
        _confirmandoFin = false;
        _comprobando = false;
        if (previas is not null)
            foreach (var (referencia, dato) in previas)
            {
                _respuestas[referencia] = dato.Respuesta.Clone();
                if (dato.Veredicto is not null) _veredictos[referencia] = dato.Veredicto;
            }
        var primera = _preguntas.ToList().FindIndex(p => !_veredictos.ContainsKey(p.PreguntaRef));
        _indice = primera >= 0 ? primera : Math.Max(0, _preguntas.Count - 1);
        _titulo.Text = string.IsNullOrWhiteSpace(actividad.Titulo) ? "Comprueba lo aprendido" : actividad.Titulo;
        Repintar();
    }

    private void Repintar()
    {
        try { _editor?.Vaciar(); } catch { }
        _editor = null;
        if (_actividad is null)
        {
            PonerCuerpo(TarjetaMensaje("Aquí aparecerá tu práctica.", null));
        }
        else if (_preguntas.Count == 0)
        {
            PonerCuerpo(TarjetaMensaje("Esta práctica todavía no tiene preguntas.", "Avísale a tu profesor."));
        }
        else if (_resultado is not null && !_revision)
        {
            PonerCuerpo(TarjetaResultado(_resultado));
        }
        else if (_confirmandoFin)
        {
            PonerCuerpo(TarjetaConfirmarFin());
        }
        else
        {
            PintarPregunta();
        }
        PintarCabecera();
        PintarPuntos();
        ActualizarNavegacion();
    }

    private void PonerCuerpo(View contenido)
    {
        _scroll.Content = new VerticalStackLayout { Padding = new Thickness(4, 4, 4, 20), Children = { contenido } };
        if (_scroll.Handler is not null)
            Dispatcher.Dispatch(async () =>
            {
                try { await _scroll.ScrollToAsync(0, 0, false); } catch { }
            });
    }

    // ================================================================================== la pregunta

    private PreguntaAula Actual => _preguntas[Math.Clamp(_indice, 0, _preguntas.Count - 1)];
    private bool Bloqueada(PreguntaAula p) => _revision || _veredictos.ContainsKey(p.PreguntaRef) || _comprobando;

    private void PintarPregunta()
    {
        var p = Actual;
        var cx = new ContextoEditor
        {
            AreaTactil = AreaTactil, Escala = 1, ResolverUrl = ResolverUrl, Editable = !Bloqueada(p), Dispatcher = Dispatcher,
            Confirmar = respuesta => AlElegir(p, respuesta),
        };
        _editor = EditorPregunta.Crear(p, cx);
        if (_respuestas.TryGetValue(p.PreguntaRef, out var previa))
        {
            try { _editor.Aplicar(previa); }
            catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, $"práctica · pregunta {p.PreguntaRef} · repintar", ex); }
        }

        var pila = new VerticalStackLayout { Spacing = 18 };
        if (_indice == 0 && _actividad is { } a && !string.IsNullOrWhiteSpace(a.Instrucciones))
            pila.Add(Ds.ConTramos(a.InstruccionesTramos, a.Instrucciones, 17, Ds.TintaSuave));
        if (!string.IsNullOrWhiteSpace(p.Enunciado) || p.EnunciadoTramos is { Count: > 0 })
            pila.Add(Ds.ConTramos(p.EnunciadoTramos, p.Enunciado, 24));
        foreach (var m in p.Medios ?? [])
        {
            if (m.Ausente) continue;
            if (m.Componente == "imagen" && !string.IsNullOrWhiteSpace(m.Url))
                pila.Add(VistasActividad.Imagen(cx, m.Url, m.TextoAlternativo, 240));
        }
        pila.Add(_editor.Vista);
        if (_veredictos.TryGetValue(p.PreguntaRef, out var veredicto)) pila.Add(PanelDeRetro(veredicto));
        else if (!_revision) pila.Add(Ds.Secundario(PuedeCalificarAhora ? "Elige tu respuesta y toca «Comprobar»." : "Elige tu respuesta y toca «Guardar respuesta».", 15));
        PonerCuerpo(Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(24, 22)));
    }

    /// <summary>La retroalimentación inmediata: icono + texto + color. Fallar es ámbar y amable; sin conexión es un «guardado» tranquilo.</summary>
    private View PanelDeRetro(VeredictoPractica v)
    {
        Color fondo, tinta;
        string glifo, titulo;
        if (v.Pendiente || v.Correcta is null)
        {
            fondo = AzulSuave; tinta = AzulTinta; glifo = "●"; titulo = "Guardada en tu tableta";
        }
        else if (v.Correcta == true)
        {
            fondo = VerdeSuave; tinta = VerdeTinta; glifo = "✓"; titulo = "¡Correcto!";
        }
        else
        {
            fondo = AmbarSuave; tinta = AmbarTinta; glifo = "✗"; titulo = "Todavía no";
        }
        var pila = new VerticalStackLayout { Spacing = 6 };
        pila.Add(new Label { Text = $"{glifo}  {titulo}", FontFamily = Ds.FuenteSemi, FontSize = 19, TextColor = tinta });
        if (v.Pendiente || v.Correcta is null)
            pila.Add(new Label { Text = "Verás si acertaste cuando tu tableta vuelva a estar en el aula.", FontSize = 16, FontFamily = Ds.FuenteRegular, TextColor = tinta, LineBreakMode = LineBreakMode.WordWrap });
        foreach (var linea in v.Retroalimentacion.Where(l => !string.IsNullOrWhiteSpace(l)))
            pila.Add(new Label { Text = linea, FontSize = 16, FontFamily = Ds.FuenteRegular, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
        var panel = new Border
        {
            BackgroundColor = fondo, StrokeThickness = 0, Padding = new Thickness(18, 14), StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno },
            Content = pila, Opacity = 0, AutomationId = "practica-retro",
        };
        SemanticProperties.SetDescription(panel, $"{titulo}. {string.Join(' ', v.Retroalimentacion)}");
        _ = panel.FadeToAsync(1, 180, Easing.CubicOut);
        return panel;
    }

    /// <summary>El editor tiene una respuesta válida: se recuerda y se habilita «Comprobar». Aún no se envía nada.</summary>
    private void AlElegir(PreguntaAula p, JsonElement respuesta)
    {
        if (Bloqueada(p)) return;
        _respuestas[p.PreguntaRef] = respuesta.Clone();
        PintarCabecera();
        PintarPuntos();
        ActualizarNavegacion();
    }

    // ================================================================================ comprobar

    private async Task ComprobarAsync()
    {
        if (_comprobando || _actividad is null || _preguntas.Count == 0) return;
        var p = Actual;
        if (!_respuestas.TryGetValue(p.PreguntaRef, out var respuesta) || _veredictos.ContainsKey(p.PreguntaRef)) return;
        try { _editor?.Vaciar(); } catch { }
        _comprobando = true;
        ActualizarNavegacion();
        VeredictoPractica veredicto;
        try
        {
            using var tope = new CancellationTokenSource(TimeSpan.FromSeconds(6));
            veredicto = Comprobar is null
                ? new VeredictoPractica(null, true, [])
                : await Comprobar(p, respuesta, tope.Token);
        }
        catch (Exception ex)
        {
            // Sin aula, o el aula tardó: la respuesta ya está en la cola de la tableta (la guarda quien aloja el control). No se le muestra un error.
            RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "práctica · comprobar", ex);
            veredicto = new VeredictoPractica(null, true, []);
        }
        _comprobando = false;
        _veredictos[p.PreguntaRef] = veredicto;
        Repintar();
    }

    private async Task TerminarAsync()
    {
        if (_actividad is null) return;
        _confirmandoFin = false;
        ResultadoDePractica resultado;
        try
        {
            using var tope = new CancellationTokenSource(TimeSpan.FromSeconds(8));
            resultado = Terminar is null ? ResultadoLocal() : await Terminar(tope.Token);
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "práctica · terminar", ex);
            resultado = ResultadoLocal();
        }
        _resultado = resultado;
        _revision = false;
        Repintar();
        Terminada?.Invoke(resultado);
    }

    /// <summary>Si quien aloja el control no pudo dar un resultado, se cuenta lo que se sabe aquí (jamás se inventa un acierto).</summary>
    private ResultadoDePractica ResultadoLocal()
    {
        var revision = _preguntas.Select((q, i) => new RevisionPractica(
            q.PreguntaRef, i + 1, q.Enunciado,
            _veredictos.TryGetValue(q.PreguntaRef, out var v) && v.Conocido ? v.Correcta : null,
            _veredictos.TryGetValue(q.PreguntaRef, out var w) ? w.Retroalimentacion : [])).ToList();
        var correctas = revision.Count(r => r.Correcta == true);
        var sinCalificar = revision.Count(r => r.Correcta is null && _respuestas.ContainsKey(r.PreguntaRef));
        return new ResultadoDePractica(correctas, _preguntas.Count, correctas * 2 >= _preguntas.Count ? "¡Buen avance!" : "Sigue practicando: puedes intentarlo otra vez.", sinCalificar, revision);
    }

    // ==================================================================================== cabecera

    private void PintarCabecera()
    {
        var total = Math.Max(1, _preguntas.Count);
        if (_resultado is not null && !_revision)
        {
            _posicion.Text = "Resultado";
            _contestadas.Text = string.Empty;
            PonerBarra(1);
            return;
        }
        _posicion.Text = _preguntas.Count == 0 ? string.Empty : $"Pregunta {Math.Clamp(_indice + 1, 1, total)} de {_preguntas.Count}";
        var comprobadas = _veredictos.Count;
        _contestadas.Text = _preguntas.Count == 0 ? string.Empty : $"{comprobadas} de {_preguntas.Count} {(comprobadas == 1 ? "hecha" : "hechas")}";
        PonerBarra((double)comprobadas / total);
    }

    private void PonerBarra(double fraccion)
    {
        fraccion = Math.Clamp(fraccion, 0, 1);
        _barraRejilla.ColumnDefinitions[0].Width = new GridLength(Math.Max(0.0001, fraccion), GridUnitType.Star);
        _barraRejilla.ColumnDefinitions[1].Width = new GridLength(Math.Max(0.0001, 1 - fraccion), GridUnitType.Star);
    }

    private void PintarGuardado(EstadoGuardado estado)
    {
        var (texto, fondo) = estado switch
        {
            EstadoGuardado.Guardando => ("●  Guardando…", Ds.Lienzo),
            EstadoGuardado.GuardadoEnElDispositivo => ("●  Guardado en tu tableta", AzulSuave),
            _ => ("✓  Guardado", VerdeSuave),
        };
        _textoGuardado.Text = texto;
        _pildoraGuardado.BackgroundColor = fondo;
        SemanticProperties.SetDescription(_pildoraGuardado, texto[3..]);
    }

    // ==================================================================================== navegación

    private Button Boton(string texto, bool principal, Action accion, double? ancho = null)
    {
        var b = new Button
        {
            Text = texto, HeightRequest = Math.Max(48, AreaTactil), CornerRadius = 14, FontFamily = principal ? Ds.FuenteSemi : Ds.FuenteMedia, FontSize = 16,
            Padding = new Thickness(22, 0), BorderWidth = principal ? 0 : 1,
            BackgroundColor = principal ? TintaEstudio : Colors.White, TextColor = principal ? Colors.White : TintaEstudio,
            BorderColor = Color.FromArgb("#D2D2D7"),
        };
        if (ancho is { } w) b.WidthRequest = w;
        Ds.Hundir(b);
        b.Clicked += (_, _) => accion();
        return b;
    }

    private void ConstruirNavegacion()
    {
        _nav.Clear();
        _nav.ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Auto)];
        _btnAnterior = Boton("◀  Anterior", false, () => Ir(_indice - 1));
        _btnAnterior.AutomationId = "practica-anterior";
        _btnTerminar = Boton("Terminar", false, PedirTerminar);
        _btnTerminar.AutomationId = "practica-terminar";
        _btnPrincipal = Boton("Comprobar", true, PrincipalPulsado);
        _btnPrincipal.AutomationId = "practica-principal";
        _nav.Add(_btnAnterior, 0, 0);
        _nav.Add(_puntos, 1, 0);
        _nav.Add(_btnTerminar, 2, 0);
        _nav.Add(_btnPrincipal, 3, 0);
    }

    private void PintarPuntos()
    {
        _puntos.Clear();
        for (var i = 0; i < _preguntas.Count; i++)
        {
            var p = _preguntas[i];
            var indice = i;
            string glifo;
            Color fondo, tinta;
            if (_veredictos.TryGetValue(p.PreguntaRef, out var v))
            {
                if (v.Conocido && v.Correcta == true) { glifo = "✓"; fondo = VerdeSuave; tinta = VerdeTinta; }
                else if (v.Conocido) { glifo = "✗"; fondo = AmbarSuave; tinta = AmbarTinta; }
                else { glifo = "●"; fondo = AzulSuave; tinta = AzulTinta; }
            }
            else if (_respuestas.ContainsKey(p.PreguntaRef)) { glifo = "•"; fondo = Ds.Lienzo; tinta = Ds.Tinta; }
            else { glifo = (i + 1).ToString(); fondo = Colors.White; tinta = GrisTexto; }
            var actual = i == _indice && (_resultado is null || _revision);
            var caja = new Border
            {
                WidthRequest = 34, HeightRequest = 34, StrokeShape = new RoundRectangle { CornerRadius = 17 }, BackgroundColor = fondo,
                Stroke = new SolidColorBrush(actual ? TintaEstudio : Color.FromArgb("#D4D4D8")), StrokeThickness = actual ? 2.5 : 1,
                Content = new Label { Text = glifo, FontFamily = Ds.FuenteMedia, FontSize = 14, TextColor = tinta, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
            };
            SemanticProperties.SetDescription(caja, $"Pregunta {i + 1}");
            var toque = new TapGestureRecognizer();
            toque.Tapped += (_, _) => Ir(indice);
            caja.GestureRecognizers.Add(toque);
            _puntos.Add(caja);
        }
    }

    private void ActualizarNavegacion()
    {
        var resultadoVisible = _resultado is not null && !_revision;
        var hayPreguntas = _preguntas.Count > 0 && _actividad is not null;
        _nav.IsVisible = hayPreguntas && !resultadoVisible && !_confirmandoFin;
        if (!_nav.IsVisible) return;
        var ultima = _indice >= _preguntas.Count - 1;
        var p = Actual;
        var comprobada = _veredictos.ContainsKey(p.PreguntaRef);
        _btnAnterior.IsEnabled = _indice > 0 && !_comprobando;
        _btnAnterior.Opacity = _btnAnterior.IsEnabled ? 1 : 0.45;
        _btnTerminar.IsVisible = !_revision;
        _btnTerminar.IsEnabled = !_comprobando;

        string texto;
        bool activo;
        if (_revision)
        {
            texto = ultima ? "Volver al resultado" : "Siguiente  ▶";
            activo = true;
        }
        else if (comprobada)
        {
            texto = ultima ? "Ver resultado" : "Siguiente  ▶";
            activo = true;
        }
        else
        {
            texto = _comprobando ? "Comprobando…" : PuedeCalificarAhora ? "Comprobar" : "Guardar respuesta";
            activo = !_comprobando && _respuestas.ContainsKey(p.PreguntaRef);
        }
        _btnPrincipal.Text = texto;
        _btnPrincipal.IsEnabled = activo;
        _btnPrincipal.Opacity = activo ? 1 : 0.45;
        SemanticProperties.SetDescription(_btnPrincipal, texto);
    }

    private void Ir(int indice)
    {
        if (_comprobando || _preguntas.Count == 0) return;
        _indice = Math.Clamp(indice, 0, _preguntas.Count - 1);
        _confirmandoFin = false;
        if (_resultado is not null && !_revision) return;
        Repintar();
    }

    private async void PrincipalPulsado()
    {
        try
        {
            var p = Actual;
            var ultima = _indice >= _preguntas.Count - 1;
            if (_revision)
            {
                if (ultima) { _revision = false; Repintar(); }
                else Ir(_indice + 1);
            }
            else if (_veredictos.ContainsKey(p.PreguntaRef))
            {
                if (ultima) await TerminarAsync();
                else Ir(_indice + 1);
            }
            else await ComprobarAsync();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "práctica · botón principal", ex); }
    }

    private async void PedirTerminar()
    {
        try
        {
            if (_actividad is null || _comprobando) return;
            var faltan = _preguntas.Count(q => !_veredictos.ContainsKey(q.PreguntaRef));
            if (faltan == 0) await TerminarAsync();
            else
            {
                _confirmandoFin = true;
                Repintar();
            }
        }
        catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "práctica · terminar", ex); }
    }

    // ================================================================================= tarjetas

    private static View TarjetaMensaje(string principal, string? detalle)
    {
        var pila = new VerticalStackLayout { Spacing = 8, HorizontalOptions = LayoutOptions.Center };
        var titulo = Ds.Titulo(principal, 22);
        titulo.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(titulo);
        if (!string.IsNullOrWhiteSpace(detalle))
        {
            var d = Ds.Secundario(detalle!, 16);
            d.HorizontalTextAlignment = TextAlignment.Center;
            pila.Add(d);
        }
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(28, 36));
    }

    private View TarjetaConfirmarFin()
    {
        var faltan = _preguntas.Count(q => !_veredictos.ContainsKey(q.PreguntaRef));
        var pila = new VerticalStackLayout { Spacing = 14, AutomationId = "practica-confirmar" };
        var titulo = Ds.Titulo(faltan == 1 ? "Te falta 1 pregunta. Puedes terminar igual." : $"Te faltan {faltan} preguntas. Puedes terminar igual.", 23);
        titulo.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(titulo);
        var s = Ds.Secundario("Las que no respondas quedarán sin hacer. Podrás intentarlo nuevamente cuando quieras.", 16);
        s.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(s);
        var seguir = Boton("Seguir practicando", false, () => { _confirmandoFin = false; Repintar(); });
        seguir.AutomationId = "practica-seguir";
        var terminar = Boton("Terminar", true, async () => { try { await TerminarAsync(); } catch (Exception ex) { RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "práctica · terminar igual", ex); } });
        terminar.AutomationId = "practica-terminar-igual";
        var botones = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 14, Margin = new Thickness(0, 6, 0, 0) };
        botones.Add(seguir, 0, 0);
        botones.Add(terminar, 1, 0);
        pila.Add(botones);
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(28, 30));
    }

    /// <summary>«7 de 8 correctas · ¡Muy bien!» y las tres salidas: revisar, intentar nuevamente o volver a la lección.</summary>
    private View TarjetaResultado(ResultadoDePractica r)
    {
        var pendiente = r.PendienteDeCalificar;
        var bien = !pendiente && r.Total > 0 && r.Correctas * 100 >= r.Total * 60;
        var fondo = pendiente ? AzulSuave : bien ? VerdeSuave : AmbarSuave;
        var tinta = pendiente ? AzulTinta : bien ? VerdeTinta : AmbarTinta;
        var titular = pendiente ? "Práctica guardada" : $"{r.Correctas} de {r.Total} {(r.Total == 1 ? "correcta" : "correctas")}";
        var mensaje = pendiente ? "Se calificará cuando tu tableta vuelva a estar en el aula. Tus respuestas están a salvo." : r.Mensaje;

        var pila = new VerticalStackLayout { Spacing = 16, HorizontalOptions = LayoutOptions.Center, AutomationId = "practica-resultado" };
        pila.Add(new Border
        {
            WidthRequest = 96, HeightRequest = 96, BackgroundColor = fondo, StrokeThickness = 0, HorizontalOptions = LayoutOptions.Center,
            StrokeShape = new RoundRectangle { CornerRadius = 48 },
            Content = new Label { Text = pendiente ? "●" : bien ? "✓" : "↻", FontSize = 44, FontFamily = Ds.FuenteMedia, TextColor = tinta, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
        });
        var titulo = Ds.Titulo(titular, 30);
        titulo.HorizontalTextAlignment = TextAlignment.Center;
        titulo.AutomationId = "practica-titular";
        pila.Add(titulo);
        var m = Ds.Cuerpo(mensaje, 20, tinta);
        m.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(m);
        var s = Ds.Secundario("Es una práctica: puedes intentarlo nuevamente las veces que quieras.", 16);
        s.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(s);

        var marcas = new HorizontalStackLayout { Spacing = 8, HorizontalOptions = LayoutOptions.Center, Margin = new Thickness(0, 4) };
        foreach (var q in r.Revision)
        {
            var (g, f, t) = q.Correcta == true ? ("✓", VerdeSuave, VerdeTinta) : q.Correcta == false ? ("✗", AmbarSuave, AmbarTinta) : ("●", AzulSuave, AzulTinta);
            marcas.Add(new Border
            {
                WidthRequest = 34, HeightRequest = 34, BackgroundColor = f, StrokeThickness = 0, StrokeShape = new RoundRectangle { CornerRadius = 17 },
                Content = new Label { Text = g, FontFamily = Ds.FuenteMedia, FontSize = 14, TextColor = t, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
            });
        }
        pila.Add(marcas);

        var revisar = Boton("Revisar respuestas", false, () => { _revision = true; _indice = 0; Repintar(); });
        revisar.AutomationId = "practica-revisar";
        var reintentar = Boton("Intentar nuevamente", true, () => IntentarNuevamente?.Invoke());
        reintentar.AutomationId = "practica-reintentar";
        var volver = Boton("Volver a la lección", false, () => VolverALaLeccion?.Invoke());
        volver.AutomationId = "practica-volver";
        var botones = new FlexLayout { Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap, JustifyContent = Microsoft.Maui.Layouts.FlexJustify.Center, Margin = new Thickness(0, 6, 0, 0) };
        foreach (var b in new[] { revisar, reintentar, volver }) { b.Margin = new Thickness(6); botones.Add(b); }
        pila.Add(botones);
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(32, 36));
    }
}

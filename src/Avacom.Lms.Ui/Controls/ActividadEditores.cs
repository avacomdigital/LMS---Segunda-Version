using System.Text.Json;
using System.Text.RegularExpressions;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Controls;

// Los editores de pregunta de ActividadResponderView: uno por tipo de pregunta (opción múltiple, verdadero o falso, completar,
// relacionar, ordenar y abierta). Cada uno pinta la pregunta, deja elegir con toques y, cuando hay una respuesta válida, la entrega a
// quien lo creó por Confirmar(): el control decide cómo guardarla. Ninguno sabe si acertó ni pinta correcto o incorrecto (DEC-032):
// "elegido" se marca con forma, trazo y una marca de texto, nunca sólo con color (UXR-011).
//
// Reglas comunes:
//  · Sólo se manda lo que el nodo puede recibir: una selección vacía, un orden incompleto o un texto en blanco NO se guardan (una
//    respuesta mal formada haría que la biblioteca la rechace); lo último guardado sigue valiendo y es lo que se vuelve a ver.
//  · Las referencias son siempre ids (opcion_ref, espacio_ref, ref), nunca posiciones: las opciones llegan barajadas por alumno.
//  · Ningún editor usa Path, Ellipse ni iconos vectoriales (Win2D): sólo Border con esquinas, texto y botones del kit.

/// <summary>Lo que un editor necesita del control que lo aloja. Es una foto: cambiar el estado obliga a crear el editor de nuevo.</summary>
internal sealed class ContextoEditor
{
    public double AreaTactil { get; init; } = 56;
    public double Escala { get; init; } = 1;
    public Func<string, Uri>? ResolverUrl { get; init; }
    /// <summary>Sin tiempo, entregado o de sólo lectura: se ve todo y no se edita.</summary>
    public bool Editable { get; init; } = true;
    public required Action<JsonElement> Confirmar { get; init; }
    public IDispatcher? Dispatcher { get; init; }

    public double Alto => Math.Max(44, AreaTactil);
}

internal abstract class EditorPregunta
{
    protected EditorPregunta(PreguntaAula pregunta, ContextoEditor cx)
    {
        P = pregunta;
        Cx = cx;
    }

    protected PreguntaAula P { get; }
    protected ContextoEditor Cx { get; }

    public abstract View Vista { get; }

    /// <summary>Vuelve a pintar lo que se respondió antes (lo último guardado). No dispara un guardado.</summary>
    public virtual void Aplicar(JsonElement respuesta) { }

    /// <summary>Guarda lo que quede pendiente (texto a medio escribir) y detiene sus temporizadores. Se llama antes de cambiar de pregunta.</summary>
    public virtual void Vaciar() { }

    protected void Confirmar(JsonElement respuesta) => Cx.Confirmar(respuesta);

    public static EditorPregunta Crear(PreguntaAula p, ContextoEditor cx)
    {
        try
        {
            return p.Componente switch
            {
                "opcion_multiple" when p.Opciones is { Count: > 0 } => new EditorOpciones(p, cx, verdaderoFalso: false),
                "verdadero_falso" => new EditorOpciones(p, cx, verdaderoFalso: true),
                "completar" when p.Espacios is { Count: > 0 } => new EditorCompletar(p, cx),
                "relacionar" when p.Izquierda is { Count: > 0 } && p.Derecha is { Count: > 0 } => new EditorRelacionar(p, cx),
                "ordenar" when p.Elementos is { Count: > 0 } => new EditorOrdenar(p, cx),
                "abierta" when EsTexto(p) => new EditorAbierta(p, cx),
                _ => new EditorNoSoportado(p, cx),
            };
        }
        catch (Exception ex)
        {
            // Una pregunta con datos raros no puede tumbar la actividad: se anota y se ofrece la salida amable.
            RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, $"actividad · pregunta {p.PreguntaRef} ({p.Componente})", ex);
            return new EditorNoSoportado(p, cx);
        }
    }

    private static bool EsTexto(PreguntaAula p) => string.IsNullOrWhiteSpace(p.FormatoRespuesta) || string.Equals(p.FormatoRespuesta, "text", StringComparison.OrdinalIgnoreCase);
}

/// <summary>Espera sin escribir: cuando pasa el tiempo sin que haya otro cambio, avisa una vez. Un temporizador del despachador, detenido al vaciar.</summary>
internal sealed class Reposo(IDispatcher? despachador, TimeSpan espera, Action alVencer)
{
    private IDispatcherTimer? _t;

    public void Reiniciar()
    {
        if (despachador is null) return;
        try
        {
            if (_t is null)
            {
                _t = despachador.CreateTimer();
                _t.Interval = espera;
                _t.IsRepeating = false;
                _t.Tick += Vencio;
            }
            _t.Stop();
            _t.Start();
        }
        catch { /* sin temporizador queda el guardado al perder el foco y al cambiar de pregunta */ }
    }

    private void Vencio(object? remitente, EventArgs e)
    {
        try { _t?.Stop(); } catch { }
        alVencer();
    }

    public void Detener()
    {
        try { _t?.Stop(); } catch { }
    }
}

/// <summary>Piezas visuales que comparten los editores.</summary>
internal static class VistasActividad
{
    public static readonly Color Reposo = Color.FromArgb("#D4D4D8");
    public static readonly Brush BrochaTinta = new SolidColorBrush(Ds.Tinta);
    public static readonly Brush BrochaReposo = new SolidColorBrush(Reposo);

    public static JsonElement Json(object valor) => JsonSerializer.SerializeToElement(valor);

    /// <summary>Una imagen de una pregunta, opción o ítem. Sin resolutor de URL (o sin URL) se anuncia con su texto alternativo.</summary>
    public static View Imagen(ContextoEditor cx, string? url, string? alternativo, double alto)
    {
        Uri? uri = null;
        if (cx.ResolverUrl is not null && !string.IsNullOrWhiteSpace(url))
        {
            try { uri = cx.ResolverUrl(url!); } catch { uri = null; }
        }
        if (uri is null)
            return Ds.Secundario(string.IsNullOrWhiteSpace(alternativo) ? "Imagen" : $"Imagen: {alternativo}", 15 * cx.Escala);
        var imagen = new Image { Aspect = Aspect.AspectFit, HeightRequest = alto, Source = new UriImageSource { Uri = uri, CachingEnabled = false } };
        if (!string.IsNullOrWhiteSpace(alternativo)) SemanticProperties.SetDescription(imagen, alternativo);
        return new Border
        {
            StrokeThickness = 0, BackgroundColor = Ds.Lienzo, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno },
            Content = imagen, HorizontalOptions = LayoutOptions.Start,
        };
    }

    /// <summary>Texto (con sus tramos) o imagen de una opción o un ítem; con las dos, la imagen va encima. Sin nada, el respaldo.</summary>
    public static View TextoOImagen(ContextoEditor cx, IReadOnlyList<Tramo>? tramos, string? texto, string? url, string? alternativo, string respaldo, double tamano)
    {
        var hayTexto = !string.IsNullOrWhiteSpace(texto);
        var hayImagen = !string.IsNullOrWhiteSpace(url);
        var etiqueta = hayTexto ? Ds.ConTramos(tramos, texto, tamano) : Ds.Cuerpo(respaldo, tamano);
        if (!hayImagen) return etiqueta;
        var pila = new VerticalStackLayout { Spacing = 6 };
        pila.Add(Imagen(cx, url, alternativo, 130 * cx.Escala));
        if (hayTexto) pila.Add(etiqueta);
        return pila;
    }

    /// <summary>El texto plano de un elemento para la descripción accesible.</summary>
    public static string Rotulo(string? texto, string? alternativo, string respaldo) =>
        !string.IsNullOrWhiteSpace(texto) ? texto! : !string.IsNullOrWhiteSpace(alternativo) ? alternativo! : respaldo;

    /// <summary>Un botón cuadrado de sólo glifo (▲ ▼) con el relieve del kit sobre fondo claro. Devuelve la cápsula que se coloca.</summary>
    public static View BotonGlifo(string glifo, double lado, string descripcion, Action alPulsar, bool activo)
    {
        var b = new Button
        {
            Text = glifo, WidthRequest = lado, HeightRequest = lado, MinimumWidthRequest = lado, MinimumHeightRequest = lado,
            CornerRadius = Ds.RadioControl, FontSize = lado * 0.4, FontFamily = Ds.FuenteMedia, Padding = 0, BorderWidth = 0,
        };
        SemanticProperties.SetDescription(b, descripcion);
        Ds.PintarRelieve(b, Colors.White, Ds.Tinta);
        Ds.Hundir(b);
        b.Clicked += (_, _) => alPulsar();
        var capsula = Ds.Capsula(b);
        capsula.VerticalOptions = LayoutOptions.Center;
        Ds.Habilitar(b, activo, 0.35);
        return capsula;
    }

    /// <summary>Una caja de texto con el borde del kit para un Entry o un Editor (sin cromo nativo en Windows: ver <see cref="NeumoChrome"/>).</summary>
    public static Border Caja(View contenido, double alto, Thickness relleno) => new()
    {
        BackgroundColor = Colors.White, Stroke = BrochaTinta, StrokeThickness = 2,
        StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Padding = relleno, MinimumHeightRequest = alto, Content = contenido,
    };

    /// <summary>Una insignia redonda con una etiqueta corta (el número de una pareja, el orden de un ítem).</summary>
    public static Border Insignia(string texto, double lado, bool oscura, double tamano)
    {
        var etiqueta = new Label
        {
            Text = texto, FontSize = tamano, FontFamily = Ds.FuenteMedia, TextColor = oscura ? Colors.White : Ds.Tinta,
            HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center,
        };
        return new Border
        {
            WidthRequest = lado, HeightRequest = lado, StrokeThickness = oscura ? 0 : 1.5, Stroke = BrochaReposo,
            BackgroundColor = oscura ? Ds.Tinta : Colors.White, StrokeShape = new RoundRectangle { CornerRadius = lado / 2 },
            VerticalOptions = LayoutOptions.Center, Content = etiqueta,
        };
    }

    public static void PonerTexto(Border insignia, string texto) { if (insignia.Content is Label l) l.Text = texto; }
}

/// <summary>
/// Una fila de opción tocable: marca a la izquierda (círculo si se elige una, cuadrado si se eligen varias) y el contenido. Elegida:
/// fondo azul claro, trazo grueso, marca rellena con «✓». Con 56 pt de alto mínimo por defecto.
/// </summary>
internal sealed class FilaOpcion : Border
{
    private readonly Border _marca;
    private readonly Label _visto;

    public FilaOpcion(View contenido, bool cuadrada, double area, string descripcion)
    {
        Descripcion = descripcion;
        _visto = new Label
        {
            Text = "✓", FontSize = 18, FontFamily = Ds.FuenteMedia, TextColor = Colors.White,
            HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center, IsVisible = false,
        };
        _marca = new Border
        {
            WidthRequest = 32, HeightRequest = 32, StrokeThickness = 2, Stroke = VistasActividad.BrochaTinta, BackgroundColor = Colors.White,
            StrokeShape = new RoundRectangle { CornerRadius = cuadrada ? 8 : 16 }, VerticalOptions = LayoutOptions.Center, Content = _visto,
        };
        contenido.VerticalOptions = LayoutOptions.Center;
        var rejilla = new Grid { ColumnDefinitions = [new ColumnDefinition(40), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 12 };
        rejilla.Add(_marca, 0, 0);
        rejilla.Add(contenido, 1, 0);
        Content = rejilla;
        Padding = new Thickness(16, 10);
        MinimumHeightRequest = area;
        StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno };
        var toque = new TapGestureRecognizer();
        toque.Tapped += (_, _) => Tocada?.Invoke();
        GestureRecognizers.Add(toque);
        Pintar(false);
    }

    public string Descripcion { get; }
    public bool Seleccionada { get; private set; }
    public event Action? Tocada;

    public void Pintar(bool seleccionada)
    {
        Seleccionada = seleccionada;
        BackgroundColor = seleccionada ? Ds.InfoSuave : Colors.White;
        Stroke = seleccionada ? VistasActividad.BrochaTinta : VistasActividad.BrochaReposo;
        StrokeThickness = seleccionada ? 3 : 1.5;
        _marca.BackgroundColor = seleccionada ? Ds.Tinta : Colors.White;
        _visto.IsVisible = seleccionada;
        SemanticProperties.SetDescription(this, $"{Descripcion}. {(seleccionada ? "Elegida" : "Sin elegir")}");
    }
}

// --------------------------------------------------------------------- opción múltiple y verdadero o falso

/// <summary>
/// <c>opcion_multiple</c> (una o varias según <c>permite_varias</c>) → <c>{"selectedOptionIds":[opcion_ref…]}</c> y
/// <c>verdadero_falso</c> → <c>{"value":true|false}</c>. Se guarda al tocar: una vez por toque, sin botón de «Comprobar».
/// </summary>
internal sealed class EditorOpciones : EditorPregunta
{
    private readonly bool _vf;
    private readonly bool _varias;
    private readonly List<OpcionAula> _opciones;
    private readonly List<FilaOpcion> _filas = [];
    private readonly HashSet<string> _elegidas = [];
    private readonly Label _pista;
    private readonly VerticalStackLayout _vista = new() { Spacing = 10 };

    public EditorOpciones(PreguntaAula p, ContextoEditor cx, bool verdaderoFalso) : base(p, cx)
    {
        _vf = verdaderoFalso;
        _varias = !_vf && p.PermiteVarias == true;
        // Verdadero o falso llega con sus dos opciones («true» / «false»); si un nodo antiguo no las manda, se ofrecen igual.
        _opciones = p.Opciones is { Count: > 0 }
            ? new List<OpcionAula>(p.Opciones)
            : new List<OpcionAula> { new("true", "Verdadero", null), new("false", "Falso", null) };
        _pista = Ds.Secundario(_varias ? "Puedes elegir más de una." : "Elige una respuesta.", 16 * cx.Escala);
        _vista.Add(_pista);
        for (var i = 0; i < _opciones.Count; i++)
        {
            var op = _opciones[i];
            var respaldo = _vf ? (EsVerdadera(op, i) ? "Verdadero" : "Falso") : $"Opción {i + 1}";
            var contenido = VistasActividad.TextoOImagen(cx, op.Tramos, op.Texto, op.Url, op.TextoAlternativo, respaldo, 21 * cx.Escala);
            var fila = new FilaOpcion(contenido, _varias, cx.Alto, VistasActividad.Rotulo(op.Texto, op.TextoAlternativo, respaldo)) { AutomationId = $"act-opcion-{op.OpcionRef}" };
            fila.Tocada += () => Tocar(op);
            _filas.Add(fila);
            _vista.Add(fila);
        }
    }

    public override View Vista => _vista;

    private static bool EsVerdadera(OpcionAula op, int indice) =>
        string.Equals(op.OpcionRef, "true", StringComparison.OrdinalIgnoreCase) ? true
        : string.Equals(op.OpcionRef, "false", StringComparison.OrdinalIgnoreCase) ? false
        : indice == 0;

    private void Tocar(OpcionAula op)
    {
        if (!Cx.Editable) return;
        if (_varias)
        {
            if (!_elegidas.Remove(op.OpcionRef)) _elegidas.Add(op.OpcionRef);
        }
        else
        {
            _elegidas.Clear();
            _elegidas.Add(op.OpcionRef);
        }
        Pintar();
        if (_elegidas.Count == 0) return;   // sin ninguna elegida no hay respuesta que mandar: lo último guardado sigue valiendo
        if (_vf)
        {
            var i = _opciones.FindIndex(o => o.OpcionRef == op.OpcionRef);
            Confirmar(VistasActividad.Json(new { value = EsVerdadera(op, i) }));
        }
        else
        {
            // En el orden en que se ven las opciones, no en el orden de los toques: la misma selección da siempre la misma respuesta.
            Confirmar(VistasActividad.Json(new { selectedOptionIds = _opciones.Where(o => _elegidas.Contains(o.OpcionRef)).Select(o => o.OpcionRef).ToArray() }));
        }
    }

    private void Pintar()
    {
        for (var i = 0; i < _filas.Count; i++) _filas[i].Pintar(_elegidas.Contains(_opciones[i].OpcionRef));
        if (_varias && _elegidas.Count == 0) _pista.Text = "Elige al menos una para guardar tu respuesta.";
        else _pista.Text = _varias ? "Puedes elegir más de una." : "Elige una respuesta.";
    }

    public override void Aplicar(JsonElement r)
    {
        _elegidas.Clear();
        if (r.ValueKind == JsonValueKind.Object)
        {
            if (_vf)
            {
                if (r.TryGetProperty("value", out var v) && v.ValueKind is JsonValueKind.True or JsonValueKind.False)
                {
                    var valor = v.GetBoolean();
                    for (var i = 0; i < _opciones.Count; i++)
                        if (EsVerdadera(_opciones[i], i) == valor) { _elegidas.Add(_opciones[i].OpcionRef); break; }
                }
            }
            else if (r.TryGetProperty("selectedOptionIds", out var ids) && ids.ValueKind == JsonValueKind.Array)
            {
                foreach (var e in ids.EnumerateArray())
                    if (e.ValueKind == JsonValueKind.String && e.GetString() is { } id && _opciones.Any(o => o.OpcionRef == id)) _elegidas.Add(id);
            }
        }
        Pintar();
    }
}

// ------------------------------------------------------------------------------------------- completar

/// <summary>
/// <c>completar</c> → <c>{"blanks":{espacio_ref:valor}}</c>. La plantilla se lee arriba con cada hueco como «[ 1 ]» y debajo hay una
/// entrada por espacio: un cuadro de texto, o (si <c>modo_entrada</c> es «select») sus opciones para tocar. Los cuadros de texto se
/// guardan al perder el foco, al pulsar «Listo» del teclado, a los 2 s sin escribir y al cambiar de pregunta; las opciones, al tocar.
/// </summary>
internal sealed class EditorCompletar : EditorPregunta
{
    private static readonly Regex Hueco = new(@"\{\{\s*([^{}]+?)\s*\}\}", RegexOptions.Compiled);
    private const int MaximoFilas = 6;   // con más opciones que estas, un selector en vez de filas

    private readonly List<EspacioAula> _espacios;
    private readonly Dictionary<string, string> _valores = [];
    private readonly Dictionary<string, Entry> _entradas = [];
    private readonly Dictionary<string, List<(string Valor, FilaOpcion Fila)>> _filas = [];
    private readonly Dictionary<string, Picker> _selectores = [];
    private readonly VerticalStackLayout _vista = new() { Spacing = 16 };
    private readonly Reposo _reposo;
    private bool _aplicando;
    private bool _guardada;
    private string? _ultimo;

    public EditorCompletar(PreguntaAula p, ContextoEditor cx) : base(p, cx)
    {
        _espacios = [.. p.Espacios!];
        _reposo = new Reposo(cx.Dispatcher, TimeSpan.FromSeconds(2), Guardar);
        foreach (var e in _espacios) _valores[e.EspacioRef] = string.Empty;

        if (!string.IsNullOrWhiteSpace(p.Plantilla))
            _vista.Add(new Label { FormattedText = Plantilla(p.Plantilla!), FontSize = 22 * cx.Escala, FontFamily = Ds.FuenteRegular, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });

        for (var i = 0; i < _espacios.Count; i++)
        {
            var e = _espacios[i];
            var bloque = new VerticalStackLayout { Spacing = 8 };
            bloque.Add(Ds.Secundario(_espacios.Count == 1 ? "Tu respuesta" : $"Espacio {i + 1}", 16 * cx.Escala));
            bloque.Add(string.Equals(e.ModoEntrada, "select", StringComparison.OrdinalIgnoreCase) && e.Opciones is { Count: > 0 } ? Seleccion(e) : Escritura(e));
            _vista.Add(bloque);
        }
    }

    public override View Vista => _vista;

    private FormattedString Plantilla(string plantilla)
    {
        var fs = new FormattedString();
        var desde = 0;
        foreach (Match m in Hueco.Matches(plantilla))
        {
            if (m.Index > desde) fs.Spans.Add(new Span { Text = plantilla[desde..m.Index], FontFamily = Ds.FuenteRegular });
            var indice = _espacios.FindIndex(x => x.EspacioRef == m.Groups[1].Value);
            fs.Spans.Add(new Span { Text = indice >= 0 ? $" [ {indice + 1} ] " : " [ … ] ", FontFamily = Ds.FuenteSemi });
            desde = m.Index + m.Length;
        }
        if (desde < plantilla.Length) fs.Spans.Add(new Span { Text = plantilla[desde..], FontFamily = Ds.FuenteRegular });
        return fs;
    }

    private View Escritura(EspacioAula e)
    {
        var entrada = new Entry
        {
            ClassId = NeumoChrome.Clase, FontFamily = Ds.FuenteRegular, FontSize = 21 * Cx.Escala, TextColor = Ds.Tinta,
            Placeholder = "Escribe aquí", PlaceholderColor = Ds.TintaSuave, BackgroundColor = Colors.Transparent,
            VerticalOptions = LayoutOptions.Center, ReturnType = ReturnType.Done, IsReadOnly = !Cx.Editable,
            AutomationId = $"act-hueco-{e.EspacioRef}",
        };
        if (string.Equals(e.ModoEntrada, "numeric", StringComparison.OrdinalIgnoreCase)) entrada.Keyboard = Keyboard.Numeric;
        entrada.TextChanged += (_, args) =>
        {
            if (_aplicando) return;
            _valores[e.EspacioRef] = args.NewTextValue ?? string.Empty;
            _reposo.Reiniciar();
        };
        entrada.Unfocused += (_, _) => Guardar();
        entrada.Completed += (_, _) => Guardar();
        _entradas[e.EspacioRef] = entrada;
        return VistasActividad.Caja(entrada, Cx.Alto, new Thickness(14, 0));
    }

    private View Seleccion(EspacioAula e)
    {
        var opciones = e.Opciones!;
        if (opciones.Count > MaximoFilas)
        {
            var lista = new Picker
            {
                ClassId = NeumoChrome.Clase, FontFamily = Ds.FuenteMedia, FontSize = 19 * Cx.Escala, TextColor = Ds.Tinta, TitleColor = Ds.TintaSuave,
                Title = "Toca para elegir", BackgroundColor = Colors.Transparent, VerticalOptions = LayoutOptions.Center, IsEnabled = Cx.Editable,
                ItemsSource = opciones.ToList(), AutomationId = $"act-hueco-{e.EspacioRef}",
            };
            lista.SelectedIndexChanged += (_, _) =>
            {
                if (_aplicando || lista.SelectedIndex < 0) return;
                _valores[e.EspacioRef] = opciones[lista.SelectedIndex];
                Guardar();
            };
            _selectores[e.EspacioRef] = lista;
            return VistasActividad.Caja(lista, Cx.Alto, new Thickness(10, 0));
        }
        var pila = new VerticalStackLayout { Spacing = 8 };
        var filas = new List<(string Valor, FilaOpcion Fila)>();
        foreach (var valor in opciones)
        {
            var fila = new FilaOpcion(Ds.Cuerpo(valor, 21 * Cx.Escala), cuadrada: false, Cx.Alto, valor);
            fila.Tocada += () =>
            {
                if (!Cx.Editable) return;
                _valores[e.EspacioRef] = valor;
                PintarFilas(e.EspacioRef);
                Guardar();
            };
            filas.Add((valor, fila));
            pila.Add(fila);
        }
        _filas[e.EspacioRef] = filas;
        return pila;
    }

    private void PintarFilas(string espacio)
    {
        if (!_filas.TryGetValue(espacio, out var filas)) return;
        var actual = _valores.GetValueOrDefault(espacio) ?? string.Empty;
        foreach (var (valor, fila) in filas) fila.Pintar(valor == actual);
    }

    private JsonElement Instantanea()
    {
        var blanks = _espacios.ToDictionary(e => e.EspacioRef, e => (_valores.GetValueOrDefault(e.EspacioRef) ?? string.Empty).Trim());
        return VistasActividad.Json(new { blanks });
    }

    private void Guardar()
    {
        _reposo.Detener();
        if (!Cx.Editable) return;
        var hayAlgo = _valores.Values.Any(v => !string.IsNullOrWhiteSpace(v));
        if (!hayAlgo && !_guardada) return;   // nada escrito y nada guardado antes: no hay respuesta
        var json = Instantanea();
        var texto = json.GetRawText();
        if (texto == _ultimo) return;
        _ultimo = texto;
        _guardada = true;
        Confirmar(json);
    }

    public override void Vaciar() => Guardar();

    public override void Aplicar(JsonElement r)
    {
        if (r.ValueKind != JsonValueKind.Object || !r.TryGetProperty("blanks", out var huecos) || huecos.ValueKind != JsonValueKind.Object) return;
        _aplicando = true;
        try
        {
            foreach (var e in _espacios)
            {
                var valor = huecos.TryGetProperty(e.EspacioRef, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? string.Empty : string.Empty;
                _valores[e.EspacioRef] = valor;
                if (_entradas.TryGetValue(e.EspacioRef, out var entrada)) entrada.Text = valor;
                if (_selectores.TryGetValue(e.EspacioRef, out var lista))
                    lista.SelectedIndex = e.Opciones is { } o ? o.ToList().IndexOf(valor) : -1;
                PintarFilas(e.EspacioRef);
            }
        }
        finally { _aplicando = false; }
        _guardada = true;
        _ultimo = Instantanea().GetRawText();
    }
}

// ----------------------------------------------------------------------------------------- relacionar

/// <summary>
/// <c>relacionar</c> → <c>{"pairs":[{"leftId","rightId"}…]}</c>. Se toca un elemento de la izquierda y luego su pareja de la derecha; cada
/// pareja lleva el mismo número en los dos lados (no sólo un color). Tocar una pareja ya hecha la deshace. Sólo se guarda cuando todos
/// los de la izquierda tienen pareja y cada elemento de la derecha se usa una vez.
/// </summary>
internal sealed class EditorRelacionar : EditorPregunta
{
    private readonly List<ElementoAula> _izq;
    private readonly List<ElementoAula> _der;
    private readonly Dictionary<string, string> _pares = [];   // izquierda → derecha
    private readonly List<Border> _cajasIzq = [];
    private readonly List<Border> _cajasDer = [];
    private readonly List<Border> _insigniasIzq = [];
    private readonly List<Border> _insigniasDer = [];
    private readonly Label _pista;
    private readonly Label _estado;
    private readonly View _quitar;
    private readonly VerticalStackLayout _vista = new() { Spacing = 12 };
    private string? _elegida;   // la de la izquierda que espera su pareja
    private string? _ultimo;

    public EditorRelacionar(PreguntaAula p, ContextoEditor cx) : base(p, cx)
    {
        _izq = [.. p.Izquierda!];
        _der = [.. p.Derecha!];
        _pista = Ds.Secundario(string.Empty, 16 * cx.Escala);
        _estado = new Label { FontFamily = Ds.FuenteMedia, FontSize = 17 * cx.Escala, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap };
        var quitar = Ds.Boton("Quitar todas las uniones", Ds.Rango.Secondary, (_, _) => QuitarTodas(), Math.Max(44, cx.AreaTactil * 0.85));
        quitar.HorizontalOptions = LayoutOptions.Start;
        _quitar = Ds.Capsula(quitar);
        _quitar.HorizontalOptions = LayoutOptions.Start;

        _vista.Add(_pista);
        var columnas = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 16 };
        var izquierda = new VerticalStackLayout { Spacing = 10 };
        var derecha = new VerticalStackLayout { Spacing = 10 };
        for (var i = 0; i < _izq.Count; i++)
        {
            var e = _izq[i];
            var insignia = VistasActividad.Insignia((i + 1).ToString(), 34, oscura: false, 17);
            _insigniasIzq.Add(insignia);
            var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 12 };
            fila.Add(insignia, 0, 0);
            fila.Add(Contenido(e, i, "Elemento"), 1, 0);
            var caja = Tarjeta(fila, $"act-izquierda-{e.Ref}", () => TocarIzquierda(e));
            _cajasIzq.Add(caja);
            izquierda.Add(caja);
        }
        for (var i = 0; i < _der.Count; i++)
        {
            var e = _der[i];
            var insignia = VistasActividad.Insignia(string.Empty, 34, oscura: true, 17);
            insignia.Opacity = 0;   // sin pareja no se ve, pero conserva su sitio para que la fila no salte al unirse
            _insigniasDer.Add(insignia);
            var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
            fila.Add(Contenido(e, i, "Pareja"), 0, 0);
            fila.Add(insignia, 1, 0);
            var caja = Tarjeta(fila, $"act-derecha-{e.Ref}", () => TocarDerecha(e));
            _cajasDer.Add(caja);
            derecha.Add(caja);
        }
        columnas.Add(izquierda, 0, 0);
        columnas.Add(derecha, 1, 0);
        _vista.Add(columnas);
        _vista.Add(_estado);
        _vista.Add(_quitar);
        Pintar();
    }

    public override View Vista => _vista;

    private View Contenido(ElementoAula e, int indice, string respaldo)
    {
        var contenido = VistasActividad.TextoOImagen(Cx, e.Tramos, e.Texto, e.Url, e.TextoAlternativo, $"{respaldo} {indice + 1}", 19 * Cx.Escala);
        contenido.VerticalOptions = LayoutOptions.Center;
        return contenido;
    }

    private Border Tarjeta(View contenido, string id, Action alTocar)
    {
        var caja = new Border
        {
            Padding = new Thickness(12, 8), MinimumHeightRequest = Cx.Alto, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno },
            Content = contenido, AutomationId = id,
        };
        var toque = new TapGestureRecognizer();
        toque.Tapped += (_, _) => alTocar();
        caja.GestureRecognizers.Add(toque);
        return caja;
    }

    private void TocarIzquierda(ElementoAula e)
    {
        if (!Cx.Editable) return;
        if (_elegida == e.Ref) _elegida = null;                // tocarla otra vez la suelta
        else { _pares.Remove(e.Ref); _elegida = e.Ref; }       // si ya tenía pareja se deshace y se vuelve a elegir
        Pintar();
    }

    private void TocarDerecha(ElementoAula e)
    {
        if (!Cx.Editable) return;
        var dueno = _pares.Where(kv => kv.Value == e.Ref).Select(kv => kv.Key).FirstOrDefault();
        if (_elegida is { } izquierda)
        {
            if (dueno is not null) _pares.Remove(dueno);        // esa pareja era de otro: pasa a la que se acaba de elegir
            _pares[izquierda] = e.Ref;
            _elegida = null;
            Pintar();
            Guardar();
        }
        else if (dueno is not null)
        {
            _pares.Remove(dueno);                               // sin elegir nada, tocar una pareja hecha la deshace
            Pintar();
        }
    }

    private void QuitarTodas()
    {
        if (!Cx.Editable) return;
        _pares.Clear();
        _elegida = null;
        Pintar();
    }

    private void Pintar()
    {
        for (var i = 0; i < _izq.Count; i++)
        {
            var r = _izq[i].Ref;
            var elegida = _elegida == r;
            var unida = _pares.ContainsKey(r);
            Estilo(_cajasIzq[i], elegida, unida);
            var insignia = _insigniasIzq[i];
            insignia.BackgroundColor = elegida ? Ds.Tinta : Colors.White;
            if (insignia.Content is Label l) l.TextColor = elegida ? Colors.White : Ds.Tinta;
        }
        for (var i = 0; i < _der.Count; i++)
        {
            var r = _der[i].Ref;
            var izquierda = _pares.Where(kv => kv.Value == r).Select(kv => kv.Key).FirstOrDefault();
            var numero = izquierda is null ? -1 : _izq.FindIndex(x => x.Ref == izquierda) + 1;
            Estilo(_cajasDer[i], false, izquierda is not null);
            _insigniasDer[i].Opacity = izquierda is null ? 0 : 1;
            VistasActividad.PonerTexto(_insigniasDer[i], numero > 0 ? numero.ToString() : string.Empty);
        }
        _pista.Text = _elegida is null ? "Toca un elemento de la izquierda y luego su pareja de la derecha." : "Ahora toca su pareja en la derecha.";
        _estado.Text = _pares.Count == _izq.Count
            ? $"Uniste {_pares.Count} de {_izq.Count}. Toca una unión para cambiarla."
            : $"Uniste {_pares.Count} de {_izq.Count}.";
        _quitar.IsVisible = Cx.Editable && _pares.Count > 0;
    }

    private static void Estilo(Border caja, bool elegida, bool unida)
    {
        caja.BackgroundColor = unida ? Ds.InfoSuave : Colors.White;
        caja.Stroke = elegida || unida ? VistasActividad.BrochaTinta : VistasActividad.BrochaReposo;
        caja.StrokeThickness = elegida ? 4 : unida ? 2.5 : 1.5;
    }

    private JsonElement Instantanea() =>
        VistasActividad.Json(new { pairs = _izq.Where(e => _pares.ContainsKey(e.Ref)).Select(e => new { leftId = e.Ref, rightId = _pares[e.Ref] }).ToArray() });

    private void Guardar()
    {
        if (!Cx.Editable || _pares.Count != _izq.Count) return;
        var json = Instantanea();
        var texto = json.GetRawText();
        if (texto == _ultimo) return;
        _ultimo = texto;
        Confirmar(json);
    }

    public override void Aplicar(JsonElement r)
    {
        if (r.ValueKind != JsonValueKind.Object || !r.TryGetProperty("pairs", out var parejas) || parejas.ValueKind != JsonValueKind.Array) return;
        _pares.Clear();
        foreach (var p in parejas.EnumerateArray())
        {
            if (p.ValueKind != JsonValueKind.Object) continue;
            var l = p.TryGetProperty("leftId", out var li) && li.ValueKind == JsonValueKind.String ? li.GetString() : null;
            var d = p.TryGetProperty("rightId", out var ri) && ri.ValueKind == JsonValueKind.String ? ri.GetString() : null;
            if (l is not null && d is not null && _izq.Any(x => x.Ref == l) && _der.Any(x => x.Ref == d) && !_pares.ContainsValue(d)) _pares[l] = d;
        }
        _elegida = null;
        Pintar();
        if (_pares.Count == _izq.Count) _ultimo = Instantanea().GetRawText();
    }
}

// --------------------------------------------------------------------------------------------- ordenar

/// <summary>
/// <c>ordenar</c> → <c>{"order":[ref…]}</c>. La lista sale en el orden en que llega; cada fila tiene «▲» y «▼» de tamaño táctil. Cada
/// movimiento se guarda al momento; «Listo» guarda el orden tal como está (quien cree que ya está bien no tiene que mover nada).
/// </summary>
internal sealed class EditorOrdenar : EditorPregunta
{
    private readonly List<ElementoAula> _orden;
    private readonly VerticalStackLayout _lista = new() { Spacing = 10 };
    private readonly Label _estado;
    private readonly VerticalStackLayout _vista = new() { Spacing = 14 };
    private string? _ultimo;

    public EditorOrdenar(PreguntaAula p, ContextoEditor cx) : base(p, cx)
    {
        _orden = [.. p.Elementos!];
        _estado = Ds.Secundario("Usa ▲ y ▼ para poner los elementos en orden.", 16 * cx.Escala);
        _vista.Add(_estado);
        _vista.Add(_lista);
        if (cx.Editable)
        {
            var listo = Ds.Boton("Listo, este es mi orden", Ds.Rango.Secondary, (_, _) => Guardar(), cx.Alto);
            listo.AutomationId = "act-orden-listo";
            listo.HorizontalOptions = LayoutOptions.Start;
            var capsula = Ds.Capsula(listo);
            capsula.HorizontalOptions = LayoutOptions.Start;
            _vista.Add(capsula);
        }
        Reconstruir();
    }

    public override View Vista => _vista;

    private void Reconstruir()
    {
        _lista.Children.Clear();
        var lado = Math.Max(48, Cx.AreaTactil);
        for (var i = 0; i < _orden.Count; i++)
        {
            var indice = i;
            var e = _orden[i];
            var fila = new Grid
            {
                ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Auto)],
                ColumnSpacing = 10,
            };
            fila.Add(VistasActividad.Insignia((i + 1).ToString(), 34, oscura: false, 17), 0, 0);
            var contenido = VistasActividad.TextoOImagen(Cx, e.Tramos, e.Texto, e.Url, e.TextoAlternativo, $"Elemento {i + 1}", 20 * Cx.Escala);
            contenido.VerticalOptions = LayoutOptions.Center;
            fila.Add(contenido, 1, 0);
            var texto = VistasActividad.Rotulo(e.Texto, e.TextoAlternativo, $"elemento {i + 1}");
            fila.Add(VistasActividad.BotonGlifo("▲", lado, $"Subir «{texto}»", () => Mover(indice, -1), Cx.Editable && i > 0), 2, 0);
            fila.Add(VistasActividad.BotonGlifo("▼", lado, $"Bajar «{texto}»", () => Mover(indice, +1), Cx.Editable && i < _orden.Count - 1), 3, 0);
            _lista.Add(new Border
            {
                BackgroundColor = Colors.White, Stroke = VistasActividad.BrochaReposo, StrokeThickness = 1.5, Padding = new Thickness(12, 8),
                MinimumHeightRequest = lado + 8, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = fila, AutomationId = $"act-orden-{e.Ref}",
            });
        }
    }

    private void Mover(int indice, int delta)
    {
        if (!Cx.Editable) return;
        var destino = indice + delta;
        if (destino < 0 || destino >= _orden.Count) return;
        (_orden[indice], _orden[destino]) = (_orden[destino], _orden[indice]);
        Reconstruir();
        Guardar();
    }

    private void Guardar()
    {
        if (!Cx.Editable) return;
        var json = VistasActividad.Json(new { order = _orden.Select(e => e.Ref).ToArray() });
        var texto = json.GetRawText();
        _estado.Text = "Tu orden está guardado. Puedes cambiarlo cuando quieras.";
        if (texto == _ultimo) return;
        _ultimo = texto;
        Confirmar(json);
    }

    public override void Aplicar(JsonElement r)
    {
        if (r.ValueKind != JsonValueKind.Object || !r.TryGetProperty("order", out var orden) || orden.ValueKind != JsonValueKind.Array) return;
        var refs = orden.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!).ToList();
        var porRef = _orden.ToDictionary(e => e.Ref);
        var nuevo = new List<ElementoAula>();
        foreach (var id in refs)
            if (porRef.TryGetValue(id, out var e) && !nuevo.Contains(e)) nuevo.Add(e);
        if (nuevo.Count != _orden.Count) return;   // una respuesta que no calza con la pregunta que llegó: se conserva lo que se ve
        _orden.Clear();
        _orden.AddRange(nuevo);
        Reconstruir();
        _ultimo = VistasActividad.Json(new { order = _orden.Select(e => e.Ref).ToArray() }).GetRawText();
        _estado.Text = "Tu orden está guardado. Puedes cambiarlo cuando quieras.";
    }
}

// ---------------------------------------------------------------------------------------------- abierta

/// <summary>
/// <c>abierta</c> (formato texto) → <c>{"text":"…"}</c>. Cuadro de texto con contador; se guarda al perder el foco, al cambiar de pregunta y
/// a los 2 s sin escribir. Un texto en blanco no se guarda. El tope de caracteres (<c>longitud_maxima</c>) lo aplica el propio cuadro.
/// </summary>
internal sealed class EditorAbierta : EditorPregunta
{
    private readonly Editor _texto;
    private readonly Label _contador;
    private readonly Reposo _reposo;
    private readonly VerticalStackLayout _vista = new() { Spacing = 8 };
    private string? _ultimoGuardado;
    private bool _aplicando;

    public EditorAbierta(PreguntaAula p, ContextoEditor cx) : base(p, cx)
    {
        _reposo = new Reposo(cx.Dispatcher, TimeSpan.FromSeconds(2), Guardar);
        _texto = new Editor
        {
            Placeholder = "Escribe tu respuesta aquí", PlaceholderColor = Ds.TintaSuave, FontFamily = Ds.FuenteRegular, FontSize = 21 * cx.Escala,
            TextColor = Ds.Tinta, BackgroundColor = Colors.Transparent, AutoSize = EditorAutoSizeOption.Disabled,
            HeightRequest = Math.Max(170, cx.AreaTactil * 3), IsReadOnly = !cx.Editable, AutomationId = "act-abierta",
        };
        if (p.LongitudMaxima is > 0) _texto.MaxLength = p.LongitudMaxima.Value;
        _contador = new Label { FontFamily = Ds.FuenteSecundaria(15), FontSize = 15 * cx.Escala, TextColor = Ds.TintaSuave, HorizontalOptions = LayoutOptions.End };
        _texto.TextChanged += (_, _) =>
        {
            Contar();
            if (!_aplicando) _reposo.Reiniciar();
        };
        _texto.Unfocused += (_, _) => Guardar();
        _vista.Add(VistasActividad.Caja(_texto, 170, new Thickness(12, 8)));
        _vista.Add(_contador);
        Contar();
    }

    public override View Vista => _vista;

    private void Contar()
    {
        var n = _texto.Text?.Length ?? 0;
        _contador.Text = P.LongitudMaxima is > 0 ? $"{n} de {P.LongitudMaxima} caracteres" : $"{n} caracteres";
    }

    private void Guardar()
    {
        _reposo.Detener();
        if (!Cx.Editable) return;
        var texto = _texto.Text ?? string.Empty;
        if (string.IsNullOrWhiteSpace(texto) || texto == _ultimoGuardado) return;
        _ultimoGuardado = texto;
        Confirmar(VistasActividad.Json(new { text = texto }));
    }

    public override void Vaciar() => Guardar();

    public override void Aplicar(JsonElement r)
    {
        if (r.ValueKind != JsonValueKind.Object || !r.TryGetProperty("text", out var t) || t.ValueKind != JsonValueKind.String) return;
        _aplicando = true;
        try { _texto.Text = t.GetString(); }
        finally { _aplicando = false; }
        _ultimoGuardado = t.GetString();
        Contar();
    }
}

// ------------------------------------------------------------------------------------------ no soportada

/// <summary>Una pregunta de un tipo que esta versión no sabe responder (o con datos que no sirven): se dice sin tecnicismos y no bloquea la entrega.</summary>
internal sealed class EditorNoSoportado : EditorPregunta
{
    private readonly View _vista;

    public EditorNoSoportado(PreguntaAula p, ContextoEditor cx) : base(p, cx)
    {
        _vista = new Border
        {
            BackgroundColor = Ds.Lienzo, StrokeThickness = 0, Padding = new Thickness(18, 16), AutomationId = "act-no-soportada",
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno },
            Content = Ds.Cuerpo("Esta pregunta se responde con tu profesor.", 19 * cx.Escala),
        };
    }

    public override View Vista => _vista;
}

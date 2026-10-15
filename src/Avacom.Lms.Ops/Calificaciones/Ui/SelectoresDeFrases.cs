using Avacom.Lms.Ops.Pages;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>
/// Una caja de texto OPCIONAL con el estilo del aula. El nodo principal no tiene teclado: nada puede exigir escribir, así que esto es siempre un extra junto a frases que
/// se tocan. Se crea UNA vez y no se mueve de contenedor: WinUI no deja pasar un cuadro de texto nativo de un contenedor a otro mientras el anterior sigue vivo.
/// </summary>
internal static class CajaDeTexto
{
    public static Entry Crear(string marcador, string descripcion, int largoMaximo = 300) => new()
    {
        Placeholder = marcador, FontSize = 17, FontFamily = Ds.FuenteRegular, TextColor = Ds.Tinta, HeightRequest = 52, BackgroundColor = Ds.Lienzo,
        IsSpellCheckEnabled = false, IsTextPredictionEnabled = false, MaxLength = largoMaximo, ReturnType = ReturnType.Done,
        AutomationId = "caja-" + descripcion.Replace(' ', '-').ToLowerInvariant(),
    };
}

/// <summary>
/// Frases que se eligen con el dedo, varias a la vez, y un campo de texto opcional debajo (comentarios pedagógicos de una revisión, fortalezas y dificultades de una
/// retroalimentación). Cada ficha lleva ✓ cuando está elegida: el estado no depende sólo del color. <see cref="Texto"/> junta las frases elegidas con lo escrito.
/// </summary>
internal sealed class SelectorDeFrases : ContentView
{
    private readonly IReadOnlyList<string> _frases;
    private readonly HashSet<string> _elegidas = [];
    private readonly FlexLayout _fichas = EstudioUi.Envolver();
    private readonly Entry? _texto;
    private readonly string _id;

    /// <summary>Cambió lo elegido o lo escrito.</summary>
    public event EventHandler? Cambio;

    public SelectorDeFrases(IReadOnlyList<string> frases, string id, string? marcadorDeTexto = "Escribe algo más (opcional)")
    {
        _frases = frases;
        _id = id;
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(_fichas);
        if (marcadorDeTexto is not null)
        {
            _texto = CajaDeTexto.Crear(marcadorDeTexto, id + " texto");
            _texto.TextChanged += (_, _) => Cambio?.Invoke(this, EventArgs.Empty);
            pila.Add(_texto);
        }
        Content = pila;
        Reconstruir();
    }

    /// <summary>Las frases elegidas y lo escrito, en un solo texto; nulo si no hay nada.</summary>
    public string? Texto => FrasesDeCalificaciones.Juntar(_frases.Where(_elegidas.Contains), _texto?.Text);

    public bool TieneAlgo => _elegidas.Count > 0 || !string.IsNullOrWhiteSpace(_texto?.Text);

    public void Limpiar()
    {
        var habia = TieneAlgo;
        _elegidas.Clear();
        if (_texto is not null) _texto.Text = string.Empty;
        Reconstruir();
        if (habia) Cambio?.Invoke(this, EventArgs.Empty);
    }

    private void Reconstruir()
    {
        _fichas.Clear();
        for (var i = 0; i < _frases.Count; i++)
        {
            var frase = _frases[i];
            _fichas.Add(EstudioUi.Chip(frase, _elegidas.Contains(frase), CalificacionesUi.Seguro(nameof(SelectorDeFrases), "Elegir", () => AlternarAsync(frase)), $"{_id}-frase-{i}"));
        }
    }

    private Task AlternarAsync(string frase)
    {
        if (!_elegidas.Add(frase)) _elegidas.Remove(frase);
        Reconstruir();
        Cambio?.Invoke(this, EventArgs.Empty);
        return Task.CompletedTask;
    }
}

/// <summary>
/// El MOTIVO de un cambio: una frase prehecha entre varias (una sola) y «Otro motivo», que abre un campo de texto opcional. Tocar una frase la elige; el motivo es obligatorio
/// pero nunca exige escribir (la propia frase «Otro motivo» ya es un motivo válido). Cada frase es una fila de ancho completo con ✓ cuando está elegida. Se crea una vez y
/// su campo de texto no cambia de contenedor.
/// </summary>
internal sealed class SelectorDeMotivo : ContentView
{
    private readonly IReadOnlyList<string> _frases;
    private readonly VerticalStackLayout _lista = new() { Spacing = 8 };
    private readonly Border _cajaDeTexto;
    private readonly Entry _texto;
    private readonly string _id;
    private string? _elegida;

    public event EventHandler? Cambio;

    /// <param name="frases">Las frases a elegir, SIN «Otro motivo»: el selector la añade al final.</param>
    public SelectorDeMotivo(IReadOnlyList<string> frases, string id)
    {
        _frases = frases;
        _id = id;
        _texto = CajaDeTexto.Crear("Escribe el motivo (opcional)", id + " otro motivo", 200);
        _texto.TextChanged += (_, _) => Cambio?.Invoke(this, EventArgs.Empty);
        _cajaDeTexto = new Border { StrokeThickness = 0, BackgroundColor = Colors.Transparent, Content = _texto, IsVisible = false };
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(_lista);
        pila.Add(_cajaDeTexto);
        Content = pila;
        Reconstruir();
    }

    /// <summary>El motivo final (la frase elegida, o «Otro motivo» con lo escrito); nulo si no se eligió ninguna.</summary>
    public string? Motivo => FrasesDeCalificaciones.MotivoFinal(_elegida, _texto.Text);

    public void Limpiar()
    {
        if (_elegida is null && string.IsNullOrEmpty(_texto.Text)) return;
        _elegida = null;
        _texto.Text = string.Empty;
        _cajaDeTexto.IsVisible = false;
        Reconstruir();
        Cambio?.Invoke(this, EventArgs.Empty);
    }

    private void Reconstruir()
    {
        _lista.Clear();
        var todas = _frases.Append(FrasesDeCalificaciones.OtroMotivo).ToList();
        for (var i = 0; i < todas.Count; i++)
        {
            var frase = todas[i];
            var elegida = _elegida == frase;
            var texto = new Label
            {
                Text = elegida ? $"✓  {frase}" : frase, FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, VerticalOptions = LayoutOptions.Center,
            };
            _lista.Add(EstudioUi.TarjetaElegible(texto, elegida, CalificacionesUi.Seguro(nameof(SelectorDeMotivo), "Elegir", () => ElegirAsync(frase)), frase, $"{_id}-motivo-{i}"));
        }
    }

    private Task ElegirAsync(string frase)
    {
        _elegida = _elegida == frase ? null : frase;
        _cajaDeTexto.IsVisible = _elegida == FrasesDeCalificaciones.OtroMotivo;
        Reconstruir();
        Cambio?.Invoke(this, EventArgs.Empty);
        return Task.CompletedTask;
    }
}

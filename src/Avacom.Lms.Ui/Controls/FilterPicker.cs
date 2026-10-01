using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Picklist de filtro neumórfico para la barra de búsqueda: una cápsula blanca con el bisel del kit y sombra suave
/// que envuelve un <see cref="Picker"/> sin cromo nativo (<see cref="NeumoChrome"/>). El primer elemento es siempre
/// <see cref="Placeholder"/> («Todos los países», «Todos los niveles»…) y significa «sin filtro»
/// (<see cref="Selected"/> devuelve null); los demás los pone <see cref="Poblar"/> con los valores distintos del
/// catálogo. Sin teclado: se elige tocando. <see cref="SelectionChanged"/> avisa sólo de cambios del usuario, no de
/// los que hace <see cref="Poblar"/> o <see cref="Reset"/>.
/// </summary>
public class FilterPicker : ContentView
{
    private readonly Picker lista;
    private readonly List<string> valores = new();
    private bool silencio;
    private string placeholder = "Todos";

    static FilterPicker() => NeumoChrome.Registrar();

    public FilterPicker()
    {
        lista = new Picker
        {
            ClassId = NeumoChrome.Clase, FontFamily = Ds.FuenteMedia, FontSize = 15, TextColor = Ds.Tinta, TitleColor = Ds.TintaSuave,
            BackgroundColor = Colors.Transparent, VerticalOptions = LayoutOptions.Center, HorizontalOptions = LayoutOptions.Fill,
        };
        lista.SelectedIndexChanged += (_, _) =>
        {
            if (!silencio) SelectionChanged?.Invoke(this, EventArgs.Empty);
        };
        Content = new Border
        {
            BackgroundColor = Colors.White,
            Stroke = Ds.Bisel(),
            StrokeThickness = 1.5,
            StrokeShape = new RoundRectangle { CornerRadius = 14 },
            Padding = new Thickness(10, 0),
            HeightRequest = 48,
            Shadow = new Shadow { Brush = new SolidColorBrush(Ds.Tinta), Offset = new Point(0, 4), Radius = 12, Opacity = 0.10f },
            Content = lista,
        };
        WidthRequest = 200;
        Poblar([]);
    }

    /// <summary>Cambio de selección hecho por el usuario.</summary>
    public event EventHandler? SelectionChanged;

    /// <summary>Texto del primer elemento, el que significa «sin filtro».</summary>
    public string Placeholder
    {
        get => placeholder;
        set
        {
            placeholder = value;
            Poblar(valores.ToList());
        }
    }

    /// <summary>Valor elegido, o null si está en «todos».</summary>
    public string? Selected => lista.SelectedIndex > 0 && lista.SelectedIndex - 1 < valores.Count ? valores[lista.SelectedIndex - 1] : null;

    /// <summary>Carga los valores (ya distintos y ordenados) y vuelve a «todos», sin avisar.</summary>
    public void Poblar(IEnumerable<string> nuevos)
    {
        silencio = true;
        try
        {
            valores.Clear();
            valores.AddRange(nuevos);
            lista.ItemsSource = new List<string>(valores.Prepend(placeholder));
            lista.SelectedIndex = 0;
            IsEnabled = valores.Count > 0;
        }
        finally { silencio = false; }
    }

    /// <summary>Deja elegido <paramref name="valor"/> si está entre los poblados (o «todos» si es null), sin avisar: para restaurar un filtro al repintar.</summary>
    public void Elegir(string? valor)
    {
        var indice = valor is null ? -1 : valores.IndexOf(valor);
        silencio = true;
        try { lista.SelectedIndex = indice < 0 ? 0 : indice + 1; }
        finally { silencio = false; }
    }

    /// <summary>Vuelve a «todos». Avisa sólo si se pide.</summary>
    public void Reset(bool notificar = false)
    {
        if (lista.SelectedIndex == 0) return;
        silencio = !notificar;
        try { lista.SelectedIndex = 0; }
        finally { silencio = false; }
    }
}

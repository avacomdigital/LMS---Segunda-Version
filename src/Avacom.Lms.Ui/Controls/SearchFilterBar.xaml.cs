namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Barra de búsqueda y filtros neumórfica (ver el XAML). Expone el texto de búsqueda (<see cref="Text"/>,
/// <see cref="TextChanged"/>), recibe los picklists con <see cref="AgregarFiltro"/> (principales o bajo «Más
/// filtros») y limpia todo con <see cref="Limpiar"/> (avisa con <see cref="LimpiarTapped"/>). El texto de búsqueda
/// es opcional: en el nodo del aula, sin teclado, los picklists son la vía táctil.
/// </summary>
public partial class SearchFilterBar : ContentView
{
    static SearchFilterBar() => NeumoChrome.Registrar();

    public SearchFilterBar() => InitializeComponent();

    /// <summary>Cambió el texto de búsqueda (también al limpiarlo).</summary>
    public event EventHandler<TextChangedEventArgs>? TextChanged;

    /// <summary>Se pulsó «Limpiar filtros»; los picklists ya están en «todos» y el texto vacío.</summary>
    public event EventHandler? LimpiarTapped;

    public string Text
    {
        get => Entrada.Text ?? string.Empty;
        set => Entrada.Text = value;
    }

    public string Placeholder
    {
        get => Entrada.Placeholder;
        set => Entrada.Placeholder = value;
    }

    /// <summary>Fila secundaria de filtros desplegada.</summary>
    public bool MasFiltrosVisible
    {
        get => ExtraFila.IsVisible;
        set
        {
            ExtraFila.IsVisible = value;
            MasBtn.Text = value ? "Menos filtros" : "Más filtros";
        }
    }

    /// <summary>Añade un picklist a la fila principal o, con <paramref name="extra"/>, a la de «Más filtros».</summary>
    public void AgregarFiltro(View filtro, bool extra = false) => (extra ? ExtraHost : FiltrosHost).Children.Add(filtro);

    /// <summary>Todos los picklists a «todos» (sin avisar cada uno) y el texto vacío.</summary>
    public void Limpiar()
    {
        foreach (var filtro in FiltrosHost.Children.Concat(ExtraHost.Children).OfType<FilterPicker>()) filtro.Reset();
        Entrada.Text = string.Empty;
    }

    private void OnTextoCambiado(object? sender, TextChangedEventArgs e) => TextChanged?.Invoke(this, e);

    private void OnMasFiltros(object? sender, EventArgs e) => MasFiltrosVisible = !MasFiltrosVisible;

    private void OnLimpiar(object? sender, EventArgs e)
    {
        Limpiar();
        LimpiarTapped?.Invoke(this, EventArgs.Empty);
    }
}

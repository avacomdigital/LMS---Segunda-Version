using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
namespace Avacom.Lms.Student.Pages;
public partial class ConnectionPage : ContentPage
{
    private readonly ILmsApiClient apiClient = new LmsApiClient(new HttpClient { Timeout = TimeSpan.FromSeconds(3) });
    private string? claveAplicada;
    public ConnectionPage() => InitializeComponent();
    private async void OnCheck(object? sender, EventArgs e)
    {
        CheckButton.IsEnabled = false; StatusLabel.Text = "●  Buscando el aula…";
        try { var ok = await apiClient.CheckHealthAsync(ConnectionOptions.Normalize(ServerEntry.Text ?? string.Empty)); StatusCard.BackgroundColor = Color.FromArgb(ok ? "#E6F5EE" : "#FDECEC"); StatusLabel.TextColor = Color.FromArgb(ok ? "#019D60" : "#E5262B"); StatusLabel.Text = ok ? "●  Conectado al aula correctamente" : "●  No encontramos el aula · revisa la dirección"; }
        catch (ArgumentException ex) { StatusLabel.Text = ex.Message; }
        finally { CheckButton.IsEnabled = true; }
    }
    private async void OnEnter(object? sender, EventArgs e)
    {
        if (string.IsNullOrWhiteSpace(NameEntry.Text)) { await DisplayAlertAsync("Falta tu nombre", "Escribe tu nombre para continuar.", "Entendido"); return; }
        Preferences.Default.Set("student_name", NameEntry.Text); Preferences.Default.Set("student_server", ServerEntry.Text ?? ConnectionOptions.Default.ServerAddress); await Shell.Current.GoToAsync("menu");
    }

    private void OnPageSizeChanged(object? sender, EventArgs e) => AjustarComposicion();

    /// <summary>
    /// La composición del XAML (tarjeta a la izquierda, lápiz a la derecha) es la de una pantalla ancha, como
    /// el acceso de OPS: a 1080p la tarjeta mide 2/3 del alto. La tableta también se usa en vertical y la ventana de Windows se
    /// puede achicar, así que aquí sólo se recolocan las mismas piezas: la tarjeta nunca baja del alto que pide el formulario
    /// (el resto es margen, repartido arriba y abajo); en vertical el lápiz pasa arriba y la tarjeta ocupa el ancho; y en una
    /// ventana muy baja se aprietan el logo, la descripción y el espaciado. Nada se quita ni cambia de función.
    /// </summary>
    private void AjustarComposicion()
    {
        if (Width <= 0 || Height <= 0) return;
        var esEstrecha = Width < 900 || Width < Height;
        var soloTarjeta = esEstrecha && Height < 940;                       // sin sitio para el lápiz: la tarjeta ocupa la ventana
        var altoTarjeta = Math.Min(Height - 48, Math.Max(Height * 2 / 3, 640));
        var margen = (Height - altoTarjeta) / 2;
        var esBaja = altoTarjeta < 640;                                     // ni siquiera el mínimo cabe: modo compacto
        Tarjeta.WidthRequest = esEstrecha ? Math.Min(560, Math.Max(280, Width - 48)) : -1;

        var clave = $"{esEstrecha}|{soloTarjeta}|{esBaja}|{(esEstrecha ? 0 : Math.Round(altoTarjeta))}";
        if (clave == claveAplicada) return;
        claveAplicada = clave;

        Escena.ColumnDefinitions = esEstrecha ? Columnas(1) : Columnas(1, 2, 1, 2);
        Escena.RowDefinitions = soloTarjeta ? Filas(1) : esEstrecha ? Filas(2, 5) : Filas(margen, altoTarjeta, margen);
        var columnas = esEstrecha ? 1 : 4; var filas = soloTarjeta ? 1 : esEstrecha ? 2 : 3;
        Colocar(Panal, 0, 0, filas, columnas);
        Colocar(Tarjeta, soloTarjeta ? 0 : 1, esEstrecha ? 0 : 1, 1, 1);
        Colocar(Lapiz, esEstrecha ? 0 : 1, esEstrecha ? 0 : 3, 1, 1);
        Lapiz.IsVisible = !soloTarjeta;
        Tarjeta.TranslationX = esEstrecha ? 0 : -50;
        Tarjeta.Margin = soloTarjeta ? new Thickness(24) : esEstrecha ? new Thickness(24, 0, 24, 24) : new Thickness(0);
        Tarjeta.HorizontalOptions = esEstrecha ? LayoutOptions.Center : LayoutOptions.Fill;
        Logo.HeightRequest = esBaja ? 64 : 100;
        Descripcion.IsVisible = !esBaja;
        Formulario.Spacing = esBaja ? 9 : 14;
    }

    private static ColumnDefinitionCollection Columnas(params double[] estrellas) => new(estrellas.Select(e => new ColumnDefinition(new GridLength(e, GridUnitType.Star))).ToArray());

    private static RowDefinitionCollection Filas(params double[] estrellas) => new(estrellas.Select(e => new RowDefinition(new GridLength(e, GridUnitType.Star))).ToArray());

    private static void Colocar(View vista, int fila, int columna, int filas, int columnas)
    {
        Grid.SetRow(vista, fila); Grid.SetColumn(vista, columna); Grid.SetRowSpan(vista, filas); Grid.SetColumnSpan(vista, columnas);
    }
}

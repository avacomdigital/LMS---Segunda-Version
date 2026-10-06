using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Student.Pages;

/// <summary>
/// «Diagnóstico de red» (depuración): el mismo panel de rendimiento que OPS muestra en Historial, para las pruebas de descarga de contenido y de red
/// desde la tableta: CPU, RAM, velocidad de bajada y de subida, latencia y pérdida hacia el nodo, disco, canal en tiempo real, latencia de aplicación y
/// errores. Student no tiene Historial, así que vive en su propia pantalla (dock «Ayuda» del menú, y en el acceso «Diagnóstico de red»). No exige teclado.
/// </summary>
public sealed class DiagnosticoRedPage : ContentPage
{
    private readonly PanelDeRendimiento panel;

    public DiagnosticoRedPage()
    {
        Shell.SetNavBarIsVisible(this, false);
        BackgroundColor = Ds.Lienzo;
        panel = new PanelDeRendimiento { App = "student", DescripcionDeConexiones = "canal de esta tableta con el aula", CarpetaDeExportacion = Path.Combine(FileSystem.AppDataDirectory, "diagnostico") };

        var volver = Ds.Boton("←  Volver", Ds.Rango.Quiet, async (_, _) => await Shell.Current.GoToAsync(".."), 52, 140);
        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 10, Margin = new Thickness(16, 12, 16, 0) };
        cabecera.Add(volver, 0, 0);
        var titulo = Ds.Titulo("Diagnóstico de red", 22);
        titulo.VerticalOptions = LayoutOptions.Center; titulo.HorizontalTextAlignment = TextAlignment.Center;
        cabecera.Add(titulo, 1, 0);

        var contenido = new VerticalStackLayout
        {
            Padding = new Thickness(20, 16, 20, 40), Spacing = 12, MaximumWidthRequest = 1300, HorizontalOptions = LayoutOptions.Center,
            Children = { Ds.Secundario("Para depurar la descarga de contenido y la red del aula. No cambia nada: sólo mide.", 14), panel },
        };
        Content = new Grid { RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Star)], Children = { cabecera, new ScrollView { Content = contenido } } };
        Grid.SetRow((View)((Grid)Content).Children[1], 1);
    }

    protected override void OnAppearing()
    {
        base.OnAppearing();
        Sesion.IniciarMonitor();
    }
}

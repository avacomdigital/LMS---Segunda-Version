using Avacom.Lms.Ui.Controls;

namespace Avacom.Lms.Ops.Pages;

public partial class DashboardPage : ContentPage
{
    public DashboardPage() => InitializeComponent();

    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0 || Height <= 0) return;
        var widthScale = Math.Max(0.55, (Width - 32) / 780d);
        var heightScale = Math.Max(0.55, (Height - 155) / 714d);
        MenuStage.Scale = Math.Min(1, Math.Min(widthScale, heightScale));
    }

    private async void OnModuleTapped(object? sender, EventArgs e)
    {
        if (sender is not ProfessorHexTile tile) return;
        switch (tile.Text)
        {
            case "Asignaturas":
                await Shell.Current.GoToAsync("asignaturas");
                break;
            case "Clase de hoy":
                await Shell.Current.GoToAsync("clase-hoy");
                break;
            case "Reportes":
                await Shell.Current.GoToAsync("activity-monitor");
                break;
            case "Dispositivos":
                await Shell.Current.GoToAsync("dispositivos");
                break;
            default:
                await DisplayAlertAsync(tile.Text, $"El módulo {tile.Text} está representado en este prototipo y listo para conectar su flujo.", "Entendido");
                break;
        }
    }

    private async void OnAssignmentsClicked(object? sender, EventArgs e) => await Shell.Current.GoToAsync("asignaturas");
    private async void OnClassTodayClicked(object? sender, EventArgs e) => await Shell.Current.GoToAsync("clase-hoy");
    private async void OnLogoutClicked(object? sender, EventArgs e) => await Shell.Current.GoToAsync("//login");
}

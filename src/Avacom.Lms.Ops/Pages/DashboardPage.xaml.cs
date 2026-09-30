using Avacom.Lms.Ui.Controls;

namespace Avacom.Lms.Ops.Pages;

public partial class DashboardPage : ContentPage
{
    private int _versionAviso;

    public DashboardPage() => InitializeComponent();

    protected override void OnAppearing()
    {
        base.OnAppearing();
        PintarPersona();
        if (Sesion.AvisoAlEntrar is { } aviso)
        {
            Sesion.AvisoAlEntrar = null;
            MostrarAviso(aviso);
        }
    }

    /// <summary>Con sesión de usuario (007-10) la cabecera muestra a quien entró; sin ella, la profesora de siempre del prototipo.</summary>
    private void PintarPersona()
    {
        if (Sesion.Usuario is not { } usuario) return;
        var nombre = Sesion.ProfesorRotulo;
        NombreLabel.Text = nombre;
        InicialesLabel.Text = Avacom.Lms.Core.Models.Identidad.InicialesDe(nombre);
        RolLabel.Text = usuario.Rol switch
        {
            "TEACHER" => "Profesorado",
            "ADMIN" => "Administración",
            "REPORTS" => "Reportes",
            "TECHNICIAN" => "Soporte técnico",
            _ => "Personal del aula",
        };
    }

    /// <summary>MSG-021: se ve unos segundos y se quita solo; el botón sólo lo adelanta.</summary>
    private async void MostrarAviso(string texto)
    {
        AvisoLabel.Text = texto;
        AvisoBanner.IsVisible = true;
        var version = ++_versionAviso;
        await Task.Delay(TimeSpan.FromSeconds(12));
        if (version == _versionAviso) AvisoBanner.IsVisible = false;
    }

    private void OnAvisoEntendido(object? sender, EventArgs e)
    {
        _versionAviso++;
        AvisoBanner.IsVisible = false;
    }

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
            case "Modo de estudio":
                await Shell.Current.GoToAsync("estudio");
                break;
            default:
                await DisplayAlertAsync(tile.Text, $"El módulo {tile.Text} está representado en este prototipo y listo para conectar su flujo.", "Entendido");
                break;
        }
    }

    private async void OnAssignmentsClicked(object? sender, EventArgs e) => await Shell.Current.GoToAsync("asignaturas");
    private async void OnClassTodayClicked(object? sender, EventArgs e) => await Shell.Current.GoToAsync("clase-hoy");
    /// <summary>Cerrar sesión avisa al nodo (si hay sesión de usuario) y suelta el pase antes de volver al acceso; la clase abierta sigue guardada.</summary>
    private async void OnLogoutClicked(object? sender, EventArgs e)
    {
        await Sesion.CerrarSesionDeUsuarioAsync();
        await Shell.Current.GoToAsync("//login");
    }
}

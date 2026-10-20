using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Acceso;
using Avacom.Lms.Ops.Licencia.Ui;
using Avacom.Lms.Ops.Busqueda;
using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ops.Reportes;
using Avacom.Lms.Ui.Controls;

namespace Avacom.Lms.Ops.Pages;

public partial class DashboardPage : ContentPage
{
    private int _versionAviso;
    private int _versionLicencia;

    public DashboardPage() => InitializeComponent();

    protected override void OnAppearing()
    {
        base.OnAppearing();
        PintarPersona();
        // MOD-019: el menú de la bitácora sólo para Administrador y Técnico (sin sesión obligatoria, el prototipo lo deja ver; el nodo decide).
        HistorialTile.IsVisible = Sesion.Usuario is null || Sesion.Usuario.Rol is "ADMIN" or "TECHNICIAN";
        // MOD-011: «Calificaciones» sólo para quien puede leer datos académicos (profesorado, administración y reportes; el rol técnico no). Sin sesión, se deja ver y el nodo decide.
        CalificacionesTile.IsVisible = CalificacionesUi.PuedeLeer;
        // MOD-013: «Reportes» con la misma regla que «Calificaciones» (profesorado, administración y reportes; ni el soporte técnico ni el alumno). Sin sesión, se deja ver y el nodo decide.
        ReportesTile.IsVisible = AccesoAReportes.Leer(Sesion.Usuario is not null, Sesion.Usuario?.Rol);
        // MOD-021: «Buscar» para quien puede buscar (profesorado, administración y reportes; ni el soporte técnico ni el alumno). Sin sesión, se deja ver y el nodo decide qué devuelve.
        BuscarTile.IsVisible = BusquedaUi.PuedeBuscar;
        // 019-01: este equipo se presenta ante el nodo como MASTER y entrega sus logs cada minuto, de mejor esfuerzo.
        _ = Sesion.RegistrarEquipoAsync();
        Sesion.EntregadorDeLogs.Iniciar();
        if (Sesion.AvisoAlEntrar is { } aviso)
        {
            Sesion.AvisoAlEntrar = null;
            MostrarAviso(aviso);
        }
        // RF-08: «Seguridad del aula» sólo para la administración.
        SeguridadButton.IsVisible = Sesion.Usuario?.EsAdministracion == true;
        _ = PintarAvisoDelPinAsync();
        // MOD-018: «Licencia» para la administración y el soporte técnico (sin sesión, se deja ver y el nodo decide), y su banda, nunca con una clase abierta en este equipo.
        LicenciaButton.IsVisible = ReglasDeLicencia.VeLaLicencia(Sesion.Usuario);
        _ = PintarAvisoDeLicenciaAsync();
        // Sólo con el perfil de pruebas de tests/Avacom.Lms.Ops.Uia (las teselas no se pueden tocar por UI Automation); sin él, nada.
        if (Ajustes.TomarRutaDePrueba() is { } ruta) Dispatcher.Dispatch(async () => await Shell.Current.GoToAsync(ruta));
    }

    /// <summary>
    /// RF-09 · RN-08: la banda del PIN maestro. Administración y técnico la ven a 30 días o menos del vencimiento, con el PIN vencido o si el equipo aún no
    /// tiene uno; la administración, además, con los días exactos (puede leer el estado fino). Al profesorado, nada.
    /// </summary>
    private async Task PintarAvisoDelPinAsync()
    {
        var usuario = Sesion.Usuario;
        if (usuario is null || !(usuario.EsAdministracion || usuario.EsTecnico)) { PinBanner.IsVisible = false; return; }
        var configuracion = await Sesion.ConsultarConfiguracionAsync() ?? Sesion.Configuracion;
        var publico = configuracion?.PinMaestro;
        EstadoPinMaestro? fino = null;
        if (usuario.EsAdministracion && publico is { Configurado: true } && (publico.PorVencer || publico.Vencido))
            fino = await Sesion.Acceso.EstadoPinMaestroAsync();
        var texto = AvisoDelPinMaestro.Texto(usuario, publico, fino);
        PinBannerLabel.Text = texto ?? string.Empty;
        PinBanner.IsVisible = texto is not null;
        PinBannerButton.IsVisible = usuario.EsAdministracion;
        PinBannerButton.Text = publico is { Configurado: false } ? "Configurarlo ahora" : "Cambiar ahora";
    }

    private async void OnSeguridadClicked(object? sender, EventArgs e) => await Shell.Current.GoToAsync("seguridad-aula");

    /// <summary>
    /// MOD-018 · R-01: la banda de la licencia, molde de la del PIN. Sólo para quien ve la licencia y NUNCA con una clase abierta en este equipo (<see cref="Sesion.ClaseAbiertaId"/>:
    /// lo que «Clase de hoy» ofrece continuar): ninguna alerta administrativa interrumpe una sesión activa. Se calcula sólo al aparecer el menú y muestra el aviso más importante de los
    /// que dio el nodo, con cuántos más hay. Si el nodo no contesta, no se pinta nada: no se inventa un aviso.
    /// </summary>
    private async Task PintarAvisoDeLicenciaAsync()
    {
        var version = ++_versionLicencia;
        try
        {
            if (!ReglasDeLicencia.MostrarBanner(Sesion.Usuario, Sesion.ClaseAbiertaId is not null)) { LicenciaBanner.IsVisible = false; return; }
            using var limite = new CancellationTokenSource(TimeSpan.FromSeconds(4));
            var estado = await Sesion.Licencia.EstadoAsync(Sesion.ProfesorId, limite.Token);
            // Al llegar la respuesta se vuelve a mirar: si mientras tanto se abrió una clase (o se salió del menú y se volvió), no se pinta esta.
            if (version != _versionLicencia) return;
            if (Sesion.ClaseAbiertaId is not null || ReglasDeLicencia.Banner(estado) is not { } banda) { LicenciaBanner.IsVisible = false; return; }
            var (fondo, tinta, filo) = LicenciaUi.ColoresDelBanner(banda.Tono);
            LicenciaBanner.BackgroundColor = fondo;
            LicenciaBanner.Stroke = new SolidColorBrush(filo);
            LicenciaBannerLabel.Text = banda.Completo;
            LicenciaBannerLabel.TextColor = tinta;
            LicenciaBannerButton.TextColor = tinta;
            LicenciaBanner.IsVisible = true;
        }
        catch (Exception ex)
        {
            LicenciaBanner.IsVisible = false;
            RegistroDeFallos.Escribir("ops", "DashboardPage.AvisoDeLicencia", ex);
        }
    }

    private async void OnLicenciaClicked(object? sender, EventArgs e)
    {
        try { await Shell.Current.GoToAsync("licencia"); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "DashboardPage.Licencia", ex); }
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
                await Shell.Current.GoToAsync(RutasDeReportes.Inicio);
                break;
            case "Dispositivos":
                await Shell.Current.GoToAsync("dispositivos");
                break;
            case "Grupos":
                await Shell.Current.GoToAsync("grupos");
                break;
            case "Modo de estudio":
                await Shell.Current.GoToAsync("estudio");
                break;
            case "Evaluaciones":
                await Shell.Current.GoToAsync("evaluaciones");
                break;
            case "Calificaciones":
                await Shell.Current.GoToAsync("calificaciones");
                break;
            case "Buscar":
                await Shell.Current.GoToAsync("buscar");
                break;
            case "Historial":
                await Shell.Current.GoToAsync("logs-bitacora");
                break;
            default:
                await DisplayAlertAsync(tile.Text, $"El módulo {tile.Text} está representado en este prototipo y listo para conectar su flujo.", "Entendido");
                break;
        }
    }

    private async void OnAssignmentsClicked(object? sender, EventArgs e) => await Shell.Current.GoToAsync("asignaturas");
    private async void OnGruposClicked(object? sender, EventArgs e) => await Shell.Current.GoToAsync("grupos");
    private async void OnClassTodayClicked(object? sender, EventArgs e) => await Shell.Current.GoToAsync("clase-hoy");
    /// <summary>Cerrar sesión avisa al nodo (si hay sesión de usuario) y suelta el pase antes de volver al acceso; la clase abierta sigue guardada.</summary>
    private async void OnLogoutClicked(object? sender, EventArgs e)
    {
        await Sesion.CerrarSesionDeUsuarioAsync();
        await Shell.Current.GoToAsync("//login");
    }
}

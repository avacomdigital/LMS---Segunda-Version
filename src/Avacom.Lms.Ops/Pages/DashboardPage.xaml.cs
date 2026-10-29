using Avacom.Lms.Core.Actualizacion;
using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Nodo;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Acceso;
using Avacom.Lms.Ops.Licencia.Ui;
using Avacom.Lms.Ops.Busqueda;
using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ops.Reportes;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

public partial class DashboardPage : ContentPage
{
    private int _versionAviso;
    private int _versionLicencia;
    private int _versionNodo;

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
        // «Agente»: sólo en modo docente (el profesorado; sin sesión, el prototipo lo deja ver).
        AgenteTile.IsVisible = Sesion.Usuario is null || Sesion.Usuario.Rol is "TEACHER";
        Recolocar();
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
        // MOD-017: «Actualizaciones» para la administración y el soporte técnico (update.read); el profesorado nunca la ve.
        ActualizacionesButton.IsVisible = ReglasDeActualizacion.VeLasActualizaciones(Sesion.Usuario);
        _ = PintarAvisoDeLicenciaAsync();
        // MOD-015: la banda del estado del nodo (restringido o en recuperación) para la administración y el técnico, nunca con una clase abierta en este equipo.
        _ = PintarAvisoDelNodoAsync();
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

    private async void OnActualizacionesClicked(object? sender, EventArgs e)
    {
        try { await Shell.Current.GoToAsync("actualizaciones"); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "DashboardPage.Actualizaciones", ex); }
    }

    private async void OnLicenciaClicked(object? sender, EventArgs e)
    {
        try { await Shell.Current.GoToAsync("licencia"); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "DashboardPage.Licencia", ex); }
    }

    /// <summary>
    /// MOD-015 · P-18: la banda del estado del nodo, molde de la del PIN. Sólo para quien ve el nodo (administración y técnico) y NUNCA con una clase abierta en este equipo. Se calcula
    /// al aparecer el menú leyendo el campo <c>nodo</c> de <c>/health/</c> (público, sin permiso y sin tocar la base) y sólo se muestra con «restringido» o «en recuperación»: si el
    /// nodo no contesta o está operativo, no se pinta nada (no se inventa un aviso).
    /// </summary>
    private async Task PintarAvisoDelNodoAsync()
    {
        var version = ++_versionNodo;
        try
        {
            if (!ReglasDeNodo.MostrarBanner(Sesion.Usuario, Sesion.ClaseAbiertaId is not null)) { NodoBanner.IsVisible = false; return; }
            using var limite = new CancellationTokenSource(TimeSpan.FromSeconds(4));
            var salud = await Sesion.Nodo.SaludAsync(limite.Token);
            if (version != _versionNodo) return;
            if (Sesion.ClaseAbiertaId is not null || ReglasDeNodo.Banner(salud) is not { } banda) { NodoBanner.IsVisible = false; return; }
            var (fondo, tinta, filo) = LicenciaUi.ColoresDelBanner(banda.Tono);
            NodoBanner.BackgroundColor = fondo;
            NodoBanner.Stroke = new SolidColorBrush(filo);
            NodoBannerLabel.Text = banda.Texto;
            NodoBannerLabel.TextColor = tinta;
            NodoBannerButton.TextColor = tinta;
            NodoBanner.IsVisible = true;
        }
        catch (Exception ex)
        {
            NodoBanner.IsVisible = false;
            RegistroDeFallos.Escribir("ops", "DashboardPage.AvisoDelNodo", ex);
        }
    }

    private async void OnNodoClicked(object? sender, EventArgs e)
    {
        try { await Shell.Current.GoToAsync("logs-bitacora"); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "DashboardPage.Nodo", ex); }
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

    // ------------------------------------------------------------------------------------------- barra inferior

    private bool _dockRecogido;
    private bool _dockAnimando;
    private List<(View Boton, double Ancho)>? _dockVisibles;

    /// <summary>
    /// «« / »»: recoge la barra inferior hasta dejar la marca y la flecha, o la despliega. La barra se encoge y se estira de
    /// forma continua: cada botón visible pasa de su ancho a cero (o al revés) mientras se funde, en 320 ms con CubicOut
    /// (movimiento lento del DS). Sólo cambia qué se ve: los que ya estaban ocultos siguen ocultos y ninguno pierde su acción.
    /// </summary>
    private async void OnDockColapsar(object? sender, EventArgs e)
    {
        if (_dockAnimando) return;
        _dockAnimando = true;
        _dockRecogido = !_dockRecogido;
        DockColapsarButton.Text = _dockRecogido ? "»" : "«";
        SemanticProperties.SetDescription(DockColapsarButton, _dockRecogido ? "Desplegar la barra" : "Recoger la barra");
        if (_dockRecogido)
            _dockVisibles = DockBotones.Children.OfType<Button>().Where(b => b != DockColapsarButton && b.IsVisible).Select(b => ((View)b, b.Width)).ToList();
        var piezas = _dockVisibles ?? [];
        if (!_dockRecogido)
            foreach (var (boton, _) in piezas) { boton.WidthRequest = 0; boton.MinimumWidthRequest = 0; boton.Opacity = 0; boton.IsVisible = true; }

        var fin = new TaskCompletionSource();
        var animacion = new Animation();
        foreach (var (boton, ancho) in piezas)
        {
            var (desde, hasta) = _dockRecogido ? (ancho, 0d) : (0d, ancho);
            if (_dockRecogido) boton.MinimumWidthRequest = 0;
            animacion.Add(0, 1, new Animation(v => boton.WidthRequest = v, desde, hasta));
            animacion.Add(_dockRecogido ? 0 : 0.35, _dockRecogido ? 0.65 : 1, new Animation(v => boton.Opacity = v, _dockRecogido ? 1 : 0, _dockRecogido ? 0 : 1));
        }
        animacion.Commit(this, "dock", 16, Ds.DurLenta, Easing.CubicOut, (_, _) => fin.TrySetResult());
        await fin.Task;

        foreach (var (boton, ancho) in piezas)
        {
            if (_dockRecogido) boton.IsVisible = false;
            boton.WidthRequest = -1;                 // vuelve a medir solo, como antes
            boton.MinimumWidthRequest = 118;
            boton.Opacity = 1;
        }
        _dockAnimando = false;
    }

    // ------------------------------------------------------------------------------------------------ panal

    /// <summary>Centro del panal y paso entre teselas (146 × 168 con 13 de separación: 159 en horizontal y 136,5 en vertical).</summary>
    private const double CentroX = 400, CentroY = 136.5, PasoX = 159, PasoY = 136.5;

    /// <summary>Huecos alrededor de «Clase de hoy», en el orden en que se llenan: el anillo de seis (en el sentido de las agujas
    /// del reloj desde arriba a la izquierda) y después los dos extremos de la fila de arriba, trabados con el anillo:
    /// cuatro arriba, tres en medio y dos abajo, simétrico y sin teselas sueltas. El último, a la derecha de la fila de abajo,
    /// sólo se usa sin sesión (el prototipo lo deja ver todo).</summary>
    private static readonly (double Dx, double Dy)[] Huecos =
    [
        (-0.5, -1), (0.5, -1), (1, 0), (0.5, 1), (-0.5, 1), (-1, 0), (-1.5, -1), (1.5, -1), (1.5, 1),
    ];

    /// <summary>
    /// Aula · Design System: «Clase de hoy» (el principal) en el centro exacto del panal y las demás teselas visibles alrededor,
    /// en este orden (colores vecinos distintos). Sólo mueve teselas: qué se ve lo decide cada regla de rol de <see cref="OnAppearing"/>.
    /// </summary>
    private void Recolocar()
    {
        AbsoluteLayout.SetLayoutBounds(ClaseHoyTile, new Rect(CentroX, CentroY, 146, 168));
        var alrededor = new ProfessorHexTile[] { GruposTile, AgenteTile, DispositivosTile, EvaluacionesTile, ReportesTile, CalificacionesTile, EstudioTile, HistorialTile, BuscarTile };
        var i = 0;
        foreach (var tesela in alrededor.Where(t => t.IsVisible).Take(Huecos.Length))
        {
            var (dx, dy) = Huecos[i++];
            AbsoluteLayout.SetLayoutBounds(tesela, new Rect(CentroX + dx * PasoX, CentroY + dy * PasoY, 146, 168));
        }
    }

    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0 || Height <= 0) return;
        // MOD-018 · U-2: las bandas persistentes (PIN, licencia, nodo) van en su propia fila encima del panal, así que lo que queda para el panal es la ventana menos ellas.
        // La fila mide 0 sin bandas; cuando una aparece, su SizeChanged vuelve a llamar aquí.
        var bandas = BandasPersistentes.Height > 0 ? BandasPersistentes.Height : 0;
        var widthScale = Math.Max(0.55, (Width - 32) / 946d);
        var heightScale = Math.Max(0.55, (Height - 236 - bandas) / 441d);   // 112 de cabecera (isla y esquinas) + 76 de barra a 28 del borde + aire
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
            case "Agente":
                await this.AlertaAsync("Agente", "El agente del aula llega muy pronto: te ayudará a preparar y acompañar tus clases.", "Entendido");
                break;
            default:
                await this.AlertaAsync(tile.Text, "Esta opción estará disponible muy pronto.", "Entendido");
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

using Avacom.Lms.Ui.Controls;
using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Student.Acceso;
namespace Avacom.Lms.Student.Pages;

/// <summary>
/// La pantalla de acceso de Student. Paso 0 (siempre): la dirección del aula y «Comprobar conexión». Después:
/// <list type="bullet">
/// <item>Modo prototipo (el nodo no exige sesión, Q-04): como siempre, se escribe el nombre y se entra.</item>
/// <item>Sesión obligatoria (RF-20…RF-28): dentro de la misma tarjeta, (1) elegir grupo, (2) tocar el nombre, (3) marcar el PIN con el teclado propio (o tocar
/// el dibujo en preescolar). «No estoy en la lista · soy nuevo» y «Entrar como visitante» quedan siempre a la vista; «Entrar con mi código» es la salida de
/// siempre. La lógica de los pasos vive en <see cref="FlujoDeAcceso"/> (probada sin interfaz); los pasos se pintan en <c>ConnectionPage.Pasos.cs</c>.</item>
/// </list>
/// </summary>
public partial class ConnectionPage : ContentPage
{
    private const string DescripcionPrototipo = "Escribe tu nombre y la dirección que aparece en la pantalla principal del profesor.";
    private const string DescripcionConSesion = "Escribe la dirección que aparece en la pantalla principal del profesor y toca «Entrar al aula».";
    private const string Verde = "#047857", VerdeSuave = "#E1F5EC", Rojo = "#C81E24", RojoSuave = "#FDE7E7", Azul = "#075985", AzulSuave = "#E3F5FC";

    private readonly ILmsApiClient apiClient = new LmsApiClient(new HttpClient { Timeout = TimeSpan.FromSeconds(3) });
    private string? claveAplicada;
    private Uri? direccionConsultada;   // el aula cuya configuración se leyó por última vez con éxito
    private bool exigeSesion;           // el aula pide identificarse (007-10, PAN-101): se entra por los pasos del acceso del alumno
    private bool entrando;
    private bool esBaja;                // ventana muy baja: logo chico y sin descripción
    private double anchoTarjeta;        // para repartir grupos, nombres y dibujos en columnas
    public ConnectionPage()
    {
        InitializeComponent();
    }

    /// <summary>
    /// Esta página vive mientras la app: al volver aquí («Salir» del menú, sesión terminada) no puede quedar nada de quien estuvo antes,
    /// porque la tableta es compartida (BR-053, JRN-022). Ni PIN ni clave se conservan (RF-00d); el código sólo cuando la misma persona vuelve a
    /// identificarse tras un aviso de sesión terminada; y el nombre del modo prototipo vuelve al valor por defecto si «Salir» lo borró.
    /// </summary>
    protected override void OnAppearing()
    {
        base.OnAppearing();
        if (!Preferences.Default.ContainsKey("student_name")) NameEntry.Text = ConnectionOptions.Default.StudentName;
        RecordarDireccionDelAula();
        AlVolverAlAcceso();
        if (TraspasoEntreApps.TomarDeLaLinea() is { } entrante) _ = CanjearEntranteAsync(entrante);
    }

    /// <summary>
    /// La dirección del aula es la de la institución, no la de una persona: se queda guardada aunque la app se cierre y la tableta la muestra al
    /// abrir (antes mostraba siempre la del XAML y había que escribirla en cada una de las tabletas cada vez que la app arrancaba). Sólo se
    /// sustituye si el campo sigue con la dirección de fábrica: lo que alguien escribió en esta misma ejecución no se pisa.
    /// </summary>
    private void RecordarDireccionDelAula()
    {
        try
        {
            if (!string.Equals(ServerEntry.Text?.Trim(), ConnectionOptions.Default.ServerAddress, StringComparison.OrdinalIgnoreCase)) return;
            var guardada = Preferences.Default.Get<string?>("student_server", null);
            if (!string.IsNullOrWhiteSpace(guardada)) ServerEntry.Text = guardada;
        }
        catch { /* sin preferencias legibles, se queda la de fábrica */ }
    }

    private async void OnCheck(object? sender, EventArgs e)
    {
        CheckButton.IsEnabled = false; Estado("●  Buscando el aula…", AzulSuave, Azul);
        try
        {
            var uri = ConnectionOptions.Normalize(ServerEntry.Text ?? string.Empty);
            var ok = await apiClient.CheckHealthAsync(uri);
            // Con el aula a la vista se lee lo que dice de sí misma: si exige sesión, después se elige grupo, nombre y PIN.
            var config = ok ? await LeerConfiguracionAsync(uri, TimeSpan.FromSeconds(3)) : null;
            if (ok) Estado("●  Conectado al aula correctamente" + (config?.SesionObligatoria == true ? " · toca «Entrar al aula»" : string.Empty), VerdeSuave, Verde);
            else Estado("●  No encontramos el aula · revisa la dirección", RojoSuave, Rojo);
        }
        catch (ArgumentException ex) { StatusLabel.Text = ex.Message; }
        finally { CheckButton.IsEnabled = true; }
    }

    /// <summary>Depuración: el panel de rendimiento y red (CPU, RAM, Mbps, latencia, errores…), disponible aun antes de entrar al aula.</summary>
    private async void OnDiagnosticoRed(object? sender, EventArgs e) => await Shell.Current.GoToAsync("diagnostico-red");

    /// <summary>MOD-019 §3.6: «Exportar diagnóstico», un ZIP con los logs del aparato (sin datos personales), la versión y la configuración no sensible.</summary>
    private void OnDiagnostico(object? sender, EventArgs e)
    {
        try
        {
            var carpeta = Path.Combine(FileSystem.AppDataDirectory, "diagnostico");
            var ruta = RegistroLocal.ExportarDiagnostico(Path.Combine(carpeta, $"diagnostico-student-{DateTime.Now:yyyyMMdd-HHmmss}.zip"),
                new { servidor = ServerEntry.Text, plataforma = Sesion.Plataforma, sesion_obligatoria = Sesion.SesionObligatoria, pendientes_de_entrega = RegistroLocal.CuentaPendientes });
            Estado($"●  Diagnóstico guardado en {ruta}", VerdeSuave, Verde);
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "ConnectionPage.Diagnostico", ex);
            Estado("●  No se pudo crear el diagnóstico", RojoSuave, Rojo);
        }
    }

    private void Estado(string texto, string fondo, string tinta)
    {
        StatusCard.BackgroundColor = Color.FromArgb(fondo); StatusLabel.TextColor = Color.FromArgb(tinta); StatusLabel.Text = texto;
    }

    /// <summary>
    /// Guarda la dirección (el cliente de acceso sale de ella), lee <c>/api/acceso/configuracion/</c> y ajusta el formulario. Nulo si el
    /// aula no contestó a tiempo: entonces todo sigue como siempre (modo prototipo / demo sin conexión).
    /// </summary>
    private async Task<ConfiguracionAcceso?> LeerConfiguracionAsync(Uri uri, TimeSpan espera)
    {
        Preferences.Default.Set("student_server", ServerEntry.Text ?? ConnectionOptions.Default.ServerAddress);
        try
        {
            using var tope = new CancellationTokenSource(espera);
            var config = await Sesion.Acceso.ConfiguracionAsync(tope.Token);
            if (config is null) return null;
            direccionConsultada = uri;
            AplicarConfiguracion(config);
            return config;
        }
        catch (OperationCanceledException) { return null; }
    }

    private void AplicarConfiguracion(ConfiguracionAcceso config)
    {
        exigeSesion = config.SesionObligatoria;
        Sesion.SesionObligatoria = exigeSesion;
        if (exigeSesion) PrepararFlujo(config);
        MostrarAcceso(exigeSesion);
    }

    /// <summary>Con sesión obligatoria el nombre libre desaparece del paso 0: quién eres se elige en los pasos siguientes. La composición de la tarjeta no cambia.</summary>
    private void MostrarAcceso(bool conSesion)
    {
        NombreBox.IsVisible = !conSesion; NotaDemo.IsVisible = !conSesion;
        if ((flujo?.Paso ?? PasoAcceso.Conexion) == PasoAcceso.Conexion) Descripcion.Text = conSesion ? DescripcionConSesion : DescripcionPrototipo;
    }

    private static bool TryNormalizar(string texto, out Uri uri)
    {
        try { uri = ConnectionOptions.Normalize(texto); return true; }
        catch (ArgumentException) { uri = null!; return false; }
    }

    private async void OnEnter(object? sender, EventArgs e)
    {
        if (entrando) return;
        entrando = true; EntrarButton.IsEnabled = false;
        try { await EntrarAsync(); }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "ConnectionPage.Entrar", ex);
            Estado("●  No pudimos entrar ahora · prueba otra vez en un momento", RojoSuave, Rojo);
        }
        finally { entrando = false; EntrarButton.IsEnabled = true; }
    }

    private async Task EntrarAsync()
    {
        var direccion = ServerEntry.Text ?? ConnectionOptions.Default.ServerAddress;
        // ¿El aula pide sesión? Se sabe al comprobar la conexión; si no se comprobó (o cambió la dirección) se pregunta ahora, con poca espera.
        // Si el aula no contesta, todo sigue como siempre: modo prototipo con el nombre escrito, o demo sin conexión.
        if (TryNormalizar(direccion, out var uri) && uri != direccionConsultada && await LeerConfiguracionAsync(uri, TimeSpan.FromSeconds(3)) is null)
        {
            exigeSesion = false; Sesion.SesionObligatoria = false; MostrarAcceso(false);
        }
        if (exigeSesion) await AbrirPasosAsync(direccion); else await EntrarSinSesionAsync(direccion);
    }

    /// <summary>Modo prototipo (Q-04, el aula no exige sesión): como siempre, sólo se pide el nombre.</summary>
    private async Task EntrarSinSesionAsync(string direccion)
    {
        if (string.IsNullOrWhiteSpace(NameEntry.Text)) { await this.AlertaAsync("Falta tu nombre", "Escribe tu nombre para continuar.", "Entendido"); return; }
        ClienteJson.Token = null; Sesion.Usuario = null;   // por si quedaba el pase de una sesión anterior
        Preferences.Default.Set("student_name", NameEntry.Text); Preferences.Default.Set("student_server", direccion); await Shell.Current.GoToAsync("menu");
    }

    /// <summary>
    /// El aula exige sesión (007-10, PAN-101): se entra por los pasos del acceso del alumno. El pase (JWT) queda en <c>ClienteJson.Token</c> y viaja en
    /// todas las peticiones; el nombre que se ve en el menú es el alias del usuario.
    /// </summary>
    private async Task AlEntrarAsync(SesionAcceso sesion)
    {
        // Un solo acceso para las dos apps: si la cuenta es del profesorado, su menú es el de AVACOM OPS. Se abre esa app con la misma sesión.
        if (TraspasoEntreApps.AppDe(sesion.Usuario) == AppDelAcceso.Ops)
        {
            await PasarAOpsAsync();
            return;
        }
        Sesion.Usuario = sesion.Usuario; Sesion.SesionObligatoria = true;
        // El nombre visible es el alias; el nombre escrito del modo prototipo no se usa con sesión.
        Preferences.Default.Remove("student_name");
        var aviso = AvisoDeSesionAnterior(sesion);
        await Shell.Current.GoToAsync("menu");
        // MSG-020: sin pedir ninguna confirmación que retrase el ingreso; un aviso tranquilizador que se va solo.
        if (aviso is not null) Avisos.Mostrar(aviso);
    }

    /// <summary>La cuenta es del profesorado: se abre AVACOM OPS con la misma sesión (sin pedir la clave otra vez). Si no se puede, se dice dónde entrar y se suelta el pase.</summary>
    private async Task PasarAOpsAsync()
    {
        Estado("●  Abriendo AVACOM OPS con tu sesión…", AzulSuave, Azul);
        var resultado = await TraspasoEntreApps.PasarAsync(Sesion.Acceso, AppDelAcceso.Ops, Sesion.BaseUri);
        if (resultado == ResultadoTraspaso.Abierta)
        {
            ClienteJson.Token = null; Sesion.Usuario = null;   // el nodo cerró esta sesión al canjearse el traspaso
            Estado("●  " + TraspasoEntreApps.MensajeSinTraspaso(AppDelAcceso.Ops, resultado), VerdeSuave, Verde);
            return;
        }
        await Sesion.CerrarSesionDeUsuarioAsync();
        Estado("●  " + TraspasoEntreApps.MensajeSinTraspaso(AppDelAcceso.Ops, resultado), RojoSuave, Rojo);
    }

    /// <summary>Student se abrió desde OPS con un código de traspaso (la cuenta es de alumno): se canjea y se entra al menú sin pedir nada.</summary>
    private async Task CanjearEntranteAsync(TraspasoEntrante entrante)
    {
        if (entrante.Servidor is { } servidor && TryNormalizar(servidor, out var uri))
        {
            Preferences.Default.Set("student_server", uri.ToString().TrimEnd('/'));
            ServerEntry.Text = uri.ToString().TrimEnd('/');
        }
        Estado("●  Entrando con tu sesión…", AzulSuave, Azul);
        var sesion = await Sesion.Acceso.CanjearTraspasoAsync(entrante.Codigo, Sesion.Dispositivo);
        if (sesion is null) { Estado("●  El traspaso no valió o ya caducó · entra con tu código", RojoSuave, Rojo); return; }
        await AlEntrarAsync(sesion);
    }

    /// <summary>MSG-020 · PAN-103: la sesión anterior de esta persona se cerró en otra tableta. Nada que hacer: todo su trabajo está a salvo.</summary>
    private static string? AvisoDeSesionAnterior(SesionAcceso sesion)
    {
        if (sesion.SesionAnterior is not { } anterior) return null;
        var donde = anterior.Dispositivo;
        // Si la sesión anterior era de esta misma tableta (la app se cerró sin «Salir») no hay nada que contar.
        if (!string.IsNullOrWhiteSpace(donde) && (string.Equals(donde, Sesion.Dispositivo, StringComparison.OrdinalIgnoreCase) || string.Equals(donde, DeviceInfo.Current.Name, StringComparison.OrdinalIgnoreCase))) return null;
        return $"Tenías tu sesión abierta en {(string.IsNullOrWhiteSpace(donde) ? "otra tableta" : Identidad.EquipoLegible(donde))}. Se cerró allí y todo tu trabajo está a salvo. Continúa aquí.";
    }

    private void OnPageSizeChanged(object? sender, EventArgs e) => AjustarComposicion();

    /// <summary>
    /// Composición del Aula · Design System (tableta), como el acceso de OPS: isla de marca arriba (fila de 86) y la tarjeta
    /// centrada en el área segura, de 560 de ancho como máximo (en vertical o en ventanas estrechas, el ancho disponible menos
    /// 24 por lado). La tarjeta nunca baja del alto que pide el formulario (640, que da cabida al teclado del PIN y a las dos
    /// acciones fijas); si ni eso cabe, modo compacto: se aprietan la descripción y el espaciado. Nada se quita ni cambia de función.
    /// </summary>
    private void AjustarComposicion()
    {
        if (Width <= 0 || Height <= 0) return;
        var altoTarjeta = Math.Max(320, Math.Min(Height - 86 - 24 - 16, 720));
        esBaja = altoTarjeta < 640;                                         // ni siquiera el mínimo cabe: modo compacto
        var ancho = Math.Min(560, Math.Max(280, Width - 48));
        var columnasAntes = ColumnasPara(anchoTarjeta, 170);
        anchoTarjeta = ancho;

        var clave = $"{esBaja}|{Math.Round(altoTarjeta)}|{Math.Round(ancho)}";
        if (clave == claveAplicada)
        {
            if (ColumnasPara(anchoTarjeta, 170) != columnasAntes) PintarPaso();
            return;
        }
        claveAplicada = clave;

        Colocar(Panal, 0, 0, 3, 1);
        Colocar(Tarjeta, 1, 0, 1, 1);
        Colocar(Lapiz, 1, 0, 1, 1);
        Lapiz.IsVisible = false;                                            // el DS no lleva el lápiz 3D: se conserva oculto
        Tarjeta.WidthRequest = ancho;
        AjustarAlto();
        Tarjeta.TranslationX = 0;
        Tarjeta.HorizontalOptions = LayoutOptions.Center;
        Descripcion.IsVisible = !esBaja;
        Formulario.Spacing = esBaja ? 8 : 14;
        // Compacto: título más pequeño y estado más bajo, para que «Entrar al aula» quede a la vista sin desplazar.
        Titulo.FontSize = esBaja ? 26 : 34;
        StatusCard.Padding = esBaja ? new Thickness(14, 8) : new Thickness(14);
        PintarPaso();
    }

    /// <summary>
    /// La tarjeta mide lo que su contenido (cabecera, paso en curso y pie), sin el blanco de un alto fijo; si no cabe en la ventana se
    /// reduce a escala, sin desplazamiento. Se recalcula al pintar cada paso y al cambiar el tamaño de la ventana.
    /// </summary>
    private void AjustarAlto()
    {
        if (Width <= 0 || Height <= 0 || Tarjeta.WidthRequest <= 0) return;
        Cabecera.Margin = new Thickness(0, VolverButton.IsVisible ? 30 : 0, 0, 0);
        var ancho = Tarjeta.WidthRequest - 2;
        double Alto(View v) => v.IsVisible ? ((IView)v).Measure(ancho, double.PositiveInfinity).Height : 0;
        var cuerpo = PasoScroll.IsVisible ? (View)PasoHost : Formulario;
        var alto = Alto((View)Cabecera.Parent) + Alto(cuerpo) + Alto(Pie) + 6;
        var maximo = Math.Max(320, Height - 86 - 24 - 16);
        // Si no cabe, la tarjeta conserva su alto y se reduce a escala hasta caber: nada se desplaza ni se corta.
        var escala = Math.Min(1, maximo / alto);
        var sobra = Math.Max(0, alto - (Height - 86 - 24)) / 2;
        Tarjeta.HeightRequest = alto;
        Tarjeta.Margin = new Thickness(0, -sobra, 0, -sobra);
        Tarjeta.Scale = escala;
    }

    /// <summary>Cuántas columnas de un ancho mínimo caben en lo útil de la tarjeta (sin los 40 + 40 de margen interior).</summary>
    private static int ColumnasPara(double anchoDeTarjeta, double minimo) =>
        anchoDeTarjeta <= 0 ? 2 : Math.Clamp((int)((anchoDeTarjeta - 80 + 10) / (minimo + 10)), 2, 4);

    private static void Colocar(View vista, int fila, int columna, int filas, int columnas)
    {
        Grid.SetRow(vista, fila); Grid.SetColumn(vista, columna); Grid.SetRowSpan(vista, filas); Grid.SetColumnSpan(vista, columnas);
    }
}

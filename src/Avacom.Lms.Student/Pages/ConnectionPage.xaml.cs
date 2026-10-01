using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
namespace Avacom.Lms.Student.Pages;
public partial class ConnectionPage : ContentPage
{
    private const string DescripcionPrototipo = "Escribe tu nombre y la dirección que aparece en la pantalla principal del profesor.";
    private const string DescripcionConSesion = "Escribe tu código, tu clave y la dirección que aparece en la pantalla principal del profesor.";
    private const string Verde = "#019D60", VerdeSuave = "#E6F5EE", Rojo = "#E5262B", RojoSuave = "#FDECEC", Azul = "#01A4E1", AzulSuave = "#E6F6FC";

    private readonly ILmsApiClient apiClient = new LmsApiClient(new HttpClient { Timeout = TimeSpan.FromSeconds(3) });
    private string? claveAplicada;
    private Uri? direccionConsultada;   // el aula cuya configuración se leyó por última vez con éxito
    private bool exigeSesion;           // el aula pide identificarse con código y clave (007-10, PAN-101)
    private bool entrando;
    public ConnectionPage()
    {
        InitializeComponent();
        CodigoEntry.Completed += (_, _) => ClaveEntry.Focus();   // «siguiente» del teclado pasa de «Tu código» a «Tu clave»
    }

    /// <summary>
    /// Esta página vive mientras la app: al volver aquí («Salir» del menú, sesión terminada) no puede quedar nada de quien estuvo antes,
    /// porque la tableta es compartida (BR-053, JRN-022). La clave nunca se conserva; el código sólo cuando la misma persona vuelve a
    /// identificarse tras un aviso de sesión terminada; y el nombre del modo prototipo vuelve al valor por defecto si «Salir» lo borró.
    /// </summary>
    protected override void OnAppearing()
    {
        base.OnAppearing();
        ClaveEntry.Text = string.Empty;
        if (!Sesion.RecordarCodigo) CodigoEntry.Text = string.Empty;
        Sesion.RecordarCodigo = false;
        if (!Preferences.Default.ContainsKey("student_name")) NameEntry.Text = ConnectionOptions.Default.StudentName;
    }

    private async void OnCheck(object? sender, EventArgs e)
    {
        CheckButton.IsEnabled = false; Estado("●  Buscando el aula…", AzulSuave, Azul);
        try
        {
            var uri = ConnectionOptions.Normalize(ServerEntry.Text ?? string.Empty);
            var ok = await apiClient.CheckHealthAsync(uri);
            // Con el aula a la vista se lee lo que dice de sí misma: si exige sesión, el formulario pide código y clave.
            var config = ok ? await LeerConfiguracionAsync(uri, TimeSpan.FromSeconds(3)) : null;
            if (ok) Estado("●  Conectado al aula correctamente" + (config?.SesionObligatoria == true ? " · escribe tu código y tu clave" : string.Empty), VerdeSuave, Verde);
            else Estado("●  No encontramos el aula · revisa la dirección", RojoSuave, Rojo);
        }
        catch (ArgumentException ex) { StatusLabel.Text = ex.Message; }
        finally { CheckButton.IsEnabled = true; }
    }

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
        // Perfiles.student.tipo_secreto == "PIN": la clave del alumno son sólo números, así que el teclado es el numérico.
        var esPin = config.Perfiles is { ValueKind: JsonValueKind.Object } perfiles
                    && perfiles.TryGetProperty("student", out var alumno) && alumno.ValueKind == JsonValueKind.Object
                    && alumno.TryGetProperty("tipo_secreto", out var tipo) && tipo.ValueKind == JsonValueKind.String && tipo.GetString() == "PIN";
        ClaveEntry.Keyboard = esPin ? Keyboard.Numeric : Keyboard.Default;
        MostrarAcceso(exigeSesion);
    }

    /// <summary>Con sesión obligatoria el nombre libre se cambia por «Tu código» y «Tu clave» (no hay modo demo). La composición de la tarjeta no cambia.</summary>
    private void MostrarAcceso(bool conSesion)
    {
        NombreBox.IsVisible = !conSesion; CodigoBox.IsVisible = conSesion; ClaveBox.IsVisible = conSesion; NotaDemo.IsVisible = !conSesion;
        Descripcion.Text = conSesion ? DescripcionConSesion : DescripcionPrototipo;
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
        if (exigeSesion) await EntrarConSesionAsync(direccion); else await EntrarSinSesionAsync(direccion);
    }

    /// <summary>Modo prototipo (Q-04, el aula no exige sesión): como siempre, sólo se pide el nombre.</summary>
    private async Task EntrarSinSesionAsync(string direccion)
    {
        if (string.IsNullOrWhiteSpace(NameEntry.Text)) { await DisplayAlertAsync("Falta tu nombre", "Escribe tu nombre para continuar.", "Entendido"); return; }
        ClienteJson.Token = null; Sesion.Usuario = null;   // por si quedaba el pase de una sesión anterior
        Preferences.Default.Set("student_name", NameEntry.Text); Preferences.Default.Set("student_server", direccion); await Shell.Current.GoToAsync("menu");
    }

    /// <summary>
    /// El aula exige sesión (007-10, PAN-101): se entra con el código y la clave de MOD-001. El pase (JWT) queda en <c>ClienteJson.Token</c>
    /// y viaja en todas las peticiones; el nombre que se ve en el menú es el alias del usuario.
    /// </summary>
    private async Task EntrarConSesionAsync(string direccion)
    {
        var codigo = (CodigoEntry.Text ?? string.Empty).Trim();
        var clave = ClaveEntry.Text ?? string.Empty;
        if (codigo.Length == 0 || clave.Length == 0)
        {
            Estado("●  Este aula pide tu código y tu clave para entrar", AzulSuave, Azul);
            (codigo.Length == 0 ? CodigoEntry : ClaveEntry).Focus();
            return;
        }

        Estado("●  Abriendo tu sesión…", AzulSuave, Azul);
        Preferences.Default.Set("student_server", direccion);
        var acceso = Sesion.Acceso;
        var sesion = await acceso.IniciarSesionAsync(codigo, clave, Sesion.Dispositivo);
        if (sesion is null)
        {
            ClaveEntry.Text = string.Empty;
            Estado("●  " + MensajeDeAcceso(acceso.UltimoError), RojoSuave, Rojo);
            if (acceso.UltimoError is { Codigo: "credenciales_invalidas" }) ClaveEntry.Focus();
            return;
        }

        Sesion.Usuario = sesion.Usuario; Sesion.SesionObligatoria = true;
        // El nombre visible es el alias; sin alias se usa el código para no mostrar el nombre por defecto de otra persona.
        if (string.IsNullOrWhiteSpace(sesion.Usuario.Alias)) Preferences.Default.Set("student_name", codigo); else Preferences.Default.Remove("student_name");
        ClaveEntry.Text = string.Empty;
        Estado("●  Conectado al aula correctamente", VerdeSuave, Verde);
        var aviso = AvisoDeSesionAnterior(sesion);
        await Shell.Current.GoToAsync("menu");
        // MSG-020: sin pedir ninguna confirmación que retrase el ingreso; un aviso tranquilizador que se va solo.
        if (aviso is not null) Avisos.Mostrar(aviso);
    }

    /// <summary>MSG-020 · PAN-103: la sesión anterior de esta persona se cerró en otra tableta. Nada que hacer: todo su trabajo está a salvo.</summary>
    private static string? AvisoDeSesionAnterior(SesionAcceso sesion)
    {
        if (sesion.SesionAnterior is not { } anterior) return null;
        var donde = anterior.Dispositivo;
        // Si la sesión anterior era de esta misma tableta (la app se cerró sin «Salir») no hay nada que contar.
        if (!string.IsNullOrWhiteSpace(donde) && (string.Equals(donde, Sesion.Dispositivo, StringComparison.OrdinalIgnoreCase) || string.Equals(donde, DeviceInfo.Current.Name, StringComparison.OrdinalIgnoreCase))) return null;
        return $"Tenías tu sesión abierta en {(string.IsNullOrWhiteSpace(donde) ? "otra tableta" : donde)}. Se cerró allí y todo tu trabajo está a salvo. Continúa aquí.";
    }

    /// <summary>MSG-022 y compañía, sin códigos ni la palabra «error»: qué pasó y qué sigue.</summary>
    private static string MensajeDeAcceso(ErrorAula? error)
    {
        if (error is null || error.Estado == 0) return "No encontramos el aula · revisa la dirección";
        switch (error.Codigo)
        {
            case "credenciales_invalidas":
                var texto = "Ese código o esa clave no coinciden. Prueba otra vez o pide ayuda a tu profesor.";
                return error.Numero("intentos_restantes") is { } restantes and > 0 ? texto + (restantes == 1 ? " Te queda 1 intento." : $" Te quedan {restantes} intentos.") : texto;
            case "usuario_bloqueado":
                return error.Numero("reintentar_en_seg") is { } segundos and > 0
                    ? $"Demasiados intentos. Espera {Math.Max(1, (int)Math.Ceiling(segundos / 60.0))} min o pide a tu profesor que te ayude."
                    : "Demasiados intentos. Pide a tu profesor que te ayude.";
            case "dispositivo_bloqueado" or "dispositivo_inactivo":
                // UXR-007: la tableta nunca aparece bloqueada ni ocupada ante el alumno.
                return "No pudimos abrir tu sesión en esta tableta. Avisa a tu profesor; tu trabajo está a salvo.";
            default:
                return "No pudimos abrir tu sesión ahora mismo. Prueba otra vez en un momento o pide ayuda a tu profesor.";
        }
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

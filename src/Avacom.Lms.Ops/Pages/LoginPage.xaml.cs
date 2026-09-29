using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Acceso de OPS. Con el nodo en modo prototipo (sin sesión obligatoria) todo sigue como siempre: «Comprobar» sondea /health/ e
/// «Iniciar como profesor» entra sin credenciales. Cuando el nodo exige sesión (007-10), «Comprobar» lo dice y «Iniciar como
/// profesor» abre, en la MISMA tarjeta, los campos Documento y Clave: es la única pantalla de OPS que pide escribir. El pase (JWT)
/// queda en <see cref="ClienteJson.Token"/> y la persona en <see cref="Sesion.Usuario"/>; sólo entra personal (nivel 2 o más).
/// Los mensajes no llevan códigos ni la palabra «error» (UXR-009) y dicen qué pasó y qué sigue (UXR-005).
/// </summary>
public partial class LoginPage : ContentPage
{
    private readonly ILmsApiClient apiClient = new LmsApiClient(new HttpClient { Timeout = TimeSpan.FromSeconds(3) });
    private bool _ocupado;

    private enum Tono { Neutro, Bien, Aviso, Problema }

    public LoginPage() => InitializeComponent();

    protected override void OnAppearing()
    {
        base.OnAppearing();
        // La clave nunca queda escrita, y el documento tampoco cuando alguien cierra su sesión a propósito: el equipo lo usa mucha gente.
        ClaveEntry.Text = string.Empty;
        if (Sesion.AvisoDeAcceso is { } aviso)
        {
            // La sesión terminó por fuera (caducó, se cerró por inactividad, se abrió en otro equipo): mensaje suave y directo a los campos.
            Sesion.AvisoDeAcceso = null;
            MostrarCredenciales(Sesion.SesionObligatoria);
            Estado(aviso, Tono.Aviso);
        }
        else DocumentoEntry.Text = string.Empty;
    }

    private async void OnCheckConnection(object? sender, EventArgs e)
    {
        if (_ocupado) return;
        _ocupado = true;
        CheckButton.IsEnabled = false; Estado("Comprobando el servicio local…", Tono.Neutro);
        try
        {
            var healthy = await apiClient.CheckHealthAsync(ConnectionOptions.Normalize(ServerEntry.Text ?? string.Empty));
            if (!healthy) { Estado("No fue posible conectar · revisa red, IP y puerto", Tono.Problema); return; }
            // El nodo contesta: se guarda la dirección (Sesion.Acceso habla con ella) y se le pregunta si exige sesión.
            Preferences.Default.Set("ops_server", ServerEntry.Text ?? Sesion.DireccionPorDefecto);
            var configuracion = await ConsultarConfiguracionAsync();
            Sesion.SesionObligatoria = configuracion?.SesionObligatoria == true;
            Estado(Sesion.SesionObligatoria ? "Conexión exitosa · este equipo pide identificarte con tu documento y tu clave" : "Conexión exitosa · API disponible", Tono.Bien);
        }
        catch (ArgumentException ex) { Estado(ex.Message, Tono.Problema); }
        finally { CheckButton.IsEnabled = true; _ocupado = false; }
    }

    /// <summary>«Iniciar como profesor»: si el nodo exige sesión pide documento y clave; si no (o si no contesta), entra como siempre.</summary>
    private async void OnEnterDemo(object? sender, EventArgs e)
    {
        if (_ocupado) return;
        _ocupado = true;
        IniciarButton.IsEnabled = false;
        try
        {
            Preferences.Default.Set("ops_server", ServerEntry.Text ?? Sesion.DireccionPorDefecto);
            Estado("Consultando al aula…", Tono.Neutro);
            var configuracion = await ConsultarConfiguracionAsync();
            Sesion.SesionObligatoria = configuracion?.SesionObligatoria == true;
            if (Sesion.SesionObligatoria)
            {
                MostrarCredenciales(true);
                Estado("Este equipo pide identificarte. Escribe tu documento y tu clave.", Tono.Neutro);
                return;
            }
            await Shell.Current.GoToAsync("dashboard");
        }
        finally { IniciarButton.IsEnabled = true; _ocupado = false; }
    }

    private void OnDocumentoCompleted(object? sender, EventArgs e) => ClaveEntry.Focus();

    private async void OnEntrar(object? sender, EventArgs e)
    {
        if (_ocupado) return;
        var documento = (DocumentoEntry.Text ?? string.Empty).Trim();
        var clave = ClaveEntry.Text ?? string.Empty;
        if (documento.Length == 0 || clave.Length == 0)
        {
            Estado("Escribe tu documento y tu clave para entrar.", Tono.Aviso);
            (documento.Length == 0 ? DocumentoEntry : ClaveEntry).Focus();
            return;
        }
        _ocupado = true;
        EntrarButton.IsEnabled = false;
        Estado("Comprobando tus datos…", Tono.Neutro);
        try
        {
            Preferences.Default.Set("ops_server", ServerEntry.Text ?? Sesion.DireccionPorDefecto);
            var acceso = Sesion.Acceso;
            var sesion = await acceso.IniciarSesionAsync(documento, clave, Sesion.Dispositivo);
            var error = acceso.UltimoError;
            // La clave se borra siempre, salvo que no se haya podido preguntar (sin conexión): así se reintenta sin volver a escribirla.
            if (sesion is not null || error is { Estado: > 0 }) ClaveEntry.Text = string.Empty;
            if (sesion is null)
            {
                Estado(MensajeDeAcceso(error), Tono.Problema);
                return;
            }
            if (sesion.Usuario.Nivel < 2)
            {
                // Un alumno no entra al nodo del profesor: se suelta el pase que acaba de recibir.
                await Sesion.CerrarSesionDeUsuarioAsync();
                Estado("Esta pantalla es del profesorado. Usa la tableta del alumno.", Tono.Aviso);
                return;
            }
            Sesion.Usuario = sesion.Usuario;
            Sesion.SesionObligatoria = true;
            // MSG-021: si esta entrada cerró la clase abierta en otro equipo, el tablero lo cuenta una vez, sin pedir confirmación.
            Sesion.AvisoAlEntrar = sesion.SesionAnterior is { } anterior
                ? $"Cerramos tu clase abierta en {NombreDeEquipo(anterior.Dispositivo)}. Continúa aquí sin perder nada."
                : null;
            Estado("Listo · entrando", Tono.Bien);
            await Shell.Current.GoToAsync("dashboard");
        }
        finally { EntrarButton.IsEnabled = true; _ocupado = false; }
    }

    private void OnCambiarServidor(object? sender, EventArgs e)
    {
        MostrarCredenciales(false);
        Estado("Sin comprobar · modo demo disponible", Tono.Neutro);
    }

    /// <summary>Le pregunta al nodo si exige sesión, sin esperar más de 4 s. Nulo si no contesta o es un nodo anterior a esta pregunta.</summary>
    private static async Task<ConfiguracionAcceso?> ConsultarConfiguracionAsync()
    {
        using var limite = new CancellationTokenSource(TimeSpan.FromSeconds(4));
        return await Sesion.Acceso.ConfiguracionAsync(limite.Token);
    }

    /// <summary>Muestra los campos de acceso en lugar de la dirección y los botones de conexión (o los devuelve).</summary>
    private void MostrarCredenciales(bool mostrar)
    {
        CredencialesGrupo.IsVisible = mostrar;
        DireccionGrupo.IsVisible = !mostrar;
        AccionesGrupo.IsVisible = !mostrar;
        if (mostrar) (string.IsNullOrEmpty(DocumentoEntry.Text) ? DocumentoEntry : ClaveEntry).Focus();
    }

    /// <summary>Qué le pasó a quien intentó entrar, en palabras de aula: sin códigos, sin «error», con lo que puede hacer ahora.</summary>
    private static string MensajeDeAcceso(ErrorAula? error)
    {
        if (error is null) return "No pudimos abrir tu sesión ahora. Vuelve a intentarlo en un momento.";
        if (error.Estado == 0) return "No hay conexión con el aula. Revisa que el equipo del aula esté encendido y en la misma red.";
        switch (error.Codigo)
        {
            case "credenciales_invalidas":
                return error.Numero("intentos_restantes") switch
                {
                    1 => "Ese documento o esa clave no coinciden. Te queda 1 intento.",
                    > 1 and var quedan => $"Ese documento o esa clave no coinciden. Te quedan {quedan} intentos.",
                    _ => "Ese documento o esa clave no coinciden.",
                };
            case "usuario_bloqueado":
                return error.Numero("reintentar_en_seg") is { } segundos and > 0
                    ? $"Demasiados intentos. Vuelve a intentarlo en {Math.Max(1, (segundos + 59) / 60)} min."
                    : "Tu cuenta está bloqueada. Pide a la administración que la desbloquee.";
            case "demasiados_intentos":
                return error.Numero("reintentar_en_ms") is { } milisegundos and > 0
                    ? $"Demasiados intentos. Vuelve a intentarlo en {Math.Max(1, (milisegundos + 59_999) / 60_000)} min."
                    : "Demasiados intentos. Espera unos minutos y vuelve a intentarlo.";
            case "no_instalado":
                return "Este equipo todavía no tiene la escuela instalada. Avisa a la administración.";
            default:
                return "No pudimos abrir tu sesión ahora. Vuelve a intentarlo en un momento.";
        }
    }

    /// <summary>El equipo donde estaba la otra sesión, sin el prefijo interno de la app («ops-», «student-»).</summary>
    private static string NombreDeEquipo(string? dispositivo)
    {
        if (string.IsNullOrWhiteSpace(dispositivo)) return "otro equipo";
        foreach (var prefijo in new[] { "ops-", "student-" })
            if (dispositivo.StartsWith(prefijo, StringComparison.OrdinalIgnoreCase) && dispositivo.Length > prefijo.Length)
                return dispositivo[prefijo.Length..];
        return dispositivo;
    }

    private void Estado(string texto, Tono tono)
    {
        var (fondo, punto, glifo) = tono switch
        {
            Tono.Bien => ("#E6F5EE", "#019D60", "✓"),
            Tono.Aviso => ("#FEF9E6", "#9A7B00", "!"),
            Tono.Problema => ("#FDECEC", "#E5262B", "!"),
            _ => ("#F1F1F1", "#52525B", "●"),
        };
        StatusCard.BackgroundColor = Color.FromArgb(fondo);
        StatusDot.TextColor = Color.FromArgb(punto);
        StatusDot.Text = glifo;
        StatusLabel.Text = texto;
    }
}

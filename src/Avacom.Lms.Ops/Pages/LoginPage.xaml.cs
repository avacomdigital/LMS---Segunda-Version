using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Acceso;
namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Acceso de OPS (RF-05). Al aparecer pregunta al nodo por su configuración, sin que nadie toque nada:
/// <list type="bullet">
/// <item>sin instalar → abre sola el primer arranque (RF-01); con una hoja de acceso sin confirmar, vuelve directo a ella (RF-03);</item>
/// <item>con sesión obligatoria → documento y contraseña, el MISMO acceso para profesorado, administración y técnico (el nodo sabe quién es por la cuenta),
/// y siempre a la vista «Crear mi usuario» y «Olvidé mi contraseña» (<see cref="OfertaDeCuenta"/>);</item>
/// <item>en modo prototipo → «Iniciar como profesor» sin credenciales, como siempre; si el nodo no contesta, lo dice y deja reintentar: nunca simula un acceso.</item>
/// </list>
/// La administración entra además con el PIN maestro: si el nodo contesta <c>pin_maestro_requerido</c> (después de comprobar la contraseña) la tarjeta muestra
/// el teclado propio de seis puntos y reenvía lo mismo con el PIN. Una contraseña provisional (la de la hoja) lleva a «Elige tu contraseña» antes del tablero.
/// Ni la contraseña ni el PIN quedan escritos tras usarse (RF-00d). Los mensajes salen de <see cref="MensajesDeAcceso"/> (UXR-005/009).
/// </summary>
public partial class LoginPage : ContentPage
{
    private readonly ILmsApiClient apiClient = new LmsApiClient(new HttpClient { Timeout = TimeSpan.FromSeconds(3) });
    private bool _ocupado;
    // Mientras se marca el PIN maestro: lo que ya se escribió, sólo en memoria. Se borra al entrar, al volver o al salir de la pantalla.
    private string? _documentoEnEspera, _claveEnEspera;
    private string? _avisoAlTocar;

    private enum Tono { Neutro, Bien, Aviso, Problema }

    public LoginPage()
    {
        InitializeComponent();
        ServerEntry.Text = Ajustes.ServidorDePrueba ?? Ajustes.Get("ops_server", Sesion.DireccionPorDefecto);
        ServerEntry.IsReadOnly = Ajustes.ServidorDePrueba is not null;
        if (Ajustes.ClavesVisiblesDePrueba) ClaveEntry.IsPassword = false;   // sólo el recorrido de UI Automation (ver Ajustes)
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        // La contraseña y el PIN nunca quedan escritos, y el documento tampoco cuando alguien cierra su sesión a propósito: el equipo lo usa mucha gente.
        ClaveEntry.Text = string.Empty;
        SalirDelPin();
        // RN-11: el nodo sólo acepta el PIN maestro de un equipo que sabe que NO es una tableta de alumno. Se presenta ya, mientras la persona escribe.
        _ = Sesion.RegistrarEquipoAsync();
        var conservarEstado = false;
        if (Sesion.AvisoDeAcceso is { } aviso)
        {
            // La sesión terminó por fuera (caducó, se cerró por inactividad, se abrió en otro equipo) o algo acaba de terminar bien: se dice una vez.
            Sesion.AvisoDeAcceso = null;
            MostrarCredenciales(Sesion.SesionObligatoria);
            Estado(aviso, aviso.StartsWith("Listo", StringComparison.Ordinal) ? Tono.Bien : Tono.Aviso);
            conservarEstado = true;
        }
        else DocumentoEntry.Text = string.Empty;

        // Un traspaso desde Student (la persona entró allí con su documento y su clave y su cuenta es de OPS): se canjea sin pedir nada.
        if (TraspasoEntreApps.TomarDeLaLinea() is { } entrante && await CanjearEntranteAsync(entrante)) return;

        if (await PrimerArranquePage.HayHojaPendienteAsync())
        {
            await Shell.Current.GoToAsync("primer-arranque");
            return;
        }
        await ComprobarEnSilencioAsync(conservarEstado);
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        ClaveEntry.Text = string.Empty;
        SalirDelPin();
    }

    /// <summary>Pregunta al nodo guardado qué ofrece, sin tocar nada. Si no contesta, deja la dirección y «Comprobar conexión» para reintentar.</summary>
    private async Task ComprobarEnSilencioAsync(bool conservarEstado)
    {
        if (_ocupado) return;
        _ocupado = true;
        try
        {
            if (!conservarEstado) Estado("Comprobando la conexión con el aula…", Tono.Neutro);
            var configuracion = await Sesion.ConsultarConfiguracionAsync();
            if (configuracion is null)
            {
                MostrarCredenciales(false);
                MostrarPrototipo(false);
                if (!conservarEstado) Estado(MensajesDeAcceso.SinConexion + " Revisa la dirección y toca «Comprobar conexión».", Tono.Problema);
                return;
            }
            if (!configuracion.Instalado)
            {
                await Shell.Current.GoToAsync("primer-arranque");
                return;
            }
            AplicarConfiguracion(configuracion, conservarEstado);
        }
        finally { _ocupado = false; }
    }

    private void AplicarConfiguracion(ConfiguracionAcceso configuracion, bool conservarEstado)
    {
        PintarOferta(configuracion);
        if (configuracion.SesionObligatoria)
        {
            MostrarPrototipo(false);
            MostrarCredenciales(true);
            if (!conservarEstado) Estado("Escribe tu documento y tu contraseña para entrar.", Tono.Neutro);
        }
        else
        {
            MostrarCredenciales(false);
            MostrarPrototipo(true);
            if (!conservarEstado) Estado("Conexión exitosa · API disponible", Tono.Bien);
        }
    }

    private async void OnCheckConnection(object? sender, EventArgs e)
    {
        if (_ocupado) return;
        _ocupado = true;
        CheckButton.IsEnabled = false; Estado("Comprobando el servicio local…", Tono.Neutro);
        try
        {
            var healthy = await apiClient.CheckHealthAsync(ConnectionOptions.Normalize(ServerEntry.Text ?? string.Empty));
            if (!healthy) { Estado("No fue posible conectar · revisa red, IP y puerto", Tono.Problema); MostrarPrototipo(false); return; }
            // El nodo contesta: se guarda la dirección (Sesion.Acceso habla con ella) y se le pregunta qué ofrece.
            Sesion.GuardarServidor(ServerEntry.Text);
            _ = Sesion.RegistrarEquipoAsync();
            var configuracion = await Sesion.ConsultarConfiguracionAsync();
            if (configuracion is null)
            {
                // Un nodo anterior a /configuracion/ no exige sesión: modo prototipo.
                Sesion.SesionObligatoria = false;
                MostrarPrototipo(true);
                Estado("Conexión exitosa · API disponible", Tono.Bien);
                return;
            }
            if (!configuracion.Instalado) { await Shell.Current.GoToAsync("primer-arranque"); return; }
            AplicarConfiguracion(configuracion, conservarEstado: false);
        }
        catch (ArgumentException ex) { Estado(ex.Message, Tono.Problema); }
        finally { CheckButton.IsEnabled = true; _ocupado = false; }
    }

    /// <summary>«Iniciar como profesor»: sólo existe con el nodo en modo prototipo (RF-05). Si entretanto el nodo pasó a exigir sesión, pide documento y contraseña.</summary>
    private async void OnEnterDemo(object? sender, EventArgs e)
    {
        if (_ocupado) return;
        _ocupado = true;
        IniciarButton.IsEnabled = false;
        try
        {
            Estado("Consultando al aula…", Tono.Neutro);
            var configuracion = await Sesion.ConsultarConfiguracionAsync();
            if (configuracion is null)
            {
                MostrarPrototipo(false);
                Estado(MensajesDeAcceso.SinConexion + " Toca «Comprobar conexión» cuando vuelva.", Tono.Problema);
                return;
            }
            if (!configuracion.Instalado) { await Shell.Current.GoToAsync("primer-arranque"); return; }
            if (configuracion.SesionObligatoria)
            {
                AplicarConfiguracion(configuracion, conservarEstado: false);
                return;
            }
            await Shell.Current.GoToAsync("dashboard");
        }
        finally { IniciarButton.IsEnabled = true; _ocupado = false; }
    }

    private void OnDocumentoCompleted(object? sender, EventArgs e) => ClaveEntry.Focus();

    private async void OnEntrar(object? sender, EventArgs e) => await EntrarAsync(null);

    private async void OnPinMaestroCompleto(object? sender, string pin) => await EntrarAsync(pin);

    /// <summary>
    /// Documento + contraseña, y si el nodo lo pide, el PIN maestro. Con <paramref name="pin"/> nulo se lee lo escrito; con PIN se reenvía lo que quedó en
    /// espera. Un PIN equivocado deja el teclado (con los intentos que quedan); cualquier otra respuesta vuelve a los campos.
    /// </summary>
    private async Task EntrarAsync(string? pin)
    {
        if (_ocupado) return;
        var documento = pin is null ? (DocumentoEntry.Text ?? string.Empty).Trim() : _documentoEnEspera ?? string.Empty;
        var clave = pin is null ? ClaveEntry.Text ?? string.Empty : _claveEnEspera ?? string.Empty;
        if (documento.Length == 0 || clave.Length == 0)
        {
            SalirDelPin();
            Estado("Escribe tu documento y tu contraseña para entrar.", Tono.Aviso);
            (documento.Length == 0 ? DocumentoEntry : ClaveEntry).Focus();
            return;
        }
        _ocupado = true;
        EntrarButton.IsEnabled = false;
        PinTeclado.Habilitado = false;
        Estado(pin is null ? "Comprobando tus datos…" : "Comprobando el PIN maestro…", Tono.Neutro);
        try
        {
            var acceso = Sesion.Acceso;
            var sesion = await acceso.IniciarSesionAsync(documento, clave, Sesion.Dispositivo, pinMaestro: pin);
            var error = acceso.UltimoError;
            if (sesion is null)
            {
                if (error is { PinMaestroRequerido: true })
                {
                    // La contraseña ya era correcta: falta el PIN. Lo escrito queda en memoria para reenviarlo y la contraseña sale del campo.
                    _documentoEnEspera = documento;
                    _claveEnEspera = clave;
                    ClaveEntry.Text = string.Empty;
                    await Sesion.AsegurarEquipoAsync();
                    MostrarPin();
                    Estado(MensajesDeAcceso.Texto(error), Tono.Neutro);
                    return;
                }
                if (pin is not null && error is { PinMaestroInvalido: true })
                {
                    await PinTeclado.SacudirAsync();
                    Estado(MensajesDeAcceso.Texto(error), Tono.Problema);
                    return;
                }
                if (pin is not null && error is { PinMaestroBloqueado: true })
                {
                    PinTeclado.Limpiar();
                    Estado(MensajesDeAcceso.Texto(error), Tono.Problema);
                    return;   // el teclado queda apagado; «Volver» sigue ahí
                }
                if (pin is not null && error is { Estado: 0 })
                {
                    PinTeclado.Limpiar();
                    Estado(MensajesDeAcceso.Texto(error) + " Vuelve a marcar el PIN cuando vuelva.", Tono.Problema);
                    return;
                }
                SalirDelPin();
                // La contraseña se borra siempre, salvo que no se haya podido preguntar (sin conexión): así se reintenta sin volver a escribirla.
                if (error is { Estado: > 0 }) ClaveEntry.Text = string.Empty;
                Estado(MensajesDeAcceso.Texto(error), Tono.Problema);
                return;
            }

            SalirDelPin();
            ClaveEntry.Text = string.Empty;
            if (TraspasoEntreApps.AppDe(sesion.Usuario) == AppDelAcceso.Student)
            {
                // Un alumno ve SU menú: el de AVACOM Student. Se le abre esa app con su sesión; si no se puede, se le dice dónde entrar y se suelta el pase.
                await PasarALaAppDelAlumnoAsync();
                return;
            }
            await AbrirTableroAsync(sesion, clave);
        }
        finally
        {
            EntrarButton.IsEnabled = true;
            PinTeclado.Habilitado = !(Sesion.Acceso.UltimoError is { PinMaestroBloqueado: true });
            _ocupado = false;
        }
    }

    /// <summary>Abre el tablero con la sesión ya identificada (por documento y clave, o por un traspaso desde Student). <paramref name="claveProvisional"/> sólo viaja en el primer caso.</summary>
    private async Task AbrirTableroAsync(SesionAcceso sesion, string? claveProvisional)
    {
        Sesion.Usuario = sesion.Usuario;
        Sesion.SesionObligatoria = true;
        // MSG-021: si esta entrada cerró la clase abierta en otro equipo, el tablero lo cuenta una vez, sin pedir confirmación.
        Sesion.AvisoAlEntrar = sesion.SesionAnterior is { } anterior
            ? $"Cerramos tu clase abierta en {NombreDeEquipo(anterior.Dispositivo)}. Continúa aquí sin perder nada."
            : null;
        if (sesion.Usuario.DebeCambiarCredencial)
        {
            // La contraseña de la hoja es provisional: antes del tablero, la persona elige la suya. La provisional pasa en memoria, una sola vez.
            Sesion.RecordarClaveProvisional(claveProvisional ?? string.Empty);
            Estado("Listo · ahora elige tu contraseña", Tono.Bien);
            await Shell.Current.GoToAsync("elegir-contrasena");
            return;
        }
        Estado("Listo · entrando", Tono.Bien);
        await Shell.Current.GoToAsync("dashboard");
    }

    /// <summary>La cuenta es de alumno: se abre AVACOM Student con la misma sesión (sin pedir la clave otra vez). Si no se puede, se dice dónde entrar.</summary>
    private async Task PasarALaAppDelAlumnoAsync()
    {
        Estado("Abriendo AVACOM Student con tu sesión…", Tono.Neutro);
        var resultado = await TraspasoEntreApps.PasarAsync(Sesion.Acceso, AppDelAcceso.Student, Sesion.BaseUri);
        if (resultado == ResultadoTraspaso.Abierta)
        {
            ClienteJson.Token = null;   // el nodo cerró esta sesión al canjearse el traspaso: esta app no sigue presentándose con ella
            Estado(TraspasoEntreApps.MensajeSinTraspaso(AppDelAcceso.Student, resultado), Tono.Bien);
            return;
        }
        await Sesion.CerrarSesionDeUsuarioAsync();
        Estado(TraspasoEntreApps.MensajeSinTraspaso(AppDelAcceso.Student, resultado), Tono.Aviso);
    }

    /// <summary>OPS se abrió desde Student con un código de traspaso: se canjea y se entra. Falso si no valió (la pantalla de acceso sigue normal).</summary>
    private async Task<bool> CanjearEntranteAsync(TraspasoEntrante entrante)
    {
        if (entrante.Servidor is { } servidor && Ajustes.ServidorDePrueba is null) Sesion.GuardarServidor(servidor);
        ServerEntry.Text = Sesion.BaseUri.ToString().TrimEnd('/');
        Estado("Entrando con tu sesión…", Tono.Neutro);
        var sesion = await Sesion.Acceso.CanjearTraspasoAsync(entrante.Codigo, Sesion.Dispositivo);
        if (sesion is null)
        {
            Estado("El traspaso no valió o ya caducó. Escribe tu documento y tu contraseña para entrar.", Tono.Aviso);
            return false;
        }
        if (TraspasoEntreApps.AppDe(sesion.Usuario) == AppDelAcceso.Student)
        {
            await Sesion.CerrarSesionDeUsuarioAsync();
            Estado(TraspasoEntreApps.MensajeSinTraspaso(AppDelAcceso.Student, ResultadoTraspaso.SinApp), Tono.Aviso);
            return false;
        }
        await AbrirTableroAsync(sesion, null);
        return true;
    }

    private void OnPinVolver(object? sender, EventArgs e)
    {
        SalirDelPin();
        Estado("Escribe tu documento y tu contraseña para entrar.", Tono.Neutro);
    }

    private async void OnCrearMiUsuario(object? sender, EventArgs e) => await IrACuentaAsync("registro-docente");

    private async void OnOlvideMiContrasena(object? sender, EventArgs e) => await IrACuentaAsync("restablecer-contrasena");

    /// <summary>Se vuelve a preguntar al nodo justo antes: el PIN pudo vencer o configurarse mientras la pantalla estaba abierta.</summary>
    private async Task IrACuentaAsync(string ruta)
    {
        if (_ocupado) return;
        var configuracion = await Sesion.ConsultarConfiguracionAsync() ?? Sesion.Configuracion;
        PintarOferta(configuracion);
        if (_avisoAlTocar is { } aviso) { Estado(aviso, Tono.Aviso); return; }
        var oferta = OfertaDeCuenta.Para(configuracion);
        if (ruta == "registro-docente" ? !oferta.CrearMiUsuario : !oferta.OlvideMiContrasena)
        {
            Estado(oferta.Nota ?? MensajesDeAcceso.SinConexion, Tono.Aviso);
            return;
        }
        await Shell.Current.GoToAsync(ruta);
    }

    private void PintarOferta(ConfiguracionAcceso? configuracion)
    {
        var oferta = OfertaDeCuenta.Para(configuracion);
        CrearUsuarioButton.IsVisible = oferta.CrearMiUsuario;
        OlvideButton.IsVisible = oferta.OlvideMiContrasena;
        Grid.SetColumnSpan(CrearUsuarioButton, oferta.OlvideMiContrasena ? 1 : 2);
        Grid.SetColumn(OlvideButton, oferta.CrearMiUsuario ? 1 : 0);
        Grid.SetColumnSpan(OlvideButton, oferta.CrearMiUsuario ? 1 : 2);
        CuentaNotaLabel.Text = oferta.Nota ?? string.Empty;
        CuentaNotaLabel.IsVisible = oferta.Nota is not null;
        _avisoAlTocar = oferta.AvisoAlTocar;
    }

    private void OnCambiarServidor(object? sender, EventArgs e)
    {
        MostrarCredenciales(false);
        MostrarPrototipo(false);
        Estado("Escribe la dirección del equipo del aula y toca «Comprobar conexión».", Tono.Neutro);
    }

    /// <summary>Muestra los campos de acceso en lugar de la dirección y los botones de conexión (o los devuelve).</summary>
    private void MostrarCredenciales(bool mostrar)
    {
        CredencialesGrupo.IsVisible = mostrar;
        DireccionGrupo.IsVisible = !mostrar;
        AccionesGrupo.IsVisible = !mostrar;
        if (!mostrar) SalirDelPin();
    }

    private void MostrarPrototipo(bool mostrar)
    {
        IniciarCapsula.IsVisible = mostrar;
        PrototipoNota.IsVisible = mostrar;
    }

    private void MostrarPin()
    {
        CamposGrupo.IsVisible = false;
        PinGrupo.IsVisible = true;
        PinTeclado.Limpiar();
        PinTeclado.Habilitado = true;
    }

    /// <summary>Deja el teclado del PIN, olvida lo que estaba en espera y vuelve a los campos.</summary>
    private void SalirDelPin()
    {
        _documentoEnEspera = null;
        _claveEnEspera = null;
        PinTeclado.Limpiar();
        PinTeclado.Habilitado = true;
        PinGrupo.IsVisible = false;
        CamposGrupo.IsVisible = true;
    }

    /// <summary>El equipo donde estaba la otra sesión, sin el prefijo interno de la app («ops-», «student-») ni el código de instalación de la tableta.</summary>
    private static string NombreDeEquipo(string? dispositivo) =>
        string.IsNullOrWhiteSpace(dispositivo) ? "otro equipo" : Identidad.EquipoLegible(dispositivo);

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

using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Acceso;
using Avacom.Lms.Ops.Controls;
using Tono = Avacom.Lms.Ops.Controls.MarcoDeAcceso.Tono;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// RF-01…RF-03 · JRN-001 · PAN-204: el primer arranque del nodo. Se abre sola cuando el nodo contesta <c>instalado = false</c>. Cinco pasos tocables en la
/// tarjeta del acceso: (1) país e idioma, (2) nombre del aula, (3) administrador, (4) PIN maestro (teclado propio, dos veces, RN-05 con palabras) y (5) la
/// hoja de acceso con la contraseña inicial del administrador —la genera el nodo y llega UNA vez— y el PIN maestro, que se imprime o se copia y se confirma.
///
/// <para>Si se interrumpe: los pasos 1–3 se reanudan desde Preferences (sólo datos no secretos, <see cref="BorradorDeInstalacion"/>); la hoja, hasta que alguien
/// confirma «Ya la entregué», vive cifrada en SecureStorage y al volver a abrir OPS se vuelve directo a ella. Confirmada, se borra y no se puede ver de nuevo
/// (RN-04). Con el nodo ya instalado y sin hoja pendiente la página no deja entrar.</para>
/// </summary>
public sealed class PrimerArranquePage : ContentPage
{
    public const string ClaveBorrador = "ops_primer_arranque";
    public const string ClaveHoja = "ops_hoja_acceso";
    private const string ArchivoHoja = "hoja-de-acceso.html";

    private readonly MarcoDeAcceso _marco = new();
    private readonly MarcoDeAcceso.Estado _estado = new();
    private BorradorDeInstalacion _borrador = new();
    private HojaDeAcceso? _hoja;
    private string? _pinPorEnviar;   // el PIN ya confirmado, sólo en memoria, mientras el nodo no contesta (RF-00e: reintentar sin volver a marcarlo)
    private bool _ocupado;

    // Los pasos se construyen UNA vez y se muestran u ocultan: WinUI no deja mover un TextBox nativo de un contenedor a otro.
    private readonly VerticalStackLayout _pasoPais = new() { Spacing = 8 };
    private readonly VerticalStackLayout _pasoAula = new() { Spacing = 8 };
    private readonly VerticalStackLayout _pasoAdmin = new() { Spacing = 8 };
    private readonly VerticalStackLayout _pasoPin = new() { Spacing = 8 };
    private readonly VerticalStackLayout _pasoHoja = new() { Spacing = 8 };
    private readonly VerticalStackLayout _yaInstalado = new() { Spacing = 8 };

    private readonly FlexLayout _paises = new() { Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap };
    private readonly FlexLayout _idiomas = new() { Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap };
    private readonly Entry _aula = MarcoDeAcceso.Campo("Por ejemplo: IE San José · Sede primaria", "Nombre del aula");
    private readonly Label _codigo = MarcoDeAcceso.Nota(string.Empty);
    private readonly Entry _documento = MarcoDeAcceso.Campo("Número de documento", "Documento del administrador");
    private readonly Entry _nombres = MarcoDeAcceso.Campo("Nombres", "Nombres del administrador");
    private readonly Entry _apellidos = MarcoDeAcceso.Campo("Apellidos", "Apellidos del administrador");
    private readonly PinMaestroDobleView _pin = new() { TextoMarcar = "Marca el PIN maestro nuevo.", TextoConfirmar = "Márcalo otra vez para confirmar." };
    private readonly View _reintentarVista;
    private readonly Label _hojaAdmin = new() { FontSize = 18, FontAttributes = FontAttributes.Bold, LineBreakMode = LineBreakMode.WordWrap };
    private readonly Label _hojaClave = ValorDeHoja();
    private readonly Label _hojaPin = ValorDeHoja();

    public PrimerArranquePage()
    {
        Shell.SetNavBarIsVisible(this, false);
        Title = "Primer arranque";
        Content = _marco;
        _marco.Titulo.Text = "Primer arranque del aula";

        // 1 · país e idioma
        _pasoPais.Add(MarcoDeAcceso.Rotulo("País del aula"));
        _pasoPais.Add(_paises);
        _pasoPais.Add(MarcoDeAcceso.Rotulo("Idioma de las pantallas"));
        _pasoPais.Add(_idiomas);
        _pasoPais.Add(MarcoDeAcceso.Principal("Siguiente", (_, _) => Avanzar(BorradorDeInstalacion.PasoAula)).Vista);

        // 2 · nombre del aula
        _aula.TextChanged += (_, _) => PintarCodigo();
        _pasoAula.Add(MarcoDeAcceso.Rotulo("Nombre del aula"));
        _pasoAula.Add(_aula);
        _pasoAula.Add(_codigo);
        _pasoAula.Add(MarcoDeAcceso.Principal("Siguiente", (_, _) => ConfirmarAula()).Vista);
        _pasoAula.Add(MarcoDeAcceso.Discreta("Atrás", (_, _) => Avanzar(BorradorDeInstalacion.PasoPais)));

        // 3 · administrador
        _pasoAdmin.Add(MarcoDeAcceso.Rotulo("Documento"));
        _pasoAdmin.Add(_documento);
        _pasoAdmin.Add(MarcoDeAcceso.Rotulo("Nombres"));
        _pasoAdmin.Add(_nombres);
        _pasoAdmin.Add(MarcoDeAcceso.Rotulo("Apellidos"));
        _pasoAdmin.Add(_apellidos);
        _pasoAdmin.Add(MarcoDeAcceso.Principal("Siguiente", (_, _) => ConfirmarAdministrador()).Vista);
        _pasoAdmin.Add(MarcoDeAcceso.Discreta("Atrás", (_, _) => Avanzar(BorradorDeInstalacion.PasoAula)));

        // 4 · PIN maestro
        _pin.PinConfirmado += async (_, pin) => await InstalarAsync(pin);
        _pasoPin.Add(_pin);
        _reintentarVista = MarcoDeAcceso.Secundaria("Reintentar", async (_, _) => { if (_pinPorEnviar is { } p) await InstalarAsync(p); }).Vista;
        _reintentarVista.IsVisible = false;
        _pasoPin.Add(_reintentarVista);
        _pasoPin.Add(MarcoDeAcceso.Discreta("Atrás", (_, _) => { _pinPorEnviar = null; Avanzar(BorradorDeInstalacion.PasoAdministrador); }));

        // 5 · hoja de acceso
        _pasoHoja.Add(MarcoDeAcceso.Rotulo("Administrador"));
        _pasoHoja.Add(_hojaAdmin);
        _pasoHoja.Add(MarcoDeAcceso.Rotulo("Contraseña inicial del administrador (provisional)"));
        _pasoHoja.Add(_hojaClave);
        _pasoHoja.Add(MarcoDeAcceso.Rotulo("PIN maestro"));
        _pasoHoja.Add(_hojaPin);
        var botones = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 12 };
        botones.Add(MarcoDeAcceso.Secundaria("Imprimir", async (_, _) => await ImprimirAsync()).Vista, 0, 0);
        botones.Add(MarcoDeAcceso.Principal("Ya la entregué", async (_, _) => await ConfirmarHojaAsync()).Vista, 1, 0);
        _pasoHoja.Add(botones);

        // ya instalado: la página no deja entrar
        _yaInstalado.Add(MarcoDeAcceso.Principal("Ir al acceso", async (_, _) => await Shell.Current.GoToAsync("//login")).Vista);

        _marco.Cuerpo.Add(_estado);
        foreach (var paso in new[] { _pasoPais, _pasoAula, _pasoAdmin, _pasoPin, _pasoHoja, _yaInstalado })
        {
            paso.IsVisible = false;
            _marco.Cuerpo.Add(paso);
        }
    }

    private static Label ValorDeHoja() => new()
    {
        FontFamily = "Consolas", FontSize = 30, FontAttributes = FontAttributes.Bold, CharacterSpacing = 1.5, TextColor = Color.FromArgb("#18181B"),
        LineBreakMode = LineBreakMode.CharacterWrap,
    };

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _estado.Mostrar(null);
        _hoja = HojaDeAcceso.Desde(await Ajustes.LeerSecretoAsync(ClaveHoja));
        if (_hoja is not null) { Mostrar(BorradorDeInstalacion.PasoHoja); return; }
        BorrarArchivoImpreso();

        var configuracion = await Sesion.ConsultarConfiguracionAsync();
        if (configuracion is { Instalado: true }) { MostrarYaInstalado(); return; }
        if (configuracion is null) _estado.Mostrar(MensajesDeAcceso.SinConexion + " Puedes ir llenando los pasos; al final hará falta la conexión.", Tono.Aviso);

        _borrador = BorradorDeInstalacion.Desde(Ajustes.Get<string?>(ClaveBorrador, null));
        _aula.Text = _borrador.Aula;
        _documento.Text = _borrador.Documento;
        _nombres.Text = _borrador.Nombres;
        _apellidos.Text = _borrador.Apellidos;
        Mostrar(_borrador.Paso);
    }

    // ------------------------------------------------------------------------------------------------------------------------ pasos

    private void Mostrar(int paso)
    {
        _pasoPais.IsVisible = paso == BorradorDeInstalacion.PasoPais;
        _pasoAula.IsVisible = paso == BorradorDeInstalacion.PasoAula;
        _pasoAdmin.IsVisible = paso == BorradorDeInstalacion.PasoAdministrador;
        _pasoPin.IsVisible = paso == BorradorDeInstalacion.PasoPin;
        _pasoHoja.IsVisible = paso == BorradorDeInstalacion.PasoHoja;
        _yaInstalado.IsVisible = false;
        switch (paso)
        {
            case BorradorDeInstalacion.PasoPais:
                _marco.Titulo.Text = "Primer arranque del aula";
                _marco.Mensaje.Text = "Paso 1 de 5 · País e idioma. Con ellos el equipo pone la hora y el idioma de las pantallas.";
                PintarFichas();
                break;
            case BorradorDeInstalacion.PasoAula:
                _marco.Titulo.Text = "Primer arranque del aula";
                _marco.Mensaje.Text = "Paso 2 de 5 · El nombre del aula, tal como lo verán los profesores.";
                PintarCodigo();
                break;
            case BorradorDeInstalacion.PasoAdministrador:
                _marco.Titulo.Text = "Primer arranque del aula";
                _marco.Mensaje.Text = "Paso 3 de 5 · Quién administra el aula. Su contraseña inicial la genera el equipo y sale en la hoja de acceso.";
                break;
            case BorradorDeInstalacion.PasoPin:
                _marco.Titulo.Text = "El PIN maestro";
                _marco.Mensaje.Text = "Paso 4 de 5 · " + PinMaestroLocal.Regla;
                _pin.Reiniciar();
                _pin.Habilitado = true;
                _reintentarVista.IsVisible = _pinPorEnviar is not null;
                break;
            case BorradorDeInstalacion.PasoHoja:
                _marco.Titulo.Text = "Hoja de acceso";
                _marco.Mensaje.Text = "Paso 5 de 5 · Imprímela o cópiala a mano y entrégala a la administración. Cuando confirmes, el equipo no la vuelve a mostrar.";
                if (_hoja is { } h)
                {
                    _hojaAdmin.Text = $"{h.Administrador} · documento {h.Documento}";
                    _hojaClave.Text = h.Contrasena;
                    _hojaPin.Text = h.PinLegible;
                }
                break;
        }
    }

    private void MostrarYaInstalado()
    {
        foreach (var paso in new[] { _pasoPais, _pasoAula, _pasoAdmin, _pasoPin, _pasoHoja }) paso.IsVisible = false;
        _yaInstalado.IsVisible = true;
        _marco.Titulo.Text = "Este equipo ya está instalado";
        _marco.Mensaje.Text = "El primer arranque se hace una sola vez. Para entrar usa el acceso con tu documento y tu contraseña.";
    }

    private void Avanzar(int paso)
    {
        _estado.Mostrar(null);
        Guardar(paso);
        Mostrar(paso);
    }

    /// <summary>Sólo lo no secreto, para reanudar: el PIN maestro nunca se guarda aquí.</summary>
    private void Guardar(int paso)
    {
        _borrador = _borrador with
        {
            Paso = paso, Aula = (_aula.Text ?? string.Empty).Trim(), Documento = (_documento.Text ?? string.Empty).Trim(),
            Nombres = (_nombres.Text ?? string.Empty).Trim(), Apellidos = (_apellidos.Text ?? string.Empty).Trim(),
        };
        Ajustes.Set(ClaveBorrador, _borrador.ToJson());
    }

    private void PintarFichas()
    {
        _paises.Clear();
        foreach (var p in Paises.Lista)
        {
            var codigo = p.Codigo;
            _paises.Add(MarcoDeAcceso.Ficha(p.Nombre, _borrador.Pais == codigo, (_, _) => { _borrador = _borrador with { Pais = codigo }; PintarFichas(); }));
        }
        _idiomas.Clear();
        foreach (var (codigo, nombre) in Paises.Idiomas)
        {
            var c = codigo;
            _idiomas.Add(MarcoDeAcceso.Ficha(nombre, _borrador.Idioma == c, (_, _) => { _borrador = _borrador with { Idioma = c }; PintarFichas(); }));
        }
    }

    private void PintarCodigo()
    {
        var nombre = (_aula.Text ?? string.Empty).Trim();
        _codigo.Text = nombre.Length == 0 ? "El código del aula sale solo del nombre." : $"Código del aula: {CodigoDeAula.Desde(nombre)}";
    }

    private void ConfirmarAula()
    {
        if (string.IsNullOrWhiteSpace(_aula.Text)) { _estado.Mostrar("Escribe el nombre del aula para seguir.", Tono.Aviso); _aula.Focus(); return; }
        Avanzar(BorradorDeInstalacion.PasoAdministrador);
    }

    private void ConfirmarAdministrador()
    {
        if (string.IsNullOrWhiteSpace(_documento.Text) || string.IsNullOrWhiteSpace(_nombres.Text))
        {
            _estado.Mostrar("Escribe al menos el documento y los nombres de quien administra el aula.", Tono.Aviso);
            (string.IsNullOrWhiteSpace(_documento.Text) ? _documento : _nombres).Focus();
            return;
        }
        Avanzar(BorradorDeInstalacion.PasoPin);
    }

    // ------------------------------------------------------------------------------------------------------------------------ instalar

    private async Task InstalarAsync(string pin)
    {
        if (_ocupado) return;
        _ocupado = true;
        _pin.Habilitado = false;
        _reintentarVista.IsVisible = false;
        _estado.Mostrar("Instalando el aula…", Tono.Neutro);
        try
        {
            var pais = Paises.Por(_borrador.Pais);
            var aula = (_aula.Text ?? string.Empty).Trim();
            var documento = (_documento.Text ?? string.Empty).Trim();
            var nombres = (_nombres.Text ?? string.Empty).Trim();
            var apellidos = (_apellidos.Text ?? string.Empty).Trim();
            var codigo = CodigoDeAula.Desde(aula);
            var acceso = Sesion.Acceso;
            var hecha = await acceso.InstalarAsync(new DatosDeInstalacion(codigo, aula, pais.Codigo, _borrador.Idioma, pais.ZonaHoraria, documento, nombres, apellidos, pin));
            if (hecha is null)
            {
                var error = acceso.UltimoError;
                if (error is { Estado: 0 } or null)
                {
                    // Sin conexión: el PIN queda en memoria para reintentar sin volver a marcarlo (RF-00e).
                    _pinPorEnviar = pin;
                    _reintentarVista.IsVisible = true;
                    _estado.Mostrar(MensajesDeAcceso.Texto(error) + " Cuando vuelva, toca «Reintentar».", Tono.Problema);
                    return;
                }
                _pinPorEnviar = null;
                switch (error.Codigo)
                {
                    case "pin_debil" or "pin_invalido":
                        _pin.Reiniciar(MensajesDeAcceso.Texto(error));
                        _estado.Mostrar(null);
                        return;
                    case "ya_instalado":
                        MostrarYaInstalado();
                        return;
                    default:
                        // Un documento o un nombre que el nodo no acepta: se vuelve al paso de los datos, con lo escrito intacto.
                        Avanzar(BorradorDeInstalacion.PasoAdministrador);
                        _estado.Mostrar(MensajesDeAcceso.Texto(error), Tono.Problema);
                        return;
                }
            }

            _pinPorEnviar = null;
            _hoja = new HojaDeAcceso(aula, codigo, $"{nombres} {apellidos}".Trim(), documento, hecha.PasswordInicial ?? string.Empty, pin,
                                     DateTimeOffset.UtcNow.ToUnixTimeMilliseconds());
            var guardada = await Ajustes.GuardarSecretoAsync(ClaveHoja, _hoja.ToJson());
            Guardar(BorradorDeInstalacion.PasoPin);
            Mostrar(BorradorDeInstalacion.PasoHoja);
            _estado.Mostrar(guardada
                ? "El aula quedó instalada. Esta hoja sigue aquí aunque cierres la aplicación, hasta que confirmes que la entregaste."
                : "El aula quedó instalada. Copia o imprime la hoja ahora: este equipo no pudo guardarla cifrada para más tarde.", guardada ? Tono.Bien : Tono.Aviso);
            _ = Sesion.ConsultarConfiguracionAsync();
            _ = Sesion.RegistrarEquipoAsync();
        }
        finally
        {
            _pin.Habilitado = true;
            _ocupado = false;
        }
    }

    // ------------------------------------------------------------------------------------------------------------------------ la hoja

    private static string RutaImpresa => Path.Combine(FileSystem.CacheDirectory, ArchivoHoja);

    /// <summary>Una página sencilla que el navegador del equipo abre e imprime; se borra al confirmar la entrega.</summary>
    private async Task ImprimirAsync()
    {
        if (_hoja is null) return;
        try
        {
            await File.WriteAllTextAsync(RutaImpresa, _hoja.Html());
            var abierta = await Launcher.Default.OpenAsync(new OpenFileRequest("Hoja de acceso", new ReadOnlyFile(RutaImpresa, "text/html")));
            _estado.Mostrar(abierta
                ? "La hoja se abrió para imprimir. Cuando la tengas en la mano, toca «Ya la entregué»."
                : "Este equipo no pudo abrir la hoja para imprimir. Cópiala a mano y luego toca «Ya la entregué».", abierta ? Tono.Neutro : Tono.Aviso);
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir(Avacom.Lms.Ui.Controls.AulaContenidoView.NombreApp, "primer arranque · imprimir", ex);
            _estado.Mostrar("Este equipo no pudo abrir la hoja para imprimir. Cópiala a mano y luego toca «Ya la entregué».", Tono.Aviso);
        }
    }

    private async Task ConfirmarHojaAsync()
    {
        Ajustes.BorrarSecreto(ClaveHoja);
        Ajustes.Remove(ClaveBorrador);
        BorrarArchivoImpreso();
        _hoja = null;
        _hojaClave.Text = _hojaPin.Text = string.Empty;
        Sesion.AvisoDeAcceso = "Listo, el aula quedó instalada. Entra con el documento del administrador, la contraseña de la hoja y el PIN maestro.";
        await Shell.Current.GoToAsync("//login");
    }

    private static void BorrarArchivoImpreso()
    {
        try { if (File.Exists(RutaImpresa)) File.Delete(RutaImpresa); } catch (Exception) { /* se intenta de nuevo en el próximo arranque */ }
    }

    /// <summary>¿Hay una hoja sin confirmar? El acceso lo pregunta al aparecer para volver directo a ella.</summary>
    public static async Task<bool> HayHojaPendienteAsync() => HojaDeAcceso.Desde(await Ajustes.LeerSecretoAsync(ClaveHoja)) is not null;
}

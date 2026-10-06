using System.Globalization;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Controls;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Seguridad del aula (RF-08, sólo administración). Todo se lee del nodo, nada es simulado:
/// <list type="bullet">
/// <item>la tarjeta del PIN maestro (<c>GET pin-maestro/</c>): estado, creado el…, vence el…, días restantes y el aviso de los 30 días (RN-08), con «Cambiar el
/// PIN maestro» —o «Configurar el PIN maestro» en un nodo que se actualizó desde una versión anterior y todavía no tiene— con el teclado propio dos veces.
/// El PIN no se vuelve a mostrar nunca (RN-04);</item>
/// <item>los interruptores del registro de profesores con el PIN, del registro propio de alumnos (RN-37) y de los visitantes (RN-47);</item>
/// <item>la lista de profesores que se registraron con el PIN maestro, con «Suspender» y «Reactivar» (RN-22).</item>
/// </list>
/// </summary>
public sealed class SeguridadAulaPage : ContentPage
{
    private static readonly CultureInfo Es = new("es-ES");
    private static readonly Color TintaPeligro = Color.FromArgb("#8A1C1F");

    private readonly Label _subtitulo = new() { FontFamily = "InterLight", FontSize = 15, TextColor = Color.FromArgb("#52525B"), LineBreakMode = LineBreakMode.WordWrap, Text = "Cargando…" };
    private readonly VerticalStackLayout _izquierda = new() { Spacing = 14, Padding = new Thickness(0, 0, 0, 40) };
    private readonly VerticalStackLayout _derecha = new() { Spacing = 10, Padding = new Thickness(0, 0, 0, 40) };
    // El teclado doble se construye UNA vez y se muestra u oculta dentro de la tarjeta del PIN.
    private readonly PinMaestroDobleView _pin = new() { TextoMarcar = "Marca el PIN maestro nuevo.", TextoConfirmar = "Márcalo otra vez para confirmar." };
    private readonly VerticalStackLayout _cambioHost = new() { Spacing = 10, IsVisible = false };

    private EstadoPinMaestro? _estadoPin;
    private ConfiguracionAcceso? _configuracion;
    private IReadOnlyList<DocentePorPin>? _docentes;
    private (string Texto, bool Problema)? _aviso;
    private bool _cambiando, _ocupado;

    public SeguridadAulaPage()
    {
        Shell.SetNavBarIsVisible(this, false);
        Title = "Seguridad del aula";
        BackgroundColor = Color.FromArgb("#F1F1F1");

        var encabezado = new VerticalStackLayout { Spacing = 6, VerticalOptions = LayoutOptions.Center };
        encabezado.Add(new Label { Text = "SEGURIDAD", FontFamily = "InterRegular", FontSize = 12, TextColor = Color.FromArgb("#52525B"), CharacterSpacing = 2.5 });
        encabezado.Add(new Label { Text = "Seguridad del aula", FontFamily = "InterMedium", FontSize = 30, TextColor = Color.FromArgb("#18181B") });
        encabezado.Add(_subtitulo);
        var actualizar = Ds.Boton("Actualizar", Ds.Rango.Secondary, async (_, _) => await CargarAsync(), 56);
        var volver = Ds.Boton("Menú principal", Ds.Rango.Quiet, async (_, _) => await Shell.Current.GoToAsync(".."), 56);
        foreach (var b in new[] { actualizar, volver }) { b.FontSize = 16; b.MinimumWidthRequest = 150; }
        var acciones = new HorizontalStackLayout { Spacing = 12, VerticalOptions = LayoutOptions.Center, Children = { Ds.Capsula(actualizar), volver } };
        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 24, HorizontalOptions = LayoutOptions.Center, WidthRequest = 1280 };
        cabecera.Add(encabezado, 0, 0);
        cabecera.Add(acciones, 1, 0);

        var columnas = new Grid { ColumnDefinitions = [new ColumnDefinition(560), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 20, HorizontalOptions = LayoutOptions.Center, WidthRequest = 1280 };
        columnas.Add(new ScrollView { Content = _izquierda }, 0, 0);
        columnas.Add(new ScrollView { Content = _derecha }, 1, 0);

        var raiz = new Grid { RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Star)], Padding = new Thickness(44, 28, 48, 24), RowSpacing = 18 };
        raiz.Add(cabecera, 0, 0);
        raiz.Add(columnas, 0, 1);
        Content = raiz;

        _pin.PinConfirmado += async (_, pin) => await CambiarPinAsync(pin);
        _cambioHost.Add(_pin);
        var cancelar = Ds.Boton("Cancelar", Ds.Rango.Quiet, (_, _) => { _cambiando = false; _pin.Reiniciar(); Pintar(); }, 46);
        cancelar.MinimumWidthRequest = 150;
        cancelar.HorizontalOptions = LayoutOptions.Center;
        _cambioHost.Add(cancelar);
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _aviso = null;
        _cambiando = false;
        await CargarAsync();
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _pin.Reiniciar();
    }

    private async Task CargarAsync()
    {
        if (_ocupado) return;
        _ocupado = true;
        try
        {
            if (Sesion.Usuario is not { EsAdministracion: true })
            {
                _estadoPin = null;
                _docentes = null;
                _subtitulo.Text = "Esta pantalla es de la administración del aula.";
                _izquierda.Clear();
                _derecha.Clear();
                _izquierda.Add(Ds.Alerta_("Sólo para la administración",
                    "Aquí se cambia el PIN maestro y se revisan los profesores que se registraron con él. Entra con una cuenta de administración para verla.",
                    Ds.AlertaSuave, Ds.Tinta));
                return;
            }
            var acceso = Sesion.Acceso;
            _configuracion = await Sesion.ConsultarConfiguracionAsync() ?? _configuracion;
            _estadoPin = await acceso.EstadoPinMaestroAsync();
            if (_estadoPin is null) _aviso = (MensajesDeAcceso.Texto(acceso.UltimoError), true);
            _docentes = await acceso.ListarDocentesPorPinMaestroAsync();
            Pintar();
        }
        finally { _ocupado = false; }
    }

    // ------------------------------------------------------------------------------------------------------------------------ pintar

    private void Pintar()
    {
        _izquierda.Clear();
        _derecha.Clear();
        var organizacion = _configuracion?.SesionObligatoria == true ? "Con sesión obligatoria" : "En modo prototipo";
        _subtitulo.Text = $"{organizacion} · el PIN maestro, quién se registró con él y las puertas de entrada del aula.";
        if (_aviso is { } aviso)
            _izquierda.Add(Ds.Alerta_(aviso.Problema ? "No se pudo" : "Listo", aviso.Texto, aviso.Problema ? Ds.PeligroSuave : Ds.ExitoSuave, aviso.Problema ? TintaPeligro : Ds.Tinta));
        _izquierda.Add(TarjetaPin());
        _izquierda.Add(TarjetaPoliticas());
        PintarDocentes();
    }

    private static string Fecha(DateTimeOffset? f) => f is { } v ? v.ToString("d 'de' MMMM 'de' yyyy", Es) : "—";

    private View TarjetaPin()
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        var e = _estadoPin;
        if (e is null)
        {
            pila.Add(Ds.Titulo("PIN maestro", 22));
            pila.Add(Ds.Secundario("No pudimos leer su estado ahora. Toca «Actualizar» para intentarlo de nuevo.", 15));
            return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(22, 18), Colors.White);
        }
        if (!e.Configurado)
        {
            pila.Add(Ds.Titulo("Aún no hay PIN maestro", 22));
            pila.Add(Ds.Cuerpo("Sin él, los profesores no pueden crear su usuario ni recuperar su contraseña. Configúralo ahora: seis números que sólo conocerá la escuela.", 16));
        }
        else
        {
            var titulo = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)] };
            titulo.Add(Ds.Titulo("PIN maestro", 22), 0, 0);
            var (texto, fondo, tinta) = e.Vencido ? ("Vencido", Ds.PeligroSuave, TintaPeligro)
                : e.Aviso ? ("Vence pronto", Ds.AlertaSuave, Glass.TintaAlerta)
                : ("Vigente", Ds.ExitoSuave, Glass.TintaExito);
            titulo.Add(Ds.Pildora(texto, fondo, tinta, 14), 1, 0);
            pila.Add(titulo);
            pila.Add(Fila("Creado el", Fecha(e.CreadoEl)));
            pila.Add(Fila("Vence el", Fecha(e.VenceEl)));
            pila.Add(Fila("Días restantes", e.Vencido ? "0 · ya venció" : e.DiasRestantes?.ToString(Es) ?? "—"));
            if (e.Vencido)
                pila.Add(Ds.Alerta_("El PIN maestro venció", "Las clases y los profesores ya registrados siguen como siempre, pero nadie puede crear un profesor ni recuperar su contraseña hasta que lo cambies.", Ds.PeligroSuave, TintaPeligro));
            else if (e.Aviso)
                pila.Add(Ds.Alerta_("Faltan 30 días o menos", "Cámbialo antes de que venza: cambiarlo reinicia el año de vigencia.", Ds.AlertaSuave, Glass.TintaAlerta));
            if (e.BloqueadoHasta is { } hasta && hasta > DateTimeOffset.UtcNow.ToUnixTimeMilliseconds())
                pila.Add(Ds.Alerta_("Demasiados intentos desde este equipo",
                    $"El PIN maestro no se acepta aquí hasta las {DateTimeOffset.FromUnixTimeMilliseconds(hasta).ToLocalTime():HH:mm}.", Ds.AlertaSuave, Glass.TintaAlerta));
            pila.Add(Ds.Secundario("Nadie puede ver el PIN maestro, ni la administración: si se olvida o se filtró, se reemplaza aquí sin necesidad de saber el actual.", 14));
        }

        if (_cambiando)
        {
            pila.Add(Ds.Secundario(Avacom.Lms.Ops.Acceso.PinMaestroLocal.Regla, 14));
            if (_cambioHost.Parent is Layout anterior) anterior.Remove(_cambioHost);
            _cambioHost.IsVisible = true;
            pila.Add(_cambioHost);
        }
        else
        {
            var boton = Ds.Boton(e.Configurado ? "Cambiar el PIN maestro" : "Configurar el PIN maestro", Ds.Rango.Primary, (_, _) =>
            {
                _cambiando = true;
                _aviso = null;
                _pin.Reiniciar();
                _pin.Habilitado = true;
                Pintar();
            }, 56);
            boton.FontSize = 16;
            boton.MinimumWidthRequest = 150;
            boton.HorizontalOptions = LayoutOptions.Start;
            pila.Add(Ds.Capsula(boton));
        }
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(22, 18), Colors.White);
    }

    private static View Fila(string rotulo, string valor)
    {
        var g = new Grid { ColumnDefinitions = [new ColumnDefinition(170), new ColumnDefinition(GridLength.Star)] };
        g.Add(Ds.Secundario(rotulo, 15), 0, 0);
        g.Add(Ds.Cuerpo(valor, 17), 1, 0);
        return g;
    }

    private View TarjetaPoliticas()
    {
        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(Ds.Titulo("Puertas de entrada", 22));
        var c = _configuracion;
        if (c is null)
        {
            pila.Add(Ds.Secundario("No pudimos leer cómo está configurada el aula. Toca «Actualizar».", 15));
            return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(22, 18), Colors.White);
        }
        pila.Add(Interruptor("Registro de profesores con el PIN maestro", "Con el PIN maestro, un profesor crea su propio usuario.", c.AutoregistroDocentes,
            nuevo => ("teacher", new { autoregistro = nuevo })));
        pila.Add(Ds.Separador());
        pila.Add(Interruptor("Registro propio de alumnos", "Un alumno que no está en la lista crea su usuario con su nombre y su PIN.", c.AutoregistroAlumnos,
            nuevo => ("student", new { autoregistro = nuevo })));
        pila.Add(Ds.Separador());
        pila.Add(Interruptor("Entrar como visitante", "Quien olvidó su PIN sigue la clase sin identificarse; lo que haga no va a ningún historial.", c.Visitante,
            nuevo => ("student", new { visitante = nuevo })));
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(22, 18), Colors.White);
    }

    private View Interruptor(string titulo, string detalle, bool encendido, Func<bool, (string Perfil, object Cambios)> cambio)
    {
        var texto = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        texto.Add(Ds.Cuerpo(titulo, 17));
        texto.Add(Ds.Secundario(detalle, 14));
        var boton = new Button
        {
            Text = encendido ? "Encendido" : "Apagado", HeightRequest = 46, WidthRequest = 150, CornerRadius = 12, BorderWidth = 1, FontSize = 15,
            BackgroundColor = encendido ? Ds.Exito : Colors.White, TextColor = encendido ? Colors.White : Ds.Tinta,
            BorderColor = encendido ? Color.FromArgb("#017A4B") : Ds.Filo, VerticalOptions = LayoutOptions.Center,
        };
        SemanticProperties.SetDescription(boton, $"{titulo}: {(encendido ? "encendido" : "apagado")}. Tocar para {(encendido ? "apagarlo" : "encenderlo")}.");
        AutomationProperties.SetName(boton, $"{titulo} · {(encendido ? "Encendido" : "Apagado")}");
        boton.Clicked += async (_, _) =>
        {
            boton.IsEnabled = false;
            var (perfil, cambios) = cambio(!encendido);
            var acceso = Sesion.Acceso;
            var r = await acceso.ConfigurarPoliticaAsync(perfil, cambios);
            _aviso = r is null
                ? (MensajesDeAcceso.Texto(acceso.UltimoError), true)
                : ($"{titulo}: {(!encendido ? "encendido" : "apagado")}.", false);
            _configuracion = await Sesion.ConsultarConfiguracionAsync() ?? _configuracion;
            Pintar();
        };
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 14 };
        fila.Add(texto, 0, 0);
        fila.Add(boton, 1, 0);
        return fila;
    }

    private void PintarDocentes()
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(Ds.Titulo("Profesores registrados con el PIN maestro", 22));
        if (_docentes is null)
        {
            pila.Add(Ds.Secundario(MensajesDeAcceso.Texto(Sesion.Acceso.UltimoError) + " Toca «Actualizar».", 15));
            _derecha.Add(Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(22, 18), Colors.White));
            return;
        }
        pila.Add(Ds.Secundario(_docentes.Count == 0
            ? "Todavía nadie creó su usuario con el PIN maestro."
            : "La escuela los aprobó con el PIN; si alguno no debería estar, suspéndelo. Su historial se conserva.", 15));
        foreach (var d in _docentes.OrderByDescending(d => d.RegistradoEn))
        {
            pila.Add(Ds.Separador());
            pila.Add(FilaDocente(d));
        }
        _derecha.Add(Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(22, 18), Colors.White));
    }

    private View FilaDocente(DocentePorPin d)
    {
        var texto = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        texto.Add(Ds.Cuerpo(d.Alias, 18));
        var detalle = $"Registrado el {d.RegistradoEl.ToString("d 'de' MMMM, HH:mm", Es)}" + (string.IsNullOrWhiteSpace(d.Equipo) ? string.Empty : $" · desde {d.Equipo}");
        texto.Add(Ds.Secundario(detalle, 14));
        var grupos = d.Grupos is { Count: > 0 } g ? string.Join(", ", g.Select(x => x.Nombre)) : "sin grupos";
        texto.Add(Ds.Secundario($"Grupos: {grupos}", 14));

        var estado = d.Suspendido ? Ds.Pildora("Suspendido", Ds.PeligroSuave, TintaPeligro, 13) : Ds.Pildora("Activo", Ds.ExitoSuave, Glass.TintaExito, 13);
        var boton = Ds.Boton(d.Suspendido ? "Reactivar" : "Suspender", Ds.Rango.Secondary, null, 46, 150);
        boton.FontSize = 15;
        var id = d.Id;
        boton.Clicked += async (_, _) =>
        {
            Ds.Habilitar(boton, false);
            var acceso = Sesion.Acceso;
            var ok = await acceso.CambiarEstadoDeUsuarioAsync(id, d.Suspendido ? "ACTIVO" : "SUSPENDIDO");
            _aviso = ok
                ? (d.Suspendido ? $"{d.Alias} puede volver a entrar." : $"{d.Alias} quedó suspendido: ya no puede entrar. Su historial se conserva.", false)
                : (MensajesDeAcceso.Texto(acceso.UltimoError), true);
            _docentes = await acceso.ListarDocentesPorPinMaestroAsync() ?? _docentes;
            Pintar();
        };
        AutomationProperties.SetName(boton, $"{(d.Suspendido ? "Reactivar" : "Suspender")} a {d.Alias}");

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 14, Padding = new Thickness(0, 4) };
        fila.Add(texto, 0, 0);
        fila.Add(estado, 1, 0);
        fila.Add(Ds.Capsula(boton), 2, 0);
        return fila;
    }

    // ------------------------------------------------------------------------------------------------------------------------ cambiar el PIN

    private async Task CambiarPinAsync(string pin)
    {
        _pin.Habilitado = false;
        try
        {
            var acceso = Sesion.Acceso;
            var cambio = await acceso.CambiarPinMaestroAsync(pin);
            if (cambio is null)
            {
                var error = acceso.UltimoError;
                if (error is { Codigo: "pin_debil" or "pin_invalido" }) { _pin.Reiniciar(MensajesDeAcceso.Texto(error)); return; }
                _pin.Reiniciar();
                _aviso = (MensajesDeAcceso.Texto(error), true);
                Pintar();
                return;
            }
            _cambiando = false;
            _pin.Reiniciar();
            var vence = DateTimeOffset.FromUnixTimeMilliseconds(cambio.VenceEn).ToLocalTime();
            _aviso = ($"El PIN maestro nuevo ya vale y vence el {Fecha(vence)}. Entrégalo a quien corresponda: no se vuelve a mostrar.", false);
            await CargarAsync();
        }
        finally { _pin.Habilitado = true; }
    }
}

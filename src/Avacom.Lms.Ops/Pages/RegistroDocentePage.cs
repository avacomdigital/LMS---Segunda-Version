using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Acceso;
using Avacom.Lms.Ops.Controls;
using Avacom.Lms.Ui.Controls;
using Tono = Avacom.Lms.Ops.Controls.MarcoDeAcceso.Tono;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// «Crear mi usuario» (RF-06 · RN-20…RN-23 · RB-13): el profesor se da de alta solo, con el PIN maestro, sin que nadie de la administración tenga que estar.
/// Cuatro pasos en la tarjeta del acceso: (1) documento, nombres y apellidos; (2) contraseña dos veces; (3) los grupos que dicta, tocando fichas (los
/// existentes, <c>ListarGruposDelAulaAsync(paraDocente: true)</c>); (4) el PIN maestro con el teclado propio, que lo envía todo. Si el PIN falla se conserva lo
/// escrito y se dicen los intentos que quedan; si el nodo rechaza otra cosa, se vuelve al paso que hay que corregir. Registrado, entra directo al tablero.
/// </summary>
public sealed class RegistroDocentePage : ContentPage
{
    private const int PasoDatos = 1, PasoClave = 2, PasoGrupos = 3, PasoPin = 4;

    private readonly MarcoDeAcceso _marco = new();
    private readonly MarcoDeAcceso.Estado _estado = new();
    private readonly VerticalStackLayout _pasoDatos = new() { Spacing = 8 };
    private readonly VerticalStackLayout _pasoClave = new() { Spacing = 8 };
    private readonly VerticalStackLayout _pasoGrupos = new() { Spacing = 8 };
    private readonly VerticalStackLayout _pasoPin = new() { Spacing = 8 };

    private readonly Entry _documento = MarcoDeAcceso.Campo("Tu número de documento", "Documento");
    private readonly Entry _nombres = MarcoDeAcceso.Campo("Tus nombres", "Nombres");
    private readonly Entry _apellidos = MarcoDeAcceso.Campo("Tus apellidos", "Apellidos");
    private readonly Entry _clave = MarcoDeAcceso.Campo("Tu contraseña", "Contraseña", secreto: true);
    private readonly Entry _repetida = MarcoDeAcceso.Campo("Escríbela otra vez", "Repite la contraseña", secreto: true);
    private readonly Label _reglaClave = MarcoDeAcceso.Nota(string.Empty);
    private readonly FlexLayout _grupos = new() { Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap };
    private readonly Label _gruposNota = MarcoDeAcceso.Nota(string.Empty);
    private readonly TecladoPinView _teclado = MarcoDeAcceso.TecladoMaestro();

    private IReadOnlyList<GrupoDelAula> _disponibles = [];
    private readonly HashSet<string> _elegidos = [];
    private int _paso = PasoDatos;
    private bool _ocupado;

    public RegistroDocentePage()
    {
        Shell.SetNavBarIsVisible(this, false);
        Title = "Crear mi usuario";
        Content = _marco;
        _marco.Titulo.Text = "Crear mi usuario";

        _pasoDatos.Add(MarcoDeAcceso.Rotulo("Documento"));
        _pasoDatos.Add(_documento);
        _pasoDatos.Add(MarcoDeAcceso.Rotulo("Nombres"));
        _pasoDatos.Add(_nombres);
        _pasoDatos.Add(MarcoDeAcceso.Rotulo("Apellidos"));
        _pasoDatos.Add(_apellidos);
        _pasoDatos.Add(MarcoDeAcceso.Principal("Siguiente", (_, _) => ConfirmarDatos()).Vista);
        _pasoDatos.Add(MarcoDeAcceso.Discreta("Volver al acceso", async (_, _) => await Shell.Current.GoToAsync("..")));

        _pasoClave.Add(MarcoDeAcceso.Rotulo("Contraseña"));
        _pasoClave.Add(_clave);
        _pasoClave.Add(MarcoDeAcceso.Rotulo("Repite la contraseña"));
        _pasoClave.Add(_repetida);
        _pasoClave.Add(_reglaClave);
        _pasoClave.Add(MarcoDeAcceso.Principal("Siguiente", (_, _) => ConfirmarClave()).Vista);
        _pasoClave.Add(MarcoDeAcceso.Discreta("Atrás", (_, _) => Mostrar(PasoDatos)));

        _pasoGrupos.Add(_gruposNota);
        _pasoGrupos.Add(_grupos);
        _pasoGrupos.Add(MarcoDeAcceso.Principal("Siguiente", (_, _) => Mostrar(PasoPin)).Vista);
        _pasoGrupos.Add(MarcoDeAcceso.Discreta("Atrás", (_, _) => Mostrar(PasoClave)));

        _teclado.PinCompleto += async (_, pin) => await RegistrarAsync(pin);
        _pasoPin.Add(new Label { Text = "Marca el PIN maestro de la escuela.", FontSize = 15, FontAttributes = FontAttributes.Bold, HorizontalTextAlignment = TextAlignment.Center });
        _pasoPin.Add(_teclado);
        _pasoPin.Add(MarcoDeAcceso.Discreta("Atrás", (_, _) => Mostrar(PasoGrupos)));

        _marco.Cuerpo.Add(_estado);
        foreach (var p in new[] { _pasoDatos, _pasoClave, _pasoGrupos, _pasoPin }) _marco.Cuerpo.Add(p);
        _repetida.Completed += (_, _) => ConfirmarClave();
    }

    private int Minimo => ContrasenaNueva.Minimo(Sesion.Configuracion, "teacher", 8);

    protected override void OnAppearing()
    {
        base.OnAppearing();
        // RN-11: el PIN maestro sólo se acepta de un equipo que el nodo sabe que no es una tableta de alumno.
        _ = Sesion.RegistrarEquipoAsync();
        Mostrar(_paso);
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _teclado.Limpiar();
    }

    private void Mostrar(int paso)
    {
        _paso = paso;
        _pasoDatos.IsVisible = paso == PasoDatos;
        _pasoClave.IsVisible = paso == PasoClave;
        _pasoGrupos.IsVisible = paso == PasoGrupos;
        _pasoPin.IsVisible = paso == PasoPin;
        _teclado.Limpiar();
        _teclado.Habilitado = true;
        _marco.Mensaje.Text = paso switch
        {
            PasoDatos => "Paso 1 de 4 · Tus datos. Con tu documento y tu contraseña entrarás a este equipo.",
            PasoClave => "Paso 2 de 4 · Tu contraseña. Es tuya desde ya: nadie más la conoce.",
            PasoGrupos => "Paso 3 de 4 · Los grupos que dictas. Sólo verás los que elijas; puedes elegir varios.",
            _ => "Paso 4 de 4 · El PIN maestro de la escuela. Si no lo tienes, pide el PIN maestro a administración.",
        };
        _reglaClave.Text = $"Al menos {Minimo} caracteres, con una mayúscula y un símbolo (por ejemplo: Profe.Rios.2026).";
        if (paso == PasoGrupos && _disponibles.Count == 0) _ = CargarGruposAsync();
    }

    private void ConfirmarDatos()
    {
        if (string.IsNullOrWhiteSpace(_documento.Text) || string.IsNullOrWhiteSpace(_nombres.Text))
        {
            _estado.Mostrar("Escribe al menos tu documento y tus nombres.", Tono.Aviso);
            (string.IsNullOrWhiteSpace(_documento.Text) ? _documento : _nombres).Focus();
            return;
        }
        _estado.Mostrar(null);
        Mostrar(PasoClave);
    }

    private void ConfirmarClave()
    {
        if (ContrasenaNueva.Problema(_clave.Text, _repetida.Text, Minimo) is { } problema)
        {
            _estado.Mostrar(problema, Tono.Aviso);
            _repetida.Text = string.Empty;
            return;
        }
        _estado.Mostrar(null);
        Mostrar(PasoGrupos);
    }

    private async Task CargarGruposAsync()
    {
        _gruposNota.Text = "Buscando los grupos del aula…";
        await Sesion.AsegurarEquipoAsync();
        var acceso = Sesion.Acceso;
        var lista = await acceso.ListarGruposDelAulaAsync(Sesion.Dispositivo, paraDocente: true);
        if (lista is null)
        {
            _gruposNota.Text = MensajesDeAcceso.Texto(acceso.UltimoError) + " Puedes seguir sin grupos y elegirlos después.";
            return;
        }
        _disponibles = lista;
        PintarGrupos();
    }

    private void PintarGrupos()
    {
        _grupos.Clear();
        _gruposNota.Text = _disponibles.Count == 0
            ? "Todavía no hay grupos en el aula. Podrás crearlos desde «Grupos» cuando entres."
            : "Toca los grupos que dictas.";
        foreach (var g in _disponibles.OrderBy(g => g.Nombre))
        {
            var id = g.Id;
            _grupos.Add(MarcoDeAcceso.Ficha(g.Nombre, _elegidos.Contains(id), (_, _) =>
            {
                if (!_elegidos.Remove(id)) _elegidos.Add(id);
                PintarGrupos();
            }));
        }
    }

    private async Task RegistrarAsync(string pin)
    {
        if (_ocupado) return;
        _ocupado = true;
        _teclado.Habilitado = false;
        _estado.Mostrar("Creando tu usuario…", Tono.Neutro);
        var bloqueado = false;
        try
        {
            await Sesion.AsegurarEquipoAsync();
            var documento = (_documento.Text ?? string.Empty).Trim();
            var clave = _clave.Text ?? string.Empty;
            var acceso = Sesion.Acceso;
            var nuevo = await acceso.RegistrarDocenteAsync(new RegistroDeDocente(
                pin, documento, (_nombres.Text ?? string.Empty).Trim(), (_apellidos.Text ?? string.Empty).Trim(), clave,
                _elegidos.Where(id => _disponibles.Any(g => g.Id == id)).ToList(), Sesion.Dispositivo));
            if (nuevo is null)
            {
                var error = acceso.UltimoError;
                var texto = MensajesDeAcceso.Texto(error);
                switch (error?.Codigo)
                {
                    case "pin_maestro_invalido":
                        await _teclado.SacudirAsync();
                        _estado.Mostrar(texto, Tono.Problema);
                        return;
                    case "pin_maestro_bloqueado":
                        bloqueado = true;
                        _teclado.Limpiar();
                        _estado.Mostrar(texto, Tono.Problema);
                        return;
                    case "secreto_debil":
                        Mostrar(PasoClave);
                        _repetida.Text = string.Empty;
                        _estado.Mostrar(texto, Tono.Problema);
                        return;
                    case "identificador_duplicado":
                        Mostrar(PasoDatos);
                        _estado.Mostrar(texto, Tono.Problema);
                        return;
                    case "datos_invalidos" when (error?.Detalle ?? string.Empty).Contains("grupo", StringComparison.OrdinalIgnoreCase):
                        _disponibles = [];
                        _elegidos.Clear();
                        Mostrar(PasoGrupos);
                        _estado.Mostrar(texto, Tono.Problema);
                        return;
                    case "datos_invalidos":
                        Mostrar(PasoDatos);
                        _estado.Mostrar(texto, Tono.Problema);
                        return;
                    default:
                        // Vencido, sin configurar, registro cerrado, desde una tableta o sin conexión: se dice qué pasó y lo escrito se conserva.
                        _teclado.Limpiar();
                        _estado.Mostrar(texto, Tono.Problema);
                        return;
                }
            }

            // Registrado: entra directo, con la contraseña que acaba de elegir (RF-06). Nada queda escrito.
            _estado.Mostrar($"Listo, {nuevo.Alias}: tu usuario quedó creado. Entrando…", Tono.Bien);
            var sesion = await acceso.IniciarSesionAsync(documento, clave, Sesion.Dispositivo);
            Limpiar();
            if (sesion is null || sesion.Usuario.Nivel < 2)
            {
                Sesion.AvisoDeAcceso = "Listo, tu usuario quedó creado. Entra con tu documento y tu contraseña.";
                await Shell.Current.GoToAsync("//login");
                return;
            }
            Sesion.Usuario = sesion.Usuario;
            Sesion.SesionObligatoria = true;
            Sesion.AvisoAlEntrar = $"Bienvenido, {nuevo.Alias}. Tu usuario quedó creado con el PIN maestro; la administración puede verlo en Seguridad del aula.";
            await Shell.Current.GoToAsync("../dashboard");
        }
        finally
        {
            _teclado.Habilitado = !bloqueado;
            _ocupado = false;
        }
    }

    private void Limpiar()
    {
        _documento.Text = _nombres.Text = _apellidos.Text = _clave.Text = _repetida.Text = string.Empty;
        _elegidos.Clear();
        _disponibles = [];
        _teclado.Limpiar();
        _paso = PasoDatos;
    }
}

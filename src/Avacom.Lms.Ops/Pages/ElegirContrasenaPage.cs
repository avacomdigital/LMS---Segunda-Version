using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Acceso;
using Avacom.Lms.Ops.Controls;
using Tono = Avacom.Lms.Ops.Controls.MarcoDeAcceso.Tono;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// «Elige tu contraseña» (RF-05): quien entró con una contraseña provisional —la de la hoja de acceso del primer arranque, o una que la administración
/// restableció— elige la suya antes de llegar al tablero (<c>PUT yo/credencial/</c>). Mientras no lo haga el nodo no le deja hacer nada más. La provisional
/// llega en memoria desde el acceso (<see cref="Sesion.TomarClaveProvisional"/>) para no tener que volver a escribirla; si no llegó, se pide.
/// </summary>
public sealed class ElegirContrasenaPage : ContentPage
{
    private readonly MarcoDeAcceso _marco = new();
    private readonly MarcoDeAcceso.Estado _estado = new();
    private readonly VerticalStackLayout _actualGrupo = new() { Spacing = 8, IsVisible = false };
    private readonly Entry _actual = MarcoDeAcceso.Campo("La contraseña con la que entraste", "Contraseña actual", secreto: true);
    private readonly Entry _nueva = MarcoDeAcceso.Campo("Tu contraseña nueva", "Contraseña nueva", secreto: true);
    private readonly Entry _repetida = MarcoDeAcceso.Campo("Escríbela otra vez", "Repite la contraseña nueva", secreto: true);
    private readonly Button _guardar;
    private string? _provisional;
    private bool _ocupado;

    public ElegirContrasenaPage()
    {
        Shell.SetNavBarIsVisible(this, false);
        Title = "Elige tu contraseña";
        Content = _marco;
        _marco.Titulo.Text = "Elige tu contraseña";
        _actualGrupo.Add(MarcoDeAcceso.Rotulo("Contraseña actual"));
        _actualGrupo.Add(_actual);
        _marco.Cuerpo.Add(_estado);
        _marco.Cuerpo.Add(_actualGrupo);
        _marco.Cuerpo.Add(MarcoDeAcceso.Rotulo("Contraseña nueva"));
        _marco.Cuerpo.Add(_nueva);
        _marco.Cuerpo.Add(MarcoDeAcceso.Rotulo("Repite la contraseña nueva"));
        _marco.Cuerpo.Add(_repetida);
        var (vista, boton) = MarcoDeAcceso.Principal("Guardar y entrar", async (_, _) => await GuardarAsync());
        _guardar = boton;
        _marco.Cuerpo.Add(vista);
        _marco.Cuerpo.Add(MarcoDeAcceso.Discreta("Salir sin cambiarla", async (_, _) => await SalirAsync()));
        _repetida.Completed += async (_, _) => await GuardarAsync();
    }

    private int Minimo
    {
        get
        {
            var perfil = Sesion.Usuario?.Menu ?? "teacher";
            return ContrasenaNueva.Minimo(Sesion.Configuracion, perfil, perfil is "admin" or "technician" ? 12 : 8);
        }
    }

    protected override void OnAppearing()
    {
        base.OnAppearing();
        _provisional ??= Sesion.TomarClaveProvisional();
        _actualGrupo.IsVisible = _provisional is null;
        _marco.Mensaje.Text = $"Entraste con una contraseña provisional. Elige una tuya para seguir: al menos {Minimo} caracteres; el equipo te dirá si le falta algo (mayúscula, número o símbolo).";
        _estado.Mostrar(null);
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _actual.Text = _nueva.Text = _repetida.Text = string.Empty;
    }

    private async Task GuardarAsync()
    {
        if (_ocupado) return;
        var actual = _provisional ?? _actual.Text ?? string.Empty;
        if (actual.Length == 0) { _estado.Mostrar("Escribe la contraseña con la que entraste.", Tono.Aviso); _actual.Focus(); return; }
        if (ContrasenaNueva.Problema(_nueva.Text, _repetida.Text, Minimo) is { } problema)
        {
            _estado.Mostrar(problema, Tono.Aviso);
            _repetida.Text = string.Empty;
            return;
        }
        _ocupado = true;
        _guardar.IsEnabled = false;
        _estado.Mostrar("Guardando tu contraseña…", Tono.Neutro);
        try
        {
            var acceso = Sesion.Acceso;
            if (!await acceso.CambiarMiContrasenaAsync(actual, _nueva.Text!))
            {
                var error = acceso.UltimoError;
                if (error is { Codigo: "credenciales_invalidas" })
                {
                    _provisional = null;
                    _actualGrupo.IsVisible = true;
                    _actual.Text = string.Empty;
                    _estado.Mostrar("La contraseña actual no coincide. Escríbela otra vez.", Tono.Problema);
                    return;
                }
                if (error is { Estado: > 0 }) _nueva.Text = _repetida.Text = string.Empty;
                _estado.Mostrar(MensajesDeAcceso.Texto(error), Tono.Problema);
                return;
            }
            _provisional = null;
            _actual.Text = _nueva.Text = _repetida.Text = string.Empty;
            if (Sesion.Usuario is { } u) Sesion.Usuario = u with { DebeCambiarCredencial = false };
            await Shell.Current.GoToAsync("../dashboard");
        }
        finally
        {
            _guardar.IsEnabled = true;
            _ocupado = false;
        }
    }

    /// <summary>Sin contraseña propia el nodo no deja hacer nada: salir cierra la sesión y vuelve al acceso.</summary>
    private async Task SalirAsync()
    {
        _provisional = null;
        await Sesion.CerrarSesionDeUsuarioAsync();
        await Shell.Current.GoToAsync("//login");
    }
}

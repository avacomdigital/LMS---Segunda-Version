using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ui.Design;

/// <summary>
/// El perfil de pantalla elegido en OPS (resolución × escala de Windows), guardado en las preferencias del equipo.
/// Todos los visores del aula lo leen al ajustar sus medios y se reajustan cuando cambia (<see cref="Cambio"/>).
/// </summary>
public static class AjustesDePantalla
{
    private const string Clave = "aula_perfil_pantalla";
    private static PerfilDePantalla? _actual;

    public static event EventHandler<PerfilDePantalla>? Cambio;

    public static PerfilDePantalla Actual
    {
        get
        {
            if (_actual is not null) return _actual;
            try { _actual = PerfilDePantalla.Leer(Preferences.Default.Get<string?>(Clave, null)); }
            catch { _actual = PerfilDePantalla.Auto; }   // preferencias no disponibles: automático, sin romper la clase
            return _actual;
        }
        set
        {
            if (Equals(_actual, value)) return;
            _actual = value;
            try { if (value.EsAuto) Preferences.Default.Remove(Clave); else Preferences.Default.Set(Clave, value.Clave); } catch { }
            Cambio?.Invoke(null, value);
        }
    }

    /// <summary>Lo que reporta el sistema ahora (píxeles físicos y escala de Windows) llevado al perfil estándar más parecido.</summary>
    public static PerfilDePantalla Detectado()
    {
        try
        {
            var d = DeviceDisplay.Current.MainDisplayInfo;
            return PerfilDePantalla.Detectar(d.Width, d.Density);
        }
        catch { return PerfilDePantalla.Auto; }
    }
}

using Android.App;
using Android.Content.PM;
using Android.OS;
using AndroidX.Activity;
using Avacom.Lms.Student.Examen;

namespace Avacom.Lms.Student;

/// <summary>
/// La Activity única de Student. Es la capa de aplicación del bloqueo de examen en Android (kiosk.md §3.4): las barras del sistema se reaplican al ganar el foco, Atrás se ignora
/// mientras rige la capa de la aplicación y lo que la Activity ve (se pausa, vuelve, se intenta salir) se cuenta a <see cref="AndroidKioskService"/>, que es quien lo informa como
/// incidente. Toda la política vive en el servicio (<see cref="AndroidKioskService.Actual"/>): aquí sólo se reenvía lo que sólo la Activity ve.
///
/// <c>SingleTask</c> evita que otra instancia de la Activity se apile. La orientación no se restringe (como antes).
/// </summary>
[Activity(Theme = "@style/Maui.SplashTheme", MainLauncher = true, LaunchMode = LaunchMode.SingleTask, ConfigurationChanges = ConfigChanges.ScreenSize | ConfigChanges.Orientation | ConfigChanges.UiMode | ConfigChanges.ScreenLayout | ConfigChanges.SmallestScreenSize | ConfigChanges.Density)]
public class MainActivity : MauiAppCompatActivity
{
    protected override void OnCreate(Bundle? savedInstanceState)
    {
        base.OnCreate(savedInstanceState);
        // Atrás por el despachador de AndroidX (no sólo OnBackPressed): con el retroceso predictivo de las versiones nuevas de Android, OnBackPressed deja de invocarse.
        // La devolución de llamada se registra DESPUÉS de la de MAUI, así que es la primera en recibir Atrás; si no hay examen se la pasa a MAUI como siempre.
        OnBackPressedDispatcher.AddCallback(this, new RetrocesoDelExamen(this));
    }

    /// <summary>Deslizar desde el borde muestra las barras: se reaplican en cada ganancia de foco mientras rija el bloqueo.</summary>
    public override void OnWindowFocusChanged(bool hasFocus)
    {
        base.OnWindowFocusChanged(hasFocus);
        if (hasFocus) AndroidKioskService.Actual?.AlGanarFoco(this);
    }

    protected override void OnPause()
    {
        base.OnPause();
        AndroidKioskService.Actual?.AlPausar(this);
    }

    protected override void OnResume()
    {
        base.OnResume();
        AndroidKioskService.Actual?.AlReanudar();
    }

    /// <summary>Atrás durante el examen: se traga y se cuenta (<c>cierre_bloqueado</c>, vía <c>atras</c>). Sin examen —o en un nivel que no lo pide— se comporta como siempre.</summary>
    private sealed class RetrocesoDelExamen(MainActivity actividad) : OnBackPressedCallback(true)
    {
        public override void HandleOnBackPressed()
        {
            if (AndroidKioskService.Actual is { } kiosco && kiosco.AlPulsarAtras(actividad)) return;
            // Nadie lo ignora: se desactiva esta devolución un instante para que el despachador entregue Atrás a la siguiente (la de MAUI) y se reactiva.
            Enabled = false;
            try { actividad.OnBackPressedDispatcher.OnBackPressed(); }
            finally { Enabled = true; }
        }
    }
}

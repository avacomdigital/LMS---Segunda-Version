using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Student.Examen;

/// <summary>
/// El servicio de kiosco de ESTA plataforma, uno por proceso (kiosk.md §2): <c>AndroidKioskService</c>, <c>WindowsKioskService</c> o <see cref="KioscoNulo"/> donde no hay bloqueo.
/// Seguro desde cualquier hilo. Si el servicio de la plataforma no se pudo crear, la tableta cae a <see cref="KioscoNulo"/> —que declara «abierto», la verdad— en vez de tumbar la app.
/// </summary>
internal static class KioscoReal
{
    /// <summary>Variable de entorno de las cuentas dedicadas al examen: con <c>1</c>, Student arranca en pantalla completa (kiosk.md §2: el alumno no debe ver el escritorio en ningún momento).</summary>
    public const string VariableDeKiosco = "AVACOM_STUDENT_KIOSCO";

    private static readonly Lazy<IKioskService> Unico = new(CrearDeLaPlataforma, LazyThreadSafetyMode.ExecutionAndPublication);

    /// <summary>La instancia única de este proceso.</summary>
    public static IKioskService Crear() => Unico.Value;

    private static IKioskService CrearDeLaPlataforma()
    {
        try
        {
#if ANDROID
            return new AndroidKioskService();
#elif WINDOWS
            return new WindowsKioskService();
#else
            return new KioscoNulo();
#endif
        }
        catch (Exception ex)
        {
            RegistroLocal.Error(Canal.Dispositivo, "kiosco.crear", "No se pudo crear el servicio de kiosco de la plataforma; esta tableta declara «abierto»", null, ex);
            return new KioscoNulo();
        }
    }

    /// <summary>
    /// Pantalla completa desde el arranque, SÓLO en las cuentas dedicadas al examen (<c>AVACOM_STUDENT_KIOSCO=1</c>); para todos los demás no cambia nada. Se llama una vez desde
    /// <c>App.CreateWindow</c> con la ventana recién creada: la ventana nativa no existe hasta que MAUI crea su manejador, así que se espera a que exista (una sola vez) y entonces
    /// se pide la pantalla completa. Nunca lanza.
    /// </summary>
    public static void PantallaCompletaDeArranque(Window ventana)
    {
        try
        {
            if (Environment.GetEnvironmentVariable(VariableDeKiosco) != "1") return;
            var hecho = 0;
            void Intentar()
            {
                if (ventana.Handler?.PlatformView is null || Interlocked.Exchange(ref hecho, 1) == 1) return;
                _ = Crear().EnterFullScreenAsync();
            }
            ventana.HandlerChanged += (_, _) => Intentar();
            ventana.Created += (_, _) => Intentar();
            Intentar();
        }
        catch (Exception ex)
        {
            RegistroLocal.Advertencia(Canal.Dispositivo, "kiosco.pantalla_completa_arranque", "No se pudo preparar la pantalla completa de arranque", null, ex);
        }
    }
}

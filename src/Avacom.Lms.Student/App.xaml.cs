using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Microsoft.Extensions.DependencyInjection;

namespace Avacom.Lms.Student;

public partial class App : Application
{
	private static int _atendiendoRechazo;

	public App()
	{
		InitializeComponent();
		// Los fallos de reproducción del visor del aula se anotan en fallos-student.log (ver RegistroDeFallos.Ruta).
		Avacom.Lms.Ui.Controls.AulaContenidoView.NombreApp = "student";
		// Una sola suscripción para toda la vida de la app (App se construye una vez): el nodo rechazó la sesión de la persona (007-10, PAN-103).
		ClienteJson.SesionRechazada += AlRechazarLaSesion;
	}

	protected override Window CreateWindow(IActivationState? activationState)
	{
		var ventana = new Window(new AppShell());
		// Pantalla completa desde el arranque sólo con AVACOM_STUDENT_KIOSCO=1 (cuentas dedicadas al examen); sin la variable no hace nada.
		Avacom.Lms.Student.Examen.KioscoReal.PantallaCompletaDeArranque(ventana);
		// Segundo plano, vuelta y cierre: la tableta declara «reconectando», «conectado» y «salió» (007-04).
		CicloDeVida.Enganchar(ventana);
		// MOD-019: arranque tras reinicio (canal dispositivo) y entrega de los avisos locales al nodo cada minuto, de mejor esfuerzo.
		RegistroLocal.Info(Canal.Dispositivo, "app.arranque", "Student arrancó", new { version = Sesion.VersionApp, plataforma = Sesion.Plataforma, servidor = Sesion.BaseUri.ToString() });
		Sesion.EntregadorDeLogs.Iniciar();
		return ventana;
	}

	/// <summary>
	/// El nodo dijo que la sesión ya no vale (caducó, se cerró por inactividad, se abrió en otra tableta…). Se vuelve a identificarse con un
	/// aviso tranquilo: lo que el alumno hizo está guardado. La clase guardada NO se olvida: tras volver a identificarse la misma persona
	/// se readmite sola (BR-053). Llega desde un hilo de fondo, así que todo pasa por el hilo de la interfaz.
	/// </summary>
	private static void AlRechazarLaSesion(ErrorAula error)
	{
		// Sin persona identificada no hay sesión que perder (por ejemplo, la cola que se vacía después de «Salir»).
		if (Sesion.Usuario is null) return;
		if (Interlocked.Exchange(ref _atendiendoRechazo, 1) == 1) return;
		MainThread.BeginInvokeOnMainThread(async () =>
		{
			try
			{
				ClienteJson.Token = null; Sesion.Usuario = null;   // el pase ya no vale; no hace falta avisarle nada al nodo
				if (Shell.Current is null || Shell.Current.CurrentPage is Pages.ConnectionPage) return;
				Sesion.RecordarCodigo = true;   // es la misma persona: que no tenga que volver a escribir su código
				await Shell.Current.GoToAsync("//connection");
				Avisos.Mostrar(error.CerradaEnOtroDispositivo
					? "Abriste tu sesión en otra tableta. Tu trabajo está a salvo; entra aquí de nuevo si quieres seguir aquí."
					: "Tu sesión terminó. Lo que hiciste está guardado; entra de nuevo para continuar.");
			}
			catch (Exception ex) { RegistroDeFallos.Escribir("student", "App.SesionRechazada", ex); }
			finally { Volatile.Write(ref _atendiendoRechazo, 0); }
		});
	}
}
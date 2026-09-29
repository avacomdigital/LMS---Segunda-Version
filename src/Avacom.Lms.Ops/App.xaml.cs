using Microsoft.Extensions.DependencyInjection;

namespace Avacom.Lms.Ops;

public partial class App : Application
{
	public App()
	{
		InitializeComponent();
		// Los fallos de reproducción del visor del aula se anotan en fallos-ops.log (ver RegistroDeFallos.Ruta).
		Avacom.Lms.Ui.Controls.AulaContenidoView.NombreApp = "ops";
		// 007-10: si el nodo rechaza la sesión (caducó, se cerró por inactividad, se abrió en otro equipo) se vuelve al acceso desde cualquier pantalla.
		Avacom.Lms.Core.Services.ClienteJson.SesionRechazada += error => MainThread.BeginInvokeOnMainThread(async () => await VolverAlAccesoAsync(error));
	}

	private static bool _volviendoAlAcceso;

	/// <summary>
	/// Manejador global de la sesión rechazada. Varias peticiones pueden ser rechazadas a la vez (cada pantalla sondea por su lado): se
	/// vuelve una sola vez al acceso y las demás se ignoran. La clase abierta no se toca: sigue guardada y se retoma al entrar de nuevo.
	/// Corre en el hilo principal porque navegar desde un evento de fondo no está permitido.
	/// </summary>
	private static async Task VolverAlAccesoAsync(Avacom.Lms.Core.Models.ErrorAula error)
	{
		if (_volviendoAlAcceso || Shell.Current is not { } shell || shell.CurrentPage is Pages.LoginPage) return;
		var sinIdentificar = Sesion.Usuario is null;
		// Sin persona identificada sólo importa «sesión requerida»: el nodo exige sesión y esta app entró sin ella (modo prototipo).
		if (sinIdentificar && error.Codigo != "sesion_requerida") return;
		_volviendoAlAcceso = true;
		try
		{
			Sesion.AvisoDeAcceso = error.CerradaEnOtroDispositivo
				? "Abriste tu sesión en otro equipo. Tu clase sigue guardada; entra aquí de nuevo si quieres continuar aquí."
				: sinIdentificar
					? "Este equipo pide identificarte. Escribe tu documento y tu clave."
					: "Tu sesión terminó. Tu clase y lo que llevabas siguen guardados; entra de nuevo para continuar.";
			Sesion.SesionObligatoria = true;
			Avacom.Lms.Core.Services.ClienteJson.Token = null;
			Sesion.Usuario = null;
			await shell.GoToAsync("//login");
		}
		finally { _volviendoAlAcceso = false; }
	}

	protected override Window CreateWindow(IActivationState? activationState)
	{
		return new Window(new AppShell());
	}
}
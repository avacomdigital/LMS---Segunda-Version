using Microsoft.UI.Xaml;

// To learn more about WinUI, the WinUI project structure,
// and more about our project templates, see: http://aka.ms/winui-project-info.

namespace Avacom.Lms.Ops.WinUI;

/// <summary>
/// Provides application-specific behavior to supplement the default Application class.
/// </summary>
public partial class App : MauiWinUIApplication
{
	/// <summary>
	/// Initializes the singleton application object.  This is the first line of authored code
	/// executed, and as such is the logical equivalent of main() or WinMain().
	/// </summary>
	public App()
	{
		this.InitializeComponent();
		// Un fallo no controlado en el aula queda en %LOCALAPPDATA%\AVACOM\lms para poder diagnosticarlo y, si la app va a caer, se intenta llevar
		// a la bitácora del nodo antes de que el proceso muera (sin esto, el error que cerraba OPS era justo el que nunca llegaba).
		this.UnhandledException += (_, e) => Avacom.Lms.Core.Services.RegistroDeFallos.Escribir("ops", "WinUI.UnhandledException", e.Exception, fatal: !e.Handled);
	}

	protected override MauiApp CreateMauiApp() => MauiProgram.CreateMauiApp();
}


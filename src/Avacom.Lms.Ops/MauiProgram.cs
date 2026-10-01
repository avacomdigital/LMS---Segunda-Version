using Microsoft.Extensions.Logging;
using Microsoft.Maui.LifecycleEvents;

namespace Avacom.Lms.Ops;

public static class MauiProgram
{
	public static MauiApp CreateMauiApp()
	{
		Avacom.Lms.Ui.Design.WebViewAjustes.Aplicar();   // antes de que exista cualquier WebView (video del aula sin superposición de DirectComposition)
		Avacom.Lms.Core.Services.RegistroDeFallos.Observar("ops");
		Sesion.PrepararAparato();   // MOD-019: logs locales con versión y aparato; el id del equipo persiste entre arranques
		var builder = MauiApp.CreateBuilder();
		builder
			.UseMauiApp<App>()
			.ConfigureFonts(fonts =>
			{
				// Inter 4.1 (OFL) en cuatro pesos estáticos; los alias son los que usan Ds y los estilos XAML.
				fonts.AddFont("Inter-Light.ttf", "InterLight");
				fonts.AddFont("Inter-Regular.ttf", "InterRegular");
				fonts.AddFont("Inter-Medium.ttf", "InterMedium");
				fonts.AddFont("Inter-SemiBold.ttf", "InterSemiBold");
			})
			.ConfigureLifecycleEvents(eventos =>
			{
#if WINDOWS
				// El nodo principal del aula se usa siempre a toda pantalla: la ventana arranca maximizada, no en el tamaño por
				// defecto de WinUI. Se hace al crearse la ventana, antes de mostrarla, para que no se vea el cambio de tamaño.
				eventos.AddWindows(windows => windows.OnWindowCreated(ventana =>
				{
					if (ventana.AppWindow?.Presenter is Microsoft.UI.Windowing.OverlappedPresenter presentador)
						presentador.Maximize();
				}));
#endif
			});

#if DEBUG
		builder.Logging.AddDebug();
#endif

		return builder.Build();
	}
}

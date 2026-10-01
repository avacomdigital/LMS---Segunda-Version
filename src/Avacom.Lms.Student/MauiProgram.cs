using Microsoft.Extensions.Logging;

namespace Avacom.Lms.Student;

public static class MauiProgram
{
	public static MauiApp CreateMauiApp()
	{
		Avacom.Lms.Ui.Design.WebViewAjustes.Aplicar();   // antes de que exista cualquier WebView (video del aula sin superposición de DirectComposition)
		Avacom.Lms.Core.Services.RegistroDeFallos.Observar("student");
		Sesion.PrepararAparato();   // MOD-019: logs locales con versión y aparato; el id de la tableta persiste entre arranques
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
			});

#if DEBUG
		builder.Logging.AddDebug();
#endif

		return builder.Build();
	}
}

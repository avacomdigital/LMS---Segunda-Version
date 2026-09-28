using Microsoft.Extensions.Logging;

namespace Avacom.Lms.Student;

public static class MauiProgram
{
	public static MauiApp CreateMauiApp()
	{
		Avacom.Lms.Core.Services.RegistroDeFallos.Observar("student");
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

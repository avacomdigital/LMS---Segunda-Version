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
				// Aula · Design System: Lexend (OFL) para la interfaz y Andika (OFL) para lectura en Inicial y Primaria.
				// Los alias son los que usan Ds y los estilos XAML.
				fonts.AddFont("Lexend-Regular.ttf", "Lexend");
				fonts.AddFont("Lexend-Medium.ttf", "LexendMedium");
				fonts.AddFont("Lexend-SemiBold.ttf", "LexendSemiBold");
				fonts.AddFont("Andika-Regular.ttf", "Andika");
				fonts.AddFont("Andika-Bold.ttf", "AndikaBold");
			});

#if DEBUG
		builder.Logging.AddDebug();
#endif

		// Campos de texto con el aspecto del Aula · Design System (sin el subrayado de Windows).
		Avacom.Lms.Ui.Controls.NeumoChrome.Registrar();
		return builder.Build();
	}
}

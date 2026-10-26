using Microsoft.Extensions.Logging;

namespace Avacom.Lms.Student;

public static class MauiProgram
{
	public static MauiApp CreateMauiApp()
	{
		Avacom.Lms.Ui.Design.WebViewAjustes.Aplicar();   // antes de que exista cualquier WebView (video del aula sin superposición de DirectComposition)
		Avacom.Lms.Core.Services.RegistroDeFallos.Observar("student");
#if ANDROID
		if (OperatingSystem.IsAndroidVersionAtLeast(24)) Avacom.Lms.Core.IdentidadDeDispositivo.IdentidadDeEquipo.Proveedor = new Platforms.Android.ProveedorKeystore();   // MOD-018 · Fase 5: clave de identidad en el Keystore (Android 7 en adelante)
#else
		Avacom.Lms.Core.IdentidadDeDispositivo.IdentidadDeEquipo.Proveedor = Avacom.Lms.Core.IdentidadDeDispositivo.ProveedorCng.SiEsWindows("AVACOM-Identidad-Student-v1");   // y en CNG de Windows (TPM si hay)
#endif
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

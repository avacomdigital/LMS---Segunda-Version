namespace Avacom.Lms.Ui.Design;

/// <summary>
/// Argumentos con los que WebView2 (Windows) debe arrancar en OPS y Student. Se llama UNA vez, al principio de
/// <c>CreateMauiApp</c>, antes de que exista cualquier WebView: el entorno de WebView2 lee la variable al crearse.
///
/// <para><b>Superposiciones de video de DirectComposition desactivadas.</b> Con ellas encendidas (lo normal), el video del curso
/// se dibujaba en el aula a (ancho del recuadro ÷ ancho de la pantalla) de su tamaño —un recuadro de 1155 px en una pantalla de
/// 1920 mostraba el fotograma a 695 px—, pegado arriba a la izquierda, con el resto del recuadro en negro y los controles
/// a todo el ancho. Lo que dibuja Chromium dentro de la WebView es correcto (<c>Page.captureScreenshot</c> da el fotograma
/// completo); el fallo estaba sólo en cómo la superposición de hardware se presentaba dentro de la ventana de MAUI. Sin
/// la superposición el video se compone como cualquier otra capa y llena su recuadro a cualquier resolución o escala.
/// Ver 02-classroom-engine/responsive.md.</para>
/// </summary>
public static class WebViewAjustes
{
    public const string Variable = "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS";
    public const string SinSuperposicionDeVideo = "--disable-features=DirectCompositionVideoOverlays,DirectCompositionLetterboxVideoOverlays";

    public static void Aplicar()
    {
        if (!OperatingSystem.IsWindows()) return;
        try
        {
            var actual = Environment.GetEnvironmentVariable(Variable);
            if (actual?.Contains(SinSuperposicionDeVideo, StringComparison.Ordinal) == true) return;
            // Se respeta lo que ya hubiera (p. ej. depuración remota): sólo se añade.
            Environment.SetEnvironmentVariable(Variable, string.IsNullOrWhiteSpace(actual) ? SinSuperposicionDeVideo : $"{actual} {SinSuperposicionDeVideo}");
        }
        catch { /* sin variable de entorno: el video se ve como antes, el resto del aula no depende de esto */ }
    }
}

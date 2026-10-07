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
#if ANDROID
        AjustarAndroid();
#endif
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

    /// <summary>
    /// <b>Android.</b> Fija la escala de una WebView que muestra una página del curso hecha para un escenario fijo (la cátedra y la teoría en html).
    /// Medido en un emulador de tableta (Bugfix 02): la página veía <c>window.innerWidth × innerHeight</c> = 1669 × 674 cuando el recuadro real era de
    /// 1248 × 503 (<c>clientWidth</c>, <c>visualViewport</c>), porque la WebView se alejaba (zoom-out) para encajar el contenido; el guion del curso calcula
    /// su escala con <c>innerWidth/innerHeight</c> y la lámina quedaba recortada por abajo y por la derecha. Sin zoom, sin «ventana ancha» y con escala
    /// inicial 100, la ventana de la página y el recuadro coinciden (medido: 2496 × 1007 las dos) y la lámina entra completa y centrada, como en Windows.
    /// En el resto de plataformas no hace nada. Sólo se aplica a la WebView del html del curso: los reproductores propios y los laboratorios no cambian.
    /// </summary>
    public static void FijarEscala(Microsoft.Maui.Controls.WebView web)
    {
#if ANDROID
        web.HandlerChanged += (_, _) =>
        {
            try
            {
                if (web.Handler?.PlatformView is not global::Android.Webkit.WebView nativa) return;
                var ajustes = nativa.Settings;
                ajustes.UseWideViewPort = false;
                ajustes.LoadWithOverviewMode = false;
                ajustes.SetSupportZoom(false);
                ajustes.BuiltInZoomControls = false;
                ajustes.DisplayZoomControls = false;
                nativa.SetInitialScale(100);
            }
            catch { /* una WebView que no acepta el ajuste conserva el comportamiento de siempre */ }
        };
#endif
    }

#if ANDROID
    /// <summary>
    /// <b>Android.</b> La WebView exige un toque del usuario para arrancar cualquier video o audio (<c>MediaPlaybackRequiresUserGesture</c>, verdadero por defecto),
    /// y entonces el <c>autoplay</c> que el curso declara para la cátedra (el profesor lleva el ritmo) se ignora en silencio: la tableta mostraba el video
    /// parado. Se desactiva esa exigencia sólo en las WebView del aula; el audio y el video sin <c>autoplay</c> siguen esperando el toque como siempre.
    /// (El tráfico HTTP sin cifrar hacia el nodo del aula se permite en el manifiesto de cada app: <c>usesCleartextTraffic</c>.)
    /// </summary>
    private static void AjustarAndroid()
    {
        Microsoft.Maui.Handlers.WebViewHandler.Mapper.AppendToMapping("AvacomMediosDelAula", static (handler, _) =>
        {
            try { handler.PlatformView.Settings.MediaPlaybackRequiresUserGesture = false; }
            catch { /* una WebView que no acepta el ajuste conserva el comportamiento de siempre */ }
        });
    }
#endif
}

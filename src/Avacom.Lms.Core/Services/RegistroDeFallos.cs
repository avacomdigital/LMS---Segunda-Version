namespace Avacom.Lms.Core.Services;

/// <summary>
/// Deja constancia de una excepción no controlada en un archivo local, para que
/// un fallo en el aula se pueda diagnosticar después. Sin Internet y sin
/// consola, un archivo en el perfil del usuario es lo único que queda.
///
/// Ruta: %LOCALAPPDATA%\AVACOM\lms\fallos-{app}.log
/// </summary>
public static class RegistroDeFallos
{
    private static readonly object Cerrojo = new();

    /// <summary>
    /// La carpeta del registro. <c>AVACOM_LMS_DIR_FALLOS</c> la sustituye (lo usan las pruebas automáticas para no escribir en el registro real de quien
    /// trabaja en el equipo); sin ella, <c>%LOCALAPPDATA%\AVACOM\lms</c>.
    /// </summary>
    private static string Carpeta =>
        Environment.GetEnvironmentVariable("AVACOM_LMS_DIR_FALLOS") is { Length: > 0 } propia
            ? propia
            : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AVACOM", "lms");

    public static string Ruta(string app) => Path.Combine(Carpeta, $"fallos-{app}.log");

    public static void Escribir(string app, string origen, Exception? excepcion)
    {
        if (excepcion is null) return;
        try
        {
            var ruta = Ruta(app);
            Directory.CreateDirectory(Path.GetDirectoryName(ruta)!);
            lock (Cerrojo)
            {
                File.AppendAllText(ruta,
                    $"[{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss zzz}] {origen}{Environment.NewLine}{excepcion}{Environment.NewLine}{Environment.NewLine}");
            }
        }
        catch (Exception)
        {
            // Si no se puede escribir el registro, no hay nada más que hacer: no se relanza.
        }
    }

    /// <summary>Engancha los tres orígenes de excepciones no controladas del proceso.</summary>
    public static void Observar(string app)
    {
        AppDomain.CurrentDomain.UnhandledException += (_, e) => Escribir(app, "AppDomain.UnhandledException", e.ExceptionObject as Exception);
        TaskScheduler.UnobservedTaskException += (_, e) => Escribir(app, "TaskScheduler.UnobservedTaskException", e.Exception);
    }
}

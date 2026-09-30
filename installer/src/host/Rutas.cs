namespace Avacom.Ops.Host;

/// <summary>
/// Donde esta cada cosa. Se resuelve desde la ubicacion del propio ejecutable,
/// asi que el producto se puede instalar en cualquier carpeta.
///
/// Separacion deliberada:
///   Program Files  -> lo que instala el instalador y nunca cambia (solo lectura)
///   ProgramData    -> lo que cambia con el uso (configuracion, base de datos, logs)
///
/// Y separacion respecto a AVACOM Biblioteca: la biblioteca es dueña de
/// %ProgramData%\AVACOM\content. OPS Master no escribe ahi jamas; solo lee
/// la nota de enlace (link.json), y lo hace el backend, no este proceso.
/// </summary>
internal static class Rutas
{
    /// <summary>Carpeta de instalacion, p. ej. C:\Program Files\AVACOM\OPS Master.</summary>
    public static string RaizInstalacion { get; } = ResolverRaiz();

    public static string CarpetaRuntime => Path.Combine(RaizInstalacion, "Runtime");
    public static string CarpetaBackend => Path.Combine(RaizInstalacion, "Backend");
    public static string CarpetaApp => Path.Combine(RaizInstalacion, "App");

    public static string PythonExe => Path.Combine(CarpetaRuntime, "Python", "python.exe");
    public static string GuionServidor => Path.Combine(CarpetaRuntime, "avacom_ops_backend.py");
    public static string ManagePy => Path.Combine(CarpetaBackend, "manage.py");
    public static string AppExe => Path.Combine(CarpetaApp, "Avacom.Lms.Ops.exe");
    public static string HostExe { get; } = Environment.ProcessPath
        ?? Path.Combine(CarpetaRuntime, "Avacom.Ops.Host.exe");

    /// <summary>
    /// Estado mutable del nodo. Nunca dentro de Program Files.
    /// AVACOM_OPS_DATOS existe solo para las pruebas del propio instalador
    /// (ensayar una actualizacion sin tocar el estado real del equipo). En un
    /// nodo instalado no esta definida.
    /// </summary>
    public static string RaizDatos { get; } =
        Environment.GetEnvironmentVariable("AVACOM_OPS_DATOS") is { Length: > 0 } sustituta
            ? sustituta
            : Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                "AVACOM", "OPS Master");

    public static string CarpetaConfig => Path.Combine(RaizDatos, "Config");
    public static string CarpetaDatos => Path.Combine(RaizDatos, "Data");
    public static string CarpetaLogs => Path.Combine(RaizDatos, "Logs");
    public static string CarpetaRespaldos => Path.Combine(RaizDatos, "Respaldos");
    public static string ArchivoManifiesto => Path.Combine(RaizInstalacion, "manifiesto.json");

    public static string ArchivoConfig => Path.Combine(CarpetaConfig, "backend.env");
    public static string BaseDeDatos => Path.Combine(CarpetaDatos, "ops-master.sqlite3");

    public static void AsegurarCarpetasDeEstado()
    {
        Directory.CreateDirectory(CarpetaConfig);
        Directory.CreateDirectory(CarpetaDatos);
        Directory.CreateDirectory(CarpetaLogs);
        Directory.CreateDirectory(CarpetaRespaldos);
    }

    private static string ResolverRaiz()
    {
        // El host vive en <instalacion>\Runtime\Avacom.Ops.Host.exe.
        var exe = Environment.ProcessPath ?? AppContext.BaseDirectory;
        var carpeta = Path.GetDirectoryName(Path.GetFullPath(exe)) ?? AppContext.BaseDirectory;
        var padre = Path.GetDirectoryName(carpeta.TrimEnd(Path.DirectorySeparatorChar));
        return padre ?? carpeta;
    }
}

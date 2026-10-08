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
    /// AVACOM_OPS_DATOS existe solo para los ensayos del propio instalador
    /// (levantar el paquete o ensayar una actualizacion sin tocar el estado real del
    /// equipo), y solo vale si el ensayo lo CONFIRMA con AVACOM_OPS_ENSAYO=1: una
    /// AVACOM_OPS_DATOS olvidada en las variables de Windows no puede llevarse el
    /// estado de un nodo real a otra carpeta.
    /// </summary>
    public static string RaizDatos { get; } =
        EsEnsayo
            ? Environment.GetEnvironmentVariable("AVACOM_OPS_DATOS")!
            : Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                "AVACOM", "OPS Master");

    public static string CarpetaConfig => Path.Combine(RaizDatos, "Config");
    public static string CarpetaDatos => Path.Combine(RaizDatos, "Data");
    public static string CarpetaLogs => Path.Combine(RaizDatos, "Logs");
    public static string CarpetaRespaldos => Path.Combine(RaizDatos, "Respaldos");

    /// <summary>
    /// La cache de medios del nodo: los videos, audios, imagenes, PDF y paginas html que el nodo trae de AVACOM Contenido una sola vez y reparte a las
    /// tabletas. Es REGENERABLE (si se borra, se vuelve a llenar sola), asi que no entra en las copias de seguridad y se borra al desinstalar. Solo el
    /// servicio (SYSTEM) y los administradores la leen: lo que hay ahi son medios de examen, y no deben quedar a la mano de cualquier usuario del equipo.
    /// </summary>
    public static string CarpetaCacheMedios => Path.Combine(RaizDatos, "CacheMedios");
    public static string ArchivoManifiesto => Path.Combine(RaizInstalacion, "manifiesto.json");

    public static string ArchivoConfig => Path.Combine(CarpetaConfig, "backend.env");
    public static string BaseDeDatos => Path.Combine(CarpetaDatos, "ops-master.sqlite3");

    /// <summary>
    /// true cuando el host corre en un ENSAYO del propio instalador: una carpeta de estado
    /// de pruebas (AVACOM_OPS_DATOS) confirmada con AVACOM_OPS_ENSAYO=1. Nunca es un nodo
    /// real. Solo lo usan los ensayos para poder levantar el paquete en otro puerto sin
    /// tocar el equipo.
    /// </summary>
    public static bool EsEnsayo =>
        Environment.GetEnvironmentVariable("AVACOM_OPS_ENSAYO") == "1"
        && Environment.GetEnvironmentVariable("AVACOM_OPS_DATOS") is { Length: > 0 };

    /// <summary>
    /// Donde WebView2 guarda su perfil si nadie le dice otra cosa: junto al
    /// ejecutable. En Program Files quien da la clase no puede escribir, y es lo
    /// que cerraba la aplicacion al abrir una leccion con audio, video, PDF o
    /// laboratorio. El instalador crea esta carpeta con permiso de escritura para
    /// los usuarios, como red de seguridad por si la aplicacion se abre sin pasar
    /// por el lanzador.
    /// </summary>
    public static string PerfilWebViewJuntoAlExe => Path.Combine(CarpetaApp, "Avacom.Lms.Ops.exe.WebView2");

    /// <summary>El perfil de WebView2 de quien da la clase: dentro de su propio perfil de Windows, siempre escribible.</summary>
    public static string PerfilWebViewDelUsuario => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "AVACOM", "OPS Master", "WebView2");

    public static void AsegurarCarpetasDeEstado()
    {
        Directory.CreateDirectory(CarpetaConfig);
        Directory.CreateDirectory(CarpetaDatos);
        Directory.CreateDirectory(CarpetaLogs);
        Directory.CreateDirectory(CarpetaRespaldos);
        Directory.CreateDirectory(CarpetaCacheMedios);
        RestringirALaAdministracion(CarpetaCacheMedios);
    }

    /// <summary>
    /// Quita los permisos heredados de ProgramData (donde los usuarios pueden leer) y deja control total solo a SYSTEM y a los administradores. Si no se
    /// puede (un ensayo sin privilegios, un disco sin permisos), la cache sigue funcionando con los permisos que tenga: no es motivo para no arrancar.
    /// </summary>
    private static void RestringirALaAdministracion(string carpeta)
    {
        if (!OperatingSystem.IsWindows()) return;
        try
        {
            var info = new DirectoryInfo(carpeta);
            var seguridad = info.GetAccessControl();
            seguridad.SetAccessRuleProtection(isProtected: true, preserveInheritance: false);
            foreach (var identidad in new[] { System.Security.Principal.WellKnownSidType.LocalSystemSid, System.Security.Principal.WellKnownSidType.BuiltinAdministratorsSid })
            {
                seguridad.AddAccessRule(new System.Security.AccessControl.FileSystemAccessRule(
                    new System.Security.Principal.SecurityIdentifier(identidad, null), System.Security.AccessControl.FileSystemRights.FullControl,
                    System.Security.AccessControl.InheritanceFlags.ContainerInherit | System.Security.AccessControl.InheritanceFlags.ObjectInherit,
                    System.Security.AccessControl.PropagationFlags.None, System.Security.AccessControl.AccessControlType.Allow));
            }
            // Quien prepara el nodo (el administrador que instala, o el usuario de un ensayo sin privilegios) conserva el acceso: sin esto, un token sin elevar
            // —en el que «Administradores» solo niega— se quedaba fuera de la carpeta que acababa de crear.
            if (System.Security.Principal.WindowsIdentity.GetCurrent().User is { } actual)
            {
                seguridad.AddAccessRule(new System.Security.AccessControl.FileSystemAccessRule(
                    actual, System.Security.AccessControl.FileSystemRights.FullControl,
                    System.Security.AccessControl.InheritanceFlags.ContainerInherit | System.Security.AccessControl.InheritanceFlags.ObjectInherit,
                    System.Security.AccessControl.PropagationFlags.None, System.Security.AccessControl.AccessControlType.Allow));
            }
            info.SetAccessControl(seguridad);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException or System.Security.SecurityException)
        {
            // Sin privilegios no se restringe; el instalador (que si los tiene) lo vuelve a intentar en la siguiente preparacion.
        }
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

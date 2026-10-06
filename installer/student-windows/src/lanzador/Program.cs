using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32;

namespace Avacom.Student.Lanzador;

/// <summary>
/// Lo que ocurre cuando alguien toca el icono de AVACOM Student:
///
///     perfil de WebView2 escribible  ->  se abre la aplicacion
///
/// Student solo hace conexiones SALIENTES hacia la OPS: no instala servicio, no abre puertos y no
/// necesita firewall. Lo unico que el instalador no puede dejar resuelto con permisos es el perfil
/// de WebView2 de cada persona, y de eso se encarga este lanzador.
///
/// Nada de lo que hace pide escribir: el equipo puede ser una tableta con Windows.
/// </summary>
internal static class Program
{
    private const string NombreApp = "Avacom.Lms.Student";
    private const string Variable = "WEBVIEW2_USER_DATA_FOLDER";

    // {app}\Lanzador\Avacom.Student.Lanzador.exe  ->  {app}\App\Avacom.Lms.Student.exe
    private static readonly string CarpetaLanzador =
        Path.GetDirectoryName(Environment.ProcessPath) ?? AppContext.BaseDirectory;
    private static readonly string CarpetaInstalacion = Path.GetFullPath(Path.Combine(CarpetaLanzador, ".."));
    private static readonly string CarpetaApp = Path.Combine(CarpetaInstalacion, "App");
    private static readonly string AppExe = Path.Combine(CarpetaApp, NombreApp + ".exe");
    private static readonly string PerfilJuntoAlExe = AppExe + ".WebView2";

    private static readonly string CarpetaDeLaPersona =
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AVACOM", "Student");
    private static readonly string PerfilDeLaPersona = Path.Combine(CarpetaDeLaPersona, "WebView2");

    private static int Main(string[] args)
    {
        var verbo = args.Length > 0 ? args[0].Trim().ToLowerInvariant() : "iniciar";
        try
        {
            return verbo switch
            {
                "iniciar" => Iniciar(),
                "verificar" => Verificar(args.Length > 1 ? args[1] : null),
                _ => 64,
            };
        }
        catch (Exception error)
        {
            // Un fallo del lanzador no puede dejar sin abrir la aplicacion ni sin explicacion.
            Escribir($"El lanzador fallo en '{verbo}'", error);
            return 70;
        }
    }

    // ------------------------------------------------------------------ iniciar

    private static int Iniciar()
    {
        Escribir($"iniciar - lanzador {Version()} - usuario {Environment.UserName}");

        if (!File.Exists(AppExe))
        {
            Escribir($"No se encontro la aplicacion en {AppExe}.");
            Avisar("No se encontro la aplicacion en este equipo. Vuelve a instalar AVACOM Student.");
            return 8;
        }

        // Un segundo toque en el icono no debe abrir una segunda ventana: se trae la que ya hay.
        if (TraerAlFrenteLaAbierta())
        {
            Escribir("AVACOM Student ya estaba abierto: se trajo al frente.");
            return 0;
        }

        var inicio = new ProcessStartInfo { FileName = AppExe, WorkingDirectory = CarpetaApp, UseShellExecute = false };
        AsegurarPerfilDeWebView(inicio);

        Process? proceso;
        try
        {
            proceso = Process.Start(inicio);
        }
        catch (Exception error)
        {
            Escribir("No se pudo abrir la aplicacion", error);
            Avisar("No se pudo abrir AVACOM Student en este equipo.");
            return 9;
        }
        if (proceso is null)
        {
            Escribir("Windows no devolvio el proceso de la aplicacion.");
            Avisar("No se pudo abrir AVACOM Student en este equipo.");
            return 9;
        }

        Escribir($"AVACOM Student abierto (pid {proceso.Id}).");

        // Si la aplicacion se cierra enseguida y con error, no se deja a la persona sin explicacion:
        // el detalle esta en fallos-student.log; aqui solo se dice que pasa y que hacer.
        if (proceso.WaitForExit(6000) && proceso.ExitCode != 0)
        {
            Escribir($"La aplicacion se cerro a los pocos segundos con el codigo {proceso.ExitCode} (0x{proceso.ExitCode:x}).");
            Avisar(
                "AVACOM Student se cerro al abrirse.\n\n" +
                "Toca el icono otra vez. Si vuelve a cerrarse, avisa a quien administra el aula: " +
                "el detalle queda en el registro de este equipo.");
            return proceso.ExitCode;
        }
        return 0;
    }

    /// <summary>
    /// Decide donde guarda WebView2 su perfil (cache, cookies, almacenamiento). Nunca impide abrir
    /// la aplicacion: si ninguna carpeta propia se puede escribir, se deja la de por defecto, que el
    /// instalador deja escribible junto a la aplicacion como red de seguridad.
    ///
    /// Orden: 1) lo que ya diga el entorno (soporte, depuracion), 2) el perfil de Windows de quien
    /// usa el equipo, 3) la carpeta temporal de esa persona.
    /// </summary>
    private static void AsegurarPerfilDeWebView(ProcessStartInfo inicio)
    {
        if (Environment.GetEnvironmentVariable(Variable) is { Length: > 0 } indicada)
        {
            Escribir($"WebView2 usa el perfil que indica el entorno: {indicada}");
            return;
        }

        foreach (var carpeta in new[] { PerfilDeLaPersona, Path.Combine(Path.GetTempPath(), "AVACOM", "Student", "WebView2") })
        {
            if (!PuedeEscribir(carpeta)) continue;
            inicio.Environment[Variable] = carpeta;
            Escribir($"WebView2 guarda su perfil en {carpeta}");
            return;
        }

        Escribir(
            "ADVERTENCIA: ninguna carpeta de perfil de WebView2 se puede escribir; se deja la de por defecto " +
            $"({PerfilJuntoAlExe}). Si la aplicacion se cierra al abrir una leccion, es por esto.");
    }

    private static bool PuedeEscribir(string carpeta)
    {
        try
        {
            Directory.CreateDirectory(carpeta);
            var prueba = Path.Combine(carpeta, $".escritura-{Environment.ProcessId}");
            File.WriteAllText(prueba, "ok");
            File.Delete(prueba);
            return true;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            Escribir($"No se puede escribir en {carpeta}", error);
            return false;
        }
    }

    /// <summary>
    /// ¿Ya esta abierta la aplicacion INSTALADA? Se compara la ruta del ejecutable: una compilacion
    /// de desarrollo abierta en otro sitio no es esta aplicacion y no debe impedir que el icono
    /// abra la instalada. Si no se puede leer la ruta de un proceso (permisos), se toma por la
    /// instalada: lo peor que pasa es no abrir una segunda ventana.
    /// </summary>
    private static bool TraerAlFrenteLaAbierta()
    {
        try
        {
            var instalada = Path.GetFullPath(AppExe);
            foreach (var proceso in Process.GetProcessesByName(NombreApp))
            {
                try
                {
                    var ruta = proceso.MainModule?.FileName;
                    if (ruta is not null && !string.Equals(Path.GetFullPath(ruta), instalada, StringComparison.OrdinalIgnoreCase)) continue;

                    var ventana = proceso.MainWindowHandle;
                    if (ventana != IntPtr.Zero)
                    {
                        if (IsIconic(ventana)) ShowWindow(ventana, 9 /* SW_RESTORE */);
                        SetForegroundWindow(ventana);
                    }
                    return true;
                }
                catch (Exception error) when (error is System.ComponentModel.Win32Exception or InvalidOperationException)
                {
                    return true;
                }
                finally
                {
                    proceso.Dispose();
                }
            }
        }
        catch (Exception)
        {
            // Si no se puede saber, se intenta abrir: lo peor es una segunda ventana.
        }
        return false;
    }

    // ---------------------------------------------------------------- verificar

    /// <summary>
    /// Comprueba, sin abrir la aplicacion, que lo instalado puede abrirse. Lo ejecuta el asistente al
    /// terminar y el verificador. Escribe un renglon por comprobacion (si se pide, en un archivo).
    /// Codigos: 0 todo bien - 1 algo bloquea - 2 funciona con avisos.
    /// </summary>
    private static int Verificar(string? archivoDeSalida)
    {
        var lineas = new List<string> { $"lanzador {Version()}", $"instalacion {CarpetaInstalacion}" };
        var bloqueos = 0;
        var avisos = 0;

        void Revisar(bool bien, bool bloquea, string texto)
        {
            if (bien) lineas.Add("ok: " + texto);
            else if (bloquea) { bloqueos++; lineas.Add("falla: " + texto); }
            else { avisos++; lineas.Add("aviso: " + texto); }
        }

        Revisar(File.Exists(AppExe), true, "la aplicacion (Avacom.Lms.Student.exe) esta en su carpeta");
        Revisar(File.Exists(Path.Combine(CarpetaApp, "hostfxr.dll")), true, "el runtime de .NET viaja dentro de la aplicacion");
        Revisar(File.Exists(Path.Combine(CarpetaApp, "Microsoft.WindowsAppRuntime.dll")), true, "el Windows App SDK viaja dentro de la aplicacion");
        Revisar(File.Exists(Path.Combine(CarpetaInstalacion, "manifiesto.json")), false, "el manifiesto de la version esta junto a la aplicacion");
        Revisar(WebView2Instalado(), false, "el runtime de WebView2 (Edge) esta instalado: lo usan las lecciones con audio, video o PDF");
        Revisar(PuedeEscribir(PerfilDeLaPersona), false, $"esta cuenta puede escribir el perfil de WebView2 ({PerfilDeLaPersona})");

        if (File.Exists(AppExe))
        {
            var version = FileVersionInfo.GetVersionInfo(AppExe).FileVersion ?? "?";
            lineas.Add($"version de la aplicacion: {version}");
        }

        foreach (var linea in lineas) Escribir("verificar - " + linea);
        if (!string.IsNullOrWhiteSpace(archivoDeSalida))
        {
            try { File.WriteAllLines(archivoDeSalida, lineas, new UTF8Encoding(false)); }
            catch (Exception error) { Escribir($"No se pudo escribir {archivoDeSalida}", error); }
        }
        return bloqueos > 0 ? 1 : avisos > 0 ? 2 : 0;
    }

    private static bool WebView2Instalado()
    {
        const string clave = @"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}";
        foreach (var (raiz, vista) in new[]
                 { (RegistryHive.LocalMachine, RegistryView.Registry32), (RegistryHive.LocalMachine, RegistryView.Registry64), (RegistryHive.CurrentUser, RegistryView.Default) })
        {
            try
            {
                using var llave = RegistryKey.OpenBaseKey(raiz, vista).OpenSubKey(clave);
                var version = llave?.GetValue("pv") as string;
                if (!string.IsNullOrEmpty(version) && version != "0.0.0.0") return true;
            }
            catch (Exception)
            {
                // Una vista del registro que no se puede leer no cuenta como "instalado".
            }
        }
        return false;
    }

    // ----------------------------------------------------------------- registro

    private static string Version()
    {
        try { return FileVersionInfo.GetVersionInfo(Environment.ProcessPath ?? "").FileVersion ?? "?"; }
        catch (Exception) { return "?"; }
    }

    private static readonly object Cerrojo = new();

    private static void Escribir(string texto, Exception? error = null)
    {
        try
        {
            Directory.CreateDirectory(CarpetaDeLaPersona);
            var ruta = Path.Combine(CarpetaDeLaPersona, "lanzador.log");
            lock (Cerrojo)
            {
                // 512 KB y una copia: el registro de un icono no debe crecer sin limite.
                if (File.Exists(ruta) && new FileInfo(ruta).Length > 512 * 1024) File.Move(ruta, ruta + ".1", overwrite: true);
                File.AppendAllText(ruta,
                    $"[{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss zzz}] {texto}{Environment.NewLine}" +
                    (error is null ? "" : error + Environment.NewLine));
            }
        }
        catch (Exception)
        {
            // Si no se puede registrar, no hay nada mas que hacer: nunca se relanza.
        }
    }

    // El lanzador no tiene interfaz propia y no merece arrastrar WinForms o WPF solo para un aviso:
    // el MessageBox del sistema basta, y se cierra con un solo toque.
    [DllImport("user32.dll", EntryPoint = "MessageBoxW", CharSet = CharSet.Unicode)]
    private static extern int MessageBox(IntPtr ventana, string texto, string titulo, uint tipo);

    [DllImport("user32.dll")] private static extern bool SetForegroundWindow(IntPtr ventana);
    [DllImport("user32.dll")] private static extern bool ShowWindow(IntPtr ventana, int orden);
    [DllImport("user32.dll")] private static extern bool IsIconic(IntPtr ventana);

    private static void Avisar(string mensaje) =>
        // MB_OK | MB_ICONINFORMATION | MB_SETFOREGROUND | MB_TOPMOST
        MessageBox(IntPtr.Zero, mensaje, "AVACOM Student", 0x00000000 | 0x00000040 | 0x00010000 | 0x00040000);
}

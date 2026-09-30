using System.Diagnostics;
using System.ServiceProcess;

namespace Avacom.Ops.Host;

/// <summary>
/// Registro y control del servicio Windows.
///
/// Se usa sc.exe -herramienta del propio sistema, sin interaccion- en lugar de
/// P/Invoke a advapi32: menos codigo que mantener y el mismo resultado.
/// </summary>
internal static class Servicio
{
    public const string Nombre = "AVACOMOPSBackend";
    public const string NombreVisible = "AVACOM OPS Master Backend";

    private const string Descripcion =
        "API local de AVACOM OPS Master (Django REST Framework sobre Daphne). " +
        "Atiende a AVACOM OPS Master y a las tabletas del aula, HTTP y tiempo real (WebSocket), en el puerto 8000. " +
        "No administra cursos: los cursos son de AVACOM Contenido.";

    public static bool Existe()
    {
        try
        {
            return ServiceController.GetServices()
                .Any(s => string.Equals(s.ServiceName, Nombre, StringComparison.OrdinalIgnoreCase));
        }
        catch (Exception)
        {
            return false;
        }
    }

    public static int Instalar(Registro registro)
    {
        if (Existe())
        {
            registro.Escribir("El servicio ya existia: se actualiza su configuracion.");
            Sc(registro, ["stop", Nombre]);
            Sc(registro, ["delete", Nombre]);
            // sc delete es asincrono: si el SCM todavia lo tiene marcado para
            // borrado, el create siguiente falla con 1072.
            Thread.Sleep(2000);
        }

        // binPath lleva el verbo del servicio. Las comillas internas son las
        // que espera el SCM cuando la ruta tiene espacios (Program Files).
        var binPath = "\"" + Rutas.HostExe + "\" servicio";
        var codigo = Sc(registro,
        [
            "create", Nombre,
            "binPath=" + binPath,
            "start=auto",
            "DisplayName=" + NombreVisible,
        ]);
        if (codigo != 0)
        {
            registro.Escribir($"sc create devolvio {codigo}: el servicio no quedo registrado.");
            return codigo;
        }

        Sc(registro, ["description", Nombre, Descripcion]);

        // El nodo del aula presta servicio a las tabletas: si el backend muere,
        // Windows lo reinicia sin que nadie tenga que tocar la pantalla.
        Sc(registro, ["failure", Nombre, "reset=86400", "actions=restart/5000/restart/15000/restart/60000"]);

        // Que los usuarios interactivos puedan arrancarlo y consultarlo sin UAC:
        // el equipo del aula es tactil y no puede escribir credenciales.
        ConcederControlAUsuarios(registro);

        registro.Escribir($"Servicio {Nombre} registrado con inicio automatico.");
        return 0;
    }

    public static void Quitar(Registro registro)
    {
        if (!Existe())
        {
            registro.Escribir("El servicio no estaba registrado.");
            return;
        }
        Detener(registro);
        Sc(registro, ["delete", Nombre]);
        registro.Escribir($"Servicio {Nombre} eliminado.");
    }

    public static bool Iniciar(Registro registro, int segundosEspera = 60)
    {
        if (!Existe()) return false;
        try
        {
            using var control = new ServiceController(Nombre);
            if (control.Status is ServiceControllerStatus.Running) return true;

            if (control.Status is not (ServiceControllerStatus.StartPending or ServiceControllerStatus.ContinuePending))
            {
                control.Start();
            }
            control.WaitForStatus(ServiceControllerStatus.Running, TimeSpan.FromSeconds(segundosEspera));
            return control.Status is ServiceControllerStatus.Running;
        }
        catch (Exception error)
        {
            registro.Escribir("No se pudo iniciar el servicio", error);
            return false;
        }
    }

    public static void Detener(Registro registro, int segundosEspera = 40)
    {
        if (!Existe()) return;
        try
        {
            using var control = new ServiceController(Nombre);
            if (control.Status is ServiceControllerStatus.Stopped) return;
            control.Stop();
            control.WaitForStatus(ServiceControllerStatus.Stopped, TimeSpan.FromSeconds(segundosEspera));
        }
        catch (Exception error)
        {
            registro.Escribir("No se pudo detener el servicio", error);
        }
    }

    public static bool EstaCorriendo()
    {
        if (!Existe()) return false;
        try
        {
            using var control = new ServiceController(Nombre);
            return control.Status is ServiceControllerStatus.Running;
        }
        catch (Exception)
        {
            return false;
        }
    }

    /// <summary>
    /// Anade a los usuarios interactivos permiso de consultar, arrancar y parar
    /// SOLO este servicio. Si falla no se interrumpe la instalacion: el
    /// servicio arranca con Windows y el lanzador se limita a esperarlo.
    /// </summary>
    private static void ConcederControlAUsuarios(Registro registro)
    {
        // SY=SYSTEM, BA=Administradores, IU=usuarios interactivos, SU=servicios.
        // A IU se le dan RP (arrancar), WP (parar) y derechos de lectura.
        const string sddl =
            "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)" +
            "(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)" +
            "(A;;CCLCSWLOCRRPWP;;;IU)" +
            "(A;;CCLCSWLOCRRC;;;SU)" +
            "S:(AU;FA;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;WD)";

        var codigo = Sc(registro, ["sdset", Nombre, sddl]);
        registro.Escribir(codigo == 0
            ? "Los usuarios del equipo pueden arrancar y detener el servicio sin credenciales."
            : $"sc sdset devolvio {codigo}; el servicio queda solo bajo control administrativo.");
    }

    private static int Sc(Registro registro, IEnumerable<string> argumentos)
    {
        var inicio = new ProcessStartInfo
        {
            FileName = Path.Combine(Environment.SystemDirectory, "sc.exe"),
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (var argumento in argumentos) inicio.ArgumentList.Add(argumento);

        try
        {
            using var proceso = Process.Start(inicio);
            if (proceso is null) return -1;
            var salida = proceso.StandardOutput.ReadToEnd() + proceso.StandardError.ReadToEnd();
            proceso.WaitForExit(60_000);
            var resumen = salida.Replace("\r", " ").Replace("\n", " ").Trim();
            registro.Escribir($"sc {string.Join(" ", argumentos.Take(2))} -> {proceso.ExitCode} {resumen}");
            return proceso.ExitCode;
        }
        catch (Exception error)
        {
            registro.Escribir("No se pudo ejecutar sc.exe", error);
            return -1;
        }
    }
}

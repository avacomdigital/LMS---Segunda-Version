#if WINDOWS
using System.Diagnostics;
using System.Net;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using Microsoft.Win32;

namespace Avacom.Lms.Student.Examen;

/// <summary>Lo que el sistema operativo dice de la capa del sistema (Assigned Access o Shell Launcher) para ESTE usuario y ESTE ejecutable.</summary>
/// <param name="Aprovisionado">La configuración del sistema nombra a la cuenta de Windows actual y a este ejecutable.</param>
/// <param name="Via"><c>assigned-access</c>, <c>assigned-access (registro)</c>, <c>shell-launcher</c> o vacía si no está aprovisionado.</param>
/// <param name="Detalle">Una frase con lo que se encontró o por qué no se pudo concluir; sirve para el registro local, no para el alumno.</param>
internal sealed record EstadoDeSistema(bool Aprovisionado, string Via, string Detalle)
{
    public static EstadoDeSistema No(string detalle) => new(false, string.Empty, detalle);
}

/// <summary>
/// La consulta REAL de la capa del sistema en Windows (kiosk.md §5.1): el archivo marcador <c>kiosk-provisioned.marker</c> que escriben los scripts es
/// sólo un indicio —si alguien borra la política pero deja el archivo, la app lo daría por aprovisionado—, así que aquí se pregunta al sistema:
/// <list type="number">
/// <item><b>Assigned Access</b>, primero el almacén donde el sistema guarda su configuración, <c>HKLM\SOFTWARE\Microsoft\Windows\AssignedAccessConfiguration</c>: se lee en
/// milisegundos y sin privilegios; si está vacío no hay nada más que preguntar.</item>
/// <item>Con datos en el almacén, el puente MDM de WMI (<c>root\cimv2\mdm\dmmap</c>, clase <c>MDM_AssignedAccess</c>, propiedad <c>Configuration</c>), que da la configuración
/// exacta pero exige administrador. La cuenta del kiosco es un usuario estándar: si el sistema niega el acceso (tarda ~5 s en negarlo, por eso se recuerda), se decide con
/// el texto del almacén. Eso es una búsqueda de texto (la misma heurística de <c>Install-Kiosk.ps1 -Verify</c>), no un análisis de la configuración, y se declara así en
/// <see cref="EstadoDeSistema.Via"/>.</item>
/// <item><b>Shell Launcher</b> por WMI (<c>root\standardcimv2\embedded</c>, clase <c>WESL_UserSetting</c>): sólo cuenta si está habilitado, asigna ESTE ejecutable como shell
/// de la cuenta actual y el proceso es de verdad el shell (en esta sesión no corre <c>explorer.exe</c>).</item>
/// </list>
/// Sólo se considera aprovisionado si la configuración nombra a la cuenta de Windows ACTUAL (por nombre o por SID) y a ESTA ruta de ejecutable. Nunca lanza: cualquier
/// fallo (sin permisos, clase inexistente, edición Home, WMI caído) es «no aprovisionado» con el motivo en el detalle.
/// </summary>
internal static class AprovisionamientoWindows
{
    private const string EspacioMdm = @"root\cimv2\mdm\dmmap";
    private const string ClaseMdm = "MDM_AssignedAccess";
    private const string EspacioShell = @"root\standardcimv2\embedded";
    private const string ClaseShell = "WESL_UserSetting";
    private const string RaizRegistro = @"SOFTWARE\Microsoft\Windows\AssignedAccessConfiguration";

    /// <summary>Consulta al sistema ahora mismo (puede tardar cientos de milisegundos: no llamarla desde el hilo de interfaz sin un tope). Nunca lanza.</summary>
    public static EstadoDeSistema Consultar()
    {
        try
        {
            var exe = Environment.ProcessPath;
            if (string.IsNullOrWhiteSpace(exe)) return EstadoDeSistema.No("No se pudo saber la ruta de este ejecutable.");
            var yo = Identidad();
            if (yo is null) return EstadoDeSistema.No("No se pudo saber la cuenta de Windows actual.");

            var notas = new List<string>();
            var aa = ConsultarAssignedAccess(yo, exe, notas);
            if (aa is not null) return aa;
            var sl = ConsultarShellLauncher(yo, exe, notas);
            if (sl is not null) return sl;
            return EstadoDeSistema.No(string.Join(" ", notas));
        }
        catch (Exception ex)
        {
            return EstadoDeSistema.No($"La consulta al sistema falló: {ex.GetType().Name}.");
        }
    }

    // ------------------------------------------------------------------------------------------------ quién soy

    internal sealed record Cuenta(string NombreCompleto, string Usuario, string Sid);

    private static Cuenta? Identidad()
    {
        using var identidad = WindowsIdentity.GetCurrent();
        var completo = identidad.Name ?? string.Empty;
        var sid = identidad.User?.Value ?? string.Empty;
        if (completo.Length == 0 && sid.Length == 0) return null;
        var barra = completo.LastIndexOf('\\');
        return new Cuenta(completo, barra >= 0 ? completo[(barra + 1)..] : completo, sid);
    }

    internal static bool EsMiCuenta(string cuenta, Cuenta yo)
    {
        var c = cuenta.Trim();
        if (c.Length == 0) return false;
        return c.Equals(yo.NombreCompleto, StringComparison.OrdinalIgnoreCase)
            || c.Equals(yo.Usuario, StringComparison.OrdinalIgnoreCase)
            || (yo.Usuario.Length > 0 && c.EndsWith('\\' + yo.Usuario, StringComparison.OrdinalIgnoreCase))
            || (yo.Sid.Length > 0 && c.Equals(yo.Sid, StringComparison.OrdinalIgnoreCase));
    }

    internal static bool EsMiEjecutable(string ruta, string exe)
    {
        var r = ruta.Trim().Trim('"');
        if (r.Length == 0) return false;
        try { r = Path.GetFullPath(Environment.ExpandEnvironmentVariables(r)); } catch (Exception) { /* se compara tal cual */ }
        return r.Equals(exe, StringComparison.OrdinalIgnoreCase);
    }

    // ------------------------------------------------------------------------------------------------ Assigned Access

    private static EstadoDeSistema? ConsultarAssignedAccess(Cuenta yo, string exe, List<string> notas)
    {
        // 1. El almacén del sistema en el registro: instantáneo y legible sin privilegios. Si el sistema no guarda NINGUNA configuración, no hay nada más que preguntar
        //    (y se evita la consulta MDM, que sin administrador tarda unos 5 s en negarse).
        var almacen = LeerAlmacenDeRegistro(out var errorRegistro);
        if (almacen is { Length: 0 })
        {
            notas.Add("Assigned Access: el almacén del sistema está vacío (no hay ninguna configuración).");
            return null;
        }

        // 2. El puente MDM de WMI: la lectura precisa de la configuración (necesita administrador).
        var configuracion = LeerConfiguracionMdm(out var errorMdm);
        if (configuracion is not null)
        {
            if (string.IsNullOrWhiteSpace(configuracion))
            {
                notas.Add("Assigned Access: el sistema no tiene ninguna configuración (MDM_AssignedAccess vacía).");
                return null;
            }
            if (ConfiguracionNombra(configuracion, yo, exe, out var motivo))
                return new EstadoDeSistema(true, "assigned-access", "Assigned Access (MDM_AssignedAccess) nombra a esta cuenta y a este ejecutable.");
            notas.Add($"Assigned Access: hay una configuración, pero {motivo}.");
            return null;
        }

        // 3. No se pudo leer el puente MDM (lo normal en la cuenta estándar del kiosco): se decide con el texto del almacén.
        if (almacen is null)
        {
            notas.Add($"Assigned Access: no se pudo consultar ({errorMdm}; registro: {errorRegistro}).");
            return null;
        }
        if (TextoNombra(almacen, yo, exe, out var motivoRegistro))
            return new EstadoDeSistema(true, "assigned-access (registro)", "El almacén de Assigned Access del sistema nombra a esta cuenta y a este ejecutable (búsqueda de texto; el puente MDM no se pudo leer sin administrador).");
        notas.Add($"Assigned Access: el almacén del sistema tiene datos, pero {motivoRegistro}.");
        return null;
    }

    /// <summary>
    /// Interpreta la configuración de Assigned Access (acepta la forma escapada que guarda MDM): una <c>Config</c> cuya <c>Account</c> sea esta cuenta y cuyo perfil
    /// (<c>DefaultProfile Id</c>) permita este ejecutable por <c>DesktopAppPath</c>.
    /// </summary>
    internal static bool ConfiguracionNombra(string configuracion, Cuenta yo, string exe, out string motivo)
    {
        var texto = configuracion.TrimStart();
        if (!texto.StartsWith('<') && texto.Contains("&lt;", StringComparison.Ordinal)) texto = WebUtility.HtmlDecode(texto);
        XDocument documento;
        try { documento = XDocument.Parse(texto); }
        catch (Exception)
        {
            // Si no es XML legible se cae a la misma búsqueda de texto que usa el script de verificación.
            return TextoNombra(texto, yo, exe, out motivo);
        }

        var usuarioHallado = false;
        foreach (var config in documento.Descendants().Where(e => e.Name.LocalName == "Config"))
        {
            var cuentas = config.Elements().Where(e => e.Name.LocalName == "Account").Select(e => e.Value);
            if (!cuentas.Any(c => EsMiCuenta(c, yo))) continue;
            usuarioHallado = true;
            var perfilId = config.Elements().FirstOrDefault(e => e.Name.LocalName == "DefaultProfile")?.Attribute("Id")?.Value;
            var perfiles = documento.Descendants().Where(e => e.Name.LocalName == "Profile" && (perfilId is null || string.Equals((string?)e.Attribute("Id"), perfilId, StringComparison.OrdinalIgnoreCase)));
            foreach (var perfil in perfiles)
            {
                var rutas = perfil.Descendants().Where(e => e.Name.LocalName == "App").Select(e => (string?)e.Attribute("DesktopAppPath")).Where(r => !string.IsNullOrEmpty(r));
                if (rutas.Any(r => EsMiEjecutable(r!, exe))) { motivo = string.Empty; return true; }
            }
        }
        motivo = usuarioHallado ? "el perfil de esta cuenta no permite este ejecutable" : "no nombra a la cuenta de Windows actual";
        return false;
    }

    /// <summary>Búsqueda de texto: la cuenta (por SID o por nombre completo, sin confundir «Ana» con «Analytics») Y la ruta del ejecutable. Sólo es heurística.</summary>
    internal static bool TextoNombra(string texto, Cuenta yo, string exe, out string motivo)
    {
        var cuentaHallada = (yo.Sid.Length > 0 && texto.Contains(yo.Sid, StringComparison.OrdinalIgnoreCase))
                         || (yo.Usuario.Length > 0 && Regex.IsMatch(texto, $@"(?<![\p{{L}}\p{{N}}_]){Regex.Escape(yo.Usuario)}(?![\p{{L}}\p{{N}}_])", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant));
        var exeHallado = texto.Contains(exe, StringComparison.OrdinalIgnoreCase);
        if (cuentaHallada && exeHallado) { motivo = string.Empty; return true; }
        motivo = (cuentaHallada, exeHallado) switch
        {
            (false, false) => "no nombra a la cuenta de Windows actual ni a este ejecutable",
            (false, true) => "no nombra a la cuenta de Windows actual",
            _ => "no nombra a este ejecutable",
        };
        return false;
    }

    /// <summary><c>MDM_AssignedAccess.Configuration</c>, o <c>null</c> si no se pudo leer (el motivo en <paramref name="error"/>). Cadena vacía: se leyó y no hay configuración.</summary>
    private static string? LeerConfiguracionMdm(out string error)
    {
        // Los privilegios de un proceso no cambian mientras vive: si el sistema ya negó el acceso no se repite una consulta que tarda ~5 s en negarse.
        if (Volatile.Read(ref mdmNegado) == 1)
        {
            error = "MDM_AssignedAccess no se puede leer sin administrador";
            return null;
        }
        try
        {
            var filas = ConsultaWmi.Leer(EspacioMdm, ClaseMdm, "Configuration");
            error = string.Empty;
            foreach (var fila in filas)
                if (fila.TryGetValue("Configuration", out var valor) && valor is string s && s.Length > 0) return s;
            return string.Empty;
        }
        catch (Exception ex)
        {
            if (ConsultaWmi.EsAccesoDenegado(ex)) Volatile.Write(ref mdmNegado, 1);
            error = $"MDM_AssignedAccess no se pudo leer: {ConsultaWmi.Describir(ex)}";
            return null;
        }
    }

    private static int mdmNegado;   // 1 cuando el sistema negó el acceso al puente MDM a este proceso

    /// <summary>
    /// Vuelca como texto las claves y valores del almacén de Assigned Access (nombres de clave incluidos: la cuenta puede ser un nombre de clave). <c>null</c> si no se
    /// pudo abrir la raíz; cadena vacía si sólo existe el esqueleto vacío que el sistema crea siempre (nivel 1 sin valores ni claves de nivel 2).
    /// </summary>
    private static string? LeerAlmacenDeRegistro(out string error)
    {
        try
        {
            using var maquina = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64);
            using var raiz = maquina.OpenSubKey(RaizRegistro, writable: false);
            if (raiz is null) { error = string.Empty; return string.Empty; }
            var texto = new StringBuilder();
            var entradas = 0;
            Volcar(raiz, 0, texto, ref entradas);
            error = string.Empty;
            return entradas == 0 ? string.Empty : texto.ToString();
        }
        catch (Exception ex)
        {
            error = ex.GetType().Name;
            return null;
        }
    }

    private static void Volcar(RegistryKey clave, int profundidad, StringBuilder texto, ref int entradas)
    {
        if (profundidad > 8 || texto.Length > 2_000_000) return;
        foreach (var nombre in clave.GetValueNames())
        {
            entradas++;
            texto.Append(' ').Append(nombre).Append('\n');
            switch (clave.GetValue(nombre))
            {
                case string s: texto.Append(s).Append('\n'); break;
                case string[] varias: texto.Append(string.Join('|', varias)).Append('\n'); break;
                case byte[] bytes:
                    texto.Append(Encoding.Unicode.GetString(bytes)).Append('\n').Append(Encoding.UTF8.GetString(bytes)).Append('\n');
                    break;
                case var otro when otro is not null: texto.Append(otro).Append('\n'); break;
            }
        }
        foreach (var hija in clave.GetSubKeyNames())
        {
            // El sistema mantiene siempre un esqueleto (Configs, GroupConfigs, Profiles, RawData) en el nivel 1: sólo cuenta como configuración lo que cuelga de él.
            if (profundidad >= 1) entradas++;
            texto.Append(hija).Append('\n');
            try
            {
                using var sub = clave.OpenSubKey(hija, writable: false);
                if (sub is not null) Volcar(sub, profundidad + 1, texto, ref entradas);
            }
            catch (Exception) { /* una subclave sin permiso no invalida el resto */ }
        }
    }

    // ------------------------------------------------------------------------------------------------ Shell Launcher

    private static EstadoDeSistema? ConsultarShellLauncher(Cuenta yo, string exe, List<string> notas)
    {
        List<Dictionary<string, object?>> filas;
        try { filas = ConsultaWmi.Leer(EspacioShell, ClaseShell, "Sid", "Shell"); }
        catch (Exception ex)
        {
            notas.Add($"Shell Launcher: no se pudo consultar ({ConsultaWmi.Describir(ex)}).");
            return null;
        }

        var asignado = filas.Any(f => f.TryGetValue("Sid", out var sid) && sid is string s && yo.Sid.Length > 0 && s.Equals(yo.Sid, StringComparison.OrdinalIgnoreCase)
                                        && f.TryGetValue("Shell", out var shell) && shell is string cmd && EsMiShell(cmd, exe));
        if (!asignado)
        {
            notas.Add("Shell Launcher: ninguna asignación pone este ejecutable como shell de esta cuenta.");
            return null;
        }

        bool habilitado;
        try { habilitado = ConsultaWmi.ShellLauncherHabilitado(EspacioShell, ClaseShell); }
        catch (Exception ex)
        {
            notas.Add($"Shell Launcher: no se pudo saber si está habilitado ({ConsultaWmi.Describir(ex)}).");
            return null;
        }
        if (!habilitado)
        {
            notas.Add("Shell Launcher: está configurado pero desactivado.");
            return null;
        }

        // Con Shell Launcher activo para esta cuenta, explorer.exe no corre en su sesión: esta app es el shell. Si corre, la configuración existe pero esta sesión
        // empezó antes (falta cerrar sesión o reiniciar) y el alumno todavía tiene el escritorio.
        if (HayExplorerEnEstaSesion())
        {
            notas.Add("Shell Launcher: está configurado, pero en esta sesión sigue corriendo el escritorio (explorer.exe); cierra sesión o reinicia.");
            return null;
        }
        return new EstadoDeSistema(true, "shell-launcher", "Shell Launcher está activo y esta app es el shell de esta cuenta.");
    }

    internal static bool EsMiShell(string ordenDeShell, string exe)
    {
        var orden = ordenDeShell.Trim();
        if (orden.Length == 0) return false;
        // El shell puede llevar argumentos: «"C:\ruta\app.exe" /x» o «C:\ruta\app.exe /x» (la ruta puede tener espacios, por eso se compara por prefijo).
        if (orden[0] == '"')
        {
            var cierre = orden.IndexOf('"', 1);
            return EsMiEjecutable(cierre > 0 ? orden[1..cierre] : orden[1..], exe);
        }
        if (EsMiEjecutable(orden, exe)) return true;
        return orden.Length > exe.Length && orden.StartsWith(exe, StringComparison.OrdinalIgnoreCase) && orden[exe.Length] == ' ';
    }

    private static bool HayExplorerEnEstaSesion()
    {
        using var yo = Process.GetCurrentProcess();
        var sesion = yo.SessionId;
        foreach (var proceso in Process.GetProcessesByName("explorer"))
        {
            try { if (proceso.SessionId == sesion) return true; }
            catch (Exception) { /* un proceso que ya terminó */ }
            finally { proceso.Dispose(); }
        }
        return false;
    }
}

/// <summary>
/// WMI sin paquetes: el localizador COM <c>WbemScripting.SWbemLocator</c> con enlace tardío. Evita agregar <c>System.Management</c> al proyecto sólo para dos consultas de
/// lectura. Cada llamada abre su conexión, lee y la suelta; los errores (acceso denegado, clase inexistente, WMI detenido) suben como excepción para que quien llama
/// decida —<see cref="AprovisionamientoWindows"/> los convierte en «no aprovisionado».
/// </summary>
internal static class ConsultaWmi
{
    /// <summary>Lee las propiedades pedidas de TODAS las instancias de una clase. Lanza si no se puede.</summary>
    public static List<Dictionary<string, object?>> Leer(string espacio, string clase, params string[] propiedades)
    {
        var tipo = Type.GetTypeFromProgID("WbemScripting.SWbemLocator") ?? throw new InvalidOperationException("WMI no está disponible (SWbemLocator).");
        dynamic? localizador = null, servicio = null, conjunto = null;
        try
        {
            localizador = Activator.CreateInstance(tipo)!;
            servicio = localizador.ConnectServer(".", espacio);
            // Banderas 0: bidireccional y síncrona, para poder contar y recorrer por índice (con las predeterminadas el recorrido es sólo hacia adelante).
            conjunto = servicio.ExecQuery("SELECT * FROM " + clase, "WQL", 0);
            var cantidad = (int)conjunto.Count;
            var filas = new List<Dictionary<string, object?>>(cantidad);
            for (var i = 0; i < cantidad; i++)
            {
                object instancia = conjunto.ItemIndex(i);
                try
                {
                    var fila = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);
                    foreach (var propiedad in propiedades)
                    {
                        try { fila[propiedad] = instancia.GetType().InvokeMember(propiedad, System.Reflection.BindingFlags.GetProperty, null, instancia, null); }
                        catch (Exception) { fila[propiedad] = null; }
                    }
                    filas.Add(fila);
                }
                finally { Liberar(instancia); }
            }
            return filas;
        }
        finally
        {
            Liberar((object?)conjunto);
            Liberar((object?)servicio);
            Liberar((object?)localizador);
        }
    }

    /// <summary><c>WESL_UserSetting.IsEnabled()</c>: método estático de la clase. Lanza si no se puede leer.</summary>
    public static bool ShellLauncherHabilitado(string espacio, string clase)
    {
        var tipo = Type.GetTypeFromProgID("WbemScripting.SWbemLocator") ?? throw new InvalidOperationException("WMI no está disponible (SWbemLocator).");
        dynamic? localizador = null, servicio = null, definicion = null, salida = null;
        try
        {
            localizador = Activator.CreateInstance(tipo)!;
            servicio = localizador.ConnectServer(".", espacio);
            definicion = servicio.Get(clase);
            salida = definicion.ExecMethod_("IsEnabled");
            return (bool)salida.Enabled;
        }
        finally
        {
            Liberar((object?)salida);
            Liberar((object?)definicion);
            Liberar((object?)servicio);
            Liberar((object?)localizador);
        }
    }

    public static bool EsAccesoDenegado(Exception ex) => (uint)ex.HResult is 0x80041003 or 0x80070005;

    public static string Describir(Exception ex)
    {
        // El 0x80041003 de WMI es «acceso denegado»; el 0x8004100E, «espacio de nombres no válido»; el 0x80041010, «clase no válida».
        var hr = ex is System.Runtime.InteropServices.COMException com ? com.HResult : ex.HResult;
        return (uint)hr switch
        {
            0x80041003 => "acceso denegado (se necesita administrador)",
            0x8004100E => "el espacio de nombres no existe en esta edición de Windows",
            0x80041010 => "la clase no existe: la característica no está activa",
            0x80070005 => "acceso denegado",
            _ => $"{ex.GetType().Name} 0x{(uint)hr:X8}",
        };
    }

    private static void Liberar(object? com)
    {
        try { if (com is not null && System.Runtime.InteropServices.Marshal.IsComObject(com)) System.Runtime.InteropServices.Marshal.FinalReleaseComObject(com); }
        catch (Exception) { /* soltar un objeto COM nunca debe fallar la consulta */ }
    }
}
#endif

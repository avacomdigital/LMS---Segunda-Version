using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Avacom.Ops.Host;

/// <summary>
/// Lo que ocurre cuando alguien toca el icono de AVACOM OPS Master:
///
///     backend en marcha  ->  validado  ->  se abre la interfaz
///
/// El equipo del aula es tactil y no tiene teclado: aqui no se pide nada que
/// haya que escribir, y cualquier aviso se cierra con un solo toque.
/// </summary>
internal static class Lanzador
{
    public static int Ejecutar()
    {
        var registro = new Registro("lanzador.log");
        var puerto = Configuracion.PuertoConfigurado();

        // Un segundo toque en el icono no debe abrir una segunda ventana.
        if (YaEstaAbierta())
        {
            registro.Escribir("AVACOM OPS Master ya estaba abierto.");
            return 0;
        }

        // 1. Backend. Normalmente ya esta: el servicio arranca con Windows.
        if (!Servicio.EstaCorriendo())
        {
            registro.Escribir("El servicio del backend no estaba en marcha: se intenta iniciar.");
            Servicio.Iniciar(registro, segundosEspera: 45);
        }

        // 1b. Dispositivo AVACOM (MOD-018 segunda proteccion). El SERVICIO (SYSTEM) comprueba la identidad UEFI y el sello y no levanta el backend si no pasan; aqui solo se le dice a la persona por que
        // no abre nada. Esto es presentacion: la barrera es la del servicio y la liberacion de la clave del paquete.
        if (!DispositivoAutorizado(registro, out var codigoDeDiagnostico))
        {
            registro.Escribir($"Dispositivo no autorizado ({codigoDeDiagnostico}): no se abre la interfaz.");
            AvisarRechazo(codigoDeDiagnostico);
            return Dispositivo.PuertaDeDispositivo.SalidaIdentidadUefi;
        }

        // 2. Validacion. Se le da tiempo al arranque en frio de Django.
        var salud = Salud.EsperarAsync(puerto, 45).GetAwaiter().GetResult();
        registro.Escribir(salud.Correcto
            ? $"Backend validado: {salud.Detalle}."
            : $"Backend sin validar: {salud.Detalle}.");

        if (!salud.Correcto)
        {
            // No se bloquea la clase: la aplicacion tiene modo local y el
            // profesor decide. Un solo toque en Aceptar y sigue.
            Avisar(
                "AVACOM OPS Master",
                "El servicio local de AVACOM OPS Master no responde todavia.\n\n" +
                "La aplicacion se abrira con la informacion que tenga disponible. " +
                "Si el problema sigue, reinicia el equipo.");
        }

        // 3. Interfaz.
        if (!File.Exists(Rutas.AppExe))
        {
            registro.Escribir($"No se encontro la aplicacion en {Rutas.AppExe}.");
            Avisar("AVACOM OPS Master", "No se encontro la aplicacion en este equipo. Vuelve a instalarla.");
            return 8;
        }

        try
        {
            var inicio = new ProcessStartInfo
            {
                FileName = Rutas.AppExe,
                WorkingDirectory = Rutas.CarpetaApp,
                UseShellExecute = false,
            };

            // La leccion usa WebView (audio, video, PDF, laboratorio). WebView2
            // guarda su perfil por defecto JUNTO AL EJECUTABLE, y la aplicacion
            // vive en Program Files, donde quien da la clase no puede escribir:
            // al crear la primera WebView falla y el proceso se cierra sin avisar.
            // Se le da una carpeta propia y escribible. Es una variable de
            // entorno que WebView2 ya lee: no cambia el producto.
            AsegurarPerfilDeWebView(inicio, registro);

            var proceso = Process.Start(inicio);
            registro.Escribir($"Interfaz de AVACOM OPS Master abierta (pid {proceso?.Id}).");
            return 0;
        }
        catch (Exception error)
        {
            registro.Escribir("No se pudo abrir la interfaz", error);
            Avisar("AVACOM OPS Master", "No se pudo abrir la aplicacion en este equipo.");
            return 9;
        }
    }

    /// <summary>
    /// ¿Este equipo es un dispositivo AVACOM autorizado? Lo dice la señal que el servicio deja en Logs (el lanzador corre sin privilegios y no puede leer el firmware). Se espera hasta 25 s a que el
    /// servicio la escriba (acaba de arrancar con Windows); sin señal despues de eso, se deniega: sin comprobacion no hay autorizacion. Una compilacion sin llaves de sello no tiene puerta.
    /// </summary>
    internal static bool DispositivoAutorizado(Registro registro, out string codigo, int esperaSegundos = 25)
    {
        codigo = "";
        if (!OperatingSystem.IsWindows() || Dispositivo.PuertaDeDispositivo.LlavesIncrustadas().Count == 0) return true;
        return LeerSenalDelLanzador(registro, Dispositivo.PuertaDeDispositivo.RutaDeSenalDelLanzadorDelNodo, esperaSegundos, out codigo);
    }

    internal static bool LeerSenalDelLanzador(Registro registro, string ruta, int esperaSegundos, out string codigo)
    {
        codigo = "";
        var limite = DateTime.UtcNow.AddSeconds(esperaSegundos);
        while (true)
        {
            try
            {
                if (File.Exists(ruta))
                {
                    using var documento = System.Text.Json.JsonDocument.Parse(File.ReadAllText(ruta));
                    codigo = documento.RootElement.TryGetProperty("codigo", out var c) && c.GetString() is { Length: > 0 } texto ? texto : Dispositivo.IdentidadUefi.Codigo(Dispositivo.EstadoDeIdentidad.ErrorDeLectura);
                    return documento.RootElement.TryGetProperty("autorizado", out var a) && a.ValueKind == System.Text.Json.JsonValueKind.True;
                }
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException or System.Text.Json.JsonException or InvalidOperationException)
            {
                registro.Escribir("No se pudo leer la señal del dispositivo", error);
            }
            if (DateTime.UtcNow >= limite) break;
            Thread.Sleep(500);
        }
        codigo = Dispositivo.IdentidadUefi.Codigo(Dispositivo.EstadoDeIdentidad.ErrorDeLectura);
        return false;
    }

    /// <summary>Dialogo modal con el mensaje obligatorio y un solo boton para cerrar. Nada de trazas ni excepciones: solo el codigo corto de diagnostico.</summary>
    private static void AvisarRechazo(string codigo) =>
        MessageBox(IntPtr.Zero, Dispositivo.IdentidadUefi.MensajeDeRechazo + Environment.NewLine + Environment.NewLine + "Código de diagnóstico: " + codigo,
                   "AVACOM OPS Master", MbOk | MbIconError | MbSetForeground | MbTopMost);

    /// <summary>
    /// Decide donde guarda WebView2 su perfil (cache, cookies, almacenamiento). Nunca
    /// impide abrir la aplicacion: si ninguna carpeta propia se puede escribir, se deja
    /// a WebView2 con su carpeta por defecto, que el instalador deja escribible junto a la
    /// aplicacion como red de seguridad.
    ///
    /// Orden: 1) lo que ya diga el entorno (soporte, depuracion), 2) el perfil de Windows de
    /// quien da la clase, 3) la carpeta temporal de esa persona.
    /// </summary>
    private static void AsegurarPerfilDeWebView(ProcessStartInfo inicio, Registro registro)
    {
        const string variable = "WEBVIEW2_USER_DATA_FOLDER";

        if (Environment.GetEnvironmentVariable(variable) is { Length: > 0 } indicada)
        {
            registro.Escribir($"WebView2 usa el perfil que indica el entorno: {indicada}");
            return;
        }

        var candidatas = new[]
        {
            Rutas.PerfilWebViewDelUsuario,
            Path.Combine(Path.GetTempPath(), "AVACOM", "OPS Master", "WebView2"),
        };
        foreach (var carpeta in candidatas)
        {
            if (!PuedeEscribir(carpeta, registro)) continue;
            inicio.Environment[variable] = carpeta;
            registro.Escribir($"WebView2 guarda su perfil en {carpeta}");
            return;
        }

        registro.Escribir(
            "ADVERTENCIA: ninguna carpeta de perfil de WebView2 se puede escribir; se deja la de por defecto " +
            $"({Rutas.PerfilWebViewJuntoAlExe}). Si la aplicacion se cierra al abrir una leccion, es por esto.");
    }

    private static bool PuedeEscribir(string carpeta, Registro registro)
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
            registro.Escribir($"No se puede escribir en {carpeta}", error);
            return false;
        }
    }

    /// <summary>
    /// ¿Ya esta abierta la aplicacion INSTALADA? Un segundo toque en el icono no debe abrir una
    /// segunda ventana. Se compara la ruta del ejecutable: una compilacion de desarrollo abierta en
    /// otro sitio no es esta aplicacion y no debe impedir que el icono abra la instalada.
    /// Si no se puede leer la ruta de un proceso (permisos), se toma por la instalada: lo
    /// peor que pasa es no abrir una segunda ventana.
    /// </summary>
    private static bool YaEstaAbierta()
    {
        try
        {
            var instalada = Path.GetFullPath(Rutas.AppExe);
            foreach (var proceso in Process.GetProcessesByName("Avacom.Lms.Ops"))
            {
                try
                {
                    var ruta = proceso.MainModule?.FileName;
                    if (ruta is null || string.Equals(Path.GetFullPath(ruta), instalada, StringComparison.OrdinalIgnoreCase))
                    {
                        return true;
                    }
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
            return false;
        }
        catch (Exception)
        {
            return false;
        }
    }

    // El host no tiene interfaz propia y no merece arrastrar WinForms o WPF
    // solo para mostrar un aviso: MessageBox del sistema es suficiente.
    [DllImport("user32.dll", EntryPoint = "MessageBoxW", CharSet = CharSet.Unicode)]
    private static extern int MessageBox(IntPtr ventana, string texto, string titulo, uint tipo);

    private const uint MbOk = 0x00000000;
    private const uint MbIconInformation = 0x00000040;
    private const uint MbIconError = 0x00000010;
    private const uint MbSetForeground = 0x00010000;
    private const uint MbTopMost = 0x00040000;

    internal static void Avisar(string titulo, string mensaje) =>
        MessageBox(IntPtr.Zero, mensaje, titulo, MbOk | MbIconInformation | MbSetForeground | MbTopMost);
}

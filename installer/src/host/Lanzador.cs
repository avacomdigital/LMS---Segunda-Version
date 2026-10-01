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
            var perfilWeb = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "AVACOM", "OPS Master", "WebView2");
            Directory.CreateDirectory(perfilWeb);
            inicio.Environment["WEBVIEW2_USER_DATA_FOLDER"] = perfilWeb;

            Process.Start(inicio);
            registro.Escribir("Interfaz de AVACOM OPS Master abierta.");
            return 0;
        }
        catch (Exception error)
        {
            registro.Escribir("No se pudo abrir la interfaz", error);
            Avisar("AVACOM OPS Master", "No se pudo abrir la aplicacion en este equipo.");
            return 9;
        }
    }

    private static bool YaEstaAbierta()
    {
        try
        {
            return Process.GetProcessesByName("Avacom.Lms.Ops").Length > 0;
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
    private const uint MbSetForeground = 0x00010000;
    private const uint MbTopMost = 0x00040000;

    internal static void Avisar(string titulo, string mensaje) =>
        MessageBox(IntPtr.Zero, mensaje, titulo, MbOk | MbIconInformation | MbSetForeground | MbTopMost);
}

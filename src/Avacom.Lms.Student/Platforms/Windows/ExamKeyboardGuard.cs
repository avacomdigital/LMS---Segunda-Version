#if WINDOWS
using System.Runtime.InteropServices;
using Avacom.Lms.Core.Evaluacion;

namespace Avacom.Lms.Student.Examen;

/// <summary>
/// El gancho de teclado de bajo nivel (<c>WH_KEYBOARD_LL</c>) que traga Windows, Alt+Tab, Esc, Alt+F4 y F11 mientras dura el examen (kiosk.md §4.3), la misma técnica de
/// los navegadores de examen comerciales. No necesita administrador. Qué teclas se descartan lo decide <see cref="FiltroDeTeclas"/> (lógica pura y probada); esta clase
/// sólo traduce lo que ve el sistema.
///
/// Cuatro detalles que costó descubrir y que se pierden al reescribirlo:
/// <list type="bullet">
/// <item><b>Descarta también KEYUP</b>, no sólo KEYDOWN: el menú Inicio se abre al SOLTAR la tecla Windows.</item>
/// <item><b>El delegado vive en un campo estático.</b> Si sólo fuera un argumento, el recolector lo liberaría y Windows llamaría a memoria inválida.</item>
/// <item><b>Se instala desde el hilo de interfaz</b>, que tiene bucle de mensajes: un gancho global sin él no recibe nada.</item>
/// <item><b>Devolver 1 consume la tecla;</b> en cualquier otro caso se termina en <c>CallNextHookEx</c>.</item>
/// </list>
///
/// Es peligroso en un equipo de desarrollo (es GLOBAL: afecta a todas las aplicaciones), así que se retira siempre: al soltar el bloqueo, al desechar el servicio, al salir
/// del proceso, ante una excepción no controlada y cuando se cierra la ventana. La función de retorno no hace nada lento ni lanza: un gancho que tarda más de ~300 ms hace
/// que Windows lo retire en silencio y que todo el teclado del equipo se sienta pegajoso.
/// </summary>
internal static class ExamKeyboardGuard
{
    private const int WhKeyboardLl = 13;
    private const int HcAction = 0;
    private const int WmKeyDown = 0x0100;
    private const int WmKeyUp = 0x0101;
    private const int WmSysKeyDown = 0x0104;
    private const int WmSysKeyUp = 0x0105;
    private const int LlkhfAltDown = 0x20;

    private delegate IntPtr LowLevelKeyboardProc(int nCode, IntPtr wParam, IntPtr lParam);

    private static readonly object Candado = new();
    private static LowLevelKeyboardProc? delegado;      // campo estático: lo mantiene vivo mientras el gancho esté instalado
    private static IntPtr gancho = IntPtr.Zero;
    private static Action<string>? alDescartar;
    private static readonly bool[] Abajo = new bool[256];   // teclas cuya pulsación se tragó y cuya suelta también debe tragarse
    private static bool procesoEnganchado;

    /// <summary>¿Hay un gancho instalado ahora mismo? La app lo consulta para informar si falló (kiosk.md §4.3).</summary>
    public static bool IsActive
    {
        get { lock (Candado) return gancho != IntPtr.Zero; }
    }

    /// <summary>
    /// Instala el gancho. Llamar desde el hilo de interfaz. <paramref name="alDescartar"/> recibe el nombre de cada combinación descartada (una sola vez por pulsación,
    /// no por repetición del teclado) y debe ser instantáneo. Idempotente. Devuelve falso, con el código de Windows en <paramref name="error"/>, si no pudo instalarse.
    /// </summary>
    public static bool Install(Action<string>? alDescartar, out int error)
    {
        lock (Candado)
        {
            ExamKeyboardGuard.alDescartar = alDescartar;
            error = 0;
            if (gancho != IntPtr.Zero) return true;
            Array.Clear(Abajo);
            delegado = Callback;
            var instalado = SetWindowsHookEx(WhKeyboardLl, delegado, GetModuleHandle(null), 0);
            if (instalado == IntPtr.Zero)
            {
                error = Marshal.GetLastWin32Error();
                delegado = null;
                ExamKeyboardGuard.alDescartar = null;
                return false;
            }
            gancho = instalado;
            if (!procesoEnganchado)
            {
                procesoEnganchado = true;
                // Al salir del proceso y ante una excepción no controlada el gancho se retira solo; Windows lo haría al morir el proceso, pero no se le deja a la suerte.
                AppDomain.CurrentDomain.ProcessExit += (_, _) => Uninstall();
                AppDomain.CurrentDomain.UnhandledException += (_, _) => Uninstall();
            }
            return true;
        }
    }

    /// <summary>Retira el gancho. Seguro desde cualquier hilo y repetible. Nunca lanza.</summary>
    public static void Uninstall()
    {
        lock (Candado)
        {
            if (gancho == IntPtr.Zero) return;
            try { UnhookWindowsHookEx(gancho); }
            catch (Exception) { /* el sistema lo retira de todos modos al terminar el proceso */ }
            gancho = IntPtr.Zero;
            delegado = null;
            alDescartar = null;
            Array.Clear(Abajo);
        }
    }

    private static IntPtr Callback(int nCode, IntPtr wParam, IntPtr lParam)
    {
        try
        {
            if (nCode == HcAction)
            {
                var mensaje = (int)wParam;
                if (mensaje is WmKeyDown or WmKeyUp or WmSysKeyDown or WmSysKeyUp)
                {
                    // KBDLLHOOKSTRUCT { DWORD vkCode; DWORD scanCode; DWORD flags; DWORD time; ULONG_PTR dwExtraInfo }: se leen los campos sin crear objetos.
                    var vk = Marshal.ReadInt32(lParam, 0) & 0xFF;
                    var flags = Marshal.ReadInt32(lParam, 8);
                    var bajada = mensaje is WmKeyDown or WmSysKeyDown;
                    var alt = (flags & LlkhfAltDown) != 0 || Pulsada(FiltroDeTeclas.VkMenu);
                    var ctrl = Pulsada(FiltroDeTeclas.VkControl);
                    var shift = Pulsada(FiltroDeTeclas.VkShift);

                    if (bajada)
                    {
                        if (FiltroDeTeclas.Descartar(vk, alt, ctrl, shift))
                        {
                            // Mantener pulsada la tecla repite KEYDOWN: sólo la primera cuenta como un intento.
                            if (!Abajo[vk])
                            {
                                Abajo[vk] = true;
                                Avisar(FiltroDeTeclas.Nombre(vk, alt, ctrl, shift));
                            }
                            return (IntPtr)1;
                        }
                    }
                    else if (Abajo[vk] || FiltroDeTeclas.Descartar(vk, alt, ctrl, shift))
                    {
                        // La suelta de una tecla cuya pulsación se tragó se traga TAMBIÉN (el menú Inicio se abre al soltar), aunque ya se haya soltado Alt o Ctrl.
                        Abajo[vk] = false;
                        return (IntPtr)1;
                    }
                }
            }
        }
        catch (Exception)
        {
            // Nunca una excepción hacia el sistema: la tecla simplemente pasa.
        }
        return CallNextHookEx(gancho, nCode, wParam, lParam);
    }

    private static void Avisar(string nombre)
    {
        try { alDescartar?.Invoke(nombre); }
        catch (Exception) { /* contar una tecla no debe estorbar a la tecla */ }
    }

    private static bool Pulsada(int vk) => (GetAsyncKeyState(vk) & 0x8000) != 0;

    /// <summary>Si Alt y F4 están pulsadas ahora mismo; sirve para distinguir un cierre por teclado de uno por otra vía.</summary>
    public static bool AltF4Pulsadas() => Pulsada(FiltroDeTeclas.VkMenu) && Pulsada(FiltroDeTeclas.VkF4);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SetWindowsHookEx(int idHook, LowLevelKeyboardProc lpfn, IntPtr hMod, uint dwThreadId);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool UnhookWindowsHookEx(IntPtr hhk);

    [DllImport("user32.dll")]
    private static extern IntPtr CallNextHookEx(IntPtr hhk, int nCode, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern short GetAsyncKeyState(int vKey);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr GetModuleHandle(string? lpModuleName);
}
#endif

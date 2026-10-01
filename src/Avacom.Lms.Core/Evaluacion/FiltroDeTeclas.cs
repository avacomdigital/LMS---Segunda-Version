namespace Avacom.Lms.Core.Evaluacion;

/// <summary>
/// Qué teclas descarta el gancho de teclado de Windows durante un examen (kiosk.md §4.3). Es lógica pura, sin una sola API de Windows, para poder probar cada
/// fila de la tabla sin instalar un gancho global en el equipo de quien desarrolla: el gancho (<c>ExamKeyboardGuard</c>) sólo traduce lo que ve el sistema
/// (código de tecla virtual y estado de Alt, Ctrl y Mayús) y le pregunta a esta clase.
///
/// Lo que se descarta, y por qué:
/// <list type="bullet">
/// <item><b>Tecla Windows</b> (izquierda y derecha), sola o combinada: abre Inicio, Win+D, Win+Tab, Win+L…</item>
/// <item><b>Alt+Tab</b> (y Alt+Mayús+Tab, Ctrl+Alt+Tab): cambia de ventana.</item>
/// <item><b>Esc</b>, con cualquier modificador: así caen también Alt+Esc (cambia de ventana), Ctrl+Esc (abre Inicio) y Ctrl+Mayús+Esc (Administrador de tareas).</item>
/// <item><b>Alt+F4</b>: cierra la ventana.</item>
/// <item><b>F11</b>: alterna la pantalla completa del sistema.</item>
/// </list>
/// Todo lo demás pasa: escribir, Tab solo, Ctrl+C / Ctrl+V, Ctrl+Tab, las flechas… (el alumno responde con el teclado). Ctrl+Alt+Supr no se puede
/// interceptar desde ninguna aplicación (kiosk.md §7); sólo lo cierra la capa del sistema.
/// </summary>
public static class FiltroDeTeclas
{
    // Códigos de tecla virtual de Windows (winuser.h). Se declaran aquí para que la lógica no dependa de ningún espacio de nombres de Windows.
    public const int VkTab = 0x09;
    public const int VkEscape = 0x1B;
    public const int VkF4 = 0x73;
    public const int VkF11 = 0x7A;
    public const int VkLWin = 0x5B;
    public const int VkRWin = 0x5C;

    /// <summary>Los códigos que no son teclas sueltas sino modificadores; el gancho los consulta con <c>GetAsyncKeyState</c>.</summary>
    public const int VkShift = 0x10;
    public const int VkControl = 0x11;
    public const int VkMenu = 0x12;      // Alt

    /// <summary>¿Se traga esta pulsación (o esta suelta) para que ni el sistema ni la aplicación la vean?</summary>
    /// <param name="vk">Código de tecla virtual de la tecla que cambió.</param>
    /// <param name="alt">Alt está pulsada.</param>
    /// <param name="ctrl">Ctrl está pulsada.</param>
    /// <param name="shift">Mayús está pulsada.</param>
    public static bool Descartar(int vk, bool alt, bool ctrl, bool shift) => Nombre(vk, alt, ctrl, shift).Length > 0;

    /// <summary>
    /// El nombre legible de la combinación descartada («Windows», «Alt+Tab», «Esc», «Ctrl+Mayús+Esc», «Alt+F4», «F11»…), tal como se agrega por minuto en el
    /// incidente <c>tecla_bloqueada</c>. Cadena vacía si la tecla pasa.
    /// </summary>
    public static string Nombre(int vk, bool alt, bool ctrl, bool shift)
    {
        switch (vk)
        {
            case VkLWin:
            case VkRWin:
                // Win+D, Win+L, Win+Tab…: todas se agrupan bajo un solo nombre para que el profesor lea «Windows» y no veinte variantes.
                return "Windows";
            case VkTab:
                return alt ? Con("Tab", true, ctrl, shift) : string.Empty;
            case VkEscape:
                return Con("Esc", alt, ctrl, shift);
            case VkF4:
                return alt ? Con("F4", true, ctrl, shift) : string.Empty;
            case VkF11:
                return "F11";
            default:
                return string.Empty;
        }
    }

    /// <summary>Alt+Tab, Ctrl+Alt+Tab… siempre en el mismo orden: Ctrl, Alt, Mayús y la tecla.</summary>
    private static string Con(string tecla, bool alt, bool ctrl, bool shift)
    {
        if (!alt && !ctrl && !shift) return tecla;
        var partes = new List<string>(4);
        if (ctrl) partes.Add("Ctrl");
        if (alt) partes.Add("Alt");
        if (shift) partes.Add("Mayús");
        partes.Add(tecla);
        return string.Join('+', partes);
    }
}

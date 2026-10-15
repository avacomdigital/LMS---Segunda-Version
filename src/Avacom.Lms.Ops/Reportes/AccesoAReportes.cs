namespace Avacom.Lms.Ops.Reportes;

/// <summary>
/// Qué ofrece la interfaz de Reportes (MOD-013) según el rol de quien entró. Es una AYUDA para no ofrecer lo que el nodo va a denegar (BR-085 y TST-069 «tanto en la interfaz como
/// en el backend»): quien decide siempre es el nodo, y dentro de la pantalla lo que se ofrece sale de lo que el nodo dice que esa persona puede (<c>filtros.puede</c>), no de
/// adivinar por el rol. Sin sesión de usuario (el prototipo, Q-34) no hay rol que consultar: se deja ver y el nodo decide, igual que «Calificaciones». Sin dependencias de MAUI.
/// </summary>
internal static class AccesoAReportes
{
    /// <summary>Entrar a Reportes: profesorado, administración y reportes. El soporte técnico (que sólo lee el uso de equipos y reconstruye) y el alumnado no ven la tesela.</summary>
    public static bool Leer(bool haySesion, string? rol) => !haySesion || rol is "TEACHER" or "ADMIN" or "REPORTS";

    /// <summary>La frase que dice por qué un rol no entra a los reportes (TST-069): no menciona datos de nadie y dice a quién pedirlo.</summary>
    public static string SinAcceso(string? rol) => rol == "TECHNICIAN"
        ? "El rol de soporte técnico no accede a datos académicos: ni a reportes de clases, de grupos ni de estudiantes. Si lo necesitas, pídele acceso a la administración."
        : "Tu rol no accede a los reportes del aula.";
}

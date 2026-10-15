using Avacom.Lms.Core.Gradebook;

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>
/// Qué ofrece la interfaz de Calificaciones (MOD-011) según el rol de quien entró. Es una AYUDA para no ofrecer lo que el nodo va a denegar (TST-069 «tanto en la
/// interfaz como en el backend»): quien decide siempre es el nodo. Sin sesión de usuario (el prototipo, Q-34) no hay rol que consultar: se deja ver y el nodo decide,
/// igual que el menú «Historial». Sin dependencias de MAUI: se prueba sin interfaz.
/// </summary>
internal static class PermisosDeCalificaciones
{
    /// <summary>Leer el libro: profesorado, administración y reportes. El rol técnico no ve datos académicos.</summary>
    public static bool Leer(bool haySesion, string? rol) => !haySesion || GradebookTexto.PuedeLeerElLibro(rol);

    /// <summary>Calificar, revisar, ajustar, reabrir, valorar, retroalimentar y publicar: sólo el profesorado (la administración no califica directamente).</summary>
    public static bool Calificar(bool haySesion, string? rol) => !haySesion || GradebookTexto.PuedeCalificar(rol);

    /// <summary>Modo, escalas y política: sólo la administración.</summary>
    public static bool Configurar(bool haySesion, string? rol) => !haySesion || GradebookTexto.PuedeConfigurar(rol);

    /// <summary>La frase que dice por qué un rol no entra a los datos académicos (TST-069).</summary>
    public static string SinAccesoAcademico(string? rol) => rol == "TECHNICIAN"
        ? "El rol de soporte técnico no accede a datos académicos: ni a calificaciones ni a datos de estudiantes. Si lo necesitas, pídele acceso a la administración."
        : "Tu rol no accede a las calificaciones del aula.";
}

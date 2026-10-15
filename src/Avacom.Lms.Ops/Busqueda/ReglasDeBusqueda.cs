using Avacom.Lms.Core.Search;

namespace Avacom.Lms.Ops.Busqueda;

/// <summary>
/// Quién puede abrir la pantalla Buscar (MOD-021). Es una AYUDA para no ofrecer lo que el nodo va a denegar: quien decide siempre es el nodo (BR-088: sólo devuelve lo que la
/// persona puede leer). Sin sesión de usuario (el prototipo, Q-34) no hay rol que consultar: se deja ver y el nodo decide. Sin dependencias de MAUI: se prueba sin interfaz.
/// </summary>
internal static class PermisosDeBusqueda
{
    /// <summary>Buscar: profesorado, administración y reportes. El soporte técnico mantiene el índice pero no busca; el alumno no tiene esta pantalla.</summary>
    public static bool Buscar(bool haySesion, string? rol) => !haySesion || rol is "TEACHER" or "ADMIN" or "REPORTS";
}

/// <summary>
/// Adónde lleva cada resultado: SIEMPRE a la pantalla del módulo propietario del recurso (no hay una pantalla paralela para ver o editar cursos, evaluaciones o clases).
/// Sin dependencias de MAUI: se prueba sin interfaz.
/// </summary>
internal static class DestinosDeBusqueda
{
    private static string E(string? valor) => Uri.EscapeDataString(valor ?? string.Empty);

    /// <summary>
    /// La ruta de Shell para abrir un resultado, o null si el destino no trae lo necesario. Cursos, lecciones y recursos abren su CURSO (la pantalla de «Clase de hoy» con sus
    /// lecciones); una evaluación, el panel del examen; un estudio asignado, su detalle en Modo de estudio; una clase en curso, la clase en vivo, y una terminada, su cierre.
    /// </summary>
    public static string? Ruta(DestinoDeNavegacion? destino, string? estado, string? titulo)
    {
        if (destino is null) return null;
        switch (destino.Tipo)
        {
            case TiposDeBusqueda.Curso or TiposDeBusqueda.Leccion or TiposDeBusqueda.Recurso:
                return string.IsNullOrWhiteSpace(destino.CursoRef) ? null : $"clase-curso?curso={E(destino.CursoRef)}&titulo={E(titulo)}";
            case TiposDeBusqueda.Evaluacion:
                return string.IsNullOrWhiteSpace(destino.EntidadId) ? null : $"examen-panel?asignacion={E(destino.EntidadId)}";
            case TiposDeBusqueda.Estudio:
                return string.IsNullOrWhiteSpace(destino.EntidadId) ? null : $"estudio?asignacion={E(destino.EntidadId)}";
            case TiposDeBusqueda.Clase:
                if (string.IsNullOrWhiteSpace(destino.EntidadId)) return null;
                return BusquedaTexto.ClaseEnCurso(estado) ? $"clase-sesion?sesion={E(destino.EntidadId)}" : $"clase-cierre?sesion={E(destino.EntidadId)}";
            default:
                return null;
        }
    }
}

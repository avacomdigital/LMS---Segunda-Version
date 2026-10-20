using Avacom.Lms.Core.Reporting;

namespace Avacom.Lms.Ops.Reportes;

/// <summary>
/// Las rutas de las pantallas de Reportes y cómo se arman sus parámetros. Un solo lugar: la pantalla que navega, la que recibe y el reporte «reciente» que se reabre dicen
/// lo mismo. Sólo viajan identificadores y los códigos del árbol académico; nunca el nombre de una persona. Sin dependencias de MAUI.
/// </summary>
public static class RutasDeReportes
{
    public const string Inicio = "reportes";
    public const string Elegir = "reportes-elegir";
    public const string Clase = "reporte-clase";
    public const string Grupo = "reporte-grupo";
    public const string Alumno = "reporte-alumno";
    public const string Uso = "reporte-uso";
    public const string Estado = "reportes-estado";
    public const string Boletin = "reporte-boletin";
    public const string Boletines = "reporte-boletines";

    /// <summary>Lo que se va a elegir en la pantalla de elección: una clase, un grupo, un alumno, o el grupo cuyos boletines se quieren.</summary>
    public const string ElegirClase = "clase", ElegirGrupo = "grupo", ElegirAlumno = "alumno", ElegirBoletin = "boletin";

    private static string Esc(string valor) => Uri.EscapeDataString(valor);

    private static string Con(string ruta, IEnumerable<(string Clave, string? Valor)> parametros)
    {
        var pares = parametros.Where(p => !string.IsNullOrEmpty(p.Valor)).Select(p => $"{p.Clave}={Esc(p.Valor!)}").ToList();
        return pares.Count == 0 ? ruta : ruta + "?" + string.Join("&", pares);
    }

    private static IEnumerable<(string, string?)> DeNodo(NodoAcademico? nodo) => nodo?.Pares().Select(p => (p.Clave, (string?)p.Valor)) ?? [];

    public static string DeElegir(string que, NodoAcademico? nodo = null) => Con(Elegir, [("que", que), .. DeNodo(nodo)]);

    public static string DeClase(string sesionId) => Con(Clase, [("sesion", sesionId)]);

    public static string DeGrupo(string grupoId, NodoAcademico? nodo = null) => Con(Grupo, [("grupo", grupoId), .. DeNodo(nodo)]);

    public static string DeAlumno(string alumnoId, string? grupoId = null, NodoAcademico? nodo = null) => Con(Alumno, [("alumno", alumnoId), ("grupo", grupoId), .. DeNodo(nodo)]);

    public static string DeUso(PeriodoPedido? periodo = null, string? grupoId = null, NodoAcademico? nodo = null) =>
        Con(Uso, [("desde", periodo?.Desde?.ToString(System.Globalization.CultureInfo.InvariantCulture)), ("hasta", periodo?.Hasta?.ToString(System.Globalization.CultureInfo.InvariantCulture)),
                  ("grupo", grupoId), .. DeNodo(nodo)]);

    /// <summary>El boletín académico de un estudiante en un grupo.</summary>
    public static string DeBoletin(string alumnoId, string grupoId, NodoAcademico? nodo = null) => Con(Boletin, [("alumno", alumnoId), ("grupo", grupoId), .. DeNodo(nodo)]);

    /// <summary>Los boletines de todos los estudiantes de un grupo (uno por estudiante; se exportan juntos).</summary>
    public static string DeBoletines(string grupoId, NodoAcademico? nodo = null) => Con(Boletines, [("grupo", grupoId), .. DeNodo(nodo)]);

    /// <summary>
    /// La pantalla que reabre un reporte reciente (los parámetros que el nodo guardó), o null si el tipo no se puede reabrir (uno reservado) o le falta lo esencial
    /// (un reciente de clase sin su identificador de sesión no es un reporte que se pueda pedir).
    /// </summary>
    public static string? DeReciente(ReporteReciente reciente)
    {
        var nodo = NodoDe(reciente.Parametro);
        switch (reciente.Tipo)
        {
            case TiposDeReporte.Clase:
                return reciente.Parametro("sesion_id") is { Length: > 0 } sesion ? DeClase(sesion) : null;
            case TiposDeReporte.Grupo:
                return reciente.Parametro("grupo_id") is { Length: > 0 } grupo ? DeGrupo(grupo, nodo) : null;
            case TiposDeReporte.Alumno:
                return reciente.Parametro("alumno_id") is { Length: > 0 } alumno ? DeAlumno(alumno, reciente.Parametro("grupo_id"), nodo) : null;
            case TiposDeReporte.Uso:
            {
                long? desde = long.TryParse(reciente.Parametro("desde"), out var d) ? d : null;
                long? hasta = long.TryParse(reciente.Parametro("hasta"), out var h) ? h : null;
                return DeUso(new PeriodoPedido(desde, hasta), reciente.Parametro("grupo_id"), nodo);
            }
            case TiposDeReporte.Boletin:
            {
                if (reciente.Parametro("grupo_id") is not { Length: > 0 } grupoDelBoletin) return null;
                return reciente.Parametro("alumno_id") is { Length: > 0 } alumnoDelBoletin ? DeBoletin(alumnoDelBoletin, grupoDelBoletin, nodo) : DeBoletines(grupoDelBoletin, nodo);
            }
            default:
                return null;
        }
    }

    /// <summary>El nodo académico de una consulta (la de la ruta o la de los parámetros de un reciente); null si no trae ningún código.</summary>
    public static NodoAcademico? NodoDe(Func<string, string?> parametro)
    {
        var nodo = new NodoAcademico(Vacio(parametro("country")), Vacio(parametro("level")), Vacio(parametro("grade")), Vacio(parametro("subject")), Vacio(parametro("topic")));
        return nodo.EstaVacio ? null : nodo;
    }

    private static string? Vacio(string? v) => string.IsNullOrWhiteSpace(v) ? null : v;

    /// <summary>El número de un parámetro de ruta (instantes en milisegundos); null si falta o no es un número.</summary>
    public static long? NumeroDe(string? texto) => long.TryParse(texto, System.Globalization.NumberStyles.Integer, System.Globalization.CultureInfo.InvariantCulture, out var n) ? n : null;
}

using System.Globalization;
using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Reporting;

// Las reglas PURAS de lo que dicen las pantallas de reportes (sin MAUI, probadas aparte): cómo se escriben una cifra, una fecha y una duración, qué dice cada estado vacío y cada error,
// cómo se ve una calificación en el modo de su nivel. Quien consulta es una persona frente a una pantalla gigante, sin teclado: nada de jerga, nada de códigos, y siempre qué hacer.

/// <summary>Cómo se escriben las cifras, las fechas y las duraciones de un reporte (es lo que la pantalla y el archivo exportado deben decir igual).</summary>
public static class FormatoDeReportes
{
    private static readonly string[] Meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
    private static readonly NumberFormatInfo Coma = new() { NumberDecimalSeparator = ",", NumberGroupSeparator = "." };
    public const string SinDato = "—";

    /// <summary>`84,5`, `100`, `22,22`; sin dato, «—» (un promedio sin valores NO es un cero).</summary>
    public static string Cifra(decimal? valor, int decimales = 2)
    {
        if (valor is not { } v) return SinDato;
        var texto = Math.Round(v, decimales, MidpointRounding.AwayFromZero).ToString("0." + new string('#', Math.Max(0, decimales)), Coma);
        return texto.TrimEnd(',');
    }

    public static string Porcentaje(decimal? valor) => valor is null ? SinDato : Cifra(valor) + " %";

    /// <summary>«4 de 5» (para asistencia, entregas…): lo concreto antes que el porcentaje.</summary>
    public static string DeTotal(int parte, int total) => $"{parte} de {total}";

    /// <summary>«1 alumno», «7 alumnos», «0 alumnos»: la cantidad con su nombre en singular o plural.</summary>
    public static string Plural(int cantidad, string singular, string plural) => cantidad == 1 ? $"1 {singular}" : $"{cantidad} {plural}";

    public static string Duracion(long? ms)
    {
        if (ms is not { } m) return SinDato;
        var minutos = Math.Max(0, m) / 60_000;
        if (minutos < 1) return "menos de 1 min";
        var (horas, resto) = (minutos / 60, minutos % 60);
        return horas > 0 ? $"{horas} h {resto:00} min" : $"{minutos} min";
    }

    private static DateTimeOffset Local(long ms, TimeZoneInfo? zona) => TimeZoneInfo.ConvertTime(DateTimeOffset.FromUnixTimeMilliseconds(ms), zona ?? TimeZoneInfo.Local);

    /// <summary>`15 oct · 10:42`.</summary>
    public static string FechaCorta(long ms, TimeZoneInfo? zona = null)
    {
        var l = Local(ms, zona);
        return $"{l.Day} {Meses[l.Month - 1]} · {l:HH:mm}";
    }

    /// <summary>`15 oct 2026 · 10:42`.</summary>
    public static string FechaLarga(long ms, TimeZoneInfo? zona = null)
    {
        var l = Local(ms, zona);
        return $"{l.Day} {Meses[l.Month - 1]} {l.Year} · {l:HH:mm}";
    }

    /// <summary>Sólo la hora: `10:42`.</summary>
    public static string Hora(long ms, TimeZoneInfo? zona = null) => Local(ms, zona).ToString("HH:mm", CultureInfo.InvariantCulture);

    /// <summary>Sólo el día: `15 oct`.</summary>
    public static string Dia(long ms, TimeZoneInfo? zona = null)
    {
        var l = Local(ms, zona);
        return $"{l.Day} {Meses[l.Month - 1]}";
    }

    /// <summary>«Datos al 15 oct · 10:42 · 2 tabletas sin sincronizar» (BR-083). Sin pendientes, sólo la fecha: lo normal no se anuncia.</summary>
    public static string LineaDeCorte(CorteDeDatos corte, TimeZoneInfo? zona = null) =>
        $"Datos al {FechaCorta(corte.En, zona)}" + (corte.Integracion.Incompleta ? " · " + corte.Integracion.Texto : "");

    /// <summary>Lo que la pantalla dice de la antigüedad del dato (el estado técnico de la proyección NO se muestra como estado interno).</summary>
    public static string Antiguedad(CorteDeDatos corte) => corte.Estado switch
    {
        EstadosDeProyeccion.Reconstruyendose => "Se están actualizando los reportes. Lo que ves es lo último que estaba listo.",
        EstadosDeProyeccion.Rezagada => $"Faltan novedades por reflejar: estos datos tienen {Duracion(corte.AntiguedadMs)}.",
        _ => "Datos al día.",
    };

    /// <summary>`2,0 KB`, `1,3 MB`, `14 GB`: el tamaño de un archivo o el espacio libre de una unidad.</summary>
    public static string Tamano(long bytes)
    {
        string[] unidades = ["B", "KB", "MB", "GB", "TB"];
        double v = Math.Max(0, bytes);
        var i = 0;
        while (v >= 1024 && i < unidades.Length - 1) { v /= 1024; i++; }
        return i == 0 ? $"{v:0} B" : (v >= 10 ? $"{v:0}" : $"{v:0.0}").Replace('.', ',') + " " + unidades[i];
    }

    /// <summary>Qué hizo la tableta de un alumno al terminar la clase (lo que el nodo anotó de su presencia).</summary>
    public static string Presencia(string estado) => estado switch
    {
        "conectado" => "Presente al cerrar",
        "reconectando" => "Sin conexión al cerrar",
        "salio" => "Salió antes del cierre",
        "expulsado" => "Retirado de la clase",
        _ => estado,
    };

    public static string EstadoDeEstudio(string estado) => estado switch { "pendiente" => "Pendiente", "en_curso" => "En curso", "completada" => "Completada", _ => estado };

    public static string EstadoDeAsignacion(string estado) => estado switch
    {
        "programada" => "Programada", "activa" => "En curso", "activa_fuera_de_plazo" => "Fuera de plazo", "cerrada" => "Cerrada", "archivada" => "Archivada", _ => estado,
    };
}

/// <summary>Lo que dice cada pantalla cuando no hay nada que mostrar: su propio texto y qué hacer (nunca una tabla vacía sin explicación).</summary>
public static class EstadosVaciosDeReportes
{
    public const string SinGrupos = "No tienes grupos con reportes. Pide a la administración que te asigne uno.";
    public const string SinClases = "No hay clases cerradas en este periodo. Elige otro periodo.";
    public const string SinClasesDelGrupo = "Este grupo todavía no tiene clases cerradas. Cuando termines una, su reporte aparece aquí.";
    public const string SinAlumnos = "Este grupo todavía no tiene alumnos. Pide a la administración que los registre.";
    public const string SinEvaluaciones = "Este grupo no tiene evaluaciones asignadas todavía.";
    public const string SinEstudio = "Este grupo no tiene tareas de estudio asignadas todavía.";
    public const string SinUso = "No hay clases finalizadas en este periodo. Elige otro periodo.";
    public const string SinRecientes = "Todavía no has abierto ningún reporte. Elige uno arriba.";
    public const string SinExportaciones = "Todavía no has guardado ningún reporte en un archivo.";
    public const string SinEquipos = "Ninguna tableta quedó registrada en las clases de este periodo.";
    public const string ClaseEnCurso = "Esta clase aún no termina. Su reporte se arma cuando la cierres.";
    public const string SinActividades = "En esta clase no se lanzó ninguna actividad: no hay participación ni aciertos que mostrar.";
    public const string SinCifras = "Todavía no hay cifras que mostrar.";
    public const string Cargando = "Armando el reporte…";
    public const string AunNoDisponible = "Aún no disponible";
    public const string Aviso = "Elige un grupo para ver su reporte.";

    /// <summary>Todo lo que el reporte mostraría está en el nodo pero esta persona no tiene nada visible: se dice sin dar a entender que haya un error.</summary>
    public static string SinAlumnosVisibles(Privacidad privacidad) => privacidad.Aplicada ? privacidad.Aviso : SinAlumnos;
}

/// <summary>Los errores del nodo y de la red, dichos para quien está frente a la pantalla: qué pasó y qué hacer. Nunca el código ni «excepción».</summary>
public static class MensajesDeReportes
{
    public static string De(ErrorAula? error, string respaldo = "No se pudo armar el reporte. Vuelve a intentarlo.")
    {
        if (error is null) return respaldo;
        return error.Codigo switch
        {
            null when error.Estado == 0 => "No hay conexión con el aula. Revisa que el equipo del aula esté encendido y en la misma red.",
            "sin_conexion" => "No hay conexión con el aula. Revisa que el equipo del aula esté encendido y en la misma red.",
            "sin_permiso" => "Tu rol no puede ver este reporte. Si lo necesitas, pídelo a la administración.",
            "fuera_de_alcance" => "Ese grupo no es de los tuyos: sólo ves los reportes de los grupos en los que eres docente.",
            "clase_en_curso" => EstadosVaciosDeReportes.ClaseEnCurso,
            "sin_sesiones_finalizadas" => EstadosVaciosDeReportes.SinUso,
            "alumno_sin_grupo" => "Ese alumno no pertenece a ningún grupo activo, así que no hay avance que mostrar.",
            "no_encontrado" => "Ese reporte ya no existe. Vuelve a elegirlo.",
            "no_instalado" => "El nodo aún no está instalado: no hay grupos ni alumnos de los que reportar.",
            "sesion_activa" => "Hay una clase en curso. Reconstruir los reportes espera a que termine, para no competir con las tabletas.",
            "reconstruccion_en_curso" => "Ya se están reconstruyendo los reportes. Espera a que termine.",
            "capacidad_reservada" => error.Detalle,
            "destino_no_permitido" => "El administrador del colegio no permite guardar reportes en memorias extraíbles. Elige una carpeta de este equipo o de la red.",
            "razon_requerida" => "Elige para qué vas a guardar este reporte.",
            "exportacion_caducada" => "Pasó demasiado tiempo sin confirmar dónde se guardó el archivo. Genera el reporte de nuevo.",
            "exportacion_ya_confirmada" => "Ese archivo ya quedó guardado.",
            "huella_distinta" => "El archivo guardado no coincide con el original, así que no se dio por guardado. Guárdalo de nuevo.",
            "conflicto_de_version" => "Otra persona cambió esta configuración mientras la editabas. Vuelve a leerla y repite tu cambio.",
            "archivo_danado" or "respuesta_incompleta" or "sin_temporal" => error.Detalle,
            _ => string.IsNullOrWhiteSpace(error.Detalle) ? respaldo : error.Detalle,
        };
    }

    /// <summary>Un 5xx o un error que no sabemos nombrar: se dice que no depende de quien consulta.</summary>
    public static bool EsDelNodo(ErrorAula? error) => error is { Estado: >= 500 };
    public static bool SinConexion(ErrorAula? error) => error is { Estado: 0 };
    public static bool SinPermiso(ErrorAula? error) => error?.Codigo is "sin_permiso" or "fuera_de_alcance";
}

/// <summary>Cómo se ve la calificación de una evaluación en el modo de su nivel: la presentación que el libro (MOD-011) ya resolvió, sin convertir nada; en modo simple, un símbolo.</summary>
public static class PresentacionDeNotas
{
    public const string SinPublicar = "Aún sin publicar";

    /// <summary>La nota tal como la presentó el libro: «3,8 · Básico» (con «provisional» si todavía no se publicó). En modo simple no hay nota: el estado.</summary>
    public static string Texto(EvaluacionDeAlumno e)
    {
        if (!e.Presento) return e.SinPresentar ? "Sin presentar" : "Aún sin presentar";
        if (e.Presentacion is { } p)
        {
            // Igual que el libro de calificaciones: la etiqueta que ya formateó el nodo, con la coma de la cultura («3.8» → «3,8», «4.0» → «4,0»); nada se vuelve a formatear.
            var nota = GradebookTexto.Valor(p.Presentada) ?? string.Empty;
            var nivel = p.Desempeno?.Nivel;
            var texto = string.IsNullOrWhiteSpace(nivel) || nivel == nota ? nota : $"{nota} · {nivel}";
            return p.Provisional ? $"{texto} (provisional)" : texto;
        }
        return EstadoSimple(e.EstadoSimple);
    }

    public static string EstadoSimple(string estado) => estado switch
    {
        EstadosSimples.NoIniciado => "Sin empezar",
        EstadosSimples.EnProgreso => "En progreso",
        EstadosSimples.Completado => "Completado",
        _ => estado,
    };

    /// <summary>El símbolo del estado simple (los mismos tres que ve el alumno): vacío, medio y lleno.</summary>
    public static string Simbolo(string simbolo) => simbolo switch { "lleno" => "●", "medio" => "◐", _ => "○" };

    /// <summary>¿La nota es del nivel en modo calificaciones y ya está publicada? (lo demás se pinta con la etiqueta de su estado).</summary>
    public static string EstadoDeLaNota(EvaluacionDeAlumno e) => e.Estado switch
    {
        EstadosDeResultado.Definitivo => "Publicada",
        EstadosDeResultado.Revisado => "Revisada, sin publicar",
        EstadosDeResultado.Provisional => "Provisional",
        EstadosDeResultado.Pendiente => "Por revisar",
        EstadosDeResultado.Reabierto => "Reabierta",
        EstadosDeResultado.Anulado => "Anulada",
        _ => e.Presento ? SinPublicar : "",
    };
}

using System.Globalization;

namespace Avacom.Lms.Core.Gradebook;

/// <summary>
/// Lo que el boletín de un estudiante y las listas de estudiantes y de evaluaciones dicen en palabras, sin pintar nada (se prueba sin interfaz). Ninguna regla académica vive aquí: el nodo
/// calcula y esto sólo traduce. Lo pendiente no es un cero, el promedio es simple e informativo, y sin sistema de calificación (modo simple) no hay cifras.
/// </summary>
public static class BoletinTexto
{
    private static CultureInfo Cultura => GradebookTexto.Cultura;

    /// <summary>Las iniciales de un nombre para el avatar: «Julian Reyes» → «JR». Dos letras como mucho; un nombre vacío, «?».</summary>
    public static string Iniciales(string? nombre)
    {
        var partes = (nombre ?? string.Empty).Split([' ', '.', '-'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        return partes.Length switch
        {
            0 => "?",
            1 => char.ToUpper(partes[0][0], Cultura).ToString(),
            _ => string.Concat(char.ToUpper(partes[0][0], Cultura), char.ToUpper(partes[1][0], Cultura)),
        };
    }

    /// <summary>La fecha de una evaluación, corta y en español: «12 oct 2026». Sin fecha, «—».</summary>
    public static string Fecha(long? ms) => ms is { } v and > 0 ? DateTimeOffset.FromUnixTimeMilliseconds(v).ToLocalTime().ToString("d MMM yyyy", Cultura).Replace(".", string.Empty) : "—";

    /// <summary>Un promedio presentado con el sistema del nivel, con la coma de la cultura: «3,8». Sin promedio, «—».</summary>
    public static string Promedio(PromedioPresentado? p) =>
        p is null ? "—" : string.IsNullOrWhiteSpace(p.Etiqueta) ? "—" : p.Valor is not null ? p.Etiqueta.Replace(".", Cultura.NumberFormat.NumberDecimalSeparator) : p.Etiqueta;

    /// <summary>El promedio simple (0–100, informativo): «71,43». Sin promedio, «—»: lo que no se ha calificado no es un cero.</summary>
    public static string PromedioInterno(decimal? valor) => GradebookTexto.Puntaje(valor);

    /// <summary>Lo que dice el desempeño y el criterio de un promedio: «Básico · cumple el criterio».</summary>
    public static string LecturaDelPromedio(PromedioPresentado? p)
    {
        if (p is null) return string.Empty;
        var partes = new List<string>();
        if (!string.IsNullOrWhiteSpace(p.Desempeno)) partes.Add(p.Desempeno!);
        if (p.CumpleCriterio is { } cumple) partes.Add(cumple ? "cumple el criterio" : "no cumple el criterio");
        return string.Join(" · ", partes);
    }

    /// <summary>Cuántas evaluaciones tienen nota de cuántas: «3 de 8 con nota».</summary>
    public static string ConNota(ResumenDeEstudiante r) => $"{r.Conteo.ConNota} de {r.Evaluaciones} con nota";

    /// <summary>Cuántas completó de cuántas: «Completó 5 de 8 evaluaciones».</summary>
    public static string Constancia(ConstanciaDelEstudiante c) =>
        c.Evaluaciones == 0 ? "Todavía no hay evaluaciones." : c.Evaluaciones == 1 ? (c.Completadas == 1 ? "Completó su única evaluación." : "Todavía no completó su única evaluación.") : $"Completó {c.Completadas} de {c.Evaluaciones} evaluaciones.";

    /// <summary>Lo que le queda al profesor por hacer con un estudiante, en una frase corta; vacío si no queda nada.</summary>
    public static string PorAtender(ConteoDeEvaluaciones c)
    {
        var partes = new List<string>();
        if (c.PorRevisar > 0) partes.Add(c.PorRevisar == 1 ? "1 por revisar" : $"{c.PorRevisar} por revisar");
        if (c.SinRegistro > 0) partes.Add(c.SinRegistro == 1 ? "1 sin registrar" : $"{c.SinRegistro} sin registrar");
        if (c.SinPublicar > 0) partes.Add(c.SinPublicar == 1 ? "1 sin publicar" : $"{c.SinPublicar} sin publicar");
        return string.Join(" · ", partes);
    }

    /// <summary>La tendencia en palabras. Con menos de cuatro calificaciones no se dice hacia dónde va: se dice cuántas faltan.</summary>
    public static string Tendencia(TendenciaDelEstudiante t) => t.Direccion switch
    {
        "sube" => $"Va mejorando: lo reciente ({Num(t.A)} de 100) supera a lo anterior ({Num(t.De)}).",
        "baja" => $"Va bajando: lo reciente ({Num(t.A)} de 100) está por debajo de lo anterior ({Num(t.De)}).",
        "estable" => $"Se mantiene estable: {Num(t.A)} de 100 frente a {Num(t.De)} antes.",
        _ => t.Minimo is { } minimo && t.Calificaciones < minimo
            ? $"Todavía no se puede decir hacia dónde va: lleva {t.Calificaciones} {(t.Calificaciones == 1 ? "calificación" : "calificaciones")} y se necesitan {minimo}."
            : "Todavía no se puede decir hacia dónde va.",
    };

    /// <summary>Un símbolo corto de la tendencia para la insignia: ▲ sube · ▼ baja · ▬ estable · · sin datos.</summary>
    public static string SimboloDeTendencia(string? direccion) => direccion switch { "sube" => "▲", "baja" => "▼", "estable" => "▬", _ => "·" };

    /// <summary>El estado de una evaluación del boletín para el profesor, en una palabra: lo que tiene, o por qué no tiene nota.</summary>
    public static string Estado(EvaluacionDelBoletin e) => e.Estado switch
    {
        EstadosDeResultado.Definitivo => "Publicada",
        EstadosDeResultado.Revisado => "Sin publicar",
        EstadosDeResultado.Provisional => "Por revisar",
        EstadosDeResultado.Reabierto => "En recalificación",
        EstadosDeResultado.SinRegistro => e.EstadoSimple == EstadosSimples.Completado ? "Sin registrar" : "Pendiente",
        EstadosDeResultado.Anulado => "Anulada",
        _ => e.EstadoSimple switch { EstadosSimples.EnProgreso => "En progreso", EstadosSimples.Completado => "Completada", _ => "Sin hacer" },
    };

    /// <summary>La nota de una evaluación como la presenta el sistema; «—» si todavía no hay (nunca un cero inventado).</summary>
    public static string Nota(EvaluacionDelBoletin e) => e.Presentacion is null ? "—" : GradebookTexto.Presentada(e.Presentacion);

    /// <summary>El resultado interno (0–100) de una evaluación, sólo para el profesor: «interno 71,43 de 100». Vacío si no hay.</summary>
    public static string Interno(EvaluacionDelBoletin e) => e.PuntajeEfectivo is { } v ? $"interno {GradebookTexto.Puntaje(v)} de 100" : string.Empty;

    /// <summary>Si con esa nota se cumple el criterio de aprobación del sistema: true/false, o nulo si el sistema no lo define o no hay nota.</summary>
    public static bool? Cumple(EvaluacionDelBoletin e) => e.Presentacion?.Aprobacion?.CumpleCriterio;

    /// <summary>Los puntos sumados de un curso o del resumen: «27 de 36 puntos · 75 %». Vacío si nada tiene puntos.</summary>
    public static string Bruto(SumaBruta? b)
    {
        if (b is null || !b.TienePuntos) return string.Empty;
        var texto = $"{GradebookTexto.Puntaje(b.Puntos)} de {GradebookTexto.Puntaje(b.PuntosMaximos)} puntos";
        return b.Porcentaje is { } p ? $"{texto} · {GradebookTexto.Puntaje(p)} %" : texto;
    }

    /// <summary>Lo que el profesor recomendó en una observación, en una línea: las frases y el comentario.</summary>
    public static string Recomendaciones(ObservacionDelDocente o)
    {
        var partes = o.Recomendaciones.Select(r => r.Texto).ToList();
        if (!string.IsNullOrWhiteSpace(o.Texto)) partes.Add(o.Texto);
        return string.Join(" · ", partes);
    }

    private static string Num(decimal? valor) => GradebookTexto.Puntaje(valor);
}

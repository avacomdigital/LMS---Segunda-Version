using Avacom.Lms.Core.Gradebook;

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>Un paso que se toca para puntuar: el valor en puntos y lo que dice el botón.</summary>
internal sealed record PasoDePuntaje(decimal Valor, string Rotulo);

/// <summary>
/// Los pasos con los que se puntúa sin teclado. Sin rúbrica: 0, 25, 50, 75 y 100 % de lo que vale la pregunta (como en el expediente del examen). Con rúbrica: pasos
/// por criterio, escogidos para que haya pocos botones sea cual sea el valor del criterio. El nodo vuelve a validar todo (0 a lo que vale, a lo sumo dos decimales).
/// Sin dependencias de MAUI: se prueba sin interfaz.
/// </summary>
internal static class PuntuacionDeRevision
{
    private static readonly decimal[] Fracciones = [0m, 0.25m, 0.5m, 0.75m, 1m];
    private static readonly decimal[] PasosPosibles = [0.25m, 0.5m, 1m, 2m, 5m, 10m, 25m, 50m];
    private const int MaximoDePasos = 6;

    /// <summary>0, 25, 50, 75 y 100 % del máximo, redondeados a dos decimales (lo que admite el nodo).</summary>
    public static IReadOnlyList<PasoDePuntaje> Porcentuales(decimal maximo) =>
        maximo <= 0
            ? []
            : Fracciones.Select(f => new PasoDePuntaje(decimal.Round(maximo * f, 2), f == 0 ? "0" : $"{(int)(f * 100)} %")).ToList();

    /// <summary>
    /// Los puntos que se pueden dar a un criterio que vale <paramref name="maximo"/>: de 0 a lo que vale, con el paso más corto que deje a lo sumo siete botones, y siempre
    /// con el máximo al final. Un criterio de 1 punto: 0 · 0,25 · 0,5 · 0,75 · 1. Uno de 2 puntos: 0 · 0,5 · 1 · 1,5 · 2.
    /// </summary>
    public static IReadOnlyList<decimal> Pasos(decimal maximo)
    {
        if (maximo <= 0) return [0m];
        var paso = PasosPosibles.FirstOrDefault(p => maximo / p <= MaximoDePasos);
        if (paso == 0) paso = decimal.Round(maximo / MaximoDePasos, 2, MidpointRounding.AwayFromZero);
        var lista = new List<decimal>();
        for (var v = 0m; v < maximo; v += paso) lista.Add(decimal.Round(v, 2));
        lista.Add(maximo);
        return lista;
    }

    /// <summary>El rótulo de un paso de un criterio: «0», «Completo» o los puntos.</summary>
    public static string Rotulo(decimal valor, decimal maximo) => valor == 0 ? "0" : valor == maximo ? $"{GradebookTexto.Puntaje(valor)} · completo" : GradebookTexto.Puntaje(valor);

    /// <summary>El total de lo elegido hasta ahora, calculado en vivo con lo que el profesor tocó. Es sólo la suma que ve el profesor; el nodo la vuelve a calcular.</summary>
    public static decimal Total(IEnumerable<decimal> elegidos) => elegidos.Sum();

    /// <summary>Lo que vale la pregunta según su rúbrica: la suma de lo que vale cada criterio.</summary>
    public static decimal MaximoDeRubrica(IEnumerable<CriterioDeRubrica> criterios) => criterios.Sum(c => c.PuntosMax);

    /// <summary>¿Ya se eligió un valor para TODOS los criterios? El nodo exige que vengan todos.</summary>
    public static bool Completa(IReadOnlyList<CriterioDeRubrica> criterios, IReadOnlyDictionary<string, decimal> elegidos) =>
        criterios.Count > 0 && criterios.All(c => elegidos.ContainsKey(c.Id));

    /// <summary>Los criterios puntuados, en el orden de la rúbrica, listos para mandar. Nulo si falta alguno o algún valor se sale de lo que vale el criterio.</summary>
    public static IReadOnlyList<CriterioPuntuado>? Armar(IReadOnlyList<CriterioDeRubrica> criterios, IReadOnlyDictionary<string, decimal> elegidos)
    {
        if (!Completa(criterios, elegidos)) return null;
        var lista = new List<CriterioPuntuado>();
        foreach (var c in criterios)
        {
            var valor = elegidos[c.Id];
            if (GradebookTexto.ErrorDePuntosDeCriterio(GradebookTexto.Puntaje(valor), c.PuntosMax) is not null) return null;
            lista.Add(new CriterioPuntuado(c.Id, valor));
        }
        return lista;
    }

    /// <summary>
    /// La firma de una petición de puntuar: lo mismo = el mismo intento de guardar (se reutiliza su <c>solicitud_id</c> tras perder la señal); cambiar un valor, el
    /// comentario o el motivo es otra petición.
    /// </summary>
    public static string FirmaManual(string intentoId, string preguntaRef, decimal puntaje, string? comentario, string? motivo) =>
        $"manual|{intentoId}|{preguntaRef}|{GradebookTexto.Puntaje(puntaje)}|{comentario}|{motivo}";

    public static string FirmaRubrica(string intentoId, string preguntaRef, IEnumerable<CriterioPuntuado> criterios, string? comentario, string? motivo) =>
        $"rubrica|{intentoId}|{preguntaRef}|{string.Join(",", criterios.Select(c => $"{c.CriterioId}={GradebookTexto.Puntaje(c.Puntos)}"))}|{comentario}|{motivo}";
}

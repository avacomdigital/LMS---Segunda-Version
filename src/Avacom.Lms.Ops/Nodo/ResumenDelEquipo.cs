using Avacom.Lms.Core.Nodo;

namespace Avacom.Lms.Ops.Nodo;

/// <summary>Una línea de la pestaña «Estado del equipo»: rótulo, valor y tono (PAN-242). Pura, sin MAUI.</summary>
public sealed record LineaDelEquipo(string Rotulo, string Valor, TonoDelNodo Tono = TonoDelNodo.Neutro);

/// <summary>Una fila de la cola por consumidor: su nombre, su estado, los pendientes y los apartados, y una línea por fuente.</summary>
public sealed record FilaDeConsumidor(string Nombre, string NombreVisible, string Estado, string EstadoVisible, TonoDelNodo Tono, long Pendientes, int Problemas, IReadOnlyList<string> Fuentes, string? Reintento);

/// <summary>
/// Lo que la pestaña «Estado del equipo» muestra del nodo (P-18), calculado sin interfaz para que <c>Ops.Tests</c> lo pruebe: el chip de estado con su explicación, las líneas de la base,
/// el disco, el reloj y el arranque (incluido el último punto de recuperación, que hasta MOD-016 es «no disponible»), la cola por consumidor del peor al mejor y los problemas con
/// qué botón ofrecer. Nada de aquí lleva la carga de un evento: el nodo no la entrega (R-13).
/// </summary>
public static class ResumenDelEquipo
{
    /// <summary>Las líneas de la tarjeta del nodo, en orden. Un valor no medido se dice como tal, nunca como cero.</summary>
    public static IReadOnlyList<LineaDelEquipo> Lineas(EstadoDelNodo e, TimeZoneInfo? zona = null)
    {
        var lineas = new List<LineaDelEquipo> { new("Versión del nodo", string.IsNullOrWhiteSpace(e.Version) ? "desconocida" : e.Version!) };
        if (e.Base is { } b)
        {
            lineas.Add(new("Base de datos", b.TransaccionInmediata && b.Integra ? "escritor único · comprobada" : !b.Integra ? "la comprobación no pasó" : "sin escritor único",
                b.TransaccionInmediata && b.Integra ? TonoDelNodo.Bien : TonoDelNodo.Problema));
            lineas.Add(new("Diario WAL", NodoTexto.Tamano(b.WalBytes), b.WalBytes > 256L * 1024 * 1024 ? TonoDelNodo.Atencion : TonoDelNodo.Neutro));
        }
        if (e.Disco is { LibreBytes: { } libre })
        {
            var total = e.Disco.TotalBytes;
            var pct = total is > 0 ? 100.0 * libre / total.Value : (double?)null;
            var valor = pct is null ? NodoTexto.Tamano(libre) + " libres" : $"{NodoTexto.Tamano(libre)} libres de {NodoTexto.Tamano(total!.Value)} ({pct.Value:0} %)";
            lineas.Add(new("Disco del nodo", valor, libre < 2L * 1024 * 1024 * 1024 || pct is < 5 ? TonoDelNodo.Problema : libre < 8L * 1024 * 1024 * 1024 ? TonoDelNodo.Atencion : TonoDelNodo.Bien));
        }
        else lineas.Add(new("Disco del nodo", "no medido"));
        if (e.Reloj is { } r)
            lineas.Add(new("Reloj del nodo", r.RetrocesoMs > 0 ? $"retrocedió {Math.Round(r.RetrocesoMs / 60000.0):0} min respecto de lo ya visto" : $"en orden · {NodoTexto.FechaYHora(r.Ahora, zona)}",
                r.RetrocesoMs > 0 ? TonoDelNodo.Problema : TonoDelNodo.Bien));
        if (e.Cola is { } c)
        {
            lineas.Add(new("Cola de salida", $"{NodoTexto.EventosEnCola(c.Eventos)} · última secuencia {c.UltimaSecuencia:N0}"));
            lineas.Add(new("Eventos apartados", NodoTexto.Apartados(c.Problemas), c.Problemas > 0 ? TonoDelNodo.Atencion : TonoDelNodo.Bien));
        }
        if (e.Arranque is { } a)
        {
            lineas.Add(new("Último arranque", a.ApagadoSucioPrevio ? "el anterior no se cerró limpio (apagado sucio)" : "cierre limpio del anterior", a.ApagadoSucioPrevio ? TonoDelNodo.Atencion : TonoDelNodo.Bien));
            if (a.Restauracion is { } rest)
                lineas.Add(new("Restauración detectada", $"la base traía hasta la secuencia {rest.MaxEnBase:N0} y el nodo ya había emitido hasta {rest.Ancla:N0}: el contador saltó a {rest.Contador:N0}", TonoDelNodo.Atencion));
        }
        lineas.Add(new("Último punto de recuperación", e.Purga is { RespaldoVerificadoHasta: > 0 } p ? $"respaldo verificado hasta la secuencia {p.RespaldoVerificadoHasta:N0}" : "no disponible: el respaldo (MOD-016) aún no existe", TonoDelNodo.Neutro));
        return lineas;
    }

    /// <summary>Los motivos del modo restringido, en frases con qué hacer (vacío si no hay).</summary>
    public static IReadOnlyList<string> Motivos(EstadoDelNodo e) => e.Motivos.Select(NodoTexto.Motivo).ToList();

    /// <summary>La cola por consumidor, del peor al mejor.</summary>
    public static IReadOnlyList<FilaDeConsumidor> Consumidores(ColaDelNodo cola, TimeZoneInfo? zona = null) =>
        ReglasDeNodo.Ordenados(cola.Consumidores).Select(c => new FilaDeConsumidor(c.Nombre, NodoTexto.NombreDeConsumidor(c.Nombre), c.Estado, NodoTexto.EstadoDeConsumidor(c.Estado),
            NodoTexto.TonoDeConsumidor(c.Estado), c.Pendientes, c.Problemas, c.Fuentes.Select(NodoTexto.Fuente).ToList(),
            c.Fuentes.Select(f => f.Reintento).FirstOrDefault(r => r is not null) is { } r ? NodoTexto.Reintento(r, zona) : null)).ToList();

    /// <summary>El resumen de una línea de la cola: «3 consumidores · 2 al día · 1 rezagado · 1 evento apartado».</summary>
    public static string ResumenDeCola(ColaDelNodo cola)
    {
        var n = cola.Consumidores.Count;
        var partes = new List<string> { n == 1 ? "1 consumidor" : $"{n} consumidores" };
        foreach (var estado in EstadosDeConsumidor.Todos)
        {
            var cuantos = cola.Consumidores.Count(c => c.Estado == estado);
            if (cuantos > 0) partes.Add($"{cuantos} {NodoTexto.EstadoDeConsumidor(estado).ToLowerInvariant()}");
        }
        partes.Add(NodoTexto.Apartados(cola.Problemas));
        return string.Join(" · ", partes);
    }
}

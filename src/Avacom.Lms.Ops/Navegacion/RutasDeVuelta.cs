namespace Avacom.Lms.Ops.Navegacion;

/// <summary>
/// La ruta relativa para volver hasta una pantalla concreta («Menú principal», «Clase de hoy») contando cuántas hay encima en la pila de Shell. Lógica pura, sin MAUI: quien llama dice cuáles
/// páginas de la pila son la buscada y aquí se decide qué hacer. El caso límite es el que rompía OPS: si la buscada <b>ya es la página de arriba</b> no hay nada que sacar; devolver una
/// ruta de reserva («..») sacaba la propia pantalla buscada y llevaba al acceso cuando el toque llegaba dos veces.
/// </summary>
public static class RutasDeVuelta
{
    /// <summary>
    /// <paramref name="coincidencias"/> lleva un valor por página de la pila, de la raíz hacia arriba (<c>true</c> = es la pantalla buscada). Devuelve «..», «../..»… con tantos saltos como
    /// páginas haya sobre la última coincidencia; <c>null</c> si esa coincidencia ya está arriba (nada que hacer); <paramref name="porDefecto"/> si ninguna página de la pila es la buscada.
    /// </summary>
    public static string? Hasta(IReadOnlyList<bool> coincidencias, string? porDefecto)
    {
        for (var i = coincidencias.Count - 1; i >= 0; i--)
        {
            if (!coincidencias[i]) continue;
            var saltos = coincidencias.Count - 1 - i;
            return saltos > 0 ? string.Join("/", Enumerable.Repeat("..", saltos)) : null;
        }
        return porDefecto;
    }
}

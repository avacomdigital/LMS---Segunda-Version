namespace Avacom.Lms.Core.Services;

/// <summary>
/// La hora del nodo del aula vista desde una app (BR-062, INV-017): ningún dato académico usa el reloj del dispositivo. La tableta
/// aprende el desfase con lo que dice el nodo (<c>servidor_en</c> de cada respuesta y del saludo del WebSocket) y con él normaliza
/// cuándo capturó cada respuesta; el nodo conserva la hora cruda del aparato sólo como dato adicional y decide con la suya.
/// </summary>
public static class RelojNodo
{
    private static long desfase;             // servidor − local, en ms
    private static int aprendido;

    public static long LocalMs => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

    /// <summary>Verdadero cuando ya se oyó al nodo al menos una vez.</summary>
    public static bool Aprendido => Volatile.Read(ref aprendido) == 1;

    /// <summary>El desfase que se aprendió: cuánto está adelantado el nodo respecto de este aparato.</summary>
    public static long DesfaseMs => Interlocked.Read(ref desfase);

    /// <summary>La hora del nodo ahora mismo, estimada. Antes de oír al nodo es la hora local.</summary>
    public static long AhoraMs => LocalMs + DesfaseMs;

    /// <summary>Aprende del <c>servidor_en</c> de una respuesta. El viaje de ida y vuelta por la LAN (milisegundos) se ignora.</summary>
    public static void Aprender(long servidorEnMs)
    {
        if (servidorEnMs <= 0) return;
        Interlocked.Exchange(ref desfase, servidorEnMs - LocalMs);
        Volatile.Write(ref aprendido, 1);
    }

    /// <summary>Convierte una hora local del aparato a hora del nodo con el desfase aprendido.</summary>
    public static long ANodo(long localMs) => localMs + DesfaseMs;

    /// <summary>Sólo para pruebas: olvida lo aprendido.</summary>
    public static void Olvidar()
    {
        Interlocked.Exchange(ref desfase, 0);
        Volatile.Write(ref aprendido, 0);
    }
}

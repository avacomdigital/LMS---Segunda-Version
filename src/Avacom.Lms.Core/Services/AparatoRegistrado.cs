namespace Avacom.Lms.Core.Services;

/// <summary>
/// El id con el que el nodo conoce a este aparato (<c>m09_dispositivo.id</c>, MOD-009). Es lo que viaja en <c>X-Avacom-Dispositivo</c> en cada
/// petición HTTP y en el handshake de los WebSocket (019-01), para que cada asiento de la bitácora sepa desde qué equipo se hizo.
///
/// El aparato lo aprende del nodo: lo devuelve el latido (<c>POST /api/dispositivos/latido/</c>, que registra al equipo si es nuevo) y la
/// participación en una clase (<c>participante.dispositivo_id</c>). Cada app lo persiste como quiera (<see cref="Cargar"/> / <see cref="Guardar"/>,
/// Preferences en MAUI) para que sobreviva al reinicio; sin persistencia funciona en memoria. Nunca se inventa: sin id, no hay cabecera.
/// </summary>
public static class AparatoRegistrado
{
    private static readonly object Cerrojo = new();
    private static string? id;
    private static bool cargado;

    /// <summary>Cómo recuperar el id guardado la última vez (por ejemplo, Preferences). Opcional.</summary>
    public static Func<string?>? Cargar { get; set; }
    /// <summary>Cómo guardar el id para la próxima vez. Opcional.</summary>
    public static Action<string?>? Guardar { get; set; }

    public static string? Id
    {
        get
        {
            lock (Cerrojo)
            {
                if (!cargado)
                {
                    cargado = true;
                    try { id = Normalizar(Cargar?.Invoke()); } catch { id = null; }
                }
                return id;
            }
        }
    }

    public static bool Conocido => !string.IsNullOrEmpty(Id);

    /// <summary>El nodo dijo quién es este aparato: se recuerda (y se persiste) si cambió.</summary>
    public static void Recordar(string? nuevo)
    {
        var limpio = Normalizar(nuevo);
        if (limpio is null) return;
        lock (Cerrojo)
        {
            cargado = true;
            if (limpio == id) return;
            id = limpio;
        }
        try { Guardar?.Invoke(limpio); } catch { }
    }

    public static void Olvidar()
    {
        lock (Cerrojo) { id = null; cargado = true; }
        try { Guardar?.Invoke(null); } catch { }
    }

    /// <summary>Lo que el nodo acepta en la cabecera: hasta 64 caracteres de letras, dígitos, punto, guion, guion bajo o dos puntos.</summary>
    private static string? Normalizar(string? valor)
    {
        var limpio = (valor ?? string.Empty).Trim();
        if (limpio.Length is 0 or > 64) return null;
        return limpio.All(c => char.IsAsciiLetterOrDigit(c) || c is '.' or '-' or '_' or ':') ? limpio : null;
    }
}

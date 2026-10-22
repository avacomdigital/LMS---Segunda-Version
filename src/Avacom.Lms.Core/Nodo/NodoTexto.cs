using System.Globalization;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Nodo;

/// <summary>Un mensaje listo para la pantalla: un título corto, qué pasó y qué hacer.</summary>
public sealed record MensajeDeNodo(string Titulo, string Texto, string? Accion = null)
{
    public string Completo => string.IsNullOrWhiteSpace(Accion) ? Texto : $"{Texto} {Accion}";
}

/// <summary>Cómo suena una línea del estado del equipo: bien, atención o problema. Nunca es una alarma: ningún aviso de plataforma interrumpe una clase (R-01, R-17).</summary>
public enum TonoDelNodo { Bien, Atencion, Problema, Neutro }

/// <summary>
/// TODOS los textos del estado del nodo y de la cola (MOD-015), para que OPS y las pruebas digan lo mismo: cada estado del nodo, cada motivo del modo restringido, cada estado de un
/// consumidor y de un problema, los pendientes, las fechas y los tamaños en español, y cada código de error con su acción. Puro y sin MAUI. Quien lee es el técnico o la administración
/// frente a una pantalla táctil de 86", sin teclado: frases cortas, sin jerga ni códigos, y siempre qué hacer.
/// </summary>
public static class NodoTexto
{
    private static readonly CultureInfo Es = CultureInfo.GetCultureInfo("es-ES");

    // ================================================================================================== fechas, cifras y tamaños

    private static DateTimeOffset Local(long ms, TimeZoneInfo? zona) => TimeZoneInfo.ConvertTime(DateTimeOffset.FromUnixTimeMilliseconds(ms), zona ?? TimeZoneInfo.Local);

    /// <summary>«12 de octubre de 2027 a las 10:42».</summary>
    public static string FechaYHora(long ms, TimeZoneInfo? zona = null)
    {
        var l = Local(ms, zona);
        return $"{l.ToString("d 'de' MMMM 'de' yyyy", Es)} a las {l.ToString("HH:mm", CultureInfo.InvariantCulture)}";
    }

    /// <summary>«12 oct · 10:42» (para una fila).</summary>
    public static string FechaCorta(long ms, TimeZoneInfo? zona = null)
    {
        var l = Local(ms, zona);
        return $"{l.ToString("d MMM", Es).Replace(".", string.Empty)} · {l.ToString("HH:mm", CultureInfo.InvariantCulture)}";
    }

    /// <summary>«1,5 GB», «512 MB», «3 KB», «0 B».</summary>
    public static string Tamano(long bytes)
    {
        if (bytes < 0) bytes = 0;
        if (bytes >= 1L << 30) return $"{(bytes / (double)(1L << 30)).ToString("0.0", Es)} GB";
        if (bytes >= 1L << 20) return $"{Math.Round(bytes / (double)(1L << 20)).ToString("0", Es)} MB";
        if (bytes >= 1L << 10) return $"{Math.Round(bytes / 1024d).ToString("0", Es)} KB";
        return $"{bytes} B";
    }

    /// <summary>«sin pendientes», «1 evento pendiente», «12 eventos pendientes».</summary>
    public static string Pendientes(long n) => n switch { <= 0 => "sin pendientes", 1 => "1 evento pendiente", _ => $"{n.ToString("N0", Es)} eventos pendientes" };

    /// <summary>«sin eventos apartados», «1 evento apartado», «3 eventos apartados».</summary>
    public static string Apartados(long n) => n switch { <= 0 => "sin eventos apartados", 1 => "1 evento apartado", _ => $"{n.ToString("N0", Es)} eventos apartados" };

    /// <summary>«12.345 eventos en la cola».</summary>
    public static string EventosEnCola(long n) => n == 1 ? "1 evento en la cola" : $"{n.ToString("N0", Es)} eventos en la cola";

    // ================================================================================================== el estado del nodo

    /// <summary>El rótulo del chip: «Operativo», «Restringido», «Recuperándose», «Arrancando», «Detenido».</summary>
    public static string Estado(string? estado) => estado switch
    {
        EstadosDelNodo.Operativo => "Operativo",
        EstadosDelNodo.Restringido => "Restringido",
        EstadosDelNodo.EnRecuperacion => "Recuperándose",
        EstadosDelNodo.Arrancando => "Arrancando",
        EstadosDelNodo.Detenido => "Detenido",
        _ => "Sin estado",
    };

    public static TonoDelNodo TonoDeEstado(string? estado) => estado switch
    {
        EstadosDelNodo.Operativo => TonoDelNodo.Bien,
        EstadosDelNodo.Restringido => TonoDelNodo.Problema,
        EstadosDelNodo.EnRecuperacion or EstadosDelNodo.Arrancando => TonoDelNodo.Atencion,
        _ => TonoDelNodo.Neutro,
    };

    /// <summary>Una frase sobre el estado, para debajo del chip.</summary>
    public static string ExplicacionDeEstado(string? estado) => estado switch
    {
        EstadosDelNodo.Operativo => "El nodo atiende con normalidad: la clase, las evaluaciones y el estudio funcionan.",
        EstadosDelNodo.Restringido => "La clase, las evaluaciones y el estudio siguen. Lo que puede esperar (altas, importaciones, exportaciones, reprocesos) espera hasta que la condición se despeje.",
        EstadosDelNodo.EnRecuperacion => "El nodo se está poniendo al día tras un corte. La clase puede seguir; los reportes y las calificaciones derivadas se actualizan en segundo plano.",
        EstadosDelNodo.Arrancando => "El nodo está arrancando sus servicios.",
        EstadosDelNodo.Detenido => "El nodo está detenido.",
        _ => "No se pudo leer el estado del nodo.",
    };

    /// <summary>Cada motivo del modo restringido (Q-N1), con qué hacer.</summary>
    public static string Motivo(string codigo) => codigo switch
    {
        MotivosDeRestriccion.TransaccionNoInmediata => "La base de datos no está configurada en modo de escritor único: el orden de los eventos no está garantizado. Avisa a soporte técnico.",
        MotivosDeRestriccion.DiscoEscaso => "Queda poco espacio en el disco del nodo. Libera espacio o avisa a soporte técnico.",
        MotivosDeRestriccion.BaseDanada => "La comprobación de la base de datos no pasó. Avisa a soporte técnico antes de seguir usando este equipo para exámenes.",
        MotivosDeRestriccion.WalEnorme => "El diario de la base de datos creció demasiado sin volcarse. Reinicia el nodo cuando no haya clase o avisa a soporte técnico.",
        MotivosDeRestriccion.ConsumidorNucleoSuspendido => "Un consumidor principal de la cola quedó suspendido por rezago. Revisa la cola y reprocesa lo apartado.",
        MotivosDeRestriccion.RelojRetrocedido => "La fecha del equipo retrocedió respecto de lo que el aula ya vio. Corrige la fecha o confírmala desde Licencia.",
        _ => $"Condición no reconocida por esta versión de OPS ({codigo}).",
    };

    // ================================================================================================== consumidores y problemas

    public static string EstadoDeConsumidor(string? estado) => estado switch
    {
        EstadosDeConsumidor.AlDia => "Al día",
        EstadosDeConsumidor.Rezagado => "Rezagado",
        EstadosDeConsumidor.Reconstruyendose => "Reconstruyéndose",
        EstadosDeConsumidor.Suspendido => "Suspendido",
        _ => "Sin estado",
    };

    public static TonoDelNodo TonoDeConsumidor(string? estado) => estado switch
    {
        EstadosDeConsumidor.AlDia => TonoDelNodo.Bien,
        EstadosDeConsumidor.Rezagado or EstadosDeConsumidor.Reconstruyendose => TonoDelNodo.Atencion,
        EstadosDeConsumidor.Suspendido => TonoDelNodo.Problema,
        _ => TonoDelNodo.Neutro,
    };

    /// <summary>El nombre con que se muestra un consumidor registrado («libro», «reportes», «busqueda»…).</summary>
    public static string NombreDeConsumidor(string nombre) => nombre switch
    {
        "gradebook" or "libro" => "Libro de calificaciones",
        "reporting" or "reportes" => "Reportes",
        "search" or "busqueda" => "Búsqueda",
        "audit" or "auditoria" => "Bitácora",
        _ => Mayuscula(nombre.Replace('_', ' ')),
    };

    /// <summary>El nombre con que se muestra una fuente (el módulo que publica): «Evaluación», «Aula», «Estudio»…</summary>
    public static string NombreDeFuente(string fuente) => fuente switch
    {
        "evaluacion" => "Evaluación",
        "classroom_engine" or "aula" => "Aula",
        "modo_estudio" or "estudio" => "Estudio",
        "gradebook" or "calificacion" => "Calificaciones",
        "device_manager" or "dispositivo" => "Dispositivos",
        "acceso" or "identidad" => "Acceso",
        "reporting" => "Reportes",
        "search" => "Búsqueda",
        "audit" => "Bitácora",
        "licenciamiento" => "Licencia",
        "nodo" => "Nodo",
        _ => Mayuscula(fuente.Replace('_', ' ')),
    };

    /// <summary>«Evaluación · marca 120 de 128 · 8 eventos pendientes».</summary>
    public static string Fuente(FuenteDeConsumidor f) => $"{NombreDeFuente(f.Fuente)} · marca {f.Marca.ToString("N0", Es)} de {f.UltimaSecuencia.ToString("N0", Es)} · {Pendientes(f.Pendientes)}";

    /// <summary>Lo que espera un reintento: «el evento 42 falló 2 veces; se reintenta a las 10:43».</summary>
    public static string Reintento(ReintentoDeFuente r, TimeZoneInfo? zona = null)
    {
        var veces = r.Intentos == 1 ? "1 vez" : $"{r.Intentos} veces";
        return $"El evento {r.Secuencia.ToString("N0", Es)} falló {veces}; se reintenta a las {Local(r.ProximoEn, zona).ToString("HH:mm:ss", CultureInfo.InvariantCulture)}.";
    }

    /// <summary>
    /// Un módulo ya conectado a la cola única (P-05): «Aula · escribe en la cola única desde el 12 de octubre, 10:43 · su historia anterior (hasta el evento 380) se conserva».
    /// Una <c>ultima_legada</c> en cero es un módulo que se cortó sin historia propia.
    /// </summary>
    public static string Corte(CorteDeModulo c, TimeZoneInfo? zona = null)
    {
        var historia = c.UltimaLegada > 0 ? $"su historia anterior (hasta el evento {c.UltimaLegada.ToString("N0", Es)}) se conserva sólo para leer" : "no tenía historia anterior";
        return $"{NombreDeFuente(c.Modulo)} · escribe en la cola única desde {FechaYHora(c.CortadoEn, zona)} · {historia}";
    }

    public static string EstadoDeProblema(string? estado) => estado switch
    {
        EstadosDeProblema.Apartado => "Apartado",
        EstadosDeProblema.Reprocesado => "Reprocesado",
        EstadosDeProblema.Descartado => "Descartado",
        _ => "Sin estado",
    };

    /// <summary>«Evento 42 de Evaluación (evaluacion.intento_abierto.v1) · apartado tras 5 intentos para Reportes».</summary>
    public static string Problema(ProblemaDeCola p)
    {
        var intentos = p.Intentos == 1 ? "1 intento" : $"{p.Intentos} intentos";
        return $"Evento {p.Secuencia.ToString("N0", Es)} de {NombreDeFuente(p.Fuente)} ({p.Tipo}) · apartado tras {intentos} para {NombreDeConsumidor(p.Consumidor)}";
    }

    /// <summary>El último error de un problema, tal como lo saneó el nodo (sin datos personales), o una frase si no hay.</summary>
    public static string ErrorDeProblema(ProblemaDeCola p) => string.IsNullOrWhiteSpace(p.UltimoError) ? "Sin detalle del error." : p.UltimoError!;

    // ================================================================================================== mensajes de las acciones

    public static readonly MensajeDeNodo Reprocesado = new("Evento reprocesado", "El consumidor volvió a aplicar el evento y quedó asentado en la bitácora.");
    public static readonly MensajeDeNodo Reproducido = new("Consumidor en reconstrucción", "Su marca volvió a cero: reproducirá toda la cola en segundo plano hasta ponerse al día. La clase no se detiene.");

    public static string ConfirmarReproceso(ProblemaDeCola p) => $"¿Reprocesar el evento {p.Secuencia.ToString("N0", Es)} para {NombreDeConsumidor(p.Consumidor)}? Si la causa del fallo ya se corrigió, se aplicará una sola vez.";

    public static string ConfirmarReproduccion(string consumidor) => $"¿Reproducir {NombreDeConsumidor(consumidor)} desde el principio? Volverá a leer toda la cola; mientras tanto lo que muestra puede ir por detrás. La clase no se detiene.";

    /// <summary>Qué decir ante un error del nodo o de la red, por su <c>codigo</c>, con qué hacer. Nunca deja un hueco ni dice «null».</summary>
    public static MensajeDeNodo DeError(ErrorAula? error)
    {
        if (error is null) return new MensajeDeNodo("No se pudo completar", "El nodo no respondió.", "Inténtalo de nuevo en unos segundos.");
        if (error.Estado == 0) return new MensajeDeNodo("Sin conexión con el nodo", "No se pudo hablar con el equipo del aula.", "Revisa la red del aula e inténtalo de nuevo.");
        return error.Codigo switch
        {
            ErroresDelNodo.SinPermiso => new MensajeDeNodo("Sin permiso", "Tu rol no puede hacer esto.",
                "Reprocesar la cola es de la administración; el técnico lo recibe por una escalada temporal (Bitácora › Escalada temporal)."),
            ErroresDelNodo.SesionRequerida => new MensajeDeNodo("Hace falta iniciar sesión", "El nodo exige una sesión para ver su estado.", "Entra con tu usuario e inténtalo de nuevo."),
            ErroresDelNodo.NoEncontrado => new MensajeDeNodo("No existe", "Ese evento apartado ya no está.", "Actualiza la lista."),
            ErroresDelNodo.ConsumidorDesconocido => new MensajeDeNodo("Consumidor desconocido", "Ese consumidor no está registrado en la cola.", "Actualiza la lista."),
            ErroresDelNodo.ConsumidorSinAplicador => new MensajeDeNodo("El consumidor no está en marcha", "No hay quién aplique el evento en el nodo ahora mismo.",
                "Reinicia el nodo cuando no haya clase y vuelve a intentarlo."),
            ErroresDelNodo.ProblemaYaResuelto => new MensajeDeNodo("Ya estaba reprocesado", "Ese evento ya se había reprocesado.", "Actualiza la lista."),
            ErroresDelNodo.ReprocesoFallido => new MensajeDeNodo("Volvió a fallar", "El evento sigue apartado: la causa del fallo no está corregida.",
                "Revisa el error del evento y avisa a soporte técnico si se repite."),
            ErroresDelNodo.DatosInvalidos => new MensajeDeNodo("Petición no válida", string.IsNullOrWhiteSpace(error.Detalle) ? "Los datos enviados no tienen la forma esperada." : error.Detalle, "Actualiza la pantalla e inténtalo de nuevo."),
            ErroresDelNodo.NodoRestringido => new MensajeDeNodo("El nodo está restringido", "Esta operación espera a que la condición se despeje. La clase sigue.", "Mira el estado del equipo."),
            _ => new MensajeDeNodo("No se pudo completar", string.IsNullOrWhiteSpace(error.Detalle) ? "El nodo respondió con un error." : error.Detalle, error.Sugerencia ?? "Inténtalo de nuevo o avisa a soporte técnico."),
        };
    }

    // ================================================================================================== el banner del menú (P-18)

    /// <summary>El texto del banner persistente, sólo para «restringido» y «en recuperación» (lo demás no se anuncia).</summary>
    public static string? Banner(NodoEnSalud? salud)
    {
        if (salud is null) return null;
        return salud.Estado switch
        {
            EstadosDelNodo.Restringido => "El nodo está en modo restringido: la clase sigue; lo que puede esperar, espera.",
            EstadosDelNodo.EnRecuperacion => "El nodo se está recuperando de un corte: la clase puede seguir mientras se pone al día.",
            _ => null,
        };
    }

    /// <summary>Lo único que Student dice si el nodo declara «en recuperación»: sereno, sin cuenta regresiva.</summary>
    public const string RecuperacionParaStudent = "El equipo del aula se está poniendo al día. Lo que hiciste está guardado.";

    private static string Mayuscula(string texto) => string.IsNullOrEmpty(texto) ? texto : char.ToUpper(texto[0], Es) + texto[1..];
}

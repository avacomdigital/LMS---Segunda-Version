using System.ComponentModel;
using System.Text.RegularExpressions;

namespace Avacom.Lms.Core.Reporting;

/// <summary>Por qué no se pudo guardar un reporte en el destino que la persona eligió. Cada uno tiene un código estable (contrato con el backend) y un texto para la pantalla.</summary>
public enum MotivoDeEscritura
{
    /// <summary>La unidad desapareció o dejó de responder a mitad (la memoria se sacó, el disco se desconectó, la carpeta ya no está).</summary>
    MedioRetirado,
    SinEspacio,
    ProtegidoContraEscritura,
    SinPermiso,
    RutaDeRedInalcanzable,
    NombreInvalido,
    BloqueadoPorAntivirus,
    ArchivoEnUso,
    /// <summary>Lo guardado no coincide con el original (tamaño o SHA-256): se descartó para no dejar un reporte dañado con apariencia de bueno.</summary>
    VerificacionFallida,
    Cancelado,
    Otro,
}

/// <summary>
/// Un fallo de escritura listo para mostrar. <see cref="Codigo"/> es snake_case y es el que viaja al backend (auditoría de la exportación): no se cambia. <see cref="Mensaje"/>
/// dice qué pasó y <see cref="Accion"/> qué puede hacer la persona, en el lenguaje de quien está frente a la pantalla: sin códigos de error ni jerga.
/// </summary>
public sealed record FalloDeEscritura(MotivoDeEscritura Motivo, string Codigo, string Mensaje, string Accion);

/// <summary>
/// De una excepción de E/S a un <see cref="FalloDeEscritura"/> que la persona entiende. Las memorias USB reales fallan de formas que .NET reporta casi todas como un
/// <see cref="IOException"/> genérico y la única pista es el código de Windows que lleva dentro (el <c>HResult</c> es 0x8007 + ese código). Este es el único sitio donde se
/// decide qué código significa qué; la lista, para quien tenga que extenderla cuando una unidad real devuelva uno que no está:
/// <list type="bullet">
/// <item>MedioRetirado: 0x02 archivo no hallado (el que se acaba de crear ya no está: el volumen cambió), 0x0F unidad inválida, 0x14 unidad desconocida, 0x15 no está lista,
/// 0x17 error de datos (CRC), 0x1B sector no hallado, 0x1D y 0x1E fallo de escritura y de lectura, 0x1F el dispositivo no funciona, 0x1B1 el dispositivo no existe, 0x3EE el
/// volumen cambió por fuera, 0x458 sin medio, 0x45D error de E/S del dispositivo, 0x467 la operación de disco falló, 0x48F dispositivo no conectado, 0x651 dispositivo retirado.
/// Y dependen de la ruta: 0x03 ruta no hallada, 0x37 el dispositivo ya no está y 0x79 tiempo agotado (en una ruta de red son «red», en las demás «medio retirado»).</item>
/// <item>SinEspacio: 0x27 y 0x70 disco lleno, 0xDF archivo demasiado grande para el sistema de archivos (FAT32 no pasa de 4 GiB), 0x718 cuota agotada.</item>
/// <item>ProtegidoContraEscritura: 0x13.</item>
/// <item>SinPermiso: 0x05 acceso denegado, 0x41 acceso a la red denegado, 0x522 privilegio no concedido, 0x52E usuario o clave incorrectos del recurso compartido.</item>
/// <item>RutaDeRedInalcanzable: 0x33 y 0x35 ruta de red no hallada, 0x36 red ocupada, 0x3B error de red inesperado, 0x40 el nombre de red ya no está, 0x43 nombre de red no
/// hallado, 0x47 el equipo no acepta más conexiones, 0x4B1 conexión recordada sin conectar, 0x4C6 no hay red, 0x4C9 conexión rechazada, 0x4CA conexión abortada, 0x4CD conexión
/// no válida, 0x4CF red inalcanzable, 0x4D0 equipo inalcanzable, 0x4D2 puerto inalcanzable, 0x8CA sin conexión de red.</item>
/// <item>NombreInvalido: 0x6F nombre demasiado largo, 0x7B nombre no válido, 0xA1 ruta mal formada, 0xCE nombre fuera de rango, 0x10B nombre de carpeta no válido.</item>
/// <item>ArchivoEnUso: 0x20 violación de uso compartido, 0x21 violación de bloqueo.</item>
/// <item>BloqueadoPorAntivirus: 0xE1 el archivo contiene un virus, 0xE2 el archivo se eliminó por contener un virus; o un mensaje que hable de virus.</item>
/// <item>Cancelado: <see cref="OperationCanceledException"/> y 0x4C7 operación cancelada por el usuario.</item>
/// </list>
/// Todo lo demás es <see cref="MotivoDeEscritura.Otro"/>: es preferible un «no se pudo guardar» honesto a una causa inventada.
/// </summary>
public static class MotivosDeEscritura
{
    private const int ProfundidadMaxima = 16;      // cuántas excepciones se miran como mucho (cadena de internas): una que se apunte a sí misma no cuelga esto

    // Lo que Windows dice en el texto cuando el código no basta. Se mira SIN lo que va entre comillas (las rutas): «'C:\virus\x'» no es un antivirus.
    private static readonly Regex TextoEntreComillas = new("'[^']*'|\"[^\"]*\"", RegexOptions.CultureInvariant | RegexOptions.Compiled);

    private static readonly Dictionary<MotivoDeEscritura, FalloDeEscritura> Fallos = new()
    {
        [MotivoDeEscritura.MedioRetirado] = Crear(MotivoDeEscritura.MedioRetirado, "medio_retirado",
            "Se retiró la memoria mientras se guardaba.",
            "Vuelve a conectarla y toca Guardar otra vez, o elige otro destino."),
        [MotivoDeEscritura.SinEspacio] = Crear(MotivoDeEscritura.SinEspacio, "sin_espacio",
            "La memoria no tiene espacio suficiente para este archivo.",
            "Libera espacio o elige otro destino. El reporte sigue en pantalla."),
        [MotivoDeEscritura.ProtegidoContraEscritura] = Crear(MotivoDeEscritura.ProtegidoContraEscritura, "protegido_contra_escritura",
            "La memoria está protegida contra escritura.",
            "Quita el seguro de la memoria o elige otro destino."),
        [MotivoDeEscritura.SinPermiso] = Crear(MotivoDeEscritura.SinPermiso, "sin_permiso",
            "No tienes permiso para guardar en esa carpeta.",
            "Elige otra carpeta, por ejemplo Documentos, o pide ayuda a soporte."),
        [MotivoDeEscritura.RutaDeRedInalcanzable] = Crear(MotivoDeEscritura.RutaDeRedInalcanzable, "ruta_de_red_inalcanzable",
            "No se pudo llegar a esa carpeta de red.",
            "Comprueba la conexión del equipo con la red del colegio o elige otro destino."),
        [MotivoDeEscritura.NombreInvalido] = Crear(MotivoDeEscritura.NombreInvalido, "nombre_invalido",
            "El sistema de esa unidad no acepta ese nombre de archivo.",
            "Elige otro destino. El reporte sigue en pantalla."),
        [MotivoDeEscritura.BloqueadoPorAntivirus] = Crear(MotivoDeEscritura.BloqueadoPorAntivirus, "bloqueado_por_antivirus",
            "Un antivirus bloqueó el archivo.",
            "Pide a soporte que permita guardar reportes ahí, o elige otro destino."),
        [MotivoDeEscritura.ArchivoEnUso] = Crear(MotivoDeEscritura.ArchivoEnUso, "archivo_en_uso",
            "Otro programa está usando ese archivo.",
            "Espera unos segundos y toca Guardar otra vez, o elige otro destino."),
        [MotivoDeEscritura.VerificacionFallida] = Crear(MotivoDeEscritura.VerificacionFallida, "verificacion_fallida",
            "El archivo guardado no coincide con el original, así que se descartó.",
            "Prueba otra vez o elige otro destino; si se repite, la memoria puede estar dañada."),
        [MotivoDeEscritura.Cancelado] = Crear(MotivoDeEscritura.Cancelado, "cancelado",
            "Cancelaste el guardado.",
            "No se guardó nada. El reporte sigue en pantalla."),
        [MotivoDeEscritura.Otro] = Crear(MotivoDeEscritura.Otro, "otro",
            "No se pudo guardar el archivo.",
            "Elige otro destino. El reporte sigue en pantalla."),
    };

    private static FalloDeEscritura Crear(MotivoDeEscritura motivo, string codigo, string mensaje, string accion) => new(motivo, codigo, mensaje, accion);

    // ---------------------------------------------------------------------------------------------------- lo que dice cada motivo

    /// <summary>El código estable del motivo («sin_espacio», «medio_retirado»…): el que se manda al backend.</summary>
    public static string Codigo(MotivoDeEscritura motivo) => De(motivo).Codigo;

    /// <summary>El fallo completo de un motivo (código, mensaje y qué hacer). Un valor que no es un motivo conocido es <see cref="MotivoDeEscritura.Otro"/>.</summary>
    public static FalloDeEscritura De(MotivoDeEscritura motivo) => Fallos.TryGetValue(motivo, out var fallo) ? fallo : Fallos[MotivoDeEscritura.Otro];

    // ---------------------------------------------------------------------------------------------------- clasificar

    /// <summary>
    /// El fallo que corresponde a una excepción al escribir en <paramref name="rutaDestino"/> (la carpeta o el archivo; sirve para saber si es una ruta de red). Mira el TIPO
    /// de la excepción y el código de Windows que lleva, la exterior primero y luego sus internas (y las de un <see cref="AggregateException"/>). NO LANZA NUNCA: una excepción
    /// nula, con un <c>Message</c> que falla o con internas que se apuntan a sí mismas también da un fallo (<see cref="MotivoDeEscritura.Otro"/>).
    /// </summary>
    public static FalloDeEscritura Clasificar(Exception ex, string? rutaDestino = null, bool unidadDeRedConocida = false)
    {
        try { return De(Motivo(ex, rutaDestino, unidadDeRedConocida)); }
        catch { return De(MotivoDeEscritura.Otro); }
    }

    // `unidadDeRedConocida`: quien conoce las unidades del sistema dice que la letra («Z:») es una unidad de red mapeada; por el texto de la ruta sólo se reconocen las UNC.
    private static MotivoDeEscritura Motivo(Exception? ex, string? rutaDestino, bool unidadDeRedConocida = false)
    {
        var enRed = unidadDeRedConocida || NombreDeArchivo.EsRutaDeRed(rutaDestino);
        foreach (var e in Recorrer(ex))
            if (ClasificarUna(e, enRed) is { } motivo)
                return motivo;
        return MotivoDeEscritura.Otro;
    }

    /// <summary>La excepción y, en anchura (las más cercanas a la de arriba primero), todas las que lleva dentro, sin repetir ninguna.</summary>
    private static IEnumerable<Exception> Recorrer(Exception? raiz)
    {
        if (raiz is null) yield break;
        var vistas = new HashSet<Exception>(ReferenceEqualityComparer.Instance);
        var pendientes = new Queue<Exception>();
        pendientes.Enqueue(raiz);
        while (pendientes.Count > 0 && vistas.Count < ProfundidadMaxima)
        {
            var actual = pendientes.Dequeue();
            if (!vistas.Add(actual)) continue;
            yield return actual;
            if (actual is AggregateException agregada)
            {
                foreach (var interna in agregada.InnerExceptions) pendientes.Enqueue(interna);
            }
            else if (actual.InnerException is { } otra)
            {
                pendientes.Enqueue(otra);
            }
        }
    }

    /// <summary>El motivo que dice UNA excepción, o null si por sí sola no dice nada (entonces se mira la interna).</summary>
    private static MotivoDeEscritura? ClasificarUna(Exception e, bool enRed)
    {
        var codigo = CodigoDeWindows(e);
        switch (e)
        {
            case OperationCanceledException:
                return MotivoDeEscritura.Cancelado;
            case PathTooLongException:
                return MotivoDeEscritura.NombreInvalido;
            // La carpeta o la unidad ya no está: en una ruta de red es la red; en el resto, que se retiró lo que había (la memoria, el disco).
            case DirectoryNotFoundException or DriveNotFoundException:
                return enRed ? MotivoDeEscritura.RutaDeRedInalcanzable : MotivoDeEscritura.MedioRetirado;
            // Un archivo que se acaba de crear y ya no está: el volumen se fue o cambió.
            case FileNotFoundException:
                return MotivoDeEscritura.MedioRetirado;
            case UnauthorizedAccessException:
                return codigo == 0x13 || IndicaSoloLectura(Mensaje(e)) ? MotivoDeEscritura.ProtegidoContraEscritura : MotivoDeEscritura.SinPermiso;
            case NotSupportedException:
                return MotivoDeEscritura.NombreInvalido;
            case ArgumentException when e is not ArgumentOutOfRangeException:
                return MotivoDeEscritura.NombreInvalido;
            case TimeoutException when enRed:
                return MotivoDeEscritura.RutaDeRedInalcanzable;
        }

        if (codigo is { } c && PorCodigo(c, enRed) is { } porCodigo) return porCodigo;

        // Último recurso, el texto (el de Windows habla de «virus» o de «protegido contra escritura» según el idioma del sistema; con el código basta casi siempre).
        var mensaje = Mensaje(e);
        if (MencionaAntivirus(mensaje)) return MotivoDeEscritura.BloqueadoPorAntivirus;
        if (IndicaSoloLectura(mensaje)) return MotivoDeEscritura.ProtegidoContraEscritura;
        return null;
    }

    private static MotivoDeEscritura? PorCodigo(int codigo, bool enRed) => codigo switch
    {
        0x27 or 0x70 or 0xDF or 0x718 => MotivoDeEscritura.SinEspacio,
        0x13 => MotivoDeEscritura.ProtegidoContraEscritura,
        0x05 or 0x41 or 0x522 or 0x52E => MotivoDeEscritura.SinPermiso,
        0x20 or 0x21 => MotivoDeEscritura.ArchivoEnUso,
        0xE1 or 0xE2 => MotivoDeEscritura.BloqueadoPorAntivirus,
        0x6F or 0x7B or 0xA1 or 0xCE or 0x10B => MotivoDeEscritura.NombreInvalido,
        0x4C7 => MotivoDeEscritura.Cancelado,
        0x33 or 0x35 or 0x36 or 0x3B or 0x40 or 0x43 or 0x47 or 0x4B1 or 0x4C6 or 0x4C9 or 0x4CA or 0x4CD or 0x4CF or 0x4D0 or 0x4D2 or 0x8CA => MotivoDeEscritura.RutaDeRedInalcanzable,
        0x03 or 0x37 or 0x79 => enRed ? MotivoDeEscritura.RutaDeRedInalcanzable : MotivoDeEscritura.MedioRetirado,
        0x02 or 0x0F or 0x14 or 0x15 or 0x17 or 0x1B or 0x1D or 0x1E or 0x1F or 0x1B1 or 0x3EE or 0x458 or 0x45D or 0x467 or 0x48F or 0x651 => MotivoDeEscritura.MedioRetirado,
        _ => null,
    };

    /// <summary>
    /// El código de error de Windows (Win32) que lleva la excepción, o null si no lleva ninguno. .NET lo guarda en el <c>HResult</c> como 0x8007 + el código (<c>HResult &amp; 0xFFFF</c>);
    /// un valor entre 1 y 0xFFFF se toma ya como el código pelado (así se construyen los de las pruebas) y un <see cref="Win32Exception"/> trae el suyo aparte. Los demás
    /// HRESULT (COM, de .NET: 0x80131620) no son un código de Windows y no se interpretan. No lanza.
    /// </summary>
    public static int? CodigoDeWindows(Exception? ex)
    {
        try
        {
            if (ex is null) return null;
            if (ex is Win32Exception win32 && win32.NativeErrorCode != 0) return win32.NativeErrorCode;
            var hr = ex.HResult;
            if ((uint)hr >> 16 == 0x8007) return hr & 0xFFFF;
            if (hr is > 0 and <= 0xFFFF) return hr;
            return null;
        }
        catch { return null; }
    }

    /// <summary>
    /// Lo que se anota en la bitácora de un fallo: el tipo, el código completo y el texto de la excepción y de las que lleva dentro. Para quien da soporte, no para la pantalla
    /// (está en el idioma del sistema). SIN rutas: Windows las pone en sus mensajes, entre comillas o sueltas, y traen el nombre de quien usa el equipo y el de las carpetas; este
    /// registro se entrega al nodo, así que se quitan aquí. No lanza.
    /// </summary>
    public static string Detalle(Exception? ex)
    {
        if (ex is null) return "sin detalle";
        var partes = new List<string>();
        try
        {
            for (var actual = ex; actual is not null && partes.Count < 4; actual = actual.InnerException)
                partes.Add($"{actual.GetType().Name} (0x{unchecked((uint)actual.HResult):X8}): {QuitarRutas(actual.Message)}");
        }
        catch { partes.Add(ex.GetType().Name); }
        return string.Join(" → ", partes);
    }

    // Una ruta entre comillas (simples o dobles), una unidad con su carpeta («C:\algo\otro») o una de red («\\servidor\recurso»). Lo demás del mensaje —qué pasó— se conserva.
    private static readonly Regex RutaEnElTexto = new(@"'[^']*'|""[^""]*""|[A-Za-z]:\\[^\s'""]*|\\\\[^\s'""]+", RegexOptions.CultureInvariant | RegexOptions.Compiled);

    private static string QuitarRutas(string? texto) => RutaEnElTexto.Replace(texto ?? string.Empty, "«ruta»");

    // ---------------------------------------------------------------------------------------------------- por el texto

    private static string Mensaje(Exception e)
    {
        try { return e.Message ?? string.Empty; }
        catch { return string.Empty; }
    }

    private static bool MencionaAntivirus(string mensaje) =>
        Contiene(SinRutas(mensaje), "virus", "malware", "potentially unwanted", "no deseado");

    private static bool IndicaSoloLectura(string mensaje)
    {
        var texto = SinRutas(mensaje);
        return Contiene(texto, "read-only", "read only", "readonly", "write protect", "write-protect", "solo lectura", "sólo lectura", "protección contra escritura")
            || (Contiene(texto, "protegid") && Contiene(texto, "escritura"));
    }

    private static string SinRutas(string mensaje) => TextoEntreComillas.Replace(mensaje, " ");

    private static bool Contiene(string texto, params string[] frases)
    {
        foreach (var frase in frases)
            if (texto.Contains(frase, StringComparison.OrdinalIgnoreCase))
                return true;
        return false;
    }
}

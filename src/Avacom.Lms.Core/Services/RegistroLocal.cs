using System.Collections.Concurrent;
using System.IO.Compression;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace Avacom.Lms.Core.Services;

/// <summary>Nivel de un renglón de log. Los nombres coinciden con los del backend (§2.1 del prompt de MOD-019).</summary>
public enum NivelLog { Debug, Info, Warning, Error, Critical }

/// <summary>Canales de los logs de diagnóstico (lista cerrada, §2.1): qué falló en el equipo, nunca quién hizo qué.</summary>
public static class Canal
{
    public const string Escritura = "escritura";        // disco lleno, IOException, cola o paquete que no se pudo guardar, log que no se pudo escribir
    public const string Comunicacion = "comunicacion";  // HttpRequestException, timeout, 401/403/409/5xx, caída y reintento del WebSocket, link.json, reloj
    public const string Dispositivo = "dispositivo";    // espacio bajo, batería baja, cambio de red, arranque, bloqueo, clave no disponible, WebView
    public const string Aplicacion = "aplicacion";      // excepciones no controladas, estados imposibles, componentes que no se pintan (Win2D)
}

/// <summary>Un renglón de log tal como se escribe en el archivo y como se entrega al nodo (<c>POST /api/logs/clientes/</c>).</summary>
public sealed record RenglonLog(
    [property: JsonPropertyName("ts")] string Ts,
    [property: JsonPropertyName("nivel")] string Nivel,
    [property: JsonPropertyName("canal")] string Canal,
    [property: JsonPropertyName("app")] string App,
    [property: JsonPropertyName("modulo")] string? Modulo,
    [property: JsonPropertyName("evento")] string? Evento,
    [property: JsonPropertyName("ruta")] string? Ruta,
    [property: JsonPropertyName("mensaje")] string Mensaje,
    [property: JsonPropertyName("detalle")] JsonNode? Detalle,
    [property: JsonPropertyName("traza")] string? Traza,
    [property: JsonPropertyName("corr")] string? Corr,
    [property: JsonPropertyName("dispositivo_id")] string? DispositivoId,
    [property: JsonPropertyName("version_app")] string? VersionApp)
{
    [JsonIgnore] public bool EsAdvertenciaOPeor => Nivel is "WARNING" or "ERROR" or "CRITICAL";
}

/// <summary>
/// El sistema de logs en archivos de texto de OPS y Student (§2.4 y §3.6 del prompt de MOD-019): JSON Lines, un archivo por app
/// (<c>{app}-app.log</c> con todo, <c>{app}-errores.log</c> sólo WARNING o superior), rotación por tamaño (2 MB × 5, el mismo criterio que
/// <c>Registro.cs</c> del instalador: nunca llena el disco), canales cerrados, y un filtro de saneamiento que descarta las claves prohibidas
/// (§2.6: ni contraseñas, PIN, tokens, respuestas ni nombres; sólo identificadores, códigos y cifras).
///
/// Es el <b>buffer offline</b> del aparato: funciona sin ninguna red. Los renglones WARNING+ quedan además en una cola en memoria que
/// <see cref="EntregadorDeLogs"/> sube al nodo cuando hay red del aula; si la entrega falla, el archivo local conserva todo, y la red
/// nunca es requisito para diagnosticar un fallo de red.
///
/// Carpeta: <c>AVACOM_LMS_DIR_LOGS</c> si está (pruebas UIA, técnico); si no, <c>%LOCALAPPDATA%\AVACOM\lms\logs</c> en Windows y el
/// directorio privado de la app en Android (allí <c>LocalApplicationData</c> es <c>files/</c>: no expuesto al alumno).
/// El logger NUNCA eleva excepciones al llamador: un fallo al registrar no tumba la app (§2.5).
/// </summary>
public static class RegistroLocal
{
    private static readonly object Cerrojo = new();
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping };
    private static readonly ConcurrentDictionary<string, long> UltimaVez = new();
    private static readonly Queue<RenglonLog> Pendientes = new();

    /// <summary>§2.6: claves que jamás se escriben en un log (se comparan en minúsculas y por «contiene»).</summary>
    public static readonly string[] ClavesProhibidas =
    [
        "secreto", "pin", "token", "password", "contrasena", "contraseña", "clave", "respuesta", "respuestas", "nombre", "nombres",
        "apellido", "apellidos", "dni", "documento", "authorization", "cookie", "identificador", "fecha_nacimiento", "correo", "email", "telefono",
    ];
    /// <summary>Identificadores técnicos que sí se admiten aunque contengan una palabra prohibida.</summary>
    public static readonly string[] ClavesPermitidas =
    [
        "identificador_hw", "usuario_id", "dispositivo_id", "persona_id", "sesion_id", "token_id", "correlacion_id", "correlacion", "corr",
        "nombre_archivo", "archivo", "participante_id", "alumno_id",
    ];
    public const string Redactado = "[redactado]";

    public static long TamanoMaximo { get; set; } = 2 * 1024 * 1024;
    public static int Copias { get; set; } = 5;
    public static int PendientesMaximos { get; set; } = 500;
    /// <summary>Un mismo (canal, evento, mensaje) no se repite en el archivo dentro de esta ventana: un sondeo sin red cada 2 s no lo inunda.</summary>
    public static TimeSpan VentanaDeRepeticion { get; set; } = TimeSpan.FromSeconds(30);

    public static string App { get; private set; } = "cliente";
    public static string? VersionApp { get; set; }
    /// <summary>De dónde sale el <c>dispositivo_id</c> de cada renglón (el id de <c>m09_dispositivo</c> que el nodo dio al registrarse).</summary>
    public static Func<string?>? DispositivoId { get; set; }
    /// <summary>Se dispara tras escribir cada renglón (desde el hilo que escribe). Lo usan las pruebas y la pestaña de diagnóstico.</summary>
    public static event Action<RenglonLog>? Escrito;

    public static void Configurar(string app, string? version = null, Func<string?>? dispositivoId = null)
    {
        App = string.IsNullOrWhiteSpace(app) ? "cliente" : app.Trim().ToLowerInvariant();
        if (version is not null) VersionApp = version;
        if (dispositivoId is not null) DispositivoId = dispositivoId;
    }

    /// <summary>La carpeta de los logs. <c>AVACOM_LMS_DIR_LOGS</c> la sustituye (pruebas, técnico).</summary>
    public static string Carpeta =>
        Environment.GetEnvironmentVariable("AVACOM_LMS_DIR_LOGS") is { Length: > 0 } propia
            ? propia
            : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AVACOM", "lms", "logs");

    public static string RutaApp => Path.Combine(Carpeta, $"{App}-app.log");
    public static string RutaErrores => Path.Combine(Carpeta, $"{App}-errores.log");

    // ------------------------------------------------------------------ escribir

    public static void Depuracion(string canal, string evento, string mensaje, object? detalle = null, string? corr = null, string? modulo = null) =>
        Escribir(NivelLog.Debug, canal, evento, mensaje, detalle, null, corr, modulo);

    public static void Info(string canal, string evento, string mensaje, object? detalle = null, string? corr = null, string? modulo = null) =>
        Escribir(NivelLog.Info, canal, evento, mensaje, detalle, null, corr, modulo);

    public static void Advertencia(string canal, string evento, string mensaje, object? detalle = null, Exception? ex = null, string? corr = null, string? modulo = null) =>
        Escribir(NivelLog.Warning, canal, evento, mensaje, detalle, ex, corr, modulo);

    public static void Error(string canal, string evento, string mensaje, object? detalle = null, Exception? ex = null, string? corr = null, string? modulo = null) =>
        Escribir(NivelLog.Error, canal, evento, mensaje, detalle, ex, corr, modulo);

    /// <summary>Escribe un renglón. Nunca lanza. <paramref name="sinFreno"/> salta la ventana de repetición.</summary>
    public static void Escribir(NivelLog nivel, string canal, string evento, string mensaje, object? detalle = null, Exception? ex = null,
                                string? corr = null, string? modulo = null, string? ruta = null, bool sinFreno = false)
    {
        try
        {
            if (!sinFreno && Repetido(canal, evento, mensaje)) return;
            var renglon = Armar(nivel, canal, evento, mensaje, detalle, ex, corr, modulo, ruta);
            var linea = JsonSerializer.Serialize(renglon, Json);
            lock (Cerrojo)
            {
                Anexar(RutaApp, linea);
                if (renglon.EsAdvertenciaOPeor)
                {
                    Anexar(RutaErrores, linea);
                    Pendientes.Enqueue(renglon);
                    while (Pendientes.Count > PendientesMaximos) Pendientes.Dequeue();
                }
            }
            try { Escrito?.Invoke(renglon); } catch { }
        }
        catch
        {
            // Si no se puede escribir el log, no hay nada más que hacer: no se relanza (y no se puede registrar el fallo del propio log).
        }
    }

    private static RenglonLog Armar(NivelLog nivel, string canal, string evento, string mensaje, object? detalle, Exception? ex, string? corr, string? modulo, string? ruta)
    {
        var canalFinal = canal is Canal.Escritura or Canal.Comunicacion or Canal.Dispositivo or Canal.Aplicacion ? canal : Canal.Aplicacion;
        var rutaFinal = ruta ?? (nivel >= NivelLog.Error ? "bad" : nivel == NivelLog.Warning ? "sad" : null);
        string? dispositivo = null;
        try { dispositivo = DispositivoId?.Invoke(); } catch { }
        return new RenglonLog(
            DateTimeOffset.Now.ToString("yyyy-MM-dd'T'HH:mm:ss.fffzzz"),
            NombreDe(nivel), canalFinal, App, modulo ?? App, evento, rutaFinal,
            Recortar(mensaje, 2000),
            Sanear(detalle),
            ex is null ? null : Recortar(ex.ToString(), 8000),
            corr, dispositivo, VersionApp);
    }

    public static string NombreDe(NivelLog nivel) => nivel switch
    {
        NivelLog.Debug => "DEBUG",
        NivelLog.Info => "INFO",
        NivelLog.Warning => "WARNING",
        NivelLog.Error => "ERROR",
        _ => "CRITICAL",
    };

    private static bool Repetido(string canal, string evento, string mensaje)
    {
        if (VentanaDeRepeticion <= TimeSpan.Zero) return false;
        var clave = $"{canal}|{evento}|{mensaje}";
        var ahora = Environment.TickCount64;
        var ventana = (long)VentanaDeRepeticion.TotalMilliseconds;
        var repetido = false;
        UltimaVez.AddOrUpdate(clave, ahora, (_, anterior) =>
        {
            if (ahora - anterior < ventana) { repetido = true; return anterior; }
            return ahora;
        });
        if (UltimaVez.Count > 2000) UltimaVez.Clear();
        return repetido;
    }

    private static string Recortar(string texto, int maximo) => texto.Length <= maximo ? texto : texto[..maximo] + "…";

    private static void Anexar(string ruta, string linea)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(ruta)!);
        Rotar(ruta);
        File.AppendAllText(ruta, linea + "\n", new UTF8Encoding(false));
    }

    /// <summary>Rotación por tamaño: <c>x.log</c> → <c>x.log.1</c> → … → <c>x.log.5</c>; la más vieja se borra. Los logs no son evidencia.</summary>
    private static void Rotar(string ruta)
    {
        try
        {
            var info = new FileInfo(ruta);
            if (!info.Exists || info.Length < TamanoMaximo) return;
            var ultima = $"{ruta}.{Copias}";
            if (File.Exists(ultima)) File.Delete(ultima);
            for (var i = Copias - 1; i >= 1; i--)
            {
                var de = $"{ruta}.{i}";
                if (File.Exists(de)) File.Move(de, $"{ruta}.{i + 1}", overwrite: true);
            }
            File.Move(ruta, $"{ruta}.1", overwrite: true);
        }
        catch { /* si no se puede rotar, se sigue escribiendo en el mismo archivo */ }
    }

    // ------------------------------------------------------------------ saneamiento

    /// <summary>Convierte <paramref name="detalle"/> a JSON y redacta toda clave prohibida en cualquier nivel (§2.6).</summary>
    public static JsonNode? Sanear(object? detalle)
    {
        if (detalle is null) return null;
        try
        {
            var nodo = detalle is JsonNode n ? n.DeepClone() : JsonSerializer.SerializeToNode(detalle, Json);
            return Limpiar(nodo, 0);
        }
        catch
        {
            return JsonValue.Create(Redactado);
        }
    }

    private static JsonNode? Limpiar(JsonNode? nodo, int profundidad)
    {
        if (nodo is null) return null;
        if (profundidad > 6) return JsonValue.Create(Redactado);
        switch (nodo)
        {
            case JsonObject objeto:
                var limpio = new JsonObject();
                foreach (var (clave, valor) in objeto)
                    limpio[clave] = Prohibida(clave) ? JsonValue.Create(Redactado) : Limpiar(valor, profundidad + 1);
                return limpio;
            case JsonArray lista:
                var salida = new JsonArray();
                foreach (var v in lista) salida.Add(Limpiar(v, profundidad + 1));
                return salida;
            default:
                return nodo.DeepClone();
        }
    }

    public static bool Prohibida(string clave)
    {
        var baja = clave.ToLowerInvariant();
        if (ClavesPermitidas.Contains(baja)) return false;
        return ClavesProhibidas.Any(baja.Contains);
    }

    // ------------------------------------------------------------------ pendientes (entrega al nodo)

    public static int CuentaPendientes { get { lock (Cerrojo) return Pendientes.Count; } }

    /// <summary>Saca hasta <paramref name="maximo"/> renglones WARNING+ para entregarlos al nodo. Si la entrega falla, <see cref="Devolver"/>.</summary>
    public static IReadOnlyList<RenglonLog> TomarPendientes(int maximo = 200)
    {
        lock (Cerrojo)
        {
            var salida = new List<RenglonLog>();
            while (salida.Count < maximo && Pendientes.Count > 0) salida.Add(Pendientes.Dequeue());
            return salida;
        }
    }

    public static void Devolver(IEnumerable<RenglonLog> renglones)
    {
        lock (Cerrojo)
        {
            var actuales = Pendientes.ToArray();
            Pendientes.Clear();
            foreach (var r in renglones) Pendientes.Enqueue(r);
            foreach (var r in actuales) Pendientes.Enqueue(r);
            while (Pendientes.Count > PendientesMaximos) Pendientes.Dequeue();
        }
    }

    /// <summary>Vacía la cola y la ventana de repetición (pruebas).</summary>
    public static void Reiniciar()
    {
        lock (Cerrojo) Pendientes.Clear();
        UltimaVez.Clear();
    }

    // ------------------------------------------------------------------ leer y exportar

    /// <summary>Las últimas líneas del archivo (<c>app</c> o <c>errores</c>), más nuevas al final, para la pantalla de diagnóstico.</summary>
    public static IReadOnlyList<RenglonLog> Leer(bool soloErrores = false, int ultimos = 200)
    {
        var ruta = soloErrores ? RutaErrores : RutaApp;
        var salida = new List<RenglonLog>();
        try
        {
            lock (Cerrojo)
            {
                if (!File.Exists(ruta)) return salida;
                foreach (var linea in File.ReadLines(ruta, Encoding.UTF8))
                {
                    if (string.IsNullOrWhiteSpace(linea)) continue;
                    try { if (JsonSerializer.Deserialize<RenglonLog>(linea, Json) is { } r) salida.Add(r); } catch (JsonException) { }
                }
            }
        }
        catch { }
        return salida.Count <= ultimos ? salida : salida.GetRange(salida.Count - ultimos, ultimos);
    }

    /// <summary>
    /// «Exportar diagnóstico» (§3.6): un ZIP con los logs del aparato (todas las copias rotadas), <c>diagnostico.json</c> (app, versión,
    /// plataforma, aparato, servidor y lo que <paramref name="info"/> aporte, saneado) y el registro viejo de fallos si existe. Devuelve la ruta.
    /// </summary>
    public static string ExportarDiagnostico(string rutaZip, object? info = null)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(rutaZip)!);
        if (File.Exists(rutaZip)) File.Delete(rutaZip);
        using var zip = ZipFile.Open(rutaZip, ZipArchiveMode.Create);
        var cabecera = new JsonObject
        {
            ["app"] = App, ["version_app"] = VersionApp, ["exportado_en"] = DateTimeOffset.Now.ToString("O"),
            ["dispositivo_id"] = DispositivoId?.Invoke(), ["sistema"] = Environment.OSVersion.ToString(), ["maquina"] = Environment.MachineName,
            ["pendientes_de_entrega"] = CuentaPendientes, ["carpeta_logs"] = Carpeta,
        };
        if (Sanear(info) is JsonObject extra)
            foreach (var (clave, valor) in extra) cabecera[clave] = valor?.DeepClone();
        var entrada = zip.CreateEntry("diagnostico.json");
        using (var escritor = new StreamWriter(entrada.Open(), new UTF8Encoding(false)))
            escritor.Write(cabecera.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
        lock (Cerrojo)
        {
            if (Directory.Exists(Carpeta))
                foreach (var archivo in Directory.EnumerateFiles(Carpeta).Where(a => Path.GetFileName(a).Contains(".log", StringComparison.OrdinalIgnoreCase)))
                    zip.CreateEntryFromFile(archivo, "logs/" + Path.GetFileName(archivo));
            var legado = RegistroDeFallos.Ruta(App);
            if (File.Exists(legado)) zip.CreateEntryFromFile(legado, "logs/" + Path.GetFileName(legado));
        }
        return rutaZip;
    }
}

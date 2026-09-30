using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>Un archivo de un paquete de prueba: lo que el nodo falso sirve y lo que el manifiesto dice de él.</summary>
internal sealed record ArchivoDePrueba(string MediaRef, byte[] Datos, string Mime = "image/png")
{
    public string Sha256 => Convert.ToHexStringLower(SHA256.HashData(Datos));
}

/// <summary>Lo que comparten las pruebas del modo de estudio: datos, manifiestos con huella válida, almacenes en carpetas temporales.</summary>
internal static class EstudioAyudas
{
    public const string Dispositivo = "student-TAB07";
    public const string Alumno = "ana-perez";
    public const string Asignacion = "asig-1";

    /// <summary>Bytes repetibles (no comprimibles) de la longitud pedida.</summary>
    public static byte[] Datos(int longitud, int semilla = 1)
    {
        var datos = new byte[longitud];
        new Random(semilla).NextBytes(datos);
        return datos;
    }

    public static string Sha256(byte[] datos) => Convert.ToHexStringLower(SHA256.HashData(datos));

    public static AlmacenEstudio Almacen(string carpeta, IProveedorDeClave? proveedor = null, Func<long>? reloj = null, Func<long?>? espacioLibre = null) =>
        new(Path.Combine(carpeta, "almacen"), proveedor ?? new ProveedorDeClaveEnMemoria(), reloj ?? (() => 1_000), espacioLibre ?? (() => long.MaxValue));

    /// <summary>El manifiesto de un paquete tal como lo entregaría el nodo: con su lección sin claves, sus archivos y la huella del JSON canónico.</summary>
    public static string ManifiestoCrudo(string paqueteId, string asignacionId, IEnumerable<ArchivoDePrueba> archivos, long? vigenteHasta = 4_000_000_000_000,
                                         bool huellaMala = false, IEnumerable<string>? noIncluidos = null)
    {
        var lista = new JsonArray();
        foreach (var a in archivos)
            lista.Add(new JsonObject { ["media_ref"] = a.MediaRef, ["clase"] = "image", ["mime"] = a.Mime, ["bytes"] = a.Datos.Length, ["sha256"] = a.Sha256 });
        var fuera = new JsonArray();
        foreach (var media in noIncluidos ?? []) fuera.Add(new JsonObject { ["media_ref"] = media, ["motivo"] = "simulacion" });
        var raiz = new JsonObject
        {
            ["paquete_id"] = paqueteId,
            ["asignacion"] = new JsonObject { ["id"] = asignacionId, ["titulo"] = "Área y volumen con lenguaje algebraico" },
            ["curso"] = new JsonObject { ["fuente"] = "biblioteca", ["curso_ref"] = "curso-1", ["version"] = "1.0.0", ["titulo"] = "Matemáticas", ["lecciones"] = 1, ["objetos"] = 3 },
            ["leccion_ref"] = "l1",
            ["vigente_hasta"] = vigenteHasta,
            ["generado_en"] = 1_759_000_000_000,
            ["leccion"] = new JsonObject { ["leccion_ref"] = "l1", ["titulo"] = "Los tres estados · ñandú", ["objetos"] = new JsonArray() },
            ["archivos"] = lista,
            ["no_incluidos"] = fuera,
        };
        using var documento = JsonDocument.Parse(raiz.ToJsonString());
        raiz["huella"] = huellaMala ? new string('0', 64) : JsonCanonico.Sha256(documento.RootElement);
        return raiz.ToJsonString();
    }

    public static PaqueteEstudio Paquete(string id, string asignacionId, IReadOnlyList<ArchivoDePrueba> archivos, long? vigenteHasta = 4_000_000_000_000, string estado = "solicitado") =>
        new(id, asignacionId, estado, null, "1.0.0", archivos.Sum(a => (long)a.Datos.Length), "huella-provisional", vigenteHasta, 1, null,
            archivos.Select(a => new ArchivoPaquete(a.MediaRef, "image", a.Mime, a.Datos.Length, a.Sha256)).ToList(), [], 5);

    /// <summary>Deja un paquete completo y disponible en el almacén, escrito por la misma vía que usa el descargador.</summary>
    public static void InstalarPaquete(AlmacenEstudio almacen, string alumnoId, string asignacionId, IReadOnlyList<ArchivoDePrueba> archivos, long? vigenteHasta = 4_000_000_000_000)
    {
        var paquete = Paquete("paq-" + asignacionId, asignacionId, archivos, vigenteHasta);
        almacen.RegistrarPaquete(alumnoId, paquete);
        var crudo = ManifiestoCrudo(paquete.Id, asignacionId, archivos, vigenteHasta);
        almacen.GuardarManifiesto(alumnoId, asignacionId, crudo, JsonSerializer.Deserialize<ManifiestoPaquete>(crudo, Ayudas.Web)!);
        foreach (var a in archivos)
        {
            using (var escritor = almacen.AbrirEscritura(alumnoId, asignacionId, a.MediaRef))
            {
                escritor.Escribir(a.Datos);
                escritor.Cerrar();
            }
            almacen.CompletarArchivo(alumnoId, asignacionId, a.MediaRef);
        }
        almacen.MarcarDisponible(alumnoId, asignacionId);
    }

    public static string TextoDe(byte[] bytes) => Encoding.UTF8.GetString(bytes);

    /// <summary>Todo el contenido en claro de un flujo.</summary>
    public static byte[] LeerTodo(Stream flujo)
    {
        using var memoria = new MemoryStream();
        flujo.CopyTo(memoria);
        return memoria.ToArray();
    }

    /// <summary>Cuenta cuántas veces aparece <paramref name="aguja"/> en <paramref name="pajar"/> (para probar que no queda texto en claro en el disco).</summary>
    public static bool Contiene(byte[] pajar, byte[] aguja) => pajar.AsSpan().IndexOf(aguja) >= 0;

    /// <summary>Todos los archivos que hay bajo una carpeta.</summary>
    public static IEnumerable<string> Archivos(string carpeta) =>
        Directory.Exists(carpeta) ? Directory.EnumerateFiles(carpeta, "*", SearchOption.AllDirectories) : [];
}

/// <summary>
/// Un flujo de lectura que se comporta como una descarga de red: entrega por partes, obedece la cancelación y, si se le pide, se corta a
/// mitad (<see cref="IOException"/>, como un corte de Wi-Fi) o cancela a mitad (una pausa del alumno).
/// </summary>
internal sealed class FlujoDePrueba(byte[] datos, int? cortarEn = null, Action? alCortar = null, int? colgarEn = null, TimeSpan? retardoPorTrozo = null) : Stream
{
    private int posicion;

    public override bool CanRead => true;
    public override bool CanSeek => false;
    public override bool CanWrite => false;
    public override long Length => throw new NotSupportedException();
    public override long Position { get => posicion; set => throw new NotSupportedException(); }

    public override async ValueTask<int> ReadAsync(Memory<byte> destino, CancellationToken ct = default)
    {
        await Task.Yield();
        if (retardoPorTrozo is { } retardo) await Task.Delay(retardo, ct);                // una red lenta: cada trozo tarda
        ct.ThrowIfCancellationRequested();
        var corte = cortarEn is { } c && c < datos.Length ? c : datos.Length;
        var cuelga = colgarEn is { } g && g < datos.Length ? g : datos.Length;
        var tope = Math.Min(corte, cuelga);
        if (posicion >= tope)
        {
            if (cuelga <= corte && cuelga < datos.Length)
            {
                // La red se fue sin avisar: no llega nada, y tampoco se cierra. Sólo la cancelación (o el tiempo de espera de quien lee) lo saca de aquí.
                await Task.Delay(Timeout.Infinite, ct);
            }
            if (corte < datos.Length)
            {
                alCortar?.Invoke();
                ct.ThrowIfCancellationRequested();
                throw new IOException("Se cortó la conexión de prueba.");
            }
            return 0;
        }
        var n = Math.Min(Math.Min(destino.Length, 16 * 1024), tope - posicion);
        datos.AsMemory(posicion, n).CopyTo(destino);
        posicion += n;
        return n;
    }

    public override Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken ct) => ReadAsync(buffer.AsMemory(offset, count), ct).AsTask();
    public override int Read(byte[] buffer, int offset, int count) => ReadAsync(buffer.AsMemory(offset, count)).AsTask().GetAwaiter().GetResult();
    public override void Flush() { }
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
}

/// <summary>
/// El nodo del aula, de mentira, en lo que toca a un paquete de estudio: solicitar, manifiesto, archivos con <c>Range</c> y confirmar. Se usa como
/// <see cref="HttpMessageHandler"/> de un <see cref="EstudioApi"/> real, así las pruebas pasan por el streaming y los errores del cliente de verdad.
/// Cada bandera reproduce una cosa que puede salir mal.
/// </summary>
internal sealed class NodoDePaquete
{
    public string PaqueteId { get; set; } = "paq-1";
    public string AsignacionId { get; set; } = EstudioAyudas.Asignacion;
    public List<ArchivoDePrueba> Archivos { get; } = [];
    public List<string> NoIncluidos { get; } = [];
    public long? VigenteHasta { get; set; } = 4_000_000_000_000;

    /// <summary>403 <c>descarga_denegada</c> al solicitar (aparato compartido).</summary>
    public bool Denegar { get; set; }
    /// <summary>410 <c>paquete_vencido</c> al pedir el manifiesto.</summary>
    public bool ManifiestoVencido { get; set; }
    public bool HuellaMala { get; set; }
    /// <summary>El nodo ignora <c>Range</c> y responde 200 con el archivo entero.</summary>
    public bool IgnorarRange { get; set; }
    /// <summary>Todo falla con un error de red.</summary>
    public bool SinRed { get; set; }
    /// <summary>Código con que responde <c>confirmar</c> (409 <c>huella_invalida</c>); nulo = confirma.</summary>
    public string? ErrorAlConfirmar { get; set; }
    /// <summary>Bytes distintos a los del manifiesto para un medio (el sha256 del manifiesto no coincide).</summary>
    public Dictionary<string, byte[]> Corrompidos { get; } = [];
    /// <summary>Para un medio: corta la PRIMERA respuesta después de esa cantidad de bytes (un corte de red que después se arregla).</summary>
    public Dictionary<string, int> CortarEn { get; } = [];
    /// <summary>Lo mismo pero cancela el token del llamador al llegar al corte (el alumno pulsa «pausar»).</summary>
    public Dictionary<string, (int Bytes, Action Cancelar)> PausarEn { get; } = [];
    /// <summary>Para un medio: la PRIMERA respuesta se queda callada, sin cerrar, después de esa cantidad de bytes (un Wi-Fi que se va sin avisar).</summary>
    public Dictionary<string, int> ColgarEn { get; } = [];
    /// <summary>Cuánto tarda cada trozo de 16 KiB de un archivo (una red lenta); sirve para probar la velocidad y el tiempo restante.</summary>
    public TimeSpan? RetardoPorTrozo { get; set; }

    public List<string> Peticiones { get; } = [];
    public string? CuerpoConfirmar { get; private set; }
    public int Solicitudes => Peticiones.Count(p => p == "POST /api/modo-estudio/paquetes/");
    public List<string> PeticionesDeArchivos(string? mediaRef = null) =>
        [.. Peticiones.Where(p => p.Contains("/archivos/") && (mediaRef is null || p.Contains("/archivos/" + mediaRef + "/")))];

    public HttpClient Cliente() => new(new ManejadorFalso(ResponderAsync));

    public EstudioApi Api() => new(Cliente(), new Uri("http://192.168.0.55:8000/"));

    public string Manifiesto() => EstudioAyudas.ManifiestoCrudo(PaqueteId, AsignacionId, Archivos, VigenteHasta, HuellaMala, NoIncluidos);

    private PaqueteEstudio Paquete(string estado) => EstudioAyudas.Paquete(PaqueteId, AsignacionId, Archivos, VigenteHasta, estado) with { Huella = JsonHuella() };

    private string JsonHuella()
    {
        using var documento = JsonDocument.Parse(Manifiesto());
        return documento.RootElement.GetProperty("huella").GetString()!;
    }

    private static HttpResponseMessage Error(HttpStatusCode estado, string codigo, string detalle = "no") =>
        Ayudas.Respuesta(estado, JsonSerializer.Serialize(new { detail = detalle, codigo }));

    private async Task<HttpResponseMessage> ResponderAsync(HttpRequestMessage req, CancellationToken ct)
    {
        var peticion = $"{req.Method} {req.RequestUri!.PathAndQuery}" + (req.Headers.Range is { } rango ? $" [{rango}]" : "");
        lock (Peticiones) Peticiones.Add(peticion);
        if (SinRed) throw new HttpRequestException("Sin ruta al aula.");
        var ruta = req.RequestUri.AbsolutePath;
        var prefijo = "/api/modo-estudio/paquetes/";
        if (!ruta.StartsWith(prefijo, StringComparison.Ordinal)) return Error(HttpStatusCode.NotFound, "no_encontrado");
        var resto = ruta[prefijo.Length..].Trim('/');

        if (req.Method == HttpMethod.Post && resto.Length == 0)
        {
            if (Denegar)
                return Ayudas.Respuesta(HttpStatusCode.Forbidden, """{"detail":"Esta tableta es compartida.","codigo":"descarga_denegada","paquete":{"estado":"denegado","motivo":"dispositivo_compartido"},"mensaje":"Pídele a tu profesor una tableta asignada."}""");
            return Ayudas.Respuesta(HttpStatusCode.Created, JsonSerializer.Serialize(new { paquete = Paquete("solicitado") }));
        }

        var partes = resto.Split('/');
        if (partes.Length < 2 || partes[0] != PaqueteId) return Error(HttpStatusCode.NotFound, "no_encontrado");
        switch (partes[1])
        {
            case "manifiesto" when req.Method == HttpMethod.Get:
                return ManifiestoVencido ? Error(HttpStatusCode.Gone, "paquete_vencido", "El paquete venció.") : Ayudas.Respuesta(HttpStatusCode.OK, Manifiesto());

            case "confirmar" when req.Method == HttpMethod.Post:
                CuerpoConfirmar = await req.Content!.ReadAsStringAsync(ct);
                return ErrorAlConfirmar is { } codigo
                    ? Error(HttpStatusCode.Conflict, codigo)
                    : Ayudas.Respuesta(HttpStatusCode.OK, JsonSerializer.Serialize(new { paquete = Paquete("disponible") with { DisponibleEn = 7 } }));

            case "archivos" when req.Method == HttpMethod.Get && partes.Length >= 3:
                return Archivo(req, Uri.UnescapeDataString(partes[2]), ct);
        }
        return Error(HttpStatusCode.NotFound, "no_encontrado");
    }

    private HttpResponseMessage Archivo(HttpRequestMessage req, string mediaRef, CancellationToken ct)
    {
        var archivo = Archivos.FirstOrDefault(a => a.MediaRef == mediaRef);
        if (archivo is null) return Error(HttpStatusCode.NotFound, "no_encontrado");
        var contenido = Corrompidos.GetValueOrDefault(mediaRef) ?? archivo.Datos;
        var desde = IgnorarRange ? 0 : req.Headers.Range?.Ranges.FirstOrDefault()?.From ?? 0;
        if (desde >= contenido.Length && contenido.Length > 0) return Error(HttpStatusCode.RequestedRangeNotSatisfiable, "rango_invalido");
        var segmento = contenido.AsMemory((int)desde).ToArray();
        int? corte = null;
        int? cuelga = null;
        Action? alCortar = null;
        if (CortarEn.Remove(mediaRef, out var bytes)) corte = bytes;
        else if (PausarEn.Remove(mediaRef, out var pausa)) { corte = pausa.Bytes; alCortar = pausa.Cancelar; }
        else if (ColgarEn.Remove(mediaRef, out var silencio)) cuelga = silencio;
        var conRango = req.Headers.Range is not null && !IgnorarRange;
        var respuesta = new HttpResponseMessage(conRango ? HttpStatusCode.PartialContent : HttpStatusCode.OK) { Content = new StreamContent(new FlujoDePrueba(segmento, corte, alCortar, cuelga, RetardoPorTrozo)) };
        respuesta.Content.Headers.ContentType = new MediaTypeHeaderValue(archivo.Mime);
        respuesta.Content.Headers.ContentLength = segmento.Length;
        if (conRango) respuesta.Content.Headers.ContentRange = new ContentRangeHeaderValue(desde, contenido.Length - 1, contenido.Length);
        respuesta.Headers.ETag = new EntityTagHeaderValue($"\"{archivo.Sha256}\"");
        return respuesta;
    }
}

/// <summary>Un <see cref="IEstudioApi"/> de mentira: sólo responde lo que la prueba le enseña; lo demás no se debería llamar.</summary>
internal sealed class EstudioApiFalsa : IEstudioApi
{
    public Uri BaseUri { get; } = new("http://192.168.0.55:8000/");
    public string? UltimoMotivo { get; set; }
    public ErrorAula? UltimoError { get; set; }
    public Uri Absoluta(string rutaRelativa) => new(BaseUri, rutaRelativa.TrimStart('/'));

    /// <summary>Lo que se hace con cada envío de sincronización: (dispositivo, emisor, eventos, alumno).</summary>
    public Func<string, string, IReadOnlyList<EventoEstudio>, string?, CancellationToken, Task<AcuseSync?>> Sincronizar { get; set; } =
        (_, _, _, _, _) => Task.FromResult<AcuseSync?>(null);

    public Task<AcuseSync?> SincronizarAsync(string dispositivo, string emisorId, IReadOnlyList<EventoEstudio> eventos, string? alumnoId = null, CancellationToken ct = default) =>
        Sincronizar(dispositivo, emisorId, eventos, alumnoId, ct);

    public Task<EstadoEstudio?> EstadoAsync(string dispositivo, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<EstudiantesEstudio?> EstudiantesAsync(string dispositivo, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<SesionEstudio?> AbrirSesionAsync(string dispositivo, string? nombre, string? plataforma, string? versionApp, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<bool> CerrarSesionAsync(string dispositivo, int colaPendiente, bool limpiezaCompleta, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<bool> LimpiezaReintentadaAsync(string dispositivo, string resultado, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<AsignacionesEstudio?> AsignacionesAsync(string dispositivo, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<AsignacionAlumno?> AsignacionAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<LeccionEstudio?> LeccionAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<ProgresoEstudio?> ProgresoAsync(string dispositivo, string asignacionId, IReadOnlyList<string> bloquesVistos, string? bloqueActual, int? posicionSeg, long? capturadoEn = null, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<CompletadaEstudio?> CompletarAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<PracticaAbierta?> PracticaAsync(string dispositivo, string asignacionId, string? objetoRef = null, bool nueva = false, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<AcusePractica?> ResponderAsync(string dispositivo, string practicaId, IReadOnlyList<RespuestaPractica> respuestas, bool terminar = false, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<AcusePractica?> TerminarPracticaAsync(string dispositivo, string practicaId, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<PaqueteEstudio?> SolicitarPaqueteAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<ListaPaquetes?> PaquetesAsync(string dispositivo, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<PaqueteEstudio?> PaqueteAsync(string dispositivo, string paqueteId, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<ManifiestoPaquete?> ManifiestoAsync(string dispositivo, string paqueteId, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<string?> ManifiestoCrudoAsync(string dispositivo, string paqueteId, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<HttpResponseMessage?> ArchivoAsync(string dispositivo, string paqueteId, string mediaRef, long? desdeByte = null, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<PaqueteEstudio?> ConfirmarPaqueteAsync(string dispositivo, string paqueteId, string huella, long bytes, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<bool> RetirarPaqueteAsync(string dispositivo, string paqueteId, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<EstadoSync?> EstadoSyncAsync(string dispositivo, string emisorId, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<GruposDocente?> GruposAsync(string actor, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<ListaAsignacionesDocente?> AsignacionesDocenteAsync(string actor, string? grupoId = null, string? estado = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<AsignacionDocente?> CrearAsignacionAsync(string actor, string? actorRotulo, NuevaAsignacion nueva, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<AsignacionDocente?> AsignacionDocenteAsync(string actor, string asignacionId, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<AsignacionDocente?> CambiarAsignacionAsync(string actor, string asignacionId, CambiosAsignacion cambios, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<AsignacionDocente?> CerrarAsignacionAsync(string actor, string asignacionId, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<bool> DecidirAsync(string actor, string asignacionId, string alumnoId, long secuencia, string? emisorId, string decision, CancellationToken ct = default) => throw new NotSupportedException();
}

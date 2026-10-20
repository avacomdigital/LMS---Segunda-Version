using System.Text.Json;
using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Ops.Licencia;
using Avacom.Lms.Ops.Reportes;

namespace Avacom.Lms.Ops.Tests;

/// <summary>Las respuestas y los archivos REALES del backend (MOD-018) que capturó Core, vinculados a esta salida.</summary>
internal static class FixturesDeLicencia
{
    private static readonly JsonSerializerOptions Web = new(JsonSerializerDefaults.Web);

    public static string Ruta(string archivo) => Path.Combine(AppContext.BaseDirectory, "Fixtures", "licencia", archivo);

    public static T Json<T>(string nombre) => JsonSerializer.Deserialize<T>(File.ReadAllText(Ruta(nombre + ".json")), Web)!;

    public static EstadoLicencia Estado(string nombre) => Json<EstadoLicencia>(nombre);

    public static byte[] Bytes(string archivo) => File.ReadAllBytes(Ruta(archivo));

    public static ResultadoDeLiberacion Liberacion() => new(Json<LiberacionDeLicencia>("liberar"), Estado("liberar"));

    public static ErrorAula Error(int estado, string fixture) =>
        new(estado, Json<JsonElement>(fixture).TryGetProperty("codigo", out var c) ? c.GetString() : null, Json<JsonElement>(fixture).GetProperty("detail").GetString()!, null, Json<JsonElement>(fixture));

    public static readonly ErrorAula SinConexion = new(0, "sin_conexion", "No hay conexión con el aula.", null, null);
}

/// <summary>
/// Un nodo falso para los flujos de OPS: cada acción devuelve lo que la prueba le diga (por omisión, la respuesta real capturada) y anota cuántas veces se llamó. Con <see cref="Freno"/>,
/// las llamadas esperan a que la prueba lo suelte: así se comprueba que un segundo toque no manda una segunda petición.
/// </summary>
internal sealed class ApiDeLicenciaFalsa : ILicenciaApi
{
    public string? UltimoMotivo { get; private set; }
    public ErrorAula? UltimoError { get; private set; }
    public List<string> Llamadas { get; } = [];
    public List<byte[]> Enviados { get; } = [];
    public TaskCompletionSource? Freno { get; set; }

    public Func<SolicitudDeLicencia?> Solicitud { get; set; } = () => FixturesDeLicencia.Json<SolicitudDeLicencia>("solicitud");
    public Func<CopiaDeLicencia?> Copia { get; set; } = () => FixturesDeLicencia.Json<CopiaDeLicencia>("copia");
    public Func<byte[], EstadoLicencia?> Activar { get; set; } = _ => FixturesDeLicencia.Estado("activar");
    public Func<byte[], EstadoLicencia?> Renovar { get; set; } = _ => FixturesDeLicencia.Estado("renovar");
    public Func<ResultadoDeLiberacion?> Liberar { get; set; } = FixturesDeLicencia.Liberacion;
    public Func<EstadoLicencia?> Reloj { get; set; } = () => FixturesDeLicencia.Estado("reloj_confirmar");
    /// <summary>El error que queda en <see cref="UltimoError"/> cuando una acción devuelve null.</summary>
    public ErrorAula? ErrorAlFallar { get; set; } = FixturesDeLicencia.SinConexion;

    public int Veces(string metodo) => Llamadas.Count(l => l == metodo);

    private async Task<T?> Responder<T>(string metodo, Func<T?> respuesta) where T : class
    {
        Llamadas.Add(metodo);
        if (Freno is { } freno) await freno.Task;
        var r = respuesta();
        (UltimoError, UltimoMotivo) = r is null ? (ErrorAlFallar, ErrorAlFallar?.Detalle) : (null, null);
        return r;
    }

    public Task<EstadoLicencia?> EstadoAsync(string actor, CancellationToken ct = default) => Responder("estado", () => FixturesDeLicencia.Estado("estado_activa"));
    public Task<ConsumoDeLicencia?> ConsumoAsync(string actor, CancellationToken ct = default) => Responder("consumo", () => FixturesDeLicencia.Json<ConsumoDeLicencia>("consumo"));
    public Task<CapacidadesDelNodo?> CapacidadesAsync(string actor, CancellationToken ct = default) => Responder("capacidades", () => FixturesDeLicencia.Json<CapacidadesDelNodo>("capacidades"));
    public Task<CopiaDeLicencia?> CopiaAsync(string actor, CancellationToken ct = default) => Responder("copia", Copia);
    public Task<SolicitudDeLicencia?> SolicitudAsync(string actor, CancellationToken ct = default) => Responder("solicitud", Solicitud);

    public Task<EstadoLicencia?> ActivarAsync(string actor, string textoOBase64, CancellationToken ct = default) => throw new NotSupportedException("OPS manda los bytes del archivo");
    public Task<EstadoLicencia?> ActivarAsync(string actor, byte[] archivo, CancellationToken ct = default) { Enviados.Add(archivo); return Responder("activar", () => Activar(archivo)); }
    public Task<EstadoLicencia?> RenovarAsync(string actor, string textoOBase64, CancellationToken ct = default) => throw new NotSupportedException("OPS manda los bytes del archivo");
    public Task<EstadoLicencia?> RenovarAsync(string actor, byte[] archivo, CancellationToken ct = default) { Enviados.Add(archivo); return Responder("renovar", () => Renovar(archivo)); }
    public Task<ResultadoDeLiberacion?> LiberarAsync(string actor, CancellationToken ct = default) => Responder("liberar", Liberar);
    public Task<EstadoLicencia?> ConfirmarRelojAsync(string actor, CancellationToken ct = default) => Responder("reloj", Reloj);
}

/// <summary>Unas unidades falsas: lo que diga la prueba, o que lance.</summary>
internal sealed class UnidadesFalsas(params UnidadInfo[] unidades) : IProveedorDeUnidades
{
    public bool Lanzar { get; set; }
    public IReadOnlyList<UnidadInfo> Unidades() => Lanzar ? throw new IOException("no se pudieron leer las unidades") : unidades;
}

internal sealed class CarpetasFalsas(string? documentos = null, string? escritorio = null, string? descargas = null) : ICarpetasConocidas
{
    public string? Documentos => documentos;
    public string? Escritorio => escritorio;
    public string? Descargas => descargas;
}

/// <summary>
/// Un sistema de archivos en memoria para el buscador de licencias: carpetas y archivos con su contenido y su fecha. Devuelve TODO lo que hay en la carpeta (sin filtrar por el patrón: así
/// se prueba que el buscador filtra por su cuenta) y nunca lo de las subcarpetas. Una carpeta «retirada» lanza al listarla y una «colgada» tarda lo que se le diga.
/// </summary>
internal sealed class LectorFalso : ILectorDeArchivos
{
    private readonly Dictionary<string, (byte[] Datos, DateTime Modificado)> _archivos = new(StringComparer.OrdinalIgnoreCase);
    private readonly HashSet<string> _carpetas = new(StringComparer.OrdinalIgnoreCase);
    public HashSet<string> Retiradas { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, TimeSpan> Colgadas { get; } = new(StringComparer.OrdinalIgnoreCase);
    public HashSet<string> QueNoSeLeen { get; } = new(StringComparer.OrdinalIgnoreCase);
    public List<string> Listadas { get; } = [];

    private static string Normal(string ruta) => ruta.Length > 3 ? ruta.TrimEnd('\\') : ruta;

    public LectorFalso Carpeta(string carpeta)
    {
        _carpetas.Add(Normal(carpeta));
        return this;
    }

    public LectorFalso Archivo(string ruta, byte[] datos, DateTime modificadoUtc)
    {
        _archivos[ruta] = (datos, modificadoUtc);
        var carpeta = Path.GetDirectoryName(ruta)!;
        _carpetas.Add(Normal(carpeta));
        return this;
    }

    public void Borrar(string ruta) => _archivos.Remove(ruta);

    public void Cambiar(string ruta, byte[] datos) => _archivos[ruta] = (datos, _archivos[ruta].Modificado);

    /// <summary>Una carpeta «retirada» todavía existe al preguntarlo y desaparece al listarla: la memoria se sacó justo entre las dos cosas.</summary>
    public bool ExisteCarpeta(string carpeta) => _carpetas.Contains(Normal(carpeta));

    public IEnumerable<ArchivoVisto> Archivos(string carpeta, string patron)
    {
        lock (Listadas) Listadas.Add(Normal(carpeta));
        if (Colgadas.TryGetValue(Normal(carpeta), out var espera)) Thread.Sleep(espera);
        if (Retiradas.Contains(Normal(carpeta))) throw new IOException("El dispositivo no está listo.", unchecked((int)0x80070015));
        return _archivos.Where(a => string.Equals(Normal(Path.GetDirectoryName(a.Key)!), Normal(carpeta), StringComparison.OrdinalIgnoreCase))
                        .Select(a => new ArchivoVisto(a.Key, a.Value.Datos.Length, a.Value.Modificado)).ToList();
    }

    public byte[] LeerInicio(string ruta, int cuantos)
    {
        if (QueNoSeLeen.Contains(ruta) || !_archivos.TryGetValue(ruta, out var a)) throw new FileNotFoundException("no está", ruta);
        return a.Datos.Take(cuantos).ToArray();
    }

    public byte[]? LeerCompleto(string ruta, int maximo)
    {
        if (QueNoSeLeen.Contains(ruta) || !_archivos.TryGetValue(ruta, out var a)) throw new FileNotFoundException("no está", ruta);
        return a.Datos.Length > maximo ? null : a.Datos.ToArray();
    }
}

/// <summary>El sistema de archivos real con ganchos (como el de las pruebas de la escritura segura): cada método hace lo normal salvo que la prueba le ponga otra cosa.</summary>
internal sealed class IoConGanchos : IOperacionesDeArchivo
{
    public IOperacionesDeArchivo Real { get; } = new OperacionesDeArchivoDelSistema();
    public Func<string, bool>? ExisteCarpetaHook { get; set; }
    public Func<string, long?>? EspacioLibreHook { get; set; }
    public Func<string, Stream>? CrearNuevoHook { get; set; }
    public Action<string>? BorrarHook { get; set; }
    public List<string> Creados { get; } = [];

    public bool ExisteCarpeta(string ruta) => ExisteCarpetaHook?.Invoke(ruta) ?? Real.ExisteCarpeta(ruta);
    public bool Existe(string ruta) => Real.Existe(ruta);
    public long? EspacioLibre(string carpeta) => EspacioLibreHook is null ? Real.EspacioLibre(carpeta) : EspacioLibreHook(carpeta);
    public Stream CrearNuevo(string ruta) { Creados.Add(ruta); return CrearNuevoHook?.Invoke(ruta) ?? Real.CrearNuevo(ruta); }
    public Stream AbrirLectura(string ruta) => Real.AbrirLectura(ruta);
    public long Tamano(string ruta) => Real.Tamano(ruta);
    public void MoverSinSobrescribir(string origen, string destino) => Real.MoverSinSobrescribir(origen, destino);
    public void Borrar(string ruta) { if (BorrarHook is null) Real.Borrar(ruta); else BorrarHook(ruta); }
    public void VaciarADisco(string ruta) => Real.VaciarADisco(ruta);
}

/// <summary>Un archivo de escritura que se rompe como una memoria que se retira: deja escribir lo que la prueba diga y luego lanza el código de Windows de «el dispositivo no está listo».</summary>
internal sealed class EscrituraQueSeCorta(Stream interno, long permitidos) : Stream
{
    private long _escritos;

    public override async ValueTask WriteAsync(ReadOnlyMemory<byte> buffer, CancellationToken cancellationToken = default)
    {
        if (_escritos + buffer.Length > permitidos)
        {
            var cabe = (int)Math.Max(0, permitidos - _escritos);
            if (cabe > 0) await interno.WriteAsync(buffer[..cabe], cancellationToken);
            _escritos += cabe;
            throw new IOException("El dispositivo no está listo.", unchecked((int)0x80070015));
        }
        await interno.WriteAsync(buffer, cancellationToken);
        _escritos += buffer.Length;
    }

    public override void Write(byte[] buffer, int offset, int count) => WriteAsync(buffer.AsMemory(offset, count)).AsTask().GetAwaiter().GetResult();
    public override void Flush() => interno.Flush();
    public override Task FlushAsync(CancellationToken cancellationToken) => interno.FlushAsync(cancellationToken);
    public override ValueTask DisposeAsync() => interno.DisposeAsync();
    protected override void Dispose(bool disposing) { if (disposing) interno.Dispose(); base.Dispose(disposing); }
    public override bool CanRead => false;
    public override bool CanSeek => false;
    public override bool CanWrite => true;
    public override long Length => interno.Length;
    public override long Position { get => interno.Position; set => throw new NotSupportedException(); }
    public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long value) => throw new NotSupportedException();
}

/// <summary>Una carpeta temporal única por prueba, que se borra al terminar, y lo que hay en ella (incluidos los temporales «.parte» que NO deben quedar).</summary>
internal sealed class CarpetaTemporal : IDisposable
{
    public string Ruta { get; } = Path.Combine(Path.GetTempPath(), "avacom-ops-licencia-tests", Guid.NewGuid().ToString("N"));

    public CarpetaTemporal() => Directory.CreateDirectory(Ruta);

    public string Sub(string nombre)
    {
        var r = Path.Combine(Ruta, nombre);
        Directory.CreateDirectory(r);
        return r;
    }

    public string[] Entradas(string? carpeta = null) =>
        Directory.GetFileSystemEntries(carpeta ?? Ruta).Select(p => Path.GetFileName(p)!).OrderBy(n => n, StringComparer.Ordinal).ToArray();

    public void Dispose()
    {
        try { Directory.Delete(Ruta, recursive: true); }
        catch { /* queda en la carpeta temporal del sistema */ }
    }
}

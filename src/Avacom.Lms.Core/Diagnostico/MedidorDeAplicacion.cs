using System.Diagnostics;
using System.Net;

namespace Avacom.Lms.Core.Diagnostico;

/// <summary>Cómo terminó una llamada del cliente al nodo (para contar errores por minuto).</summary>
public enum ResultadoDeLlamada { Correcta, Cliente4xx, Servidor5xx, TiempoAgotado, SinConexion }

/// <summary>Lo que la aplicación midió de sí misma en la ventana reciente: cuánto tarda el nodo en contestar y cuántos errores hubo.</summary>
public sealed record ResumenDeAplicacion(
    int Llamadas, double? P50Ms, double? P95Ms, double? MaximoMs,
    int Cliente4xx, int Servidor5xx, int TiemposAgotados, int SinConexion, int Reconexiones,
    double ErroresPorMinuto, long BytesBajados, long BytesSubidos)
{
    public int Errores => Cliente4xx + Servidor5xx + TiemposAgotados + SinConexion + Reconexiones;
}

/// <summary>
/// Indicadores «de aplicación» para depurar (latencia p50/p95 de las llamadas al nodo, errores por minuto, reconexiones del canal en tiempo real y
/// bytes que la app movió). Es lo que tarda AVACOM de verdad, no sólo la red. Los percentiles y los errores se calculan sobre una ventana
/// móvil (5 minutos por defecto); «errores/min» mira el último minuto. Hilo seguro. <see cref="Global"/> es el del proceso; las pruebas usan
/// instancias propias con su reloj.
/// </summary>
public sealed class MedidorDeAplicacion
{
    public static MedidorDeAplicacion Global { get; } = new();

    /// <summary>Las llamadas del propio diagnóstico no se miden: medirse a sí mismo falsearía el resultado.</summary>
    public const string RutaDelDiagnostico = "/api/aula/tiempo-real";

    private readonly record struct Evento(long Ms, double? Latencia, ResultadoDeLlamada? Resultado, bool Reconexion);

    private readonly object candado = new();
    private readonly Queue<Evento> eventos = new();
    private readonly Func<long> reloj;
    private readonly long ventanaMs;
    private long bajados, subidos;

    public MedidorDeAplicacion(Func<long>? reloj = null, TimeSpan? ventana = null)
    {
        this.reloj = reloj ?? (() => Environment.TickCount64);
        ventanaMs = (long)(ventana ?? TimeSpan.FromMinutes(5)).TotalMilliseconds;
    }

    /// <summary>Anota una llamada. <paramref name="latenciaMs"/> es nula cuando no hubo respuesta (sin red, tiempo agotado).</summary>
    public void RegistrarLlamada(double? latenciaMs, ResultadoDeLlamada resultado)
    {
        lock (candado) { eventos.Enqueue(new Evento(reloj(), latenciaMs, resultado, false)); Podar(); }
    }

    /// <summary>El canal en tiempo real se cayó y volvió a abrirse.</summary>
    public void RegistrarReconexion()
    {
        lock (candado) { eventos.Enqueue(new Evento(reloj(), null, null, true)); Podar(); }
    }

    public void SumarBajados(long bytes) { if (bytes > 0) Interlocked.Add(ref bajados, bytes); }
    public void SumarSubidos(long bytes) { if (bytes > 0) Interlocked.Add(ref subidos, bytes); }
    public long BytesBajados => Interlocked.Read(ref bajados);
    public long BytesSubidos => Interlocked.Read(ref subidos);

    /// <summary>Canales de tiempo real abiertos ahora en este proceso (OPS: el del profesor; Student: el de la tableta).</summary>
    public int CanalesAbiertos => Volatile.Read(ref canales);
    private int canales;
    public void CanalAbierto() => Interlocked.Increment(ref canales);
    public void CanalCerrado() { if (Interlocked.Decrement(ref canales) < 0) Interlocked.Exchange(ref canales, 0); }

    public void Reiniciar()
    {
        lock (candado) eventos.Clear();
    }

    public ResumenDeAplicacion Resumen()
    {
        Evento[] copia;
        var ahora = reloj();
        lock (candado) { Podar(); copia = [.. eventos]; }
        var latencias = copia.Where(e => e.Latencia is not null).Select(e => e.Latencia!.Value).Order().ToArray();
        int Contar(ResultadoDeLlamada r) => copia.Count(e => e.Resultado == r);
        var reconexiones = copia.Count(e => e.Reconexion);
        var ultimoMinuto = copia.Count(e => ahora - e.Ms <= 60_000 && (e.Reconexion || e.Resultado is not (null or ResultadoDeLlamada.Correcta)));
        return new ResumenDeAplicacion(
            copia.Count(e => e.Resultado is not null), Percentil(latencias, 0.50), Percentil(latencias, 0.95), latencias.Length == 0 ? null : latencias[^1],
            Contar(ResultadoDeLlamada.Cliente4xx), Contar(ResultadoDeLlamada.Servidor5xx), Contar(ResultadoDeLlamada.TiempoAgotado), Contar(ResultadoDeLlamada.SinConexion),
            reconexiones, ultimoMinuto, BytesBajados, BytesSubidos);
    }

    /// <summary>El mismo criterio que el nodo (<c>ESTADISTICAS.resumen</c>): el elemento en la posición n·p, sin interpolar.</summary>
    public static double? Percentil(IReadOnlyList<double> ordenados, double p) =>
        ordenados.Count == 0 ? null : ordenados[Math.Min(ordenados.Count - 1, (int)(ordenados.Count * p))];

    public static ResultadoDeLlamada Clasificar(HttpStatusCode estado) => (int)estado switch
    {
        >= 500 => ResultadoDeLlamada.Servidor5xx,
        >= 400 => ResultadoDeLlamada.Cliente4xx,
        _ => ResultadoDeLlamada.Correcta,
    };

    private void Podar()
    {
        var corte = reloj() - ventanaMs;
        while (eventos.Count > 0 && eventos.Peek().Ms < corte) eventos.Dequeue();
    }
}

/// <summary>
/// Mide cada llamada HTTP del cliente: tiempo hasta recibir las cabeceras, resultado y bytes (de subida por el cuerpo de la petición y de bajada por lo que
/// realmente se lee de la respuesta, también en descargas por tramos). No cambia nada de lo que la app envía ni recibe.
/// </summary>
public sealed class HandlerDeMedicion : DelegatingHandler
{
    private readonly MedidorDeAplicacion medidor;

    public HandlerDeMedicion(HttpMessageHandler? interno = null, MedidorDeAplicacion? medidor = null) : base(interno ?? new HttpClientHandler())
    {
        this.medidor = medidor ?? MedidorDeAplicacion.Global;
    }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage peticion, CancellationToken ct)
    {
        var propia = peticion.RequestUri?.AbsolutePath.StartsWith(MedidorDeAplicacion.RutaDelDiagnostico, StringComparison.OrdinalIgnoreCase) == true;
        if (!propia && peticion.Content?.Headers.ContentLength is { } subida) medidor.SumarSubidos(subida);
        var reloj = Stopwatch.StartNew();
        HttpResponseMessage respuesta;
        try
        {
            respuesta = await base.SendAsync(peticion, ct);
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or IOException)
        {
            // Si quien llamó canceló, no es un fallo de red: no cuenta. Si no, es un tiempo agotado (TaskCanceled) o una red caída.
            if (!propia && !ct.IsCancellationRequested)
                medidor.RegistrarLlamada(null, ex is TaskCanceledException ? ResultadoDeLlamada.TiempoAgotado : ResultadoDeLlamada.SinConexion);
            throw;
        }
        if (propia) return respuesta;
        medidor.RegistrarLlamada(reloj.Elapsed.TotalMilliseconds, MedidorDeAplicacion.Clasificar(respuesta.StatusCode));
        if (respuesta.Content is { } contenido) respuesta.Content = new ContenidoContado(contenido, medidor);
        return respuesta;
    }

    /// <summary>Deja pasar el cuerpo tal cual y suma los bytes que se leen.</summary>
    private sealed class ContenidoContado : HttpContent
    {
        private readonly HttpContent interno;
        private readonly MedidorDeAplicacion medidor;

        public ContenidoContado(HttpContent interno, MedidorDeAplicacion medidor)
        {
            this.interno = interno;
            this.medidor = medidor;
            foreach (var cabecera in interno.Headers) Headers.TryAddWithoutValidation(cabecera.Key, cabecera.Value);
        }

        protected override async Task SerializeToStreamAsync(Stream destino, TransportContext? contexto)
        {
            await using var origen = await interno.ReadAsStreamAsync();
            await using var contado = new FlujoContado(origen, medidor);
            await contado.CopyToAsync(destino);
        }

        protected override async Task<Stream> CreateContentReadStreamAsync() => new FlujoContado(await interno.ReadAsStreamAsync(), medidor);

        protected override bool TryComputeLength(out long largo)
        {
            largo = interno.Headers.ContentLength ?? 0;
            return interno.Headers.ContentLength is not null;
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) interno.Dispose();
            base.Dispose(disposing);
        }
    }

    private sealed class FlujoContado(Stream interno, MedidorDeAplicacion medidor) : Stream
    {
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override long Seek(long desplazamiento, SeekOrigin origen) => throw new NotSupportedException();
        public override void SetLength(long valor) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int desplazamiento, int cuenta) => throw new NotSupportedException();

        public override int Read(byte[] buffer, int desplazamiento, int cuenta)
        {
            var n = interno.Read(buffer, desplazamiento, cuenta);
            medidor.SumarBajados(n);
            return n;
        }

        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken ct = default)
        {
            var n = await interno.ReadAsync(buffer, ct);
            medidor.SumarBajados(n);
            return n;
        }

        public override async Task<int> ReadAsync(byte[] buffer, int desplazamiento, int cuenta, CancellationToken ct) =>
            await ReadAsync(buffer.AsMemory(desplazamiento, cuenta), ct);

        protected override void Dispose(bool disposing)
        {
            if (disposing) interno.Dispose();
            base.Dispose(disposing);
        }

        public override async ValueTask DisposeAsync()
        {
            await interno.DisposeAsync();
            await base.DisposeAsync();
        }
    }
}

using System.Diagnostics;
using System.Globalization;
using System.Net.Sockets;
using System.Text;

namespace Avacom.Lms.Core.Diagnostico;

/// <summary>Una lectura de todos los indicadores. Lo que el equipo no puede medir es nulo (el panel dice «no disponible»).</summary>
public sealed record MuestraDeRendimiento(
    DateTimeOffset Instante,
    double? CpuSistemaPct, double CpuProcesoPct,
    double? RamSistemaPct, double? RamSistemaUsadaMb, double? RamSistemaTotalMb, double RamProcesoMb,
    double? DescargaMbps, double? CargaMbps, double? DescargaAppMbps, double? CargaAppMbps,
    double? LatenciaMs, double? PerdidaPct,
    double? DiscoLibreGb, double? DiscoLibrePct, double? DiscoLecturaMBs, double? DiscoEscrituraMBs,
    int? ConexionesActivas, int CanalesAbiertos,
    double? LatenciaAppP50Ms, double? LatenciaAppP95Ms, double ErroresPorMinuto, ResumenDeAplicacion Aplicacion,
    string? Marca);

/// <summary>
/// Mide cada pocos segundos lo que hace falta para depurar una prueba de red y de descarga: CPU, RAM, velocidad de bajada y de subida, latencia
/// y pérdida hacia el nodo, disco, conexiones activas y lo que la propia app midió (<see cref="MedidorDeAplicacion"/>). Guarda un historial
/// acotado (10 minutos a 2 s), con «marcas» numeradas para señalar momentos de la prueba («aquí empezó la descarga»), y lo exporta a CSV.
///
/// Una sola instancia por proceso (<see cref="Global"/>), que arranca con <see cref="Iniciar"/> y sigue midiendo aunque se cierre la pantalla.
/// Cuesta casi nada: una lectura al sistema, una conexión TCP corta al nodo y una consulta pequeña cada intervalo.
///
/// Cómo se miden las cosas (para leer bien el resultado):
/// · CPU y RAM «del equipo» son de toda la máquina (en OPS incluye al nodo, que corre en la misma máquina); «de la app» es sólo este proceso.
/// · Bajada y subida salen de las tarjetas de red (todo el tráfico del equipo; en OPS es lo que el nodo reparte a las tabletas). Si el sistema no
///   las da (Android) se usan los bytes que la app movió (<c>DescargaAppMbps</c>).
/// · La latencia es el tiempo de abrir una conexión TCP al puerto del nodo, no un ping: el cortafuegos de Windows suele tirar los ICMP y daría una
///   pérdida falsa. La «pérdida» es el porcentaje de sondeos que no conectaron en 1 s entre los últimos 30: indica inestabilidad, no es pérdida de paquetes exacta.
/// </summary>
public sealed class MonitorDeRendimiento
{
    public static MonitorDeRendimiento Global { get; } = new();

    public static readonly TimeSpan IntervaloPorDefecto = TimeSpan.FromSeconds(2);
    public const int CapacidadDelHistorial = 300;
    private const int SondeosParaLaPerdida = 30;
    private static readonly TimeSpan TiempoDelSondeo = TimeSpan.FromSeconds(1);

    private readonly ILectorDelSistema lector;
    private readonly MedidorDeAplicacion medidor;
    private readonly object candado = new();
    private readonly List<MuestraDeRendimiento> historial = [];
    private readonly Queue<bool> sondeos = new();
    private readonly Func<Uri, CancellationToken, Task<double?>> sonda;
    private int marcas;
    private string? marcaPendiente;
    private CancellationTokenSource? parada;
    private Task? bucle;

    // lo anterior, para convertir contadores acumulados en tasas
    private long tickAnterior;
    private (ulong Inactivo, ulong Total)? cpuSistemaAnterior;
    private TimeSpan cpuProcesoAnterior;
    private (long Rx, long Tx)? redAnterior;
    private (long Leidos, long Escritos)? discoAnterior;
    private long bajadosAnterior, subidosAnterior;
    private readonly Func<long> reloj;

    public MonitorDeRendimiento(ILectorDelSistema? lector = null, MedidorDeAplicacion? medidor = null, Func<Uri, CancellationToken, Task<double?>>? sonda = null, Func<long>? reloj = null)
    {
        this.lector = lector ?? new LectorDelSistema();
        this.medidor = medidor ?? MedidorDeAplicacion.Global;
        this.sonda = sonda ?? SondearTcpAsync;
        this.reloj = reloj ?? (() => Stopwatch.GetTimestamp() * 1000 / Stopwatch.Frequency);
    }

    /// <summary>El nodo al que se mide la latencia (host y puerto).</summary>
    public Uri? Nodo { get; private set; }
    /// <summary>Dónde viven los datos de la app: de ahí se toma el volumen cuyo espacio se mide.</summary>
    public string RutaDeDatos { get; set; } = Path.GetTempPath();
    /// <summary>Lo que cuenta las conexiones activas con el nodo. En OPS: los alumnos con canal abierto que el nodo dice tener. Nulo: sólo se muestra el canal propio.</summary>
    public Func<CancellationToken, Task<int?>>? ConexionesRemotas { get; set; }
    /// <summary>Sustituye la lectura del disco donde <c>DriveInfo</c> no sirve (Android lo lee con <c>StatFs</c>): devuelve (total, libre) en bytes.</summary>
    public Func<(long Total, long Libre)?>? LectorDeDisco { get; set; }

    public TimeSpan Intervalo { get; private set; } = IntervaloPorDefecto;
    public bool EnMarcha => bucle is { IsCompleted: false };
    public event Action<MuestraDeRendimiento>? Muestreado;

    /// <summary>Arranca la medición (una sola vez por proceso; llamarla de nuevo sólo actualiza el nodo y el contador de conexiones).</summary>
    public void Iniciar(Uri nodo, Func<CancellationToken, Task<int?>>? conexionesRemotas = null, TimeSpan? intervalo = null)
    {
        Nodo = nodo;
        if (conexionesRemotas is not null) ConexionesRemotas = conexionesRemotas;
        if (EnMarcha) return;
        Intervalo = intervalo ?? IntervaloPorDefecto;
        parada = new CancellationTokenSource();
        var ct = parada.Token;
        bucle = Task.Run(async () =>
        {
            using var reloj = new PeriodicTimer(Intervalo);
            try
            {
                await TomarMuestraAsync(ct);
                while (await reloj.WaitForNextTickAsync(ct)) await TomarMuestraAsync(ct);
            }
            catch (OperationCanceledException) { }
        });
    }

    public void Detener()
    {
        try { parada?.Cancel(); } catch { }
    }

    /// <summary>El historial, de la lectura más vieja a la más nueva.</summary>
    public IReadOnlyList<MuestraDeRendimiento> Historial()
    {
        lock (candado) return [.. historial];
    }

    public MuestraDeRendimiento? Ultima()
    {
        lock (candado) return historial.Count == 0 ? null : historial[^1];
    }

    /// <summary>Señala el momento actual con «Marca N» (se verá en la tabla y en el CSV). Devuelve el nombre de la marca.</summary>
    public string Marcar()
    {
        lock (candado)
        {
            marcaPendiente = $"Marca {++marcas}";
            return marcaPendiente;
        }
    }

    /// <summary>Vacía el historial y los contadores de la app para empezar una corrida limpia.</summary>
    public void Reiniciar()
    {
        lock (candado) { historial.Clear(); sondeos.Clear(); marcas = 0; marcaPendiente = null; }
        medidor.Reiniciar();
    }

    /// <summary>Una lectura ahora. Pública para que las pruebas (y «Actualizar») no dependan del reloj.</summary>
    public async Task<MuestraDeRendimiento> TomarMuestraAsync(CancellationToken ct = default)
    {
        var tick = reloj();
        var segundos = tickAnterior == 0 ? 0 : Math.Max(0.001, (tick - tickAnterior) / 1000.0);
        tickAnterior = tick;

        // CPU del equipo: variación del tiempo ocupado sobre el total. Si el sistema no da el contador, nulo.
        double? cpuSistema = null;
        var cpuS = lector.TiemposDeCpuDelSistema();
        if (cpuS is { } actual && cpuSistemaAnterior is { } previo && actual.Total > previo.Total)
            cpuSistema = Acotar(100.0 * (1.0 - (double)(actual.Inactivo - previo.Inactivo) / (actual.Total - previo.Total)));
        cpuSistemaAnterior = cpuS;

        // CPU de la app: segundos de CPU gastados entre segundos de reloj y núcleos (100 % = todos los núcleos ocupados).
        var cpuP = lector.TiempoDeCpuDelProceso();
        var cpuProceso = segundos > 0 ? Acotar(100.0 * (cpuP - cpuProcesoAnterior).TotalSeconds / (segundos * lector.Nucleos)) : 0;
        cpuProcesoAnterior = cpuP;

        double? ramPct = null, ramUsada = null, ramTotal = null;
        if (lector.MemoriaDelSistema() is { } mem && mem.Total > 0)
        {
            ramTotal = mem.Total / Mb; ramUsada = (mem.Total - mem.Disponible) / Mb;
            ramPct = Acotar(100.0 * (mem.Total - mem.Disponible) / mem.Total);
        }

        double? baja = null, sube = null;
        var red = lector.BytesDeRed();
        if (red is { } r && redAnterior is { } rp && segundos > 0)
        {
            baja = Mbps(r.Recibidos - rp.Rx, segundos); sube = Mbps(r.Enviados - rp.Tx, segundos);
        }
        redAnterior = red;

        var bajados = medidor.BytesBajados; var subidos = medidor.BytesSubidos;
        double? bajaApp = segundos > 0 ? Mbps(bajados - bajadosAnterior, segundos) : null, subeApp = segundos > 0 ? Mbps(subidos - subidosAnterior, segundos) : null;
        bajadosAnterior = bajados; subidosAnterior = subidos;

        double? lectura = null, escritura = null;
        var disco = lector.BytesDeDiscoDelProceso();
        if (disco is { } d && discoAnterior is { } dp && segundos > 0)
        {
            lectura = Math.Max(0, (d.Leidos - dp.Leidos) / Mb / segundos); escritura = Math.Max(0, (d.Escritos - dp.Escritos) / Mb / segundos);
        }
        discoAnterior = disco;

        double? libreGb = null, librePct = null;
        var espacio = LectorDeDisco?.Invoke() ?? lector.Disco(RutaDeDatos);
        if (espacio is { } e && e.Total > 0) { libreGb = e.Libre / (Mb * 1024); librePct = 100.0 * e.Libre / e.Total; }

        // Latencia y pérdida hacia el nodo.
        double? latencia = null;
        if (Nodo is { } nodo)
        {
            latencia = await sonda(nodo, ct);
            lock (candado)
            {
                sondeos.Enqueue(latencia is not null);
                while (sondeos.Count > SondeosParaLaPerdida) sondeos.Dequeue();
            }
        }
        double? perdida;
        lock (candado) perdida = sondeos.Count == 0 ? null : 100.0 * sondeos.Count(ok => !ok) / sondeos.Count;

        int? conexiones = null;
        if (ConexionesRemotas is { } contar)
        {
            try
            {
                using var limite = CancellationTokenSource.CreateLinkedTokenSource(ct);
                limite.CancelAfter(TimeSpan.FromSeconds(1.5));
                conexiones = await contar(limite.Token);
            }
            catch { conexiones = null; }
        }

        var app = medidor.Resumen();
        string? marca;
        MuestraDeRendimiento muestra;
        lock (candado)
        {
            marca = marcaPendiente; marcaPendiente = null;
            muestra = new MuestraDeRendimiento(DateTimeOffset.Now, cpuSistema, cpuProceso, ramPct, ramUsada, ramTotal, lector.MemoriaDelProceso() / Mb,
                baja, sube, bajaApp, subeApp, latencia, perdida, libreGb, librePct, lectura, escritura, conexiones, medidor.CanalesAbiertos,
                app.P50Ms, app.P95Ms, app.ErroresPorMinuto, app, marca);
            historial.Add(muestra);
            if (historial.Count > CapacidadDelHistorial) historial.RemoveAt(0);
        }
        Muestreado?.Invoke(muestra);
        return muestra;
    }

    /// <summary>El historial en CSV (coma como separador y punto decimal, UTF-8), una fila por lectura: sirve para graficar la prueba en una hoja de cálculo.</summary>
    public string ComoCsv()
    {
        var sb = new StringBuilder();
        sb.AppendLine("hora,marca,cpu_sistema_pct,cpu_app_pct,ram_sistema_pct,ram_sistema_usada_mb,ram_app_mb,descarga_mbps,carga_mbps,descarga_app_mbps,carga_app_mbps," +
                      "latencia_red_ms,perdida_sondeos_pct,disco_libre_gb,disco_libre_pct,disco_lectura_mbs,disco_escritura_mbs,conexiones_activas,canales_abiertos," +
                      "latencia_app_p50_ms,latencia_app_p95_ms,errores_por_min,llamadas,err_4xx,err_5xx,timeouts,sin_conexion,reconexiones");
        foreach (var m in Historial())
        {
            var a = m.Aplicacion;
            sb.AppendLine(string.Join(',',
                m.Instante.ToString("yyyy-MM-dd HH:mm:ss"), Texto(m.Marca), N(m.CpuSistemaPct), N(m.CpuProcesoPct), N(m.RamSistemaPct), N(m.RamSistemaUsadaMb), N(m.RamProcesoMb),
                N(m.DescargaMbps), N(m.CargaMbps), N(m.DescargaAppMbps), N(m.CargaAppMbps), N(m.LatenciaMs), N(m.PerdidaPct), N(m.DiscoLibreGb), N(m.DiscoLibrePct),
                N(m.DiscoLecturaMBs), N(m.DiscoEscrituraMBs), m.ConexionesActivas?.ToString(CultureInfo.InvariantCulture) ?? "", m.CanalesAbiertos.ToString(CultureInfo.InvariantCulture),
                N(m.LatenciaAppP50Ms), N(m.LatenciaAppP95Ms), N(m.ErroresPorMinuto), a.Llamadas.ToString(CultureInfo.InvariantCulture), a.Cliente4xx.ToString(CultureInfo.InvariantCulture),
                a.Servidor5xx.ToString(CultureInfo.InvariantCulture), a.TiemposAgotados.ToString(CultureInfo.InvariantCulture), a.SinConexion.ToString(CultureInfo.InvariantCulture),
                a.Reconexiones.ToString(CultureInfo.InvariantCulture)));
        }
        return sb.ToString();

        static string N(double? v) => v is { } x && double.IsFinite(x) ? x.ToString("0.##", CultureInfo.InvariantCulture) : "";
        static string Texto(string? t) => t is null ? "" : "\"" + t.Replace("\"", "\"\"") + "\"";
    }

    public string ExportarCsv(string ruta)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(ruta))!);
        File.WriteAllText(ruta, ComoCsv(), new UTF8Encoding(true));
        return ruta;
    }

    /// <summary>Milisegundos que tarda en abrirse una conexión TCP al puerto del nodo; nulo si no conecta en 1 s.</summary>
    private static async Task<double?> SondearTcpAsync(Uri nodo, CancellationToken ct)
    {
        var reloj = Stopwatch.StartNew();
        try
        {
            using var cliente = new TcpClient();
            using var limite = CancellationTokenSource.CreateLinkedTokenSource(ct);
            limite.CancelAfter(TiempoDelSondeo);
            await cliente.ConnectAsync(nodo.Host, nodo.Port, limite.Token);
            return reloj.Elapsed.TotalMilliseconds;
        }
        catch { return null; }
    }

    private const double Mb = 1024.0 * 1024.0;
    private static double Mbps(long bytes, double segundos) => Math.Max(0, bytes * 8.0 / 1_000_000.0 / segundos);
    private static double Acotar(double pct) => double.IsFinite(pct) ? Math.Clamp(pct, 0, 100) : 0;
}

using System.Net;
using Avacom.Lms.Core.Diagnostico;

namespace Avacom.Lms.Core.Tests;

public sealed class RendimientoTests
{
    private sealed class Reloj { public long Ms = 1_000_000; }

    private sealed class RespondeCon(Func<HttpRequestMessage, HttpResponseMessage> responder) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage peticion, CancellationToken ct) => Task.FromResult(responder(peticion));
    }

    private sealed class Falla(Exception ex) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage peticion, CancellationToken ct) => throw ex;
    }

    private sealed class LectorFalso : ILectorDelSistema
    {
        public int Nucleos => 4;
        public (ulong, ulong)? Cpu; public TimeSpan CpuProceso; public (long, long)? Mem = (8L << 30, 2L << 30);
        public (long, long)? Red; public (long, long)? DiscoProceso; public (long, long)? Espacio = (500L << 30, 100L << 30);
        public (ulong Inactivo, ulong Total)? TiemposDeCpuDelSistema() => Cpu;
        public TimeSpan TiempoDeCpuDelProceso() => CpuProceso;
        public (long Total, long Disponible)? MemoriaDelSistema() => Mem;
        public long MemoriaDelProceso() => 200L << 20;
        public (long Recibidos, long Enviados)? BytesDeRed() => Red;
        public (long Leidos, long Escritos)? BytesDeDiscoDelProceso() => DiscoProceso;
        public (long Total, long Libre)? Disco(string ruta) => Espacio;
    }

    [Fact]
    public void LosPercentilesUsanElMismoCriterioQueElNodo()
    {
        var reloj = new Reloj();
        var m = new MedidorDeAplicacion(() => reloj.Ms);
        for (var i = 1; i <= 100; i++) m.RegistrarLlamada(i, ResultadoDeLlamada.Correcta);
        var r = m.Resumen();
        Assert.Equal(100, r.Llamadas);
        Assert.Equal(51, r.P50Ms);     // posición 100·0,50 = 50 → el elemento 51
        Assert.Equal(96, r.P95Ms);
        Assert.Equal(100, r.MaximoMs);
        Assert.Equal(0, r.Errores);
    }

    [Fact]
    public void SinLlamadasNoInventaLatencias()
    {
        var r = new MedidorDeAplicacion().Resumen();
        Assert.Null(r.P50Ms); Assert.Null(r.P95Ms); Assert.Null(r.MaximoMs);
        Assert.Equal(0, r.ErroresPorMinuto);
    }

    [Fact]
    public void LosErroresPorMinutoSoloMiranElUltimoMinutoYLaVentanaOlvidaLoViejo()
    {
        var reloj = new Reloj();
        var m = new MedidorDeAplicacion(() => reloj.Ms, TimeSpan.FromMinutes(5));
        m.RegistrarLlamada(10, ResultadoDeLlamada.Servidor5xx);
        m.RegistrarLlamada(null, ResultadoDeLlamada.TiempoAgotado);
        reloj.Ms += 90_000;                                    // lo anterior ya tiene más de un minuto
        m.RegistrarLlamada(20, ResultadoDeLlamada.Cliente4xx);
        m.RegistrarReconexion();
        m.RegistrarLlamada(null, ResultadoDeLlamada.SinConexion);
        var r = m.Resumen();
        Assert.Equal(3, r.ErroresPorMinuto);                   // 4xx + reconexión + sin red
        Assert.Equal((1, 1, 1, 1, 1), (r.Cliente4xx, r.Servidor5xx, r.TiemposAgotados, r.SinConexion, r.Reconexiones));
        reloj.Ms += 6 * 60_000;                                // fuera de la ventana de 5 min
        Assert.Equal(0, m.Resumen().Errores);
    }

    [Fact]
    public void LosCanalesAbiertosNuncaBajanDeCero()
    {
        var m = new MedidorDeAplicacion();
        m.CanalCerrado();
        Assert.Equal(0, m.CanalesAbiertos);
        m.CanalAbierto(); m.CanalAbierto(); m.CanalCerrado();
        Assert.Equal(1, m.CanalesAbiertos);
    }

    [Fact]
    public async Task ElHandlerMideLatenciaResultadoYBytesSinTocarLaRespuesta()
    {
        var m = new MedidorDeAplicacion();
        using var http = new HttpClient(new HandlerDeMedicion(new RespondeCon(p =>
            p.RequestUri!.AbsolutePath == "/malo" ? new HttpResponseMessage(HttpStatusCode.InternalServerError) { Content = new StringContent("x") }
                                                  : new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(new byte[4096]) }), m));
        var cuerpo = await http.GetByteArrayAsync("http://nodo/ok");
        Assert.Equal(4096, cuerpo.Length);
        await using (var flujo = await http.GetStreamAsync("http://nodo/ok")) await flujo.CopyToAsync(Stream.Null);   // descarga por flujo
        Assert.Equal(HttpStatusCode.InternalServerError, (await http.GetAsync("http://nodo/malo")).StatusCode);
        using var envio = new HttpRequestMessage(HttpMethod.Post, "http://nodo/ok") { Content = new StringContent("hola") };
        (await http.SendAsync(envio)).Dispose();

        var r = m.Resumen();
        Assert.Equal(4, r.Llamadas);
        Assert.Equal(1, r.Servidor5xx);
        Assert.Equal(4096 * 3 + 1, m.BytesBajados);            // tres descargas de 4096 (la del POST se almacena en memoria al enviar) + «x»
        Assert.Equal(4, m.BytesSubidos);
    }

    [Fact]
    public async Task ElHandlerClasificaTiempoAgotadoSinRedYNoCuentaLoCanceladoPorQuienLlama()
    {
        var m = new MedidorDeAplicacion();
        using (var http = new HttpClient(new HandlerDeMedicion(new Falla(new TaskCanceledException("tiempo")), m)))
            await Assert.ThrowsAsync<TaskCanceledException>(() => http.GetAsync("http://nodo/a"));
        using (var http = new HttpClient(new HandlerDeMedicion(new Falla(new HttpRequestException("sin red")), m)))
            await Assert.ThrowsAsync<HttpRequestException>(() => http.GetAsync("http://nodo/a"));
        using var cancelada = new CancellationTokenSource(); cancelada.Cancel();
        using (var http = new HttpClient(new HandlerDeMedicion(new Falla(new TaskCanceledException("yo")), m)))
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => http.GetAsync("http://nodo/a", cancelada.Token));
        var r = m.Resumen();
        Assert.Equal((1, 1), (r.TiemposAgotados, r.SinConexion));
        Assert.Equal(2, r.Llamadas);                           // cuentan como llamadas, pero sin respuesta no aportan latencia
        Assert.Null(r.P50Ms);
    }

    [Fact]
    public async Task LasLlamadasDelPropioDiagnosticoNoSeMiden()
    {
        var m = new MedidorDeAplicacion();
        using var http = new HttpClient(new HandlerDeMedicion(new RespondeCon(_ => new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{}") }), m));
        await http.GetStringAsync("http://nodo/api/aula/tiempo-real/");
        Assert.Equal(0, m.Resumen().Llamadas);
        Assert.Equal(0, m.BytesBajados);
    }

    [Fact]
    public async Task ElMonitorConvierteContadoresAcumuladosEnTasas()
    {
        var m = new MedidorDeAplicacion();
        var lector = new LectorFalso { Cpu = (100, 200), Red = (0, 0), DiscoProceso = (0, 0) };
        var t = 10_000L;
        var monitor = new MonitorDeRendimiento(lector, m, sonda: (_, _) => Task.FromResult<double?>(12.5), reloj: () => t);
        await monitor.TomarMuestraAsync();                       // la primera sólo fija la base

        t += 2000;                                               // 2 s después
        lector.Cpu = (150, 300);                                 // +50 inactivos de +100 → 50 % de uso
        lector.CpuProceso = TimeSpan.FromSeconds(1.6);           // 1,6 s de CPU en 2 s con 4 núcleos = 20 %
        lector.Red = (5_000_000, 2_500_000);                     // 5 MB bajados y 2,5 MB subidos en 2 s = 20 y 10 Mbps
        lector.DiscoProceso = (4L << 20, 2L << 20);              // 4 MB leídos y 2 MB escritos en 2 s
        m.SumarBajados(500_000);
        var s = await monitor.TomarMuestraAsync();

        Assert.Equal(50, s.CpuSistemaPct!.Value, 1);
        Assert.Equal(20, s.CpuProcesoPct, 1);
        Assert.Equal(75, s.RamSistemaPct!.Value, 1);             // 8 GB con 2 GB disponibles
        Assert.Equal(20, s.DescargaMbps!.Value, 1);
        Assert.Equal(10, s.CargaMbps!.Value, 1);
        Assert.Equal(2, s.DescargaAppMbps!.Value, 1);            // 0,5 MB en 2 s = 2 Mbps
        Assert.Equal(2, s.DiscoLecturaMBs!.Value, 1);
        Assert.Equal(1, s.DiscoEscrituraMBs!.Value, 1);
        Assert.Equal(20, s.DiscoLibrePct!.Value, 1);
        Assert.Equal(100, s.DiscoLibreGb!.Value, 1);
    }

    [Fact]
    public async Task SinLecturaDelSistemaElPanelRecibeNuloEnVezDeUnCero()
    {
        var lector = new LectorFalso { Cpu = null, Mem = null, Red = null, DiscoProceso = null, Espacio = null };
        var monitor = new MonitorDeRendimiento(lector, new MedidorDeAplicacion(), sonda: (_, _) => Task.FromResult<double?>(null));
        await monitor.TomarMuestraAsync();
        var s = await monitor.TomarMuestraAsync();
        Assert.Null(s.CpuSistemaPct); Assert.Null(s.RamSistemaPct); Assert.Null(s.DescargaMbps); Assert.Null(s.DiscoLibreGb); Assert.Null(s.DiscoLecturaMBs);
        Assert.Null(s.PerdidaPct);                                // sin nodo definido no hay sondeos
    }

    [Fact]
    public async Task LaPerdidaEsElPorcentajeDeSondeosSinRespuestaYLasMarcasSeAnotanUnaVez()
    {
        var respuestas = new Queue<double?>([5, null, 7, null]);
        var monitor = new MonitorDeRendimiento(new LectorFalso(), new MedidorDeAplicacion(), sonda: (_, _) => Task.FromResult(respuestas.Dequeue()));
        monitor.Iniciar(new Uri("http://nodo:8000"), intervalo: TimeSpan.FromHours(1));
        monitor.Detener();
        await Task.Delay(100);                                    // que termine la lectura inicial de Iniciar y no compita con las de la prueba
        monitor.Reiniciar();
        respuestas = new Queue<double?>([5, null, 7, null]);
        await monitor.TomarMuestraAsync();
        Assert.Equal("Marca 1", monitor.Marcar());
        var conMarca = await monitor.TomarMuestraAsync();
        var siguiente = await monitor.TomarMuestraAsync();
        Assert.Equal("Marca 1", conMarca.Marca);
        Assert.Null(siguiente.Marca);
        Assert.Equal(33.3, siguiente.PerdidaPct!.Value, 1);       // 1 de 3 sondeos falló
    }

    [Fact]
    public async Task ElHistorialTieneTopeYElCsvTrae11IndicadoresPorFila()
    {
        var monitor = new MonitorDeRendimiento(new LectorFalso(), new MedidorDeAplicacion(), sonda: (_, _) => Task.FromResult<double?>(1));
        for (var i = 0; i < MonitorDeRendimiento.CapacidadDelHistorial + 5; i++) await monitor.TomarMuestraAsync();
        Assert.Equal(MonitorDeRendimiento.CapacidadDelHistorial, monitor.Historial().Count);
        var lineas = monitor.ComoCsv().Split('\n', StringSplitOptions.RemoveEmptyEntries);
        Assert.Equal(MonitorDeRendimiento.CapacidadDelHistorial + 1, lineas.Length);
        var columnas = lineas[0].TrimEnd('\r').Split(',').Length;
        Assert.All(lineas.Skip(1), l => Assert.Equal(columnas, l.TrimEnd('\r').Split(',').Length));
        Assert.Contains("latencia_app_p95_ms", lineas[0]);
        var ruta = monitor.ExportarCsv(Path.Combine(Ayudas.CarpetaTemporal(), "r.csv"));
        Assert.True(File.Exists(ruta));
    }
}

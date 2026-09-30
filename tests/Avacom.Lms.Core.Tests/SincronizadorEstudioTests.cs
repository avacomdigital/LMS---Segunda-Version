using System.Text.Json;
using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>El sincronizador: vacía la cola en orden y por lotes, reconoce lo que el nodo respondió, y sin conexión no pierde nada.</summary>
[Collection("estado global")]
public sealed class SincronizadorEstudioTests : IDisposable
{
    private const string Dispositivo = EstudioAyudas.Dispositivo;

    private readonly string carpeta = Ayudas.CarpetaTemporal();
    private readonly ProveedorDeClaveEnMemoria proveedor = new();
    private readonly EstudioApiFalsa api = new();
    private readonly ColaEstudio cola;

    public SincronizadorEstudioTests()
    {
        RelojNodo.Olvidar();
        cola = new ColaEstudio(Path.Combine(carpeta, "cola.avc"), proveedor);
    }

    public void Dispose()
    {
        RelojNodo.Olvidar();
        try { Directory.Delete(carpeta, true); } catch { }
    }

    private SincronizadorEstudio Sincronizador() => new(api, cola);

    private long Encolar(string alumno = "ana", string tipo = TiposEventoEstudio.BloqueVisto) =>
        cola.Encolar(alumno, tipo, Ayudas.Json("""{"asignacion_id":"asig-1","bloques_vistos":["b1"]}"""));

    private static AcuseSync Acuse(IEnumerable<EventoEstudio> eventos, Func<long, string>? estado = null, long servidorEn = 123_456) =>
        new(true, servidorEn, eventos.Select(e => new ResultadoEvento(e.Secuencia, (estado ?? (_ => "integrado"))(e.Secuencia), null, null)).ToList(), null, [], []);

    private static ErrorAula Error(int estado, string? codigo) => new(estado, codigo, "detalle del nodo", null, null);

    /// <summary>El nodo responde siempre «integrado» a todo y anota cada envío.</summary>
    private List<(string? Alumno, long[] Secuencias)> NodoQueAcepta()
    {
        var envios = new List<(string?, long[])>();
        api.Sincronizar = (_, _, eventos, alumno, _) =>
        {
            envios.Add((alumno, eventos.Select(e => e.Secuencia).ToArray()));
            return Task.FromResult<AcuseSync?>(Acuse(eventos));
        };
        return envios;
    }

    // ------------------------------------------------------------------------------- el acuse

    [Fact]
    public async Task ConAcuse_SeReconocenTodasLasSecuenciasQueElNodoRespondio_Incluidas_LasRechazadasYLasPendientesDeDecision()
    {
        foreach (var _ in Enumerable.Range(0, 4)) Encolar();
        string? emisor = null;
        string? dispositivo = null;
        IReadOnlyList<EventoEstudio>? recibidos = null;
        api.Sincronizar = (disp, emi, eventos, alumno, _) =>
        {
            (dispositivo, emisor, recibidos) = (disp, emi, eventos);
            Assert.Equal("ana", alumno);
            return Task.FromResult<AcuseSync?>(Acuse(eventos, s => s switch { 1 => "integrado", 2 => "duplicado", 3 => "rechazado", _ => "pendiente_decision" }));
        };
        var integrados = new List<(string, AcuseSync)>();
        var sincronizador = Sincronizador();
        sincronizador.Integrado += (alumno, acuse) => integrados.Add((alumno, acuse));

        var r = await sincronizador.VaciarAsync(Dispositivo);

        Assert.Equal((1, 1, 1, 1, 0, false), (r.Enviados, r.Duplicados, r.Rechazados, r.PendientesDeDecision, r.Pendientes, r.SinConexion));
        Assert.NotNull(r.Ultimo);
        Assert.Empty(cola.Pendientes());
        Assert.Empty(new ColaEstudio(Path.Combine(carpeta, "cola.avc"), proveedor).Pendientes());   // y el borrado quedó guardado
        Assert.Equal((Dispositivo, cola.EmisorId), (dispositivo, emisor));
        Assert.Equal([1L, 2, 3, 4], recibidos!.Select(e => e.Secuencia).ToArray());
        var (alumnoDelAviso, acuseDelAviso) = Assert.Single(integrados);
        Assert.Equal("ana", alumnoDelAviso);
        Assert.Same(r.Ultimo, acuseDelAviso);
        Assert.InRange(RelojNodo.AhoraMs, 123_456, 123_456 + 60_000);                           // aprendió el «servidor_en»
        Assert.Null(sincronizador.UltimoError);
    }

    [Fact]
    public async Task SinPendientes_NoLlamaAlNodo()
    {
        api.Sincronizar = (_, _, _, _, _) => throw new InvalidOperationException("no debería llamarse");
        Assert.Equal(ResultadoSincronizacionEstudio.Nada, await Sincronizador().VaciarAsync(Dispositivo));
    }

    // ---------------------------------------------------------------------------------- lotes

    [Fact]
    public async Task ManejaLotesDe200_EnOrdenDeSecuencia_YVaciaLaCola()
    {
        foreach (var _ in Enumerable.Range(0, 450)) Encolar();
        var envios = NodoQueAcepta();

        var r = await Sincronizador().VaciarAsync(Dispositivo);

        Assert.Equal([200, 200, 50], envios.Select(e => e.Secuencias.Length).ToArray());
        var todas = envios.SelectMany(e => e.Secuencias).ToArray();
        Assert.Equal(Enumerable.Range(1, 450).Select(i => (long)i).ToArray(), todas);         // todas, en orden y sin repetir
        Assert.All(envios, e => Assert.Equal(e.Secuencias.OrderBy(s => s).ToArray(), e.Secuencias));
        Assert.Equal((450, 0, false), (r.Enviados, r.Pendientes, r.SinConexion));
        Assert.Equal(SincronizadorEstudio.EventosPorEnvio, 200);
    }

    [Fact]
    public async Task LoQueSeGuardaMientrasElEnvioViaja_SaleEnElSiguienteLoteDeLaMismaPasada()
    {
        Encolar();
        var envios = new List<long[]>();
        api.Sincronizar = (_, _, eventos, _, _) =>
        {
            envios.Add(eventos.Select(e => e.Secuencia).ToArray());
            if (envios.Count == 1) Encolar();                                                  // el alumno sigue trabajando mientras la red contesta
            return Task.FromResult<AcuseSync?>(Acuse(eventos));
        };
        var r = await Sincronizador().VaciarAsync(Dispositivo);
        Assert.Equal([[1L], [2L]], envios);
        Assert.Equal((2, 0), (r.Enviados, r.Pendientes));
    }

    // ------------------------------------------------------------------------------ sin conexión

    [Theory]
    [InlineData(0, "sin_conexion")]
    [InlineData(-1, null)]                          // sin error alguno: se trata como falta de conexión
    [InlineData(503, "fuente_no_disponible")]
    [InlineData(500, null)]
    [InlineData(401, "sesion_expirada")]            // la persona vuelve a identificarse y la cola sigue ahí
    public async Task SinConexionOFalloDelNodo_ConservaToda_LaCola_YSeReintentaDespues(int estado, string? codigo)
    {
        var ids = new[] { Encolar(), Encolar(), Encolar("beto") };
        var llamadas = 0;
        api.Sincronizar = (_, _, _, _, _) =>
        {
            llamadas++;
            api.UltimoError = estado < 0 ? null : Error(estado, codigo);
            return Task.FromResult<AcuseSync?>(null);
        };
        var sincronizador = Sincronizador();

        var r = await sincronizador.VaciarAsync(Dispositivo);

        Assert.Equal((0, 3, true), (r.Enviados, r.Pendientes, r.SinConexion));
        Assert.Equal(1, llamadas);                                                             // no se insiste con los demás alumnos: la red no está
        Assert.Equal(ids, cola.Pendientes().Select(e => e.Evento.Secuencia).ToArray());
        Assert.Equal(estado < 0 ? null : (int?)estado, sincronizador.UltimoError?.Estado);

        var envios = NodoQueAcepta();                                                          // vuelve la red
        var despues = await sincronizador.VaciarAsync(Dispositivo);
        Assert.Equal((3, 0), (despues.Enviados, despues.Pendientes));
        Assert.Equal(2, envios.Count);
        Assert.Null(sincronizador.UltimoError);
    }

    [Theory]
    [InlineData(400, "datos_invalidos")]
    [InlineData(403, "dispositivo_ajeno")]
    [InlineData(403, "no_es_el_titular")]
    [InlineData(403, "persona_ajena")]
    [InlineData(404, "no_encontrado")]
    [InlineData(409, "asignacion_cerrada")]
    public async Task UnRechazoDelEnvioCompleto_NoDescartaLaCola_QuedaElMotivo_YSigueConLosDemasAlumnos(int estado, string codigo)
    {
        Encolar("ana");
        Encolar("ana");
        Encolar("beto");
        var llamadas = new List<string?>();
        api.Sincronizar = (_, _, eventos, alumno, _) =>
        {
            llamadas.Add(alumno);
            if (alumno == "ana")
            {
                api.UltimoError = Error(estado, codigo);
                return Task.FromResult<AcuseSync?>(null);
            }
            return Task.FromResult<AcuseSync?>(Acuse(eventos));
        };
        var sincronizador = Sincronizador();

        var r = await sincronizador.VaciarAsync(Dispositivo);

        Assert.Equal(["ana", "beto"], llamadas);                                               // una vez por alumno: sin bucles
        Assert.Equal((1, 2, false), (r.Enviados, r.Pendientes, r.SinConexion));
        Assert.Equal([1L, 2], cola.Pendientes().Select(e => e.Evento.Secuencia).ToArray());   // lo de ana se conserva íntegro
        Assert.Equal((estado, codigo), (sincronizador.UltimoError!.Estado, sincronizador.UltimoError.Codigo));
    }

    [Theory]
    [InlineData(typeof(NotSupportedException), false)]          // un cuerpo que no es JSON: el cliente no lo previó y lanza
    [InlineData(typeof(InvalidOperationException), false)]
    [InlineData(typeof(HttpRequestException), true)]
    [InlineData(typeof(IOException), true)]
    public async Task UnaExcepcionInesperadaDelCliente_NoSaleDelVaciado_NiPierdeNada(Type tipo, bool esDeRed)
    {
        Encolar();
        Encolar("beto");
        var llamadas = 0;
        api.Sincronizar = (_, _, _, _, _) =>
        {
            llamadas++;
            throw (Exception)Activator.CreateInstance(tipo, "falló")!;
        };

        var r = await Sincronizador().VaciarAsync(Dispositivo);

        Assert.Equal((0, 2, esDeRed), (r.Enviados, r.Pendientes, r.SinConexion));
        Assert.Equal(1, llamadas);                                                             // y no se sigue con los demás alumnos
        Assert.Equal(2, cola.CantidadPendiente());
    }

    [Fact]
    public async Task UnAcuseQueNoAcusa_NoSeToma_PorAcuse()
    {
        Encolar();
        api.Sincronizar = (_, _, eventos, _, _) => Task.FromResult<AcuseSync?>(Acuse(eventos) with { Acuse = false });
        var r = await Sincronizador().VaciarAsync(Dispositivo);
        Assert.Equal((0, 1, false), (r.Enviados, r.Pendientes, r.SinConexion));
        Assert.Single(cola.Pendientes());
    }

    // ------------------------------------------------------------- lo que responde el nodo

    [Fact]
    public async Task SoloSeReconoceLoQueSeEnvioYElNodoRespondio_LoDemasSigueEsperando()
    {
        foreach (var _ in Enumerable.Range(0, 3)) Encolar();
        var llamadas = 0;
        api.Sincronizar = (_, _, _, _, _) =>
        {
            llamadas++;
            // Un nodo que sólo contesta por la secuencia 1 (y por una, la 99, que esta cola nunca envió).
            var resultados = new[] { new ResultadoEvento(1, "integrado", null, null), new ResultadoEvento(99, "integrado", null, null) };
            return Task.FromResult<AcuseSync?>(new AcuseSync(true, 5, resultados, null, [], []));
        };
        var sincronizador = Sincronizador();

        var primera = await sincronizador.VaciarAsync(Dispositivo);

        Assert.Equal((1, 2), (primera.Enviados, primera.Pendientes));                          // la 99 no cuenta: nunca salió de esta cola
        Assert.Equal([2L, 3], cola.Pendientes().Select(e => e.Evento.Secuencia).ToArray());
        Assert.Equal(2, llamadas);                                                             // tras el acuse parcial se intentó con lo que quedaba; sin respuesta, se paró

        NodoQueAcepta();
        var siguiente = await sincronizador.VaciarAsync(Dispositivo);
        Assert.Equal((2, 0), (siguiente.Enviados, siguiente.Pendientes));
    }

    [Fact]
    public async Task UnNodoQueNoRespondeNadaDeLoEnviado_NoHaceQueSeInsistaEnLaMismaPasada()
    {
        Encolar();
        Encolar();
        var llamadas = 0;
        api.Sincronizar = (_, _, _, _, _) =>
        {
            llamadas++;
            return Task.FromResult<AcuseSync?>(new AcuseSync(true, 5, [], null, [], []));
        };
        var r = await Sincronizador().VaciarAsync(Dispositivo);
        Assert.Equal(1, llamadas);
        Assert.Equal(2, r.Pendientes);
    }

    [Fact]
    public async Task UnEstadoQueNoSeConoce_NoSeDaPorRecibido()
    {
        Encolar();
        Encolar();
        api.Sincronizar = (_, _, eventos, _, _) =>
            Task.FromResult<AcuseSync?>(Acuse(eventos, s => s == 1 ? "integrado" : "estado-del-futuro"));
        var r = await Sincronizador().VaciarAsync(Dispositivo);
        Assert.Equal((1, 1), (r.Enviados, r.Pendientes));
        Assert.Equal([2L], cola.Pendientes().Select(e => e.Evento.Secuencia).ToArray());
    }

    // ---------------------------------------------------------------- varios alumnos y varios hilos

    [Fact]
    public async Task SiLaColaMezclaAlumnos_HaceUnEnvioPorAlumno_ConSusEventosEnOrden()
    {
        foreach (var alumno in new[] { "ana", "beto", "ana", "beto", "ana" }) Encolar(alumno);
        var envios = NodoQueAcepta();
        var avisados = new List<string>();
        var sincronizador = Sincronizador();
        sincronizador.Integrado += (alumno, _) => avisados.Add(alumno);

        var r = await sincronizador.VaciarAsync(Dispositivo);

        Assert.Equal(2, envios.Count);
        Assert.Equal("ana", envios[0].Alumno);                                                 // primero quien tiene el evento más antiguo
        Assert.Equal([1L, 3, 5], envios[0].Secuencias);
        Assert.Equal("beto", envios[1].Alumno);
        Assert.Equal([2L, 4], envios[1].Secuencias);
        Assert.Equal(["ana", "beto"], avisados);
        Assert.Equal((5, 0), (r.Enviados, r.Pendientes));
    }

    [Fact]
    public async Task UnaSolaPasadaALaVez_LaSegundaNoHaceNada()
    {
        Encolar();
        var liberar = new TaskCompletionSource();
        var enviados = 0;
        api.Sincronizar = async (_, _, eventos, _, _) =>
        {
            Interlocked.Increment(ref enviados);
            await liberar.Task;
            return Acuse(eventos);
        };
        var sincronizador = Sincronizador();
        var primera = sincronizador.VaciarAsync(Dispositivo);
        while (Volatile.Read(ref enviados) == 0) await Task.Delay(10);

        var segunda = await sincronizador.VaciarAsync(Dispositivo);

        Assert.Equal(ResultadoSincronizacionEstudio.Nada, segunda);
        liberar.SetResult();
        Assert.Equal(1, (await primera).Enviados);
        Assert.Equal(1, enviados);                                                             // un solo envío en total
    }

    [Fact]
    public async Task UnOyenteQueFalla_NoDetieneElVaciado()
    {
        Encolar();
        Encolar("beto");
        NodoQueAcepta();
        var sincronizador = Sincronizador();
        sincronizador.Integrado += (_, _) => throw new InvalidOperationException("la pantalla ya no existe");
        var r = await sincronizador.VaciarAsync(Dispositivo);
        Assert.Equal((2, 0), (r.Enviados, r.Pendientes));
    }

    [Fact]
    public async Task UnTokenCancelado_NoPierdeNada_YElSincronizadorSigueSirviendo()
    {
        Encolar();
        NodoQueAcepta();
        var sincronizador = Sincronizador();
        using var cancelado = new CancellationTokenSource();
        cancelado.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => sincronizador.VaciarAsync(Dispositivo, cancelado.Token));
        Assert.Equal(1, cola.CantidadPendiente());
        Assert.Equal(1, (await sincronizador.VaciarAsync(Dispositivo)).Enviados);            // no quedó bloqueado
    }
}

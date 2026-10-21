using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Nodo;
using Avacom.Lms.Ops.Nodo;

namespace Avacom.Lms.Ops.Tests;

/// <summary>
/// La pestaña «Estado del equipo» sin MAUI (MOD-015, P-18): las líneas del nodo (nada «no medido» sale como cero; el último punto de recuperación dice que MOD-016 no existe), la cola
/// del peor consumidor al mejor, el resumen de una línea, y [Reprocesar]/[Reproducir] con un solo envío aunque se toque dos veces y el mensaje de cada error. Contra las respuestas reales
/// capturadas por el backend.
/// </summary>
public sealed class NodoLogicaTests
{
    private static readonly JsonSerializerOptions Web = new(JsonSerializerDefaults.Web);
    private static readonly TimeZoneInfo Utc = TimeZoneInfo.Utc;

    private static T Fixture<T>(string nombre) => JsonSerializer.Deserialize<T>(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "nodo", nombre + ".json")), Web)!;

    // ---------------------------------------------------------------------------------------------------- las líneas del nodo

    [Fact]
    public void Lineas_DeUnNodoOperativo_DicenLoMedidoYNoInventanCeros()
    {
        var lineas = ResumenDelEquipo.Lineas(Fixture<EstadoDelNodo>("estado"), Utc);
        var por = lineas.ToDictionary(l => l.Rotulo, l => l);
        Assert.Equal("escritor único · comprobada", por["Base de datos"].Valor);
        Assert.Equal(TonoDelNodo.Bien, por["Base de datos"].Tono);
        Assert.Equal("no medido", por["Disco del nodo"].Valor);                                   // null en la respuesta: nunca «0 B libres»
        Assert.StartsWith("en orden", por["Reloj del nodo"].Valor);
        Assert.Equal("11 eventos en la cola · última secuencia 11", por["Cola de salida"].Valor);
        Assert.Equal("1 evento apartado", por["Eventos apartados"].Valor);
        Assert.Equal(TonoDelNodo.Atencion, por["Eventos apartados"].Tono);
        Assert.Equal("cierre limpio del anterior", por["Último arranque"].Valor);
        Assert.Contains("MOD-016", por["Último punto de recuperación"].Valor);
        Assert.Equal("2.9.1", por["Versión del nodo"].Valor);
        Assert.Empty(ResumenDelEquipo.Motivos(Fixture<EstadoDelNodo>("estado")));
        foreach (var l in lineas) { Assert.False(string.IsNullOrWhiteSpace(l.Valor)); Assert.DoesNotContain("null", l.Valor); }
    }

    [Fact]
    public void Lineas_DeUnNodoRestringido_DicenElDiscoElWalYLosMotivos()
    {
        var e = Fixture<EstadoDelNodo>("estado_restringido");
        var por = ResumenDelEquipo.Lineas(e, Utc).ToDictionary(l => l.Rotulo, l => l);
        Assert.Equal("sin escritor único", por["Base de datos"].Valor);
        Assert.Equal(TonoDelNodo.Problema, por["Base de datos"].Tono);
        Assert.Equal("11 MB", por["Diario WAL"].Valor);
        Assert.Equal("1,4 GB libres de 238,4 GB (1 %)", por["Disco del nodo"].Valor);
        Assert.Equal(TonoDelNodo.Problema, por["Disco del nodo"].Tono);
        var motivos = ResumenDelEquipo.Motivos(e);
        Assert.Equal(e.Motivos.Count, motivos.Count);
        Assert.All(motivos, m => Assert.False(string.IsNullOrWhiteSpace(m)));
        Assert.Contains(motivos, m => m.Contains("escritor único"));
        Assert.Contains(motivos, m => m.Contains("espacio"));
    }

    [Fact]
    public void Lineas_ConRestauracionYApagadoSucio()
    {
        var e = Fixture<EstadoDelNodo>("estado") with { Arranque = new ArranqueDelNodo(7, true, new RestauracionDetectada(3, 500, false, 10500, 1)) };
        var por = ResumenDelEquipo.Lineas(e, Utc).ToDictionary(l => l.Rotulo, l => l);
        Assert.Equal("el anterior no se cerró limpio (apagado sucio)", por["Último arranque"].Valor);
        Assert.Equal(TonoDelNodo.Atencion, por["Último arranque"].Tono);
        Assert.Equal("la base traía hasta la secuencia 3 y el nodo ya había emitido hasta 500: el contador saltó a 10.500", por["Restauración detectada"].Valor);
    }

    // ---------------------------------------------------------------------------------------------------- la cola

    [Fact]
    public void Consumidores_DelPeorAlMejor_ConSusFuentes()
    {
        var cola = Fixture<ColaDelNodo>("cola");
        var filas = ResumenDelEquipo.Consumidores(cola, Utc);
        Assert.Equal(["reportes", "libro"], filas.Select(f => f.Nombre).ToArray());
        var reportes = filas[0];
        Assert.Equal(("Reportes", "Rezagado", TonoDelNodo.Atencion, 5L, 1), (reportes.NombreVisible, reportes.EstadoVisible, reportes.Tono, reportes.Pendientes, reportes.Problemas));
        Assert.Equal(["Evaluación · marca 3 de 8 · 5 eventos pendientes"], reportes.Fuentes);
        Assert.Null(reportes.Reintento);
        Assert.Equal("2 consumidores · 1 al día · 1 rezagado · 1 evento apartado", ResumenDelEquipo.ResumenDeCola(cola));
        var conReintento = cola with { Consumidores = [cola.Consumidores[0] with { Fuentes = [cola.Consumidores[0].Fuentes[0] with { Reintento = new ReintentoDeFuente(9, 3, 1_790_000_000_000, "x") }] }] };
        Assert.Contains("falló 3 veces", ResumenDelEquipo.Consumidores(conReintento, Utc)[0].Reintento);
    }

    // ---------------------------------------------------------------------------------------------------- reprocesar y reproducir

    private sealed class ApiFalsa : INodoApi
    {
        public int Reprocesos, Reproducciones;
        public TaskCompletionSource<bool> Puerta = new();
        public ErrorAula? Error;
        public string? UltimoMotivo => Error?.Detalle;
        public ErrorAula? UltimoError => Error;
        public Task<EstadoDelNodo?> EstadoAsync(string actor, CancellationToken ct = default) => Task.FromResult<EstadoDelNodo?>(Fixture<EstadoDelNodo>("estado"));
        public Task<ColaDelNodo?> ColaAsync(string actor, CancellationToken ct = default) => Task.FromResult<ColaDelNodo?>(Fixture<ColaDelNodo>("cola"));
        public Task<ProblemasDeCola?> ProblemasAsync(string actor, string? consumidor = null, string? estado = null, int limite = 100, CancellationToken ct = default) =>
            Task.FromResult<ProblemasDeCola?>(Fixture<ProblemasDeCola>("problemas"));
        public Task<NodoEnSalud?> SaludAsync(CancellationToken ct = default) => Task.FromResult<NodoEnSalud?>(Fixture<SaludConNodo>("health").Nodo);

        public async Task<ProblemaDeCola?> ReprocesarAsync(string actor, long problemaId, CancellationToken ct = default)
        {
            Reprocesos++;
            await Puerta.Task;
            return Error is null ? Fixture<ProblemaDeCola>("reprocesar") : null;
        }

        public async Task<ReproduccionDeConsumidor?> ReproducirAsync(string actor, string consumidor, string? fuente = null, CancellationToken ct = default)
        {
            Reproducciones++;
            await Puerta.Task;
            return Error is null ? Fixture<ReproduccionDeConsumidor>("reproducir") : null;
        }
    }

    [Fact]
    public async Task Reprocesar_UnSoloEnvioAunqueSeToqueDosVeces_YElMensajeDelResultado()
    {
        var api = new ApiFalsa();
        var flujo = new FlujoDeReproceso(api, "adm-1");
        var primero = flujo.ReprocesarAsync(1);
        var segundo = await flujo.ReprocesarAsync(1);                      // segundo toque mientras el primero viaja
        Assert.Equal("Ya se está reprocesando", segundo.Titulo);
        api.Puerta.SetResult(true);
        var mensaje = await primero;
        Assert.Equal((1, 1), (api.Reprocesos, flujo.Envios));
        Assert.Equal(NodoTexto.Reprocesado, mensaje);
        Assert.Equal(EstadosDeProblema.Reprocesado, flujo.UltimoReprocesado!.Estado);
    }

    [Fact]
    public async Task Reprocesar_SinPermiso_DiceComoConseguirLaEscalada()
    {
        var api = new ApiFalsa { Error = new ErrorAula(403, ErroresDelNodo.SinPermiso, "Tu rol no tiene concedido node.queue.replay.", null, null) };
        api.Puerta.SetResult(true);
        var mensaje = await new FlujoDeReproceso(api, "tec-1").ReprocesarAsync(1);
        Assert.Equal("Sin permiso", mensaje.Titulo);
        Assert.Contains("escalada", mensaje.Completo);
        var fallido = new ApiFalsa { Error = new ErrorAula(409, ErroresDelNodo.ReprocesoFallido, "x", null, null) };
        fallido.Puerta.SetResult(true);
        Assert.Equal("Volvió a fallar", (await new FlujoDeReproceso(fallido, "adm-1").ReprocesarAsync(1)).Titulo);
    }

    [Fact]
    public async Task Reproducir_UnSoloEnvio_YElMensaje()
    {
        var api = new ApiFalsa();
        var flujo = new FlujoDeReproceso(api, "adm-1");
        var primero = flujo.ReproducirAsync("reportes");
        Assert.Equal("Ya se está reproduciendo", (await flujo.ReproducirAsync("reportes")).Titulo);
        api.Puerta.SetResult(true);
        Assert.Equal(NodoTexto.Reproducido, await primero);
        Assert.Equal(1, api.Reproducciones);
        Assert.Equal(EstadosDeConsumidor.Reconstruyendose, flujo.UltimaReproduccion!.Estado);
    }
}

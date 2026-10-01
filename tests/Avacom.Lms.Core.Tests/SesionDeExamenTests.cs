using System.Text.Json;
using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

// ============================================================================================ los dobles

/// <summary>El nodo falso de la tableta: devuelve lo que la prueba le configure y apunta cada llamada en el <see cref="Orden"/> compartido con el kiosco.</summary>
internal sealed class ApiAlumnoFalsa(List<string> orden) : IExamenAlumnoApi
{
    public string? UltimoMotivo => UltimoError?.Detalle;
    public ErrorAula? UltimoError { get; set; }

    public bool SinRed;
    public ErrorAula? ErrorSiguiente;                                   // un error HTTP para la PRÓXIMA llamada (después se vuelve a la normalidad)
    public AperturaDeIntento? Apertura;
    public Queue<EstadoDeIntento> Estados = new();
    public EstadoDeIntento? EstadoFijo;
    public PreguntasDeIntento? Preguntas;
    public Func<IReadOnlyList<RespuestaDeExamen>, AcuseDeRespuestas>? AlEnviarRespuestas;
    public EntregaDeIntento? Entrega;

    public readonly List<string> Orden = orden;
    public readonly List<DatosDeTableta?> Aperturas = [];
    public readonly List<LatidoDeTableta> Latidos = [];
    public readonly List<IReadOnlyList<RespuestaDeExamen>> RespuestasEnviadas = [];
    public readonly List<string> OrigenesEnviados = [];
    public readonly List<IReadOnlyList<IncidenteDeTableta>> IncidentesEnviados = [];
    public readonly List<InformeDeBloqueo> BloqueosInformados = [];
    public readonly List<(bool Confirmar, int Respuestas)> Entregas = [];

    /// <summary>Verdadero si esta llamada debe fallar (sin red o con el error de la prueba); deja el error como lo dejaría <c>ClienteJson</c>.</summary>
    private bool Falla(string nombre)
    {
        Orden.Add("api:" + nombre);
        if (SinRed)
        {
            UltimoError = new ErrorAula(0, "sin_conexion", "No hay conexión con el aula.", null, null);
            return true;
        }
        if (ErrorSiguiente is { } e)
        {
            UltimoError = e;
            ErrorSiguiente = null;
            return true;
        }
        UltimoError = null;
        return false;
    }

    public Task<MisEvaluaciones?> MisAsync(string dispositivo, string? alumnoId = null, bool todas = false, CancellationToken ct = default) =>
        Task.FromResult(Falla("mias") ? null : MisEvaluaciones.Vacio);

    public Task<AntesalaDeExamen?> AntesalaAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default) =>
        Task.FromResult<AntesalaDeExamen?>(null);

    public Task<AperturaDeIntento?> AbrirAsync(string dispositivo, string asignacionId, DatosDeTableta? tableta = null, string? alumnoId = null, CancellationToken ct = default)
    {
        Aperturas.Add(tableta);
        return Task.FromResult(Falla("abrir") ? null : Apertura);
    }

    public Task<EstadoDeIntento?> EstadoAsync(string dispositivo, string intentoId, string? alumnoId = null, CancellationToken ct = default) =>
        Task.FromResult(Falla("estado") ? null : EstadoFijo);

    public Task<EstadoDeIntento?> LatirAsync(string dispositivo, string intentoId, LatidoDeTableta latido, string? alumnoId = null, CancellationToken ct = default)
    {
        Latidos.Add(latido);
        if (Falla("latido")) return Task.FromResult<EstadoDeIntento?>(null);
        return Task.FromResult<EstadoDeIntento?>(Estados.Count > 0 ? Estados.Dequeue() : EstadoFijo);
    }

    public Task<PreguntasDeIntento?> PreguntasAsync(string dispositivo, string intentoId, string? alumnoId = null, CancellationToken ct = default) =>
        Task.FromResult(Falla("preguntas") ? null : Preguntas);

    public Task<AcuseDeRespuestas?> EnviarRespuestasAsync(string dispositivo, string intentoId, IReadOnlyList<RespuestaDeExamen> respuestas, string origen = "directo",
                                                          string? preguntaActual = null, long? transcurridoMs = null, string? alumnoId = null, CancellationToken ct = default)
    {
        if (Falla("respuestas")) return Task.FromResult<AcuseDeRespuestas?>(null);
        RespuestasEnviadas.Add(respuestas);
        OrigenesEnviados.Add(origen);
        var acuse = AlEnviarRespuestas?.Invoke(respuestas) ??
                    new AcuseDeRespuestas(true, respuestas.Select(r => r.PreguntaRef).ToList(), [], [], [], null, null, "aceptar", 1, 1_790_000_000_000);
        return Task.FromResult<AcuseDeRespuestas?>(acuse);
    }

    public Task<AcuseDeIncidentes?> EnviarIncidentesAsync(string dispositivo, string intentoId, IReadOnlyList<IncidenteDeTableta> incidentes, string? alumnoId = null, CancellationToken ct = default)
    {
        if (Falla("incidentes")) return Task.FromResult<AcuseDeIncidentes?>(null);
        IncidentesEnviados.Add(incidentes);
        return Task.FromResult<AcuseDeIncidentes?>(new AcuseDeIncidentes(incidentes.Count, 0));
    }

    public Task<AcuseDeBloqueo?> InformarBloqueoAsync(string dispositivo, string intentoId, InformeDeBloqueo informe, string? alumnoId = null, CancellationToken ct = default)
    {
        if (Falla("bloqueo")) return Task.FromResult<AcuseDeBloqueo?>(null);
        BloqueosInformados.Add(informe);
        return Task.FromResult<AcuseDeBloqueo?>(new AcuseDeBloqueo(null, null));
    }

    public Task<EntregaDeIntento?> EntregarAsync(string dispositivo, string intentoId, bool confirmar, IReadOnlyList<RespuestaDeExamen>? respuestas = null,
                                                 long? transcurridoMs = null, string? alumnoId = null, CancellationToken ct = default)
    {
        if (Falla("entregar")) return Task.FromResult<EntregaDeIntento?>(null);
        Entregas.Add((confirmar, respuestas?.Count ?? 0));
        return Task.FromResult(Entrega);
    }

    public Task<ResultadoDeIntento?> ResultadoAsync(string dispositivo, string intentoId, string? alumnoId = null, CancellationToken ct = default) =>
        Task.FromResult<ResultadoDeIntento?>(null);
}

/// <summary>El kiosco de la tableta de la prueba: apunta qué se le pidió y en qué orden, y deja a la prueba decidir qué logra.</summary>
internal sealed class KioscoFalso(List<string> orden) : IKioskService
{
    public bool IsTrueDeviceLockAvailable { get; set; } = true;
    public string Capacidad { get; set; } = Niveles.Controlado;
    public string LockdownSummary => "Kiosco de pruebas.";
    public bool ExamenEnCurso { get; set; }
    public event Action<HechoDeKiosco>? Hecho;

    public readonly List<PlanDeBloqueo> Planes = [];
    public bool? EnCursoAlAplicar;
    public bool? EnCursoAlSoltar;
    public int Soltadas;
    public Func<PlanDeBloqueo, InformeDeBloqueo>? Logra;                 // por omisión: todo lo que el plan pide
    public Exception? LanzarAlAplicar;

    public void Disparar(HechoDeKiosco hecho) => Hecho?.Invoke(hecho);

    public Task EnterFullScreenAsync(CancellationToken ct = default) => Task.CompletedTask;

    public Task<InformeDeBloqueo> StartExamLockAsync(PlanDeBloqueo plan, CancellationToken ct = default)
    {
        orden.Add("kiosco:aplicar");
        EnCursoAlAplicar = ExamenEnCurso;
        Planes.Add(plan);
        if (LanzarAlAplicar is { } ex) throw ex;
        return Task.FromResult(Logra?.Invoke(plan) ?? PoliticaDeKiosco.Evaluar(plan, new CapasDeBloqueo(plan.CapaSistema, plan.CapaApp, plan.BloquearCapturas, plan.CubrirPantallasExtra)));
    }

    public Task<InformeDeBloqueo> StopExamLockAsync(CancellationToken ct = default)
    {
        orden.Add("kiosco:soltar");
        EnCursoAlSoltar = ExamenEnCurso;
        Soltadas++;
        return Task.FromResult(new InformeDeBloqueo(ResultadosDeBloqueo.Liberado, CapasDeBloqueo.Ninguna));
    }
}

// ==================================================================================== la sesión del examen

/// <summary>
/// El examen de una tableta de punta a punta, sin interfaz y con dobles de la API y del kiosco: abrir, bloquear, guardar antes de enviar, dar señal,
/// seguir al profesor, suspenderse, entregar y soltar el bloqueo SÓLO con la entrega confirmada (kiosk.md §2, §5).
/// </summary>
[Collection("estado global")]
public sealed class SesionDeExamenTests : IDisposable
{
    private const string Tab = "student-TAB07";
    private readonly string carpeta = Ayudas.CarpetaTemporal();
    private readonly List<string> orden = [];
    private readonly ApiAlumnoFalsa api;
    private readonly KioscoFalso kiosco;
    private readonly ColaExamen cola;
    private long local = 10_000_000;

    public SesionDeExamenTests()
    {
        api = new ApiAlumnoFalsa(orden);
        kiosco = new KioscoFalso(orden);
        cola = new ColaExamen(Path.Combine(carpeta, "examen.cola"), new ProveedorDeClaveEnMemoria(), () => local);
        RelojNodo.Olvidar();
        api.EstadoFijo = Estado();
        api.Apertura = Apertura();
        api.Preguntas = Preguntas();
    }

    public void Dispose()
    {
        RelojNodo.Olvidar();
        try { Directory.Delete(carpeta, true); } catch { }
    }

    private SesionDeExamen Sesion(AlmacenDePin? pin = null) =>
        new(api, cola, kiosco, Tab, "ana", new DatosDeTableta("Tableta 07", "android", "0.4.2"), pin, () => local);

    // ---- los datos del nodo
    private static ResumenDeIntento Intento(string estado = EstadosIntento.EnCurso, int respondidas = 0, int secMax = 0) =>
        new("i-1", estado, 1, "a-1", Niveles.Controlado, "q1", respondidas, 4, SecuenciaMaxima: secMax);

    private static RelojDeIntento Reloj(bool corre = true, long restante = 600_000) =>
        new(600, restante, corre, !corre, 1_790_000_000_000, 600_000 - restante);

    private static PlanDeBloqueo Controlado(bool sistema = true) => new(Niveles.Controlado, sistema, true, true, false, true, true, 5, Parcial: !sistema);
    private static readonly PlanDeBloqueo Supervisado = new(Niveles.Supervisado, false, false, true, true, false, false, 5);

    private static AperturaDeIntento Apertura(PlanDeBloqueo? plan = null, int secMax = 0, bool reanudado = false, string estado = EstadosIntento.EnCurso) =>
        new(Intento(estado, secMax: secMax), Reloj(estado == EstadosIntento.EnCurso), plan ?? Controlado(), null, 4, EstadosIntento.Suspendido(estado), null, reanudado);

    private static EstadoDeIntento Estado(string estado = EstadosIntento.EnCurso, PlanDeBloqueo? plan = null, bool espera = false, bool sesionActiva = true,
                                          long restante = 580_000, MensajeDeIntento? mensaje = null) =>
        new(Intento(estado), Reloj(estado == EstadosIntento.EnCurso, restante), plan ?? Controlado(), espera, sesionActiva, mensaje, false, 5, 1_790_000_005_000);

    private static PreguntaAula Q(string id) =>
        new(id, "multiple_choice", "opcion_multiple", $"Enunciado de {id}", null, null, 1, 1, 30, false, false, null, null, null, null, null, null, null, null);

    private static PreguntasDeIntento Preguntas() =>
        new("i-1", "Examen", null, null, "1.0.0", true, new[] { "q1", "q2", "q3", "q4" }.Select(Q).ToList(), new Dictionary<string, RespuestaGuardada>(), "q1");

    private static EntregaDeIntento Entregada(string estado = EstadosIntento.Calificado) =>
        new(Intento(estado, 4), 1_790_000_100_000, "alumno", new QueSigue("resultado_al_liberar", "Tu examen quedó entregado."), false, 1_790_000_100_000);

    private static JsonElement R(string texto) => Ayudas.Json($$"""{"text":"{{texto}}"}""");

    private async Task<SesionDeExamen> Abierta(PlanDeBloqueo? plan = null)
    {
        api.Apertura = Apertura(plan);
        var s = Sesion();
        var salida = await s.AbrirAsync("a-1");
        Assert.True(salida.Empezo, salida.Mensaje);
        await s.CargarPreguntasAsync();
        orden.Clear();
        return s;
    }

    // ====================================================================================================== abrir

    [Fact]
    public async Task Abrir_ActivaLaBanderaANTESDelBloqueo_AplicaElPlanDelNodo_YLeContaLoQueLogro()
    {
        using var s = Sesion();
        var salida = await s.AbrirAsync("a-1");
        Assert.Equal(ResultadoDeApertura.Abierto, salida.Resultado);
        Assert.Equal(FaseDeExamen.EnCurso, s.Fase);
        Assert.True(kiosco.EnCursoAlAplicar, "La bandera de examen en curso debe estar activa antes de aplicar el bloqueo (kiosk.md §2).");
        Assert.True(kiosco.ExamenEnCurso);
        Assert.Equal(Controlado(), kiosco.Planes.Single());
        Assert.Equal(ResultadosDeBloqueo.Aplicado, s.UltimoInforme!.Resultado);
        Assert.Null(s.AvisoDeSeguridad);
        // el informe se cuenta al nodo: lo que la tableta LOGRÓ, no lo que se le pidió
        Assert.Equal(ResultadosDeBloqueo.Aplicado, api.BloqueosInformados.Single().Resultado);
        Assert.Equal(new[] { "api:abrir", "kiosco:aplicar", "api:bloqueo" }, orden);
    }

    [Fact]
    public async Task Abrir_LaTabletaDeclaraSuCapacidadRealYSusDatos()
    {
        kiosco.Capacidad = Niveles.Supervisado;
        using var s = Sesion();
        await s.AbrirAsync("a-1");
        var datos = api.Aperturas.Single()!;
        Assert.Equal(("Tableta 07", "android", "0.4.2", Niveles.Supervisado), (datos.Nombre, datos.Plataforma, datos.VersionApp, datos.CapacidadControl));
    }

    [Fact]
    public async Task Abrir_ConLaTabletaPorDebajoDelNivel_ElExamenNoEmpieza_NiSeBloquea_HastaQueElProfesorDecide()
    {
        api.Apertura = new AperturaDeIntento(new ResumenDeIntento("i-1", EstadosIntento.NoIniciado, 1), null, null, null, 0, false,
                                             new MensajeDeIntento("espera_admision", "Tu tableta no alcanza el nivel de control de este examen."), false,
                                             new AdmisionDeTableta("adm-1", "en_espera", Niveles.Controlado, Niveles.Supervisado));
        using var s = Sesion();
        var salida = await s.AbrirAsync("a-1");
        Assert.Equal(ResultadoDeApertura.EsperaAdmision, salida.Resultado);
        Assert.Equal(FaseDeExamen.EsperandoAdmision, s.Fase);
        Assert.Empty(kiosco.Planes);
        Assert.False(kiosco.ExamenEnCurso);
        Assert.Null(s.IntentoId);
        // el profesor admite: volver a pulsar «Comenzar» (idempotente) abre el intento
        api.Apertura = Apertura(Supervisado);
        var segunda = await s.AbrirAsync("a-1");
        Assert.True(segunda.Empezo);
        Assert.Equal(FaseDeExamen.EnCurso, s.Fase);
        Assert.Equal(Supervisado, s.Plan);                                // un plan que no pide capas no bloquea nada, pero el examen SÍ está en curso
        Assert.Empty(kiosco.Planes);
        Assert.True(kiosco.ExamenEnCurso);
    }

    [Fact]
    public async Task Abrir_SinRed_NoCambiaNada_YElMensajeEsParaElAlumno()
    {
        api.SinRed = true;
        using var s = Sesion();
        var salida = await s.AbrirAsync("a-1");
        Assert.Equal(ResultadoDeApertura.SinConexion, salida.Resultado);
        Assert.Contains("No hay conexión", salida.Mensaje);
        Assert.Equal(FaseDeExamen.SinExamen, s.Fase);
        Assert.False(kiosco.ExamenEnCurso);
        Assert.True(s.SinConexion);
    }

    [Theory]
    [InlineData(403, "admision_rechazada", ResultadoDeApertura.Rechazada)]
    [InlineData(409, "asignacion_no_abierta", ResultadoDeApertura.NoDisponible)]
    [InlineData(409, "intentos_agotados", ResultadoDeApertura.NoDisponible)]
    [InlineData(409, "version_no_disponible", ResultadoDeApertura.NoDisponible)]
    [InlineData(503, "fuente_no_disponible", ResultadoDeApertura.NoDisponible)]
    public async Task Abrir_UnErrorDelNodoSeConvierteEnUnaFraseParaElAlumno(int estado, string codigo, ResultadoDeApertura esperado)
    {
        api.ErrorSiguiente = new ErrorAula(estado, codigo, "detalle del nodo", null, null);
        using var s = Sesion();
        var salida = await s.AbrirAsync("a-1");
        Assert.Equal(esperado, salida.Resultado);
        Assert.Equal(codigo, salida.Codigo);
        Assert.NotEqual("detalle del nodo", salida.Mensaje);            // un código crudo o el texto del servidor no se le muestra tal cual
        Assert.Equal(FaseDeExamen.SinExamen, s.Fase);
        Assert.False(kiosco.ExamenEnCurso);
    }

    [Fact]
    public async Task Abrir_UnIntentoQueYaEstaSuspendido_SeReanudaConElBloqueoPuestoYEsperandoAlProfesor()
    {
        api.Apertura = Apertura(estado: EstadosIntento.Pausado, reanudado: true);
        using var s = Sesion();
        var salida = await s.AbrirAsync("a-1");
        Assert.Equal(ResultadoDeApertura.Reanudado, salida.Resultado);
        Assert.Equal(FaseDeExamen.Suspendido, s.Fase);
        Assert.Single(kiosco.Planes);                                    // un suspendido NO queda libre
    }

    [Fact]
    public async Task Abrir_LaSecuenciaArrancaDesdeLoQueElNodoYaAcepto()
    {
        api.Apertura = Apertura(secMax: 7);
        using var s = Sesion();
        await s.AbrirAsync("a-1");
        Assert.Equal(8, s.Responder("q1", R("a")));
    }

    [Fact]
    public async Task Abrir_DosVecesLaMismaAsignacion_NoVuelveAAplicarNada()
    {
        using var s = Sesion();
        await s.AbrirAsync("a-1");
        var otra = await s.AbrirAsync("a-1");
        Assert.Equal(ResultadoDeApertura.Reanudado, otra.Resultado);
        Assert.Single(kiosco.Planes);
        Assert.Single(api.Aperturas);
    }

    // ============================================================================================ el bloqueo, a la vista

    [Fact]
    public async Task UnBloqueoParcial_SeInforma_SeMuestra_YNingunMensajeDeRedLoPisa()
    {
        kiosco.Logra = plan => PoliticaDeKiosco.Evaluar(plan, new CapasDeBloqueo(false, true, true, true), "La app no es Device Owner.");
        using var s = Sesion();
        await s.AbrirAsync("a-1");
        Assert.Equal(ResultadosDeBloqueo.Parcial, s.UltimoInforme!.Resultado);
        Assert.StartsWith("Bloqueo parcial", s.AvisoDeSeguridad);
        Assert.Equal(ResultadosDeBloqueo.Parcial, api.BloqueosInformados.Single().Resultado);     // el nodo lo sabe: registra el incidente y el profesor lo ve
        var aviso = s.AvisoDeSeguridad;
        // se cae la red y vuelve: el aviso de seguridad sigue ahí
        api.SinRed = true;
        await s.LatirAsync();
        Assert.True(s.SinConexion);
        Assert.Equal(aviso, s.AvisoDeSeguridad);
        api.SinRed = false;
        await s.LatirAsync();
        Assert.False(s.SinConexion);
        Assert.Equal(aviso, s.AvisoDeSeguridad);
    }

    [Fact]
    public async Task UnBloqueoFallido_ElExamenSigue_ConElAvisoYElInformeAlNodo()
    {
        kiosco.Logra = plan => PoliticaDeKiosco.Evaluar(plan, CapasDeBloqueo.Ninguna, "Sin Device Owner.");
        using var s = Sesion();
        var salida = await s.AbrirAsync("a-1");
        Assert.True(salida.Empezo);                                       // el nodo no invalida por esto (BR-077): el alumno presenta
        Assert.Equal(FaseDeExamen.EnCurso, s.Fase);
        Assert.Contains("no se pudo aplicar", s.AvisoDeSeguridad);
        Assert.Equal(ResultadosDeBloqueo.Fallido, api.BloqueosInformados.Single().Resultado);
    }

    [Fact]
    public async Task SiElKioscoLanzaUnaExcepcion_NoTumbaElExamen_SeInformaComoFallido()
    {
        kiosco.LanzarAlAplicar = new InvalidOperationException("El paquete no quedó autorizado.");
        using var s = Sesion();
        var salida = await s.AbrirAsync("a-1");
        Assert.True(salida.Empezo);
        Assert.Equal(ResultadosDeBloqueo.Fallido, s.UltimoInforme!.Resultado);
        Assert.NotNull(s.AvisoDeSeguridad);
        Assert.Equal(ResultadosDeBloqueo.Fallido, api.BloqueosInformados.Single().Resultado);
    }

    [Fact]
    public async Task ElInformeDeBloqueoSeGuardaAntesDeEnviarse_SinRedSaleDespues()
    {
        api.SinRed = true;
        api.Apertura = Apertura();
        // abrir necesita la red; se abre con red y se corta justo al informar
        api.SinRed = false;
        using var s = Sesion();
        await s.AbrirAsync("a-1");
        Assert.Empty(cola.Pendientes());                                  // llegó
        api.BloqueosInformados.Clear();
        api.EstadoFijo = Estado(plan: Supervisado);                       // el profesor degrada: hay un informe nuevo
        api.SinRed = true;
        await s.LatirAsync();                                             // sin red no se entera
        api.SinRed = false;
        await s.LatirAsync();
        Assert.Single(api.BloqueosInformados);
        Assert.Empty(cola.Pendientes());
    }

    // ======================================================================================== responder y la cola

    [Fact]
    public async Task Responder_GuardaEnElDispositivoANTESDeEnviar_YSinRedNoSePierdeNada()
    {
        using var s = await Abierta();
        api.SinRed = true;
        Assert.Equal(1, s.Responder("q1", R("a")));
        Assert.Equal(2, s.Responder("q2", R("b")));
        Assert.Equal(EstadoDeGuardado.GuardadoEnDispositivo, s.Guardado);
        Assert.Equal(2, s.PendientesEnDispositivo);
        var vaciado = await s.VaciarAsync();
        Assert.True(vaciado.SinConexion);
        Assert.Equal(2, vaciado.Pendientes);
        api.SinRed = false;
        vaciado = await s.VaciarAsync();
        Assert.Equal(new[] { "q1", "q2" }, api.RespuestasEnviadas.Single().Select(r => r.PreguntaRef).OrderBy(x => x));
        Assert.Equal((0, EstadoDeGuardado.GuardadoEnNodo), (vaciado.Pendientes, s.Guardado));
    }

    [Fact]
    public async Task ResponderYEnviar_ConRedSale_YElAcuseVaciaLaCola()
    {
        using var s = await Abierta();
        await s.ResponderYEnviarAsync("q1", R("a"));
        Assert.Single(api.RespuestasEnviadas);
        Assert.Equal("directo", api.OrigenesEnviados.Single());
        Assert.Equal(EstadoDeGuardado.GuardadoEnNodo, s.Guardado);
    }

    [Fact]
    public async Task LoQueEsperoMuchoEnLaCola_SaleMarcadoComoCola()
    {
        using var s = await Abierta();
        api.SinRed = true;
        s.Responder("q1", R("a"));
        local += 60_000;                                                   // un minuto sin red
        api.SinRed = false;
        await s.VaciarAsync();
        Assert.Equal("cola", api.OrigenesEnviados.Single());
    }

    [Fact]
    public async Task UnaRespuestaRechazadaConSuMotivoNoSeReenviaEternamente()
    {
        using var s = await Abierta();
        api.AlEnviarRespuestas = r => new AcuseDeRespuestas(true, [], [], [], [new RechazoDeRespuesta(r[0].PreguntaRef, "forma no admitida")], null, null, "aceptar");
        await s.ResponderYEnviarAsync("q1", R("a"));
        Assert.Equal(0, s.PendientesEnDispositivo);
    }

    [Theory]
    [InlineData(409, "intento_cerrado")]
    [InlineData(409, "asignacion_cerrada")]
    [InlineData(403, "dispositivo_ajeno")]
    [InlineData(404, "no_encontrado")]
    public async Task UnRechazoDefinitivoDelNodo_DescartaEsaParte(int estado, string codigo)
    {
        using var s = await Abierta();
        s.Responder("q1", R("a"));
        api.ErrorSiguiente = new ErrorAula(estado, codigo, "x", null, null);
        var v = await s.VaciarAsync();
        Assert.Equal((1, 0), (v.Descartados, v.Pendientes));
        Assert.False(v.SinConexion);
    }

    [Theory]
    [InlineData(500, "error")]
    [InlineData(503, "fuente_no_disponible")]
    public async Task UnErrorDelServidorNoDescarta_ConservaYReintenta(int estado, string codigo)
    {
        using var s = await Abierta();
        s.Responder("q1", R("a"));
        api.ErrorSiguiente = new ErrorAula(estado, codigo, "x", null, null);
        var v = await s.VaciarAsync();
        Assert.Equal((0, 1), (v.Descartados, v.Pendientes));
        Assert.Equal(1, (await s.VaciarAsync()).Enviados);
    }

    [Fact]
    public async Task Responder_SoloMientrasElIntentoAceptaRespuestas()
    {
        using var s = Sesion();
        Assert.Throws<InvalidOperationException>(() => s.Responder("q1", R("a")));          // sin examen
        await s.AbrirAsync("a-1");
        s.Responder("q1", R("a"));
        api.EstadoFijo = Estado(EstadosIntento.Entregado);
        await s.LatirAsync();
        Assert.Throws<InvalidOperationException>(() => s.Responder("q2", R("b")));          // ya terminó
    }

    [Fact]
    public async Task EnSuspension_SeSiguenGuardandoLasRespuestas_BR071()
    {
        using var s = await Abierta();
        api.EstadoFijo = Estado(EstadosIntento.Pausado, espera: true, mensaje: new MensajeDeIntento("suspendido", "Tu examen queda en pausa."));
        await s.LatirAsync();
        Assert.Equal(FaseDeExamen.Suspendido, s.Fase);
        Assert.Equal(1, s.Responder("q1", R("a")));                       // lo que ya estaba capturado no se pierde
    }

    [Fact]
    public async Task RespuestaDe_MuestraLaPendienteDeEsteDispositivoSobreLaDelNodo()
    {
        api.Preguntas = Preguntas() with { Respondidas = new() { ["q1"] = new RespuestaGuardada(R("del-nodo"), 1) } };
        using var s = await Abierta();
        Assert.Equal("del-nodo", s.RespuestaDe("q1")!.Value.GetProperty("text").GetString());
        s.Responder("q1", R("mas-reciente"));
        Assert.Equal("mas-reciente", s.RespuestaDe("q1")!.Value.GetProperty("text").GetString());
        Assert.Null(s.RespuestaDe("q4"));
        Assert.Equal(3, s.Faltan);                                          // q2, q3 y q4
        Assert.True(s.Respondida("q1"));
    }

    [Fact]
    public async Task LoYaEnviadoNoSeOlvida_FaltanSigueContandoLoRespondido_YEntregarNoPideConfirmarDeMas()
    {
        using var s = await Abierta();
        foreach (var q in new[] { "q1", "q2", "q3", "q4" }) await s.ResponderYEnviarAsync(q, R("x"));
        Assert.Equal(0, s.PendientesEnDispositivo);                        // la cola se vació al enviar…
        Assert.Equal((0, true), (s.Faltan, s.Respondida("q1")));            // …pero el alumno sigue teniendo todo respondido
        api.Entrega = Entregada();
        var salida = await s.EntregarAsync(confirmar: false);
        Assert.Equal(ResultadoDeEntrega.Entregado, salida.Resultado);       // sin un «Te faltan 4» que no es cierto
    }

    // =========================================================================================== el latido

    [Fact]
    public async Task Latido_LlevaPorDondeVaYLaCapacidad_YAprendeElRelojDelNodo()
    {
        using var s = await Abierta();
        s.IrA("q3");
        var salida = await s.LatirAsync();
        Assert.False(salida.SinConexion);
        var l = api.Latidos.Single();
        Assert.Equal(("q3", Niveles.Controlado), (l.PreguntaActual, l.CapacidadControl));
        Assert.NotNull(l.TranscurridoMs);
        Assert.True(RelojNodo.Aprendido);
        Assert.Equal(580_000, s.Reloj!.RestanteMs);
    }

    [Fact]
    public async Task Latido_SinRed_NoEsUnError_EsSinConexion_YSeAvisaSoloCuandoCambia()
    {
        using var s = await Abierta();
        var avisos = 0;
        s.Cambio += () => avisos++;
        api.SinRed = true;
        var a = await s.LatirAsync();
        Assert.True(a.SinConexion);
        Assert.True(a.Cambio);
        var antes = avisos;
        var b = await s.LatirAsync();
        Assert.True(b.SinConexion);
        Assert.False(b.Cambio);                                             // seguir sin red no repinta
        Assert.Equal(antes, avisos);
        Assert.Equal(FaseDeExamen.EnCurso, s.Fase);                         // el examen sigue
    }

    [Fact]
    public async Task ElNodoSuspende_LaTabletaEsperaAlProfesor_ElBloqueoNoSeSuelta_YAlReactivarVuelveALaNormalidad()
    {
        using var s = await Abierta();
        api.EstadoFijo = Estado(EstadosIntento.Pausado, espera: true, restante: 412_000, mensaje: new MensajeDeIntento("suspendido", "Tu examen queda en pausa."));
        var salida = await s.LatirAsync();
        Assert.True(salida.Cambio);
        Assert.Equal(FaseDeExamen.Suspendido, s.Fase);
        Assert.Equal("suspendido", s.Mensaje!.Codigo);
        Assert.Equal(0, kiosco.Soltadas);
        Assert.True(kiosco.ExamenEnCurso);
        Assert.Equal(412_000, s.RestanteMs);                                // detenido: no baja mientras espera
        api.EstadoFijo = Estado(restante: 412_000);                         // el profesor reactivó
        await s.LatirAsync();
        Assert.Equal(FaseDeExamen.EnCurso, s.Fase);
        Assert.Null(s.Mensaje);
        Assert.Equal(0, kiosco.Soltadas);
    }

    [Fact]
    public async Task ElProfesorDegradaElNivel_LaTabletaSueltaLoQueYaNoSeExige_YLoInforma()
    {
        using var s = await Abierta(Controlado());
        kiosco.Logra = null;
        api.EstadoFijo = Estado(plan: Supervisado);
        await s.LatirAsync();
        Assert.Equal(1, kiosco.Soltadas);                                   // se soltó la capa del sistema…
        Assert.True(kiosco.ExamenEnCurso);                                  // …pero el examen sigue en curso
        Assert.Equal(Supervisado, s.Plan);
        Assert.Equal(ResultadosDeBloqueo.Aplicado, s.UltimoInforme!.Resultado);
        Assert.Null(s.AvisoDeSeguridad);
        Assert.Equal(ResultadosDeBloqueo.Aplicado, api.BloqueosInformados.Last().Resultado);
    }

    [Fact]
    public async Task UnPlanConLasMismasExigencias_NoVuelveAAplicarseEnCadaLatido()
    {
        using var s = await Abierta(Controlado());
        api.EstadoFijo = Estado(plan: Controlado() with { LatidoSeg = 10 });
        for (var i = 0; i < 3; i++) await s.LatirAsync();
        Assert.Empty(kiosco.Planes.Skip(1));
        Assert.Single(api.BloqueosInformados);
    }

    [Fact]
    public async Task ElNodoEntregaPorTiempoAgotado_LoCapturadoAntesSaleYDespuesSeSueltaElBloqueo()
    {
        using var s = await Abierta();
        api.SinRed = true;
        s.Responder("q1", R("capturada-antes-del-corte"));
        api.SinRed = false;
        api.EstadoFijo = Estado(EstadosIntento.Calificado);                 // el nodo entregó
        orden.Clear();
        await s.LatirAsync();
        Assert.Equal(FaseDeExamen.Terminado, s.Fase);
        Assert.Single(api.RespuestasEnviadas);                              // lo capturado antes todavía llega por la gracia
        Assert.True(orden.IndexOf("api:respuestas") < orden.IndexOf("kiosco:soltar"));
        Assert.False(kiosco.ExamenEnCurso);
        Assert.False(kiosco.EnCursoAlSoltar == false, "La bandera debe bajarse DESPUÉS de soltar el bloqueo.");
    }

    [Fact]
    public async Task OtraTabletaTomoElExamen_EstaSeLiberaYNoEscribeMas()
    {
        using var s = await Abierta();
        api.EstadoFijo = Estado(sesionActiva: false, mensaje: new MensajeDeIntento("otra_tableta", "Este examen continúa en otra tableta."));
        await s.LatirAsync();
        Assert.Equal(FaseDeExamen.EnOtraTableta, s.Fase);
        Assert.Equal(1, kiosco.Soltadas);
        Assert.False(kiosco.ExamenEnCurso);
        Assert.Throws<InvalidOperationException>(() => s.Responder("q1", R("a")));
        var latidosAntes = api.Latidos.Count;
        await s.LatirAsync();
        Assert.Equal(latidosAntes, api.Latidos.Count);                      // ya no da señal por un intento que no es suyo
    }

    [Fact]
    public async Task LaVaciadaTrasUnLatidoConRed_ManejaLoQueQuedoEnLaCola()
    {
        using var s = await Abierta();
        api.SinRed = true;
        s.Responder("q1", R("a"));
        await s.LatirAsync();
        api.SinRed = false;
        var latido = await s.LatirAsync();
        Assert.False(latido.SinConexion);
        Assert.Equal(0, s.PendientesEnDispositivo);                         // la red volvió y el latido vació la cola
    }

    // =========================================================================================== los incidentes

    [Fact]
    public async Task UnHechoDelKiosco_SeEncolaConSuRefCliente_YSaleConElSiguienteVaciado()
    {
        using var s = await Abierta();
        kiosco.Disparar(new HechoDeKiosco(TiposDeIncidente.SalidaDeApp, new() { ["via"] = "inicio" }));
        kiosco.Disparar(new HechoDeKiosco(TiposDeIncidente.TeclaBloqueada));
        Assert.Equal(2, s.PendientesEnDispositivo);
        await s.VaciarAsync();
        var enviados = api.IncidentesEnviados.Single();
        Assert.Equal(new[] { "salida_de_app", "tecla_bloqueada" }, enviados.Select(i => i.Tipo));
        Assert.Equal(2, enviados.Select(i => i.RefCliente).Distinct().Count());
        Assert.Equal(0, s.PendientesEnDispositivo);
    }

    [Fact]
    public async Task UnIncidenteReenviadoLlevaLaMismaReferencia_ElNodoNoLoDuplica()
    {
        using var s = await Abierta();
        kiosco.Disparar(new HechoDeKiosco(TiposDeIncidente.CierreBloqueado));
        api.ErrorSiguiente = new ErrorAula(500, "error", "x", null, null);      // el primer envío falla
        await s.VaciarAsync();
        await s.VaciarAsync();                                              // el segundo sale
        Assert.Single(api.IncidentesEnviados);
        var referencia = api.IncidentesEnviados.Single().Single().RefCliente;
        Assert.Matches("^[0-9a-f]{8}-\\d+$", referencia);
    }

    [Fact]
    public async Task LosHechosQueNoSonDeLaTableta_O_SinExamenAbierto_SeIgnoran()
    {
        using var s = Sesion();
        kiosco.Disparar(new HechoDeKiosco(TiposDeIncidente.SalidaDeApp));       // sin examen: nada que informar
        await s.AbrirAsync("a-1");
        kiosco.Disparar(new HechoDeKiosco("desconexion"));                       // un hecho del nodo: la tableta no lo fabrica
        Assert.Equal(0, s.PendientesEnDispositivo);
        s.Dispose();
        kiosco.Disparar(new HechoDeKiosco(TiposDeIncidente.SalidaDeApp));       // desuscrita
    }

    // ============================================================================================== entregar

    [Fact]
    public async Task Entregar_ConPreguntasSinResponder_PideConfirmarYNoLlamaAlNodo()
    {
        using var s = await Abierta();
        s.Responder("q1", R("a"));
        var salida = await s.EntregarAsync(confirmar: false);
        Assert.Equal((ResultadoDeEntrega.NecesitaConfirmar, 3), (salida.Resultado, salida.Faltan));    // «Te faltan 3»
        Assert.Empty(api.Entregas);
        Assert.Equal(0, kiosco.Soltadas);
    }

    [Fact]
    public async Task Entregar_ElBloqueoSeSueltaSoloDespuesDeConfirmarseLaEntrega()
    {
        using var s = await Abierta();
        foreach (var q in new[] { "q1", "q2", "q3", "q4" }) s.Responder(q, R("x"));
        api.Entrega = Entregada();
        orden.Clear();
        var salida = await s.EntregarAsync(confirmar: false);
        Assert.Equal(ResultadoDeEntrega.Entregado, salida.Resultado);
        Assert.Equal(FaseDeExamen.Terminado, s.Fase);
        Assert.True(orden.IndexOf("api:entregar") < orden.IndexOf("kiosco:soltar"), string.Join(" → ", orden));
        Assert.True(orden.IndexOf("api:respuestas") < orden.IndexOf("api:entregar"));     // las respuestas viajan antes que la entrega
        Assert.False(kiosco.ExamenEnCurso);
        Assert.Equal(0, s.PendientesEnDispositivo);
        Assert.Equal("resultado_al_liberar", s.Entrega!.QueSigue.Codigo);
    }

    [Fact]
    public async Task Entregar_ConfirmandoQueFaltanPreguntas_Entrega()
    {
        using var s = await Abierta();
        api.Entrega = Entregada();
        var salida = await s.EntregarAsync(confirmar: true);
        Assert.True(salida.Terminada);
        Assert.True(api.Entregas.Single().Confirmar);
    }

    [Fact]
    public async Task Entregar_SinRed_QuedaGuardada_ElBloqueoSigue_YSaleSolaCuandoVuelveLaConexion()
    {
        using var s = await Abierta();
        foreach (var q in new[] { "q1", "q2", "q3", "q4" }) s.Responder(q, R("x"));
        api.SinRed = true;
        var salida = await s.EntregarAsync(confirmar: false);
        Assert.Equal(ResultadoDeEntrega.GuardadaSinRed, salida.Resultado);
        Assert.Contains("se enviará en cuanto haya conexión", salida.Mensaje);
        Assert.Equal(0, kiosco.Soltadas);                                   // el alumno no queda fuera con el examen a medias… ni suelto
        Assert.True(kiosco.ExamenEnCurso);
        Assert.True(cola.Pendientes("i-1").Single().Entregar);
        api.SinRed = false;
        api.Entrega = Entregada();
        await s.LatirAsync();                                               // vuelve la red: el latido vacía y la entrega sale
        Assert.Equal(FaseDeExamen.Terminado, s.Fase);
        Assert.Single(api.Entregas);
        Assert.Equal(1, kiosco.Soltadas);
        Assert.False(kiosco.ExamenEnCurso);
        Assert.Equal(0, cola.CantidadPendiente());
    }

    [Fact]
    public async Task Entregar_ElNodoPideConfirmar_SeLeDiceCuantasFaltan()
    {
        using var s = await Abierta();
        foreach (var q in new[] { "q1", "q2", "q3", "q4" }) s.Responder(q, R("x"));
        api.ErrorSiguiente = null;
        // el nodo sabe de preguntas que esta tableta no vio: pide confirmar con su lista
        api.Preguntas = Preguntas();
        var extra = Ayudas.Json("""{"faltan":["q9","q10"]}""");
        await s.VaciarAsync();
        api.ErrorSiguiente = new ErrorAula(409, "confirmacion_requerida", "Te faltan 2", null, extra);
        var salida = await s.EntregarAsync(confirmar: false);
        Assert.Equal((ResultadoDeEntrega.NecesitaConfirmar, 2), (salida.Resultado, salida.Faltan));
        Assert.Equal(FaseDeExamen.EnCurso, s.Fase);
        Assert.Equal(0, kiosco.Soltadas);
    }

    [Fact]
    public async Task Entregar_Suspendido_NoLlamaAlNodo_DiceQueSeEsperaAlProfesor()
    {
        using var s = await Abierta();
        api.EstadoFijo = Estado(EstadosIntento.Pausado, espera: true, mensaje: new MensajeDeIntento("suspendido", "Tu examen queda en pausa. Avisa a tu profesor."));
        await s.LatirAsync();
        var salida = await s.EntregarAsync(confirmar: true);
        Assert.Equal(ResultadoDeEntrega.Suspendido, salida.Resultado);
        Assert.Contains("pausa", salida.Mensaje);
        Assert.Empty(api.Entregas);
        Assert.Equal(0, kiosco.Soltadas);
    }

    [Fact]
    public async Task Entregar_YaEntregado_EsIdempotente()
    {
        using var s = await Abierta();
        api.Entrega = Entregada();
        await s.EntregarAsync(confirmar: true);
        var otra = await s.EntregarAsync(confirmar: true);
        Assert.Equal(ResultadoDeEntrega.Entregado, otra.Resultado);
        Assert.Single(api.Entregas);
    }

    [Fact]
    public async Task Entregar_ElNodoRechaza_SeDiceYSeSigueEnElExamen()
    {
        using var s = await Abierta();
        foreach (var q in new[] { "q1", "q2", "q3", "q4" }) s.Responder(q, R("x"));
        await s.VaciarAsync();
        api.ErrorSiguiente = new ErrorAula(403, "dispositivo_ajeno", "Esta tableta no es del intento.", null, null);
        var salida = await s.EntregarAsync(confirmar: false);
        Assert.Equal(ResultadoDeEntrega.Rechazada, salida.Resultado);
        Assert.Equal("Esta tableta no es del intento.", salida.Mensaje);
        Assert.Equal(FaseDeExamen.EnCurso, s.Fase);
        Assert.Equal(0, kiosco.Soltadas);
    }

    [Fact]
    public async Task Entregar_SinExamenAbierto_EsUnUsoIncorrecto()
    {
        using var s = Sesion();
        await Assert.ThrowsAsync<InvalidOperationException>(() => s.EntregarAsync(false));
    }

    // ===================================================================================== salida administrativa

    [Fact]
    public async Task SalidaAdministrativa_SinPinFijado_NoHaySalidaLocal()
    {
        using var s = await Abierta();
        Assert.Equal(ResultadoDePin.SinPin, await s.SalidaAdministrativaAsync("482915"));
        Assert.Equal(FaseDeExamen.EnCurso, s.Fase);
        Assert.Equal(0, kiosco.Soltadas);
    }

    [Fact]
    public async Task SalidaAdministrativa_ConElPinCorrecto_SueltaElBloqueoYElNodoLoSabe()
    {
        var pin = new AlmacenDePin(Path.Combine(carpeta, "pin.json"), 1_000);
        pin.Establecer("482915");
        api.Apertura = Apertura();
        using var s = Sesion(pin);
        await s.AbrirAsync("a-1");
        orden.Clear();
        Assert.Equal(ResultadoDePin.Incorrecto, await s.SalidaAdministrativaAsync("000001"));
        Assert.Equal(0, kiosco.Soltadas);
        Assert.Equal(ResultadoDePin.Correcto, await s.SalidaAdministrativaAsync("482915"));
        Assert.Equal(FaseDeExamen.Liberada, s.Fase);
        Assert.Equal(1, kiosco.Soltadas);
        Assert.False(kiosco.ExamenEnCurso);
        Assert.Equal(ResultadosDeBloqueo.Liberado, api.BloqueosInformados.Last().Resultado);       // el nodo registra «bloqueo liberado» (severidad alta)
        Assert.Contains("PIN", api.BloqueosInformados.Last().Motivo);
    }

    // ================================================================================================ el cronómetro

    [Fact]
    public async Task ElRestanteSoloEsParaPintar_YSinLimiteNoHayCuentaRegresiva()
    {
        api.Apertura = Apertura() with { Reloj = new RelojDeIntento(null, null, true, false, 1_790_000_000_000) };
        using var s = Sesion();
        await s.AbrirAsync("a-1");
        Assert.Null(s.RestanteMs);
        Assert.True(s.TranscurridoMs >= 0);
    }

    [Fact]
    public async Task Cerrar_VuelveASinExamen_PeroNoTocaLoPendienteEnLaCola()
    {
        using var s = await Abierta();
        api.SinRed = true;
        s.Responder("q1", R("a"));
        s.Cerrar();
        Assert.Equal(FaseDeExamen.SinExamen, s.Fase);
        Assert.Null(s.IntentoId);
        Assert.Equal(1, cola.CantidadPendiente("i-1"));                     // lo pendiente sale cuando vuelva la red
    }
}

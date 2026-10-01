using System.Diagnostics;
using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Evaluacion;

/// <summary>En qué momento del examen está la tableta.</summary>
public enum FaseDeExamen
{
    /// <summary>No hay examen abierto en esta tableta.</summary>
    SinExamen,
    /// <summary>Se pidió abrir el intento y el nodo aún no contestó.</summary>
    Abriendo,
    /// <summary>La tableta no alcanza el nivel y el profesor debe decidir: el examen todavía no empezó (BR-075).</summary>
    EsperandoAdmision,
    /// <summary>El reloj corre y el alumno responde.</summary>
    EnCurso,
    /// <summary>El cronómetro está detenido y todo lo respondido está guardado: se espera al profesor (PAN-122). El bloqueo SIGUE puesto.</summary>
    Suspendido,
    /// <summary>La entrega está en marcha o guardada a la espera de la red.</summary>
    Entregando,
    /// <summary>El intento terminó (entregado, en revisión, calificado o anulado) y el bloqueo ya se soltó.</summary>
    Terminado,
    /// <summary>El examen continúa en otra tableta: ésta ya no escribe y se libera.</summary>
    EnOtraTableta,
    /// <summary>Un administrador sacó la tableta del examen con el PIN local (kiosk.md §5.3). El intento sigue en el nodo.</summary>
    Liberada,
}

/// <summary>Los tres valores del estado de guardado (CMP-002): lo que el alumno necesita saber para confiar en que no pierde nada.</summary>
public enum EstadoDeGuardado { GuardadoEnNodo, GuardadoEnDispositivo }

public enum ResultadoDeApertura { Abierto, Reanudado, EsperaAdmision, Rechazada, NoDisponible, SinConexion }

/// <summary>Lo que pasó al abrir. <c>Mensaje</c> es el texto para el alumno (nunca un código crudo).</summary>
public sealed record SalidaDeApertura(ResultadoDeApertura Resultado, string? Mensaje = null, string? Codigo = null)
{
    public bool Empezo => Resultado is ResultadoDeApertura.Abierto or ResultadoDeApertura.Reanudado;
}

public enum ResultadoDeEntrega { Entregado, NecesitaConfirmar, GuardadaSinRed, Suspendido, Rechazada }

/// <summary>Lo que pasó al entregar. Con <see cref="ResultadoDeEntrega.NecesitaConfirmar"/> <c>Faltan</c> trae cuántas preguntas quedan sin responder («Te faltan N»).</summary>
public sealed record SalidaDeEntrega(ResultadoDeEntrega Resultado, EntregaDeIntento? Entrega = null, int Faltan = 0, string? Mensaje = null)
{
    public bool Terminada => Resultado == ResultadoDeEntrega.Entregado;
}

/// <summary>Lo que pasó con un latido: el estado que contestó el nodo (null si no hubo conexión) y si cambió algo que la pantalla deba repintar.</summary>
public sealed record SalidaDeLatido(EstadoDeIntento? Estado, bool SinConexion, bool Cambio);

/// <summary>Cuánto salió, cuánto sigue esperando y cuánto rechazó el nodo de forma definitiva en una pasada de <see cref="SesionDeExamen.VaciarAsync"/>.</summary>
public sealed record ResultadoDeVaciado(int Enviados, int Pendientes, int Descartados, bool SinConexion)
{
    public static readonly ResultadoDeVaciado Nada = new(0, 0, 0, false);
}

/// <summary>
/// El examen de UNA tableta, de punta a punta y sin una sola línea de interfaz (se prueba con dobles de la API y del kiosco): abrir el intento, aplicar el
/// bloqueo que el nodo decide, guardar cada respuesta ANTES de enviarla, dar señal cada 5 s, seguir el plan cuando el profesor lo degrada, esperar al profesor
/// cuando el intento se suspende, entregar y soltar el bloqueo SÓLO cuando la entrega está confirmada.
///
/// Reglas que esta clase hace cumplir:
/// <list type="bullet">
/// <item><b>Lo que el alumno responde se guarda primero en la cola local cifrada</b> (<see cref="ColaExamen"/>) y recién después se intenta enviar; nada se pierde por un corte.</item>
/// <item><b>El reloj es del nodo.</b> La tableta pinta el cronómetro y manda su cuenta monotónica, pero nunca decide cuándo se acaba el tiempo (INV-017).</item>
/// <item><b>La bandera de «examen en curso» se activa ANTES de aplicar el bloqueo</b> y se baja DESPUÉS de soltarlo (kiosk.md §2).</item>
/// <item><b>El bloqueo se libera sólo tras confirmar la entrega</b> (o al ver que el nodo ya entregó, o por la salida administrativa). Si el nodo no responde, el alumno
/// no queda fuera con el examen a medias: la entrega queda guardada y se reintenta; el bloqueo sigue.</item>
/// <item><b>Un bloqueo incompleto se informa y se muestra, no se esconde ni se pisa con mensajes de red</b> (<see cref="AvisoDeSeguridad"/>).</item>
/// <item><b>Suspendido no suelta nada:</b> la pantalla dice que se espera al profesor y el bloqueo sigue puesto.</item>
/// </list>
/// </summary>
public sealed class SesionDeExamen : IDisposable
{
    private const long UmbralDeCola = 5_000;

    private readonly IExamenAlumnoApi api;
    private readonly ColaExamen cola;
    private readonly IKioskService kiosco;
    private readonly string dispositivo;
    private readonly string? alumnoId;
    private readonly DatosDeTableta? tableta;
    private readonly AlmacenDePin? pin;
    private readonly Func<long> ahoraLocal;
    private readonly SemaphoreSlim sincronizando = new(1, 1);
    private readonly Stopwatch cronometro = new();
    private long consumidoBaseMs;
    private bool disposed;
    /// <summary>Lo que el alumno tiene respondido, venga del nodo o de este dispositivo (la cola se vacía al enviar; esto no): de aquí salen «Te faltan N» y lo que se pinta.</summary>
    private readonly Dictionary<string, JsonElement> respondidas = [];

    public SesionDeExamen(IExamenAlumnoApi api, ColaExamen cola, IKioskService kiosco, string dispositivo, string? alumnoId = null, DatosDeTableta? tableta = null,
                          AlmacenDePin? pin = null, Func<long>? ahoraLocal = null)
    {
        this.api = api ?? throw new ArgumentNullException(nameof(api));
        this.cola = cola ?? throw new ArgumentNullException(nameof(cola));
        this.kiosco = kiosco ?? throw new ArgumentNullException(nameof(kiosco));
        ArgumentException.ThrowIfNullOrWhiteSpace(dispositivo);
        this.dispositivo = dispositivo;
        this.alumnoId = alumnoId;
        this.tableta = tableta;
        this.pin = pin;
        this.ahoraLocal = ahoraLocal ?? (() => RelojNodo.LocalMs);
        kiosco.Hecho += AlHecho;
    }

    // ------------------------------------------------------------------------------------- lo que la pantalla lee

    public FaseDeExamen Fase { get; private set; } = FaseDeExamen.SinExamen;
    public string? AsignacionId { get; private set; }
    public string? IntentoId { get; private set; }
    public ResumenDeIntento? Intento { get; private set; }
    public RelojDeIntento? Reloj { get; private set; }
    public PlanDeBloqueo? Plan { get; private set; }
    public CondicionesDeExamen? Condiciones { get; private set; }
    public MensajeDeIntento? Mensaje { get; private set; }
    public PreguntasDeIntento? Preguntas { get; private set; }
    public EntregaDeIntento? Entrega { get; private set; }
    public InformeDeBloqueo? UltimoInforme { get; private set; }
    public string? PreguntaActual { get; private set; }

    /// <summary>Hay un bloqueo incompleto (parcial o fallido): se muestra SIEMPRE al alumno y no lo pisa ningún mensaje de red (kiosk.md §5.2).</summary>
    public string? AvisoDeSeguridad { get; private set; }

    /// <summary>La última vez que el nodo no contestó. Sirve para decir «guardado en este dispositivo» sin alarmar.</summary>
    public bool SinConexion { get; private set; }

    /// <summary>Qué hay activo AHORA según el kiosco (nunca lanza).</summary>
    public string ResumenDeBloqueo => Seguro(() => kiosco.LockdownSummary, "No se pudo consultar el estado del bloqueo.");

    public EstadoDeGuardado Guardado => IntentoId is { } id && cola.CantidadPendiente(id) > 0 ? EstadoDeGuardado.GuardadoEnDispositivo : EstadoDeGuardado.GuardadoEnNodo;

    public int PendientesEnDispositivo => IntentoId is { } id ? cola.CantidadPendiente(id) : 0;

    public event Action? Cambio;

    /// <summary>
    /// Lo que le queda al alumno, en milisegundos, según el nodo y lo transcurrido desde que el nodo lo dijo (nulo si el examen no tiene límite). Con el reloj
    /// detenido o suspendido no baja. Es sólo para pintar: el nodo entrega cuando se acaba (TST-032).
    /// </summary>
    public long? RestanteMs
    {
        get
        {
            if (Reloj is not { RestanteMs: { } restante }) return null;
            return Math.Max(0, restante - (CorreElCronometro ? cronometro.ElapsedMilliseconds : 0));
        }
    }

    /// <summary>Cuánto lleva presentando según esta tableta (lo que consumió el nodo más lo transcurrido desde su última palabra).</summary>
    public long TranscurridoMs => consumidoBaseMs + (CorreElCronometro ? cronometro.ElapsedMilliseconds : 0);

    /// <summary>El nodo dice que el reloj corre y esta tableta sigue presentando (también mientras entrega: el tiempo no se detiene por pulsar «Entregar»).</summary>
    private bool CorreElCronometro => Reloj is { Corriendo: true } && Fase is FaseDeExamen.EnCurso or FaseDeExamen.Entregando;

    // ============================================================================================================ abrir

    /// <summary>
    /// FUN-109. Idempotente: llamarla de nuevo (el alumno que vuelve a pulsar «Comenzar», o la tableta que espera la decisión del profesor) devuelve el
    /// mismo intento. Con la tableta por debajo del nivel el examen NO empieza: <see cref="ResultadoDeApertura.EsperaAdmision"/>.
    /// </summary>
    public async Task<SalidaDeApertura> AbrirAsync(string asignacionId, CancellationToken ct = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(asignacionId);
        if (Fase is FaseDeExamen.EnCurso or FaseDeExamen.Suspendido or FaseDeExamen.Entregando && AsignacionId == asignacionId)
            return new SalidaDeApertura(ResultadoDeApertura.Reanudado);
        var anterior = Fase;
        Fase = FaseDeExamen.Abriendo;
        Avisar();
        var datos = (tableta ?? new DatosDeTableta()) with { CapacidadControl = Seguro(() => kiosco.Capacidad, Niveles.Abierto) };
        var apertura = await api.AbrirAsync(dispositivo, asignacionId, datos, alumnoId, ct);
        if (apertura is null)
        {
            Fase = anterior == FaseDeExamen.Abriendo ? FaseDeExamen.SinExamen : anterior;
            var error = api.UltimoError;
            SinConexion = error is null || error.Estado == 0;
            Avisar();
            return Salida(error);
        }

        SinConexion = false;
        AsignacionId = asignacionId;
        Condiciones = apertura.Condiciones;
        if (apertura.EnEsperaDeAdmision)
        {
            Fase = FaseDeExamen.EsperandoAdmision;
            Intento = apertura.Intento;
            Mensaje = apertura.Mensaje;
            Avisar();
            return new SalidaDeApertura(ResultadoDeApertura.EsperaAdmision, apertura.Mensaje?.Texto, apertura.Mensaje?.Codigo);
        }

        IntentoId = apertura.Intento.Id;
        PreguntaActual = apertura.Intento.PreguntaActual;
        // La secuencia nunca retrocede: si esta instalación perdió su contador (datos borrados, otra tableta) arranca desde lo que el nodo ya aceptó.
        cola.AsegurarSecuenciaMinima(IntentoId, apertura.Intento.SecuenciaMaxima);
        Aplicar(apertura.Intento, apertura.Reloj, apertura.Mensaje, apertura.EsperaReactivacion);
        // La bandera ANTES del bloqueo: el rechazo al cierre debe valer incluso en un equipo sin aprovisionar (kiosk.md §2).
        kiosco.ExamenEnCurso = true;
        await AplicarPlanAsync(apertura.PlanBloqueo ?? PlanDeBloqueo.Libre, ct);
        Avisar();
        return new SalidaDeApertura(apertura.Reanudado ? ResultadoDeApertura.Reanudado : ResultadoDeApertura.Abierto);
    }

    private SalidaDeApertura Salida(ErrorAula? error)
    {
        if (error is null || error.Estado == 0)
            return new SalidaDeApertura(ResultadoDeApertura.SinConexion, "No hay conexión con el aula. Tus respuestas no se pierden; vuelve a intentarlo en un momento.");
        return error.Codigo switch
        {
            "admision_rechazada" => new SalidaDeApertura(ResultadoDeApertura.Rechazada, "Tu profesor no admitió esta tableta para el examen. Pídele que te indique cómo continuar.", error.Codigo),
            "asignacion_no_abierta" or "asignacion_cerrada" => new SalidaDeApertura(ResultadoDeApertura.NoDisponible, "Este examen no está abierto en este momento.", error.Codigo),
            "intentos_agotados" => new SalidaDeApertura(ResultadoDeApertura.NoDisponible, "Ya usaste todos los intentos de este examen.", error.Codigo),
            "version_no_disponible" => new SalidaDeApertura(ResultadoDeApertura.NoDisponible, "El curso cambió de versión y este examen ya no se puede abrir. Avisa a tu profesor.", error.Codigo),
            "fuente_no_disponible" => new SalidaDeApertura(ResultadoDeApertura.NoDisponible, "El aula no puede leer el examen en este momento. Inténtalo de nuevo en un momento.", error.Codigo),
            _ => new SalidaDeApertura(ResultadoDeApertura.NoDisponible, error.Detalle, error.Codigo),
        };
    }

    /// <summary>Pide el examen de este alumno. Con una respuesta guardada sólo en este dispositivo, la pinta encima de lo que dice el nodo.</summary>
    public async Task<bool> CargarPreguntasAsync(CancellationToken ct = default)
    {
        if (IntentoId is not { } id) return false;
        var preguntas = await api.PreguntasAsync(dispositivo, id, alumnoId, ct);
        if (preguntas is null)
        {
            SinConexion = api.UltimoError is null || api.UltimoError.Estado == 0;
            Avisar();
            return false;
        }
        SinConexion = false;
        Preguntas = preguntas;
        PreguntaActual ??= preguntas.PreguntaActual;
        // Lo que el nodo ya tiene se suma a lo conocido; lo pendiente en este dispositivo es MÁS reciente y no se pisa.
        if (preguntas.Respondidas is { } delNodo)
            foreach (var (referencia, guardada) in delNodo)
                if (cola.RespuestaPendiente(id, referencia) is null) respondidas[referencia] = guardada.Respuesta.Clone();
        Avisar();
        return true;
    }

    /// <summary>La respuesta que la pantalla debe mostrar para una pregunta: la pendiente en este dispositivo si la hay (es más reciente) o la que el nodo ya tiene.</summary>
    public JsonElement? RespuestaDe(string preguntaRef) => respondidas.TryGetValue(preguntaRef, out var respuesta) ? respuesta : null;

    public bool Respondida(string preguntaRef) => RespuestaDe(preguntaRef) is not null;

    /// <summary>Cuántas preguntas de su examen aún no tienen respuesta (ni en el nodo ni en este dispositivo).</summary>
    public int Faltan => Preguntas is null ? 0 : Preguntas.Preguntas.Count(p => !Respondida(p.PreguntaRef));

    // ====================================================================================================== responder

    /// <summary>
    /// Guarda una respuesta EN EL DISPOSITIVO y devuelve su secuencia. Va antes que cualquier envío: si el guardado falla, lanza y el alumno se entera; si el
    /// envío falla después, no importa, la cola lo reintenta. Sólo mientras el intento acepta respuestas.
    /// </summary>
    public int Responder(string preguntaRef, JsonElement respuesta)
    {
        if (IntentoId is not { } id || Fase is not (FaseDeExamen.EnCurso or FaseDeExamen.Suspendido))
            throw new InvalidOperationException("No hay un examen abierto que acepte respuestas.");
        var secuencia = cola.Guardar(id, preguntaRef, respuesta);
        respondidas[preguntaRef] = respuesta.Clone();          // sólo si el guardado en el dispositivo tuvo éxito (si falla, Guardar lanza antes)
        PreguntaActual = preguntaRef;
        Avisar();
        return secuencia;
    }

    /// <summary>Atajo para la pantalla: guarda y, sin esperar, intenta enviar lo pendiente (sin red no pasa nada).</summary>
    public async Task<int> ResponderYEnviarAsync(string preguntaRef, JsonElement respuesta, CancellationToken ct = default)
    {
        var secuencia = Responder(preguntaRef, respuesta);
        await VaciarAsync(ct);
        return secuencia;
    }

    /// <summary>Por dónde va el alumno (viaja en el latido). No avisa a la pantalla: es la propia pantalla quien la cambia.</summary>
    public void IrA(string preguntaRef) => PreguntaActual = preguntaRef;

    // ======================================================================================================== latido

    /// <summary>
    /// El punto de recuperación (cada <see cref="PlanDeBloqueo.LatidoSeg"/> segundos): da señal, aprende el reloj del nodo, ajusta el bloqueo si el profesor lo
    /// degradó, detecta la suspensión y la entrega hecha por el nodo, y vacía la cola si hay red. Un fallo de red no es un error: es <c>SinConexion</c>.
    /// </summary>
    public async Task<SalidaDeLatido> LatirAsync(CancellationToken ct = default)
    {
        if (IntentoId is not { } id || Fase is FaseDeExamen.SinExamen or FaseDeExamen.Terminado or FaseDeExamen.Liberada or FaseDeExamen.EnOtraTableta)
            return new SalidaDeLatido(null, false, false);
        var latido = new LatidoDeTableta(PreguntaActual, TranscurridoMs, ahoraLocal(), Seguro(() => kiosco.Capacidad, Niveles.Abierto));
        var estado = await api.LatirAsync(dispositivo, id, latido, alumnoId, ct);
        if (estado is null)
        {
            var error = api.UltimoError;
            var sinRed = error is null || error.Estado == 0 || error.Estado >= 500;
            var cambio = SinConexion != sinRed;
            SinConexion = sinRed;
            if (cambio) Avisar();
            return new SalidaDeLatido(null, sinRed, cambio);
        }

        var huboSinConexion = SinConexion;
        SinConexion = false;
        RelojNodo.Aprender(estado.ServidorEn);
        var anterior = (Fase, Intento?.Estado, Mensaje?.Codigo);
        await AplicarEstadoAsync(estado, ct);
        if (Fase is not (FaseDeExamen.Terminado or FaseDeExamen.EnOtraTableta)) await VaciarAsync(ct);
        var cambioFinal = huboSinConexion || anterior != (Fase, Intento?.Estado, Mensaje?.Codigo);
        if (cambioFinal) Avisar();
        return new SalidaDeLatido(estado, false, cambioFinal);
    }

    private async Task AplicarEstadoAsync(EstadoDeIntento estado, CancellationToken ct)
    {
        Aplicar(estado.Intento, estado.Reloj, estado.Mensaje, estado.EsperaReactivacion);
        if (!estado.SesionActiva)
        {
            // Otra tableta tomó el examen (TST-027): ésta ya no escribe ni mantiene vivo el intento; se libera.
            Fase = FaseDeExamen.EnOtraTableta;
            await SoltarAsync(ct);
            return;
        }
        if (EstadosIntento.Terminado(estado.Intento.Estado))
        {
            // El nodo entregó (tiempo agotado, plazo, cierre forzado del profesor): lo capturado antes todavía llega por la gracia; después se suelta.
            await VaciarAsync(ct);
            Fase = FaseDeExamen.Terminado;
            await SoltarAsync(ct);
            cola.Olvidar(IntentoId!);
            return;
        }
        if (estado.PlanBloqueo is { } plan && !plan.MismasExigencias(Plan)) await AplicarPlanAsync(plan, ct);
    }

    private void Aplicar(ResumenDeIntento intento, RelojDeIntento? reloj, MensajeDeIntento? mensaje, bool esperaReactivacion)
    {
        Intento = intento;
        Mensaje = mensaje;
        if (reloj is not null)
        {
            Reloj = reloj;
            consumidoBaseMs = reloj.ConsumidoMs;
            cronometro.Restart();
        }
        Fase = EstadosIntento.Terminado(intento.Estado) ? FaseDeExamen.Terminado
             : esperaReactivacion || EstadosIntento.Suspendido(intento.Estado) ? FaseDeExamen.Suspendido
             : Fase == FaseDeExamen.Entregando ? FaseDeExamen.Entregando
             : FaseDeExamen.EnCurso;
        if (intento.PreguntaActual is { Length: > 0 } actual && PreguntaActual is null) PreguntaActual = actual;
    }

    // ======================================================================================================== bloqueo

    /// <summary>
    /// Aplica (o reajusta) el plan del nodo y le cuenta lo que LOGRÓ. Un plan que ya no pide nada (el profesor degradó a supervisado o abierto) suelta la capa del
    /// sistema. Un resultado incompleto queda en <see cref="AvisoDeSeguridad"/> hasta que un bloqueo completo lo reemplace.
    /// </summary>
    private async Task AplicarPlanAsync(PlanDeBloqueo plan, CancellationToken ct)
    {
        Plan = plan;
        InformeDeBloqueo informe;
        try
        {
            if (plan.PideAlgo)
                informe = await kiosco.StartExamLockAsync(plan, ct);
            else
            {
                // El profesor degradó el nivel (o el examen nunca pidió bloqueo): se suelta lo que hubiera y se informa que no queda nada por lograr.
                var suelto = await kiosco.StopExamLockAsync(ct);
                informe = PoliticaDeKiosco.Evaluar(plan, suelto.Capas);
            }
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            // Una excepción no es el canal del estado (kiosk.md §5.2), pero una implementación de plataforma puede tropezar: se informa como fallido, con el motivo.
            RegistroLocal.Error(Canal.Dispositivo, "examen.bloqueo_excepcion", "El servicio de kiosco lanzó una excepción al aplicar el plan", new { nivel = plan.Nivel }, ex);
            informe = new InformeDeBloqueo(ResultadosDeBloqueo.Fallido, CapasDeBloqueo.Ninguna, $"El bloqueo no se pudo aplicar: {ex.GetType().Name}.");
        }
        UltimoInforme = informe;
        AvisoDeSeguridad = informe.Completo ? null : PoliticaDeKiosco.Resumen(informe);
        await InformarBloqueoAsync(informe, ct);
    }

    private async Task InformarBloqueoAsync(InformeDeBloqueo informe, CancellationToken ct)
    {
        if (IntentoId is not { } id) return;
        // Se guarda ANTES de enviarlo: un informe de bloqueo que no llega es un profesor que cree que todo está bien.
        cola.PonerBloqueo(id, informe);
        await VaciarAsync(ct);
    }

    private async Task SoltarAsync(CancellationToken ct)
    {
        try { await kiosco.StopExamLockAsync(ct); }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            RegistroLocal.Error(Canal.Dispositivo, "examen.liberar_excepcion", "El servicio de kiosco lanzó una excepción al soltar el bloqueo", null, ex);
        }
        finally
        {
            kiosco.ExamenEnCurso = false;   // DESPUÉS de soltar
        }
        AvisoDeSeguridad = null;
        Plan = null;
        Avisar();
    }

    private void AlHecho(HechoDeKiosco hecho)
    {
        if (disposed || IntentoId is not { } id || !EstadosIntento.AceptaRespuestas(Intento?.Estado) || !TiposDeIncidente.DeLaTableta.Contains(hecho.Tipo)) return;
        // Las salidas y regresos sólo se informan si el plan del nodo las pide (supervisado y controlado). El servicio de plataforma no recibe el plan cuando éste no
        // exige bloqueo, así que emite siempre; en un examen abierto nadie debe ver «salió de la aplicación».
        if (hecho.Tipo is TiposDeIncidente.SalidaDeApp or TiposDeIncidente.RegresoAApp && Plan?.RegistrarSalidas != true) return;
        try
        {
            cola.RegistrarIncidente(id, hecho.Tipo, hecho.Detalle);
            Avisar();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            RegistroLocal.Error(Canal.Escritura, "examen.incidente_no_guardado", "No se pudo guardar un incidente en la cola local", new { tipo = hecho.Tipo }, ex);
        }
    }

    // ====================================================================================================== vaciar la cola

    /// <summary>
    /// Vacía la cola hacia el nodo: incidentes, respuestas, informe de bloqueo y, si ya se pidió, la entrega. Sólo cuando llega el acuse borra lo enviado. Sin
    /// conexión no se pierde nada; un rechazo definitivo (400, 403, 404, 409) descarta SU parte para no reintentarla eternamente. No reentrante.
    /// </summary>
    public async Task<ResultadoDeVaciado> VaciarAsync(CancellationToken ct = default)
    {
        if (!await sincronizando.WaitAsync(0, ct)) return ResultadoDeVaciado.Nada;
        int enviados = 0, descartados = 0;
        var sinConexion = false;
        try
        {
            foreach (var paquete in cola.Pendientes())
            {
                ct.ThrowIfCancellationRequested();
                var corte = await VaciarPaqueteAsync(paquete, ct);
                enviados += corte.Enviados;
                descartados += corte.Descartados;
                if (corte.Cortar)
                {
                    sinConexion = corte.SinConexion;
                    break;
                }
            }
        }
        finally
        {
            sincronizando.Release();
        }
        if (sinConexion != SinConexion && sinConexion) { SinConexion = true; Avisar(); }
        return new ResultadoDeVaciado(enviados, cola.CantidadPendiente(), descartados, sinConexion);
    }

    private readonly record struct Corte(int Enviados, int Descartados, bool Cortar, bool SinConexion);

    private async Task<Corte> VaciarPaqueteAsync(PaqueteDeExamen paquete, CancellationToken ct)
    {
        int enviados = 0, descartados = 0;
        var id = paquete.IntentoId;
        var alumno = alumnoId;

        if (paquete.Incidentes.Count > 0)
        {
            var acuse = await api.EnviarIncidentesAsync(dispositivo, id, paquete.Incidentes, alumno, ct);
            if (acuse is not null) { cola.Reconocer(paquete, PartesDeCola.Incidentes); enviados += paquete.Incidentes.Count; }
            else if (Definitivo(api.UltimoError)) { cola.Descartar(id, PartesDeCola.Incidentes); descartados += paquete.Incidentes.Count; }
            else return new Corte(enviados, descartados, true, EsSinRed(api.UltimoError));
        }

        if (paquete.Respuestas.Count > 0)
        {
            var antiguedad = ahoraLocal() - paquete.EncoladoEn;
            var origen = antiguedad > UmbralDeCola || paquete.Respuestas.Any(r => r.CapturadaEn is { } c && RelojNodo.AhoraMs - c > UmbralDeCola) ? "cola" : "directo";
            var acuse = await api.EnviarRespuestasAsync(dispositivo, id, paquete.Respuestas, origen, id == IntentoId ? PreguntaActual : null,
                                                        id == IntentoId ? TranscurridoMs : null, alumno, ct);
            if (acuse is not null)
            {
                RelojNodo.Aprender(acuse.ServidorEn);
                // Aceptadas, duplicadas, superadas y rechazadas con motivo son todas una respuesta definitiva del nodo: no se reenvían. Una pendiente de
                // decisión del profesor (BR-074) tampoco: el nodo la conserva y nunca la descarta en silencio.
                cola.Reconocer(paquete, PartesDeCola.Respuestas);
                enviados += paquete.Respuestas.Count;
                if (acuse.Rechazadas is { Count: > 0 } rechazadas)
                    RegistroLocal.Advertencia(Canal.Comunicacion, "examen.respuestas_rechazadas", "El nodo rechazó respuestas con su motivo", new { cantidad = rechazadas.Count });
            }
            else if (Definitivo(api.UltimoError)) { cola.Descartar(id, PartesDeCola.Respuestas); descartados += paquete.Respuestas.Count; }
            else return new Corte(enviados, descartados, true, EsSinRed(api.UltimoError));
        }

        if (paquete.Bloqueo is not null)
        {
            var acuse = await api.InformarBloqueoAsync(dispositivo, id, paquete.Bloqueo, alumno, ct);
            if (acuse is not null) { cola.Reconocer(paquete, PartesDeCola.Bloqueo); enviados++; }
            else if (Definitivo(api.UltimoError)) { cola.Descartar(id, PartesDeCola.Bloqueo); descartados++; }
            else return new Corte(enviados, descartados, true, EsSinRed(api.UltimoError));
        }

        if (paquete.Entregar)
        {
            // La entrega que quedó guardada sin red sale en cuanto hay conexión. Las respuestas ya viajaron arriba; aquí no hace falta mandarlas otra vez.
            var entrega = await api.EntregarAsync(dispositivo, id, paquete.Confirmar, null, id == IntentoId ? TranscurridoMs : null, alumno, ct);
            if (entrega is not null)
            {
                cola.Reconocer(paquete, PartesDeCola.Entrega);
                enviados++;
                if (id == IntentoId) await TerminarConEntregaAsync(entrega, ct);
            }
            else
            {
                var error = api.UltimoError;
                // Suspendido o a la espera de confirmar: no es definitivo; se conserva y sale cuando el profesor reactive al alumno.
                if (error?.Codigo is "transicion_invalida" or "confirmacion_requerida" || !Definitivo(error))
                    return new Corte(enviados, descartados, error?.Codigo is not ("transicion_invalida" or "confirmacion_requerida"), EsSinRed(error));
                cola.Descartar(id, PartesDeCola.Entrega);
                descartados++;
            }
        }
        return new Corte(enviados, descartados, false, false);
    }

    private static bool EsSinRed(ErrorAula? error) => error is null || error.Estado == 0;

    /// <summary>Una respuesta del nodo que no se arregla reintentando: 400, 403, 404 y 409 (menos un 5xx, la red o una sesión perdida).</summary>
    private static bool Definitivo(ErrorAula? error) =>
        error is { Estado: >= 400 and < 500, SesionPerdida: false, PersonaAjena: false, Frenado: false };

    // ======================================================================================================== entregar

    /// <summary>
    /// FUN-114. Con preguntas sin responder devuelve <see cref="ResultadoDeEntrega.NecesitaConfirmar"/> («Te faltan N») y NO entrega hasta que el alumno
    /// confirme. Sin red, la entrega queda GUARDADA en el dispositivo y sale sola al volver la conexión: el bloqueo sigue y el alumno no queda fuera con el examen a
    /// medias. El bloqueo se suelta sólo cuando el nodo confirma la entrega.
    /// </summary>
    public async Task<SalidaDeEntrega> EntregarAsync(bool confirmar, CancellationToken ct = default)
    {
        if (IntentoId is not { } id || Fase is FaseDeExamen.SinExamen or FaseDeExamen.Abriendo or FaseDeExamen.EsperandoAdmision)
            throw new InvalidOperationException("No hay un examen abierto que entregar.");
        if (Fase == FaseDeExamen.Terminado) return new SalidaDeEntrega(ResultadoDeEntrega.Entregado, Entrega);
        if (Fase == FaseDeExamen.Suspendido)
            return new SalidaDeEntrega(ResultadoDeEntrega.Suspendido, null, 0, Mensaje?.Texto ?? "Tu examen está en pausa. Avisa a tu profesor para continuar.");

        var faltan = Faltan;
        if (faltan > 0 && !confirmar) return new SalidaDeEntrega(ResultadoDeEntrega.NecesitaConfirmar, null, faltan);

        var antes = Fase;
        Fase = FaseDeExamen.Entregando;
        Avisar();
        await VaciarAsync(ct);   // lo pendiente primero: el nodo recibe las respuestas en orden y la entrega las encuentra
        var entrega = await api.EntregarAsync(dispositivo, id, confirmar, null, TranscurridoMs, alumnoId, ct);
        if (entrega is not null)
        {
            await TerminarConEntregaAsync(entrega, ct);
            return new SalidaDeEntrega(ResultadoDeEntrega.Entregado, entrega);
        }

        var error = api.UltimoError;
        if (EsSinRed(error) || error is { Estado: >= 500 })
        {
            cola.MarcarEntrega(id, confirmar);
            SinConexion = true;
            Avisar();
            return new SalidaDeEntrega(ResultadoDeEntrega.GuardadaSinRed, null, 0,
                "Tu entrega quedó guardada en este dispositivo y se enviará en cuanto haya conexión. No cierres el examen.");
        }

        Fase = antes;
        if (error?.Codigo == "confirmacion_requerida")
        {
            var pendientes = error.Extra is { ValueKind: JsonValueKind.Object } e && e.TryGetProperty("faltan", out var f) && f.ValueKind == JsonValueKind.Array ? f.GetArrayLength() : Math.Max(1, faltan);
            Avisar();
            return new SalidaDeEntrega(ResultadoDeEntrega.NecesitaConfirmar, null, pendientes);
        }
        if (error?.Codigo == "transicion_invalida")
        {
            await LatirAsync(ct);   // aprende que está suspendido o ya entregado
            Avisar();
            return Fase == FaseDeExamen.Terminado
                ? new SalidaDeEntrega(ResultadoDeEntrega.Entregado, Entrega)
                : new SalidaDeEntrega(ResultadoDeEntrega.Suspendido, null, 0, error.Detalle);
        }
        Avisar();
        return new SalidaDeEntrega(ResultadoDeEntrega.Rechazada, null, 0, error?.Detalle ?? "El aula no aceptó la entrega.");
    }

    private async Task TerminarConEntregaAsync(EntregaDeIntento entrega, CancellationToken ct)
    {
        Entrega = entrega;
        Intento = entrega.Intento;
        Fase = FaseDeExamen.Terminado;
        SinConexion = false;
        // La entrega ya está confirmada: AHORA se suelta el bloqueo (kiosk.md §2) y se cuenta (la liberación tras entregar no es un incidente).
        await SoltarAsync(ct);
        // Soltar el bloqueo después de entregar no es un incidente ni hay que informarlo: el intento ya terminó. Lo que quede en la cola (un incidente de
        // último momento) sale en la próxima pasada y, vacía, se olvida el contador.
        if (IntentoId is { } id) cola.Olvidar(id);
        Avisar();
    }

    // =========================================================================================== salida administrativa

    /// <summary>
    /// kiosk.md §5.3: una vía para sacar a un alumno de un examen colgado que no depende del servidor. Con el PIN local correcto suelta el bloqueo; el intento SIGUE
    /// en el nodo (que registra <c>bloqueo_liberado</c> porque se soltó con el examen en marcha). Sin PIN fijado en esta tableta no hay salida local: el profesor
    /// usa el cierre forzado y la tableta se suelta sola al ver el intento entregado.
    /// </summary>
    public async Task<ResultadoDePin> SalidaAdministrativaAsync(string pinIntroducido, CancellationToken ct = default)
    {
        if (pin is null) return ResultadoDePin.SinPin;
        var resultado = pin.Verificar(pinIntroducido ?? "");
        if (resultado != ResultadoDePin.Correcto) return resultado;
        RegistroLocal.Advertencia(Canal.Dispositivo, "examen.salida_administrativa", "Salida administrativa del examen con el PIN local", new { intento = IntentoId });
        if (IntentoId is { } id)
        {
            cola.PonerBloqueo(id, new InformeDeBloqueo(ResultadosDeBloqueo.Liberado, CapasDeBloqueo.Ninguna, "salida administrativa con PIN local"));
            await VaciarAsync(ct);
        }
        Fase = FaseDeExamen.Liberada;
        await SoltarAsync(ct);
        return ResultadoDePin.Correcto;
    }

    // ============================================================================================================ otros

    /// <summary>Vuelve a «sin examen» (el alumno salió de la pantalla de resultado). Lo pendiente en la cola NO se toca.</summary>
    public void Cerrar()
    {
        Fase = FaseDeExamen.SinExamen;
        AsignacionId = IntentoId = null;
        Intento = null;
        Reloj = null;
        Plan = null;
        Preguntas = null;
        Entrega = null;
        Mensaje = null;
        PreguntaActual = null;
        AvisoDeSeguridad = null;
        cronometro.Reset();
        consumidoBaseMs = 0;
        respondidas.Clear();
        Avisar();
    }

    private void Avisar()
    {
        try { Cambio?.Invoke(); }
        catch (Exception) { /* una pantalla que falla no debe tumbar el examen */ }
    }

    private static T Seguro<T>(Func<T> consulta, T respaldo)
    {
        try { return consulta(); }
        catch (Exception) { return respaldo; }   // kiosk.md §5.2: lo que construye un resumen no debe lanzar dentro del catch que reporta un fallo
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        kiosco.Hecho -= AlHecho;
        sincronizando.Dispose();
    }
}

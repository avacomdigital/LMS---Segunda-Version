#if WINDOWS
using System.Runtime.InteropServices;
using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Services;
using Microsoft.UI.Windowing;
using WinWindow = Microsoft.UI.Xaml.Window;
using RectInt32 = global::Windows.Graphics.RectInt32;

namespace Avacom.Lms.Student.Examen;

/// <summary>
/// El bloqueo del examen en Windows (kiosk.md §4): las cuatro piezas que viven en el proceso y la consulta REAL de la que vive en el sistema.
/// <list type="bullet">
/// <item><b>Capa de la aplicación</b>: pantalla completa de verdad (<c>AppWindowPresenterKind.FullScreen</c>, no maximizar), <c>AppWindow.Closing</c> cancelado mientras dure el examen
/// (se engancha UNA vez) y el gancho de teclado <see cref="ExamKeyboardGuard"/>.</item>
/// <item><b>Capturas</b>: <c>SetWindowDisplayAffinity</c> (<c>WDA_EXCLUDEFROMCAPTURE</c>; <c>WDA_MONITOR</c> en compilaciones viejas).</item>
/// <item><b>Pantallas adicionales</b>: <see cref="SecondaryScreenBlocker"/>.</item>
/// <item><b>Capa del sistema</b>: la app NO puede aplicarla; la aprovisionan <c>Install-Kiosk.ps1</c> o <c>Install-ShellLauncher.ps1</c>. Aquí sólo se PREGUNTA al sistema
/// (<see cref="AprovisionamientoWindows"/>), nunca al archivo marcador, y se informa lo que hay.</item>
/// </list>
/// Reglas de diseño (kiosk.md §5): se informa el estado real, no el deseado; un bloqueo parcial se informa, no se oculta; ninguna excepción llega al alumno; y
/// <see cref="LockdownSummary"/> nunca lanza.
///
/// Seguridad del equipo de desarrollo: el gancho de teclado es GLOBAL. El interruptor <c>AVACOM_EXAM_NO_LOCKDOWN=1</c> (kiosk.md §4.6) deja la capa de la aplicación apagada
/// —sin gancho, sin cubrir monitores y con el cierre permitido— para poder probar OPS y Student en el MISMO equipo y volver con Alt+Tab. Se lee en cada llamada, no al arrancar.
/// </summary>
internal sealed class WindowsKioskService : IKioskService, IDisposable
{
    /// <summary>El interruptor de desarrollo (kiosk.md §4.6).</summary>
    public const string InterruptorDeDesarrollo = "AVACOM_EXAM_NO_LOCKDOWN";

    private const uint WdaNone = 0x0;
    private const uint WdaMonitor = 0x1;
    private const uint WdaExcludeFromCapture = 0x11;
    private const long VigenciaDeLaConsultaMs = 5_000;
    private static readonly TimeSpan TopeDeLaConsulta = TimeSpan.FromSeconds(8);
    private static readonly TimeSpan PeriodoDeVigilancia = TimeSpan.FromSeconds(5);
    private static readonly TimeSpan EsperaAntesDeDarSalida = TimeSpan.FromMilliseconds(300);

    private readonly AgregadorDeTeclas agregador = new(() => Environment.TickCount64);
    private bool desechado;

    // ---- lo que otros hilos leen (la sesión, el gancho, los temporizadores)
    private volatile bool examenEnCurso;
    private volatile PlanDeBloqueo? plan;          // el plan que se aplicó (nulo: ninguna capa pedida)
    private volatile bool planResuelto;            // Start o Stop ya contestaron para este examen; mientras no, el cierre se rechaza por prudencia
    private volatile string? motivo;
    private volatile CapasDeBloqueo ultimasCapas = CapasDeBloqueo.Ninguna;
    private volatile bool pantallaCompletaAplicada;

    // ---- la ventana (sólo el hilo de interfaz las toca)
    private WinWindow? nativa;
    private AppWindow? appWindow;
    private IntPtr hwnd;
    private bool ventanaEnganchada;
    private SecondaryScreenBlocker? bloqueador;
    private AppWindowPresenterKind? presentadorPrevio;
    private bool previoMaximizada;
    private RectInt32 previoLimites;
    private bool pantallaCompletaDeArranque;
    private uint afinidad = WdaNone;
    private int extrasInformadas;

    // ---- seguimiento de salidas (lo tocan el hilo de interfaz y un temporizador)
    private readonly object candadoSalida = new();
    private bool ventanaActiva = true;
    private bool salidaInformada;
    private long desdeMs;
    private int versionDeSalida;

    // ---- consulta al sistema
    private readonly object candadoSistema = new();
    private EstadoDeSistema? estadoSistema;
    private long estadoSistemaEn;
    private Task<EstadoDeSistema>? consultaEnCurso;

    // ---- vigilancia periódica: teclas agregadas por minuto y monitores nuevos
    private Timer? vigilancia;
    private int vigilando;

    // ---- entrega ordenada de hechos
    private readonly object candadoHechos = new();
    private Task cadenaDeHechos = Task.CompletedTask;

    public WindowsKioskService()
    {
        // Se calienta la consulta al sistema en segundo plano para que la primera vez que la pantalla pregunte «¿qué capacidad tengo?» ya esté contestada.
        try { Task.Run(() => ConsultarYGuardar()); } catch (Exception) { /* sin calentar: la primera consulta espera */ }
    }

    public event Action<HechoDeKiosco>? Hecho;

    // =================================================================================================== lo que se declara

    public bool IsTrueDeviceLockAvailable
    {
        get
        {
            try { return SistemaConEspera().Aprovisionado; }
            catch (Exception) { return false; }
        }
    }

    /// <summary>La capa de la aplicación existe en Windows salvo que el interruptor de desarrollo la apague: la capacidad declarada refleja eso, no lo deseado.</summary>
    private static bool CapaAppDisponible => !InterruptorActivo();

    public string Capacidad
    {
        get
        {
            try { return PoliticaDeKiosco.CapacidadDeclarable(IsTrueDeviceLockAvailable, CapaAppDisponible); }
            catch (Exception) { return Niveles.Abierto; }
        }
    }

    public string LockdownSummary
    {
        get
        {
            try
            {
                var aplicado = plan;
                if (aplicado is null) return PoliticaDeKiosco.Resumen(null);
                // El informe se recalcula con lo que hay AHORA: el gancho, el estado del sistema… Si Windows retiró algo en silencio, el resumen no lo esconde.
                var vivas = ultimasCapas with
                {
                    Sistema = SistemaSinEsperar()?.Aprovisionado ?? ultimasCapas.Sistema,
                    App = ultimasCapas.App && ExamKeyboardGuard.IsActive,
                };
                return PoliticaDeKiosco.Resumen(PoliticaDeKiosco.Evaluar(aplicado, vivas, motivo));
            }
            catch (Exception)
            {
                return "No se pudo consultar el estado del bloqueo.";
            }
        }
    }

    public bool ExamenEnCurso
    {
        get => examenEnCurso;
        set
        {
            if (examenEnCurso == value) return;
            examenEnCurso = value;
            if (value)
            {
                // Empieza un examen: todavía no se sabe qué plan se aplicará. Se engancha la ventana ya, para ver salidas incluso en un nivel sin capas (supervisado).
                plan = null;
                planResuelto = false;
                try { MainThread.BeginInvokeOnMainThread(() => { try { AsegurarVentana(); } catch (Exception) { /* la ventana aún no existe */ } }); }
                catch (Exception) { /* sin hilo de interfaz (la app se está cerrando) */ }
            }
            else
            {
                plan = null;
                planResuelto = false;
                ReiniciarSeguimientoDeSalida();
            }
        }
    }

    /// <summary>El interruptor de desarrollo, leído AHORA (no se guarda en el arranque).</summary>
    public static bool InterruptorActivo() => Environment.GetEnvironmentVariable(InterruptorDeDesarrollo) == "1";

    /// <summary>El cierre se rechaza mientras dure el examen y la capa de la aplicación esté pedida —o todavía no se sepa qué se pidió— y el interruptor de desarrollo no la apague.</summary>
    private bool RechazaElCierre => examenEnCurso && !InterruptorActivo() && (!planResuelto || plan is { CapaApp: true });

    // ====================================================================================================== pantalla completa

    public async Task EnterFullScreenAsync(CancellationToken ct = default)
    {
        try
        {
            await MainThread.InvokeOnMainThreadAsync(() =>
            {
                if (!AsegurarVentana()) return;
                if (PonerPantallaCompleta()) pantallaCompletaDeArranque = true;
            }).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            RegistroLocal.Advertencia(Canal.Dispositivo, "kiosco.pantalla_completa_arranque", "No se pudo pasar a pantalla completa al arrancar", null, ex);
        }
    }

    // ============================================================================================================== aplicar

    public async Task<InformeDeBloqueo> StartExamLockAsync(PlanDeBloqueo plan, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(plan);
        try
        {
            var sistema = await SistemaFrescoAsync().ConfigureAwait(false);
            return await MainThread.InvokeOnMainThreadAsync(() => Aplicar(plan, sistema)).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            // Nunca queda el gancho puesto tras un fallo: es global y el alumno (o quien desarrolla) se quedaría sin teclado.
            ExamKeyboardGuard.Uninstall();
            RegistroLocal.Error(Canal.Dispositivo, "kiosco.windows_excepcion", "El bloqueo de Windows lanzó una excepción al aplicarse", new { nivel = plan.Nivel }, ex);
            ultimasCapas = CapasDeBloqueo.Ninguna;
            motivo = $"El bloqueo no se pudo aplicar: {ex.GetType().Name}.";
            return new InformeDeBloqueo(ResultadosDeBloqueo.Fallido, CapasDeBloqueo.Ninguna, motivo);
        }
    }

    /// <summary>Aplica el plan EN EL HILO DE INTERFAZ (WinUI y el gancho lo exigen). Reconcilia: aplica lo que el plan pide y suelta lo que ya no pide.</summary>
    private InformeDeBloqueo Aplicar(PlanDeBloqueo nuevo, EstadoDeSistema sistema)
    {
        var notas = new List<string>();
        var interruptor = InterruptorActivo();
        plan = nuevo;
        planResuelto = true;

        if (!AsegurarVentana())
        {
            notas.Add("No hay una ventana de la app sobre la que aplicar el bloqueo.");
            return Terminar(nuevo, new CapasDeBloqueo(sistema.Aprovisionado, false, false, false), notas, sistema);
        }

        bool app = false, capturas = false, pantallas = false;
        if (interruptor && (nuevo.CapaApp || nuevo.CubrirPantallasExtra))
            notas.Add($"Interruptor de desarrollo {InterruptorDeDesarrollo}=1: sin gancho de teclado, con el cierre permitido y sin cubrir otras pantallas. Es un equipo de desarrollo.");

        // ---- capa de la aplicación: pantalla completa + cierre rechazado + gancho de teclado
        if (nuevo.CapaApp)
        {
            var pantalla = Paso(PonerPantallaCompleta, notas, "No se pudo pasar a pantalla completa.");
            if (interruptor)
            {
                ExamKeyboardGuard.Uninstall();
            }
            else
            {
                var gancho = ExamKeyboardGuard.Install(agregador.Registrar, out var codigo);
                if (!gancho) notas.Add($"No se pudo instalar el gancho de teclado (error {codigo} de Windows).");
                // El cierre ya se rechaza (RechazaElCierre lo deduce del plan); ver AlCerrar.
                app = pantalla && gancho;
            }
        }
        else
        {
            Paso(() => { ExamKeyboardGuard.Uninstall(); RestaurarPantallaCompleta(); return true; }, notas, "No se pudo soltar la capa de la aplicación.");
        }

        // ---- capturas
        if (nuevo.BloquearCapturas) capturas = Paso(() => AplicarAfinidad(notas), notas, null);
        else Paso(() => { QuitarAfinidad(); return true; }, notas, "No se pudo soltar el bloqueo de capturas.");

        // ---- monitores adicionales (sólo en modo extendido; en duplicado Windows expone un único display y no hay nada que cubrir)
        if (nuevo.CubrirPantallasExtra && !interruptor) pantallas = Paso(CubrirPantallas, notas, "No se pudo cubrir los monitores adicionales.");
        else Paso(() => { LiberarPantallas(); return true; }, notas, "No se pudo soltar la cobertura de monitores.");

        if (app || pantallas) IniciarVigilancia(); else DetenerVigilancia();

        return Terminar(nuevo, new CapasDeBloqueo(sistema.Aprovisionado, app, capturas, pantallas), notas, sistema);
    }

    private InformeDeBloqueo Terminar(PlanDeBloqueo pedido, CapasDeBloqueo capas, List<string> notas, EstadoDeSistema sistema)
    {
        if (pedido.CapaSistema && !capas.Sistema)
            notas.Add("La capa del sistema no está aprovisionada en este equipo (Assigned Access o Shell Launcher).");
        motivo = notas.Count == 0 ? null : string.Join(" ", notas);
        ultimasCapas = capas;
        var informe = PoliticaDeKiosco.Evaluar(pedido, capas, motivo);
        RegistroLocal.Info(Canal.Dispositivo, "kiosco.windows_aplicado", "Bloqueo de Windows aplicado",
            new { nivel = pedido.Nivel, resultado = informe.Resultado, capas, sistema = sistema.Via, detalle_sistema = sistema.Detalle, motivo });
        return informe;
    }

    /// <summary>Ejecuta un paso del bloqueo sin que una excepción corte los demás ni llegue al alumno. Un fallo es «no lo logré», con su nota.</summary>
    private static bool Paso(Func<bool> paso, List<string> notas, string? fallo)
    {
        try
        {
            if (paso()) return true;
            if (fallo is not null && !notas.Contains(fallo)) notas.Add(fallo);
            return false;
        }
        catch (Exception ex)
        {
            notas.Add($"{fallo ?? "Un paso del bloqueo falló."} ({ex.GetType().Name})");
            RegistroLocal.Advertencia(Canal.Dispositivo, "kiosco.windows_paso", fallo ?? "Un paso del bloqueo falló", null, ex);
            return false;
        }
    }

    // ================================================================================================================ soltar

    public async Task<InformeDeBloqueo> StopExamLockAsync(CancellationToken ct = default)
    {
        try
        {
            return await MainThread.InvokeOnMainThreadAsync(Soltar).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            // Lo más importante, pase lo que pase: que el gancho global no se quede puesto.
            ExamKeyboardGuard.Uninstall();
            plan = null;
            planResuelto = true;
            ultimasCapas = CapasDeBloqueo.Ninguna;
            RegistroLocal.Error(Canal.Dispositivo, "kiosco.windows_liberar_excepcion", "El bloqueo de Windows lanzó una excepción al soltarse", null, ex);
            return new InformeDeBloqueo(ResultadosDeBloqueo.Liberado, CapasDeBloqueo.Ninguna, $"Se soltó el gancho de teclado; el resto no se pudo revertir: {ex.GetType().Name}.");
        }
    }

    private InformeDeBloqueo Soltar()
    {
        var notas = new List<string>();
        // 1. El gancho PRIMERO: es lo único peligroso si algo más falla.
        ExamKeyboardGuard.Uninstall();
        plan = null;
        planResuelto = true;      // ya no se pide nada: el cierre vuelve a estar permitido
        motivo = null;
        ultimasCapas = CapasDeBloqueo.Ninguna;
        DetenerVigilancia();
        Paso(() => { VaciarTeclas(todo: true); return true; }, notas, "No se pudieron informar las últimas teclas descartadas.");
        // 2. El resto, cada paso por su cuenta.
        Paso(() => { LiberarPantallas(); return true; }, notas, "No se pudieron soltar los monitores adicionales.");
        Paso(() => { QuitarAfinidad(); return true; }, notas, "No se pudo soltar el bloqueo de capturas.");
        Paso(() => { RestaurarPantallaCompleta(); return true; }, notas, "No se pudo restaurar la ventana.");
        extrasInformadas = 0;
        ReiniciarSeguimientoDeSalida();
        RegistroLocal.Info(Canal.Dispositivo, "kiosco.windows_liberado", "Bloqueo de Windows liberado", notas.Count == 0 ? null : new { notas });
        return new InformeDeBloqueo(ResultadosDeBloqueo.Liberado, CapasDeBloqueo.Ninguna, notas.Count == 0 ? null : string.Join(" ", notas));
    }

    // ================================================================================================================ ventana

    /// <summary>La ventana nativa de la app, enganchada una sola vez. Hilo de interfaz. Falso si todavía no existe.</summary>
    private bool AsegurarVentana()
    {
        var ventana = Application.Current?.Windows.FirstOrDefault()?.Handler?.PlatformView as WinWindow;
        if (ventana is null) return false;
        if (!ReferenceEquals(ventana, nativa))
        {
            DesengancharVentana();
            nativa = ventana;
            appWindow = ventana.AppWindow;
            hwnd = WinRT.Interop.WindowNative.GetWindowHandle(ventana);
            presentadorPrevio = null;
        }
        if (!ventanaEnganchada)
        {
            // AppWindow.Closing se engancha UNA vez por ventana; los demás eventos también.
            appWindow!.Closing += AlCerrar;
            nativa!.Activated += AlActivar;
            nativa.Closed += AlCerrarseLaVentana;
            ventanaEnganchada = true;
        }
        return true;
    }

    private void DesengancharVentana()
    {
        if (nativa is null || !ventanaEnganchada) return;
        try
        {
            appWindow!.Closing -= AlCerrar;
            nativa.Activated -= AlActivar;
            nativa.Closed -= AlCerrarseLaVentana;
        }
        catch (Exception) { /* la ventana ya no existe */ }
        ventanaEnganchada = false;
    }

    private bool PonerPantallaCompleta()
    {
        var aw = appWindow ?? throw new InvalidOperationException("Sin ventana.");
        if (aw.Presenter.Kind == AppWindowPresenterKind.FullScreen)
        {
            pantallaCompletaAplicada = true;
            return true;
        }
        if (presentadorPrevio is null)
        {
            presentadorPrevio = aw.Presenter.Kind;
            previoMaximizada = aw.Presenter is OverlappedPresenter { State: OverlappedPresenterState.Maximized };
            previoLimites = new RectInt32(aw.Position.X, aw.Position.Y, aw.Size.Width, aw.Size.Height);
        }
        aw.SetPresenter(AppWindowPresenterKind.FullScreen);
        pantallaCompletaAplicada = aw.Presenter.Kind == AppWindowPresenterKind.FullScreen;
        return pantallaCompletaAplicada;
    }

    /// <summary>Devuelve la ventana a como estaba antes del examen. Si la pantalla completa se pidió desde el arranque (cuenta dedicada), se queda como está.</summary>
    private void RestaurarPantallaCompleta()
    {
        pantallaCompletaAplicada = pantallaCompletaDeArranque && pantallaCompletaAplicada;
        if (pantallaCompletaDeArranque || appWindow is null || presentadorPrevio is null) return;
        var aw = appWindow;
        var previo = presentadorPrevio.Value;
        presentadorPrevio = null;
        pantallaCompletaAplicada = false;
        if (aw.Presenter.Kind != AppWindowPresenterKind.FullScreen) return;      // alguien ya la sacó de pantalla completa
        aw.SetPresenter(previo == AppWindowPresenterKind.FullScreen ? AppWindowPresenterKind.Default : previo);
        if (aw.Presenter is OverlappedPresenter overlapped)
        {
            if (previoMaximizada) overlapped.Maximize();
            else
            {
                overlapped.Restore();
                aw.MoveAndResize(previoLimites);
            }
        }
    }

    private bool AplicarAfinidad(List<string> notas)
    {
        if (hwnd == IntPtr.Zero) return false;
        if (afinidad != WdaNone) return true;
        if (SetWindowDisplayAffinity(hwnd, WdaExcludeFromCapture)) { afinidad = WdaExcludeFromCapture; return true; }
        var error = Marshal.GetLastWin32Error();
        // Antes de Windows 10 2004 (compilación 19041) no existe EXCLUDEFROMCAPTURE: WDA_MONITOR muestra la ventana en negro en la captura.
        if (SetWindowDisplayAffinity(hwnd, WdaMonitor))
        {
            afinidad = WdaMonitor;
            RegistroLocal.Info(Canal.Dispositivo, "kiosco.capturas_monitor", "Se usó WDA_MONITOR para bloquear las capturas (Windows anterior a la compilación 19041)", new { error });
            return true;
        }
        notas.Add($"No se pudo bloquear las capturas (error {error} de Windows).");
        return false;
    }

    private void QuitarAfinidad()
    {
        if (afinidad == WdaNone || hwnd == IntPtr.Zero) return;
        afinidad = WdaNone;
        SetWindowDisplayAffinity(hwnd, WdaNone);
    }

    private bool CubrirPantallas()
    {
        if (nativa is null) return false;
        var examen = nativa;
        bloqueador ??= new SecondaryScreenBlocker(
            examen.AppWindow.Id,
            () => MainThread.BeginInvokeOnMainThread(() => { try { nativa?.Activate(); } catch (Exception) { /* sin ventana */ } }));
        SincronizarPantallas();
        return true;      // sin monitores adicionales no hay nada sin cubrir: la capa está lograda
    }

    /// <summary>Cubre los monitores que hay ahora y avisa (<c>pantalla_adicional</c>) cuando aparece uno más de los que ya se habían informado. Hilo de interfaz.</summary>
    private void SincronizarPantallas()
    {
        if (bloqueador is null) return;
        var cantidad = bloqueador.Sincronizar();
        if (cantidad > extrasInformadas) Emitir(TiposDeIncidente.PantallaAdicional, new() { ["cantidad"] = cantidad });
        extrasInformadas = cantidad;
    }

    private void LiberarPantallas()
    {
        var b = bloqueador;
        bloqueador = null;
        extrasInformadas = 0;
        b?.Dispose();
    }

    // ======================================================================================================== eventos de la ventana

    private void AlCerrar(AppWindow sender, AppWindowClosingEventArgs args)
    {
        try
        {
            if (!RechazaElCierre) return;
            args.Cancel = true;
            // Con el gancho puesto Alt+F4 ni llega aquí (se traga antes); si llega, el teclado sigue pulsado y se distingue de un cierre por otra vía.
            Emitir(TiposDeIncidente.CierreBloqueado, new() { ["via"] = ExamKeyboardGuard.AltF4Pulsadas() ? "alt_f4" : "cierre" });
        }
        catch (Exception) { /* un fallo al informar no debe dejar cerrar la ventana a medio examen ni tumbar la app */ }
    }

    private void AlActivar(object sender, Microsoft.UI.Xaml.WindowActivatedEventArgs args)
    {
        try
        {
            if (!examenEnCurso) return;
            var sinFoco = args.WindowActivationState == Microsoft.UI.Xaml.WindowActivationState.Deactivated;
            lock (candadoSalida)
            {
                if (sinFoco)
                {
                    if (!ventanaActiva) return;
                    ventanaActiva = false;
                    desdeMs = RelojNodo.AhoraMs;
                    var version = ++versionDeSalida;
                    // Se espera un instante antes de dar la salida: un cuadro de diálogo o una cubierta de monitor de ESTA app quita el foco unos milisegundos y no es salir.
                    _ = Task.Delay(EsperaAntesDeDarSalida).ContinueWith(_ => ConfirmarSalida(version), TaskScheduler.Default);
                }
                else
                {
                    ventanaActiva = true;
                    versionDeSalida++;
                    if (!salidaInformada) return;
                    salidaInformada = false;
                    var hasta = RelojNodo.AhoraMs;
                    Emitir(TiposDeIncidente.RegresoAApp, new() { ["desde"] = desdeMs, ["hasta"] = hasta, ["fuera_ms"] = Math.Max(0, hasta - desdeMs) });
                }
            }
        }
        catch (Exception) { /* informar una salida no debe tumbar la ventana */ }
    }

    private void ConfirmarSalida(int version)
    {
        try
        {
            lock (candadoSalida)
            {
                if (version != versionDeSalida || ventanaActiva || salidaInformada || !examenEnCurso) return;
                if (EsDeEsteProceso(GetForegroundWindow())) return;      // otra ventana de la propia app tiene el foco: no salió
                salidaInformada = true;
                Emitir(TiposDeIncidente.SalidaDeApp, new() { ["desde"] = desdeMs });
            }
        }
        catch (Exception) { /* de mejor esfuerzo */ }
    }

    private void ReiniciarSeguimientoDeSalida()
    {
        lock (candadoSalida)
        {
            ventanaActiva = true;
            salidaInformada = false;
            versionDeSalida++;
        }
    }

    /// <summary>La ventana se cerró de verdad (el cierre estaba permitido): ni gancho, ni cubiertas, ni temporizadores quedan vivos.</summary>
    private void AlCerrarseLaVentana(object sender, Microsoft.UI.Xaml.WindowEventArgs args)
    {
        try
        {
            ExamKeyboardGuard.Uninstall();
            DetenerVigilancia();
            LiberarPantallas();
            ventanaEnganchada = false;
            nativa = null;
            appWindow = null;
            hwnd = IntPtr.Zero;
            afinidad = WdaNone;
            ultimasCapas = CapasDeBloqueo.Ninguna;
            pantallaCompletaAplicada = false;
        }
        catch (Exception) { /* la ventana ya se está yendo */ }
    }

    // ============================================================================================================ vigilancia periódica

    private void IniciarVigilancia()
    {
        vigilancia ??= new Timer(_ => Vigilar(), null, PeriodoDeVigilancia, PeriodoDeVigilancia);
    }

    private void DetenerVigilancia()
    {
        var t = vigilancia;
        vigilancia = null;
        t?.Dispose();
    }

    /// <summary>Cada pocos segundos, en un hilo del grupo: entrega las teclas de los minutos ya terminados y revisa si apareció un monitor nuevo.</summary>
    private void Vigilar()
    {
        if (Interlocked.Exchange(ref vigilando, 1) == 1) return;
        try
        {
            VaciarTeclas(todo: false);
            if (bloqueador is not null) MainThread.BeginInvokeOnMainThread(() => { try { SincronizarPantallas(); } catch (Exception) { /* la siguiente pasada lo reintenta */ } });
        }
        catch (Exception) { /* de mejor esfuerzo */ }
        finally { Volatile.Write(ref vigilando, 0); }
    }

    /// <summary>UN incidente <c>tecla_bloqueada</c> por minuto (modelado-datos.md §4.7), no uno por pulsación.</summary>
    private void VaciarTeclas(bool todo)
    {
        foreach (var resumen in todo ? agregador.VaciarTodo() : agregador.Vaciar())
            Emitir(TiposDeIncidente.TeclaBloqueada, resumen.Detalle());
    }

    // ================================================================================================================ hechos

    /// <summary>
    /// Entrega un hecho a la sesión, en orden y SIN bloquear a quien lo vio: la sesión guarda cada incidente en una cola cifrada en disco, y el hilo de interfaz (o el gancho
    /// de teclado) no puede esperar por eso.
    /// </summary>
    private void Emitir(string tipo, Dictionary<string, object?>? detalle = null)
    {
        var hecho = new HechoDeKiosco(tipo, detalle);
        lock (candadoHechos)
        {
            cadenaDeHechos = cadenaDeHechos.ContinueWith(_ =>
            {
                try { Hecho?.Invoke(hecho); }
                catch (Exception ex) { RegistroLocal.Advertencia(Canal.Dispositivo, "kiosco.hecho_no_entregado", "Quien escucha los hechos del kiosco lanzó una excepción", new { tipo }, ex); }
            }, CancellationToken.None, TaskContinuationOptions.None, TaskScheduler.Default);
        }
    }

    // ================================================================================================= consulta al sistema operativo

    /// <summary>Para las propiedades síncronas: la respuesta vigente, o la consulta nueva con un tope. Nunca lanza.</summary>
    private EstadoDeSistema SistemaConEspera()
    {
        Task<EstadoDeSistema> espera;
        lock (candadoSistema)
        {
            if (estadoSistema is not null && Environment.TickCount64 - estadoSistemaEn < VigenciaDeLaConsultaMs) return estadoSistema;
            consultaEnCurso ??= Task.Run(ConsultarYGuardar);
            // Con una respuesta anterior se devuelve ESA mientras se refresca en segundo plano: el hilo de interfaz no se queda esperando al sistema.
            if (estadoSistema is not null) return estadoSistema;
            espera = consultaEnCurso;
        }
        return espera.Wait(TopeDeLaConsulta) ? espera.Result : EstadoDeSistema.No("La consulta al sistema tardó demasiado.");
    }

    /// <summary>Para el resumen: lo último que se supo, sin esperar a nadie (y refrescándolo si caducó).</summary>
    private EstadoDeSistema? SistemaSinEsperar()
    {
        lock (candadoSistema)
        {
            if (estadoSistema is null || Environment.TickCount64 - estadoSistemaEn >= VigenciaDeLaConsultaMs) consultaEnCurso ??= Task.Run(ConsultarYGuardar);
            return estadoSistema;
        }
    }

    /// <summary>Para aplicar el bloqueo: una consulta vigente o nueva, esperada sin bloquear el hilo.</summary>
    private async Task<EstadoDeSistema> SistemaFrescoAsync()
    {
        Task<EstadoDeSistema> consulta;
        lock (candadoSistema)
        {
            if (estadoSistema is not null && Environment.TickCount64 - estadoSistemaEn < VigenciaDeLaConsultaMs) return estadoSistema;
            consulta = consultaEnCurso ??= Task.Run(ConsultarYGuardar);
        }
        try { return await consulta.WaitAsync(TopeDeLaConsulta).ConfigureAwait(false); }
        catch (TimeoutException) { return EstadoDeSistema.No("La consulta al sistema tardó demasiado."); }
    }

    private EstadoDeSistema ConsultarYGuardar()
    {
        EstadoDeSistema resultado;
        try { resultado = AprovisionamientoWindows.Consultar(); }
        catch (Exception ex) { resultado = EstadoDeSistema.No($"La consulta al sistema falló: {ex.GetType().Name}."); }
        lock (candadoSistema)
        {
            estadoSistema = resultado;
            estadoSistemaEn = Environment.TickCount64;
            consultaEnCurso = null;
        }
        return resultado;
    }

    // ================================================================================================================== desechar

    public void Dispose()
    {
        if (desechado) return;
        desechado = true;
        ExamKeyboardGuard.Uninstall();
        DetenerVigilancia();
        try
        {
            MainThread.BeginInvokeOnMainThread(() =>
            {
                try { LiberarPantallas(); QuitarAfinidad(); DesengancharVentana(); }
                catch (Exception) { /* la ventana ya no está */ }
            });
        }
        catch (Exception) { /* sin hilo de interfaz */ }
    }

    // ===================================================================================================================== Win32

    private static bool EsDeEsteProceso(IntPtr ventana)
    {
        if (ventana == IntPtr.Zero) return false;
        GetWindowThreadProcessId(ventana, out var proceso);
        return proceso == (uint)Environment.ProcessId;
    }

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetWindowDisplayAffinity(IntPtr hWnd, uint dwAffinity);

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
}
#endif

#if ANDROID
#pragma warning disable CA1416 // las llamadas por versión de Android se protegen con Build.VERSION.SdkInt
#pragma warning disable CA1422 // APIs en desuso que siguen siendo las únicas por debajo de la API 30
using Android.App;
using Android.App.Admin;
using Android.Content;
using Android.Hardware.Display;
using Android.OS;
using Android.Views;
using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Services;
using AndroidActivity = Android.App.Activity;
using OperationCanceledException = System.OperationCanceledException;
using AndroidActivityManager = Android.App.ActivityManager;

namespace Avacom.Lms.Student.Examen;

/// <summary>
/// El bloqueo del examen en Android (kiosk.md §3): Device Owner + Lock Task de <c>DevicePolicyManager</c> (la capa del sistema) más la capa de la aplicación en la Activity
/// (barras ocultas, Atrás ignorado, pantalla encendida, FLAG_SECURE). Son APIs nativas: nada de esto es específico de MAUI.
///
/// Reglas que esta clase hace cumplir:
/// <list type="bullet">
/// <item><b>El orden de §3.3, exacto:</b> <c>SetLockTaskPackages</c> → comprobar <c>IsLockTaskPermitted</c> → <c>SetLockTaskFeatures(None)</c> (sólo API 28+; el proyecto llega a la 21)
/// → <c>AddUserRestriction(DisallowCreateWindows)</c> → <c>StartLockTask</c> → ocultar la interfaz del sistema.</item>
/// <item><b>Todo en el hilo de interfaz, con el error devuelto al llamador</b> (<see cref="RunOnUiThreadAsync{T}"/>, un puente con <see cref="TaskCompletionSource{TResult}"/>): sin él, una
/// excepción dentro de <c>RunOnUiThread</c> —por ejemplo, una tableta que no es Device Owner— subiría por el hilo de interfaz y cerraría la app en pleno examen.</item>
/// <item><b>Informar el estado real:</b> <see cref="IsTrueDeviceLockAvailable"/> es <c>IsDeviceOwnerApp</c> (una consulta al sistema, no un archivo), y la capa del sistema sólo se
/// informa lograda si, tras <c>StartLockTask</c>, el sistema dice que la tarea quedó bloqueada (<c>Locked</c>, no el simple fijado de pantalla).</item>
/// <item>Sin Device Owner la capa de la aplicación funciona igual y el resultado es <b>parcial</b> (o fallido si sólo se pedía la del sistema), nunca una excepción.</item>
/// </list>
/// La Activity y este servicio comparten estado por <see cref="Actual"/>. El apagado forzado por hardware no lo impide ningún software (kiosk.md §7).
/// </summary>
internal sealed class AndroidKioskService : IKioskService
{
    private static readonly TimeSpan EsperaParaVerificarLockTask = TimeSpan.FromMilliseconds(500);

    /// <summary>La instancia viva (una por proceso); la usa <c>MainActivity</c> para consultar la bandera y avisar de lo que ve la Activity. Puede ser nula antes de que exista.</summary>
    public static AndroidKioskService? Actual { get; private set; }

    private volatile bool examenEnCurso;
    private volatile PlanDeBloqueo? plan;
    private volatile bool planResuelto;
    private volatile string? motivo;
    private volatile CapasDeBloqueo ultimasCapas = CapasDeBloqueo.Ninguna;

    // Lo que se aplicó y hay que revertir (sólo el hilo de interfaz lo toca).
    private bool lockTaskPuesto;
    private bool restriccionPuesta;
    private bool capaAppPuesta;
    private volatile bool pantallaCompletaDeArranque;

    // Salidas (OnPause / OnResume).
    private readonly object candadoSalida = new();
    private bool salidaInformada;
    private long desdeMs;

    private readonly object candadoHechos = new();
    private Task cadenaDeHechos = Task.CompletedTask;

    public AndroidKioskService() => Actual = this;

    public event Action<HechoDeKiosco>? Hecho;

    // =================================================================================================== lo que se declara

    /// <summary>¿Es esta app el Device Owner de la tableta? Una consulta real a <c>DevicePolicyManager</c>; nunca lanza.</summary>
    public bool IsTrueDeviceLockAvailable
    {
        get
        {
            try
            {
                var contexto = Platform.CurrentActivity ?? (Context)Android.App.Application.Context;
                return Politicas(contexto)?.IsDeviceOwnerApp(contexto.PackageName) == true;
            }
            catch (Exception) { return false; }
        }
    }

    public string Capacidad
    {
        get
        {
            try { return PoliticaDeKiosco.CapacidadDeclarable(IsTrueDeviceLockAvailable, capaApp: true); }
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
                var vivas = ultimasCapas with { Sistema = ultimasCapas.Sistema && IsTrueDeviceLockAvailable };
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
            plan = null;
            planResuelto = false;
            if (!value) lock (candadoSalida) salidaInformada = false;
        }
    }

    /// <summary>
    /// La capa de la aplicación vale mientras dure el examen y se haya pedido —o todavía no se sepa qué se pidió: el rechazo debe valer incluso antes de que el bloqueo termine
    /// de aplicarse (kiosk.md §2)—. En un nivel que no la pide (abierto, supervisado) Atrás y las barras funcionan como siempre.
    /// </summary>
    public bool CapaAppVigente => examenEnCurso && (!planResuelto || plan is { CapaApp: true });

    // ===================================================================================================== pantalla completa

    public async Task EnterFullScreenAsync(CancellationToken ct = default)
    {
        pantallaCompletaDeArranque = true;       // la Activity la reaplica en cada ganancia de foco
        try
        {
            await RunOnUiThreadAsync(() =>
            {
                var actividad = Platform.CurrentActivity ?? throw new InvalidOperationException("No hay una pantalla activa.");
                actividad.Window?.AddFlags(WindowManagerFlags.KeepScreenOn);
                OcultarBarras(actividad);
                return true;
            }).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            // Sin Activity todavía: no es un fallo, la Activity lo aplicará al ganar el foco.
            RegistroLocal.Advertencia(Canal.Dispositivo, "kiosco.pantalla_completa_arranque", "No se pudo ocultar la interfaz del sistema al arrancar", null, ex);
        }
    }

    // ============================================================================================================== aplicar

    private sealed class ResultadoUi
    {
        public bool App { get; init; }
        public bool Capturas { get; init; }
        public bool Pantallas { get; init; }
        public bool LockTaskIntentado { get; init; }
        public required List<string> Notas { get; init; }
    }

    public async Task<InformeDeBloqueo> StartExamLockAsync(PlanDeBloqueo plan, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(plan);
        try
        {
            var primero = await RunOnUiThreadAsync(() => AplicarEnUi(plan)).ConfigureAwait(false);
            var notas = primero.Notas;
            var sistema = false;
            if (primero.LockTaskIntentado)
            {
                // startLockTask() surte efecto de forma asíncrona: se le da un instante y se PREGUNTA al sistema; no se da por hecho.
                await Task.Delay(EsperaParaVerificarLockTask, ct).ConfigureAwait(false);
                sistema = await RunOnUiThreadAsync(() => VerificarLockTask(notas)).ConfigureAwait(false);
            }
            return Terminar(plan, new CapasDeBloqueo(sistema, primero.App, primero.Capturas, primero.Pantallas), notas);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            // Una excepción (por ejemplo «no es Device Owner», o sin Activity) vuelve como informe tipado: NUNCA llega al alumno ni tumba la app.
            RegistroLocal.Error(Canal.Dispositivo, "kiosco.android_excepcion", "El bloqueo de Android lanzó una excepción al aplicarse", new { nivel = plan.Nivel }, ex);
            ultimasCapas = CapasDeBloqueo.Ninguna;
            motivo = $"El bloqueo no se pudo aplicar: {ex.GetType().Name}.";
            this.plan = plan;
            planResuelto = true;
            return new InformeDeBloqueo(ResultadosDeBloqueo.Fallido, CapasDeBloqueo.Ninguna, motivo);
        }
    }

    private InformeDeBloqueo Terminar(PlanDeBloqueo pedido, CapasDeBloqueo capas, List<string> notas)
    {
        motivo = notas.Count == 0 ? null : string.Join(" ", notas);
        ultimasCapas = capas;
        var informe = PoliticaDeKiosco.Evaluar(pedido, capas, motivo);
        RegistroLocal.Info(Canal.Dispositivo, "kiosco.android_aplicado", "Bloqueo de Android aplicado", new { nivel = pedido.Nivel, resultado = informe.Resultado, capas, motivo });
        return informe;
    }

    /// <summary>Aplica el plan EN EL HILO DE INTERFAZ. Reconcilia: aplica lo que el plan pide y suelta lo que ya no pide. Puede lanzar: <see cref="RunOnUiThreadAsync{T}"/> lo devuelve al llamador.</summary>
    private ResultadoUi AplicarEnUi(PlanDeBloqueo nuevo)
    {
        var actividad = Platform.CurrentActivity ?? throw new InvalidOperationException("No hay una pantalla (Activity) activa donde aplicar el bloqueo.");
        var notas = new List<string>();
        plan = nuevo;
        planResuelto = true;

        // ---- capa de la aplicación: barras ocultas (y reaplicadas al ganar foco), Atrás ignorado (MainActivity), pantalla encendida
        var app = false;
        if (nuevo.CapaApp)
        {
            try
            {
                actividad.Window?.AddFlags(WindowManagerFlags.KeepScreenOn);
                OcultarBarras(actividad);
                capaAppPuesta = true;
                app = actividad is MainActivity;
                if (!app) notas.Add("La pantalla actual no es la actividad principal de la app: Atrás no se puede ignorar.");
            }
            catch (Exception ex)
            {
                notas.Add($"No se pudo aplicar la capa de la aplicación ({ex.GetType().Name}).");
                RegistroLocal.Advertencia(Canal.Dispositivo, "kiosco.android_capa_app", "No se pudo aplicar la capa de la aplicación", null, ex);
            }
        }
        else SoltarCapaApp(actividad, notas);

        // ---- capturas: FLAG_SECURE
        var capturas = false;
        if (nuevo.BloquearCapturas)
        {
            try { actividad.Window?.AddFlags(WindowManagerFlags.Secure); capturas = true; }
            catch (Exception ex) { notas.Add($"No se pudo bloquear las capturas ({ex.GetType().Name})."); }
        }
        else
        {
            try { actividad.Window?.ClearFlags(WindowManagerFlags.Secure); } catch (Exception) { /* sin ventana */ }
        }

        // ---- pantallas adicionales: Android no tiene un equivalente al bloqueador de monitores (kiosk.md §7); se CONSULTA cuántas hay y, si hay una (cable, Miracast), se informa que no se pudo cubrir
        var pantallas = false;
        if (nuevo.CubrirPantallasExtra)
        {
            var extras = ContarPantallasAdicionales(actividad);
            pantallas = extras == 0;
            if (extras > 0)
            {
                notas.Add($"Hay {extras} pantalla(s) adicional(es) conectada(s) y Android no permite cubrirlas.");
                Emitir(TiposDeIncidente.PantallaAdicional, new() { ["cantidad"] = extras });
            }
        }

        // ---- capa del sistema: Device Owner + Lock Task (kiosk.md §3.3)
        var intentado = false;
        if (nuevo.CapaSistema) intentado = IntentarLockTask(actividad, notas);
        else SoltarLockTask(actividad, notas);

        return new ResultadoUi { App = app, Capturas = capturas, Pantallas = pantallas, LockTaskIntentado = intentado, Notas = notas };
    }

    /// <summary>Los seis pasos de §3.3 en su orden exacto. Falso, con la razón en <paramref name="notas"/>, si no se pudo; nunca lanza.</summary>
    private bool IntentarLockTask(AndroidActivity actividad, List<string> notas)
    {
        var paquete = actividad.PackageName ?? throw new InvalidOperationException("La Activity no conoce su paquete.");
        var politicas = Politicas(actividad);
        if (politicas is null || !politicas.IsDeviceOwnerApp(paquete))
        {
            notas.Add("La app no es Device Owner de esta tableta: la capa del sistema (Lock Task) no se puede aplicar.");
            return false;
        }
        var administrador = new ComponentName(paquete, ExamDeviceAdminReceiver.NombreCompleto);
        try
        {
            politicas.SetLockTaskPackages(administrador, [paquete]);                                   // 1. autorizar
            if (!politicas.IsLockTaskPermitted(paquete))                                              // 2. comprobar
                throw new InvalidOperationException("El paquete no quedó autorizado para Lock Task.");
            if ((int)Build.VERSION.SdkInt >= 28)                                                       // 3. quitar TODO (Inicio, Recientes, notificaciones, apagado…)
                politicas.SetLockTaskFeatures(administrador, LockTaskFeatures.None);
            politicas.AddUserRestriction(administrador, UserManager.DisallowCreateWindows);          // 4. sin ventanas flotantes
            restriccionPuesta = true;
            actividad.StartLockTask();                                                                 // 5. fijar
            lockTaskPuesto = true;
            OcultarBarras(actividad);                                                                  // 6. inmersivo
            return true;
        }
        catch (Exception ex)
        {
            notas.Add($"Lock Task no se pudo aplicar ({ex.GetType().Name}: {ex.Message}).");
            RegistroLocal.Advertencia(Canal.Dispositivo, "kiosco.android_lock_task", "Lock Task no se pudo aplicar", null, ex);
            return false;
        }
    }

    /// <summary>Tras <c>StartLockTask</c>: ¿el sistema dice que la tarea quedó bloqueada? Fijado de pantalla (el alumno puede salir) no cuenta como la capa del sistema.</summary>
    private bool VerificarLockTask(List<string> notas)
    {
        var actividad = Platform.CurrentActivity;
        if (actividad is null) { notas.Add("No se pudo verificar Lock Task: no hay pantalla activa."); return false; }
        var gestor = actividad.GetSystemService(Context.ActivityService) as AndroidActivityManager;
        if (gestor is null) { notas.Add("No se pudo verificar Lock Task: el sistema no dio el gestor de actividades."); return false; }
        if ((int)Build.VERSION.SdkInt >= 23)
        {
            switch (gestor.LockTaskModeState)
            {
                case LockTaskMode.Locked:
                    return true;
                case LockTaskMode.Pinned:
                    notas.Add("La tableta quedó en fijado de pantalla, no en Lock Task: el alumno puede salir.");
                    return false;
                default:
                    notas.Add("Lock Task no quedó activo tras pedirlo.");
                    return false;
            }
        }
        if (gestor.IsInLockTaskMode) return true;
        notas.Add("Lock Task no quedó activo tras pedirlo.");
        return false;
    }

    // ================================================================================================================ soltar

    public async Task<InformeDeBloqueo> StopExamLockAsync(CancellationToken ct = default)
    {
        try
        {
            return await RunOnUiThreadAsync(Soltar).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            // Sin Activity ya no hay nada que soltar en pantalla; el estado de este servicio sí se limpia.
            RegistroLocal.Advertencia(Canal.Dispositivo, "kiosco.android_liberar_excepcion", "El bloqueo de Android lanzó una excepción al soltarse", null, ex);
            Reiniciar();
            return new InformeDeBloqueo(ResultadosDeBloqueo.Liberado, CapasDeBloqueo.Ninguna, $"No se pudo revertir todo: {ex.GetType().Name}.");
        }
    }

    private InformeDeBloqueo Soltar()
    {
        var notas = new List<string>();
        var actividad = Platform.CurrentActivity;
        if (actividad is null) notas.Add("No hay pantalla activa: sólo se limpió el estado.");
        else
        {
            SoltarLockTask(actividad, notas);
            SoltarCapaApp(actividad, notas);
            try { actividad.Window?.ClearFlags(WindowManagerFlags.Secure); } catch (Exception) { /* sin ventana */ }
        }
        Reiniciar();
        RegistroLocal.Info(Canal.Dispositivo, "kiosco.android_liberado", "Bloqueo de Android liberado", notas.Count == 0 ? null : new { notas });
        return new InformeDeBloqueo(ResultadosDeBloqueo.Liberado, CapasDeBloqueo.Ninguna, notas.Count == 0 ? null : string.Join(" ", notas));
    }

    private void Reiniciar()
    {
        plan = null;
        planResuelto = true;      // ya no se pide nada
        motivo = null;
        ultimasCapas = CapasDeBloqueo.Ninguna;
        lockTaskPuesto = false;
        restriccionPuesta = false;
        capaAppPuesta = false;
    }

    /// <summary><c>StopLockTask</c> (lanza si no estaba activo: se ignora) + <c>ClearUserRestriction</c>.</summary>
    private void SoltarLockTask(AndroidActivity actividad, List<string> notas)
    {
        if (lockTaskPuesto)
        {
            try { actividad.StopLockTask(); }
            catch (Exception ex) when (ex is InvalidOperationException or Java.Lang.IllegalStateException) { /* no estaba activo: ya está suelto */ }
            catch (Exception ex) { notas.Add($"StopLockTask falló ({ex.GetType().Name})."); }
            lockTaskPuesto = false;
        }
        if (restriccionPuesta)
        {
            try
            {
                var paquete = actividad.PackageName;
                if (paquete is not null) Politicas(actividad)?.ClearUserRestriction(new ComponentName(paquete, ExamDeviceAdminReceiver.NombreCompleto), UserManager.DisallowCreateWindows);
            }
            catch (Exception ex) { notas.Add($"No se pudo quitar la restricción de ventanas ({ex.GetType().Name})."); }
            restriccionPuesta = false;
        }
    }

    /// <summary>Muestra de nuevo la interfaz del sistema y apaga la pantalla siempre encendida, salvo que la pantalla completa se haya pedido desde el arranque (cuenta dedicada).</summary>
    private void SoltarCapaApp(AndroidActivity actividad, List<string> notas)
    {
        if (!capaAppPuesta) return;
        capaAppPuesta = false;
        if (pantallaCompletaDeArranque) return;
        try
        {
            actividad.Window?.ClearFlags(WindowManagerFlags.KeepScreenOn);
            MostrarBarras(actividad);
        }
        catch (Exception ex) { notas.Add($"No se pudo mostrar la interfaz del sistema ({ex.GetType().Name})."); }
    }

    // ======================================================================================== lo que ve la Activity (MainActivity)

    /// <summary>La Activity ganó el foco: deslizar desde el borde muestra las barras, así que se reaplican (kiosk.md §3.4).</summary>
    public void AlGanarFoco(AndroidActivity actividad)
    {
        try { if (CapaAppVigente || pantallaCompletaDeArranque) OcultarBarras(actividad); }
        catch (Exception) { /* un detalle visual no debe tumbar la Activity */ }
    }

    /// <summary>Atrás mientras rige la capa de la aplicación: se ignora (Lock Task no intercepta Atrás y, si la Activity termina, termina la tarea y con ella el bloqueo). Devuelve si se tragó.</summary>
    public bool AlPulsarAtras(AndroidActivity actividad)
    {
        try
        {
            if (!CapaAppVigente) return false;
            OcultarBarras(actividad);
            Emitir(TiposDeIncidente.CierreBloqueado, new() { ["via"] = "atras" });
            return true;
        }
        catch (Exception) { return CapaAppVigente; }
    }

    /// <summary>La app dejó de verse (Inicio, Recientes, otra app, pantalla apagada).</summary>
    public void AlPausar(AndroidActivity actividad)
    {
        try
        {
            if (!examenEnCurso || actividad.IsChangingConfigurations) return;
            lock (candadoSalida)
            {
                if (salidaInformada) return;
                salidaInformada = true;
                desdeMs = RelojNodo.AhoraMs;
                Emitir(TiposDeIncidente.SalidaDeApp, new() { ["desde"] = desdeMs });
            }
        }
        catch (Exception) { /* informar una salida no debe tumbar la Activity */ }
    }

    /// <summary>La app volvió a verse.</summary>
    public void AlReanudar()
    {
        try
        {
            lock (candadoSalida)
            {
                if (!salidaInformada) return;
                salidaInformada = false;
                var hasta = RelojNodo.AhoraMs;
                if (!examenEnCurso) return;
                Emitir(TiposDeIncidente.RegresoAApp, new() { ["desde"] = desdeMs, ["hasta"] = hasta, ["fuera_ms"] = Math.Max(0, hasta - desdeMs) });
            }
        }
        catch (Exception) { /* de mejor esfuerzo */ }
    }

    // ================================================================================================================ utilidades

    /// <summary>Cuántas pantallas hay además de la de la tableta (una externa por cable o Miracast). Si el sistema no contesta, 0: no se inventan pantallas.</summary>
    private static int ContarPantallasAdicionales(Context contexto)
    {
        try { return Math.Max(0, ((contexto.GetSystemService(Context.DisplayService) as DisplayManager)?.GetDisplays()?.Length ?? 1) - 1); }
        catch (Exception) { return 0; }
    }

    private static DevicePolicyManager? Politicas(Context contexto) => contexto.GetSystemService(Context.DevicePolicyService) as DevicePolicyManager;

    /// <summary>Barras de estado y navegación ocultas, que reaparecen al deslizar desde el borde (inmersivo «sticky»). Hilo de interfaz.</summary>
    internal static void OcultarBarras(AndroidActivity actividad)
    {
        var ventana = actividad.Window;
        if (ventana is null) return;
        if ((int)Build.VERSION.SdkInt >= 30)
        {
            var control = ventana.InsetsController;
            if (control is null) return;
            control.Hide(WindowInsets.Type.StatusBars() | WindowInsets.Type.NavigationBars());
            control.SystemBarsBehavior = (int)WindowInsetsControllerBehavior.ShowTransientBarsBySwipe;
        }
        else
        {
            var banderas = SystemUiFlags.ImmersiveSticky | SystemUiFlags.HideNavigation | SystemUiFlags.Fullscreen
                         | SystemUiFlags.LayoutStable | SystemUiFlags.LayoutHideNavigation | SystemUiFlags.LayoutFullscreen;
            ventana.DecorView.SystemUiFlags = banderas;
        }
    }

    private static void MostrarBarras(AndroidActivity actividad)
    {
        var ventana = actividad.Window;
        if (ventana is null) return;
        if ((int)Build.VERSION.SdkInt >= 30) ventana.InsetsController?.Show(WindowInsets.Type.StatusBars() | WindowInsets.Type.NavigationBars());
        else ventana.DecorView.SystemUiFlags = SystemUiFlags.Visible;
    }

    /// <summary>
    /// Ejecuta <paramref name="trabajo"/> en el hilo de interfaz y devuelve su resultado o su excepción AL LLAMADOR (kiosk.md §3.3). Si ya estamos en el hilo de interfaz se ejecuta en
    /// el acto. Una excepción jamás sube por el hilo de interfaz.
    /// </summary>
    private static Task<T> RunOnUiThreadAsync<T>(Func<T> trabajo)
    {
        var actividad = Platform.CurrentActivity;
        if (actividad is null) return Task.FromException<T>(new InvalidOperationException("No hay una pantalla (Activity) activa."));
        if (Looper.MyLooper() == Looper.MainLooper)
        {
            try { return Task.FromResult(trabajo()); }
            catch (Exception ex) { return Task.FromException<T>(ex); }
        }
        var fuente = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
        actividad.RunOnUiThread(() =>
        {
            try { fuente.SetResult(trabajo()); }
            catch (Exception ex) { fuente.SetException(ex); }
        });
        return fuente.Task;
    }

    /// <summary>Entrega un hecho a la sesión en orden y sin bloquear a quien lo vio (la sesión guarda el incidente en una cola cifrada en disco).</summary>
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
}
#endif

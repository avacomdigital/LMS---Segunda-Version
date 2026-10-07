namespace Avacom.Lms.Core.Services;

/// <summary>
/// Deja constancia de una excepción no controlada en un archivo local, para que
/// un fallo en el aula se pueda diagnosticar después. Sin Internet y sin
/// consola, un archivo en el perfil del usuario es lo único que queda.
///
/// Ruta: %LOCALAPPDATA%\AVACOM\lms\fallos-{app}.log
///
/// Desde MOD-019 es una FACHADA de <see cref="RegistroLocal"/> (§2.4): cada excepción queda además como renglón ERROR del canal
/// <c>aplicacion</c> en <c>{app}-app.log</c> / <c>{app}-errores.log</c> y en la cola que se entrega al nodo. El archivo plano de siempre se
/// conserva para no cambiar lo que el técnico ya sabe leer.
/// </summary>
public static class RegistroDeFallos
{
    private static readonly object Cerrojo = new();

    /// <summary>
    /// La carpeta del registro. <c>AVACOM_LMS_DIR_FALLOS</c> la sustituye (lo usan las pruebas automáticas para no escribir en el registro real de quien
    /// trabaja en el equipo); sin ella, <c>%LOCALAPPDATA%\AVACOM\lms</c>.
    /// </summary>
    private static string Carpeta =>
        Environment.GetEnvironmentVariable("AVACOM_LMS_DIR_FALLOS") is { Length: > 0 } propia
            ? propia
            : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AVACOM", "lms");

    public static string Ruta(string app) => Path.Combine(Carpeta, $"fallos-{app}.log");

    /// <summary>
    /// La entrega inmediata de los renglones pendientes al nodo. La fija <see cref="EntregadorDeLogs"/> al arrancar. La usan los orígenes FATALES: la
    /// app está a punto de caer y el minuto de espera del entregador no llega, así que se intenta una entrega y se espera unos segundos.
    /// </summary>
    public static Func<Task>? EntregaUrgente { get; set; }

    /// <summary>Cuánto se espera, como máximo, la entrega urgente de una caída antes de dejar morir el proceso.</summary>
    public static TimeSpan EsperaUrgente { get; set; } = TimeSpan.FromSeconds(3);

    /// <summary>
    /// Una excepción no controlada, escrita para que un técnico la entienda sin abrir el código: qué pasó (en palabras), de qué tipo y con qué código, y en
    /// qué parte de AVACOM ocurrió (clase, método y línea). El texto técnico completo va en la traza.
    /// </summary>
    public static void Escribir(string app, string origen, Exception? excepcion, bool fatal = false)
    {
        if (excepcion is null) return;
        try
        {
            var donde = DondeFallo(excepcion);
            var mensaje = $"{Explicacion(origen, fatal)}. {Resumen(excepcion)}{(donde is null ? string.Empty : $" · en {donde}")}";
            RegistroLocal.Escribir(NivelLog.Error, Canal.Aplicacion, "excepcion.no_controlada", mensaje,
                new { origen, tipo = excepcion.GetType().Name, codigo = CodigoDe(excepcion), donde, fatal }, excepcion, sinFreno: true);
        }
        catch { }
        AnexarAlArchivo(app, origen, excepcion);
        if (fatal) EntregarAntesDeMorir();
    }

    /// <summary>
    /// Un fallo que la app SÍ atrapó pero que es un defecto (no un caso normal): queda como ERROR con el evento y el mensaje que el llamador ya sabe decir
    /// («No se pudo mostrar la Teoría…»), y en el archivo plano de siempre. Lo entrega el entregador de logs sin esperar al siguiente minuto.
    /// </summary>
    public static void Anotar(string app, string origen, Exception excepcion, string evento, string mensaje, object? detalle = null)
    {
        try { RegistroLocal.Escribir(NivelLog.Error, Canal.Aplicacion, evento, mensaje, detalle, excepcion, modulo: app, sinFreno: true); } catch { }
        AnexarAlArchivo(app, origen, excepcion);
    }

    private static void AnexarAlArchivo(string app, string origen, Exception excepcion)
    {
        try
        {
            var ruta = Ruta(app);
            Directory.CreateDirectory(Path.GetDirectoryName(ruta)!);
            lock (Cerrojo)
            {
                File.AppendAllText(ruta,
                    $"[{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss zzz}] {origen}{Environment.NewLine}{excepcion}{Environment.NewLine}{Environment.NewLine}");
            }
        }
        catch (Exception)
        {
            // Si no se puede escribir el registro, no hay nada más que hacer: no se relanza.
        }
    }

    /// <summary>
    /// La app va a caer: lo último que hace es intentar llevar el error a la bitácora del nodo (con un máximo de <see cref="EsperaUrgente"/>). Si no hay
    /// red o el aparato aún no se presentó al nodo, no pasa nada: el error queda en el archivo de pendientes y el próximo arranque lo entrega.
    /// </summary>
    private static void EntregarAntesDeMorir()
    {
        try
        {
            var entrega = EntregaUrgente;
            if (entrega is null) return;
            Task.Run(entrega).Wait(EsperaUrgente);
        }
        catch { /* ya se está cayendo: nada de lo que falle aquí puede empeorarlo */ }
    }

    /// <summary>Lo que significa cada origen, en palabras para quien lee la bitácora. Un origen libre («BitacoraPage.ExportarDiagnostico») se dice tal cual.</summary>
    public static string Explicacion(string origen, bool fatal = false) => origen switch
    {
        "WinUI.UnhandledException" => "Falló la interfaz de Windows y la aplicación se cerró sin controlarlo",
        "AppDomain.UnhandledException" => "Excepción no controlada: la aplicación se cerró",
        "TaskScheduler.UnobservedTaskException" => "Una tarea en segundo plano falló y nadie la esperaba (la aplicación sigue abierta)",
        "Android.UnhandledException" => "Falló la aplicación de Android sin controlarlo",
        _ => fatal ? $"Falló la aplicación y se cerró ({origen})" : $"Falló una operación ({origen})",
    };

    /// <summary>«COMException (0x800F1000): texto del sistema» — el tipo, el código si lo hay y el mensaje, con la causa de fondo cuando es otra.</summary>
    public static string Resumen(Exception excepcion)
    {
        var tipo = excepcion.GetType().Name;
        var codigo = CodigoDe(excepcion);
        var texto = $"{tipo}{(codigo is null ? string.Empty : $" ({codigo})")}: {excepcion.Message}".Trim();
        var raiz = excepcion;
        while (raiz.InnerException is { } interna) raiz = interna;
        if (!ReferenceEquals(raiz, excepcion)) texto += $" · causa: {raiz.GetType().Name}: {raiz.Message}";
        return texto;
    }

    /// <summary>El código de Windows (HRESULT) de una excepción de interoperabilidad, en hexadecimal; null si no es de ese tipo.</summary>
    public static string? CodigoDe(Exception excepcion) =>
        excepcion is System.Runtime.InteropServices.ExternalException && excepcion.HResult != 0 ? $"0x{excepcion.HResult:X8}" : null;

    /// <summary>
    /// El primer punto de AVACOM de la pila (<c>AulaContenidoView.MostrarHtml (AulaContenidoView.cs:255)</c>): qué clase y qué método estaban pintando,
    /// guardando o llamando cuando falló. Sin él, la pila empieza en WinUI y no dice nada de dónde mirar. Null si la pila no tiene código nuestro.
    /// </summary>
    public static string? DondeFallo(Exception excepcion)
    {
        try
        {
            var marcos = new System.Diagnostics.StackTrace(excepcion, fNeedFileInfo: true).GetFrames();
            foreach (var marco in marcos ?? [])
            {
                var metodo = marco.GetMethod();
                var tipo = metodo?.DeclaringType;
                if (metodo is null || tipo?.FullName is not { } completo || !completo.StartsWith("Avacom.", StringComparison.Ordinal)) continue;
                // Una lambda o una máquina de estados (async) vive en un tipo anidado «<>c» / «<Metodo>d__3»: se dice la clase y el método de verdad.
                var nombreMetodo = metodo.Name;
                var clase = tipo;
                while (clase.DeclaringType is not null && clase.Name.Contains('<')) clase = clase.DeclaringType;
                var generado = System.Text.RegularExpressions.Regex.Match(tipo.Name + "." + metodo.Name, @"<(?<m>[A-Za-z0-9_]+)>");
                if (generado.Success) nombreMetodo = generado.Groups["m"].Value;
                var archivo = marco.GetFileName() is { Length: > 0 } f ? $" ({Path.GetFileName(f)}:{marco.GetFileLineNumber()})" : string.Empty;
                return $"{clase.Name}.{nombreMetodo}{archivo}";
            }
        }
        catch { /* describir el fallo nunca debe fallar */ }
        return null;
    }

    /// <summary>Engancha los orígenes de excepciones no controladas del proceso. Una excepción que TERMINA el proceso intenta entregarse antes de morir.</summary>
    public static void Observar(string app)
    {
        RegistroLocal.Configurar(app);
        AppDomain.CurrentDomain.UnhandledException += (_, e) => Escribir(app, "AppDomain.UnhandledException", e.ExceptionObject as Exception, fatal: e.IsTerminating);
        TaskScheduler.UnobservedTaskException += (_, e) => Escribir(app, "TaskScheduler.UnobservedTaskException", e.Exception);
    }
}

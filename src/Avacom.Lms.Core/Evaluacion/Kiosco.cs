namespace Avacom.Lms.Core.Evaluacion;

/// <summary>Algo que el servicio de kiosco vio en la plataforma (salió de la app, intentó cerrar, apareció otra pantalla…). La sesión le pone el <c>ref_cliente</c> y lo encola.</summary>
public sealed record HechoDeKiosco(string Tipo, Dictionary<string, object?>? Detalle = null);

/// <summary>
/// Todo el bloqueo de la tableta detrás de una interfaz (kiosk.md §2): la lógica del examen no sabe qué plataforma hay debajo. Una implementación por
/// plataforma (<c>AndroidKioskService</c>, <c>WindowsKioskService</c>); <see cref="KioscoNulo"/> para los equipos que no bloquean y para las pruebas.
///
/// Dos reglas de diseño que la interfaz hace cumplir (kiosk.md §5):
/// <list type="bullet">
/// <item><b>Informar el estado real, no el deseado.</b> <see cref="Capacidad"/> y <see cref="LockdownSummary"/> consultan al sistema (Device Owner,
/// Assigned Access), no a un archivo marcador; <see cref="LockdownSummary"/> NUNCA lanza.</item>
/// <item><b>Un bloqueo parcial se informa, no se oculta.</b> <see cref="StartExamLockAsync"/> no usa una excepción como canal de estado: devuelve un
/// <see cref="InformeDeBloqueo"/> tipado (aplicado · parcial · fallido) con el motivo.</item>
/// </list>
/// </summary>
public interface IKioskService
{
    /// <summary>¿Está aprovisionada la capa del sistema operativo? (Device Owner en Android; Assigned Access o Shell Launcher en Windows.)</summary>
    bool IsTrueDeviceLockAvailable { get; }

    /// <summary>
    /// Lo que esta tableta puede DECLARAR al nodo (BR-075): <c>controlado</c> sólo con la capa del sistema aprovisionada; <c>supervisado</c> si al menos
    /// la capa de aplicación funciona; <c>abierto</c> si nada. El nodo compara esto con el nivel del examen antes de abrir el intento.
    /// </summary>
    string Capacidad { get; }

    /// <summary>Qué restricciones hay activas AHORA, en una frase para el profesor y el alumno. Nunca lanza.</summary>
    string LockdownSummary { get; }

    /// <summary>
    /// La bandera que las plataformas consultan para negarse a cerrar la ventana. La sesión la activa ANTES de aplicar el bloqueo: el rechazo al cierre
    /// debe valer incluso en un equipo sin aprovisionar.
    /// </summary>
    bool ExamenEnCurso { get; set; }

    /// <summary>Pantalla completa desde el arranque de la app (el alumno no debe ver el escritorio en ningún momento), sin examen aún.</summary>
    Task EnterFullScreenAsync(CancellationToken ct = default);

    /// <summary>Aplica el plan que el nodo decidió y devuelve lo que LOGRÓ. No lanza por un bloqueo incompleto.</summary>
    Task<InformeDeBloqueo> StartExamLockAsync(PlanDeBloqueo plan, CancellationToken ct = default);

    /// <summary>Suelta el bloqueo del examen (al confirmarse la entrega, al degradar el nivel o por la salida administrativa).</summary>
    Task<InformeDeBloqueo> StopExamLockAsync(CancellationToken ct = default);

    /// <summary>La plataforma vio algo que el profesor debe poder consultar (BR-077). Se dispara desde cualquier hilo.</summary>
    event Action<HechoDeKiosco>? Hecho;
}

/// <summary>Una tableta o un equipo sin bloqueo: declara <c>abierto</c>, no aplica nada y lo dice. Sirve a las plataformas que no bloquean y a las pruebas.</summary>
public sealed class KioscoNulo : IKioskService
{
    public bool IsTrueDeviceLockAvailable => false;
    public string Capacidad => Niveles.Abierto;
    public string LockdownSummary => "Sin bloqueo: esta plataforma no restringe el uso del dispositivo durante el examen.";
    public bool ExamenEnCurso { get; set; }
    public event Action<HechoDeKiosco>? Hecho { add { } remove { } }

    public Task EnterFullScreenAsync(CancellationToken ct = default) => Task.CompletedTask;

    public Task<InformeDeBloqueo> StartExamLockAsync(PlanDeBloqueo plan, CancellationToken ct = default) =>
        Task.FromResult(PoliticaDeKiosco.Evaluar(plan, CapasDeBloqueo.Ninguna, "Esta plataforma no aplica ningún bloqueo."));

    public Task<InformeDeBloqueo> StopExamLockAsync(CancellationToken ct = default) =>
        Task.FromResult(new InformeDeBloqueo(ResultadosDeBloqueo.Liberado, CapasDeBloqueo.Ninguna));
}

/// <summary>
/// Las decisiones puras del bloqueo, sin plataforma debajo (kiosk.md §7: «aísla la lógica detrás de la interfaz para poder probarla con un doble»):
/// qué resultado informar según lo que el plan pedía y lo que se logró, y qué capacidad declarar.
/// </summary>
public static class PoliticaDeKiosco
{
    /// <summary>
    /// Compara lo PEDIDO con lo LOGRADO. <b>Aplicado</b>: todo lo que el plan pedía está aplicado Y el plan no era ya parcial. <b>Fallido</b>: el plan pedía algo y no
    /// se logró nada. <b>Parcial</b>: el resto, incluido el caso de un plan que el nodo ya marcó parcial (se pidió «controlado» a una tableta sin la capa del
    /// sistema): aunque todo lo demás se aplique, se informa PARCIAL porque la salida del sistema operativo sigue abierta. Un plan que no pide nada es
    /// <b>aplicado</b>: no hay nada que lograr.
    /// </summary>
    public static InformeDeBloqueo Evaluar(PlanDeBloqueo plan, CapasDeBloqueo logradas, string? motivo = null)
    {
        ArgumentNullException.ThrowIfNull(plan);
        ArgumentNullException.ThrowIfNull(logradas);
        var pedidas = Pedidas(plan);
        if (pedidas.Count == 0 && !plan.Parcial)
            return new InformeDeBloqueo(ResultadosDeBloqueo.Aplicado, logradas, motivo);

        var faltan = pedidas.Where(capa => !Lograda(capa, logradas)).ToList();
        if (pedidas.Count > 0 && faltan.Count == pedidas.Count)
            return new InformeDeBloqueo(ResultadosDeBloqueo.Fallido, logradas, motivo ?? $"No se aplicó ninguna capa pedida ({string.Join(", ", pedidas)}).");

        if (faltan.Count == 0 && !plan.Parcial)
            return new InformeDeBloqueo(ResultadosDeBloqueo.Aplicado, logradas, motivo);

        var detalle = new List<string>();
        if (plan.Parcial) detalle.Add("la capa del sistema no está aprovisionada en esta tableta");
        if (faltan.Count > 0) detalle.Add($"no se logró: {string.Join(", ", faltan)}");
        return new InformeDeBloqueo(ResultadosDeBloqueo.Parcial, logradas, motivo ?? Capitalizar(string.Join("; ", detalle)) + ".");
    }

    /// <summary>Las capas que el plan pide, en el vocabulario del informe (<c>sistema</c>, <c>app</c>, <c>capturas</c>, <c>pantallas</c>).</summary>
    public static IReadOnlyList<string> Pedidas(PlanDeBloqueo plan)
    {
        var capas = new List<string>(4);
        if (plan.CapaSistema) capas.Add("sistema");
        if (plan.CapaApp) capas.Add("app");
        if (plan.BloquearCapturas) capas.Add("capturas");
        if (plan.CubrirPantallasExtra) capas.Add("pantallas");
        return capas;
    }

    private static bool Lograda(string capa, CapasDeBloqueo c) => capa switch
    {
        "sistema" => c.Sistema,
        "app" => c.App,
        "capturas" => c.Capturas,
        "pantallas" => c.Pantallas,
        _ => false,
    };

    /// <summary>
    /// La capacidad que una tableta puede declarar según lo que REALMENTE tiene (kiosk.md §5.1): <c>controlado</c> con la capa del sistema aprovisionada y
    /// la de aplicación funcionando; <c>supervisado</c> con sólo la de aplicación; <c>abierto</c> si ninguna.
    /// </summary>
    public static string CapacidadDeclarable(bool capaSistema, bool capaApp) =>
        capaSistema && capaApp ? Niveles.Controlado : capaApp ? Niveles.Supervisado : Niveles.Abierto;

    /// <summary>El texto de «qué restricciones hay activas», a partir de un informe: la verdad, sin adornos.</summary>
    public static string Resumen(InformeDeBloqueo? informe)
    {
        if (informe is null) return "Sin bloqueo aplicado.";
        var activas = new List<string>();
        if (informe.Capas.Sistema) activas.Add("dispositivo dedicado al examen");
        if (informe.Capas.App) activas.Add("pantalla completa y cierre rechazado");
        if (informe.Capas.Capturas) activas.Add("capturas bloqueadas");
        if (informe.Capas.Pantallas) activas.Add("pantallas adicionales cubiertas");
        var lista = activas.Count == 0 ? "ninguna restricción activa" : string.Join(", ", activas);
        return informe.Resultado switch
        {
            ResultadosDeBloqueo.Aplicado => $"Bloqueo completo: {lista}.",
            ResultadosDeBloqueo.Parcial => $"Bloqueo parcial: {lista}. {informe.Motivo}".TrimEnd(),
            ResultadosDeBloqueo.Fallido => $"El bloqueo no se pudo aplicar. {informe.Motivo}".TrimEnd(),
            _ => "Bloqueo liberado.",
        };
    }

    private static string Capitalizar(string texto) => texto.Length == 0 ? texto : char.ToUpperInvariant(texto[0]) + texto[1..];
}

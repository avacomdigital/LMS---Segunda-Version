namespace Avacom.Lms.Ops.Navegacion;

/// <summary>
/// Qué hacer con una petición de navegación de Shell cuando la misma persona (o una prueba de UI Automation que reintenta) la repite: lógica pura, sin MAUI, para poder probarla.
/// <para>
/// El caso que obligó a escribirla: «Menú principal» activado DOS veces seguidas (un doble toque en la pantalla táctil, o el reintento de <c>Invoke()</c> tras una excepción de UI
/// Automation) hacía <c>GoToAsync("..")</c> dos veces. La primera saca la pantalla y deja el menú a la vista; la segunda, pedida ya con el menú como página actual, lo saca a él y
/// lleva al <b>acceso</b> con el proceso vivo y la sesión abierta, sin ningún 401 (Shell resuelve cada «..» contra el estado del momento en que le toca, no del momento en que se pidió).
/// </para>
/// <list type="bullet">
/// <item><b>Salir del menú con «..» nunca es válido</b>: el menú no tiene botón de atrás (se sale con «Cerrar sesión», que va a <c>//login</c>). Un «volver» pedido con el menú a la vista
/// es el segundo toque de un doble toque, y se ignora.</item>
/// <item><b>Una petición idéntica a la anterior dentro de <see cref="VentanaDeDobleToque"/></b> también se ignora: el doble toque en una tesela del menú apilaba dos pantallas iguales y el
/// primer «Menú principal» volvía a la copia en lugar de al menú.</item>
/// </list>
/// </summary>
public sealed class GuardiaDeNavegacion
{
    /// <summary>
    /// Lo que separa los dos toques de un doble toque. Un segundo toque deliberado (ver la pantalla nueva y tocar otra vez) tarda bastante más; el reintento programado de una prueba
    /// tarda aún más y lo para la otra regla (el menú a la vista).
    /// </summary>
    public static readonly TimeSpan VentanaDeDobleToque = TimeSpan.FromMilliseconds(350);

    public enum Veredicto
    {
        /// <summary>Se deja pasar.</summary>
        Pasa,
        /// <summary>Un «volver» con el menú principal ya a la vista: sacaría el menú y llevaría al acceso.</summary>
        YaEstaEnElMenu,
        /// <summary>La misma petición que la anterior, dentro de la ventana del doble toque.</summary>
        DobleToque,
    }

    private readonly Func<long> _ahoraMs;
    private string? _ultimoDestino;
    private long _ultimoMs;

    /// <param name="ahoraMs">Reloj monótono en milisegundos (en las pruebas, uno falso).</param>
    public GuardiaDeNavegacion(Func<long>? ahoraMs = null)
    {
        _ahoraMs = ahoraMs ?? (() => Environment.TickCount64);
        _ultimoMs = long.MinValue / 2;
    }

    /// <summary>
    /// Decide sobre una petición. <paramref name="destino"/> es el texto que se le dio a <c>GoToAsync</c> («..», «../..», «licencia», «//login»…); <paramref name="paginaActualEsElMenu"/>, si la
    /// pantalla que se va a dejar es el menú principal. Una petición ignorada no mueve la ventana: la tercera pulsación, pasada la ventana desde la primera, vuelve a valer.
    /// </summary>
    public Veredicto Evaluar(string? destino, bool paginaActualEsElMenu)
    {
        var d = destino?.Trim() ?? string.Empty;
        if (d.Length == 0) return Veredicto.Pasa;                                   // sin destino legible (arranque, cambio de elemento): no se toca
        if (paginaActualEsElMenu && EsSoloVolver(d)) return Veredicto.YaEstaEnElMenu;
        var ahora = _ahoraMs();
        if (string.Equals(d, _ultimoDestino, StringComparison.Ordinal) && ahora - _ultimoMs < VentanaDeDobleToque.TotalMilliseconds) return Veredicto.DobleToque;
        _ultimoDestino = d;
        _ultimoMs = ahora;
        return Veredicto.Pasa;
    }

    /// <summary>«..», «../..»…: una ruta que sólo saca pantallas (no lleva a ninguna nueva).</summary>
    public static bool EsSoloVolver(string? destino)
    {
        var d = destino?.Trim().Trim('/');
        return !string.IsNullOrEmpty(d) && d.Split('/').All(s => s == "..");
    }
}

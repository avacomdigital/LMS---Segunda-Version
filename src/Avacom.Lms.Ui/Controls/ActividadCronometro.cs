using System.Diagnostics;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// El cronómetro de una actividad lanzada (CMP-003, 007-06) visto desde la tableta. El nodo manda un estado nuevo cada vez que
/// algo cambia (<see cref="CronometroAula"/>) y la tableta cuenta hacia atrás sola entre un aviso y el siguiente con un reloj
/// monotónico (<see cref="Stopwatch"/>): ni la hora del aparato ni un cambio de hora del sistema mueven el conteo (BR-062).
///
/// Cuatro estados y nada más: <c>en_curso</c> · <c>congelado</c> (el profesor detuvo la clase) · <c>vencido_con_gracia</c> ·
/// <c>vencido</c>. Un estado desconocido (una versión futura del nodo) se trata como «sin cronómetro»: no bloquea nada.
/// Sin lógica de pantalla: la separación deja probar los textos y las transiciones sin levantar controles.
/// </summary>
internal sealed class CronometroLocal
{
    public const string EnCurso = "en_curso", Congelado = "congelado", ConGracia = "vencido_con_gracia", Vencido = "vencido";

    private CronometroAula? _crono;
    private long _marca;             // Stopwatch.GetTimestamp() cuando llegó el estado
    private long _restanteBaseMs;    // lo que quedaba al llegar, ya corregido por el viaje del aviso

    /// <summary>Recibe el estado que acaba de dictar el nodo (o nulo si la actividad no tiene límite de tiempo).</summary>
    public void Fijar(CronometroAula? crono, long servidorEnMs)
    {
        _crono = crono;
        _marca = Stopwatch.GetTimestamp();
        _restanteBaseMs = crono?.RestanteMs ?? 0;
        // Si el aviso ya venía envejecido (un estado guardado, una pantalla que se abrió tarde) se descuenta lo que viajó,
        // pero sólo cuando el reloj del nodo ya se aprendió y el desfase es creíble: nunca se confía en una hora suelta.
        if (crono?.Estado == EnCurso && servidorEnMs > 0 && RelojNodo.Aprendido)
        {
            var envejecido = RelojNodo.AhoraMs - servidorEnMs;
            if (envejecido is > 0 and < 120_000) _restanteBaseMs = Math.Max(0, _restanteBaseMs - envejecido);
        }
    }

    /// <summary>Verdadero si hay un cronómetro que la pantalla deba mostrar.</summary>
    public bool Hay => Estado is not null;

    private long TranscurridoLocalMs => (long)Stopwatch.GetElapsedTime(_marca).TotalMilliseconds;

    /// <summary>Lo que queda ahora. Congelado o vencido no se mueve; en curso baja con el reloj local.</summary>
    public long RestanteMs => _crono?.Estado == EnCurso ? Math.Max(0, _restanteBaseMs - TranscurridoLocalMs) : Math.Max(0, _restanteBaseMs);

    /// <summary>
    /// El estado que la pantalla debe mostrar ahora. Cuando el conteo local llega a cero antes de que llegue el aviso del nodo, la
    /// pantalla no se queda en «Quedan 00:00»: pasa a la gracia (el nodo confirmará o corregirá con su siguiente estado).
    /// </summary>
    public string? Estado
    {
        get
        {
            switch (_crono?.Estado)
            {
                case EnCurso: return RestanteMs <= 0 ? ConGracia : EnCurso;
                case Congelado: return Congelado;
                case ConGracia: return ConGracia;
                case Vencido: return Vencido;
                default: return null;
            }
        }
    }

    /// <summary>Se puede cambiar lo respondido: sin cronómetro o con el tiempo corriendo.</summary>
    public bool PermiteEditar => Estado is null or EnCurso;

    /// <summary>Se puede entregar: además, dentro de la gracia. Congelado o vencido no hay nada que entregar desde la pantalla.</summary>
    public bool PermiteEntregar => Estado is null or EnCurso or ConGracia;

    /// <summary>Los textos de CMP-003. Nunca alarma: en el último minuto sigue igual de neutro.</summary>
    public (string Titulo, string? Detalle) Texto() => Estado switch
    {
        EnCurso => ($"Quedan {Formato(RestanteMs)}", null),
        Congelado => ("Tiempo detenido: tu profesor detuvo la clase", "Lo que llevas está a salvo."),
        ConGracia => ("Se acabó el tiempo. Todavía puedes entregar lo que llevas.", null),
        Vencido => ("Terminó el tiempo", "Lo que respondiste quedó guardado."),
        _ => (string.Empty, null),
    };

    /// <summary>mm:ss (h:mm:ss desde una hora). Redondea hacia arriba: con 400 ms por delante todavía queda un segundo.</summary>
    public static string Formato(long ms)
    {
        var s = (long)Math.Ceiling(Math.Max(0, ms) / 1000.0);
        var h = s / 3600;
        var m = s % 3600 / 60;
        var seg = s % 60;
        return h > 0 ? $"{h}:{m:00}:{seg:00}" : $"{m:00}:{seg:00}";
    }
}

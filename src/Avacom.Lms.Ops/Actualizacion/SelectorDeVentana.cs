using Avacom.Lms.Core.Actualizacion;

namespace Avacom.Lms.Ops.Actualizacion;

/// <summary>Un atajo para elegir cuándo: «En 30 minutos», «Esta noche a las 22:00»…</summary>
public sealed record AtajoDeVentana(string Titulo, long InicioMs);

/// <summary>
/// El selector táctil de la ventana de una actualización (CAP-108, C-2): sin teclado, con atajos y botones de ± media hora y ± un día, y una duración de una lista cerrada. Puro, sin MAUI y
/// con la hora del NODO (nunca la del equipo de OPS) y la zona horaria que se le pase: se prueba sin interfaz. Las reglas son las que el nodo vuelve a comprobar (<c>programar/</c>): la
/// ventana no empieza en el pasado, queda a 90 días como mucho y dura entre 10 minutos y un día; el selector no deja llegar a una ventana que el nodo rechazaría.
/// </summary>
public sealed class SelectorDeVentana
{
    private const long Minuto = 60_000;
    private const long MediaHora = 30 * Minuto;
    private const long Dia = 24 * 60 * Minuto;
    public const int DiasMaximos = 90;

    /// <summary>Las duraciones que se ofrecen (minutos). Bastan para cualquier paquete de módulo: el nodo avisa si el paquete necesita más (3 o 5 minutos).</summary>
    public static readonly IReadOnlyList<int> Duraciones = [30, 60, 120, 180];

    private readonly long _ahora;
    private readonly TimeZoneInfo _zona;

    /// <summary>Nada antes de esta hora: la próxima media hora que deja al menos 5 minutos de margen.</summary>
    public long Minimo { get; }

    public long Inicio { get; private set; }
    public int DuracionMin { get; private set; } = 60;

    public SelectorDeVentana(long ahoraDelNodoMs, TimeZoneInfo? zona = null)
    {
        _ahora = ahoraDelNodoMs;
        _zona = zona ?? TimeZoneInfo.Local;
        Minimo = AlSiguienteBloque(_ahora + 5 * Minuto);
        Inicio = AlSiguienteBloque(_ahora + MediaHora);
    }

    public long Desde => Inicio;
    public long Hasta => Inicio + DuracionMin * Minuto;
    public VentanaDeActualizacion Ventana => new(Desde, Hasta);

    public bool PuedeAdelantarMediaHora => Inicio - MediaHora >= Minimo;
    public bool PuedeAdelantarUnDia => Inicio - Dia >= Minimo;
    public bool PuedeAtrasarMediaHora => Inicio + MediaHora <= Maximo;
    public bool PuedeAtrasarUnDia => Inicio + Dia <= Maximo;
    private long Maximo => _ahora + DiasMaximos * Dia - Dia;

    public bool EsValida => Inicio >= Minimo && Inicio <= Maximo && DuracionMin is >= 10 and <= 1440;

    /// <summary>«hoy de 22:00 a 23:00».</summary>
    public string Resumen => ActualizacionTexto.Ventana(Ventana, _ahora, _zona);

    public string DiaTexto => ActualizacionTexto.Dia(Inicio, _ahora, _zona);
    public string HoraTexto => ActualizacionTexto.Hora(Inicio, _zona);

    public void MasMediaHora() { if (PuedeAtrasarMediaHora) Inicio += MediaHora; }
    public void MenosMediaHora() { if (PuedeAdelantarMediaHora) Inicio -= MediaHora; }
    public void MasUnDia() { if (PuedeAtrasarUnDia) Inicio += Dia; }
    public void MenosUnDia() { if (PuedeAdelantarUnDia) Inicio -= Dia; }

    public void Elegir(long inicioMs)
    {
        var bloque = AlSiguienteBloque(inicioMs);
        if (bloque >= Minimo && bloque <= Maximo) Inicio = bloque;
    }

    public void ElegirDuracion(int minutos)
    {
        if (Duraciones.Contains(minutos)) DuracionMin = minutos;
    }

    /// <summary>
    /// Los atajos que caben después de <see cref="Minimo"/>: en 30 minutos, esta noche a las 22:00 (si todavía no pasó), mañana a las 06:00 y el próximo sábado a las 08:00. Cada uno ya es
    /// una media hora exacta; no se repite ninguno.
    /// </summary>
    public IReadOnlyList<AtajoDeVentana> Atajos()
    {
        var lista = new List<AtajoDeVentana>();
        void Poner(string titulo, long ms)
        {
            var bloque = AlSiguienteBloque(ms);
            if (bloque >= Minimo && bloque <= Maximo && lista.All(a => a.InicioMs != bloque)) lista.Add(new AtajoDeVentana(titulo, bloque));
        }
        var hoy = EnLocal(_ahora).Date;
        Poner("En 30 minutos", _ahora + MediaHora);
        Poner("Esta noche a las 22:00", DeLocal(hoy.AddHours(22)));
        Poner("Mañana a las 06:00", DeLocal(hoy.AddDays(1).AddHours(6)));
        var dias = ((int)DayOfWeek.Saturday - (int)hoy.DayOfWeek + 7) % 7;
        Poner("El sábado a las 08:00", DeLocal(hoy.AddDays(dias == 0 ? 7 : dias).AddHours(8)));
        return lista;
    }

    private DateTime EnLocal(long ms) => TimeZoneInfo.ConvertTime(DateTimeOffset.FromUnixTimeMilliseconds(ms), _zona).DateTime;

    private long DeLocal(DateTime local) => new DateTimeOffset(local, _zona.GetUtcOffset(local)).ToUnixTimeMilliseconds();

    /// <summary>Sube a la próxima media hora exacta en la zona del aula (22:00, 22:30…): la ventana siempre empieza en una hora redonda.</summary>
    private long AlSiguienteBloque(long ms)
    {
        var offset = _zona.GetUtcOffset(DateTimeOffset.FromUnixTimeMilliseconds(ms)).Ticks / TimeSpan.TicksPerMillisecond;
        var local = ms + offset;
        var resto = local % MediaHora;
        return resto == 0 ? ms : ms + (MediaHora - resto);
    }
}

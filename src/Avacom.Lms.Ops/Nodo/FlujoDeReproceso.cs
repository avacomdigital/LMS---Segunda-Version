using Avacom.Lms.Core.Nodo;

namespace Avacom.Lms.Ops.Nodo;

/// <summary>
/// [Reprocesar] y [Reproducir] sin MAUI (P-18, R-17): una sola confirmación, un solo envío aunque se toque dos veces, y el mensaje del resultado con qué hacer. Quien decide es el nodo
/// (el técnico sin escalada recibe «sin permiso» y aquí se dice cómo conseguirla).
/// </summary>
public sealed class FlujoDeReproceso(INodoApi api, string actor)
{
    private int _ocupado;

    public int Envios { get; private set; }
    public ProblemaDeCola? UltimoReprocesado { get; private set; }
    public ReproduccionDeConsumidor? UltimaReproduccion { get; private set; }

    /// <summary>Reprocesa UN evento apartado. Con el flujo ocupado (un segundo toque mientras el primero viaja) no envía nada.</summary>
    public async Task<MensajeDeNodo> ReprocesarAsync(long problemaId, CancellationToken ct = default)
    {
        if (Interlocked.Exchange(ref _ocupado, 1) == 1) return new MensajeDeNodo("Ya se está reprocesando", "Espera a que termine.");
        try
        {
            Envios++;
            var r = await api.ReprocesarAsync(actor ?? string.Empty, problemaId, ct);
            if (r is null) return NodoTexto.DeError(api.UltimoError);
            UltimoReprocesado = r;
            return NodoTexto.Reprocesado;
        }
        finally { Interlocked.Exchange(ref _ocupado, 0); }
    }

    /// <summary>Reproduce un consumidor desde cero (todas sus fuentes).</summary>
    public async Task<MensajeDeNodo> ReproducirAsync(string consumidor, CancellationToken ct = default)
    {
        if (Interlocked.Exchange(ref _ocupado, 1) == 1) return new MensajeDeNodo("Ya se está reproduciendo", "Espera a que termine.");
        try
        {
            Envios++;
            var r = await api.ReproducirAsync(actor ?? string.Empty, consumidor, null, ct);
            if (r is null) return NodoTexto.DeError(api.UltimoError);
            UltimaReproduccion = r;
            return NodoTexto.Reproducido;
        }
        finally { Interlocked.Exchange(ref _ocupado, 0); }
    }
}

using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Ops.Reportes;

namespace Avacom.Lms.Ops.Licencia;

/// <summary>
/// Las preferencias pequeñas con un prefijo propio: así la «última carpeta usada» de la licencia se recuerda con <see cref="PreferenciasDeDestino"/> (por persona, con la clave resumida)
/// sin mezclarse con la de los reportes.
/// </summary>
public sealed class AlmacenConPrefijo(IAlmacenDePreferencias almacen, string prefijo) : IAlmacenDePreferencias
{
    public const string DeLicencia = "licencia.";

    public string? Leer(string clave) => almacen.Leer(prefijo + clave);

    public void Guardar(string clave, string valor) => almacen.Guardar(prefijo + clave, valor);
}

/// <summary>«Confirmar la fecha de hoy» (P-06) sin MAUI: una sola confirmación, un solo envío aunque se toque dos veces, y el mensaje del resultado.</summary>
public sealed class ConfirmacionDeFecha(ILicenciaApi api, string actor)
{
    private int _ocupado;

    public int Envios { get; private set; }
    public EstadoLicencia? EstadoNuevo { get; private set; }

    public async Task<MensajeDeLicencia> ConfirmarAsync(CancellationToken ct = default)
    {
        if (Interlocked.Exchange(ref _ocupado, 1) == 1) return new MensajeDeLicencia("Ya se está confirmando", "Espera a que termine.", null);
        try
        {
            Envios++;
            var nuevo = await api.ConfirmarRelojAsync(actor ?? string.Empty, ct);
            if (nuevo is null) return LicenciaTexto.DeError(api.UltimoError) with { Titulo = "La fecha no se confirmó" };
            EstadoNuevo = nuevo;
            return new MensajeDeLicencia("Fecha confirmada", LicenciaTexto.FechaHecha, null);
        }
        finally { Interlocked.Exchange(ref _ocupado, 0); }
    }
}

namespace Avacom.Lms.Ops.Reportes.Ui;

/// <summary>
/// Una escritura LENTA a pedido, sólo con el perfil de pruebas (<c>AVACOM_OPS_ESCRITURA_LENTA_MS</c>): imita una memoria USB mala para poder ver en ventana la barra de avance, cancelar a mitad y
/// retirar la memoria mientras se guarda. Antes de la escritura segura de verdad espera ese tiempo (en diez pasos, subiendo el avance hasta la mitad) y respeta la cancelación como lo hace
/// ella: devolviendo «cancelado», sin lanzar. Sin el perfil o sin la variable devuelve null y se usa la escritura segura sin más.
/// </summary>
internal static class EscrituraLentaDePrueba
{
    public static FlujoDeExportacion.Escritor? Crear()
    {
        if (Ajustes.Perfil is null || !int.TryParse(Environment.GetEnvironmentVariable("AVACOM_OPS_ESCRITURA_LENTA_MS"), out var ms) || ms <= 0) return null;
        return async (origen, sha, bytes, carpeta, nombre, progreso, ct) =>
        {
            try
            {
                for (var paso = 1; paso <= 10; paso++)
                {
                    await Task.Delay(Math.Max(1, ms / 10), ct);
                    progreso?.Report(paso / 20.0);
                }
            }
            catch (OperationCanceledException)
            {
                return new ResultadoDeEscritura(false, null, 0, null, Avacom.Lms.Core.Reporting.MotivosDeEscritura.De(Avacom.Lms.Core.Reporting.MotivoDeEscritura.Cancelado));
            }
            return await EscrituraSegura.EscribirAsync(origen, sha, bytes, carpeta, nombre, new Mitad(progreso), ct);
        };
    }

    /// <summary>El avance de la escritura de verdad ocupa de la mitad al final de la barra.</summary>
    private sealed class Mitad(IProgress<double>? destino) : IProgress<double>
    {
        public void Report(double valor) => destino?.Report(0.5 + (Math.Clamp(valor, 0, 1) * 0.5));
    }
}

/// <summary>
/// Sólo con el perfil de pruebas de <c>tests/Avacom.Lms.Ops.Uia</c> (<c>AVACOM_OPS_PERFIL</c>): agrega a las unidades del sistema las que diga <c>AVACOM_OPS_UNIDADES_PRUEBA</c>, para ver y
/// probar en ventana lo que sin una memoria USB física no se puede (la fila «Extraíble», la política que la oculta, la memoria que se retira). Cada unidad es
/// <c>raíz|etiqueta|tipo|libre|total</c> (tipo: <c>extraible</c>, <c>fija</c> o <c>red</c>; tamaños en bytes) y varias van separadas por «;». La raíz es una carpeta real (por ejemplo la letra de un
/// <c>subst</c>): la unidad sólo «está conectada» mientras esa carpeta exista, así que borrar el <c>subst</c> equivale a retirar la memoria. Sin el perfil, esto no hace nada.
/// </summary>
internal sealed class ProveedorConUnidadesDePrueba : IProveedorDeUnidades
{
    private readonly IProveedorDeUnidades _real;
    private readonly IReadOnlyList<UnidadInfo> _extras;

    public ProveedorConUnidadesDePrueba(IProveedorDeUnidades real)
    {
        _real = real ?? throw new ArgumentNullException(nameof(real));
        _extras = Ajustes.Perfil is null ? [] : Leer(Environment.GetEnvironmentVariable("AVACOM_OPS_UNIDADES_PRUEBA"));
    }

    public IReadOnlyList<UnidadInfo> Unidades()
    {
        var lista = _real.Unidades().ToList();
        if (_extras.Count == 0) return lista;
        var presentes = _extras.Where(e => Directory.Exists(e.Raiz)).ToList();
        lista.RemoveAll(u => presentes.Any(e => string.Equals(e.Raiz.TrimEnd('\\'), u.Raiz.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase)));
        lista.AddRange(presentes);
        return lista;
    }

    internal static IReadOnlyList<UnidadInfo> Leer(string? texto)
    {
        var salida = new List<UnidadInfo>();
        foreach (var parte in (texto ?? string.Empty).Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            var c = parte.Split('|');
            if (c.Length < 5 || !long.TryParse(c[3], out var libre) || !long.TryParse(c[4], out var total)) continue;
            var tipo = c[2].ToLowerInvariant() switch { "extraible" => TipoDeUnidad.Extraible, "red" => TipoDeUnidad.Red, _ => TipoDeUnidad.Fija };
            salida.Add(new UnidadInfo(c[0], c[1], tipo, Lista: true, libre, total, EsUsb: false));
        }
        return salida;
    }
}

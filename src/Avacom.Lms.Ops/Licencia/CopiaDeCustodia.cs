using System.Text;
using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Ops.Reportes;

namespace Avacom.Lms.Ops.Licencia;

/// <summary>Cómo terminó la copia de custodia: el mensaje para la pantalla y, si salió bien, las rutas de los tres archivos.</summary>
public sealed record ResultadoDeCopia(bool Ok, MensajeDeLicencia Mensaje, IReadOnlyList<string> Rutas, FalloDeEscritura? Fallo = null, string? Detalle = null)
{
    /// <summary>¿Repetir en el MISMO destino puede arreglarlo? (se volvió a conectar la memoria, se liberó espacio, volvió la conexión con el aula).</summary>
    public bool SePuedeRepetir => Fallo?.Motivo is not (MotivoDeEscritura.SinPermiso or MotivoDeEscritura.NombreInvalido or MotivoDeEscritura.Cancelado);
}

/// <summary>
/// «Guardar copia de la licencia» (CAP-111) sin MAUI: el <c>.avlic</c> vigente (<c>GET copia/</c>), una solicitud nueva de este equipo (<c>POST solicitud/</c>) y una hoja de texto
/// (<see cref="LicenciaTexto.HojaDeCustodia"/>) que cita los nombres con que quedaron. Los tres van al destino con la escritura segura y como conjunto: o quedan los tres, o ninguno.
/// La hoja va en UTF-8 con marca y saltos de línea de Windows, para que el Bloc de notas la abra bien. Sin datos de personas ni la huella del equipo.
/// </summary>
public sealed class CopiaDeCustodia(ILicenciaApi api, string actor, EscritorDeLicencias escritor, Func<long> ahoraMs, TimeZoneInfo? zona = null)
{
    private int _ocupado;

    public async Task<ResultadoDeCopia> GuardarAsync(DestinoElegido destino, IProgress<double>? progreso = null, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(destino);
        if (Interlocked.Exchange(ref _ocupado, 1) == 1) return new ResultadoDeCopia(false, new MensajeDeLicencia("Ya se está guardando", "Espera a que termine.", null), []);
        try
        {
            var copia = await api.CopiaAsync(actor ?? string.Empty, ct);
            if (copia is null) return DelNodo();
            var solicitud = await api.SolicitudAsync(actor ?? string.Empty, ct);
            if (solicitud is null) return DelNodo();

            var licencia = ArchivoParaGuardar.DelNodo(copia, ".avlic");
            var pedido = ArchivoParaGuardar.DelNodo(solicitud, ".avreq");
            var r = await escritor.GuardarAsync(
            [
                _ => licencia,
                _ => pedido,
                escritas => Hoja(copia, solicitud, Path.GetFileName(escritas[0]), Path.GetFileName(escritas[1])),
            ], destino.Carpeta, progreso, ct);
            if (!r.Ok)
            {
                var fallo = r.Fallo!;
                return new ResultadoDeCopia(false, new MensajeDeLicencia("No se pudo guardar la copia", fallo.Mensaje, fallo.Accion), [], fallo, r.Detalle);
            }
            var carpeta = Path.GetDirectoryName(r.Rutas[0]) ?? destino.Carpeta;
            return new ResultadoDeCopia(true, new MensajeDeLicencia("Copia guardada", LicenciaTexto.CopiaGuardada(carpeta), null), r.Rutas);
        }
        finally { Interlocked.Exchange(ref _ocupado, 0); }
    }

    private ArchivoParaGuardar Hoja(CopiaDeLicencia copia, SolicitudDeLicencia solicitud, string nombreLicencia, string nombreSolicitud)
    {
        var texto = LicenciaTexto.HojaDeCustodia(copia, solicitud, nombreLicencia, nombreSolicitud, ahoraMs(), zona);
        var bytes = Encoding.UTF8.GetPreamble().Concat(Encoding.UTF8.GetBytes(texto)).ToArray();
        return new ArchivoParaGuardar(LicenciaTexto.NombreDeLaHoja, bytes);
    }

    private ResultadoDeCopia DelNodo()
    {
        var e = LicenciaTexto.DeError(api.UltimoError);
        return new ResultadoDeCopia(false, e with { Titulo = "No se pudo preparar la copia" }, []);
    }
}

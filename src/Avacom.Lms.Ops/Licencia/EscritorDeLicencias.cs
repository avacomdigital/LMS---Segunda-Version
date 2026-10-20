using System.Security.Cryptography;
using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Ops.Reportes;

namespace Avacom.Lms.Ops.Licencia;

/// <summary>Un archivo para guardar: su nombre propuesto, sus bytes y el SHA-256 con que se verifica lo escrito (el del nodo; si es null, el de los bytes).</summary>
public sealed record ArchivoParaGuardar(string Nombre, byte[] Datos, string? Sha256 = null)
{
    /// <summary>El archivo que entregó el nodo, verificado contra el SHA-256 QUE DIJO EL NODO (así un base64 dañado en el camino se descubre al guardar).</summary>
    public static ArchivoParaGuardar DelNodo(IArchivoDelNodo archivo, string extension) => new(EscritorDeLicencias.NombreSeguro(archivo.Nombre, extension), archivo.Bytes(), archivo.Sha256);
}

/// <summary>Cómo terminó un guardado de uno o varios archivos. Si no <see cref="Ok"/>, no quedó NADA de esta operación en el destino (salvo lo que <see cref="SinBorrar"/> diga).</summary>
public sealed record ResultadoDeGuardado(bool Ok, IReadOnlyList<string> Rutas, FalloDeEscritura? Fallo, string? Detalle, IReadOnlyList<string> SinBorrar)
{
    public static ResultadoDeGuardado Bien(IReadOnlyList<string> rutas) => new(true, rutas, null, null, []);
}

/// <summary>
/// Guarda los archivos de la licencia —la solicitud (<c>.avreq</c>), la copia de custodia (<c>.avlic</c> + <c>.avreq</c> + hoja <c>.txt</c>) y la prueba de liberación (<c>.avrel</c>)— en una
/// memoria USB o una carpeta, con <see cref="EscrituraSegura"/>: cada archivo va a un temporal en la misma carpeta, se vacía a la unidad, se relee sin caché, se compara con su SHA-256 y sólo
/// entonces toma su nombre, SIN sobrescribir nada (si el nombre existe, «(2)», «(3)»…). Un conjunto es todo o nada: si falla el segundo, se borra el primero que ESTA operación acaba de
/// dejar (nunca un archivo que ya estaba). Nunca lanza por un problema de la unidad. Sin MAUI: se prueba con un sistema de archivos falso.
/// </summary>
public sealed class EscritorDeLicencias(IOperacionesDeArchivo? io = null)
{
    private readonly IOperacionesDeArchivo _io = io ?? new OperacionesDeArchivoDelSistema();

    /// <summary>El nombre propuesto, seguro en cualquier sistema de archivos y con la extensión que corresponde.</summary>
    public static string NombreSeguro(string? propuesto, string extension)
    {
        var (nombre, _) = NombreDeArchivo.SepararExtension(propuesto ?? string.Empty);
        return NombreDeArchivo.Sanear(nombre, extension, "licencia");
    }

    /// <summary>Un conjunto de archivos cuyo contenido ya se conoce.</summary>
    public Task<ResultadoDeGuardado> GuardarAsync(IReadOnlyList<ArchivoParaGuardar> archivos, string carpeta, IProgress<double>? progreso = null, CancellationToken ct = default) =>
        GuardarAsync(archivos.Select(a => (Func<IReadOnlyList<string>, ArchivoParaGuardar>)(_ => a)).ToList(), carpeta, progreso, ct);

    /// <summary>
    /// Un conjunto donde un archivo puede depender de los nombres FINALES de los anteriores (la hoja de la copia cita los nombres con que quedaron la licencia y la solicitud, que pueden
    /// llevar «(2)»). Cada fábrica recibe las rutas ya escritas por esta operación.
    /// </summary>
    public async Task<ResultadoDeGuardado> GuardarAsync(IReadOnlyList<Func<IReadOnlyList<string>, ArchivoParaGuardar>> fabricas, string carpeta, IProgress<double>? progreso = null,
                                                       CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(fabricas);
        ArgumentNullException.ThrowIfNull(carpeta);
        var escritas = new List<string>();
        for (var i = 0; i < fabricas.Count; i++)
        {
            ArchivoParaGuardar archivo;
            try { archivo = fabricas[i](escritas); }
            catch (Exception e)
            {
                var pendientes = Revertir(escritas);
                return new ResultadoDeGuardado(false, [], MotivosDeEscritura.De(MotivoDeEscritura.Otro), "No se pudo preparar el archivo: " + MotivosDeEscritura.Detalle(e), pendientes);
            }
            var sha = string.IsNullOrWhiteSpace(archivo.Sha256) ? Convert.ToHexStringLower(SHA256.HashData(archivo.Datos)) : archivo.Sha256!;
            var tramo = new Tramo(progreso, i, fabricas.Count);
            ResultadoDeEscritura r;
            using (var origen = new MemoryStream(archivo.Datos, writable: false))
                r = await EscrituraSegura.EscribirAsync(origen, sha, archivo.Datos.Length, carpeta, archivo.Nombre, tramo, ct, _io).ConfigureAwait(false);
            if (!r.Ok)
            {
                // Todo o nada: lo que ESTA operación ya dejó en el destino se quita (nunca lo que ya estaba: EscrituraSegura no sobrescribe).
                var pendientes = Revertir(escritas);
                var detalle = pendientes.Count == 0 ? r.Detalle : $"{r.Detalle} | quedaron sin borrar {pendientes.Count} archivo(s) de esta operación";
                return new ResultadoDeGuardado(false, [], r.Fallo ?? MotivosDeEscritura.De(MotivoDeEscritura.Otro), detalle, pendientes);
            }
            escritas.Add(r.RutaFinal!);
        }
        try { progreso?.Report(1.0); } catch { /* quien escucha el avance no puede hacer fallar el guardado */ }
        return ResultadoDeGuardado.Bien(escritas);
    }

    /// <summary>Borra lo que esta operación escribió. Devuelve lo que no se pudo borrar (la unidad ya no está, o no deja).</summary>
    private List<string> Revertir(IEnumerable<string> rutas)
    {
        var sinBorrar = new List<string>();
        foreach (var ruta in rutas)
        {
            try { _io.Borrar(ruta); }
            catch (Exception e) when (e is DirectoryNotFoundException or DriveNotFoundException or FileNotFoundException) { /* ya no está: nada que borrar */ }
            catch { sinBorrar.Add(ruta); }
        }
        return sinBorrar;
    }

    /// <summary>El avance de un archivo dentro del conjunto: el archivo i de n ocupa su tramo de la barra.</summary>
    private sealed class Tramo(IProgress<double>? destino, int indice, int total) : IProgress<double>
    {
        public void Report(double valor)
        {
            if (destino is null || total <= 0) return;
            try { destino.Report(Math.Clamp((indice + Math.Clamp(valor, 0, 1)) / total, 0, 1)); }
            catch { /* idem */ }
        }
    }
}

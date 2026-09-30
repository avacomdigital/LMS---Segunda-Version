using System.Buffers;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net;
using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Estudio;

/// <summary>
/// Baja un paquete de estudio completo (CAP-047, FUN-084): pide el paquete al nodo si aún no lo tiene, baja el manifiesto y VERIFICA su huella,
/// baja cada archivo REANUDANDO desde lo ya escrito (<c>Range</c>) y cifrándolo al escribirlo, verifica el SHA-256 de cada archivo y confirma
/// con el nodo. Pausar es cancelar el token: lo bajado queda a salvo (sólo se pierde la cola de menos de 64 KiB que aún no era un bloque
/// completo) y volver a llamar continúa donde se quedó. Nunca lanza por la red ni por el nodo: devuelve un <see cref="ResultadoDescarga"/>.
///
/// Resultados: <c>Completa</c> · <c>Pausada</c> (token cancelado) · <c>SinConexion</c> (sin red o se cortó a media descarga; queda pausado y
/// reanudable) · <c>Denegada</c> (BR-054: aparato compartido o el profesor no permite el paquete) · <c>Vencida</c> (410) ·
/// <c>HuellaInvalida</c> (la huella del manifiesto, el sha256 de un archivo o la confirmación no coinciden) · <c>SinEspacio</c> ·
/// <c>Fallida</c> (cualquier otra cosa). Tras un resultado que no es <c>Completa</c>, <see cref="UltimoError"/> y <see cref="UltimoMotivo"/> dicen por qué.
/// </summary>
/// <param name="api">El cliente de <c>/api/modo-estudio/</c>.</param>
/// <param name="almacen">El almacén donde se escribe el paquete.</param>
/// <param name="ahoraNodoMs">Reloj del nodo con el que se juzga la vigencia de lo que ya se tenía (por defecto <see cref="RelojNodo.AhoraMs"/>).</param>
/// <param name="esperaSinDatos">Cuánto se espera sin que llegue un solo byte antes de dar la descarga por cortada (por defecto 30 s). Un Wi-Fi que se
/// va sin avisar no cierra la conexión: sin este límite la lectura quedaría colgada hasta que el sistema se rinda, minutos después.</param>
public sealed class DescargadorDePaquetes(IEstudioApi api, AlmacenEstudio almacen, Func<long>? ahoraNodoMs = null, TimeSpan? esperaSinDatos = null) : IDescargadorDePaquetes
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private readonly Func<long> ahora = ahoraNodoMs ?? (() => RelojNodo.AhoraMs);
    private readonly TimeSpan esperaMaxima = esperaSinDatos is { } espera && espera > TimeSpan.Zero ? espera : TimeSpan.FromSeconds(30);
    private readonly ConcurrentDictionary<string, byte> enCurso = new();

    /// <summary>El error del nodo que detuvo la última descarga (por ejemplo <c>descarga_denegada</c> con el mensaje MSG-046 en <c>Extra</c>); nulo si no fue un error del nodo.</summary>
    public ErrorAula? UltimoError { get; private set; }

    /// <summary>El motivo, en palabras, de que la última descarga no terminara; nulo si terminó.</summary>
    public string? UltimoMotivo { get; private set; }

    public Task<ResultadoDescarga> DescargarAsync(string dispositivo, string alumnoId, string asignacionId, IProgress<ProgresoDescarga>? progreso = null,
                                                  CancellationToken ct = default) =>
        EjecutarAsync(dispositivo, alumnoId, asignacionId, progreso, actualizar: false, ct);

    /// <summary>
    /// «Actualizar descarga»: vuelve a pedir el paquete al nodo aunque ya esté disponible (el nodo refresca su manifiesto y su vigencia) y baja
    /// sólo lo que cambió: los archivos con el mismo sha256 se conservan.
    /// </summary>
    public Task<ResultadoDescarga> ActualizarAsync(string dispositivo, string alumnoId, string asignacionId, IProgress<ProgresoDescarga>? progreso = null,
                                                   CancellationToken ct = default) =>
        EjecutarAsync(dispositivo, alumnoId, asignacionId, progreso, actualizar: true, ct);

    // ------------------------------------------------------------------------------- el avance

    /// <summary>Lo que se va bajando y cómo se le cuenta a la pantalla: bytes, fracción, velocidad y tiempo restante estimados.</summary>
    private sealed class Avance(IProgress<ProgresoDescarga>? progreso, string asignacionId)
    {
        private readonly Stopwatch reloj = Stopwatch.StartNew();
        private long ultimoMs = long.MinValue / 2;

        public long Total { get; set; }
        /// <summary>Bytes que hay de cada archivo (completos o a medias): su suma es lo descargado.</summary>
        public Dictionary<string, long> PorArchivo { get; } = new(StringComparer.Ordinal);
        /// <summary>Lo descargado cuando no hay archivos que contar (un paquete que ya estaba disponible).</summary>
        public long? HechoFijo { get; set; }
        /// <summary>Bytes que llegaron por la red en ESTA llamada: la base de la velocidad (lo que ya estaba en disco no cuenta).</summary>
        public long BytesSesion { get; set; }
        public string? Archivo { get; set; }
        public long Hecho => HechoFijo ?? PorArchivo.Values.Sum();

        /// <summary>Informa a la pantalla. Sin <paramref name="forzar"/> lo hace a lo sumo cada 200 ms, para no inundar la interfaz.</summary>
        public void Reportar(string estado, bool forzar = false)
        {
            if (progreso is null) return;
            var ms = reloj.ElapsedMilliseconds;
            if (!forzar && ms - ultimoMs < 200) return;
            ultimoMs = ms;
            var hecho = Hecho;
            double? velocidad = BytesSesion > 0 && ms >= 200 ? BytesSesion * 1000.0 / ms : null;
            TimeSpan? restante = velocidad is > 0 ? TimeSpan.FromSeconds(Math.Max(0, Total - hecho) / velocidad.Value) : null;
            var fraccion = Total <= 0 ? (estado == "disponible" ? 1 : 0) : Math.Clamp((double)hecho / Total, 0, 1);
            try { progreso.Report(new ProgresoDescarga(asignacionId, hecho, Total, fraccion, Archivo, velocidad, restante, estado)); }
            catch (Exception) { /* una pantalla que ya no está no debe detener la descarga */ }
        }
    }

    // ------------------------------------------------------------------------------- el recorrido

    private async Task<ResultadoDescarga> EjecutarAsync(string dispositivo, string alumnoId, string asignacionId, IProgress<ProgresoDescarga>? progreso,
                                                        bool actualizar, CancellationToken ct)
    {
        var llave = alumnoId + "\n" + asignacionId;
        if (!enCurso.TryAdd(llave, 0))
        {
            // Dos llamadas a la vez para la misma lección se pisarían el archivo a medias: la segunda no hace nada y lo dice.
            UltimoError = null;
            UltimoMotivo = "Ya hay una descarga de esta lección en curso.";
            return ResultadoDescarga.Fallida;
        }
        var avance = new Avance(progreso, asignacionId);
        try
        {
            UltimoError = null;
            UltimoMotivo = null;
            return await RecorrerAsync(dispositivo, alumnoId, asignacionId, avance, actualizar, ct);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            return Pausar(alumnoId, asignacionId, avance);
        }
        catch (OperationCanceledException)
        {
            // Una cancelación que no es del llamador (el tiempo de espera de la red): es una descarga interrumpida y reanudable.
            return Terminar(ResultadoDescarga.SinConexion, alumnoId, asignacionId, avance, error: null, motivo: "Se agotó el tiempo de espera de la conexión con el aula.");
        }
        catch (Exception ex) when (ex is not OutOfMemoryException)
        {
            // El disco, el cifrado o un cuerpo inesperado del nodo: para quien llama es una descarga fallida y reanudable, no una excepción.
            return Terminar(ResultadoDescarga.Fallida, alumnoId, asignacionId, avance, error: null, motivo: ex.Message);
        }
        finally
        {
            enCurso.TryRemove(llave, out _);
        }
    }

    private async Task<ResultadoDescarga> RecorrerAsync(string dispositivo, string alumnoId, string asignacionId, Avance avance, bool actualizar, CancellationToken ct)
    {
        var local = almacen.ObtenerPaquete(alumnoId, asignacionId);
        var vigente = local is not null && local.Estado != "vencido" && !(local.VigenteHasta is { } hasta && ahora() > hasta);
        if (vigente && local!.Disponible && !actualizar)
        {
            avance.Total = local.BytesTotal;
            avance.HechoFijo = local.BytesTotal;
            avance.Reportar("disponible", forzar: true);
            return ResultadoDescarga.Completa;
        }

        // (a) el paquete: si ya se pidió y sigue vigente se continúa ese; si no, se pide al nodo (403 → denegado; 410 → vencido)
        string paqueteId;
        var pedidoAhora = false;
        if (vigente && !actualizar && local!.Estado is "descargando" or "pausado")
        {
            paqueteId = local.PaqueteId;
        }
        else
        {
            var (paquete, fallo) = await PedirAsync(dispositivo, alumnoId, asignacionId, avance, ct);
            if (fallo is { } f) return f;
            paqueteId = paquete!.Id;
            pedidoAhora = true;
        }

        // (b) el manifiesto, tal como llegó, con su huella verificada
        string? crudo;
        while (true)
        {
            crudo = await api.ManifiestoCrudoAsync(dispositivo, paqueteId, alumnoId, ct);
            if (crudo is not null) break;
            ct.ThrowIfCancellationRequested();
            var error = api.UltimoError;
            if (error is { Estado: 404 } && !pedidoAhora)
            {
                // El nodo ya no conoce ese paquete (lo retiró o lo rehízo): se pide de nuevo, una sola vez.
                pedidoAhora = true;
                var (nuevo, fallo) = await PedirAsync(dispositivo, alumnoId, asignacionId, avance, ct);
                if (fallo is { } f) return f;
                paqueteId = nuevo!.Id;
                continue;
            }
            return Terminar(Clasificar(error), alumnoId, asignacionId, avance, error);
        }

        ManifiestoPaquete? manifiesto;
        try
        {
            using var documento = JsonDocument.Parse(crudo);
            var raiz = documento.RootElement;
            if (raiz.ValueKind != JsonValueKind.Object || !raiz.TryGetProperty("huella", out var declarada) || declarada.ValueKind != JsonValueKind.String
                || !JsonCanonico.CoincideConHuella(raiz, declarada.GetString()!))
                return Terminar(ResultadoDescarga.HuellaInvalida, alumnoId, asignacionId, avance, null, "La huella del manifiesto no coincide: llegó alterado o incompleto.");
            manifiesto = raiz.Deserialize<ManifiestoPaquete>(Json);
        }
        catch (JsonException)
        {
            return Terminar(ResultadoDescarga.Fallida, alumnoId, asignacionId, avance, null, "El manifiesto del paquete no se pudo leer.");
        }
        if (manifiesto is null || manifiesto.PaqueteId != paqueteId)
            return Terminar(ResultadoDescarga.Fallida, alumnoId, asignacionId, avance, null, "El manifiesto no corresponde al paquete pedido.");
        // Sin el sha256 de un archivo no hay forma de comprobar lo que se baje: el manifiesto está mal armado y no se descarga nada.
        if (manifiesto.Archivos.Any(a => string.IsNullOrWhiteSpace(a.Sha256) || a.Bytes < 0))
            return Terminar(ResultadoDescarga.HuellaInvalida, alumnoId, asignacionId, avance, null, "El manifiesto trae un archivo sin sha256 o con un tamaño inválido.");
        almacen.GuardarManifiesto(alumnoId, asignacionId, crudo, manifiesto);
        var archivos = manifiesto.Archivos.GroupBy(a => a.MediaRef, StringComparer.Ordinal).Select(g => g.First()).ToList();   // un medio repetido cuenta una sola vez

        // (c) qué falta y si cabe
        long total = 0, faltaEnDisco = 0;
        var pendientes = 0;
        foreach (var a in archivos)
        {
            total += a.Bytes;
            var (completo, bytes) = almacen.EstadoDeArchivo(alumnoId, asignacionId, a.MediaRef);
            avance.PorArchivo[a.MediaRef] = completo ? a.Bytes : Math.Min(bytes, a.Bytes);
            if (completo) continue;
            pendientes++;
            faltaEnDisco += ArchivoCifrado.LongitudDelArchivo(a.Bytes) - (bytes > 0 ? ArchivoCifrado.LongitudDelArchivo(Math.Min(bytes, a.Bytes)) : 0);
        }
        avance.Total = total;
        if (pendientes == 0 && almacen.ObtenerPaquete(alumnoId, asignacionId) is { Estado: "disponible" })
        {
            avance.Reportar("disponible", forzar: true);
            return ResultadoDescarga.Completa;      // «Actualizar descarga» y nada cambió
        }
        if (faltaEnDisco > 0 && almacen.EspacioLibreBytes() is { } libre && libre < faltaEnDisco)
            return Terminar(ResultadoDescarga.SinEspacio, alumnoId, asignacionId, avance, null, "No hay espacio libre suficiente para descargar la lección.");

        // (d) cada archivo, en orden
        almacen.PublicarEstado(alumnoId, asignacionId, "descargando");
        avance.Reportar("descargando", forzar: true);
        foreach (var archivo in archivos)
        {
            ct.ThrowIfCancellationRequested();
            if (await BajarArchivoAsync(dispositivo, alumnoId, asignacionId, paqueteId, archivo, avance, ct) is { } fallo) return fallo;
        }

        // (e) todo bajado y verificado: se confirma con el nodo y el paquete queda disponible
        var confirmado = await api.ConfirmarPaqueteAsync(dispositivo, paqueteId, manifiesto.Huella, total, alumnoId, ct);
        if (confirmado is null)
        {
            ct.ThrowIfCancellationRequested();
            var error = api.UltimoError;
            return Terminar(Clasificar(error), alumnoId, asignacionId, avance, error);
        }
        almacen.MarcarDisponible(alumnoId, asignacionId, confirmado);
        avance.Reportar("disponible", forzar: true);
        return ResultadoDescarga.Completa;
    }

    /// <summary>Pide el paquete al nodo. Devuelve el paquete o, si no se pudo, el resultado con que termina la descarga.</summary>
    private async Task<(PaqueteEstudio? Paquete, ResultadoDescarga? Fallo)> PedirAsync(string dispositivo, string alumnoId, string asignacionId, Avance avance, CancellationToken ct)
    {
        var paquete = await api.SolicitarPaqueteAsync(dispositivo, asignacionId, alumnoId, ct);
        if (paquete is null)
        {
            ct.ThrowIfCancellationRequested();
            var error = api.UltimoError;
            return (null, Terminar(Clasificar(error), alumnoId, asignacionId, avance, error));
        }
        if (paquete.Denegado)
            return (null, Terminar(ResultadoDescarga.Denegada, alumnoId, asignacionId, avance, null, $"El nodo no permite descargar esta lección en este aparato ({paquete.Motivo})."));
        if (paquete.Vencido)
            return (null, Terminar(ResultadoDescarga.Vencida, alumnoId, asignacionId, avance, null, "El paquete de esta lección ya venció."));
        almacen.RegistrarPaquete(alumnoId, paquete);
        return (paquete, null);
    }

    /// <summary>
    /// Baja UN archivo del paquete (o continúa el que quedó a medias) y lo verifica. Devuelve null si quedó completo y verificado; si no, el
    /// resultado con que termina la descarga.
    /// </summary>
    private async Task<ResultadoDescarga?> BajarArchivoAsync(string dispositivo, string alumnoId, string asignacionId, string paqueteId, ArchivoPaquete archivo,
                                                             Avance avance, CancellationToken ct)
    {
        if (almacen.EstadoDeArchivo(alumnoId, asignacionId, archivo.MediaRef).Completo) return null;
        avance.Archivo = archivo.MediaRef;

        var escritor = almacen.AbrirEscritura(alumnoId, asignacionId, archivo.MediaRef);
        if (escritor.BytesEnClaro > archivo.Bytes)
        {
            // Lo escrito es más largo que el archivo del manifiesto: no es de esta versión. Se empieza de cero.
            escritor.Dispose();
            almacen.DescartarArchivo(alumnoId, asignacionId, archivo.MediaRef);
            escritor = almacen.AbrirEscritura(alumnoId, asignacionId, archivo.MediaRef);
        }

        string sha;
        using (escritor)
        {
            avance.PorArchivo[archivo.MediaRef] = escritor.BytesEnClaro;
            if (escritor.BytesEnClaro < archivo.Bytes)
            {
                var pedido = escritor.BytesEnClaro;
                using var respuesta = await api.ArchivoAsync(dispositivo, paqueteId, archivo.MediaRef, pedido > 0 ? pedido : null, alumnoId, ct);
                if (respuesta is null)
                {
                    ct.ThrowIfCancellationRequested();
                    var error = api.UltimoError;
                    if (error is { Estado: 416 })
                    {
                        // El nodo dice que lo pedido queda fuera del archivo: el archivo del nodo no es el del manifiesto. Se tira lo escrito.
                        escritor.Dispose();
                        almacen.DescartarArchivo(alumnoId, asignacionId, archivo.MediaRef);
                        return Terminar(ResultadoDescarga.Fallida, alumnoId, asignacionId, avance, error, "El archivo del nodo no coincide con el manifiesto.");
                    }
                    return Terminar(Clasificar(error), alumnoId, asignacionId, avance, error);
                }

                // 206 empalma en el byte pedido; 200 es el archivo entero (el nodo ignoró Range): se saltan los bytes que ya se tenían.
                var inicio = respuesta.StatusCode == HttpStatusCode.PartialContent ? respuesta.Content.Headers.ContentRange?.From ?? pedido : 0;
                if (inicio > pedido)
                    return Terminar(ResultadoDescarga.Fallida, alumnoId, asignacionId, avance, null, "El nodo respondió un tramo que no empalma con lo ya descargado.");
                var saltar = pedido - inicio;

                Stream flujo;
                try { flujo = await respuesta.Content.ReadAsStreamAsync(ct); }
                catch (Exception ex) when (ex is HttpRequestException or IOException)
                {
                    ct.ThrowIfCancellationRequested();
                    return Terminar(ResultadoDescarga.SinConexion, alumnoId, asignacionId, avance, null, "Se cortó la conexión con el aula.");
                }

                var cortado = false;
                var exceso = false;
                var buffer = ArrayPool<byte>.Shared.Rent(64 * 1024);
                // Un solo temporizador para todas las lecturas: cada una lo reprograma. Si vence, el nodo lleva demasiado callado y la descarga se da por cortada.
                using var sinDatos = CancellationTokenSource.CreateLinkedTokenSource(ct);
                try
                {
                    await using (flujo)
                    {
                        while (true)
                        {
                            int n;
                            sinDatos.CancelAfter(esperaMaxima);
                            try { n = await flujo.ReadAsync(buffer.AsMemory(), sinDatos.Token); }
                            catch (OperationCanceledException) when (!ct.IsCancellationRequested)
                            {
                                cortado = true;   // se agotó la espera sin datos: no fue el alumno quien pausó
                                break;
                            }
                            catch (Exception ex) when (ex is HttpRequestException or IOException)
                            {
                                ct.ThrowIfCancellationRequested();   // cancelar puede llegar como un IOException con la cancelación dentro
                                cortado = true;
                                break;
                            }
                            if (n == 0) break;
                            if (!Aplicar(escritor, buffer, n, ref saltar, archivo.Bytes, avance, archivo.MediaRef)) { exceso = true; break; }
                            avance.Reportar("descargando");
                        }
                    }
                }
                finally
                {
                    ArrayPool<byte>.Shared.Return(buffer);
                }

                if (exceso)
                {
                    escritor.Dispose();
                    almacen.DescartarArchivo(alumnoId, asignacionId, archivo.MediaRef);
                    return Terminar(ResultadoDescarga.HuellaInvalida, alumnoId, asignacionId, avance, null, "El nodo entregó más bytes de los que declara el manifiesto.");
                }
                if (cortado || escritor.BytesEnClaro < archivo.Bytes)
                    return Terminar(ResultadoDescarga.SinConexion, alumnoId, asignacionId, avance, null, "La descarga se interrumpió; se reanudará donde quedó.");
            }
            escritor.Cerrar();
            sha = escritor.Sha256Hex();
        }

        if (!string.Equals(sha, archivo.Sha256, StringComparison.OrdinalIgnoreCase))
        {
            almacen.DescartarArchivo(alumnoId, asignacionId, archivo.MediaRef);
            avance.PorArchivo[archivo.MediaRef] = 0;
            return Terminar(ResultadoDescarga.HuellaInvalida, alumnoId, asignacionId, avance, null, "El sha256 de un archivo descargado no coincide con el del manifiesto: se descartó.");
        }
        almacen.CompletarArchivo(alumnoId, asignacionId, archivo.MediaRef);
        avance.PorArchivo[archivo.MediaRef] = archivo.Bytes;
        avance.Reportar("descargando", forzar: true);
        return null;
    }

    /// <summary>Escribe lo que llegó (sin los bytes que ya se tenían). Falso si el nodo mandó más de lo que declara el manifiesto.</summary>
    private static bool Aplicar(EscritorCifrado escritor, byte[] buffer, int n, ref long saltar, long esperado, Avance avance, string mediaRef)
    {
        var datos = buffer.AsSpan(0, n);
        if (saltar > 0)
        {
            var descartar = (int)Math.Min(saltar, n);
            saltar -= descartar;
            datos = datos[descartar..];
            if (datos.IsEmpty) return true;
        }
        if (datos.Length > esperado - escritor.BytesEnClaro) return false;
        escritor.Escribir(datos);
        avance.BytesSesion += datos.Length;
        avance.PorArchivo[mediaRef] = escritor.BytesEnClaro;
        return true;
    }

    // ------------------------------------------------------------------------------ cómo termina

    /// <summary>Qué resultado corresponde a un error del nodo. Sin conexión es <c>Estado == 0</c>; un 5xx o un 401 es un fallo del nodo, no de la red.</summary>
    private static ResultadoDescarga Clasificar(ErrorAula? error)
    {
        if (error is null) return ResultadoDescarga.Fallida;
        if (error.Estado == 0) return ResultadoDescarga.SinConexion;
        if (error.Codigo == "descarga_denegada") return ResultadoDescarga.Denegada;
        if (error.Estado == 410 || error.Codigo == "paquete_vencido") return ResultadoDescarga.Vencida;
        if (error.Codigo == "huella_invalida") return ResultadoDescarga.HuellaInvalida;
        return ResultadoDescarga.Fallida;
    }

    /// <summary>
    /// Deja constancia de por qué se detuvo la descarga y del estado del paquete: «pausado» (reanudable), o «vencido» si el nodo dijo 410. Un
    /// paquete que ya estaba disponible no cambia (fallar al actualizar no lo daña).
    /// </summary>
    private ResultadoDescarga Terminar(ResultadoDescarga resultado, string alumnoId, string asignacionId, Avance avance, ErrorAula? error = null, string? motivo = null)
    {
        UltimoError = error;
        UltimoMotivo = motivo ?? error?.Detalle;
        var estado = resultado == ResultadoDescarga.Vencida ? "vencido" : "pausado";
        try { almacen.PublicarEstado(alumnoId, asignacionId, estado); }
        catch (Exception) { /* el estado es una comodidad para la pantalla: lo bajado sigue en su sitio */ }
        avance.Reportar(estado, forzar: true);
        return resultado;
    }

    private ResultadoDescarga Pausar(string alumnoId, string asignacionId, Avance avance)
    {
        UltimoError = null;
        UltimoMotivo = null;
        try { almacen.PublicarEstado(alumnoId, asignacionId, "pausado"); }
        catch (Exception) { /* idem */ }
        avance.Reportar("pausado", forzar: true);
        return ResultadoDescarga.Pausada;
    }
}

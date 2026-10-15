using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ops.Reportes;

/// <summary>Cómo terminó un intento de guardar el reporte (la hoja de exportar decide qué pantalla mostrar con esto).</summary>
public enum EstadoDelGuardado
{
    /// <summary>Escrito en el destino, releído y confirmado ante el nodo: entregado.</summary>
    Guardado,
    /// <summary>Escrito y releído, pero el nodo no pudo anotarlo (sin conexión, caducó…): el archivo está bien; <see cref="FlujoDeExportacion.ReintentarConfirmacionAsync"/> vuelve a intentarlo.</summary>
    GuardadoSinConfirmar,
    /// <summary>No se pudo escribir en ese destino (memoria retirada, sin espacio…): no quedó nada a medias; se puede elegir otro destino SIN generar de nuevo.</summary>
    NoSePudoEscribir,
    /// <summary>El nodo no autorizó la exportación (la política, el permiso, una razón que falta…).</summary>
    NoAutorizado,
    /// <summary>No hubo conexión con el aula: no se generó nada.</summary>
    SinConexion,
    /// <summary>El archivo llegó dañado desde el nodo o no se pudo guardar en un temporal de este equipo: hay que volver a generarlo.</summary>
    ArchivoDanado,
    /// <summary>La persona canceló.</summary>
    Cancelado,
}

/// <summary>
/// El resultado de un intento, con las dos frases que la pantalla necesita: <see cref="Mensaje"/> (qué pasó) y <see cref="Accion"/> (qué puede hacer la persona). En
/// <see cref="Fallo"/> y <see cref="ErrorDelNodo"/> viene lo técnico para la bitácora; nunca para la pantalla.
/// </summary>
public sealed record ResultadoDelGuardado(EstadoDelGuardado Estado, string Mensaje, string? Accion, string? RutaFinal = null, long Bytes = 0, FalloDeEscritura? Fallo = null,
                                          ErrorAula? ErrorDelNodo = null, string? Detalle = null, TipoDeDestino? Tipo = null)
{
    public bool Escrito => Estado is EstadoDelGuardado.Guardado or EstadoDelGuardado.GuardadoSinConfirmar;
}

/// <summary>Un destino ya decidido: la carpeta donde se escribe y de qué clase de lugar es (lo que viaja al nodo es la clase, nunca la ruta).</summary>
public sealed record DestinoElegido(string Carpeta, TipoDeDestino Tipo);

/// <summary>
/// El flujo de exportar un reporte a un archivo (FUN-146) sin nada de interfaz: autorizar y bajar el archivo del nodo a un temporal, escribirlo con
/// <see cref="EscrituraSegura"/> y registrar el resultado en dos tiempos (<c>…/confirmar/</c>). Lo que hace la hoja de exportar es llamar a esto y pintar lo que devuelve.
///
/// Reglas que se prueban aparte:
/// <list type="bullet">
/// <item>Un archivo ya autorizado y bajado SE REUTILIZA si la escritura falla y la persona elige otro destino (no se vuelve a generar), mientras siga vigente y no cambie el
/// formato ni la razón; si caducó o cambió algo, se autoriza otra vez solo.</item>
/// <item>Un fallo de escritura se avisa al nodo con el motivo de la lista cerrada (sin ruta, sin nombre) y NO cierra la exportación.</item>
/// <item>Sólo se confirma «guardado» con la huella que se RELEYÓ de la unidad, nunca con la que prometió el nodo.</item>
/// <item>Escrito y releído pero sin poder avisar al nodo: el archivo se da por bueno (es lo que importa) y la confirmación queda pendiente de reintentar.</item>
/// <item>El temporal se borra siempre al terminar: al guardar, al cancelar, al soltar el flujo.</item>
/// </list>
/// </summary>
public sealed class FlujoDeExportacion : IDisposable
{
    /// <summary>Cuánto antes de que expire se da una autorización por vencida: el tiempo de escribir en una memoria lenta no debe agotarla a mitad.</summary>
    internal static readonly TimeSpan Margen = TimeSpan.FromSeconds(45);

    /// <summary>De cuánto del avance total es la bajada del archivo desde el nodo (el resto es escribir y verificar).</summary>
    internal const double PesoDeLaBajada = 0.35;

    /// <summary>Quien escribe: por omisión, la escritura segura. Las pruebas ponen otra.</summary>
    public delegate Task<ResultadoDeEscritura> Escritor(Stream origen, string sha256Esperado, long bytesEsperados, string carpetaDestino, string nombreSeguro,
                                                        IProgress<double>? progreso, CancellationToken ct);

    private readonly IReportesApi _api;
    private readonly string _actor;
    private readonly string _carpetaTemporal;
    private readonly Escritor _escribir;
    private readonly Func<long> _ahoraMs;

    private ArchivoExportado? _archivo;
    private string? _formatoDelArchivo, _razonDelArchivo;
    private volatile bool _dispuesto;
    private (string Id, TipoDeDestino Tipo, string Huella, string Ruta, long Bytes)? _sinConfirmar;

    public FlujoDeExportacion(IReportesApi api, string actor, ReporteSolicitado reporte, string carpetaTemporal, Escritor? escritor = null, Func<long>? ahoraMs = null)
    {
        _api = api ?? throw new ArgumentNullException(nameof(api));
        _actor = actor ?? throw new ArgumentNullException(nameof(actor));
        Reporte = reporte ?? throw new ArgumentNullException(nameof(reporte));
        _carpetaTemporal = carpetaTemporal ?? throw new ArgumentNullException(nameof(carpetaTemporal));
        _escribir = escritor ?? ((origen, sha, bytes, carpeta, nombre, progreso, ct) => EscrituraSegura.EscribirAsync(origen, sha, bytes, carpeta, nombre, progreso, ct));
        _ahoraMs = ahoraMs ?? (() => RelojNodo.AhoraMs);
    }

    public ReporteSolicitado Reporte { get; }

    /// <summary>
    /// Quién anota —en el registro local, que lo entrega al nodo— un destino que falló, con su detalle técnico SIN rutas. Es la red de seguridad de lo que no se pudo probar sin una memoria
    /// física: un código de Windows que la tabla de <see cref="MotivosDeEscritura"/> no conoce sale como «No se pudo guardar el archivo» y aquí queda el código completo para ampliarla.
    /// Nunca lanza; no se llama cuando la persona canceló.
    /// </summary>
    public Action<ResultadoDelGuardado, TipoDeDestino>? AlFallarLaEscritura { get; init; }

    private void AnotarFallo(ResultadoDelGuardado resultado, TipoDeDestino tipo)
    {
        try { AlFallarLaEscritura?.Invoke(resultado, tipo); }
        catch (Exception) { /* anotar es de mejor esfuerzo: lo que se le dice a la persona no depende de ello */ }
    }

    /// <summary>¿Hay un archivo ya bajado que se puede escribir en otro destino sin generar de nuevo?</summary>
    public bool TieneArchivoListo => _archivo is not null && !HaVencido(_archivo);

    /// <summary>¿Quedó un archivo escrito cuyo registro ante el nodo está pendiente?</summary>
    public bool HayConfirmacionPendiente => _sinConfirmar is not null;

    /// <summary>El error del último intento del cliente (para quien necesita más que el mensaje: sin conexión, código).</summary>
    public ErrorAula? UltimoError => _api.UltimoError;

    // ---------------------------------------------------------------------------------------------------- el alcance (no genera nada)

    /// <summary>Lo que se va a guardar, antes de confirmar: qué trae, si lleva nombres, hasta qué corte llegan los datos y la política del administrador. No genera ni registra nada.</summary>
    public Task<AlcanceDeExportacion?> AlcanceAsync(string formato, CancellationToken ct = default) => _api.AlcanceAsync(_actor, Reporte, formato, ct);

    // ---------------------------------------------------------------------------------------------------------------- guardar

    public async Task<ResultadoDelGuardado> GuardarAsync(DestinoElegido destino, string formato, string? razonCodigo, IProgress<double>? progreso = null, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(destino);
        var razon = string.IsNullOrWhiteSpace(razonCodigo) ? null : razonCodigo;

        // 1. El archivo del nodo: se reutiliza el que ya se bajó si sigue valiendo. Sigue valiendo si es el mismo formato, la misma razón Y la misma CLASE de destino: el nodo aplica su política al
        // autorizar (por clase de destino), así que cambiar de una carpeta del equipo a una memoria USB —que el administrador pudo cerrar mientras tanto— vuelve a pasar por el nodo.
        var yaBajado = _archivo is not null && _formatoDelArchivo == formato && _razonDelArchivo == razon && _archivo.DestinoAutorizado == destino.Tipo.Codigo() && !HaVencido(_archivo);
        if (!yaBajado)
        {
            SoltarArchivo();
            ArchivoExportado? bajado;
            try
            {
                bajado = await _api.AutorizarExportacionAsync(_actor, Reporte, formato, destino.Tipo.Codigo(), razon, _carpetaTemporal, new Escalado(progreso, 0, PesoDeLaBajada), ct);
            }
            catch (OperationCanceledException)
            {
                return CanceladoAntesDeEscribir();
            }
            // El cliente cuenta una cancelación durante la petición como «sin conexión»: aquí se sabe que fue la persona.
            if (bajado is null) return ct.IsCancellationRequested ? CanceladoAntesDeEscribir() : DelNodo(_api.UltimoError, _api.UltimoMotivo);
            (_archivo, _formatoDelArchivo, _razonDelArchivo) = (bajado, formato, razon);
        }
        var archivo = _archivo!;
        var comienzo = yaBajado ? 0 : PesoDeLaBajada;

        // 2. Escribir en el destino, con todas las comprobaciones.
        var nombre = NombreDeArchivo.Sanear(archivo.NombreArchivo, FormatosDeExportacion.Extension(archivo.Formato));
        ResultadoDeEscritura escrito;
        try
        {
            // FileShare.Delete: si la hoja se cierra a mitad de la escritura, Dispose() puede borrar el temporal aunque este flujo siga abierto (Windows lo quita cuando se cierra el
            // último manejador). Sin él, el borrado fallaba y un temporal con nombres de alumnos se quedaba en la caché hasta el próximo arranque.
            await using var origen = new FileStream(archivo.RutaTemporal, FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete, 81_920, FileOptions.Asynchronous | FileOptions.SequentialScan);
            escrito = await _escribir(origen, archivo.Huella, archivo.Bytes, destino.Carpeta, nombre, new Escalado(progreso, comienzo, 1 - comienzo), ct);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // El temporal es de ESTE equipo, no del destino: si ya no se puede abrir, no es culpa de la memoria; hay que generar de nuevo.
            SoltarArchivo();
            var danado = new ResultadoDelGuardado(EstadoDelGuardado.ArchivoDanado, "El archivo preparado ya no está en este equipo.", "Vuelve a guardar el reporte: se genera de nuevo.",
                Detalle: MotivosDeEscritura.Detalle(ex), Tipo: destino.Tipo);
            AnotarFallo(danado, destino.Tipo);
            return danado;
        }
        finally
        {
            // La hoja (y con ella este flujo) se cerró mientras se escribía: nadie espera ya ese temporal. Si el borrado de Dispose() no alcanzó, se termina aquí.
            if (_dispuesto) archivo.Dispose();
        }

        // 3. Una escritura que falló: se avisa al nodo y el archivo bajado queda para otro destino.
        if (!escrito.Ok)
        {
            var fallo = escrito.Fallo ?? MotivosDeEscritura.De(MotivoDeEscritura.Otro);
            await AvisarFalloAsync(archivo.Id, destino.Tipo, fallo);
            if (fallo.Motivo == MotivoDeEscritura.Cancelado)
            {
                SoltarArchivo();
                return new ResultadoDelGuardado(EstadoDelGuardado.Cancelado, fallo.Mensaje, fallo.Accion, Fallo: fallo, Detalle: escrito.Detalle, Tipo: destino.Tipo);
            }
            var noSePudo = new ResultadoDelGuardado(EstadoDelGuardado.NoSePudoEscribir, fallo.Mensaje, fallo.Accion, Fallo: fallo, Detalle: escrito.Detalle, Tipo: destino.Tipo);
            AnotarFallo(noSePudo, destino.Tipo);
            return noSePudo;
        }

        // 4. Escrito y releído: ahora sí se registra ante el nodo, con la huella que se RELEYÓ.
        var ruta = escrito.RutaFinal!;
        var huella = escrito.Sha256!;
        SoltarArchivo();                                                  // ya está guardado: el temporal sobra
        return await ConfirmarAsync(archivo.Id, destino.Tipo, huella, ruta, escrito.Bytes);
    }

    /// <summary>Vuelve a avisar al nodo de un archivo que ya se escribió y se verificó (cuando la primera confirmación no llegó). Sin nada pendiente, no hace nada y lo dice.</summary>
    public async Task<ResultadoDelGuardado> ReintentarConfirmacionAsync()
    {
        if (_sinConfirmar is not { } p)
            return new ResultadoDelGuardado(EstadoDelGuardado.NoSePudoEscribir, "No hay nada pendiente de avisar al aula.", null);
        return await ConfirmarAsync(p.Id, p.Tipo, p.Huella, p.Ruta, p.Bytes);
    }

    private async Task<ResultadoDelGuardado> ConfirmarAsync(string id, TipoDeDestino tipo, string huella, string ruta, long bytes)
    {
        var respuesta = await _api.ConfirmarGuardadoAsync(_actor, id, tipo.Codigo(), huella);
        if (respuesta is not null)
        {
            _sinConfirmar = null;
            return new ResultadoDelGuardado(EstadoDelGuardado.Guardado, "Guardado.", null, ruta, bytes, Tipo: tipo);
        }
        var error = _api.UltimoError;
        // «Ya quedó entregada» no es un fallo: otra confirmación (un reintento que sí llegó) lo anotó antes.
        if (error?.Codigo == "exportacion_ya_confirmada")
        {
            _sinConfirmar = null;
            return new ResultadoDelGuardado(EstadoDelGuardado.Guardado, "Guardado.", null, ruta, bytes, Tipo: tipo);
        }
        _sinConfirmar = (id, tipo, huella, ruta, bytes);
        var causa = MensajesDeReportes.SinConexion(error) ? "No hubo conexión con el aula para anotarlo."
                  : error?.Codigo == "exportacion_caducada" ? "Pasó demasiado tiempo y el aula ya no lo puede anotar como entregado."
                  : "El aula no pudo anotarlo.";
        var accion = error?.Codigo == "exportacion_caducada" ? "El archivo está bien guardado. Si necesitas que quede registrado, guarda el reporte otra vez."
                   : "El archivo está bien guardado. Toca «Avisar al aula» cuando haya conexión.";
        if (error?.Codigo == "exportacion_caducada") _sinConfirmar = null;                       // un registro caducado no se puede reintentar
        return new ResultadoDelGuardado(EstadoDelGuardado.GuardadoSinConfirmar, causa, accion, ruta, bytes, ErrorDelNodo: error, Tipo: tipo);
    }

    private async Task AvisarFalloAsync(string id, TipoDeDestino tipo, FalloDeEscritura fallo)
    {
        try { await _api.ConfirmarFalloAsync(_actor, id, tipo.Codigo(), MotivosDeEscritura.Codigo(fallo.Motivo)); }
        catch (Exception) { /* avisar es de mejor esfuerzo: lo que se le dice a la persona no depende de ello */ }
    }

    private static ResultadoDelGuardado CanceladoAntesDeEscribir() =>
        new(EstadoDelGuardado.Cancelado, "Cancelaste el guardado.", "No se guardó nada. El reporte sigue en pantalla.");

    private static ResultadoDelGuardado DelNodo(ErrorAula? error, string? motivo)
    {
        if (MensajesDeReportes.SinConexion(error))
            return new ResultadoDelGuardado(EstadoDelGuardado.SinConexion, MensajesDeReportes.De(error), "Cuando el aula vuelva a estar conectada, toca Guardar otra vez.", ErrorDelNodo: error);
        if (error is { Estado: -1 })
            return new ResultadoDelGuardado(EstadoDelGuardado.ArchivoDanado, MensajesDeReportes.De(error), error.Sugerencia ?? "Vuelve a guardar el reporte: se genera de nuevo.", ErrorDelNodo: error);
        var mensaje = MensajesDeReportes.De(error, string.IsNullOrWhiteSpace(motivo) ? "El aula no autorizó guardar este reporte." : motivo);
        return new ResultadoDelGuardado(EstadoDelGuardado.NoAutorizado, mensaje, AccionDeNoAutorizado(error?.Codigo), ErrorDelNodo: error);
    }

    private static string? AccionDeNoAutorizado(string? codigo) => codigo switch
    {
        "destino_no_permitido" => "Elige una carpeta de este equipo o de la red.",
        "razon_requerida" => "Vuelve a elegir y escoge para qué vas a guardarlo.",
        "sin_permiso" or "fuera_de_alcance" => "Si lo necesitas, pídelo a la administración.",
        _ => "Vuelve a intentarlo.",
    };

    private bool HaVencido(ArchivoExportado archivo) => archivo.ExpiraEn > 0 && _ahoraMs() >= archivo.ExpiraEn - (long)Margen.TotalMilliseconds;

    private void SoltarArchivo()
    {
        _archivo?.Dispose();
        _archivo = null;
        _formatoDelArchivo = _razonDelArchivo = null;
    }

    /// <summary>Suelta el archivo temporal (si queda alguno): la hoja se cerró, o se salió de la pantalla.</summary>
    public void Dispose()
    {
        _dispuesto = true;
        SoltarArchivo();
    }

    /// <summary>Un tramo del avance total: lo que cuenta de 0 a 1 en una etapa se vuelve «de inicio a inicio + peso» del avance de toda la operación.</summary>
    private sealed class Escalado(IProgress<double>? destino, double inicio, double peso) : IProgress<double>
    {
        public void Report(double valor) => destino?.Report(Math.Clamp(inicio + (Math.Clamp(valor, 0, 1) * peso), 0, 1));
    }
}

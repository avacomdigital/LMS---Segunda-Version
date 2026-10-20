using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Ops.Reportes;

namespace Avacom.Lms.Ops.Licencia;

public enum PasoDeLiberacion
{
    /// <summary>Elegir dónde guardar el archivo de liberación: se elige ANTES de liberar, para no liberar sin poder guardar la prueba.</summary>
    ElegirDestino,
    /// <summary>La confirmación única: qué pasa y que se puede deshacer.</summary>
    Confirmando,
    Liberando,
    /// <summary>Liberado y con el <c>.avrel</c> guardado en el destino.</summary>
    Liberada,
    /// <summary>El nodo ya liberó el equipo pero el <c>.avrel</c> no se pudo escribir: se puede guardar en otro destino sin volver a liberar.</summary>
    LiberadaSinGuardar,
    /// <summary>El nodo no liberó (sin conexión, sin permiso, no hay licencia instalada).</summary>
    NoLiberada,
}

/// <summary>
/// «Liberar este equipo» (JRN-020) sin MAUI: se elige dónde guardar el archivo de liberación, se confirma UNA vez, el nodo libera y firma el <c>.avrel</c>, y se escribe con la escritura
/// segura. El nodo no puede volver a dar el mismo archivo (después de liberar ya no hay licencia instalada), así que si la escritura falla los bytes se conservan en memoria y se pueden
/// guardar en otro destino sin volver a llamar al nodo. Se deshace volviendo a activar el mismo <c>.avlic</c>.
/// </summary>
public sealed class FlujoDeLiberacion
{
    /// <summary>Lo mínimo libre que se pide al destino antes de liberar (un <c>.avrel</c> mide unos cientos de bytes).</summary>
    public const long EspacioMinimo = 64 * 1024;

    private readonly ILicenciaApi _api;
    private readonly string _actor;
    private readonly EscritorDeLicencias _escritor;
    private readonly IOperacionesDeArchivo _io;
    private LiberacionDeLicencia? _archivo;
    private int _ocupado;

    public FlujoDeLiberacion(ILicenciaApi api, string actor, EscritorDeLicencias escritor, IOperacionesDeArchivo? io = null)
    {
        _api = api ?? throw new ArgumentNullException(nameof(api));
        _actor = actor ?? string.Empty;
        _escritor = escritor ?? throw new ArgumentNullException(nameof(escritor));
        _io = io ?? new OperacionesDeArchivoDelSistema();
    }

    public PasoDeLiberacion Paso { get; private set; } = PasoDeLiberacion.ElegirDestino;
    public DestinoElegido? Destino { get; private set; }
    public MensajeDeLicencia? Aviso { get; private set; }
    public string? RutaDelArchivo { get; private set; }
    public EstadoLicencia? EstadoNuevo { get; private set; }
    /// <summary>Cuántas veces se pidió liberar al nodo (las pruebas comprueban que la confirmación es única).</summary>
    public int Envios { get; private set; }

    /// <summary>El destino del <c>.avrel</c> (antes de liberar) → la confirmación.</summary>
    public bool ElegirDestino(DestinoElegido destino)
    {
        ArgumentNullException.ThrowIfNull(destino);
        if (Paso is not (PasoDeLiberacion.ElegirDestino or PasoDeLiberacion.Confirmando or PasoDeLiberacion.NoLiberada)) return false;
        Destino = destino;
        Paso = PasoDeLiberacion.Confirmando;
        Aviso = null;
        return true;
    }

    /// <summary>«Cambiar»: de la confirmación, de vuelta a elegir el destino.</summary>
    public void CambiarDestino()
    {
        if (Paso is not (PasoDeLiberacion.Confirmando or PasoDeLiberacion.NoLiberada)) return;
        Paso = PasoDeLiberacion.ElegirDestino;
        Aviso = null;
    }

    /// <summary>La confirmación única: libera y guarda el archivo. Sólo desde la confirmación y una sola vez. Verdadero si el equipo quedó liberado (con o sin el archivo guardado).</summary>
    public async Task<bool> LiberarAsync(CancellationToken ct = default)
    {
        if (Paso != PasoDeLiberacion.Confirmando || Destino is not { } destino) return false;
        if (Interlocked.Exchange(ref _ocupado, 1) == 1) return false;
        try
        {
            Paso = PasoDeLiberacion.Liberando;
            Aviso = null;
            // Antes de liberar: el destino tiene que estar y tener sitio. Si no, no se toca el nodo.
            bool existe;
            long? libre;
            try { existe = _io.ExisteCarpeta(destino.Carpeta); libre = existe ? _io.EspacioLibre(destino.Carpeta) : null; }
            catch { existe = false; libre = null; }
            if (!existe || libre is < EspacioMinimo)
            {
                Paso = PasoDeLiberacion.ElegirDestino;
                Aviso = !existe
                    ? new MensajeDeLicencia("Ese lugar ya no está", "La memoria o la carpeta elegida ya no está conectada. No se liberó nada.", "Elige otro destino.")
                    : new MensajeDeLicencia("No hay espacio", "Ese lugar no tiene espacio libre para el archivo de liberación. No se liberó nada.", "Elige otro destino.");
                return false;
            }

            Envios++;
            var r = await _api.LiberarAsync(_actor, ct);
            if (r is null)
            {
                Paso = PasoDeLiberacion.NoLiberada;
                Aviso = LicenciaTexto.DeError(_api.UltimoError) with { Titulo = "El equipo no se liberó" };
                return false;
            }
            _archivo = r.Archivo;
            EstadoNuevo = r.Estado;
            return await EscribirAsync(destino, ct);
        }
        finally { Interlocked.Exchange(ref _ocupado, 0); }
    }

    /// <summary>Ya liberado pero sin el archivo guardado: lo escribe en otro destino SIN volver a liberar.</summary>
    public async Task<bool> GuardarEnOtroDestinoAsync(DestinoElegido destino, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(destino);
        if (Paso != PasoDeLiberacion.LiberadaSinGuardar || _archivo is null) return false;
        if (Interlocked.Exchange(ref _ocupado, 1) == 1) return false;
        try
        {
            Destino = destino;
            Paso = PasoDeLiberacion.Liberando;
            return await EscribirAsync(destino, ct);
        }
        finally { Interlocked.Exchange(ref _ocupado, 0); }
    }

    private async Task<bool> EscribirAsync(DestinoElegido destino, CancellationToken ct)
    {
        var escrito = await _escritor.GuardarAsync([ArchivoParaGuardar.DelNodo(_archivo!, ".avrel")], destino.Carpeta, null, ct);
        if (escrito.Ok)
        {
            RutaDelArchivo = escrito.Rutas[0];
            Paso = PasoDeLiberacion.Liberada;
            Aviso = new MensajeDeLicencia("Equipo liberado", LicenciaTexto.LiberadaGuardada(RutaDelArchivo), LicenciaTexto.LiberarDeshacer);
            return true;
        }
        Paso = PasoDeLiberacion.LiberadaSinGuardar;
        var fallo = escrito.Fallo!;
        Aviso = new MensajeDeLicencia(LicenciaTexto.LiberarSinGuardar, $"{fallo.Mensaje} {fallo.Accion}", LicenciaTexto.LiberarSinGuardarAccion);
        return true;                                                                                 // el equipo SÍ quedó liberado
    }
}

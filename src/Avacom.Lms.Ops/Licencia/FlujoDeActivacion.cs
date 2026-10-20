using System.Security.Cryptography;
using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Ops.Reportes;

namespace Avacom.Lms.Ops.Licencia;

/// <summary>Dónde está el flujo de activación. Los pasos 1 a 3 de P-18; la pantalla pinta lo que corresponde a cada uno.</summary>
public enum PasoDeActivacion
{
    /// <summary>Paso 1: elegir dónde guardar la solicitud (o «Ya tengo el archivo de licencia»).</summary>
    Solicitud,
    GuardandoSolicitud,
    /// <summary>Paso 1 hecho: la solicitud quedó en la memoria.</summary>
    SolicitudGuardada,
    /// <summary>Paso 2: AVACOM firma la licencia (fuera del programa). Sólo se explica.</summary>
    EsperandoLicencia,
    /// <summary>Paso 3: se buscan los <c>.avlic</c> en las memorias y carpetas.</summary>
    Buscando,
    /// <summary>Paso 3: las tarjetas (o el aviso de que no hay ninguna).</summary>
    Eligiendo,
    /// <summary>Paso 3: la confirmación ÚNICA con el resumen de lo que se va a instalar.</summary>
    Confirmando,
    Instalando,
    /// <summary>El nodo instaló la licencia: <see cref="FlujoDeActivacion.EstadoNuevo"/> trae el estado nuevo.</summary>
    Instalada,
    /// <summary>No se instaló: <see cref="FlujoDeActivacion.Aviso"/> dice por qué y qué hacer.</summary>
    NoInstalada,
}

/// <summary>
/// El flujo de activar o renovar la licencia SIN internet en tres pasos táctiles (P-18), como máquina de estados sin MAUI. La pantalla llama a sus métodos y pinta <see cref="Paso"/> y
/// <see cref="Aviso"/>. Reglas que se prueban:
/// <list type="bullet">
/// <item>Paso 1: el nodo firma la solicitud y se escribe con la escritura segura; si la escritura falla, la MISMA solicitud se guarda en otro destino sin pedir otra.</item>
/// <item>Paso 3: sólo se puede elegir un candidato de la búsqueda vigente; elegirlo lleva a UNA confirmación; sólo desde ella se instala, una sola vez aunque se toque dos veces.</item>
/// <item>Al instalar se vuelve a leer el archivo: si ya no está o cambió desde que se listó, no se envía nada y se pide buscar de nuevo.</item>
/// <item>Sin conexión o con un fallo del aula se puede reintentar el MISMO archivo; con un archivo rechazado, se elige otro.</item>
/// </list>
/// Quien decide si el archivo vale es el nodo (SEC-001): aquí sólo se reconoce la marca para no listar basura.
/// </summary>
public sealed class FlujoDeActivacion
{
    private readonly ILicenciaApi _api;
    private readonly string _actor;
    private readonly Func<CancellationToken, Task<BusquedaDeLicencias>> _buscar;
    private readonly ILectorDeArchivos _lector;
    private readonly EscritorDeLicencias _escritor;
    private readonly Action<string>? _recordarCarpeta;
    private SolicitudDeLicencia? _solicitud;
    private int _ocupado;

    public FlujoDeActivacion(ILicenciaApi api, string actor, string via, Func<CancellationToken, Task<BusquedaDeLicencias>> buscar, ILectorDeArchivos lector, EscritorDeLicencias escritor,
                             Action<string>? recordarCarpeta = null)
    {
        _api = api ?? throw new ArgumentNullException(nameof(api));
        _actor = actor ?? string.Empty;
        Via = via == ViasDeInstalacion.Renovar ? ViasDeInstalacion.Renovar : ViasDeInstalacion.Activar;
        _buscar = buscar ?? throw new ArgumentNullException(nameof(buscar));
        _lector = lector ?? throw new ArgumentNullException(nameof(lector));
        _escritor = escritor ?? throw new ArgumentNullException(nameof(escritor));
        _recordarCarpeta = recordarCarpeta;
    }

    public PasoDeActivacion Paso { get; private set; } = PasoDeActivacion.Solicitud;
    /// <summary><c>activar</c> o <c>renovar</c> (<see cref="ReglasDeLicencia.Via"/>).</summary>
    public string Via { get; }
    /// <summary>El último problema o resultado, para pintarlo. Se limpia al avanzar.</summary>
    public MensajeDeLicencia? Aviso { get; private set; }
    public string? RutaDeLaSolicitud { get; private set; }
    /// <summary>El nivel de huella con que salió la solicitud (<c>hardware</c> o <c>instalacion</c>).</summary>
    public string? NivelDeLaSolicitud => _solicitud?.Nivel;
    public BusquedaDeLicencias? Busqueda { get; private set; }
    public CandidatoDeLicencia? Elegido { get; private set; }
    public EstadoLicencia? EstadoNuevo { get; private set; }
    /// <summary>Tras un fallo de red o del aula, se puede volver a enviar el mismo archivo.</summary>
    public bool PuedeReintentar { get; private set; }
    /// <summary>Cuántas veces se envió un archivo al nodo (las pruebas comprueban que la confirmación es única).</summary>
    public int Envios { get; private set; }

    /// <summary>1, 2 o 3: el paso que se ve.</summary>
    public int NumeroDePaso => Paso switch
    {
        PasoDeActivacion.Solicitud or PasoDeActivacion.GuardandoSolicitud or PasoDeActivacion.SolicitudGuardada => 1,
        PasoDeActivacion.EsperandoLicencia => 2,
        _ => 3,
    };

    // ---------------------------------------------------------------------------------------------------- paso 1 · la solicitud

    /// <summary>Pide al nodo la solicitud (una vez por flujo) y la guarda en <paramref name="destino"/>. Verdadero si quedó guardada.</summary>
    public async Task<bool> GuardarSolicitudAsync(DestinoElegido destino, IProgress<double>? progreso = null, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(destino);
        if (Paso is not (PasoDeActivacion.Solicitud or PasoDeActivacion.SolicitudGuardada)) return false;
        if (Interlocked.Exchange(ref _ocupado, 1) == 1) return false;
        try
        {
            Paso = PasoDeActivacion.GuardandoSolicitud;
            Aviso = null;
            if (_solicitud is null)
            {
                var solicitud = await _api.SolicitudAsync(_actor, ct);
                if (solicitud is null)
                {
                    Paso = PasoDeActivacion.Solicitud;
                    var e = LicenciaTexto.DeError(_api.UltimoError);
                    Aviso = e with { Titulo = "No se pudo preparar la solicitud" };
                    return false;
                }
                _solicitud = solicitud;
            }
            var r = await _escritor.GuardarAsync([ArchivoParaGuardar.DelNodo(_solicitud, ".avreq")], destino.Carpeta, progreso, ct);
            if (!r.Ok)
            {
                Paso = PasoDeActivacion.Solicitud;
                var fallo = r.Fallo!;
                Aviso = new MensajeDeLicencia("No se pudo guardar la solicitud", fallo.Mensaje, fallo.Accion);
                return false;
            }
            RutaDeLaSolicitud = r.Rutas[0];
            Paso = PasoDeActivacion.SolicitudGuardada;
            var texto = LicenciaTexto.SolicitudGuardada(RutaDeLaSolicitud);
            Aviso = new MensajeDeLicencia("Solicitud guardada", texto, _solicitud.Nivel == NivelesDeHuella.Instalacion ? LicenciaTexto.SolicitudConHuellaDeInstalacion : null);
            Recordar(destino.Carpeta);
            return true;
        }
        finally { Interlocked.Exchange(ref _ocupado, 0); }
    }

    /// <summary>Paso 1 hecho → paso 2.</summary>
    public void Continuar()
    {
        if (Paso != PasoDeActivacion.SolicitudGuardada) return;
        Paso = PasoDeActivacion.EsperandoLicencia;
        Aviso = null;
    }

    /// <summary>Vuelve al paso 1 (por ejemplo, para guardar otra vez la solicitud).</summary>
    public void VolverAlPaso1()
    {
        if (Paso is PasoDeActivacion.GuardandoSolicitud or PasoDeActivacion.Buscando or PasoDeActivacion.Instalando or PasoDeActivacion.Instalada) return;
        Paso = RutaDeLaSolicitud is null ? PasoDeActivacion.Solicitud : PasoDeActivacion.SolicitudGuardada;
        Aviso = null;
    }

    // ---------------------------------------------------------------------------------------------------- paso 3 · elegir el archivo

    /// <summary>«Ya tengo el archivo de licencia» (desde el paso 1 o el 2) o «Buscar de nuevo»: busca los <c>.avlic</c> y deja la lista.</summary>
    public async Task BuscarAsync(CancellationToken ct = default)
    {
        if (Paso is PasoDeActivacion.GuardandoSolicitud or PasoDeActivacion.Instalando or PasoDeActivacion.Instalada) return;
        if (Interlocked.Exchange(ref _ocupado, 1) == 1) return;
        try
        {
            Paso = PasoDeActivacion.Buscando;
            Aviso = null;
            Elegido = null;
            BusquedaDeLicencias busqueda;
            try { busqueda = await _buscar(ct); }
            catch (OperationCanceledException) { busqueda = new BusquedaDeLicencias([], 0, 0, 0, false); }
            catch { busqueda = new BusquedaDeLicencias([], 0, 0, 0, false); }
            Busqueda = busqueda;
            Paso = PasoDeActivacion.Eligiendo;
            if (busqueda.Vacia) Aviso = new MensajeDeLicencia("No hay archivos de licencia", LicenciaTexto.SinArchivos, LicenciaTexto.SinArchivosAccion);
        }
        finally { Interlocked.Exchange(ref _ocupado, 0); }
    }

    /// <summary>Tocar una tarjeta: lleva a la confirmación. Sólo vale un candidato de la búsqueda vigente.</summary>
    public bool Elegir(CandidatoDeLicencia candidato)
    {
        if (Paso is not (PasoDeActivacion.Eligiendo or PasoDeActivacion.Confirmando) || Busqueda is null || !Busqueda.Candidatos.Contains(candidato)) return false;
        Elegido = candidato;
        Paso = PasoDeActivacion.Confirmando;
        Aviso = null;
        return true;
    }

    /// <summary>Desde la confirmación o desde un rechazo, de vuelta a las tarjetas.</summary>
    public void VolverALaLista()
    {
        if (Paso is not (PasoDeActivacion.Confirmando or PasoDeActivacion.NoInstalada)) return;
        Paso = PasoDeActivacion.Eligiendo;
        Elegido = null;
        Aviso = Busqueda is { Vacia: true } ? new MensajeDeLicencia("No hay archivos de licencia", LicenciaTexto.SinArchivos, LicenciaTexto.SinArchivosAccion) : null;
        PuedeReintentar = false;
    }

    /// <summary>La frase de la confirmación única.</summary>
    public string? Confirmacion(TimeZoneInfo? zona = null) =>
        Elegido is { } c ? LicenciaTexto.Confirmacion(c.Nombre, c.Lugar, c.ModificadoMs, Via, zona) : null;

    /// <summary>Instala el archivo confirmado. Sólo desde la confirmación, y una sola vez aunque se toque dos veces. Verdadero si el nodo lo instaló.</summary>
    public Task<bool> InstalarAsync(CancellationToken ct = default) => Paso == PasoDeActivacion.Confirmando ? EnviarAsync(ct) : Task.FromResult(false);

    /// <summary>Vuelve a enviar el MISMO archivo tras un fallo de red o del aula (no tras un rechazo del archivo).</summary>
    public Task<bool> ReintentarAsync(CancellationToken ct = default) => Paso == PasoDeActivacion.NoInstalada && PuedeReintentar && Elegido is not null ? EnviarAsync(ct) : Task.FromResult(false);

    private async Task<bool> EnviarAsync(CancellationToken ct)
    {
        if (Elegido is not { } candidato) return false;
        if (Interlocked.Exchange(ref _ocupado, 1) == 1) return false;
        try
        {
            Paso = PasoDeActivacion.Instalando;
            Aviso = null;
            PuedeReintentar = false;

            // Lo que se instala es lo que se confirmó: el archivo se vuelve a leer y tiene que ser el mismo.
            byte[]? datos;
            try { datos = _lector.LeerCompleto(candidato.Ruta, MarcaDeLicencia.TamanoMaximo); }
            catch { datos = null; }
            if (datos is null || datos.Length == 0)
            {
                Paso = PasoDeActivacion.NoInstalada;
                Aviso = new MensajeDeLicencia("No se pudo leer el archivo", LicenciaTexto.ArchivoYaNoEsta, LicenciaTexto.ArchivoYaNoEstaAccion);
                return false;
            }
            if (!string.Equals(Convert.ToHexStringLower(SHA256.HashData(datos)), candidato.Sha256, StringComparison.OrdinalIgnoreCase))
            {
                Paso = PasoDeActivacion.NoInstalada;
                Aviso = new MensajeDeLicencia("El archivo cambió", "El archivo cambió desde que se listó, así que no se instaló.", "Toca «Buscar de nuevo» y vuelve a elegirlo.");
                return false;
            }

            Envios++;
            var nuevo = Via == ViasDeInstalacion.Renovar ? await _api.RenovarAsync(_actor, datos, ct) : await _api.ActivarAsync(_actor, datos, ct);
            if (nuevo is null)
            {
                var error = _api.UltimoError;
                Paso = PasoDeActivacion.NoInstalada;
                Aviso = LicenciaTexto.DeError(error);
                PuedeReintentar = error is null || error.Estado == 0 || error.Estado >= 500;
                return false;
            }
            EstadoNuevo = nuevo;
            Paso = PasoDeActivacion.Instalada;
            Aviso = LicenciaTexto.ResultadoDeInstalacion(nuevo);
            Recordar(candidato.Carpeta);
            return true;
        }
        finally { Interlocked.Exchange(ref _ocupado, 0); }
    }

    private void Recordar(string carpeta)
    {
        try { _recordarCarpeta?.Invoke(carpeta); }
        catch { /* recordar la carpeta es una comodidad: no puede hacer fallar el paso */ }
    }
}

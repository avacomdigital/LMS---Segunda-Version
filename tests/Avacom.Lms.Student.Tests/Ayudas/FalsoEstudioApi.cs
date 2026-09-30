using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Student.Tests;

/// <summary>
/// El aula de mentira: cada llamada que la tableta hace queda anotada (con la persona que la hizo) y contesta lo que la prueba le haya dicho.
/// Sin nada dicho, el aula «no contesta» (devuelve null, como el cliente real sin red). Lo que las pruebas no usan lanza.
/// </summary>
internal sealed class FalsoEstudioApi : IEstudioApi
{
    private static readonly JsonSerializerOptions Web = new(JsonSerializerDefaults.Web);

    public static T Json<T>(string json) => JsonSerializer.Deserialize<T>(json, Web)!;

    /// <summary>Lo que la tableta pidió, en orden: «Método(dispositivo, alumno, …)».</summary>
    public List<string> Llamadas { get; } = [];

    public Uri BaseUri { get; } = new("http://aula.test:8000/");
    public string? UltimoMotivo { get; set; }
    public ErrorAula? UltimoError { get; set; }
    public Uri Absoluta(string rutaRelativa) => new(BaseUri, rutaRelativa.TrimStart('/'));

    /// <summary>Si es falso, el aula no contesta a nada (sin Wi-Fi o nodo apagado).</summary>
    public bool EnLinea { get; set; } = true;

    // ----------------------------------------------------------------------------- lo que el aula contesta
    public Func<string?, EstadoEstudio?> Estado { get; set; } = _ => null;
    public Func<EstudiantesEstudio?> Estudiantes { get; set; } = () => null;
    public Func<string?, SesionEstudio?> Sesion { get; set; } = _ => null;
    public Func<string?, AsignacionesEstudio?> Asignaciones { get; set; } = _ => null;
    public Func<string, string?, LeccionEstudio?> Leccion { get; set; } = (_, _) => null;
    public Func<string, bool, string?, PracticaAbierta?> Practica { get; set; } = (_, _, _) => null;
    public Func<string, IReadOnlyList<RespuestaPractica>, bool, AcusePractica?> Responder { get; set; } = (_, _, _) => null;
    public Func<string, AcusePractica?> Terminar { get; set; } = _ => null;
    public Func<string, IReadOnlyList<EventoEstudio>, string?, AcuseSync?> Sincronizar { get; set; } = (_, _, _) => null;
    public int Registros { get; private set; }

    /// <summary>Una respuesta 404 del nodo (o el error que se indique) para lo que la prueba no preparó.</summary>
    private T? Contestar<T>(string llamada, Func<T?> respuesta) where T : class
    {
        Llamadas.Add(llamada);
        if (!EnLinea)
        {
            UltimoError = new ErrorAula(0, "sin_conexion", "No hay conexión con el aula.", null, null);
            return null;
        }
        var r = respuesta();
        if (r is null) UltimoError = new ErrorAula(404, "no_encontrado", "No existe.", null, null);
        else UltimoError = null;
        return r;
    }

    public Task<EstadoEstudio?> EstadoAsync(string dispositivo, string? alumnoId = null, CancellationToken ct = default) =>
        Task.FromResult(Contestar($"Estado({dispositivo},{alumnoId})", () => Estado(alumnoId)));

    public Task<EstudiantesEstudio?> EstudiantesAsync(string dispositivo, CancellationToken ct = default) =>
        Task.FromResult(Contestar($"Estudiantes({dispositivo})", () => Estudiantes()));

    public Task<SesionEstudio?> AbrirSesionAsync(string dispositivo, string? nombre, string? plataforma, string? versionApp, string? alumnoId = null, CancellationToken ct = default) =>
        Task.FromResult(Contestar($"AbrirSesion({dispositivo},{alumnoId})", () => Sesion(alumnoId)));

    public Task<bool> CerrarSesionAsync(string dispositivo, int colaPendiente, bool limpiezaCompleta, string? alumnoId = null, CancellationToken ct = default)
    {
        Llamadas.Add($"CerrarSesion({dispositivo},{alumnoId},cola={colaPendiente},completa={limpiezaCompleta})");
        return Task.FromResult(EnLinea);
    }

    public Task<bool> LimpiezaReintentadaAsync(string dispositivo, string resultado, CancellationToken ct = default)
    {
        Llamadas.Add($"LimpiezaReintentada({dispositivo},{resultado})");
        return Task.FromResult(EnLinea);
    }

    public Task<AsignacionesEstudio?> AsignacionesAsync(string dispositivo, string? alumnoId = null, CancellationToken ct = default) =>
        Task.FromResult(Contestar($"Asignaciones({dispositivo},{alumnoId})", () => Asignaciones(alumnoId)));

    public Task<AsignacionAlumno?> AsignacionAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();

    public Task<LeccionEstudio?> LeccionAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default) =>
        Task.FromResult(Contestar($"Leccion({dispositivo},{alumnoId},{asignacionId})", () => Leccion(asignacionId, alumnoId)));

    public Task<ProgresoEstudio?> ProgresoAsync(string dispositivo, string asignacionId, IReadOnlyList<string> bloquesVistos, string? bloqueActual,
                                                int? posicionSeg, long? capturadoEn = null, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();

    public Task<CompletadaEstudio?> CompletarAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();

    public Task<PracticaAbierta?> PracticaAsync(string dispositivo, string asignacionId, string? objetoRef = null, bool nueva = false, string? alumnoId = null, CancellationToken ct = default) =>
        Task.FromResult(Contestar($"Practica({dispositivo},{alumnoId},{asignacionId},nueva={nueva})", () => Practica(asignacionId, nueva, objetoRef)));

    public Task<AcusePractica?> ResponderAsync(string dispositivo, string practicaId, IReadOnlyList<RespuestaPractica> respuestas, bool terminar = false,
                                               string? alumnoId = null, CancellationToken ct = default) =>
        Task.FromResult(Contestar($"Responder({dispositivo},{alumnoId},{practicaId},{string.Join('+', respuestas.Select(r => r.PreguntaRef))})", () => Responder(practicaId, respuestas, terminar)));

    public Task<AcusePractica?> TerminarPracticaAsync(string dispositivo, string practicaId, string? alumnoId = null, CancellationToken ct = default) =>
        Task.FromResult(Contestar($"TerminarPractica({dispositivo},{alumnoId},{practicaId})", () => Terminar(practicaId)));

    public Task<PaqueteEstudio?> SolicitarPaqueteAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default) =>
        Task.FromResult(Contestar($"SolicitarPaquete({dispositivo},{alumnoId},{asignacionId})", () => (PaqueteEstudio?)null));
    public Task<ListaPaquetes?> PaquetesAsync(string dispositivo, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<PaqueteEstudio?> PaqueteAsync(string dispositivo, string paqueteId, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<ManifiestoPaquete?> ManifiestoAsync(string dispositivo, string paqueteId, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<string?> ManifiestoCrudoAsync(string dispositivo, string paqueteId, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<HttpResponseMessage?> ArchivoAsync(string dispositivo, string paqueteId, string mediaRef, long? desdeByte = null, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<PaqueteEstudio?> ConfirmarPaqueteAsync(string dispositivo, string paqueteId, string huella, long bytes, string? alumnoId = null, CancellationToken ct = default) => throw new NotSupportedException();

    public Task<bool> RetirarPaqueteAsync(string dispositivo, string paqueteId, string? alumnoId = null, CancellationToken ct = default)
    {
        Llamadas.Add($"RetirarPaquete({dispositivo},{alumnoId},{paqueteId})");
        return Task.FromResult(EnLinea);
    }

    public Task<AcuseSync?> SincronizarAsync(string dispositivo, string emisorId, IReadOnlyList<EventoEstudio> eventos, string? alumnoId = null, CancellationToken ct = default)
    {
        Llamadas.Add($"Sincronizar({dispositivo},{alumnoId},{string.Join('+', eventos.Select(e => $"{e.Secuencia}:{e.Tipo}"))})");
        if (!EnLinea)
        {
            UltimoError = new ErrorAula(0, "sin_conexion", "No hay conexión con el aula.", null, null);
            return Task.FromResult<AcuseSync?>(null);
        }
        UltimoError = null;
        return Task.FromResult(Sincronizar(emisorId, eventos, alumnoId));
    }

    public Task<EstadoSync?> EstadoSyncAsync(string dispositivo, string emisorId, CancellationToken ct = default) => throw new NotSupportedException();

    public Task<GruposDocente?> GruposAsync(string actor, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<ListaAsignacionesDocente?> AsignacionesDocenteAsync(string actor, string? grupoId = null, string? estado = null, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<AsignacionDocente?> CrearAsignacionAsync(string actor, string? actorRotulo, NuevaAsignacion nueva, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<AsignacionDocente?> AsignacionDocenteAsync(string actor, string asignacionId, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<AsignacionDocente?> CambiarAsignacionAsync(string actor, string asignacionId, CambiosAsignacion cambios, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<AsignacionDocente?> CerrarAsignacionAsync(string actor, string asignacionId, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<bool> DecidirAsync(string actor, string asignacionId, string alumnoId, long secuencia, string? emisorId, string decision, CancellationToken ct = default) => throw new NotSupportedException();

    /// <summary>La tableta se dio de alta (la prueba se lo pasa al servicio como su «registrar aparato»).</summary>
    public Task RegistrarAparato(CancellationToken ct)
    {
        Registros++;
        Llamadas.Add("RegistrarAparato");
        return Task.CompletedTask;
    }
}

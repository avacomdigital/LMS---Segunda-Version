using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Estudio;

/// <summary>
/// Vacía la cola local hacia el nodo (<c>POST /sync/</c>, CAP-048, BR-137): toma hasta 200 eventos EN ORDEN de secuencia por envío, y cuando el
/// nodo acusa recibo borra de la cola TODAS las secuencias que respondió —integradas, duplicadas, rechazadas y también las que quedaron
/// pendientes de decisión del profesor: ésas ya las guardó el nodo—. No exige sesión abierta: el nodo autoriza por el aparato asignado al alumno.
///
/// Sin conexión (no hay respuesta, 5xx, o la sesión de usuario caducó) no pierde nada: la cola queda como estaba y el resultado dice
/// <c>SinConexion</c> (no hay un nodo que reciba ahora; se reintenta en la próxima pasada). Un 4xx sobre el envío completo (<c>datos_invalidos</c>,
/// aparato ajeno…) tampoco descarta nada en silencio: la cola se conserva, el motivo queda en <see cref="UltimoError"/> y se sigue con los demás
/// alumnos. Si la cola mezcla alumnos hace un envío por alumno, porque el nodo autoriza por alumno. No es reentrante: una segunda llamada
/// mientras hay una en curso no hace nada.
///
/// En <see cref="ResultadoSincronizacionEstudio"/>: <c>Enviados</c> son los eventos que el nodo <i>integró</i> en esta pasada; <c>Duplicados</c>,
/// <c>Rechazados</c> y <c>PendientesDeDecision</c>, los que respondió con esos estados (todo lo que salió de la cola es la suma de los cuatro);
/// <c>Pendientes</c>, lo que sigue esperando.
/// </summary>
public sealed class SincronizadorEstudio(IEstudioApi api, IColaEstudio cola) : ISincronizadorEstudio
{
    /// <summary>El máximo de eventos por envío que acepta el contrato (§4.5).</summary>
    public const int EventosPorEnvio = 200;

    private readonly SemaphoreSlim ocupado = new(1, 1);

    /// <summary>
    /// El nodo acusó un envío. El primer argumento es el ALUMNO de los eventos (el almacén local es por alumno): quien escucha actualiza el
    /// avance de las tareas y las prácticas de ese alumno con lo que el nodo respondió (tareas, veredictos). Se dispara en el hilo de la pasada.
    /// </summary>
    public event Action<string, AcuseSync>? Integrado;

    /// <summary>El error del nodo que detuvo la última pasada (para saber por qué la cola no se vació); nulo si no hubo.</summary>
    public ErrorAula? UltimoError { get; private set; }

    public async Task<ResultadoSincronizacionEstudio> VaciarAsync(string dispositivo, CancellationToken ct = default)
    {
        if (!await ocupado.WaitAsync(0, ct)) return ResultadoSincronizacionEstudio.Nada;
        int integrados = 0, duplicados = 0, rechazados = 0, pendientesDeDecision = 0;
        var sinConexion = false;
        AcuseSync? ultimo = null;
        UltimoError = null;
        try
        {
            // Un envío por alumno (el nodo autoriza por alumno); primero el que tiene el evento más antiguo.
            var alumnos = cola.Pendientes(null, int.MaxValue).Select(e => e.AlumnoId).Distinct().ToList();
            var detener = false;
            foreach (var alumno in alumnos)
            {
                if (detener) break;
                while (true)
                {
                    ct.ThrowIfCancellationRequested();
                    var lote = cola.Pendientes(alumno, EventosPorEnvio);
                    if (lote.Count == 0) break;
                    var enviadas = lote.Select(e => e.Evento.Secuencia).ToHashSet();
                    AcuseSync? acuse;
                    try { acuse = await api.SincronizarAsync(dispositivo, cola.EmisorId, lote.Select(e => e.Evento).ToList(), alumno, ct); }
                    catch (Exception ex) when (ex is not OperationCanceledException)
                    {
                        // El cliente ya convierte los fallos de red en un resultado nulo; esto es lo que no previó (un cuerpo que no es JSON…). Para la cola
                        // da igual: no hubo acuse, nada se toca y se reintentará.
                        UltimoError = null;
                        sinConexion = ex is HttpRequestException or IOException;
                        detener = true;
                        break;
                    }
                    if (acuse is null || !acuse.Acuse)
                    {
                        var error = acuse is null ? api.UltimoError : null;
                        UltimoError = error;
                        // Sin respuesta, un fallo del nodo (5xx) o una sesión caducada: no hay un nodo que reciba ahora. Nada se toca, el resultado dice
                        // «sin conexión» —la pantalla sigue diciendo «guardado en tu tableta»— y se reintentará en la próxima pasada.
                        if (acuse is null && (error is null || error.Estado == 0 || error.Estado >= 500 || error.SesionPerdida))
                        {
                            sinConexion = true;
                            detener = true;
                        }
                        else if (acuse is not null) detener = true;   // un 200 que no acusa recibo: algo anda mal en el nodo; se conserva todo y se para
                        break;   // un 4xx sobre este envío: se conserva y se sigue con el siguiente alumno
                    }

                    RelojNodo.Aprender(acuse.ServidorEn);
                    ultimo = acuse;
                    var acusadas = new List<long>();
                    foreach (var resultado in acuse.Resultados ?? [])
                    {
                        if (!enviadas.Contains(resultado.Secuencia)) continue;
                        switch (resultado.Estado)
                        {
                            case "integrado": integrados++; break;
                            case "duplicado": duplicados++; break;
                            case "rechazado": rechazados++; break;
                            case "pendiente_decision": pendientesDeDecision++; break;
                            default: continue;   // un estado que no se conoce: no se da por recibido
                        }
                        acusadas.Add(resultado.Secuencia);
                    }
                    cola.Reconocer(acusadas);
                    try { Integrado?.Invoke(alumno, acuse); }
                    catch (Exception) { /* una pantalla que falla no debe detener el vaciado: lo enviado ya se reconoció */ }
                    if (acusadas.Count == 0) break;   // el nodo no reconoció nada de lo enviado: no se insiste en la misma pasada
                }
            }
        }
        finally
        {
            ocupado.Release();
        }
        return new ResultadoSincronizacionEstudio(integrados, duplicados, rechazados, pendientesDeDecision, cola.CantidadPendiente(), sinConexion, ultimo);
    }
}

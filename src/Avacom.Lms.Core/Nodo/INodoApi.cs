using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Nodo;

/// <summary>
/// Cliente de <c>/api/nodo/</c> (MOD-015 · Node Platform y Cola de Salida) para OPS: el estado del nodo (PAN-242), la cola por consumidor y los eventos apartados (CAP-097, nunca su
/// carga), el reproceso de un evento apartado y la reproducción de un consumidor (FUN-164, <c>node.queue.replay</c>). Quien decide es el nodo: este cliente sólo pide y entrega lo que el
/// nodo responde. Student no lo usa (sólo lee el campo <c>nodo</c> de <c>/health/</c>, público).
///
/// Mismas reglas de degradación que el resto de clientes del LMS: un error HTTP o de red NO es una excepción; devuelve <c>null</c> y deja el motivo en <see cref="UltimoMotivo"/> y el
/// <c>codigo</c> del backend en <see cref="UltimoError"/> (<c>sin_permiso</c> con su <c>permiso</c>, <c>no_encontrado</c>, <c>consumidor_desconocido</c>,
/// <c>consumidor_sin_aplicador</c>, <c>problema_ya_resuelto</c>, <c>reproceso_fallido</c>, <c>datos_invalidos</c>). Con <see cref="UltimoError"/>.Estado == 0 no hay conexión.
///
/// Quien actúa se identifica con <c>actor</c> mientras el nodo no exija sesión (Q-34); con sesión manda el JWT y el nodo ignora <c>actor</c>.
/// </summary>
public interface INodoApi
{
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }

    /// <summary><c>GET estado/</c> (<c>node.health.read</c>): estado, motivos, base, disco, reloj y la cola en cifras.</summary>
    Task<EstadoDelNodo?> EstadoAsync(string actor, CancellationToken ct = default);

    /// <summary><c>GET cola/</c> (<c>node.queue.read</c>): cada consumidor con sus fuentes, marcas, pendientes y estado. Sin carga útil.</summary>
    Task<ColaDelNodo?> ColaAsync(string actor, CancellationToken ct = default);

    /// <summary><c>GET problemas/</c> (<c>node.queue.read</c>): los eventos apartados (por defecto los que siguen apartados), de un consumidor o de todos.</summary>
    Task<ProblemasDeCola?> ProblemasAsync(string actor, string? consumidor = null, string? estado = null, int limite = 100, CancellationToken ct = default);

    /// <summary><c>POST problemas/{id}/reprocesar/</c> (<c>node.queue.replay</c>): vuelve a aplicar UN evento apartado; deja asiento. 409 <c>reproceso_fallido</c> si vuelve a fallar.</summary>
    Task<ProblemaDeCola?> ReprocesarAsync(string actor, long problemaId, CancellationToken ct = default);

    /// <summary><c>POST consumidores/{nombre}/reproducir/</c> (<c>node.queue.replay</c>): la marca vuelve a cero (de una fuente o de todas) y el consumidor se reconstruye.</summary>
    Task<ReproduccionDeConsumidor?> ReproducirAsync(string actor, string consumidor, string? fuente = null, CancellationToken ct = default);

    /// <summary><c>GET /health/</c>, sólo su campo <c>nodo</c>: público, sin permiso, sin tocar la base. Para el banner del menú.</summary>
    Task<NodoEnSalud?> SaludAsync(CancellationToken ct = default);
}

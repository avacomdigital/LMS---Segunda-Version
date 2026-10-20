using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Licencia;

/// <summary>
/// Cliente de <c>/api/licencia/</c> (MOD-018 · Licensing) para OPS: el estado, el consumo y los módulos; la solicitud, la activación y la renovación sin internet mediante archivo; la copia
/// de custodia (CAP-111), la liberación del equipo (JRN-020) y la confirmación de la fecha tras un salto sospechoso del reloj. Quien decide es el nodo (SEC-001): este cliente sólo pide y
/// entrega lo que el nodo responde. Student no lo usa.
///
/// Mismas reglas de degradación que el resto de clientes del LMS: un error HTTP o de red NO es una excepción; devuelve <c>null</c> y deja el motivo en <see cref="UltimoMotivo"/> y el
/// <c>codigo</c> del backend en <see cref="UltimoError"/> (<c>licencia_invalida</c> con su <c>motivo</c>, <c>huella_no_coincide</c>, <c>conflicto</c>, <c>sin_permiso</c>,
/// <c>no_encontrado</c>, <c>datos_invalidos</c>). Con <see cref="UltimoError"/>.Estado == 0 no hay conexión con el nodo.
///
/// Quien actúa se identifica con <c>actor</c> mientras el nodo no exija sesión (Q-34); con sesión manda el JWT y el nodo ignora <c>actor</c>.
/// </summary>
public interface ILicenciaApi
{
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }

    /// <summary><c>GET estado/</c> (<c>license.read</c>): estado, motivo, vigencia, huella, límites, módulos y avisos.</summary>
    Task<EstadoLicencia?> EstadoAsync(string actor, CancellationToken ct = default);

    /// <summary><c>GET consumo/</c> (<c>license.read</c>): equipos y usuarios frente a lo contratado, contados en el momento, y la concurrencia.</summary>
    Task<ConsumoDeLicencia?> ConsumoAsync(string actor, CancellationToken ct = default);

    /// <summary><c>GET capacidades/</c> (cualquier sesión): qué módulos están encendidos, sin ningún detalle de la licencia.</summary>
    Task<CapacidadesDelNodo?> CapacidadesAsync(string actor, CancellationToken ct = default);

    /// <summary><c>GET copia/</c> (<c>license.read</c>): el <c>.avlic</c> vigente para guardarlo bajo custodia. 404 <c>no_encontrado</c> si no hay licencia instalada.</summary>
    Task<CopiaDeLicencia?> CopiaAsync(string actor, CancellationToken ct = default);

    /// <summary><c>POST solicitud/</c> (<c>license.activate</c>): la solicitud (<c>.avreq</c>) de este equipo, nueva en cada llamada.</summary>
    Task<SolicitudDeLicencia?> SolicitudAsync(string actor, CancellationToken ct = default);

    /// <summary>
    /// <c>POST activar/</c> (<c>license.activate</c>) con el texto <c>AVL1.…</c> (viaja como <c>licencia</c>) o con el base64 de los bytes del <c>.avlic</c> (viaja como
    /// <c>archivo_b64</c>). Devuelve el estado nuevo con <see cref="EstadoLicencia.Accion"/> (<c>activada</c>, <c>renovada</c> o <c>reactivada</c>).
    /// </summary>
    Task<EstadoLicencia?> ActivarAsync(string actor, string textoOBase64, CancellationToken ct = default);

    /// <summary><c>POST activar/</c> con los bytes del archivo tal como están en la memoria (si el archivo es la forma de texto <c>AVL1.</c>, viaja como texto).</summary>
    Task<EstadoLicencia?> ActivarAsync(string actor, byte[] archivo, CancellationToken ct = default);

    /// <summary><c>POST renovar/</c> (<c>license.renew</c>, sólo la administración): un archivo posterior de la MISMA licencia.</summary>
    Task<EstadoLicencia?> RenovarAsync(string actor, string textoOBase64, CancellationToken ct = default);

    /// <summary><c>POST renovar/</c> con los bytes del archivo.</summary>
    Task<EstadoLicencia?> RenovarAsync(string actor, byte[] archivo, CancellationToken ct = default);

    /// <summary>
    /// <c>POST liberar/</c> (<c>license.activate</c>): el equipo deja de usar la licencia y el nodo entrega la prueba de liberación (<c>.avrel</c>) junto con su estado nuevo. Se deshace
    /// volviendo a activar el mismo archivo. 409 <c>conflicto</c> si no hay licencia instalada.
    /// </summary>
    Task<ResultadoDeLiberacion?> LiberarAsync(string actor, CancellationToken ct = default);

    /// <summary><c>POST reloj/confirmar/</c> (<c>license.activate</c>): la fecha de hoy es la correcta tras un salto sospechoso del reloj; la sospecha se apaga.</summary>
    Task<EstadoLicencia?> ConfirmarRelojAsync(string actor, CancellationToken ct = default);
}

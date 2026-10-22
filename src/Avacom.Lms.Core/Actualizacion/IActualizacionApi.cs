using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Actualizacion;

/// <summary>
/// Cliente de <c>/api/actualizacion/</c> (MOD-017 · Update Manager) para OPS: el estado y los módulos del nodo, los paquetes <c>.avupd</c> que hay en las memorias, su importación, su
/// programación, la aplicación y la reversión, y el historial. Quien decide es el nodo (BR-013, SEC-001): verifica la firma, la compatibilidad, la serie, el espacio y que no haya una
/// clase abierta; este cliente sólo pide y entrega lo que el nodo responde. Nunca manda una ruta de archivo (P-11): sólo los ids que el nodo mismo listó. Student no lo usa.
///
/// Mismas reglas de degradación que el resto de clientes del LMS: un error HTTP o de red NO es una excepción; devuelve <c>null</c> y deja el motivo en <see cref="UltimoMotivo"/> y el
/// <c>codigo</c> del backend en <see cref="UltimoError"/> (<c>firma_invalida</c> y <c>paquete_invalido</c> con su <c>motivo</c>, <c>sesion_activa</c>, <c>contrato_incompatible</c>,
/// <c>espacio_insuficiente</c>, <c>fuera_de_plazo_reversion</c>, <c>estado_invalido</c>, <c>sin_permiso</c>…). Con <see cref="UltimoError"/>.Estado == 0 no hay conexión con el nodo.
///
/// Quien actúa se identifica con <c>actor</c> mientras el nodo no exija sesión (Q-34); con sesión manda el JWT y el nodo ignora <c>actor</c>.
/// </summary>
public interface IActualizacionApi
{
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }

    /// <summary><c>GET estado/</c> (<c>update.read</c>): estado, módulos con sus versiones, lo programado, lo revertible y el espacio libre.</summary>
    Task<EstadoDeActualizacion?> EstadoAsync(string actor, CancellationToken ct = default);

    /// <summary><c>GET paquetes/</c> (<c>update.read</c>): los paquetes de las memorias (candidatos) y los ya importados.</summary>
    Task<ListaDePaquetes?> PaquetesAsync(string actor, CancellationToken ct = default);

    /// <summary><c>GET paquetes/{id}/</c> (<c>update.read</c>): la ficha completa, con su historial.</summary>
    Task<FichaDePaquete?> PaqueteAsync(string actor, string paqueteId, CancellationToken ct = default);

    /// <summary><c>GET historial/</c> (<c>update.read</c>): lo último primero. <paramref name="limite"/> hasta 500; <paramref name="tipos"/> filtra por tipo.</summary>
    Task<HistorialDeActualizacion?> HistorialAsync(string actor, int limite = 50, IReadOnlyList<string>? tipos = null, CancellationToken ct = default);

    /// <summary>
    /// <c>POST paquetes/importar/</c> (<c>update.package.import</c>): trae al nodo el candidato (id opaco que el nodo listó) y lo verifica. 201 con la ficha (<c>verificado</c> o
    /// <c>incompatible</c>); 422 <c>firma_invalida</c> o <c>paquete_invalido</c> con su <c>motivo</c> si se rechaza (no se guarda nada).
    /// </summary>
    Task<FichaDePaquete?> ImportarAsync(string actor, string candidatoId, CancellationToken ct = default);

    /// <summary><c>POST paquetes/{id}/programar/</c> (<c>update.schedule</c>): una ventana única, en ms del reloj del nodo. 200 con la ficha <c>programado</c>.</summary>
    Task<FichaDePaquete?> ProgramarAsync(string actor, string paqueteId, long desde, long hasta, CancellationToken ct = default);

    /// <summary><c>POST paquetes/{id}/desprogramar/</c> (<c>update.schedule</c>): cancela la ventana. 200 con la ficha <c>verificado</c>.</summary>
    Task<FichaDePaquete?> DesprogramarAsync(string actor, string paqueteId, CancellationToken ct = default);

    /// <summary>
    /// <c>POST paquetes/{id}/aplicar/</c> (<c>update.apply</c>): aplicar ahora. 202 con la ficha <c>aplicando</c> y su <c>orden</c>; 409 <c>sesion_activa</c> si hay una clase abierta
    /// (la actualización se difiere, nunca la interrumpe), <c>contrato_incompatible</c>, <c>espacio_insuficiente</c>…
    /// </summary>
    Task<FichaDePaquete?> AplicarAsync(string actor, string paqueteId, CancellationToken ct = default);

    /// <summary>
    /// <c>POST paquetes/{id}/revertir/</c> (<c>update.apply</c>) con la nota obligatoria. 202 con la orden de reversión; 409 <c>fuera_de_plazo_reversion</c> pasados los 14 días.
    /// </summary>
    Task<FichaDePaquete?> RevertirAsync(string actor, string paqueteId, string nota, CancellationToken ct = default);
}

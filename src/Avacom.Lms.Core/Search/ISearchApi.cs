using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Search;

/// <summary>
/// Cliente de <c>/api/search/</c> (MOD-021 · Search) para el PERSONAL (OPS): buscar entre lo que el nodo tiene y lo que la persona puede leer, sus filtros, el estado del
/// índice y la comprobación de permiso al abrir un resultado. Contrato en <c>spec-driven/13-search/02-api.md</c>.
///
/// Mismas reglas de degradación que el resto de clientes del LMS: un error HTTP o de red NO es una excepción, devuelve <c>null</c> y deja el motivo en
/// <see cref="UltimoMotivo"/> y el <c>codigo</c> del backend en <see cref="UltimoError"/> (<c>consulta_vacia</c>, <c>consulta_invalida</c>, <c>sin_permiso</c>,
/// <c>no_disponible</c>, <c>catalogo_no_disponible</c>…). Con <see cref="UltimoError"/>.Estado == 0 no hay conexión con el nodo del aula.
///
/// Toda petición admite cancelación: una consulta nueva cancela la anterior. El profesor se identifica con <c>actor</c> mientras el nodo no exija sesión (Q-34); con
/// sesión manda el JWT.
/// </summary>
public interface ISearchApi
{
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }

    /// <summary>CAP-124 · CAP-125: busca por texto con filtros. Lo que no puede leer la persona no llega: ni el resultado, ni un fragmento, ni un conteo.</summary>
    Task<RespuestaDeBusqueda?> BuscarAsync(string actor, ConsultaDeBusqueda consulta, CancellationToken ct = default);

    /// <summary>Las opciones de filtro válidas para quien consulta.</summary>
    Task<OpcionesDeFiltros?> FiltrosAsync(string actor, CancellationToken ct = default);

    /// <summary>El estado del índice (consultable, rezagado, construyéndose, reconstruyéndose).</summary>
    Task<EstadoDeBusqueda?> EstadoAsync(string actor, CancellationToken ct = default);

    /// <summary>BR-088 al abrir: el nodo vuelve a comprobar el permiso y la vigencia del recurso original. Null con <c>no_disponible</c> si ya no se puede abrir.</summary>
    Task<AperturaDeResultado?> AbrirAsync(string actor, DestinoDeNavegacion destino, CancellationToken ct = default);
}

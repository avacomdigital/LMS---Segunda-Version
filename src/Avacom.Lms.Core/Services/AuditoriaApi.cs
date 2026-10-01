using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>
/// Cliente de <c>/api/auditoria/</c> (MOD-019 · Audit) para OPS: la bitácora de sólo lectura (PAN-240), la integridad de la cadena, las
/// exportaciones firmadas y los accesos del técnico. Toda ruta exige sesión de usuario (<see cref="ClienteJson.Token"/>) y el permiso que
/// corresponda (<c>audit.read</c> · <c>audit.export</c>); sin él el nodo responde 403 <c>permiso_denegado</c> y lo asienta. No existe ningún
/// verbo de escritura sobre asientos ni tramos. Mismas reglas de degradación que <see cref="AulaApi"/>: null + <see cref="ClienteJson.UltimoError"/>.
/// </summary>
public interface IAuditoriaApi
{
    Uri BaseUri { get; }
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }

    Task<PaginaAsientos?> AsientosAsync(FiltrosBitacora? filtros = null, CancellationToken ct = default);
    Task<Asiento?> AsientoAsync(string idOSecuencia, CancellationToken ct = default);
    Task<CatalogoAuditoria?> CatalogoAsync(CancellationToken ct = default);
    Task<TramosBitacora?> TramosAsync(CancellationToken ct = default);
    Task<EstadoBitacora?> EstadoAsync(CancellationToken ct = default);
    Task<ResultadoVerificacion?> VerificarAsync(bool todos = false, CancellationToken ct = default);
    Task<ListaExportaciones?> ExportacionesAsync(CancellationToken ct = default);
    /// <summary>Exporta un tramo entero (<paramref name="tramoId"/>) o un rango (<paramref name="desde"/>, <paramref name="hasta"/>). Exige autorización de salida vigente.</summary>
    Task<Exportacion?> ExportarAsync(string motivoCodigo, string? tramoId = null, long? desde = null, long? hasta = null, string? motivoDetalle = null, CancellationToken ct = default);
    /// <summary>Baja el archivo firmado de una exportación a <paramref name="rutaDestino"/>. Devuelve la ruta o null si el nodo lo negó.</summary>
    Task<string?> DescargarExportacionAsync(string exportacionId, string rutaDestino, CancellationToken ct = default);
    Task<AccesosDelTecnico?> AccesosDelTecnicoAsync(long? desde = null, long? hasta = null, int? limite = null, long? antes = null, CancellationToken ct = default);
}

public sealed class AuditoriaApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri), IAuditoriaApi
{
    public Task<PaginaAsientos?> AsientosAsync(FiltrosBitacora? filtros = null, CancellationToken ct = default) =>
        ObtenerAsync<PaginaAsientos>("api/auditoria/asientos/" + (filtros ?? new FiltrosBitacora()).Query(), ct);

    public Task<Asiento?> AsientoAsync(string idOSecuencia, CancellationToken ct = default) =>
        ObtenerAsync<Asiento>($"api/auditoria/asientos/{Uri.EscapeDataString(idOSecuencia)}/", ct);

    public Task<CatalogoAuditoria?> CatalogoAsync(CancellationToken ct = default) =>
        ObtenerAsync<CatalogoAuditoria>("api/auditoria/catalogo/", ct);

    public Task<TramosBitacora?> TramosAsync(CancellationToken ct = default) =>
        ObtenerAsync<TramosBitacora>("api/auditoria/tramos/", ct);

    public Task<EstadoBitacora?> EstadoAsync(CancellationToken ct = default) =>
        ObtenerAsync<EstadoBitacora>("api/auditoria/estado/", ct);

    public Task<ResultadoVerificacion?> VerificarAsync(bool todos = false, CancellationToken ct = default) =>
        EnviarAsync<ResultadoVerificacion>("api/auditoria/verificar/", new { todos }, ct);

    public Task<ListaExportaciones?> ExportacionesAsync(CancellationToken ct = default) =>
        ObtenerAsync<ListaExportaciones>("api/auditoria/exportaciones/", ct);

    /// <summary>El nodo valida `desde`/`hasta` como enteros no nulos: se manda sólo el alcance que aplica (tramo o rango), nunca nulos.</summary>
    public Task<Exportacion?> ExportarAsync(string motivoCodigo, string? tramoId = null, long? desde = null, long? hasta = null, string? motivoDetalle = null, CancellationToken ct = default) =>
        string.IsNullOrWhiteSpace(tramoId)
            ? EnviarAsync<Exportacion>("api/auditoria/exportar/", new { desde, hasta, motivo_codigo = motivoCodigo, motivo_detalle = motivoDetalle ?? string.Empty }, ct)
            : EnviarAsync<Exportacion>("api/auditoria/exportar/", new { tramo_id = tramoId, motivo_codigo = motivoCodigo, motivo_detalle = motivoDetalle ?? string.Empty }, ct);

    public async Task<string?> DescargarExportacionAsync(string exportacionId, string rutaDestino, CancellationToken ct = default)
    {
        using var respuesta = await ObtenerRespuestaAsync($"api/auditoria/exportaciones/{Uri.EscapeDataString(exportacionId)}/descargar/", null, ct);
        if (respuesta is null) return null;
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(rutaDestino)!);
            var temporal = rutaDestino + ".parcial";
            await using (var archivo = File.Create(temporal))
            await using (var cuerpo = await respuesta.Content.ReadAsStreamAsync(ct))
                await cuerpo.CopyToAsync(archivo, ct);
            File.Move(temporal, rutaDestino, overwrite: true);
            return rutaDestino;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            RegistroLocal.Error(Canal.Escritura, "exportacion.guardar_fallo", "No se pudo guardar la exportación en el equipo", new { archivo = Path.GetFileName(rutaDestino) }, ex);
            return null;
        }
    }

    public Task<AccesosDelTecnico?> AccesosDelTecnicoAsync(long? desde = null, long? hasta = null, int? limite = null, long? antes = null, CancellationToken ct = default) =>
        ObtenerAsync<AccesosDelTecnico>("api/auditoria/tecnico/accesos/" + new FiltrosBitacora(Desde: desde, Hasta: hasta, Limite: limite, Antes: antes).Query(), ct);
}

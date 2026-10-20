using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Reporting;

/// <summary>
/// Cliente de <c>/api/reportes/</c> (MOD-013): las rutas de <c>spec-driven/14-reporting/02-api.md</c>, una por método de <see cref="IReportesApi"/>. El profesor se identifica con
/// <c>actor</c> en la consulta (GET) o en el cuerpo (POST/PUT); los campos opcionales que valen null NO viajan. Un error HTTP o de red no es una excepción: devuelve null y deja el
/// motivo y el <c>codigo</c> en <see cref="ClienteJson.UltimoMotivo"/> y <see cref="ClienteJson.UltimoError"/>.
/// </summary>
public sealed class ReportesApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri), IReportesApi
{
    private const string Base = "api/reportes/";
    public const string CabeceraExport = "X-Avacom-Export-";
    private const int Bloque = 81_920;

    /// <summary>El identificador de una exportación da nombre al temporal local: tiene que ser un código (letras, números, guion y guion bajo), nunca una ruta. El nodo manda un UUID.</summary>
    private static readonly Regex IdSeguro = new("^[A-Za-z0-9_-]{1,64}$", RegexOptions.CultureInvariant | RegexOptions.Compiled);

    private static string Esc(string valor) => Uri.EscapeDataString(valor);

    /// <summary>La ruta con su consulta; los valores nulos o vacíos no viajan.</summary>
    private static string Ruta(string ruta, params (string Clave, string? Valor)[] consulta) => Ruta(ruta, consulta, null);

    private static string Ruta(string ruta, IEnumerable<(string Clave, string? Valor)> consulta, NodoAcademico? nodo)
    {
        var texto = new StringBuilder(Base).Append(ruta);
        var separador = '?';
        foreach (var (clave, valor) in consulta.Concat(nodo?.Pares().Select(p => (p.Clave, (string?)p.Valor)) ?? []))
        {
            if (string.IsNullOrEmpty(valor)) continue;
            texto.Append(separador).Append(clave).Append('=').Append(Esc(valor));
            separador = '&';
        }
        return texto.ToString();
    }

    private static string? Num(long? valor) => valor?.ToString(System.Globalization.CultureInfo.InvariantCulture);

    // ================================================================================================== leer

    public Task<ListaDeClases?> ClasesAsync(string actor, FiltroDeClases? filtro = null, CancellationToken ct = default) =>
        ObtenerAsync<ListaDeClases>(Ruta("clases/", [("grupo_id", filtro?.GrupoId), ("desde", Num(filtro?.Desde)), ("hasta", Num(filtro?.Hasta)), ("limite", filtro?.Limite?.ToString()), ("actor", actor)], filtro?.Nodo), ct);

    public Task<ReporteDeClase?> ClaseAsync(string actor, string sesionId, CancellationToken ct = default) =>
        ObtenerAsync<ReporteDeClase>(Ruta($"clases/{Esc(sesionId)}/", ("actor", actor)), ct);

    public Task<ReporteDeGrupo?> GrupoAsync(string actor, string grupoId, NodoAcademico? nodo = null, CancellationToken ct = default) =>
        ObtenerAsync<ReporteDeGrupo>(Ruta($"grupos/{Esc(grupoId)}/", [("actor", actor)], nodo), ct);

    public Task<AlumnosParaElegir?> AlumnosAsync(string actor, string grupoId, CancellationToken ct = default) =>
        ObtenerAsync<AlumnosParaElegir>(Ruta("alumnos/", ("grupo_id", grupoId), ("actor", actor)), ct);

    public Task<ReporteDeAlumno?> AlumnoAsync(string actor, string alumnoId, string? grupoId = null, NodoAcademico? nodo = null, CancellationToken ct = default) =>
        ObtenerAsync<ReporteDeAlumno>(Ruta($"alumnos/{Esc(alumnoId)}/", [("grupo_id", grupoId), ("actor", actor)], nodo), ct);

    public Task<ReporteDeUso?> UsoAsync(string actor, PeriodoPedido? periodo = null, string? grupoId = null, NodoAcademico? nodo = null, CancellationToken ct = default) =>
        ObtenerAsync<ReporteDeUso>(Ruta("uso/", [("desde", Num(periodo?.Desde)), ("hasta", Num(periodo?.Hasta)), ("grupo_id", grupoId), ("actor", actor)], nodo), ct);

    public Task<ReporteDeBoletin?> BoletinAsync(string actor, string alumnoId, string? grupoId = null, NodoAcademico? nodo = null, CancellationToken ct = default) =>
        ObtenerAsync<ReporteDeBoletin>(Ruta($"boletines/{Esc(alumnoId)}/", [("grupo_id", grupoId), ("actor", actor)], nodo), ct);

    public Task<ReporteDeBoletines?> BoletinesAsync(string actor, string grupoId, NodoAcademico? nodo = null, CancellationToken ct = default) =>
        ObtenerAsync<ReporteDeBoletines>(Ruta("boletines/", [("grupo_id", grupoId), ("actor", actor)], nodo), ct);

    public Task<FiltrosDeReportes?> FiltrosAsync(string actor, CancellationToken ct = default) =>
        ObtenerAsync<FiltrosDeReportes>(Ruta("filtros/", ("actor", actor)), ct);

    public Task<RecientesDeReportes?> RecientesAsync(string actor, CancellationToken ct = default) =>
        ObtenerAsync<RecientesDeReportes>(Ruta("recientes/", ("actor", actor)), ct);

    // ====================================================================== configuración y agregados

    public Task<RespuestaDeConfiguracion?> ConfiguracionAsync(string actor, CancellationToken ct = default) =>
        ObtenerAsync<RespuestaDeConfiguracion>(Ruta("configuracion/", ("actor", actor)), ct);

    public Task<RespuestaDeConfiguracion?> CambiarConfiguracionAsync(string actor, CambioDeConfiguracion cambio, CancellationToken ct = default)
    {
        var cuerpo = new Dictionary<string, object> { ["actor"] = actor };
        if (cambio.UmbralPrivacidad is { } u) cuerpo["umbral_privacidad"] = u;
        if (cambio.ExtraiblesPermitidos is { } e) cuerpo["extraibles_permitidos"] = e;
        if (cambio.ExigirRazon is { } r) cuerpo["exigir_razon"] = r;
        if (cambio.PlantillaBoletin is { } p) cuerpo["plantilla_boletin"] = p;
        if (cambio.PeriodosBoletin is { } periodos) cuerpo["periodos_boletin"] = periodos;
        if (cambio.LeyendaBoletin is { } l) cuerpo["leyenda_boletin"] = l;
        if (cambio.VersionEsperada is { } v) cuerpo["version_esperada"] = v;
        return ReemplazarAsync<RespuestaDeConfiguracion>(Base + "configuracion/", cuerpo, ct);
    }

    public Task<EstadoDeAgregados?> EstadoAsync(string actor, CancellationToken ct = default) =>
        ObtenerAsync<EstadoDeAgregados>(Ruta("estado/", ("actor", actor)), ct);

    public Task<ResultadoDeActualizacion?> ActualizarAsync(string actor, CancellationToken ct = default) =>
        EnviarAsync<ResultadoDeActualizacion>(Base + "actualizar/", new { actor }, ct);

    public Task<ResultadoDeReconstruccion?> ReconstruirAsync(string actor, CancellationToken ct = default) =>
        EnviarAsync<ResultadoDeReconstruccion>(Base + "reconstruir/", new { actor }, ct);

    // ================================================================================================ exportar

    private static Dictionary<string, object> CuerpoDeExportacion(string actor, ReporteSolicitado reporte, string formato, string? destinoTipo = null, string? razonCodigo = null)
    {
        var cuerpo = new Dictionary<string, object> { ["reporte"] = reporte.ACuerpo(), ["formato"] = formato, ["actor"] = actor };
        if (!string.IsNullOrEmpty(destinoTipo)) cuerpo["destino_tipo"] = destinoTipo;
        if (!string.IsNullOrEmpty(razonCodigo)) cuerpo["razon_codigo"] = razonCodigo;
        return cuerpo;
    }

    public Task<AlcanceDeExportacion?> AlcanceAsync(string actor, ReporteSolicitado reporte, string formato, CancellationToken ct = default) =>
        EnviarAsync<AlcanceDeExportacion>(Base + "exportaciones/alcance/", CuerpoDeExportacion(actor, reporte, formato), ct);

    public async Task<ArchivoExportado?> AutorizarExportacionAsync(string actor, ReporteSolicitado reporte, string formato, string destinoTipo, string? razonCodigo, string carpetaTemporal,
                                                                    IProgress<double>? progreso = null, CancellationToken ct = default)
    {
        using var respuesta = await EnviarParaRespuestaAsync(Base + "exportaciones/", CuerpoDeExportacion(actor, reporte, formato, destinoTipo, razonCodigo), ct);
        if (respuesta is null) return null;
        string Cabecera(string nombre) => respuesta.Headers.TryGetValues(CabeceraExport + nombre, out var v) ? v.FirstOrDefault() ?? "" : "";
        var id = Cabecera("Id");
        var huella = Cabecera("Huella").ToLowerInvariant();
        if (!IdSeguro.IsMatch(id) || huella.Length != 64 || !long.TryParse(Cabecera("Bytes"), out var bytes))
        {
            AnotarMotivo("respuesta_incompleta", "El nodo entregó el archivo sin sus datos de control: no se puede guardar con seguridad.", "Vuelve a intentarlo; si se repite, avisa a soporte.");
            return null;
        }
        string? ruta = null;
        var completo = false;
        try
        {
            Directory.CreateDirectory(carpetaTemporal);
            ruta = Path.Combine(carpetaTemporal, $"{id}.parte");
            using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            long recibidos = 0;
            await using (var salida = new FileStream(ruta, FileMode.Create, FileAccess.Write, FileShare.None, Bloque, FileOptions.Asynchronous | FileOptions.SequentialScan))
            await using (var cuerpo = await respuesta.Content.ReadAsStreamAsync(ct))
            {
                var bufer = new byte[Bloque];
                int leidos;
                while ((leidos = await cuerpo.ReadAsync(bufer.AsMemory(0, Bloque), ct)) > 0)
                {
                    hash.AppendData(bufer, 0, leidos);
                    await salida.WriteAsync(bufer.AsMemory(0, leidos), ct);
                    recibidos += leidos;
                    if (bytes > 0) progreso?.Report(Math.Min(1.0, (double)recibidos / bytes));
                }
                await salida.FlushAsync(ct);
            }
            if (recibidos != bytes || !string.Equals(Convert.ToHexString(hash.GetHashAndReset()), huella, StringComparison.OrdinalIgnoreCase))
            {
                File.Delete(ruta);
                AnotarMotivo("archivo_danado", "El archivo llegó dañado desde el nodo y se descartó.", "Vuelve a generar el reporte.");
                return null;
            }
            progreso?.Report(1.0);
            _ = long.TryParse(Cabecera("Expira-En"), out var expira);
            _ = long.TryParse(Cabecera("Corte-En"), out var corte);
            _ = int.TryParse(Cabecera("Filas"), out var filas);
            var archivo = new ArchivoExportado
            {
                Id = id, Tipo = Cabecera("Tipo"), Formato = Cabecera("Formato"), Huella = huella, Bytes = bytes, Filas = filas, NombreArchivo = Uri.UnescapeDataString(Cabecera("Nombre")),
                ExpiraEn = expira, CorteEn = corte, Nominal = Cabecera("Nominal") == "true", UmbralAplicado = Cabecera("Umbral-Aplicado") == "true", DestinoAutorizado = Cabecera("Destino"),
                RutaTemporal = ruta,
            };
            completo = true;
            return archivo;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or HttpRequestException)
        {
            RegistroLocal.Error(Canal.Escritura, "reportes.temporal_fallo", "No se pudo bajar el reporte exportado a un archivo temporal", new { formato, tipo = reporte.Tipo }, ex);
            AnotarMotivo("sin_temporal", "No se pudo bajar el reporte a este equipo.", "Comprueba que el equipo tenga espacio libre y vuelve a intentarlo.");
            return null;
        }
        finally
        {
            // Un archivo a medias nunca se queda: ni por un fallo, ni porque la persona canceló a mitad de la bajada (la cancelación sale como excepción).
            if (!completo && ruta is not null)
                try { File.Delete(ruta); } catch (Exception) { /* un temporal que no se deja borrar se limpia en el próximo arranque */ }
        }
    }

    public Task<RespuestaDeExportacion?> ConfirmarGuardadoAsync(string actor, string exportacionId, string destinoTipo, string huellaVerificada, CancellationToken ct = default) =>
        EnviarAsync<RespuestaDeExportacion>(Base + $"exportaciones/{Esc(exportacionId)}/confirmar/",
            new Dictionary<string, object> { ["resultado"] = "guardado", ["destino_tipo"] = destinoTipo, ["huella_verificada"] = huellaVerificada, ["actor"] = actor }, ct);

    public Task<RespuestaDeExportacion?> ConfirmarFalloAsync(string actor, string exportacionId, string destinoTipo, string motivoCodigo, CancellationToken ct = default) =>
        EnviarAsync<RespuestaDeExportacion>(Base + $"exportaciones/{Esc(exportacionId)}/confirmar/",
            new Dictionary<string, object> { ["resultado"] = "fallido", ["destino_tipo"] = destinoTipo, ["motivo"] = motivoCodigo, ["actor"] = actor }, ct);

    public Task<RespuestaDeExportacion?> ExportacionAsync(string actor, string exportacionId, CancellationToken ct = default) =>
        ObtenerAsync<RespuestaDeExportacion>(Ruta($"exportaciones/{Esc(exportacionId)}/", ("actor", actor)), ct);

    public Task<ListaDeExportaciones?> ExportacionesAsync(string actor, CancellationToken ct = default) =>
        ObtenerAsync<ListaDeExportaciones>(Ruta("exportaciones/", ("actor", actor)), ct);
}

using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Reporting;

/// <summary>
/// Cliente de <c>/api/reportes/</c> (MOD-013) para el PERSONAL (OPS): el reporte de una clase, de un grupo y de un alumno, el uso de equipos, los filtros, la configuración
/// del nodo y la exportación a archivo en dos tiempos. Contrato en <c>spec-driven/14-reporting/02-api.md</c>.
///
/// Mismas reglas de degradación que el resto de clientes del LMS: un error HTTP o de red NO es una excepción, devuelve <c>null</c> y deja el motivo en
/// <see cref="UltimoMotivo"/> y el <c>codigo</c> del backend en <see cref="UltimoError"/> (<c>sin_permiso</c>, <c>fuera_de_alcance</c>, <c>clase_en_curso</c>,
/// <c>sin_sesiones_finalizadas</c>, <c>destino_no_permitido</c>, <c>huella_distinta</c>, <c>exportacion_caducada</c>…). Con <see cref="UltimoError"/>.Estado == 0 no hay conexión con el nodo.
///
/// El profesor se identifica con <c>actor</c> mientras el nodo no exija sesión (Q-34); con sesión manda el JWT.
/// </summary>
public interface IReportesApi
{
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }

    // ---- leer
    Task<ListaDeClases?> ClasesAsync(string actor, FiltroDeClases? filtro = null, CancellationToken ct = default);
    Task<ReporteDeClase?> ClaseAsync(string actor, string sesionId, CancellationToken ct = default);
    Task<ReporteDeGrupo?> GrupoAsync(string actor, string grupoId, NodoAcademico? nodo = null, CancellationToken ct = default);
    Task<AlumnosParaElegir?> AlumnosAsync(string actor, string grupoId, CancellationToken ct = default);
    Task<ReporteDeAlumno?> AlumnoAsync(string actor, string alumnoId, string? grupoId = null, NodoAcademico? nodo = null, CancellationToken ct = default);
    Task<ReporteDeUso?> UsoAsync(string actor, PeriodoPedido? periodo = null, string? grupoId = null, NodoAcademico? nodo = null, CancellationToken ct = default);
    /// <summary>El boletín académico de un estudiante (sin <paramref name="grupoId"/>, el primero de sus grupos que se puede ver).</summary>
    Task<ReporteDeBoletin?> BoletinAsync(string actor, string alumnoId, string? grupoId = null, NodoAcademico? nodo = null, CancellationToken ct = default);
    /// <summary>Los boletines de todos los estudiantes de un grupo (uno por estudiante): lo que se exporta como un zip.</summary>
    Task<ReporteDeBoletines?> BoletinesAsync(string actor, string grupoId, NodoAcademico? nodo = null, CancellationToken ct = default);
    Task<FiltrosDeReportes?> FiltrosAsync(string actor, CancellationToken ct = default);
    Task<RecientesDeReportes?> RecientesAsync(string actor, CancellationToken ct = default);

    // ---- configuración del nodo y estado de los agregados
    Task<RespuestaDeConfiguracion?> ConfiguracionAsync(string actor, CancellationToken ct = default);
    Task<RespuestaDeConfiguracion?> CambiarConfiguracionAsync(string actor, CambioDeConfiguracion cambio, CancellationToken ct = default);
    Task<EstadoDeAgregados?> EstadoAsync(string actor, CancellationToken ct = default);
    Task<ResultadoDeActualizacion?> ActualizarAsync(string actor, CancellationToken ct = default);
    Task<ResultadoDeReconstruccion?> ReconstruirAsync(string actor, CancellationToken ct = default);

    // ---- exportar a archivo (FUN-146), en dos tiempos
    /// <summary>El alcance declarado ANTES de confirmar: qué se va a guardar, si lleva nombres y la política del administrador. No genera nada.</summary>
    Task<AlcanceDeExportacion?> AlcanceAsync(string actor, ReporteSolicitado reporte, string formato, CancellationToken ct = default);

    /// <summary>
    /// 1.er tiempo: el nodo autoriza, genera el archivo y lo entrega; aquí se baja directo a un archivo temporal de <paramref name="carpetaTemporal"/> (nunca entero en memoria) y se
    /// comprueba su SHA-256 contra el que declaró el nodo. Quien lo recibe lo escribe donde la persona elija y debe liberarlo (borra el temporal). Null si el nodo lo negó, si no hubo
    /// conexión o si el archivo llegó dañado (<see cref="UltimoError"/> lo dice).
    /// </summary>
    Task<ArchivoExportado?> AutorizarExportacionAsync(string actor, ReporteSolicitado reporte, string formato, string destinoTipo, string? razonCodigo, string carpetaTemporal,
                                                      IProgress<double>? progreso = null, CancellationToken ct = default);

    /// <summary>2.º tiempo, cuando se guardó: el tipo de destino y la huella que se verificó releyendo el archivo ya escrito. Sólo entonces el nodo lo da por entregado.</summary>
    Task<RespuestaDeExportacion?> ConfirmarGuardadoAsync(string actor, string exportacionId, string destinoTipo, string huellaVerificada, CancellationToken ct = default);

    /// <summary>2.º tiempo, cuando NO se pudo guardar: el motivo (de <see cref="MotivosDeEscritura"/>). No cierra la exportación: se puede elegir otro destino sin generar de nuevo.</summary>
    Task<RespuestaDeExportacion?> ConfirmarFalloAsync(string actor, string exportacionId, string destinoTipo, string motivoCodigo, CancellationToken ct = default);

    Task<RespuestaDeExportacion?> ExportacionAsync(string actor, string exportacionId, CancellationToken ct = default);
    Task<ListaDeExportaciones?> ExportacionesAsync(string actor, CancellationToken ct = default);
}

/// <summary>Los filtros del listado de clases (fichas, nunca texto): grupo, periodo en milisegundos y nodo académico.</summary>
public sealed record FiltroDeClases(string? GrupoId = null, long? Desde = null, long? Hasta = null, int? Limite = null, NodoAcademico? Nodo = null);

/// <summary>El periodo de un reporte de uso: instantes del nodo en milisegundos; null = sin tope por ese lado.</summary>
public sealed record PeriodoPedido(long? Desde, long? Hasta);

/// <summary>Un nodo académico para filtrar (país · nivel · grado · materia · tema), con los mismos nombres que el árbol de AVACOM Contenido.</summary>
public sealed record NodoAcademico(string? Country = null, string? Level = null, string? Grade = null, string? Subject = null, string? Topic = null)
{
    public bool EstaVacio => string.IsNullOrEmpty(Country) && string.IsNullOrEmpty(Level) && string.IsNullOrEmpty(Grade) && string.IsNullOrEmpty(Subject) && string.IsNullOrEmpty(Topic);

    /// <summary>Los pares clave/valor que viajan (los vacíos no).</summary>
    public IEnumerable<(string Clave, string Valor)> Pares()
    {
        if (!string.IsNullOrEmpty(Country)) yield return ("country", Country);
        if (!string.IsNullOrEmpty(Level)) yield return ("level", Level);
        if (!string.IsNullOrEmpty(Grade)) yield return ("grade", Grade);
        if (!string.IsNullOrEmpty(Subject)) yield return ("subject", Subject);
        if (!string.IsNullOrEmpty(Topic)) yield return ("topic", Topic);
    }
}

/// <summary>Qué reporte se exporta: el mismo que se ve en pantalla, con los mismos parámetros. Lo que vale null no viaja.</summary>
public sealed record ReporteSolicitado(string Tipo, string? SesionId = null, string? GrupoId = null, string? AlumnoId = null, long? Desde = null, long? Hasta = null, NodoAcademico? Nodo = null)
{
    public static ReporteSolicitado DeClase(string sesionId) => new(TiposDeReporte.Clase, SesionId: sesionId);
    public static ReporteSolicitado DeGrupo(string grupoId, NodoAcademico? nodo = null) => new(TiposDeReporte.Grupo, GrupoId: grupoId, Nodo: nodo);
    public static ReporteSolicitado DeAlumno(string alumnoId, string? grupoId = null, NodoAcademico? nodo = null) => new(TiposDeReporte.Alumno, AlumnoId: alumnoId, GrupoId: grupoId, Nodo: nodo);
    public static ReporteSolicitado DeUso(PeriodoPedido? periodo = null, string? grupoId = null) => new(TiposDeReporte.Uso, GrupoId: grupoId, Desde: periodo?.Desde, Hasta: periodo?.Hasta);
    /// <summary>El boletín de UN estudiante (con <paramref name="alumnoId"/>) o los de todo un grupo (sin él): entonces el nodo entrega un zip con un archivo por estudiante.</summary>
    public static ReporteSolicitado DeBoletin(string grupoId, string? alumnoId = null, NodoAcademico? nodo = null) => new(TiposDeReporte.Boletin, GrupoId: grupoId, AlumnoId: alumnoId, Nodo: nodo);

    /// <summary>El cuerpo del descriptor tal como lo espera el nodo (<c>reporte</c> de <c>exportaciones/</c>).</summary>
    public Dictionary<string, object> ACuerpo()
    {
        var cuerpo = new Dictionary<string, object> { ["tipo"] = Tipo };
        if (!string.IsNullOrEmpty(SesionId)) cuerpo["sesion_id"] = SesionId;
        if (!string.IsNullOrEmpty(GrupoId)) cuerpo["grupo_id"] = GrupoId;
        if (!string.IsNullOrEmpty(AlumnoId)) cuerpo["alumno_id"] = AlumnoId;
        if (Desde is { } d) cuerpo["desde"] = d;
        if (Hasta is { } h) cuerpo["hasta"] = h;
        if (Nodo is not null) foreach (var (clave, valor) in Nodo.Pares()) cuerpo[clave] = valor;
        return cuerpo;
    }
}

/// <summary>
/// El archivo que el nodo entregó, ya en un temporal local con su huella comprobada. <see cref="Dispose"/> borra el temporal: quien lo escribe en el destino lo libera al terminar
/// (con éxito o sin él). Mientras no se libere, un fallo de escritura permite elegir OTRO destino sin volver a generarlo.
/// </summary>
public sealed class ArchivoExportado : IDisposable
{
    public required string Id { get; init; }
    public required string Tipo { get; init; }
    public required string Formato { get; init; }
    public required string Huella { get; init; }
    public required long Bytes { get; init; }
    public required int Filas { get; init; }
    public required string NombreArchivo { get; init; }
    public required long ExpiraEn { get; init; }
    public required long CorteEn { get; init; }
    public required bool Nominal { get; init; }
    public required bool UmbralAplicado { get; init; }
    public required string DestinoAutorizado { get; init; }
    public required string RutaTemporal { get; init; }

    private bool liberado;

    public void Dispose()
    {
        if (liberado) return;
        try
        {
            if (File.Exists(RutaTemporal)) File.Delete(RutaTemporal);
            liberado = true;                // sólo cuando ya no está: un borrado que falló (el archivo en uso) se vuelve a intentar en la próxima llamada
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { /* si no se pudo, queda para el próximo intento o, a más tardar, para el próximo arranque */ }
    }
}

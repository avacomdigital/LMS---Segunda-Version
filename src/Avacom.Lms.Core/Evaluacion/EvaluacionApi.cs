using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Evaluacion;

/// <summary>
/// Cliente de <c>/api/evaluacion/</c> (MOD-010): las rutas de <c>spec-driven/06-evaluation-delivery/backend.md</c> §4, una por método de
/// <see cref="IExamenAlumnoApi"/> (tableta) y de <see cref="IExamenDocenteApi"/> (OPS).
///
/// El aparato viaja como <c>dispositivo</c> en la consulta (GET) o en el cuerpo (POST); <c>alumno_id</c> sólo si el llamador lo da (tableta compartida sin
/// sesión); el profesor manda <c>actor</c> igual. Los campos opcionales que valen null NO viajan: un serializador estricto del backend no distingue
/// «ausente» de «nulo». Un error HTTP o de red no es una excepción: devuelve null (o false) y deja el motivo y el <c>codigo</c> en
/// <see cref="ClienteJson.UltimoMotivo"/> y <see cref="ClienteJson.UltimoError"/>.
/// </summary>
public sealed class EvaluacionApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri), IExamenAlumnoApi, IExamenDocenteApi
{
    private const string Base = "api/evaluacion/";

    private static string Esc(string valor) => Uri.EscapeDataString(valor);

    /// <summary>La ruta con su consulta; los valores nulos o vacíos no viajan.</summary>
    private static string Ruta(string ruta, params (string Clave, string? Valor)[] consulta)
    {
        var texto = new StringBuilder(Base).Append(ruta);
        var separador = '?';
        foreach (var (clave, valor) in consulta)
        {
            if (string.IsNullOrEmpty(valor)) continue;
            texto.Append(separador).Append(clave).Append('=').Append(Esc(valor));
            separador = '&';
        }
        return texto.ToString();
    }

    /// <summary>El cuerpo de una petición de la tableta: el aparato, los campos que no son nulos y, si viene, <c>alumno_id</c>.</summary>
    private static Dictionary<string, object?> Tableta(string dispositivo, string? alumnoId, params (string Clave, object? Valor)[] campos)
    {
        var cuerpo = new Dictionary<string, object?> { ["dispositivo"] = dispositivo };
        foreach (var (clave, valor) in campos)
            if (valor is not null) cuerpo[clave] = valor;
        if (alumnoId is not null) cuerpo["alumno_id"] = alumnoId;
        return cuerpo;
    }

    /// <summary>El cuerpo de una petición del profesor: sus campos que no son nulos y el <c>actor</c>.</summary>
    private static Dictionary<string, object?> Docente(string actor, params (string Clave, object? Valor)[] campos)
    {
        var cuerpo = new Dictionary<string, object?>();
        foreach (var (clave, valor) in campos)
            if (valor is not null) cuerpo[clave] = valor;
        cuerpo["actor"] = actor;
        return cuerpo;
    }

    private static string Asig(string id) => $"asignaciones/{Esc(id)}/";
    private static string Intento(string id) => $"intentos/{Esc(id)}/";

    /// <summary>Verdadero si el backend contestó 2xx (el cuerpo no importa).</summary>
    private async Task<bool> Hecho(string ruta, object cuerpo, CancellationToken ct) =>
        await EnviarAsync<JsonElement?>(ruta, cuerpo, ct) is not null;

    // ============================================================================================ tableta del alumno

    public Task<MisEvaluaciones?> MisAsync(string dispositivo, string? alumnoId = null, bool todas = false, CancellationToken ct = default) =>
        ObtenerAsync<MisEvaluaciones>(Ruta("mias/", ("dispositivo", dispositivo), ("alumno_id", alumnoId), ("todas", todas ? "1" : null)), ct);

    public Task<AntesalaDeExamen?> AntesalaAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default) =>
        ObtenerAsync<AntesalaDeExamen>(Ruta(Asig(asignacionId) + "antesala/", ("dispositivo", dispositivo), ("alumno_id", alumnoId)), ct);

    public Task<AperturaDeIntento?> AbrirAsync(string dispositivo, string asignacionId, DatosDeTableta? tableta = null, string? alumnoId = null, CancellationToken ct = default) =>
        EnviarAsync<AperturaDeIntento>(Base + Asig(asignacionId) + "intentos/",
            Tableta(dispositivo, alumnoId, ("nombre", tableta?.Nombre), ("plataforma", tableta?.Plataforma), ("version_app", tableta?.VersionApp),
                    ("capacidad_control", tableta?.CapacidadControl)), ct);

    public Task<EstadoDeIntento?> EstadoAsync(string dispositivo, string intentoId, string? alumnoId = null, CancellationToken ct = default) =>
        ObtenerAsync<EstadoDeIntento>(Ruta(Intento(intentoId) + "estado/", ("dispositivo", dispositivo), ("alumno_id", alumnoId)), ct);

    public Task<EstadoDeIntento?> LatirAsync(string dispositivo, string intentoId, LatidoDeTableta latido, string? alumnoId = null, CancellationToken ct = default) =>
        EnviarAsync<EstadoDeIntento>(Base + Intento(intentoId) + "latido/",
            Tableta(dispositivo, alumnoId, ("pregunta_actual", latido.PreguntaActual), ("transcurrido_ms", latido.TranscurridoMs), ("hora_tableta_ms", latido.HoraTabletaMs),
                    ("capacidad_control", latido.CapacidadControl), ("bateria_pct", latido.BateriaPct), ("espacio_libre_mb", latido.EspacioLibreMb)), ct);

    public Task<PreguntasDeIntento?> PreguntasAsync(string dispositivo, string intentoId, string? alumnoId = null, CancellationToken ct = default) =>
        ObtenerAsync<PreguntasDeIntento>(Ruta(Intento(intentoId) + "preguntas/", ("dispositivo", dispositivo), ("alumno_id", alumnoId)), ct);

    public Task<AcuseDeRespuestas?> EnviarRespuestasAsync(string dispositivo, string intentoId, IReadOnlyList<RespuestaDeExamen> respuestas, string origen = "directo",
                                                          string? preguntaActual = null, long? transcurridoMs = null, string? alumnoId = null, CancellationToken ct = default) =>
        EnviarAsync<AcuseDeRespuestas>(Base + Intento(intentoId) + "respuestas/",
            Tableta(dispositivo, alumnoId, ("respuestas", Lista(respuestas)), ("origen", origen), ("pregunta_actual", preguntaActual), ("transcurrido_ms", transcurridoMs)), ct);

    /// <summary>La respuesta del alumno viaja TAL CUAL (puede llevar nulos con sentido); sólo las horas de captura opcionales se omiten cuando faltan.</summary>
    private static List<Dictionary<string, object?>> Lista(IReadOnlyList<RespuestaDeExamen> respuestas) =>
        respuestas.Select(r =>
        {
            var item = new Dictionary<string, object?> { ["pregunta_ref"] = r.PreguntaRef, ["respuesta"] = r.Respuesta, ["secuencia"] = r.Secuencia };
            if (r.CapturadaEn is { } capturada) item["capturada_en"] = capturada;
            if (r.CapturadaEnTableta is { } tableta) item["capturada_en_tableta"] = tableta;
            return item;
        }).ToList();

    public Task<AcuseDeIncidentes?> EnviarIncidentesAsync(string dispositivo, string intentoId, IReadOnlyList<IncidenteDeTableta> incidentes, string? alumnoId = null, CancellationToken ct = default)
    {
        var lista = incidentes.Select(i =>
        {
            var item = new Dictionary<string, object?> { ["tipo"] = i.Tipo, ["ref_cliente"] = i.RefCliente };
            if (i.OcurridoEn is { } nodo) item["ocurrido_en"] = nodo;
            if (i.OcurridoEnTableta is { } tableta) item["ocurrido_en_tableta"] = tableta;
            if (i.Detalle is { Count: > 0 } detalle) item["detalle"] = detalle;
            return item;
        }).ToList();
        return EnviarAsync<AcuseDeIncidentes>(Base + Intento(intentoId) + "incidentes/", Tableta(dispositivo, alumnoId, ("incidentes", lista)), ct);
    }

    public Task<AcuseDeBloqueo?> InformarBloqueoAsync(string dispositivo, string intentoId, InformeDeBloqueo informe, string? alumnoId = null, CancellationToken ct = default) =>
        EnviarAsync<AcuseDeBloqueo>(Base + Intento(intentoId) + "bloqueo/",
            Tableta(dispositivo, alumnoId, ("resultado", informe.Resultado),
                    ("capas", new Dictionary<string, bool> { ["sistema"] = informe.Capas.Sistema, ["app"] = informe.Capas.App, ["capturas"] = informe.Capas.Capturas, ["pantallas"] = informe.Capas.Pantallas }),
                    ("motivo", string.IsNullOrWhiteSpace(informe.Motivo) ? null : informe.Motivo)), ct);

    public Task<EntregaDeIntento?> EntregarAsync(string dispositivo, string intentoId, bool confirmar, IReadOnlyList<RespuestaDeExamen>? respuestas = null,
                                                 long? transcurridoMs = null, string? alumnoId = null, CancellationToken ct = default) =>
        EnviarAsync<EntregaDeIntento>(Base + Intento(intentoId) + "entregar/",
            Tableta(dispositivo, alumnoId, ("confirmar", confirmar ? true : null), ("respuestas", respuestas is { Count: > 0 } ? Lista(respuestas) : null),
                    ("transcurrido_ms", transcurridoMs)), ct);

    public Task<ResultadoDeIntento?> ResultadoAsync(string dispositivo, string intentoId, string? alumnoId = null, CancellationToken ct = default) =>
        ObtenerAsync<ResultadoDeIntento>(Ruta(Intento(intentoId) + "resultado/", ("dispositivo", dispositivo), ("alumno_id", alumnoId)), ct);

    // ================================================================================================ profesor (OPS)

    public Task<ListaDeAsignaciones?> AsignacionesAsync(string actor, string? estado = null, string? grupoId = null, string? sesionId = null, CancellationToken ct = default) =>
        ObtenerAsync<ListaDeAsignaciones>(Ruta("asignaciones/", ("estado", estado), ("grupo_id", grupoId), ("sesion_id", sesionId), ("actor", actor)), ct);

    public Task<AsignacionDeExamen?> AsignacionAsync(string actor, string asignacionId, CancellationToken ct = default) =>
        ObtenerAsync<AsignacionDeExamen>(Ruta(Asig(asignacionId), ("actor", actor)), ct);

    public Task<AsignacionDeExamen?> CrearAsync(string actor, string? actorRotulo, NuevoExamen nuevo, CancellationToken ct = default)
    {
        var cuerpo = Docente(actor,
            ("actor_rotulo", actorRotulo), ("fuente", nuevo.Fuente), ("curso_ref", nuevo.CursoRef), ("objeto_ref", nuevo.ObjetoRef), ("alcance", "grupo"),
            ("grupo_id", nuevo.GrupoId), ("sesion_id", nuevo.SesionId), ("nivel_examen", nuevo.NivelExamen), ("tiempo", nuevo.Tiempo),
            ("abre_en", nuevo.AbreEn), ("limite_en", nuevo.LimiteEn), ("plazo", nuevo.Plazo), ("gracia_min", nuevo.GraciaMin),
            ("reactivacion", nuevo.Reactivacion), ("resultados", nuevo.Resultados), ("iniciar", nuevo.Iniciar));
        // Sin tope de intentos (TST-030) se dice con un nulo EXPLÍCITO: la clave ausente significa «uno» (BR-072).
        cuerpo["intentos_permitidos"] = nuevo.IntentosPermitidos;
        return EnviarAsync<AsignacionDeExamen>(Base + "asignaciones/", cuerpo, ct);
    }

    public Task<AsignacionDeExamen?> IniciarAsync(string actor, string asignacionId, CancellationToken ct = default) =>
        EnviarAsync<AsignacionDeExamen>(Base + Asig(asignacionId) + "iniciar/", Docente(actor), ct);

    public Task<AsignacionDeExamen?> CerrarAsync(string actor, string asignacionId, string? motivo = null, CancellationToken ct = default) =>
        EnviarAsync<AsignacionDeExamen>(Base + Asig(asignacionId) + "cerrar/", Docente(actor, ("motivo", motivo)), ct);

    public Task<AsignacionDeExamen?> ProrrogarAsync(string actor, string asignacionId, long limiteEn, CancellationToken ct = default) =>
        EnviarAsync<AsignacionDeExamen>(Base + Asig(asignacionId) + "prorrogar/", Docente(actor, ("limite_en", limiteEn)), ct);

    public Task<AsignacionDeExamen?> ReabrirAsync(string actor, string asignacionId, long? limiteEn = null, CancellationToken ct = default) =>
        EnviarAsync<AsignacionDeExamen>(Base + Asig(asignacionId) + "reabrir/", Docente(actor, ("limite_en", limiteEn)), ct);

    public Task<AsignacionDeExamen?> ConfigurarPlazoAsync(string actor, string asignacionId, long limiteEn, string? plazo = null, int? graciaMin = null, CancellationToken ct = default) =>
        ParchearAsync<AsignacionDeExamen>(Base + Asig(asignacionId) + "plazo/", Docente(actor, ("limite_en", limiteEn), ("plazo", plazo), ("gracia_min", graciaMin)), ct);

    public Task<AsignacionDeExamen?> EndurecerAsync(string actor, string asignacionId, long? limiteEn = null, CancellationToken ct = default) =>
        EnviarAsync<AsignacionDeExamen>(Base + Asig(asignacionId) + "endurecer/", Docente(actor, ("limite_en", limiteEn)), ct);

    public Task<AsignacionDeExamen?> DefinirNivelAsync(string actor, string asignacionId, string nivel, CancellationToken ct = default) =>
        EnviarAsync<AsignacionDeExamen>(Base + Asig(asignacionId) + "nivel/", Docente(actor, ("nivel_examen", nivel)), ct);

    public Task<AsignacionDeExamen?> DegradarAsync(string actor, string asignacionId, string nivel, string motivo, CancellationToken ct = default) =>
        EnviarAsync<AsignacionDeExamen>(Base + Asig(asignacionId) + "degradar/", Docente(actor, ("nivel_examen", nivel), ("motivo", motivo)), ct);

    public Task<AsignacionDeExamen?> LiberarResultadosAsync(string actor, string asignacionId, CancellationToken ct = default) =>
        EnviarAsync<AsignacionDeExamen>(Base + Asig(asignacionId) + "liberar-resultados/", Docente(actor), ct);

    public Task<PanelDeExamen?> PanelAsync(string actor, string asignacionId, CancellationToken ct = default) =>
        ObtenerAsync<PanelDeExamen>(Ruta(Asig(asignacionId) + "panel/", ("actor", actor)), ct);

    public Task<ElegibilidadDeTabletas?> ElegibilidadAsync(string actor, string asignacionId, string? nivel = null, CancellationToken ct = default) =>
        ObtenerAsync<ElegibilidadDeTabletas>(Ruta(Asig(asignacionId) + "elegibilidad/", ("nivel", nivel), ("actor", actor)), ct);

    public Task<ListaDeAdmisiones?> AdmisionesAsync(string actor, string asignacionId, bool todas = false, CancellationToken ct = default) =>
        ObtenerAsync<ListaDeAdmisiones>(Ruta(Asig(asignacionId) + "admisiones/", ("todas", todas ? "1" : null), ("actor", actor)), ct);

    public Task<AdmisionPendiente?> DecidirAdmisionAsync(string actor, string asignacionId, string admisionId, string decision, string? nivelAdmitido, string motivo, CancellationToken ct = default) =>
        EnviarAsync<AdmisionPendiente>(Base + Asig(asignacionId) + $"admisiones/{Esc(admisionId)}/decidir/",
            Docente(actor, ("decision", decision), ("nivel_admitido", nivelAdmitido), ("motivo", motivo)), ct);

    public Task<ReactivacionHecha?> ReactivarTodosAsync(string actor, string asignacionId, CancellationToken ct = default) =>
        EnviarAsync<ReactivacionHecha>(Base + Asig(asignacionId) + "reactivar/", Docente(actor), ct);

    public Task<ResultadosDeExamen?> ResultadosAsync(string actor, string asignacionId, CancellationToken ct = default) =>
        ObtenerAsync<ResultadosDeExamen>(Ruta(Asig(asignacionId) + "resultados/", ("actor", actor)), ct);

    public Task<ExpedienteDeIntento?> ExpedienteAsync(string actor, string intentoId, CancellationToken ct = default) =>
        ObtenerAsync<ExpedienteDeIntento>(Ruta(Intento(intentoId), ("actor", actor)), ct);

    public Task<RevisionDeIntento?> RevisionAsync(string actor, string intentoId, CancellationToken ct = default) =>
        ObtenerAsync<RevisionDeIntento>(Ruta(Intento(intentoId) + "revision/", ("actor", actor)), ct);

    public Task<ReactivacionHecha?> ReactivarAsync(string actor, string intentoId, string? desdePregunta = null, CancellationToken ct = default) =>
        EnviarAsync<ReactivacionHecha>(Base + Intento(intentoId) + "reactivar/", Docente(actor, ("desde_pregunta", desdePregunta)), ct);

    public Task<bool> CerrarIntentoAsync(string actor, string intentoId, CancellationToken ct = default) =>
        Hecho(Base + Intento(intentoId) + "cerrar/", Docente(actor), ct);

    public Task<bool> AnularAsync(string actor, string intentoId, string motivo, CancellationToken ct = default) =>
        Hecho(Base + Intento(intentoId) + "anular/", Docente(actor, ("motivo", motivo)), ct);

    public Task<PuntajeAsentado?> PuntuarAsync(string actor, string intentoId, string preguntaRef, double puntaje, string? comentario = null, string? motivo = null, CancellationToken ct = default) =>
        EnviarAsync<PuntajeAsentado>(Base + Intento(intentoId) + $"respuestas/{Esc(preguntaRef)}/puntuar/",
            Docente(actor, ("puntaje", puntaje), ("comentario", comentario), ("motivo", motivo)), ct);

    public Task<IntentoPublicado?> PublicarAsync(string actor, string intentoId, CancellationToken ct = default) =>
        EnviarAsync<IntentoPublicado>(Base + Intento(intentoId) + "publicar/", Docente(actor), ct);

    public Task<bool> DecidirEnvioAsync(string actor, string intentoId, string decision, string? motivo = null, CancellationToken ct = default) =>
        Hecho(Base + Intento(intentoId) + "decidir-envio/", Docente(actor, ("decision", decision), ("motivo", motivo)), ct);

    public Task<bool> RecalificarAsync(string actor, string intentoId, CancellationToken ct = default) =>
        Hecho(Base + Intento(intentoId) + "recalificar/", Docente(actor), ct);
}

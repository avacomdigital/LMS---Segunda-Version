using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>
/// Cliente de <c>/api/modo-estudio/</c> (MOD-008): las rutas de la §4 del contrato, una por método de <see cref="IEstudioApi"/>.
///
/// El aparato viaja como <c>dispositivo</c> en la consulta (GET, DELETE) o en el cuerpo (POST, PATCH); <c>alumno_id</c> sólo si el llamador lo da
/// (tableta compartida sin sesión, D-3); el profesor manda <c>actor</c> igual: en la consulta o en el cuerpo. Los campos opcionales que valen
/// null NO viajan (un serializador estricto del backend no distingue «ausente» de «nulo»); la única excepción es <c>fecha_limite: null</c>
/// al quitar la fecha de una asignación, que es precisamente lo que se quiere decir.
///
/// Un error HTTP o de red no es una excepción: devuelve null (o false) y deja el motivo en <see cref="ClienteJson.UltimoMotivo"/> y el
/// <c>codigo</c> del backend en <see cref="ClienteJson.UltimoError"/>, con el JSON completo del error en <see cref="ErrorAula.Extra"/>
/// (<c>descarga_denegada</c> trae ahí el <c>paquete</c> denegado y el mensaje MSG-046; <c>bloques_pendientes</c>, la lista <c>faltan</c>).
/// </summary>
public sealed class EstudioApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri), IEstudioApi
{
    private const string Base = "api/modo-estudio/";

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

    /// <summary>El cuerpo de una petición del alumno: el aparato, los campos que no son nulos y, si viene, <c>alumno_id</c>.</summary>
    private static Dictionary<string, object?> Cuerpo(string dispositivo, string? alumnoId, params (string Clave, object? Valor)[] campos)
    {
        var cuerpo = new Dictionary<string, object?> { ["dispositivo"] = dispositivo };
        foreach (var (clave, valor) in campos)
            if (valor is not null) cuerpo[clave] = valor;
        if (alumnoId is not null) cuerpo["alumno_id"] = alumnoId;
        return cuerpo;
    }

    /// <summary>El cuerpo de una petición del profesor: sus campos que no son nulos y el <c>actor</c>.</summary>
    private static Dictionary<string, object?> CuerpoDocente(string actor, params (string Clave, object? Valor)[] campos)
    {
        var cuerpo = new Dictionary<string, object?>();
        foreach (var (clave, valor) in campos)
            if (valor is not null) cuerpo[clave] = valor;
        cuerpo["actor"] = actor;
        return cuerpo;
    }

    // ---------------------------------------------------------------- estado y sesión de estudio

    public async Task<EstadoEstudio?> EstadoAsync(string dispositivo, string? alumnoId = null, CancellationToken ct = default)
    {
        // Es la pregunta del menú de Student: pase lo que pase en el camino (red, cancelación, un cuerpo raro), el menú no debe romperse.
        try { return await ObtenerAsync<EstadoEstudio>(Ruta("estado/", ("dispositivo", dispositivo), ("alumno_id", alumnoId)), ct); }
        catch { return null; }
    }

    public async Task<EstudiantesEstudio?> EstudiantesAsync(string dispositivo, CancellationToken ct = default)
    {
        // Igual que el estado: es lo primero que se pide al entrar, y la pantalla no debe romperse pase lo que pase en el camino.
        try { return await ObtenerAsync<EstudiantesEstudio>(Ruta("estudiantes/", ("dispositivo", dispositivo)), ct); }
        catch { return null; }
    }

    public Task<SesionEstudio?> AbrirSesionAsync(string dispositivo, string? nombre, string? plataforma, string? versionApp, string? alumnoId = null, CancellationToken ct = default) =>
        EnviarAsync<SesionEstudio>(Base + "sesion/", Cuerpo(dispositivo, alumnoId, ("nombre", nombre), ("plataforma", plataforma), ("version_app", versionApp)), ct);

    public async Task<bool> CerrarSesionAsync(string dispositivo, int colaPendiente, bool limpiezaCompleta, string? alumnoId = null, CancellationToken ct = default)
    {
        var respuesta = await EnviarAsync<JsonElement?>(Base + "sesion/cerrar/",
            Cuerpo(dispositivo, alumnoId, ("cola_pendiente", colaPendiente), ("limpieza", limpiezaCompleta ? "completa" : "pendiente")), ct);
        return Afirmativa(respuesta, "cerrada");
    }

    public async Task<bool> LimpiezaReintentadaAsync(string dispositivo, string resultado, CancellationToken ct = default) =>
        Afirmativa(await EnviarAsync<JsonElement?>(Base + "sesion/limpieza/", Cuerpo(dispositivo, null, ("resultado", resultado)), ct), "ok");

    /// <summary>Verdadero si el backend contestó 2xx y no negó expresamente la propiedad (<c>cerrada</c>, <c>ok</c>).</summary>
    private static bool Afirmativa(JsonElement? respuesta, string propiedad) =>
        respuesta is { } r && !(r.ValueKind == JsonValueKind.Object && r.TryGetProperty(propiedad, out var v) && v.ValueKind == JsonValueKind.False);

    // ---------------------------------------------------------------- pendientes y lección

    public Task<AsignacionesEstudio?> AsignacionesAsync(string dispositivo, string? alumnoId = null, CancellationToken ct = default) =>
        ObtenerAsync<AsignacionesEstudio>(Ruta("asignaciones/", ("dispositivo", dispositivo), ("alumno_id", alumnoId)), ct);

    public Task<AsignacionAlumno?> AsignacionAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default) =>
        ObtenerAsync<AsignacionAlumno>(Ruta($"asignaciones/{Esc(asignacionId)}/", ("dispositivo", dispositivo), ("alumno_id", alumnoId)), ct);

    public Task<LeccionEstudio?> LeccionAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default) =>
        ObtenerAsync<LeccionEstudio>(Ruta($"lecciones/{Esc(asignacionId)}/", ("dispositivo", dispositivo), ("alumno_id", alumnoId)), ct);

    public Task<ProgresoEstudio?> ProgresoAsync(string dispositivo, string asignacionId, IReadOnlyList<string> bloquesVistos, string? bloqueActual,
                                                int? posicionSeg, long? capturadoEn = null, string? alumnoId = null, CancellationToken ct = default) =>
        ParchearAsync<ProgresoEstudio>(Base + $"lecciones/{Esc(asignacionId)}/progreso/",
            Cuerpo(dispositivo, alumnoId, ("bloques_vistos", bloquesVistos is { Count: > 0 } ? bloquesVistos : null), ("bloque_actual", bloqueActual),
                   ("posicion_seg", posicionSeg), ("capturado_en", capturadoEn)), ct);

    public Task<CompletadaEstudio?> CompletarAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default) =>
        EnviarAsync<CompletadaEstudio>(Base + $"lecciones/{Esc(asignacionId)}/completar/", Cuerpo(dispositivo, alumnoId), ct);

    // ------------------------------------------------------------------------ práctica

    public Task<PracticaAbierta?> PracticaAsync(string dispositivo, string asignacionId, string? objetoRef = null, bool nueva = false, string? alumnoId = null, CancellationToken ct = default) =>
        EnviarAsync<PracticaAbierta>(Base + $"lecciones/{Esc(asignacionId)}/practica/",
            Cuerpo(dispositivo, alumnoId, ("objeto_ref", objetoRef), ("nueva", nueva ? true : null)), ct);

    public Task<AcusePractica?> ResponderAsync(string dispositivo, string practicaId, IReadOnlyList<RespuestaPractica> respuestas, bool terminar = false,
                                               string? alumnoId = null, CancellationToken ct = default)
    {
        // La respuesta del alumno viaja tal cual (puede llevar nulos con sentido); sólo la hora de captura opcional se omite cuando falta.
        var lista = respuestas.Select(r =>
        {
            var item = new Dictionary<string, object?> { ["pregunta_ref"] = r.PreguntaRef, ["respuesta"] = r.Respuesta, ["secuencia"] = r.Secuencia };
            if (r.CapturadaEn is { } capturada) item["capturada_en"] = capturada;
            return item;
        }).ToList();
        return EnviarAsync<AcusePractica>(Base + $"practicas/{Esc(practicaId)}/respuestas/",
            Cuerpo(dispositivo, alumnoId, ("respuestas", lista), ("terminar", terminar ? true : null)), ct);
    }

    public async Task<AcusePractica?> TerminarPracticaAsync(string dispositivo, string practicaId, string? alumnoId = null, CancellationToken ct = default)
    {
        // El contrato dice sólo «{practica, resultado}»: se lee con tolerancia (la práctica puede llegar resumida o completa) en vez de
        // fallar entero por un campo cuya forma no está fijada.
        var crudo = await EnviarAsync<JsonElement?>(Base + $"practicas/{Esc(practicaId)}/terminar/", Cuerpo(dispositivo, alumnoId), ct);
        return crudo is { ValueKind: JsonValueKind.Object } raiz ? AcuseDeTerminar(raiz) : null;
    }

    private static AcusePractica AcuseDeTerminar(JsonElement raiz)
    {
        ResultadoPractica? resultado = null;
        if (raiz.TryGetProperty("resultado", out var r) && r.ValueKind == JsonValueKind.Object) resultado = Leer<ResultadoPractica>(r);
        ResumenPractica? practica = null;
        if (raiz.TryGetProperty("practica", out var p) && p.ValueKind == JsonValueKind.Object)
            practica = new ResumenPractica(Cadena(p, "id") ?? "", Cadena(p, "estado") ?? "", Entero(p, "respondidas"), Entero(p, "aciertos"),
                                           Entero(p, "total_preguntas"), Entero(p, "sin_calificar"));
        var acuse = !(raiz.TryGetProperty("acuse", out var a) && a.ValueKind == JsonValueKind.False);
        var servidorEn = raiz.TryGetProperty("servidor_en", out var s) && s.ValueKind == JsonValueKind.Number && s.TryGetInt64(out var ms) ? ms : 0;
        return new AcusePractica(acuse, null, null, null, null, null, practica, resultado, servidorEn);
    }

    private static T? Leer<T>(JsonElement elemento)
    {
        try { return elemento.Deserialize<T>(Json); }
        catch (JsonException) { return default; }
    }

    private static string? Cadena(JsonElement objeto, string propiedad) =>
        objeto.TryGetProperty(propiedad, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;

    /// <summary>Un entero de la respuesta; si el campo es una colección (p. ej. <c>respondidas</c> como diccionario) cuenta sus elementos.</summary>
    private static int Entero(JsonElement objeto, string propiedad) =>
        !objeto.TryGetProperty(propiedad, out var v) ? 0 : v.ValueKind switch
        {
            JsonValueKind.Number => v.TryGetInt32(out var n) ? n : 0,
            JsonValueKind.Object => v.EnumerateObject().Count(),
            JsonValueKind.Array => v.GetArrayLength(),
            _ => 0,
        };

    // ------------------------------------------------------------------------- paquete

    public async Task<PaqueteEstudio?> SolicitarPaqueteAsync(string dispositivo, string asignacionId, string? alumnoId = null, CancellationToken ct = default) =>
        DesenvolverPaquete(await EnviarAsync<JsonElement?>(Base + "paquetes/", Cuerpo(dispositivo, alumnoId, ("asignacion_id", asignacionId)), ct));

    public Task<ListaPaquetes?> PaquetesAsync(string dispositivo, string? alumnoId = null, CancellationToken ct = default) =>
        ObtenerAsync<ListaPaquetes>(Ruta("paquetes/", ("dispositivo", dispositivo), ("alumno_id", alumnoId)), ct);

    public async Task<PaqueteEstudio?> PaqueteAsync(string dispositivo, string paqueteId, string? alumnoId = null, CancellationToken ct = default) =>
        DesenvolverPaquete(await ObtenerAsync<JsonElement?>(Ruta($"paquetes/{Esc(paqueteId)}/", ("dispositivo", dispositivo), ("alumno_id", alumnoId)), ct));

    public Task<ManifiestoPaquete?> ManifiestoAsync(string dispositivo, string paqueteId, string? alumnoId = null, CancellationToken ct = default) =>
        ObtenerAsync<ManifiestoPaquete>(Ruta($"paquetes/{Esc(paqueteId)}/manifiesto/", ("dispositivo", dispositivo), ("alumno_id", alumnoId)), ct);

    public Task<string?> ManifiestoCrudoAsync(string dispositivo, string paqueteId, string? alumnoId = null, CancellationToken ct = default) =>
        ObtenerTextoAsync(Ruta($"paquetes/{Esc(paqueteId)}/manifiesto/", ("dispositivo", dispositivo), ("alumno_id", alumnoId)), ct);

    public Task<HttpResponseMessage?> ArchivoAsync(string dispositivo, string paqueteId, string mediaRef, long? desdeByte = null, string? alumnoId = null, CancellationToken ct = default) =>
        ObtenerRespuestaAsync(Ruta($"paquetes/{Esc(paqueteId)}/archivos/{Esc(mediaRef)}/", ("dispositivo", dispositivo), ("alumno_id", alumnoId)),
            desdeByte is >= 0 and var desde ? cabeceras => cabeceras.Range = new RangeHeaderValue(desde, null) : null, ct);

    public async Task<PaqueteEstudio?> ConfirmarPaqueteAsync(string dispositivo, string paqueteId, string huella, long bytes, string? alumnoId = null, CancellationToken ct = default) =>
        DesenvolverPaquete(await EnviarAsync<JsonElement?>(Base + $"paquetes/{Esc(paqueteId)}/confirmar/",
            Cuerpo(dispositivo, alumnoId, ("huella", huella), ("bytes", bytes)), ct));

    public Task<bool> RetirarPaqueteAsync(string dispositivo, string paqueteId, string? alumnoId = null, CancellationToken ct = default) =>
        EliminarAsync(Ruta($"paquetes/{Esc(paqueteId)}/", ("dispositivo", dispositivo), ("alumno_id", alumnoId)), ct);

    /// <summary>
    /// El contrato escribe a veces «{paquete}» y a veces «paquete»: se acepta el objeto envuelto (<c>{"paquete":{…}}</c>) o suelto. Si el
    /// <c>servidor_en</c> viene en el sobre y no dentro del paquete, se le pasa al paquete.
    /// </summary>
    private static PaqueteEstudio? DesenvolverPaquete(JsonElement? crudo)
    {
        if (crudo is not { ValueKind: JsonValueKind.Object } raiz) return null;
        var cuerpo = raiz.TryGetProperty("paquete", out var interno) && interno.ValueKind == JsonValueKind.Object ? interno : raiz;
        var paquete = Leer<PaqueteEstudio>(cuerpo);
        if (paquete is { ServidorEn: 0 } && raiz.TryGetProperty("servidor_en", out var s) && s.ValueKind == JsonValueKind.Number && s.TryGetInt64(out var ms))
            paquete = paquete with { ServidorEn = ms };
        return paquete;
    }

    // ---------------------------------------------------------------------- trabajo sin red

    public Task<AcuseSync?> SincronizarAsync(string dispositivo, string emisorId, IReadOnlyList<EventoEstudio> eventos, string? alumnoId = null, CancellationToken ct = default)
    {
        var lista = eventos.Select(e =>
        {
            var item = new Dictionary<string, object?> { ["secuencia"] = e.Secuencia, ["tipo"] = e.Tipo, ["ocurrido_en"] = e.OcurridoEn, ["carga"] = e.Carga };
            if (e.OcurridoEnTableta is { } tableta) item["ocurrido_en_tableta"] = tableta;
            return item;
        }).ToList();
        return EnviarAsync<AcuseSync>(Base + "sync/", Cuerpo(dispositivo, alumnoId, ("emisor_id", emisorId), ("eventos", lista)), ct);
    }

    public Task<EstadoSync?> EstadoSyncAsync(string dispositivo, string emisorId, CancellationToken ct = default) =>
        ObtenerAsync<EstadoSync>(Ruta("sync/status/", ("dispositivo", dispositivo), ("emisor_id", emisorId)), ct);

    // -------------------------------------------------------------------- profesor · OPS

    public Task<GruposDocente?> GruposAsync(string actor, CancellationToken ct = default) =>
        ObtenerAsync<GruposDocente>(Ruta("docente/grupos/", ("actor", actor)), ct);

    public Task<ListaAsignacionesDocente?> AsignacionesDocenteAsync(string actor, string? grupoId = null, string? estado = null, CancellationToken ct = default) =>
        ObtenerAsync<ListaAsignacionesDocente>(Ruta("docente/asignaciones/", ("grupo_id", grupoId), ("estado", estado), ("actor", actor)), ct);

    public Task<AsignacionDocente?> CrearAsignacionAsync(string actor, string? actorRotulo, NuevaAsignacion nueva, CancellationToken ct = default) =>
        EnviarAsync<AsignacionDocente>(Base + "docente/asignaciones/", CuerpoDocente(actor,
            ("actor_rotulo", actorRotulo), ("alcance", nueva.Alcance), ("grupo_id", nueva.GrupoId), ("alumnos", nueva.Alumnos), ("curso_ref", nueva.CursoRef),
            ("fuente", nueva.Fuente), ("leccion_ref", nueva.LeccionRef), ("titulo", nueva.Titulo), ("consigna", nueva.Consigna),
            ("fecha_limite", nueva.FechaLimite), ("plazo", nueva.Plazo), ("gracia_min", nueva.GraciaMin), ("paquete_permitido", nueva.PaquetePermitido)), ct);

    public Task<AsignacionDocente?> AsignacionDocenteAsync(string actor, string asignacionId, CancellationToken ct = default) =>
        ObtenerAsync<AsignacionDocente>(Ruta($"docente/asignaciones/{Esc(asignacionId)}/", ("actor", actor)), ct);

    public Task<AsignacionDocente?> CambiarAsignacionAsync(string actor, string asignacionId, CambiosAsignacion cambios, CancellationToken ct = default)
    {
        var cuerpo = CuerpoDocente(actor, ("plazo", cambios.Plazo), ("gracia_min", cambios.GraciaMin), ("titulo", cambios.Titulo),
                                   ("consigna", cambios.Consigna), ("paquete_permitido", cambios.PaquetePermitido));
        // Quitar la fecha es lo único que se dice con un nulo explícito.
        if (cambios.QuitarFecha) cuerpo["fecha_limite"] = null;
        else if (cambios.FechaLimite is { } fecha) cuerpo["fecha_limite"] = fecha;
        return ParchearAsync<AsignacionDocente>(Base + $"docente/asignaciones/{Esc(asignacionId)}/", cuerpo, ct);
    }

    public Task<AsignacionDocente?> CerrarAsignacionAsync(string actor, string asignacionId, CancellationToken ct = default) =>
        EnviarAsync<AsignacionDocente>(Base + $"docente/asignaciones/{Esc(asignacionId)}/cerrar/", CuerpoDocente(actor), ct);

    public async Task<bool> DecidirAsync(string actor, string asignacionId, string alumnoId, long secuencia, string? emisorId, string decision, CancellationToken ct = default) =>
        await EnviarAsync<JsonElement?>(Base + $"docente/asignaciones/{Esc(asignacionId)}/decisiones/",
            CuerpoDocente(actor, ("alumno_id", alumnoId), ("secuencia", secuencia), ("emisor_id", emisorId), ("decision", decision)), ct) is not null;
}

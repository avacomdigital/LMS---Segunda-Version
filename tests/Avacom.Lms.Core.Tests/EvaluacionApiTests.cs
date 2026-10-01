using System.Net;
using System.Text.Json;
using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// El cliente de <c>/api/evaluacion/</c> contra un nodo falso: método, URL y cuerpo de cada ruta del contrato (backend.md §4) — los campos nulos NO viajan,
/// el aparato va en la consulta (GET) o en el cuerpo (POST), el profesor manda <c>actor</c> — y los errores con su código y sus extras.
/// </summary>
[Collection("estado global")]
public sealed class EvaluacionApiTests : IDisposable
{
    private const string Base = "/api/evaluacion/";
    private const string Tab = "student-TAB07";

    public EvaluacionApiTests() => ClienteJson.Token = null;
    public void Dispose() => ClienteJson.Token = null;

    private sealed record Captura(HttpMethod Metodo, string Url, string? Cuerpo, string? Autorizacion)
    {
        public JsonElement Json => Ayudas.Json(Cuerpo!);
        public string[] Claves => Json.EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal).ToArray();
    }

    private static (EvaluacionApi Api, List<Captura> Capturas) Api(Func<Captura, HttpResponseMessage> responder)
    {
        var capturas = new List<Captura>();
        var http = new HttpClient(new ManejadorFalso(async (req, _) =>
        {
            var cuerpo = req.Content is null ? null : await req.Content.ReadAsStringAsync();
            var captura = new Captura(req.Method, req.RequestUri!.PathAndQuery, cuerpo, req.Headers.Authorization?.ToString());
            capturas.Add(captura);
            return responder(captura);
        }));
        return (new EvaluacionApi(http, new Uri("http://192.168.0.55:8000/")), capturas);
    }

    private static (EvaluacionApi Api, List<Captura> Capturas) Api(HttpStatusCode estado = HttpStatusCode.OK, string json = "{}") => Api(_ => Ayudas.Respuesta(estado, json));

    private const string IntentoJson = """{"id":"i-1","estado":"en_curso","numero":1}""";

    // ---------------------------------------------------------------------------------------- la tableta

    [Fact]
    public async Task Estudiantes_EsUnGetSinParametros_ElQuienEresDeLaEvaluacion()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"disponible":true,"motivo":"","grupos":[{"id":"g-1","nombre":"Octavo A","alumnos":[{"id":"a-1","rotulo":"Ana"}]}]}""");
        var r = await api.EstudiantesAsync();
        Assert.Equal("Ana", r!.Grupos.Single().Alumnos.Single().Rotulo);
        Assert.Equal((HttpMethod.Get, Base + "estudiantes/"), (capturas.Single().Metodo, capturas.Single().Url));
    }

    [Fact]
    public async Task Mias_EsUnGetConElAparatoYLaOpcionTodas_SinCamposVacios()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"pendientes":[],"recientes":[],"servidor_en":1}""");
        var r = await api.MisAsync(Tab);
        Assert.NotNull(r);
        await api.MisAsync(Tab, "ana", todas: true);
        Assert.Equal(Base + "mias/?dispositivo=student-TAB07", capturas[0].Url);
        Assert.Equal(Base + "mias/?dispositivo=student-TAB07&alumno_id=ana&todas=1", capturas[1].Url);
        Assert.All(capturas, c => Assert.Equal(HttpMethod.Get, c.Metodo));
    }

    [Fact]
    public async Task Abrir_LaTabletaSeCuentaYDeclaraSuCapacidad_LoNuloNoViaja()
    {
        var (api, capturas) = Api(HttpStatusCode.Created, $$"""{"intento":{{IntentoJson}},"preguntas_total":4,"espera_reactivacion":false,"reanudado":false}""");
        var r = await api.AbrirAsync(Tab, "a/1", new DatosDeTableta("Tableta 07", "android", "0.4.2", Niveles.Controlado));
        Assert.Equal("i-1", r!.Intento.Id);
        var c = capturas.Single();
        Assert.Equal((HttpMethod.Post, Base + "asignaciones/a%2F1/intentos/"), (c.Metodo, c.Url));   // el id viaja escapado
        Assert.Equal(new[] { "capacidad_control", "dispositivo", "nombre", "plataforma", "version_app" }, c.Claves);
        Assert.Equal("controlado", c.Json.GetProperty("capacidad_control").GetString());

        capturas.Clear();
        await api.AbrirAsync(Tab, "a-1");
        Assert.Equal(new[] { "dispositivo" }, capturas.Single().Claves);
        capturas.Clear();
        await api.AbrirAsync(Tab, "a-1", alumnoId: "ana");
        Assert.Equal(new[] { "alumno_id", "dispositivo" }, capturas.Single().Claves);
    }

    [Fact]
    public async Task Latido_LlevaPorDondeVaYLoQueDeclara_ElNodoDecideElTiempo()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, $$"""{"intento":{{IntentoJson}},"espera_reactivacion":false}""");
        var e = await api.LatirAsync(Tab, "i-1", new LatidoDeTableta("q3", 12_000, 1_790_000_000_000, Niveles.Supervisado, 80, 2048));
        Assert.Equal(EstadosIntento.EnCurso, e!.Intento.Estado);
        var c = capturas.Single();
        Assert.Equal((HttpMethod.Post, Base + "intentos/i-1/latido/"), (c.Metodo, c.Url));
        Assert.Equal(new[] { "bateria_pct", "capacidad_control", "dispositivo", "espacio_libre_mb", "hora_tableta_ms", "pregunta_actual", "transcurrido_ms" }, c.Claves);
        capturas.Clear();
        await api.LatirAsync(Tab, "i-1", new LatidoDeTableta());
        Assert.Equal(new[] { "dispositivo" }, capturas.Single().Claves);
    }

    [Fact]
    public async Task Respuestas_VanConSuSecuencia_LaRespuestaTalCual_YElOrigen()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"acuse":true,"aceptadas":["q1"],"duplicadas":[],"superadas":[],"rechazadas":[]}""");
        var respuestas = new[]
        {
            new RespuestaDeExamen("q1", 3, Ayudas.Json("""{"selectedOptionIds":["a","c"]}"""), 1_790_000_001_000, 1_790_000_000_950),
            new RespuestaDeExamen("q2", 4, Ayudas.Json("""{"text":null}""")),
        };
        var acuse = await api.EnviarRespuestasAsync(Tab, "i-1", respuestas, "cola", "q2", 187_000);
        Assert.True(acuse!.Acuse);
        var c = capturas.Single();
        Assert.Equal((HttpMethod.Post, Base + "intentos/i-1/respuestas/"), (c.Metodo, c.Url));
        Assert.Equal(new[] { "dispositivo", "origen", "pregunta_actual", "respuestas", "transcurrido_ms" }, c.Claves);
        var lista = c.Json.GetProperty("respuestas");
        Assert.Equal(new[] { "capturada_en", "capturada_en_tableta", "pregunta_ref", "respuesta", "secuencia" },
                     lista[0].EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal));
        Assert.Equal(new[] { "pregunta_ref", "respuesta", "secuencia" }, lista[1].EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal));
        Assert.Equal("a", lista[0].GetProperty("respuesta").GetProperty("selectedOptionIds")[0].GetString());
        Assert.Equal(JsonValueKind.Null, lista[1].GetProperty("respuesta").GetProperty("text").ValueKind);   // lo que el alumno mandó va tal cual, nulo incluido
        Assert.Equal(3, lista[0].GetProperty("secuencia").GetInt32());
    }

    [Fact]
    public async Task Incidentes_LlevanSuRefCliente_YElDetalleSoloSiLoHay()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"registrados":2,"duplicados":0,"estado":"en_curso"}""");
        var r = await api.EnviarIncidentesAsync(Tab, "i-1",
        [
            new IncidenteDeTableta("salida_de_app", "dev1-17", 1_790_000_100_020, 1_790_000_099_900, new() { ["segundos"] = 4 }),
            new IncidenteDeTableta("regreso_a_app", "dev1-18"),
        ]);
        Assert.Equal(2, r!.Registrados);
        var lista = capturas.Single().Json.GetProperty("incidentes");
        Assert.Equal(new[] { "detalle", "ocurrido_en", "ocurrido_en_tableta", "ref_cliente", "tipo" }, lista[0].EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal));
        Assert.Equal(new[] { "ref_cliente", "tipo" }, lista[1].EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal));
        Assert.Equal(4, lista[0].GetProperty("detalle").GetProperty("segundos").GetInt32());
    }

    [Fact]
    public async Task Bloqueo_InformaLasCuatroCapasQueLogro_YElMotivo()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"plan_bloqueo":null,"incidente":"bloqueo_parcial"}""");
        var r = await api.InformarBloqueoAsync(Tab, "i-1", new InformeDeBloqueo(ResultadosDeBloqueo.Parcial, new CapasDeBloqueo(false, true, true, false), "No es Device Owner"));
        Assert.Equal("bloqueo_parcial", r!.Incidente);
        var c = capturas.Single();
        Assert.Equal(Base + "intentos/i-1/bloqueo/", c.Url);
        var cuerpo = c.Json;
        Assert.Equal("parcial", cuerpo.GetProperty("resultado").GetString());
        var capas = cuerpo.GetProperty("capas");
        Assert.Equal((false, true, true, false), (capas.GetProperty("sistema").GetBoolean(), capas.GetProperty("app").GetBoolean(),
                                                  capas.GetProperty("capturas").GetBoolean(), capas.GetProperty("pantallas").GetBoolean()));
        Assert.Equal("No es Device Owner", cuerpo.GetProperty("motivo").GetString());
    }

    [Fact]
    public async Task Entregar_ConfirmarSoloViajaSiEsVerdadero_YLasRespuestasSoloSiLasHay()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"intento":{"id":"i-1","estado":"entregado","numero":1},"entregado_en":5,"origen_entrega":"alumno","que_sigue":{"codigo":"resultado_al_liberar","texto":"x"}}""");
        await api.EntregarAsync(Tab, "i-1", confirmar: false);
        await api.EntregarAsync(Tab, "i-1", confirmar: true, [new RespuestaDeExamen("q4", 9, Ayudas.Json("""{"order":["a"]}"""))], 612_000);
        Assert.Equal(new[] { "dispositivo" }, capturas[0].Claves);
        Assert.Equal(new[] { "confirmar", "dispositivo", "respuestas", "transcurrido_ms" }, capturas[1].Claves);
        Assert.Equal(Base + "intentos/i-1/entregar/", capturas[1].Url);
    }

    [Fact]
    public async Task PreguntasEstadoResultadoYAntesala_SonGets()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"intento_id":"i-1","navegacion_atras":true,"preguntas":[],"respondidas":{}}""");
        await api.PreguntasAsync(Tab, "i-1");
        await api.EstadoAsync(Tab, "i-1", "ana");
        await api.ResultadoAsync(Tab, "i-1");
        await api.AntesalaAsync(Tab, "a-1");
        Assert.Equal(new[]
        {
            Base + "intentos/i-1/preguntas/?dispositivo=student-TAB07",
            Base + "intentos/i-1/estado/?dispositivo=student-TAB07&alumno_id=ana",
            Base + "intentos/i-1/resultado/?dispositivo=student-TAB07",
            Base + "asignaciones/a-1/antesala/?dispositivo=student-TAB07",
        }, capturas.Select(c => c.Url));
    }

    // ------------------------------------------------------------------------------------------ el profesor

    [Fact]
    public async Task Crear_NivelObligatorio_TiempoComoObjeto_YIntentosIlimitadosSeDiceConUnNuloExplicito()
    {
        var (api, capturas) = Api(HttpStatusCode.Created, """{"id":"a-1","titulo":"x","estado":"activa","nivel_examen":"controlado"}""");
        var nuevo = new NuevoExamen("biblioteca", "curso-1", "l3-exam", Niveles.Controlado, "g-1", "s-1", TiempoDeExamen.Fijo(600), IntentosPermitidos: 2, LimiteEn: 1_790_000_600_000);
        var r = await api.CrearAsync("prof-1", "Prof. Gómez", nuevo);
        Assert.Equal("a-1", r!.Id);
        var c = capturas.Single();
        Assert.Equal((HttpMethod.Post, Base + "asignaciones/"), (c.Metodo, c.Url));
        var cuerpo = c.Json;
        Assert.Equal("controlado", cuerpo.GetProperty("nivel_examen").GetString());
        Assert.Equal(("grupo", "g-1", "s-1", "prof-1", "Prof. Gómez"), (cuerpo.GetProperty("alcance").GetString(), cuerpo.GetProperty("grupo_id").GetString(),
                     cuerpo.GetProperty("sesion_id").GetString(), cuerpo.GetProperty("actor").GetString(), cuerpo.GetProperty("actor_rotulo").GetString()));
        Assert.Equal(("fijo", 600), (cuerpo.GetProperty("tiempo").GetProperty("modo").GetString(), cuerpo.GetProperty("tiempo").GetProperty("limite_seg").GetInt32()));
        Assert.Equal(2, cuerpo.GetProperty("intentos_permitidos").GetInt32());
        Assert.False(cuerpo.TryGetProperty("abre_en", out _));               // lo nulo no viaja
        Assert.True(cuerpo.GetProperty("iniciar").GetBoolean());

        capturas.Clear();
        await api.CrearAsync("prof-1", null, nuevo with { IntentosPermitidos = null, Tiempo = null });
        var sinTope = capturas.Single().Json;
        Assert.Equal(JsonValueKind.Null, sinTope.GetProperty("intentos_permitidos").ValueKind);   // TST-030: sin tope = nulo EXPLÍCITO (la clave ausente significa uno)
        Assert.False(sinTope.TryGetProperty("tiempo", out _));
        Assert.False(sinTope.TryGetProperty("actor_rotulo", out _));
    }

    [Fact]
    public async Task AccionesSobreLaAsignacion_RutaMetodoYCuerpo()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"id":"a-1","titulo":"x","estado":"activa","nivel_examen":"supervisado"}""");
        await api.IniciarAsync("p", "a-1");
        await api.CerrarAsync("p", "a-1", "Sonó el timbre");
        await api.ProrrogarAsync("p", "a-1", 100);
        await api.ReabrirAsync("p", "a-1");
        await api.ConfigurarPlazoAsync("p", "a-1", 200, "blando", 5);
        await api.EndurecerAsync("p", "a-1", 300);
        await api.DefinirNivelAsync("p", "a-1", Niveles.Supervisado);
        await api.DegradarAsync("p", "a-1", Niveles.Abierto, "Fallas de red");
        await api.LiberarResultadosAsync("p", "a-1");
        await api.ReactivarTodosAsync("p", "a-1");
        Assert.Equal(new[]
        {
            "POST iniciar/", "POST cerrar/", "POST prorrogar/", "POST reabrir/", "PATCH plazo/", "POST endurecer/", "POST nivel/", "POST degradar/",
            "POST liberar-resultados/", "POST reactivar/",
        }, capturas.Select(c => $"{c.Metodo} {c.Url[(Base + "asignaciones/a-1/").Length..]}"));
        Assert.All(capturas, c => Assert.Equal("p", c.Json.GetProperty("actor").GetString()));
        Assert.Equal("Sonó el timbre", capturas[1].Json.GetProperty("motivo").GetString());
        Assert.Equal(("abierto", "Fallas de red"), (capturas[7].Json.GetProperty("nivel_examen").GetString(), capturas[7].Json.GetProperty("motivo").GetString()));
        Assert.Equal(new[] { "actor" }, capturas[3].Claves);                  // reabrir sin plazo nuevo: sólo el actor
    }

    [Fact]
    public async Task LecturasDelProfesor_LlevanElActorEnLaConsulta()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"asignaciones":[],"filas":[],"admisiones":[]}""");
        await api.AsignacionesAsync("p", "activa", "g-1", "s-1");
        await api.PanelAsync("p", "a-1");
        await api.ElegibilidadAsync("p", "a-1", Niveles.Controlado);
        await api.AdmisionesAsync("p", "a-1", todas: true);
        await api.ResultadosAsync("p", "a-1");
        await api.ContarSuspendidosAsync("p", "a-1");
        await api.ExpedienteAsync("p", "i-1");
        await api.RevisionAsync("p", "i-1");
        Assert.Equal(new[]
        {
            Base + "asignaciones/?estado=activa&grupo_id=g-1&sesion_id=s-1&actor=p",
            Base + "asignaciones/a-1/panel/?actor=p",
            Base + "asignaciones/a-1/elegibilidad/?nivel=controlado&actor=p",
            Base + "asignaciones/a-1/admisiones/?todas=1&actor=p",
            Base + "asignaciones/a-1/resultados/?actor=p",
            Base + "asignaciones/a-1/reactivar/?actor=p",
            Base + "intentos/i-1/?actor=p",
            Base + "intentos/i-1/revision/?actor=p",
        }, capturas.Select(c => c.Url));
    }

    [Fact]
    public async Task AccionesSobreElIntento_Y_DecidirLaAdmision()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"id":"adm-1","estado":"admitido","nivel_exigido":"controlado","nivel_alcanzado":"supervisado","alumno_id":"ana"}""");
        await api.DecidirAdmisionAsync("p", "a-1", "adm-1", "admitir", Niveles.Supervisado, "La tableta aún no está aprovisionada");
        await api.ReactivarAsync("p", "i-1", "q9");
        await api.CerrarIntentoAsync("p", "i-1");
        Assert.True(await api.AnularAsync("p", "i-1", "Se detectó otro dispositivo"));
        await api.PuntuarAsync("p", "i-1", "q5", 0.5, "Casi", "Corrección");
        await api.PublicarAsync("p", "i-1");
        Assert.True(await api.DecidirEnvioAsync("p", "i-1", "aceptar", "Se le cayó la red"));
        Assert.True(await api.RecalificarAsync("p", "i-1"));
        Assert.Equal(new[]
        {
            Base + "asignaciones/a-1/admisiones/adm-1/decidir/", Base + "intentos/i-1/reactivar/", Base + "intentos/i-1/cerrar/", Base + "intentos/i-1/anular/",
            Base + "intentos/i-1/respuestas/q5/puntuar/", Base + "intentos/i-1/publicar/", Base + "intentos/i-1/decidir-envio/", Base + "intentos/i-1/recalificar/",
        }, capturas.Select(c => c.Url));
        Assert.Equal(new[] { "actor", "decision", "motivo", "nivel_admitido" }, capturas[0].Claves);
        Assert.Equal(new[] { "actor", "motivo" }, capturas[3].Claves);
        Assert.Equal(new[] { "actor", "comentario", "motivo", "puntaje" }, capturas[4].Claves);
    }

    // ------------------------------------------------------------------------------------------- los errores

    [Fact]
    public async Task UnErrorNoEsUnaExcepcion_DejaElCodigoElMotivoYLosExtras()
    {
        var (api, _) = Api(HttpStatusCode.Conflict, """{"detail":"Te faltan 2 pregunta(s)","codigo":"confirmacion_requerida","faltan":["q1","q2"]}""");
        Assert.Null(await api.EntregarAsync(Tab, "i-1", confirmar: false));
        Assert.Equal(("confirmacion_requerida", 409, "Te faltan 2 pregunta(s)"), (api.UltimoError!.Codigo, api.UltimoError.Estado, api.UltimoMotivo));
        Assert.Equal(2, api.UltimoError.Extra!.Value.GetProperty("faltan").GetArrayLength());
    }

    [Fact]
    public async Task SinRed_DevuelveNull_Estado0_YNoLanza()
    {
        var http = new HttpClient(new ManejadorFalso((_, _) => throw new HttpRequestException("sin red")));
        var api = new EvaluacionApi(http, new Uri("http://192.168.0.55:8000/"));
        Assert.Null(await api.LatirAsync(Tab, "i-1", new LatidoDeTableta()));
        Assert.Equal((0, "sin_conexion"), (api.UltimoError!.Estado, api.UltimoError.Codigo));
        Assert.False(await api.AnularAsync("p", "i-1", "motivo"));
    }

    [Fact]
    public async Task ElResultadoAntesDeLiberarse_Es403ConSuCodigo()
    {
        var (api, _) = Api(HttpStatusCode.Forbidden, """{"detail":"El profesor aún no libera los resultados.","codigo":"resultados_no_liberados"}""");
        Assert.Null(await api.ResultadoAsync(Tab, "i-1"));
        Assert.Equal("resultados_no_liberados", api.UltimoError!.Codigo);
    }

    [Fact]
    public async Task ConSesion_ElJwtViajaEnCadaPeticion()
    {
        ClienteJson.Token = "jwt-del-profesor";
        var (api, capturas) = Api(HttpStatusCode.OK, """{"filas":[]}""");
        await api.PanelAsync("p", "a-1");
        Assert.Equal("Bearer jwt-del-profesor", capturas.Single().Autorizacion);
    }
}

using System.Net;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>Lo estático del proceso (reloj del nodo y pase de sesión) se toca en estas pruebas: no corren en paralelo con otras que lo toquen.</summary>
[CollectionDefinition("estado global", DisableParallelization = true)]
public sealed class EstadoGlobalCollection;

internal static class Ayudas
{
    public static readonly JsonSerializerOptions Web = new(JsonSerializerDefaults.Web);

    public static HttpResponseMessage Respuesta(HttpStatusCode estado, string json) =>
        new(estado) { Content = new StringContent(json, Encoding.UTF8, "application/json") };

    public static string CarpetaTemporal()
    {
        var ruta = Path.Combine(Path.GetTempPath(), "avacom-tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(ruta);
        return ruta;
    }

    public static JsonElement Json(string texto) => JsonDocument.Parse(texto).RootElement.Clone();
}

internal sealed class ManejadorFalso(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> responder) : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => responder(request, cancellationToken);
}

// ================================================================================ mensajes

public sealed class MensajeAulaTests
{
    [Fact]
    public void Hola_DelProfesor_TraeElConteoQuePintaElRecuadroVerde()
    {
        var m = JsonSerializer.Deserialize<MensajeAula>("""
            {"tipo":"hola","rol":"docente","sesion":{"id":"s1","estado":"abierta"},"servidor_en":1000,"latido_ms":5000,"respaldo_ms":15000,
             "conteo":{"total":3,"conectados":2,"reconectando":1,"esperando":0,"salieron":0},"capacidad":{"normal":50,"pico":100,"activos":3,"nivel":"normal"}}
            """, Ayudas.Web)!;
        Assert.Equal(("hola", "docente", 5000), (m.Tipo, m.Rol, m.LatidoMs));
        Assert.Equal(2, m.ConteoDelMensaje!.Conectados);
        Assert.Equal("normal", m.Capacidad!.Nivel);
    }

    [Fact]
    public void Conteo_SeLeeComoConteoDeSesion()
    {
        var m = JsonSerializer.Deserialize<MensajeAula>("""{"tipo":"conteo","sesion_id":"s1","total":5,"conectados":4,"reconectando":1,"esperando":0,"salieron":0,"emitido_en":7}""", Ayudas.Web)!;
        var conteo = m.ConteoDelMensaje!;
        Assert.Equal((5, 4, 1), (conteo.Total, conteo.Conectados, conteo.Reconectando));
        Assert.Null(JsonSerializer.Deserialize<MensajeAula>("""{"tipo":"cambio","que":"selector"}""", Ayudas.Web)!.ConteoDelMensaje);
    }

    [Fact]
    public void Cambio_DiceQueCambioYNoLlevaContenido()
    {
        var m = JsonSerializer.Deserialize<MensajeAula>("""{"tipo":"cambio","que":"sesion","sesion_id":"s1","carga":{"estado":"suspendida","causa":"reinicio"},"emitido_en":9}""", Ayudas.Web)!;
        Assert.True(m.EsCambio("sesion"));
        Assert.False(m.EsCambio("selector"));
        Assert.Equal(("suspendida", "reinicio"), (m.CargaTexto("estado"), m.CargaTexto("causa")));
    }

    [Fact]
    public void EstadoDeTableta_ConLoNuevoDeTiempoReal()
    {
        var e = JsonSerializer.Deserialize<EstadoTableta>("""
            {"sesion":{"id":"s","estado":"suspendida","fuente_curso":"ejemplo","curso_ref":"c","curso_rotulo":"C","leccion_ref":"l","leccion_rotulo":"L","grupo_rotulo":"","profesor_rotulo":"P","origen_cierre":"","finalizada_en":null},
             "activa":true,"participante":null,"selector":null,"seguimiento":true,"pantallas_bloqueadas":false,"proyectando":true,"ayuda_pedida":true,
             "recuperacion":{"causa":"reinicio","suspendida_en":10,"transcurrido_ms":5000,"ventana_ms":180000,"dentro_de_ventana":true,"bloque":2,"bloque_rotulo":"Tres estados","minuto":14},
             "pendientes":[{"id":"d","clase":"actividad","abierta_en":1,"cerrada_en":null,"disponible_estudio":false,"total_preguntas":6,"puntos_totales":13,
                            "cronometro":{"estado":"congelado","limite_ms":600000,"restante_ms":500000,"transcurrido_ms":100000},"intentos_usados":1,
                            "intento":{"id":"i","estado":"en_curso","numero":1,"respondidas":2,"secuencia_maxima":4}}],
             "avisos":[],"cierre":{"origen_cierre":"inactividad","finalizada_en":5,"pendientes":[{"distribucion_id":"d","rotulo":"P","clase":"actividad","entregado":false}],"estudio":[]},
             "servidor_en":3,"tiempo_real":{"latido_ms":5000,"respaldo_ms":15000}}
            """, Ayudas.Web)!;
        Assert.True(e.Proyectando);
        Assert.True(e.AyudaPedida);
        Assert.Equal("Ibas en el bloque 2, minuto 14.", e.Recuperacion!.Texto);
        var p = e.Pendientes![0];
        Assert.Equal(("congelado", 500_000L), (p.Cronometro!.Estado, p.Cronometro.RestanteMs));
        Assert.Equal((2, 4, 1), (p.Intento!.Respondidas, p.Intento.SecuenciaMaxima, p.IntentosUsados));
        Assert.Equal("inactividad", e.Cierre!.OrigenCierre);
        Assert.Equal(5000, e.TiempoReal!.LatidoMs);
    }
}

// ================================================================================ acceso

[Collection("estado global")]
public sealed class AccesoApiTests : IDisposable
{
    public AccesoApiTests() => ClienteJson.Token = null;
    public void Dispose() => ClienteJson.Token = null;

    private static AccesoApi Api(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> f) =>
        new(new HttpClient(new ManejadorFalso(f)), new Uri("http://192.168.0.55:8000/"));

    [Fact]
    public async Task Login_GuardaElPaseYLoManda_YCerrarSesionLoSuelta()
    {
        var cabeceras = new List<string?>();
        var api = Api((req, _) =>
        {
            cabeceras.Add(req.Headers.Authorization?.ToString());
            return Task.FromResult(req.RequestUri!.AbsolutePath switch
            {
                "/api/acceso/configuracion/" => Ayudas.Respuesta(HttpStatusCode.OK, """{"instalado":true,"sesion_obligatoria":true,"inactividad_min":30}"""),
                "/api/acceso/sesiones/" => Ayudas.Respuesta(HttpStatusCode.OK, """{"token":"jwt-1","tipo":"Bearer","expira_en":9,"sesion_id":"ses-1","usuario":{"id":"u1","alias":"Ana","rol":"TEACHER","menu":"teacher","nivel":2},"sesion_anterior":{"sesion_id":"ses-0","dispositivo":"Tableta 3"}}"""),
                _ => new HttpResponseMessage(HttpStatusCode.NoContent),
            });
        });
        var config = await api.ConfiguracionAsync();
        Assert.True(config!.SesionObligatoria);
        Assert.Null(cabeceras[0]);                                   // antes del login no viaja ningún pase
        var sesion = await api.IniciarSesionAsync("80123456", "clave", "ops-PC");
        Assert.Equal(("jwt-1", "Ana", 2), (sesion!.Token, sesion.Usuario.Alias, sesion.Usuario.Nivel));
        Assert.True(sesion.CerroOtraSesion);
        Assert.Equal("jwt-1", ClienteJson.Token);
        await api.ConfiguracionAsync();
        Assert.Equal("Bearer jwt-1", cabeceras[^1]);                 // y desde entonces viaja en todas
        Assert.True(await api.CerrarSesionAsync());
        Assert.Null(ClienteJson.Token);
    }

    [Fact]
    public async Task CerrarSesion_NoBorraElPaseDeQuienSeIdentificoMientrasLaLlamadaViajaba()
    {
        ClienteJson.Token = "jwt-de-ana";
        var api = Api((_, _) =>
        {
            ClienteJson.Token = "jwt-de-beto";           // Beto se identifica mientras la salida de Ana todavía viaja
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NoContent));
        });
        Assert.True(await api.CerrarSesionAsync());
        Assert.Equal("jwt-de-beto", ClienteJson.Token);
    }

    [Fact]
    public async Task UnLoginQueFalla_NoDejaPase_YExponeElCodigo()
    {
        ClienteJson.Token = "viejo";
        var api = Api((_, _) => Task.FromResult(Ayudas.Respuesta(HttpStatusCode.Unauthorized, """{"detail":"Identificador o clave incorrectos.","codigo":"credenciales_invalidas","intentos_restantes":3}""")));
        Assert.Null(await api.IniciarSesionAsync("x", "y", "d"));
        Assert.Null(ClienteJson.Token);
        Assert.Equal(("credenciales_invalidas", 3L), (api.UltimoError!.Codigo, api.UltimoError.Numero("intentos_restantes")));
    }

    [Fact]
    public async Task UnPaseRechazado_AvisaPorElEventoConElMotivo()
    {
        ErrorAula? recibido = null;
        void Oyente(ErrorAula e) => recibido = e;
        ClienteJson.SesionRechazada += Oyente;
        try
        {
            ClienteJson.Token = "jwt";
            var api = new AulaApi(new HttpClient(new ManejadorFalso((_, _) => Task.FromResult(
                Ayudas.Respuesta(HttpStatusCode.Unauthorized, """{"detail":"La sesión se cerró porque entraste desde otro dispositivo.","codigo":"sesion_cerrada_otro_dispositivo"}""")))),
                new Uri("http://192.168.0.55:8000/"));
            Assert.Null(await api.SesionAsync("s1"));
            Assert.True(recibido!.SesionPerdida);
            Assert.True(recibido.CerradaEnOtroDispositivo);          // PAN-103
        }
        finally { ClienteJson.SesionRechazada -= Oyente; }
    }

    [Fact]
    public async Task Aula_FrenoYAulaLlena_SeReconocenPorSuCodigo()
    {
        var api = new AulaApi(new HttpClient(new ManejadorFalso((req, _) => Task.FromResult(req.RequestUri!.Query.Contains("llena")
            ? Ayudas.Respuesta((HttpStatusCode)409, """{"detail":"El aula alcanzó su capacidad.","codigo":"aula_llena","capacidad":100}""")
            : Ayudas.Respuesta((HttpStatusCode)429, """{"detail":"Demasiados códigos equivocados.","codigo":"demasiados_intentos","reintentar_en_ms":45000}""")))),
            new Uri("http://192.168.0.55:8000/"));
        Assert.Null(await api.UnirseAsync("111111", "ana", "Ana", "tab", null));
        Assert.True(api.UltimoError!.Frenado);
        Assert.Equal(45_000L, api.UltimoError.Numero("reintentar_en_ms"));
        Assert.Null(await api.EstadoAsync("s?llena", "p"));
        Assert.True(api.UltimoError!.AulaLlena);
    }
}

// ================================================================================ reloj

[Collection("estado global")]
public sealed class RelojNodoTests : IDisposable
{
    public RelojNodoTests() => RelojNodo.Olvidar();
    public void Dispose() => RelojNodo.Olvidar();

    [Fact]
    public void ElDesfaseSeAprendeDelNodo_YNormalizaLaHoraDelAparato()
    {
        Assert.False(RelojNodo.Aprendido);
        var local = RelojNodo.LocalMs;
        RelojNodo.Aprender(local + 40 * 60_000);           // el nodo va 40 minutos adelante de este aparato (AC-072)
        Assert.True(RelojNodo.Aprendido);
        Assert.InRange(RelojNodo.DesfaseMs, 40 * 60_000 - 50, 40 * 60_000 + 50);
        Assert.InRange(RelojNodo.ANodo(local) - local, 40 * 60_000 - 50, 40 * 60_000 + 50);
        Assert.InRange(RelojNodo.AhoraMs - RelojNodo.LocalMs, 40 * 60_000 - 50, 40 * 60_000 + 50);
        RelojNodo.Aprender(0);                              // un valor inservible no borra lo aprendido
        Assert.True(RelojNodo.DesfaseMs > 0);
    }
}

// ================================================================================ cola local

[Collection("estado global")]
public sealed class ColaRespuestasTests : IDisposable
{
    private readonly string carpeta = Ayudas.CarpetaTemporal();
    private string Archivo => Path.Combine(carpeta, "cola.json");
    public ColaRespuestasTests() => RelojNodo.Olvidar();
    public void Dispose() { RelojNodo.Olvidar(); try { Directory.Delete(carpeta, true); } catch { } }

    private static JsonElement Resp(string json = """{"value":true}""") => Ayudas.Json(json);

    [Fact]
    public void LaSecuenciaEsMonotonicaPorIntento_YSobreviveAlReinicioDeLaApp()
    {
        var cola = new ColaRespuestas(Archivo);
        Assert.Equal(1, cola.Guardar("s", "d", "p", 1, "q1", Resp()));
        Assert.Equal(2, cola.Guardar("s", "d", "p", 1, "q2", Resp()));
        Assert.Equal(1, cola.Guardar("s", "d", "p", 2, "q1", Resp()));         // otro intento, otra cuenta
        var reabierta = new ColaRespuestas(Archivo);                            // la app se cerró y volvió a abrir
        Assert.Equal(3, reabierta.Guardar("s", "d", "p", 1, "q3", Resp()));    // no se reutiliza ninguna secuencia
        Assert.Equal(3, reabierta.UltimaSecuencia("s", "d", "p", 1));
        Assert.Equal(4, reabierta.CantidadPendiente());
    }

    [Fact]
    public void VolverAResponderSustituyeLoPendienteDeEsaPregunta_ConSecuenciaMayor()
    {
        var cola = new ColaRespuestas(Archivo);
        cola.Guardar("s", "d", "p", 1, "q1", Resp("""{"value":false}"""));
        var segunda = cola.Guardar("s", "d", "p", 1, "q1", Resp("""{"value":true}"""));
        var paquete = Assert.Single(cola.Pendientes());
        var r = Assert.Single(paquete.Respuestas);
        Assert.Equal((segunda, true), (r.Secuencia, r.Respuesta.GetProperty("value").GetBoolean()));
        Assert.True(r.CapturadaEn > 0 && r.CapturadaEnTableta > 0);
    }

    [Fact]
    public void LaHoraDeCapturaSeNormalizaConElDesfaseAprendido()
    {
        var cola = new ColaRespuestas(Archivo);
        RelojNodo.Aprender(RelojNodo.LocalMs + 40 * 60_000);
        cola.Guardar("s", "d", "p", 1, "q1", Resp());
        var r = cola.Pendientes()[0].Respuestas[0];
        Assert.InRange(r.CapturadaEn!.Value - r.CapturadaEnTableta!.Value, 40 * 60_000 - 50, 40 * 60_000 + 50);   // la cruda se conserva como dato adicional
    }

    [Fact]
    public void ReconocerBorraLoEnviado_PeroConservaLoGuardadoMientrasViajaba()
    {
        var cola = new ColaRespuestas(Archivo);
        cola.Guardar("s", "d", "p", 1, "q1", Resp());
        cola.Guardar("s", "d", "p", 1, "q2", Resp());
        var enViaje = cola.Pendientes()[0];
        cola.Guardar("s", "d", "p", 1, "q3", Resp());                          // llega otra respuesta mientras el envío viaja
        cola.Guardar("s", "d", "p", 1, "q1", Resp("""{"value":false}"""));     // y se corrige una ya enviada
        cola.Reconocer(enViaje);
        var quedan = Assert.Single(cola.Pendientes()).Respuestas.Select(r => r.PreguntaRef).OrderBy(x => x).ToArray();
        Assert.Equal(["q1", "q3"], quedan);                                     // q2 salió; q3 y la corrección de q1 siguen esperando
    }

    [Fact]
    public void LaEntregaEsperaAQueSalgaLoPendiente_YSeBorraConElAcuse()
    {
        var cola = new ColaRespuestas(Archivo);
        cola.Guardar("s", "d", "p", 1, "q1", Resp());
        cola.Entregar("s", "d", "p", 1);
        var paquete = cola.Pendientes()[0];
        Assert.True(paquete.Entregar);
        Assert.Equal(2, cola.CantidadPendiente());                              // una respuesta y la entrega
        cola.Reconocer(paquete);
        Assert.Empty(cola.Pendientes());
        cola.Entregar("s", "d", "p", 2);                                        // una entrega sin respuestas nuevas también es un envío
        Assert.Equal(1, cola.CantidadPendiente());
        Assert.Equal(1, cola.UltimaSecuencia("s", "d", "p", 1));                // el contador no se pierde al vaciarse
    }

    [Fact]
    public void UnArchivoCorruptoSeApartaYLaColaEmpiezaVacia()
    {
        File.WriteAllText(Archivo, "{esto no es json");
        var cola = new ColaRespuestas(Archivo);
        Assert.Empty(cola.Pendientes());
        Assert.True(File.Exists(Archivo + ".dañado"));
        Assert.Equal(1, cola.Guardar("s", "d", "p", 1, "q1", Resp()));         // y se puede seguir guardando
    }

    [Fact]
    public void OlvidarUnaSesionSoloVale_SiNoQuedaNadaPendiente()
    {
        var cola = new ColaRespuestas(Archivo);
        cola.Guardar("s1", "d", "p", 1, "q1", Resp());
        cola.Olvidar("s1");
        Assert.Equal(1, cola.CantidadPendiente("s1"));
        cola.Reconocer(cola.Pendientes()[0]);
        cola.Olvidar("s1");
        Assert.Equal(0, cola.UltimaSecuencia("s1", "d", "p", 1));
    }

    [Fact]
    public void ElCambioSeAvisa()
    {
        var cola = new ColaRespuestas(Archivo);
        var avisos = 0;
        cola.Cambio += () => avisos++;
        cola.Guardar("s", "d", "p", 1, "q1", Resp());
        cola.Entregar("s", "d", "p", 1);
        cola.Reconocer(cola.Pendientes()[0]);
        Assert.Equal(3, avisos);
    }
}

// ================================================================================ sincronización

[Collection("estado global")]
public sealed class SincronizadorRespuestasTests : IDisposable
{
    private readonly string carpeta = Ayudas.CarpetaTemporal();
    public SincronizadorRespuestasTests() { RelojNodo.Olvidar(); ClienteJson.Token = null; }
    public void Dispose() { RelojNodo.Olvidar(); try { Directory.Delete(carpeta, true); } catch { } }

    private ColaRespuestas Cola() => new(Path.Combine(carpeta, "cola.json"));

    private static AulaApi Api(Func<HttpRequestMessage, Task<HttpResponseMessage>> f) =>
        new(new HttpClient(new ManejadorFalso((req, _) => f(req))), new Uri("http://192.168.0.55:8000/"));

    private const string AcuseJson = """{"acuse":true,"politica":"aceptar","intento":{"id":"i1","estado":"en_curso","numero":1,"respondidas":1,"secuencia_maxima":1},"aceptadas":["q1"],"duplicadas":[],"superadas":[],"rechazadas":[],"recibida_en":5,"servidor_en":123456}""";

    [Fact]
    public async Task ConAcuse_SeBorraLoEnviado_YSeAprendeElRelojDelNodo()
    {
        var cola = Cola();
        cola.Guardar("s1", "d1", "p1", 1, "q1", Ayudas.Json("""{"value":true}"""));
        string? cuerpo = null;
        var sync = new SincronizadorRespuestas(Api(async req => { cuerpo = await req.Content!.ReadAsStringAsync(); return Ayudas.Respuesta(HttpStatusCode.OK, AcuseJson); }), cola);
        var r = await sync.VaciarAsync();
        Assert.Equal((1, 0, 0, false), (r.Enviados, r.Pendientes, r.Descartados, r.SinConexion));
        Assert.Empty(cola.Pendientes());
        Assert.InRange(RelojNodo.AhoraMs, 123456, 123456 + 60_000);             // aprendió el «servidor_en»
        using var doc = JsonDocument.Parse(cuerpo!);
        Assert.Equal("p1", doc.RootElement.GetProperty("participante_id").GetString());
        Assert.Equal(1, doc.RootElement.GetProperty("intento_numero").GetInt32());
        Assert.Equal("directo", doc.RootElement.GetProperty("origen").GetString());
        var enviada = doc.RootElement.GetProperty("respuestas")[0];
        Assert.Equal(("q1", 1), (enviada.GetProperty("pregunta_ref").GetString(), enviada.GetProperty("secuencia").GetInt32()));
        Assert.True(enviada.TryGetProperty("capturada_en", out _) && enviada.TryGetProperty("capturada_en_tableta", out _));
    }

    [Fact]
    public async Task SinRed_NoSePierdeNada_YElSiguienteIntentoLoEnvia()
    {
        var cola = Cola();
        cola.Guardar("s1", "d1", "p1", 1, "q1", Ayudas.Json("""{"value":true}"""));
        cola.Entregar("s1", "d1", "p1", 1);
        var caido = true;
        var llamadas = 0;
        var sync = new SincronizadorRespuestas(Api(req =>
        {
            llamadas++;
            if (caido) throw new HttpRequestException("sin ruta al aula");
            return Task.FromResult(Ayudas.Respuesta(HttpStatusCode.OK, AcuseJson));
        }), cola);
        var primera = await sync.VaciarAsync();
        Assert.Equal((0, 2, 0, true), (primera.Enviados, primera.Pendientes, primera.Descartados, primera.SinConexion));
        Assert.Single(cola.Pendientes());
        caido = false;
        var segunda = await sync.VaciarAsync();
        Assert.Equal((1, 0, false), (segunda.Enviados, segunda.Pendientes, segunda.SinConexion));
        Assert.Equal(2, llamadas);
    }

    [Theory]
    [InlineData(409, "distribucion_cerrada")]
    [InlineData(409, "intento_entregado")]
    [InlineData(403, "sin_permiso")]
    [InlineData(404, "no_encontrado")]
    [InlineData(400, "datos_invalidos")]
    public async Task UnRechazoDefinitivo_DescartaElPaquete_ParaNoReintentarloEternamente(int estado, string codigo)
    {
        var cola = Cola();
        cola.Guardar("s1", "d1", "p1", 1, "q1", Ayudas.Json("""{"value":true}"""));
        var sync = new SincronizadorRespuestas(Api(_ => Task.FromResult(Ayudas.Respuesta((HttpStatusCode)estado, $$"""{"detail":"no","codigo":"{{codigo}}"}"""))), cola);
        var resueltos = new List<AcuseRespuestas?>();
        sync.PaqueteResuelto += (_, acuse) => resueltos.Add(acuse);
        var r = await sync.VaciarAsync();
        Assert.Equal((0, 0, 1), (r.Enviados, r.Pendientes, r.Descartados));
        Assert.Null(Assert.Single(resueltos));
    }

    [Fact]
    public async Task LoDeOtraPersona_EnUnaTabletaCompartida_SeConserva_YLoPropioSigueSaliendo()
    {
        var cola = Cola();
        cola.Guardar("s1", "d1", "pAna", 1, "q1", Ayudas.Json("""{"value":true}"""));      // lo dejó Ana, que ya salió
        cola.Guardar("s1", "d1", "pBeto", 1, "q1", Ayudas.Json("""{"value":false}"""));    // lo de Beto, que tiene la sesión abierta
        var sync = new SincronizadorRespuestas(Api(async req =>
        {
            var cuerpo = await req.Content!.ReadAsStringAsync();
            return cuerpo.Contains("pAna")
                ? Ayudas.Respuesta((HttpStatusCode)403, """{"detail":"Ese participante es de otra persona.","codigo":"persona_ajena"}""")
                : Ayudas.Respuesta(HttpStatusCode.OK, AcuseJson);
        }), cola);
        var r = await sync.VaciarAsync();
        Assert.Equal((1, 1, 0), (r.Enviados, r.Pendientes, r.Descartados));    // lo de Beto salió, lo de Ana sigue esperando a su dueña
        Assert.Equal("pAna", Assert.Single(cola.Pendientes()).ParticipanteId);
    }

    [Fact]
    public async Task UnErrorDelServidorOUnaSesionPerdida_ConservaLaCola()
    {
        var cola = Cola();
        cola.Guardar("s1", "d1", "p1", 1, "q1", Ayudas.Json("""{"value":true}"""));
        var sync500 = new SincronizadorRespuestas(Api(_ => Task.FromResult(Ayudas.Respuesta((HttpStatusCode)500, """{"detail":"falla"}"""))), cola);
        Assert.Equal(1, (await sync500.VaciarAsync()).Pendientes);
        var sync401 = new SincronizadorRespuestas(Api(_ => Task.FromResult(Ayudas.Respuesta((HttpStatusCode)401, """{"detail":"caducó","codigo":"sesion_expirada"}"""))), cola);
        Assert.Equal(1, (await sync401.VaciarAsync()).Pendientes);      // la persona vuelve a identificarse y la cola sigue ahí
    }

    [Fact]
    public async Task UnaSegundaPasadaMientrasHayUnaEnCurso_NoHaceNada()
    {
        var cola = Cola();
        cola.Guardar("s1", "d1", "p1", 1, "q1", Ayudas.Json("""{"value":true}"""));
        var liberar = new TaskCompletionSource();
        var enviados = 0;
        var sync = new SincronizadorRespuestas(Api(async _ => { Interlocked.Increment(ref enviados); await liberar.Task; return Ayudas.Respuesta(HttpStatusCode.OK, AcuseJson); }), cola);
        var primera = sync.VaciarAsync();
        await Task.Delay(100);
        var segunda = await sync.VaciarAsync();
        Assert.Equal(ResultadoSincronizacion.Nada, segunda);
        liberar.SetResult();
        Assert.Equal(1, (await primera).Enviados);
        Assert.Equal(1, enviados);
    }

    [Fact]
    public async Task LoQueLlevaMuchoEnLaCola_SaleMarcadoComoDeCola()
    {
        var cola = Cola();
        cola.Guardar("s1", "d1", "p1", 1, "q1", Ayudas.Json("""{"value":true}"""));
        await Task.Delay(50);
        string? origen = null;
        var sync = new SincronizadorRespuestas(Api(async req =>
        {
            using var doc = JsonDocument.Parse(await req.Content!.ReadAsStringAsync());
            origen = doc.RootElement.GetProperty("origen").GetString();
            return Ayudas.Respuesta(HttpStatusCode.OK, AcuseJson);
        }), cola);
        await sync.VaciarAsync();
        Assert.Equal("directo", origen);                                        // recién guardado: es un envío en línea
    }
}

// ================================================================================ WebSocket

/// <summary>Un servidor WebSocket de mentira sobre HttpListener: lo que el cliente ve del canal del aula.</summary>
internal sealed class ServidorWs : IAsyncDisposable
{
    private readonly HttpListener escucha = new();
    private readonly CancellationTokenSource parada = new();
    public int Puerto { get; }
    public int Conexiones;
    public List<string> Consultas { get; } = [];
    public List<string> Recibidos { get; } = [];
    public Func<WebSocket, int, Task> Sesion { get; set; } = (_, _) => Task.CompletedTask;
    public Uri Base => new($"http://127.0.0.1:{Puerto}/");

    public ServidorWs()
    {
        var l = new TcpListener(IPAddress.Loopback, 0);
        l.Start();
        Puerto = ((IPEndPoint)l.LocalEndpoint).Port;
        l.Stop();
        escucha.Prefixes.Add($"http://127.0.0.1:{Puerto}/");
        escucha.Start();
        _ = Task.Run(AceptarAsync);
    }

    private async Task AceptarAsync()
    {
        while (!parada.IsCancellationRequested)
        {
            HttpListenerContext ctx;
            try { ctx = await escucha.GetContextAsync(); }
            catch { return; }
            if (!ctx.Request.IsWebSocketRequest) { ctx.Response.StatusCode = 400; ctx.Response.Close(); continue; }
            var n = Interlocked.Increment(ref Conexiones);
            lock (Consultas) Consultas.Add(ctx.Request.Url!.PathAndQuery);
            var socket = (await ctx.AcceptWebSocketAsync(null)).WebSocket;
            _ = Task.Run(async () =>
            {
                try { await Sesion(socket, n); } catch { }
            });
        }
    }

    public static Task Enviar(WebSocket s, string json) => s.SendAsync(Encoding.UTF8.GetBytes(json), WebSocketMessageType.Text, true, CancellationToken.None);

    /// <summary>Lee mensajes del cliente y los anota hasta que se cierre.</summary>
    public async Task LeerAsync(WebSocket s)
    {
        var buffer = new byte[4096];
        while (s.State == WebSocketState.Open)
        {
            var r = await s.ReceiveAsync(buffer, CancellationToken.None);
            if (r.MessageType == WebSocketMessageType.Close) return;
            lock (Recibidos) Recibidos.Add(Encoding.UTF8.GetString(buffer, 0, r.Count));
        }
    }

    public async ValueTask DisposeAsync()
    {
        parada.Cancel();
        escucha.Abort();
        await Task.CompletedTask;
    }
}

[Collection("estado global")]
public sealed class AulaSocketClientTests : IDisposable
{
    public AulaSocketClientTests() => RelojNodo.Olvidar();
    public void Dispose() => RelojNodo.Olvidar();

    private static async Task Hasta(Func<bool> condicion, int ms = 5000, string? motivo = null)
    {
        var fin = DateTime.UtcNow.AddMilliseconds(ms);
        while (DateTime.UtcNow < fin)
        {
            if (condicion()) return;
            await Task.Delay(20);
        }
        Assert.Fail(motivo ?? "No se cumplió la condición a tiempo.");
    }

    [Fact]
    public void LaDireccionDelCanalSaleDeLaDelNodo()
    {
        Assert.Equal("ws://192.168.0.55:8000/ws/aula/sesiones/s%201/?rol=docente",
                     AulaSocketClient.UriDe(new Uri("http://192.168.0.55:8000/"), "s 1", "docente", null, null).AbsoluteUri);
        Assert.Equal("wss://nodo/ws/aula/sesiones/s1/?rol=estudiante&participante=p1&token=a%2Bb",
                     AulaSocketClient.UriDe(new Uri("https://nodo/"), "s1", "estudiante", "p1", "a+b").AbsoluteUri);
    }

    [Fact]
    public async Task ElProfesorRecibeElHolaConElConteo_YLuegoCadaConteo()
    {
        await using var servidor = new ServidorWs();
        servidor.Sesion = async (s, _) =>
        {
            await ServidorWs.Enviar(s, """{"tipo":"hola","rol":"docente","servidor_en":1000,"latido_ms":5000,"conteo":{"total":1,"conectados":1,"reconectando":0,"esperando":0,"salieron":0}}""");
            await Task.Delay(100);
            await ServidorWs.Enviar(s, """{"tipo":"conteo","sesion_id":"s1","total":3,"conectados":3,"reconectando":0,"esperando":0,"salieron":0}""");
            await servidor.LeerAsync(s);
        };
        var recibidos = new List<MensajeAula>();
        var estados = new List<ConexionAula>();
        await using var cliente = new AulaSocketClient(servidor.Base, "s1", "docente");
        cliente.Mensaje += m => { lock (recibidos) recibidos.Add(m); };
        cliente.ConexionCambio += estados.Add;
        cliente.Iniciar();
        await Hasta(() => { lock (recibidos) return recibidos.Count >= 2; });
        Assert.Equal(ConexionAula.Conectado, cliente.Conexion);
        Assert.Equal(1, recibidos[0].ConteoDelMensaje!.Conectados);
        Assert.Equal(3, recibidos[1].ConteoDelMensaje!.Conectados);
        Assert.Contains("rol=docente", servidor.Consultas[0]);
        Assert.Equal([ConexionAula.Conectado], estados);
        Assert.True(RelojNodo.Aprendido);                                        // el «hola» enseña el reloj del nodo
    }

    [Fact]
    public async Task LaTabletaManda_ElLatidoQuePideElNodo_Y_LaPresenciaQueDeclara()
    {
        await using var servidor = new ServidorWs();
        servidor.Sesion = async (s, _) =>
        {
            await ServidorWs.Enviar(s, """{"tipo":"hola","rol":"estudiante","servidor_en":1000,"latido_ms":100,"participante":{"id":"p1","estado":"conectado"}}""");
            await servidor.LeerAsync(s);
        };
        await using var cliente = new AulaSocketClient(servidor.Base, "s1", "estudiante", "p1", telemetria: () => new { espacio_libre_mb = 900 });
        cliente.Iniciar();
        await Hasta(() => cliente.Conectado);
        await Hasta(() => { lock (servidor.Recibidos) return servidor.Recibidos.Any(x => x.Contains("\"latido\"") && x.Contains("espacio_libre_mb")); }, motivo: "no llegó el latido");
        Assert.True(await cliente.DeclararPresenciaAsync("reconectando"));
        await Hasta(() => { lock (servidor.Recibidos) return servidor.Recibidos.Any(x => x.Contains("\"presencia\"") && x.Contains("reconectando")); });
        Assert.Contains("participante=p1", servidor.Consultas[0]);
    }

    [Fact]
    public async Task SiElCanalSeCae_ReconectaSolo_YElHttpSigueDeRespaldo()
    {
        await using var servidor = new ServidorWs();
        servidor.Sesion = async (s, n) =>
        {
            await ServidorWs.Enviar(s, """{"tipo":"hola","rol":"docente","servidor_en":1,"latido_ms":5000,"conteo":{"total":0,"conectados":0,"reconectando":0,"esperando":0,"salieron":0}}""");
            if (n == 1) { await Task.Delay(100); s.Abort(); return; }   // la primera conexión se corta de golpe
            await servidor.LeerAsync(s);
        };
        var estados = new List<ConexionAula>();
        await using var cliente = new AulaSocketClient(servidor.Base, "s1", "docente");
        cliente.ConexionCambio += e => { lock (estados) estados.Add(e); };
        cliente.Iniciar();
        await Hasta(() => Volatile.Read(ref servidor.Conexiones) >= 2, 8000, "no reconectó");
        await Hasta(() => cliente.Conectado);
        lock (estados) Assert.Equal([ConexionAula.Conectado, ConexionAula.Reconectando, ConexionAula.Conectado], estados);
    }

    [Fact]
    public async Task ElNodoQueRechaza_NoSeReintenta_YQuedaElMotivo()
    {
        await using var servidor = new ServidorWs();
        servidor.Sesion = async (s, _) =>
        {
            await ServidorWs.Enviar(s, """{"tipo":"error","codigo":"participante_expulsado","detalle":"El participante fue expulsado."}""");
            await s.CloseAsync((WebSocketCloseStatus)4403, "expulsado", CancellationToken.None);
        };
        await using var cliente = new AulaSocketClient(servidor.Base, "s1", "estudiante", "p1");
        cliente.Iniciar();
        await Hasta(() => cliente.Rechazado, 5000, "no se marcó el rechazo");
        await Task.Delay(1500);
        Assert.Equal(1, servidor.Conexiones);                                     // no vuelve a llamar
        Assert.Equal("participante_expulsado", cliente.UltimoRechazo!.Codigo);
        Assert.Equal(ConexionAula.TrabajandoEnElDispositivo, cliente.Conexion);
    }

    [Fact]
    public async Task SinNodo_PasaDeReconectandoATrabajandoEnElDispositivo()
    {
        var libre = new TcpListener(IPAddress.Loopback, 0);
        libre.Start();
        var puerto = ((IPEndPoint)libre.LocalEndpoint).Port;
        libre.Stop();                                                              // nadie escucha en ese puerto
        var estados = new List<ConexionAula>();
        await using var cliente = new AulaSocketClient(new Uri($"http://127.0.0.1:{puerto}/"), "s1", "estudiante", "p1", tiempoParaTrabajarSolo: TimeSpan.FromMilliseconds(600));
        cliente.ConexionCambio += e => { lock (estados) estados.Add(e); };
        cliente.Iniciar();
        await Hasta(() => cliente.Conexion == ConexionAula.TrabajandoEnElDispositivo, 6000, "no pasó a trabajar en el dispositivo");
        lock (estados) Assert.Equal([ConexionAula.TrabajandoEnElDispositivo], estados);   // nunca estuvo conectado: de Reconectando (inicial) a Trabajando
    }

    [Fact]
    public async Task DetenerCierraElCanal_YNoReintenta()
    {
        await using var servidor = new ServidorWs();
        servidor.Sesion = async (s, _) =>
        {
            await ServidorWs.Enviar(s, """{"tipo":"hola","rol":"docente","servidor_en":1,"latido_ms":5000,"conteo":{"total":0,"conectados":0,"reconectando":0,"esperando":0,"salieron":0}}""");
            await servidor.LeerAsync(s);
        };
        var cliente = new AulaSocketClient(servidor.Base, "s1", "docente");
        cliente.Iniciar();
        await Hasta(() => cliente.Conectado);
        await cliente.DetenerAsync();
        await Task.Delay(1500);
        Assert.Equal(1, servidor.Conexiones);
        Assert.False(cliente.Conectado);
    }
}

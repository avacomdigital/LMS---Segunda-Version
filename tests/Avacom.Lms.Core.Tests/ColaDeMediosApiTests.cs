using System.Net;
using System.Text;
using Avacom.Lms.Core.Diagnostico;

namespace Avacom.Lms.Core.Tests;

/// <summary>El cliente de la cola de medios del nodo (<c>/api/medios/cola/</c>) contra un backend falso: contratos, rutas y degradación.</summary>
public sealed class ColaDeMediosApiTests
{
    private const string EstadoJson = """
        {"activa":true,"motivo_apagada":"","modo":"hilos",
         "cola":{"pendientes":2,"descargando":1},
         "recursos":{"pendiente":2,"descargando":1,"disponible":14,"fallido":1,"cancelado":0},
         "cache":{"bytes_ocupados":734003200,"bytes_maximo":4294967296,"bytes_libres_disco":53687091200,"bytes_libres_minimo":1073741824,"lecturas_activas":3},
         "transferencias":{"en_uso":3,"maximo":24,"pico":11},
         "limites":{"descargas_simultaneas":3,"transferencias_simultaneas":24,"ancho_entrada_bps":0,"ancho_salida_bps":2097152},
         "contadores":{"aciertos":240,"siguiendo":12,"directos":1,"bytes_servidos":987654321},
         "campo_futuro":{"que":"se ignora"}}
        """;

    private const string RecursosJson = """
        {"recursos":[
          {"id":"r1","estado":"descargando","prioridad":"proyeccion","fuente":"biblioteca","curso_ref":"avacom.co.science","curso_version":"1.0.0","media_ref":"vid-changes","ruta":"",
           "tipo_mime":"video/mp4","bytes_total":104857600,"bytes_hechos":52428800,"porcentaje":50,"sha256":"","intentos":1,"error_codigo":"","error_detalle":"","usos":0,
           "creado_en":1,"actualizado_en":2,"terminado_en":null,"ultimo_uso_en":null},
          {"id":"r2","estado":"fallido","prioridad":"clase","fuente":"biblioteca","curso_ref":"avacom.co.science","curso_version":"1.0.0","media_ref":"aud-summary","ruta":"",
           "tipo_mime":"","bytes_total":null,"bytes_hechos":0,"porcentaje":null,"sha256":"","intentos":3,"error_codigo":"origen_no_disponible","error_detalle":"La biblioteca se cerró.","usos":0,
           "creado_en":1,"actualizado_en":3,"terminado_en":3,"ultimo_uso_en":null}],
         "total":2}
        """;

    private static HttpResponseMessage Json(HttpStatusCode estado, string cuerpo) =>
        new(estado) { Content = new StringContent(cuerpo, Encoding.UTF8, "application/json") };

    private sealed class Falso(Func<HttpRequestMessage, string?, HttpResponseMessage> responder) : HttpMessageHandler
    {
        public List<(HttpMethod Metodo, string Ruta, string? Cuerpo)> Peticiones { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            var cuerpo = request.Content is null ? null : await request.Content.ReadAsStringAsync(ct);
            Peticiones.Add((request.Method, request.RequestUri!.PathAndQuery, cuerpo));
            return responder(request, cuerpo);
        }
    }

    private static ColaDeMediosApi Api(Falso falso) => new(new HttpClient(falso), new Uri("http://aula.local:8000/"));

    [Fact]
    public async Task El_estado_trae_cola_cache_cupos_y_limites_y_ignora_lo_que_no_conoce()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, EstadoJson));
        var e = (await Api(falso).EstadoAsync())!;
        Assert.Equal((HttpMethod.Get, "/api/medios/cola/"), (falso.Peticiones[0].Metodo, falso.Peticiones[0].Ruta));
        Assert.True(e.Activa);
        Assert.Equal((2, 1), (e.Cola!.Pendientes, e.Cola.Descargando));
        Assert.Equal((14, 1, 0, 0), (e.En("disponible"), e.En("fallido"), e.En("cancelado"), e.En("no-existe")));
        Assert.Equal((734003200L, 4294967296L, 3), (e.Cache!.BytesOcupados, e.Cache.BytesMaximo, e.Cache.LecturasActivas));
        Assert.Equal((3, 24, 11), (e.Transferencias!.EnUso, e.Transferencias.Maximo, e.Transferencias.Pico));
        Assert.Equal((3, 24, 0L, 2097152L), (e.Limites!.DescargasSimultaneas, e.Limites.TransferenciasSimultaneas, e.Limites.AnchoEntradaBps, e.Limites.AnchoSalidaBps));
        Assert.Equal(987654321L, e.Contadores!["bytes_servidos"]);
    }

    [Fact]
    public async Task Los_recursos_traen_avance_y_motivo_de_fallo()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, RecursosJson));
        var lista = (await Api(falso).RecursosAsync(contexto: "sesion 1", estado: "fallido", limite: 500))!;
        Assert.Equal("/api/medios/cola/recursos/?limite=200&contexto=sesion%201&estado=fallido", falso.Peticiones[0].Ruta);   // el tope es 200 y el contexto viaja escapado
        Assert.Equal(2, lista.Total);
        var bajando = lista.Recursos![0];
        Assert.Equal(("descargando", "proyeccion", "vid-changes", 50, 52428800L), (bajando.Estado, bajando.Prioridad, bajando.MediaRef, bajando.Porcentaje, bajando.BytesHechos));
        Assert.True(bajando.EnCurso);
        Assert.False(bajando.Fallo);
        var fallido = lista.Recursos[1];
        Assert.True(fallido.Fallo);
        Assert.Null(fallido.Porcentaje);
        Assert.Equal(("origen_no_disponible", "La biblioteca se cerró.", 3), (fallido.ErrorCodigo, fallido.ErrorDetalle, fallido.Intentos));
    }

    [Fact]
    public async Task Sin_filtros_la_consulta_sólo_lleva_el_límite()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, """{"recursos":[],"total":0}"""));
        await Api(falso).RecursosAsync();
        Assert.Equal("/api/medios/cola/recursos/?limite=100", falso.Peticiones[0].Ruta);
    }

    [Fact]
    public async Task Cancelar_reintentar_y_vaciar_usan_las_rutas_de_la_cola()
    {
        var falso = new Falso((req, _) => req.RequestUri!.AbsolutePath.EndsWith("limpiar/")
            ? Json(HttpStatusCode.OK, """{"expulsados":7}""")
            : Json(HttpStatusCode.OK, """{"ok":true}"""));
        var api = Api(falso);
        Assert.True(await api.CancelarAsync("r1"));
        Assert.True(await api.ReintentarAsync("r 2"));
        Assert.Equal(7, await api.LimpiarAsync());
        Assert.Equal(["/api/medios/cola/recursos/r1/cancelar/", "/api/medios/cola/recursos/r%202/reintentar/", "/api/medios/cola/limpiar/"], falso.Peticiones.Select(p => p.Ruta).ToArray());
        Assert.All(falso.Peticiones, p => Assert.Equal(HttpMethod.Post, p.Metodo));
    }

    [Fact]
    public async Task Un_409_o_un_403_se_cuentan_como_que_no_se_pudo_y_dejan_el_motivo()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.Conflict, """{"detail":"Ese recurso no se puede cancelar (no existe o ya está listo).","codigo":"conflicto"}"""));
        var api = Api(falso);
        Assert.False(await api.CancelarAsync("r1"));
        Assert.Equal(409, api.UltimoError!.Estado);
        Assert.Equal("conflicto", api.UltimoError.Codigo);

        var prohibido = Api(new Falso((_, _) => Json(HttpStatusCode.Forbidden, """{"detail":"Sólo el personal del aula puede cambiar la cola de medios.","codigo":"sin_permiso"}""")));
        Assert.Null(await prohibido.LimpiarAsync());
        Assert.Equal(403, prohibido.UltimoError!.Estado);
    }

    [Fact]
    public async Task Una_cola_que_se_apago_sola_dice_por_que()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, """{"activa":false,"motivo_apagada":"No se pudo preparar la carpeta de la caché de medios (C:\\x): Acceso denegado","recursos":{}}"""));
        var e = (await Api(falso).EstadoAsync())!;
        Assert.False(e.Activa);
        Assert.Contains("Acceso denegado", e.MotivoApagada);
    }

    [Fact]
    public async Task Sin_nodo_el_estado_es_nulo_y_no_lanza()
    {
        var api = Api(new Falso((_, _) => throw new HttpRequestException("sin red")));
        Assert.Null(await api.EstadoAsync());
        Assert.NotNull(api.UltimoMotivo);
    }
}

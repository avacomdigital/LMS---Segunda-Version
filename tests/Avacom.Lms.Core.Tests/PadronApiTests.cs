using System.Net;
using System.Text;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>El cliente de /api/acceso/padron/ contra un backend falso: rutas, cuerpos, lectura del estado y motivos de rechazo.</summary>
public sealed class PadronApiTests
{
    private static readonly Uri Base = new("http://127.0.0.1:8000/");

    private sealed class Falso(Func<HttpRequestMessage, string?, HttpResponseMessage> responder) : HttpMessageHandler
    {
        public List<(HttpMethod Metodo, string Ruta, string? Cuerpo)> Peticiones { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            var cuerpo = request.Content is null ? null : await request.Content.ReadAsStringAsync(ct);
            Peticiones.Add((request.Method, request.RequestUri!.AbsolutePath, cuerpo));
            return responder(request, cuerpo);
        }
    }

    private static HttpResponseMessage Json(HttpStatusCode estado, string json) =>
        new(estado) { Content = new StringContent(json, Encoding.UTF8, "application/json") };

    private const string EstadoJson = """
        {"instalado":true,"organizacion":{"codigo":"AULA-PRUEBA","nombre":"Aula de prueba"},
         "grupos":[{"id":"g1","codigo":"SEXTO-A","nombre":"Sexto A","periodo":"2026","nivel_clave":"secundaria","activo":true,
                    "estudiantes":[{"id":"u1","alias":"Juan Pérez","estado":"ACTIVO","provisional":false}],"docentes":0}],
         "sin_grupo":[{"id":"u2","alias":"Ana Gómez"}]}
        """;

    [Fact]
    public async Task Lee_el_estado_con_grupos_estudiantes_y_sin_grupo()
    {
        var api = new PadronApi(new HttpClient(new Falso((_, _) => Json(HttpStatusCode.OK, EstadoJson))), Base);
        var estado = await api.EstadoAsync();
        Assert.NotNull(estado);
        Assert.True(estado.Instalado);
        Assert.Equal("Aula de prueba", estado.Organizacion!.Nombre);
        Assert.Equal("SEXTO-A", estado.Grupos[0].Codigo);
        Assert.Equal("Juan Pérez", estado.Grupos[0].Estudiantes[0].Alias);
        Assert.Equal("Ana Gómez", estado.SinGrupo[0].Alias);
    }

    [Fact]
    public async Task El_nodo_vacio_se_lee_como_no_instalado_sin_error()
    {
        var api = new PadronApi(new HttpClient(new Falso((_, _) => Json(HttpStatusCode.OK, """{"instalado":false,"organizacion":null,"grupos":[],"sin_grupo":[]}"""))), Base);
        var estado = await api.EstadoAsync();
        Assert.False(estado!.Instalado);
        Assert.Empty(estado.Grupos);
        Assert.Null(api.UltimoError);
    }

    [Fact]
    public async Task Registrar_un_estudiante_manda_nombres_documento_y_grupo_y_trae_el_pin_inicial()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.Created, """{"id":"u1","alias":"Juan Pérez","grupo_id":"g1","identificador":"AULA-PRUEBA-482913","secreto_inicial":"483920"}"""));
        var api = new PadronApi(new HttpClient(falso), Base);
        var e = await api.RegistrarEstudianteAsync("Juan", "Pérez", null, "g1");
        Assert.Equal("483920", e!.SecretoInicial);
        Assert.Equal("AULA-PRUEBA-482913", e.Identificador);
        var (metodo, ruta, cuerpo) = Assert.Single(falso.Peticiones);
        Assert.Equal(HttpMethod.Post, metodo);
        Assert.Equal("/api/acceso/padron/estudiantes/", ruta);
        Assert.Contains("\"nombres\":\"Juan\"", cuerpo);
        Assert.Contains("\"grupo_id\":\"g1\"", cuerpo);
        Assert.Contains("\"documento\":\"\"", cuerpo);
    }

    [Fact]
    public async Task Un_documento_repetido_devuelve_null_y_deja_el_motivo()
    {
        var api = new PadronApi(new HttpClient(new Falso((_, _) =>
            Json(HttpStatusCode.BadRequest, """{"detail":"El CODIGO_ESTUDIANTIL ya pertenece a otra persona.","codigo":"identificador_duplicado"}"""))), Base);
        Assert.Null(await api.RegistrarEstudianteAsync("Ana", "", "122499", "g1"));
        Assert.Equal("identificador_duplicado", api.UltimoError!.Codigo);
        Assert.Contains("ya pertenece", api.UltimoError.Detalle);
    }

    [Fact]
    public async Task Crear_un_grupo_manda_el_nombre_y_el_nivel_solo_si_se_eligio()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.Created, """{"id":"g1","codigo":"SEXTO-A","nombre":"Sexto A","periodo":"2026","nivel_clave":null}"""));
        var api = new PadronApi(new HttpClient(falso), Base);
        var g = await api.CrearGrupoAsync("Sexto A");
        Assert.Equal("SEXTO-A", g!.Codigo);
        Assert.Contains("\"nivel_clave\":null", falso.Peticiones[0].Cuerpo);
        await api.CrearGrupoAsync("Sexto A", "secundaria");
        Assert.Contains("\"nivel_clave\":\"secundaria\"", falso.Peticiones[1].Cuerpo);
    }

    [Fact]
    public async Task Matricular_y_retirar_usan_las_rutas_del_grupo_y_el_estudiante()
    {
        var falso = new Falso((r, _) => r.Method == HttpMethod.Delete ? new HttpResponseMessage(HttpStatusCode.NoContent) : Json(HttpStatusCode.Created, """{"grupo_id":"g 2","usuario_id":"u1","papel":"ESTUDIANTE","ya_estaba":false}"""));
        var api = new PadronApi(new HttpClient(falso), Base);
        Assert.True(await api.MatricularAsync("g 2", "u1"));
        Assert.True(await api.RetirarAsync("g 2", "u1"));
        Assert.Equal("/api/acceso/padron/grupos/g%202/estudiantes/", falso.Peticiones[0].Ruta);
        Assert.Equal("/api/acceso/padron/grupos/g%202/estudiantes/u1/", falso.Peticiones[1].Ruta);
    }

    [Fact]
    public async Task Preparar_el_aula_ya_instalada_es_false_con_su_motivo()
    {
        var api = new PadronApi(new HttpClient(new Falso((_, _) => Json(HttpStatusCode.Conflict, """{"detail":"El nodo ya está instalado.","codigo":"ya_instalado"}"""))), Base);
        Assert.False(await api.PrepararAulaDePruebaAsync());
        Assert.Equal("ya_instalado", api.UltimoError!.Codigo);
    }

    [Fact]
    public async Task Sin_red_el_estado_es_null_y_dice_que_no_hay_conexion()
    {
        var api = new PadronApi(new HttpClient(new Falso((_, _) => throw new HttpRequestException("sin red"))), Base);
        Assert.Null(await api.EstadoAsync());
        Assert.Equal("sin_conexion", api.UltimoError!.Codigo);
    }
}

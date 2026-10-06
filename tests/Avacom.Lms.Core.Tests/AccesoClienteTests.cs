using System.Net;
using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// El cliente de /api/acceso/ contra un backend falso (RF-10…RF-13 de los requisitos de acceso): rutas, cuerpos y lectura de cada llamada nueva —el PIN
/// maestro, el alta propia de profesores y alumnos, la lista de nombres, el visitante—, más cada código de rechazo del §C.4.3 con sus extras
/// (<c>reintentar_en_seg</c>, <c>intentos_restantes</c>, <c>sugerencia</c>).
/// </summary>
[Collection("registro-local")]   // comparte el pase (ClienteJson.Token) y el registro local con las otras pruebas que los tocan
public sealed class AccesoClienteTests : IDisposable
{
    private static readonly Uri Base = new("http://127.0.0.1:8000/");

    private sealed class Falso(Func<HttpRequestMessage, string?, HttpResponseMessage> responder) : HttpMessageHandler
    {
        public List<(HttpMethod Metodo, string Ruta, string? Cuerpo, string? Autorizacion)> Peticiones { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            var cuerpo = request.Content is null ? null : await request.Content.ReadAsStringAsync(ct);
            Peticiones.Add((request.Method, request.RequestUri!.PathAndQuery, cuerpo, request.Headers.Authorization?.ToString()));
            return responder(request, cuerpo);
        }
    }

    private static HttpResponseMessage Json(HttpStatusCode estado, string json) =>
        new(estado) { Content = new StringContent(json, Encoding.UTF8, "application/json") };

    private static AccesoApi Api(Falso falso) => new(new HttpClient(falso), Base);

    private const string SesionJson = """
        {"token":"JWT-1","tipo":"Bearer","expira_en":1800000000000,"sesion_id":"s1","inactividad_min":30,"sesion_anterior":null,
         "usuario":{"id":"u1","alias":"Juan P.","rol":"STUDENT","menu":"student","nivel":1,"debe_cambiar_credencial":false,"clase_sesion":"NORMAL",
                    "provisional":false,"origen":"AUTOALTA_ALUMNO","confirmado":false}}
        """;

    public AccesoClienteTests() => ClienteJson.Token = null;
    public void Dispose() => ClienteJson.Token = null;

    // ------------------------------------------------------------------------------------------------------------- configuración

    [Fact]
    public async Task La_configuracion_trae_el_estado_publico_del_pin_y_las_puertas_de_entrada()
    {
        var api = Api(new Falso((_, _) => Json(HttpStatusCode.OK, """
            {"instalado":true,"sesion_obligatoria":true,"pin_maestro":{"configurado":true,"vencido":false,"por_vencer":true},
             "autoregistro_alumnos":true,"autoregistro_docentes":true,"visitante":true}
            """)));
        var c = await api.ConfiguracionAsync();
        Assert.NotNull(c);
        Assert.True(c.Instalado);
        Assert.True(c.PinMaestro!.Configurado);
        Assert.True(c.PinMaestro.PorVencer);
        Assert.True(c.AutoregistroAlumnos && c.Visitante);
        Assert.True(c.OfreceRegistroDeProfesores);
    }

    [Fact]
    public async Task Sin_pin_maestro_configurado_el_registro_de_profesores_no_se_ofrece()
    {
        var api = Api(new Falso((_, _) => Json(HttpStatusCode.OK, """{"instalado":true,"sesion_obligatoria":true,"pin_maestro":{"configurado":false},"autoregistro_docentes":true}""")));
        Assert.False((await api.ConfiguracionAsync())!.OfreceRegistroDeProfesores);
    }

    [Fact]
    public async Task Un_nodo_anterior_sin_los_campos_nuevos_se_lee_con_las_puertas_cerradas()
    {
        var api = Api(new Falso((_, _) => Json(HttpStatusCode.OK, """{"instalado":true,"sesion_obligatoria":false}""")));
        var c = (await api.ConfiguracionAsync())!;
        Assert.Null(c.PinMaestro);
        Assert.False(c.Visitante);
        Assert.False(c.AutoregistroAlumnos);
        Assert.False(c.OfreceRegistroDeProfesores);
    }

    // ------------------------------------------------------------------------------------------------------------- iniciar sesión

    [Fact]
    public async Task Iniciar_sesion_manda_documento_y_clave_y_guarda_el_pase_sin_pin_maestro()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, SesionJson));
        var api = Api(falso);
        var sesion = await api.IniciarSesionAsync("80123456", "clave", "ops-PC");
        Assert.Equal("JWT-1", ClienteJson.Token);
        Assert.Equal("Juan P.", sesion!.Usuario.Alias);
        Assert.False(sesion.Usuario.EsVisitante);
        Assert.False(sesion.Usuario.Confirmado);
        var (_, ruta, cuerpo, _) = Assert.Single(falso.Peticiones);
        Assert.Equal("/api/acceso/sesiones/", ruta);
        Assert.DoesNotContain("pin_maestro", cuerpo);
        Assert.DoesNotContain("usuario_id", cuerpo);
    }

    [Fact]
    public async Task La_administracion_manda_ademas_el_pin_maestro()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, SesionJson));
        await Api(falso).IniciarSesionAsync("1042888795", "clave", "ops-PC", pinMaestro: "482915");
        Assert.Contains("\"pin_maestro\":\"482915\"", falso.Peticiones[0].Cuerpo);
    }

    [Fact]
    public async Task Si_el_nodo_pide_el_pin_maestro_lo_dice_con_su_codigo_y_no_deja_pase()
    {
        var api = Api(new Falso((_, _) => Json(HttpStatusCode.Unauthorized, """{"detail":"La administración entra además con el PIN maestro.","codigo":"pin_maestro_requerido"}""")));
        Assert.Null(await api.IniciarSesionAsync("1042888795", "clave", "ops-PC"));
        Assert.True(api.UltimoError!.PinMaestroRequerido);
        Assert.Null(ClienteJson.Token);
    }

    [Fact]
    public async Task El_alumno_entra_tocando_su_nombre_con_su_pin()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, SesionJson));
        var sesion = await Api(falso).IniciarSesionAlumnoAsync("u1", "1234", "student-TAB");
        Assert.Equal("JWT-1", ClienteJson.Token);
        Assert.NotNull(sesion);
        var (metodo, ruta, cuerpo, _) = Assert.Single(falso.Peticiones);
        Assert.Equal(HttpMethod.Post, metodo);
        Assert.Equal("/api/acceso/sesiones/", ruta);
        Assert.Contains("\"usuario_id\":\"u1\"", cuerpo);
        Assert.Contains("\"secreto\":\"1234\"", cuerpo);
        Assert.Contains("\"dispositivo\":\"student-TAB\"", cuerpo);
        Assert.DoesNotContain("identificador", cuerpo);
    }

    [Fact]
    public async Task Un_login_nuevo_no_viaja_con_el_pase_de_la_sesion_anterior()
    {
        ClienteJson.Token = "VIEJO";
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, SesionJson));
        await Api(falso).IniciarSesionAlumnoAsync("u1", "1234", "student-TAB");
        Assert.Null(falso.Peticiones[0].Autorizacion);
    }

    [Fact]
    public async Task El_visitante_entra_sin_clave_y_su_sesion_se_reconoce()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, """
            {"token":"JWT-V","expira_en":1800000000000,"sesion_id":"sv","usuario":{"id":"v1","alias":"Visitante · tableta-07","rol":"STUDENT","menu":"student",
             "nivel":1,"clase_sesion":"VISITANTE","provisional":true,"origen":"VISITANTE","confirmado":false}}
            """));
        var sesion = await Api(falso).EntrarComoVisitanteAsync("student-TAB");
        Assert.True(sesion!.Usuario.EsVisitante);
        Assert.Equal("JWT-V", ClienteJson.Token);
        var (_, ruta, cuerpo, _) = Assert.Single(falso.Peticiones);
        Assert.Equal("/api/acceso/sesiones/visitante/", ruta);
        Assert.Equal("""{"dispositivo":"student-TAB"}""", cuerpo);
    }

    [Fact]
    public async Task El_visitante_puede_decir_a_que_grupo_se_une()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, SesionJson));
        await Api(falso).EntrarComoVisitanteAsync("student-TAB", "g1");
        Assert.Contains("\"grupo_id\":\"g1\"", falso.Peticiones[0].Cuerpo);
    }

    // ------------------------------------------------------------------------------------------------------------- primer arranque

    [Fact]
    public async Task El_primer_arranque_manda_el_aula_el_administrador_y_el_pin_maestro_y_trae_la_hoja_de_acceso()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.Created, """
            {"organizacion":{"codigo":"IE-1","nombre":"IE Uno"},"administrador":{"id":"a1","alias":"Administración"},"password_inicial":"Gx9.kLm2!pQrs"}
            """));
        var hecho = await Api(falso).InstalarAsync(new DatosDeInstalacion("IE-1", "IE Uno", "CO", "es", "America/Bogota", "1042888795", "Ana", "Pérez", "482915"));
        Assert.Equal("Gx9.kLm2!pQrs", hecho!.PasswordInicial);
        Assert.Equal("a1", hecho.Administrador.Id);
        var (_, ruta, cuerpo, _) = Assert.Single(falso.Peticiones);
        Assert.Equal("/api/acceso/instalacion/", ruta);
        using var doc = JsonDocument.Parse(cuerpo!);
        Assert.Equal("482915", doc.RootElement.GetProperty("pin_maestro").GetString());
        Assert.Equal("es-CO", doc.RootElement.GetProperty("organizacion").GetProperty("locale").GetString());
        Assert.Equal("1042888795", doc.RootElement.GetProperty("administrador").GetProperty("dni").GetString());
        Assert.Equal(string.Empty, doc.RootElement.GetProperty("administrador").GetProperty("password").GetString());   // el nodo genera la contraseña inicial
    }

    [Fact]
    public async Task Un_pin_trivial_en_la_instalacion_se_rechaza_con_su_codigo()
    {
        var api = Api(new Falso((_, _) => Json(HttpStatusCode.BadRequest, """{"detail":"Ese PIN es demasiado fácil de adivinar.","codigo":"pin_debil"}""")));
        Assert.Null(await api.InstalarAsync(new DatosDeInstalacion("IE-1", "IE Uno", "CO", "es", "America/Bogota", "1", "Ana", "", "123456")));
        Assert.Equal("pin_debil", api.UltimoError!.Codigo);
    }

    // ------------------------------------------------------------------------------------------------------------- PIN maestro

    [Fact]
    public async Task El_estado_del_pin_trae_fechas_y_dias_pero_nunca_el_pin()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, """
            {"configurado":true,"creado_en":1790000000000,"vence_en":1821536000000,"dias_restantes":28,"vencido":false,"aviso":true,"bloqueado_hasta":null}
            """));
        var e = await Api(falso).EstadoPinMaestroAsync();
        Assert.Equal(28, e!.DiasRestantes);
        Assert.True(e.Aviso);
        Assert.False(e.Vencido);
        Assert.NotNull(e.VenceEl);
        Assert.Equal(HttpMethod.Get, falso.Peticiones[0].Metodo);
        Assert.Equal("/api/acceso/pin-maestro/", falso.Peticiones[0].Ruta);
    }

    [Fact]
    public async Task Cambiar_el_pin_maestro_es_un_PUT_con_el_pin_nuevo()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, """{"creado_en":1790000000000,"vence_en":1821536000000,"dias_restantes":365}"""));
        var r = await Api(falso).CambiarPinMaestroAsync("739104");
        Assert.Equal(365, r!.DiasRestantes);
        var (metodo, ruta, cuerpo, _) = Assert.Single(falso.Peticiones);
        Assert.Equal(HttpMethod.Put, metodo);
        Assert.Equal("/api/acceso/pin-maestro/", ruta);
        Assert.Equal("""{"pin_nuevo":"739104"}""", cuerpo);
    }

    [Fact]
    public async Task Un_pin_nuevo_que_ya_se_uso_se_rechaza_como_debil()
    {
        var api = Api(new Falso((_, _) => Json(HttpStatusCode.BadRequest, """{"detail":"Ese PIN ya se usó hace poco.","codigo":"pin_debil"}""")));
        Assert.Null(await api.CambiarPinMaestroAsync("482915"));
        Assert.Equal("pin_debil", api.UltimoError!.Codigo);
    }

    // ------------------------------------------------------------------------------------------------------------- profesores

    [Fact]
    public async Task Registrar_un_docente_manda_el_pin_los_grupos_y_el_equipo()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.Created, """{"id":"d1","alias":"Marta Ríos"}"""));
        var d = await Api(falso).RegistrarDocenteAsync(new RegistroDeDocente("482915", "52100200", "Marta", "Ríos", "Profe.Nuevo.2026!", ["g1", "g2"], "ops-PC"));
        Assert.Equal("Marta Ríos", d!.Alias);
        var (metodo, ruta, cuerpo, _) = Assert.Single(falso.Peticiones);
        Assert.Equal(HttpMethod.Post, metodo);
        Assert.Equal("/api/acceso/docentes/registro/", ruta);
        using var doc = JsonDocument.Parse(cuerpo!);
        Assert.Equal("482915", doc.RootElement.GetProperty("pin_maestro").GetString());
        Assert.Equal(["g1", "g2"], doc.RootElement.GetProperty("grupos").EnumerateArray().Select(x => x.GetString()!).ToArray());
        Assert.Equal("ops-PC", doc.RootElement.GetProperty("dispositivo").GetString());
    }

    [Fact]
    public async Task Un_pin_equivocado_deja_los_intentos_que_quedan()
    {
        var api = Api(new Falso((_, _) => Json(HttpStatusCode.Unauthorized, """{"detail":"Ese PIN no es. Te quedan 3 intentos.","codigo":"pin_maestro_invalido","intentos_restantes":3}""")));
        Assert.Null(await api.RegistrarDocenteAsync(new RegistroDeDocente("906531", "1", "A", "", "x", [], "ops-PC")));
        Assert.True(api.UltimoError!.PinMaestroInvalido);
        Assert.Equal(3, api.UltimoError.IntentosRestantes);
    }

    [Fact]
    public async Task Restablecer_la_contrasena_devuelve_las_sesiones_cerradas()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, """{"sesiones_revocadas":2}"""));
        var cerradas = await Api(falso).RestablecerContrasenaDocenteAsync("482915", "80123456", "Nueva.Clave.2026!", "ops-PC");
        Assert.Equal(2, cerradas);
        var (_, ruta, cuerpo, _) = Assert.Single(falso.Peticiones);
        Assert.Equal("/api/acceso/docentes/restablecer/", ruta);
        Assert.Contains("\"secreto_nuevo\":\"Nueva.Clave.2026!\"", cuerpo);
    }

    [Fact]
    public async Task Restablecer_con_un_documento_que_no_es_de_profesor_deja_el_motivo()
    {
        var api = Api(new Falso((_, _) => Json(HttpStatusCode.NotFound, """{"detail":"No encontramos un profesor con ese documento.","codigo":"no_encontrado"}""")));
        Assert.Null(await api.RestablecerContrasenaDocenteAsync("482915", "999", "x", "ops-PC"));
        Assert.Equal(404, api.UltimoError!.Estado);
    }

    [Fact]
    public async Task La_lista_de_docentes_registrados_con_el_pin_trae_equipo_y_grupos()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, """
            [{"id":"d1","alias":"Marta Ríos","estado":"ACTIVO","origen":"PIN_MAESTRO","registrado_en":1790000000000,"confirmado":false,
              "equipo":"ops-sala-docentes","equipo_id":"e1","grupos":[{"id":"g1","nombre":"Octavo A"}]}]
            """));
        var lista = await Api(falso).ListarDocentesPorPinMaestroAsync();
        var d = Assert.Single(lista!);
        Assert.Equal("ops-sala-docentes", d.Equipo);
        Assert.Equal("Octavo A", d.Grupos![0].Nombre);
        Assert.False(d.Suspendido);
        Assert.Equal("/api/acceso/docentes/?origen=PIN_MAESTRO", falso.Peticiones[0].Ruta);
    }

    [Fact]
    public async Task Suspender_a_un_profesor_es_un_PATCH_con_el_estado()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, """{"id":"d1","estado":"SUSPENDIDO"}"""));
        Assert.True(await Api(falso).CambiarEstadoDeUsuarioAsync("d1", "SUSPENDIDO"));
        var (metodo, ruta, cuerpo, _) = Assert.Single(falso.Peticiones);
        Assert.Equal(HttpMethod.Patch, metodo);
        Assert.Equal("/api/acceso/usuarios/d1/", ruta);
        Assert.Equal("""{"estado":"SUSPENDIDO"}""", cuerpo);
    }

    // ------------------------------------------------------------------------------------------------------------- alumnos

    [Fact]
    public async Task La_lista_de_grupos_se_pide_con_la_huella_de_la_tableta_y_trae_el_tipo_de_clave()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, """
            [{"id":"g1","codigo":"8A","nombre":"Octavo A","nivel_clave":"secundaria","tipo_secreto":"PIN","longitud_pin":4,"alumnos":12,"registro_abierto":true},
             {"id":"g2","codigo":"TR","nombre":"Transición","nivel_clave":"preescolar","tipo_secreto":"AVATAR","longitud_pin":4,"alumnos":0,"registro_abierto":true}]
            """));
        var grupos = await Api(falso).ListarGruposDelAulaAsync("student-TAB 1");
        Assert.Equal(2, grupos!.Count);
        Assert.False(grupos[0].UsaAvatar);
        Assert.True(grupos[1].UsaAvatar);
        Assert.Equal(4, grupos[0].LongitudPin);
        Assert.Equal("/api/acceso/aula/grupos/?dispositivo=student-TAB%201", falso.Peticiones[0].Ruta);
    }

    [Fact]
    public async Task El_profesor_pide_todos_los_grupos_activos()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, "[]"));
        await Api(falso).ListarGruposDelAulaAsync("ops-PC", paraDocente: true);
        Assert.Equal("/api/acceso/aula/grupos/?dispositivo=ops-PC&para=docente", falso.Peticiones[0].Ruta);
    }

    [Fact]
    public async Task La_lista_de_nombres_trae_el_alias_y_si_falta_el_pin_y_nada_mas()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, """[{"id":"u1","alias":"Juan P.","pin_pendiente":false},{"id":"u2","alias":"Luisa","pin_pendiente":true}]"""));
        var lista = await Api(falso).ListarEstudiantesDelGrupoAsync("g1", "student-TAB");
        Assert.Equal(["Juan P.", "Luisa"], lista!.Select(a => a.Alias).ToArray());
        Assert.True(lista![1].PinPendiente);
        Assert.Equal("/api/acceso/aula/grupos/g1/estudiantes/?dispositivo=student-TAB", falso.Peticiones[0].Ruta);
    }

    [Fact]
    public async Task Una_tableta_no_registrada_no_ve_la_lista_y_lo_dice()
    {
        var api = Api(new Falso((_, _) => Json(HttpStatusCode.Forbidden, """{"detail":"Esta tableta no está registrada en el aula.","codigo":"dispositivo_no_autorizado"}""")));
        Assert.Null(await api.ListarGruposDelAulaAsync("student-TAB"));
        Assert.True(api.UltimoError!.DispositivoNoAutorizado);
    }

    [Fact]
    public async Task El_alta_propia_del_alumno_manda_grupo_nombre_y_pin()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.Created, """{"id":"u9","alias":"Pedro G."}"""));
        var a = await Api(falso).RegistrarEstudianteAsync(new RegistroDeAlumno("g1", "Pedro", "Gómez", null, "1234", "student-TAB"));
        Assert.Equal("Pedro G.", a!.Alias);
        var (_, ruta, cuerpo, _) = Assert.Single(falso.Peticiones);
        Assert.Equal("/api/acceso/estudiantes/registro/", ruta);
        using var doc = JsonDocument.Parse(cuerpo!);
        Assert.Equal("g1", doc.RootElement.GetProperty("grupo_id").GetString());
        Assert.Equal("1234", doc.RootElement.GetProperty("pin").GetString());
        Assert.Equal("Gómez", doc.RootElement.GetProperty("apellidos").GetString());
    }

    [Fact]
    public async Task Un_alias_repetido_trae_la_sugerencia_de_una_letra_mas()
    {
        var api = Api(new Falso((_, _) => Json(HttpStatusCode.Conflict,
            """{"detail":"Ya hay alguien llamado Juan P. en este grupo. Añade una letra: Juan Pé.","codigo":"alias_duplicado","alias":"Juan P.","sugerencia":"Juan Pé."}""")));
        Assert.Null(await api.RegistrarEstudianteAsync(new RegistroDeAlumno("g1", "Juan", "Pérez", null, "1234", "student-TAB")));
        Assert.True(api.UltimoError!.AliasDuplicado);
        Assert.Equal("Juan Pé.", api.UltimoError.Sugerencia);
        Assert.Equal("Juan P.", api.UltimoError.Texto("alias"));
    }

    [Fact]
    public async Task Elegir_el_pin_pendiente_es_un_POST_a_la_cuenta_del_alumno()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, """{"id":"u1","alias":"Juan P."}"""));
        Assert.True(await Api(falso).EstablecerPinAlumnoAsync("u1", "4321", "student-TAB"));
        var (_, ruta, cuerpo, _) = Assert.Single(falso.Peticiones);
        Assert.Equal("/api/acceso/estudiantes/u1/pin/", ruta);
        Assert.Contains("\"pin\":\"4321\"", cuerpo);
    }

    [Fact]
    public async Task Tocar_el_nombre_de_un_alumno_sin_pin_se_dice_como_pin_pendiente()
    {
        var api = Api(new Falso((_, _) => Json(HttpStatusCode.Forbidden, """{"detail":"Todavía no tienes PIN.","codigo":"pin_pendiente","usuario_id":"u1"}""")));
        Assert.Null(await api.IniciarSesionAlumnoAsync("u1", "1234", "student-TAB"));
        Assert.True(api.UltimoError!.PinPendiente);
        Assert.Null(ClienteJson.Token);
    }

    [Fact]
    public async Task Una_tableta_en_pausa_dice_cuanto_falta_y_su_codigo()
    {
        var api = Api(new Falso((_, _) => Json((HttpStatusCode)423, """{"detail":"Esperemos un momento.","codigo":"dispositivo_en_pausa","reintentar_en_seg":87}""")));
        Assert.Null(await api.IniciarSesionAlumnoAsync("u1", "0000", "student-TAB"));
        Assert.True(api.UltimoError!.DispositivoEnPausa);
        Assert.Equal(87, api.UltimoError.ReintentarEnSeg);
    }

    [Fact]
    public async Task El_profesor_confirma_a_un_alumno_y_ve_a_los_visitantes()
    {
        var falso = new Falso((req, _) => req.RequestUri!.AbsolutePath.EndsWith("/visitantes/")
            ? Json(HttpStatusCode.OK, """[{"usuario_id":"v1","alias":"Visitante · tableta-07","sesion_id":"s1","dispositivo_id":"e1","dispositivo":"tableta-07","emitida_en":1790000000000}]""")
            : Json(HttpStatusCode.OK, """{"id":"u1","confirmado_en":1790000000000}"""));
        var api = Api(falso);
        var c = await api.ConfirmarUsuarioAsync("u1");
        Assert.NotNull(c!.ConfirmadoEn);
        var visitas = await api.ListarVisitantesAsync();
        Assert.Equal("tableta-07", Assert.Single(visitas!).Dispositivo);
        Assert.Equal("/api/acceso/usuarios/u1/confirmar/", falso.Peticiones[0].Ruta);
    }

    [Fact]
    public async Task Vincular_una_visita_a_un_alumno_manda_el_usuario_definitivo()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, """{"provisional_id":"v1","definitivo_id":"u1","sesiones_revocadas":0}"""));
        Assert.True(await Api(falso).VincularVisitanteAsync("v1", "u1"));
        var (_, ruta, cuerpo, _) = Assert.Single(falso.Peticiones);
        Assert.Equal("/api/acceso/usuarios/v1/vincular/", ruta);
        Assert.Equal("""{"usuario_definitivo_id":"u1"}""", cuerpo);
    }

    [Fact]
    public async Task Apagar_el_registro_o_los_visitantes_es_un_PUT_a_la_politica_del_perfil()
    {
        var falso = new Falso((_, _) => Json(HttpStatusCode.OK, """{"perfil":"student","autoregistro":false,"bloqueo_alcance":"DISPOSITIVO","visitante":true}"""));
        var p = await Api(falso).ConfigurarPoliticaAsync("student", new { autoregistro = false });
        Assert.False(p!.Autoregistro);
        Assert.True(p.Visitante);
        var (metodo, ruta, cuerpo, _) = Assert.Single(falso.Peticiones);
        Assert.Equal(HttpMethod.Put, metodo);
        Assert.Equal("/api/acceso/politicas/student/", ruta);
        Assert.Equal("""{"autoregistro":false}""", cuerpo);
    }

    // ------------------------------------------------------------------------------------------------------------- errores de red y de sesión

    [Fact]
    public async Task Sin_conexion_ninguna_llamada_simula_un_acceso()
    {
        var api = Api(new Falso((_, _) => throw new HttpRequestException("sin red")));
        Assert.Null(await api.IniciarSesionAlumnoAsync("u1", "1234", "student-TAB"));
        Assert.Null(await api.EntrarComoVisitanteAsync("student-TAB"));
        Assert.Null(await api.ListarGruposDelAulaAsync("student-TAB"));
        Assert.Null(await api.RegistrarEstudianteAsync(new RegistroDeAlumno("g", "A", null, null, "1234", "d")));
        Assert.Equal(0, api.UltimoError!.Estado);
        Assert.Null(ClienteJson.Token);
    }

    // ------------------------------------------------------------------------------------------------------------- autorización de salida con PIN

    [Fact]
    public async Task La_autorizacion_de_salida_pide_el_pin_maestro_cuando_quien_autoriza_es_de_administracion()
    {
        var falso = new Falso((_, cuerpo) => cuerpo!.Contains("pin_maestro")
            ? Json(HttpStatusCode.OK, SesionJson.Replace("\"id\":\"u1\"", "\"id\":\"admin2\""))
            : Json(HttpStatusCode.Unauthorized, """{"detail":"La administración entra además con el PIN maestro.","codigo":"pin_maestro_requerido"}"""));
        var api = Api(falso);
        var primera = await AutorizacionDeSalida.ConcederAsync(api, "yo", "ops-PC", "52000111", "Coordina.2026!Aula", "Inspección interna");
        Assert.False(primera.Ok);
        Assert.True(primera.RequierePinMaestro);
        Assert.Null(ClienteJson.Token);   // el pase de quien usa el equipo vuelve siempre (aquí no había)
    }
}

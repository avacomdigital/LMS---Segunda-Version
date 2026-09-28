using System.Net;
using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>El cliente de /api/aula/ contra un backend falso: contratos, degradación y códigos de negocio.</summary>
public sealed class AulaApiTests
{
    private const string VistaCursoJson = """
        {"fuente":"ejemplo","esquema":"1.0","curso_ref":"avacom.co.lower-secondary.6.science.states-of-matter","version":"1.0.0",
         "titulo":"Estados de la materia y sus cambios","subtitulo":"Sólido, líquido, gas","idioma":"es-CO",
         "clasificacion":{"pais":"CO","idioma":"es-CO","nivel":{"codigo":"lower_secondary","nombre":"Básica secundaria","orden":2},
                          "grado":{"codigo":"6","nombre":"Sexto","orden":6},"asignatura":{"codigo":"science","nombre":"Ciencias naturales"},"tema":null},
         "duracion_estimada_min":180,"modos":["class"],"portada_url":"/api/aula/cursos/x/medios/img-cover-matter/?fuente=ejemplo","rol":"docente",
         "medios":[{"media_ref":"sim-heating-curve","clase":"simulation","componente":"webview","titulo":"Curva","mime":"text/html",
                    "url":"/api/aula/cursos/x/medios/sim-heating-curve/index.html?fuente=ejemplo","base_url":"/api/aula/cursos/x/medios/sim-heating-curve/?fuente=ejemplo",
                    "simulacion":{"entrada":"index.html","proveedor":"avacom","tecnologia":"html5_canvas","orientacion":"landscape","ajustes":["scale_to_fit","block_network"],"destinos":["screen","tablet"],"ancho_diseno":1280,"alto_diseno":720},
                    "licencia":{"tipo":"avacom","atribucion":null,"fuente_url":null},"ausente":false}],
         "lecciones":[{"leccion_ref":"l1","titulo":"Los tres estados","resumen":"r","objetivos":["a"],"duracion_estimada_min":90,"modos":["class"],
            "objetos":[
              {"objeto_ref":"l1-lecture","tipo":"lecture","componente":"presentacion","titulo":"Todo es materia","modos":["class"],"tema_ref":"t","duracion_estimada_seg":1200,"fuera_de_alcance":false,"modulo":"MOD-007",
               "total_unidades":1,"laminas":[{"unidad_ref":"s1","indice":1,"titulo":"Qué es la materia","duracion_seg":240,
                 "bloques":[{"tipo":"heading","componente":"titulo","texto":"Qué es","nivel":1,"tramos":[{"texto":"Qué es","negrita":false}]},
                            {"tipo":"text","componente":"texto","texto":"**Materia** es","estilo":"definition","tramos":[{"texto":"Materia","negrita":true},{"texto":" es","negrita":false}]},
                            {"tipo":"video","componente":"video","media_ref":"vid","url":"/api/aula/cursos/x/medios/vid/?fuente=ejemplo","pie":"p","desde_seg":0,"hasta_seg":60,"autoplay":false,"duracion_seg":150.0,"subtitulos_url":"/s","transcripcion_url":"/t"}]}]},
              {"objeto_ref":"l1-lab","tipo":"simulation_lab","componente":"laboratorio_web","titulo":"Lab","modos":["class"],"fuera_de_alcance":false,"modulo":"MOD-007",
               "url_lanzamiento":"/api/aula/cursos/x/medios/sim-heating-curve/index.html?fuente=ejemplo&startTemp=-10","parametros_lanzamiento":{"startTemp":-10,"altitudeMeters":0},"pasos":["a","b"],"preguntas_guia":["q"]},
              {"objeto_ref":"l1-act","tipo":"activity","componente":"actividad","titulo":"Practica","modos":["class"],"fuera_de_alcance":false,"modulo":"MOD-007",
               "ajustes":{"retroalimentacion":"immediate","intentos_permitidos":2,"barajar_preguntas":false,"barajar_opciones":true,"tiempo_limite_seg":300},"puntos_totales":3.5,
               "preguntas":[{"pregunta_ref":"q1","tipo":"multiple_choice","componente":"opcion_multiple","enunciado":"¿Cuál *pesa* más? $2 \\times 3$","puntos":1.5,"credito_parcial":false,"permite_varias":false,
                             "enunciado_tramos":[{"texto":"¿Cuál ","negrita":false,"cursiva":false,"matematica":false},{"texto":"pesa","negrita":false,"cursiva":true,"matematica":false},{"texto":" más? ","negrita":false,"cursiva":false,"matematica":false},{"texto":"2 × 3","negrita":false,"cursiva":false,"matematica":true}],
                             "medios":[{"media_ref":"img-vaso","clase":"image","componente":"imagen","url":"/api/aula/cursos/x/medios/img-vaso/?fuente=ejemplo","texto_alternativo":"Un vaso","ausente":false}],
                             "opciones":[{"opcion_ref":"a","texto":"El aire","media_ref":null,"url":null},{"opcion_ref":"b","texto":null,"media_ref":"img-leche","url":"/api/aula/cursos/x/medios/img-leche/?fuente=ejemplo","texto_alternativo":"Leche"}]},
                            {"pregunta_ref":"q3","tipo":"fill_blanks","componente":"completar","enunciado":"Completa.","puntos":2,"credito_parcial":true,"plantilla":"Un líquido tiene volumen {{b1}}",
                             "espacios":[{"espacio_ref":"b1","modo_entrada":"select","opciones":["propio","variable"]}]}]},
              {"objeto_ref":"l3-exam","tipo":"exam","componente":"examen","titulo":"Examen","modos":["exam"],"fuera_de_alcance":true,"modulo":"MOD-010","preguntas":[],"total_preguntas_banco":12}]}],
         "resumen":{"lecciones":1,"objetos":4,"medios":1,"preguntas":2},
         "notas_docente":{"summary":"Curso de cuatro sesiones.","tips":["Parta de lo que ven en casa."]}}
        """;

    private const string EstadoTabletaJson = """
        {"sesion":{"id":"s1","estado":"abierta","fuente_curso":"ejemplo","curso_ref":"c","curso_rotulo":"Estados","leccion_ref":"l1","leccion_rotulo":"Los tres estados","grupo_rotulo":"","profesor_rotulo":"Prof. Gómez"},
         "activa":true,
         "participante":{"id":"p1","persona_id":"ana","persona_rotulo":"Ana Pérez","dispositivo":"tab","dispositivo_id":"d-1","dispositivo_bloqueado":true,"estado":"conectado","admision_nominal":false,"ingreso":1,"ultimo_latido_en":2},
         "selector":{"id":"f","curso_ref":"c","leccion_ref":"l1","objeto_ref":"l1-lecture","objeto_tipo":"lecture","unidad_ref":"s2","unidad_indice":2,"media_ref":"","rotulo":"Tres estados","declarado_en":3},
         "seguimiento":true,"pantallas_bloqueadas":true,
         "pendientes":[{"id":"d1","clase":"actividad","objeto_ref":"l1-act","objeto_tipo":"activity","rotulo":"Practica","alcance":"seleccion","destinatarios":["ana"],"excluidos_bloqueados":["luis"],"intentos_permitidos":2,"tiempo_limite_seg":600,"disponible_estudio":false,"abierta_en":4,"cerrada_en":null,"entrega":"pendiente"}],
         "avisos":[{"id":"a1","participante_id":null,"texto":"Miren al frente","enviado_en":5}],
         "servidor_en":6,"intervalo_sondeo_ms":2000,"nuevo":true,"en_espera":false}
        """;

    private const string SesionJson = """
        {"id":"s1","estado":"abierta","activa":true,"codigo_union":"613385","via_origen":"leccion","fuente_curso":"ejemplo","curso_ref":"c","curso_rotulo":"Estados","leccion_ref":"l1","leccion_rotulo":"Los tres estados",
         "selector":{"id":"f","objeto_ref":"l1-lecture","objeto_tipo":"lecture","unidad_ref":"","rotulo":"Todo","declarado_en":1},"seguimiento":true,"pantallas_bloqueadas":false,
         "participantes":[],"conteo":{"total":0,"conectados":0,"reconectando":0,"esperando":0,"salieron":0},"distribuciones":[],"avisos":[],"resumen":null,"servidor_en":2}
        """;

    private const string DispositivosJson = """
        [{"id":"d-1","organizacion_id":"o","identificador_hw":"student-TAB07","identificador":"student-TAB07","nombre":"Tableta 07","tipo":"TABLETA","plataforma":"android","version_app":"0.4.2",
          "activo":true,"bloqueado":true,"registrado_en":1,"ultimo_latido_en":2,"en_linea":false,"sesion_abierta":{"id":"s","alumno_id":"ana","iniciada_en":3}},
         {"id":"d-2","organizacion_id":"o","identificador_hw":"hw-2","identificador":"hw-2","nombre":"","tipo":"TABLETA","plataforma":"","version_app":"",
          "activo":true,"bloqueado":false,"registrado_en":1,"ultimo_latido_en":2,"en_linea":true,"sesion_abierta":null}]
        """;

    [Fact]
    public void VistaCurso_SeDeserializaConComponentesYTramos()
    {
        var vista = JsonSerializer.Deserialize<VistaCurso>(VistaCursoJson, new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
        Assert.Equal("Ciencias naturales", vista.Clasificacion!.Asignatura!.Nombre);
        var leccion = vista.Lecciones[0];
        Assert.Equal(["presentacion", "laboratorio_web", "actividad", "examen"], leccion.Objetos!.Select(o => o.Componente).ToArray());
        Assert.Equal(3, leccion.ObjetosDelAula.Count);
        var lamina = leccion.Objetos![0].Unidades[0];
        Assert.Equal("Materia", lamina.Bloques[1].Tramos![0].Texto);
        Assert.True(lamina.Bloques[1].Tramos![0].Negrita);
        Assert.Equal(60, lamina.Bloques[2].HastaSeg);
        var lab = leccion.Objetos[1];
        Assert.Equal(-10, lab.ParametrosLanzamiento!["startTemp"].GetInt32());
        Assert.True(vista.Medios![0].Simulacion!.EscalaAlViewport);
        Assert.True(vista.Medios![0].Simulacion!.SirveEnTableta);
        var actividad = leccion.Objetos[2];
        Assert.Equal("Opción múltiple", actividad.Preguntas![0].TipoLegible);
        Assert.Equal(["propio", "variable"], actividad.Preguntas![1].Espacios![0].Opciones!.ToArray());
        // Esquema 1.0: `points` es decimal, las preguntas traen medios, las opciones pueden ser imagen y
        // los tramos llevan cursiva y matemática (opcionales: un tramo sólo con `negrita` sigue valiendo).
        Assert.Equal(3.5, actividad.PuntosTotales);
        Assert.Equal(300, actividad.Ajustes!.TiempoLimiteSeg);
        var pregunta = actividad.Preguntas[0];
        Assert.Equal(1.5, pregunta.Puntos);
        Assert.Equal("img-vaso", pregunta.Medios![0].MediaRef);
        Assert.True(pregunta.EnunciadoTramos![1].Cursiva);
        Assert.True(pregunta.EnunciadoTramos![3].Matematica);
        Assert.Equal("2 × 3", pregunta.EnunciadoTramos![3].Texto);
        Assert.Null(pregunta.Opciones![0].Url);
        Assert.Equal("img-leche", pregunta.Opciones![1].MediaRef);
        Assert.False(lamina.Bloques[1].Tramos![0].Cursiva);
        Assert.True(vista.Objeto("l3-exam")!.FueraDeAlcance);
        Assert.Contains("Curso de cuatro sesiones.", vista.NotasDocente!.Lineas());
    }

    [Fact]
    public void EstadoTableta_SeDeserializaConSelectorPendientesYAvisos()
    {
        var estado = JsonSerializer.Deserialize<EstadoTableta>(EstadoTabletaJson, new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
        Assert.True(estado.Activa);
        Assert.True(estado.PantallasBloqueadas);
        Assert.Equal("s2", estado.Selector!.UnidadRef);
        Assert.Equal("AP", estado.Participante!.Iniciales);
        Assert.True(estado.Participante.Admitido);
        Assert.True(estado.Participante.TieneTableta);
        Assert.True(estado.Participante.TabletaBloqueada);
        var pendiente = estado.Pendientes![0];
        Assert.Equal("pendiente", pendiente.Entrega);
        Assert.True(pendiente.EstaAbierta);
        Assert.Equal(["ana"], pendiente.Destinatarios!.ToArray());
        Assert.Equal(1, pendiente.Excluidos);
        Assert.Equal("2 intentos · 10 min", pendiente.ReglasTexto);
        Assert.Equal(2000, estado.IntervaloSondeoMs);
    }

    [Fact]
    public async Task DispositivosApi_ListaElInventarioYBloqueaPorLaRutaDeMod009()
    {
        var urls = new List<string>();
        string? cuerpo = null;
        var manejador = new ManejadorFalso(async (req, _) =>
        {
            urls.Add(req.RequestUri!.AbsoluteUri);
            if (req.Method == HttpMethod.Post) cuerpo = await req.Content!.ReadAsStringAsync();
            return Respuesta(HttpStatusCode.OK, req.Method == HttpMethod.Post ? """{"id":"d-1","identificador_hw":"x","nombre":"Tableta 07","tipo":"TABLETA","activo":true,"bloqueado":true,"en_linea":true,"registrado_en":1,"ultimo_latido_en":1,"sesion_abierta":null}""" : DispositivosJson);
        });
        var api = new DispositivosApi(new HttpClient(manejador), new Uri("http://192.168.0.55:8000/"));
        var lista = await api.ListarAsync();
        Assert.Equal("http://192.168.0.55:8000/api/dispositivos/", urls[0]);
        Assert.Equal(2, lista!.Count);
        Assert.Equal(("Tableta 07", "Bloqueada", "Android · app 0.4.2 · en uso por ana"), (lista[0].NombreVisible, lista[0].EstadoLegible, lista[0].Detalle));
        Assert.Equal(("hw-2", "En línea", "Plataforma sin declarar · libre"), (lista[1].NombreVisible, lista[1].EstadoLegible, lista[1].Detalle));
        var bloqueada = await api.BloquearAsync("d-1", "prof-1", "mal uso");
        Assert.True(bloqueada!.Bloqueado);
        Assert.Equal("http://192.168.0.55:8000/api/dispositivos/d-1/bloquear/", urls[1]);
        Assert.Contains("\"motivo\":\"mal uso\"", cuerpo);
        Assert.Null(api.UltimoError);
    }

    [Fact]
    public async Task Un503NoEsExcepcion_DevuelveNullYElMotivo()
    {
        var api = new AulaApi(Cliente(HttpStatusCode.ServiceUnavailable,
            """{"disponible":false,"detail":"No hay manifiesto de ejemplo.","codigo":"fuente_no_disponible","sugerencia":"Define AVACOM_AULA_CURSO_EJEMPLO."}"""),
            new Uri("http://127.0.0.1:8000/"));
        var catalogo = await api.CursosAsync();
        Assert.Null(catalogo);
        Assert.Equal("No hay manifiesto de ejemplo.", api.UltimoMotivo);
        Assert.Equal("fuente_no_disponible", api.UltimoError!.Codigo);
        Assert.Equal("Define AVACOM_AULA_CURSO_EJEMPLO.", api.UltimoError.Sugerencia);
        Assert.Equal(503, api.UltimoError.Estado);
    }

    [Fact]
    public async Task Un409ExponeElCodigoYLosExtras()
    {
        var api = new AulaApi(Cliente(HttpStatusCode.Conflict,
            """{"detail":"El profesor ya tiene una sesión abierta.","codigo":"sesion_activa_existente","sesion_id":"abc","codigo_union":"613385"}"""),
            new Uri("http://127.0.0.1:8000/"));
        var sesion = await api.IniciarAsync(new IniciarSesionSolicitud("leccion", "c", "l1", null, "ejemplo", "prof-1", "Prof.", "pantalla"));
        Assert.Null(sesion);
        Assert.Equal("sesion_activa_existente", api.UltimoError!.Codigo);
        Assert.Equal("abc", api.UltimoError.Texto("sesion_id"));
    }

    [Fact]
    public async Task IniciarEnviaElCuerpoEnSnakeCaseConContentLengthYLeeLaSesion()
    {
        HttpRequestMessage? capturada = null;
        string? cuerpo = null;
        var manejador = new ManejadorFalso(async (req, _) =>
        {
            capturada = req;
            cuerpo = req.Content is null ? null : await req.Content.ReadAsStringAsync();
            return Respuesta(HttpStatusCode.Created, SesionJson);
        });
        var api = new AulaApi(new HttpClient(manejador), new Uri("http://127.0.0.1:8000/"));
        var sesion = await api.IniciarAsync(new IniciarSesionSolicitud("leccion", "c", "l1", null, "ejemplo", "prof-1", "Prof. Gómez", "pantalla"));
        Assert.NotNull(sesion);
        Assert.Equal("613385", sesion!.CodigoUnion);
        Assert.Equal("l1-lecture", sesion.Selector!.ObjetoRef);
        Assert.Equal("http://127.0.0.1:8000/api/aula/sesiones/", capturada!.RequestUri!.AbsoluteUri);
        Assert.NotNull(capturada.Content!.Headers.ContentLength);
        Assert.Contains("\"leccion_ref\":\"l1\"", cuerpo);
        Assert.Contains("\"profesor_id\":\"prof-1\"", cuerpo);
        Assert.Null(api.UltimoError);
    }

    [Fact]
    public void LasUrlDeMediosSeResuelvenContraLaBaseDelBackend()
    {
        var api = new AulaApi(new HttpClient(new ManejadorFalso((_, _) => Task.FromResult(Respuesta(HttpStatusCode.OK, "{}")))), new Uri("http://192.168.0.55:8000/"), "ejemplo");
        Assert.Equal("http://192.168.0.55:8000/api/aula/cursos/x/medios/img/?fuente=ejemplo", api.Absoluta("/api/aula/cursos/x/medios/img/?fuente=ejemplo").AbsoluteUri);
        Assert.Equal("ejemplo", api.Fuente);
    }

    [Fact]
    public async Task SinFuenteElParametroNoViajaYElBackendDecide()
    {
        var urls = new List<string>();
        var manejador = new ManejadorFalso((req, _) =>
        {
            urls.Add(req.RequestUri!.AbsoluteUri);
            return Task.FromResult(Respuesta(HttpStatusCode.OK, VistaCursoJson));
        });
        var sinFuente = new AulaApi(new HttpClient(manejador), new Uri("http://127.0.0.1:8000/"));
        Assert.Null(sinFuente.Fuente);
        await sinFuente.CursosAsync();
        await sinFuente.CursoAsync("c", docente: true);
        Assert.Equal("http://127.0.0.1:8000/api/aula/cursos/", urls[0]);
        Assert.Equal("http://127.0.0.1:8000/api/aula/cursos/c/?rol=docente", urls[1]);

        var biblioteca = new AulaApi(new HttpClient(manejador), new Uri("http://127.0.0.1:8000/"), "biblioteca");
        await biblioteca.CursoAsync("c", docente: false);
        Assert.Equal("http://127.0.0.1:8000/api/aula/cursos/c/?rol=estudiante&fuente=biblioteca", urls[2]);
    }

    // ------------------------------------------------------------------ ayudas

    private static HttpClient Cliente(HttpStatusCode estado, string json) =>
        new(new ManejadorFalso((_, _) => Task.FromResult(Respuesta(estado, json))));

    private static HttpResponseMessage Respuesta(HttpStatusCode estado, string json) =>
        new(estado) { Content = new StringContent(json, Encoding.UTF8, "application/json") };

    private sealed class ManejadorFalso(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> responder) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => responder(request, cancellationToken);
    }
}

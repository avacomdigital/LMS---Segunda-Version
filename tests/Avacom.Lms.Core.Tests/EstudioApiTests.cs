using System.Net;
using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// El cliente de <c>/api/modo-estudio/</c> contra un nodo falso: una prueba por familia de rutas del contrato (§4) verificando método, URL, cuerpo y el
/// mapeo del JSON de ejemplo; los errores con su código y sus extras; y lo que <c>ClienteJson</c> ganó (PATCH, texto crudo, respuesta en streaming).
/// </summary>
[Collection("estado global")]
public sealed class EstudioApiTests : IDisposable
{
    private const string Base = "/api/modo-estudio/";
    private const string Dispositivo = "student-TAB07";

    public EstudioApiTests() => ClienteJson.Token = null;
    public void Dispose() => ClienteJson.Token = null;

    private sealed record Captura(HttpMethod Metodo, string Url, string? Cuerpo, long? Longitud, string? Autorizacion, string? Rango)
    {
        public JsonElement Json => Ayudas.Json(Cuerpo!);
        public string[] Claves => Json.EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal).ToArray();
    }

    private static (EstudioApi Api, List<Captura> Capturas) Api(Func<Captura, HttpResponseMessage> responder)
    {
        var capturas = new List<Captura>();
        var http = new HttpClient(new ManejadorFalso(async (req, _) =>
        {
            var cuerpo = req.Content is null ? null : await req.Content.ReadAsStringAsync();
            var captura = new Captura(req.Method, req.RequestUri!.PathAndQuery, cuerpo, req.Content?.Headers.ContentLength, req.Headers.Authorization?.ToString(), req.Headers.Range?.ToString());
            capturas.Add(captura);
            return responder(captura);
        }));
        return (new EstudioApi(http, new Uri("http://192.168.0.55:8000/")), capturas);
    }

    private static (EstudioApi Api, List<Captura> Capturas) Api(HttpStatusCode estado, string json) => Api(_ => Ayudas.Respuesta(estado, json));

    // ---------------------------------------------------------------------- los JSON del contrato

    private const string AsignacionJson = """
        {"id":"asig-1","titulo":"Área y volumen con lenguaje algebraico","consigna":"","descripcion":"Calcula áreas",
         "asignatura":"Lengua Castellana","unidad":"Unidad 2",
         "curso":{"fuente":"biblioteca","curso_ref":"curso-1","version":"1.0.0","titulo":"Matemáticas"},
         "leccion_ref":"l1","fecha_limite":1759600000000,"plazo":"blando","gracia_ms":900000,"estado_asignacion":"activa",
         "profesor":"Ms. Carter","asignada_en":1759000000000,
         "tarea":{"estado":"en_curso","vencida":false,"fuera_de_plazo":false,"avance_pct":57.14,"bloques_total":7,"bloques_obligatorios":7,"bloques_atendidos":4,
                  "ultimo_bloque":{"ref":"b4","indice":4,"titulo":"Lámina 4","tipo":"lamina","posicion_seg":208},
                  "puede_reanudar":true,"abierta_en":1,"ultimo_avance_en":2,"completada_en":null},
         "practica":{"disponible":true,"objeto_ref":"act-1","titulo":"Comprueba lo aprendido","total_preguntas":8,"intentos":2,"mejor_correctas":7,"ultima_correctas":6,"en_curso":false},
         "evaluacion":{"objeto_ref":"exam-1","titulo":"Evaluación de la Unidad 2"},
         "paquete":{"id":"paq-1","estado":"disponible","motivo":"","bytes_total":88080384,"bytes_estimados":88080384,"vigente_hasta":1759700000000,"huella":"abc"},
         "descarga":{"permitida":true,"motivo":""},
         "bloques":[{"ref":"b1","indice":1,"tipo":"lamina","titulo":"Lámina 1","obligatorio":true,"atendido":true},
                    {"ref":"b2","indice":2,"tipo":"pagina","titulo":"Página 2","obligatorio":true,"atendido":false}]}
        """;

    private const string TareaJson = """{"estado":"en_curso","vencida":false,"fuera_de_plazo":true,"avance_pct":71.43,"bloques_total":7,"bloques_obligatorios":7,"bloques_atendidos":5,"ultimo_bloque":null,"puede_reanudar":true,"abierta_en":1,"ultimo_avance_en":9,"completada_en":null}""";

    private const string PaqueteJson = """
        {"id":"paq-1","asignacion_id":"asig-1","estado":"solicitado","motivo":"","curso_version":"1.0.0","bytes_total":300,"huella":"h1","vigente_hasta":1759700000000,
         "solicitado_en":10,"disponible_en":null,
         "archivos":[{"media_ref":"img-1","clase":"image","mime":"image/png","bytes":100,"sha256":"aa"},{"media_ref":"vid-1","clase":"video","mime":"video/mp4","bytes":200,"sha256":"bb"}],
         "no_incluidos":[{"media_ref":"sim-1","motivo":"simulacion"}],"servidor_en":1759000000000}
        """;

    private static string Envuelto(string paquete) => $$"""{"paquete":{{paquete}}}""";

    // ----------------------------------------------------------------------- estado y sesión

    [Fact]
    public async Task Estado_EsUnGetConElAparatoEnLaConsulta_YMapeaLaRespuestaDelMenu()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """
            {"disponible":true,"motivo":"","perfil":"asignado","alumno":{"id":"ana","rotulo":"Ana Pérez"},
             "dispositivo":{"id":"d-1","nombre":"Tableta 07","identificador_hw":"student-TAB07"},"descarga_permitida":true,"servidor_en":1759000000000}
            """);

        var estado = await api.EstadoAsync(Dispositivo);
        await api.EstadoAsync("student con espacio", "ana pérez");

        Assert.Equal((HttpMethod.Get, $"{Base}estado/?dispositivo=student-TAB07"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal($"{Base}estado/?dispositivo=student%20con%20espacio&alumno_id=ana%20p%C3%A9rez", capturas[1].Url);
        Assert.Null(capturas[0].Cuerpo);
        Assert.True(estado!.Disponible);
        Assert.Equal(("asignado", "ana", "Ana Pérez", true, 1759000000000), (estado.Perfil, estado.Alumno!.Id, estado.Alumno.Rotulo, estado.DescargaPermitida, estado.ServidorEn));
        Assert.Equal(("d-1", "student-TAB07"), (estado.Dispositivo!.Id, estado.Dispositivo.IdentificadorHw));
        Assert.Null(api.UltimoError);
    }

    [Fact]
    public async Task Estado_TraeAlDuenoDeLaTableta_ParaOfrecerloPrimeroEnQuienEres()
    {
        var (api, _) = Api(HttpStatusCode.OK, """
            {"disponible":true,"motivo":"","perfil":"asignado","alumno":null,"dueno":{"id":"ana","rotulo":"Ana Pérez"},
             "dispositivo":{"id":"d-1","nombre":"Tableta 07","identificador_hw":"student-TAB07"},"descarga_permitida":true,"servidor_en":1759000000000}
            """);

        var estado = await api.EstadoAsync(Dispositivo);

        Assert.Null(estado!.Alumno);
        Assert.Equal(("ana", "Ana Pérez"), (estado.Dueno!.Id, estado.Dueno.Rotulo));
    }

    [Fact]
    public async Task Estudiantes_EsUnGetSinAlumno_YMapeaLosGruposConSusNombres()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """
            {"disponible":true,"motivo":"","grupos":[
               {"id":"g-5b","codigo":"5B","nombre":"Quinto B","alumnos":[{"id":"e1","rotulo":"Ethan Martínez"},{"id":"s1","rotulo":"Sofía Ramírez"}]},
               {"id":"","codigo":"","nombre":"Alumnos","alumnos":[{"id":"m1","rotulo":"Mateo Gómez"}]}],
             "dueno":{"id":"e1","rotulo":"Ethan Martínez"},"servidor_en":1759000000000}
            """);

        var roster = await api.EstudiantesAsync(Dispositivo);

        Assert.Equal((HttpMethod.Get, $"{Base}estudiantes/?dispositivo=student-TAB07"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Null(capturas[0].Cuerpo);
        Assert.True(roster!.Disponible);
        Assert.Equal(2, roster.Grupos.Count);
        Assert.Equal(("5B", "Quinto B", 2), (roster.Grupos[0].Codigo, roster.Grupos[0].Nombre, roster.Grupos[0].Alumnos.Count));
        Assert.Equal(("s1", "Sofía Ramírez"), (roster.Grupos[0].Alumnos[1].Id, roster.Grupos[0].Alumnos[1].Rotulo));
        Assert.Equal("e1", roster.Dueno!.Id);
        Assert.Equal(1759000000000, roster.ServidorEn);
    }

    [Fact]
    public async Task Estudiantes_NoSePuedeUsar_LlegaConSuMotivoYSinGrupos()
    {
        var (api, _) = Api(HttpStatusCode.OK, """{"disponible":false,"motivo":"dispositivo_bloqueado","grupos":[],"dueno":null,"servidor_en":5}""");

        var roster = await api.EstudiantesAsync(Dispositivo);

        Assert.False(roster!.Disponible);
        Assert.Equal("dispositivo_bloqueado", roster.Motivo);
        Assert.Empty(roster.Grupos);
        Assert.Null(roster.Dueno);
    }

    [Fact]
    public async Task Estudiantes_NuncaLanza_SinRedDevuelveNull()
    {
        var sinRed = new EstudioApi(new HttpClient(new ManejadorFalso((_, _) => throw new HttpRequestException("sin ruta al aula"))), new Uri("http://192.168.0.55:8000/"));
        Assert.Null(await sinRed.EstudiantesAsync(Dispositivo));
        Assert.Equal(0, sinRed.UltimoError!.Estado);
        Assert.Null(await Api(HttpStatusCode.OK, "esto no es json").Api.EstudiantesAsync(Dispositivo));
    }

    [Fact]
    public async Task Estado_NuncaLanza_NiSinRedNiConUnCuerpoRaro_NiConUnFalloInesperado()
    {
        var sinRed = new EstudioApi(new HttpClient(new ManejadorFalso((_, _) => throw new HttpRequestException("sin ruta al aula"))), new Uri("http://192.168.0.55:8000/"));
        Assert.Null(await sinRed.EstadoAsync(Dispositivo));
        Assert.Equal(0, sinRed.UltimoError!.Estado);
        Assert.Equal("sin_conexion", sinRed.UltimoError.Codigo);

        var inesperado = new EstudioApi(new HttpClient(new ManejadorFalso((_, _) => throw new InvalidOperationException("algo que nadie previó"))), new Uri("http://192.168.0.55:8000/"));
        Assert.Null(await inesperado.EstadoAsync(Dispositivo));

        Assert.Null(await Api(HttpStatusCode.OK, "esto no es json").Api.EstadoAsync(Dispositivo));
        Assert.Null(await Api(_ => new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("<html/>", Encoding.UTF8, "text/html") }).Api.EstadoAsync(Dispositivo));
        Assert.Null(await Api(HttpStatusCode.ServiceUnavailable, """{"detail":"La biblioteca no responde.","codigo":"fuente_no_disponible"}""").Api.EstadoAsync(Dispositivo));

        using var cancelado = new CancellationTokenSource();
        cancelado.Cancel();
        Assert.Null(await Api(HttpStatusCode.OK, "{}").Api.EstadoAsync(Dispositivo, ct: cancelado.Token));
    }

    [Fact]
    public async Task Sesion_AbreYCierra_ConLosCamposQueNoSonNulos_YElAlumnoSoloSiSeDa()
    {
        var (api, capturas) = Api(c => c.Url.Contains("cerrar")
            ? Ayudas.Respuesta(HttpStatusCode.OK, """{"cerrada":true}""")
            : Ayudas.Respuesta(HttpStatusCode.OK, """{"sesion_id":"s-1","alumno":{"id":"ana","rotulo":"Ana"},"dispositivo":{"id":"d-1","nombre":"T7","identificador_hw":"hw"},"perfil":"asignado","servidor_en":5}"""));

        var sesion = await api.AbrirSesionAsync(Dispositivo, "Tableta 07", "android", "0.4.2");
        await api.AbrirSesionAsync(Dispositivo, null, null, null, alumnoId: "ana");
        Assert.Equal((HttpMethod.Post, $"{Base}sesion/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(["dispositivo", "nombre", "plataforma", "version_app"], capturas[0].Claves);
        Assert.Equal("0.4.2", capturas[0].Json.GetProperty("version_app").GetString());
        Assert.Equal(["alumno_id", "dispositivo"], capturas[1].Claves);                          // lo nulo no viaja; el alumno sí, porque se dio
        Assert.NotNull(capturas[0].Longitud);                                                    // el cuerpo viaja con Content-Length
        Assert.Equal(("s-1", "asignado", "Ana"), (sesion!.SesionId, sesion.Perfil, sesion.Alumno.Rotulo));

        Assert.True(await api.CerrarSesionAsync(Dispositivo, 3, limpiezaCompleta: false));
        Assert.True(await api.CerrarSesionAsync(Dispositivo, 0, limpiezaCompleta: true, alumnoId: "ana"));
        Assert.Equal((HttpMethod.Post, $"{Base}sesion/cerrar/"), (capturas[2].Metodo, capturas[2].Url));
        Assert.Equal(["cola_pendiente", "dispositivo", "limpieza"], capturas[2].Claves);
        Assert.Equal((3, "pendiente"), (capturas[2].Json.GetProperty("cola_pendiente").GetInt32(), capturas[2].Json.GetProperty("limpieza").GetString()));
        Assert.Equal("completa", capturas[3].Json.GetProperty("limpieza").GetString());
        Assert.Equal("ana", capturas[3].Json.GetProperty("alumno_id").GetString());
    }

    [Fact]
    public async Task Sesion_Cerrar_NoEsExitoSiElNodoNiegaElCierre_YLaLimpiezaReintentadaVaAsuRuta()
    {
        Assert.False(await Api(HttpStatusCode.OK, """{"cerrada":false}""").Api.CerrarSesionAsync(Dispositivo, 0, true));
        Assert.False(await Api(HttpStatusCode.Forbidden, """{"detail":"no","codigo":"sin_permiso"}""").Api.CerrarSesionAsync(Dispositivo, 0, true));

        var (api, capturas) = Api(HttpStatusCode.OK, """{"ok":true}""");
        Assert.True(await api.LimpiezaReintentadaAsync(Dispositivo, "completa"));
        Assert.Equal((HttpMethod.Post, $"{Base}sesion/limpieza/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(["dispositivo", "resultado"], capturas[0].Claves);
    }

    // ----------------------------------------------------------------------- pendientes y lección

    [Fact]
    public async Task Asignaciones_DevuelveLaListaConCadaAsignacionCompleta()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, $$"""
            {"alumno":{"id":"ana","rotulo":"Ana"},"asignaciones":[{{AsignacionJson}}],"resumen":{"pendientes":1,"descargadas":1,"completadas":0},"servidor_en":77}
            """);

        var lista = await api.AsignacionesAsync(Dispositivo);

        Assert.Equal((HttpMethod.Get, $"{Base}asignaciones/?dispositivo=student-TAB07"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal((1, 1, 0, 77), (lista!.Resumen!.Pendientes, lista.Resumen.Descargadas, lista.Resumen.Completadas, (int)lista.ServidorEn));
        var a = Assert.Single(lista.Asignaciones);
        Assert.Equal(("asig-1", "Área y volumen con lenguaje algebraico", "Lengua Castellana", "Unidad 2", "l1"), (a.Id, a.Titulo, a.Asignatura, a.Unidad, a.LeccionRef));
        Assert.Equal(("biblioteca", "curso-1", "1.0.0"), (a.Curso!.Fuente, a.Curso.CursoRef, a.Curso.Version));
        Assert.Equal((1759600000000L, "blando", 900000L, "Ms. Carter", false), (a.FechaLimite, a.Plazo, a.GraciaMs, a.Profesor, a.Cerrada));
        Assert.Equal(("en_curso", 57.14, 7, 4, true, false), (a.Tarea!.Estado, a.Tarea.AvancePct, a.Tarea.BloquesTotal, a.Tarea.BloquesAtendidos, a.Tarea.PuedeReanudar, a.Tarea.Completada));
        Assert.Equal(("b4", 4, "lamina", 208), (a.Tarea.UltimoBloque!.Ref, a.Tarea.UltimoBloque.Indice, a.Tarea.UltimoBloque.Tipo, a.Tarea.UltimoBloque.PosicionSeg));
        Assert.Null(a.Tarea.CompletadaEn);
        Assert.Equal((true, "act-1", 8, 2, 7, 6, false), (a.Practica!.Disponible, a.Practica.ObjetoRef, a.Practica.TotalPreguntas, a.Practica.Intentos, a.Practica.MejorCorrectas, a.Practica.UltimaCorrectas, a.Practica.EnCurso));
        Assert.Equal("exam-1", a.Evaluacion!.ObjetoRef);
        Assert.Equal(("paq-1", "disponible", 88080384L, 1759700000000L, "abc"), (a.Paquete!.Id, a.Paquete.Estado, a.Paquete.BytesTotal, a.Paquete.VigenteHasta, a.Paquete.Huella));
        Assert.True(a.Descarga!.Permitida);
        Assert.Equal(["b1", "b2"], a.Bloques!.Select(b => b.Ref).ToArray());
        Assert.Equal([true, false], a.Bloques!.Select(b => b.Atendido).ToArray());
    }

    [Fact]
    public async Task UnaAsignacionYUnaLeccion_VanPorSusRutas_ConElIdEscapado()
    {
        var (api, capturas) = Api(c => Ayudas.Respuesta(HttpStatusCode.OK, c.Url.Contains("/lecciones/")
            ? $$"""
                {"asignacion":{{AsignacionJson}},"curso":{"curso_ref":"curso-1","titulo":"Matemáticas","lecciones":1,"objetos":3},
                 "leccion":{"leccion_ref":"l1","titulo":"Los tres estados","objetos":[]},
                 "bloques":[{"ref":"b1","indice":1,"tipo":"lamina","titulo":"Lámina 1","obligatorio":true,"atendido":false}],
                 "reanudar":{"bloque_ref":"b4","indice":4,"posicion_seg":208,"puede":true},"servidor_en":9}
                """
            : AsignacionJson));

        var asignacion = await api.AsignacionAsync(Dispositivo, "asig 1/x", "ana");
        var leccion = await api.LeccionAsync(Dispositivo, "asig-1");

        Assert.Equal((HttpMethod.Get, $"{Base}asignaciones/asig%201%2Fx/?dispositivo=student-TAB07&alumno_id=ana"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal($"{Base}lecciones/asig-1/?dispositivo=student-TAB07", capturas[1].Url);
        Assert.Equal("asig-1", asignacion!.Id);
        Assert.Equal(("l1", "Los tres estados"), (leccion!.Leccion.LeccionRef, leccion.Leccion.Titulo));
        Assert.Equal(("b4", 4, 208, true), (leccion.Reanudar!.BloqueRef, leccion.Reanudar.Indice, leccion.Reanudar.PosicionSeg, leccion.Reanudar.Puede));
        Assert.Equal("Matemáticas", leccion.Curso!.Titulo);
        Assert.Equal("asig-1", leccion.Asignacion.Id);
        Assert.Single(leccion.Bloques);
    }

    [Fact]
    public async Task Progreso_EsUnPatch_ConLosCamposQueSeDan_ConContentLength()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, $$"""{"tarea":{{TareaJson}},"aceptados":["b1","b2"],"desconocidos":["b99"]}""");

        var progreso = await api.ProgresoAsync(Dispositivo, "asig-1", ["b1", "b2"], "b2", 208, capturadoEn: 1759000123000);
        await api.ProgresoAsync(Dispositivo, "asig-1", [], "b3", null, alumnoId: "ana");
        await api.ProgresoAsync(Dispositivo, "asig-1", [], null, 15);

        Assert.Equal((HttpMethod.Patch, $"{Base}lecciones/asig-1/progreso/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(["bloque_actual", "bloques_vistos", "capturado_en", "dispositivo", "posicion_seg"], capturas[0].Claves);
        Assert.Equal(["b1", "b2"], capturas[0].Json.GetProperty("bloques_vistos").EnumerateArray().Select(e => e.GetString()!).ToArray());
        Assert.Equal(1759000123000, capturas[0].Json.GetProperty("capturado_en").GetInt64());
        Assert.NotNull(capturas[0].Longitud);
        Assert.Equal(["alumno_id", "bloque_actual", "dispositivo"], capturas[1].Claves);         // sin bloques vistos ni posición: no viajan
        Assert.Equal(["dispositivo", "posicion_seg"], capturas[2].Claves);
        Assert.Equal(("en_curso", 71.43, true), (progreso!.Tarea.Estado, progreso.Tarea.AvancePct, progreso.Tarea.FueraDePlazo));
        Assert.Equal(["b1", "b2"], progreso.Aceptados!.ToArray());
        Assert.Equal(["b99"], progreso.Desconocidos!.ToArray());
    }

    [Fact]
    public async Task Completar_EsUnPost_YSinTodosLosObligatoriosLlevaLoQueFalta()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, $$"""{"tarea":{{TareaJson.Replace("en_curso", "completada")}}}""");
        var completada = await api.CompletarAsync(Dispositivo, "asig-1");
        Assert.Equal((HttpMethod.Post, $"{Base}lecciones/asig-1/completar/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(["dispositivo"], capturas[0].Claves);
        Assert.True(completada!.Tarea.Completada);

        var (pendientes, _) = Api(HttpStatusCode.Conflict, """{"detail":"Faltan bloques.","codigo":"bloques_pendientes","faltan":[{"ref":"b5","indice":5,"titulo":"Lámina 5"},{"ref":"b6","indice":6,"titulo":"Práctica"}]}""");
        Assert.Null(await pendientes.CompletarAsync(Dispositivo, "asig-1"));
        Assert.Equal(("bloques_pendientes", 409, "Faltan bloques."), (pendientes.UltimoError!.Codigo, pendientes.UltimoError.Estado, pendientes.UltimoMotivo));
        var faltan = pendientes.UltimoError.Extra!.Value.GetProperty("faltan");
        Assert.Equal(["b5", "b6"], faltan.EnumerateArray().Select(f => f.GetProperty("ref").GetString()!).ToArray());
    }

    // -------------------------------------------------------------------------------- práctica

    private const string ObjetoJson = """{"objeto_ref":"act-1","tipo":"activity","componente":"actividad","titulo":"Comprueba lo aprendido","fuera_de_alcance":false}""";

    [Fact]
    public async Task Practica_AbreOReanuda_ConNuevaSoloCuandoEsTrue()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """
            {"practica":{"id":"p-1","numero":2,"estado":"en_curso","objeto_ref":"act-1","titulo":"Comprueba lo aprendido","total_preguntas":8,
                         "respondidas":{"q1":{"respuesta":{"value":"a"},"veredicto":{"pregunta_ref":"q1","correcta":true,"puntaje":1,"puntaje_maximo":1,"pendiente":false,"retroalimentacion":["¡Bien!"]}},
                                        "q2":{"respuesta":{"value":["x"]},"veredicto":null}},
                         "aciertos":1,"iniciada_en":5,"reanudada":true},
             "objeto":@OBJETO@}
            """.Replace("@OBJETO@", ObjetoJson));

        var abierta = await api.PracticaAsync(Dispositivo, "asig-1");
        await api.PracticaAsync(Dispositivo, "asig-1", "act-1", nueva: true, alumnoId: "ana");

        Assert.Equal((HttpMethod.Post, $"{Base}lecciones/asig-1/practica/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(["dispositivo"], capturas[0].Claves);
        Assert.Equal(["alumno_id", "dispositivo", "nueva", "objeto_ref"], capturas[1].Claves);
        Assert.True(capturas[1].Json.GetProperty("nueva").GetBoolean());
        var practica = abierta!.Practica;
        Assert.Equal(("p-1", 2, "en_curso", 8, 1, true, false), (practica.Id, practica.Numero, practica.Estado, practica.TotalPreguntas, practica.Aciertos, practica.Reanudada, practica.Terminada));
        Assert.Equal(["q1", "q2"], practica.Respondidas!.Keys.OrderBy(k => k).ToArray());
        Assert.Equal("a", practica.Respondidas["q1"].Respuesta.GetProperty("value").GetString());
        Assert.True(practica.Respondidas["q1"].Veredicto!.Correcta);
        Assert.Equal(["¡Bien!"], practica.Respondidas["q1"].Veredicto!.Retroalimentacion!.ToArray());
        Assert.Null(practica.Respondidas["q2"].Veredicto);
        Assert.Equal(("act-1", "actividad"), (abierta.Objeto.ObjetoRef, abierta.Objeto.Componente));
    }

    [Fact]
    public async Task Responder_ManejaLasRespuestasTalCual_YOmiteLaHoraDeCapturaQueFalta()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """
            {"acuse":true,"veredictos":[{"pregunta_ref":"q1","correcta":false,"puntaje":0,"puntaje_maximo":1.5,"pendiente":false,"retroalimentacion":["Casi."]}],
             "aceptadas":["q1"],"duplicadas":["q2"],"superadas":[],"rechazadas":[{"pregunta_ref":"q3","motivo":"formato"}],
             "practica":{"id":"p-1","estado":"en_curso","respondidas":2,"aciertos":0,"total_preguntas":8,"sin_calificar":1},"resultado":null,"servidor_en":99}
            """);
        var respuestas = new[]
        {
            new RespuestaPractica("q1", Ayudas.Json("""{"value":null,"detalle":{"vacio":null}}"""), 1),                 // un nulo DENTRO de la respuesta es parte de ella
            new RespuestaPractica("q2", Ayudas.Json("""{"value":["a","b"]}"""), 2, CapturadaEn: 1759000123000),
        };

        var acuse = await api.ResponderAsync(Dispositivo, "p 1", respuestas, terminar: true);
        await api.ResponderAsync(Dispositivo, "p-1", respuestas[..1]);

        Assert.Equal((HttpMethod.Post, $"{Base}practicas/p%201/respuestas/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(["dispositivo", "respuestas", "terminar"], capturas[0].Claves);
        Assert.Equal(["dispositivo", "respuestas"], capturas[1].Claves);                                            // terminar sólo cuando es verdad
        var enviadas = capturas[0].Json.GetProperty("respuestas");
        Assert.Equal(["pregunta_ref", "respuesta", "secuencia"], enviadas[0].EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal).ToArray());
        Assert.Equal(JsonValueKind.Null, enviadas[0].GetProperty("respuesta").GetProperty("value").ValueKind);       // sin capturada_en, pero con su nulo interno intacto
        Assert.Equal(JsonValueKind.Null, enviadas[0].GetProperty("respuesta").GetProperty("detalle").GetProperty("vacio").ValueKind);
        Assert.Equal(1759000123000, enviadas[1].GetProperty("capturada_en").GetInt64());
        Assert.Equal(2, enviadas[1].GetProperty("secuencia").GetInt32());
        Assert.True(capturas[0].Json.GetProperty("terminar").GetBoolean());

        Assert.True(acuse!.Acuse);
        Assert.Equal(("q1", false, 1.5, "Casi."), (acuse.Veredictos![0].PreguntaRef, acuse.Veredictos[0].Correcta, acuse.Veredictos[0].PuntajeMaximo, acuse.Veredictos[0].Retroalimentacion![0]));
        Assert.Equal(["q1"], acuse.Aceptadas!.ToArray());
        Assert.Equal(["q2"], acuse.Duplicadas!.ToArray());
        Assert.Equal(("q3", "formato"), (acuse.Rechazadas![0].PreguntaRef, acuse.Rechazadas[0].Motivo));
        Assert.Equal(("p-1", 2, 1), (acuse.Practica!.Id, acuse.Practica.Respondidas, acuse.Practica.SinCalificar));
        Assert.Null(acuse.Resultado);
        Assert.Equal(99, acuse.ServidorEn);
    }

    [Theory]
    [InlineData("""{"id":"p-1","estado":"terminada","respondidas":3,"aciertos":2,"total_preguntas":3,"sin_calificar":0}""")]                                                       // resumida
    [InlineData("""{"id":"p-1","numero":1,"estado":"terminada","total_preguntas":3,"respondidas":{"q1":{},"q2":{},"q3":{}},"aciertos":2,"iniciada_en":5,"reanudada":false}""")]      // completa
    public async Task Terminar_LeeElResultado_AunqueLaPracticaLleguesResumidaOCompleta(string practicaJson)
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """
            {"practica":@PRACTICA@,
             "resultado":{"correctas":2,"total":3,"porcentaje":66.7,"mensaje":"2 de 3 correctas","sin_calificar":0,
                          "revision":[{"pregunta_ref":"q1","correcta":true,"retroalimentacion":[]},{"pregunta_ref":"q2","correcta":false,"retroalimentacion":["Repasa la lámina 3."]}]}}
            """.Replace("@PRACTICA@", practicaJson));

        var acuse = await api.TerminarPracticaAsync(Dispositivo, "p-1", "ana");

        Assert.Equal((HttpMethod.Post, $"{Base}practicas/p-1/terminar/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(["alumno_id", "dispositivo"], capturas[0].Claves);
        Assert.True(acuse!.Acuse);                                                                                  // llegó 200: el nodo lo recibió
        Assert.Equal(("p-1", "terminada", 3, 2, 3, 0), (acuse.Practica!.Id, acuse.Practica.Estado, acuse.Practica.Respondidas, acuse.Practica.Aciertos, acuse.Practica.TotalPreguntas, acuse.Practica.SinCalificar));
        Assert.Equal((2, 3, 66.7, "2 de 3 correctas"), (acuse.Resultado!.Correctas, acuse.Resultado.Total, acuse.Resultado.Porcentaje, acuse.Resultado.Mensaje));
        Assert.Equal(["Repasa la lámina 3."], acuse.Resultado.Revision![1].Retroalimentacion!.ToArray());
        Assert.False(acuse.Resultado.Revision[1].Correcta);
    }

    // -------------------------------------------------------------------------------- paquete

    [Fact]
    public async Task SolicitarPaquete_EsUnPostQueDevuelveElPaquete_ConSusArchivos()
    {
        var (api, capturas) = Api(HttpStatusCode.Created, Envuelto(PaqueteJson));

        var paquete = await api.SolicitarPaqueteAsync(Dispositivo, "asig-1");
        await api.SolicitarPaqueteAsync(Dispositivo, "asig-1", "ana");

        Assert.Equal((HttpMethod.Post, $"{Base}paquetes/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(["asignacion_id", "dispositivo"], capturas[0].Claves);
        Assert.Equal(["alumno_id", "asignacion_id", "dispositivo"], capturas[1].Claves);
        Assert.Equal(("paq-1", "asig-1", "solicitado", 300L, "h1", 1759700000000L), (paquete!.Id, paquete.AsignacionId, paquete.Estado, paquete.BytesTotal, paquete.Huella, paquete.VigenteHasta));
        Assert.Equal(1759000000000L, paquete.ServidorEn);
        Assert.False(paquete.Denegado);
        Assert.Equal(["img-1", "vid-1"], paquete.Archivos!.Select(a => a.MediaRef).ToArray());
        Assert.Equal(("video/mp4", 200L, "bb"), (paquete.Archivos![1].Mime, paquete.Archivos[1].Bytes, paquete.Archivos[1].Sha256));
        Assert.Equal("sim-1", paquete.NoIncluidos![0].MediaRef);
    }

    [Fact]
    public async Task UnAparatoCompartido_RecibeUn403DescargaDenegada_ConElPaqueteDenegadoYElMensajeEnLosExtras()
    {
        var (api, _) = Api(HttpStatusCode.Forbidden, """
            {"detail":"Esta tableta es compartida.","codigo":"descarga_denegada","paquete":{"estado":"denegado","motivo":"dispositivo_compartido"},"mensaje":"Pídele a tu profesor una tableta asignada."}
            """);

        Assert.Null(await api.SolicitarPaqueteAsync(Dispositivo, "asig-1"));

        var error = api.UltimoError!;
        Assert.Equal(("descarga_denegada", 403, "Esta tableta es compartida."), (error.Codigo, error.Estado, api.UltimoMotivo));
        Assert.Equal("Pídele a tu profesor una tableta asignada.", error.Texto("mensaje"));
        Assert.Equal(("denegado", "dispositivo_compartido"),
                     (error.Extra!.Value.GetProperty("paquete").GetProperty("estado").GetString(), error.Extra.Value.GetProperty("paquete").GetProperty("motivo").GetString()));
    }

    [Fact]
    public async Task PaqueteYPaquetes_VanPorSusRutas_YElPaqueteLlegaEnvueltoOSuelto()
    {
        var (api, capturas) = Api(c => Ayudas.Respuesta(HttpStatusCode.OK, c.Url.Contains("paq-envuelto") ? Envuelto(PaqueteJson) : c.Url.StartsWith($"{Base}paquetes/?") ? $$"""{"paquetes":[{{PaqueteJson}}]}""" : PaqueteJson));

        var lista = await api.PaquetesAsync(Dispositivo, "ana");
        var suelto = await api.PaqueteAsync(Dispositivo, "paq-1");
        var envuelto = await api.PaqueteAsync(Dispositivo, "paq-envuelto");

        Assert.Equal((HttpMethod.Get, $"{Base}paquetes/?dispositivo=student-TAB07&alumno_id=ana"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal($"{Base}paquetes/paq-1/?dispositivo=student-TAB07", capturas[1].Url);
        Assert.Equal("paq-1", Assert.Single(lista!.Paquetes).Id);
        Assert.Equal(("paq-1", 300L, 1759000000000L), (suelto!.Id, suelto.BytesTotal, suelto.ServidorEn));
        Assert.Equal(("paq-1", 2), (envuelto!.Id, envuelto.Archivos!.Count));
    }

    [Fact]
    public async Task ElServidorEnDelSobre_SePasaAlPaqueteSiNoTraeElSuyo()
    {
        var (api, _) = Api(HttpStatusCode.OK, """{"paquete":{"id":"paq-1","asignacion_id":"asig-1","estado":"disponible","bytes_total":1},"servidor_en":4242}""");
        Assert.Equal(4242, (await api.PaqueteAsync(Dispositivo, "paq-1"))!.ServidorEn);
    }

    [Fact]
    public async Task Manifiesto_SeLeeTipadoYTalComoLlego()
    {
        var crudo = """
            {"paquete_id":"paq-1","asignacion":{"id":"asig-1","titulo":"Área"},"curso":{"curso_ref":"curso-1","titulo":"Mates","lecciones":1,"objetos":3},"leccion_ref":"l1",
             "vigente_hasta":1759700000000,"generado_en":1759000000000,"leccion":{"leccion_ref":"l1","titulo":"Los tres estados","campo_que_el_dto_no_conoce":[1,2,{"x":null}]},
             "archivos":[{"media_ref":"img-1","clase":"image","mime":"image/png","bytes":100,"sha256":"aa"}],"no_incluidos":[],"huella":"h1"}
            """;
        var (api, capturas) = Api(HttpStatusCode.OK, crudo);

        var tipado = await api.ManifiestoAsync(Dispositivo, "paq-1");
        var texto = await api.ManifiestoCrudoAsync(Dispositivo, "paq-1", "ana");

        Assert.Equal((HttpMethod.Get, $"{Base}paquetes/paq-1/manifiesto/?dispositivo=student-TAB07"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal($"{Base}paquetes/paq-1/manifiesto/?dispositivo=student-TAB07&alumno_id=ana", capturas[1].Url);
        Assert.Equal(("paq-1", "l1", "h1", 1759700000000L), (tipado!.PaqueteId, tipado.LeccionRef, tipado.Huella, tipado.VigenteHasta));
        Assert.Equal("Los tres estados", tipado.Leccion.GetProperty("titulo").GetString());
        Assert.Equal("img-1", Assert.Single(tipado.Archivos).MediaRef);
        Assert.Equal(crudo, texto);                                                                                // ni un byte distinto: la huella se verifica sobre esto
    }

    [Fact]
    public async Task Manifiesto_ConUnErrorHttp_DevuelveNull_ConSuCodigo()
    {
        var (api, _) = Api(HttpStatusCode.Gone, """{"detail":"El paquete venció.","codigo":"paquete_vencido"}""");
        Assert.Null(await api.ManifiestoCrudoAsync(Dispositivo, "paq-1"));
        Assert.Equal(("paquete_vencido", 410), (api.UltimoError!.Codigo, api.UltimoError.Estado));
        Assert.Null(await api.ManifiestoAsync(Dispositivo, "paq-1"));
        Assert.Equal(410, api.UltimoError!.Estado);
    }

    [Fact]
    public async Task Archivo_DevuelveLaRespuestaAbierta_ConRangeSoloSiSePideDesdeUnByte()
    {
        var contenido = Enumerable.Range(0, 300).Select(i => (byte)i).ToArray();
        var (api, capturas) = Api(c =>
        {
            var desdeByte = c.Rango is { } r ? int.Parse(r["bytes=".Length..^1]) : 0;
            var respuesta = new HttpResponseMessage(c.Rango is null ? HttpStatusCode.OK : HttpStatusCode.PartialContent) { Content = new ByteArrayContent(contenido[desdeByte..]) };
            if (c.Rango is not null) respuesta.Content.Headers.ContentRange = new System.Net.Http.Headers.ContentRangeHeaderValue(desdeByte, contenido.Length - 1, contenido.Length);
            return respuesta;
        });

        using var entero = (await api.ArchivoAsync(Dispositivo, "paq-1", "vid 1"))!;
        using var desde = (await api.ArchivoAsync(Dispositivo, "paq-1", "vid-1", desdeByte: 100, alumnoId: "ana"))!;

        Assert.Equal((HttpMethod.Get, $"{Base}paquetes/paq-1/archivos/vid%201/?dispositivo=student-TAB07"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Null(capturas[0].Rango);
        Assert.Equal($"{Base}paquetes/paq-1/archivos/vid-1/?dispositivo=student-TAB07&alumno_id=ana", capturas[1].Url);
        Assert.Equal("bytes=100-", capturas[1].Rango);
        Assert.Equal(HttpStatusCode.OK, entero.StatusCode);
        Assert.Equal(contenido, await entero.Content.ReadAsByteArrayAsync());
        Assert.Equal(HttpStatusCode.PartialContent, desde.StatusCode);
        Assert.Equal(100, desde.Content.Headers.ContentRange!.From);
        Assert.Equal(contenido[100..], await desde.Content.ReadAsByteArrayAsync());
        Assert.Null(api.UltimoError);

        using var desdeElPrincipio = (await api.ArchivoAsync(Dispositivo, "paq-1", "vid-1", desdeByte: 0))!;
        Assert.Equal("bytes=0-", capturas[2].Rango);                                              // un 0 explícito sí es un Range válido
        using var negativo = (await api.ArchivoAsync(Dispositivo, "paq-1", "vid-1", desdeByte: -5))!;
        Assert.Null(capturas[3].Rango);                                                           // uno negativo no tiene sentido: se pide entero
    }

    [Fact]
    public async Task Archivo_LoDevuelveSinLeerElCuerpo_ParaBajarloPorPartes()
    {
        // El cuerpo tarda: si el cliente lo esperara entero (ResponseHeadersRead), la respuesta no llegaría hasta después de que termine.
        var cuerpoListo = new TaskCompletionSource();
        var http = new HttpClient(new ManejadorFalso((_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StreamContent(new FlujoDePrueba(new byte[50_000], cortarEn: 20_000, alCortar: () => cuerpoListo.TrySetResult())),
        })));
        var api = new EstudioApi(http, new Uri("http://192.168.0.55:8000/"));

        using var respuesta = (await api.ArchivoAsync(Dispositivo, "paq-1", "vid-1"))!;
        Assert.NotNull(respuesta);
        await using var flujo = await respuesta.Content.ReadAsStreamAsync();
        var lectura = new byte[8_000];
        Assert.Equal(8_000, await flujo.ReadAsync(lectura));                                                       // el primer tramo llega antes de que el cuerpo termine
        Assert.False(cuerpoListo.Task.IsCompleted);
    }

    [Theory]
    [InlineData(404, "no_encontrado")]
    [InlineData(410, "paquete_vencido")]
    [InlineData(416, "rango_invalido")]
    [InlineData(403, "descarga_denegada")]
    public async Task Archivo_ConUnErrorHttp_DevuelveNull_LiberaLaRespuesta_YDejaElCodigo(int estado, string codigo)
    {
        var respuestas = new List<HttpResponseMessage>();
        var http = new HttpClient(new ManejadorFalso((_, _) =>
        {
            var r = Ayudas.Respuesta((HttpStatusCode)estado, $$"""{"detail":"no","codigo":"{{codigo}}"}""");
            respuestas.Add(r);
            return Task.FromResult(r);
        }));
        var api = new EstudioApi(http, new Uri("http://192.168.0.55:8000/"));

        Assert.Null(await api.ArchivoAsync(Dispositivo, "paq-1", "vid-1", 50));

        Assert.Equal((estado, codigo), (api.UltimoError!.Estado, api.UltimoError.Codigo));
        Assert.Throws<ObjectDisposedException>(() => respuestas[0].Content.ReadAsStringAsync().GetAwaiter().GetResult());   // no se dejó una respuesta abierta sin dueño
    }

    [Fact]
    public async Task Archivo_SinRed_DevuelveNull_ConEstadoCero()
    {
        var api = new EstudioApi(new HttpClient(new ManejadorFalso((_, _) => throw new HttpRequestException("sin ruta"))), new Uri("http://192.168.0.55:8000/"));
        Assert.Null(await api.ArchivoAsync(Dispositivo, "paq-1", "vid-1"));
        Assert.Equal(0, api.UltimoError!.Estado);
    }

    [Fact]
    public async Task Confirmar_YRetirar_VanPorSusRutas()
    {
        var (api, capturas) = Api(c => c.Metodo == HttpMethod.Delete
            ? new HttpResponseMessage(HttpStatusCode.NoContent)
            : Ayudas.Respuesta(HttpStatusCode.OK, Envuelto(PaqueteJson.Replace("solicitado", "disponible"))));

        var confirmado = await api.ConfirmarPaqueteAsync(Dispositivo, "paq-1", "h1", 300, "ana");
        var retirado = await api.RetirarPaqueteAsync(Dispositivo, "paq-1");
        await api.RetirarPaqueteAsync(Dispositivo, "paq 1", "ana");

        Assert.Equal((HttpMethod.Post, $"{Base}paquetes/paq-1/confirmar/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(["alumno_id", "bytes", "dispositivo", "huella"], capturas[0].Claves);
        Assert.Equal(("h1", 300), (capturas[0].Json.GetProperty("huella").GetString(), capturas[0].Json.GetProperty("bytes").GetInt32()));
        Assert.Equal("disponible", confirmado!.Estado);
        Assert.Equal((HttpMethod.Delete, $"{Base}paquetes/paq-1/?dispositivo=student-TAB07"), (capturas[1].Metodo, capturas[1].Url));
        Assert.Equal($"{Base}paquetes/paq%201/?dispositivo=student-TAB07&alumno_id=ana", capturas[2].Url);
        Assert.Null(capturas[1].Cuerpo);
        Assert.True(retirado);

        var (mala, _) = Api(HttpStatusCode.Conflict, """{"detail":"La huella no coincide.","codigo":"huella_invalida"}""");
        Assert.Null(await mala.ConfirmarPaqueteAsync(Dispositivo, "paq-1", "otra", 300));
        Assert.Equal("huella_invalida", mala.UltimoError!.Codigo);
        var (noHay, _) = Api(HttpStatusCode.NotFound, """{"detail":"No existe.","codigo":"no_encontrado"}""");
        Assert.False(await noHay.RetirarPaqueteAsync(Dispositivo, "paq-9"));
        Assert.Equal(404, noHay.UltimoError!.Estado);
    }

    // ------------------------------------------------------------------------ trabajo sin red

    [Fact]
    public async Task Sincronizar_EnviaLosEventosConSuCargaIntacta_YMapeaElAcuse()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """
            {"acuse":true,"servidor_en":555,
             "resultados":[{"secuencia":1,"estado":"integrado","motivo":"","detalle":{"tarea":"asig-1"}},{"secuencia":2,"estado":"rechazado","motivo":"bloques_pendientes","detalle":null},
                           {"secuencia":3,"estado":"pendiente_decision","motivo":"fuera_de_plazo","detalle":null}],
             "resumen":{"integrados":1,"duplicados":0,"rechazados":1,"pendientes_decision":1},
             "asignaciones":[{"id":"asig-1","tarea":null}],
             "veredictos":[{"asignacion_id":"asig-1","objeto_ref":"act-1","numero":2,"pregunta_ref":"q1","veredicto":{"pregunta_ref":"q1","correcta":true,"puntaje":1,"puntaje_maximo":1,"pendiente":false,"retroalimentacion":[]}}]}
            """);
        var eventos = new[]
        {
            new EventoEstudio(1, TiposEventoEstudio.BloqueVisto, 1759000000100, 1759000000000, Ayudas.Json("""{"asignacion_id":"asig-1","bloques_vistos":["b1"],"posicion_seg":null}""")),
            new EventoEstudio(2, TiposEventoEstudio.LeccionCompletada, 1759000000200, null, Ayudas.Json("""{"asignacion_id":"asig-1"}""")),
            new EventoEstudio(3, TiposEventoEstudio.RespuestaEnviada, 1759000000300, 1759000000250, Ayudas.Json("""{"asignacion_id":"asig-1","objeto_ref":"act-1","intento_numero":2,"pregunta_ref":"q1","respuesta":{"value":true},"secuencia_respuesta":1}""")),
        };

        var acuse = await api.SincronizarAsync(Dispositivo, "emisor-1", eventos, "ana");
        await api.SincronizarAsync(Dispositivo, "emisor-1", eventos[1..2]);

        Assert.Equal((HttpMethod.Post, $"{Base}sync/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(["alumno_id", "dispositivo", "emisor_id", "eventos"], capturas[0].Claves);
        Assert.Equal(["dispositivo", "emisor_id", "eventos"], capturas[1].Claves);
        Assert.NotNull(capturas[0].Longitud);
        var enviados = capturas[0].Json.GetProperty("eventos");
        Assert.Equal(["carga", "ocurrido_en", "ocurrido_en_tableta", "secuencia", "tipo"], enviados[0].EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal).ToArray());
        Assert.Equal(["carga", "ocurrido_en", "secuencia", "tipo"], enviados[1].EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal).ToArray());   // la hora cruda opcional no viaja si no hay
        Assert.Equal((1L, "study.block.viewed", 1759000000100L, 1759000000000L), (enviados[0].GetProperty("secuencia").GetInt64(), enviados[0].GetProperty("tipo").GetString(), enviados[0].GetProperty("ocurrido_en").GetInt64(), enviados[0].GetProperty("ocurrido_en_tableta").GetInt64()));
        Assert.Equal(JsonValueKind.Null, enviados[0].GetProperty("carga").GetProperty("posicion_seg").ValueKind);   // los nulos de la carga sí viajan
        Assert.Equal(2, enviados[2].GetProperty("carga").GetProperty("intento_numero").GetInt32());

        Assert.True(acuse!.Acuse);
        Assert.Equal(555, acuse.ServidorEn);
        Assert.Equal([(1L, "integrado"), (2L, "rechazado"), (3L, "pendiente_decision")], acuse.Resultados.Select(r => (r.Secuencia, r.Estado)).ToArray());
        Assert.True(acuse.Resultados[0].Integrado);
        Assert.Equal("asig-1", acuse.Resultados[0].Detalle!.Value.GetProperty("tarea").GetString());
        Assert.Equal("bloques_pendientes", acuse.Resultados[1].Motivo);
        Assert.Equal((1, 0, 1, 1), (acuse.Resumen!.Integrados, acuse.Resumen.Duplicados, acuse.Resumen.Rechazados, acuse.Resumen.PendientesDecision));
        Assert.Equal("asig-1", acuse.Asignaciones![0].Id);
        Assert.Equal(("act-1", 2, "q1", true), (acuse.Veredictos![0].ObjetoRef, acuse.Veredictos[0].Numero, acuse.Veredictos[0].PreguntaRef, acuse.Veredictos[0].Veredicto!.Correcta));
    }

    [Fact]
    public async Task EstadoSync_EsUnGetConElEmisor()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """
            {"emisor_id":"emisor-1","ultima_secuencia":12,"conteos":{"synced":10,"rejected":1,"conflict":1},
             "pendientes_decision":[{"secuencia":7,"tipo":"study.answer.submitted","asignacion_id":"asig-1","motivo":"fuera_de_plazo"}]}
            """);
        var estado = await api.EstadoSyncAsync(Dispositivo, "emisor 1");
        Assert.Equal((HttpMethod.Get, $"{Base}sync/status/?dispositivo=student-TAB07&emisor_id=emisor%201"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(("emisor-1", 12L, 10, 1, 1), (estado!.EmisorId, estado.UltimaSecuencia, estado.Conteos!.Synced, estado.Conteos.Rejected, estado.Conteos.Conflict));
        Assert.Equal((7L, "asig-1", "fuera_de_plazo"), (estado.PendientesDecision![0].Secuencia, estado.PendientesDecision[0].AsignacionId, estado.PendientesDecision[0].Motivo));
    }

    // ------------------------------------------------------------------------------ profesor

    private const string AsignacionDocenteJson = """
        {"id":"asig-1","titulo":"Área y volumen","consigna":"Lee y practica","asignatura":"Matemáticas","unidad":"Unidad 2","grupo_id":"g-1","grupo_rotulo":"6.º A",
         "curso":{"fuente":"biblioteca","curso_ref":"curso-1","version":"1.0.0","titulo":"Mates"},"leccion_ref":"l1","fecha_limite":1759600000000,"plazo":"endurecido","gracia_ms":900000,
         "estado":"activa","alcance":"grupo","paquete_permitido":true,"destinatarios_total":3,"completaron":1,"en_curso":1,"pendientes":1,"fuera_de_plazo":0,"pendientes_decision":1,"creada_en":1759000000000,
         "alumnos":[{"alumno_id":"ana","rotulo":"Ana Pérez","estado":"completada","vencida":false,"fuera_de_plazo":false,"avance_pct":100,"bloques_atendidos":7,"bloques_total":7,
                     "ultimo_avance_en":9,"completada_en":10,"practica":{"intentos":2,"mejor_correctas":7,"total":8},"paquete":{"estado":"disponible"},
                     "dispositivo":{"id":"d-1","nombre":"Tableta 07","perfil":"asignado"},"pendientes_decision":0}]}
        """;

    [Fact]
    public async Task Docente_Grupos_Y_Asignaciones_LlevanElActorEnLaConsulta()
    {
        var (api, capturas) = Api(c => Ayudas.Respuesta(HttpStatusCode.OK, c.Url.Contains("/grupos/")
            ? """{"instalado":true,"grupos":[{"id":"g-1","codigo":"6A","nombre":"6.º A","nivel_clave":"lower_secondary","alumnos":[{"id":"ana","rotulo":"Ana Pérez"}]}]}"""
            : $$"""{"asignaciones":[{{AsignacionDocenteJson}}]}"""));

        var grupos = await api.GruposAsync("prof-1");
        var lista = await api.AsignacionesDocenteAsync("prof-1", "g-1", "activa");
        await api.AsignacionesDocenteAsync("prof 2");

        Assert.Equal((HttpMethod.Get, $"{Base}docente/grupos/?actor=prof-1"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal($"{Base}docente/asignaciones/?grupo_id=g-1&estado=activa&actor=prof-1", capturas[1].Url);
        Assert.Equal($"{Base}docente/asignaciones/?actor=prof%202", capturas[2].Url);
        Assert.True(grupos!.Instalado);
        Assert.Equal(("6A", "lower_secondary", "Ana Pérez"), (grupos.Grupos[0].Codigo, grupos.Grupos[0].NivelClave, grupos.Grupos[0].Alumnos[0].Rotulo));
        var a = Assert.Single(lista!.Asignaciones);
        Assert.Equal(("asig-1", "endurecido", 3, 1, 1, 1, false), (a.Id, a.Plazo, a.DestinatariosTotal, a.Completaron, a.EnCurso, a.Pendientes, a.Cerrada));
    }

    [Fact]
    public async Task Docente_CrearAsignacion_EnviaElActorYSoloLosCamposDados()
    {
        var (api, capturas) = Api(HttpStatusCode.Created, AsignacionDocenteJson);
        var nueva = new NuevaAsignacion("grupo", "g-1", null, "curso-1", "biblioteca", "l1", Titulo: null, Consigna: "Lee y practica", FechaLimite: 1759600000000, Plazo: "endurecido", GraciaMin: 15);

        var creada = await api.CrearAsignacionAsync("prof-1", "Ms. Carter", nueva);
        await api.CrearAsignacionAsync("prof-1", null, new NuevaAsignacion("seleccion", null, ["ana", "beto"], "curso-1", null, "l1", PaquetePermitido: false));

        Assert.Equal((HttpMethod.Post, $"{Base}docente/asignaciones/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(["actor", "actor_rotulo", "alcance", "consigna", "curso_ref", "fecha_limite", "fuente", "gracia_min", "grupo_id", "leccion_ref", "paquete_permitido", "plazo"], capturas[0].Claves);
        Assert.Equal(("prof-1", "Ms. Carter", "grupo", 15, true), (capturas[0].Json.GetProperty("actor").GetString(), capturas[0].Json.GetProperty("actor_rotulo").GetString(),
                     capturas[0].Json.GetProperty("alcance").GetString(), capturas[0].Json.GetProperty("gracia_min").GetInt32(), capturas[0].Json.GetProperty("paquete_permitido").GetBoolean()));
        Assert.Equal(["actor", "alcance", "alumnos", "curso_ref", "leccion_ref", "paquete_permitido"], capturas[1].Claves);
        Assert.Equal(["ana", "beto"], capturas[1].Json.GetProperty("alumnos").EnumerateArray().Select(e => e.GetString()!).ToArray());
        Assert.False(capturas[1].Json.GetProperty("paquete_permitido").GetBoolean());

        Assert.Equal(("asig-1", "6.º A", "Lee y practica"), (creada!.Id, creada.GrupoRotulo, creada.Consigna));
    }

    [Fact]
    public async Task Docente_Detalle_TraeLaTablaDeQuienCompleto()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, AsignacionDocenteJson);
        var detalle = await api.AsignacionDocenteAsync("prof-1", "asig-1");
        Assert.Equal((HttpMethod.Get, $"{Base}docente/asignaciones/asig-1/?actor=prof-1"), (capturas[0].Metodo, capturas[0].Url));
        var fila = Assert.Single(detalle!.Alumnos!);
        Assert.Equal(("ana", "Ana Pérez", "completada", 100.0, 7, 7, 10L), (fila.AlumnoId, fila.Rotulo, fila.Estado, fila.AvancePct, fila.BloquesAtendidos, fila.BloquesTotal, fila.CompletadaEn));
        Assert.Equal((2, 7, 8, "disponible"), (fila.Practica!.Intentos, fila.Practica.MejorCorrectas, fila.Practica.Total, fila.Paquete!.Estado));
        Assert.Equal(("d-1", "asignado", 0), (fila.Dispositivo!.Id, fila.Dispositivo.Perfil, fila.PendientesDecision));
    }

    [Fact]
    public async Task Docente_Cambiar_EsUnPatch_ConSoloLoQueCambia_YQuitarLaFechaEsUnNuloExplicito()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, AsignacionDocenteJson);

        await api.CambiarAsignacionAsync("prof-1", "asig-1", new CambiosAsignacion(FechaLimite: 1759700000000, Plazo: "endurecido", GraciaMin: 5));
        await api.CambiarAsignacionAsync("prof-1", "asig-1", new CambiosAsignacion(QuitarFecha: true, PaquetePermitido: false));
        await api.CambiarAsignacionAsync("prof-1", "asig-1", new CambiosAsignacion(Titulo: "Otro título"));

        Assert.All(capturas, c => Assert.Equal((HttpMethod.Patch, $"{Base}docente/asignaciones/asig-1/"), (c.Metodo, c.Url)));
        Assert.Equal(["actor", "fecha_limite", "gracia_min", "plazo"], capturas[0].Claves);
        Assert.Equal(1759700000000, capturas[0].Json.GetProperty("fecha_limite").GetInt64());
        Assert.Equal(["actor", "fecha_limite", "paquete_permitido"], capturas[1].Claves);
        Assert.Equal(JsonValueKind.Null, capturas[1].Json.GetProperty("fecha_limite").ValueKind);                    // «quitar la fecha» se dice con nulo
        Assert.False(capturas[1].Json.GetProperty("paquete_permitido").GetBoolean());
        Assert.Equal(["actor", "titulo"], capturas[2].Claves);                                                         // sin tocar la fecha: la clave no viaja
    }

    [Fact]
    public async Task Docente_CerrarYDecidir_VanPorSusRutas()
    {
        var (api, capturas) = Api(c => c.Url.EndsWith("/cerrar/") ? Ayudas.Respuesta(HttpStatusCode.OK, AsignacionDocenteJson.Replace("\"activa\"", "\"cerrada\"")) : Ayudas.Respuesta(HttpStatusCode.OK, """{"ok":true}"""));

        var cerrada = await api.CerrarAsignacionAsync("prof-1", "asig-1");
        var decidida = await api.DecidirAsync("prof-1", "asig-1", "ana", 7, "emisor-1", "aceptar");
        await api.DecidirAsync("prof-1", "asig-1", "ana", 8, null, "descartar");

        Assert.Equal((HttpMethod.Post, $"{Base}docente/asignaciones/asig-1/cerrar/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(["actor"], capturas[0].Claves);
        Assert.True(cerrada!.Cerrada);
        Assert.Equal((HttpMethod.Post, $"{Base}docente/asignaciones/asig-1/decisiones/"), (capturas[1].Metodo, capturas[1].Url));
        Assert.Equal(["actor", "alumno_id", "decision", "emisor_id", "secuencia"], capturas[1].Claves);
        Assert.Equal((7, "aceptar", "emisor-1"), (capturas[1].Json.GetProperty("secuencia").GetInt32(), capturas[1].Json.GetProperty("decision").GetString(), capturas[1].Json.GetProperty("emisor_id").GetString()));
        Assert.Equal(["actor", "alumno_id", "decision", "secuencia"], capturas[2].Claves);
        Assert.True(decidida);
    }

    // -------------------------------------------------------------- MOD-009 · asignar y liberar

    private const string DispositivoAsignadoJson = """
        {"id":"d-1","identificador_hw":"student-TAB07","nombre":"Tableta 07","tipo":"TABLETA","plataforma":"android","version_app":"0.4.2","activo":true,"bloqueado":false,"en_linea":true,
         "registrado_en":1,"ultimo_latido_en":2,"sesion_abierta":null,"perfil":"asignado","asignado_a":{"id":"ana","rotulo":"Ana Pérez"}}
        """;

    [Fact]
    public async Task Dispositivos_Asignar_Y_Liberar_VanPorLaRutaDeMod009()
    {
        var capturas = new List<Captura>();
        var api = new DispositivosApi(new HttpClient(new ManejadorFalso(async (req, _) =>
        {
            capturas.Add(new Captura(req.Method, req.RequestUri!.PathAndQuery, await req.Content!.ReadAsStringAsync(), req.Content.Headers.ContentLength, null, null));
            return Ayudas.Respuesta(HttpStatusCode.OK, req.RequestUri.AbsolutePath.EndsWith("/asignar/") ? DispositivoAsignadoJson : DispositivoAsignadoJson.Replace("\"asignado\"", "\"compartido\"").Replace("{\"id\":\"ana\",\"rotulo\":\"Ana Pérez\"}", "null"));
        })), new Uri("http://192.168.0.55:8000/"));

        var asignado = await api.AsignarAsync("d-1", "ana", "tecnico-1");
        var liberado = await api.LiberarAsync("d 1", "tecnico-1");

        Assert.Equal((HttpMethod.Post, "/api/dispositivos/d-1/asignar/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(["actor", "alumno_id"], capturas[0].Claves);
        Assert.Equal(("ana", "tecnico-1"), (capturas[0].Json.GetProperty("alumno_id").GetString(), capturas[0].Json.GetProperty("actor").GetString()));
        Assert.NotNull(capturas[0].Longitud);
        Assert.True(asignado!.Asignado);
        Assert.Equal(("asignado", "ana", "Ana Pérez"), (asignado.Perfil, asignado.AsignadoA!.Id, asignado.AsignadoA.Rotulo));
        Assert.Equal((HttpMethod.Post, "/api/dispositivos/d%201/liberar/"), (capturas[1].Metodo, capturas[1].Url));
        Assert.Equal(["actor"], capturas[1].Claves);
        Assert.False(liberado!.Asignado);
        Assert.Null(liberado.AsignadoA);
    }

    [Theory]
    [InlineData("asignar", "dispositivo_ya_asignado")]
    [InlineData("liberar", "paquete_sin_integrar")]
    public async Task Dispositivos_LosConflictosDe409_QuedanEnUltimoError(string accion, string codigo)
    {
        var api = new DispositivosApi(new HttpClient(new ManejadorFalso((_, _) => Task.FromResult(
            Ayudas.Respuesta(HttpStatusCode.Conflict, """{"detail":"No se puede.","codigo":"@CODIGO@","asignado_a":{"id":"beto"}}""".Replace("@CODIGO@", codigo))))), new Uri("http://192.168.0.55:8000/"));

        var resultado = accion == "asignar" ? await api.AsignarAsync("d-1", "ana", "t") : await api.LiberarAsync("d-1", "t");

        Assert.Null(resultado);
        Assert.Equal((codigo, 409, "No se puede."), (api.UltimoError!.Codigo, api.UltimoError.Estado, api.UltimoMotivo));
        Assert.Equal("beto", api.UltimoError.Extra!.Value.GetProperty("asignado_a").GetProperty("id").GetString());
    }

    // ------------------------------------------------------------------------- lo compartido

    [Fact]
    public async Task ElPaseDeSesion_ViajaEnLasRutasNuevas_IncluidoElArchivoEnStreaming()
    {
        ClienteJson.Token = "jwt-de-ana";
        var (api, capturas) = Api(c => c.Url.Contains("/archivos/")
            ? new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent([1, 2, 3]) }
            : Ayudas.Respuesta(HttpStatusCode.OK, PaqueteJson));

        await api.PaqueteAsync(Dispositivo, "paq-1");
        await api.ManifiestoCrudoAsync(Dispositivo, "paq-1");
        using var archivo = await api.ArchivoAsync(Dispositivo, "paq-1", "img-1");
        await api.ProgresoAsync(Dispositivo, "asig-1", ["b1"], null, null);
        await api.RetirarPaqueteAsync(Dispositivo, "paq-1");

        Assert.All(capturas, c => Assert.Equal("Bearer jwt-de-ana", c.Autorizacion));
    }

    [Fact]
    public async Task UnaSesionQueCaduca_AvisaPorElEventoDeSiempre_TambienEnLasRutasNuevas()
    {
        ClienteJson.Token = "jwt";
        ErrorAula? recibido = null;
        void Oyente(ErrorAula e) => recibido = e;
        ClienteJson.SesionRechazada += Oyente;
        try
        {
            var (api, _) = Api(HttpStatusCode.Unauthorized, """{"detail":"La sesión caducó.","codigo":"sesion_expirada"}""");
            Assert.Null(await api.ProgresoAsync(Dispositivo, "asig-1", ["b1"], null, null));
            Assert.True(recibido!.SesionPerdida);
        }
        finally { ClienteJson.SesionRechazada -= Oyente; }
    }

    [Fact]
    public void LaBaseYLasUrlAbsolutas_SeResuelvenComoEnElResto()
    {
        var api = new EstudioApi(new HttpClient(), new Uri("http://192.168.0.55:8000/"));
        Assert.Equal("http://192.168.0.55:8000/api/modo-estudio/asignaciones/asig-1/medios/img-1/", api.Absoluta("/api/modo-estudio/asignaciones/asig-1/medios/img-1/").AbsoluteUri);
        Assert.Equal(new Uri("http://192.168.0.55:8000/"), api.BaseUri);
    }
}

using System.Net;
using System.Text.Json;
using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// El cliente de <c>/api/gradebook/</c> contra un nodo falso: método, URL y cuerpo de cada ruta del contrato — los campos nulos NO viajan, el profesor manda
/// <c>actor</c>, todo cambio manda su <c>solicitud_id</c> y su <c>version_esperada</c> — y los errores con su código y sus extras.
/// </summary>
[Collection("estado global")]
public sealed class GradebookApiTests : IDisposable
{
    private const string Base = "/api/gradebook/";

    public GradebookApiTests() => ClienteJson.Token = null;
    public void Dispose() => ClienteJson.Token = null;

    private sealed record Captura(HttpMethod Metodo, string Url, string? Cuerpo)
    {
        public JsonElement Json => Ayudas.Json(Cuerpo!);
        public string[] Claves => Json.EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal).ToArray();
    }

    private static (GradebookApi Api, List<Captura> Capturas) Api(Func<Captura, HttpResponseMessage> responder)
    {
        var capturas = new List<Captura>();
        var http = new HttpClient(new ManejadorFalso(async (req, _) =>
        {
            var cuerpo = req.Content is null ? null : await req.Content.ReadAsStringAsync();
            var captura = new Captura(req.Method, req.RequestUri!.PathAndQuery, cuerpo);
            capturas.Add(captura);
            return responder(captura);
        }));
        return (new GradebookApi(http, new Uri("http://192.168.0.55:8000/")), capturas);
    }

    private static (GradebookApi Api, List<Captura> Capturas) Api(HttpStatusCode estado = HttpStatusCode.OK, string json = "{}") => Api(_ => Ayudas.Respuesta(estado, json));

    private static string Calificacion(int version = 2, string estado = "revisada") => $$"""
        {"calificacion":{"id":"c-1","intento_id":"i-1","asignacion_id":"a-1","alumno_id":"al-1","grupo_id":"g-1","nivel_clave":"secundaria","periodo":"2026","curso_ref":"curso",
        "numero_intento":1,"puntaje_original":71.43,"puntaje_efectivo":85.0,"ajustada":true,"regla_puntuacion":"mod10.porcentaje.v1","origen":"automatica","evaluador_id":"sistema",
        "estado":"{{estado}}","version":{{version}},"publicada":false,"registrada_en":1,"actualizada_en":2},"historial":[],"reintento":false,"servidor_en":3}
        """;

    // ---------------------------------------------------------------------------------------------- leer

    [Fact]
    public async Task Libro_EsUnGetConLosFiltrosQueSeDieron_SinCamposVacios()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"grupo":{"id":"g-1","codigo":"8A","nombre":"Octavo A","periodo":"2026","nivel_clave":"secundaria"},"modo":"simple","escala":null,"politica_intentos":"ultimo","asignaciones":[],"alumnos":[],"totales":{"alumnos":0,"asignaciones":0,"pendientes":0,"por_revisar":0,"sin_publicar":0},"servidor_en":1}""");
        var l = await api.LibroAsync("prof-1", "g-1");
        Assert.False(l!.EnModoCalificaciones);
        await api.LibroAsync("prof-1", "g-1", asignacionId: "a-1", periodo: "2026", cursoRef: "c r", busqueda: "ana lópez");
        Assert.Equal(Base + "libro/?grupo_id=g-1&actor=prof-1", capturas[0].Url);
        Assert.Equal(Base + "libro/?grupo_id=g-1&asignacion_id=a-1&periodo=2026&curso_ref=c%20r&q=ana%20l%C3%B3pez&actor=prof-1", capturas[1].Url);
        Assert.All(capturas, c => Assert.Equal(HttpMethod.Get, c.Metodo));
    }

    [Fact]
    public async Task Bandeja_Revision_Resumen_Calificacion_SonGets()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, "{}");
        await api.BandejaAsync("prof-1", grupoId: "g-1");
        await api.BandejaAsync("prof-1", asignacionId: "a 1");
        await api.RevisionAsync("prof-1", "i-1");
        await api.CalificacionAsync("prof-1", "c-1");
        await api.ResumenAsync("prof-1", "g-1", periodo: "2026");
        await api.ConfiguracionAsync("adm-1");
        await api.PlantillasAsync("adm-1", "co");
        Assert.Equal(new[]
        {
            Base + "revisiones/?grupo_id=g-1&actor=prof-1", Base + "revisiones/?asignacion_id=a%201&actor=prof-1", Base + "revisiones/i-1/?actor=prof-1",
            Base + "calificaciones/c-1/?actor=prof-1", Base + "resumen/?grupo_id=g-1&periodo=2026&actor=prof-1", Base + "configuracion/?actor=adm-1",
            Base + "escalas/plantillas/?pais=co&actor=adm-1",
        }, capturas.Select(c => c.Url).ToArray());
        Assert.All(capturas, c => Assert.Equal(HttpMethod.Get, c.Metodo));
    }

    // ---------------------------------------------------------------------------------- la revisión docente

    [Fact]
    public async Task Puntuar_ManualMandaPuntajeComentarioYSolicitud_LoNuloNoViaja()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"intento_id":"i-1","pregunta_ref":"q 5","numero":1,"tipo":"manual","puntaje":1.5,"pendientes":[],"listo_para_confirmar":true,"reintento":false}""");
        var r = await api.PuntuarAsync("prof-1", "i-1", "q 5", 1.5m, "Bien explicado", null, "sol-1");
        Assert.True(r!.ListoParaConfirmar);
        var c = capturas.Single();
        Assert.Equal((HttpMethod.Post, Base + "revisiones/i-1/respuestas/q%205/"), (c.Metodo, c.Url));
        Assert.Equal(new[] { "actor", "comentario", "puntaje", "solicitud_id" }, c.Claves);          // `motivo` nulo no viaja
        Assert.Equal(1.5m, c.Json.GetProperty("puntaje").GetDecimal());
    }

    [Fact]
    public async Task AplicarRubrica_MandaCadaCriterioConSusPuntos()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"intento_id":"i-1","pregunta_ref":"q","numero":1,"tipo":"rubrica","puntaje":3,"pendientes":[],"listo_para_confirmar":true,"reintento":false}""");
        await api.AplicarRubricaAsync("prof-1", "i-1", "q", [new CriterioPuntuado("r1", 1m), new CriterioPuntuado("r2", 1.5m)], "ok", "Recalificación", "sol-2");
        var c = capturas.Single();
        Assert.Equal(new[] { "actor", "comentario", "criterios", "motivo", "solicitud_id" }, c.Claves);
        var criterios = c.Json.GetProperty("criterios").EnumerateArray().ToList();
        Assert.Equal(("r1", 1m), (criterios[0].GetProperty("criterio_id").GetString(), criterios[0].GetProperty("puntos").GetDecimal()));
        Assert.Equal(1.5m, criterios[1].GetProperty("puntos").GetDecimal());
        Assert.False(c.Json.TryGetProperty("puntaje", out _));                                       // manual o rúbrica, nunca las dos
    }

    [Fact]
    public async Task ConfirmarRevision_EsUnPostSinMasQueElActor()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"intento_id":"i-1","estado":"calificado","resultado":"creada","registrada":true}""");
        var r = await api.ConfirmarRevisionAsync("prof-1", "i-1");
        Assert.True(r!.Registrada);
        Assert.Equal((HttpMethod.Post, Base + "revisiones/i-1/confirmar/"), (capturas.Single().Metodo, capturas.Single().Url));
        Assert.Equal(new[] { "actor" }, capturas.Single().Claves);
    }

    // ------------------------------------------------------------------------------------- cambios a una nota

    [Fact]
    public async Task Ajustar_MandaElNuevoValorElMotivoLaVersionYLaSolicitud()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, Calificacion());
        var r = await api.AjustarAsync("prof-1", "c-1", 85.25m, "Se reconoció una respuesta correcta", 1, "sol-aj-1");
        Assert.Equal(85.0m, r!.Calificacion.PuntajeEfectivo);
        var c = capturas.Single();
        Assert.Equal((HttpMethod.Post, Base + "calificaciones/c-1/ajustar/"), (c.Metodo, c.Url));
        Assert.Equal(new[] { "actor", "motivo", "puntaje_nuevo", "solicitud_id", "version_esperada" }, c.Claves);
        Assert.Equal(85.25m, c.Json.GetProperty("puntaje_nuevo").GetDecimal());                        // el decimal viaja exacto, sin pasar por double
        Assert.Equal(1, c.Json.GetProperty("version_esperada").GetInt32());
        Assert.Equal("sol-aj-1", c.Json.GetProperty("solicitud_id").GetString());
    }

    [Fact]
    public async Task ReabrirValorarRetroalimentarPublicarYRetirar_CadaUnoEnSuRuta()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, Calificacion());
        await api.ReabrirAsync("prof-1", "c-1", "El estudiante pidió revisar", 2, "s1");
        await api.ValorarAsync("prof-1", "c-1", "alto", "Su proceso fue superior", 2, "s2");
        await api.RetroalimentarAsync("prof-1", "c-1", new Dictionary<string, string> { ["fortalezas"] = "Razona bien" }, "Tiempo adicional", 2, "s3");
        await api.PublicarAsync("prof-1", "c-1");
        await api.PublicarAsync("prof-1", "c-1", 3, "s4");
        await api.RetirarPublicacionAsync("prof-1", "c-1", "Se publicó antes del acta", 4, "s5");
        await api.PublicarAsignacionAsync("prof-1", "a-1");
        Assert.Equal(new[]
        {
            Base + "calificaciones/c-1/reabrir/", Base + "calificaciones/c-1/valoracion/", Base + "calificaciones/c-1/retroalimentacion/", Base + "calificaciones/c-1/publicar/",
            Base + "calificaciones/c-1/publicar/", Base + "calificaciones/c-1/retirar-publicacion/", Base + "asignaciones/a-1/publicar/",
        }, capturas.Select(c => c.Url).ToArray());
        Assert.All(capturas, c => Assert.Equal(HttpMethod.Post, c.Metodo));
        Assert.Equal(new[] { "actor", "adaptacion", "fortalezas", "solicitud_id", "version_esperada" }, capturas[2].Claves);
        Assert.Equal(new[] { "actor" }, capturas[3].Claves);                                           // publicar sin versión ni solicitud: sólo el actor
        Assert.Equal(new[] { "actor", "solicitud_id", "version_esperada" }, capturas[4].Claves);
    }

    [Fact]
    public async Task Observar_EsUnPutConLasRecomendacionesElGrupoYLoOpcionalSoloSiViene()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"observacion":{"id":"o-1","alumno_id":"al-1","grupo_id":"g-1","periodo":"2026","curso_ref":"","recomendaciones":[{"codigo":"pedir_ayuda","texto":"Pedir ayuda"}],"texto":"","version":1,"actualizada_en":1,"actualizada_por":"prof-1"},"cambiado":true,"servidor_en":1}""");
        var r = await api.ObservarAsync("prof-1", "al-1", "g-1", ["pedir_ayuda"]);
        Assert.True(r!.Cambiado);
        Assert.True(r.Observacion.EsGeneral);
        await api.ObservarAsync("prof-1", "al-1", "g-1", ["pedir_ayuda", "entregar_a_tiempo"], "Va mejorando", "curso-1", 2);
        Assert.Equal((HttpMethod.Put, Base + "estudiantes/al-1/observacion/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(new[] { "actor", "grupo_id", "recomendaciones" }, capturas[0].Claves);
        Assert.Equal(new[] { "actor", "curso_ref", "grupo_id", "recomendaciones", "texto", "version_esperada" }, capturas[1].Claves);
        Assert.Equal(2, capturas[1].Json.GetProperty("recomendaciones").GetArrayLength());
    }

    [Fact]
    public async Task ElLibroYElBoletin_SeSegmentanPorMateriaConElCodigoDelArbol()
    {
        var (api, capturas) = Api();
        await api.LibroAsync("prof-1", "g-1", materia: "math");
        await api.LibroAsync("prof-1", "g-1", cursoRef: "curso-1", soloResumen: true);
        await api.BoletinAsync("prof-1", "al-1", "g-1", materia: "science");
        Assert.Equal(new[]
        {
            Base + "libro/?grupo_id=g-1&subject=math&actor=prof-1",
            Base + "libro/?grupo_id=g-1&curso_ref=curso-1&vista=resumen&actor=prof-1",
            Base + "estudiantes/al-1/boletin/?grupo_id=g-1&subject=science&limite=20&actor=prof-1",
        }, capturas.Select(c => c.Url).ToArray());
    }

    // ============================================================================================= configuración

    [Fact]
    public async Task Configuracion_AdoptarVistaPreviaValidarYConfigurarNivel()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, "{}");
        await api.AdoptarPlantillaAsync("adm-1", "co-1-5", jurisdiccion: "Antioquia");
        await api.VistaPreviaAsync("adm-1", "co-1-5", null, [0m, 50m, 100m]);
        await api.ValidarNivelAsync("adm-1", "secundaria", "calificaciones", "esc-1");
        await api.ConfigurarNivelAsync("adm-1", "preescolar", "simple", null);
        Assert.Equal((HttpMethod.Post, Base + "escalas/adoptar/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(new[] { "actor", "jurisdiccion", "plantilla" }, capturas[0].Claves);
        Assert.Equal((HttpMethod.Post, Base + "escalas/vista-previa/"), (capturas[1].Metodo, capturas[1].Url));
        Assert.Equal(new[] { "actor", "plantilla", "valores" }, capturas[1].Claves);
        Assert.Equal(3, capturas[1].Json.GetProperty("valores").GetArrayLength());
        Assert.Equal((HttpMethod.Put, Base + "niveles/secundaria/"), (capturas[2].Metodo, capturas[2].Url));
        Assert.Equal(new[] { "actor", "escala_id", "modo", "validar" }, capturas[2].Claves);
        Assert.True(capturas[2].Json.GetProperty("validar").GetBoolean());
        Assert.Equal(new[] { "actor", "modo" }, capturas[3].Claves);
        Assert.False(capturas[3].Json.TryGetProperty("validar", out _));
    }

    [Fact]
    public async Task ConfigurarPolitica_PutAPoliticaConSoloLaPoliticaDeIntentos()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, "{}");
        await api.ConfigurarPoliticaAsync("adm-1", "mejor");
        Assert.Equal((HttpMethod.Put, Base + "politica/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(new[] { "actor", "politica_intentos" }, capturas[0].Claves);
        Assert.Equal("mejor", capturas[0].Json.GetProperty("politica_intentos").GetString());
    }

    // ============================================================================================ el alumno

    [Fact]
    public async Task MisResultados_SeIdentificaConElAlumnoYElAparato_SinCamposVacios()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, """{"alumno_id":"al-1","items":[],"servidor_en":1}""");
        var r = await api.MisResultadosAsync("al-1", "student-TAB07");
        Assert.Empty(r!.Items);
        await api.MisResultadosAsync();
        Assert.Equal(Base + "mias/?alumno_id=al-1&dispositivo=student-TAB07", capturas[0].Url);
        Assert.Equal(Base + "mias/", capturas[1].Url);
    }

    // ================================================================================================ errores

    [Fact]
    public async Task UnConflictoDeVersion_DejaElCodigoYLaVersionActual_SinLanzarExcepcion()
    {
        var (api, _) = Api(HttpStatusCode.Conflict, """{"codigo":"conflicto_de_version","detail":"Otra persona cambió esta calificación","version_actual":4,"puntaje_efectivo":90.0,"estado":"revisada"}""");
        var r = await api.AjustarAsync("prof-1", "c-1", 60m, "Por una razón de peso", 1, "s1");
        Assert.Null(r);
        Assert.Equal((409, "conflicto_de_version"), (api.UltimoError!.Estado, api.UltimoError.Codigo));
        Assert.True(GradebookTexto.EsConflictoDeVersion(api.UltimoError));
        Assert.Equal(4, GradebookTexto.VersionActual(api.UltimoError));
        Assert.Contains("Otra persona", GradebookTexto.Error(api.UltimoError, api.UltimoMotivo));
    }

    [Fact]
    public async Task UnPermisoDenegado_DejaElCodigo()
    {
        var (api, _) = Api(HttpStatusCode.Forbidden, """{"codigo":"sin_permiso","detail":"Tu rol no tiene concedido grades.modify.","permiso":"grades.modify"}""");
        Assert.Null(await api.AjustarAsync("tec-1", "c-1", 60m, "Intento no autorizado", 1, "s1"));
        Assert.Equal((403, "sin_permiso"), (api.UltimoError!.Estado, api.UltimoError.Codigo));
        Assert.False(GradebookTexto.SinConexion(api.UltimoError));
    }

    [Fact]
    public async Task SinConexionConElNodo_NoEsUnaExcepcionYSeDiceAsi()
    {
        var http = new HttpClient(new ManejadorFalso((_, _) => throw new HttpRequestException("sin red")));
        var api = new GradebookApi(http, new Uri("http://192.168.0.55:8000/"));
        Assert.Null(await api.AjustarAsync("prof-1", "c-1", 60m, "Por una razón de peso", 1, "s1"));
        Assert.True(GradebookTexto.SinConexion(api.UltimoError));
        Assert.Contains("Sin conexión con el nodo", GradebookTexto.Error(api.UltimoError, api.UltimoMotivo));
        Assert.Contains("sin duplicar", GradebookTexto.Error(api.UltimoError, api.UltimoMotivo));         // reintentar con la misma solicitud es seguro
    }

    [Fact]
    public async Task ConLaSesionObligatoria_ElPaseViajaEnCadaPeticion()
    {
        ClienteJson.Token = "pase-123";
        string? autorizacion = null;
        var http = new HttpClient(new ManejadorFalso((req, _) =>
        {
            autorizacion = req.Headers.Authorization?.ToString();
            return Task.FromResult(Ayudas.Respuesta(HttpStatusCode.OK, """{"alumno_id":"a","items":[],"servidor_en":1}"""));
        }));
        await new GradebookApi(http, new Uri("http://192.168.0.55:8000/")).MisResultadosAsync();
        Assert.Equal("Bearer pase-123", autorizacion);
    }
}

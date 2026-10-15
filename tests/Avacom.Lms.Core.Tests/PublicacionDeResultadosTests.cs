using System.Net;
using System.Text.Json;
using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// RF-004 (publicación de resultados) y RF-002/RF-003 (número de preguntas) en el cliente: los DTOs contra respuestas REALES del backend
/// (<c>Fixtures/evaluacion/</c>, capturadas por <c>test_capturar_contrato.py</c>) y las tres rutas nuevas del cliente (ficha del examen, política de
/// publicación, publicar a un alumno) con su método, URL y cuerpo. Los campos nulos no viajan.
/// </summary>
[Collection("estado global")]
public sealed class PublicacionDeResultadosTests : IDisposable
{
    private const string Base = "/api/evaluacion/";

    public PublicacionDeResultadosTests() => ClienteJson.Token = null;
    public void Dispose() => ClienteJson.Token = null;

    private static string Leer(string nombre) => File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "evaluacion", nombre + ".json"));

    private static T Cargar<T>(string nombre) =>
        JsonSerializer.Deserialize<T>(Leer(nombre), Ayudas.Web) ?? throw new InvalidOperationException($"{nombre}.json no se pudo leer como {typeof(T).Name}.");

    private sealed record Captura(HttpMethod Metodo, string Url, string? Cuerpo)
    {
        public JsonElement Json => Ayudas.Json(Cuerpo!);
        public string[] Claves => Json.EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal).ToArray();
    }

    private static (EvaluacionApi Api, List<Captura> Capturas) Api(HttpStatusCode estado = HttpStatusCode.OK, string json = "{}")
    {
        var capturas = new List<Captura>();
        var http = new HttpClient(new ManejadorFalso(async (req, _) =>
        {
            capturas.Add(new Captura(req.Method, req.RequestUri!.PathAndQuery, req.Content is null ? null : await req.Content.ReadAsStringAsync()));
            return Ayudas.Respuesta(estado, json);
        }));
        return (new EvaluacionApi(http, new Uri("http://192.168.0.55:8000/")), capturas);
    }

    // ------------------------------------------------------------------------------------------ los contratos

    [Fact]
    public void FichaDelExamen_DiceElBancoLosTemasYLoQueSugiere_SinPreguntasNiClaves()
    {
        var f = Cargar<FichaDeExamen>("ficha_examen");
        Assert.Equal((12, 12, "fixed", "1.0.0"), (f.TotalBanco, f.PreguntasSugeridas, f.Estrategia, f.CursoVersion));
        Assert.Equal(new[] { "t-changes", "t-states" }, f.Temas);
        Assert.Equal(6, f.Tipos!.Count);
        Assert.Equal(2, f.Tipos["open"]);
        Assert.Equal(("tras_liberar", "tras_liberar"), (f.ResultadosSugeridos, f.ResultadosPorDefecto));
        Assert.Equal(700, f.Tiempo!.EstimadoBancoSeg);
        var texto = Leer("ficha_examen").ToLowerInvariant();
        Assert.DoesNotContain("iscorrect", texto);
        Assert.DoesNotContain("\"prompt\"", texto);
    }

    [Fact]
    public void LaAsignacion_TraeLaPoliticaLaFechaYQuienPublico()
    {
        var a = Cargar<AsignacionDeExamen>("asignacion");
        Assert.Equal((PoliticasDeResultados.TrasLiberar, null, null, "", 12, "fixed"), (a.Resultados, a.PublicarEn, a.LiberadosEn, a.LiberadosPor, a.TotalBanco, a.Estrategia));
        Assert.False(a.ResultadosPublicados);
        var publicada = Cargar<AsignacionDeExamen>("asignacion_publicada");
        Assert.True(publicada.ResultadosPublicados);
        Assert.True(publicada.LiberadosEn > 0);
        Assert.False(string.IsNullOrEmpty(publicada.LiberadosPor));      // quién publicó, siempre
        Assert.NotEqual("sistema", publicada.LiberadosPor);               // lo publicó el profesor, no la política
    }

    [Fact]
    public void LosResultadosDelProfesor_DicenQueVeYaCadaAlumno()
    {
        var r = Cargar<ResultadosDeExamen>("resultados");
        Assert.Equal((PoliticasDeResultados.TrasLiberar, null, null, ""), (r.Resultados, r.PublicarEn, r.LiberadosEn, r.LiberadosPor));
        var fila = Assert.Single(r.Filas);
        Assert.True(fila.Definitivo);
        Assert.False(fila.ResultadoPublicado);                             // calificado, pero el alumno todavía no lo ve
        Assert.True(fila.ListoParaPublicar);
        Assert.NotNull(fila.Porcentaje);                                   // el profesor sí ve la nota antes de publicar
    }

    [Fact]
    public void PublicarAUnAlumno_DevuelveQuienYCuando()
    {
        var r = Cargar<ResultadoLiberado>("resultado_liberado");
        Assert.Equal(EstadosIntento.Calificado, r.Estado);
        Assert.True(r.LiberadoEn > 0);
        Assert.False(string.IsNullOrEmpty(r.LiberadoPor));
        Assert.True(r.ResultadoPublicado);
    }

    [Fact]
    public void ElPanel_TraeLosContadoresDePublicacionYRevision()
    {
        var p = Cargar<PanelDeExamen>("panel");
        Assert.Equal((PoliticasDeResultados.TrasLiberar, null), (p.Asignacion.Resultados, p.Asignacion.PublicarEn));
        Assert.Equal(12, p.Asignacion.TotalBanco);
        Assert.Equal((0, 0, 0), (p.Totales.ListosParaPublicar, p.Totales.Publicados, p.Totales.ReactivosPorRevisar));   // Juan todavía presenta
        var fila = Assert.Single(p.Filas);
        Assert.False(fila.ResultadoPublicado);
        Assert.False(fila.ListoParaPublicar);
    }

    [Fact]
    public void LaEntregaYMisEvaluaciones_DicenCuandoSinRevelarLaNota()
    {
        var e = Cargar<EntregaDeIntento>("entrega");
        Assert.Equal((PoliticasDeResultados.TrasLiberar, null, false), (e.Resultados, e.PublicarEn, e.ResultadoDisponible));
        Assert.DoesNotContain("porcentaje", Leer("entrega"));
        var mias = Cargar<MisEvaluaciones>("mias");
        var mia = mias.Pendientes.Single();
        Assert.Equal((PoliticasDeResultados.TrasLiberar, null), (mia.Resultados, mia.PublicarEn));
        Assert.DoesNotContain("porcentaje", Leer("mias"));
        Assert.DoesNotContain("puntaje", Leer("mias"));
        var antesala = Cargar<AntesalaDeExamen>("antesala");
        Assert.Equal(PoliticasDeResultados.TrasLiberar, antesala.Asignacion.Resultados);
        Assert.Null(antesala.Asignacion.PublicarEn);
    }

    [Fact]
    public void Politicas_NormalizanLosSinonimosDelDocumentoDeRequisitos()
    {
        Assert.Equal(PoliticasDeResultados.AlEntregar, PoliticasDeResultados.Normalizar("inmediata"));
        Assert.Equal(PoliticasDeResultados.TrasLiberar, PoliticasDeResultados.Normalizar("manual"));
        Assert.Equal(PoliticasDeResultados.TrasLiberar, PoliticasDeResultados.Normalizar(null));
        Assert.Equal(PoliticasDeResultados.Programada, PoliticasDeResultados.Normalizar("programada"));
    }

    // ------------------------------------------------------------------------------------------ las rutas

    [Fact]
    public void ExamenesDisponibles_SalenDelBackendRealYDicenCuantasVecesSeAplicaron()
    {
        var d = Cargar<ExamenesDisponibles>("examenes_disponibles");
        Assert.True(d.Disponible);
        Assert.Equal(1, d.Total);
        var curso = Assert.Single(d.Cursos);
        Assert.Equal("Estados de la materia y sus cambios", curso.Titulo);
        var examen = Assert.Single(curso.Examenes);
        Assert.Equal(("l3-exam", 12, 2, 1), (examen.ObjetoRef, examen.Preguntas, examen.Aplicaciones, examen.Abiertas));
        Assert.Empty(d.Omitidos!);
        var texto = Leer("examenes_disponibles").ToLowerInvariant();
        Assert.DoesNotContain("iscorrect", texto);       // sólo referencias y rótulos: ni una pregunta ni una clave
        Assert.DoesNotContain("\"prompt\"", texto);
    }

    [Fact]
    public async Task ExamenesDisponibles_EsUnGetConLaFuenteYElActor()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, Leer("examenes_disponibles"));
        var d = await api.ExamenesDisponiblesAsync("p", "biblioteca");
        Assert.Equal(1, d!.Total);
        var c = capturas.Single();
        Assert.Equal((HttpMethod.Get, Base + "examenes/disponibles/?fuente=biblioteca&actor=p"), (c.Metodo, c.Url));
    }

    [Fact]
    public async Task ExamenesDisponibles_ConLaBibliotecaCerrada_DiceElMotivoSinRomperse()
    {
        var (api, _) = Api(HttpStatusCode.OK, """{"fuente":"biblioteca","disponible":false,"motivo":"AVACOM Contenido no está abierto.","sugerencia":"Ábrelo.","cursos":[],"omitidos":[]}""");
        var d = await api.ExamenesDisponiblesAsync("p", "biblioteca");
        Assert.Equal((false, 0, "AVACOM Contenido no está abierto."), (d!.Disponible, d.Total, d.Motivo));
    }

    [Fact]
    public async Task ExamenesDisponibles_SinPermiso_Es403ConSuCodigo()
    {
        var (api, _) = Api(HttpStatusCode.Forbidden, """{"detail":"No.","codigo":"sin_permiso"}""");
        Assert.Null(await api.ExamenesDisponiblesAsync("alumno", "biblioteca"));
        Assert.Equal(("sin_permiso", 403), (api.UltimoError!.Codigo, api.UltimoError.Estado));
    }

    [Fact]
    public async Task Ficha_EsUnGetConFuenteCursoYExamenEnLaConsulta()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, Leer("ficha_examen"));
        var f = await api.FichaAsync("p", "biblioteca", "curso-1", "l3-exam");
        Assert.Equal(12, f!.TotalBanco);
        var c = capturas.Single();
        Assert.Equal((HttpMethod.Get, Base + "examenes/?fuente=biblioteca&curso_ref=curso-1&objeto_ref=l3-exam&actor=p"), (c.Metodo, c.Url));
    }

    [Fact]
    public async Task ConfigurarPublicacion_EsUnPatchConLaPoliticaYSoloConFechaSiLaHay()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, Leer("asignacion"));
        await api.ConfigurarPublicacionAsync("p", "a-1", PoliticasDeResultados.Programada, 1_790_000_000_000);
        await api.ConfigurarPublicacionAsync("p", "a-1", PoliticasDeResultados.AlFinalizarGrupo);
        Assert.All(capturas, c => Assert.Equal((HttpMethod.Patch, Base + "asignaciones/a-1/publicacion/"), (c.Metodo, c.Url)));
        Assert.Equal(new[] { "actor", "publicar_en", "resultados" }, capturas[0].Claves);
        Assert.Equal(1_790_000_000_000, capturas[0].Json.GetProperty("publicar_en").GetInt64());
        Assert.Equal(new[] { "actor", "resultados" }, capturas[1].Claves);          // sin fecha, la clave no viaja
    }

    [Fact]
    public async Task LiberarResultadoDeUnAlumno_EsUnPostSobreElIntento()
    {
        var (api, capturas) = Api(HttpStatusCode.OK, Leer("resultado_liberado"));
        var r = await api.LiberarResultadoAsync("p", "i-1");
        Assert.True(r!.ResultadoPublicado);
        var c = capturas.Single();
        Assert.Equal((HttpMethod.Post, Base + "intentos/i-1/liberar-resultado/"), (c.Metodo, c.Url));
        Assert.Equal(new[] { "actor" }, c.Claves);
    }

    [Fact]
    public async Task LiberarResultado_Con409_DevuelveNullYElCodigo()
    {
        var (api, _) = Api(HttpStatusCode.Conflict, """{"detail":"Quedan 2 reactivo(s) sin puntuar.","codigo":"reactivos_pendientes","pendientes":["q-5","q-9"]}""");
        Assert.Null(await api.LiberarResultadoAsync("p", "i-1"));
        Assert.Equal(("reactivos_pendientes", 409), (api.UltimoError!.Codigo, api.UltimoError.Estado));
    }

    [Fact]
    public async Task Crear_LlevaPreguntasYFechaDePublicacionSoloCuandoSeEligen()
    {
        var (api, capturas) = Api(HttpStatusCode.Created, Leer("asignacion"));
        var basico = new NuevoExamen("biblioteca", "curso-1", "l3-exam", Niveles.Abierto, "g-1");
        await api.CrearAsync("p", "Prof.", basico);
        await api.CrearAsync("p", "Prof.", basico with { Preguntas = 20, Resultados = PoliticasDeResultados.Programada, PublicarEn = 123, Estrategia = "random_balanced", MezclarOpciones = false });
        Assert.DoesNotContain("preguntas", capturas[0].Claves);
        Assert.DoesNotContain("publicar_en", capturas[0].Claves);
        Assert.Equal("tras_liberar", capturas[0].Json.GetProperty("resultados").GetString());   // el valor seguro por defecto
        var j = capturas[1].Json;
        Assert.Equal((20, "programada", 123L, "random_balanced", false),
            (j.GetProperty("preguntas").GetInt32(), j.GetProperty("resultados").GetString(), j.GetProperty("publicar_en").GetInt64(),
             j.GetProperty("estrategia").GetString(), j.GetProperty("mezclar_opciones").GetBoolean()));
    }
}

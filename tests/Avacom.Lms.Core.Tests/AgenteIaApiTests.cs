using System.Net;
using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.AgenteIa;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// El cliente de <c>/api/agente-ia/</c> contra respuestas REALES del backend, capturadas por <c>backend/agente_ia/tests/test_capturar_contrato.py</c> en <c>Fixtures/agente_ia/</c>: lo que dice el
/// nodo cuando todo va bien y cuando la IA no está, está ocupada, tarda o responde basura. No hace falta Qwen para probar esto: el nodo contesta lo mismo con cualquier servicio de IA.
/// </summary>
[Collection("registro-local")]
public sealed class AgenteIaApiTests : IDisposable
{
    private readonly string carpeta;

    public AgenteIaApiTests()
    {
        carpeta = Path.Combine(Path.GetTempPath(), "avacom-core-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(carpeta);
        Environment.SetEnvironmentVariable("AVACOM_LMS_DIR_LOGS", carpeta);
        RegistroLocal.Reiniciar();
        RegistroLocal.VentanaDeRepeticion = TimeSpan.Zero;
        RegistroLocal.Configurar("ops", "1.0.0", () => "d-prueba");
        ClienteJson.Token = null;
    }

    public void Dispose()
    {
        Environment.SetEnvironmentVariable("AVACOM_LMS_DIR_LOGS", null);
        RegistroLocal.Reiniciar();
        RegistroLocal.VentanaDeRepeticion = TimeSpan.FromSeconds(30);
        try { Directory.Delete(carpeta, recursive: true); } catch { }
    }

    private static string Ruta(string nombre) => Path.Combine(AppContext.BaseDirectory, "Fixtures", "agente_ia", nombre);
    private static string Texto(string nombre) => File.ReadAllText(Ruta(nombre + ".json"));

    private static HttpResponseMessage Json(HttpStatusCode estado, string cuerpo) => new(estado) { Content = new StringContent(cuerpo, Encoding.UTF8, "application/json") };

    private sealed class Falso(Func<HttpRequestMessage, string?, CancellationToken, Task<HttpResponseMessage>> responder) : HttpMessageHandler
    {
        public List<(HttpMethod Metodo, string Ruta, string? Cuerpo, string? Corr)> Peticiones { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            var cuerpo = request.Content is null ? null : await request.Content.ReadAsStringAsync(ct);
            request.Headers.TryGetValues("X-Avacom-Correlacion", out var corr);
            Peticiones.Add((request.Method, request.RequestUri!.PathAndQuery, cuerpo, corr?.FirstOrDefault()));
            return await responder(request, cuerpo, ct);
        }
    }

    private static Falso Responde(HttpStatusCode estado, string cuerpo) => new((_, _, _) => Task.FromResult(Json(estado, cuerpo)));
    private static AgenteIaApi Api(Falso falso) => new(new HttpClient(falso), new Uri("http://aula.local:8000/"));

    // ---------------------------------------------------------------------------------------------- preguntar

    [Fact]
    public async Task Preguntar_LeeLaRespuestaRealDelNodo_YMandaPreguntaActorYConversacionEnUtf8()
    {
        var falso = Responde(HttpStatusCode.OK, Texto("preguntar"));
        var r = await Api(falso).PreguntarAsync("prof-1", "¿Cuánto es 1943? Ñandú", "ops-abc");
        Assert.NotNull(r);
        Assert.Equal(("ops-pantalla-1", "Mil novecientos cuarenta y tres. ¡Con gusto!", "qwen3:8b", true), (r.Conversacion, r.Texto, r.Modelo, r.ContextoUsado));
        Assert.True(r.Ms >= 0);
        var (metodo, ruta, cuerpo, corr) = falso.Peticiones.Single();
        Assert.Equal((HttpMethod.Post, "/api/agente-ia/preguntar/"), (metodo, ruta));
        Assert.False(string.IsNullOrEmpty(corr));
        using var doc = JsonDocument.Parse(cuerpo!);
        Assert.Equal(("¿Cuánto es 1943? Ñandú", "prof-1", "ops-abc"), (doc.RootElement.GetProperty("pregunta").GetString(), doc.RootElement.GetProperty("actor").GetString(), doc.RootElement.GetProperty("conversacion").GetString()));
    }

    [Fact]
    public async Task Preguntar_SinConversacion_NoLaManda()
    {
        var falso = Responde(HttpStatusCode.OK, Texto("preguntar"));
        await Api(falso).PreguntarAsync("p", "hola", null);
        Assert.DoesNotContain("conversacion", falso.Peticiones.Single().Cuerpo!);
    }

    [Theory]
    [InlineData("error_servicio_apagado", 503, "ai_unreachable", true)]
    [InlineData("error_tiempo_agotado", 504, "ai_timeout", true)]
    [InlineData("error_ocupado", 429, "busy", true)]
    [InlineData("error_modelo", 502, "llm_error", true)]
    [InlineData("error_modelo_no_instalado", 503, "llm_model_missing", false)]
    [InlineData("error_pregunta_vacia", 400, "question_required", false)]
    public async Task Preguntar_CadaFalloDelNodo_DaNullConSuCodigoYUnTextoParaLaPersona(string fixture, int estado, string codigo, bool reintentable)
    {
        var api = Api(Responde((HttpStatusCode)estado, Texto(fixture)));
        Assert.Null(await api.PreguntarAsync("p", "hola", "c"));
        Assert.Equal((estado, codigo), (api.UltimoError!.Estado, api.UltimoError.Codigo));
        Assert.Equal(reintentable, TextoDelAgente.Reintentable(api.UltimoError));
        var texto = TextoDelAgente.Para(api.UltimoError, api.UltimoMotivo);
        Assert.False(string.IsNullOrWhiteSpace(texto));
        Assert.DoesNotContain("127.0.0.1", texto);
        Assert.DoesNotContain("Ollama", texto);
        Assert.DoesNotContain("Exception", texto);
    }

    [Fact]
    public async Task Preguntar_SinPermiso_DiceQueElRolNoPuede()
    {
        var api = Api(Responde(HttpStatusCode.Forbidden, Texto("error_sin_permiso")));
        Assert.Null(await api.PreguntarAsync("p", "hola", null));
        Assert.Equal("sin_permiso", api.UltimoError!.Codigo);
        Assert.Equal("Tu rol no puede usar el asistente.", TextoDelAgente.Para(api.UltimoError, api.UltimoMotivo));
        Assert.False(TextoDelAgente.Reintentable(api.UltimoError));
    }

    [Fact]
    public async Task Preguntar_ElNodoApagado_EsSinConexion_YSeReintenta()
    {
        var api = Api(new Falso((_, _, _) => throw new HttpRequestException("rechazado")));
        Assert.Null(await api.PreguntarAsync("p", "hola", null));
        Assert.Equal((0, "sin_conexion"), (api.UltimoError!.Estado, api.UltimoError.Codigo));
        Assert.Equal(TextoDelAgente.SinNodo, TextoDelAgente.Para(api.UltimoError, api.UltimoMotivo));
        Assert.True(TextoDelAgente.Reintentable(api.UltimoError));
    }

    [Fact]
    public async Task Preguntar_SiSeAgotaElTiempoDelCliente_DiceQueTardoDemasiado_NoQueNoHayConexion()
    {
        var api = Api(new Falso(async (_, _, ct) => { await Task.Delay(TimeSpan.FromSeconds(30), ct); return Json(HttpStatusCode.OK, Texto("preguntar")); }));
        api.EsperaDePregunta = TimeSpan.FromMilliseconds(150);
        Assert.Null(await api.PreguntarAsync("p", "hola", null));
        Assert.Equal("tiempo_agotado", api.UltimoError!.Codigo);
        Assert.Contains("tardó demasiado", TextoDelAgente.Para(api.UltimoError, api.UltimoMotivo));
        Assert.True(TextoDelAgente.Reintentable(api.UltimoError));
    }

    [Fact]
    public async Task Preguntar_SiLaPersonaCancela_NoEsUnFallo()
    {
        var api = Api(new Falso(async (_, _, ct) => { await Task.Delay(TimeSpan.FromSeconds(30), ct); return Json(HttpStatusCode.OK, Texto("preguntar")); }));
        using var cts = new CancellationTokenSource(TimeSpan.FromMilliseconds(100));
        Assert.Null(await api.PreguntarAsync("p", "hola", null, cts.Token));
        Assert.Equal("cancelado", api.UltimoError!.Codigo);
    }

    [Fact]
    public async Task Preguntar_ConUnTextoVacioODelNodoQueNoEsJson_NoRompe()
    {
        var vacio = Api(Responde(HttpStatusCode.OK, """{"conversacion":"x","texto":"  ","modelo":"m","contexto_usado":true,"ms":1}"""));
        Assert.Null(await vacio.PreguntarAsync("p", "hola", null));
        Assert.Equal("respuesta_vacia", vacio.UltimoError!.Codigo);
        var basura = Api(Responde(HttpStatusCode.OK, "<html>no soy json</html>"));
        Assert.Null(await basura.PreguntarAsync("p", "hola", null));
        Assert.NotNull(basura.UltimoError);
    }

    // ---------------------------------------------------------------------------------------------- estado

    [Fact]
    public async Task Estado_Sano()
    {
        var falso = Responde(HttpStatusCode.OK, Texto("estado"));
        var e = (await Api(falso).EstadoAsync("prof-1"))!;
        Assert.Equal((true, true, true, null, "qwen3:8b"), (e.Disponible, e.VozDisponible, e.ServicioActivo, e.Codigo, e.Modelo));
        Assert.Equal(string.Empty, TextoDelAgente.ParaEstado(e));
        Assert.Equal((HttpMethod.Get, "/api/agente-ia/estado/?actor=prof-1"), (falso.Peticiones[0].Metodo, falso.Peticiones[0].Ruta));
    }

    [Fact]
    public async Task Estado_ServicioApagado_EsUnaRespuestaNoUnError()
    {
        var api = Api(Responde(HttpStatusCode.OK, Texto("estado_servicio_apagado")));
        var e = (await api.EstadoAsync("p"))!;
        Assert.Null(api.UltimoError);
        Assert.Equal((false, false, "ai_unreachable"), (e.Disponible, e.ServicioActivo, e.Codigo));
        Assert.False(string.IsNullOrWhiteSpace(e.Sugerencia));
        Assert.Equal("El asistente no está disponible en este momento.", TextoDelAgente.ParaEstado(e));
    }

    [Fact]
    public async Task Estado_ModeloFaltante()
    {
        var e = (await Api(Responde(HttpStatusCode.OK, Texto("estado_modelo_faltante"))).EstadoAsync("p"))!;
        Assert.Equal((false, true, "llm_model_missing"), (e.Disponible, e.ServicioActivo, e.Codigo));
        Assert.Equal("El asistente aún no está configurado en este equipo.", TextoDelAgente.ParaEstado(e));
    }

    [Fact]
    public void Estado_SinVozPeroConTexto_AvisaSoloDeLaVoz()
    {
        var e = new EstadoDelAgente(true, true, true, false, null, null, "La voz del asistente no está disponible.", null, "qwen3:8b");
        Assert.Equal("La voz del asistente no está disponible.", TextoDelAgente.ParaEstado(e));
        Assert.Equal(TextoDelAgente.SinNodo, TextoDelAgente.ParaEstado(null));
    }

    // ---------------------------------------------------------------------------------------------- hablar

    private static HttpResponseMessage Audio(byte[] wav, string duracion = "200", string trozos = "1")
    {
        var r = new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(wav) };
        r.Content.Headers.ContentType = new("audio/wav");
        r.Headers.Add("X-Audio-Duration-Ms", duracion);
        r.Headers.Add("X-Audio-Chunks", trozos);
        return r;
    }

    [Fact]
    public async Task Hablar_DevuelveElWavRealDelNodo_ConSuDuracionYTrozos()
    {
        var wav = File.ReadAllBytes(Ruta("hablar.wav"));
        var cabeceras = JsonDocument.Parse(File.ReadAllText(Ruta("hablar_cabeceras.json"))).RootElement;
        var falso = new Falso((_, _, _) => Task.FromResult(Audio(wav, cabeceras.GetProperty("X-Audio-Duration-Ms").GetString()!, cabeceras.GetProperty("X-Audio-Chunks").GetString()!)));
        var v = (await Api(falso).HablarAsync("prof-1", "Hola mundo.", 1.0))!;
        Assert.Equal(wav, v.Wav);
        Assert.Equal((200, 1), (v.DuracionMs, v.Trozos));
        var formato = FormatoWav.Leer(v.Wav)!;
        Assert.Equal((1, 22050, 16), (formato.Canales, formato.Frecuencia, formato.Bits));
        Assert.InRange(formato.DuracionMs, 195, 205);
        using var doc = JsonDocument.Parse(falso.Peticiones.Single().Cuerpo!);
        Assert.Equal(("Hola mundo.", 1.0, "prof-1"), (doc.RootElement.GetProperty("texto").GetString(), doc.RootElement.GetProperty("velocidad").GetDouble(), doc.RootElement.GetProperty("actor").GetString()));
        Assert.Equal("/api/agente-ia/hablar/", falso.Peticiones.Single().Ruta);
    }

    [Fact]
    public async Task Hablar_SinCabeceraDeDuracion_LaCalculaDelPropioWav()
    {
        var wav = File.ReadAllBytes(Ruta("hablar.wav"));
        var r = new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(wav) };
        var v = (await Api(new Falso((_, _, _) => Task.FromResult(r))).HablarAsync("p", "Hola.", 1.0))!;
        Assert.InRange(v.DuracionMs, 195, 205);
        Assert.Equal(1, v.Trozos);
    }

    [Theory]
    [InlineData("error_voz_ocupada", 429, "tts_busy", true)]
    [InlineData("error_voz_invalida", 502, "ai_invalid_response", true)]
    [InlineData("error_texto_sin_contenido", 422, "empty_text", false)]
    public async Task Hablar_CadaFalloDelNodo_DaNullConSuCodigo(string fixture, int estado, string codigo, bool reintentable)
    {
        var api = Api(Responde((HttpStatusCode)estado, Texto(fixture)));
        Assert.Null(await api.HablarAsync("p", "Hola.", 1.0));
        Assert.Equal((estado, codigo), (api.UltimoError!.Estado, api.UltimoError.Codigo));
        Assert.Equal(reintentable, TextoDelAgente.Reintentable(api.UltimoError));
    }

    [Fact]
    public async Task Hablar_UnCuerpoQueNoEsAudio_NoLlegaALaPantalla()
    {
        foreach (var basura in new[] { Encoding.UTF8.GetBytes("<html>502 Bad Gateway</html>" + new string(' ', 60)), new byte[10], Array.Empty<byte>() })
        {
            var api = Api(new Falso((_, _, _) => Task.FromResult(Audio(basura))));
            Assert.Null(await api.HablarAsync("p", "Hola.", 1.0));
            Assert.Equal("audio_invalido", api.UltimoError!.Codigo);
            Assert.Contains("llegó dañada", api.UltimoMotivo);
        }
    }

    [Fact]
    public async Task Hablar_SiLaRespuestaSeCortaAMedias_NoLanza()
    {
        var wav = File.ReadAllBytes(Ruta("hablar.wav"));
        var cortada = new HttpResponseMessage(HttpStatusCode.OK) { Content = new StreamContent(new FlujoQueFalla(wav)) };
        var api = Api(new Falso((_, _, _) => Task.FromResult(cortada)));
        Assert.Null(await api.HablarAsync("p", "Hola.", 1.0));
        Assert.Equal("audio_cortado", api.UltimoError!.Codigo);
    }

    [Fact]
    public async Task Hablar_ElTiempoAgotado_DiceQueLaVozTardo()
    {
        var api = Api(new Falso(async (_, _, ct) => { await Task.Delay(TimeSpan.FromSeconds(30), ct); return Audio(File.ReadAllBytes(Ruta("hablar.wav"))); }));
        api.EsperaDeVoz = TimeSpan.FromMilliseconds(150);
        Assert.Null(await api.HablarAsync("p", "Hola.", 1.0));
        Assert.Equal("tiempo_agotado", api.UltimoError!.Codigo);
        Assert.Contains("voz", api.UltimoMotivo);
    }

    private sealed class FlujoQueFalla(byte[] inicio) : Stream
    {
        private int pos;
        public override int Read(byte[] buffer, int offset, int count)
        {
            if (pos >= inicio.Length / 2) throw new IOException("conexión cerrada por el nodo");
            var n = Math.Min(count, inicio.Length / 2 - pos);
            Array.Copy(inicio, pos, buffer, offset, n);
            pos += n;
            return n;
        }
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }

    // ---------------------------------------------------------------------------------------------- el WAV

    [Fact]
    public void FormatoWav_RechazaLoQueNoEsAudioYAceptaLoCortado()
    {
        Assert.Null(FormatoWav.Leer(new byte[0]));
        Assert.Null(FormatoWav.Leer(Encoding.ASCII.GetBytes("RIFF" + new string('\0', 80))));
        Assert.Null(FormatoWav.Leer(Encoding.UTF8.GetBytes("<html>" + new string(' ', 80))));
        var wav = File.ReadAllBytes(Ruta("hablar.wav"));
        var cortado = FormatoWav.Leer(wav.AsSpan(0, wav.Length - 1001))!;
        Assert.Equal(0, cortado.Largo % 2);
        Assert.True(cortado.Largo < wav.Length - 44);
    }
}

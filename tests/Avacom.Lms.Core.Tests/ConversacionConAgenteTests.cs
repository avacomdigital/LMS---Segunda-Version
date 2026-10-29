using System.Text.Json;
using Avacom.Lms.Core.AgenteIa;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// El turno de conversación (pregunta → texto → voz → sonido) con sus estados, y SOBRE TODO que nada de lo que pueda fallar —el nodo, la IA, la voz, el reproductor, un suscriptor, un defecto
/// propio— rompe la aplicación: el turno nunca lanza, deja el motivo, el avatar vuelve al reposo y queda constancia en el log local sin el texto de la pregunta ni el de la respuesta.
/// </summary>
[Collection("registro-local")]
public sealed class ConversacionConAgenteTests : IDisposable
{
    private readonly string carpeta;
    private readonly TimeSpan errorAntes = ConversacionConAgente.DuracionDelError;

    public ConversacionConAgenteTests()
    {
        carpeta = Path.Combine(Path.GetTempPath(), "avacom-core-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(carpeta);
        Environment.SetEnvironmentVariable("AVACOM_LMS_DIR_LOGS", carpeta);
        RegistroLocal.Reiniciar();
        RegistroLocal.VentanaDeRepeticion = TimeSpan.Zero;
        RegistroLocal.Configurar("ops", "1.0.0", () => "d-prueba");
        ConversacionConAgente.DuracionDelError = TimeSpan.FromMilliseconds(120);
    }

    public void Dispose()
    {
        ConversacionConAgente.DuracionDelError = errorAntes;
        Environment.SetEnvironmentVariable("AVACOM_LMS_DIR_LOGS", null);
        RegistroLocal.Reiniciar();
        RegistroLocal.VentanaDeRepeticion = TimeSpan.FromSeconds(30);
        try { Directory.Delete(carpeta, recursive: true); } catch { }
    }

    private const string Pregunta = "¿Cuánto es mil novecientos cuarenta y tres?";
    private const string Respuesta = "Mil novecientos cuarenta y tres, claro que sí.";
    private static readonly byte[] Wav = File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "Fixtures", "agente_ia", "hablar.wav"));

    private static ErrorAula Error(int estado, string codigo, string detalle, bool reintentable) =>
        new(estado, codigo, detalle, null, JsonDocument.Parse($$"""{"reintentable":{{(reintentable ? "true" : "false")}}}""").RootElement.Clone());

    private sealed class ApiFalsa : IAgenteIaApi
    {
        public string? UltimoMotivo { get; set; }
        public ErrorAula? UltimoError { get; set; }
        public Func<string, string?, CancellationToken, Task<RespuestaDelAgente?>> AlPreguntar { get; set; } = (_, c, _) => Task.FromResult<RespuestaDelAgente?>(new(c ?? "", Respuesta, "qwen3:8b", true, 9));
        public Func<string, CancellationToken, Task<VozDelAgente?>> AlHablar { get; set; } = (_, _) => Task.FromResult<VozDelAgente?>(new(Wav, 200, 1));
        public Func<EstadoDelAgente?> AlEstado { get; set; } = () => new(true, true, true, true, null, null, null, null, "qwen3:8b");
        public List<(string Actor, string Pregunta, string? Conversacion)> Preguntas { get; } = [];
        public List<string> Voces { get; } = [];

        public Task<RespuestaDelAgente?> PreguntarAsync(string actor, string pregunta, string? conversacion, CancellationToken ct = default)
        {
            Preguntas.Add((actor, pregunta, conversacion));
            return AlPreguntar(pregunta, conversacion, ct);
        }

        public Task<VozDelAgente?> HablarAsync(string actor, string texto, double velocidad, CancellationToken ct = default)
        {
            Voces.Add(texto);
            return AlHablar(texto, ct);
        }

        public Task<EstadoDelAgente?> EstadoAsync(string actor, CancellationToken ct = default) => Task.FromResult(AlEstado());

        public ApiFalsa Falla(ErrorAula error, string motivo)
        {
            UltimoError = error;
            UltimoMotivo = motivo;
            AlPreguntar = (_, _, _) => Task.FromResult<RespuestaDelAgente?>(null);
            return this;
        }
    }

    private sealed class ReproductorFalso : IReproductorDeAudio
    {
        public List<(int Bytes, int DuracionMs)> Reproducidos { get; } = [];
        public int Detenciones { get; private set; }
        public Func<byte[], CancellationToken, Task> Al { get; set; } = (_, _) => Task.CompletedTask;
        public Task ReproducirAsync(byte[] wav, int duracionMs, CancellationToken ct)
        {
            Reproducidos.Add((wav.Length, duracionMs));
            return Al(wav, ct);
        }
        public void Detener() => Detenciones++;
    }

    private static (ConversacionConAgente C, List<EstadoDelAvatar> Estados, List<string> Textos) Armar(ApiFalsa api, IReproductorDeAudio rep)
    {
        var c = new ConversacionConAgente(api, rep, () => "prof-1");
        var estados = new List<EstadoDelAvatar>();
        var textos = new List<string>();
        c.EstadoCambiado += (e, _) => { lock (estados) estados.Add(e); };
        c.TextoListo += t => { lock (textos) textos.Add(t); };
        return (c, estados, textos);
    }

    private string Log() => File.Exists(RegistroLocal.RutaApp) ? File.ReadAllText(RegistroLocal.RutaApp) : string.Empty;

    private static async Task Hasta(Func<bool> condicion, int ms = 3000)
    {
        for (var t = 0; t < ms && !condicion(); t += 10) await Task.Delay(10);
    }

    // ---------------------------------------------------------------------------------------------- lo que sale bien

    [Fact]
    public async Task UnTurnoCompleto_PasaPorPensandoHablandoYReposo_YMuestraElTextoAntesDeLaVoz()
    {
        var api = new ApiFalsa();
        var rep = new ReproductorFalso();
        var (c, estados, textos) = Armar(api, rep);
        var ordenTexto = new List<string>();
        c.TextoListo += _ => ordenTexto.Add("texto");
        api.AlHablar = (_, _) => { ordenTexto.Add("voz"); return Task.FromResult<VozDelAgente?>(new(Wav, 200, 1)); };

        var r = await c.PreguntarAsync(Pregunta);

        Assert.Equal((true, Respuesta, true, null, null), (r.Respondio, r.Texto, r.Hablo, r.Aviso, r.Codigo));
        Assert.Equal([EstadoDelAvatar.Pensando, EstadoDelAvatar.Hablando, EstadoDelAvatar.Reposo], estados);
        Assert.Equal([Respuesta], textos);
        Assert.Equal(["texto", "voz"], ordenTexto);                                // el texto ya está en pantalla cuando se pide la voz
        Assert.Equal([(Wav.Length, 200)], rep.Reproducidos);
        Assert.Equal(("prof-1", Pregunta, c.IdDePantalla), api.Preguntas.Single());
        Assert.False(c.Ocupada);
        Assert.Equal(EstadoDelAvatar.Reposo, c.Estado);
        Assert.DoesNotContain("novecientos", Log());                               // ni la pregunta ni la respuesta van al log
        Assert.Contains("aiagent.consulta", Log());
    }

    [Fact]
    public async Task LaConversacionSeConservaEntreTurnos_YNuevaConversacionLaCambia()
    {
        var api = new ApiFalsa();
        var (c, _, _) = Armar(api, new ReproductorFalso());
        await c.PreguntarAsync("uno", hablar: false);
        await c.PreguntarAsync("dos", hablar: false);
        c.NuevaConversacion();
        await c.PreguntarAsync("tres", hablar: false);
        Assert.Equal(api.Preguntas[0].Conversacion, api.Preguntas[1].Conversacion);
        Assert.NotEqual(api.Preguntas[1].Conversacion, api.Preguntas[2].Conversacion);
        Assert.Matches("^[A-Za-z0-9_.:-]{1,40}$", api.Preguntas[0].Conversacion!);
        Assert.Empty(api.Voces);                                                    // hablar:false no pide voz
    }

    [Fact]
    public async Task EscucharDeNuevo_PideSoloLaVoz_SinVolverAPreguntarle_AlModelo()
    {
        var api = new ApiFalsa();
        var rep = new ReproductorFalso();
        var (c, estados, _) = Armar(api, rep);
        var r = await c.EscucharAsync(Respuesta);
        Assert.True(r.Hablo);
        Assert.Empty(api.Preguntas);
        Assert.Equal([Respuesta], api.Voces);
        Assert.Equal([EstadoDelAvatar.Pensando, EstadoDelAvatar.Hablando, EstadoDelAvatar.Reposo], estados);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   \n ")]
    public async Task PreguntaVacia_NoLlamaAlNodo(string? texto)
    {
        var api = new ApiFalsa();
        var (c, estados, _) = Armar(api, new ReproductorFalso());
        var r = await c.PreguntarAsync(texto);
        Assert.Equal((false, "question_required"), (r.Respondio, r.Codigo));
        Assert.Empty(api.Preguntas);
        Assert.Empty(estados);
    }

    [Fact]
    public async Task PreguntaDemasiadoLarga_NoLlamaAlNodo_YElLimiteExactoSiPasa()
    {
        var api = new ApiFalsa();
        var (c, _, _) = Armar(api, new ReproductorFalso());
        Assert.Equal("question_too_long", (await c.PreguntarAsync(new string('a', 2001))).Codigo);
        Assert.Empty(api.Preguntas);
        Assert.True((await c.PreguntarAsync(new string('a', 2000), hablar: false)).Respondio);
    }

    // ---------------------------------------------------------------------------------------------- la IA no responde

    [Fact]
    public async Task ElServicioDeIaCaido_DaUnAvisoParaLaPersona_PasaPorErrorYVuelveSoloAlReposo_YQuedaEnElLog()
    {
        var api = new ApiFalsa().Falla(Error(503, "ai_unreachable", "El asistente no está disponible en este momento.", true), "El asistente no está disponible en este momento.");
        var rep = new ReproductorFalso();
        var (c, estados, textos) = Armar(api, rep);
        string? mensajeDeError = null;
        c.EstadoCambiado += (e, m) => { if (e == EstadoDelAvatar.Error) mensajeDeError = m; };

        var r = await c.PreguntarAsync(Pregunta);

        Assert.Equal((false, null, false, "El asistente no está disponible en este momento.", "ai_unreachable", true), (r.Respondio, r.Texto, r.Hablo, r.Aviso, r.Codigo, r.Reintentable));
        Assert.Equal("El asistente no está disponible en este momento.", mensajeDeError);
        Assert.Empty(textos);
        Assert.Empty(rep.Reproducidos);
        Assert.Empty(api.Voces);
        Assert.Equal(EstadoDelAvatar.Error, c.Estado);
        Assert.False(c.Ocupada);                                                   // se puede volver a preguntar ya mismo
        await Hasta(() => c.Estado == EstadoDelAvatar.Reposo);
        Assert.Equal([EstadoDelAvatar.Pensando, EstadoDelAvatar.Error, EstadoDelAvatar.Reposo], estados);
        var log = Log();
        Assert.Contains("aiagent.consulta_fallida", log);
        Assert.Contains("ai_unreachable", log);
        Assert.DoesNotContain("novecientos", log);
        Assert.Contains("WARNING", File.ReadAllText(RegistroLocal.RutaErrores));        // sube al nodo
    }

    [Fact]
    public async Task LaSugerenciaDelNodo_SeDiceJuntoAlMotivo()
    {
        var api = new ApiFalsa().Falla(new ErrorAula(503, "ai_unreachable", "El asistente no está disponible en este momento.", "Avisa a quien administra el equipo.", JsonDocument.Parse("""{"reintentable":true}""").RootElement.Clone()),
                                      "El asistente no está disponible en este momento.");
        var (c, _, _) = Armar(api, new ReproductorFalso());
        var r = await c.PreguntarAsync(Pregunta);
        Assert.Equal("El asistente no está disponible en este momento. Avisa a quien administra el equipo.", r.Aviso);
    }

    [Theory]
    [InlineData(503, "llm_model_missing", false)]
    [InlineData(504, "ai_timeout", true)]
    [InlineData(429, "busy", true)]
    [InlineData(502, "ai_invalid_response", true)]
    public async Task CadaCodigoDelNodo_LlegaALaPersonaConSuReintento(int estado, string codigo, bool reintentable)
    {
        var api = new ApiFalsa().Falla(Error(estado, codigo, "Texto del nodo para la persona.", reintentable), "Texto del nodo para la persona.");
        var (c, _, _) = Armar(api, new ReproductorFalso());
        var r = await c.PreguntarAsync(Pregunta);
        Assert.Equal((codigo, reintentable, "Texto del nodo para la persona."), (r.Codigo, r.Reintentable, r.Aviso));
    }

    [Fact]
    public async Task ElNodoApagado_EsSinConexion_YSeReintenta()
    {
        var api = new ApiFalsa().Falla(new ErrorAula(0, "sin_conexion", "No hay conexión con el aula.", null, null), "No hay conexión con el aula.");
        var (c, _, _) = Armar(api, new ReproductorFalso());
        var r = await c.PreguntarAsync(Pregunta);
        Assert.Equal(("sin_conexion", true, TextoDelAgente.SinNodo), (r.Codigo, r.Reintentable, r.Aviso));
    }

    [Fact]
    public async Task SiLaVozFalla_LaRespuestaEscritaSeConserva_YNoHayErrorDeAvatar()
    {
        var api = new ApiFalsa();
        api.AlHablar = (_, _) =>
        {
            api.UltimoError = Error(503, "tts_unavailable", "La voz del asistente no está disponible. Puedes leer la respuesta.", true);
            api.UltimoMotivo = "La voz del asistente no está disponible. Puedes leer la respuesta.";
            return Task.FromResult<VozDelAgente?>(null);
        };
        var (c, estados, textos) = Armar(api, new ReproductorFalso());
        var r = await c.PreguntarAsync(Pregunta);
        Assert.Equal((true, Respuesta, false, "tts_unavailable", true), (r.Respondio, r.Texto, r.Hablo, r.Codigo, r.Reintentable));
        Assert.Contains("Puedes leer la respuesta", r.Aviso);
        Assert.Equal([Respuesta], textos);
        Assert.DoesNotContain(EstadoDelAvatar.Error, estados);
        Assert.Equal(EstadoDelAvatar.Reposo, c.Estado);
        Assert.Contains("aiagent.voz_fallida", Log());
    }

    [Fact]
    public async Task SiElReproductorFalla_SeAvisa_SeRegistraComoErrorDelEquipo_YLaAppSigue()
    {
        var rep = new ReproductorFalso { Al = (_, _) => throw new InvalidOperationException("sin tarjeta de sonido") };
        var (c, estados, textos) = Armar(new ApiFalsa(), rep);
        var r = await c.PreguntarAsync(Pregunta);
        Assert.Equal((true, Respuesta, false, "reproduccion_fallida", true), (r.Respondio, r.Texto, r.Hablo, r.Codigo, r.Reintentable));
        Assert.Contains("No se pudo reproducir la voz", r.Aviso);
        Assert.Equal([Respuesta], textos);
        Assert.Equal(EstadoDelAvatar.Reposo, c.Estado);
        Assert.Equal([EstadoDelAvatar.Pensando, EstadoDelAvatar.Hablando, EstadoDelAvatar.Reposo], estados);
        var log = Log();
        Assert.Contains("aiagent.reproduccion_fallida", log);
        Assert.Contains("\"nivel\":\"ERROR\"", File.ReadAllText(RegistroLocal.RutaErrores));
        Assert.DoesNotContain("novecientos", log);
    }

    [Fact]
    public async Task SinReproductor_ElAsistenteResponde_PorEscrito()
    {
        var (c, _, _) = Armar(new ApiFalsa(), new SinReproductor());
        var r = await c.PreguntarAsync(Pregunta);
        Assert.Equal((true, Respuesta, false), (r.Respondio, r.Texto, r.Hablo));
        Assert.Equal("reproduccion_fallida", r.Codigo);
    }

    [Fact]
    public async Task UnDefectoPropio_NoEscapaComoExcepcion()
    {
        var api = new ApiFalsa { AlPreguntar = (_, _, _) => throw new InvalidCastException("bug") };
        var (c, estados, _) = Armar(api, new ReproductorFalso());
        var r = await c.PreguntarAsync(Pregunta);
        Assert.Equal((false, "ai_cliente", TextoDelAgente.Generico), (r.Respondio, r.Codigo, r.Aviso));
        Assert.True(r.Reintentable);
        Assert.Contains(EstadoDelAvatar.Error, estados);
        Assert.Contains("aiagent.defecto", Log());
        Assert.False(c.Ocupada);
        Assert.True((await new ConversacionConAgente(new ApiFalsa(), new ReproductorFalso(), () => "p").PreguntarAsync(Pregunta, hablar: false)).Respondio);
    }

    [Fact]
    public async Task UnSuscriptorQueLanza_NoEstropeaElTurno()
    {
        var (c, _, _) = Armar(new ApiFalsa(), new ReproductorFalso());
        c.EstadoCambiado += (_, _) => throw new InvalidOperationException("la pantalla ya no existe");
        c.TextoListo += _ => throw new InvalidOperationException("la pantalla ya no existe");
        var r = await c.PreguntarAsync(Pregunta);
        Assert.Equal((true, true), (r.Respondio, r.Hablo));
    }

    // ---------------------------------------------------------------------------------------------- simultaneidad y cancelación

    [Fact]
    public async Task UnaPreguntaMientrasHayOtra_SeRechazaSinPisarLaPrimera()
    {
        var liberar = new TaskCompletionSource();
        var api = new ApiFalsa { AlPreguntar = async (_, _, _) => { await liberar.Task; return new("c", Respuesta, "m", true, 1); } };
        var (c, _, _) = Armar(api, new ReproductorFalso());
        var primera = c.PreguntarAsync("uno", hablar: false);
        await Hasta(() => c.Ocupada);
        var segunda = await c.PreguntarAsync("dos", hablar: false);
        Assert.Equal((false, "ocupado", true), (segunda.Respondio, segunda.Codigo, segunda.Reintentable));
        Assert.Single(api.Preguntas);
        liberar.SetResult();
        Assert.True((await primera).Respondio);
    }

    [Fact]
    public async Task Detener_CancelaLaEsperaDelModelo_CortaElSonido_YDejaElAvatarEnReposo()
    {
        var api = new ApiFalsa { AlPreguntar = async (_, _, ct) => { await Task.Delay(TimeSpan.FromSeconds(30), ct); return null; } };
        var rep = new ReproductorFalso();
        var (c, estados, _) = Armar(api, rep);
        var turno = c.PreguntarAsync(Pregunta);
        await Hasta(() => c.Ocupada);
        c.Detener();
        var r = await turno.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.True(r.Cancelado);
        Assert.Null(r.Aviso);
        Assert.Equal(1, rep.Detenciones);
        Assert.Equal(EstadoDelAvatar.Reposo, c.Estado);
        Assert.DoesNotContain(EstadoDelAvatar.Error, estados);
        Assert.False(c.Ocupada);
    }

    [Fact]
    public async Task Detener_MientrasSuena_CancelaLaReproduccion_YLaRespuestaEscritaSeConserva()
    {
        var rep = new ReproductorFalso { Al = async (_, ct) => await Task.Delay(TimeSpan.FromSeconds(30), ct) };
        var (c, _, textos) = Armar(new ApiFalsa(), rep);
        var turno = c.PreguntarAsync(Pregunta);
        await Hasta(() => c.Estado == EstadoDelAvatar.Hablando);
        c.Detener();
        var r = await turno.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.Equal((true, Respuesta, true), (r.Respondio, r.Texto, r.Cancelado));
        Assert.Equal([Respuesta], textos);
        Assert.Equal(EstadoDelAvatar.Reposo, c.Estado);
    }

    // ---------------------------------------------------------------------------------------------- estado del servicio

    [Fact]
    public async Task ConsultarEstado_NoDisponible_QuedaEnElLog_YNoLanza()
    {
        var api = new ApiFalsa { AlEstado = () => new(true, false, false, false, "ai_unreachable", "El asistente no está disponible en este momento.", null, null, null) };
        var (c, _, _) = Armar(api, new ReproductorFalso());
        var e = await c.ConsultarEstadoAsync();
        Assert.False(e!.Disponible);
        Assert.Contains("aiagent.no_disponible", Log());
        Assert.Contains("ai_unreachable", Log());
    }

    [Fact]
    public async Task ConsultarEstado_ElNodoNoContesta_DaNull_YQuedaEnElLog()
    {
        var api = new ApiFalsa { AlEstado = () => null, UltimoError = new ErrorAula(0, "sin_conexion", "No hay conexión con el aula.", null, null) };
        var (c, _, _) = Armar(api, new ReproductorFalso());
        Assert.Null(await c.ConsultarEstadoAsync());
        Assert.Contains("aiagent.estado_sin_respuesta", Log());
    }

    [Fact]
    public async Task ConsultarEstado_UnaExcepcionInesperada_NoEscapa()
    {
        var api = new ApiFalsa { AlEstado = () => throw new InvalidOperationException("bug") };
        var (c, _, _) = Armar(api, new ReproductorFalso());
        Assert.Null(await c.ConsultarEstadoAsync());
    }
}

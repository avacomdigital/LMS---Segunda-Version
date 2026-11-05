using System.Net;
using System.Security.Cryptography;
using System.Text.Json;
using Avacom.Lms.Core.IdentidadDeDispositivo;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// Identidad de dispositivo (MOD-018, Fase 5): el cliente de <c>/api/licencia/identidad/</c> contra las respuestas REALES capturadas del backend
/// (<c>test_capturar_contrato_identidad.py</c>), lo que se firma (el MISMO vector que prueba el nodo), el cuerpo, las palabras de aula y la clave en CNG de Windows.
/// </summary>
[Collection("estado global")]
public sealed class IdentidadDeDispositivoTests : IDisposable
{
    public IdentidadDeDispositivoTests() => ClienteJson.Token = null;

    public void Dispose() => ClienteJson.Token = null;

    private static string Fixture(string nombre) => File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "identidad", nombre + ".json"));

    private sealed record Captura(HttpMethod Metodo, string Url, string? Cuerpo);

    private static (IdentidadApi Api, List<Captura> Capturas) Api(Func<Captura, HttpResponseMessage> responder)
    {
        var capturas = new List<Captura>();
        var http = new HttpClient(new ManejadorFalso(async (req, _) =>
        {
            var captura = new Captura(req.Method, req.RequestUri!.PathAndQuery, req.Content is null ? null : await req.Content.ReadAsStringAsync());
            capturas.Add(captura);
            return responder(captura);
        }));
        return (new IdentidadApi(http, new Uri("http://192.168.0.55:8000/")), capturas);
    }

    private sealed class ProveedorFalso(PruebaDeClave? prueba) : IProveedorDeIdentidad
    {
        public string Nombre => "software";
        public List<(string Hw, byte[] Reto)> Pedidos { get; } = [];
        public Task<PruebaDeClave?> ProbarAsync(string identificadorHw, byte[] reto, CancellationToken ct = default)
        {
            Pedidos.Add((identificadorHw, reto));
            return Task.FromResult(prueba);
        }
    }

    // ---------------------------------------------------------------------------------------------------- lo que se firma

    [Fact]
    public void ElMensajeDelRetoEsElMismoVectorQuePruebaElNodo()
    {
        var reto = Enumerable.Range(0, 32).Select(i => (byte)i).ToArray();
        var mensaje = ReglasDeIdentidad.MensajeDelReto(reto, "student-tableta-aabbccdd");
        Assert.Equal("415641434f4d2d494431000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f73747564656e742d7461626c6574612d6161626263636464",
            Convert.ToHexStringLower(mensaje));
    }

    [Fact]
    public void ElCuerpoLlevaTodoEnBase64_YLaCadenaSoloSiExiste()
    {
        var reto = new byte[32];
        var sinCadena = ReglasDeIdentidad.Cuerpo(reto, new PruebaDeClave([1, 2], [3, 4], [], "tpm"));
        Assert.Equal(["clave_publica", "firma", "nonce", "proveedor"], sinCadena.Keys.Order(StringComparer.Ordinal).ToArray());
        Assert.Equal("AQI=", sinCadena["clave_publica"]);
        var conCadena = ReglasDeIdentidad.Cuerpo(reto, new PruebaDeClave([1], [2], [[9, 9], [8]], ""));
        Assert.Equal(["CQk=", "CA=="], (string[])conCadena["cadena"]);
        Assert.False(conCadena.ContainsKey("proveedor"));
    }

    [Theory]
    [InlineData("hardware", "Verificada por hardware", 2)]
    [InlineData("software", "Con clave propia", 1)]
    [InlineData("declarada", "Declarada", 0)]
    [InlineData("", "Declarada", 0)]
    [InlineData(null, "Declarada", 0)]
    [InlineData("rara", "Declarada", 0)]
    public void LaGarantiaSeDiceEnPalabrasDeAula(string? garantia, string etiqueta, int nivel)
    {
        Assert.Equal(etiqueta, ReglasDeIdentidad.Etiqueta(garantia));
        Assert.Equal(nivel, ReglasDeIdentidad.Nivel(garantia));
        Assert.False(string.IsNullOrWhiteSpace(ReglasDeIdentidad.Explicacion(garantia)));
    }

    // ---------------------------------------------------------------------------------------------------- contrato real

    [Fact]
    public async Task ElReto_EsUnPostSinCuerpo_YSeLeeComoElRealDelNodo()
    {
        var (api, capturas) = Api(_ => Ayudas.Respuesta(HttpStatusCode.Created, Fixture("reto")));
        var reto = await api.RetoAsync();
        Assert.NotNull(reto);
        Assert.Equal((HttpMethod.Post, "/api/licencia/identidad/reto/"), (capturas[0].Metodo, capturas[0].Url));
        Assert.Equal(32, reto.Bytes()!.Length);
        Assert.Equal("ecdsa-p256-sha256", reto.Algoritmo);
        Assert.Equal("AVACOM-ID1", reto.Contexto);
        Assert.True(reto.VenceEn > 0);
    }

    [Theory]
    [InlineData("enrolar_software", "software", "sin_cadena")]
    [InlineData("enrolar_hardware", "hardware", "ok")]
    [InlineData("enrolar_confirmada", "software", "confirmada")]
    public async Task ElEnrolamiento_SeLeeComoElRealDelNodo(string fixture, string garantia, string motivo)
    {
        var (api, capturas) = Api(_ => Ayudas.Respuesta(HttpStatusCode.OK, Fixture(fixture)));
        var r = await api.EnrolarAsync("student-tableta-aabbccdd", ReglasDeIdentidad.Cuerpo(new byte[32], new PruebaDeClave([1], [2], [], "")));
        Assert.NotNull(r);
        Assert.Equal((garantia, motivo), (r.Garantia, r.Motivo));
        Assert.False(string.IsNullOrEmpty(r.ClaveHuella));
        Assert.False(string.IsNullOrEmpty(r.DispositivoId));
        var cuerpo = JsonDocument.Parse(capturas[0].Cuerpo!).RootElement;
        Assert.Equal("student-tableta-aabbccdd", cuerpo.GetProperty("identificador_hw").GetString());
        Assert.True(cuerpo.GetProperty("identidad").TryGetProperty("nonce", out _));
    }

    [Theory]
    [InlineData("error_clave_distinta", HttpStatusCode.Conflict, "clave_distinta")]
    [InlineData("error_reto_invalido", HttpStatusCode.BadRequest, "reto_invalido")]
    [InlineData("error_identidad_invalida", HttpStatusCode.BadRequest, "identidad_invalida")]
    [InlineData("error_equipo_no_registrado", HttpStatusCode.NotFound, "no_encontrado")]
    public async Task UnError_NoEsUnaExcepcion_YDejaSuCodigo(string fixture, HttpStatusCode estado, string codigo)
    {
        var (api, _) = Api(_ => Ayudas.Respuesta(estado, Fixture(fixture)));
        Assert.Null(await api.EnrolarAsync("hw", new Dictionary<string, object>()));
        Assert.Equal(codigo, api.UltimoError?.Codigo);
    }

    [Fact]
    public void ElDispositivoDelInventarioTraeSuGarantia_YSinElla_EsDeclarada()
    {
        var real = JsonSerializer.Deserialize<DispositivoAula>(Fixture("dispositivo_con_garantia"), Ayudas.Web)!;
        Assert.Equal("software", real.Garantia);
        Assert.Equal("Con clave propia", real.GarantiaLegible);
        Assert.False(string.IsNullOrEmpty(real.ClaveHuella));
        var viejo = JsonSerializer.Deserialize<DispositivoAula>("""{"id":"d","identificador_hw":"h","activo":true,"bloqueado":false,"en_linea":true,"registrado_en":1,"ultimo_latido_en":1,"sesion_abierta":null}""", Ayudas.Web)!;
        Assert.Null(viejo.Garantia);
        Assert.Equal("Declarada", viejo.GarantiaLegible);
    }

    [Fact]
    public async Task ElListadoRealNoTrae_LaLlavePublica()
    {
        var real = Fixture("dispositivo_con_garantia");
        Assert.DoesNotContain("clave_publica", real);
        await Task.CompletedTask;
    }

    // ---------------------------------------------------------------------------------------------------- IdentidadDeEquipo

    [Fact]
    public async Task Confirmar_PideUnReto_LoFirma_YLoEnrola()
    {
        var anotaciones = new List<string>();
        var (api, capturas) = Api(c => c.Url.EndsWith("reto/") ? Ayudas.Respuesta(HttpStatusCode.Created, Fixture("reto")) : Ayudas.Respuesta(HttpStatusCode.OK, Fixture("enrolar_software")));
        var proveedor = new ProveedorFalso(new PruebaDeClave([1], [2], [], "software"));
        var identidad = new IdentidadDeEquipo(api, proveedor, (e, d) => anotaciones.Add($"{e}:{d}"));
        var r = await identidad.ConfirmarAsync("student-tableta-aabbccdd");
        Assert.Equal("software", r!.Garantia);
        Assert.Equal(["/api/licencia/identidad/reto/", "/api/licencia/identidad/enrolar/"], capturas.Select(c => c.Url).ToArray());
        Assert.Equal("student-tableta-aabbccdd", proveedor.Pedidos.Single().Hw);
        Assert.Equal(32, proveedor.Pedidos.Single().Reto.Length);
        Assert.Contains("identidad.confirmada:software", anotaciones);
    }

    [Fact]
    public async Task SinProveedor_SinRed_OSinClave_NuncaLanza_YDevuelveNull()
    {
        var (api, _) = Api(_ => Ayudas.Respuesta(HttpStatusCode.Created, Fixture("reto")));
        Assert.Null(await new IdentidadDeEquipo(api, null).ConfirmarAsync("hw"));
        Assert.Null(await new IdentidadDeEquipo(api, null).ParaRegistroAsync("hw"));
        Assert.Null(await new IdentidadDeEquipo(api, new ProveedorFalso(null)).ConfirmarAsync("hw"));
        var http = new HttpClient(new ManejadorFalso((_, _) => throw new HttpRequestException("apagado")));
        var sinRed = new IdentidadDeEquipo(new IdentidadApi(http, new Uri("http://192.168.0.55:8000/")), new ProveedorFalso(new PruebaDeClave([1], [2], [], "x")));
        Assert.Null(await sinRed.ConfirmarAsync("hw"));
        Assert.Null(await sinRed.ParaRegistroAsync("hw"));
    }

    [Fact]
    public async Task UnProveedorQueExplota_NoTumbaLaApp()
    {
        var (api, _) = Api(_ => Ayudas.Respuesta(HttpStatusCode.Created, Fixture("reto")));
        var identidad = new IdentidadDeEquipo(api, new Explota());
        Assert.Null(await identidad.ConfirmarAsync("hw"));
        Assert.Null(await identidad.ParaRegistroAsync("hw"));
    }

    private sealed class Explota : IProveedorDeIdentidad
    {
        public string Nombre => "x";
        public Task<PruebaDeClave?> ProbarAsync(string identificadorHw, byte[] reto, CancellationToken ct = default) => throw new InvalidOperationException("boom");
    }

    [Fact]
    public async Task ParaRegistro_DevuelveElCuerpoQueViajaDentroDelLatido()
    {
        var (api, _) = Api(_ => Ayudas.Respuesta(HttpStatusCode.Created, Fixture("reto")));
        var cuerpo = await new IdentidadDeEquipo(api, new ProveedorFalso(new PruebaDeClave([1], [2], [[7]], "strongbox"))).ParaRegistroAsync("hw");
        Assert.NotNull(cuerpo);
        Assert.Equal(["cadena", "clave_publica", "firma", "nonce", "proveedor"], cuerpo.Keys.Order(StringComparer.Ordinal).ToArray());
    }

    // ---------------------------------------------------------------------------------------------------- CNG (sólo Windows)

    [Fact]
    public async Task LaClaveEnCng_FirmaElRetoYSeVerificaConSuPublica_SinSalirNuncaLaPrivada()
    {
        if (!OperatingSystem.IsWindows()) return;
        var nombre = "AVACOM-Prueba-" + Guid.NewGuid().ToString("N")[..8];
        var proveedor = new ProveedorCng(nombre, probarTpm: false);
        try
        {
            var reto = RandomNumberGenerator.GetBytes(32);
            var prueba = await proveedor.ProbarAsync("ops-pc-1", reto);
            Assert.NotNull(prueba);
            Assert.Equal("software", prueba.Proveedor);
            Assert.Equal(64, prueba.Firma.Length);                                  // P1363: lo que CNG entrega y el nodo acepta
            using var publica = ECDsa.Create();
            publica.ImportSubjectPublicKeyInfo(prueba.ClavePublica, out _);
            Assert.True(publica.VerifyData(ReglasDeIdentidad.MensajeDelReto(reto, "ops-pc-1"), prueba.Firma, HashAlgorithmName.SHA256));
            Assert.False(publica.VerifyData(ReglasDeIdentidad.MensajeDelReto(reto, "ops-pc-2"), prueba.Firma, HashAlgorithmName.SHA256));
            // la misma clave la segunda vez (no se crea otra)
            var otra = await proveedor.ProbarAsync("ops-pc-1", RandomNumberGenerator.GetBytes(32));
            Assert.Equal(prueba.ClavePublica, otra!.ClavePublica);
            // y la privada no se exporta
            using var clave = CngKey.Open(nombre, CngProvider.MicrosoftSoftwareKeyStorageProvider);
            Assert.Equal(CngExportPolicies.None, clave.ExportPolicy);
            Assert.ThrowsAny<CryptographicException>(() => clave.Export(CngKeyBlobFormat.EccPrivateBlob));
        }
        finally { proveedor.Borrar(); }
    }

    [Fact]
    public async Task ElProveedorCng_ConTpm_CaeASoftwareSiNoHayTpm_YNuncaLanza()
    {
        if (!OperatingSystem.IsWindows()) return;
        var nombre = "AVACOM-Prueba-" + Guid.NewGuid().ToString("N")[..8];
        var proveedor = new ProveedorCng(nombre, probarTpm: true);
        try
        {
            var prueba = await proveedor.ProbarAsync("ops-pc-3", new byte[32]);
            Assert.NotNull(prueba);
            Assert.Contains(prueba.Proveedor, new[] { "tpm", "software" });        // en un equipo con TPM, «tpm»; si no, cae a software
        }
        finally { proveedor.Borrar(); }
    }
}

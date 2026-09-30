using System.Net;
using System.Net.Http.Headers;
using System.Net.Sockets;
using System.Text;
using Avacom.Lms.Core.Estudio;

namespace Avacom.Lms.Core.Tests;

/// <summary>El servidor local de medios: GET, HEAD y Range sobre archivos cifrados de varios bloques, la capacidad en la ruta y el manejo de la conexión.</summary>
public sealed class ServidorLocalDeMediosTests : IDisposable
{
    private const int B = ArchivoCifrado.LongitudBloque;
    private const string Alumno = EstudioAyudas.Alumno;
    private const string Asignacion = EstudioAyudas.Asignacion;

    private readonly string carpeta = Ayudas.CarpetaTemporal();
    private readonly AlmacenEstudio almacen;
    private readonly ServidorLocalDeMedios servidor;
    private readonly HttpClient cliente = new();
    private readonly byte[] video = EstudioAyudas.Datos(3 * B + 777, 41);
    private readonly byte[] imagen = EstudioAyudas.Datos(1234, 42);

    public ServidorLocalDeMediosTests()
    {
        almacen = EstudioAyudas.Almacen(carpeta);
        EstudioAyudas.InstalarPaquete(almacen, Alumno, Asignacion,
        [
            new ArchivoDePrueba("video", video, "video/mp4"),
            new ArchivoDePrueba("imagen", imagen, "image/png"),
            new ArchivoDePrueba("vacio", [], "text/plain"),
        ]);
        servidor = new ServidorLocalDeMedios(almacen);
    }

    public void Dispose()
    {
        cliente.Dispose();
        servidor.Dispose();
        try { Directory.Delete(carpeta, true); } catch { }
    }

    private Uri Url(string media = "video") => servidor.UrlDe(Alumno, Asignacion, media);

    private async Task<HttpResponseMessage> Pedir(Uri url, string? rango = null, HttpMethod? metodo = null)
    {
        var peticion = new HttpRequestMessage(metodo ?? HttpMethod.Get, url);
        if (rango is not null) peticion.Headers.TryAddWithoutValidation("Range", rango);
        return await cliente.SendAsync(peticion, HttpCompletionOption.ResponseContentRead);
    }

    // -------------------------------------------------------------------------------- GET

    [Fact]
    public async Task UnGetCompleto_EntregaElArchivoDescifradoSinCorromperlo_ConLasCabecerasDelContrato()
    {
        using var r = await Pedir(Url());

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal(video, await r.Content.ReadAsByteArrayAsync());
        Assert.Equal(video.Length, r.Content.Headers.ContentLength);
        Assert.Equal("video/mp4", r.Content.Headers.ContentType!.MediaType);
        Assert.Equal("bytes", Assert.Single(r.Headers.AcceptRanges));
        Assert.True(r.Headers.CacheControl!.NoStore);
        Assert.Equal("*", r.Headers.GetValues("Access-Control-Allow-Origin").Single());
        Assert.Equal("nosniff", r.Headers.GetValues("X-Content-Type-Options").Single());
        Assert.NotNull(r.Headers.Date);

        using var otra = await Pedir(Url("imagen"));
        Assert.Equal(imagen, await otra.Content.ReadAsByteArrayAsync());
        Assert.Equal("image/png", otra.Content.Headers.ContentType!.MediaType);
    }

    [Fact]
    public async Task UnArchivoVacio_SeSirveConCeroBytes_YNingunRangoLoSatisface()
    {
        using var r = await Pedir(Url("vacio"));
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Empty(await r.Content.ReadAsByteArrayAsync());
        Assert.Equal(0, r.Content.Headers.ContentLength);
        using var rango = await Pedir(Url("vacio"), "bytes=0-");
        Assert.Equal(HttpStatusCode.RequestedRangeNotSatisfiable, rango.StatusCode);
        Assert.Equal("bytes */0", rango.Content.Headers.ContentRange?.ToString() ?? rango.Headers.GetValues("Content-Range").Single());
    }

    // ------------------------------------------------------------------------------- Range

    [Theory]
    [InlineData(0, 0)]
    [InlineData(100, 199)]
    [InlineData(B - 1, B)]                 // cruza el borde del primer bloque
    [InlineData(B - 6, B + 9)]
    [InlineData(2 * B - 3, 2 * B + 2)]
    [InlineData(60_000, 140_000)]          // atraviesa tres bloques
    [InlineData(3 * B, 3 * B + 776)]       // el último bloque, corto
    public async Task UnRangoEnElMedio_DaUn206_ConSuContentRange_YLosBytesExactos(int desde, int hasta)
    {
        using var r = await Pedir(Url(), $"bytes={desde}-{hasta}");

        Assert.Equal(HttpStatusCode.PartialContent, r.StatusCode);
        Assert.Equal(new ContentRangeHeaderValue(desde, hasta, video.Length), r.Content.Headers.ContentRange);
        Assert.Equal(hasta - desde + 1, r.Content.Headers.ContentLength);
        Assert.Equal(video.AsSpan(desde, hasta - desde + 1).ToArray(), await r.Content.ReadAsByteArrayAsync());
    }

    [Fact]
    public async Task UnRangoAbiertoAlFinalYUnSufijo_SirvenElRestoYLosUltimosBytes()
    {
        using var abierto = await Pedir(Url(), $"bytes={B + 10}-");
        Assert.Equal(HttpStatusCode.PartialContent, abierto.StatusCode);
        Assert.Equal(new ContentRangeHeaderValue(B + 10, video.Length - 1, video.Length), abierto.Content.Headers.ContentRange);
        Assert.Equal(video[(B + 10)..], await abierto.Content.ReadAsByteArrayAsync());

        using var sufijo = await Pedir(Url(), "bytes=-50");
        Assert.Equal(HttpStatusCode.PartialContent, sufijo.StatusCode);
        Assert.Equal(new ContentRangeHeaderValue(video.Length - 50, video.Length - 1, video.Length), sufijo.Content.Headers.ContentRange);
        Assert.Equal(video[^50..], await sufijo.Content.ReadAsByteArrayAsync());

        using var sufijoGigante = await Pedir(Url(), "bytes=-999999999");
        Assert.Equal(HttpStatusCode.PartialContent, sufijoGigante.StatusCode);                    // más que el archivo: todo el archivo
        Assert.Equal(video, await sufijoGigante.Content.ReadAsByteArrayAsync());

        using var pasado = await Pedir(Url(), $"bytes={video.Length - 10}-{video.Length + 5000}"); // el final se recorta al del archivo
        Assert.Equal(new ContentRangeHeaderValue(video.Length - 10, video.Length - 1, video.Length), pasado.Content.Headers.ContentRange);
        Assert.Equal(video[^10..], await pasado.Content.ReadAsByteArrayAsync());
    }

    [Theory]
    [InlineData("bytes=<LARGO>-")]
    [InlineData("bytes=<LARGO>-<LARGO>")]
    [InlineData("bytes=99999999-")]
    [InlineData("bytes=-0")]
    public async Task UnRangoQueNoTocaElArchivo_Da416_ConElLargoEnElContentRange(string rango)
    {
        using var r = await Pedir(Url(), rango.Replace("<LARGO>", video.Length.ToString()));
        Assert.Equal(HttpStatusCode.RequestedRangeNotSatisfiable, r.StatusCode);
        Assert.Equal($"bytes */{video.Length}", r.Content.Headers.ContentRange?.ToString() ?? r.Headers.GetValues("Content-Range").Single());
        Assert.Empty(await r.Content.ReadAsByteArrayAsync());
    }

    [Theory]
    [InlineData("bytes=abc")]
    [InlineData("items=1-2")]
    [InlineData("bytes=0-1,5-6")]         // varios rangos: no se soportan, se sirve entero (lo permite el RFC)
    [InlineData("bytes=5-2")]
    [InlineData("bytes=--3")]
    [InlineData("")]
    public async Task UnRangoQueNoSeEntiende_SeIgnora_YSeSirveEntero(string rango)
    {
        using var r = await Pedir(Url(), rango);
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal(video, await r.Content.ReadAsByteArrayAsync());
    }

    [Fact]
    public async Task ElArchivoSePuedeLeerPorTrozosConRange_YQuedaIgualAlOriginal()
    {
        var recomposicion = new MemoryStream();
        for (var desde = 0; desde < video.Length; desde += 10_007)
        {
            using var r = await Pedir(Url(), $"bytes={desde}-{Math.Min(video.Length - 1, desde + 10_006)}");
            Assert.Equal(HttpStatusCode.PartialContent, r.StatusCode);
            recomposicion.Write(await r.Content.ReadAsByteArrayAsync());
        }
        Assert.Equal(video, recomposicion.ToArray());
    }

    [Fact]
    public async Task VariasPeticionesALaVez_SeAtiendenBien()
    {
        var tareas = Enumerable.Range(0, 16).Select(async i =>
        {
            var desde = i * 9_000;
            using var r = await Pedir(Url(), $"bytes={desde}-{desde + 8_999}");
            return (await r.Content.ReadAsByteArrayAsync()).AsSpan().SequenceEqual(video.AsSpan(desde, 9_000));
        }).ToArray();
        Assert.All(await Task.WhenAll(tareas), Assert.True);
    }

    // -------------------------------------------------------------------------- HEAD y otros

    [Fact]
    public async Task UnHead_DaLasMismasCabecerasQueUnGet_SinCuerpo()
    {
        using var r = await Pedir(Url(), metodo: HttpMethod.Head);
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal(video.Length, r.Content.Headers.ContentLength);
        Assert.Equal("video/mp4", r.Content.Headers.ContentType!.MediaType);
        Assert.Equal("bytes", Assert.Single(r.Headers.AcceptRanges));
        Assert.Empty(await r.Content.ReadAsByteArrayAsync());

        using var conRango = await Pedir(Url(), "bytes=10-19", HttpMethod.Head);
        Assert.Equal(HttpStatusCode.PartialContent, conRango.StatusCode);
        Assert.Equal(10, conRango.Content.Headers.ContentLength);
        Assert.Equal(new ContentRangeHeaderValue(10, 19, video.Length), conRango.Content.Headers.ContentRange);
        Assert.Empty(await conRango.Content.ReadAsByteArrayAsync());
    }

    [Fact]
    public async Task OtrosMetodos_Dan405_YLaConsultaPreviaDeCorsSeResponde()
    {
        using var post = await Pedir(Url(), metodo: HttpMethod.Post);
        Assert.Equal(HttpStatusCode.MethodNotAllowed, post.StatusCode);
        Assert.Contains("GET", post.Content.Headers.Allow);
        using var borrar = await Pedir(Url(), metodo: HttpMethod.Delete);
        Assert.Equal(HttpStatusCode.MethodNotAllowed, borrar.StatusCode);

        using var previa = await Pedir(Url(), metodo: HttpMethod.Options);
        Assert.Equal(HttpStatusCode.NoContent, previa.StatusCode);
        Assert.Equal("*", previa.Headers.GetValues("Access-Control-Allow-Origin").Single());
        Assert.Contains("Range", previa.Headers.GetValues("Access-Control-Allow-Headers").Single());
        Assert.Contains("GET", previa.Headers.GetValues("Access-Control-Allow-Methods").Single());
    }

    // ---------------------------------------------------------------- la capacidad en la ruta

    [Fact]
    public async Task UnaRutaSinLaCapacidadDelArranque_EsUn404_ComoCualquierOtraRuta()
    {
        var baseUrl = servidor.Iniciar();
        var capacidad = baseUrl.AbsolutePath.Trim('/');
        var raiz = $"{baseUrl.Scheme}://{baseUrl.Authority}";
        var rutas = new[]
        {
            $"/otra-capacidad/{Alumno}/{Asignacion}/video",                        // capacidad equivocada
            $"/{Alumno}/{Asignacion}/video",                                       // sin capacidad
            $"/{capacidad}/{Alumno}/{Asignacion}",                                 // le falta un tramo
            $"/{capacidad}/{Alumno}/{Asignacion}/video/extra",                     // le sobra uno
            $"/{capacidad}/{Alumno}/{Asignacion}/video/",                          // barra final
            $"/{capacidad}/{Alumno}/{Asignacion}/no-existe",                       // medio inexistente
            $"/{capacidad}/beto/{Asignacion}/video",                               // alumno sin paquete
            $"/{capacidad}/{Alumno}/otra-asignacion/video",
            $"/{capacidad}//{Asignacion}/video",                                   // segmento vacío
            "/",
            "/favicon.ico",
        };
        foreach (var ruta in rutas)
        {
            using var r = await Pedir(new Uri(raiz + ruta));
            Assert.True(r.StatusCode == HttpStatusCode.NotFound, $"{ruta} → {(int)r.StatusCode}");
            Assert.Empty(await r.Content.ReadAsByteArrayAsync());
        }
        using var buena = await Pedir(new Uri($"{raiz}/{capacidad}/{Alumno}/{Asignacion}/video"));      // y la buena, sí
        Assert.Equal(HttpStatusCode.OK, buena.StatusCode);
        using var conConsulta = await Pedir(new Uri($"{raiz}/{capacidad}/{Alumno}/{Asignacion}/video?token=x#y"));   // la consulta no cuenta
        Assert.Equal(HttpStatusCode.OK, conConsulta.StatusCode);
    }

    [Fact]
    public async Task CadaArranqueTieneSuPropiaCapacidad_YSoloEscuchaEnLoopback()
    {
        using var otro = new ServidorLocalDeMedios(almacen);
        var a = servidor.Iniciar();
        var b = otro.Iniciar();
        Assert.Equal("127.0.0.1", a.Host);
        Assert.Equal("127.0.0.1", b.Host);
        Assert.NotEqual(a.AbsolutePath, b.AbsolutePath);
        Assert.Matches("^/[0-9a-f]{32}/$", a.AbsolutePath);
        Assert.Equal(a, servidor.Iniciar());                                          // iniciar dos veces es lo mismo

        using var cruzada = await Pedir(new Uri(a.GetLeftPart(UriPartial.Authority) + b.AbsolutePath + $"{Alumno}/{Asignacion}/video"));   // la capacidad de otro arranque no sirve aquí
        Assert.Equal(HttpStatusCode.NotFound, cruzada.StatusCode);
    }

    [Fact]
    public async Task UrlDe_CodificaCadaSegmento_YElServidorLosDecodifica()
    {
        const string alumno = "ana pérez/1";
        const string asignacion = "asig 1";
        const string medio = "img#1?x";
        EstudioAyudas.InstalarPaquete(almacen, alumno, asignacion, [new ArchivoDePrueba(medio, imagen, "image/png")]);

        var url = servidor.UrlDe(alumno, asignacion, medio);

        Assert.EndsWith("/ana%20p%C3%A9rez%2F1/asig%201/img%231%3Fx", url.AbsoluteUri);
        Assert.StartsWith(servidor.Iniciar().AbsoluteUri, url.AbsoluteUri);
        using var r = await Pedir(url);
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal(imagen, await r.Content.ReadAsByteArrayAsync());
    }

    // ---------------------------------------------------------- lo que no autentica no se entrega

    [Fact]
    public async Task UnBloqueAlteradoEnElDisco_CortaLaConexion_ElGetNoEntregaBasura_YLoDemasSigueSirviendo()
    {
        var medio = Directory.GetFiles(Path.Combine(carpeta, "almacen"), "m-*.avc", SearchOption.AllDirectories)
            .Single(f => new FileInfo(f).Length == ArchivoCifrado.LongitudDelArchivo(video.Length));
        var bytes = File.ReadAllBytes(medio);
        bytes[36 + 2 * (B + 16) + 500] ^= 0x01;                                       // un bit del tercer bloque
        File.WriteAllBytes(medio, bytes);

        var fallo = await Record.ExceptionAsync(async () =>
        {
            using var r = await cliente.GetAsync(Url(), HttpCompletionOption.ResponseHeadersRead);
            await r.Content.ReadAsByteArrayAsync();                                   // la respuesta se corta antes de tiempo: el cliente lo nota
        });
        Assert.True(fallo is HttpRequestException or IOException, $"se esperaba una respuesta cortada y fue: {fallo?.GetType().Name ?? "ninguna excepción"}");
        using var primerBloque = await Pedir(Url(), "bytes=0-99");                     // el resto del archivo sigue íntegro
        Assert.Equal(video[..100], await primerBloque.Content.ReadAsByteArrayAsync());
        using var ultimo = await Pedir(Url(), $"bytes={3 * B}-");
        Assert.Equal(video[(3 * B)..], await ultimo.Content.ReadAsByteArrayAsync());
    }

    [Fact]
    public async Task UnMedioRetiradoMientrasTanto_EsUn404()
    {
        using var antes = await Pedir(Url("imagen"));
        Assert.Equal(HttpStatusCode.OK, antes.StatusCode);
        almacen.EliminarPaquete(Alumno, Asignacion);
        using var despues = await Pedir(Url("imagen"));
        Assert.Equal(HttpStatusCode.NotFound, despues.StatusCode);
    }

    // ----------------------------------------------------------------------- la conexión

    private sealed record RespuestaCruda(string Linea, Dictionary<string, string> Cabeceras, byte[] Cuerpo);

    private static async Task<RespuestaCruda> LeerRespuesta(NetworkStream red, bool sinCuerpo = false)
    {
        var cabecera = new List<byte>();
        var uno = new byte[1];
        while (true)
        {
            if (await red.ReadAsync(uno) == 0) throw new EndOfStreamException("La conexión se cerró antes de terminar la cabecera.");
            cabecera.Add(uno[0]);
            var n = cabecera.Count;
            if (n >= 4 && cabecera[n - 4] == '\r' && cabecera[n - 3] == '\n' && cabecera[n - 2] == '\r' && cabecera[n - 1] == '\n') break;
        }
        var lineas = Encoding.Latin1.GetString(cabecera.ToArray()).Split("\r\n", StringSplitOptions.RemoveEmptyEntries);
        var cabeceras = lineas.Skip(1).Select(l => l.Split(':', 2)).ToDictionary(p => p[0].Trim(), p => p[1].Trim(), StringComparer.OrdinalIgnoreCase);
        var largo = sinCuerpo || !cabeceras.TryGetValue("Content-Length", out var l) ? 0 : int.Parse(l);
        var cuerpo = new byte[largo];
        var leido = 0;
        while (leido < largo)
        {
            var n = await red.ReadAsync(cuerpo.AsMemory(leido));
            if (n == 0) throw new EndOfStreamException("La conexión se cerró a mitad del cuerpo.");
            leido += n;
        }
        return new RespuestaCruda(lineas[0], cabeceras, cuerpo);
    }

    private static async Task Enviar(NetworkStream red, string texto) => await red.WriteAsync(Encoding.Latin1.GetBytes(texto));

    /// <summary>¿El servidor cerró su lado? Leer devuelve 0 (cierre limpio) o falla (la conexión ya no existe): en ambos casos ya no habla.</summary>
    private static async Task<bool> Cerrada(NetworkStream red)
    {
        try { return await red.ReadAsync(new byte[1]).AsTask().WaitAsync(TimeSpan.FromSeconds(5)) == 0; }
        catch (IOException) { return true; }
    }

    private async Task<(TcpClient Cliente, NetworkStream Red, string Ruta)> Conectar()
    {
        var url = Url("imagen");
        var tcp = new TcpClient();
        await tcp.ConnectAsync(IPAddress.Loopback, url.Port);
        return (tcp, tcp.GetStream(), url.PathAndQuery);
    }

    [Fact]
    public async Task LaConexionSeMantieneAbierta_ParaVariasPeticiones_HastaQueElClientePidaCerrar()
    {
        var (tcp, red, ruta) = await Conectar();
        using var _ = tcp;

        await Enviar(red, $"GET {ruta} HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n");
        var primera = await LeerRespuesta(red);
        Assert.Equal("HTTP/1.1 200 OK", primera.Linea);
        Assert.Equal("keep-alive", primera.Cabeceras["Connection"]);
        Assert.Equal(imagen, primera.Cuerpo);

        await Enviar(red, $"GET {ruta} HTTP/1.1\r\nHost: 127.0.0.1\r\nRange: bytes=10-19\r\n\r\n");        // la misma conexión, otra petición
        var segunda = await LeerRespuesta(red);
        Assert.Equal("HTTP/1.1 206 Partial Content", segunda.Linea);
        Assert.Equal(imagen[10..20], segunda.Cuerpo);

        await Enviar(red, $"HEAD {ruta} HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n");
        var cabecera = await LeerRespuesta(red, sinCuerpo: true);
        Assert.Equal(imagen.Length.ToString(), cabecera.Cabeceras["Content-Length"]);

        await Enviar(red, $"GET {ruta} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n");
        var ultima = await LeerRespuesta(red);
        Assert.Equal("close", ultima.Cabeceras["Connection"]);
        Assert.Equal(imagen, ultima.Cuerpo);
        Assert.True(await Cerrada(red));                                                                 // y el servidor cerró
    }

    [Fact]
    public async Task VariasPeticionesEnviadasJuntas_SeContestanUnaTrasOtra()
    {
        var (tcp, red, ruta) = await Conectar();
        using var _ = tcp;
        await Enviar(red, $"GET {ruta} HTTP/1.1\r\nHost: x\r\n\r\nGET {ruta} HTTP/1.1\r\nHost: x\r\nRange: bytes=0-4\r\n\r\n");
        var primera = await LeerRespuesta(red);
        var segunda = await LeerRespuesta(red);
        Assert.Equal(imagen, primera.Cuerpo);
        Assert.Equal(imagen[..5], segunda.Cuerpo);
    }

    [Fact]
    public async Task HttpUnoPuntoCero_CierraSalvoQueSePidaMantener()
    {
        var (tcp, red, ruta) = await Conectar();
        using var _ = tcp;
        await Enviar(red, $"GET {ruta} HTTP/1.0\r\n\r\n");
        var r = await LeerRespuesta(red);
        Assert.Equal("close", r.Cabeceras["Connection"]);
        Assert.Equal(imagen, r.Cuerpo);
        Assert.True(await Cerrada(red));
    }

    [Fact]
    public async Task UnCuerpoEnUnGet_SeLeeParaQueLaSiguientePeticionEmpieceDondeDebe()
    {
        var (tcp, red, ruta) = await Conectar();
        using var _ = tcp;
        await Enviar(red, $"GET {ruta} HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\n\r\nhola!GET {ruta} HTTP/1.1\r\nHost: x\r\nRange: bytes=0-1\r\n\r\n");
        Assert.Equal(imagen, (await LeerRespuesta(red)).Cuerpo);
        Assert.Equal(imagen[..2], (await LeerRespuesta(red)).Cuerpo);
    }

    [Theory]
    [InlineData("esto no es http\r\n\r\n", "HTTP/1.1 400 Bad Request")]
    [InlineData("GET /x HTTP/2.0\r\nHost: x\r\n\r\n", "HTTP/1.1 400 Bad Request")]
    [InlineData("GET /x HTTP/1.1\r\nsin-dos-puntos\r\n\r\n", "HTTP/1.1 400 Bad Request")]
    [InlineData("GET /x HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n", "HTTP/1.1 400 Bad Request")]
    [InlineData("GET /x HTTP/1.1\r\nHost: x\r\nContent-Length: 99999999\r\n\r\n", "HTTP/1.1 413 Content Too Large")]
    public async Task UnaPeticionMalformada_RecibeUnErrorYSeCierra(string peticion, string linea)
    {
        var (tcp, red, _) = await Conectar();
        using var _ = tcp;
        await Enviar(red, peticion);
        var r = await LeerRespuesta(red);
        Assert.Equal(linea, r.Linea);
        Assert.Equal("close", r.Cabeceras["Connection"]);
        Assert.True(await Cerrada(red));
    }

    [Fact]
    public async Task UnaCabeceraDemasiadoLarga_Da431()
    {
        var (tcp, red, _) = await Conectar();
        using var _ = tcp;
        await Enviar(red, "GET /x HTTP/1.1\r\nX-Relleno: " + new string('a', 17 * 1024));
        var r = await LeerRespuesta(red);
        Assert.Equal("HTTP/1.1 431 Request Header Fields Too Large", r.Linea);
    }

    // ------------------------------------------------------------------------- el cierre

    [Fact]
    public async Task Dispose_CierraElPuertoYLasConexionesAbiertas_YNoSePuedeReiniciar()
    {
        var (tcp, red, ruta) = await Conectar();
        using var _ = tcp;
        await Enviar(red, $"GET {ruta} HTTP/1.1\r\nHost: x\r\n\r\n");
        await LeerRespuesta(red);
        var puerto = servidor.Iniciar().Port;

        servidor.Dispose();

        Assert.True(await Cerrada(red));                                                                  // la conexión que estaba abierta se cerró
        await Assert.ThrowsAnyAsync<Exception>(async () =>
        {
            using var nuevo = new TcpClient();
            await nuevo.ConnectAsync(IPAddress.Loopback, puerto);                       // y el puerto ya no escucha
        });
        Assert.Throws<ObjectDisposedException>(() => servidor.Iniciar());
        servidor.Dispose();                                                              // liberar dos veces es inocuo
    }

    [Fact]
    public void SinIniciar_DisposeNoHaceNada()
    {
        using var nuevo = new ServidorLocalDeMedios(almacen);
        nuevo.Dispose();
        nuevo.Dispose();
    }
}

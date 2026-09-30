using System.Net;
using System.Text.Json;
using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>Un <see cref="IProgress{T}"/> que anota en el acto (Progress&lt;T&gt; publica en otro hilo y las pruebas verían el avance tarde).</summary>
internal sealed class ProgresoAnotado : IProgress<ProgresoDescarga>
{
    public List<ProgresoDescarga> Reportes { get; } = [];
    public void Report(ProgresoDescarga valor) { lock (Reportes) Reportes.Add(valor); }
}

/// <summary>
/// El descargador de paquetes contra un nodo falso que habla HTTP de verdad (streaming, <c>Range</c>, errores): descarga completa, corte y
/// reanudación desde el byte correcto, huellas del manifiesto y de los archivos, denegada, vencida, sin espacio, pausa y confirmación.
/// </summary>
[Collection("estado global")]
public sealed class DescargadorTests : IDisposable
{
    private const int B = ArchivoCifrado.LongitudBloque;
    private const string Dispositivo = EstudioAyudas.Dispositivo;
    private const string Alumno = EstudioAyudas.Alumno;
    private const string Asignacion = EstudioAyudas.Asignacion;

    private readonly string carpeta = Ayudas.CarpetaTemporal();
    private readonly ProveedorDeClaveEnMemoria proveedor = new();
    private readonly NodoDePaquete nodo = new();
    private readonly ProgresoAnotado progreso = new();
    private readonly ArchivoDePrueba pequeno = new("pequeno", EstudioAyudas.Datos(5_000, 31), "image/png");
    private readonly ArchivoDePrueba grande = new("grande", EstudioAyudas.Datos(2 * B + 12_345, 32), "video/mp4");
    private long libre = long.MaxValue;
    private readonly AlmacenEstudio almacen;

    public DescargadorTests()
    {
        ClienteJson.Token = null;
        almacen = EstudioAyudas.Almacen(carpeta, proveedor, () => 1_000, () => libre);
        nodo.Archivos.Add(pequeno);
        nodo.Archivos.Add(grande);
    }

    public void Dispose()
    {
        ClienteJson.Token = null;
        try { Directory.Delete(carpeta, true); } catch { }
    }

    private DescargadorDePaquetes Descargador(EstudioApi? api = null) => new(api ?? nodo.Api(), almacen, () => 1_000);

    private Task<ResultadoDescarga> Bajar(DescargadorDePaquetes descargador, CancellationToken ct = default) =>
        descargador.DescargarAsync(Dispositivo, Alumno, Asignacion, progreso, ct);

    private PaqueteLocal Paquete() => almacen.ObtenerPaquete(Alumno, Asignacion)!;

    private byte[] Leer(string mediaRef)
    {
        using var flujo = almacen.AbrirArchivo(Alumno, Asignacion, mediaRef)!;
        return EstudioAyudas.LeerTodo(flujo);
    }

    // ----------------------------------------------------------------------------- lo feliz

    [Fact]
    public async Task UnaDescargaCompleta_PideManifiestaBajaVerificaConfirmaYDejaElPaqueteDisponible()
    {
        var descargador = Descargador();
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));

        Assert.Null(descargador.UltimoError);
        Assert.Null(descargador.UltimoMotivo);
        var paquete = Paquete();
        Assert.True(paquete.Disponible);
        Assert.Equal(pequeno.Datos.Length + grande.Datos.Length, paquete.BytesTotal);
        Assert.Equal(paquete.BytesTotal, paquete.BytesDescargados);
        using var manifiesto = JsonDocument.Parse(nodo.Manifiesto());
        Assert.Equal(manifiesto.RootElement.GetProperty("huella").GetString(), paquete.Huella);
        Assert.NotNull(almacen.LeerManifiesto(Alumno, Asignacion));
        Assert.Equal(pequeno.Datos, Leer("pequeno"));
        Assert.Equal(grande.Datos, Leer("grande"));
        Assert.Equal((grande.Datos.Length, "video/mp4"), almacen.InfoArchivo(Alumno, Asignacion, "grande")!.Value);

        // Las peticiones, en orden: pedir, manifiesto, cada archivo (sin Range: es una descarga nueva) y confirmar.
        Assert.Collection(nodo.Peticiones,
            p => Assert.Equal("POST /api/modo-estudio/paquetes/", p),
            p => Assert.Equal($"GET /api/modo-estudio/paquetes/paq-1/manifiesto/?dispositivo={Dispositivo}&alumno_id={Alumno}", p),
            p => Assert.Equal($"GET /api/modo-estudio/paquetes/paq-1/archivos/pequeno/?dispositivo={Dispositivo}&alumno_id={Alumno}", p),
            p => Assert.Equal($"GET /api/modo-estudio/paquetes/paq-1/archivos/grande/?dispositivo={Dispositivo}&alumno_id={Alumno}", p),
            p => Assert.Equal("POST /api/modo-estudio/paquetes/paq-1/confirmar/", p));
        using var confirmar = JsonDocument.Parse(nodo.CuerpoConfirmar!);
        Assert.Equal(manifiesto.RootElement.GetProperty("huella").GetString(), confirmar.RootElement.GetProperty("huella").GetString());
        Assert.Equal(paquete.BytesTotal, confirmar.RootElement.GetProperty("bytes").GetInt64());
        Assert.Equal((Dispositivo, Alumno), (confirmar.RootElement.GetProperty("dispositivo").GetString(), confirmar.RootElement.GetProperty("alumno_id").GetString()));

        // El progreso sube sin retroceder, empieza «descargando» y termina «disponible» al 100 %.
        var reportes = progreso.Reportes;
        Assert.NotEmpty(reportes);
        Assert.Equal("descargando", reportes[0].Estado);
        Assert.Equal(reportes.Select(r => r.BytesDescargados).OrderBy(b => b).ToList(), reportes.Select(r => r.BytesDescargados).ToList());
        Assert.All(reportes, r => Assert.Equal(paquete.BytesTotal, r.BytesTotal));
        Assert.Contains(reportes, r => r.Archivo == "grande");
        Assert.Equal(("disponible", 1.0, paquete.BytesTotal), (reportes[^1].Estado, reportes[^1].Fraccion, reportes[^1].BytesDescargados));
        Assert.All(reportes, r => Assert.Equal(Asignacion, r.AsignacionId));
    }

    [Fact]
    public async Task ElProgreso_TraeLaVelocidadYElTiempoRestanteEstimados_CuandoLaRedEsLenta()
    {
        nodo.RetardoPorTrozo = TimeSpan.FromMilliseconds(40);                          // ~10 trozos de 16 KiB × 40 ms: la descarga dura más de 200 ms
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(Descargador()));

        var conVelocidad = progreso.Reportes.Where(r => r.Estado == "descargando" && r.BytesPorSegundo is > 0 && r.Restante is not null).ToList();
        Assert.NotEmpty(conVelocidad);
        Assert.All(conVelocidad, r =>
        {
            Assert.True(r.Restante >= TimeSpan.Zero);
            Assert.True(r.BytesPorSegundo < 50_000_000);                                // del orden de la red simulada (~400 KB/s), no un disparate
        });
        var primero = progreso.Reportes[0];
        Assert.Null(primero.BytesPorSegundo);                                           // al empezar todavía no hay de qué medir
        Assert.Null(primero.Restante);
        var final = progreso.Reportes[^1];
        Assert.Equal(("disponible", 1.0), (final.Estado, final.Fraccion));
    }

    [Fact]
    public async Task LosArchivosNoIncluidos_NoSeBajan_YUnArchivoVacioNoNecesitaPeticion()
    {
        nodo.NoIncluidos.Add("simulacion-lab");
        nodo.Archivos.Add(new ArchivoDePrueba("vacio", [], "text/plain"));
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(Descargador()));
        Assert.Empty(nodo.PeticionesDeArchivos("simulacion-lab"));
        Assert.Empty(nodo.PeticionesDeArchivos("vacio"));                           // cero bytes: no hay nada que pedir
        Assert.Empty(Leer("vacio"));
        Assert.Equal(pequeno.Datos.Length + grande.Datos.Length, Paquete().BytesTotal);
    }

    [Fact]
    public async Task UnMedioRepetidoEnElManifiesto_SeBajaUnaSolaVez_YCuentaUnaSolaVez()
    {
        nodo.Archivos.Add(pequeno);                                                  // el mismo medio dos veces
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(Descargador()));
        Assert.Single(nodo.PeticionesDeArchivos("pequeno"));
        using var confirmar = JsonDocument.Parse(nodo.CuerpoConfirmar!);
        Assert.Equal(pequeno.Datos.Length + grande.Datos.Length, confirmar.RootElement.GetProperty("bytes").GetInt64());
        Assert.Equal(pequeno.Datos.Length + grande.Datos.Length, Paquete().BytesTotal);
        Assert.Equal(pequeno.Datos, Leer("pequeno"));
    }

    [Fact]
    public async Task UnPaqueteYaDescargadoYVigente_NoPideNadaAlNodo()
    {
        var descargador = Descargador();
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
        var antes = nodo.Peticiones.Count;
        progreso.Reportes.Clear();
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
        Assert.Equal(antes, nodo.Peticiones.Count);
        Assert.Equal(("disponible", 1.0), (progreso.Reportes[^1].Estado, progreso.Reportes[^1].Fraccion));
    }

    // -------------------------------------------------------------- corte, pausa y reanudación

    [Fact]
    public async Task UnCorteAMitad_DejaElPaquetePausado_YLaReanudacionPideDesdeElByteCorrecto_SinVolverAPedirLoYaBajado()
    {
        nodo.CortarEn["grande"] = 100_000;                                          // se cae la red con 100 000 bytes del archivo grande
        var descargador = Descargador();
        Assert.Equal(ResultadoDescarga.SinConexion, await Bajar(descargador));

        var pausado = Paquete();
        Assert.Equal("pausado", pausado.Estado);
        Assert.Equal(pequeno.Datos.Length + B, pausado.BytesDescargados);           // el pequeño completo y un bloque entero del grande; la cola se perdió
        Assert.NotNull(descargador.UltimoMotivo);
        Assert.Equal("pausado", progreso.Reportes[^1].Estado);
        Assert.Equal(1, nodo.Solicitudes);
        var peticionesAntes = nodo.Peticiones.Count;

        progreso.Reportes.Clear();
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));

        var nuevas = nodo.Peticiones.Skip(peticionesAntes).ToList();
        Assert.Equal(1, nodo.Solicitudes);                                           // no se volvió a pedir el paquete
        Assert.DoesNotContain(nuevas, p => p.Contains("/archivos/pequeno/"));        // ni el archivo que ya estaba completo
        var pedidoGrande = Assert.Single(nuevas, p => p.Contains("/archivos/grande/"));
        Assert.EndsWith($"[bytes={B}-]", pedidoGrande);                              // desde el primer byte que faltaba
        Assert.Contains(nuevas, p => p.Contains("/manifiesto/"));                    // sí se rebajó el manifiesto (barato y verifica vigencia)
        Assert.Equal(("descargando", pequeno.Datos.Length + B), (progreso.Reportes[0].Estado, progreso.Reportes[0].BytesDescargados));   // ya empieza mostrando lo que había
        Assert.True(Paquete().Disponible);
        Assert.Equal(grande.Datos, Leer("grande"));                                  // y lo reanudado quedó idéntico al original
        Assert.Equal(pequeno.Datos, Leer("pequeno"));
    }

    [Fact]
    public async Task LaPausaPorToken_DevuelvePausada_SinLanzar_YSePuedeReanudar()
    {
        using var pausa = new CancellationTokenSource();
        nodo.PausarEn["grande"] = (135_000, pausa.Cancel);                           // el alumno pulsa «pausar» a los 135 000 bytes (dos bloques y medio)
        var descargador = Descargador();

        var resultado = await Bajar(descargador, pausa.Token);

        Assert.Equal(ResultadoDescarga.Pausada, resultado);
        Assert.Null(descargador.UltimoError);
        var paquete = Paquete();
        Assert.Equal("pausado", paquete.Estado);
        Assert.Equal(pequeno.Datos.Length + 2 * B, paquete.BytesDescargados);       // dos bloques completos del grande quedaron a salvo
        Assert.Equal("pausado", progreso.Reportes[^1].Estado);
        Assert.Equal(0, nodo.PeticionesDeArchivos("grande").Count(p => p.Contains("[bytes=")));

        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
        Assert.EndsWith($"[bytes={2 * B}-]", nodo.PeticionesDeArchivos("grande")[^1]);
        Assert.Equal(grande.Datos, Leer("grande"));
    }

    [Fact]
    public async Task UnNodoQueSeQuedaCallado_SinCerrar_SeDaPorCortadoTrasLaEsperaSinDatos_YSePuedeReanudar()
    {
        nodo.ColgarEn["grande"] = 100_000;                                           // el Wi-Fi se va sin avisar: no llega nada y la conexión no se cierra
        var descargador = new DescargadorDePaquetes(nodo.Api(), almacen, () => 1_000, esperaSinDatos: TimeSpan.FromMilliseconds(300));

        var espera = System.Diagnostics.Stopwatch.StartNew();
        var resultado = await Bajar(descargador).WaitAsync(TimeSpan.FromSeconds(20));    // sin el límite, esto no terminaría nunca

        Assert.Equal(ResultadoDescarga.SinConexion, resultado);
        Assert.True(espera.Elapsed < TimeSpan.FromSeconds(10));
        Assert.Equal("pausado", Paquete().Estado);
        Assert.Equal(pequeno.Datos.Length + B, Paquete().BytesDescargados);           // lo que llegó antes del silencio quedó a salvo

        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));           // y al volver la red se continúa donde iba
        Assert.EndsWith($"[bytes={B}-]", nodo.PeticionesDeArchivos("grande")[^1]);
        Assert.Equal(grande.Datos, Leer("grande"));
    }

    [Fact]
    public async Task PausarMientrasElNodoEstaCallado_EsUnaPausa_NoUnaEsperaAgotada()
    {
        nodo.ColgarEn["grande"] = 100_000;
        using var pausa = new CancellationTokenSource(TimeSpan.FromMilliseconds(400));
        var descargador = new DescargadorDePaquetes(nodo.Api(), almacen, () => 1_000, esperaSinDatos: TimeSpan.FromSeconds(30));
        Assert.Equal(ResultadoDescarga.Pausada, await Bajar(descargador, pausa.Token).WaitAsync(TimeSpan.FromSeconds(20)));
        Assert.Equal("pausado", progreso.Reportes[^1].Estado);
    }

    [Fact]
    public async Task UnTokenYaCancelado_TambienEsUnaPausa_NoUnaExcepcion()
    {
        using var cancelado = new CancellationTokenSource();
        cancelado.Cancel();
        Assert.Equal(ResultadoDescarga.Pausada, await Bajar(Descargador(), cancelado.Token));
        Assert.Null(almacen.ObtenerPaquete(Alumno, Asignacion));                     // todavía no había pedido nada
    }

    [Fact]
    public async Task UnNodoQueIgnoraRange_ElDescargadorSaltaLosBytesYaBajados()
    {
        nodo.CortarEn["grande"] = 100_000;
        var descargador = Descargador();
        Assert.Equal(ResultadoDescarga.SinConexion, await Bajar(descargador));
        nodo.IgnorarRange = true;                                                    // ahora el nodo contesta 200 con el archivo entero
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
        Assert.EndsWith($"[bytes={B}-]", nodo.PeticionesDeArchivos("grande")[^1]);
        Assert.Equal(grande.Datos, Leer("grande"));
    }

    [Fact]
    public async Task SinRedAlPedir_DevuelveSinConexion_ConElErrorQueLoExplica_Y_LuegoContinua()
    {
        nodo.SinRed = true;
        var descargador = Descargador();
        Assert.Equal(ResultadoDescarga.SinConexion, await Bajar(descargador));
        Assert.Equal(0, descargador.UltimoError!.Estado);
        Assert.Null(almacen.ObtenerPaquete(Alumno, Asignacion));
        nodo.SinRed = false;
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
        Assert.Null(descargador.UltimoError);
    }

    [Fact]
    public async Task SinRedDespuesDeBajarElManifiesto_QuedaPausado()
    {
        var descargador = Descargador();
        nodo.CortarEn["pequeno"] = 10;
        Assert.Equal(ResultadoDescarga.SinConexion, await Bajar(descargador));
        Assert.Equal("pausado", Paquete().Estado);
        Assert.Equal(0, Paquete().BytesDescargados);                                 // ni un bloque completo todavía
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
        Assert.Equal(pequeno.Datos, Leer("pequeno"));
    }

    // ----------------------------------------------------------------------- verificaciones

    [Fact]
    public async Task UnaHuellaDeManifiestoDistinta_EsHuellaInvalida_YNoSeBajaNada()
    {
        nodo.HuellaMala = true;
        var descargador = Descargador();
        Assert.Equal(ResultadoDescarga.HuellaInvalida, await Bajar(descargador));
        Assert.Empty(nodo.PeticionesDeArchivos());
        Assert.DoesNotContain(nodo.Peticiones, p => p.Contains("/confirmar/"));
        Assert.Null(almacen.LeerManifiestoCrudo(Alumno, Asignacion));                // el manifiesto que no pasó la verificación no se guarda
        Assert.False(Paquete().Disponible);
        Assert.Contains("huella", descargador.UltimoMotivo!, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ElSha256DeUnArchivoDistinto_SeDescarta_YEsHuellaInvalida_SinConfirmar()
    {
        var otro = (byte[])grande.Datos.Clone();
        otro[70_000] ^= 0xFF;                                                        // un solo byte cambiado, misma longitud
        nodo.Corrompidos["grande"] = otro;
        var descargador = Descargador();

        Assert.Equal(ResultadoDescarga.HuellaInvalida, await Bajar(descargador));

        Assert.DoesNotContain(nodo.Peticiones, p => p.Contains("/confirmar/"));
        Assert.Equal((false, 0L), almacen.EstadoDeArchivo(Alumno, Asignacion, "grande"));   // se descartó
        Assert.Empty(Directory.GetFiles(Path.Combine(carpeta, "almacen"), "m-*.parte", SearchOption.AllDirectories));
        Assert.True(almacen.EstadoDeArchivo(Alumno, Asignacion, "pequeno").Completo);        // lo demás sigue bueno
        Assert.False(Paquete().Disponible);
        Assert.Null(almacen.AbrirArchivo(Alumno, Asignacion, "grande"));

        nodo.Corrompidos.Clear();                                                    // el nodo se arregla: sólo se vuelve a bajar el archivo malo
        var antes = nodo.Peticiones.Count;
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
        Assert.DoesNotContain(nodo.Peticiones.Skip(antes), p => p.Contains("/archivos/pequeno/"));
        Assert.Equal(grande.Datos, Leer("grande"));
    }

    [Fact]
    public async Task UnManifiestoSinSha256_NoSeDescarga()
    {
        var conSha = nodo.Manifiesto();
        using var documento = JsonDocument.Parse(conSha);
        // Un manifiesto bien firmado pero mal armado: un archivo sin sha256. Se sirve con su huella recalculada.
        var texto = conSha.Replace(pequeno.Sha256, "");
        using var sinSha = JsonDocument.Parse(texto);
        var huella = JsonCanonico.Sha256(sinSha.RootElement, soloAscii: false, "huella");
        var firmado = texto.Replace(documento.RootElement.GetProperty("huella").GetString()!, huella);
        var api = new EstudioApi(new HttpClient(new ManejadorFalso((req, _) => Task.FromResult(req.Method == HttpMethod.Post && req.RequestUri!.AbsolutePath.EndsWith("/paquetes/")
            ? Ayudas.Respuesta(HttpStatusCode.Created, """{"paquete":{"id":"paq-1","asignacion_id":"asig-1","estado":"solicitado","bytes_total":1,"huella":"x","servidor_en":1}}""")
            : Ayudas.Respuesta(HttpStatusCode.OK, firmado)))), new Uri("http://192.168.0.55:8000/"));
        var descargador = Descargador(api);
        Assert.Equal(ResultadoDescarga.HuellaInvalida, await Bajar(descargador));
        Assert.Contains("sha256", descargador.UltimoMotivo!);
    }

    [Fact]
    public async Task UnaConfirmacionRechazada_EsHuellaInvalida_YAlReintentarSoloSeConfirma()
    {
        nodo.ErrorAlConfirmar = "huella_invalida";
        var descargador = Descargador();
        Assert.Equal(ResultadoDescarga.HuellaInvalida, await Bajar(descargador));
        Assert.Equal("huella_invalida", descargador.UltimoError!.Codigo);
        Assert.False(Paquete().Disponible);
        Assert.Equal(2, nodo.PeticionesDeArchivos().Count);

        nodo.ErrorAlConfirmar = null;
        var antes = nodo.Peticiones.Count;
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
        var nuevas = nodo.Peticiones.Skip(antes).ToList();
        Assert.DoesNotContain(nuevas, p => p.Contains("/archivos/"));                // todo estaba bajado y verificado: sólo confirma
        Assert.Contains(nuevas, p => p.Contains("/confirmar/"));
        Assert.True(Paquete().Disponible);
    }

    // ------------------------------------------------------------------- denegada y vencida

    [Fact]
    public async Task UnAparatoCompartido_RecibeDenegada_ConElMensajeDelNodo_YNoSeBajaNada()
    {
        nodo.Denegar = true;
        var descargador = Descargador();
        Assert.Equal(ResultadoDescarga.Denegada, await Bajar(descargador));

        Assert.Equal(("descarga_denegada", 403), (descargador.UltimoError!.Codigo, descargador.UltimoError.Estado));
        Assert.Equal("Pídele a tu profesor una tableta asignada.", descargador.UltimoError.Texto("mensaje"));
        Assert.Equal("dispositivo_compartido", descargador.UltimoError.Extra!.Value.GetProperty("paquete").GetProperty("motivo").GetString());
        Assert.Single(nodo.Peticiones);
        Assert.Null(almacen.ObtenerPaquete(Alumno, Asignacion));
    }

    [Fact]
    public async Task UnPaqueteVencido_Da410_YQuedaMarcadoComoVencido()
    {
        nodo.ManifiestoVencido = true;
        var descargador = Descargador();
        Assert.Equal(ResultadoDescarga.Vencida, await Bajar(descargador));
        Assert.Equal(410, descargador.UltimoError!.Estado);
        Assert.Equal("vencido", Paquete().Estado);
        Assert.Empty(nodo.PeticionesDeArchivos());
        Assert.Equal("vencido", progreso.Reportes[^1].Estado);
        Assert.Equal(1, almacen.LiberarVencidos(Alumno, 0).Paquetes);               // y MSG-045: lo vencido se puede liberar
        Assert.Null(almacen.ObtenerPaquete(Alumno, Asignacion));
    }

    [Fact]
    public async Task UnPaqueteQueVencioEnElAparato_NoSeReutilizaSinPedirloOtraVez()
    {
        var descargador = Descargador();
        nodo.VigenteHasta = 900;                                                     // el reloj del aparato dice 1 000: ya venció al terminar de bajarse
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
        Assert.Equal("vencido", Paquete().Estado);
        nodo.VigenteHasta = 4_000_000_000_000;                                       // el profesor reabre la asignación: el nodo da vigencia nueva
        var antes = nodo.Solicitudes;
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
        Assert.Equal(antes + 1, nodo.Solicitudes);                                   // lo vencido no se da por bueno: se pide otra vez
        Assert.True(Paquete().Disponible);
        Assert.Equal(grande.Datos, Leer("grande"));                                  // y no hubo que bajar los archivos de nuevo
        Assert.Single(nodo.PeticionesDeArchivos("grande"));
    }

    // --------------------------------------------------------------------- espacio y concurrencia

    [Fact]
    public async Task SinEspacio_NoSeBajaNada_YSePuedeReintentarCuandoHayLugar()
    {
        libre = 1_000;
        var descargador = Descargador();
        Assert.Equal(ResultadoDescarga.SinEspacio, await Bajar(descargador));
        Assert.Empty(nodo.PeticionesDeArchivos());
        Assert.Equal("pausado", Paquete().Estado);
        libre = long.MaxValue;
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
    }

    [Fact]
    public async Task ElEspacioQueHaceFalta_CuentaLoYaBajado_YElCifrado()
    {
        var descargador = Descargador();
        nodo.CortarEn["grande"] = 100_000;                                           // se corta con un bloque completo del grande a salvo
        Assert.Equal(ResultadoDescarga.SinConexion, await Bajar(descargador));
        var yaBajado = Paquete().BytesDescargados;
        Assert.True(yaBajado > pequeno.Datos.Length);
        // Falta: lo que resta del archivo grande (más cifrado); con un poco más de eso alcanza, con menos no.
        var falta = ArchivoCifrado.LongitudDelArchivo(grande.Datos.Length) - ArchivoCifrado.LongitudDelArchivo(yaBajado - pequeno.Datos.Length);
        libre = falta - 1;
        Assert.Equal(ResultadoDescarga.SinEspacio, await Bajar(descargador));
        libre = falta;
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
    }

    [Fact]
    public async Task DosDescargasDeLaMismaLeccion_LaSegundaNoHaceNada()
    {
        using var enCurso = new ManualResetEventSlim();
        using var seguir = new ManualResetEventSlim();
        nodo.PausarEn["grande"] = (70_000, () => { enCurso.Set(); seguir.Wait(TimeSpan.FromSeconds(10)); });
        var descargador = Descargador();
        var primera = Task.Run(() => Bajar(descargador));
        Assert.True(enCurso.Wait(TimeSpan.FromSeconds(10)));

        Assert.Equal(ResultadoDescarga.Fallida, await Bajar(descargador));           // la lección ya se está bajando

        seguir.Set();
        Assert.Equal(ResultadoDescarga.SinConexion, await primera);                  // la primera termina como le tocaba (se cortó la red simulada)
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
        Assert.Equal(grande.Datos, Leer("grande"));
    }

    // ---------------------------------------------------------------------- actualizar

    [Fact]
    public async Task ActualizarDescarga_BajaSoloLoQueCambio()
    {
        var descargador = Descargador();
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
        var nuevoGrande = new ArchivoDePrueba("grande", EstudioAyudas.Datos(B + 10, 77), "video/mp4");
        nodo.Archivos[1] = nuevoGrande;                                              // el editor cambió el video; la imagen sigue igual
        var antes = nodo.Peticiones.Count;

        Assert.Equal(ResultadoDescarga.Completa, await descargador.ActualizarAsync(Dispositivo, Alumno, Asignacion, progreso));

        var nuevas = nodo.Peticiones.Skip(antes).ToList();
        Assert.Contains("POST /api/modo-estudio/paquetes/", nuevas);                 // se vuelve a pedir el paquete
        Assert.DoesNotContain(nuevas, p => p.Contains("/archivos/pequeno/"));
        Assert.Single(nuevas, p => p.Contains("/archivos/grande/"));
        Assert.Equal(nuevoGrande.Datos, Leer("grande"));
        Assert.Equal(pequeno.Datos, Leer("pequeno"));
        Assert.True(Paquete().Disponible);
        Assert.Equal(pequeno.Datos.Length + nuevoGrande.Datos.Length, Paquete().BytesTotal);
    }

    [Fact]
    public async Task ActualizarDescarga_SinCambios_NoBajaNiConfirmaDeNuevo()
    {
        var descargador = Descargador();
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
        var antes = nodo.Peticiones.Count;
        Assert.Equal(ResultadoDescarga.Completa, await descargador.ActualizarAsync(Dispositivo, Alumno, Asignacion));
        var nuevas = nodo.Peticiones.Skip(antes).ToList();
        Assert.Equal(2, nuevas.Count);                                               // pedir y manifiesto; nada más
        Assert.True(Paquete().Disponible);
    }

    [Fact]
    public async Task ActualizarDescarga_QueFalla_NoDanaUnPaqueteQueYaServia()
    {
        var descargador = Descargador();
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
        nodo.SinRed = true;
        Assert.Equal(ResultadoDescarga.SinConexion, await descargador.ActualizarAsync(Dispositivo, Alumno, Asignacion));
        Assert.True(Paquete().Disponible);
        Assert.Equal(grande.Datos, Leer("grande"));
    }

    // ------------------------------------------------------------ el nodo cambió de paquete

    [Fact]
    public async Task SiElNodoYaNoConoceElPaqueteQueSeReanuda_LoPideDeNuevoUnaSolaVez()
    {
        nodo.CortarEn["grande"] = 100_000;
        var descargador = Descargador();
        Assert.Equal(ResultadoDescarga.SinConexion, await Bajar(descargador));
        Assert.Equal("paq-1", Paquete().PaqueteId);

        nodo.PaqueteId = "paq-2";                                                    // el nodo rehízo el paquete: el id anterior ya no existe (404)
        var antes = nodo.Solicitudes;
        Assert.Equal(ResultadoDescarga.Completa, await Bajar(descargador));
        Assert.Equal(antes + 1, nodo.Solicitudes);
        Assert.Equal("paq-2", Paquete().PaqueteId);
        Assert.Equal(grande.Datos, Leer("grande"));
    }
}

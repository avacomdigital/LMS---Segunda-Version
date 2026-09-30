using System.Buffers;
using System.Collections.Concurrent;
using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;

namespace Avacom.Lms.Core.Estudio;

/// <summary>
/// El servidor HTTP local de los medios de un paquete descargado (spec-driven/04-modo-estudio/02-modelo-y-api.md §5): escucha SÓLO en
/// <c>127.0.0.1</c>, en un puerto libre, y sirve —descifrándolos al vuelo desde <see cref="IAlmacenEstudio.AbrirArchivo"/>, sin cargar el archivo
/// entero en memoria— los mismos archivos que el aula sirve por red, para que los visores de siempre (<c>WebView</c>, <c>Image</c>, video) lean la
/// lección SIN nodo. Está escrito sobre <see cref="TcpListener"/> y no sobre <c>HttpListener</c> para que funcione igual en Android.
///
/// Ruta: <c>/{capacidad}/{alumno}/{asignación}/{mediaRef}</c>. La <i>capacidad</i> es un secreto aleatorio de este arranque: otra app del equipo
/// que hable con el puerto sin conocerla recibe 404 (igual que ante cualquier otra ruta). Hace <c>GET</c>, <c>HEAD</c> y <c>OPTIONS</c>; soporta
/// <c>Range</c> de un solo rango (<c>a-b</c>, <c>a-</c>, <c>-n</c>) con 206 y 416; nunca cachea (<c>Cache-Control: no-store</c>) y abre el CORS
/// (<c>Access-Control-Allow-Origin: *</c>) porque los visores web piden los medios desde otro origen. La conexión se mantiene abierta entre
/// peticiones (HTTP/1.1) salvo que el cliente pida cerrarla. Si un bloque no autentica a mitad de un cuerpo, se corta la conexión: jamás se
/// entrega contenido que no pasó la verificación.
/// </summary>
public sealed class ServidorLocalDeMedios(IAlmacenEstudio almacen) : IServidorLocalDeMedios
{
    private const int MaximoDeCabecera = 16 * 1024;
    private const int MaximoDeCuerpoIgnorado = 1024 * 1024;
    private static readonly TimeSpan EsperaEntrePeticiones = TimeSpan.FromSeconds(30);

    private readonly object candado = new();
    private readonly ConcurrentDictionary<TcpClient, byte> conexiones = new();
    private TcpListener? escucha;
    private CancellationTokenSource? parada;
    private Uri? baseUrl;
    private byte[] capacidad = [];
    private bool liberado;

    // ----------------------------------------------------------------------------- arranque

    public Uri Iniciar()
    {
        lock (candado)
        {
            ObjectDisposedException.ThrowIf(liberado, this);
            if (baseUrl is not null) return baseUrl;
            capacidad = Encoding.ASCII.GetBytes(Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(16)));
            var oyente = new TcpListener(IPAddress.Loopback, 0);
            oyente.Start();
            var puerto = ((IPEndPoint)oyente.LocalEndpoint).Port;
            escucha = oyente;
            parada = new CancellationTokenSource();
            baseUrl = new Uri($"http://127.0.0.1:{puerto}/{Encoding.ASCII.GetString(capacidad)}/");
            var ct = parada.Token;
            _ = Task.Run(() => AceptarAsync(oyente, ct));
            return baseUrl;
        }
    }

    public Uri UrlDe(string alumnoId, string asignacionId, string mediaRef)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(alumnoId);
        ArgumentException.ThrowIfNullOrWhiteSpace(asignacionId);
        ArgumentException.ThrowIfNullOrWhiteSpace(mediaRef);
        var raiz = Iniciar();
        return new Uri(raiz, $"{Uri.EscapeDataString(alumnoId)}/{Uri.EscapeDataString(asignacionId)}/{Uri.EscapeDataString(mediaRef)}");
    }

    public void Dispose()
    {
        CancellationTokenSource? cancelacion;
        TcpListener? oyente;
        lock (candado)
        {
            if (liberado) return;
            liberado = true;
            cancelacion = parada;
            oyente = escucha;
        }
        try { cancelacion?.Cancel(); } catch (ObjectDisposedException) { }
        try { oyente?.Stop(); } catch (SocketException) { }
        foreach (var conexion in conexiones.Keys)
        {
            try { conexion.Dispose(); } catch (Exception) { }
        }
        conexiones.Clear();
    }

    private async Task AceptarAsync(TcpListener oyente, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            TcpClient cliente;
            try { cliente = await oyente.AcceptTcpClientAsync(ct); }
            catch (Exception ex) when (ex is OperationCanceledException or ObjectDisposedException) { return; }
            catch (SocketException)
            {
                if (ct.IsCancellationRequested) return;
                // Una conexión que se cayó antes de aceptarla no debe apagar el servidor; la pausa evita girar en vacío si el fallo se repite.
                try { await Task.Delay(50, ct); }
                catch (OperationCanceledException) { return; }
                continue;
            }
            conexiones[cliente] = 0;
            _ = Task.Run(() => AtenderAsync(cliente, ct));
        }
    }

    // ------------------------------------------------------------------------ una conexión

    private sealed class Conexion(NetworkStream red)
    {
        public NetworkStream Red { get; } = red;
        public byte[] Buffer { get; } = new byte[MaximoDeCabecera];
        public int Largo { get; set; }
    }

    private sealed record Peticion(string Metodo, string Destino, string Version, Dictionary<string, string> Cabeceras)
    {
        public string? Cabecera(string nombre) => Cabeceras.GetValueOrDefault(nombre);

        /// <summary>HTTP/1.1 mantiene la conexión salvo que se pida cerrar; HTTP/1.0, sólo si se pide mantenerla.</summary>
        public bool QuiereMantener()
        {
            var deseo = Cabecera("connection") ?? "";
            return Version == "HTTP/1.1"
                ? !deseo.Contains("close", StringComparison.OrdinalIgnoreCase)
                : deseo.Contains("keep-alive", StringComparison.OrdinalIgnoreCase);
        }
    }

    private async Task AtenderAsync(TcpClient cliente, CancellationToken ct)
    {
        try
        {
            cliente.NoDelay = true;
            var conexion = new Conexion(cliente.GetStream());
            while (!ct.IsCancellationRequested)
            {
                var peticion = await LeerPeticionAsync(conexion, ct);
                if (peticion is null) break;
                if (!await ResponderAsync(conexion, peticion, ct)) break;
            }
            await CerrarConCortesiaAsync(cliente, conexion.Red, ct);
        }
        catch (Exception)
        {
            // El cliente se fue a mitad de una respuesta, un bloque no autenticó o se cerró el servidor: en todos los casos la conexión se cierra
            // y no hay nadie a quien avisar (un servidor local no registra fallos de sus clientes).
        }
        finally
        {
            conexiones.TryRemove(cliente, out _);
            try { cliente.Dispose(); } catch (Exception) { }
        }
    }

    /// <summary>
    /// Cierra la conexión sin pisar la última respuesta: avisa que no se enviará más (FIN) y lee un momento lo que el cliente todavía mande. Cerrar de
    /// golpe con datos sin leer hace que el sistema reinicie la conexión (RST) y el cliente pierda la respuesta de error que se acaba de escribir.
    /// </summary>
    private static async Task CerrarConCortesiaAsync(TcpClient cliente, NetworkStream red, CancellationToken ct)
    {
        try
        {
            if (ct.IsCancellationRequested || !cliente.Connected) return;
            cliente.Client.Shutdown(SocketShutdown.Send);
            using var limite = CancellationTokenSource.CreateLinkedTokenSource(ct);
            limite.CancelAfter(TimeSpan.FromMilliseconds(500));
            var basura = new byte[4096];
            var leido = 0;
            while (leido < 64 * 1024)
            {
                var n = await red.ReadAsync(basura, limite.Token);
                if (n == 0) break;
                leido += n;
            }
        }
        catch (Exception)
        {
            // Da igual cómo termine: ya no queda nada que decirle a este cliente.
        }
    }

    /// <summary>Lee la cabecera de la siguiente petición. Nulo si el cliente cerró, se agotó la espera o la petición no era válida (ya se contestó).</summary>
    private async Task<Peticion?> LeerPeticionAsync(Conexion c, CancellationToken ct)
    {
        while (true)
        {
            var fin = BuscarFinDeCabecera(c.Buffer, c.Largo);
            if (fin >= 0)
            {
                var texto = Encoding.Latin1.GetString(c.Buffer, 0, fin);
                var sobrante = c.Largo - (fin + 4);
                Buffer.BlockCopy(c.Buffer, fin + 4, c.Buffer, 0, sobrante);
                c.Largo = sobrante;
                var peticion = Analizar(texto);
                if (peticion is null) { await ResponderVacioAsync(c, 400, "Bad Request", cerrar: true, ct); return null; }
                if (peticion.Cabeceras.ContainsKey("transfer-encoding")) { await ResponderVacioAsync(c, 400, "Bad Request", cerrar: true, ct); return null; }
                if (!await DescartarCuerpoAsync(c, peticion, ct)) return null;
                return peticion;
            }
            if (c.Largo >= c.Buffer.Length)
            {
                await ResponderVacioAsync(c, 431, "Request Header Fields Too Large", cerrar: true, ct);
                return null;
            }
            using var limite = CancellationTokenSource.CreateLinkedTokenSource(ct);
            limite.CancelAfter(EsperaEntrePeticiones);
            int n;
            try { n = await c.Red.ReadAsync(c.Buffer.AsMemory(c.Largo), limite.Token); }
            catch (OperationCanceledException) { return null; }
            if (n == 0) return null;
            c.Largo += n;
        }
    }

    private static int BuscarFinDeCabecera(byte[] buffer, int largo)
    {
        for (var i = 0; i + 3 < largo; i++)
            if (buffer[i] == '\r' && buffer[i + 1] == '\n' && buffer[i + 2] == '\r' && buffer[i + 3] == '\n') return i;
        return -1;
    }

    private static Peticion? Analizar(string texto)
    {
        var lineas = texto.Split("\r\n");
        var partes = lineas[0].Split(' ');
        if (partes.Length != 3 || partes[0].Length == 0 || partes[1].Length == 0 || !partes[2].StartsWith("HTTP/1.", StringComparison.Ordinal)) return null;
        var cabeceras = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (var i = 1; i < lineas.Length; i++)
        {
            var dos = lineas[i].IndexOf(':');
            if (dos <= 0) return null;
            cabeceras[lineas[i][..dos].Trim()] = lineas[i][(dos + 1)..].Trim();
        }
        return new Peticion(partes[0].ToUpperInvariant(), partes[1], partes[2], cabeceras);
    }

    /// <summary>Un GET o HEAD no lleva cuerpo, pero si lo trae hay que leerlo para que la siguiente petición de la conexión empiece donde debe.</summary>
    private async Task<bool> DescartarCuerpoAsync(Conexion c, Peticion p, CancellationToken ct)
    {
        if (!long.TryParse(p.Cabecera("content-length"), NumberStyles.None, CultureInfo.InvariantCulture, out var largo) || largo == 0) return true;
        if (largo > MaximoDeCuerpoIgnorado)
        {
            await ResponderVacioAsync(c, 413, "Content Too Large", cerrar: true, ct);
            return false;
        }
        var faltan = largo - Math.Min(largo, c.Largo);
        var deLoLeido = (int)Math.Min(largo, c.Largo);
        Buffer.BlockCopy(c.Buffer, deLoLeido, c.Buffer, 0, c.Largo - deLoLeido);
        c.Largo -= deLoLeido;
        var basura = new byte[4096];
        while (faltan > 0)
        {
            using var limite = CancellationTokenSource.CreateLinkedTokenSource(ct);
            limite.CancelAfter(EsperaEntrePeticiones);
            int n;
            try { n = await c.Red.ReadAsync(basura.AsMemory(0, (int)Math.Min(basura.Length, faltan)), limite.Token); }
            catch (OperationCanceledException) { return false; }
            if (n == 0) return false;
            faltan -= n;
        }
        return true;
    }

    // ------------------------------------------------------------------------ una petición

    /// <summary>Contesta una petición. Falso si la conexión debe cerrarse (se pidió, o el cuerpo quedó a medias).</summary>
    private async Task<bool> ResponderAsync(Conexion c, Peticion p, CancellationToken ct)
    {
        var mantener = p.QuiereMantener();
        if (p.Metodo == "OPTIONS")
        {
            // La consulta previa (preflight) de CORS que hace el visor web antes de pedir un medio con Range.
            await EscribirCabeceraAsync(c, 204, "No Content", mantener, [
                ("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS"),
                ("Access-Control-Allow-Headers", "Range, Content-Type"),
                ("Access-Control-Max-Age", "600"),
                ("Content-Length", "0"),
            ], ct);
            return mantener;
        }
        if (p.Metodo is not ("GET" or "HEAD"))
        {
            await EscribirCabeceraAsync(c, 405, "Method Not Allowed", mantener, [("Allow", "GET, HEAD, OPTIONS"), ("Content-Length", "0")], ct);
            return mantener;
        }

        var medio = ResolverRuta(p.Destino);
        (long Longitud, string? Mime)? info = null;
        if (medio is { } m) info = almacen.InfoArchivo(m.Alumno, m.Asignacion, m.MediaRef);
        if (medio is null || info is null)
        {
            await ResponderVacioAsync(c, 404, "Not Found", cerrar: !mantener, ct);
            return mantener;
        }

        var longitud = info.Value.Longitud;
        var rango = ResolverRango(p.Cabecera("range"), longitud);
        if (rango.Insatisfacible)
        {
            await EscribirCabeceraAsync(c, 416, "Range Not Satisfiable", mantener, [("Content-Range", $"bytes */{longitud}"), ("Content-Length", "0")], ct);
            return mantener;
        }
        var inicio = rango.Presente ? rango.Inicio : 0;
        var cantidad = longitud == 0 ? 0 : (rango.Presente ? rango.Fin : longitud - 1) - inicio + 1;
        var cabeceras = new List<(string, string)>
        {
            ("Content-Type", TipoSeguro(info.Value.Mime)),
            ("Accept-Ranges", "bytes"),
            ("Content-Length", cantidad.ToString(CultureInfo.InvariantCulture)),
            ("Access-Control-Expose-Headers", "Content-Length, Content-Range, Accept-Ranges, Content-Type"),
        };
        if (rango.Presente) cabeceras.Add(("Content-Range", $"bytes {inicio}-{inicio + cantidad - 1}/{longitud}"));
        var codigo = rango.Presente ? 206 : 200;
        var frase = rango.Presente ? "Partial Content" : "OK";

        if (p.Metodo == "HEAD" || cantidad == 0)
        {
            await EscribirCabeceraAsync(c, codigo, frase, mantener, cabeceras, ct);
            return mantener;
        }

        // Se abre el archivo ANTES de mandar la cabecera: si ya no está (lo retiraron) todavía se puede contestar 404.
        await using var flujo = almacen.AbrirArchivo(medio.Value.Alumno, medio.Value.Asignacion, medio.Value.MediaRef);
        if (flujo is null)
        {
            await ResponderVacioAsync(c, 404, "Not Found", cerrar: !mantener, ct);
            return mantener;
        }
        await EscribirCabeceraAsync(c, codigo, frase, mantener, cabeceras, ct);
        var buffer = ArrayPool<byte>.Shared.Rent(64 * 1024);
        try
        {
            if (inicio > 0)
            {
                if (flujo.CanSeek) flujo.Seek(inicio, SeekOrigin.Begin);
                else await SaltarAsync(flujo, inicio, buffer, ct);
            }
            var restante = cantidad;
            while (restante > 0)
            {
                var n = await flujo.ReadAsync(buffer.AsMemory(0, (int)Math.Min(buffer.Length, restante)), ct);
                if (n == 0) return false;   // el archivo resultó más corto de lo anunciado: se corta la conexión, no se rellena
                await c.Red.WriteAsync(buffer.AsMemory(0, n), ct);
                restante -= n;
            }
        }
        finally
        {
            ArrayPool<byte>.Shared.Return(buffer);
        }
        return mantener;
    }

    private static async Task SaltarAsync(Stream flujo, long bytes, byte[] buffer, CancellationToken ct)
    {
        while (bytes > 0)
        {
            var n = await flujo.ReadAsync(buffer.AsMemory(0, (int)Math.Min(buffer.Length, bytes)), ct);
            if (n == 0) return;
            bytes -= n;
        }
    }

    // --------------------------------------------------------------------------- la ruta y el rango

    /// <summary>Descompone <c>/{capacidad}/{alumno}/{asignación}/{mediaRef}</c>. Nulo si la capacidad no es la de este arranque o la forma no es la esperada.</summary>
    private (string Alumno, string Asignacion, string MediaRef)? ResolverRuta(string destino)
    {
        var corte = destino.IndexOfAny(['?', '#']);
        var camino = corte >= 0 ? destino[..corte] : destino;
        if (!camino.StartsWith('/')) return null;
        var partes = camino[1..].Split('/');
        if (partes.Length != 4 || partes.Skip(1).Any(string.IsNullOrEmpty)) return null;
        byte[] esperada;
        lock (candado) esperada = capacidad;
        if (!CryptographicOperations.FixedTimeEquals(Encoding.ASCII.GetBytes(partes[0]), esperada)) return null;
        var alumno = Uri.UnescapeDataString(partes[1]);
        var asignacion = Uri.UnescapeDataString(partes[2]);
        var medio = Uri.UnescapeDataString(partes[3]);
        return string.IsNullOrWhiteSpace(alumno) || string.IsNullOrWhiteSpace(asignacion) || string.IsNullOrWhiteSpace(medio) ? null : (alumno, asignacion, medio);
    }

    private readonly record struct RangoPedido(bool Presente, bool Insatisfacible, long Inicio, long Fin);

    /// <summary>
    /// Interpreta <c>Range</c> (RFC 9110 §14): <c>bytes=a-b</c>, <c>bytes=a-</c> y <c>bytes=-n</c>. Una unidad desconocida, varios rangos o una
    /// sintaxis inválida se IGNORAN (se sirve el archivo entero, como permite el RFC); un rango que no toca el archivo es insatisfacible (416).
    /// </summary>
    private static RangoPedido ResolverRango(string? valor, long longitud)
    {
        var sinRango = new RangoPedido(false, false, 0, 0);
        if (string.IsNullOrWhiteSpace(valor)) return sinRango;
        valor = valor.Trim();
        if (!valor.StartsWith("bytes=", StringComparison.OrdinalIgnoreCase)) return sinRango;
        var especificacion = valor[6..].Trim();
        if (especificacion.Contains(',')) return sinRango;
        var guion = especificacion.IndexOf('-');
        if (guion < 0) return sinRango;
        var izquierda = especificacion[..guion].Trim();
        var derecha = especificacion[(guion + 1)..].Trim();
        var insatisfacible = new RangoPedido(true, true, 0, 0);
        if (izquierda.Length == 0)
        {
            // -n: los últimos n bytes
            if (!long.TryParse(derecha, NumberStyles.None, CultureInfo.InvariantCulture, out var ultimos)) return sinRango;
            if (ultimos == 0 || longitud == 0) return insatisfacible;
            return new RangoPedido(true, false, Math.Max(0, longitud - ultimos), longitud - 1);
        }
        if (!long.TryParse(izquierda, NumberStyles.None, CultureInfo.InvariantCulture, out var desde)) return sinRango;
        long hasta;
        if (derecha.Length == 0) hasta = longitud - 1;
        else
        {
            if (!long.TryParse(derecha, NumberStyles.None, CultureInfo.InvariantCulture, out hasta)) return sinRango;
            if (hasta < desde) return sinRango;
        }
        if (desde >= longitud) return insatisfacible;
        return new RangoPedido(true, false, desde, Math.Min(hasta, longitud - 1));
    }

    /// <summary>El tipo del medio va en una cabecera: sólo ASCII imprimible (un manifiesto con saltos de línea no puede inyectar cabeceras).</summary>
    private static string TipoSeguro(string? mime) =>
        !string.IsNullOrWhiteSpace(mime) && mime.All(c => c is >= ' ' and < (char)0x7F) ? mime.Trim() : "application/octet-stream";

    // ------------------------------------------------------------------------- escribir respuestas

    private static async Task ResponderVacioAsync(Conexion c, int codigo, string frase, bool cerrar, CancellationToken ct) =>
        await EscribirCabeceraAsync(c, codigo, frase, mantener: !cerrar, [("Content-Length", "0")], ct);

    private static async Task EscribirCabeceraAsync(Conexion c, int codigo, string frase, bool mantener, IEnumerable<(string Nombre, string Valor)> cabeceras, CancellationToken ct)
    {
        var texto = new StringBuilder(384)
            .Append("HTTP/1.1 ").Append(codigo).Append(' ').Append(frase).Append("\r\n")
            .Append("Date: ").Append(DateTime.UtcNow.ToString("R", CultureInfo.InvariantCulture)).Append("\r\n")
            .Append("Cache-Control: no-store\r\n")
            .Append("Access-Control-Allow-Origin: *\r\n")
            .Append("Cross-Origin-Resource-Policy: cross-origin\r\n")
            .Append("X-Content-Type-Options: nosniff\r\n")
            .Append("Connection: ").Append(mantener ? "keep-alive" : "close").Append("\r\n");
        foreach (var (nombre, valor) in cabeceras) texto.Append(nombre).Append(": ").Append(valor).Append("\r\n");
        texto.Append("\r\n");
        await c.Red.WriteAsync(Encoding.ASCII.GetBytes(texto.ToString()), ct);
    }
}

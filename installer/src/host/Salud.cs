using System.Net;
using System.Net.WebSockets;
using System.Text.Json;
using System.Net.NetworkInformation;
using System.Net.Sockets;

namespace Avacom.Ops.Host;

/// <summary>
/// Comprobaciones sobre el puerto y sobre la salud real del backend.
///
/// El endpoint /health/ ya existe en el backend (avacom_lms/urls.py). El
/// instalador lo usa tal cual: añadirlo o cambiarlo seria modificar el
/// comportamiento del producto, que es justo lo que no debe hacer.
/// </summary>
internal static class Salud
{
    /// <summary>
    /// El backend escucha en 0.0.0.0 pero a 0.0.0.0 no se le puede preguntar:
    /// la comprobacion se hace por loopback, que es donde vive el cliente OPS.
    /// </summary>
    public static string UrlSalud(int puerto) => $"http://127.0.0.1:{puerto}/health/";

    public sealed record Resultado(bool Correcto, string Detalle);

    /// <summary>
    /// Lo que /health/ dice del nodo: si tiene organizacion, si las claves son las derivadas y,
    /// si el modulo de acceso no pudo leer su base de datos, el error (permisos de Data, base
    /// bloqueada o corrupta). <c>Error</c> es null cuando todo va bien.
    /// </summary>
    public sealed record EstadoDelNodo(bool? Instalado, bool? ClavesDerivadas, string? Error = null);

    /// <summary>
    /// Pregunta a /health/ por el estado del modulo de acceso. Sin organizacion
    /// el login responde 409 no_instalado: la pantalla final del instalador lo
    /// avisa, porque crearla es una tarea de la aplicacion y no del asistente.
    /// </summary>
    public static async Task<EstadoDelNodo> EstadoAsync(int puerto)
    {
        try
        {
            using var cliente = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
            var cuerpo = await cliente.GetStringAsync(UrlSalud(puerto)).ConfigureAwait(false);
            using var documento = JsonDocument.Parse(cuerpo);
            if (!documento.RootElement.TryGetProperty("acceso", out var acceso)) return new EstadoDelNodo(null, null);

            var error = acceso.TryGetProperty("error", out var texto) && texto.ValueKind == JsonValueKind.String
                ? texto.GetString()
                : null;
            return new EstadoDelNodo(Booleano(acceso, "instalado"), Booleano(acceso, "claves_derivadas"), error);
        }
        catch (Exception error) when (error is HttpRequestException or TaskCanceledException or JsonException)
        {
            return new EstadoDelNodo(null, null);
        }
    }

    /// <summary>
    /// Lo que el aula ve de AVACOM Contenido (la biblioteca de cursos), preguntandoselo al propio backend:
    /// /api/aula/fuente/ no falla nunca, dice si hay contenido y cuantos cursos. Es informativo: sin
    /// biblioteca el aula instala y arranca igual, solo que sin cursos hasta que se abra. El instalador
    /// no habla con AVACOM Contenido ni lee su nota de enlace: eso es del backend.
    /// </summary>
    public sealed record EstadoDeBiblioteca(bool? Disponible, string Motivo, int? Cursos, string? VersionApp);

    public static async Task<EstadoDeBiblioteca> BibliotecaAsync(int puerto)
    {
        try
        {
            using var cliente = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
            var cuerpo = await cliente.GetStringAsync($"http://127.0.0.1:{puerto}/api/aula/fuente/").ConfigureAwait(false);
            using var documento = JsonDocument.Parse(cuerpo);
            var raiz = documento.RootElement;

            var motivo = raiz.TryGetProperty("motivo", out var m) && m.ValueKind == JsonValueKind.String ? m.GetString() ?? "" : "";
            int? cursos = raiz.TryGetProperty("cursos_instalados", out var c) && c.ValueKind == JsonValueKind.Array
                ? c.GetArrayLength()
                : null;
            var version = raiz.TryGetProperty("version_app", out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
            return new EstadoDeBiblioteca(Booleano(raiz, "disponible"), motivo, cursos, version);
        }
        catch (Exception error) when (error is HttpRequestException or TaskCanceledException or JsonException)
        {
            return new EstadoDeBiblioteca(null, "no se pudo consultar", null, null);
        }
    }

    private static bool? Booleano(JsonElement objeto, string nombre) =>
        objeto.TryGetProperty(nombre, out var valor) && valor.ValueKind is JsonValueKind.True or JsonValueKind.False
            ? valor.GetBoolean()
            : null;

    /// <summary>
    /// ¿El canal en tiempo real acepta conexiones? Se hace el saludo WebSocket
    /// contra una sesion que no existe: el consumidor del aula acepta la
    /// conexion y la cierra con su propio codigo, y aceptarla (HTTP 101) es
    /// justo lo que prueba que Daphne y Channels estan sirviendo el WebSocket.
    /// Con Waitress esto respondia 404.
    /// </summary>
    public static async Task<Resultado> ProbarWebSocketAsync(int puerto)
    {
        using var socket = new ClientWebSocket();
        using var limite = new CancellationTokenSource(TimeSpan.FromSeconds(8));
        try
        {
            var uri = new Uri($"ws://127.0.0.1:{puerto}/ws/aula/sesiones/validacion-del-instalador/?rol=docente");
            await socket.ConnectAsync(uri, limite.Token).ConfigureAwait(false);
            try
            {
                await socket.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "validacion", limite.Token).ConfigureAwait(false);
            }
            catch (Exception error) when (error is WebSocketException or OperationCanceledException or ObjectDisposedException)
            {
                // El servidor ya lo cerro con su codigo: la conexion se habia aceptado.
            }
            return new Resultado(true, "el canal en tiempo real acepta conexiones");
        }
        catch (Exception error) when (error is WebSocketException or OperationCanceledException or HttpRequestException)
        {
            return new Resultado(false, $"el canal en tiempo real no acepta conexiones ({error.Message})");
        }
    }

    /// <summary>Espera hasta <paramref name="segundos"/> a que el backend conteste.</summary>
    public static async Task<Resultado> EsperarAsync(int puerto, int segundos, CancellationToken cancelacion = default)
    {
        using var cliente = new HttpClient { Timeout = TimeSpan.FromSeconds(4) };
        var limite = DateTimeOffset.UtcNow.AddSeconds(segundos);
        var ultimo = "el backend no contesto todavia";

        while (DateTimeOffset.UtcNow < limite && !cancelacion.IsCancellationRequested)
        {
            try
            {
                using var respuesta = await cliente.GetAsync(UrlSalud(puerto), cancelacion).ConfigureAwait(false);
                var cuerpo = await respuesta.Content.ReadAsStringAsync(cancelacion).ConfigureAwait(false);

                if (respuesta.IsSuccessStatusCode && cuerpo.Contains("avacom-lms-backend", StringComparison.Ordinal))
                {
                    return new Resultado(true, Resumir(cuerpo));
                }
                ultimo = $"contesto {(int)respuesta.StatusCode} en {UrlSalud(puerto)}";
            }
            catch (Exception error) when (error is HttpRequestException or TaskCanceledException)
            {
                ultimo = "el backend no acepta conexiones todavia";
            }

            try
            {
                await Task.Delay(TimeSpan.FromSeconds(1), cancelacion).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                break;
            }
        }
        return new Resultado(false, ultimo);
    }

    /// <summary>true si nadie escucha aun en el puerto.</summary>
    public static bool PuertoLibre(int puerto)
    {
        var escuchando = IPGlobalProperties.GetIPGlobalProperties().GetActiveTcpListeners();
        if (escuchando.Any(p => p.Port == puerto)) return false;

        // Escuchar en la lista de puertos no basta: un socket exclusivo puede
        // impedir el bind sin figurar. Se comprueba haciendo el mismo bind que
        // hara Daphne.
        try
        {
            using var prueba = new TcpListener(IPAddress.Any, puerto);
            prueba.Start();
            prueba.Stop();
            return true;
        }
        catch (SocketException)
        {
            return false;
        }
    }

    /// <summary>
    /// Si el puerto esta ocupado, ¿lo ocupa nuestro propio backend? Distinguirlo
    /// evita que una reinstalacion se lea como un conflicto con otro programa.
    /// </summary>
    public static async Task<bool> EsNuestroBackendAsync(int puerto)
    {
        var resultado = await EsperarAsync(puerto, 2).ConfigureAwait(false);
        return resultado.Correcto;
    }

    /// <summary>
    /// De la salud del backend solo se afirma lo que /health/ dice del propio nodo. Antes aqui se
    /// decia tambien si la biblioteca estaba abierta, pero ese campo de /health/ habla del contrato
    /// anterior de la biblioteca (enlace.json) y daba "no esta abierta" con AVACOM Contenido
    /// funcionando: la biblioteca se consulta con <see cref="BibliotecaAsync"/>.
    /// </summary>
    private static string Resumir(string cuerpo) => "backend operativo";
}

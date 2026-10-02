using System.Globalization;
using System.Text;
using System.Text.Json;

namespace Avacom.Ops.Host;

/// <summary>
/// Los registros que el backend escribe en la carpeta de Logs del nodo (MOD-019: JSON Lines,
/// un archivo por canal). El instalador no los interpreta: solo comprueba que EXISTEN y que el
/// servicio los esta escribiendo, que es lo que la regla del producto exige ("el sistema siempre
/// debe poder guardar auditoria y logs"). Si el servicio no pudiera escribir en Logs, el backend
/// se desvia solo a una carpeta temporal y sigue funcionando, y nadie se enteraria hasta
/// necesitar el registro: por eso se mira aqui, justo al terminar de instalar.
/// </summary>
internal static class RegistrosDelNodo
{
    private const int BytesDeCola = 8192;

    /// <summary>La carpeta donde escribe el backend: la de backend.env (AVACOM_LMS_DIR_LOGS) o la de siempre.</summary>
    public static string CarpetaDelBackend() =>
        Configuracion.Leer().TryGetValue("AVACOM_LMS_DIR_LOGS", out var propia) && propia.Length > 0
            ? propia
            : Rutas.CarpetaLogs;

    /// <summary>
    /// ¿Hay un renglon reciente en backend-app.log? La validacion acaba de pedirle /health/ y abrir
    /// un WebSocket: cada peticion deja una linea, asi que si no hay ninguna reciente es que el
    /// servicio no esta escribiendo ahi.
    /// </summary>
    public static bool ComprobarEscrituraDelBackend(Registro registro)
    {
        var carpeta = CarpetaDelBackend();
        var archivo = Path.Combine(carpeta, "backend-app.log");

        for (var intento = 1; intento <= 6; intento++)
        {
            var ultima = UltimaMarcaDeTiempo(archivo);
            if (ultima is { } marca && DateTimeOffset.Now - marca < TimeSpan.FromMinutes(5))
            {
                registro.Escribir($"El backend esta escribiendo sus registros en {carpeta} (ultimo renglon a las {marca:HH:mm:ss}).");
                return true;
            }
            Thread.Sleep(500);
        }

        registro.Escribir(
            $"ADVERTENCIA: el backend no esta escribiendo sus registros en {carpeta}. " +
            "El servicio sigue funcionando, pero los registros y la auditoria en archivo iran a la carpeta temporal del sistema.");
        return false;
    }

    /// <summary>
    /// La marca de tiempo ("ts") del ultimo renglon JSON del archivo. Se lee solo la cola y con
    /// el archivo compartido: el backend lo tiene abierto escribiendo, y su tamano en el
    /// directorio puede ir por detras, asi que se pregunta al propio manejador.
    /// </summary>
    internal static DateTimeOffset? UltimaMarcaDeTiempo(string archivo)
    {
        try
        {
            using var flujo = new FileStream(archivo, FileMode.Open, FileAccess.Read,
                FileShare.ReadWrite | FileShare.Delete);
            var cola = (int)Math.Min(flujo.Length, BytesDeCola);
            if (cola == 0) return null;

            flujo.Seek(-cola, SeekOrigin.End);
            var bytes = new byte[cola];
            var leidos = 0;
            while (leidos < cola)
            {
                var n = flujo.Read(bytes, leidos, cola - leidos);
                if (n <= 0) break;
                leidos += n;
            }

            var lineas = Encoding.UTF8.GetString(bytes, 0, leidos).Split('\n');
            for (var i = lineas.Length - 1; i >= 0; i--)
            {
                var linea = lineas[i].Trim();
                if (!linea.StartsWith('{')) continue;
                try
                {
                    using var documento = JsonDocument.Parse(linea);
                    if (documento.RootElement.TryGetProperty("ts", out var ts)
                        && ts.ValueKind == JsonValueKind.String
                        && DateTimeOffset.TryParse(ts.GetString(), CultureInfo.InvariantCulture, DateTimeStyles.None, out var marca))
                    {
                        return marca;
                    }
                }
                catch (JsonException)
                {
                    // Primera linea cortada por la ventana de lectura: se sigue hacia atras.
                }
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
        }
        return null;
    }
}

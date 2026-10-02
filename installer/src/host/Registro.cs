using System.Text;

namespace Avacom.Ops.Host;

/// <summary>
/// Registro en archivo. El host no tiene consola (es un servicio y un lanzador
/// tactil), asi que el unico diagnostico posible es lo que quede escrito.
///
/// Rota por tamaño para que un backend que reinicie en bucle no llene el disco
/// del equipo del aula.
///
/// Una linea de registro NO se pierde porque otro proceso tenga el archivo
/// abierto: el backend (Python) escribe en el mismo instalacion.log mientras
/// corre, y el host sigue anotando ahi la validacion y los avisos. Por eso se
/// abre compartiendo lectura y escritura, y se reintenta unos instantes.
/// Tampoco un fallo de permisos puede tumbar nada: si la carpeta de Logs no se
/// puede escribir, se anota en la carpeta temporal del usuario.
/// </summary>
internal sealed class Registro
{
    private const long TamanoMaximoBytes = 2 * 1024 * 1024;
    private const int Intentos = 5;
    private static readonly UTF8Encoding Utf8SinMarca = new(false);

    private readonly string _ruta;
    private readonly Lock _candado = new();

    public Registro(string nombreArchivo)
    {
        var carpeta = Rutas.CarpetaLogs;
        try
        {
            Directory.CreateDirectory(carpeta);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            // Sin carpeta de Logs escribible, el diagnostico se desvia en lugar de perderse.
            carpeta = Path.Combine(Path.GetTempPath(), "AVACOM", "OPS Master", "Logs");
            try { Directory.CreateDirectory(carpeta); } catch (Exception) { /* se intentara igual al escribir */ }
        }
        _ruta = Path.Combine(carpeta, nombreArchivo);
    }

    public string Ruta => _ruta;

    public void Escribir(string mensaje)
    {
        var linea = $"{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss zzz}  {mensaje}";
        lock (_candado)
        {
            Rotar();
            Anexar(linea);
        }
    }

    public void Escribir(string mensaje, Exception error) =>
        Escribir($"{mensaje}: {error.GetType().Name}: {error.Message}");

    private void Anexar(string linea)
    {
        for (var intento = 1; intento <= Intentos; intento++)
        {
            try
            {
                using var flujo = new FileStream(_ruta, FileMode.Append, FileAccess.Write,
                    FileShare.ReadWrite | FileShare.Delete);
                using var escritor = new StreamWriter(flujo, Utf8SinMarca);
                escritor.WriteLine(linea);
                return;
            }
            catch (IOException) when (intento < Intentos)
            {
                // El otro proceso lo tiene abierto en este instante (o lo esta rotando).
                Thread.Sleep(40 * intento);
            }
            catch (IOException)
            {
                return; // Un fallo al registrar no puede tumbar el servicio.
            }
            catch (UnauthorizedAccessException)
            {
                return;
            }
        }
    }

    /// <summary>
    /// Si otro proceso tiene abierto el archivo (el backend con instalacion.log),
    /// el movimiento falla y se deja: rota el que lo tiene abierto. Lo importante
    /// es que un fallo aqui no impida escribir la linea.
    /// </summary>
    private void Rotar()
    {
        try
        {
            var info = new FileInfo(_ruta);
            if (!info.Exists || info.Length < TamanoMaximoBytes) return;

            var anterior = _ruta + ".1";
            if (File.Exists(anterior)) File.Delete(anterior);
            File.Move(_ruta, anterior);
        }
        catch (IOException)
        {
        }
        catch (UnauthorizedAccessException)
        {
        }
    }
}

using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;

namespace Avacom.Ops.Host.Actualizacion;

/// <summary>Un paso fallo: el aplicador decide si no se toco nada (se rechaza) o si hay que volver atras.</summary>
internal sealed class FalloDePaso(string paso, string mensaje) : Exception(mensaje)
{
    public string Paso { get; } = paso;
}

/// <summary>Operaciones de disco con la garantia que pide MOD-017: nada a medias, y lo escrito se vuelve a leer.</summary>
internal static class Disco
{
    private static readonly UTF8Encoding Utf8SinMarca = new(false);

    public static string Sha256DeArchivo(string ruta)
    {
        using var flujo = new FileStream(ruta, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
        return Convert.ToHexString(SHA256.HashData(flujo)).ToLowerInvariant();
    }

    /// <summary>Escribe a un temporal junto al destino, lo vuelca a disco y lo renombra: un corte deja el archivo viejo o el nuevo, nunca la mitad.</summary>
    public static void EscribirAtomico(string destino, string texto) => EscribirAtomico(destino, Utf8SinMarca.GetBytes(texto));

    public static void EscribirAtomico(string destino, byte[] bytes)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(destino)!);
        var temporal = destino + ".tmp";
        using (var flujo = new FileStream(temporal, FileMode.Create, FileAccess.Write, FileShare.None))
        {
            flujo.Write(bytes, 0, bytes.Length);
            flujo.Flush(flushToDisk: true);
        }
        File.Move(temporal, destino, overwrite: true);
    }

    /// <summary>
    /// Copia origen -> destino por un temporal, comprueba el SHA-256 de lo ESCRITO contra <paramref name="sha"/> y renombra. Si no cuadra, borra el temporal y falla:
    /// el destino queda como estaba.
    /// </summary>
    public static void CopiarVerificado(string origen, string destino, string sha)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(destino)!);
        var temporal = destino + ".avupd.tmp";
        try
        {
            using (var entrada = new FileStream(origen, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            using (var salida = new FileStream(temporal, FileMode.Create, FileAccess.Write, FileShare.None))
            {
                entrada.CopyTo(salida);
                salida.Flush(flushToDisk: true);
            }
            var escrita = Sha256DeArchivo(temporal);
            if (!string.Equals(escrita, sha, StringComparison.OrdinalIgnoreCase))
                throw new IOException($"La copia de {Path.GetFileName(destino)} no coincide con su huella.");
            File.Move(temporal, destino, overwrite: true);
        }
        finally
        {
            try { File.Delete(temporal); } catch (Exception error) when (error is IOException or UnauthorizedAccessException) { }
        }
    }

    /// <summary>La ruta completa de <paramref name="relativa"/> dentro de <paramref name="raiz"/>, o excepcion si se sale de ella o pasa por un enlace.</summary>
    public static string Confinar(string raiz, string relativa)
    {
        var raizCompleta = Path.GetFullPath(raiz).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        var completa = Path.GetFullPath(Path.Combine(raizCompleta, relativa.Replace('/', Path.DirectorySeparatorChar)));
        if (!completa.StartsWith(raizCompleta, StringComparison.OrdinalIgnoreCase))
            throw new IOException($"La ruta {relativa} se sale de {raiz}.");
        // Un enlace simbolico o una union en el camino llevaria la escritura a otra parte.
        var actual = Path.GetDirectoryName(completa);
        while (actual is not null && actual.Length >= raizCompleta.Length && Directory.Exists(actual))
        {
            if (new DirectoryInfo(actual).Attributes.HasFlag(FileAttributes.ReparsePoint))
                throw new IOException($"La carpeta {actual} es un enlace: no se escribe a traves de ella.");
            actual = Path.GetDirectoryName(actual);
        }
        return completa;
    }

    /// <summary>Borra las carpetas vacias desde <paramref name="carpeta"/> hacia arriba, sin llegar a <paramref name="hasta"/>.</summary>
    public static void PodarVacias(string carpeta, string hasta)
    {
        var tope = Path.GetFullPath(hasta).TrimEnd(Path.DirectorySeparatorChar);
        var actual = Path.GetFullPath(carpeta).TrimEnd(Path.DirectorySeparatorChar);
        while (actual.Length > tope.Length && actual.StartsWith(tope, StringComparison.OrdinalIgnoreCase) && Directory.Exists(actual)
               && !Directory.EnumerateFileSystemEntries(actual).Any())
        {
            try { Directory.Delete(actual); } catch (Exception error) when (error is IOException or UnauthorizedAccessException) { return; }
            actual = Path.GetDirectoryName(actual) ?? tope;
        }
    }

    public static void BorrarCarpeta(string carpeta)
    {
        for (var intento = 1; intento <= 3; intento++)
        {
            try
            {
                if (Directory.Exists(carpeta)) Directory.Delete(carpeta, recursive: true);
                return;
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
                Thread.Sleep(200 * intento);
            }
        }
    }

    public static long Ahora() => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
}

/// <summary>Python del runtime del nodo, con la configuracion de backend.env, como lo arranca el servicio (ProcesoBackend.Preparar).</summary>
internal static class Interprete
{
    public sealed record Salida(int Codigo, string Texto);

    public static Salida Ejecutar(Registro registro, IEnumerable<string> argumentos, TimeSpan limite)
    {
        var inicio = ProcesoBackend.Preparar(Rutas.PythonExe, argumentos);
        try
        {
            using var proceso = Process.Start(inicio);
            if (proceso is null) return new Salida(-1, "");
            ProcesoBackend.EntregarClave(proceso);
            var tareaErrores = proceso.StandardError.ReadToEndAsync();
            var tareaSalida = proceso.StandardOutput.ReadToEndAsync();
            if (!proceso.WaitForExit((int)Math.Max(1000, limite.TotalMilliseconds)))
            {
                try { proceso.Kill(entireProcessTree: true); } catch (Exception error) when (error is InvalidOperationException or System.ComponentModel.Win32Exception) { }
                registro.Escribir($"[python] Se agoto el tiempo ({limite.TotalSeconds:0} s): proceso terminado.");
                return new Salida(-2, "");
            }
            var texto = tareaSalida.GetAwaiter().GetResult();
            var errores = tareaErrores.GetAwaiter().GetResult();
            foreach (var linea in (texto + errores).Split('\n', StringSplitOptions.RemoveEmptyEntries))
                registro.Escribir($"[python] {linea.TrimEnd('\r')}");
            return new Salida(proceso.ExitCode, texto);
        }
        catch (Exception error)
        {
            registro.Escribir("No se pudo ejecutar el runtime de Python", error);
            return new Salida(-1, "");
        }
    }

    /// <summary>manage.py con los argumentos dados (check, migrate...), con el tiempo que quede del paso.</summary>
    public static Salida Manage(Registro registro, TimeSpan limite, params string[] argumentos) =>
        Ejecutar(registro, new[] { Rutas.ManagePy }.Concat(argumentos), limite);
}

/// <summary>
/// Fallos y cortes a proposito para los ENSAYOS del instalador (TST-061, A4): solo existen si el host corre como ensayo (AVACOM_OPS_ENSAYO=1 y una carpeta de estado de
/// pruebas), nunca en un nodo real. AVACOM_ACTUALIZACION_FALLO=paso[:porcentaje] hace fallar ese paso (a ese avance) y AVACOM_ACTUALIZACION_CORTE=paso[:porcentaje] mata el
/// proceso del host justo ahi, como un corte de energia. El backend no las hereda (todo AVACOM_* se descarta antes de lanzarlo).
/// </summary>
internal static class Inyeccion
{
    private static (string Paso, int Avance)? Leer(string variable)
    {
        if (!Rutas.EsEnsayo) return null;
        var valor = Environment.GetEnvironmentVariable(variable);
        if (string.IsNullOrWhiteSpace(valor)) return null;
        var partes = valor.Split(':', 2);
        var avance = partes.Length == 2 && int.TryParse(partes[1], out var p) ? p : 0;
        return (partes[0].Trim().ToLowerInvariant(), avance);
    }

    /// <summary>Lanza un fallo en <paramref name="paso"/> si el avance (0 a 100) alcanzo el configurado.</summary>
    public static void Fallar(string paso, int avance)
    {
        if (Leer("AVACOM_ACTUALIZACION_FALLO") is { } f && f.Paso == paso && avance >= f.Avance)
            throw new FalloDePaso(paso, $"Fallo inyectado en {paso} al {avance} %.");
    }

    public static void Cortar(string paso, int avance)
    {
        if (Leer("AVACOM_ACTUALIZACION_CORTE") is { } c && c.Paso == paso && avance >= c.Avance)
            Process.GetCurrentProcess().Kill();
    }
}

namespace Avacom.Ops.Host;

/// <summary>
/// Copia de seguridad, restauracion y vaciado de los datos del nodo.
///
/// "Los datos" son la base de datos (el archivo mas su -wal y su -shm, que son
/// una sola cosa para SQLite) y backend.env (las claves que cifran a las personas
/// guardadas en esa base). Se tratan siempre juntos: una base sin sus claves, o
/// unas claves sin su base, dejan a las personas ya guardadas sin poder
/// descifrarse ni buscarse.
///
/// Todo esto se ejecuta con el servicio detenido.
/// </summary>
internal static class Datos
{
    private const int RespaldosQueSeConservan = 5;

    private static string[] ArchivosDeBase =>
        [Rutas.BaseDeDatos, Rutas.BaseDeDatos + "-wal", Rutas.BaseDeDatos + "-shm"];

    private static string ArchivoUltimoRespaldo => Path.Combine(Rutas.CarpetaLogs, "respaldo-ultimo.txt");

    public static bool Hay() => File.Exists(Rutas.BaseDeDatos) || File.Exists(Rutas.ArchivoConfig);

    /// <summary>Carpeta del ultimo respaldo hecho por esta instalacion, o null.</summary>
    public static string? UltimoRespaldo()
    {
        try
        {
            if (!File.Exists(ArchivoUltimoRespaldo)) return null;
            var carpeta = File.ReadAllText(ArchivoUltimoRespaldo).Trim();
            return Directory.Exists(carpeta) ? carpeta : null;
        }
        catch (IOException)
        {
            return null;
        }
    }

    /// <summary>
    /// Copia base (+wal, +shm) y backend.env a Respaldos\version-fecha.
    /// Sin datos que copiar no hace nada. Devuelve la carpeta, o null si no habia nada.
    /// </summary>
    public static string? Respaldar(Registro registro, string version)
    {
        Rutas.AsegurarCarpetasDeEstado();
        try { File.Delete(ArchivoUltimoRespaldo); } catch (IOException) { }

        if (!Hay())
        {
            registro.Escribir("No hay datos previos que respaldar.");
            return null;
        }

        var limpia = string.Concat(version.Where(c => char.IsLetterOrDigit(c) || c is '.' or '-'));
        var carpeta = Path.Combine(Rutas.CarpetaRespaldos, $"{(limpia.Length > 0 ? limpia : "sin-version")}-{DateTime.Now:yyyyMMdd-HHmmss}");
        Directory.CreateDirectory(Path.Combine(carpeta, "Data"));
        Directory.CreateDirectory(Path.Combine(carpeta, "Config"));

        foreach (var archivo in ArchivosDeBase.Where(File.Exists))
        {
            File.Copy(archivo, Path.Combine(carpeta, "Data", Path.GetFileName(archivo)), overwrite: true);
        }
        if (File.Exists(Rutas.ArchivoConfig))
        {
            File.Copy(Rutas.ArchivoConfig, Path.Combine(carpeta, "Config", "backend.env"), overwrite: true);
        }

        File.WriteAllText(ArchivoUltimoRespaldo, carpeta);
        registro.Escribir($"Respaldo de los datos creado: {carpeta}");
        PodarViejos(registro);
        return carpeta;
    }

    /// <summary>Deja los datos como estaban en el ultimo respaldo (base, -wal, -shm y backend.env juntos).</summary>
    public static bool Restaurar(Registro registro)
    {
        var carpeta = UltimoRespaldo();
        if (carpeta is null)
        {
            registro.Escribir("No hay respaldo que restaurar.");
            return false;
        }

        Vaciar(registro, silencioso: true);
        foreach (var archivo in Directory.EnumerateFiles(Path.Combine(carpeta, "Data")))
        {
            File.Copy(archivo, Path.Combine(Rutas.CarpetaDatos, Path.GetFileName(archivo)), overwrite: true);
        }
        var env = Path.Combine(carpeta, "Config", "backend.env");
        if (File.Exists(env)) File.Copy(env, Rutas.ArchivoConfig, overwrite: true);

        registro.Escribir($"Datos restaurados desde {carpeta}.");
        return true;
    }

    /// <summary>Retira base (+wal, +shm) y backend.env. Quien llama ya dejo un respaldo.</summary>
    public static void Vaciar(Registro registro, bool silencioso = false)
    {
        foreach (var archivo in ArchivosDeBase.Append(Rutas.ArchivoConfig))
        {
            if (File.Exists(archivo)) File.Delete(archivo);
        }
        if (!silencioso) registro.Escribir("Base de datos y configuracion retiradas para empezar de cero.");
    }

    /// <summary>Solo la base (con -wal y -shm): la configuracion se conserva.</summary>
    public static void VaciarBase(Registro registro)
    {
        foreach (var archivo in ArchivosDeBase.Where(File.Exists)) File.Delete(archivo);
        registro.Escribir("Base de datos retirada; se creara una nueva.");
    }

    private static void PodarViejos(Registro registro)
    {
        try
        {
            var viejos = new DirectoryInfo(Rutas.CarpetaRespaldos).GetDirectories()
                .OrderByDescending(d => d.CreationTimeUtc)
                .Skip(RespaldosQueSeConservan);
            foreach (var carpeta in viejos)
            {
                carpeta.Delete(recursive: true);
                registro.Escribir($"Respaldo antiguo retirado: {carpeta.Name}");
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            registro.Escribir("No se pudieron podar los respaldos antiguos", error);
        }
    }
}

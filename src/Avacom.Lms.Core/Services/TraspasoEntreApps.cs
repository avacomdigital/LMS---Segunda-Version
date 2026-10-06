using System.Diagnostics;

namespace Avacom.Lms.Core.Services;

/// <summary>Las dos apps del producto: OPS (el profesorado, la administración y el técnico) y Student (el alumno).</summary>
public enum AppDelAcceso { Ops, Student }

/// <summary>Cómo terminó el intento de abrir la sesión en la otra app.</summary>
public enum ResultadoTraspaso
{
    /// <summary>La otra app se abrió con el código. La sesión de esta app ya no vale: el nodo la cierra al canjear.</summary>
    Abierta,
    /// <summary>No hay forma de abrir la otra app desde aquí (otro sistema, o no está instalada): no se pidió ningún código.</summary>
    SinApp,
    /// <summary>El nodo no dio el código (sin red, sesión de visita, contraseña provisional pendiente…).</summary>
    SinCodigo,
    /// <summary>Se obtuvo el código pero la otra app no arrancó.</summary>
    NoArranco,
}

/// <summary>El código que trajo la otra app al abrirse: <c>--traspaso=</c> y, opcional, <c>--servidor=</c>.</summary>
public sealed record TraspasoEntrante(string Codigo, string? Servidor);

/// <summary>
/// Un solo acceso para las dos apps. Quien entra por la app que tiene a mano se identifica con su documento y su clave; el nodo dice qué rol es.
/// Si ese rol pertenece a la otra app (un profesor en Student, un alumno en OPS), la app pide al nodo un código de traspaso (un solo uso, 60 s),
/// abre la otra app con ese código y se despide: la otra app lo canjea por una sesión nueva sin volver a pedir la clave. El código nunca es un pase:
/// sólo el nodo lo convierte en sesión, y al hacerlo cierra la de origen.
///
/// Sólo funciona en Windows, con las dos apps en el mismo equipo (OPS instalado en <c>Archivos de programa\AVACOM\OPS Master</c> o compilado
/// junto a Student, o la ruta en <c>AVACOM_OPS_EXE</c> / <c>AVACOM_STUDENT_EXE</c>). En una tableta Android no se puede abrir OPS: ahí se
/// le dice a la persona dónde entrar.
/// </summary>
public static class TraspasoEntreApps
{
    public const string ArgumentoCodigo = "--traspaso=";
    public const string ArgumentoServidor = "--servidor=";

    /// <summary>El alumno es de Student; todo lo demás (profesorado, administración, técnico, reportes) es de OPS.</summary>
    public static AppDelAcceso AppDe(UsuarioDeSesion usuario) =>
        string.Equals(usuario.Menu, "student", StringComparison.OrdinalIgnoreCase) ? AppDelAcceso.Student : AppDelAcceso.Ops;

    public static string NombreDe(AppDelAcceso app) => app == AppDelAcceso.Ops ? "AVACOM OPS" : "AVACOM Student";

    /// <summary>Lee el traspaso de los argumentos con que se abrió la app, o nulo si no vino ninguno.</summary>
    public static TraspasoEntrante? Leer(IEnumerable<string> argumentos)
    {
        string? codigo = null, servidor = null;
        foreach (var a in argumentos)
        {
            if (a.StartsWith(ArgumentoCodigo, StringComparison.Ordinal)) codigo = a[ArgumentoCodigo.Length..].Trim();
            else if (a.StartsWith(ArgumentoServidor, StringComparison.Ordinal)) servidor = a[ArgumentoServidor.Length..].Trim();
        }
        return string.IsNullOrEmpty(codigo) ? null : new TraspasoEntrante(codigo, string.IsNullOrEmpty(servidor) ? null : servidor);
    }

    private static int _tomado;

    /// <summary>El traspaso con que se abrió ESTA app, una sola vez: la primera pantalla que lo pide lo recibe; las siguientes, nada.</summary>
    public static TraspasoEntrante? TomarDeLaLinea()
    {
        if (Interlocked.Exchange(ref _tomado, 1) == 1) return null;
        try { return Leer(Environment.GetCommandLineArgs().Skip(1)); }
        catch { return null; }
    }

    /// <summary>
    /// Dónde está el ejecutable de la otra app: la variable de entorno, la instalación de OPS y, en desarrollo, la compilación más reciente de
    /// <c>src\Avacom.Lms.&lt;App&gt;\bin</c> subiendo desde la carpeta de esta app. Nulo fuera de Windows o si no se encuentra.
    /// </summary>
    public static string? BuscarEjecutable(AppDelAcceso app, Func<string, string?>? entorno = null, Func<string, bool>? existe = null,
                                           string? carpetaBase = null, Func<string, IEnumerable<string>>? compilaciones = null)
    {
        if (!OperatingSystem.IsWindows() && entorno is null) return null;
        entorno ??= Environment.GetEnvironmentVariable;
        existe ??= File.Exists;
        var nombre = app == AppDelAcceso.Ops ? "Avacom.Lms.Ops.exe" : "Avacom.Lms.Student.exe";
        var variable = entorno(app == AppDelAcceso.Ops ? "AVACOM_OPS_EXE" : "AVACOM_STUDENT_EXE");
        if (!string.IsNullOrWhiteSpace(variable)) return existe(variable) ? variable : null;

        if (app == AppDelAcceso.Ops)
        {
            var programas = entorno("ProgramFiles");
            if (!string.IsNullOrWhiteSpace(programas))
            {
                var instalado = Path.Combine(programas, "AVACOM", "OPS Master", "App", nombre);
                if (existe(instalado)) return instalado;
            }
        }

        var carpeta = carpetaBase ?? AppContext.BaseDirectory;
        compilaciones ??= bin => Directory.Exists(bin) ? Directory.EnumerateFiles(bin, nombre, SearchOption.AllDirectories) : [];
        for (var dir = carpeta.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar); !string.IsNullOrEmpty(dir); dir = Path.GetDirectoryName(dir) ?? string.Empty)
        {
            var bin = Path.Combine(dir, "..", $"Avacom.Lms.{(app == AppDelAcceso.Ops ? "Ops" : "Student")}", "bin");
            var candidatas = compilaciones(Path.GetFullPath(bin)).Where(existe).OrderByDescending(f => SafeFecha(f)).ToList();
            if (candidatas.Count > 0) return candidatas[0];
            if (Path.GetFileName(dir).Equals("src", StringComparison.OrdinalIgnoreCase)) break;
        }
        return null;

        static DateTime SafeFecha(string f) { try { return File.GetLastWriteTimeUtc(f); } catch { return DateTime.MinValue; } }
    }

    /// <summary>Abre la otra app con el código (y el servidor, para que hable con el mismo nodo). Falso si no arrancó.</summary>
    public static bool Lanzar(string ejecutable, string codigo, Uri servidor)
    {
        try
        {
            var inicio = new ProcessStartInfo(ejecutable) { UseShellExecute = false, WorkingDirectory = Path.GetDirectoryName(ejecutable) ?? string.Empty };
            inicio.ArgumentList.Add(ArgumentoCodigo + codigo);
            inicio.ArgumentList.Add(ArgumentoServidor + servidor.GetLeftPart(UriPartial.Authority));
            return Process.Start(inicio) is not null;
        }
        catch { return false; }
    }

    /// <summary>
    /// Pasa la sesión de esta app a <paramref name="destino"/>: busca la otra app ANTES de pedir el código (para no gastar una sesión en vano),
    /// pide el código y la abre. Con <see cref="ResultadoTraspaso.Abierta"/> la sesión de esta app ya no sirve; con cualquier otro la persona
    /// sigue identificada y quien llama decide si la cierra.
    /// </summary>
    public static async Task<ResultadoTraspaso> PasarAsync(IAccesoApi api, AppDelAcceso destino, Uri servidor,
                                                           Func<AppDelAcceso, string?>? buscar = null, Func<string, string, Uri, bool>? lanzar = null,
                                                           CancellationToken ct = default)
    {
        var ejecutable = (buscar ?? (a => BuscarEjecutable(a)))(destino);
        if (ejecutable is null) return ResultadoTraspaso.SinApp;
        var traspaso = await api.PedirTraspasoAsync(ct);
        if (traspaso is null) return ResultadoTraspaso.SinCodigo;
        return (lanzar ?? Lanzar)(ejecutable, traspaso.Codigo, servidor) ? ResultadoTraspaso.Abierta : ResultadoTraspaso.NoArranco;
    }

    /// <summary>Lo que se le dice a la persona cuando su rol es de la otra app y no se pudo abrir.</summary>
    public static string MensajeSinTraspaso(AppDelAcceso destino, ResultadoTraspaso resultado) => resultado switch
    {
        ResultadoTraspaso.Abierta => $"Abrimos {NombreDe(destino)} con tu sesión.",
        _ when destino == AppDelAcceso.Ops => "Tu cuenta es del profesorado. Entra en AVACOM OPS, en el equipo del profesor.",
        _ => "Tu cuenta es de alumno. Entra en AVACOM Student, en la tableta del alumno.",
    };
}

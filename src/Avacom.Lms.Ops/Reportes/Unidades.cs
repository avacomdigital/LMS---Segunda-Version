using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace Avacom.Lms.Ops.Reportes;

/// <summary>Qué clase de unidad es, según Windows (<see cref="DriveType"/> sin los nombres en inglés).</summary>
public enum TipoDeUnidad
{
    Desconocida,
    SinRaiz,
    /// <summary>Memoria USB, tarjeta SD: Windows las llama «removibles».</summary>
    Extraible,
    /// <summary>Un disco que Windows ve como fijo. OJO: un disco externo USB suele llegar así; <see cref="UnidadInfo.EsUsb"/> es lo que lo delata.</summary>
    Fija,
    Red,
    Optica,
    Ram,
}

/// <summary>
/// Lo que se sabe de una unidad en un instante. <see cref="Lista"/> es falso para un lector vacío, una unidad bloqueada o una que no contestó a tiempo: de ésas no se sabe
/// nada más (la etiqueta y los tamaños vienen vacíos). <see cref="TipoEfectivo"/> es lo que importa para ofrecerla como destino.
/// </summary>
public sealed record UnidadInfo(string Raiz, string Etiqueta, TipoDeUnidad Tipo, bool Lista, long LibreBytes, long TotalBytes, bool EsUsb)
{
    /// <summary>
    /// El tipo con el que se trata. Una unidad «fija» que en realidad cuelga de un puerto USB (un disco externo) se trata como extraíble: la persona la conectó y la va a
    /// retirar, y el administrador puede haber prohibido guardar en ellas.
    /// </summary>
    public TipoDeUnidad TipoEfectivo => Tipo == TipoDeUnidad.Fija && EsUsb ? TipoDeUnidad.Extraible : Tipo;

    /// <summary>«E:» (en mayúscula) si la raíz es una letra de unidad; si no, null.</summary>
    public string? Letra => Raiz is { Length: >= 2 } r && char.IsAsciiLetter(r[0]) && r[1] == ':' ? char.ToUpperInvariant(r[0]) + ":" : null;
}

/// <summary>De dónde sale la lista de unidades. Las pruebas ponen una falsa: un lector vacío, un disco USB «fijo» o una unidad de red se arman sin hardware.</summary>
public interface IProveedorDeUnidades
{
    IReadOnlyList<UnidadInfo> Unidades();
}

/// <summary>El nombre y el tipo de una unidad, lo único que se sabe de ella antes de preguntarle nada (preguntarle puede tardar).</summary>
internal readonly record struct RaizDeUnidad(string Raiz, TipoDeUnidad Tipo);

/// <summary>
/// Las unidades del equipo según Windows (<see cref="DriveInfo.GetDrives"/>). Tres cuidados, porque este es el código que toca unidades reales:
/// <list type="bullet">
/// <item>Cada unidad se lee aparte y dentro de su propio try/catch: una que lanza (un lector que se retira justo ahora, un volumen bloqueado) queda como «no lista» y no tumba la lista.</item>
/// <item>Preguntarle a una unidad puede TARDAR sin límite: una unidad de red mapeada cuyo servidor está apagado hace esperar a Windows decenas de segundos, y un disco externo
/// dormido tarda en despertar. Todas las unidades se leen EN PARALELO y se espera como mucho <see cref="PlazoPorOmision"/> en total; la que no contestó a tiempo sale como «no lista».</item>
/// <item>La lectura que se quedó colgada no se abandona ni se repite: se sigue esperando la MISMA en el sondeo siguiente (si no, cada sondeo apilaría otra hebra bloqueada),
/// y cuando por fin contesta, el sondeo que sigue ya la ve.</item>
/// </list>
/// Aun así llamarla puede costar hasta ese plazo: quien la llame desde la pantalla debe hacerlo fuera del hilo de la interfaz.
/// </summary>
public sealed class ProveedorDeUnidadesDelSistema : IProveedorDeUnidades
{
    /// <summary>Cuánto se espera, como mucho, a que contesten todas las unidades en cada llamada.</summary>
    public static readonly TimeSpan PlazoPorOmision = TimeSpan.FromSeconds(3);

    private readonly Func<IReadOnlyList<RaizDeUnidad>> _enumerar;
    private readonly Func<RaizDeUnidad, UnidadInfo> _leer;
    private readonly TimeSpan _plazo;
    private readonly object _candado = new();
    private readonly Dictionary<string, Task<UnidadInfo>> _lecturasEnCurso = new(StringComparer.OrdinalIgnoreCase);

    public ProveedorDeUnidadesDelSistema(TimeSpan? plazo = null) : this(EnumerarDelSistema, LeerDelSistema, plazo ?? PlazoPorOmision) { }

    /// <summary>La costura de las pruebas: cómo se enumeran las unidades y cómo se lee cada una (una que se cuelga, una que lanza).</summary>
    internal ProveedorDeUnidadesDelSistema(Func<IReadOnlyList<RaizDeUnidad>> enumerar, Func<RaizDeUnidad, UnidadInfo> leer, TimeSpan plazo)
    {
        _enumerar = enumerar ?? throw new ArgumentNullException(nameof(enumerar));
        _leer = leer ?? throw new ArgumentNullException(nameof(leer));
        _plazo = plazo;
    }

    public IReadOnlyList<UnidadInfo> Unidades()
    {
        IReadOnlyList<RaizDeUnidad> raices;
        try { raices = _enumerar(); }
        catch { return []; }

        var lecturas = raices.Select(raiz => (Raiz: raiz, Tarea: LecturaDe(raiz))).ToList();
        try { Task.WaitAll(lecturas.Select(l => (Task)l.Tarea).ToArray(), _plazo); }
        catch { /* ninguna lectura lanza (se atrapan en LecturaDe): por si acaso, se mira una por una */ }

        return lecturas
            .Select(l => l.Tarea.IsCompletedSuccessfully ? l.Tarea.Result : NoLista(l.Raiz))
            .ToList();
    }

    /// <summary>La lectura de esa unidad que ya está en marcha o, si no hay ninguna, una nueva en el grupo de hebras.</summary>
    private Task<UnidadInfo> LecturaDe(RaizDeUnidad raiz)
    {
        lock (_candado)
        {
            if (_lecturasEnCurso.TryGetValue(raiz.Raiz, out var enCurso)) return enCurso;

            // La tarea se registra ANTES de que arranque el trabajo: si éste termina enseguida, su propio «se acabó» siempre encuentra qué quitar.
            var origen = new TaskCompletionSource<UnidadInfo>(TaskCreationOptions.RunContinuationsAsynchronously);
            _lecturasEnCurso[raiz.Raiz] = origen.Task;
            _ = Task.Run(() =>
            {
                UnidadInfo info;
                try { info = _leer(raiz); }
                catch { info = NoLista(raiz); }
                lock (_candado) _lecturasEnCurso.Remove(raiz.Raiz);
                origen.SetResult(info);
            });
            return origen.Task;
        }
    }

    private static UnidadInfo NoLista(RaizDeUnidad raiz) => new(raiz.Raiz, string.Empty, raiz.Tipo, false, 0, 0, false);

    // ------------------------------------------------------------------ lo que dice Windows

    private static IReadOnlyList<RaizDeUnidad> EnumerarDelSistema()
    {
        var raices = new List<RaizDeUnidad>();
        foreach (var unidad in DriveInfo.GetDrives())
        {
            try { raices.Add(new RaizDeUnidad(unidad.Name, Convertir(unidad.DriveType))); }
            catch { /* una unidad que lanza al preguntarle su tipo no entra, y las demás sí */ }
        }
        return raices;
    }

    private static TipoDeUnidad Convertir(DriveType tipo) => tipo switch
    {
        DriveType.NoRootDirectory => TipoDeUnidad.SinRaiz,
        DriveType.Removable => TipoDeUnidad.Extraible,
        DriveType.Fixed => TipoDeUnidad.Fija,
        DriveType.Network => TipoDeUnidad.Red,
        DriveType.CDRom => TipoDeUnidad.Optica,
        DriveType.Ram => TipoDeUnidad.Ram,
        _ => TipoDeUnidad.Desconocida,
    };

    private static UnidadInfo LeerDelSistema(RaizDeUnidad raiz)
    {
        var lista = false;
        var etiqueta = string.Empty;
        long libre = 0, total = 0;
        try
        {
            var unidad = new DriveInfo(raiz.Raiz);
            lista = unidad.IsReady;
            if (lista)
            {
                // cada dato por separado: si la memoria se retira entre una pregunta y otra, lo que ya se supo no se pierde
                try { etiqueta = unidad.VolumeLabel ?? string.Empty; } catch { }
                try { libre = unidad.AvailableFreeSpace; } catch { }
                try { total = unidad.TotalSize; } catch { }
            }
        }
        catch { lista = false; }

        // sólo vale la pena preguntar por el bus de lo que está listo y es un disco (los lectores ópticos, las redes y los discos RAM no cuelgan de USB)
        var esUsb = lista && (raiz.Tipo is TipoDeUnidad.Fija or TipoDeUnidad.Extraible) && DetectorDeUsb.EsUsb(raiz.Raiz);
        return new UnidadInfo(raiz.Raiz, etiqueta, raiz.Tipo, lista, libre, total, esUsb);
    }
}

/// <summary>
/// ¿La unidad cuelga de un puerto USB? Windows reporta casi todos los discos externos como «fijos», así que el tipo de unidad no basta. Se le pregunta al controlador del volumen
/// por su tipo de bus (<c>IOCTL_STORAGE_QUERY_PROPERTY</c> con <c>StorageDeviceProperty</c>) y el valor 7 es <c>BusTypeUsb</c>. Se abre el volumen SIN pedir ningún acceso (basta para
/// consultar propiedades y no exige ser administrador). Cualquier fallo —no es Windows, no es una letra de unidad, el volumen no deja abrirse, el controlador no contesta— es «no».
/// </summary>
internal static class DetectorDeUsb
{
    private const uint IoctlStorageQueryProperty = 0x002D1400;
    private const int PosicionDelTipoDeBus = 28;        // STORAGE_DEVICE_DESCRIPTOR: versión 4, tamaño 4, cuatro banderas de 1 byte, cuatro desplazamientos de texto de 4 → «BusType» empieza en el byte 28
    private const int TipoDeBusUsb = 7;                 // STORAGE_BUS_TYPE.BusTypeUsb
    private const uint CompartirLecturaYEscritura = 3;
    private const uint AbrirExistente = 3;

    public static bool EsUsb(string raiz)
    {
        if (!OperatingSystem.IsWindows()) return false;
        try
        {
            if (raiz is not { Length: >= 2 } || !char.IsAsciiLetter(raiz[0]) || raiz[1] != ':') return false;

            using var volumen = CreateFileW(@"\\.\" + char.ToUpperInvariant(raiz[0]) + ":", 0, CompartirLecturaYEscritura, IntPtr.Zero, AbrirExistente, 0, IntPtr.Zero);
            if (volumen.IsInvalid) return false;

            // STORAGE_PROPERTY_QUERY con PropertyId = StorageDeviceProperty (0) y QueryType = PropertyStandardQuery (0): doce bytes en cero
            var consulta = new byte[12];
            var respuesta = new byte[1024];
            if (!DeviceIoControl(volumen, IoctlStorageQueryProperty, consulta, consulta.Length, respuesta, respuesta.Length, out var devueltos, IntPtr.Zero)) return false;
            return devueltos >= PosicionDelTipoDeBus + sizeof(int) && BitConverter.ToInt32(respuesta, PosicionDelTipoDeBus) == TipoDeBusUsb;
        }
        catch
        {
            return false;
        }
    }

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern SafeFileHandle CreateFileW(string nombre, uint acceso, uint compartir, IntPtr seguridad, uint disposicion, uint banderas, IntPtr plantilla);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DeviceIoControl(SafeFileHandle dispositivo, uint codigo, byte[] entrada, int tamanoDeEntrada, byte[] salida, int tamanoDeSalida, out int devueltos, IntPtr superpuesto);
}

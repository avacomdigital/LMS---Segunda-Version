using System.Security.Cryptography;
using System.Text;

namespace Avacom.Lms.Ops.Reportes;

/// <summary>
/// Dónde se guardan las preferencias pequeñas del equipo (clave, valor de texto). En la aplicación es <c>Preferences</c> de MAUI; aquí es una interfaz para que esta lógica se
/// pruebe sin MAUI. Nada de esto es secreto: sólo la última carpeta elegida.
/// </summary>
public interface IAlmacenDePreferencias
{
    string? Leer(string clave);
    void Guardar(string clave, string valor);
}

/// <summary>
/// La última carpeta donde cada persona guardó un reporte, para ofrecerla primero la próxima vez: nadie tiene que volver a navegar hasta «Reportes de 8A» en una pantalla táctil.
/// Se recuerda POR USUARIO (varias personas comparten el equipo del aula) y la clave no lleva el identificador en claro: es el prefijo más los 16 primeros dígitos hexadecimales del
/// SHA-256 del identificador. Si la carpeta recordada ya no existe (se retiró la memoria, se borró) no se ofrece. Nunca lanza: una preferencia que no se puede leer o guardar no
/// debe impedir exportar.
/// </summary>
public sealed class PreferenciasDeDestino
{
    /// <summary>Lo que antecede, en la clave, al resumen del identificador de usuario.</summary>
    public const string PrefijoDeClave = "reportes.ultima_carpeta.";

    private readonly IAlmacenDePreferencias _almacen;
    private readonly TimeSpan _plazoParaExistir;
    private readonly Func<string, bool> _existe;

    /// <param name="almacen">Dónde se guarda.</param>
    /// <param name="plazoParaExistir">Cuánto se espera a saber si la carpeta recordada existe (una de red cuyo servidor está apagado haría esperar decenas de segundos): pasado el plazo se toma por «no está».</param>
    public PreferenciasDeDestino(IAlmacenDePreferencias almacen, TimeSpan? plazoParaExistir = null)
        : this(almacen, plazoParaExistir ?? TimeSpan.FromSeconds(2), Directory.Exists) { }

    /// <summary>La costura de las pruebas: cómo se comprueba que una carpeta existe.</summary>
    internal PreferenciasDeDestino(IAlmacenDePreferencias almacen, TimeSpan plazoParaExistir, Func<string, bool> existe)
    {
        _almacen = almacen ?? throw new ArgumentNullException(nameof(almacen));
        _plazoParaExistir = plazoParaExistir;
        _existe = existe ?? throw new ArgumentNullException(nameof(existe));
    }

    /// <summary>La clave con la que se guarda la carpeta de ese usuario. Un identificador nulo se trata como vacío (el equipo sin sesión).</summary>
    public static string Clave(string? usuarioId)
    {
        var resumen = SHA256.HashData(Encoding.UTF8.GetBytes(usuarioId ?? string.Empty));
        return PrefijoDeClave + Convert.ToHexStringLower(resumen)[..16];
    }

    /// <summary>La última carpeta que eligió esa persona, o null si no eligió ninguna o la carpeta ya no existe.</summary>
    public string? UltimaCarpeta(string usuarioId)
    {
        try
        {
            var ruta = _almacen.Leer(Clave(usuarioId));
            if (string.IsNullOrWhiteSpace(ruta)) return null;
            return Existencia.DeCarpeta(ruta, _plazoParaExistir, _existe) ? ruta : null;
        }
        catch
        {
            return null;
        }
    }

    /// <summary>Anota la carpeta donde esa persona acaba de guardar un reporte. Una ruta vacía no se anota.</summary>
    public void RecordarCarpeta(string usuarioId, string ruta)
    {
        if (string.IsNullOrWhiteSpace(ruta)) return;
        try { _almacen.Guardar(Clave(usuarioId), ruta); }
        catch { /* no poder recordar la carpeta no es motivo para fallar */ }
    }
}

using System.Security.Cryptography;
using System.Text.Json;
using Avacom.Lms.Core.Estudio;

namespace Avacom.Lms.Core.Evaluacion;

/// <summary>Cómo se guarda un PIN: nunca el PIN. PBKDF2-HMAC-SHA256 con una sal propia de ESTE equipo y las iteraciones con que se derivó.</summary>
public sealed record RegistroDePin(string Sal, int Iteraciones, string Hash);

/// <summary>El resultado de comprobar un PIN: acertó, falló o está frenado por demasiados fallos seguidos.</summary>
public enum ResultadoDePin { Correcto, Incorrecto, Frenado, SinPin }

/// <summary>
/// La salida administrativa del kiosco (kiosk.md §5.3): una vía para sacar a un alumno de un examen colgado que no depende del servidor ni de Internet.
/// <b>No copia el almacenamiento del prototipo</b> (SHA-256 sin sal sobre seis dígitos, con un PIN por omisión escrito en el código): aquí el PIN se guarda
/// con PBKDF2, sal por equipo y un número de iteraciones que viaja con el registro; el PIN lo fija quien aprovisiona cada tableta y es DISTINTO por equipo.
///
/// Un PIN corto se recorre entero en segundos aunque esté bien derivado, así que además hay un freno: cinco fallos seguidos bloquean los intentos un
/// minuto y cada nuevo bloqueo duplica la espera (hasta una hora). Sin PIN fijado no hay salida local: la vía es entonces la del profesor
/// (<c>cierre forzado</c> en el nodo, y la tableta se suelta sola al ver el intento entregado).
/// </summary>
public sealed class AlmacenDePin
{
    public const int Iteraciones = 210_000;
    public const int LongitudSal = 16;
    public const int LongitudHash = 32;
    public const int LongitudMinima = 6;
    public const int FallosAntesDelFreno = 5;
    public static readonly TimeSpan FrenoInicial = TimeSpan.FromMinutes(1);
    public static readonly TimeSpan FrenoMaximo = TimeSpan.FromHours(1);

    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    private readonly string ruta;
    private readonly int iteraciones;
    private readonly Func<DateTimeOffset> reloj;
    private readonly object candado = new();
    private RegistroDePin? registro;
    private int fallosSeguidos;
    private int bloqueos;
    private DateTimeOffset? frenadoHasta;

    /// <param name="ruta">Archivo donde queda el registro (sal, iteraciones, hash). Nunca el PIN.</param>
    /// <param name="iteraciones">Sólo las pruebas lo bajan; en producción son <see cref="Iteraciones"/>.</param>
    /// <param name="reloj">Sólo para las pruebas del freno.</param>
    public AlmacenDePin(string ruta, int iteraciones = Iteraciones, Func<DateTimeOffset>? reloj = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(ruta);
        this.ruta = Path.GetFullPath(ruta);
        this.iteraciones = iteraciones;
        this.reloj = reloj ?? (() => DateTimeOffset.UtcNow);
        registro = Leer();
    }

    public bool Existe => registro is not null;

    /// <summary>Cuánto falta para poder volver a intentar, si el freno está puesto.</summary>
    public TimeSpan? EsperaRestante
    {
        get
        {
            lock (candado)
                return frenadoHasta is { } hasta && hasta > reloj() ? hasta - reloj() : null;
        }
    }

    /// <summary>
    /// Fija el PIN de este equipo. Con uno ya fijado exige el actual; sin PIN lo puede fijar quien aprovisiona. Devuelve false (y no cambia nada) si el PIN nuevo
    /// no cumple (≥ 6 dígitos, no todos iguales, ni una escalera) o el actual no coincide.
    /// </summary>
    public bool Establecer(string pinNuevo, string? pinActual = null)
    {
        if (!EsAceptable(pinNuevo)) return false;
        lock (candado)
        {
            if (registro is not null && Comprobar(pinActual ?? "", registro) != ResultadoDePin.Correcto) return false;
            registro = Crear(pinNuevo, iteraciones);
            Guardar(registro);
            fallosSeguidos = 0;
            return true;
        }
    }

    /// <summary>Comprueba un PIN con el freno puesto. Un acierto reinicia los fallos.</summary>
    public ResultadoDePin Verificar(string pin)
    {
        lock (candado)
        {
            if (registro is null) return ResultadoDePin.SinPin;
            if (frenadoHasta is { } hasta && hasta > reloj()) return ResultadoDePin.Frenado;
            var resultado = Comprobar(pin, registro);
            if (resultado == ResultadoDePin.Correcto)
            {
                fallosSeguidos = 0;
                bloqueos = 0;
                frenadoHasta = null;
                return resultado;
            }
            if (++fallosSeguidos >= FallosAntesDelFreno)
            {
                var espera = TimeSpan.FromTicks(Math.Min(FrenoMaximo.Ticks, FrenoInicial.Ticks << Math.Min(bloqueos, 10)));
                frenadoHasta = reloj() + espera;
                bloqueos++;
                fallosSeguidos = 0;
            }
            return ResultadoDePin.Incorrecto;
        }
    }

    // ------------------------------------------------------------------------------------ la derivación

    /// <summary>Deriva el registro de un PIN con una sal nueva. Pública para poder comprobar el formato.</summary>
    public static RegistroDePin Crear(string pin, int iteraciones = Iteraciones)
    {
        var sal = RandomNumberGenerator.GetBytes(LongitudSal);
        return new RegistroDePin(Convert.ToBase64String(sal), iteraciones, Convert.ToBase64String(Derivar(pin, sal, iteraciones)));
    }

    /// <summary>Compara en tiempo constante.</summary>
    public static ResultadoDePin Comprobar(string pin, RegistroDePin registro)
    {
        try
        {
            var esperado = Convert.FromBase64String(registro.Hash);
            var obtenido = Derivar(pin, Convert.FromBase64String(registro.Sal), registro.Iteraciones);
            return CryptographicOperations.FixedTimeEquals(esperado, obtenido) ? ResultadoDePin.Correcto : ResultadoDePin.Incorrecto;
        }
        catch (FormatException)
        {
            return ResultadoDePin.Incorrecto;
        }
    }

    private static byte[] Derivar(string pin, byte[] sal, int iteraciones) =>
        Rfc2898DeriveBytes.Pbkdf2(System.Text.Encoding.UTF8.GetBytes(pin), sal, iteraciones, HashAlgorithmName.SHA256, LongitudHash);

    /// <summary>Un PIN de al menos seis dígitos que no sea una repetición (111111) ni una escalera (123456, 654321).</summary>
    public static bool EsAceptable(string? pin)
    {
        if (string.IsNullOrEmpty(pin) || pin.Length < LongitudMinima || !pin.All(char.IsAsciiDigit)) return false;
        if (pin.All(c => c == pin[0])) return false;
        var paso = pin[1] - pin[0];
        if (paso is 1 or -1)
        {
            var escalera = true;
            for (var i = 1; i < pin.Length && escalera; i++) escalera = pin[i] - pin[i - 1] == paso;
            if (escalera) return false;
        }
        return true;
    }

    // --------------------------------------------------------------------------------- el archivo

    private RegistroDePin? Leer()
    {
        try
        {
            if (!File.Exists(ruta)) return null;
            var leido = JsonSerializer.Deserialize<RegistroDePin>(File.ReadAllText(ruta), Json);
            return leido is { Iteraciones: > 0 } && !string.IsNullOrEmpty(leido.Sal) && !string.IsNullOrEmpty(leido.Hash) ? leido : null;
        }
        catch (Exception ex) when (ex is JsonException or IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    private void Guardar(RegistroDePin nuevo) => ArchivosLocales.EscribirAtomico(ruta, JsonSerializer.SerializeToUtf8Bytes(nuevo, Json));
}

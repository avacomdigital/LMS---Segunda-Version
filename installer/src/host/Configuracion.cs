using System.Security.Cryptography;
using System.Text;

namespace Avacom.Ops.Host;

/// <summary>
/// La configuracion local del nodo: un archivo de variables de entorno que el
/// instalador genera en la primera instalacion y que el servicio le pasa al
/// backend.
///
/// Por que variables de entorno y no un settings.py editado: el backend YA lee
/// su configuracion de os.environ (AVACOM_LMS_SECRET, AVACOM_LMS_DB,
/// AVACOM_LMS_CLAVE_DATOS, ...). Configurarlo asi es usar el mecanismo que el
/// producto ya tiene, sin tocar una sola linea de su codigo.
///
/// backend.env tiene el mismo estatus que la base de datos: las tres claves de
/// acceso cifran y buscan a las personas guardadas en ella. Se conservan o se
/// reemplazan juntos, y nunca se agregan claves nuevas en silencio a una base
/// que ya tiene datos de acceso.
/// </summary>
internal static class Configuracion
{
    public const string HostPorDefecto = "0.0.0.0";
    public const int PuertoPorDefecto = 8000;

    private static readonly string[] ClavesDeAcceso =
        ["AVACOM_LMS_CLAVE_DATOS", "AVACOM_LMS_CLAVE_INDICE", "AVACOM_LMS_CLAVE_TOKENS"];

    public static Dictionary<string, string> Leer()
    {
        var valores = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (!File.Exists(Rutas.ArchivoConfig)) return valores;

        foreach (var linea in File.ReadAllLines(Rutas.ArchivoConfig))
        {
            var texto = linea.Trim();
            if (texto.Length == 0 || texto.StartsWith('#')) continue;

            var corte = texto.IndexOf('=');
            if (corte <= 0) continue;

            var clave = texto[..corte].Trim();
            var valor = texto[(corte + 1)..].Trim();
            if (clave.Length > 0) valores[clave] = valor;
        }
        return valores;
    }

    public static int PuertoConfigurado()
    {
        var valores = Leer();
        return valores.TryGetValue("AVACOM_OPS_BACKEND_PORT", out var texto)
            && int.TryParse(texto, out var puerto)
            && puerto is > 0 and < 65536
                ? puerto
                : PuertoPorDefecto;
    }

    /// <summary>
    /// Genera la configuracion si no existe. Es idempotente a proposito: una
    /// reinstalacion o una actualizacion no debe cambiar las claves ni mover la
    /// base de datos de un nodo que ya tiene expediente cargado.
    /// </summary>
    /// <returns>true si el archivo se creo en esta llamada.</returns>
    public static bool CrearSiFalta(Registro registro)
    {
        Rutas.AsegurarCarpetasDeEstado();

        if (File.Exists(Rutas.ArchivoConfig))
        {
            registro.Escribir($"La configuracion ya existia, se conserva: {Rutas.ArchivoConfig}");
            return false;
        }

        var contenido = new StringBuilder();
        contenido.AppendLine("# Configuracion local de AVACOM OPS Master (backend).");
        contenido.AppendLine("# Generada por el instalador. Una reinstalacion NO la sobrescribe.");
        contenido.AppendLine("#");
        contenido.AppendLine("# Formato: CLAVE=valor, una por linea. El servicio AVACOMOPSBackend");
        contenido.AppendLine("# las entrega al backend como variables de entorno.");
        contenido.AppendLine("#");
        contenido.AppendLine("# ATENCION: este archivo tiene el mismo estatus que la base de datos.");
        contenido.AppendLine("# Las tres claves de acceso cifran y buscan a las personas guardadas en");
        contenido.AppendLine("# ella. Si cambian mientras la base se conserva, esas personas dejan de");
        contenido.AppendLine("# poder descifrarse. Se conservan o se reemplazan juntos: base y claves.");
        contenido.AppendLine();
        contenido.AppendLine("# Clave de firma de este nodo. Unica por instalacion.");
        contenido.AppendLine($"AVACOM_LMS_SECRET={ClaveNueva()}");
        contenido.AppendLine();
        AgregarClavesDeAcceso(contenido, ClavesDeAcceso);
        contenido.AppendLine("# 0 en una instalacion distribuida: sin trazas de error hacia la LAN del aula.");
        contenido.AppendLine("# Ponlo en 1 solo para diagnosticar, y reinicia el servicio AVACOMOPSBackend.");
        contenido.AppendLine("AVACOM_LMS_DEBUG=0");
        contenido.AppendLine();
        contenido.AppendLine("# La base de datos del nodo (organizacion, personas, dispositivos, clases,");
        contenido.AppendLine("# expediente). Vive fuera de Program Files y, segun la politica de datos de");
        contenido.AppendLine("# cada version, sobrevive a las actualizaciones.");
        contenido.AppendLine($"AVACOM_LMS_DB={Rutas.BaseDeDatos}");
        contenido.AppendLine();
        contenido.AppendLine("# Escucha de la API local (HTTP y WebSocket, un solo puerto). Las tabletas");
        contenido.AppendLine("# llegan por la IP del equipo maestro.");
        contenido.AppendLine($"AVACOM_OPS_BACKEND_HOST={HostPorDefecto}");
        contenido.AppendLine($"AVACOM_OPS_BACKEND_PORT={PuertoPorDefecto}");
        contenido.AppendLine();
        contenido.AppendLine("# Tiempo de espera hacia AVACOM Contenido, en segundos.");
        contenido.AppendLine("AVACOM_CONTENIDO_TIEMPO_ESPERA_SEG=3");
        contenido.AppendLine();
        contenido.AppendLine("# Los cursos salen SIEMPRE de AVACOM Contenido (la biblioteca). El curso de ejemplo");
        contenido.AppendLine("# del repositorio es solo para pruebas: aqui esta apagado y no viaja en el instalador.");
        contenido.AppendLine("AVACOM_AULA_FUENTE_CURSOS=biblioteca");
        contenido.AppendLine("AVACOM_AULA_PERMITIR_EJEMPLO=0");
        contenido.AppendLine();
        contenido.AppendLine("# AVACOM_CONTENIDO_ENLACE y AVACOM_CONTENIDO_ENLACE_V2 se dejan SIN definir");
        contenido.AppendLine("# a proposito: el backend busca la nota de enlace de AVACOM Contenido donde");
        contenido.AppendLine(@"# esta la publica (%ProgramData%\AVACOM\content\link.json). Definirlas aqui");
        contenido.AppendLine("# solo sirve para pruebas con el host de pruebas del repositorio.");

        File.WriteAllText(Rutas.ArchivoConfig, contenido.ToString(), new UTF8Encoding(false));
        registro.Escribir($"Configuracion creada: {Rutas.ArchivoConfig}");
        return true;
    }

    /// <summary>
    /// Una configuracion que ya existe puede venir de la version 2.0.0, que solo
    /// tenia AVACOM_LMS_SECRET (el backend derivaba de ella las tres claves de
    /// acceso). Completarla es seguro unicamente si la base todavia no guarda
    /// personas: con personas guardadas, agregar claves nuevas las dejaria
    /// ilegibles.
    /// </summary>
    /// <param name="hayPersonasGuardadas">null si no se pudo saber; se trata como "si hay".</param>
    /// <returns>Un aviso si las claves se dejaron como estaban, o null.</returns>
    public static string? CompletarClavesDeAcceso(Registro registro, bool? hayPersonasGuardadas)
    {
        var actuales = Leer();
        var faltantes = ClavesDeAcceso.Where(c => !actuales.TryGetValue(c, out var v) || v.Length == 0).ToArray();
        if (faltantes.Length == 0) return null;

        if (hayPersonasGuardadas != false)
        {
            registro.Escribir(
                "La base ya guarda personas y la configuracion no tiene las claves de acceso propias: " +
                "no se agregan claves nuevas en silencio; el backend sigue derivandolas de AVACOM_LMS_SECRET.");
            return "Este nodo sigue usando las claves derivadas de la version anterior. Se conservan tal cual " +
                   "porque ya hay personas guardadas; no se pueden cambiar sin perderlas.";
        }

        var texto = new StringBuilder();
        texto.AppendLine();
        texto.AppendLine("# Claves de acceso agregadas por una actualizacion, cuando la base aun no");
        texto.AppendLine("# guardaba personas. Ver la advertencia del principio de este archivo.");
        AgregarClavesDeAcceso(texto, faltantes);
        File.AppendAllText(Rutas.ArchivoConfig, texto.ToString(), new UTF8Encoding(false));
        registro.Escribir($"Claves de acceso agregadas a la configuracion ({faltantes.Length}): la base no tenia personas.");
        return null;
    }

    private static void AgregarClavesDeAcceso(StringBuilder salida, IEnumerable<string> claves)
    {
        foreach (var clave in claves)
        {
            switch (clave)
            {
                case "AVACOM_LMS_CLAVE_DATOS":
                    salida.AppendLine("# Cifra los datos personales (AES-256-GCM).");
                    break;
                case "AVACOM_LMS_CLAVE_INDICE":
                    salida.AppendLine("# Indice ciego (HMAC-SHA-256) para buscar por documento, codigo o correo.");
                    break;
                default:
                    salida.AppendLine("# Firma de las sesiones (JWT).");
                    break;
            }
            salida.AppendLine($"{clave}={Convert.ToBase64String(RandomNumberGenerator.GetBytes(32))}");
            salida.AppendLine();
        }
    }

    private static string ClaveNueva()
    {
        const string alfabeto = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@%^&*(-_=+)";
        var salida = new StringBuilder(64);
        for (var i = 0; i < 64; i++)
        {
            salida.Append(alfabeto[RandomNumberGenerator.GetInt32(alfabeto.Length)]);
        }
        return salida.ToString();
    }
}

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
///
/// Los textos de este archivo van SIN acentos a proposito: varios los lee el
/// asistente de Inno Setup como texto ANSI y un acento en UTF-8 saldria roto.
/// </summary>
internal static class Configuracion
{
    public const string HostPorDefecto = "0.0.0.0";
    public const int PuertoPorDefecto = 8000;

    private static readonly string[] ClavesDeAcceso =
        ["AVACOM_LMS_CLAVE_DATOS", "AVACOM_LMS_CLAVE_INDICE", "AVACOM_LMS_CLAVE_TOKENS"];

    /// <summary>
    /// Las notas de enlace de AVACOM Contenido solo se fuerzan para pruebas con el
    /// host de pruebas del repositorio. En un nodo real se dejan SIN definir: el
    /// backend busca la nota donde la biblioteca la publica
    /// (%ProgramData%\AVACOM\content\link.json). Una que apunte a otro sitio deja
    /// al aula sin cursos aunque la biblioteca este abierta.
    /// </summary>
    private static readonly string[] EnlacesDePrueba = ["AVACOM_CONTENIDO_ENLACE", "AVACOM_CONTENIDO_ENLACE_V2"];

    /// <summary>
    /// Todo lo que el nodo instalado no puede heredar de Windows: ni de variables
    /// del usuario ni del equipo. El backend se configura SOLO con backend.env, de
    /// modo que una variable olvidada por un tecnico o por un desarrollador (otra
    /// base de datos, el curso de ejemplo encendido, una nota de enlace de pruebas)
    /// no cambia lo que hace el aula.
    /// </summary>
    public static bool EsDeAvacom(string nombre) =>
        nombre.StartsWith("AVACOM_", StringComparison.OrdinalIgnoreCase);

    /// <summary>
    /// Un ajuste de la configuracion del nodo.
    /// <paramref name="Forzar"/>: si el archivo trae otro valor, se corrige. Se fuerza solo
    /// lo que el producto exige para funcionar; el resto se respeta si ya estaba.
    /// </summary>
    private sealed record Ajuste(string Clave, string Valor, bool Forzar, string Comentario);

    private static Ajuste[] Ajustes() =>
    [
        new("AVACOM_LMS_DEBUG", "0", false,
            "0 en una instalacion distribuida: sin trazas de error hacia la LAN del aula.\n" +
            "Ponlo en 1 solo para diagnosticar, y reinicia el servicio AVACOMOPSBackend."),

        new("AVACOM_LMS_ENTORNO", "instalado", true,
            "Entorno de ejecucion. Instalado: los registros y la bitacora van a ProgramData,\n" +
            "nunca a la carpeta del programa."),

        new("AVACOM_LMS_DB", Rutas.BaseDeDatos, true,
            "La base de datos del nodo (organizacion, personas, dispositivos, clases,\n" +
            "expediente). Vive fuera de Program Files y, segun la politica de datos de\n" +
            "cada version, sobrevive a las actualizaciones. Las copias de seguridad miran\n" +
            "esta ruta: no la cambies."),

        new("AVACOM_LMS_DIR_LOGS", Rutas.CarpetaLogs, false,
            "Carpeta de los registros del nodo (JSON Lines) y de los archivos de la bitacora.\n" +
            "Es la misma que usan el instalador y el diagnostico."),

        new("AVACOM_OPS_BACKEND_HOST", HostPorDefecto, !Rutas.EsEnsayo,
            "Escucha de la API local (HTTP y WebSocket, un solo puerto). Las tabletas llegan\n" +
            "por la IP del equipo maestro: debe ser 0.0.0.0:8000."),
        new("AVACOM_OPS_BACKEND_PORT", PuertoPorDefecto.ToString(), !Rutas.EsEnsayo, ""),

        new("AVACOM_CONTENIDO_TIEMPO_ESPERA_SEG", "3", false,
            "Tiempo de espera hacia AVACOM Contenido, en segundos."),

        new("AVACOM_AULA_FUENTE_CURSOS", "biblioteca", true,
            "Los cursos salen SIEMPRE de AVACOM Contenido (la biblioteca). El curso de ejemplo\n" +
            "del repositorio es solo para pruebas: aqui esta apagado y no viaja en el instalador."),
        new("AVACOM_AULA_PERMITIR_EJEMPLO", "0", true, ""),
    ];

    /// <summary>
    /// Lee backend.env. Si no se puede leer devuelve lo que haya (nada): quien necesite
    /// saber SI se pudo leer pregunta antes a <see cref="EsUtilizable"/>.
    /// </summary>
    public static Dictionary<string, string> Leer()
    {
        var valores = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (!File.Exists(Rutas.ArchivoConfig)) return valores;

        string[] lineas;
        try
        {
            lineas = File.ReadAllLines(Rutas.ArchivoConfig);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            return valores;
        }

        foreach (var linea in lineas)
        {
            if (TryPartir(linea, out var clave, out var valor)) valores[clave] = valor;
        }
        return valores;
    }

    private static bool TryPartir(string linea, out string clave, out string valor)
    {
        clave = valor = "";
        var texto = linea.Trim();
        if (texto.Length == 0 || texto.StartsWith('#')) return false;

        var corte = texto.IndexOf('=');
        if (corte <= 0) return false;

        clave = texto[..corte].Trim();
        valor = texto[(corte + 1)..].Trim();
        return clave.Length > 0;
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
    /// ¿Hay configuracion suficiente para arrancar el backend sin riesgo? Sin ella el
    /// backend arrancaria con los valores de desarrollo: la clave de prototipo y una base
    /// de datos NUEVA dentro de Program Files, y el aula seguiria funcionando sobre un
    /// expediente vacio sin que nadie lo notara. Es preferible no arrancar y decir por que.
    /// </summary>
    public static bool EsUtilizable(out string motivo)
    {
        motivo = "";
        if (!File.Exists(Rutas.ArchivoConfig))
        {
            motivo = "no existe backend.env";
            return false;
        }

        try
        {
            _ = File.ReadAllLines(Rutas.ArchivoConfig);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            motivo = $"no se puede leer backend.env ({error.GetType().Name})";
            return false;
        }

        var valores = Leer();
        foreach (var obligatoria in new[] { "AVACOM_LMS_SECRET", "AVACOM_LMS_DB" })
        {
            if (!valores.TryGetValue(obligatoria, out var valor) || valor.Length == 0)
            {
                motivo = $"falta {obligatoria} en backend.env";
                return false;
            }
        }
        return true;
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
        contenido.AppendLine("# las entrega al backend como variables de entorno. El backend se");
        contenido.AppendLine("# configura SOLO con este archivo: las variables AVACOM_* de Windows se ignoran.");
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
        contenido.Append(TextoDe(Ajustes()));
        contenido.AppendLine();
        contenido.AppendLine("# AVACOM_CONTENIDO_ENLACE y AVACOM_CONTENIDO_ENLACE_V2 se dejan SIN definir");
        contenido.AppendLine("# a proposito: el backend busca la nota de enlace de AVACOM Contenido donde");
        contenido.AppendLine(@"# esta la publica (%ProgramData%\AVACOM\content\link.json). Definirlas aqui");
        contenido.AppendLine("# solo sirve para pruebas con el host de pruebas del repositorio, y el");
        contenido.AppendLine("# instalador las retira de un nodo real.");

        File.WriteAllText(Rutas.ArchivoConfig, contenido.ToString(), new UTF8Encoding(false));
        registro.Escribir($"Configuracion creada: {Rutas.ArchivoConfig}");
        return true;
    }

    /// <summary>
    /// Lleva una configuracion que ya existe a lo que el producto exige, sin tocar las
    /// claves de acceso ni nada que sea del tecnico:
    ///
    ///   * agrega lo que falta (entorno, carpeta de registros, fuente de cursos...);
    ///   * corrige solo lo que el producto no admite otro valor (la base de datos que
    ///     miran las copias de seguridad, la fuente de cursos siempre biblioteca, el
    ///     curso de ejemplo apagado, la escucha en 0.0.0.0:8000);
    ///   * retira las notas de enlace de pruebas de AVACOM Contenido, dejando la linea
    ///     original comentada para que se sepa que hubo.
    ///
    /// Es lo que protege al nodo de configuracion externa: una configuracion antigua o
    /// tocada a mano no puede dejar al aula sin cursos, ni escribir sus registros fuera
    /// de sitio, ni apuntar a otra base de datos. Antes de esto el instalador ya dejo una
    /// copia de backend.env en Respaldos.
    /// </summary>
    /// <returns>Los avisos que merecen verse en la pantalla final (puede ser vacio).</returns>
    public static IReadOnlyList<string> Normalizar(Registro registro)
    {
        var avisos = new List<string>();
        if (!File.Exists(Rutas.ArchivoConfig)) return avisos;

        try
        {
            var originales = File.ReadAllLines(Rutas.ArchivoConfig);
            var salida = new List<string>(originales.Length + 24);
            var cambios = new List<string>();
            var presentes = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var ajustes = Ajustes().ToDictionary(a => a.Clave, StringComparer.OrdinalIgnoreCase);
            var version = Manifiesto.Version();

            foreach (var linea in originales)
            {
                if (!TryPartir(linea, out var clave, out var valor))
                {
                    salida.Add(linea);
                    continue;
                }

                if (EnlacesDePrueba.Contains(clave, StringComparer.OrdinalIgnoreCase))
                {
                    if (valor.Length == 0)
                    {
                        salida.Add(linea);
                        continue;
                    }
                    salida.Add($"# Retirada por el instalador {version}: una nota de enlace de pruebas deja al aula sin cursos.");
                    salida.Add("# " + linea.TrimStart());
                    cambios.Add($"{clave} retirada");
                    avisos.Add($"Se retiro de la configuracion {clave}, que apuntaba a una nota de enlace de pruebas. " +
                               "El aula usa el AVACOM Contenido instalado en este equipo.");
                    continue;
                }

                presentes.Add(clave);
                if (ajustes.TryGetValue(clave, out var ajuste) && ajuste.Forzar && !Coincide(clave, valor, ajuste.Valor))
                {
                    salida.Add($"{clave}={ajuste.Valor}");
                    cambios.Add($"{clave}: {valor} -> {ajuste.Valor}");
                    if (clave.Equals("AVACOM_AULA_PERMITIR_EJEMPLO", StringComparison.OrdinalIgnoreCase)
                        || clave.Equals("AVACOM_AULA_FUENTE_CURSOS", StringComparison.OrdinalIgnoreCase))
                    {
                        avisos.Add("Los cursos salen siempre de AVACOM Contenido: se apago el curso de ejemplo que estaba encendido.");
                    }
                    continue;
                }
                salida.Add(linea);
            }

            var faltantes = Ajustes().Where(a => !presentes.Contains(a.Clave)).ToArray();
            if (faltantes.Length > 0)
            {
                salida.Add("");
                salida.Add($"# Agregado por el instalador {version}:");
                foreach (var linea in TextoDe(faltantes).Split(["\r\n", "\n"], StringSplitOptions.None)) salida.Add(linea);
                cambios.Add($"agregadas {faltantes.Length}: {string.Join(", ", faltantes.Select(f => f.Clave))}");
            }

            if (!presentes.Contains("AVACOM_LMS_SECRET"))
            {
                registro.Escribir("ADVERTENCIA: la configuracion no tiene AVACOM_LMS_SECRET; el backend usa la clave de prototipo.");
                avisos.Add("La configuracion de este nodo no tiene su clave de firma propia. Se conserva como esta para no dejar ilegibles los datos guardados.");
            }

            if (cambios.Count == 0)
            {
                registro.Escribir("La configuracion ya estaba al dia: no se cambio nada.");
                return avisos.Distinct().ToList();
            }

            // Se escribe a un temporal y se reemplaza: una luz que se va a mitad de escritura no
            // puede dejar backend.env a medias (con sus claves, eso dejaria al nodo sin personas).
            var temporal = Rutas.ArchivoConfig + ".nuevo";
            File.WriteAllText(temporal, string.Join(Environment.NewLine, salida) + Environment.NewLine, new UTF8Encoding(false));
            File.Move(temporal, Rutas.ArchivoConfig, overwrite: true);
            foreach (var cambio in cambios) registro.Escribir($"Configuracion normalizada: {cambio}");
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            registro.Escribir("No se pudo normalizar la configuracion; se deja como estaba", error);
            avisos.Add("No se pudo ajustar la configuracion de este nodo. Se dejo como estaba; el detalle esta en los registros.");
        }
        return avisos.Distinct().ToList();
    }

    private static bool Coincide(string clave, string actual, string esperado)
    {
        // Las rutas se comparan ya normalizadas: C:\ProgramData\x y c:\programdata\x\ son lo mismo.
        if (clave is "AVACOM_LMS_DB" or "AVACOM_LMS_DIR_LOGS")
        {
            try
            {
                return string.Equals(Path.GetFullPath(actual).TrimEnd('\\'), Path.GetFullPath(esperado).TrimEnd('\\'),
                    StringComparison.OrdinalIgnoreCase);
            }
            catch (ArgumentException)
            {
                return false;
            }
        }
        return string.Equals(actual, esperado, StringComparison.OrdinalIgnoreCase);
    }

    private static string TextoDe(IEnumerable<Ajuste> ajustes)
    {
        var texto = new StringBuilder();
        var primero = true;
        foreach (var ajuste in ajustes)
        {
            if (ajuste.Comentario.Length > 0)
            {
                if (!primero) texto.AppendLine();
                foreach (var linea in ajuste.Comentario.Split('\n')) texto.AppendLine("# " + linea);
            }
            texto.AppendLine($"{ajuste.Clave}={ajuste.Valor}");
            primero = false;
        }
        return texto.ToString();
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

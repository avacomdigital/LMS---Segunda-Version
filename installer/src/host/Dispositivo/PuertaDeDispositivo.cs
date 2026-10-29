using System.Reflection;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using Avacom.Ops.Host.Actualizacion;
using Avacom.Ops.Host.Integridad;
using static Avacom.Ops.Host.Dispositivo.FormatoSello;

namespace Avacom.Ops.Host.Dispositivo;

/// <summary>
/// S1 · «¿este equipo es un dispositivo AVACOM autenticado?». Tres verbos del Host (todos sin teclado, todo con toques, USB y archivos):
///
///   solicitar-sello [carpeta] [--serie X]   crea las claves del equipo si faltan y escribe <c>equipo.avsol</c> (la solicitud, firmada por el equipo) en la carpeta o en la primera memoria USB.
///   instalar-sello [ruta]                   toma un <c>.avsello</c> (y una lista <c>.avrev</c> si hay) de una ruta, de una carpeta o de una memoria USB, lo VERIFICA y lo guarda en Config\sello.
///   verificar-dispositivo                   da el veredicto y escribe la señal Config\dispositivo.json. Sale con 0 solo si es «autenticado».
///   puerta-instalacion                      lo que corre el instalador ANTES de copiar nada: recoge un sello de una USB si lo hay, verifica, y si no pasa, deja una solicitud para llevar a AVACOM.
///
/// Franqueza (SP-01/SP-05): esta puerta es un chequeo, y el instalador y este ejecutable son archivos parcheables por quien administra un equipo. La proteccion que no se salta con un parche es la
/// liberacion de la clave del paquete (S2): sin la clave del TPM del equipo sellado, el codigo no existe en claro. Esto es el mensaje claro y la evidencia, no la barrera.
///
/// Un sello que no se puede LEER por un fallo del sistema (TPM bloqueado, claves ausentes) es «no_verificable», no «clave_distinta»: es lo que distingue un error de un fraude (SR-03).
/// </summary>
internal static class PuertaDeDispositivo
{
    public const string CarpetaDeSello = "sello";
    public const string ArchivoDeSello = "equipo.avsello";
    public const string ArchivoDeRevocados = "revocados.avrev";
    public const string ArchivoDeSolicitud = "equipo.avsol";
    public const string ArchivoDeSenal = "dispositivo.json";
    public const string MarcadorDeDesarrollo = "AVACOM-DESARROLLO";
    public const string Desarrollo = "desarrollo";

    // Codigos de salida de los verbos (los lee el instalador).
    public const int SalidaAutenticado = 0, SalidaSinSello = 40, SalidaSelloInvalido = 41, SalidaClaveDistinta = 42, SalidaRevocado = 43, SalidaNoVerificable = 44, SalidaUso = 45, SalidaSinClaves = 46, SalidaIdentidadUefi = 47;

    public static IReadOnlyDictionary<string, byte[]> LlavesIncrustadas()
    {
        var texto = Assembly.GetExecutingAssembly().GetCustomAttributes<AssemblyMetadataAttribute>().FirstOrDefault(a => a.Key == "ClavesDeSello")?.Value;
        return Verificador.AnalizarLlaves(texto);
    }

    public static int Salida(string estado) => estado switch
    {
        Autenticado or Desarrollo => SalidaAutenticado, SinSello => SalidaSinSello, SelloInvalido => SalidaSelloInvalido, ClaveDistinta => SalidaClaveDistinta, Revocado => SalidaRevocado, IdentidadUefiRechazada => SalidaIdentidadUefi,
        _ => SalidaNoVerificable,
    };

    // ----------------------------------------------------------------------------------------------------------------- desarrollo
    /// <summary>
    /// El marcador de desarrollo (SP-10): un archivo vacio <c>%ProgramData%\AVACOM\AVACOM-DESARROLLO</c>. Solo vale si su DUENO es la administracion (Administradores o SYSTEM): un usuario estandar puede crear el archivo,
    /// pero no ser su dueno como administrador. No hay opcion de linea de comandos que apague la puerta.
    /// </summary>
    public static bool HayMarcadorDeDesarrollo(string? carpeta = null)
    {
        try
        {
            var ruta = Path.Combine(carpeta ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AVACOM"), MarcadorDeDesarrollo);
            if (!File.Exists(ruta) || !OperatingSystem.IsWindows()) return false;
            var dueno = new FileInfo(ruta).GetAccessControl().GetOwner(typeof(SecurityIdentifier)) as SecurityIdentifier;
            return dueno is not null && (dueno.IsWellKnown(WellKnownSidType.BuiltinAdministratorsSid) || dueno.IsWellKnown(WellKnownSidType.LocalSystemSid));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidOperationException) { return false; }
    }

    // ----------------------------------------------------------------------------------------------------------------- verificar
    public sealed record Resultado(string Estado, string Motivo, Sello? Sello, bool EnTpm, string? ClaveHuellaDelEquipo, long RevocadosNumero, string UefiId = "")
    {
        /// <summary>El estado de identidad con los nombres del contrato (Authorized, VariableNotFound, …). Un sello que falta, no verifica o no es de este equipo es «dispositivo sin licencia».</summary>
        public EstadoDeIdentidad Identidad => Estado switch
        {
            Autenticado or Desarrollo => EstadoDeIdentidad.Autorizado,
            IdentidadUefiRechazada => Motivo switch
            {
                "variable_no_encontrada" => EstadoDeIdentidad.VariableNoEncontrada,
                "firmware_no_uefi" => EstadoDeIdentidad.FirmwareNoSoportado,
                "dispositivo_sin_licencia" or "sello_sin_identificador" => EstadoDeIdentidad.DispositivoSinLicencia,
                var m when m.StartsWith("atributos_", StringComparison.Ordinal) => EstadoDeIdentidad.AtributosInvalidos,
                var m when m.StartsWith("privilegio_", StringComparison.Ordinal) => EstadoDeIdentidad.AccesoDenegado,
                "vacio" or "demasiado_largo" or "no_es_utf8" or "formato" => EstadoDeIdentidad.IdentificadorInvalido,
                _ => EstadoDeIdentidad.ErrorDeLectura,
            },
            NoVerificable => EstadoDeIdentidad.ErrorDeLectura,
            _ => EstadoDeIdentidad.DispositivoSinLicencia,
        };

        public string CodigoDeDiagnostico => IdentidadUefi.Codigo(Identidad);
    }

    private static Resultado RechazoUefi(IdentidadLeida identidad, IClavesDeEquipo claves) => new(IdentidadUefiRechazada, identidad.Motivo, null, claves.EnTpm, null, 0);

    public static byte[]? Leer(string ruta) { try { return File.Exists(ruta) ? File.ReadAllBytes(ruta) : null; } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return null; } }

    /// <summary>
    /// El veredicto de ESTE equipo con lo que hay en <paramref name="carpetaSello"/>. No crea claves: un equipo que nunca pidio sello simplemente no tiene.
    ///
    /// Orden (el del prompt de identidad UEFI): 1) la identidad que el firmware declara (variable <c>AVACOM_DEVICE_ID</c>: UEFI, permiso, existencia, atributos, formato); 2) el sello firmado por AVACOM
    /// y la prueba de que la clave del TPM es la suya; 3) que ese sello AUTORICE el identificador leido. Sin las tres, no hay autorizacion (denegado por defecto).
    /// </summary>
    public static Resultado Verificar(IClavesDeEquipo claves, IReadOnlyDictionary<string, byte[]> llaves, string carpetaSello, long ahoraMs, ILectorUefi uefi)
    {
        var identidad = IdentidadUefi.Leer(uefi);
        if (identidad.Fallo is not null) return RechazoUefi(identidad, claves);
        var datos = Leer(Path.Combine(carpetaSello, ArchivoDeSello));
        var revocados = new HashSet<string>(StringComparer.Ordinal);
        long numero = 0;
        if (Leer(Path.Combine(carpetaSello, ArchivoDeRevocados)) is { } lista)
        {
            try { (numero, revocados) = LeerRevocados(lista, llaves); }
            catch (Rechazo) { /* una lista ilegible no se obedece ni se inventa: se sigue con lo que no esta revocado */ }
        }
        var spki = claves.IdentidadSpki();
        var huella = spki is null ? null : HuellaDe(spki);
        bool? posesion = null;
        if (datos is { Length: > 0 } && huella is not null)
        {
            var reto = RandomNumberGenerator.GetBytes(32);
            var firma = claves.Firmar(MensajeDePosesion(reto, huella));
            if (firma is not null)
            {
                try { using var ec = ECDsa.Create(); ec.ImportSubjectPublicKeyInfo(spki!, out _); posesion = ec.VerifyData(MensajeDePosesion(reto, huella), firma, HashAlgorithmName.SHA256, DSASignatureFormat.IeeeP1363FixedFieldConcatenation); }
                catch (Exception ex) when (ex is CryptographicException or ArgumentException) { posesion = false; }
            }
        }
        var v = Evaluar(datos, llaves, huella, posesion, revocados, ahoraMs);
        var hex = huella is null ? null : Convert.ToHexString(huella).ToLowerInvariant();
        if (v.Estado == Autenticado && v.Sello is { } sello)
        {
            // El sello es de ESTE equipo (clave y posesion). Falta que AUTORICE el identificador que el firmware declara: un sello sin identificador no autoriza ninguno, y uno con otro es de otro dispositivo.
            if (sello.UefiId.Length == 0) return new Resultado(IdentidadUefiRechazada, "sello_sin_identificador", sello, claves.EnTpm, hex, numero, identidad.Id);
            if (!string.Equals(sello.UefiId, identidad.Id, StringComparison.Ordinal)) return new Resultado(IdentidadUefiRechazada, "dispositivo_sin_licencia", sello, claves.EnTpm, hex, numero, identidad.Id);
        }
        return new Resultado(v.Estado, v.Motivo, v.Sello, claves.EnTpm, hex, numero, identidad.Id);
    }

    public static string Senal(Resultado r, DateTime ahoraUtc) => JsonSerializer.Serialize(new
    {
        version = 1,
        verificado = ahoraUtc.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'"),
        estado = r.Estado,
        motivo = r.Motivo,
        serie = r.Sello?.Serie,
        origen = r.Sello?.Origen,
        evidencia = r.Sello?.Evidencia,
        sello_id = r.Sello?.Id,
        kid = r.Sello?.Kid,
        clave_huella = r.ClaveHuellaDelEquipo,
        en_tpm = r.EnTpm,
        revocados = r.RevocadosNumero,
        codigo = r.CodigoDeDiagnostico,                  // el identificador UEFI mismo no se copia a ninguna señal
    });

    /// <summary>
    /// La señal PARA EL LANZADOR (usuario estandar, que no puede leer Config ni el firmware): solo estado y codigo, en Logs, que cualquier usuario puede leer. Es PRESENTACION: quien la falsee solo logra
    /// ocultar o mostrar el aviso; el nodo no arranca sin pasar la puerta del servicio ni liberar la clave del paquete.
    /// </summary>
    public static string SenalParaElLanzador(Resultado r, DateTime ahoraUtc) => JsonSerializer.Serialize(new
    {
        version = 1,
        verificado = ahoraUtc.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'"),
        autorizado = r.Identidad == EstadoDeIdentidad.Autorizado,
        estado = r.Estado,
        codigo = r.CodigoDeDiagnostico,
    });

    public static string Mensaje(string estado) => estado switch
    {
        Autenticado => "Este equipo es un dispositivo AVACOM autenticado.",
        Desarrollo => "Modo de desarrollo: la puerta de dispositivo esta apagada por el marcador de un administrador.",
        SinSello => "Este equipo no es un dispositivo AVACOM autenticado: no trae el sello de AVACOM.",
        SelloInvalido => "El sello de este equipo no es valido (esta alterado, vencido o no es de AVACOM).",
        ClaveDistinta => "El sello es de otro equipo: este equipo no puede probar que le pertenece.",
        Revocado => "AVACOM revoco el sello de este equipo.",
        IdentidadUefiRechazada => "La identidad UEFI de este equipo no esta autorizada por AVACOM.",
        _ => "No se pudo comprobar el equipo (el modulo de seguridad no respondio). Intenta de nuevo; si sigue igual, avisa a AVACOM.",
    };

    // ----------------------------------------------------------------------------------------------------------------- solicitar
    /// <param name="uefiId">El <c>AVACOM_DEVICE_ID</c> que el equipo leyo de su firmware: viaja firmado por la clave del equipo para que AVACOM sepa a que identidad atar el sello.</param>
    public static (int Codigo, string Ruta) Solicitar(IClavesDeEquipo claves, string carpetaDestino, string? serie, long ahoraMs, string uefiId)
    {
        if (!claves.Crear()) return (SalidaSinClaves, "");
        var spki = claves.IdentidadSpki();
        if (spki is null) return (SalidaSinClaves, "");
        var s = new DatosDeSolicitud(RandomNumberGenerator.GetBytes(16), Limpio(serie ?? DatosDelEquipo.Serie()), Limpio(DatosDelEquipo.Modelo()), spki, claves.CifradoSpki(), claves.EkPub(), DatosDelEquipo.Mac(), claves.EnTpm, ahoraMs, uefiId);
        var datos = EscribirSolicitud(s, m => claves.Firmar(m) ?? throw new InvalidOperationException("la clave de identidad no firmo"));
        Directory.CreateDirectory(carpetaDestino);
        var ruta = Path.Combine(carpetaDestino, ArchivoDeSolicitud);
        File.WriteAllBytes(ruta, datos);
        return (0, ruta);
    }

    private static string Limpio(string texto)
    {
        var sb = new StringBuilder();
        foreach (var c in texto.Trim()) if (c is >= ' ' and <= '~') sb.Append(c);
        return sb.Length > 64 ? sb.ToString(0, 64) : sb.ToString();
    }

    // ----------------------------------------------------------------------------------------------------------------- instalar
    /// <summary>Las candidatas de una ruta: un archivo, una carpeta (se buscan <c>*.avsello</c> y <c>*.avrev</c>, sin bajar mas de un nivel) o, sin ruta, las unidades extraibles.</summary>
    public static IEnumerable<string> Candidatas(string? ruta)
    {
        IEnumerable<string> raices = ruta is not null ? [ruta] : UnidadesExtraibles();
        foreach (var raiz in raices)
        {
            if (File.Exists(raiz)) { yield return raiz; continue; }
            if (!Directory.Exists(raiz)) continue;
            IEnumerable<string> encontrados;
            try { encontrados = Directory.EnumerateFiles(raiz, "*.avsello").Concat(Directory.EnumerateFiles(raiz, "*.avrev")).Concat(Directory.EnumerateFiles(raiz, "*.avclave")).ToList(); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { continue; }
            foreach (var f in encontrados) yield return f;
        }
    }

    public static IEnumerable<string> UnidadesExtraibles()
    {
        // En un ensayo del instalador la «memoria USB» es una carpeta de pruebas (AVACOM_OPS_USB): jamas se mira una unidad real.
        if (Rutas.EsEnsayo)
        {
            if (Environment.GetEnvironmentVariable("AVACOM_OPS_USB") is { Length: > 0 } carpeta && Directory.Exists(carpeta)) yield return carpeta;
            yield break;
        }
        foreach (var d in DriveInfo.GetDrives())
        {
            bool listo;
            try { listo = d.IsReady && d.DriveType == DriveType.Removable; } catch (IOException) { continue; }
            if (listo) yield return d.RootDirectory.FullName;
        }
    }

    /// <summary>
    /// Verifica y guarda. Un sello que no verifica NO se instala (no se pisa uno bueno con basura). Una lista de revocados mas vieja que la guardada tampoco. Devuelve un mensaje por archivo.
    /// </summary>
    public static (int Instalados, List<string> Mensajes) Instalar(IEnumerable<string> archivos, IReadOnlyDictionary<string, byte[]> llaves, string carpetaSello)
    {
        var instalados = 0;
        var mensajes = new List<string>();
        foreach (var archivo in archivos)
        {
            byte[] datos;
            try { datos = File.ReadAllBytes(archivo); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { mensajes.Add($"{Path.GetFileName(archivo)}: no se pudo leer."); continue; }
            Directory.CreateDirectory(carpetaSello);
            if (datos.AsSpan().StartsWith(MagicSello))
            {
                try
                {
                    var s = LeerSello(datos, llaves);
                    Disco.EscribirAtomico(Path.Combine(carpetaSello, ArchivoDeSello), datos);
                    mensajes.Add($"Sello instalado: serie {s.Serie}.");
                    instalados++;
                }
                catch (Rechazo r) { mensajes.Add($"{Path.GetFileName(archivo)}: el sello no es valido ({r.Motivo})."); }
            }
            else if (datos.AsSpan().StartsWith(MagicClave))
            {
                try
                {
                    var c = LeerClave(datos, llaves);
                    Disco.EscribirAtomico(Path.Combine(carpetaSello, $"paquete-{Convert.ToHexString(c.KidPaquete).ToLowerInvariant()}.avclave"), datos);
                    mensajes.Add($"Clave del paquete {Convert.ToHexString(c.KidPaquete).ToLowerInvariant()} instalada.");
                    instalados++;
                }
                catch (Rechazo r) { mensajes.Add($"{Path.GetFileName(archivo)}: la clave del paquete no es valida ({r.Motivo})."); }
            }
            else if (datos.AsSpan().StartsWith(MagicRevocados))
            {
                try
                {
                    var (numero, _) = LeerRevocados(datos, llaves);
                    var actual = Leer(Path.Combine(carpetaSello, ArchivoDeRevocados)) is { } previa ? SafeNumero(previa, llaves) : -1;
                    if (numero <= actual) { mensajes.Add($"Lista de revocados {numero}: ya hay una igual o mas nueva ({actual})."); continue; }
                    Disco.EscribirAtomico(Path.Combine(carpetaSello, ArchivoDeRevocados), datos);
                    mensajes.Add($"Lista de revocados {numero} instalada.");
                    instalados++;
                }
                catch (Rechazo r) { mensajes.Add($"{Path.GetFileName(archivo)}: la lista no es valida ({r.Motivo})."); }
            }
        }
        return (instalados, mensajes);
    }

    private static long SafeNumero(byte[] lista, IReadOnlyDictionary<string, byte[]> llaves)
    {
        try { return LeerRevocados(lista, llaves).Numero; } catch (Rechazo) { return -1; }
    }

    public static string CarpetaDeSelloDelNodo => Path.Combine(Rutas.CarpetaConfig, CarpetaDeSello);
    public static string RutaDeSenal => Path.Combine(Rutas.CarpetaConfig, ArchivoDeSenal);

    public const string ArchivoDeSenalDelLanzador = "dispositivo-estado.json";

    /// <summary>La señal del lanzador vive en Logs, hermana de Config (Config solo la leen SYSTEM y los administradores; Logs, cualquier usuario).</summary>
    public static string RutaDeSenalDelLanzador(string rutaDeSenalDeConfig) =>
        Path.Combine(Path.GetDirectoryName(Path.GetDirectoryName(rutaDeSenalDeConfig)) ?? "", "Logs", ArchivoDeSenalDelLanzador);

    public static string RutaDeSenalDelLanzadorDelNodo => RutaDeSenalDelLanzador(RutaDeSenal);
}

/// <summary>Lo informativo del equipo (SP-03: ninguno de estos datos decide nada).</summary>
internal static class DatosDelEquipo
{
    public static string Serie() => Wmi("SELECT SerialNumber FROM Win32_BIOS", "SerialNumber");
    public static string Modelo() => Wmi("SELECT Model FROM Win32_ComputerSystem", "Model");

    private static string Wmi(string consulta, string propiedad)
    {
        // WMI via PowerShell no: se evita arrancar otro proceso. System.Management no viaja en el Host; se lee del registro de SMBIOS (HKLM\HARDWARE\DESCRIPTION\System\BIOS).
        try
        {
            using var clave = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(@"HARDWARE\DESCRIPTION\System\BIOS");
            var nombre = propiedad == "SerialNumber" ? "SystemSerialNumber" : "SystemProductName";
            return clave?.GetValue(nombre) as string ?? "";
        }
        catch (Exception ex) when (ex is UnauthorizedAccessException or System.Security.SecurityException or IOException) { return ""; }
    }

    public static string Mac()
    {
        try
        {
            foreach (var n in System.Net.NetworkInformation.NetworkInterface.GetAllNetworkInterfaces())
            {
                if (n.OperationalStatus != System.Net.NetworkInformation.OperationalStatus.Up) continue;
                if (n.NetworkInterfaceType is System.Net.NetworkInformation.NetworkInterfaceType.Loopback or System.Net.NetworkInformation.NetworkInterfaceType.Tunnel) continue;
                var b = n.GetPhysicalAddress().GetAddressBytes();
                if (b.Length == 6) return string.Join(":", b.Select(x => x.ToString("X2")));
            }
        }
        catch (Exception ex) when (ex is System.Net.NetworkInformation.NetworkInformationException or InvalidOperationException) { }
        return "";
    }
}

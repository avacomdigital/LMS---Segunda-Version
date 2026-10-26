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
    public const int SalidaAutenticado = 0, SalidaSinSello = 40, SalidaSelloInvalido = 41, SalidaClaveDistinta = 42, SalidaRevocado = 43, SalidaNoVerificable = 44, SalidaUso = 45, SalidaSinClaves = 46;

    public static IReadOnlyDictionary<string, byte[]> LlavesIncrustadas()
    {
        var texto = Assembly.GetExecutingAssembly().GetCustomAttributes<AssemblyMetadataAttribute>().FirstOrDefault(a => a.Key == "ClavesDeSello")?.Value;
        return Verificador.AnalizarLlaves(texto);
    }

    public static int Salida(string estado) => estado switch
    {
        Autenticado or Desarrollo => SalidaAutenticado, SinSello => SalidaSinSello, SelloInvalido => SalidaSelloInvalido, ClaveDistinta => SalidaClaveDistinta, Revocado => SalidaRevocado,
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
    public sealed record Resultado(string Estado, string Motivo, Sello? Sello, bool EnTpm, string? ClaveHuellaDelEquipo, long RevocadosNumero);

    public static byte[]? Leer(string ruta) { try { return File.Exists(ruta) ? File.ReadAllBytes(ruta) : null; } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return null; } }

    /// <summary>El veredicto de ESTE equipo con lo que hay en <paramref name="carpetaSello"/>. No crea claves: un equipo que nunca pidio sello simplemente no tiene.</summary>
    public static Resultado Verificar(IClavesDeEquipo claves, IReadOnlyDictionary<string, byte[]> llaves, string carpetaSello, long ahoraMs)
    {
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
        return new Resultado(v.Estado, v.Motivo, v.Sello, claves.EnTpm, huella is null ? null : Convert.ToHexString(huella).ToLowerInvariant(), numero);
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
    });

    public static string Mensaje(string estado) => estado switch
    {
        Autenticado => "Este equipo es un dispositivo AVACOM autenticado.",
        Desarrollo => "Modo de desarrollo: la puerta de dispositivo esta apagada por el marcador de un administrador.",
        SinSello => "Este equipo no es un dispositivo AVACOM autenticado: no trae el sello de AVACOM.",
        SelloInvalido => "El sello de este equipo no es valido (esta alterado, vencido o no es de AVACOM).",
        ClaveDistinta => "El sello es de otro equipo: este equipo no puede probar que le pertenece.",
        Revocado => "AVACOM revoco el sello de este equipo.",
        _ => "No se pudo comprobar el equipo (el modulo de seguridad no respondio). Intenta de nuevo; si sigue igual, avisa a AVACOM.",
    };

    // ----------------------------------------------------------------------------------------------------------------- solicitar
    public static (int Codigo, string Ruta) Solicitar(IClavesDeEquipo claves, string carpetaDestino, string? serie, long ahoraMs)
    {
        if (!claves.Crear()) return (SalidaSinClaves, "");
        var spki = claves.IdentidadSpki();
        if (spki is null) return (SalidaSinClaves, "");
        var s = new DatosDeSolicitud(RandomNumberGenerator.GetBytes(16), Limpio(serie ?? DatosDelEquipo.Serie()), Limpio(DatosDelEquipo.Modelo()), spki, claves.CifradoSpki(), claves.EkPub(), DatosDelEquipo.Mac(), claves.EnTpm, ahoraMs);
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
            try { encontrados = Directory.EnumerateFiles(raiz, "*.avsello").Concat(Directory.EnumerateFiles(raiz, "*.avrev")).ToList(); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { continue; }
            foreach (var f in encontrados) yield return f;
        }
    }

    public static IEnumerable<string> UnidadesExtraibles()
    {
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

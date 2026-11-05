using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Text;
using System.Text.RegularExpressions;

namespace Avacom.Ops.Host.Dispositivo;

/// <summary>Lo que paso al pedirle al firmware una variable UEFI. <see cref="Leida"/> es la UNICA que trae valor.</summary>
internal enum EstadoDeLecturaUefi { Leida, VariableNoEncontrada, FirmwareNoSoportado, AccesoDenegado, ValorDemasiadoLargo, ErrorDeLectura }

internal sealed record LecturaUefi(EstadoDeLecturaUefi Estado, byte[]? Valor = null, uint Atributos = 0, int CodigoDeSistema = 0);

/// <summary>El puerto del firmware: lo unico que toca hardware. Las pruebas lo reemplazan por uno falso; jamas se escribe ni se borra una variable (este contrato solo tiene «leer»).</summary>
internal interface ILectorUefi
{
    LecturaUefi Leer(string nombre, Guid proveedor);
}

/// <summary>
/// El resultado de decidir si un equipo es un dispositivo AVACOM autorizado, con los nombres del contrato pedido (Authorized, VariableNotFound, InvalidIdentifier, InvalidAttributes, DeviceNotLicensed,
/// UnsupportedFirmware, AccessDenied, ReadError). <see cref="Autorizado"/> SOLO lo da el conjunto: identidad leida del firmware + sello firmado por AVACOM que la autoriza.
/// </summary>
internal enum EstadoDeIdentidad { Autorizado, VariableNoEncontrada, IdentificadorInvalido, AtributosInvalidos, DispositivoSinLicencia, FirmwareNoSoportado, AccesoDenegado, ErrorDeLectura }

/// <summary>El contrato de la validacion de identidad. La implementacion (<see cref="IdentidadDeDispositivo"/>) NO tiene un criterio propio: es la misma puerta que usan el instalador y el servicio.</summary>
internal interface IIdentidadDeDispositivoAvacom
{
    ResultadoDeIdentidad Validar();
}

internal sealed record ResultadoDeIdentidad(EstadoDeIdentidad Estado, string Codigo, string Motivo)
{
    public bool Autorizado => Estado == EstadoDeIdentidad.Autorizado;
}

/// <summary>Una identidad leida del firmware. <see cref="Fallo"/> es null si se leyo, tiene formato y atributos validos (todavia NO esta autorizada: eso lo dice el sello).</summary>
internal sealed record IdentidadLeida(EstadoDeIdentidad? Fallo, string Id, string Motivo);

/// <summary>
/// La identidad UEFI del dispositivo: la variable <c>AVACOM_DEVICE_ID</c> (GUID {8b7f9c20-3e51-4c8a-a7d1-91c62e0f4b35}) que la fabrica graba en el firmware de cada OPS AVACOM.
///
/// IDENTIDAD no es AUTORIZACION. Esta clase solo LEE y valida la forma: una variable UEFI corriente la puede crear quien tenga privilegios suficientes, asi que un valor «AVACOM-OPS-…» bien formado no
/// prueba nada. Lo que autoriza es que el sello que AVACOM firmo para este equipo traiga ESE identificador (<see cref="PuertaDeDispositivo.Verificar"/>). Tampoco se compara con ningun valor fijo:
/// cada equipo tiene el suyo (el de pruebas, AVACOM-OPS-00001234, no esta en el codigo).
/// </summary>
internal static class IdentidadUefi
{
    public const string Nombre = "AVACOM_DEVICE_ID";
    public static readonly Guid Proveedor = new("8b7f9c20-3e51-4c8a-a7d1-91c62e0f4b35");

    public const uint AtributoNoVolatil = 0x1, AtributoServiciosDeArranque = 0x2, AtributoEnEjecucion = 0x4;
    /// <summary>Los tres atributos con que la fabrica graba la variable (0x7). Se exigen TODOS; un firmware que ademas la proteja con otros bits (escritura autenticada) tambien se acepta.</summary>
    public const uint AtributosEsperados = AtributoNoVolatil | AtributoServiciosDeArranque | AtributoEnEjecucion;

    public const int MaximoDeBytes = 64;

    // El formato autorizado: «AVACOM-OPS-» y 8 a 16 mayusculas o digitos. Es el mismo de la estacion (sello.FORMATO_UEFI_ID).
    private static readonly Regex Formato = new(@"\AAVACOM-OPS-[0-9A-Z]{8,16}\z", RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);

    public static bool EsFormatoValido(string texto) => Formato.IsMatch(texto);

    /// <summary>Lee la variable y comprueba, en este orden: que el firmware sea UEFI y deje leerla, que exista, que traiga los atributos esperados, que el valor sea UTF-8 limpio y de formato autorizado.</summary>
    public static IdentidadLeida Leer(ILectorUefi lector)
    {
        LecturaUefi lectura;
        try { lectura = lector.Leer(Nombre, Proveedor); }
        catch (Exception)
        {
            // Denegado por defecto: cualquier fallo del puerto (API ausente, error nativo, acceso a memoria) es «error de lectura». La excepcion NO se propaga ni se copia al motivo.
            return new IdentidadLeida(EstadoDeIdentidad.ErrorDeLectura, "", "excepcion_al_leer");
        }
        switch (lectura.Estado)
        {
            case EstadoDeLecturaUefi.FirmwareNoSoportado: return new IdentidadLeida(EstadoDeIdentidad.FirmwareNoSoportado, "", "firmware_no_uefi");
            case EstadoDeLecturaUefi.AccesoDenegado: return new IdentidadLeida(EstadoDeIdentidad.AccesoDenegado, "", $"privilegio_{lectura.CodigoDeSistema}");
            case EstadoDeLecturaUefi.VariableNoEncontrada: return new IdentidadLeida(EstadoDeIdentidad.VariableNoEncontrada, "", "variable_no_encontrada");
            case EstadoDeLecturaUefi.ValorDemasiadoLargo: return new IdentidadLeida(EstadoDeIdentidad.IdentificadorInvalido, "", "demasiado_largo");
            case EstadoDeLecturaUefi.ErrorDeLectura or not EstadoDeLecturaUefi.Leida: return new IdentidadLeida(EstadoDeIdentidad.ErrorDeLectura, "", $"error_{lectura.CodigoDeSistema}");
        }
        if ((lectura.Atributos & AtributosEsperados) != AtributosEsperados) return new IdentidadLeida(EstadoDeIdentidad.AtributosInvalidos, "", $"atributos_{lectura.Atributos:X}");
        var valor = lectura.Valor ?? [];
        var fin = valor.Length;
        while (fin > 0 && valor[fin - 1] == 0) fin--;                                              // el firmware a veces deja un terminador
        if (fin == 0 || fin > MaximoDeBytes) return new IdentidadLeida(EstadoDeIdentidad.IdentificadorInvalido, "", fin == 0 ? "vacio" : "demasiado_largo");
        string texto;
        try { texto = new UTF8Encoding(false, throwOnInvalidBytes: true).GetString(valor, 0, fin); }
        catch (ArgumentException) { return new IdentidadLeida(EstadoDeIdentidad.IdentificadorInvalido, "", "no_es_utf8"); }
        return EsFormatoValido(texto) ? new IdentidadLeida(null, texto, "") : new IdentidadLeida(EstadoDeIdentidad.IdentificadorInvalido, "", "formato");
    }

    /// <summary>El codigo corto que ve quien da soporte (sin datos del equipo). Nunca se muestra una excepcion.</summary>
    public static string Codigo(EstadoDeIdentidad estado) => estado switch
    {
        EstadoDeIdentidad.Autorizado => "AVC-UEFI-00",
        EstadoDeIdentidad.VariableNoEncontrada => "AVC-UEFI-01",
        EstadoDeIdentidad.IdentificadorInvalido => "AVC-UEFI-02",
        EstadoDeIdentidad.AtributosInvalidos => "AVC-UEFI-03",
        EstadoDeIdentidad.DispositivoSinLicencia => "AVC-UEFI-04",
        EstadoDeIdentidad.FirmwareNoSoportado => "AVC-UEFI-05",
        EstadoDeIdentidad.AccesoDenegado => "AVC-UEFI-06",
        _ => "AVC-UEFI-07",
    };

    /// <summary>El mensaje obligatorio cuando falla la identidad o la autorizacion (instalador y aplicacion). No lleva datos tecnicos.</summary>
    public const string MensajeDeRechazo =
        "El LMS solo puede correr en dispositivos AVACOM. En caso de tratarse de un error, contacte con su distribuidor o canales de soporte autorizados.";
}

/// <summary>
/// La lectura real: <c>GetFirmwareEnvironmentVariableExW</c> de kernel32. SOLO LEE: este ensamblado no importa <c>SetFirmwareEnvironmentVariable</c> y no hay forma de escribir o borrar una variable.
///
/// Permisos: Windows exige el privilegio <c>SeSystemEnvironmentPrivilege</c> (los administradores lo tienen, desactivado; SYSTEM tambien). Se ACTIVA solo mientras dura la lectura y se vuelve a
/// desactivar: no se eleva la aplicacion entera ni se pide nada al usuario. Quien da la clase (usuario estandar) no puede leerla; por eso la lee el SERVICIO (SYSTEM) y el INSTALADOR (administrador),
/// y el lanzador solo muestra el resultado que dejo el servicio.
/// </summary>
[SupportedOSPlatform("windows")]
internal sealed class LectorUefiWindows : ILectorUefi
{
    private const int ErrorFuncionInvalida = 1, ErrorAccesoDenegado = 5, ErrorBufferInsuficiente = 122, ErrorNoEncontrada = 203, ErrorPrivilegioNoConcedido = 1314, ErrorNoTodosAsignados = 1300;
    private const uint TipoUefi = 2, TipoBios = 1;

    public LecturaUefi Leer(string nombre, Guid proveedor)
    {
        // ¿El equipo arranco con UEFI? Con Legacy BIOS la API responde «funcion invalida»; se pregunta antes para dar el motivo exacto.
        if (GetFirmwareType(out var tipo) && tipo == TipoBios) return new LecturaUefi(EstadoDeLecturaUefi.FirmwareNoSoportado);

        var activado = AjustarPrivilegio(activar: true);
        try
        {
            var buffer = new byte[MaximoLeido];
            var largo = GetFirmwareEnvironmentVariableExW(nombre, proveedor.ToString("B"), buffer, (uint)buffer.Length, out var atributos);
            if (largo > 0) return new LecturaUefi(EstadoDeLecturaUefi.Leida, buffer[..(int)largo], atributos);
            var error = Marshal.GetLastWin32Error();
            return error switch
            {
                ErrorFuncionInvalida => new LecturaUefi(EstadoDeLecturaUefi.FirmwareNoSoportado, CodigoDeSistema: error),
                ErrorNoEncontrada => new LecturaUefi(EstadoDeLecturaUefi.VariableNoEncontrada, CodigoDeSistema: error),
                ErrorPrivilegioNoConcedido or ErrorAccesoDenegado => new LecturaUefi(EstadoDeLecturaUefi.AccesoDenegado, CodigoDeSistema: error),
                ErrorBufferInsuficiente => new LecturaUefi(EstadoDeLecturaUefi.ValorDemasiadoLargo, CodigoDeSistema: error),
                _ => new LecturaUefi(EstadoDeLecturaUefi.ErrorDeLectura, CodigoDeSistema: error),
            };
        }
        finally
        {
            if (activado) AjustarPrivilegio(activar: false);
        }
    }

    private const int MaximoLeido = 256;

    private static bool AjustarPrivilegio(bool activar)
    {
        if (!OpenProcessToken(GetCurrentProcess(), 0x0020 | 0x0008, out var ficha)) return false;     // TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY
        try
        {
            if (!LookupPrivilegeValueW(null, "SeSystemEnvironmentPrivilege", out var luid)) return false;
            var privilegios = new TokenPrivilegios { Cantidad = 1, Luid = luid, Atributos = activar ? 0x2u : 0u };   // SE_PRIVILEGE_ENABLED
            if (!AdjustTokenPrivileges(ficha, false, ref privilegios, 0, IntPtr.Zero, IntPtr.Zero)) return false;
            return Marshal.GetLastWin32Error() != ErrorNoTodosAsignados;                                      // true aunque no se concediera = el truco clasico de esta API
        }
        finally { CloseHandle(ficha); }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Luid { public uint Baja; public int Alta; }

    [StructLayout(LayoutKind.Sequential)]
    private struct TokenPrivilegios { public uint Cantidad; public Luid Luid; public uint Atributos; }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetFirmwareType(out uint tipo);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern uint GetFirmwareEnvironmentVariableExW(string nombre, string guid, byte[] buffer, uint tamano, out uint atributos);

    [DllImport("kernel32.dll")]
    private static extern IntPtr GetCurrentProcess();

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr manejador);

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern bool OpenProcessToken(IntPtr proceso, uint acceso, out IntPtr ficha);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool LookupPrivilegeValueW(string? sistema, string nombre, out Luid luid);

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern bool AdjustTokenPrivileges(IntPtr ficha, bool desactivarTodos, ref TokenPrivilegios nuevos, uint tamano, IntPtr anteriores, IntPtr tamanoAnterior);
}

/// <summary>
/// El lector de un ENSAYO del instalador (AVACOM_OPS_ENSAYO=1 + carpeta de pruebas): el identificador sale de la variable de entorno <c>AVACOM_OPS_UEFI</c>; sin ella, «variable no encontrada».
/// Igual que la «memoria USB» de ensayo, jamas se usa fuera de un ensayo.
/// </summary>
internal sealed class LectorUefiDeEnsayo(string? id) : ILectorUefi
{
    public LecturaUefi Leer(string nombre, Guid proveedor) =>
        string.IsNullOrEmpty(id) ? new LecturaUefi(EstadoDeLecturaUefi.VariableNoEncontrada) : new LecturaUefi(EstadoDeLecturaUefi.Leida, Encoding.UTF8.GetBytes(id), IdentidadUefi.AtributosEsperados);
}

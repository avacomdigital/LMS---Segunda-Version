using System.ComponentModel;
using Avacom.Lms.Core.Reporting;

namespace Avacom.Lms.Core.Tests;

/// <summary>De una excepción de E/S a lo que la persona ve: qué pasó y qué hacer. Los códigos son un contrato con el backend.</summary>
public sealed class MotivosDeEscrituraTests
{
    /// <summary>Un IOException con el HResult fijado, como lo construye .NET al traducir un error de Windows.</summary>
    private static IOException Io(int hresult) => new("fallo de prueba", hresult);

    /// <summary>El HResult que .NET guarda para un código de Windows: 0x8007 + el código.</summary>
    private static int Hr(int win32) => unchecked((int)(0x80070000u | (uint)win32));

    private static MotivoDeEscritura Motivo(Exception ex, string? ruta = null) => MotivosDeEscritura.Clasificar(ex, ruta).Motivo;

    private sealed class MensajeQueFalla : Exception
    {
        public override string Message => throw new InvalidOperationException("este mensaje no se puede leer");
    }

    // ---------------------------------------------------------------------------------------------------- el contrato

    [Fact]
    public void LosOnceCodigos_SonExactamenteLosDelContrato()
    {
        var esperados = new Dictionary<MotivoDeEscritura, string>
        {
            [MotivoDeEscritura.MedioRetirado] = "medio_retirado",
            [MotivoDeEscritura.SinEspacio] = "sin_espacio",
            [MotivoDeEscritura.ProtegidoContraEscritura] = "protegido_contra_escritura",
            [MotivoDeEscritura.SinPermiso] = "sin_permiso",
            [MotivoDeEscritura.RutaDeRedInalcanzable] = "ruta_de_red_inalcanzable",
            [MotivoDeEscritura.NombreInvalido] = "nombre_invalido",
            [MotivoDeEscritura.BloqueadoPorAntivirus] = "bloqueado_por_antivirus",
            [MotivoDeEscritura.ArchivoEnUso] = "archivo_en_uso",
            [MotivoDeEscritura.VerificacionFallida] = "verificacion_fallida",
            [MotivoDeEscritura.Cancelado] = "cancelado",
            [MotivoDeEscritura.Otro] = "otro",
        };

        var todos = Enum.GetValues<MotivoDeEscritura>();
        Assert.Equal(11, todos.Length);
        Assert.Equal(esperados.Keys.OrderBy(m => m), todos.OrderBy(m => m));              // no falta ni sobra ninguno
        foreach (var (motivo, codigo) in esperados)
        {
            Assert.Equal(codigo, MotivosDeEscritura.Codigo(motivo));
            Assert.Equal(codigo, MotivosDeEscritura.De(motivo).Codigo);
            Assert.Equal(motivo, MotivosDeEscritura.De(motivo).Motivo);
        }
        Assert.Equal(11, todos.Select(MotivosDeEscritura.Codigo).Distinct().Count());
    }

    [Fact]
    public void TodoMotivo_TieneMensajeYAccion_EnEspanolClaroYSinJerga()
    {
        foreach (var motivo in Enum.GetValues<MotivoDeEscritura>())
        {
            var fallo = MotivosDeEscritura.De(motivo);
            foreach (var texto in new[] { fallo.Mensaje, fallo.Accion })
            {
                Assert.False(string.IsNullOrWhiteSpace(texto), $"{motivo} sin texto");
                Assert.EndsWith(".", texto);
                Assert.False(texto.Any(char.IsDigit), $"{motivo}: «{texto}» trae un número (¿un código de error?)");
                foreach (var jerga in new[] { "excepción", "excepcion", "exception", "hresult", "0x", "ioexception", "error " })
                    Assert.DoesNotContain(jerga, texto, StringComparison.OrdinalIgnoreCase);
            }
        }
        Assert.Equal(11, Enum.GetValues<MotivoDeEscritura>().Select(m => MotivosDeEscritura.De(m).Mensaje).Distinct().Count());       // ningún mensaje se repite
    }

    [Fact]
    public void LosTextosAcordados_SonLosQueLaPersonaLee()
    {
        Assert.Equal("La memoria no tiene espacio suficiente para este archivo.", MotivosDeEscritura.De(MotivoDeEscritura.SinEspacio).Mensaje);
        Assert.Equal("Libera espacio o elige otro destino. El reporte sigue en pantalla.", MotivosDeEscritura.De(MotivoDeEscritura.SinEspacio).Accion);
        Assert.Equal("Se retiró la memoria mientras se guardaba.", MotivosDeEscritura.De(MotivoDeEscritura.MedioRetirado).Mensaje);
        Assert.Equal("Vuelve a conectarla y toca Guardar otra vez, o elige otro destino.", MotivosDeEscritura.De(MotivoDeEscritura.MedioRetirado).Accion);
        Assert.Equal("La memoria está protegida contra escritura.", MotivosDeEscritura.De(MotivoDeEscritura.ProtegidoContraEscritura).Mensaje);
        Assert.Equal("Quita el seguro de la memoria o elige otro destino.", MotivosDeEscritura.De(MotivoDeEscritura.ProtegidoContraEscritura).Accion);
        Assert.Equal("No tienes permiso para guardar en esa carpeta.", MotivosDeEscritura.De(MotivoDeEscritura.SinPermiso).Mensaje);
        Assert.Equal("No se pudo llegar a esa carpeta de red.", MotivosDeEscritura.De(MotivoDeEscritura.RutaDeRedInalcanzable).Mensaje);
        Assert.Equal("Comprueba la conexión del equipo con la red del colegio o elige otro destino.", MotivosDeEscritura.De(MotivoDeEscritura.RutaDeRedInalcanzable).Accion);
        Assert.Equal("El sistema de esa unidad no acepta ese nombre de archivo.", MotivosDeEscritura.De(MotivoDeEscritura.NombreInvalido).Mensaje);
        Assert.Equal("Un antivirus bloqueó el archivo.", MotivosDeEscritura.De(MotivoDeEscritura.BloqueadoPorAntivirus).Mensaje);
        Assert.Equal("Pide a soporte que permita guardar reportes ahí, o elige otro destino.", MotivosDeEscritura.De(MotivoDeEscritura.BloqueadoPorAntivirus).Accion);
        Assert.Equal("Otro programa está usando ese archivo.", MotivosDeEscritura.De(MotivoDeEscritura.ArchivoEnUso).Mensaje);
        Assert.Equal("El archivo guardado no coincide con el original, así que se descartó.", MotivosDeEscritura.De(MotivoDeEscritura.VerificacionFallida).Mensaje);
        Assert.Equal("Prueba otra vez o elige otro destino; si se repite, la memoria puede estar dañada.", MotivosDeEscritura.De(MotivoDeEscritura.VerificacionFallida).Accion);
        Assert.Equal("Cancelaste el guardado.", MotivosDeEscritura.De(MotivoDeEscritura.Cancelado).Mensaje);
        Assert.Equal("No se pudo guardar el archivo.", MotivosDeEscritura.De(MotivoDeEscritura.Otro).Mensaje);
        Assert.Equal("Elige otro destino. El reporte sigue en pantalla.", MotivosDeEscritura.De(MotivoDeEscritura.Otro).Accion);
    }

    [Fact]
    public void UnValorQueNoEsUnMotivo_EsOtro()
    {
        Assert.Equal(MotivoDeEscritura.Otro, MotivosDeEscritura.De((MotivoDeEscritura)999).Motivo);
        Assert.Equal("otro", MotivosDeEscritura.Codigo((MotivoDeEscritura)(-1)));
    }

    // ---------------------------------------------------------------------------------------------------- por el código de Windows

    // La tabla completa de MotivosDeEscritura, un renglón por código. Se prueba de tres formas: el código pelado, el HResult que arma .NET (0x8007 + código) y un Win32Exception.
    [Theory]
    [InlineData(0x70, MotivoDeEscritura.SinEspacio)]               // ERROR_DISK_FULL
    [InlineData(0x27, MotivoDeEscritura.SinEspacio)]               // ERROR_HANDLE_DISK_FULL
    [InlineData(0xDF, MotivoDeEscritura.SinEspacio)]               // ERROR_FILE_TOO_LARGE (FAT32)
    [InlineData(0x718, MotivoDeEscritura.SinEspacio)]              // ERROR_NOT_ENOUGH_QUOTA
    [InlineData(0x13, MotivoDeEscritura.ProtegidoContraEscritura)] // ERROR_WRITE_PROTECT
    [InlineData(0x05, MotivoDeEscritura.SinPermiso)]               // ERROR_ACCESS_DENIED
    [InlineData(0x41, MotivoDeEscritura.SinPermiso)]               // ERROR_NETWORK_ACCESS_DENIED
    [InlineData(0x522, MotivoDeEscritura.SinPermiso)]              // ERROR_PRIVILEGE_NOT_HELD
    [InlineData(0x52E, MotivoDeEscritura.SinPermiso)]              // ERROR_LOGON_FAILURE
    [InlineData(0x20, MotivoDeEscritura.ArchivoEnUso)]             // ERROR_SHARING_VIOLATION
    [InlineData(0x21, MotivoDeEscritura.ArchivoEnUso)]             // ERROR_LOCK_VIOLATION
    [InlineData(0xE1, MotivoDeEscritura.BloqueadoPorAntivirus)]    // ERROR_VIRUS_INFECTED
    [InlineData(0xE2, MotivoDeEscritura.BloqueadoPorAntivirus)]    // ERROR_VIRUS_DELETED
    [InlineData(0x6F, MotivoDeEscritura.NombreInvalido)]           // ERROR_BUFFER_OVERFLOW (nombre demasiado largo)
    [InlineData(0x7B, MotivoDeEscritura.NombreInvalido)]           // ERROR_INVALID_NAME
    [InlineData(0xA1, MotivoDeEscritura.NombreInvalido)]           // ERROR_BAD_PATHNAME
    [InlineData(0xCE, MotivoDeEscritura.NombreInvalido)]           // ERROR_FILENAME_EXCED_RANGE
    [InlineData(0x10B, MotivoDeEscritura.NombreInvalido)]          // ERROR_DIRECTORY
    [InlineData(0x4C7, MotivoDeEscritura.Cancelado)]               // ERROR_CANCELLED
    [InlineData(0x33, MotivoDeEscritura.RutaDeRedInalcanzable)]    // ERROR_REM_NOT_LIST
    [InlineData(0x35, MotivoDeEscritura.RutaDeRedInalcanzable)]    // ERROR_BAD_NETPATH
    [InlineData(0x36, MotivoDeEscritura.RutaDeRedInalcanzable)]    // ERROR_NETWORK_BUSY
    [InlineData(0x3B, MotivoDeEscritura.RutaDeRedInalcanzable)]    // ERROR_UNEXP_NET_ERR
    [InlineData(0x40, MotivoDeEscritura.RutaDeRedInalcanzable)]    // ERROR_NETNAME_DELETED
    [InlineData(0x43, MotivoDeEscritura.RutaDeRedInalcanzable)]    // ERROR_BAD_NET_NAME
    [InlineData(0x47, MotivoDeEscritura.RutaDeRedInalcanzable)]    // ERROR_REQ_NOT_ACCEP
    [InlineData(0x4B1, MotivoDeEscritura.RutaDeRedInalcanzable)]   // ERROR_CONNECTION_UNAVAIL
    [InlineData(0x4C6, MotivoDeEscritura.RutaDeRedInalcanzable)]   // ERROR_NO_NETWORK
    [InlineData(0x4C9, MotivoDeEscritura.RutaDeRedInalcanzable)]   // ERROR_CONNECTION_REFUSED
    [InlineData(0x4CA, MotivoDeEscritura.RutaDeRedInalcanzable)]   // ERROR_CONNECTION_ABORTED
    [InlineData(0x4CD, MotivoDeEscritura.RutaDeRedInalcanzable)]   // ERROR_CONNECTION_INVALID
    [InlineData(0x4CF, MotivoDeEscritura.RutaDeRedInalcanzable)]   // ERROR_NETWORK_UNREACHABLE
    [InlineData(0x4D0, MotivoDeEscritura.RutaDeRedInalcanzable)]   // ERROR_HOST_UNREACHABLE
    [InlineData(0x4D2, MotivoDeEscritura.RutaDeRedInalcanzable)]   // ERROR_PORT_UNREACHABLE
    [InlineData(0x8CA, MotivoDeEscritura.RutaDeRedInalcanzable)]   // ERROR_NOT_CONNECTED
    [InlineData(0x02, MotivoDeEscritura.MedioRetirado)]            // ERROR_FILE_NOT_FOUND (el archivo recién creado ya no está)
    [InlineData(0x0F, MotivoDeEscritura.MedioRetirado)]            // ERROR_INVALID_DRIVE
    [InlineData(0x14, MotivoDeEscritura.MedioRetirado)]            // ERROR_BAD_UNIT
    [InlineData(0x15, MotivoDeEscritura.MedioRetirado)]            // ERROR_NOT_READY
    [InlineData(0x17, MotivoDeEscritura.MedioRetirado)]            // ERROR_CRC
    [InlineData(0x1B, MotivoDeEscritura.MedioRetirado)]            // ERROR_SECTOR_NOT_FOUND
    [InlineData(0x1D, MotivoDeEscritura.MedioRetirado)]            // ERROR_WRITE_FAULT
    [InlineData(0x1E, MotivoDeEscritura.MedioRetirado)]            // ERROR_READ_FAULT
    [InlineData(0x1F, MotivoDeEscritura.MedioRetirado)]            // ERROR_GEN_FAILURE
    [InlineData(0x1B1, MotivoDeEscritura.MedioRetirado)]           // ERROR_NO_SUCH_DEVICE
    [InlineData(0x3EE, MotivoDeEscritura.MedioRetirado)]           // ERROR_FILE_INVALID
    [InlineData(0x458, MotivoDeEscritura.MedioRetirado)]           // ERROR_NO_MEDIA_IN_DRIVE
    [InlineData(0x45D, MotivoDeEscritura.MedioRetirado)]           // ERROR_IO_DEVICE
    [InlineData(0x467, MotivoDeEscritura.MedioRetirado)]           // ERROR_DISK_OPERATION_FAILED
    [InlineData(0x48F, MotivoDeEscritura.MedioRetirado)]           // ERROR_DEVICE_NOT_CONNECTED
    [InlineData(0x651, MotivoDeEscritura.MedioRetirado)]           // ERROR_DEVICE_REMOVED
    public void PorCodigoDeWindows(int codigo, MotivoDeEscritura esperado)
    {
        Assert.Equal(esperado, Motivo(Io(codigo)));                                // el código pelado
        Assert.Equal(esperado, Motivo(Io(Hr(codigo))));                            // como lo arma .NET
        Assert.Equal(esperado, Motivo(new Win32Exception(codigo)));                // o como una Win32Exception
        Assert.Equal(esperado, Motivo(new IOException("envoltorio", Io(Hr(codigo)))));   // y dentro de otra excepción sin código propio
    }

    [Theory]
    [InlineData(0x03)]                 // ERROR_PATH_NOT_FOUND
    [InlineData(0x37)]                 // ERROR_DEV_NOT_EXIST
    [InlineData(0x79)]                 // ERROR_SEM_TIMEOUT
    public void LosCodigosQueDependenDeLaRuta_SonDeRedSoloEnUnaRutaDeRed(int codigo)
    {
        Assert.Equal(MotivoDeEscritura.MedioRetirado, Motivo(Io(Hr(codigo))));
        Assert.Equal(MotivoDeEscritura.MedioRetirado, Motivo(Io(Hr(codigo)), @"E:\Reportes"));
        Assert.Equal(MotivoDeEscritura.RutaDeRedInalcanzable, Motivo(Io(Hr(codigo)), @"\\servidor\reportes"));
        Assert.Equal(MotivoDeEscritura.RutaDeRedInalcanzable, Motivo(Io(codigo), "//servidor/reportes"));
    }

    [Theory]
    [InlineData(0x57)]                 // ERROR_INVALID_PARAMETER: no es de ninguna causa conocida
    [InlineData(0x1111)]
    [InlineData(0x570)]                // ERROR_FILE_CORRUPT: la memoria está dañada, pero «se retiró» sería mentira
    [InlineData(0x32)]                 // ERROR_NOT_SUPPORTED
    [InlineData(0x80)]
    [InlineData(0xB7)]                 // ERROR_ALREADY_EXISTS: el escritor lo resuelve solo; si llegara hasta aquí no es una causa que decir
    [InlineData(0x50)]                 // ERROR_FILE_EXISTS
    public void UnCodigoQueNoEstaEnLaTabla_EsOtro(int codigo)
    {
        Assert.Equal(MotivoDeEscritura.Otro, Motivo(Io(codigo)));
        Assert.Equal(MotivoDeEscritura.Otro, Motivo(Io(Hr(codigo))));
    }

    [Theory]
    [InlineData(unchecked((int)0x80131620))]       // COR_E_IO: el IOException genérico de .NET
    [InlineData(unchecked((int)0x80004005))]       // E_FAIL
    [InlineData(unchecked((int)0x80070000))]       // código 0
    [InlineData(0)]
    [InlineData(-1)]
    [InlineData(int.MinValue)]
    [InlineData(int.MaxValue)]
    [InlineData(0x10000)]
    [InlineData(unchecked((int)0x80030070))]       // el 0x70 de OTRA familia de HRESULT no es «disco lleno»
    public void UnHResultQueNoEsUnCodigoDeWindows_NoSeInterpreta(int hresult) => Assert.Equal(MotivoDeEscritura.Otro, Motivo(Io(hresult)));

    // ---------------------------------------------------------------------------------------------------- por el tipo

    [Fact]
    public void AccesoDenegado_EsSinPermiso_AMenosQueDigaSoloLectura()
    {
        Assert.Equal(MotivoDeEscritura.SinPermiso, Motivo(new UnauthorizedAccessException()));
        Assert.Equal(MotivoDeEscritura.SinPermiso, Motivo(new UnauthorizedAccessException("Access to the path is denied.")));
        Assert.Equal(MotivoDeEscritura.ProtegidoContraEscritura, Motivo(new UnauthorizedAccessException("The file system is read-only.")));
        Assert.Equal(MotivoDeEscritura.ProtegidoContraEscritura, Motivo(new UnauthorizedAccessException("Unidad de solo lectura.")));
        Assert.Equal(MotivoDeEscritura.ProtegidoContraEscritura, Motivo(new UnauthorizedAccessException("El medio está protegido contra escritura.")));
        Assert.Equal(MotivoDeEscritura.ProtegidoContraEscritura, Motivo(new UnauthorizedAccessException("x") { HResult = Hr(0x13) }));
        // «solo lectura» dentro de la RUTA no cuenta: es el nombre de una carpeta
        Assert.Equal(MotivoDeEscritura.SinPermiso, Motivo(new UnauthorizedAccessException("Access to the path 'C:\\solo lectura\\x' is denied.")));
    }

    [Fact]
    public void LaCancelacion_EsCancelado()
    {
        Assert.Equal(MotivoDeEscritura.Cancelado, Motivo(new OperationCanceledException()));
        Assert.Equal(MotivoDeEscritura.Cancelado, Motivo(new TaskCanceledException()));
        Assert.Equal(MotivoDeEscritura.Cancelado, Motivo(new IOException("envoltorio", new OperationCanceledException())));
    }

    [Fact]
    public void LosErroresDeRuta_SonNombreInvalido()
    {
        Assert.Equal(MotivoDeEscritura.NombreInvalido, Motivo(new PathTooLongException()));
        Assert.Equal(MotivoDeEscritura.NombreInvalido, Motivo(new ArgumentException("ruta con un carácter nulo")));
        Assert.Equal(MotivoDeEscritura.NombreInvalido, Motivo(new ArgumentNullException("path")));
        Assert.Equal(MotivoDeEscritura.NombreInvalido, Motivo(new NotSupportedException("El formato de la ruta no es compatible.")));
        Assert.Equal(MotivoDeEscritura.Otro, Motivo(new ArgumentOutOfRangeException("bufferSize")));           // eso es un error de programa, no del nombre
    }

    [Theory]
    [InlineData(null, MotivoDeEscritura.MedioRetirado)]
    [InlineData("", MotivoDeEscritura.MedioRetirado)]
    [InlineData(@"E:\Reportes", MotivoDeEscritura.MedioRetirado)]
    [InlineData(@"Z:\Compartida", MotivoDeEscritura.MedioRetirado)]                     // una letra mapeada no se reconoce por el texto
    [InlineData(@"\\?\C:\Reportes", MotivoDeEscritura.MedioRetirado)]
    [InlineData(@"\\servidor\reportes", MotivoDeEscritura.RutaDeRedInalcanzable)]
    [InlineData(@"\\servidor\reportes\2026", MotivoDeEscritura.RutaDeRedInalcanzable)]
    [InlineData("//servidor/reportes", MotivoDeEscritura.RutaDeRedInalcanzable)]
    [InlineData(@"\\?\UNC\servidor\reportes", MotivoDeEscritura.RutaDeRedInalcanzable)]
    public void UnaCarpetaQueYaNoEsta_EsLaRedSiLaRutaEsDeRed_YSiNoElMedio(string? ruta, MotivoDeEscritura esperado)
    {
        Assert.Equal(esperado, Motivo(new DirectoryNotFoundException(), ruta));
        Assert.Equal(esperado, Motivo(new DriveNotFoundException(), ruta));
    }

    [Fact]
    public void UnArchivoQueSeAcabaDeCrearYYaNoEsta_EsQueSeFueElMedio() => Assert.Equal(MotivoDeEscritura.MedioRetirado, Motivo(new FileNotFoundException("no está")));

    [Fact]
    public void UnTiempoAgotado_EsDeRedSoloEnUnaRutaDeRed()
    {
        Assert.Equal(MotivoDeEscritura.RutaDeRedInalcanzable, Motivo(new TimeoutException(), @"\\servidor\reportes"));
        Assert.Equal(MotivoDeEscritura.Otro, Motivo(new TimeoutException(), @"E:\Reportes"));
    }

    // ---------------------------------------------------------------------------------------------------- por el texto

    [Theory]
    [InlineData("Operation did not complete successfully because the file contains a virus or potentially unwanted software.")]
    [InlineData("La operación no se completó porque el archivo contiene un virus o software potencialmente no deseado.")]
    [InlineData("Blocked by VIRUS protection")]
    [InlineData("El antivirus bloqueó la escritura.")]
    [InlineData("Malware detectado.")]
    public void UnMensajeQueHablaDeVirus_EsAntivirus(string mensaje) => Assert.Equal(MotivoDeEscritura.BloqueadoPorAntivirus, Motivo(new IOException(mensaje)));

    [Fact]
    public void ElTextoDeUnaRuta_NoCuentaComoMensaje()
    {
        Assert.Equal(MotivoDeEscritura.Otro, Motivo(new IOException("No se pudo abrir 'C:\\virus\\informe.xlsx'.")));
        Assert.Equal(MotivoDeEscritura.Otro, Motivo(new IOException("No se pudo abrir \"D:\\malware\\x\".")));
    }

    [Fact]
    public void UnIOExceptionQueDiceSoloLectura_EsProtegido() =>
        Assert.Equal(MotivoDeEscritura.ProtegidoContraEscritura, Motivo(new IOException("Read-only file system")));

    [Fact]
    public void LoQueNoSeReconoce_EsOtro()
    {
        Assert.Equal(MotivoDeEscritura.Otro, Motivo(new IOException("algo raro")));
        Assert.Equal(MotivoDeEscritura.Otro, Motivo(new InvalidOperationException("estado imposible")));
        Assert.Equal(MotivoDeEscritura.Otro, Motivo(new Exception()));
        Assert.Equal(MotivoDeEscritura.Otro, Motivo(new OutOfMemoryException()));
    }

    // ---------------------------------------------------------------------------------------------------- cadenas de excepciones

    [Fact]
    public void SeMiraDentroDeLasInternas_CuandoLaExteriorNoDiceNada()
    {
        Assert.Equal(MotivoDeEscritura.SinEspacio, Motivo(new IOException("externa", new IOException("interna", Hr(0x70)))));
        Assert.Equal(MotivoDeEscritura.ProtegidoContraEscritura,
                     Motivo(new Exception("a", new InvalidOperationException("b", new IOException("c", Hr(0x13))))));
        Assert.Equal(MotivoDeEscritura.MedioRetirado, Motivo(new AggregateException(new InvalidOperationException("x"), Io(Hr(0x15)))));
    }

    [Fact]
    public void GanaLaMasExterna_QueSeaClasificable()
    {
        // la exterior ya dice «sin permiso»: no se busca una causa más profunda que la contradiga
        Assert.Equal(MotivoDeEscritura.SinPermiso, Motivo(new UnauthorizedAccessException("no", Io(Hr(0x70)))));
        // y entre varias internas de un AggregateException, la primera que diga algo
        Assert.Equal(MotivoDeEscritura.SinEspacio, Motivo(new AggregateException(Io(Hr(0x70)), Io(Hr(0x15)))));
    }

    [Fact]
    public void UnaCadenaMuyLarga_NoCuelgaNiDesbordaLaPila()
    {
        Exception e = Io(Hr(0x70));
        for (var i = 0; i < 20_000; i++) e = new Exception("capa", e);
        var fallo = MotivosDeEscritura.Clasificar(e);
        Assert.NotNull(fallo);                         // sea cual sea la respuesta, vuelve rápido y con un fallo
    }

    // ---------------------------------------------------------------------------------------------------- nunca lanza

    [Fact]
    public void Clasificar_NuncaLanza()
    {
        Assert.Equal(MotivoDeEscritura.Otro, MotivosDeEscritura.Clasificar(null!).Motivo);
        Assert.Equal(MotivoDeEscritura.Otro, MotivosDeEscritura.Clasificar(new MensajeQueFalla()).Motivo);                 // un Message que lanza
        Assert.Equal(MotivoDeEscritura.Otro, MotivosDeEscritura.Clasificar(new IOException("x", new MensajeQueFalla())).Motivo);
        foreach (var ruta in new[] { null, "", " ", "\0", @"\\", @"\\?\", new string('x', 100_000), "ñ:\\*?" })
            Assert.NotNull(MotivosDeEscritura.Clasificar(new IOException("x", Hr(0x79)), ruta));
        foreach (var hr in new[] { 0, -1, 1, 0xFFFF, 0x10000, int.MinValue, int.MaxValue, Hr(0), Hr(0xFFFF), unchecked((int)0xFFFFFFFF) })
            Assert.NotNull(MotivosDeEscritura.Clasificar(Io(hr), @"\\srv\x"));
    }

    // ---------------------------------------------------------------------------------------------------- ayudas públicas

    [Fact]
    public void CodigoDeWindows_SaleDelHResultDeLasTresFormas()
    {
        Assert.Equal(0x70, MotivosDeEscritura.CodigoDeWindows(Io(Hr(0x70))));
        Assert.Equal(0x70, MotivosDeEscritura.CodigoDeWindows(Io(0x70)));
        Assert.Equal(5, MotivosDeEscritura.CodigoDeWindows(new Win32Exception(5)));
        Assert.Equal(0x20, MotivosDeEscritura.CodigoDeWindows(new IOException("x", Hr(0x20))));
        Assert.Null(MotivosDeEscritura.CodigoDeWindows(new IOException("x")));                                   // el HResult genérico de .NET no es de Windows
        Assert.Null(MotivosDeEscritura.CodigoDeWindows(Io(0)));
        Assert.Null(MotivosDeEscritura.CodigoDeWindows(null));
    }

    [Fact]
    public void Detalle_LlevaElTipoElCodigoCompletoYElTextoDeCadaCapa()
    {
        var detalle = MotivosDeEscritura.Detalle(new IOException("capa externa", Io(Hr(0x70))));
        Assert.Contains("IOException", detalle);
        Assert.Contains("0x80070070", detalle);
        Assert.Contains("capa externa", detalle);
        Assert.Contains("fallo de prueba", detalle);
        Assert.Contains(" → ", detalle);
        Assert.Equal("sin detalle", MotivosDeEscritura.Detalle(null));
        Assert.Contains("MensajeQueFalla", MotivosDeEscritura.Detalle(new MensajeQueFalla()));                    // un Message que lanza no hace lanzar
    }

    [Fact]
    public void Detalle_NoTraeRutasNiElNombreDeQuienUsaElEquipo()
    {
        // Este detalle se anota en el registro local, que se entrega al nodo: Windows pone la ruta —con el usuario y las carpetas— en sus mensajes.
        var ex = new IOException(@"Access to the path 'C:\Users\María Pérez\Documents\reporte-grupo-8A.xlsx' is denied. Antes: E:\Reportes\8A\x.parte y \\colegio\reportes\8A\x.parte.",
            new UnauthorizedAccessException("Acceso denegado a la ruta de acceso \"D:\\Mis datos\\Ana\\y.csv\"."));
        var detalle = MotivosDeEscritura.Detalle(ex);
        Assert.Contains("IOException", detalle);
        Assert.Contains("UnauthorizedAccessException", detalle);
        Assert.Contains("is denied", detalle);                                                                    // lo que pasó se conserva…
        Assert.Contains("Acceso denegado a la ruta de acceso", detalle);
        foreach (var propio in new[] { "María", "Pérez", "Users", "Documents", "reporte-grupo", @"E:\", "Reportes", "colegio", "Mis datos", "Ana", ".parte", ".csv" })
            Assert.DoesNotContain(propio, detalle);                                                               // …y lo que identifica a alguien o a una carpeta, no
        Assert.Contains("«ruta»", detalle);
    }
}

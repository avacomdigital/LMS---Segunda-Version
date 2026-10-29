using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Avacom.Ops.Host.Dispositivo;
using Org.BouncyCastle.Math.EC.Rfc8032;
using static Avacom.Ops.Host.Dispositivo.FormatoSello;

namespace Avacom.Ops.Host.Tests;

/// <summary>Un equipo de mentira: claves en memoria (ECDSA P-256 y RSA-2048) que cumplen <see cref="IClavesDeEquipo"/>. Sin TPM, sin elevar, sin tocar el almacen de claves del usuario.</summary>
internal sealed class EquipoFalso : IClavesDeEquipo
{
    private ECDsa? _id = ECDsa.Create(ECCurve.NamedCurves.nistP256);
    private RSA? _cif = RSA.Create(2048);
    public bool EnTpm => false;
    public bool NoFirma { get; set; }
    public byte[]? IdentidadSpki() => _id?.ExportSubjectPublicKeyInfo();
    public byte[]? CifradoSpki() => _cif?.ExportSubjectPublicKeyInfo();
    public byte[]? Firmar(byte[] mensaje) => NoFirma || _id is null ? null : _id.SignData(mensaje, HashAlgorithmName.SHA256, DSASignatureFormat.IeeeP1363FixedFieldConcatenation);
    public byte[]? Desenvolver(byte[] envuelto) { try { return _cif?.Decrypt(envuelto, RSAEncryptionPadding.OaepSHA256); } catch (CryptographicException) { return null; } }
    public bool Crear() => true;
    public byte[]? EkPub() => [1, 2, 3, 4];
    public void PerderLasClaves() { _id = null; _cif = null; }
    public byte[] Huella => HuellaDe(IdentidadSpki()!);
}

/// <summary>El firmware de mentira: jamas toca el firmware real ni escribe nada. Por omision el equipo AVACOM de pruebas (AVACOM-OPS-00001234, atributos 0x7).</summary>
internal sealed class LectorUefiFalso : ILectorUefi
{
    public const string IdDePrueba = "AVACOM-OPS-00001234";
    public LecturaUefi Lectura { get; set; } = Con(IdDePrueba);
    public Exception? Lanza { get; set; }
    public int Lecturas { get; private set; }
    public string? NombrePedido { get; private set; }
    public Guid? ProveedorPedido { get; private set; }

    public static LecturaUefi Con(string id, uint atributos = IdentidadUefi.AtributosEsperados) => new(EstadoDeLecturaUefi.Leida, Encoding.UTF8.GetBytes(id), atributos);

    public LecturaUefi Leer(string nombre, Guid proveedor)
    {
        Lecturas++;
        NombrePedido = nombre;
        ProveedorPedido = proveedor;
        return Lanza is null ? Lectura : throw Lanza;
    }
}

/// <summary>La estacion de AVACOM, en C#: firma sellos de verdad (Ed25519) para probar el verificador del Host sin depender del Python.</summary>
internal sealed class EstacionDePrueba
{
    public byte[] Privada { get; } = RandomNumberGenerator.GetBytes(32);
    public byte[] Publica { get; } = new byte[32];
    public const string Kid = "sello-prueba";
    public IReadOnlyDictionary<string, byte[]> Llaves => new Dictionary<string, byte[]> { [Kid] = Publica };

    public EstacionDePrueba() => Ed25519.GeneratePublicKey(Privada, 0, Publica, 0);

    private byte[] Firmar(byte[] cuerpo, byte[]? privada = null)
    {
        var firma = new byte[64];
        Ed25519.Sign(privada ?? Privada, 0, cuerpo, 0, cuerpo.Length, firma, 0);
        return [.. cuerpo, .. firma];
    }

    private static byte[] Tlv(byte[] magic, string kid, SortedDictionary<int, (byte[] Valor, bool Critica)> campos)
    {
        var k = Encoding.ASCII.GetBytes(kid);
        var ms = new MemoryStream();
        ms.Write(magic); ms.Write([0, 1, (byte)k.Length]); ms.Write(k);
        foreach (var (t, (v, c)) in campos)
        {
            var etiqueta = t | (c ? 0x8000 : 0);
            ms.Write([(byte)(etiqueta >> 8), (byte)etiqueta, (byte)(v.Length >> 8), (byte)v.Length]); ms.Write(v);
        }
        return ms.ToArray();
    }

    private static byte[] U64(long n) { var b = new byte[8]; for (var i = 7; i >= 0; i--) { b[i] = (byte)n; n >>= 8; } return b; }

    public byte[] Sello(byte[] claveHuella, string serie = "OPS-0001", long emitido = 1_790_000_000_000, long vence = 0, string kid = Kid, byte[]? privada = null, string mac = "00:11:22:33:44:55",
                        string? uefiId = LectorUefiFalso.IdDePrueba)
    {
        var campos = new SortedDictionary<int, (byte[], bool)>
        {
            [TId] = (RandomNumberGenerator.GetBytes(16), true), [TSerie] = (Encoding.ASCII.GetBytes(serie), false), [TOrigen] = ([1], true), [TClaveHuella] = (claveHuella, true),
            [TEmitido] = (U64(emitido), true), [TVence] = (U64(vence), true), [TEvidencia] = ([1], true),
        };
        if (mac.Length > 0) campos[TMac] = (Encoding.ASCII.GetBytes(mac), false);
        if (!string.IsNullOrEmpty(uefiId)) campos[TUefiId] = (Encoding.ASCII.GetBytes(uefiId), false);
        return Firmar(Tlv(MagicSello, kid, campos), privada);
    }

    public byte[] FirmarClave(SortedDictionary<int, (byte[], bool)> campos, string? firmante = null)
    {
        if (firmante is null) return Firmar(Tlv(MagicClave, Kid, campos));
        var otra = RandomNumberGenerator.GetBytes(32);        // un firmante que no es el de sello: la llave publica no esta entre las que el Host confia
        return Firmar(Tlv(MagicClave, Kid, campos), otra);
    }

    public byte[] Revocados(long numero, params byte[][] huellas)
    {
        var campos = new SortedDictionary<int, (byte[], bool)> { [RNumero] = ([(byte)(numero >> 24), (byte)(numero >> 16), (byte)(numero >> 8), (byte)numero], true), [REmitida] = (U64(1_790_000_000_000), true),
                                                                  [RHuellas] = (huellas.OrderBy(h => Convert.ToHexString(h), StringComparer.Ordinal).SelectMany(h => h).ToArray(), true) };
        return Firmar(Tlv(MagicRevocados, Kid, campos));
    }
}

public class SelloVectoresTests
{
    private static string RutaDeVectores()
    {
        var carpeta = AppContext.BaseDirectory;
        while (carpeta is not null && !File.Exists(Path.Combine(carpeta, "Fixtures", "sello", "vectores.json")))
            carpeta = Path.GetDirectoryName(carpeta);
        var local = carpeta is null ? null : Path.Combine(carpeta, "Fixtures", "sello", "vectores.json");
        return local ?? Path.Combine(Directory.GetCurrentDirectory(), "Fixtures", "sello", "vectores.json");
    }

    /// <summary>La prueba diferencial: el backend (Python) y el Host (C#) leen los MISMOS archivos y dan el mismo veredicto y el mismo motivo, en los 316 casos (incluidas 300 mutaciones).</summary>
    [Fact]
    public void ElHostDaElMismoVeredictoQueElBackendEnCadaVector()
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(RutaDeVectores()));
        var llaves = new Dictionary<string, byte[]> { [doc.RootElement.GetProperty("kid").GetString()!] = Convert.FromHexString(doc.RootElement.GetProperty("publica").GetString()!) };
        var casos = doc.RootElement.GetProperty("casos").EnumerateArray().ToList();
        Assert.True(casos.Count >= 300);
        var distintos = new List<string>();
        foreach (var c in casos)
        {
            byte[]? sello = c.GetProperty("sello").ValueKind == JsonValueKind.Null ? null : Convert.FromBase64String(c.GetProperty("sello").GetString()!);
            byte[]? equipo = c.GetProperty("equipo").ValueKind == JsonValueKind.Null ? null : Convert.FromHexString(c.GetProperty("equipo").GetString()!);
            bool? posesion = c.GetProperty("posesion").ValueKind == JsonValueKind.Null ? null : c.GetProperty("posesion").GetBoolean();
            var revocados = c.GetProperty("revocados").EnumerateArray().Select(x => x.GetString()!).ToHashSet();
            var v = Evaluar(sello, llaves, equipo, posesion, revocados, c.GetProperty("ahora").GetInt64());
            var esperado = (c.GetProperty("estado").GetString(), c.GetProperty("motivo").GetString());
            if ((v.Estado, v.Motivo) != esperado) distintos.Add($"{c.GetProperty("nombre").GetString()}: C# {v.Estado}/{v.Motivo} · Python {esperado.Item1}/{esperado.Item2}");
        }
        Assert.True(distintos.Count == 0, string.Join("\n", distintos));
    }

    [Fact]
    public void LosRevocadosDelVectorSeLeenIgual()
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(RutaDeVectores()));
        var llaves = new Dictionary<string, byte[]> { [doc.RootElement.GetProperty("kid").GetString()!] = Convert.FromHexString(doc.RootElement.GetProperty("publica").GetString()!) };
        var r = doc.RootElement.GetProperty("revocados");
        var (numero, huellas) = LeerRevocados(Convert.FromBase64String(r.GetProperty("archivo").GetString()!), llaves);
        Assert.Equal(r.GetProperty("numero").GetInt64(), numero);
        Assert.Equal(r.GetProperty("huellas").EnumerateArray().Select(x => x.GetString()!).Order().ToList(), huellas.Order().ToList());
        var alterado = Assert.Throws<Rechazo>(() => LeerRevocados(Convert.FromBase64String(doc.RootElement.GetProperty("revocados_alterado").GetString()!), llaves));
        Assert.Equal("firma_invalida", alterado.Motivo);
    }
}

public class PuertaDeDispositivoTests : IDisposable
{
    private readonly string _tmp = Path.Combine(Path.GetTempPath(), "avacom-sello-" + Guid.NewGuid().ToString("N"));
    private readonly EstacionDePrueba _estacion = new();
    private readonly EquipoFalso _equipo = new();
    private readonly LectorUefiFalso _uefi = new();
    private string Sello => Path.Combine(_tmp, "Config", "sello");
    private string Senal => Path.Combine(_tmp, "Config", "dispositivo.json");

    public PuertaDeDispositivoTests() => Directory.CreateDirectory(Sello);
    public void Dispose() { try { Directory.Delete(_tmp, true); } catch (IOException) { } }

    private void Poner(byte[] sello) => File.WriteAllBytes(Path.Combine(Sello, PuertaDeDispositivo.ArchivoDeSello), sello);

    private PuertaDeDispositivo.Resultado Verificar() => PuertaDeDispositivo.Verificar(_equipo, _estacion.Llaves, Sello, 1_790_000_000_001, _uefi);

    [Fact]
    public void UnEquipoConSelloValidoYSuClaveEsAutenticado()
    {
        Poner(_estacion.Sello(_equipo.Huella));
        var r = Verificar();
        Assert.Equal(Autenticado, r.Estado);
        Assert.Equal("OPS-0001", r.Sello!.Serie);
    }

    [Fact] public void SinArchivoDeSelloNoEsAutenticado() => Assert.Equal(SinSello, Verificar().Estado);

    [Fact]
    public void UnSelloCopiadoDeOtroEquipoNoSirve()
    {
        Poner(_estacion.Sello(new EquipoFalso().Huella));
        Assert.Equal(ClaveDistinta, Verificar().Estado);
    }

    [Fact]
    public void UnEquipoQueNoPuedeFirmarEsNoVerificableNoFraude()
    {
        Poner(_estacion.Sello(_equipo.Huella));
        _equipo.NoFirma = true;
        Assert.Equal(NoVerificable, Verificar().Estado);
    }

    [Fact]
    public void UnEquipoSinClavesConSelloEsNoVerificable()
    {
        Poner(_estacion.Sello(_equipo.Huella));
        _equipo.PerderLasClaves();
        Assert.Equal(NoVerificable, Verificar().Estado);
    }

    [Fact]
    public void UnSelloFirmadoPorOtraLlaveEsInvalido()
    {
        Poner(_estacion.Sello(_equipo.Huella, privada: RandomNumberGenerator.GetBytes(32)));
        var r = Verificar();
        Assert.Equal((SelloInvalido, "firma_invalida"), (r.Estado, r.Motivo));
    }

    [Fact]
    public void UnSelloVencidoEsInvalido()
    {
        Poner(_estacion.Sello(_equipo.Huella, vence: 1_790_000_000_000 + 1));
        var r = PuertaDeDispositivo.Verificar(_equipo, _estacion.Llaves, Sello, 1_790_000_000_000 + 2, _uefi);
        Assert.Equal((SelloInvalido, "vencido"), (r.Estado, r.Motivo));
    }

    [Fact]
    public void UnaListaDeRevocadosConLaClaveDelEquipoLoRevoca()
    {
        Poner(_estacion.Sello(_equipo.Huella));
        File.WriteAllBytes(Path.Combine(Sello, PuertaDeDispositivo.ArchivoDeRevocados), _estacion.Revocados(5, _equipo.Huella));
        var r = Verificar();
        Assert.Equal((Revocado, 5L), (r.Estado, r.RevocadosNumero));
    }

    [Fact]
    public void LaMacYElSerieNoDecidenNada()
    {
        foreach (var (serie, mac) in new[] { ("OPS-9999", ""), ("X", "AA:BB:CC:DD:EE:FF"), ("OPS-0001", "00:11:22:33:44:55") })
        {
            Poner(_estacion.Sello(_equipo.Huella, serie: serie, mac: mac));
            Assert.Equal(Autenticado, Verificar().Estado);
        }
    }

    [Fact]
    public void LaSenalNoLlevaDatosDePersonasNiLicencias()
    {
        Poner(_estacion.Sello(_equipo.Huella));
        var texto = PuertaDeDispositivo.Senal(Verificar(), DateTime.UtcNow);
        using var doc = JsonDocument.Parse(texto);
        Assert.Equal("autenticado", doc.RootElement.GetProperty("estado").GetString());
        Assert.Equal(["version", "verificado", "estado", "motivo", "serie", "origen", "evidencia", "sello_id", "kid", "clave_huella", "en_tpm", "revocados", "codigo"], doc.RootElement.EnumerateObject().Select(p => p.Name).ToArray());
    }

    // ------------------------------------------------------------------------------------------------- instalar
    [Fact]
    public void InstalarNoPisaUnSelloBuenoConBasuraNiAceptaUnoAjeno()
    {
        var bueno = _estacion.Sello(_equipo.Huella);
        var usb = Path.Combine(_tmp, "usb");
        Directory.CreateDirectory(usb);
        File.WriteAllBytes(Path.Combine(usb, "equipo.avsello"), bueno);
        var (n, _) = PuertaDeDispositivo.Instalar(PuertaDeDispositivo.Candidatas(usb), _estacion.Llaves, Sello);
        Assert.Equal(1, n);
        Assert.Equal(Autenticado, Verificar().Estado);

        var malo = (byte[])bueno.Clone();
        malo[^1] ^= 1;
        File.WriteAllBytes(Path.Combine(usb, "equipo.avsello"), malo);
        var (n2, mensajes) = PuertaDeDispositivo.Instalar(PuertaDeDispositivo.Candidatas(usb), _estacion.Llaves, Sello);
        Assert.Equal(0, n2);
        Assert.Contains("firma_invalida", string.Join(" ", mensajes));
        Assert.Equal(bueno, File.ReadAllBytes(Path.Combine(Sello, PuertaDeDispositivo.ArchivoDeSello)));
    }

    [Fact]
    public void UnaListaDeRevocadosMasViejaNoReemplazaALaMasNueva()
    {
        var usb = Path.Combine(_tmp, "usb");
        Directory.CreateDirectory(usb);
        File.WriteAllBytes(Path.Combine(usb, "r5.avrev"), _estacion.Revocados(5, new byte[32]));
        Assert.Equal(1, PuertaDeDispositivo.Instalar(PuertaDeDispositivo.Candidatas(usb), _estacion.Llaves, Sello).Instalados);
        File.Delete(Path.Combine(usb, "r5.avrev"));
        File.WriteAllBytes(Path.Combine(usb, "r4.avrev"), _estacion.Revocados(4));
        Assert.Equal(0, PuertaDeDispositivo.Instalar(PuertaDeDispositivo.Candidatas(usb), _estacion.Llaves, Sello).Instalados);
        Assert.Equal(5L, LeerRevocados(File.ReadAllBytes(Path.Combine(Sello, PuertaDeDispositivo.ArchivoDeRevocados)), _estacion.Llaves).Numero);
    }

    // ------------------------------------------------------------------------------------------------- la puerta del instalador
    private static Registro Reg() => new("dispositivo-pruebas.log");

    [Fact]
    public void LaPuertaSinSelloSeNiegaYDejaLaSolicitudEnLaMemoria()
    {
        var usb = Path.Combine(_tmp, "usbvacia");
        Directory.CreateDirectory(usb);
        var codigo = Verbos.PuertaCon(_equipo, _estacion.Llaves, Sello, Senal, Reg(), () => [usb], _uefi);
        Assert.Equal(PuertaDeDispositivo.SalidaSinSello, codigo);
        var solicitud = Path.Combine(usb, "AVACOM", PuertaDeDispositivo.ArchivoDeSolicitud);
        Assert.True(File.Exists(solicitud));
        Assert.StartsWith("AVSO", Encoding.ASCII.GetString(File.ReadAllBytes(solicitud), 0, 4));
        Assert.False(File.Exists(Path.Combine(Sello, PuertaDeDispositivo.ArchivoDeSello)));
    }

    [Fact]
    public void LaPuertaRecogeElSelloDeLaMemoriaYDejaPasar()
    {
        var usb = Path.Combine(_tmp, "usbconsello");
        Directory.CreateDirectory(usb);
        File.WriteAllBytes(Path.Combine(usb, "OPS-0001.avsello"), _estacion.Sello(_equipo.Huella));
        Assert.Equal(0, Verbos.PuertaCon(_equipo, _estacion.Llaves, Sello, Senal, Reg(), () => [usb], _uefi));
        Assert.Equal("autenticado", JsonDocument.Parse(File.ReadAllText(Senal)).RootElement.GetProperty("estado").GetString());
    }

    [Fact]
    public void LaPuertaSeNiegaConElSelloDeOtroEquipo()
    {
        var usb = Path.Combine(_tmp, "usbajena");
        Directory.CreateDirectory(usb);
        File.WriteAllBytes(Path.Combine(usb, "OPS-0001.avsello"), _estacion.Sello(new EquipoFalso().Huella));
        Assert.Equal(PuertaDeDispositivo.SalidaClaveDistinta, Verbos.PuertaCon(_equipo, _estacion.Llaves, Sello, Senal, Reg(), () => [usb], _uefi));
    }

    [Fact]
    public void SinLlavesCompiladasElVerbosDiceNoVerificable()
    {
        Assert.Equal(PuertaDeDispositivo.SalidaNoVerificable, Verbos.VerificarCon(_equipo, new Dictionary<string, byte[]>(), Sello, Senal, Reg(), escribirMensaje: false, _uefi));
    }

    [Fact]
    public void ElMarcadorDeDesarrolloDeUnUsuarioEstandarNoApagaLaPuerta()
    {
        // Un archivo creado por quien corre las pruebas (no por «Administradores» ni SYSTEM) NO vale: un usuario puede crear el archivo, pero no ser su dueno como administracion.
        var carpeta = Path.Combine(_tmp, "ProgramData", "AVACOM");
        Directory.CreateDirectory(carpeta);
        File.WriteAllBytes(Path.Combine(carpeta, PuertaDeDispositivo.MarcadorDeDesarrollo), []);
        using var identidad = System.Security.Principal.WindowsIdentity.GetCurrent();
        var esAdministracion = identidad.Owner is { } d && (d.IsWellKnown(System.Security.Principal.WellKnownSidType.BuiltinAdministratorsSid) || d.IsWellKnown(System.Security.Principal.WellKnownSidType.LocalSystemSid));
        Assert.Equal(esAdministracion, PuertaDeDispositivo.HayMarcadorDeDesarrollo(carpeta));
        Assert.False(PuertaDeDispositivo.HayMarcadorDeDesarrollo(Path.Combine(_tmp, "no-existe")));
    }

    // ------------------------------------------------------------------------------------------------- identidad UEFI (AVACOM_DEVICE_ID)
    private ResultadoDeIdentidad Identidad() => new IdentidadDeDispositivo(_equipo, _estacion.Llaves, Sello, _uefi, () => 1_790_000_000_001).Validar();

    [Fact]
    public void VariableValidaYSelloQueLaAutorizaPermiteLaEjecucion()
    {
        Poner(_estacion.Sello(_equipo.Huella));
        var r = Identidad();
        Assert.Equal((EstadoDeIdentidad.Autorizado, "AVC-UEFI-00"), (r.Estado, r.Codigo));
        Assert.Equal(("AVACOM_DEVICE_ID", new Guid("8b7f9c20-3e51-4c8a-a7d1-91c62e0f4b35")), (_uefi.NombrePedido, _uefi.ProveedorPedido));
    }

    [Fact]
    public void CadaEquipoTieneElSuyo_ElIdentificadorDePruebasNoEstaEnElCodigo()
    {
        _uefi.Lectura = LectorUefiFalso.Con("AVACOM-OPS-00009999");
        Poner(_estacion.Sello(_equipo.Huella, uefiId: "AVACOM-OPS-00009999"));
        Assert.True(Identidad().Autorizado);
    }

    [Fact]
    public void LaVariableInexistenteBloquea()
    {
        Poner(_estacion.Sello(_equipo.Huella));
        _uefi.Lectura = new LecturaUefi(EstadoDeLecturaUefi.VariableNoEncontrada, CodigoDeSistema: 203);
        var r = Identidad();
        Assert.Equal((EstadoDeIdentidad.VariableNoEncontrada, "AVC-UEFI-01"), (r.Estado, r.Codigo));
        Assert.Equal(PuertaDeDispositivo.SalidaIdentidadUefi, PuertaDeDispositivo.Salida(Verificar().Estado));
    }

    [Fact]
    public void ElGuidIncorrectoNoEncuentraLaVariable_SeLeeSoloConElGuidAvacom()
    {
        // Un firmware que solo tiene la variable bajo OTRO GUID responde «no encontrada» para el nuestro: el lector se invoca siempre con el GUID exacto.
        Poner(_estacion.Sello(_equipo.Huella));
        var por = new LectorPorGuid(new Guid("11111111-2222-3333-4444-555555555555"), LectorUefiFalso.Con(LectorUefiFalso.IdDePrueba));
        var r = PuertaDeDispositivo.Verificar(_equipo, _estacion.Llaves, Sello, 1_790_000_000_001, por);
        Assert.Equal((IdentidadUefiRechazada, "variable_no_encontrada"), (r.Estado, r.Motivo));
        var bueno = new LectorPorGuid(IdentidadUefi.Proveedor, LectorUefiFalso.Con(LectorUefiFalso.IdDePrueba));
        Assert.Equal(Autenticado, PuertaDeDispositivo.Verificar(_equipo, _estacion.Llaves, Sello, 1_790_000_000_001, bueno).Estado);
    }

    private sealed class LectorPorGuid(Guid guidDeLaVariable, LecturaUefi lectura) : ILectorUefi
    {
        public LecturaUefi Leer(string nombre, Guid proveedor) => proveedor == guidDeLaVariable && nombre == "AVACOM_DEVICE_ID" ? lectura : new LecturaUefi(EstadoDeLecturaUefi.VariableNoEncontrada, CodigoDeSistema: 203);
    }

    [Theory]
    [InlineData("", "vacio")]
    [InlineData("AVACOM-OPS-", "formato")]
    [InlineData("AVACOM-OPS-1234", "formato")]
    [InlineData("avacom-ops-00001234", "formato")]
    [InlineData("XAVACOM-OPS-00001234", "formato")]
    [InlineData("AVACOM-OPS-00001234 ", "formato")]
    [InlineData("AVACOM-OPS-0000123!", "formato")]
    [InlineData("DS2015", "formato")]
    [InlineData("AVACOM-OPS-00001234\n", "formato")]
    public void UnIdentificadorVacioOMalFormadoBloquea(string id, string motivo)
    {
        Poner(_estacion.Sello(_equipo.Huella));
        _uefi.Lectura = LectorUefiFalso.Con(id);
        var r = Verificar();
        Assert.Equal((IdentidadUefiRechazada, motivo), (r.Estado, r.Motivo));
        Assert.Equal(EstadoDeIdentidad.IdentificadorInvalido, r.Identidad);
    }

    [Fact]
    public void UnIdentificadorQueNoEsUtf8OQueSePasaDeLargoBloquea()
    {
        Poner(_estacion.Sello(_equipo.Huella));
        _uefi.Lectura = new LecturaUefi(EstadoDeLecturaUefi.Leida, [0xFF, 0xFE, 0x41], 7);
        Assert.Equal("no_es_utf8", Verificar().Motivo);
        _uefi.Lectura = new LecturaUefi(EstadoDeLecturaUefi.Leida, Encoding.ASCII.GetBytes("AVACOM-OPS-" + new string('0', 80)), 7);
        Assert.Equal("demasiado_largo", Verificar().Motivo);
        _uefi.Lectura = new LecturaUefi(EstadoDeLecturaUefi.ValorDemasiadoLargo, CodigoDeSistema: 122);
        Assert.Equal(EstadoDeIdentidad.IdentificadorInvalido, Verificar().Identidad);
    }

    [Fact]
    public void ElTerminadorNuloQueDejaElFirmwareSeIgnora()
    {
        Poner(_estacion.Sello(_equipo.Huella));
        _uefi.Lectura = new LecturaUefi(EstadoDeLecturaUefi.Leida, [.. Encoding.ASCII.GetBytes(LectorUefiFalso.IdDePrueba), 0, 0], 7);
        Assert.Equal(Autenticado, Verificar().Estado);
    }

    [Theory]
    [InlineData(0u)]
    [InlineData(0x1u)]
    [InlineData(0x3u)]
    [InlineData(0x6u)]
    public void LosAtributosIncorrectosBloquean(uint atributos)
    {
        Poner(_estacion.Sello(_equipo.Huella));
        _uefi.Lectura = LectorUefiFalso.Con(LectorUefiFalso.IdDePrueba, atributos);
        var r = Identidad();
        Assert.Equal((EstadoDeIdentidad.AtributosInvalidos, "AVC-UEFI-03"), (r.Estado, r.Codigo));
    }

    [Fact]
    public void UnFirmwareQueAdemasProtegeLaVariableConEscrituraAutenticadaSeAcepta()
    {
        Poner(_estacion.Sello(_equipo.Huella));
        _uefi.Lectura = LectorUefiFalso.Con(LectorUefiFalso.IdDePrueba, 0x27);        // 0x7 + escritura autenticada con tiempo
        Assert.Equal(Autenticado, Verificar().Estado);
    }

    [Fact]
    public void UnIdentificadorValidoSinAutorizacionDeLicenciaBloquea()
    {
        // Tres formas de «no autorizado»: no hay sello; el sello es de otro identificador; el sello no trae ninguno.
        var r0 = Identidad();
        Assert.Equal(EstadoDeIdentidad.DispositivoSinLicencia, r0.Estado);

        Poner(_estacion.Sello(_equipo.Huella, uefiId: "AVACOM-OPS-00004321"));
        var r1 = Verificar();
        Assert.Equal((IdentidadUefiRechazada, "dispositivo_sin_licencia"), (r1.Estado, r1.Motivo));
        Assert.Equal((EstadoDeIdentidad.DispositivoSinLicencia, "AVC-UEFI-04"), (r1.Identidad, r1.CodigoDeDiagnostico));

        Poner(_estacion.Sello(_equipo.Huella, uefiId: ""));
        var r2 = Verificar();
        Assert.Equal((IdentidadUefiRechazada, "sello_sin_identificador"), (r2.Estado, r2.Motivo));
        Assert.Equal(EstadoDeIdentidad.DispositivoSinLicencia, r2.Identidad);
    }

    [Fact]
    public void FormatoValidoNoBastaParaAutorizar_UnaVariableCreadaPorOtroSinSelloNoPasa()
    {
        // Alguien graba AVACOM-OPS-00001234 en un equipo ajeno: el formato cuadra, pero no hay sello firmado por AVACOM para el: bloqueado.
        Assert.Equal(SinSello, Verificar().Estado);
        // Y con el sello COPIADO de un equipo legitimo (mismo identificador) falla la clave del TPM.
        Poner(_estacion.Sello(new EquipoFalso().Huella));
        Assert.Equal(ClaveDistinta, Verificar().Estado);
    }

    [Fact]
    public void ElErrorDeAccesoALaVariableBloqueaYDejaDiagnostico()
    {
        Poner(_estacion.Sello(_equipo.Huella));
        _uefi.Lectura = new LecturaUefi(EstadoDeLecturaUefi.AccesoDenegado, CodigoDeSistema: 1314);
        var r = Identidad();
        Assert.Equal((EstadoDeIdentidad.AccesoDenegado, "AVC-UEFI-06"), (r.Estado, r.Codigo));
        Assert.Equal("identidad_uefi/privilegio_1314", r.Motivo);
        var registro = Reg();
        Assert.Equal(PuertaDeDispositivo.SalidaIdentidadUefi, Verbos.VerificarCon(_equipo, _estacion.Llaves, Sello, Senal, registro, escribirMensaje: true, _uefi));
        Assert.Contains("AVC-UEFI-06", File.ReadAllText(Path.Combine(_tmp, "Logs", "dispositivo-estado.json")));
    }

    [Fact]
    public void ElFirmwareLegacyBiosBloqueaYSeRegistraLaIncompatibilidad()
    {
        Poner(_estacion.Sello(_equipo.Huella));
        _uefi.Lectura = new LecturaUefi(EstadoDeLecturaUefi.FirmwareNoSoportado, CodigoDeSistema: 1);
        var r = Identidad();
        Assert.Equal((EstadoDeIdentidad.FirmwareNoSoportado, "AVC-UEFI-05"), (r.Estado, r.Codigo));
        Assert.Contains("firmware_no_uefi", r.Motivo);
    }

    [Fact]
    public void UnaExcepcionAlLeerElFirmwareBloqueaSinFiltrarLaExcepcion()
    {
        Poner(_estacion.Sello(_equipo.Huella));
        _uefi.Lanza = new System.ComponentModel.Win32Exception(31);
        var r = Identidad();
        Assert.Equal((EstadoDeIdentidad.ErrorDeLectura, "AVC-UEFI-07"), (r.Estado, r.Codigo));
        Assert.DoesNotContain("Win32", r.Motivo, StringComparison.Ordinal);
    }

    [Fact]
    public void SinInternetNiServiciosExternosElDispositivoAutorizadoPasa()
    {
        // El camino completo (firmware falso + sello + clave del equipo + lista de revocados local) no abre ninguna conexion: todo es local. Se comprueba que corre con la red «cortada» a nivel de proceso.
        Poner(_estacion.Sello(_equipo.Huella));
        using var _ = new SinRed();
        Assert.True(Identidad().Autorizado);
    }

    private sealed class SinRed : IDisposable
    {
        private readonly string? _antes = Environment.GetEnvironmentVariable("HTTP_PROXY");
        public SinRed() => Environment.SetEnvironmentVariable("HTTP_PROXY", "http://127.0.0.1:9");
        public void Dispose() => Environment.SetEnvironmentVariable("HTTP_PROXY", _antes);
    }

    [Fact]
    public void LaAutorizacionSobreviveAUnReinicio_LaVariableEsPersistenteYElEstadoSeRecalculaDeCero()
    {
        // «Reinicio»: el proceso empieza otra vez sin estado en memoria; la variable (NV) y el sello (archivo) siguen. Dos instancias nuevas, mismo resultado.
        Poner(_estacion.Sello(_equipo.Huella));
        for (var vuelta = 0; vuelta < 3; vuelta++)
            Assert.True(new IdentidadDeDispositivo(_equipo, _estacion.Llaves, Sello, new LectorUefiFalso(), () => 1_790_000_000_001).Validar().Autorizado);
        Assert.Equal(0x7u, IdentidadUefi.AtributosEsperados);
    }

    [Fact]
    public void LaIdentidadDeFirmwareSeLeeAntesQueElSelloYSinIdentidadNoSeDejaSolicitud()
    {
        var usb = Path.Combine(_tmp, "usbsinuefi");
        Directory.CreateDirectory(usb);
        _uefi.Lectura = new LecturaUefi(EstadoDeLecturaUefi.VariableNoEncontrada, CodigoDeSistema: 203);
        var codigo = Verbos.PuertaCon(_equipo, _estacion.Llaves, Sello, Senal, Reg(), () => [usb], _uefi);
        Assert.Equal(PuertaDeDispositivo.SalidaIdentidadUefi, codigo);                      // instalacion detenida
        Assert.False(Directory.Exists(Path.Combine(usb, "AVACOM")));                          // un equipo ajeno no recibe una solicitud para llevar a AVACOM
    }

    [Fact]
    public void UnEquipoConIdentidadValidaPeroSelloDeOtroIdentificadorRecibeSolicitudConSuIdentidad()
    {
        var usb = Path.Combine(_tmp, "usbotroid");
        Directory.CreateDirectory(usb);
        Poner(_estacion.Sello(_equipo.Huella, uefiId: "AVACOM-OPS-00004321"));
        Assert.Equal(PuertaDeDispositivo.SalidaIdentidadUefi, Verbos.PuertaCon(_equipo, _estacion.Llaves, Sello, Senal, Reg(), () => [usb], _uefi));
        var bytes = File.ReadAllBytes(Path.Combine(usb, "AVACOM", PuertaDeDispositivo.ArchivoDeSolicitud));
        Assert.Contains(LectorUefiFalso.IdDePrueba, Encoding.ASCII.GetString(bytes));
    }

    [Fact]
    public void NoSePuedePedirSelloSinUnaIdentidadUefiValida()
    {
        // El verbo solicitar-sello: sin identidad leida no hay solicitud (la estacion tampoco la sellaria).
        var uefi = IdentidadUefi.Leer(new LectorUefiDeEnsayo(null));
        Assert.Equal(EstadoDeIdentidad.VariableNoEncontrada, uefi.Fallo);
        Assert.Equal(LectorUefiFalso.IdDePrueba, IdentidadUefi.Leer(new LectorUefiDeEnsayo(LectorUefiFalso.IdDePrueba)).Id);
    }

    [Fact]
    public void ElServicioNoLevantaElBackendDeUnDispositivoNoAutorizado()
    {
        PuertaDelServicio.OlvidarElUltimo();
        var registro = Reg();
        Assert.False(PuertaDelServicio.Permite(registro, _estacion.Llaves, _equipo, Sello, Senal, _uefi));          // sin sello
        Poner(_estacion.Sello(_equipo.Huella));
        Assert.True(PuertaDelServicio.Permite(registro, _estacion.Llaves, _equipo, Sello, Senal, _uefi));
        _uefi.Lectura = new LecturaUefi(EstadoDeLecturaUefi.VariableNoEncontrada, CodigoDeSistema: 203);
        Assert.False(PuertaDelServicio.Permite(registro, _estacion.Llaves, _equipo, Sello, Senal, _uefi));
        Assert.True(PuertaDelServicio.Permite(registro, new Dictionary<string, byte[]>(), _equipo, Sello, Senal, _uefi));     // una compilacion sin llaves de sello (desarrollo) no tiene puerta
    }

    [Fact]
    public void ElMensajeObligatorioEsExactamenteElDelPrompt()
    {
        Assert.Equal("El LMS solo puede correr en dispositivos AVACOM. En caso de tratarse de un error, contacte con su distribuidor o canales de soporte autorizados.", IdentidadUefi.MensajeDeRechazo);
    }

    // ------------------------------------------------------------------------------------------------- la solicitud
    [Fact]
    public void LaSolicitudSeEscribeYLaFirmaElEquipoConSuClave()
    {
        var (codigo, ruta) = PuertaDeDispositivo.Solicitar(_equipo, Path.Combine(_tmp, "salida"), "OPS-0001", 1_790_000_000_000, LectorUefiFalso.IdDePrueba);
        Assert.Equal(0, codigo);
        var datos = File.ReadAllBytes(ruta);
        Assert.StartsWith("AVSO", Encoding.ASCII.GetString(datos, 0, 4));
        // la firma son los ultimos 64 bytes y la verifica la clave publica del equipo (lo que hace el backend/la estacion al leer la solicitud)
        using var ec = ECDsa.Create();
        ec.ImportSubjectPublicKeyInfo(_equipo.IdentidadSpki()!, out _);
        Assert.True(ec.VerifyData(datos.AsSpan(0, datos.Length - 64), datos.AsSpan(datos.Length - 64), HashAlgorithmName.SHA256, DSASignatureFormat.IeeeP1363FixedFieldConcatenation));
        datos[20] ^= 1;
        Assert.False(ec.VerifyData(datos.AsSpan(0, datos.Length - 64), datos.AsSpan(datos.Length - 64), HashAlgorithmName.SHA256, DSASignatureFormat.IeeeP1363FixedFieldConcatenation));
        if (Environment.GetEnvironmentVariable("AVACOM_CAPTURAR_SELLO") == "1")
        {
            var destino = Path.Combine(Path.GetDirectoryName(RutaCapturas())!, "solicitud-csharp.avsol");
            File.WriteAllBytes(destino, File.ReadAllBytes(ruta));
        }
    }

    private static string RutaCapturas()
    {
        var carpeta = AppContext.BaseDirectory;
        while (carpeta is not null && !File.Exists(Path.Combine(carpeta, "Avacom.Ops.Host.Tests.csproj"))) carpeta = Path.GetDirectoryName(carpeta);
        return Path.Combine(carpeta!, "Fixtures", "sello", "vectores.json");
    }

    [Fact]
    public void LaOpcionDeSerieEsLaDeLaSolicitudYNoLaDelBios()
    {
        var (_, ruta) = PuertaDeDispositivo.Solicitar(_equipo, Path.Combine(_tmp, "salida2"), "MI-SERIE-77", 1, LectorUefiFalso.IdDePrueba);
        Assert.Contains("MI-SERIE-77", Encoding.ASCII.GetString(File.ReadAllBytes(ruta)));
    }
}

/// <summary>Las claves de VERDAD en CNG (ambito de usuario y nombre propio para no tocar ninguna clave del producto): con TPM si el equipo lo tiene, y si no, de software.</summary>
public class ClavesCngRealesTests
{
    [Fact]
    public void LasClavesSeCreanFirmanYDesenvuelvenSinExportarse()
    {
        var claves = new ClavesCng("-pruebas-" + Guid.NewGuid().ToString("N")[..8], maquina: false);
        try
        {
            Assert.Null(claves.IdentidadSpki());
            Assert.True(claves.Crear());
            var spki = claves.IdentidadSpki();
            Assert.NotNull(spki);
            // prueba de posesion: firma el reto con la clave del equipo y la verifica con su publica
            var reto = RandomNumberGenerator.GetBytes(32);
            var mensaje = MensajeDePosesion(reto, HuellaDe(spki!));
            var firma = claves.Firmar(mensaje);
            Assert.Equal(64, firma!.Length);
            using var ec = ECDsa.Create();
            ec.ImportSubjectPublicKeyInfo(spki!, out _);
            Assert.True(ec.VerifyData(mensaje, firma, HashAlgorithmName.SHA256, DSASignatureFormat.IeeeP1363FixedFieldConcatenation));
            // desenvolver: RSA-OAEP-SHA256 con la clave que no sale del proveedor
            using var rsa = RSA.Create();
            rsa.ImportSubjectPublicKeyInfo(claves.CifradoSpki()!, out _);
            var k = RandomNumberGenerator.GetBytes(32);
            Assert.Equal(k, claves.Desenvolver(rsa.Encrypt(k, RSAEncryptionPadding.OaepSHA256)));
            Assert.Null(claves.Desenvolver(new byte[256]));          // basura no se desenvuelve
            // ninguna de las dos es exportable
            Assert.ThrowsAny<CryptographicException>(() => { using var k2 = CngKey.Open(ClavesCng.NombreIdentidad + "x"); });
        }
        finally { claves.Borrar(); }
    }

    [Fact]
    public void LaVerificacionCompletaConClavesRealesDaAutenticado()
    {
        var claves = new ClavesCng("-pruebas-" + Guid.NewGuid().ToString("N")[..8], maquina: false);
        var estacion = new EstacionDePrueba();
        var carpeta = Path.Combine(Path.GetTempPath(), "avacom-cng-" + Guid.NewGuid().ToString("N"));
        try
        {
            Assert.True(claves.Crear());
            Directory.CreateDirectory(carpeta);
            File.WriteAllBytes(Path.Combine(carpeta, PuertaDeDispositivo.ArchivoDeSello), estacion.Sello(HuellaDe(claves.IdentidadSpki()!)));
            var sw = System.Diagnostics.Stopwatch.StartNew();
            var r = PuertaDeDispositivo.Verificar(claves, estacion.Llaves, carpeta, 1_790_000_000_001, new LectorUefiFalso());
            Assert.Equal(Autenticado, r.Estado);
            Assert.True(sw.ElapsedMilliseconds < 2000, $"verificar tardo {sw.ElapsedMilliseconds} ms");
            Console.WriteLine($"verificar con claves CNG reales (EnTpm={claves.EnTpm}): {sw.ElapsedMilliseconds} ms");
        }
        finally { claves.Borrar(); try { Directory.Delete(carpeta, true); } catch (IOException) { } }
    }

    [Fact]
    public void SinElevarLasClavesDeMaquinaSeNiegan_ElDispositivoNoSeCreaALaFuerza()
    {
        using var id = System.Security.Principal.WindowsIdentity.GetCurrent();
        if (new System.Security.Principal.WindowsPrincipal(id).IsInRole(System.Security.Principal.WindowsBuiltInRole.Administrator)) return;       // elevado: la creacion de maquina si funciona
        var claves = new ClavesCng("-pruebas-" + Guid.NewGuid().ToString("N")[..8], maquina: true, probarTpm: false);
        Assert.False(claves.Crear() && claves.IdentidadSpki() is null);
    }
}

/// <summary>S2 · la liberacion de la llave del paquete con un equipo de mentira (RSA en memoria): quien puede desenvolver K y quien no.</summary>
public class LiberacionDeClaveTests : IDisposable
{
    private readonly string _tmp = Path.Combine(Path.GetTempPath(), "avacom-liberacion-" + Guid.NewGuid().ToString("N"));
    private readonly EstacionDePrueba _estacion = new();
    private readonly EquipoFalso _equipo = new();
    private readonly LectorUefiFalso _uefi = new();
    private readonly byte[] _k = RandomNumberGenerator.GetBytes(32);
    private string Sello => Path.Combine(_tmp, "sello");
    private byte[] Kid => KidDePaquete(_k);

    public LiberacionDeClaveTests() => Directory.CreateDirectory(Sello);
    public void Dispose() { try { Directory.Delete(_tmp, true); } catch (IOException) { } }

    private byte[] AvClave(IClavesDeEquipo paraEquipo, byte[]? kid = null, byte[]? k = null, string? firmante = null)
    {
        using var rsa = RSA.Create();
        rsa.ImportSubjectPublicKeyInfo(paraEquipo.CifradoSpki()!, out _);
        var campos = new SortedDictionary<int, (byte[], bool)>
        {
            [KId] = (RandomNumberGenerator.GetBytes(16), true), [KCifradoHuella] = (HuellaDe(paraEquipo.CifradoSpki()!), true), [KKidPaquete] = (kid ?? Kid, true),
            [KEnvuelta] = (rsa.Encrypt(k ?? _k, RSAEncryptionPadding.OaepSHA256), true), [KEmitida] = (new byte[8], true),
        };
        return _estacion.FirmarClave(campos, firmante);
    }

    private (byte[]? K, string Motivo) Liberar(IClavesDeEquipo? equipo = null) =>
        LiberacionDeClave.Liberar(equipo ?? _equipo, _estacion.Llaves, Sello, Kid, 1_790_000_000_001, desarrollo: false, _uefi);

    private void ConSello(IClavesDeEquipo? equipo = null) => File.WriteAllBytes(Path.Combine(Sello, PuertaDeDispositivo.ArchivoDeSello), _estacion.Sello(HuellaDe((equipo ?? _equipo).IdentidadSpki()!)));

    [Fact]
    public void ElEquipoSelladoConSuClaveLiberaK()
    {
        ConSello();
        File.WriteAllBytes(Path.Combine(Sello, "paquete-x.avclave"), AvClave(_equipo));
        var (k, motivo) = Liberar();
        Assert.Equal(_k, k);
        Assert.Equal("", motivo);
    }

    [Fact]
    public void SinSelloNoSeLibera()
    {
        File.WriteAllBytes(Path.Combine(Sello, "paquete-x.avclave"), AvClave(_equipo));
        Assert.Equal((null, "dispositivo_sin_sello"), Liberar());
    }

    [Fact]
    public void LaClaveEnvueltaParaOtroEquipoNoSeAbre()
    {
        ConSello();
        File.WriteAllBytes(Path.Combine(Sello, "paquete-x.avclave"), AvClave(new EquipoFalso()));
        Assert.Equal((null, "clave_de_otro_equipo"), Liberar());
    }

    [Fact]
    public void UnaClaveDeOtraVersionDelPaqueteNoCuenta()
    {
        ConSello();
        File.WriteAllBytes(Path.Combine(Sello, "paquete-x.avclave"), AvClave(_equipo, kid: new byte[8]));
        Assert.Equal((null, "sin_clave_para_este_paquete"), Liberar());
    }

    [Fact]
    public void UnaClaveQueNoAbreElPaqueteSeRechaza()
    {
        ConSello();
        File.WriteAllBytes(Path.Combine(Sello, "paquete-x.avclave"), AvClave(_equipo, k: RandomNumberGenerator.GetBytes(32)));      // el kid dice una cosa y la llave envuelta es otra
        Assert.Equal((null, "clave_no_abre_el_paquete"), Liberar());
    }

    [Fact]
    public void UnaClaveFirmadaPorOtraLlaveNoSeObedece()
    {
        ConSello();
        File.WriteAllBytes(Path.Combine(Sello, "paquete-x.avclave"), AvClave(_equipo, firmante: "otro"));
        Assert.StartsWith("clave_", Liberar().Motivo);
    }

    [Fact]
    public void UnEquipoRevocadoNoLiberaAunqueTengaLaClave()
    {
        ConSello();
        File.WriteAllBytes(Path.Combine(Sello, "paquete-x.avclave"), AvClave(_equipo));
        File.WriteAllBytes(Path.Combine(Sello, PuertaDeDispositivo.ArchivoDeRevocados), _estacion.Revocados(1, _equipo.Huella));
        Assert.Equal((null, "dispositivo_revocado"), Liberar());
    }

    [Fact]
    public void SinTpmElPaqueteNoSeAbreNiSeAnunciaComoFraude()
    {
        ConSello();
        File.WriteAllBytes(Path.Combine(Sello, "paquete-x.avclave"), AvClave(_equipo));
        _equipo.PerderLasClaves();
        Assert.Equal((null, "dispositivo_no_verificable"), Liberar());
    }

    [Fact]
    public void LaKidDeUnPaqueteSeLeeDeSuCabeceraSinAbrirlo()
    {
        var cabecera = new byte[37];
        "AVPK"u8.CopyTo(cabecera);
        new byte[] { 1, 2, 3, 4, 5, 6, 7, 8 }.CopyTo(cabecera, 7);
        var ruta = Path.Combine(_tmp, "codigo.avpkg");
        File.WriteAllBytes(ruta, cabecera);
        Assert.Equal(new byte[] { 1, 2, 3, 4, 5, 6, 7, 8 }, LiberacionDeClave.KidDelPaquete(ruta));
        File.WriteAllBytes(ruta, new byte[10]);
        Assert.Null(LiberacionDeClave.KidDelPaquete(ruta));
    }

    [Fact]
    public void ElKidDeLaLlaveCoincideConElDelLectorPython()
    {
        // k = 00 01 02 … 1f: el valor lo calcula avacom_boot.kid_de y lo comprueba tools/licencias (prueba del mismo nombre).
        var k = Enumerable.Range(0, 32).Select(i => (byte)i).ToArray();
        Assert.Equal(Convert.ToHexString(SHA256.HashData([.. "avacom-kid|"u8.ToArray(), .. k])[..8]), Convert.ToHexString(KidDePaquete(k)));
    }
}

/// <summary>
/// La lectura REAL del firmware con <c>GetFirmwareEnvironmentVariableExW</c>: SOLO LEE (el ensamblado no importa ninguna funcion de escritura). Su resultado depende del equipo (UEFI o Legacy, elevado o no,
/// con la variable o sin ella), asi que aqui solo se comprueba que la llamada es valida (no revienta, no devuelve basura) y que cae en uno de los estados definidos.
/// </summary>
public class LectorUefiWindowsRealTests
{
    [Fact]
    public void LaLecturaRealDelFirmwareEsSoloLecturaYDevuelveUnEstadoDefinido()
    {
        var l = new LectorUefiWindows().Leer(IdentidadUefi.Nombre, IdentidadUefi.Proveedor);
        Console.WriteLine($"lectura real de {IdentidadUefi.Nombre}: {l.Estado} (codigo de sistema {l.CodigoDeSistema}, {(l.Valor?.Length ?? 0)} bytes)");
        Assert.True(Enum.IsDefined(l.Estado));
        Assert.Equal(l.Estado == EstadoDeLecturaUefi.Leida, l.Valor is { Length: > 0 });
        // el resultado nunca puede ser «error de lectura» por una firma de API mal declarada (87 = parametro incorrecto)
        Assert.NotEqual(87, l.CodigoDeSistema);
    }

    [Fact]
    public void ElEnsambladoNoImportaNingunaFuncionQueEscribaOBorreVariablesUefi()
    {
        var host = Path.GetDirectoryName(RutaDeLasFuentes())!;
        var fuentes = Directory.GetFiles(host, "*.cs", SearchOption.AllDirectories)
                               .Where(f => !f.Contains(Path.DirectorySeparatorChar + "obj" + Path.DirectorySeparatorChar) && !f.Contains(Path.DirectorySeparatorChar + "bin" + Path.DirectorySeparatorChar));
        Assert.NotEmpty(fuentes);
        foreach (var f in fuentes)
        {
            var codigo = File.ReadAllLines(f).Where(l => !l.TrimStart().StartsWith("//", StringComparison.Ordinal));
            Assert.DoesNotContain(codigo, l => l.Contains("SetFirmwareEnvironmentVariable", StringComparison.Ordinal));
        }
    }

    private static string RutaDeLasFuentes()
    {
        var carpeta = AppContext.BaseDirectory;
        while (carpeta is not null && !Directory.Exists(Path.Combine(carpeta, "installer", "src", "host"))) carpeta = Path.GetDirectoryName(carpeta);
        return Path.Combine(carpeta!, "installer", "src", "host", "Dispositivo");
    }
}

/// <summary>El aviso del lanzador (usuario estandar): lee la señal que dejo el servicio y, si el dispositivo no esta autorizado, no abre la interfaz y muestra el mensaje obligatorio.</summary>
public class LanzadorDispositivoTests : IDisposable
{
    private readonly string _tmp = Path.Combine(Path.GetTempPath(), "avacom-lanzador-" + Guid.NewGuid().ToString("N"));
    private string Senal => Path.Combine(_tmp, "Logs", "dispositivo-estado.json");

    public LanzadorDispositivoTests() => Directory.CreateDirectory(Path.Combine(_tmp, "Logs"));
    public void Dispose() { try { Directory.Delete(_tmp, true); } catch (IOException) { } }

    private static Registro Reg() => new("dispositivo-pruebas.log");

    private static string Json(bool autorizado, string codigo) => PuertaDeDispositivo.SenalParaElLanzador(
        new PuertaDeDispositivo.Resultado(autorizado ? Autenticado : IdentidadUefiRechazada, autorizado ? "" : "variable_no_encontrada", null, false, null, 0), DateTime.UtcNow).Replace("AVC-UEFI-00", codigo);

    [Fact]
    public void SiElServicioDijoAutorizadoElLanzadorAbre()
    {
        File.WriteAllText(Senal, Json(true, "AVC-UEFI-00"));
        Assert.True(Lanzador.LeerSenalDelLanzador(Reg(), Senal, 0, out var codigo));
        Assert.Equal("AVC-UEFI-00", codigo);
    }

    [Fact]
    public void SiElServicioDijoNoAutorizadoElLanzadorNoAbreYDaElCodigo()
    {
        File.WriteAllText(Senal, Json(false, "AVC-UEFI-01"));
        Assert.False(Lanzador.LeerSenalDelLanzador(Reg(), Senal, 0, out var codigo));
        Assert.Equal("AVC-UEFI-01", codigo);
        using var doc = JsonDocument.Parse(File.ReadAllText(Senal));
        Assert.False(doc.RootElement.GetProperty("autorizado").GetBoolean());
        Assert.Equal(["version", "verificado", "autorizado", "estado", "codigo"], doc.RootElement.EnumerateObject().Select(p => p.Name).ToArray());
    }

    [Fact]
    public void SinSenalDelServicioSeDeniegaPorOmision()
    {
        Assert.False(Lanzador.LeerSenalDelLanzador(Reg(), Path.Combine(_tmp, "Logs", "no-existe.json"), 0, out var codigo));
        Assert.Equal("AVC-UEFI-07", codigo);
    }

    [Fact]
    public void UnaSenalIlegibleTambienSeDeniega()
    {
        File.WriteAllText(Senal, "esto no es json");
        Assert.False(Lanzador.LeerSenalDelLanzador(Reg(), Senal, 0, out _));
    }

    [Fact]
    public void UnaCompilacionSinLlavesDeSelloNoTienePuertaYElLanzadorAbre()
    {
        Assert.True(Lanzador.DispositivoAutorizado(Reg(), out _, esperaSegundos: 0));
    }
}


using System.Security.Cryptography;
using System.Text;
using Org.BouncyCastle.Math.EC.Rfc8032;

namespace Avacom.Ops.Host.Dispositivo;

/// <summary>
/// El sello de dispositivo AVACOM (S1), lado C#. Es el GEMELO de <c>backend/licenciamiento/dominio/sello.py</c> (y de <c>tlv.py</c>): mismo envoltorio, mismas etiquetas, mismo orden de
/// comprobaciones y los mismos motivos de rechazo. Si uno cambia, cambia el otro (hay un archivo de vectores que los dos leen).
///
///   magic(4) · version(u16)=1 · largo del kid(u8) · kid · [ etiqueta(u16) · largo(u16) · valor ]… · firma(64)
///
/// La firma Ed25519 cubre TODO lo anterior a ella y se verifica ANTES de leer ningun campo. El algoritmo esta fijado.
/// </summary>
internal static class FormatoSello
{
    public static readonly byte[] MagicSello = "AVSL"u8.ToArray();
    public static readonly byte[] MagicRevocados = "AVRV"u8.ToArray();
    public static readonly byte[] MagicSolicitud = "AVSO"u8.ToArray();
    public static readonly byte[] MagicClave = "AVKY"u8.ToArray();

    public const int MaxArchivo = 16 * 1024, MaxValor = 4096, MaxCampos = 32, MaxKid = 64, TamFirma = 64;
    private const ushort Critica = 0x8000;
    private const string ContextoPosesion = "AVACOM-SELLO1";

    // Etiquetas del sello (numero → (largo maximo, critica)).
    public const int TId = 1, TSerie = 2, TModelo = 3, TOrigen = 4, TClaveHuella = 5, TCifradoHuella = 6, TEkHuella = 7, TEmitido = 8, TVence = 9, TLote = 10, TMac = 11, TEvidencia = 12, TUefiId = 13;
    private static readonly Dictionary<int, (int Max, bool Critica)> ConocidosSello = new()
    {
        [TId] = (16, true), [TSerie] = (64, false), [TModelo] = (64, false), [TOrigen] = (1, true), [TClaveHuella] = (32, true), [TCifradoHuella] = (32, false), [TEkHuella] = (32, false),
        [TEmitido] = (8, true), [TVence] = (8, true), [TLote] = (32, false), [TMac] = (17, false), [TEvidencia] = (1, true), [TUefiId] = (32, false),
    };
    private static readonly int[] ObligatoriosSello = [TId, TOrigen, TClaveHuella, TEmitido, TVence, TEvidencia];

    public const int KId = 1, KCifradoHuella = 2, KKidPaquete = 3, KEnvuelta = 4, KEmitida = 5, KVersion = 6;
    private static readonly Dictionary<int, (int Max, bool Critica)> ConocidosClave = new()
    {
        [KId] = (16, true), [KCifradoHuella] = (32, true), [KKidPaquete] = (8, true), [KEnvuelta] = (512, true), [KEmitida] = (8, true), [KVersion] = (32, false),
    };

    public const int RNumero = 1, REmitida = 2, RHuellas = 3;
    private static readonly Dictionary<int, (int Max, bool Critica)> ConocidosRevocados = new() { [RNumero] = (4, true), [REmitida] = (8, true), [RHuellas] = (32 * 128, true) };

    // Etiquetas de la solicitud (.avsol), que escribe ESTE lado.
    public const int SId = 1, SSerie = 2, SModelo = 3, SClave = 4, SCifrado = 5, SEk = 6, SMac = 7, SProveedor = 8, SCreada = 9, SUefiId = 10;
    private static readonly Dictionary<int, (int Max, bool Critica)> ConocidosSolicitud = new()
    {
        [SId] = (16, true), [SSerie] = (64, false), [SModelo] = (64, false), [SClave] = (128, true), [SCifrado] = (600, false), [SEk] = (600, false), [SMac] = (17, false),
        [SProveedor] = (1, true), [SCreada] = (8, true), [SUefiId] = (32, false),
    };

    public const string Autenticado = "autenticado", SinSello = "sin_sello", SelloInvalido = "sello_invalido", ClaveDistinta = "clave_distinta", Revocado = "revocado", NoVerificable = "no_verificable";

    /// <summary>La capa de IDENTIDAD UEFI rechazo al equipo (variable ausente o mal formada, firmware no UEFI, sin permiso, o el sello no autoriza ese identificador). <c>motivo</c> dice cual.</summary>
    public const string IdentidadUefiRechazada = "identidad_uefi";

    /// <summary>Un rechazo con su motivo (el mismo vocabulario que <c>LicenciaInvalida.motivo</c> del backend).</summary>
    internal sealed class Rechazo(string motivo) : Exception(motivo) { public string Motivo { get; } = motivo; }

    internal sealed record Sello(string Id, string Serie, string Modelo, string Origen, byte[] ClaveHuella, byte[]? CifradoHuella, byte[]? EkHuella, long Emitido, long Vence, string Lote, string Mac,
                                 string Evidencia, string Kid, string Sha256, string UefiId = "")
    {
        public bool Vencido(long ahoraMs) => Vence != 0 && ahoraMs > Vence;
    }

    internal sealed record Veredicto(string Estado, string Motivo = "", Sello? Sello = null);

    // ----------------------------------------------------------------------------------------------------------------- TLV
    private static (string Kid, int Fin) LeerCabecera(byte[] datos, byte[] magic)
    {
        if (datos.Length > MaxArchivo) throw new Rechazo("demasiado_grande");
        if (datos.Length < 4 + 2 + 1 + 1 + TamFirma) throw new Rechazo("demasiado_corta");
        if (!datos.AsSpan(0, 4).SequenceEqual(magic)) throw new Rechazo("formato");
        var version = (datos[4] << 8) | datos[5];
        if (version != 1) throw new Rechazo("version_no_soportada");
        int largo = datos[6];
        if (largo is < 1 or > MaxKid || 7 + largo + TamFirma > datos.Length) throw new Rechazo("formato");
        for (var i = 0; i < largo; i++)
        {
            var c = datos[7 + i];
            var bueno = c is >= (byte)'a' and <= (byte)'z' || c is >= (byte)'0' and <= (byte)'9' || c is (byte)'.' or (byte)'_' or (byte)'-';
            if (!bueno) throw new Rechazo("formato");
        }
        return (Encoding.ASCII.GetString(datos, 7, largo), 7 + largo);
    }

    private static Dictionary<int, byte[]> LeerCampos(ReadOnlySpan<byte> cuerpo, Dictionary<int, (int Max, bool Critica)> conocidos)
    {
        var campos = new Dictionary<int, byte[]>();
        var pos = 0;
        var ultima = 0;
        var total = 0;
        while (pos < cuerpo.Length)
        {
            total++;
            if (total > MaxCampos || pos + 4 > cuerpo.Length) throw new Rechazo("formato");
            var etiqueta = (cuerpo[pos] << 8) | cuerpo[pos + 1];
            var largo = (cuerpo[pos + 2] << 8) | cuerpo[pos + 3];
            pos += 4;
            var numero = etiqueta & 0x7FFF;
            var critica = (etiqueta & Critica) != 0;
            if (numero == 0 || numero <= ultima) throw new Rechazo("formato");
            ultima = numero;
            if (largo > MaxValor || pos + largo > cuerpo.Length) throw new Rechazo("formato");
            var valor = cuerpo.Slice(pos, largo).ToArray();
            pos += largo;
            if (conocidos.TryGetValue(numero, out var regla))
            {
                if (critica != regla.Critica) throw new Rechazo("formato");
                if (largo > regla.Max) throw new Rechazo("campo_invalido");
                campos[numero] = valor;
            }
            else if (critica) throw new Rechazo("etiqueta_critica_desconocida");
        }
        return campos;
    }

    /// <summary>Verifica la firma con la llave del <c>kid</c> y SOLO entonces interpreta los campos.</summary>
    private static (Dictionary<int, byte[]> Campos, string Kid, string Sha256) Abrir(byte[] datos, byte[] magic, IReadOnlyDictionary<string, byte[]> claves, Dictionary<int, (int Max, bool Critica)> conocidos)
    {
        var (kid, fin) = LeerCabecera(datos, magic);
        if (!claves.TryGetValue(kid, out var publica)) throw new Rechazo("kid_desconocido");
        var firmado = datos.Length - TamFirma;
        bool valida;
        try { valida = publica.Length == 32 && Ed25519.Verify(datos, firmado, publica, 0, datos, 0, firmado); }
        catch (Exception error) when (error is ArgumentException or InvalidOperationException) { valida = false; }
        if (!valida) throw new Rechazo("firma_invalida");
        return (LeerCampos(datos.AsSpan(fin, firmado - fin), conocidos), kid, Convert.ToHexString(SHA256.HashData(datos)).ToLowerInvariant());
    }

    // ----------------------------------------------------------------------------------------------------------------- sello y revocados
    private static string Texto(Dictionary<int, byte[]> c, int etiqueta)
    {
        if (!c.TryGetValue(etiqueta, out var valor)) return "";
        foreach (var b in valor) if (b is < 0x20 or > 0x7E) throw new Rechazo("campo_invalido");      // ASCII imprimible, como str.isprintable() sobre ASCII
        return Encoding.ASCII.GetString(valor);
    }

    private static long Entero(Dictionary<int, byte[]> c, int etiqueta, int bytes)
    {
        var v = c[etiqueta];
        if (v.Length != bytes) throw new Rechazo("campo_invalido");
        ulong n = 0;
        foreach (var b in v) n = (n << 8) | b;
        return n > long.MaxValue ? throw new Rechazo("campo_invalido") : (long)n;
    }

    public static Sello LeerSello(byte[] datos, IReadOnlyDictionary<string, byte[]> claves)
    {
        var (c, kid, sha) = Abrir(datos, MagicSello, claves, ConocidosSello);
        if (ObligatoriosSello.Any(t => !c.ContainsKey(t))) throw new Rechazo("campo_faltante");
        var origen = Entero(c, TOrigen, 1) switch { 1 => "fabrica", 2 => "entrega", _ => null };
        var evidencia = Entero(c, TEvidencia, 1) switch { 1 => "inventario", 2 => "ekcert", 3 => "activacion", _ => null };
        if (origen is null || evidencia is null || c[TId].Length != 16 || c[TClaveHuella].Length != 32) throw new Rechazo("campo_invalido");
        foreach (var t in new[] { TCifradoHuella, TEkHuella }) if (c.TryGetValue(t, out var v) && v.Length != 32) throw new Rechazo("campo_invalido");
        var emitido = Entero(c, TEmitido, 8);
        var vence = Entero(c, TVence, 8);
        if (vence != 0 && vence <= emitido) throw new Rechazo("campo_invalido");
        var uefiId = Texto(c, TUefiId);
        if (uefiId.Length > 0 && !IdentidadUefi.EsFormatoValido(uefiId)) throw new Rechazo("campo_invalido");
        var id = Convert.ToHexString(c[TId]).ToLowerInvariant();
        return new Sello($"{id[..8]}-{id[8..12]}-{id[12..16]}-{id[16..20]}-{id[20..]}", Texto(c, TSerie), Texto(c, TModelo), origen, c[TClaveHuella], c.GetValueOrDefault(TCifradoHuella),
                         c.GetValueOrDefault(TEkHuella), emitido, vence, Texto(c, TLote), Texto(c, TMac), evidencia, kid, sha, uefiId);
    }

    /// <summary>(numero de la lista, huellas de clave revocadas).</summary>
    public static (long Numero, HashSet<string> Huellas) LeerRevocados(byte[] datos, IReadOnlyDictionary<string, byte[]> claves)
    {
        var (c, _, _) = Abrir(datos, MagicRevocados, claves, ConocidosRevocados);
        if (!c.ContainsKey(RNumero) || !c.TryGetValue(RHuellas, out var crudo) || crudo.Length % 32 != 0) throw new Rechazo("campo_invalido");
        var huellas = new HashSet<string>(StringComparer.Ordinal);
        for (var i = 0; i < crudo.Length; i += 32) huellas.Add(Convert.ToHexString(crudo, i, 32).ToLowerInvariant());
        return (Entero(c, RNumero, 4), huellas);
    }

    /// <summary>La llave K de una version del paquete, envuelta para la clave de cifrado de un equipo (S2). Mismo gemelo que <c>sello.leer_clave</c>.</summary>
    internal sealed record ClaveDePaquete(string Id, byte[] CifradoHuella, byte[] KidPaquete, byte[] Envuelta, long Emitida, string Version, string Kid, string Sha256);

    public static ClaveDePaquete LeerClave(byte[] datos, IReadOnlyDictionary<string, byte[]> claves)
    {
        var (c, kid, sha) = Abrir(datos, MagicClave, claves, ConocidosClave);
        if (new[] { KId, KCifradoHuella, KKidPaquete, KEnvuelta, KEmitida }.Any(t => !c.ContainsKey(t))) throw new Rechazo("campo_faltante");
        if (c[KId].Length != 16 || c[KCifradoHuella].Length != 32 || c[KKidPaquete].Length != 8 || c[KEnvuelta].Length is < 64 or > 512) throw new Rechazo("campo_invalido");
        var id = Convert.ToHexString(c[KId]).ToLowerInvariant();
        return new ClaveDePaquete($"{id[..8]}-{id[8..12]}-{id[12..16]}-{id[16..20]}-{id[20..]}", c[KCifradoHuella], c[KKidPaquete], c[KEnvuelta], Entero(c, KEmitida, 8), Texto(c, KVersion), kid, sha);
    }

    /// <summary>El identificador de 8 bytes de una llave de paquete: SHA-256(«avacom-kid|» + K)[..8]. Es el mismo que calcula el lector Python (<c>avacom_boot.kid_de</c>).</summary>
    public static byte[] KidDePaquete(byte[] k) => SHA256.HashData([.. "avacom-kid|"u8.ToArray(), .. k])[..8];

    public static byte[] MensajeDePosesion(byte[] reto, byte[] claveHuella)
    {
        if (reto.Length != 32 || claveHuella.Length != 32) throw new ArgumentException("reto y huella miden 32 bytes");
        return [.. Encoding.ASCII.GetBytes(ContextoPosesion), .. reto, .. claveHuella];
    }

    /// <summary>
    /// El veredicto. Mismo orden que <c>sello.evaluar</c> del backend: sin_sello · sello_invalido (firma, kid, formato, vencido) · revocado · no_verificable (el equipo no pudo mostrar su clave: un fallo del
    /// sistema, no un fraude) · clave_distinta (otra clave, o no supo firmar el reto) · autenticado. <paramref name="posesion"/> null = no se pudo firmar.
    /// </summary>
    public static Veredicto Evaluar(byte[]? datosSello, IReadOnlyDictionary<string, byte[]> claves, byte[]? claveHuellaDelEquipo, bool? posesion, IReadOnlySet<string> revocados, long ahoraMs)
    {
        if (datosSello is null || datosSello.Length == 0) return new Veredicto(SinSello);
        Sello sello;
        try { sello = LeerSello(datosSello, claves); }
        catch (Rechazo r) { return new Veredicto(SelloInvalido, r.Motivo); }
        if (sello.Vencido(ahoraMs)) return new Veredicto(SelloInvalido, "vencido", sello);
        if (revocados.Contains(Convert.ToHexString(sello.ClaveHuella).ToLowerInvariant())) return new Veredicto(Revocado, "", sello);
        if (claveHuellaDelEquipo is null) return new Veredicto(NoVerificable, "sin_clave", sello);
        if (!claveHuellaDelEquipo.AsSpan().SequenceEqual(sello.ClaveHuella)) return new Veredicto(ClaveDistinta, "otra_clave", sello);
        if (posesion is not true) return posesion is false ? new Veredicto(ClaveDistinta, "sin_posesion", sello) : new Veredicto(NoVerificable, "no_firmo", sello);
        return new Veredicto(Autenticado, "", sello);
    }

    // ----------------------------------------------------------------------------------------------------------------- solicitud (.avsol)
    public sealed record DatosDeSolicitud(byte[] Id, string Serie, string Modelo, byte[] ClavePublica, byte[]? CifradoPublica, byte[]? EkPublica, string Mac, bool EnTpm, long Creada, string UefiId = "");

    /// <summary>La solicitud, firmada por el propio equipo con su clave de identidad (ECDSA P-256, 64 bytes P1363). <paramref name="firmar"/> la hace la clave no exportable.</summary>
    public static byte[] EscribirSolicitud(DatosDeSolicitud s, Func<byte[], byte[]> firmar)
    {
        var campos = new SortedDictionary<int, byte[]> { [SId] = s.Id, [SClave] = s.ClavePublica, [SProveedor] = [(byte)(s.EnTpm ? 1 : 0)], [SCreada] = Entero8(s.Creada) };
        foreach (var (t, v) in new[] { (SSerie, s.Serie), (SModelo, s.Modelo), (SMac, s.Mac), (SUefiId, s.UefiId) }) if (v.Length > 0) campos[t] = Encoding.ASCII.GetBytes(v);
        if (s.CifradoPublica is { Length: > 0 }) campos[SCifrado] = s.CifradoPublica;
        if (s.EkPublica is { Length: > 0 }) campos[SEk] = s.EkPublica;
        var kid = "equipo"u8.ToArray();
        using var cuerpo = new MemoryStream();
        cuerpo.Write(MagicSolicitud);
        cuerpo.Write([0, 1, (byte)kid.Length]);
        cuerpo.Write(kid);
        foreach (var (t, v) in campos)
        {
            var (max, critica) = ConocidosSolicitud[t];
            if (v.Length > max) throw new ArgumentException($"el campo {t} es demasiado largo");
            var etiqueta = t | (critica ? Critica : 0);
            cuerpo.Write([(byte)(etiqueta >> 8), (byte)etiqueta, (byte)(v.Length >> 8), (byte)v.Length]);
            cuerpo.Write(v);
        }
        var sinFirma = cuerpo.ToArray();
        var firma = firmar(sinFirma);
        if (firma.Length != TamFirma) throw new InvalidOperationException("la firma no mide 64 bytes");
        return [.. sinFirma, .. firma];
    }

    private static byte[] Entero8(long n) { var b = new byte[8]; for (var i = 7; i >= 0; i--) { b[i] = (byte)n; n >>= 8; } return b; }

    public static byte[] HuellaDe(byte[] datos) => SHA256.HashData(datos);
}

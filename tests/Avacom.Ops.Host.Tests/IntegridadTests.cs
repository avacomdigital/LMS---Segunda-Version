using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Avacom.Ops.Host.Integridad;
using Org.BouncyCastle.Math.EC.Rfc8032;

namespace Avacom.Ops.Host.Tests;

/// <summary>Una instalacion de mentira en una carpeta temporal: Backend, Runtime, App, una DLL nativa, el manifiesto, la lista de integridad y su firma.</summary>
internal sealed class Instalacion : IDisposable
{
    public string Raiz { get; } = Path.Combine(Path.GetTempPath(), "avacom-host-pruebas-" + Guid.NewGuid().ToString("N"));
    public byte[] Privada { get; } = new byte[32];
    public byte[] Publica { get; } = new byte[32];
    public IReadOnlyDictionary<string, byte[]> Llaves => new Dictionary<string, byte[]> { ["upd-prueba"] = Publica };

    public static readonly Dictionary<string, string> Archivos = new()
    {
        ["Backend/manage.py"] = "print('manage')",
        ["Backend/licenciamiento/servicios.py"] = "x = 1",
        ["Backend/reporting/dominio/boletin.py"] = "y = 2",
        ["Backend/native/avacom_lic.dll"] = "MZ-nativa",
        ["Runtime/avacom_ops_backend.py"] = "import daphne",
        ["Runtime/Python/python.exe"] = "MZ-python",
        ["App/Avacom.Lms.Ops.dll"] = "MZ-app",
    };

    public Instalacion(bool firmada = true, bool conLista = true)
    {
        RandomNumberGenerator.Fill(Privada);
        Ed25519.GeneratePublicKey(Privada, 0, Publica, 0);
        Directory.CreateDirectory(Raiz);
        foreach (var (ruta, texto) in Archivos) Escribir(ruta, texto);
        if (conLista) Sellar(firmada);
        else File.WriteAllText(Path.Combine(Raiz, "manifiesto.json"), "{\"version\":\"2.0.0\"}");
    }

    public void Escribir(string ruta, string texto)
    {
        var completa = Path.Combine(Raiz, ruta.Replace('/', Path.DirectorySeparatorChar));
        Directory.CreateDirectory(Path.GetDirectoryName(completa)!);
        File.WriteAllText(completa, texto);
    }

    public static string Sha(string texto) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(texto))).ToLowerInvariant();

    /// <summary>Lo que hace Build-Installer.ps1 / New-ManifiestoFirmado.ps1: lista de integridad → manifiesto con su huella → firma Ed25519 de los bytes del manifiesto.</summary>
    public void Sellar(bool firmada)
    {
        var lista = JsonSerializer.SerializeToUtf8Bytes(new { version = 1, archivos = Archivos.OrderBy(p => p.Key, StringComparer.Ordinal).Select(p => new[] { p.Key, Sha(p.Value) }) });
        File.WriteAllBytes(Path.Combine(Raiz, "integridad.json"), lista);
        var manifiesto = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new { version = "2.16.0", integridad = new { archivo = "integridad.json", sha256 = Convert.ToHexString(SHA256.HashData(lista)).ToLowerInvariant() } }));
        File.WriteAllBytes(Path.Combine(Raiz, "manifiesto.json"), manifiesto);
        if (!firmada) return;
        var firma = new byte[64];
        Ed25519.Sign(Privada, 0, Publica, 0, manifiesto, 0, manifiesto.Length, firma, 0);
        File.WriteAllText(Path.Combine(Raiz, "manifiesto.firma.json"), JsonSerializer.Serialize(new { kid = "upd-prueba", alg = "ed25519", firma = Convert.ToBase64String(firma) }));
    }

    public void Dispose()
    {
        try { Directory.Delete(Raiz, recursive: true); } catch (IOException) { }
    }
}

public class IntegridadTests
{
    private static readonly IReadOnlyDictionary<string, string> SinAplicadas = new Dictionary<string, string>();

    private static ResultadoDeIntegridad Verificar(Instalacion i, IReadOnlyDictionary<string, byte[]>? llaves = null, IReadOnlyDictionary<string, string>? aplicadas = null) =>
        Verificador.Verificar(i.Raiz, llaves ?? i.Llaves, aplicadas ?? SinAplicadas);

    [Fact]
    public void Ed25519_cumple_el_vector_1_del_RFC_8032_y_acepta_firmas_de_Python()
    {
        // RFC 8032 §7.1, prueba 1 (mensaje vacio).
        var pk = Convert.FromHexString("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a");
        var sig = Convert.FromHexString("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b");
        Assert.True(Ed25519.Verify(sig, 0, pk, 0, [], 0, 0));
        Assert.False(Ed25519.Verify(sig, 0, pk, 0, [1], 0, 1));

        // Una firma hecha por `cryptography` (la que usa el emisor de AVACOM): semilla 0x01 x32, mensaje «avacom-integridad».
        var publica = Convert.FromHexString("8a88e3dd7409f195fd52db2d3cba5d72ca6709bf1d94121bf3748801b40f6f5c");
        var firma = Convert.FromHexString(DeEmisorDePython.Firma);
        Assert.True(Ed25519.Verify(firma, 0, publica, 0, Encoding.ASCII.GetBytes("avacom-integridad"), 0, 17));
    }

    [Fact]
    public void Una_instalacion_integra_y_firmada_esta_ok()
    {
        using var i = new Instalacion();
        var r = Verificar(i);
        Assert.Equal("ok", r.Estado);
        Assert.Equal("ok", r.Firma);
        Assert.Equal("upd-prueba", r.Kid);
        Assert.Equal(Instalacion.Archivos.Count, r.ArchivosComprobados);
        Assert.Empty(r.Hallazgos);
    }

    [Fact]
    public void Alterar_un_py_del_backend_se_ve_y_dice_cual()
    {
        using var i = new Instalacion();
        i.Escribir("Backend/licenciamiento/servicios.py", "x = 1  # parche de campo");
        var r = Verificar(i);
        Assert.Equal("alterada", r.Estado);
        var h = Assert.Single(r.Hallazgos);
        Assert.Equal(("backend", "modificado", 1), (h.Tipo, h.Detalle, h.Cantidad));
        Assert.Equal(["Backend/licenciamiento/servicios.py"], h.Ejemplos);
    }

    [Fact]
    public void Un_archivo_que_falta_y_uno_que_sobra_se_ven()
    {
        using var i = new Instalacion();
        File.Delete(Path.Combine(i.Raiz, "Backend", "manage.py"));
        i.Escribir("Backend/reporting/puerta_trasera.py", "import os");
        i.Escribir("Backend/reporting/notas.txt", "no se ejecuta");          // un .txt de mas no es codigo
        i.Escribir("Backend/reporting/__pycache__/x.pyc", "bytecode");        // y el bytecode lo crea Python solo
        var r = Verificar(i);
        Assert.Equal("alterada", r.Estado);
        Assert.Contains(r.Hallazgos, h => h is { Tipo: "backend", Detalle: "falta" } && h.Ejemplos.Contains("Backend/manage.py"));
        Assert.Contains(r.Hallazgos, h => h is { Tipo: "backend", Detalle: "sobra" } && h.Ejemplos.SequenceEqual(["Backend/reporting/puerta_trasera.py"]));
        Assert.Equal(2, r.Hallazgos.Count);
    }

    [Fact]
    public void Una_dll_nativa_cambiada_es_del_tipo_nativo()
    {
        using var i = new Instalacion();
        i.Escribir("Backend/native/avacom_lic.dll", "MZ-otra");
        var r = Verificar(i);
        Assert.Equal("alterada", r.Estado);
        Assert.Equal("nativo", Assert.Single(r.Hallazgos).Tipo);
    }

    [Fact]
    public void Del_runtime_y_de_la_app_tambien_se_avisa()
    {
        using var i = new Instalacion();
        i.Escribir("Runtime/avacom_ops_backend.py", "import os");
        i.Escribir("App/Avacom.Lms.Ops.dll", "MZ-otra");
        var r = Verificar(i);
        Assert.Equal(["app", "runtime"], r.Hallazgos.Select(h => h.Tipo).ToArray());
    }

    [Fact]
    public void Sin_el_archivo_de_firma_o_con_la_firma_de_otra_llave_se_rechaza()
    {
        using var i = new Instalacion();
        File.Delete(Path.Combine(i.Raiz, "manifiesto.firma.json"));
        var sinFirma = Verificar(i);
        Assert.Equal("alterada", sinFirma.Estado);
        Assert.Equal("ausente", sinFirma.Firma);

        using var otra = new Instalacion();
        var ajena = new Dictionary<string, byte[]> { ["upd-prueba"] = i.Publica };     // el Host confia en la llave de i; el paquete de «otra» esta firmado con la suya
        var r = Verificar(otra, ajena);
        Assert.Equal("alterada", r.Estado);
        Assert.Equal("invalida", r.Firma);
    }

    [Fact]
    public void Un_kid_que_el_host_no_conoce_se_rechaza()
    {
        using var i = new Instalacion();
        var r = Verificar(i, new Dictionary<string, byte[]> { ["upd-otra"] = i.Publica });
        Assert.Equal("kid_desconocido", r.Firma);
        Assert.Equal("alterada", r.Estado);
    }

    [Fact]
    public void Editar_el_manifiesto_rompe_la_firma_y_la_lista_alterada_no_sirve_de_referencia()
    {
        using var i = new Instalacion();
        var ruta = Path.Combine(i.Raiz, "manifiesto.json");
        File.WriteAllText(ruta, File.ReadAllText(ruta).Replace("2.16.0", "9.9.9"));
        Assert.Equal("invalida", Verificar(i).Firma);

        using var j = new Instalacion();
        var lista = Path.Combine(j.Raiz, "integridad.json");
        File.WriteAllText(lista, File.ReadAllText(lista).Replace("Backend/manage.py", "Backend/manage.px"));
        var r = Verificar(j);
        Assert.Equal("alterada", r.Estado);
        Assert.Contains(r.Hallazgos, h => h is { Tipo: "manifiesto", Detalle: "lista_alterada" });
        Assert.DoesNotContain(r.Hallazgos, h => h.Tipo == "backend");         // no acusa a los archivos con una lista que no es la firmada
    }

    [Fact]
    public void Sin_llaves_incrustadas_un_desarrollo_compara_huellas_y_declara_sin_firma()
    {
        using var i = new Instalacion(firmada: false);
        var vacias = new Dictionary<string, byte[]>();
        var limpia = Verificar(i, vacias);
        Assert.Equal(("sin_firma", "sin_llave"), (limpia.Estado, limpia.Firma));
        i.Escribir("Backend/manage.py", "alterado");
        Assert.Equal("alterada", Verificar(i, vacias).Estado);
    }

    [Fact]
    public void Un_paquete_anterior_sin_lista_no_es_verificable_ni_alarma()
    {
        using var i = new Instalacion(conLista: false);
        var r = Verificar(i, new Dictionary<string, byte[]>());
        Assert.Equal("no_verificable", r.Estado);
        Assert.Empty(r.Hallazgos);
    }

    [Fact]
    public void Con_llaves_y_sin_manifiesto_se_alerta()
    {
        using var i = new Instalacion();
        File.Delete(Path.Combine(i.Raiz, "manifiesto.json"));
        var r = Verificar(i);
        Assert.Equal("alterada", r.Estado);
    }

    [Fact]
    public void Una_actualizacion_firmada_no_es_una_alteracion_y_revertirla_si_lo_es_si_el_disco_no_volvio()
    {
        using var i = new Instalacion();
        var carpeta = Path.Combine(i.Raiz, "Actualizaciones");
        i.Escribir("Backend/reporting/dominio/boletin.py", "y = 3  # version 1.4.0");
        i.Escribir("Backend/reporting/dominio/nuevo.py", "z = 1");
        Aplicadas.RegistrarAplicado(carpeta, "paquete-0001", [("reporting/dominio/boletin.py", Instalacion.Sha("y = 3  # version 1.4.0")), ("reporting/dominio/nuevo.py", Instalacion.Sha("z = 1"))]);
        var aplicadas = Aplicadas.Leer(carpeta);
        Assert.Equal("ok", Verificar(i, aplicadas: aplicadas).Estado);

        // El disco se alteraria despues de la actualizacion: ya no coincide con lo que el paquete declaro.
        i.Escribir("Backend/reporting/dominio/boletin.py", "y = 3  # manipulado");
        Assert.Equal("alterada", Verificar(i, aplicadas: aplicadas).Estado);

        // Una reversion exitosa retira al paquete: la lista original vuelve a mandar (y el codigo viejo tiene que estar en disco).
        Aplicadas.RegistrarRevertido(carpeta, "paquete-0001");
        Assert.Empty(Aplicadas.Leer(carpeta));
        i.Escribir("Backend/reporting/dominio/boletin.py", "y = 2");
        File.Delete(Path.Combine(i.Raiz, "Backend", "reporting", "dominio", "nuevo.py"));
        Assert.Equal("ok", Verificar(i).Estado);
    }

    [Fact]
    public void Una_ruta_de_la_lista_que_se_sale_de_la_instalacion_se_marca_y_no_se_lee()
    {
        using var i = new Instalacion();
        var r = Verificar(i, aplicadas: new Dictionary<string, string> { ["Backend/../../fuera.py"] = new string('a', 64) });
        Assert.Contains(r.Hallazgos, h => h.Detalle == "ruta_invalida");
    }

    [Fact]
    public void La_senal_cumple_el_contrato_que_lee_el_backend()
    {
        var r = new ResultadoDeIntegridad("alterada", "invalida", "upd-2026-1", "2.16.0", 12, [new Hallazgo("backend", "modificado", 2, ["Backend/a.py", "Backend/b.py"])]);
        using var doc = JsonDocument.Parse(Senal.Serializar(r, new DateTime(2026, 10, 22, 17, 0, 0, DateTimeKind.Utc)));
        var raiz = doc.RootElement;
        Assert.Equal(1, raiz.GetProperty("version").GetInt32());
        Assert.Equal("2026-10-22T17:00:00Z", raiz.GetProperty("verificado").GetString());
        Assert.Equal("alterada", raiz.GetProperty("estado").GetString());
        Assert.Equal("invalida", raiz.GetProperty("firma").GetString());
        Assert.Equal("upd-2026-1", raiz.GetProperty("kid").GetString());
        Assert.Equal(12, raiz.GetProperty("archivos_comprobados").GetInt32());
        var h = raiz.GetProperty("hallazgos")[0];
        Assert.Equal("backend", h.GetProperty("tipo").GetString());
        Assert.Equal(2, h.GetProperty("cantidad").GetInt32());
        Assert.Equal(2, h.GetProperty("ejemplos").GetArrayLength());
    }

    [Fact]
    public void Las_llaves_incrustadas_se_leen_con_tolerancia()
    {
        var hex = new string('a', 64);
        var llaves = Verificador.AnalizarLlaves($"upd-2026-1:{hex}| malformada |upd-corta:abcd|upd-2026-2:{hex}");
        Assert.Equal(["upd-2026-1", "upd-2026-2"], llaves.Keys.OrderBy(k => k).ToArray());
        Assert.Empty(Verificador.AnalizarLlaves(null));
    }
}

/// <summary>Firma real de `cryptography` (Ed25519, semilla de 32 bytes 0x01, mensaje «avacom-integridad»), generada fuera de .NET para probar la compatibilidad de la verificacion.</summary>
internal static class DeEmisorDePython
{
    public const string Firma = "52fa59c097c6ce72d79f94b5dd80515098ea214181b8ff2e88a53fe36ed7dbdf6b56be86eb26feece322da783886ac6812e513355ecfbcb05b46b8685e281a01";
}

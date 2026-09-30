using System.Text.Json;
using Avacom.Lms.Core.Estudio;

namespace Avacom.Lms.Core.Tests;

/// <summary>El JSON canónico de la huella del manifiesto: idéntico al que produce Python (<c>json.dumps</c> con claves ordenadas y sin espacios).</summary>
public sealed class JsonCanonicoTests
{
    private static JsonElement Analizar(string texto) => JsonDocument.Parse(texto).RootElement.Clone();

    [Fact]
    public void ElCanonicoYLaHuella_CoincidenConLosQueProduceElJsonDumpsDePython()
    {
        using var oro = JsonDocument.Parse(CanonicoDorado.Json);
        var entrada = Analizar(oro.RootElement.GetProperty("entrada").GetString()!);

        Assert.Equal(oro.RootElement.GetProperty("canonico_utf8").GetString(), JsonCanonico.Canonico(entrada, soloAscii: false, "huella"));
        Assert.Equal(oro.RootElement.GetProperty("canonico_ascii").GetString(), JsonCanonico.Canonico(entrada, soloAscii: true, "huella"));
        Assert.Equal(oro.RootElement.GetProperty("hash_utf8").GetString(), JsonCanonico.Sha256(entrada, soloAscii: false, "huella"));
        Assert.Equal(oro.RootElement.GetProperty("hash_ascii").GetString(), JsonCanonico.Sha256(entrada, soloAscii: true, "huella"));
        Assert.Equal("fc5ccc3b7f5cb951e78ec21f0c919e8a460db64a0d5ab5dd82255a267d8917fd", oro.RootElement.GetProperty("hash_utf8").GetString());   // el valor de referencia, a la vista
    }

    [Fact]
    public void LaHuellaSeVerificaSinSuPropioCampo_ConLasDosCodificacionesYSinDistinguirMayusculas()
    {
        using var oro = JsonDocument.Parse(CanonicoDorado.Json);
        var manifiesto = Analizar(oro.RootElement.GetProperty("entrada").GetString()!);
        var utf8 = oro.RootElement.GetProperty("hash_utf8").GetString()!;
        var ascii = oro.RootElement.GetProperty("hash_ascii").GetString()!;

        Assert.True(JsonCanonico.CoincideConHuella(manifiesto, utf8));               // lo que fija el contrato
        Assert.True(JsonCanonico.CoincideConHuella(manifiesto, ascii));              // el mismo contenido escrito con \uXXXX (json.dumps por defecto)
        Assert.True(JsonCanonico.CoincideConHuella(manifiesto, utf8.ToUpperInvariant()));
        Assert.True(JsonCanonico.CoincideConHuella(manifiesto, "  " + utf8 + " "));
        Assert.False(JsonCanonico.CoincideConHuella(manifiesto, new string('0', 64)));
        Assert.False(JsonCanonico.CoincideConHuella(manifiesto, ""));
        Assert.False(JsonCanonico.CoincideConHuella(Analizar("[1,2]"), utf8));
    }

    [Fact]
    public void UnCambioMinimoEnElManifiesto_CambiaLaHuella()
    {
        using var oro = JsonDocument.Parse(CanonicoDorado.Json);
        var hash = oro.RootElement.GetProperty("hash_utf8").GetString()!;
        var original = oro.RootElement.GetProperty("entrada").GetString()!;
        Assert.False(JsonCanonico.CoincideConHuella(Analizar(original.Replace("\"bytes\":3", "\"bytes\":4")), hash));
        Assert.False(JsonCanonico.CoincideConHuella(Analizar(original.Replace("ñandú", "ñandu")), hash));
        Assert.False(JsonCanonico.CoincideConHuella(Analizar(original.Replace("diez", "Diez")), hash));
    }

    [Fact]
    public void LaHuellaNoDependeDelOrdenDeLasClavesNiDeLosEspaciosDelOriginal()
    {
        var a = Analizar("""{"b":[1,{"y":2,"x":1}],"a":"é","huella":"x"}""");
        var b = Analizar("{ \"a\" : \"é\",\n  \"huella\": \"otra\",\n  \"b\": [ 1 , { \"x\": 1, \"y\": 2 } ] }");
        Assert.Equal("""{"a":"é","b":[1,{"x":1,"y":2}]}""", JsonCanonico.Canonico(a, soloAscii: false, "huella"));
        Assert.Equal(JsonCanonico.Sha256(a, false, "huella"), JsonCanonico.Sha256(b, false, "huella"));
        Assert.Equal("""{"a":"é","b":[1,{"x":1,"y":2}],"huella":"x"}""", JsonCanonico.Canonico(a));   // sin pedir omitir nada, la huella cuenta
    }

    [Fact]
    public void SoloLaRaizOmiteElCampoHuella_UnoAnidadoSeConserva()
    {
        var manifiesto = Analizar("""{"huella":"x","asignacion":{"huella":"anidada","id":1}}""");
        Assert.Equal("""{"asignacion":{"huella":"anidada","id":1}}""", JsonCanonico.Canonico(manifiesto, soloAscii: false, "huella"));
    }

    [Fact]
    public void LasClavesOrdenanPorPuntoDeCodigo_NoPorUnidadUtf16()
    {
        // U+E000 (BMP) va ANTES que U+1F600 (par sustituto D83D DE00) por punto de código, pero después por unidad UTF-16.
        var manifiesto = Analizar("{\"\\ud83d\\ude00\":2,\"\\ue000\":1,\"z\":0,\"Z\":9,\"10\":3,\"2\":4}");
        Assert.Equal("{\"10\":3,\"2\":4,\"Z\":9,\"z\":0,\"\ue000\":1,\"\U0001F600\":2}", JsonCanonico.Canonico(manifiesto));
    }

    [Fact]
    public void LosNumerosConservanSuTextoOriginal()
    {
        var manifiesto = Analizar("""{"n":[1,2.5,1.0,-0.0,100000.0,1e-07,12345678901234567890,0,-1]}""");
        Assert.Equal("""{"n":[1,2.5,1.0,-0.0,100000.0,1e-07,12345678901234567890,0,-1]}""", JsonCanonico.Canonico(manifiesto));
    }

    [Fact]
    public void LasCadenasSeEscapanComoLoHaceJsonDumps()
    {
        var texto = "a\"b\\c/d<e>&f\n\r\t\b\f\u0001\u001f\u007f\u00e9\u2028\U0001F600";
        var manifiesto = Analizar(System.Text.Json.JsonSerializer.Serialize(new { t = texto }));
        // Sin ensure_ascii: sólo comillas, barra invertida y controles (con \u minúscula); DEL, acentos y emoji van tal cual.
        Assert.Equal("{\"t\":\"a\\\"b\\\\c/d<e>&f\\n\\r\\t\\b\\f\\u0001\\u001f\u007f\u00e9\u2028\U0001F600\"}", JsonCanonico.Canonico(manifiesto));
        // Con ensure_ascii: todo lo que no es ASCII imprimible, como \uXXXX en minúsculas y los no-BMP como par sustituto.
        Assert.Equal("{\"t\":\"a\\\"b\\\\c/d<e>&f\\n\\r\\t\\b\\f\\u0001\\u001f\\u007f\\u00e9\\u2028\\ud83d\\ude00\"}", JsonCanonico.Canonico(manifiesto, soloAscii: true));
    }

    [Fact]
    public void LosLiteralesYLosVacios()
    {
        Assert.Equal("""{"a":[],"b":{},"c":null,"d":true,"e":false,"f":""}""", JsonCanonico.Canonico(Analizar("""{"f":"","e":false,"d":true,"c":null,"b":{},"a":[]}""")));
    }
}

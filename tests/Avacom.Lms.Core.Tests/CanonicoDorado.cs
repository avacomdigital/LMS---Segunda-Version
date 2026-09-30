namespace Avacom.Lms.Core.Tests;

// Generado con Python 3 (json.dumps con sort_keys=True y separators=(",", ":")): la respuesta «de referencia» del canonicalizador del
// contrato (spec-driven/04-modo-estudio/02-modelo-y-api.md §4.4) para un manifiesto con texto no ASCII, controles, comillas, barras,
// números de varias formas y claves que ordenan distinto por punto de código que por unidad UTF-16.
internal static class CanonicoDorado
{
    public const string Json = """"
{
 "entrada": "{\"paquete_id\":\"p-1\",\"vigente_hasta\":1759700000000,\"leccion\":{\"titulo\":\"\u00c1rea y volumen \u00b7 \u00f1and\u00fa \ud83d\ude00\",\"texto\":\"l\u00ednea 1\\nl\u00ednea 2\\t\\\"comillas\\\" \\\\ barra / diagonal <b>&amp; \u2028 fin\\u0001\\u001f\",\"numeros\":[1,2.5,1.0,-0.0,100000.0,1e-07,12345678901234567890],\"vacios\":{\"lista\":[],\"objeto\":{},\"nulo\":null,\"cierto\":true,\"falso\":false},\"\ue000\":\"privada\",\"\ud83d\ude00\":\"emoji\",\"\u00e9\":\"acento\",\"b\":2,\"a\":1,\"B\":3,\"10\":\"diez\",\"2\":\"dos\"},\"archivos\":[{\"sha256\":\"abababababababababababababababababababababababababababababababab\",\"bytes\":3,\"mime\":\"image/png\",\"clase\":\"image\",\"media_ref\":\"img-1\"}],\"no_incluidos\":[{\"media_ref\":\"sim-1\",\"motivo\":\"simulacion\"}],\"generado_en\":1759000000000,\"huella\":\"0000000000000000000000000000000000000000000000000000000000000000\"}",
 "canonico_utf8": "{\"archivos\":[{\"bytes\":3,\"clase\":\"image\",\"media_ref\":\"img-1\",\"mime\":\"image/png\",\"sha256\":\"abababababababababababababababababababababababababababababababab\"}],\"generado_en\":1759000000000,\"leccion\":{\"10\":\"diez\",\"2\":\"dos\",\"B\":3,\"a\":1,\"b\":2,\"numeros\":[1,2.5,1.0,-0.0,100000.0,1e-07,12345678901234567890],\"texto\":\"l\u00ednea 1\\nl\u00ednea 2\\t\\\"comillas\\\" \\\\ barra / diagonal <b>&amp; \u2028 fin\\u0001\\u001f\",\"titulo\":\"\u00c1rea y volumen \u00b7 \u00f1and\u00fa \ud83d\ude00\",\"vacios\":{\"cierto\":true,\"falso\":false,\"lista\":[],\"nulo\":null,\"objeto\":{}},\"\u00e9\":\"acento\",\"\ue000\":\"privada\",\"\ud83d\ude00\":\"emoji\"},\"no_incluidos\":[{\"media_ref\":\"sim-1\",\"motivo\":\"simulacion\"}],\"paquete_id\":\"p-1\",\"vigente_hasta\":1759700000000}",
 "canonico_ascii": "{\"archivos\":[{\"bytes\":3,\"clase\":\"image\",\"media_ref\":\"img-1\",\"mime\":\"image/png\",\"sha256\":\"abababababababababababababababababababababababababababababababab\"}],\"generado_en\":1759000000000,\"leccion\":{\"10\":\"diez\",\"2\":\"dos\",\"B\":3,\"a\":1,\"b\":2,\"numeros\":[1,2.5,1.0,-0.0,100000.0,1e-07,12345678901234567890],\"texto\":\"l\\u00ednea 1\\nl\\u00ednea 2\\t\\\"comillas\\\" \\\\ barra / diagonal <b>&amp; \\u2028 fin\\u0001\\u001f\",\"titulo\":\"\\u00c1rea y volumen \\u00b7 \\u00f1and\\u00fa \\ud83d\\ude00\",\"vacios\":{\"cierto\":true,\"falso\":false,\"lista\":[],\"nulo\":null,\"objeto\":{}},\"\\u00e9\":\"acento\",\"\\ue000\":\"privada\",\"\\ud83d\\ude00\":\"emoji\"},\"no_incluidos\":[{\"media_ref\":\"sim-1\",\"motivo\":\"simulacion\"}],\"paquete_id\":\"p-1\",\"vigente_hasta\":1759700000000}",
 "hash_utf8": "fc5ccc3b7f5cb951e78ec21f0c919e8a460db64a0d5ab5dd82255a267d8917fd",
 "hash_ascii": "622dddf57000453b0a5f6d4f09fc8f2591c0d930a996b9f7a721d40986d0ebf7"
}
"""";
}

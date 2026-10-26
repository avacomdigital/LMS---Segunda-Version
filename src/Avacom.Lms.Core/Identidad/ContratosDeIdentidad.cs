using System.Text;
using System.Text.Json.Serialization;

namespace Avacom.Lms.Core.IdentidadDeDispositivo;

// Identidad de dispositivo (MOD-018, Fase 5, P-24). Core no conoce MAUI ni Android: dónde vive la clave (Keystore de Android, CNG de Windows) entra por interfaz y lo implementa cada app.
//
//  · La clave es EC P-256 y NO se puede exportar: la app firma con ella pero nunca la ve.
//  · El nodo emite un reto de 32 bytes y de un solo uso; el equipo firma «AVACOM-ID1 · reto · su huella» y manda la clave pública, la firma y, en Android al crear la clave, la cadena de atestación.
//  · Se identifica al presentarse y al abrir sesión, no en cada petición. Y NUNCA decide si una tableta entra a clase: sin clave, sin red o con un error, la app sigue como siempre.

/// <summary>Lo que el equipo presenta: su clave pública (SubjectPublicKeyInfo DER), la firma del reto y, si la clave se creó en este momento, la cadena de atestación (certificados DER).</summary>
public sealed record PruebaDeClave(byte[] ClavePublica, byte[] Firma, IReadOnlyList<byte[]> Cadena, string Proveedor);

/// <summary>Quien guarda la clave de identidad del equipo y firma con ella. Android: Keystore (StrongBox si existe); Windows: CNG (TPM si hay, software si no).</summary>
public interface IProveedorDeIdentidad
{
    /// <summary>Con qué se guarda la clave: <c>strongbox</c> · <c>tee</c> · <c>tpm</c> · <c>software</c>. Informativo: el nodo no se fía de lo que el equipo dice de sí mismo.</summary>
    string Nombre { get; }

    /// <summary>
    /// Firma el reto con la clave del equipo; la crea la primera vez (en Android, con el reto como desafío de atestación y devolviendo su cadena). Devuelve null si no hay forma de tener
    /// una clave en este equipo: el nodo lo tratará como «declarada» y todo sigue funcionando.
    /// </summary>
    Task<PruebaDeClave?> ProbarAsync(string identificadorHw, byte[] reto, CancellationToken ct = default);
}

public sealed record RetoDeIdentidad(
    [property: JsonPropertyName("nonce")] string Nonce,
    [property: JsonPropertyName("vence_en")] long VenceEn,
    [property: JsonPropertyName("algoritmo")] string? Algoritmo = null,
    [property: JsonPropertyName("contexto")] string? Contexto = null)
{
    public byte[]? Bytes()
    {
        try { return Convert.FromBase64String(Nonce); }
        catch (FormatException) { return null; }
    }
}

/// <summary>La respuesta del nodo a un enrolamiento: el nivel con que quedó el equipo (<c>declarada</c> · <c>software</c> · <c>hardware</c>) y por qué.</summary>
public sealed record ResultadoDeIdentidad(
    [property: JsonPropertyName("garantia")] string Garantia,
    [property: JsonPropertyName("motivo")] string? Motivo,
    [property: JsonPropertyName("clave_huella")] string? ClaveHuella,
    [property: JsonPropertyName("dispositivo_id")] string? DispositivoId,
    [property: JsonPropertyName("confirmada_en")] long? ConfirmadaEn = null);

public static class ReglasDeIdentidad
{
    /// <summary>El prefijo que ata la firma a este protocolo (el nodo usa el mismo: <c>PREFIJO_DEL_RETO</c>).</summary>
    public const string Prefijo = "AVACOM-ID1";

    /// <summary>Lo que se firma: el reto del nodo atado a la huella con que el equipo se registró (la firma no sirve para otro equipo ni para otro reto).</summary>
    public static byte[] MensajeDelReto(byte[] reto, string identificadorHw)
    {
        ArgumentNullException.ThrowIfNull(reto);
        var prefijo = Encoding.ASCII.GetBytes(Prefijo);
        var huella = Encoding.UTF8.GetBytes(identificadorHw ?? string.Empty);
        var mensaje = new byte[prefijo.Length + reto.Length + huella.Length];
        prefijo.CopyTo(mensaje, 0);
        reto.CopyTo(mensaje, prefijo.Length);
        huella.CopyTo(mensaje, prefijo.Length + reto.Length);
        return mensaje;
    }

    /// <summary>
    /// El cuerpo de la identidad tal como lo espera el nodo (<c>nonce</c>, <c>clave_publica</c>, <c>firma</c>, <c>cadena</c> opcional y <c>proveedor</c>, todo en base64). La cadena sólo va si
    /// existe: en Android la atestación sólo se puede pedir al CREAR la clave.
    /// </summary>
    public static Dictionary<string, object> Cuerpo(byte[] reto, PruebaDeClave prueba)
    {
        var cuerpo = new Dictionary<string, object>
        {
            ["nonce"] = Convert.ToBase64String(reto),
            ["clave_publica"] = Convert.ToBase64String(prueba.ClavePublica),
            ["firma"] = Convert.ToBase64String(prueba.Firma),
        };
        if (prueba.Cadena.Count > 0) cuerpo["cadena"] = prueba.Cadena.Select(Convert.ToBase64String).ToArray();
        if (!string.IsNullOrWhiteSpace(prueba.Proveedor)) cuerpo["proveedor"] = prueba.Proveedor;
        return cuerpo;
    }

    /// <summary>La garantía en palabras del aula (para la pantalla Dispositivos). Vacío o desconocido = «Declarada».</summary>
    public static string Etiqueta(string? garantia) => (garantia ?? string.Empty).Trim().ToLowerInvariant() switch
    {
        "hardware" => "Verificada por hardware",
        "software" => "Con clave propia",
        _ => "Declarada",
    };

    /// <summary>Una línea que explica el nivel, sin jerga: lo que el nodo pudo comprobar de este equipo.</summary>
    public static string Explicacion(string? garantia, string? motivo = null) => (garantia ?? string.Empty).Trim().ToLowerInvariant() switch
    {
        "hardware" => "El equipo probó una clave guardada en su entorno seguro y la app es la de AVACOM.",
        "software" => motivo switch
        {
            "sin_cadena" => "El equipo probó tener una clave propia; el nodo no pudo comprobar dónde la guarda.",
            "raiz_desconocida" => "El equipo probó tener una clave propia; su certificado no llega a una raíz de Google (un emulador, por ejemplo).",
            "gestor_de_arranque_abierto" or "arranque_no_verificado" => "El equipo probó tener una clave propia; su arranque no está verificado o su gestor de arranque está abierto.",
            "app_ajena" or "paquete_ajeno" => "El equipo probó tener una clave propia; la app no coincide con la de AVACOM.",
            _ => "El equipo probó tener una clave propia; el nodo no pudo comprobar más.",
        },
        _ => "El equipo sólo dice quién es: aún no probó una clave.",
    };

    /// <summary>La garantía como número para ordenar y comparar: declarada 0 · software 1 · hardware 2.</summary>
    public static int Nivel(string? garantia) => (garantia ?? string.Empty).Trim().ToLowerInvariant() switch { "hardware" => 2, "software" => 1, _ => 0 };
}

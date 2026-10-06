using System.Globalization;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ops.Acceso;

// Lo que las pantallas de acceso de OPS deciden SIN interfaz: qué se ofrece, qué se avisa, cómo se reanuda el primer arranque y cómo se imprime la hoja.
// Vive aparte para poder probarse con xunit (tests/Avacom.Lms.Ops.Tests compila este archivo tal cual); no usa nada de MAUI.

/// <summary>
/// RN-02 y RN-05 del lado de la pantalla: se avisa ANTES de pedir la confirmación, para no hacer marcar dos veces un PIN que el nodo va a rechazar. El nodo
/// vuelve a validarlo (y es el único que sabe si se repite uno de los tres últimos): esto sólo ahorra un paso, no decide nada.
/// </summary>
public static class PinMaestroLocal
{
    public const int Longitud = 6;

    /// <summary>La regla RN-05 en palabras de aula, para la pantalla que pide marcarlo.</summary>
    public const string Regla = "Seis números que sólo conocerá la escuela. No sirven seis iguales (111111), seguidos (123456 o 654321) ni parejas o tríos que se repiten (121212, 123123).";

    public static bool FormatoValido(string? pin) => pin is { Length: Longitud } && pin.All(c => c is >= '0' and <= '9');

    /// <summary>Lo mismo que <c>PoliticaPinMaestro.es_trivial</c> del nodo.</summary>
    public static bool EsTrivial(string pin)
    {
        if (!FormatoValido(pin)) return false;
        if (pin.Distinct().Count() == 1) return true;
        var pasos = Enumerable.Range(0, pin.Length - 1).Select(i => pin[i + 1] - pin[i]).ToArray();
        if (pasos.All(p => p == 1) || pasos.All(p => p == -1)) return true;
        return pin == string.Concat(Enumerable.Repeat(pin[..2], 3)) || pin == string.Concat(Enumerable.Repeat(pin[..3], 2));
    }

    /// <summary>Qué decir de un PIN recién marcado, o null si se puede pedir la confirmación.</summary>
    public static string? Problema(string pin) =>
        !FormatoValido(pin) ? "El PIN maestro son exactamente seis números."
        : EsTrivial(pin) ? "Ese PIN es demasiado fácil de adivinar: evita números repetidos, seguidos o parejas que se repiten. Marca otro."
        : null;
}

public sealed record Pais(string Codigo, string Nombre, string ZonaHoraria);

/// <summary>Las fichas del paso 1 del primer arranque: nada que escribir.</summary>
public static class Paises
{
    public static readonly IReadOnlyList<Pais> Lista =
    [
        new("CO", "Colombia", "America/Bogota"),
        new("MX", "México", "America/Mexico_City"),
        new("PE", "Perú", "America/Lima"),
        new("EC", "Ecuador", "America/Guayaquil"),
        new("CL", "Chile", "America/Santiago"),
        new("AR", "Argentina", "America/Argentina/Buenos_Aires"),
        new("ES", "España", "Europe/Madrid"),
        new("US", "Estados Unidos", "America/New_York"),
    ];

    public static readonly IReadOnlyList<(string Codigo, string Nombre)> Idiomas = [("es", "Español"), ("en", "English")];

    public static Pais Por(string? codigo) => Lista.FirstOrDefault(p => p.Codigo == codigo) ?? Lista[0];
}

/// <summary>El código de la organización sale del nombre del aula: nadie tiene que inventarlo (en el equipo táctil cada letra cuesta).</summary>
public static class CodigoDeAula
{
    public static string Desde(string? nombre)
    {
        var sinTildes = new StringBuilder();
        foreach (var c in (nombre ?? string.Empty).Normalize(NormalizationForm.FormD))
        {
            if (CharUnicodeInfo.GetUnicodeCategory(c) == UnicodeCategory.NonSpacingMark) continue;
            sinTildes.Append(char.IsLetterOrDigit(c) && c < 128 ? char.ToUpperInvariant(c) : '-');
        }
        var codigo = string.Join('-', sinTildes.ToString().Split('-', StringSplitOptions.RemoveEmptyEntries));
        if (codigo.Length > 32) codigo = codigo[..32].TrimEnd('-');
        return codigo.Length == 0 ? "AULA" : codigo;
    }
}

/// <summary>
/// Lo escrito en los pasos 1–3 del primer arranque, para reanudar si se interrumpe (RF-01). Sólo datos NO secretos: el PIN maestro nunca se guarda aquí, y
/// la contraseña y el PIN de la hoja van cifrados aparte (<see cref="HojaDeAcceso"/>). <c>Paso</c> es el que toca mostrar: el último confirmado más uno.
/// </summary>
public sealed record BorradorDeInstalacion(
    [property: JsonPropertyName("paso")] int Paso = 1,
    [property: JsonPropertyName("pais")] string Pais = "CO",
    [property: JsonPropertyName("idioma")] string Idioma = "es",
    [property: JsonPropertyName("aula")] string Aula = "",
    [property: JsonPropertyName("documento")] string Documento = "",
    [property: JsonPropertyName("nombres")] string Nombres = "",
    [property: JsonPropertyName("apellidos")] string Apellidos = "")
{
    public const int PasoPais = 1, PasoAula = 2, PasoAdministrador = 3, PasoPin = 4, PasoHoja = 5;

    public string ToJson() => JsonSerializer.Serialize(this);

    /// <summary>Un borrador ilegible o de otra versión empieza de cero, nunca a medias.</summary>
    public static BorradorDeInstalacion Desde(string? json)
    {
        if (string.IsNullOrWhiteSpace(json)) return new();
        try
        {
            var b = JsonSerializer.Deserialize<BorradorDeInstalacion>(json) ?? new();
            return b with { Paso = b.PasoReanudable };
        }
        catch (JsonException) { return new(); }
    }

    /// <summary>
    /// Nunca se reanuda más allá de lo que de verdad se confirmó: sin aula no hay paso 3, sin administrador no hay paso 4, y la hoja (paso 5) sólo existe si
    /// está guardada aparte; un borrador sin ella vuelve al PIN.
    /// </summary>
    public int PasoReanudable
    {
        get
        {
            var paso = Math.Clamp(Paso, PasoPais, PasoPin);
            if (paso > PasoAula && string.IsNullOrWhiteSpace(Aula)) paso = PasoAula;
            if (paso > PasoAdministrador && (string.IsNullOrWhiteSpace(Documento) || string.IsNullOrWhiteSpace(Nombres))) paso = PasoAdministrador;
            return paso;
        }
    }
}

/// <summary>
/// PAN-204 · la hoja de acceso del primer arranque: la contraseña inicial del administrador (la genera el nodo y llega UNA vez) y el PIN maestro recién
/// marcado. Hasta que alguien confirma «Ya la entregué» vive cifrada en el equipo (SecureStorage); después se borra y no se puede volver a ver (RN-04).
/// </summary>
public sealed record HojaDeAcceso(
    [property: JsonPropertyName("aula")] string Aula,
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("administrador")] string Administrador,
    [property: JsonPropertyName("documento")] string Documento,
    [property: JsonPropertyName("contrasena")] string Contrasena,
    [property: JsonPropertyName("pin_maestro")] string PinMaestro,
    [property: JsonPropertyName("creada_en")] long CreadaEn)
{
    public string ToJson() => JsonSerializer.Serialize(this);

    public static HojaDeAcceso? Desde(string? json)
    {
        if (string.IsNullOrWhiteSpace(json)) return null;
        try
        {
            var h = JsonSerializer.Deserialize<HojaDeAcceso>(json);
            return h is null || string.IsNullOrEmpty(h.Contrasena) || string.IsNullOrEmpty(h.PinMaestro) ? null : h;
        }
        catch (JsonException) { return null; }
    }

    /// <summary>El PIN en dos grupos de tres, como se dicta en voz alta: «482 915».</summary>
    public string PinLegible => PinMaestro.Length == 6 ? $"{PinMaestro[..3]} {PinMaestro[3..]}" : PinMaestro;

    /// <summary>Una página imprimible, sin dependencias: se abre en el navegador del equipo y pide imprimir sola.</summary>
    public string Html()
    {
        static string E(string? s) => WebUtility.HtmlEncode(s ?? string.Empty);
        var fecha = DateTimeOffset.FromUnixTimeMilliseconds(CreadaEn).ToLocalTime().ToString("d 'de' MMMM 'de' yyyy, HH:mm", new CultureInfo("es-ES"));
        return $$"""
            <!doctype html>
            <html lang="es"><head><meta charset="utf-8"><title>Hoja de acceso · {{E(Aula)}}</title>
            <style>
              @page { size: A4; margin: 18mm; }
              body { font-family: "Segoe UI", Arial, sans-serif; color: #18181B; max-width: 720px; margin: 24px auto; }
              h1 { font-size: 26px; margin: 0 0 4px; } .sub { color: #52525B; margin: 0 0 28px; }
              .caja { border: 2px solid #18181B; border-radius: 14px; padding: 18px 22px; margin: 0 0 18px; }
              .rotulo { font-size: 13px; letter-spacing: .12em; text-transform: uppercase; color: #52525B; margin: 0 0 6px; }
              .valor { font-family: Consolas, "Courier New", monospace; font-size: 34px; font-weight: 700; letter-spacing: .06em; margin: 0; }
              .nota { font-size: 14px; line-height: 1.5; color: #3F3F46; } ol { padding-left: 20px; }
            </style></head>
            <body onload="window.print()">
              <h1>Hoja de acceso · {{E(Aula)}}</h1>
              <p class="sub">Código del aula {{E(Codigo)}} · creada el {{E(fecha)}}</p>
              <div class="caja"><p class="rotulo">Administrador</p><p class="valor" style="font-size:24px">{{E(Administrador)}}</p>
                <p class="nota">Documento: <b>{{E(Documento)}}</b></p></div>
              <div class="caja"><p class="rotulo">Contraseña inicial del administrador</p><p class="valor">{{E(Contrasena)}}</p>
                <p class="nota">Es provisional: la primera vez que entres, el equipo te pedirá elegir una propia.</p></div>
              <div class="caja"><p class="rotulo">PIN maestro de la escuela</p><p class="valor">{{E(PinLegible)}}</p>
                <p class="nota">Con él los profesores crean su usuario y recuperan su contraseña, y la administración entra al equipo.
                Vence en un año. Nadie puede volver a verlo en el equipo: si se olvida, la administración lo reemplaza.</p></div>
              <ol class="nota">
                <li>Guarda esta hoja en un lugar seguro y entrégala sólo a la administración.</li>
                <li>Esta hoja no se puede volver a imprimir.</li>
              </ol>
            </body></html>
            """;
    }
}

/// <summary>
/// RF-05 · RN-03 · RF-09: qué ofrece la pantalla de acceso a quien todavía no puede entrar. Sin PIN maestro configurado ni el alta ni la recuperación de
/// profesores existen; con el registro cerrado sólo queda «Olvidé mi contraseña»; con el PIN vencido las dos acciones siguen ahí y explican qué pasó.
/// </summary>
public sealed record OfertaDeCuenta(bool CrearMiUsuario, bool OlvideMiContrasena, string? Nota, string? AvisoAlTocar)
{
    public const string SinPinMaestro = "Crear tu usuario y recuperar tu contraseña se activan cuando la administración configure el PIN maestro.";
    public const string RegistroCerrado = "El registro de profesores está cerrado. Si aún no tienes usuario, pídeselo a la administración.";
    public const string PinVencido = "El PIN maestro venció. Pídele a administración que lo cambie y vuelve a intentarlo.";

    public static OfertaDeCuenta Para(ConfiguracionAcceso? configuracion)
    {
        if (configuracion is not { Instalado: true }) return new(false, false, null, null);
        if (configuracion.PinMaestro is not { Configurado: true } pin) return new(false, false, SinPinMaestro, null);
        if (pin.Vencido) return new(configuracion.AutoregistroDocentes, true, null, PinVencido);
        if (!configuracion.AutoregistroDocentes) return new(false, true, RegistroCerrado, null);
        return new(true, true, null, null);
    }
}

/// <summary>
/// RN-08 · RF-09: la banda del tablero. Administración y técnico la ven a 30 días o menos del vencimiento (la administración con los días exactos, porque
/// puede leer el estado fino); al profesorado nunca se le muestra una cuenta atrás. También avisa si el PIN venció o si el equipo aún no tiene uno (nodos que
/// se actualizaron desde una versión anterior).
/// </summary>
public static class AvisoDelPinMaestro
{
    private static readonly CultureInfo Es = new("es-ES");

    public static string? Texto(UsuarioDeSesion? usuario, EstadoPublicoDelPin? publico, EstadoPinMaestro? fino = null)
    {
        if (usuario is null || !(usuario.EsAdministracion || usuario.EsTecnico)) return null;
        var admin = usuario.EsAdministracion;
        var configurado = fino?.Configurado ?? publico?.Configurado;
        if (configurado is null) return null;
        if (configurado == false)
            return admin
                ? "Este equipo todavía no tiene PIN maestro. Configúralo en Seguridad del aula: sin él, los profesores no pueden crear su usuario ni recuperar su contraseña."
                : "Este equipo todavía no tiene PIN maestro. Pídele a la administración que lo configure.";
        if (fino?.Vencido ?? publico?.Vencido ?? false)
            return admin
                ? "El PIN maestro venció. Mientras no lo cambies, los profesores no pueden crear su usuario ni recuperar su contraseña. Cámbialo en Seguridad del aula."
                : "El PIN maestro venció. Avisa a la administración para que lo cambie.";
        if (!(fino?.Aviso ?? publico?.PorVencer ?? false)) return null;
        if (!admin || fino?.DiasRestantes is not { } dias) return "El PIN maestro vence en menos de 30 días. Avisa a la administración para que lo cambie.";
        var cuando = dias switch { <= 0 => "hoy", 1 => "mañana", _ => $"en {dias} días" };
        var fecha = fino.VenceEl is { } v ? $" ({v.ToString("d 'de' MMMM", Es)})" : string.Empty;
        return $"El PIN maestro vence {cuando}{fecha}. Cámbialo en Seguridad del aula antes de esa fecha.";
    }
}

/// <summary>Lo que se comprueba de una contraseña nueva antes de enviarla; las reglas finas (mayúscula, símbolo) las dice el nodo con <c>secreto_debil</c>.</summary>
public static class ContrasenaNueva
{
    public static string? Problema(string? nueva, string? repetida, int minimo)
    {
        if (string.IsNullOrEmpty(nueva) || string.IsNullOrEmpty(repetida)) return "Escribe tu contraseña nueva dos veces.";
        if (nueva != repetida) return "Las dos contraseñas no coinciden. Escríbelas otra vez.";
        if (nueva.Length < minimo) return $"La contraseña necesita al menos {minimo} caracteres.";
        return null;
    }

    /// <summary>La longitud mínima del perfil según la configuración pública del nodo (<c>perfiles.teacher.longitud_minima</c>), o la de fábrica.</summary>
    public static int Minimo(ConfiguracionAcceso? configuracion, string perfil, int porDefecto)
    {
        if (configuracion?.Perfiles is { ValueKind: JsonValueKind.Object } perfiles
            && perfiles.TryGetProperty(perfil, out var p) && p.ValueKind == JsonValueKind.Object
            && p.TryGetProperty("longitud_minima", out var l) && l.TryGetInt32(out var n) && n > 0)
            return n;
        return porDefecto;
    }
}

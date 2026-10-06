namespace Avacom.Lms.Ops;

/// <summary>
/// Las preferencias y el almacén cifrado de OPS, con un <b>perfil de pruebas</b> opcional. Todas las instancias de OPS de un equipo comparten
/// <see cref="Preferences"/>: una OPS de prueba que escribiera la dirección del servidor, el id del equipo o el borrador del primer arranque se los cambiaría a
/// la instancia de quien trabaja en ese equipo. Con la variable de entorno <c>AVACOM_OPS_PERFIL</c> (la usa <c>tests/Avacom.Lms.Ops.Uia</c>) todo se guarda en
/// un contenedor aparte con ese nombre y la dirección del servidor sale de <c>AVACOM_OPS_SERVIDOR</c>. Sin la variable no cambia nada.
/// </summary>
public static class Ajustes
{
    /// <summary>El perfil de pruebas activo, o null en el uso normal.</summary>
    public static string? Perfil { get; } = Environment.GetEnvironmentVariable("AVACOM_OPS_PERFIL") is { Length: > 0 } p ? p.Trim() : null;

    /// <summary>La dirección del nodo que fija el perfil de pruebas (sólo con <see cref="Perfil"/>).</summary>
    public static string? ServidorDePrueba { get; } =
        Perfil is not null && Environment.GetEnvironmentVariable("AVACOM_OPS_SERVIDOR") is { Length: > 0 } s ? s.Trim() : null;

    /// <summary>
    /// Sólo con el perfil de pruebas y <c>AVACOM_OPS_CLAVES_VISIBLES=1</c>: los campos de contraseña no se enmascaran. El campo enmascarado de MAUI en Windows
    /// (MauiPasswordTextBox) no acepta el ValuePattern de UI Automation —el texto se ve pero la contraseña queda vacía—, así que sin esto el recorrido de
    /// interfaz no podría escribir una contraseña sin tomar el teclado de quien trabaja en el equipo. Sin el perfil no hace nada.
    /// </summary>
    public static bool ClavesVisiblesDePrueba { get; } = Perfil is not null && Environment.GetEnvironmentVariable("AVACOM_OPS_CLAVES_VISIBLES") == "1";

    private static string? _rutaDePrueba = Perfil is not null && Environment.GetEnvironmentVariable("AVACOM_OPS_RUTA") is { Length: > 0 } r ? r.Trim() : null;

    /// <summary>
    /// Sólo con el perfil de pruebas: la pantalla a la que el tablero salta UNA vez al aparecer (<c>AVACOM_OPS_RUTA</c>, p. ej. <c>activity-monitor</c>). Existe
    /// porque las teselas hexagonales se tocan con un gesto que UI Automation no puede invocar; sin el perfil no hace nada.
    /// </summary>
    public static string? TomarRutaDePrueba()
    {
        var r = _rutaDePrueba;
        _rutaDePrueba = null;
        return r;
    }

    private static string? Contenedor => Perfil is null ? null : $"avacom_ops_{Perfil}";

    public static T Get<T>(string clave, T porDefecto) =>
        Contenedor is { } c ? Preferences.Default.Get(clave, porDefecto, c) : Preferences.Default.Get(clave, porDefecto);

    public static void Set<T>(string clave, T valor)
    {
        if (Contenedor is { } c) Preferences.Default.Set(clave, valor, c);
        else Preferences.Default.Set(clave, valor);
    }

    public static void Remove(string clave)
    {
        if (Contenedor is { } c) Preferences.Default.Remove(clave, c);
        else Preferences.Default.Remove(clave);
    }

    private static string ClaveSegura(string clave) => Perfil is null ? clave : $"{Contenedor}_{clave}";

    /// <summary>SecureStorage (DPAPI en Windows). Si el almacén no está disponible devuelve null: quien llama decide qué decir.</summary>
    public static async Task<string?> LeerSecretoAsync(string clave)
    {
        try { return await SecureStorage.Default.GetAsync(ClaveSegura(clave)); }
        catch (Exception) { return null; }
    }

    public static async Task<bool> GuardarSecretoAsync(string clave, string valor)
    {
        try { await SecureStorage.Default.SetAsync(ClaveSegura(clave), valor); return true; }
        catch (Exception) { return false; }
    }

    public static void BorrarSecreto(string clave)
    {
        try { SecureStorage.Default.Remove(ClaveSegura(clave)); } catch (Exception) { /* no había nada que borrar */ }
    }
}

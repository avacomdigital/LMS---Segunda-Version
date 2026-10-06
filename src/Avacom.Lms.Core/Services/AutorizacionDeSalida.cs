namespace Avacom.Lms.Core.Services;

/// <summary>
/// PAN-241 · Escalada temporal: la «autorización de salida» que exige exportar la bitácora (MOD-019, ESC-03, BR-105). Otra persona de
/// administración se identifica en este mismo equipo, concede a quien está al frente una escalada de <c>audit.export</c> (vale una operación:
/// el nodo la consume al exportar) y se despide en el mismo paso. Durante esos milisegundos el pase del proceso es el de quien autoriza; al
/// terminar vuelve a ser el de quien usa el equipo, pase lo que pase. No existe la autoconcesión (BR-101): el nodo la niega y aquí se corta antes.
/// Vive en el Core para poder probarse contra un backend falso; OPS sólo la llama.
/// </summary>
public static class AutorizacionDeSalida
{
    public const string PermisoExportar = "audit.export";
    public static readonly TimeSpan Vigencia = TimeSpan.FromMinutes(30);

    /// <summary>Motivos de lista (nodo táctil): el nodo guarda el texto en la escalada y en el asiento.</summary>
    public static readonly string[] Motivos =
    [
        "Inspección interna", "Auditoría externa", "Requerimiento legal o de la autoridad educativa", "Respaldo externo de evidencia", "Soporte técnico de AVACOM",
    ];

    /// <summary><c>RequierePinMaestro</c>: quien autoriza es de administración y el nodo exige además el PIN maestro; la pantalla lo pide con el teclado y repite.</summary>
    public sealed record Resultado(bool Ok, string Mensaje, long? VigenteHastaMs = null, bool RequierePinMaestro = false);

    /// <summary>
    /// <paramref name="beneficiarioId"/> es quien usa el equipo (recibe la escalada); <paramref name="documento"/> y <paramref name="clave"/> son
    /// de quien autoriza; <paramref name="pinMaestro"/> es el PIN maestro, que toda cuenta de administración presenta además de su clave mientras esté vigente.
    /// <paramref name="dispositivo"/> es la huella del equipo para el login. Devuelve el resultado y deja <see cref="ClienteJson.Token"/> exactamente como estaba.
    /// </summary>
    public static async Task<Resultado> ConcederAsync(IAccesoApi acceso, string? beneficiarioId, string dispositivo, string documento, string clave, string motivo,
                                                     CancellationToken ct = default, string? pinMaestro = null)
    {
        if (string.IsNullOrEmpty(beneficiarioId)) return new(false, "Hace falta una sesión de usuario en este equipo.");
        if (string.IsNullOrWhiteSpace(documento) || string.IsNullOrWhiteSpace(clave)) return new(false, "Escribe el documento y la clave de quien autoriza.");
        if (string.IsNullOrWhiteSpace(motivo)) return new(false, "Elige el motivo de la autorización.");
        var miPase = ClienteJson.Token;
        try
        {
            var otra = await acceso.IniciarSesionAsync(documento.Trim(), clave, dispositivo, pinMaestro: pinMaestro, ct: ct);
            if (otra is null)
            {
                var error = acceso.UltimoError;
                if (error is { PinMaestroRequerido: true }) return new(false, "Quien autoriza es de administración: escribe además el PIN maestro.", RequierePinMaestro: true);
                if (error is { PinMaestroInvalido: true } or { PinMaestroBloqueado: true }) return new(false, MensajesDeAcceso.Texto(error), RequierePinMaestro: true);
                return new(false, error?.Codigo == "credenciales_invalidas" ? "Documento o clave incorrectos." : error?.Detalle ?? "No se pudo identificar a quien autoriza.");
            }
            if (otra.Usuario.Id == beneficiarioId)
            {
                await acceso.CerrarSesionAsync(ct);
                return new(false, "No existe la autoconcesión: quien autoriza debe ser otra persona de administración.");
            }
            var vigenteHasta = DateTimeOffset.UtcNow.Add(Vigencia).ToUnixTimeMilliseconds();
            var escalada = await acceso.OtorgarEscaladaAsync(beneficiarioId, PermisoExportar, "ORGANIZATION", motivo, vigenteHasta, ct);
            var errorEscalada = acceso.UltimoError;   // el cierre de sesión que sigue lo borraría
            await acceso.CerrarSesionAsync(ct);   // quien autoriza no deja sesión abierta aquí
            if (escalada is null)
            {
                var error = errorEscalada;
                return new(false, error?.Codigo == "sin_permiso" ? "Esa persona no puede conceder escaladas (hace falta el rol de administración)." : error?.Detalle ?? "El nodo no concedió la autorización.");
            }
            RegistroLocal.Info(Canal.Aplicacion, "auditoria.salida_autorizada", "Autorización de salida concedida",
                               new { usuario_id = beneficiarioId, permiso = PermisoExportar, minutos = Vigencia.TotalMinutes });
            return new(true, $"Autorización concedida hasta las {DateTimeOffset.FromUnixTimeMilliseconds(vigenteHasta).ToLocalTime():HH:mm}. Se registra todo lo que hagas con ella (MSG-052).", vigenteHasta);
        }
        catch (Exception ex)
        {
            RegistroLocal.Error(Canal.Aplicacion, "auditoria.salida_fallo", "No se pudo completar la autorización de salida", new { tipo = ex.GetType().Name }, ex);
            return new(false, "No se pudo completar la autorización.");
        }
        finally
        {
            ClienteJson.Token = miPase;   // el pase de quien usa el equipo vuelve siempre
        }
    }
}

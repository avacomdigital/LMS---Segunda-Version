using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ops;

/// <summary>
/// PAN-241 · Escalada temporal en OPS: la «autorización de salida» que exige exportar la bitácora (MOD-019, ESC-03, BR-105). La lógica vive en
/// <see cref="AutorizacionDeSalida"/> (Core, probada contra un backend falso); aquí sólo se le pasan la sesión y el equipo de OPS.
/// </summary>
public static class Autorizaciones
{
    public static readonly string[] MotivosDeAutorizacion = AutorizacionDeSalida.Motivos;

    public static async Task<(bool Ok, string Mensaje)> AutorizarSalidaAsync(string documentoDeQuienAutoriza, string claveDeQuienAutoriza, string motivo, CancellationToken ct = default)
    {
        var r = await AutorizacionDeSalida.ConcederAsync(Sesion.Acceso, Sesion.Usuario?.Id, Sesion.Dispositivo, documentoDeQuienAutoriza, claveDeQuienAutoriza, motivo, ct);
        return (r.Ok, r.Mensaje);
    }
}

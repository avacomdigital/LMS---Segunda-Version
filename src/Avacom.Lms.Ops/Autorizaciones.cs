using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ops;

/// <summary>
/// PAN-241 · Escalada temporal en OPS: la «autorización de salida» que exige exportar la bitácora (MOD-019, ESC-03, BR-105). La lógica vive en
/// <see cref="AutorizacionDeSalida"/> (Core, probada contra un backend falso); aquí sólo se le pasan la sesión y el equipo de OPS.
/// </summary>
public static class Autorizaciones
{
    public static readonly string[] MotivosDeAutorizacion = AutorizacionDeSalida.Motivos;

    /// <summary>
    /// <c>RequierePinMaestro</c>: quien autoriza es de administración y el nodo pide además el PIN maestro (o el que se marcó no era): la pantalla muestra el
    /// teclado propio y vuelve a llamar con <paramref name="pinMaestro"/>, conservando el documento y la clave mientras tanto.
    /// </summary>
    public static async Task<(bool Ok, string Mensaje, bool RequierePinMaestro)> AutorizarSalidaAsync(string documentoDeQuienAutoriza, string claveDeQuienAutoriza, string motivo,
                                                                                                    string? pinMaestro = null, CancellationToken ct = default)
    {
        if (pinMaestro is not null) await Sesion.AsegurarEquipoAsync();   // RN-11: el nodo sólo acepta el PIN de un equipo que no es tableta de alumno
        var r = await AutorizacionDeSalida.ConcederAsync(Sesion.Acceso, Sesion.Usuario?.Id, Sesion.Dispositivo, documentoDeQuienAutoriza, claveDeQuienAutoriza, motivo, ct, pinMaestro);
        return (r.Ok, r.Mensaje, r.RequierePinMaestro);
    }
}

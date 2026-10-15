using Avacom.Lms.Core.Diagnostico;
using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>
/// Lee <c>GET /api/gradebook/escalas/{id}/</c>: una escala adoptada CON sus versiones y la definición de cada una (los tramos de desempeño). El cliente de Core
/// (<c>IGradebookApi</c>) no trae esa lectura: <c>/configuracion/</c> sólo manda de cada escala su <c>ultima_version</c> (id, número, huella) sin definición, y Core no la
/// modela. Hasta que Core la incluya, OPS la lee con este cliente propio, con las mismas reglas de degradación que los demás (un error devuelve null y deja el motivo).
/// La respuesta es exactamente la forma de <see cref="EscalaAdoptada"/>.
///
/// Una versión de escala es inmutable (el nodo no tiene ruta para editarla), así que lo leído de una versión se guarda en memoria y no se vuelve a pedir.
/// </summary>
internal sealed class LectorDeEscalas(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri)
{
    private static readonly HttpClient Http = new(new HandlerDeMedicion()) { Timeout = TimeSpan.FromSeconds(15) };
    private static LectorDeEscalas? _actual;
    private static readonly Dictionary<string, EscalaAdoptada> PorVersion = [];

    /// <summary>El lector del nodo actual (una instancia por dirección, como los clientes de <c>Sesion</c>).</summary>
    public static LectorDeEscalas Actual
    {
        get
        {
            var actual = Sesion.BaseUri;
            if (_actual is null || _actual.BaseUri != actual) _actual = new LectorDeEscalas(Http, actual);
            return _actual;
        }
    }

    /// <summary>La escala con todas sus versiones, o null si no se pudo leer (el motivo queda en <c>UltimoMotivo</c> y <c>UltimoError</c>).</summary>
    public async Task<EscalaAdoptada?> EscalaAsync(string actor, string escalaId, CancellationToken ct = default)
    {
        var escala = await ObtenerAsync<EscalaAdoptada>($"api/gradebook/escalas/{Uri.EscapeDataString(escalaId)}/?actor={Uri.EscapeDataString(actor)}", ct);
        if (escala?.Versiones is { } versiones)
            foreach (var v in versiones) PorVersion[v.Id] = escala;
        return escala;
    }

    /// <summary>La última versión de una escala (la que el nodo usa al adoptarla para un nivel).</summary>
    public static VersionDeEscala? UltimaVersion(EscalaAdoptada? escala) => escala?.Versiones?.OrderByDescending(v => v.Numero).FirstOrDefault();

    /// <summary>
    /// Los tramos de desempeño de una versión de escala. Si la versión ya se leyó, no vuelve a pedirla. Vacío (y la acción de valorar se omite) si no se puede leer.
    /// </summary>
    public async Task<IReadOnlyList<TramoDeEscala>> TramosAsync(string actor, string escalaId, string? versionId)
    {
        EscalaAdoptada? escala = null;
        if (versionId is not null) PorVersion.TryGetValue(versionId, out escala);
        escala ??= await EscalaAsync(actor, escalaId);
        var version = escala?.Versiones?.FirstOrDefault(v => v.Id == versionId) ?? UltimaVersion(escala);
        return TramosDeEscala.Leer(version?.Definicion);
    }
}

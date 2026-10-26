namespace Avacom.Lms.Core.IdentidadDeDispositivo;

/// <summary>
/// Quien se identifica ante el nodo en nombre de este equipo (MOD-018, Fase 5). Mejor esfuerzo y SIN excepciones hacia la pantalla: sin proveedor de clave (un equipo sin Keystore ni CNG), sin red
/// o con cualquier error, las dos operaciones devuelven null y la app sigue exactamente como antes. El nodo decide el nivel de garantía; aquí sólo se presenta la prueba.
/// </summary>
public sealed class IdentidadDeEquipo(IdentidadApi api, IProveedorDeIdentidad? proveedor, Action<string, string>? registrar = null)
{
    private static readonly TimeSpan Tope = TimeSpan.FromSeconds(8);

    /// <summary>El proveedor de este equipo, si lo hay (lo instala cada app al arrancar: Keystore en Android, CNG en Windows).</summary>
    public static IProveedorDeIdentidad? Proveedor { get; set; }

    public bool Disponible => proveedor is not null;

    private void Anotar(string evento, string detalle) => registrar?.Invoke(evento, detalle);

    private async Task<(byte[] Reto, Dictionary<string, object> Cuerpo)?> PreparaAsync(string identificadorHw, CancellationToken ct)
    {
        if (proveedor is null) return null;
        var reto = (await api.RetoAsync(ct))?.Bytes();
        if (reto is null || reto.Length < 16) return null;
        var prueba = await proveedor.ProbarAsync(identificadorHw, reto, ct);
        return prueba is null ? null : (reto, ReglasDeIdentidad.Cuerpo(reto, prueba));
    }

    /// <summary>
    /// La identidad que viaja DENTRO del registro de un equipo nuevo (primer contacto): el nodo la verifica junto al cupo y, si la licencia pide un nivel mínimo, es lo que deja entrar a un equipo
    /// nuevo. Null si no se puede probar nada; el registro se hace igual y el equipo entra como «declarada».
    /// </summary>
    public async Task<Dictionary<string, object>?> ParaRegistroAsync(string identificadorHw, CancellationToken ct = default)
    {
        try
        {
            using var tope = CancellationTokenSource.CreateLinkedTokenSource(ct);
            tope.CancelAfter(Tope);
            return (await PreparaAsync(identificadorHw, tope.Token))?.Cuerpo;
        }
        catch (Exception ex)
        {
            Anotar("identidad.preparacion_fallo", ex.GetType().Name);
            return null;
        }
    }

    /// <summary>
    /// Se identifica ante el nodo con un reto nuevo (al presentarse y al abrir sesión): la primera vez enrola la clave y, en Android, su atestación; las siguientes sólo firma el reto. Devuelve lo que
    /// el nodo contestó, o null si no hubo respuesta (sin red, sin clave, 404 porque el equipo aún no se registró, 409 porque cambió de clave).
    /// </summary>
    public async Task<ResultadoDeIdentidad?> ConfirmarAsync(string identificadorHw, CancellationToken ct = default)
    {
        try
        {
            using var tope = CancellationTokenSource.CreateLinkedTokenSource(ct);
            tope.CancelAfter(Tope);
            if (await PreparaAsync(identificadorHw, tope.Token) is not { } preparada) return null;
            var resultado = await api.EnrolarAsync(identificadorHw, preparada.Cuerpo, tope.Token);
            if (resultado is null) Anotar("identidad.rechazada", api.UltimoError?.Codigo ?? api.UltimoMotivo ?? "sin_respuesta");
            else Anotar("identidad.confirmada", resultado.Garantia);
            return resultado;
        }
        catch (Exception ex)
        {
            Anotar("identidad.fallo", ex.GetType().Name);
            return null;
        }
    }
}

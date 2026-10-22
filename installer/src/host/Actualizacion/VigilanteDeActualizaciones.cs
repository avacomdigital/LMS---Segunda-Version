using System.Text.Json;

namespace Avacom.Ops.Host.Actualizacion;

/// <summary>
/// Lo que el servicio hace con Actualizaciones\orden.json (MOD-017, P-06): la mira cada pocos segundos, la obedece UNA vez (con el aplicador) y, al arrancar, retoma o
/// deshace lo que un corte dejo a medias. No sabe de paquetes: solo de la orden y del resultado. Todo lo que escribe lo lee el backend al volver (FUN-187).
/// </summary>
internal sealed class VigilanteDeActualizaciones
{
    private readonly Registro _r = new("actualizacion.log");
    private readonly Aplicador _aplicador;
    private string? _atendida;                          // la orden de este proceso que ya se intento: nunca dos veces
    private DateTime _ultimoMantenimiento = DateTime.MinValue;

    public VigilanteDeActualizaciones() => _aplicador = new Aplicador(_r);

    /// <summary>Antes de levantar el backend por primera vez: la carpeta existe y esta restringida, un corte anterior se retoma o se deshace, y las instantaneas viejas se retiran.</summary>
    public void Arrancar()
    {
        try
        {
            Directory.CreateDirectory(Rutas.CarpetaActualizaciones);
            Rutas.RestringirALaAdministracion(Rutas.CarpetaActualizaciones);
            _aplicador.Recuperar();
            Mantener(forzar: true);
        }
        catch (Exception error)
        {
            // Una actualizacion rota no puede impedir que el aula arranque.
            _r.Escribir("El arranque del vigilante de actualizaciones fallo", error);
        }
    }

    /// <summary>¿Hay una orden que este proceso todavia no atendio y que el backend aun no tiene cerrada?</summary>
    public bool HayOrdenNueva()
    {
        try
        {
            if (!File.Exists(Aplicador.RutaDeOrden)) return false;
            var id = IdDe(Aplicador.RutaDeOrden);
            if (id is null || id == _atendida) return false;
            if (File.Exists(Aplicador.RutaDeResultado) && IdDe(Aplicador.RutaDeResultado) == id) return false;
            return true;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    /// <summary>
    /// Obedece la orden. <paramref name="pararBackend"/> se llama una sola vez y solo si hace falta (despues de comprobar que no hay clase). Devuelve true si se paro el backend
    /// (el llamador debe volver a levantarlo), false si no (aplazada o rechazada: el backend sigue como estaba).
    /// </summary>
    public bool Atender(Action pararBackend)
    {
        var parado = false;
        try
        {
            _atendida = IdDe(Aplicador.RutaDeOrden);
            Orden orden;
            try
            {
                orden = Orden.Leer(Aplicador.RutaDeOrden);
            }
            catch (OrdenInvalida error)
            {
                _aplicador.RechazarOrdenIlegible(error.Message);
                return false;
            }
            _aplicador.Procesar(orden, () => { parado = true; pararBackend(); });
        }
        catch (Exception error)
        {
            // Un fallo inesperado del orquestador: el checkpoint queda donde estaba y el siguiente arranque lo recupera.
            _r.Escribir("El aplicador de actualizaciones fallo de forma inesperada", error);
        }
        return parado;
    }

    /// <summary>Retira las instantaneas de mas de 14 dias, a lo sumo cada 30 minutos.</summary>
    public void Mantener(bool forzar = false)
    {
        if (!forzar && DateTime.UtcNow - _ultimoMantenimiento < TimeSpan.FromMinutes(30)) return;
        _ultimoMantenimiento = DateTime.UtcNow;
        _aplicador.Mantenimiento();
    }

    /// <summary>El verbo <c>aplicar-actualizacion</c> (el servicio PARADO): retoma lo pendiente y atiende la orden. Devuelve el codigo de salida.</summary>
    public int AplicarAhora()
    {
        Arrancar();
        if (HayOrdenNueva()) Atender(() => { });
        if (!File.Exists(Aplicador.RutaDeResultado)) return File.Exists(Aplicador.RutaDeOrden) ? 33 : 0;
        return LeerResultado() switch
        {
            "aplicado" or "revertido" => 0,
            "aplazada" => 30,
            "rechazada" => 31,
            _ => 32,
        };
    }

    private static string? LeerResultado()
    {
        try
        {
            using var d = JsonDocument.Parse(File.ReadAllText(Aplicador.RutaDeResultado));
            return d.RootElement.TryGetProperty("resultado", out var v) ? v.GetString() : null;
        }
        catch (Exception error) when (error is IOException or JsonException or UnauthorizedAccessException) { return null; }
    }

    private static string? IdDe(string archivo)
    {
        try
        {
            using var d = JsonDocument.Parse(File.ReadAllText(archivo));
            return d.RootElement.TryGetProperty("orden_id", out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
        }
        catch (JsonException) { return null; }
    }
}

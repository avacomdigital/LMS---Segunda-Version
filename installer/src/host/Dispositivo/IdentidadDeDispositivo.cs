namespace Avacom.Ops.Host.Dispositivo;

/// <summary>
/// La implementacion del contrato de identidad: NO decide nada por su cuenta. Es la misma puerta (<see cref="PuertaDeDispositivo.Verificar"/>) que usan el instalador, el servicio y la liberacion de la
/// llave del paquete, vista con los nombres del contrato (Autorizado, VariableNoEncontrada, …). Los tres pasos, en este orden, estan alli: la identidad que el firmware declara, el sello de AVACOM con la
/// prueba de posesion de la clave del TPM, y que el sello autorice ese identificador.
/// </summary>
internal sealed class IdentidadDeDispositivo(IClavesDeEquipo claves, IReadOnlyDictionary<string, byte[]> llaves, string carpetaSello, ILectorUefi lector, Func<long> ahoraMs) : IIdentidadDeDispositivoAvacom
{
    public ResultadoDeIdentidad Validar()
    {
        var r = PuertaDeDispositivo.Verificar(claves, llaves, carpetaSello, ahoraMs(), lector);
        return new ResultadoDeIdentidad(r.Identidad, r.CodigoDeDiagnostico, r.Motivo.Length > 0 ? $"{r.Estado}/{r.Motivo}" : r.Estado);
    }
}

/// <summary>
/// La puerta del SERVICIO: antes de levantar el backend, el nodo comprueba que es un dispositivo AVACOM autorizado. El servicio corre como SYSTEM, que puede leer el firmware; el lanzador y la
/// aplicacion (usuario estandar) no. Si la comprobacion no pasa, el backend NO arranca (sin backend la aplicacion no tiene datos ni lecciones), y se anota por que.
///
/// Solo existe en una compilacion con llaves de sello (la misma condicion que la puerta del instalador). Un desarrollo sin llaves no tiene puerta.
/// </summary>
[System.Runtime.Versioning.SupportedOSPlatform("windows")]
internal static class PuertaDelServicio
{
    private static string? _ultimo;

    public static bool Permite(Registro registro) =>
        Permite(registro, PuertaDeDispositivo.LlavesIncrustadas(), Verbos.ClavesDeEsteEquipo(), PuertaDeDispositivo.CarpetaDeSelloDelNodo, PuertaDeDispositivo.RutaDeSenal, Verbos.LectorUefiDeEsteEquipo());

    internal static bool Permite(Registro registro, IReadOnlyDictionary<string, byte[]> llaves, IClavesDeEquipo claves, string carpetaSello, string rutaSenal, ILectorUefi lector)
    {
        if (llaves.Count == 0) return true;
        var r = Verbos.Resolver(claves, llaves, carpetaSello, rutaSenal, lector);
        var autorizado = r.Identidad == EstadoDeIdentidad.Autorizado;
        var linea = $"{r.Estado}/{r.Motivo}";
        if (linea != _ultimo)            // solo cuando cambia: el servicio reintenta cada minuto y no debe llenar el registro
        {
            _ultimo = linea;
            registro.Escribir(autorizado
                ? $"Dispositivo AVACOM autorizado ({r.Estado})."
                : $"Dispositivo NO autorizado: {r.Estado} ({r.Motivo}), codigo {r.CodigoDeDiagnostico}. El backend no arranca; se vuelve a comprobar en cada reintento.");
        }
        return autorizado;
    }

    internal static void OlvidarElUltimo() => _ultimo = null;
}

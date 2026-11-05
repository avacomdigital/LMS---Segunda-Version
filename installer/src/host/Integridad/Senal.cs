using System.Text.Json;
using Avacom.Ops.Host.Actualizacion;

namespace Avacom.Ops.Host.Integridad;

/// <summary>
/// La SEÑAL de integridad: el archivo que el Host deja en %ProgramData%\AVACOM\OPS Master\Config\integridad.json y que el backend (licenciamiento/infraestructura/integridad.py) lee para
/// avisar al administrador y asentar `licencia.integridad_alterada` en la bitacora. Contrato (version 1, sin datos de personas ni de licencias; las rutas son de CODIGO del producto):
///
///   { "version": 1, "verificado": "2026-10-22T17:00:00Z", "estado": "ok|alterada|sin_firma|no_verificable",
///     "firma": "ok|ausente|ilegible|kid_desconocido|invalida|sin_llave", "kid": "upd-2026-1"|null, "version_producto": "2.16.0",
///     "archivos_comprobados": 5871,
///     "hallazgos": [ { "tipo": "backend|runtime|app|nativo|manifiesto|firma|otro", "detalle": "modificado|falta|sobra|...", "cantidad": 2, "ejemplos": ["Backend/x.py"] } ] }
///
/// Se reescribe en CADA arranque del servicio (y despues de una actualizacion): una alteracion que se corrige deja de avisarse al siguiente arranque. Nunca impide arrancar.
/// </summary>
internal static class Senal
{
    public const string Archivo = "integridad.json";

    /// <summary>
    /// Donde el backend la busca: %ProgramData%\AVACOM\OPS Master\Config\integridad.json. En un nodo real es la misma carpeta de estado del Host; en un ENSAYO del instalador el backend usa la variable
    /// ProgramData que el ensayo mueve (como Actualizaciones\), y el Host la imita.
    /// </summary>
    public static string Ruta =>
        Rutas.EsEnsayo && Environment.GetEnvironmentVariable("ProgramData") is { Length: > 0 } programData
            ? Path.Combine(programData, "AVACOM", "OPS Master", "Config", Archivo)
            : Path.Combine(Rutas.CarpetaConfig, Archivo);

    public static string Serializar(ResultadoDeIntegridad r, DateTime ahoraUtc) => JsonSerializer.Serialize(new
    {
        version = 1,
        verificado = ahoraUtc.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'"),
        estado = r.Estado,
        firma = r.Firma,
        kid = r.Kid,
        version_producto = r.VersionDelProducto,
        archivos_comprobados = r.ArchivosComprobados,
        hallazgos = r.Hallazgos.Select(h => new { tipo = h.Tipo, detalle = h.Detalle, cantidad = h.Cantidad, ejemplos = h.Ejemplos }),
    });

    /// <summary>Verifica, deja el asiento en servicio.log y escribe la señal. NUNCA lanza: lo que falle aqui no puede tumbar el servicio.</summary>
    public static ResultadoDeIntegridad? Comprobar(Registro registro, string? rutaDeLaSenal = null)
    {
        try
        {
            var inicio = DateTime.UtcNow;
            var resultado = Verificador.Verificar();
            registro.Escribir($"Integridad del despliegue: {resultado.Estado} (firma {resultado.Firma}{(resultado.Kid is null ? "" : ", llave " + resultado.Kid)}; " +
                              $"{resultado.ArchivosComprobados} archivos en {(DateTime.UtcNow - inicio).TotalMilliseconds:0} ms).");
            foreach (var h in resultado.Hallazgos)
                registro.Escribir($"  INTEGRIDAD ALTERADA · {h.Tipo} · {h.Detalle} · {h.Cantidad}: {string.Join(", ", h.Ejemplos)}");
            if (resultado.Estado == "alterada")
                registro.Escribir("  El nodo arranca igual: una diferencia es evidencia para el administrador, no un motivo para dejar el aula sin clase.");
            Disco.EscribirAtomico(rutaDeLaSenal ?? Ruta, Serializar(resultado, DateTime.UtcNow));
            return resultado;
        }
        catch (Exception error)
        {
            try { registro.Escribir("La verificacion de integridad del despliegue fallo; el servicio sigue", error); } catch (Exception) { /* nada mas que hacer */ }
            return null;
        }
    }
}

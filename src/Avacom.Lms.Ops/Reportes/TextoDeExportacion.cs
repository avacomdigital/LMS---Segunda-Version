using Avacom.Lms.Core.Reporting;

namespace Avacom.Lms.Ops.Reportes;

/// <summary>Lo que dice la hoja de confirmación antes de escribir: la frase del alcance con el destino, y las advertencias. Tal como las leerá el profesor, sin jerga.</summary>
public sealed record TextoDeConfirmacion(string Frase, string Advertencia, string? Privacidad, bool Nominal);

/// <summary>
/// Las frases de la exportación a archivo (FUN-146) que dependen del destino: cómo se nombra un lugar, qué se confirma y cómo se dice que quedó guardado. Puro, sin MAUI.
/// Nada de aquí lleva datos de personas: el alcance lo redacta el nodo (con el grupo y los conteos) y aquí sólo se le añade el lugar.
/// </summary>
public static class TextoDeExportacion
{
    /// <summary>La ficha de un formato: el nombre grande y qué trae, en una línea.</summary>
    public static (string Titulo, string Descripcion) Formato(string formato) => formato == FormatosDeExportacion.Csv
        ? ("CSV (.csv)", "Texto plano con acentos; abre bien en Excel en español.")
        : ("Excel (.xlsx)", "Una hoja de resumen y una de detalle.");

    /// <summary>
    /// Cómo se nombra el destino en la confirmación: «E: · MEMORIA (14 GB libres)» para una unidad con etiqueta; «Memoria USB (F:) (14 GB libres)» cuando el nombre ya trae la letra
    /// (una unidad sin etiqueta); «Documentos» para un atajo; la carpeta tal cual para una que se eligió a mano.
    /// </summary>
    public static string DescribirDestino(DestinoDeExportacion destino)
    {
        if (destino.EsAtajo) return destino.Nombre;
        if (destino.Letra is null) return string.IsNullOrWhiteSpace(destino.Ruta) ? destino.Nombre : destino.Ruta;       // una carpeta elegida a mano, o una raíz de red sin letra
        var libre = destino.LibreBytes is { } l ? $" ({FormatoDeReportes.Tamano(l)} libres)" : string.Empty;
        var traeLaLetra = destino.Nombre.Contains(destino.Letra, StringComparison.OrdinalIgnoreCase);
        return (traeLaLetra ? destino.Nombre : $"{destino.Letra} · {destino.Nombre}") + libre;
    }

    /// <summary>La clase de lugar, para el rótulo de la fila: «Extraíble», «Red» o nada (un disco o carpeta del equipo no necesita marca).</summary>
    public static string? Marca(TipoDeDestino tipo) => tipo switch { TipoDeDestino.Extraible => "Extraíble", TipoDeDestino.Red => "Red", _ => null };

    /// <summary>
    /// La confirmación con el alcance declarado: «Vas a guardar el reporte del grupo 8A (7 alumnos, …, datos al 15 oct · 10:42) en E: · MEMORIA (14 GB libres).», seguida de la
    /// advertencia (con nombres de alumnos, o «Sin datos de personas.»). Si el umbral de privacidad recortó el reporte, también lo dice.
    /// </summary>
    public static TextoDeConfirmacion Confirmacion(AlcanceDeExportacion alcance, DestinoDeExportacion destino)
    {
        var alcanceTexto = alcance.TextoAlcance.TrimEnd();
        var frase = $"{alcanceTexto} en {DescribirDestino(destino)}.";
        var privacidad = alcance.UmbralAplicado || alcance.Privacidad.Aplicada ? alcance.Privacidad.Aviso : null;
        return new TextoDeConfirmacion(frase, alcance.Advertencia, string.IsNullOrWhiteSpace(privacidad) ? null : privacidad, alcance.Nominal);
    }

    /// <summary>
    /// «Guardado en E:\Reportes\reporte-grupo-8A-….xlsx» con el tamaño. El recordatorio de esperar sólo se da en una memoria extraíble: ya se vació a disco y se releyó, pero no se
    /// promete una expulsión segura que no se implementó.
    /// </summary>
    public static (string Titulo, string Detalle, string? Recordatorio) Exito(string rutaFinal, long bytes, TipoDeDestino tipo) =>
        ($"Guardado en {rutaFinal}", $"Tamaño: {FormatoDeReportes.Tamano(bytes)}. El archivo se comprobó releyéndolo del destino.",
         tipo == TipoDeDestino.Extraible ? "Espera un momento antes de retirar la memoria." : null);

    /// <summary>El título de la hoja según el paso.</summary>
    public static string TituloDe(AlcanceDeExportacion? alcance) => alcance is null ? "Guardar el reporte en un archivo" : $"Guardar «{alcance.Titulo}» en un archivo";

    /// <summary>
    /// Qué botones ofrece la hoja tras un fallo. <see cref="GuardarOtraVez"/> repite sobre el MISMO destino (sin generar de nuevo el archivo ya bajado); <see cref="ElegirOtroDestino"/>
    /// vuelve al paso de elegir, y <see cref="ReleerLaPolitica"/> dice que la elección vieja ya no vale (el aula cambió la política del administrador) y hay que volver a leerla.
    /// Sin ninguno de los dos, sólo se puede cerrar.
    /// </summary>
    public readonly record struct BotonesDelFallo(bool GuardarOtraVez, bool ElegirOtroDestino, bool ReleerLaPolitica);

    /// <summary>
    /// Las frases de los fallos dicen «toca Guardar otra vez, o elige otro destino»: la pantalla ofrece EXACTAMENTE esos botones. Se repite lo que se arregla afuera (se vuelve a conectar la
    /// memoria, se libera espacio, vuelve la red, se quita el seguro; una conexión caída o un archivo dañado). Cambiar de carpeta no arregla un permiso del reporte mismo
    /// (<c>sin_permiso</c>, <c>fuera_de_alcance</c>): ahí sólo se cierra. Un destino o una razón que el aula rechaza (<c>destino_no_permitido</c>, <c>razon_requerida</c>) se resuelven eligiendo de nuevo.
    /// </summary>
    public static BotonesDelFallo BotonesPara(ResultadoDelGuardado r)
    {
        var codigoDelNodo = r.ErrorDelNodo?.Codigo;
        switch (r.Estado)
        {
            case EstadoDelGuardado.SinConexion or EstadoDelGuardado.ArchivoDanado:
                return new BotonesDelFallo(GuardarOtraVez: true, ElegirOtroDestino: false, ReleerLaPolitica: false);
            case EstadoDelGuardado.NoSePudoEscribir:
                var arreglable = r.Fallo?.Motivo is MotivoDeEscritura.MedioRetirado or MotivoDeEscritura.SinEspacio or MotivoDeEscritura.ProtegidoContraEscritura
                    or MotivoDeEscritura.RutaDeRedInalcanzable or MotivoDeEscritura.ArchivoEnUso or MotivoDeEscritura.VerificacionFallida or MotivoDeEscritura.BloqueadoPorAntivirus;
                return new BotonesDelFallo(GuardarOtraVez: arreglable, ElegirOtroDestino: true, ReleerLaPolitica: false);
            case EstadoDelGuardado.NoAutorizado:
                return codigoDelNodo switch
                {
                    "destino_no_permitido" or "razon_requerida" => new BotonesDelFallo(GuardarOtraVez: false, ElegirOtroDestino: true, ReleerLaPolitica: true),
                    "sin_permiso" or "fuera_de_alcance" => new BotonesDelFallo(false, false, false),
                    _ => new BotonesDelFallo(GuardarOtraVez: true, ElegirOtroDestino: false, ReleerLaPolitica: false),
                };
            default:
                return new BotonesDelFallo(false, false, false);
        }
    }
}

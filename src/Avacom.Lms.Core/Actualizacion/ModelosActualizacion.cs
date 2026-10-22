using System.Text.Json;
using System.Text.Json.Serialization;

namespace Avacom.Lms.Core.Actualizacion;

// Contratos de /api/actualizacion/ (MOD-017 · Update Manager) tal como los entrega el nodo (backend/actualizacion/interfaces/views.py; respuestas reales en Fixtures/actualizacion/).
// Los nombres JSON son los del backend (snake_case). El cliente NO decide nada de la actualización (BR-013, SEC-001): firma, compatibilidad, serie, clases abiertas y plazo los
// calcula el nodo; aquí sólo se lee lo que respondió para pintarlo. Las horas son instantes del nodo en milisegundos. Un valor que llega null significa «no aplica», nunca cero.
// Ninguna respuesta trae una ruta de archivo (P-11): los paquetes de una memoria se nombran por un id opaco.

// ------------------------------------------------------------------------------------------------ catálogos (los códigos del contrato; el texto lo pone ActualizacionTexto)

/// <summary>Los estados de un paquete (P-05): los seis del Maestro y tres internos del nodo. El estado se DERIVA del historial de sólo inserción; el cliente sólo lo nombra.</summary>
public static class EstadosDePaquete
{
    public const string Recibido = "recibido";
    public const string Verificado = "verificado";
    public const string Incompatible = "incompatible";
    public const string Programado = "programado";
    public const string Aplicando = "aplicando";
    public const string Aplicado = "aplicado";
    public const string Revertido = "revertido";
    public const string ReversionFallida = "reversion_fallida";
    public const string Archivado = "archivado";

    public static readonly IReadOnlyList<string> Todos = [Recibido, Verificado, Incompatible, Programado, Aplicando, Aplicado, Revertido, ReversionFallida, Archivado];
}

/// <summary>El estado del nodo frente a las actualizaciones (<c>estado</c> de <c>estado/</c>).</summary>
public static class EstadosDelNodoActualizado
{
    public const string AlDia = "al_dia";
    public const string Programado = "programado";
    public const string Aplicando = "aplicando";

    public static readonly IReadOnlyList<string> Todos = [AlDia, Programado, Aplicando];
}

/// <summary>Qué hace una orden al <c>Host</c>.</summary>
public static class AccionesDeOrden
{
    public const string Aplicar = "aplicar";
    public const string Revertir = "revertir";
}

/// <summary>Los <c>codigo</c> de error de <c>/api/actualizacion/</c> y el 503 del inicio de clases.</summary>
public static class CodigosDeActualizacion
{
    public const string DatosInvalidos = "datos_invalidos";
    public const string SinPermiso = "sin_permiso";
    public const string NoEncontrado = "no_encontrado";
    public const string SesionActiva = "sesion_activa";
    public const string ContratoIncompatible = "contrato_incompatible";
    public const string EspacioInsuficiente = "espacio_insuficiente";
    public const string YaAplicado = "ya_aplicado";
    public const string SerieMenor = "serie_menor";
    public const string FueraDePlazoReversion = "fuera_de_plazo_reversion";
    public const string EstadoInvalido = "estado_invalido";
    public const string EnCurso = "actualizacion_en_curso";
    public const string PaqueteRepetido = "paquete_repetido";
    public const string FirmaInvalida = "firma_invalida";
    public const string PaqueteInvalido = "paquete_invalido";
}

/// <summary>Los permisos del módulo (P-10). Los resuelve el nodo; el cliente sólo los nombra para no ofrecer lo que el nodo va a denegar.</summary>
public static class PermisosDeActualizacion
{
    public const string Leer = "update.read";
    public const string Importar = "update.package.import";
    public const string Programar = "update.schedule";
    public const string Aplicar = "update.apply";
}

/// <summary>Los <c>tipo</c> de una fila del historial (FUN-187). Un tipo que esta versión no conoce se muestra con una frase general, no se calla.</summary>
public static class TiposDeHistorial
{
    public const string Recibido = "recibido";
    public const string Verificado = "verificado";
    public const string Incompatible = "incompatible";
    public const string Rechazado = "rechazado";
    public const string Programado = "programado";
    public const string Desprogramado = "desprogramado";
    public const string VentanaVencida = "ventana_vencida";
    public const string Bloqueada = "bloqueada";
    public const string Aplicando = "aplicando";
    public const string Aplicado = "aplicado";
    public const string Revertido = "revertido";
    public const string ReversionFallida = "reversion_fallida";
    public const string Aplazada = "aplazada";
    public const string Archivado = "archivado";

    public static readonly IReadOnlyList<string> Todos =
        [Recibido, Verificado, Incompatible, Rechazado, Programado, Desprogramado, VentanaVencida, Bloqueada, Aplicando, Aplicado, Revertido, ReversionFallida, Aplazada, Archivado];
}

// ------------------------------------------------------------------------------------------------ estado/

/// <summary>Una clase de actualización que el nodo ya aceptó y que el <c>Host</c> todavía no terminó (<c>en_curso</c>). Mientras dura, el inicio de clases responde 503.</summary>
public sealed record ActualizacionEnCurso(
    [property: JsonPropertyName("paquete_id")] string PaqueteId,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("accion")] string Accion,
    [property: JsonPropertyName("orden_id")] string? OrdenId,
    [property: JsonPropertyName("desde")] long? Desde);

/// <summary>La ventana de una actualización programada, en ms del reloj del nodo.</summary>
public sealed record VentanaDeActualizacion(
    [property: JsonPropertyName("desde")] long Desde,
    [property: JsonPropertyName("hasta")] long Hasta);

public sealed record ProgramadoResumen(
    [property: JsonPropertyName("paquete_id")] string PaqueteId,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("ventana")] VentanaDeActualizacion? Ventana);

/// <summary>Lo ya aplicado que todavía se puede revertir (14 días, INV-008).</summary>
public sealed record RevertibleResumen(
    [property: JsonPropertyName("paquete_id")] string PaqueteId,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("aplicado_en")] long AplicadoEn,
    [property: JsonPropertyName("revertible_hasta")] long RevertibleHasta);

/// <summary>Un módulo del nodo con su versión, de datos y de contrato (BR-012), y si se puede actualizar por separado.</summary>
public sealed record ModuloInstalado(
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("modulo")] string? Modulo,
    [property: JsonPropertyName("version")] string Version,
    [property: JsonPropertyName("version_datos")] int VersionDatos,
    [property: JsonPropertyName("version_contrato")] int VersionContrato,
    [property: JsonPropertyName("serie")] int Serie,
    [property: JsonPropertyName("actualizable")] bool Actualizable,
    [property: JsonPropertyName("produce")] IReadOnlyList<string>? Produce = null,
    [property: JsonPropertyName("consume")] IReadOnlyDictionary<string, int[]>? Consume = null);

/// <summary><c>GET estado/</c>: lo que el nodo sabe de sus actualizaciones.</summary>
public sealed record EstadoDeActualizacion(
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("en_curso")] ActualizacionEnCurso? EnCurso,
    [property: JsonPropertyName("programados")] IReadOnlyList<ProgramadoResumen>? Programados,
    [property: JsonPropertyName("revertibles")] IReadOnlyList<RevertibleResumen>? Revertibles,
    [property: JsonPropertyName("paquetes")] IReadOnlyDictionary<string, int>? Paquetes,
    [property: JsonPropertyName("orden_pendiente")] bool OrdenPendiente,
    [property: JsonPropertyName("canal")] string? Canal,
    [property: JsonPropertyName("version")] string? Version,
    [property: JsonPropertyName("contrato_biblioteca")] int? ContratoBiblioteca,
    [property: JsonPropertyName("modulos")] IReadOnlyList<ModuloInstalado>? Modulos,
    [property: JsonPropertyName("espacio_libre")] long? EspacioLibre,
    [property: JsonPropertyName("dias_reversion")] int DiasReversion,
    [property: JsonPropertyName("servidor_en")] long ServidorEn)
{
    public IReadOnlyList<ProgramadoResumen> ProgramadosOVacio => Programados ?? [];
    public IReadOnlyList<RevertibleResumen> RevertiblesOVacio => Revertibles ?? [];
    public IReadOnlyList<ModuloInstalado> ModulosOVacio => Modulos ?? [];
    public bool Aplicando => Estado == EstadosDelNodoActualizado.Aplicando || EnCurso is not null || OrdenPendiente;
}

// ------------------------------------------------------------------------------------------------ paquetes/

/// <summary>Un <c>.avupd</c> encontrado en una memoria extraíble o en la carpeta de entrada. El id es opaco: la API nunca recibe ni devuelve una ruta (P-11).</summary>
public sealed record CandidatoDePaquete(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("origen")] string? Origen,
    [property: JsonPropertyName("bytes")] long Bytes,
    [property: JsonPropertyName("modificado_en")] long? ModificadoEn,
    [property: JsonPropertyName("fuente")] string? Fuente,
    [property: JsonPropertyName("importado")] string? Importado)
{
    /// <summary>Ya entró al nodo (su <c>paquete_id</c>): no se ofrece importarlo otra vez.</summary>
    public bool YaImportado => !string.IsNullOrEmpty(Importado);
}

public sealed record Incompatibilidad(
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("modulo")] string? Modulo,
    [property: JsonPropertyName("detalle")] string? Detalle);

public sealed record ModuloDelPaquete(
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("version")] string Version,
    [property: JsonPropertyName("version_datos")] int VersionDatos,
    [property: JsonPropertyName("version_contrato")] int VersionContrato,
    [property: JsonPropertyName("serie")] int Serie,
    [property: JsonPropertyName("cambia_contrato")] bool CambiaContrato,
    [property: JsonPropertyName("requiere")] IReadOnlyDictionary<string, int>? Requiere = null,
    [property: JsonPropertyName("migraciones")] IReadOnlyList<string>? Migraciones = null);

public sealed record RequisitosDelPaquete(
    [property: JsonPropertyName("contrato_biblioteca")] int? ContratoBiblioteca,
    [property: JsonPropertyName("cliente_minimo")] string? ClienteMinimo,
    [property: JsonPropertyName("contrato_red")] int? ContratoRed,
    [property: JsonPropertyName("espacio_bytes")] long? EspacioBytes);

/// <summary>El resumen del manifiesto firmado (sin la lista de archivos ni sus rutas): qué cambia, cuánto pesa y qué exige.</summary>
public sealed record ManifiestoResumen(
    [property: JsonPropertyName("paquete_id")] string? PaqueteId,
    [property: JsonPropertyName("nombre")] string? Nombre,
    [property: JsonPropertyName("version_producto")] string? VersionProducto,
    [property: JsonPropertyName("version_minima")] string? VersionMinima,
    [property: JsonPropertyName("serie")] int Serie,
    [property: JsonPropertyName("archivos")] int Archivos,
    [property: JsonPropertyName("bytes")] long Bytes,
    [property: JsonPropertyName("emitido_en")] long? EmitidoEn,
    [property: JsonPropertyName("nota")] string? Nota,
    [property: JsonPropertyName("modulos")] IReadOnlyList<ModuloDelPaquete>? Modulos,
    [property: JsonPropertyName("requisitos")] RequisitosDelPaquete? Requisitos);

/// <summary>Una fila del historial (de sólo inserción). <c>Detalle</c> es lo que el nodo anotó: ids, versiones, resultado, hashes; nunca rutas ni personas.</summary>
public sealed record HechoDeHistorial(
    [property: JsonPropertyName("id")] long Id,
    [property: JsonPropertyName("paquete_id")] string? PaqueteId,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("en")] long En,
    [property: JsonPropertyName("actor")] string? Actor,
    [property: JsonPropertyName("serie")] int? Serie,
    [property: JsonPropertyName("version_producto")] string? VersionProducto,
    [property: JsonPropertyName("detalle")] JsonElement? Detalle)
{
    public string? Texto(string clave) =>
        Detalle is { ValueKind: JsonValueKind.Object } d && d.TryGetProperty(clave, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;

    public long? Numero(string clave) =>
        Detalle is { ValueKind: JsonValueKind.Object } d && d.TryGetProperty(clave, out var v) && v.ValueKind == JsonValueKind.Number && v.TryGetInt64(out var n) ? n : null;
}

/// <summary>La orden que el nodo dejó al <c>Host</c> al aceptar aplicar o revertir (202).</summary>
public sealed record OrdenEmitida(
    [property: JsonPropertyName("orden_id")] string OrdenId,
    [property: JsonPropertyName("accion")] string Accion,
    [property: JsonPropertyName("limite_minutos")] int LimiteMinutos,
    [property: JsonPropertyName("pasos")] IReadOnlyList<string>? Pasos,
    [property: JsonPropertyName("emitida_en")] long EmitidaEn);

/// <summary>La ficha de un paquete (<c>paquetes/{id}/</c> y lo que devuelven importar, programar, aplicar y revertir). En la lista <c>paquetes/</c> viene sin <c>historial</c>.</summary>
public sealed record FichaDePaquete(
    [property: JsonPropertyName("paquete_id")] string PaqueteId,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("version_producto")] string? VersionProducto,
    [property: JsonPropertyName("serie")] int Serie,
    [property: JsonPropertyName("modulos")] IReadOnlyList<string>? Modulos,
    [property: JsonPropertyName("kid")] string? Kid,
    [property: JsonPropertyName("sha256")] string? Sha256,
    [property: JsonPropertyName("bytes")] long Bytes,
    [property: JsonPropertyName("archivo")] string? Archivo,
    [property: JsonPropertyName("origen")] string? Origen,
    [property: JsonPropertyName("recibido_en")] long RecibidoEn,
    [property: JsonPropertyName("manifiesto")] ManifiestoResumen? Manifiesto,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("en_curso")] bool EnCurso,
    [property: JsonPropertyName("accion")] string? Accion,
    [property: JsonPropertyName("orden_id")] string? OrdenId,
    [property: JsonPropertyName("ventana")] VentanaDeActualizacion? Ventana,
    [property: JsonPropertyName("aplicado_en")] long? AplicadoEn,
    [property: JsonPropertyName("revertible_hasta")] long? RevertibleHasta,
    [property: JsonPropertyName("revertible")] bool Revertible,
    [property: JsonPropertyName("incompatibilidades")] IReadOnlyList<Incompatibilidad>? Incompatibilidades,
    [property: JsonPropertyName("ultima_en")] long? UltimaEn,
    [property: JsonPropertyName("historial")] IReadOnlyList<HechoDeHistorial>? Historial = null,
    [property: JsonPropertyName("orden")] OrdenEmitida? Orden = null)
{
    public IReadOnlyList<Incompatibilidad> IncompatibilidadesOVacio => Incompatibilidades ?? [];
    public IReadOnlyList<HechoDeHistorial> HistorialOVacio => Historial ?? [];
    public IReadOnlyList<ModuloDelPaquete> ModulosDelManifiesto => Manifiesto?.Modulos ?? [];
}

/// <summary><c>GET paquetes/</c>: los candidatos en las memorias y la carpeta de entrada, y las fichas de lo ya importado.</summary>
public sealed record ListaDePaquetes(
    [property: JsonPropertyName("candidatos")] IReadOnlyList<CandidatoDePaquete>? Candidatos,
    [property: JsonPropertyName("paquetes")] IReadOnlyList<FichaDePaquete>? Paquetes,
    [property: JsonPropertyName("servidor_en")] long ServidorEn)
{
    public IReadOnlyList<CandidatoDePaquete> CandidatosOVacio => Candidatos ?? [];
    public IReadOnlyList<FichaDePaquete> PaquetesOVacio => Paquetes ?? [];
}

/// <summary><c>GET historial/</c>: lo último primero.</summary>
public sealed record HistorialDeActualizacion(
    [property: JsonPropertyName("historial")] IReadOnlyList<HechoDeHistorial>? Historial,
    [property: JsonPropertyName("servidor_en")] long ServidorEn)
{
    public IReadOnlyList<HechoDeHistorial> HechosOVacio => Historial ?? [];
}

/// <summary>El campo aditivo <c>actualizacion</c> de <c>GET /health/</c> (público).</summary>
public sealed record SaludDeActualizacion(
    [property: JsonPropertyName("estado")] string? Estado,
    [property: JsonPropertyName("en_curso")] ActualizacionEnCurso? EnCurso,
    [property: JsonPropertyName("programados")] int Programados,
    [property: JsonPropertyName("orden_pendiente")] bool OrdenPendiente);

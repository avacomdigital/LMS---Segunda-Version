using System.Text.Json.Serialization;

namespace Avacom.Lms.Core.Nodo;

// Contratos de /api/nodo/ (MOD-015 · Node Platform y Cola de Salida) tal como los entrega el nodo (backend/nodo/interfaces/views.py y aplicacion/{estado,consumidores}.py). Los nombres
// JSON son los del backend (snake_case). El cliente NO decide nada del nodo: lo que llega es lo que el nodo evaluó y aquí sólo se lee para pintarlo. Las horas son instantes del nodo en
// milisegundos. NINGUNA respuesta trae la carga de un evento (R-13): el técnico ve metadatos.

// ------------------------------------------------------------------------------------------------ catálogos (los códigos del contrato; el texto lo pone NodoTexto)

/// <summary>Los estados del nodo (H del Maestro).</summary>
public static class EstadosDelNodo
{
    public const string Arrancando = "arrancando";
    public const string Operativo = "operativo";
    public const string Restringido = "restringido";
    public const string EnRecuperacion = "en_recuperacion";
    public const string Detenido = "detenido";

    public static readonly IReadOnlyList<string> Todos = [Arrancando, Operativo, Restringido, EnRecuperacion, Detenido];
}

/// <summary>Por qué el nodo está restringido (Q-N1): códigos de <c>motivos[]</c>.</summary>
public static class MotivosDeRestriccion
{
    public const string TransaccionNoInmediata = "transaccion_no_inmediata";
    public const string DiscoEscaso = "disco_escaso";
    public const string BaseDanada = "base_danada";
    public const string WalEnorme = "wal_enorme";
    public const string ConsumidorNucleoSuspendido = "consumidor_nucleo_suspendido";
    public const string RelojRetrocedido = "reloj_retrocedido";

    public static readonly IReadOnlyList<string> Todos = [TransaccionNoInmediata, DiscoEscaso, BaseDanada, WalEnorme, ConsumidorNucleoSuspendido, RelojRetrocedido];
}

/// <summary>El estado de un consumidor (P-06).</summary>
public static class EstadosDeConsumidor
{
    public const string AlDia = "al_dia";
    public const string Rezagado = "rezagado";
    public const string Reconstruyendose = "reconstruyendose";
    public const string Suspendido = "suspendido";

    public static readonly IReadOnlyList<string> Todos = [AlDia, Rezagado, Reconstruyendose, Suspendido];
}

/// <summary>El estado de un evento apartado (P-07).</summary>
public static class EstadosDeProblema
{
    public const string Apartado = "apartado";
    public const string Reprocesado = "reprocesado";
    public const string Descartado = "descartado";

    public static readonly IReadOnlyList<string> Todos = [Apartado, Reprocesado, Descartado];
}

/// <summary>Los <c>codigo</c> de error que esta API responde.</summary>
public static class ErroresDelNodo
{
    public const string SinPermiso = "sin_permiso";
    public const string NoEncontrado = "no_encontrado";
    public const string ConsumidorDesconocido = "consumidor_desconocido";
    public const string ConsumidorSinAplicador = "consumidor_sin_aplicador";
    public const string ProblemaYaResuelto = "problema_ya_resuelto";
    public const string ReprocesoFallido = "reproceso_fallido";
    public const string DatosInvalidos = "datos_invalidos";
    public const string NodoRestringido = "nodo_restringido";
    public const string SesionRequerida = "sesion_requerida";
}

/// <summary>Los permisos que la API exige (sección J y P-17).</summary>
public static class PermisosDelNodo
{
    public const string Reprocesar = "node.queue.replay";
    public const string LeerCola = "node.queue.read";
    public const string LeerSalud = "node.health.read";
}

// ------------------------------------------------------------------------------------------------ GET estado/

/// <summary>El estado del nodo evaluado ahora (FUN-167, PAN-242).</summary>
public sealed record EstadoDelNodo(
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("motivos")] IReadOnlyList<string> Motivos,
    [property: JsonPropertyName("restringido")] bool Restringido,
    [property: JsonPropertyName("version")] string? Version,
    [property: JsonPropertyName("arranque")] ArranqueDelNodo? Arranque,
    [property: JsonPropertyName("base")] BaseDelNodo? Base,
    [property: JsonPropertyName("disco")] DiscoDelNodo? Disco,
    [property: JsonPropertyName("reloj")] RelojDelNodo? Reloj,
    [property: JsonPropertyName("cola")] ColaResumida? Cola,
    [property: JsonPropertyName("purga")] PurgaDelNodo? Purga,
    [property: JsonPropertyName("servidor_en")] long ServidorEn)
{
    public bool Operativo => Estado == EstadosDelNodo.Operativo;
    public bool EnRecuperacion => Estado == EstadosDelNodo.EnRecuperacion;
}

public sealed record ArranqueDelNodo(
    [property: JsonPropertyName("id")] long? Id,
    [property: JsonPropertyName("apagado_sucio_previo")] bool ApagadoSucioPrevio,
    [property: JsonPropertyName("restauracion")] RestauracionDetectada? Restauracion);

/// <summary>Lo que las anclas detectaron al arrancar (P-12): la base traía menos que lo emitido y el contador saltó.</summary>
public sealed record RestauracionDetectada(
    [property: JsonPropertyName("max_en_base")] long MaxEnBase,
    [property: JsonPropertyName("ancla")] long Ancla,
    [property: JsonPropertyName("sin_ancla")] bool SinAncla,
    [property: JsonPropertyName("contador")] long Contador,
    [property: JsonPropertyName("detectada_en")] long DetectadaEn);

public sealed record BaseDelNodo(
    [property: JsonPropertyName("transaccion_inmediata")] bool TransaccionInmediata,
    [property: JsonPropertyName("integra")] bool Integra,
    [property: JsonPropertyName("wal_bytes")] long WalBytes);

/// <summary>El disco donde vive la base. Un <c>null</c> es «no medido», nunca un cero.</summary>
public sealed record DiscoDelNodo(
    [property: JsonPropertyName("libre_bytes")] long? LibreBytes,
    [property: JsonPropertyName("total_bytes")] long? TotalBytes);

public sealed record RelojDelNodo(
    [property: JsonPropertyName("ahora")] long Ahora,
    [property: JsonPropertyName("marca_alta")] long MarcaAlta,
    [property: JsonPropertyName("retroceso_ms")] long RetrocesoMs);

public sealed record ColaResumida(
    [property: JsonPropertyName("eventos")] long Eventos,
    [property: JsonPropertyName("ultima_secuencia")] long UltimaSecuencia,
    [property: JsonPropertyName("contador")] long Contador,
    [property: JsonPropertyName("problemas")] int Problemas,
    [property: JsonPropertyName("consumidores")] IReadOnlyList<ConsumidorResumido> Consumidores);

public sealed record ConsumidorResumido(
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("pendientes")] long Pendientes,
    [property: JsonPropertyName("problemas")] int Problemas);

public sealed record PurgaDelNodo(
    [property: JsonPropertyName("habilitada")] bool Habilitada,
    [property: JsonPropertyName("respaldo_verificado_hasta")] long RespaldoVerificadoHasta);

// ------------------------------------------------------------------------------------------------ GET cola/

/// <summary>La cola por consumidor (CAP-097): cada fuente con su marca, lo último publicado, los pendientes y el estado. Sin carga útil.</summary>
public sealed record ColaDelNodo(
    [property: JsonPropertyName("consumidores")] IReadOnlyList<ConsumidorDeCola> Consumidores,
    [property: JsonPropertyName("eventos")] long Eventos,
    [property: JsonPropertyName("ultima_secuencia")] long UltimaSecuencia,
    [property: JsonPropertyName("contador")] long Contador,
    [property: JsonPropertyName("problemas")] int Problemas,
    [property: JsonPropertyName("cortes")] IReadOnlyList<CorteDeModulo> Cortes,
    [property: JsonPropertyName("purga")] PurgaDelNodo? Purga,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

public sealed record ConsumidorDeCola(
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("modulo")] string Modulo,
    [property: JsonPropertyName("version_contrato")] int VersionContrato,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("fuentes")] IReadOnlyList<FuenteDeConsumidor> Fuentes,
    [property: JsonPropertyName("pendientes")] long Pendientes,
    [property: JsonPropertyName("problemas")] int Problemas,
    [property: JsonPropertyName("registrado_en")] long RegistradoEn,
    [property: JsonPropertyName("actualizado_en")] long ActualizadoEn);

public sealed record FuenteDeConsumidor(
    [property: JsonPropertyName("fuente")] string Fuente,
    [property: JsonPropertyName("marca")] long Marca,
    [property: JsonPropertyName("ultima_secuencia")] long UltimaSecuencia,
    [property: JsonPropertyName("pendientes")] long Pendientes,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("actualizada_en")] long ActualizadaEn,
    [property: JsonPropertyName("reintento")] ReintentoDeFuente? Reintento);

/// <summary>El evento que retiene la marca y espera su siguiente intento (FUN-162).</summary>
public sealed record ReintentoDeFuente(
    [property: JsonPropertyName("secuencia")] long Secuencia,
    [property: JsonPropertyName("intentos")] int Intentos,
    [property: JsonPropertyName("proximo_en")] long ProximoEn,
    [property: JsonPropertyName("error")] string? Error);

public sealed record CorteDeModulo(
    [property: JsonPropertyName("modulo")] string Modulo,
    [property: JsonPropertyName("ultima_legada")] long UltimaLegada,
    [property: JsonPropertyName("cortado_en")] long CortadoEn);

// ------------------------------------------------------------------------------------------------ problemas/ y reprocesar/

public sealed record ProblemasDeCola(
    [property: JsonPropertyName("problemas")] IReadOnlyList<ProblemaDeCola> Problemas,
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

/// <summary>Un evento apartado (FUN-163): metadatos y el último error ya saneado; NUNCA la carga. <c>ServidorEn</c> sólo llega en la respuesta de reprocesar.</summary>
public sealed record ProblemaDeCola(
    [property: JsonPropertyName("id")] long Id,
    [property: JsonPropertyName("consumidor")] string Consumidor,
    [property: JsonPropertyName("fuente")] string Fuente,
    [property: JsonPropertyName("secuencia")] long Secuencia,
    [property: JsonPropertyName("evento_id")] string? EventoId,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("intentos")] int Intentos,
    [property: JsonPropertyName("intentos_reproceso")] int IntentosReproceso,
    [property: JsonPropertyName("ultimo_error")] string? UltimoError,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("apartado_en")] long ApartadoEn,
    [property: JsonPropertyName("resuelto_en")] long? ResueltoEn,
    [property: JsonPropertyName("resuelto_por")] string? ResueltoPor,
    [property: JsonPropertyName("servidor_en")] long? ServidorEn = null)
{
    public bool Apartado => Estado == EstadosDeProblema.Apartado;
}

// ------------------------------------------------------------------------------------------------ consumidores/<nombre>/reproducir/

public sealed record ReproduccionDeConsumidor(
    [property: JsonPropertyName("consumidor")] string Consumidor,
    [property: JsonPropertyName("fuente")] string? Fuente,
    [property: JsonPropertyName("marcas_reiniciadas")] int MarcasReiniciadas,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("servidor_en")] long ServidorEn);

// ------------------------------------------------------------------------------------------------ /health/ (campo aditivo `nodo`)

/// <summary>Lo que <c>/health/</c> dice del nodo sin tocar la base: para el banner del menú y para Student. Pública, sin permiso.</summary>
public sealed record NodoEnSalud(
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("motivos")] IReadOnlyList<string>? Motivos,
    [property: JsonPropertyName("restringido")] bool Restringido,
    [property: JsonPropertyName("apagado_sucio_previo")] bool ApagadoSucioPrevio,
    [property: JsonPropertyName("version")] string? Version)
{
    public bool EnRecuperacion => Estado == EstadosDelNodo.EnRecuperacion;
}

/// <summary>Sólo el campo <c>nodo</c> de <c>/health/</c>; lo demás se ignora.</summary>
public sealed record SaludConNodo([property: JsonPropertyName("nodo")] NodoEnSalud? Nodo);

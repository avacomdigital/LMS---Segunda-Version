using System.Text.Json;
using System.Text.Json.Serialization;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Evaluacion;

// Contratos de /api/evaluacion/ (MOD-010 · Evaluation & Delivery Engine), tal como los define
// spec-driven/06-evaluation-delivery/backend.md §4. Los nombres JSON son los del backend (snake_case). Las preguntas reutilizan
// PreguntaAula (la misma forma que ya pintan los controles de Student) y NINGÚN tipo de aquí lleva una clave de corrección: el nodo
// no la tiene (artículo 14) y la biblioteca nunca la entrega a una tableta.

// ------------------------------------------------------------------------------------------ catálogos

/// <summary>Los tres niveles de control (DEC-009), de menor a mayor exigencia.</summary>
public static class Niveles
{
    public const string Abierto = "abierto";
    public const string Supervisado = "supervisado";
    public const string Controlado = "controlado";

    public static readonly IReadOnlyList<string> Todos = [Abierto, Supervisado, Controlado];

    /// <summary>0 abierto · 1 supervisado · 2 controlado. Lo que no se reconoce cuenta como abierto (una tableta que no declara nada no promete nada).</summary>
    public static int Rango(string? nivel) => nivel switch { Supervisado => 1, Controlado => 2, _ => 0 };

    public static string Normalizar(string? nivel) => Rango(nivel) switch { 2 => Controlado, 1 => Supervisado, _ => Abierto };

    /// <summary>BR-075: ¿una tableta que declara <paramref name="capacidad"/> alcanza el nivel <paramref name="exigido"/>?</summary>
    public static bool Alcanza(string? capacidad, string? exigido) => Rango(capacidad) >= Rango(exigido);

    public static string Rotulo(string? nivel) => Normalizar(nivel) switch
    {
        Controlado => "Controlado",
        Supervisado => "Supervisado",
        _ => "Abierto",
    };
}

/// <summary>Los nueve estados del intento (modelado-datos.md §5.2) y los grupos que la tableta necesita distinguir.</summary>
public static class EstadosIntento
{
    public const string NoIniciado = "no_iniciado";
    public const string EnCurso = "en_curso";
    public const string Pausado = "pausado_desconexion";
    public const string Restaurando = "restaurando";
    public const string EnCursoFueraDePlazo = "en_curso_fuera_de_plazo";
    public const string Entregado = "entregado";
    public const string EnRevision = "en_revision_docente";
    public const string Calificado = "calificado";
    public const string Anulado = "anulado";

    /// <summary>El reloj corre y el alumno puede responder.</summary>
    public static bool Corriendo(string? estado) => estado is EnCurso or EnCursoFueraDePlazo;

    /// <summary>Esperan al profesor: el cronómetro está detenido y todo lo respondido está guardado.</summary>
    public static bool Suspendido(string? estado) => estado is Pausado or Restaurando;

    /// <summary>El nodo sigue aceptando respuestas (BR-071: lo capturado antes de la pausa llega después).</summary>
    public static bool AceptaRespuestas(string? estado) => Corriendo(estado) || Suspendido(estado);

    /// <summary>Ya se entregó (o se anuló): el examen terminó para la tableta y el bloqueo puede soltarse.</summary>
    public static bool Terminado(string? estado) => estado is Entregado or EnRevision or Calificado or Anulado;
}

// ------------------------------------------------------------------------------------- el intento

/// <summary>El cronómetro del NODO (INV-017). <c>RestanteMs</c> es nulo si el examen no tiene límite. La tableta lo pinta; nunca lo decide.</summary>
public sealed record RelojDeIntento(
    [property: JsonPropertyName("limite_seg")] int? LimiteSeg,
    [property: JsonPropertyName("restante_ms")] long? RestanteMs,
    [property: JsonPropertyName("corriendo")] bool Corriendo,
    [property: JsonPropertyName("congelado")] bool Congelado,
    [property: JsonPropertyName("servidor_en")] long ServidorEn = 0,
    [property: JsonPropertyName("consumido_ms")] long ConsumidoMs = 0);

/// <summary>
/// Lo que el nodo le pide a la tableta que bloquee (D-12). El nodo decide, la tableta aplica y <b>informa</b> lo que logró
/// (<see cref="InformeDeBloqueo"/>): el nodo nunca presume que se aplicó. <c>Parcial</c> avisa de que se pide <c>controlado</c> y la capa del sistema
/// no está disponible en esta tableta.
/// </summary>
public sealed record PlanDeBloqueo(
    [property: JsonPropertyName("nivel")] string Nivel,
    [property: JsonPropertyName("capa_sistema")] bool CapaSistema,
    [property: JsonPropertyName("capa_app")] bool CapaApp,
    [property: JsonPropertyName("registrar_salidas")] bool RegistrarSalidas,
    [property: JsonPropertyName("registrar_consultas")] bool RegistrarConsultas,
    [property: JsonPropertyName("bloquear_capturas")] bool BloquearCapturas,
    [property: JsonPropertyName("cubrir_pantallas_extra")] bool CubrirPantallasExtra,
    [property: JsonPropertyName("latido_seg")] int LatidoSeg = 5,
    [property: JsonPropertyName("parcial")] bool Parcial = false,
    [property: JsonPropertyName("nivel_exigido")] string? NivelExigido = null,
    [property: JsonPropertyName("capacidad")] string? Capacidad = null)
{
    /// <summary>Sin ninguna exigencia: la tableta no debe cambiar nada de su comportamiento normal.</summary>
    public static readonly PlanDeBloqueo Libre = new(Niveles.Abierto, false, false, false, false, false, false, 10);

    public bool PideAlgo => CapaSistema || CapaApp || BloquearCapturas || CubrirPantallasExtra;

    /// <summary>Las mismas exigencias (la cadencia del latido no cuenta): sirve para no volver a aplicar un bloqueo que ya está aplicado.</summary>
    public bool MismasExigencias(PlanDeBloqueo? otro) =>
        otro is not null && Nivel == otro.Nivel && CapaSistema == otro.CapaSistema && CapaApp == otro.CapaApp && RegistrarSalidas == otro.RegistrarSalidas
        && RegistrarConsultas == otro.RegistrarConsultas && BloquearCapturas == otro.BloquearCapturas && CubrirPantallasExtra == otro.CubrirPantallasExtra
        && Parcial == otro.Parcial;
}

public sealed record MensajeDeIntento(
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("texto")] string Texto);

/// <summary>El intento visto por la tableta. <c>Respondidas</c> y <c>Total</c> sólo cuentan lo que el nodo ya tiene.</summary>
public sealed record ResumenDeIntento(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("numero")] int Numero,
    [property: JsonPropertyName("asignacion_id")] string? AsignacionId = null,
    [property: JsonPropertyName("nivel_efectivo")] string? NivelEfectivo = null,
    [property: JsonPropertyName("pregunta_actual")] string? PreguntaActual = null,
    [property: JsonPropertyName("respondidas")] int Respondidas = 0,
    [property: JsonPropertyName("total")] int Total = 0,
    [property: JsonPropertyName("fuera_de_plazo")] bool FueraDePlazo = false,
    [property: JsonPropertyName("envio_tardio")] string? EnvioTardio = null,
    [property: JsonPropertyName("navegacion_atras")] bool NavegacionAtras = true,
    [property: JsonPropertyName("secuencia_maxima")] int SecuenciaMaxima = 0);

/// <summary>El cuerpo de <c>GET /intentos/{id}/estado/</c> y de <c>POST …/latido/</c>: qué pintar, cuánto tiempo queda y qué se bloquea.</summary>
public sealed record EstadoDeIntento(
    [property: JsonPropertyName("intento")] ResumenDeIntento Intento,
    [property: JsonPropertyName("reloj")] RelojDeIntento? Reloj,
    [property: JsonPropertyName("plan_bloqueo")] PlanDeBloqueo? PlanBloqueo,
    [property: JsonPropertyName("espera_reactivacion")] bool EsperaReactivacion,
    [property: JsonPropertyName("sesion_activa")] bool SesionActiva = true,
    [property: JsonPropertyName("mensaje")] MensajeDeIntento? Mensaje = null,
    [property: JsonPropertyName("resultado_disponible")] bool ResultadoDisponible = false,
    [property: JsonPropertyName("latido_seg")] int LatidoSeg = 5,
    [property: JsonPropertyName("servidor_en")] long ServidorEn = 0);

/// <summary>El texto obligatorio del nivel (JRN-010): el alumno sabe SIEMPRE bajo qué condiciones presenta, antes de empezar.</summary>
public sealed record CondicionesDeExamen(
    [property: JsonPropertyName("nivel")] string Nivel,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("texto")] string Texto,
    [property: JsonPropertyName("registra")] IReadOnlyList<string>? Registra = null,
    [property: JsonPropertyName("sistema")] string? Sistema = null,
    [property: JsonPropertyName("profesor")] string? Profesor = null);

/// <summary>La solicitud del profesor cuando esta tableta no alcanza el nivel (BR-075, BR-076).</summary>
public sealed record AdmisionDeTableta(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("nivel_exigido")] string NivelExigido,
    [property: JsonPropertyName("nivel_alcanzado")] string NivelAlcanzado,
    [property: JsonPropertyName("nivel_admitido")] string? NivelAdmitido = null);

/// <summary>
/// <c>POST /asignaciones/{id}/intentos/</c>: <b>201</b> intento abierto, <b>200</b> ya había uno vivo (<c>Reanudado</c>) o <b>202</b> la tableta no alcanza el
/// nivel y espera al profesor (<c>Admision</c> con estado <c>en_espera</c>, el intento sigue <c>no_iniciado</c>).
/// </summary>
public sealed record AperturaDeIntento(
    [property: JsonPropertyName("intento")] ResumenDeIntento Intento,
    [property: JsonPropertyName("reloj")] RelojDeIntento? Reloj,
    [property: JsonPropertyName("plan_bloqueo")] PlanDeBloqueo? PlanBloqueo,
    [property: JsonPropertyName("condiciones")] CondicionesDeExamen? Condiciones,
    [property: JsonPropertyName("preguntas_total")] int PreguntasTotal,
    [property: JsonPropertyName("espera_reactivacion")] bool EsperaReactivacion,
    [property: JsonPropertyName("mensaje")] MensajeDeIntento? Mensaje,
    [property: JsonPropertyName("reanudado")] bool Reanudado,
    [property: JsonPropertyName("admision")] AdmisionDeTableta? Admision = null,
    [property: JsonPropertyName("servidor_en")] long ServidorEn = 0)
{
    /// <summary>La tableta no alcanza el nivel y el profesor tiene que decidir: el examen todavía no empezó.</summary>
    public bool EnEsperaDeAdmision => Admision is { Estado: "en_espera" } || Intento.Estado == EstadosIntento.NoIniciado;
}

/// <summary>Lo que el alumno ya respondió (según el nodo), para reanudar donde iba.</summary>
public sealed record RespuestaGuardada(
    [property: JsonPropertyName("respuesta")] JsonElement Respuesta,
    [property: JsonPropertyName("secuencia")] int Secuencia);

/// <summary><c>GET /intentos/{id}/preguntas/</c>: el examen DE ESTE ALUMNO, en su orden, sin ninguna clave (<c>Cache-Control: no-store</c>).</summary>
public sealed record PreguntasDeIntento(
    [property: JsonPropertyName("intento_id")] string IntentoId,
    [property: JsonPropertyName("titulo")] string? Titulo,
    [property: JsonPropertyName("instrucciones")] string? Instrucciones,
    [property: JsonPropertyName("instrucciones_tramos")] IReadOnlyList<Tramo>? InstruccionesTramos,
    [property: JsonPropertyName("version")] string? Version,
    [property: JsonPropertyName("navegacion_atras")] bool NavegacionAtras,
    [property: JsonPropertyName("preguntas")] IReadOnlyList<PreguntaAula> Preguntas,
    [property: JsonPropertyName("respondidas")] Dictionary<string, RespuestaGuardada>? Respondidas,
    [property: JsonPropertyName("pregunta_actual")] string? PreguntaActual,
    [property: JsonPropertyName("servidor_en")] long ServidorEn = 0);

// ---------------------------------------------------------------------------- respuestas e incidentes

public sealed record RechazoDeRespuesta(
    [property: JsonPropertyName("pregunta_ref")] string PreguntaRef,
    [property: JsonPropertyName("motivo")] string Motivo);

public sealed record IntentoAcusado(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("respondidas")] int Respondidas,
    [property: JsonPropertyName("secuencia_maxima")] int SecuenciaMaxima = 0,
    [property: JsonPropertyName("envio_tardio")] string? EnvioTardio = null);

/// <summary>
/// El acuse de <c>POST …/respuestas/</c>. <c>Aceptadas</c> entraron, <c>Duplicadas</c> eran un reenvío de lo ya guardado, <c>Superadas</c> llegaron con una
/// secuencia menor o de una sesión más antigua (no pisan a la vigente) y <c>Rechazadas</c> traen su motivo. Con <c>Politica</c> distinta de <c>aceptar</c>
/// (<c>decide_el_profesor</c>) el intento ya se había entregado y el envío espera la decisión del profesor: nunca se descarta en silencio (BR-074).
/// </summary>
public sealed record AcuseDeRespuestas(
    [property: JsonPropertyName("acuse")] bool Acuse,
    [property: JsonPropertyName("aceptadas")] IReadOnlyList<string>? Aceptadas,
    [property: JsonPropertyName("duplicadas")] IReadOnlyList<string>? Duplicadas,
    [property: JsonPropertyName("superadas")] IReadOnlyList<string>? Superadas,
    [property: JsonPropertyName("rechazadas")] IReadOnlyList<RechazoDeRespuesta>? Rechazadas,
    [property: JsonPropertyName("intento")] IntentoAcusado? Intento,
    [property: JsonPropertyName("reloj")] RelojDeIntento? Reloj,
    [property: JsonPropertyName("politica")] string? Politica = null,
    [property: JsonPropertyName("recibida_en")] long RecibidaEn = 0,
    [property: JsonPropertyName("servidor_en")] long ServidorEn = 0)
{
    public bool EsperaAlProfesor => Politica == "decide_el_profesor";
}

/// <summary>Una respuesta capturada en la tableta, con su secuencia y la hora de captura ya normalizada al reloj del nodo (BR-062).</summary>
public sealed record RespuestaDeExamen(
    [property: JsonPropertyName("pregunta_ref")] string PreguntaRef,
    [property: JsonPropertyName("secuencia")] int Secuencia,
    [property: JsonPropertyName("respuesta")] JsonElement Respuesta,
    [property: JsonPropertyName("capturada_en")] long? CapturadaEn = null,
    [property: JsonPropertyName("capturada_en_tableta")] long? CapturadaEnTableta = null);

/// <summary>Los tipos que la tableta puede informar (BR-077). Cualquier otro lo rechaza el nodo: un cliente no fabrica hechos del nodo ni del profesor.</summary>
public static class TiposDeIncidente
{
    public const string SalidaDeApp = "salida_de_app";
    public const string RegresoAApp = "regreso_a_app";
    public const string CierreBloqueado = "cierre_bloqueado";
    public const string TeclaBloqueada = "tecla_bloqueada";
    public const string PantallaAdicional = "pantalla_adicional";
    public const string BloqueoParcial = "bloqueo_parcial";
    public const string BloqueoFallido = "bloqueo_fallido";
    public const string BloqueoLiberado = "bloqueo_liberado";
    public const string ConsultaRecurso = "consulta_recurso";

    public static readonly IReadOnlyList<string> DeLaTableta =
    [
        SalidaDeApp, RegresoAApp, CierreBloqueado, TeclaBloqueada, PantallaAdicional, BloqueoParcial, BloqueoFallido, BloqueoLiberado, ConsultaRecurso,
    ];
}

/// <summary>Un incidente que la tableta vio. <c>RefCliente</c> es la clave de idempotencia: reenviar la cola no duplica nada (INV-005).</summary>
public sealed record IncidenteDeTableta(
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("ref_cliente")] string RefCliente,
    [property: JsonPropertyName("ocurrido_en")] long? OcurridoEn = null,
    [property: JsonPropertyName("ocurrido_en_tableta")] long? OcurridoEnTableta = null,
    [property: JsonPropertyName("detalle")] Dictionary<string, object?>? Detalle = null);

public sealed record AcuseDeIncidentes(
    [property: JsonPropertyName("registrados")] int Registrados,
    [property: JsonPropertyName("duplicados")] int Duplicados,
    [property: JsonPropertyName("estado")] string? Estado = null,
    [property: JsonPropertyName("servidor_en")] long ServidorEn = 0);

// ------------------------------------------------------------------------------------------ bloqueo

/// <summary>Las capas que la tableta LOGRÓ aplicar (no las que se le pidieron).</summary>
public sealed record CapasDeBloqueo(
    [property: JsonPropertyName("sistema")] bool Sistema,
    [property: JsonPropertyName("app")] bool App,
    [property: JsonPropertyName("capturas")] bool Capturas,
    [property: JsonPropertyName("pantallas")] bool Pantallas)
{
    public static readonly CapasDeBloqueo Ninguna = new(false, false, false, false);
}

public static class ResultadosDeBloqueo
{
    public const string Aplicado = "aplicado";
    public const string Parcial = "parcial";
    public const string Fallido = "fallido";
    public const string Liberado = "liberado";
}

/// <summary>Lo que la tableta le dice al nodo sobre el bloqueo (kiosk.md §5.2): un resultado tipado, nunca una excepción usada como canal de estado.</summary>
public sealed record InformeDeBloqueo(
    [property: JsonPropertyName("resultado")] string Resultado,
    [property: JsonPropertyName("capas")] CapasDeBloqueo Capas,
    [property: JsonPropertyName("motivo")] string? Motivo = null)
{
    public bool Completo => Resultado is ResultadosDeBloqueo.Aplicado or ResultadosDeBloqueo.Liberado;
}

public sealed record AcuseDeBloqueo(
    [property: JsonPropertyName("plan_bloqueo")] PlanDeBloqueo? PlanBloqueo,
    [property: JsonPropertyName("incidente")] string? Incidente,
    [property: JsonPropertyName("servidor_en")] long ServidorEn = 0);

// ------------------------------------------------------------------------------- entrega y resultado

public sealed record QueSigue(
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("texto")] string Texto);

/// <summary>PAN-123: la confirmación de la entrega. NUNCA dice «calificado» mientras quede un reactivo por revisar.</summary>
public sealed record EntregaDeIntento(
    [property: JsonPropertyName("intento")] ResumenDeIntento Intento,
    [property: JsonPropertyName("entregado_en")] long? EntregadoEn,
    [property: JsonPropertyName("origen_entrega")] string? OrigenEntrega,
    [property: JsonPropertyName("que_sigue")] QueSigue QueSigue,
    [property: JsonPropertyName("resultado_disponible")] bool ResultadoDisponible = false,
    [property: JsonPropertyName("servidor_en")] long ServidorEn = 0);

public sealed record DetalleDeResultado(
    [property: JsonPropertyName("pregunta_ref")] string PreguntaRef,
    [property: JsonPropertyName("respondida")] bool Respondida,
    [property: JsonPropertyName("puntaje")] double? Puntaje,
    [property: JsonPropertyName("puntaje_maximo")] double? PuntajeMaximo,
    [property: JsonPropertyName("correcta")] bool? Correcta,
    [property: JsonPropertyName("retroalimentacion")] IReadOnlyList<string>? Retroalimentacion = null,
    [property: JsonPropertyName("comentario")] string? Comentario = null);

/// <summary>Sólo cuando el profesor liberó los resultados (DEC-032). Antes, el nodo responde 403 <c>resultados_no_liberados</c>.</summary>
public sealed record ResultadoDeIntento(
    [property: JsonPropertyName("intento_id")] string IntentoId,
    [property: JsonPropertyName("porcentaje")] double? Porcentaje,
    [property: JsonPropertyName("puntaje")] double? Puntaje,
    [property: JsonPropertyName("puntaje_maximo")] double? PuntajeMaximo,
    [property: JsonPropertyName("aprobado")] bool? Aprobado,
    [property: JsonPropertyName("aprobacion_pct")] double? AprobacionPct,
    [property: JsonPropertyName("detalle")] IReadOnlyList<DetalleDeResultado>? Detalle,
    [property: JsonPropertyName("servidor_en")] long ServidorEn = 0);

// ----------------------------------------------------------------------------- descubrir y antesala

public sealed record MiIntento(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("numero")] int Numero,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("resultado_disponible")] bool ResultadoDisponible = false);

/// <summary>Una evaluación que le alcanza al alumno. <c>PuedeComenzar = false</c> trae su <c>Motivo</c> (<c>espera_admision</c> · <c>rechazada</c> · <c>no_abierta</c> · …).</summary>
public sealed record EvaluacionDelAlumno(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("curso_rotulo")] string? CursoRotulo,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("nivel_examen")] string NivelExamen,
    [property: JsonPropertyName("abre_en")] long? AbreEn,
    [property: JsonPropertyName("limite_en")] long? LimiteEn,
    [property: JsonPropertyName("plazo")] string? Plazo,
    [property: JsonPropertyName("sesion_id")] string? SesionId,
    [property: JsonPropertyName("preguntas")] int Preguntas,
    [property: JsonPropertyName("puede_comenzar")] bool PuedeComenzar,
    [property: JsonPropertyName("motivo")] string? Motivo,
    [property: JsonPropertyName("mi_intento")] MiIntento? MiIntento);

public sealed record MisEvaluaciones(
    [property: JsonPropertyName("pendientes")] IReadOnlyList<EvaluacionDelAlumno> Pendientes,
    [property: JsonPropertyName("recientes")] IReadOnlyList<EvaluacionDelAlumno> Recientes,
    [property: JsonPropertyName("alumno_id")] string? AlumnoId = null,
    [property: JsonPropertyName("servidor_en")] long ServidorEn = 0)
{
    public static readonly MisEvaluaciones Vacio = new([], []);
}

public sealed record DatosDeLaAntesala(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("curso_rotulo")] string? CursoRotulo,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("preguntas")] int Preguntas,
    [property: JsonPropertyName("duracion_seg")] int? DuracionSeg,
    [property: JsonPropertyName("intentos_permitidos")] int? IntentosPermitidos,
    [property: JsonPropertyName("intentos_usados")] int IntentosUsados,
    [property: JsonPropertyName("plazo")] string? Plazo,
    [property: JsonPropertyName("limite_en")] long? LimiteEn,
    [property: JsonPropertyName("resultados")] string? Resultados,
    [property: JsonPropertyName("permite_retroceso")] bool PermiteRetroceso = true);

public sealed record DispositivoDeAntesala(
    [property: JsonPropertyName("id")] string? Id,
    [property: JsonPropertyName("capacidad")] string? Capacidad,
    [property: JsonPropertyName("alcanza")] bool Alcanza,
    [property: JsonPropertyName("nivel_exigido")] string NivelExigido);

/// <summary>PAN-120: lo que el alumno debe ver ANTES de empezar —duración, condiciones y qué se registra—. Iniciar sin que lo haya visto es lo que el sistema nunca hace.</summary>
public sealed record AntesalaDeExamen(
    [property: JsonPropertyName("asignacion")] DatosDeLaAntesala Asignacion,
    [property: JsonPropertyName("condiciones")] CondicionesDeExamen Condiciones,
    [property: JsonPropertyName("dispositivo")] DispositivoDeAntesala? Dispositivo,
    [property: JsonPropertyName("admision")] AdmisionDeTableta? Admision,
    [property: JsonPropertyName("mi_intento")] MiIntento? MiIntento,
    [property: JsonPropertyName("puede_comenzar")] bool PuedeComenzar,
    [property: JsonPropertyName("motivo")] string? Motivo,
    [property: JsonPropertyName("servidor_en")] long ServidorEn = 0);

// ======================================================================================= profesor · OPS

/// <summary>Una asignación de examen (ENT-011). <c>Nivel</c> es el vigente; <c>NivelDeclarado</c> el mínimo con que se creó.</summary>
public sealed record AsignacionDeExamen(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("nivel_examen")] string NivelExamen,
    [property: JsonPropertyName("nivel_declarado")] string? NivelDeclarado,
    [property: JsonPropertyName("plazo")] string? Plazo,
    [property: JsonPropertyName("abre_en")] long? AbreEn,
    [property: JsonPropertyName("limite_en")] long? LimiteEn,
    [property: JsonPropertyName("gracia_ms")] long GraciaMs,
    [property: JsonPropertyName("reactivacion")] string? Reactivacion,
    [property: JsonPropertyName("intentos_permitidos")] int? IntentosPermitidos,
    [property: JsonPropertyName("sesion_id")] string? SesionId,
    [property: JsonPropertyName("resultados")] string? Resultados,
    [property: JsonPropertyName("liberados_en")] long? LiberadosEn,
    [property: JsonPropertyName("objeto_rotulo")] string? ObjetoRotulo,
    [property: JsonPropertyName("curso_rotulo")] string? CursoRotulo,
    [property: JsonPropertyName("grupo_rotulo")] string? GrupoRotulo,
    [property: JsonPropertyName("preguntas_por_alumno")] int PreguntasPorAlumno,
    [property: JsonPropertyName("armado_previo")] ArmadoPrevio? ArmadoPrevio = null,
    [property: JsonPropertyName("totales")] TotalesDelPanel? Totales = null)
{
    public bool Abierta => Estado is "activa" or "activa_fuera_de_plazo";
}

public sealed record ArmadoPrevio(
    [property: JsonPropertyName("estrategia")] string? Estrategia,
    [property: JsonPropertyName("preguntas_por_alumno")] int PreguntasPorAlumno,
    [property: JsonPropertyName("total_banco")] int TotalBanco,
    [property: JsonPropertyName("limite_seg_estimado")] int? LimiteSegEstimado,
    [property: JsonPropertyName("avisos")] IReadOnlyList<string>? Avisos);

public sealed record ListaDeAsignaciones(
    [property: JsonPropertyName("asignaciones")] IReadOnlyList<AsignacionDeExamen> Asignaciones);

/// <summary>El tiempo del examen que el profesor elige: lo que dice la biblioteca, un límite fijo o sin límite.</summary>
public sealed record TiempoDeExamen(
    [property: JsonPropertyName("modo")] string Modo,
    [property: JsonPropertyName("limite_seg")] int? LimiteSeg = null)
{
    public static readonly TiempoDeExamen DeLaBiblioteca = new("biblioteca");
    public static readonly TiempoDeExamen SinLimite = new("sin_limite");
    public static TiempoDeExamen Fijo(int segundos) => new("fijo", segundos);
}

/// <summary>
/// Lo que el profesor decide al aplicar un examen. <c>NivelExamen</c> es OBLIGATORIO y el sistema nunca lo preselecciona (Guion, paso 1).
/// Los campos que valen null no viajan.
/// </summary>
public sealed record NuevoExamen(
    string Fuente, string CursoRef, string ObjetoRef, string NivelExamen, string GrupoId, string? SesionId = null,
    TiempoDeExamen? Tiempo = null, int? IntentosPermitidos = 1, long? AbreEn = null, long? LimiteEn = null, string Plazo = "blando", int? GraciaMin = null,
    string Reactivacion = "profesor", string Resultados = "tras_liberar", bool Iniciar = true);

public sealed record TotalesDelPanel(
    [property: JsonPropertyName("destinatarios")] int Destinatarios,
    [property: JsonPropertyName("sin_intento")] int SinIntento,
    [property: JsonPropertyName("en_espera_admision")] int EnEsperaAdmision,
    [property: JsonPropertyName("en_curso")] int EnCurso,
    [property: JsonPropertyName("suspendidos")] int Suspendidos,
    [property: JsonPropertyName("restaurando")] int Restaurando,
    [property: JsonPropertyName("entregados")] int Entregados,
    [property: JsonPropertyName("en_revision")] int EnRevision,
    [property: JsonPropertyName("calificados")] int Calificados,
    [property: JsonPropertyName("anulados")] int Anulados,
    [property: JsonPropertyName("con_incidentes")] int ConIncidentes,
    [property: JsonPropertyName("pendientes_decision")] int PendientesDecision,
    [property: JsonPropertyName("no_iniciados")] int NoIniciados = 0);

public sealed record TabletaDeFila(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("nombre")] string? Nombre,
    [property: JsonPropertyName("capacidad")] string? Capacidad,
    [property: JsonPropertyName("alcanza")] bool Alcanza);

public sealed record ResumenDeIncidentes(
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("informativa")] int Informativa,
    [property: JsonPropertyName("atencion")] int Atencion,
    [property: JsonPropertyName("alta")] int Alta,
    [property: JsonPropertyName("ultimo")] UltimoIncidente? Ultimo);

public sealed record UltimoIncidente(
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("ocurrido_en")] long OcurridoEn,
    [property: JsonPropertyName("severidad")] string? Severidad = null);

public sealed record BloqueoDeFila([property: JsonPropertyName("resultado")] string? Resultado);

public sealed record AdmisionDeFila(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("nivel_exigido")] string NivelExigido,
    [property: JsonPropertyName("nivel_alcanzado")] string NivelAlcanzado);

/// <summary>Una fila del panel (PAN-005/121). Ordenadas por quién necesita al profesor, no alfabéticamente. No suena, no marca en rojo y no ofrece anular.</summary>
public sealed record FilaDelPanel(
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("rotulo")] string Rotulo,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("requiere_reactivacion")] bool RequiereReactivacion,
    [property: JsonPropertyName("intento_id")] string? IntentoId,
    [property: JsonPropertyName("numero")] int? Numero,
    [property: JsonPropertyName("nivel_efectivo")] string? NivelEfectivo,
    [property: JsonPropertyName("dispositivo")] TabletaDeFila? Dispositivo,
    [property: JsonPropertyName("respondidas")] int Respondidas,
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("pregunta_actual")] string? PreguntaActual,
    [property: JsonPropertyName("reloj")] RelojDeIntento? Reloj,
    [property: JsonPropertyName("silencio_ms")] long? SilencioMs,
    [property: JsonPropertyName("incidentes")] ResumenDeIncidentes? Incidentes,
    [property: JsonPropertyName("bloqueo")] BloqueoDeFila? Bloqueo,
    [property: JsonPropertyName("admision")] AdmisionDeFila? Admision,
    [property: JsonPropertyName("fuera_de_plazo")] bool FueraDePlazo,
    [property: JsonPropertyName("envio_tardio")] string? EnvioTardio,
    [property: JsonPropertyName("origen_entrega")] string? OrigenEntrega,
    [property: JsonPropertyName("requiere_revision")] bool RequiereRevision,
    [property: JsonPropertyName("porcentaje")] double? Porcentaje,
    [property: JsonPropertyName("anulado_por")] string? AnuladoPor)
{
    public bool EsperaAlProfesor => RequiereReactivacion || Admision is { Estado: "en_espera" } || EnvioTardio == "pendiente_decision";
}

public sealed record PanelDeExamen(
    [property: JsonPropertyName("asignacion")] AsignacionDeExamen Asignacion,
    [property: JsonPropertyName("totales")] TotalesDelPanel Totales,
    [property: JsonPropertyName("filas")] IReadOnlyList<FilaDelPanel> Filas,
    [property: JsonPropertyName("servidor_en")] long ServidorEn = 0);

public sealed record FilaDeElegibilidad(
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("rotulo")] string Rotulo,
    [property: JsonPropertyName("dispositivo_id")] string? DispositivoId,
    [property: JsonPropertyName("dispositivo_nombre")] string? DispositivoNombre,
    [property: JsonPropertyName("capacidad")] string? Capacidad,
    [property: JsonPropertyName("nivel_exigido")] string NivelExigido,
    [property: JsonPropertyName("alcanza")] bool? Alcanza);

public sealed record ResumenDeElegibilidad(
    [property: JsonPropertyName("alcanzan")] int Alcanzan,
    [property: JsonPropertyName("no_alcanzan")] int NoAlcanzan,
    [property: JsonPropertyName("sin_tableta")] int SinTableta);

/// <summary>PAN-060, paso 4: qué tabletas alcanzan el nivel (MSG-036). Se pide ANTES de aplicar y al cambiar de nivel.</summary>
public sealed record ElegibilidadDeTabletas(
    [property: JsonPropertyName("nivel_examen")] string NivelExamen,
    [property: JsonPropertyName("filas")] IReadOnlyList<FilaDeElegibilidad> Filas,
    [property: JsonPropertyName("resumen")] ResumenDeElegibilidad Resumen,
    [property: JsonPropertyName("mensaje")] string? Mensaje,
    [property: JsonPropertyName("servidor_en")] long ServidorEn = 0);

public sealed record AdmisionPendiente(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("alumno_rotulo")] string? AlumnoRotulo,
    [property: JsonPropertyName("dispositivo_id")] string? DispositivoId,
    [property: JsonPropertyName("dispositivo_rotulo")] string? DispositivoRotulo,
    [property: JsonPropertyName("nivel_exigido")] string NivelExigido,
    [property: JsonPropertyName("nivel_alcanzado")] string NivelAlcanzado,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("nivel_admitido")] string? NivelAdmitido = null,
    [property: JsonPropertyName("motivo")] string? Motivo = null);

public sealed record ListaDeAdmisiones(
    [property: JsonPropertyName("admisiones")] IReadOnlyList<AdmisionPendiente> Admisiones);

public sealed record ReactivacionHecha(
    [property: JsonPropertyName("intento_id")] string? IntentoId,
    [property: JsonPropertyName("estado")] string? Estado,
    [property: JsonPropertyName("restante_ms")] long? RestanteMs,
    [property: JsonPropertyName("desde_pregunta")] string? DesdePregunta,
    [property: JsonPropertyName("suspendidos")] int Suspendidos = 0,
    [property: JsonPropertyName("reactivados")] int Reactivados = 0);

public sealed record LineaDeTiempo(
    [property: JsonPropertyName("en")] long En,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("origen")] string? Origen,
    [property: JsonPropertyName("severidad")] string? Severidad = null,
    [property: JsonPropertyName("detalle")] JsonElement? Detalle = null);

public sealed record IncidenteDeExpediente(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("severidad")] string Severidad,
    [property: JsonPropertyName("origen")] string Origen,
    [property: JsonPropertyName("ocurrido_en")] long OcurridoEn,
    [property: JsonPropertyName("detalle")] JsonElement? Detalle = null);

public sealed record DatosDelExpediente(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("alumno_rotulo")] string? AlumnoRotulo,
    [property: JsonPropertyName("numero")] int Numero,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("nivel_efectivo")] string? NivelEfectivo,
    [property: JsonPropertyName("origen_entrega")] string? OrigenEntrega,
    [property: JsonPropertyName("fuera_de_plazo")] bool FueraDePlazo,
    [property: JsonPropertyName("envio_tardio")] string? EnvioTardio,
    [property: JsonPropertyName("porcentaje")] double? Porcentaje,
    [property: JsonPropertyName("anulado_por")] string? AnuladoPor,
    [property: JsonPropertyName("motivo_anulacion")] string? MotivoAnulacion,
    [property: JsonPropertyName("iniciado_en")] long? IniciadoEn,
    [property: JsonPropertyName("entregado_en")] long? EntregadoEn);

/// <summary>PAN-062. Sólo lectura: ni siquiera ofrece la acción de anular junto al expediente (Guion, paso 7).</summary>
public sealed record ExpedienteDeIntento(
    [property: JsonPropertyName("intento")] DatosDelExpediente Intento,
    [property: JsonPropertyName("respondidas")] int Respondidas,
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("reloj")] RelojDeIntento? Reloj,
    [property: JsonPropertyName("incidentes")] IReadOnlyList<IncidenteDeExpediente> Incidentes,
    [property: JsonPropertyName("resumen_incidentes")] ResumenDeIncidentes ResumenIncidentes,
    [property: JsonPropertyName("linea_de_tiempo")] IReadOnlyList<LineaDeTiempo> LineaDeTiempo,
    [property: JsonPropertyName("servidor_en")] long ServidorEn = 0);

public sealed record FilaDeResultados(
    [property: JsonPropertyName("alumno_id")] string AlumnoId,
    [property: JsonPropertyName("rotulo")] string Rotulo,
    [property: JsonPropertyName("intento_id")] string? IntentoId,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("porcentaje")] double? Porcentaje,
    [property: JsonPropertyName("definitivo")] bool Definitivo,
    [property: JsonPropertyName("aprobado")] bool? Aprobado,
    [property: JsonPropertyName("fuera_de_plazo")] bool FueraDePlazo,
    [property: JsonPropertyName("requiere_revision")] bool RequiereRevision,
    [property: JsonPropertyName("incidentes")] int Incidentes);

public sealed record ResultadosDeExamen(
    [property: JsonPropertyName("asignacion_id")] string AsignacionId,
    [property: JsonPropertyName("titulo")] string? Titulo,
    [property: JsonPropertyName("aprobacion_pct")] double? AprobacionPct,
    [property: JsonPropertyName("liberados_en")] long? LiberadosEn,
    [property: JsonPropertyName("promedio_porcentaje")] double? PromedioPorcentaje,
    [property: JsonPropertyName("datos_suficientes")] bool DatosSuficientes,
    [property: JsonPropertyName("filas")] IReadOnlyList<FilaDeResultados> Filas);

public sealed record PreguntaDeRevision(
    [property: JsonPropertyName("pregunta")] PreguntaAula Pregunta,
    [property: JsonPropertyName("respuesta")] JsonElement? Respuesta,
    [property: JsonPropertyName("respondida")] bool Respondida,
    [property: JsonPropertyName("veredicto")] JsonElement? Veredicto,
    [property: JsonPropertyName("revision")] JsonElement? Revision);

public sealed record RevisionDeIntento(
    [property: JsonPropertyName("intento")] JsonElement Intento,
    [property: JsonPropertyName("titulo")] string? Titulo,
    [property: JsonPropertyName("filas")] IReadOnlyList<PreguntaDeRevision> Filas);

public sealed record PuntajeAsentado(
    [property: JsonPropertyName("pregunta_ref")] string PreguntaRef,
    [property: JsonPropertyName("puntaje")] double Puntaje,
    [property: JsonPropertyName("pendientes")] IReadOnlyList<string>? Pendientes,
    [property: JsonPropertyName("porcentaje")] double? Porcentaje);

public sealed record IntentoPublicado(
    [property: JsonPropertyName("intento_id")] string IntentoId,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("porcentaje")] double? Porcentaje,
    [property: JsonPropertyName("calificado_por")] string? CalificadoPor);

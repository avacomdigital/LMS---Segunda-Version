"""
La práctica autocalificable (D-5, D-6, FUN-083, FUN-088, BR-055): respuestas, veredictos, aciertos y el mensaje que se le dice al
alumno. Dominio puro: no importa Django ni sabe de HTTP.

Reglas del Documento Maestro que se cumplen aquí:
  - BR-055 · D-5: la práctica es una actividad de aprendizaje SEPARADA de la evaluación formal. No consume intentos, no tiene tope de
    intentos («Puedes intentarlo nuevamente») y nunca se llama «nota», «examen» ni «evaluación».
  - DEC-032: el módulo no publica nota ni la guarda como calificación. El «resultado» es una lectura amable de cuántas respuestas
    fueron correctas; `puntaje` y `puntaje_maximo` viven en la escala interna y no se muestran.
  - INV-013 · BR-138: una respuesta por pregunta y secuencia; reenviar el mismo paquete no duplica nada y entre dos secuencias
    prevalece la mayor. Se reutiliza `classroom_engine.dominio.actividad.fusionar_respuestas` (regla pura del aula), no se copia.
  - D-6: la clave de respuesta sólo vive en la biblioteca. Lo que no se pudo calificar (biblioteca cerrada, pregunta abierta) queda
    SIN veredicto y se califica en la siguiente lectura o sincronización; mientras tanto no se inventa nota.
"""
from __future__ import annotations

from classroom_engine.dominio import actividad as actividad_aula
from classroom_engine.dominio import respuestas as respuestas_aula
from classroom_engine.dominio.errores import DatosInvalidos as DatosInvalidosAula

from . import catalogos as cat
from .errores import DatosInvalidos

MAX_RESPUESTAS_POR_ENVIO = 200

# Lo que se le dice al alumno al terminar. Nunca «nota», «examen» ni «evaluación» (BR-055).
MENSAJE_MUY_BIEN = "¡Muy bien!"
MENSAJE_BUEN_AVANCE = "¡Buen avance!"
MENSAJE_SIGUE_PRACTICANDO = "Sigue practicando: puedes intentarlo otra vez"
MENSAJE_GUARDADO = "Tus respuestas quedaron guardadas: verás cuántas acertaste en cuanto se revisen."
MENSAJE_SIN_RESPUESTAS = "Aún no respondiste ninguna pregunta: puedes intentarlo otra vez"
UMBRAL_MUY_BIEN, UMBRAL_BUEN_AVANCE = 85.0, 60.0


# ---------------------------------------------------------------------- lo que llega del aparato

def _entero(valor, minimo: int = 0) -> int | None:
    if isinstance(valor, bool) or valor in (None, ""):
        return None
    try:
        entero = int(valor)
    except (TypeError, ValueError):
        return None
    return entero if entero >= minimo else None


def normalizar_respuestas(entrada) -> tuple[list[dict], list[dict]]:
    """`(limpias, rechazadas)`. Cada respuesta lleva `pregunta_ref`, `respuesta` (un objeto con la forma del tipo de pregunta),
    `secuencia` (un entero ≥ 1, monotónico por práctica y aparato) y, opcional, `capturada_en` (ya normalizada al reloj del nodo).
    Lo mal formado se rechaza pregunta por pregunta: el resto se guarda igual (BR-071)."""
    if not isinstance(entrada, list):
        raise DatosInvalidos("`respuestas` debe ser una lista.")
    if len(entrada) > MAX_RESPUESTAS_POR_ENVIO:
        raise DatosInvalidos(f"Un envío admite hasta {MAX_RESPUESTAS_POR_ENVIO} respuestas.", respuestas=len(entrada))
    limpias: list[dict] = []
    rechazadas: list[dict] = []
    for r in entrada:
        ref = str(r.get("pregunta_ref") or "") if isinstance(r, dict) else ""
        if not ref:
            rechazadas.append({"pregunta_ref": "", "motivo": "falta pregunta_ref"})
        elif not isinstance(r.get("respuesta"), dict) or not r["respuesta"]:
            rechazadas.append({"pregunta_ref": ref, "motivo": "la respuesta debe ser un objeto no vacío"})
        elif _entero(r.get("secuencia"), 1) is None:
            rechazadas.append({"pregunta_ref": ref, "motivo": "la secuencia debe ser un entero ≥ 1"})
        else:
            limpias.append({"pregunta_ref": ref, "respuesta": dict(r["respuesta"]), "secuencia": _entero(r.get("secuencia"), 1),
                            "capturada_en": _entero(r.get("capturada_en"))})
    return limpias, rechazadas


def pregunta_de(objeto: dict | None, pregunta_ref: str) -> dict | None:
    """La pregunta de la actividad tal como la vio el alumno (sin claves), o None."""
    return next((p for p in (objeto or {}).get("preguntas") or [] if p.get("pregunta_ref") == pregunta_ref), None)


def validar_forma(pregunta: dict, respuesta: dict) -> dict:
    """La `response` tal como debe viajar a la biblioteca, o DatosInvalidos. Las opciones, huecos, parejas y elementos se identifican
    por su `id`, nunca por su posición (llegan barajados). Es la validación del aula (`respuestas.validar_respuesta`)."""
    try:
        return respuestas_aula.validar_respuesta(pregunta, respuesta)
    except DatosInvalidosAula as error:
        raise DatosInvalidos(error.detalle, **error.extra) from error


def fusionar(vigentes: list[dict], nuevas: list[dict]) -> tuple[list[dict], actividad_aula.ResultadoFusion]:
    """INV-013: aplica las respuestas nuevas sobre las vigentes de una práctica sin duplicar nada. La misma secuencia de la misma
    pregunta es un reenvío (se acusa y no se toca); una mayor sustituye a la vigente; una menor llega tarde y no la pisa."""
    fusionadas, resultado = actividad_aula.fusionar_respuestas(vigentes, nuevas)
    for r in fusionadas:
        r.pop("sesion_usuario_id", None)     # el aula lo usa para separar sesiones de usuario; aquí la identidad es del aparato
    return fusionadas, resultado


# ------------------------------------------------------------------------------- veredictos

def veredicto_a_guardar(veredicto: dict | None) -> dict | None:
    """Lo que se guarda de la traducción del veredicto de la biblioteca: sin ninguna clave, sólo el resultado y su retroalimentación."""
    if veredicto is None:
        return None
    correcta = veredicto.get("correcta")
    return {"puntaje": veredicto.get("puntaje"), "puntaje_maximo": veredicto.get("puntaje_maximo"),
            "correcta": correcta if isinstance(correcta, bool) else None,
            "pendiente": bool(veredicto.get("pendiente")), "retroalimentacion": [str(x) for x in veredicto.get("retroalimentacion") or []]}


def veredicto_publico(respuesta: dict) -> dict | None:
    """El veredicto de una respuesta con la forma del contrato: `{pregunta_ref, correcta, puntaje, puntaje_maximo, pendiente,
    retroalimentacion[]}`. None si aún no se calificó."""
    v = respuesta.get("veredicto")
    if v is None:
        return None
    return {"pregunta_ref": str(respuesta["pregunta_ref"]), "correcta": v.get("correcta"), "puntaje": v.get("puntaje"),
            "puntaje_maximo": v.get("puntaje_maximo"), "pendiente": bool(v.get("pendiente")),
            "retroalimentacion": list(v.get("retroalimentacion") or [])}


def calificada(respuesta: dict) -> bool:
    """Con veredicto y sin quedar pendiente de revisión manual."""
    v = respuesta.get("veredicto")
    return v is not None and not v.get("pendiente")


def sin_calificar(respuestas: list[dict]) -> int:
    return sum(1 for r in respuestas if not calificada(r))


def aciertos(respuestas: list[dict]) -> int:
    """Las respuestas con `correcta = true`."""
    return sum(1 for r in respuestas if (r.get("veredicto") or {}).get("correcta") is True)


def por_calificar(respuestas: list[dict]) -> list[dict]:
    """Lo que todavía no tiene veredicto (la biblioteca no estaba): se reintenta en la siguiente lectura o sincronización."""
    return [r for r in respuestas if r.get("veredicto") is None]


def aplicar_veredictos(respuestas: list[dict], calificadas: dict[str, tuple[int | None, dict | None]]) -> tuple[list[dict], list[str]]:
    """Pone cada veredicto sobre la respuesta que se calificó: `calificadas` es `{pregunta_ref: (secuencia, veredicto)}`. Si la
    respuesta vigente ya es otra (una secuencia mayor llegó mientras se calificaba), el veredicto viejo no la pisa."""
    aplicados: list[str] = []
    for r in respuestas:
        ref = str(r["pregunta_ref"])
        if ref not in calificadas:
            continue
        secuencia, veredicto = calificadas[ref]
        if veredicto is None or (secuencia is not None and int(r.get("secuencia") or 0) != int(secuencia)):
            continue
        r["veredicto"] = veredicto_a_guardar(veredicto)
        aplicados.append(ref)
    return respuestas, aplicados


def totales(respuestas: list[dict]) -> tuple[float | None, float | None]:
    """(puntaje, máximo) de lo ya calificado, en la escala interna. Lo pendiente no suma: no se inventa nota. No se publica."""
    puntaje, maximo, _ = actividad_aula.totales_del_intento(respuestas)
    return puntaje, maximo


def resumen(respuestas: list[dict], total_preguntas: int) -> dict:
    """Lo que la pantalla necesita saber de una práctica: `{respondidas, aciertos, total_preguntas, sin_calificar}`."""
    return {"respondidas": len(respuestas), "aciertos": aciertos(respuestas), "total_preguntas": int(total_preguntas),
            "sin_calificar": sin_calificar(respuestas)}


def respondidas_del_alumno(respuestas: list[dict]) -> dict[str, dict]:
    """`{pregunta_ref: {respuesta, veredicto}}`: lo que el alumno ya contestó en esta práctica, para reanudarla."""
    return {str(r["pregunta_ref"]): {"respuesta": r["respuesta"], "veredicto": veredicto_publico(r)} for r in respuestas}


# -------------------------------------------------------------------------------- resultado

def mensaje_de(correctas: int, total: int, respondidas: int, calificadas: int) -> str:
    """El mensaje amable del resultado. Sin nada respondido o sin nada calificado todavía, no se inventa un resultado."""
    if respondidas == 0:
        return MENSAJE_SIN_RESPUESTAS
    if calificadas == 0:
        return MENSAJE_GUARDADO
    porcentaje = 100.0 * correctas / total if total else 0.0
    if porcentaje >= UMBRAL_MUY_BIEN:
        return MENSAJE_MUY_BIEN
    if porcentaje >= UMBRAL_BUEN_AVANCE:
        return MENSAJE_BUEN_AVANCE
    return MENSAJE_SIGUE_PRACTICANDO


def resultado_de(respuestas: list[dict], total_preguntas: int) -> dict:
    """«7 de 8 correctas»: `{correctas, total, porcentaje, mensaje, revision[{pregunta_ref, correcta, retroalimentacion[]}],
    sin_calificar}`. Es una lectura de la práctica, no una nota (DEC-032)."""
    correctas = aciertos(respuestas)
    total = int(total_preguntas)
    calificadas = sum(1 for r in respuestas if calificada(r))
    return {
        "correctas": correctas, "total": total,
        "porcentaje": round(100.0 * correctas / total, 2) if total else None,
        "mensaje": mensaje_de(correctas, total, len(respuestas), calificadas),
        "revision": [{"pregunta_ref": str(r["pregunta_ref"]), "correcta": (r.get("veredicto") or {}).get("correcta"),
                      "retroalimentacion": list((r.get("veredicto") or {}).get("retroalimentacion") or [])} for r in respuestas],
        "sin_calificar": sin_calificar(respuestas),
    }


# ------------------------------------------------------------------- resumen en la tarea

def siguiente_numero(practicas: list[dict]) -> int:
    """El número de la práctica siguiente: 1, 2, 3… sin tope (D-5)."""
    return max((int(p["numero"]) for p in practicas), default=0) + 1


def resumen_de_practicas(practicas: list[dict], total_por_defecto: int = 0) -> dict:
    """El resumen que la tarea guarda de las prácticas de UNA actividad: cuántas se han abierto, los aciertos de la mejor y de la
    última TERMINADA (None si no hay ninguna) y el total de preguntas."""
    terminadas = sorted((p for p in practicas if p["estado"] == cat.TERMINADA), key=lambda p: int(p["numero"]))
    total = int(max(practicas, key=lambda p: int(p["numero"]))["total_preguntas"]) if practicas else 0
    return {
        "practica_intentos": len(practicas),
        "practica_mejor": max((int(p["aciertos"]) for p in terminadas), default=None),
        "practica_ultima": int(terminadas[-1]["aciertos"]) if terminadas else None,
        "practica_total": total or int(total_por_defecto or 0),
    }

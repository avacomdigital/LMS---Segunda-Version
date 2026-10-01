"""
Las respuestas de un intento (FUN-110, FUN-111, INV-013, BR-009, BR-071, BR-138, D-6, D-7): fusión idempotente con sesiones, forma por tipo
y totales en la escala interna de 0 a 100. Dominio puro: ningún archivo de esta carpeta importa Django ni sabe de HTTP.

Una respuesta es única por (intento, pregunta, sesión, secuencia). La secuencia es un contador monotónico que la tableta persiste ANTES de
enviar y que no depende de su reloj. Reglas de la fusión, por pregunta:

  · misma sesión, misma secuencia          → DUPLICADA: se acusa y no se toca (reenvío del mismo paquete, INV-005)
  · misma sesión, secuencia menor          → SUPERADA: llegó tarde; no pisa a la vigente
  · misma sesión, secuencia mayor          → ACEPTADA: sustituye a la vigente
  · otra sesión, MÁS reciente que la vigente → ACEPTADA (BR-138: gana la sesión más reciente, sin importar el orden de llegada)
  · otra sesión, MÁS antigua que la vigente  → SUPERADA: la tableta anterior no sustituye a la actual (TST-027)

Lo sustituido o superado no se pierde: queda en `historial` de esa respuesta (acotado), como evidencia.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from classroom_engine.dominio.respuestas import FORMAS_RESPUESTA          # la misma tabla que usa el aula: tipo → claves admitidas

from . import catalogos as cat
from .errores import DatosInvalidos

MAX_HISTORIAL = 10


@dataclass
class ResultadoFusion:
    aceptadas: list[str] = field(default_factory=list)
    duplicadas: list[str] = field(default_factory=list)
    superadas: list[str] = field(default_factory=list)


def forma_valida(tipo: str, respuesta: Any) -> str | None:
    """Comprobación ligera de la FORMA de una respuesta (no de su acierto): un objeto no vacío cuyas claves son las que admite el tipo. Devuelve
    el motivo del rechazo o None. La validación profunda (cada referencia existe en la pregunta que vio el alumno) se hace al calificar."""
    if not isinstance(respuesta, dict) or not respuesta:
        return "la respuesta debe ser un objeto no vacío"
    claves = FORMAS_RESPUESTA.get(tipo)
    if claves is None:
        return None                        # tipo que este LMS no conoce (conjunto abierto): la biblioteca decide
    sobrantes = set(respuesta) - set(claves)
    if sobrantes:
        return f"una pregunta «{tipo}» admite {', '.join(claves)}; sobra: {', '.join(sorted(sobrantes))}"
    return None


def limpiar_respuestas(entrada: Any, armado: list[str], tipos: dict[str, str], maximo: int) -> tuple[list[dict], list[dict]]:
    """Separa lo que se puede fusionar de lo que se rechaza, con su motivo. Nunca lanza por una respuesta mala: el resto del paquete se guarda
    (TST-036: cada respuesta es independiente)."""
    if entrada in (None, ""):
        return [], []
    if not isinstance(entrada, list):
        raise DatosInvalidos("`respuestas` debe ser una lista.")
    if len(entrada) > maximo:
        raise DatosInvalidos(f"Un envío admite hasta {maximo} respuestas.", respuestas=len(entrada), maximo=maximo)
    limpias: list[dict] = []
    rechazadas: list[dict] = []
    permitidas = set(armado)
    for r in entrada:
        ref = str(r.get("pregunta_ref") or "").strip() if isinstance(r, dict) else ""
        if not ref:
            rechazadas.append({"pregunta_ref": "", "motivo": "falta pregunta_ref"})
            continue
        if ref not in permitidas:
            rechazadas.append({"pregunta_ref": ref, "motivo": "la pregunta no está en tu examen"})
            continue
        secuencia = _entero(r.get("secuencia"))
        if secuencia is None or secuencia < 1:
            rechazadas.append({"pregunta_ref": ref, "motivo": "la secuencia debe ser un entero ≥ 1"})
            continue
        motivo = forma_valida(tipos.get(ref, ""), r.get("respuesta"))
        if motivo:
            rechazadas.append({"pregunta_ref": ref, "motivo": motivo})
            continue
        limpias.append({"pregunta_ref": ref, "respuesta": dict(r["respuesta"]), "secuencia": secuencia,
                        "capturada_en": _entero(r.get("capturada_en")), "capturada_en_tableta": _entero(r.get("capturada_en_tableta"))})
    return limpias, rechazadas


def _entero(valor) -> int | None:
    if valor is None or isinstance(valor, bool) or valor == "":
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _historial(actual: dict, motivo: str, entra_secuencia: int | None = None) -> dict:
    return {"respuesta": actual.get("respuesta"), "secuencia": actual.get("secuencia"), "sesion_ref": actual.get("sesion_ref", ""),
            "recibida_en": actual.get("recibida_en"), "capturada_en": actual.get("capturada_en"), "motivo": motivo}


def _con_historial(base: dict, extra: dict) -> list[dict]:
    return [*list(base.get("historial") or []), extra][-MAX_HISTORIAL:]


def fusionar(vigentes: list[dict], nuevas: list[dict], *, sesion_ref: str, sesion_orden: int, ahora: int,
             origen: str = cat.DIRECTO) -> tuple[list[dict], ResultadoFusion]:
    """Aplica las respuestas nuevas sobre las vigentes del intento, sin duplicar nada (INV-013, BR-138). Las nuevas se procesan en orden de
    secuencia, de modo que dos cambios de la misma pregunta en un mismo vaciado de cola dejan la última. Devuelve la lista completa (en el orden
    de la primera aparición de cada pregunta) y el detalle de qué pasó con cada una."""
    por_pregunta = {str(r["pregunta_ref"]): dict(r) for r in vigentes}
    orden = [str(r["pregunta_ref"]) for r in vigentes]
    resultado = ResultadoFusion()
    for nueva in sorted(nuevas, key=lambda r: (int(r["secuencia"]), str(r["pregunta_ref"]))):
        ref = str(nueva["pregunta_ref"])
        secuencia = int(nueva["secuencia"])
        entrada = {"pregunta_ref": ref, "respuesta": nueva["respuesta"], "secuencia": secuencia, "sesion_ref": sesion_ref,
                   "sesion_orden": int(sesion_orden), "recibida_en": ahora, "capturada_en": nueva.get("capturada_en") or ahora,
                   "capturada_en_tableta": nueva.get("capturada_en_tableta"), "origen": origen, "veredicto": None, "revision": None,
                   "historial": []}
        actual = por_pregunta.get(ref)
        if actual is None:
            por_pregunta[ref] = entrada
            orden.append(ref)
            resultado.aceptadas.append(ref)
            continue
        misma_sesion = actual.get("sesion_ref", "") == sesion_ref
        vigente_sec = int(actual.get("secuencia") or 0)
        if misma_sesion:
            if secuencia == vigente_sec:
                resultado.duplicadas.append(ref)
                continue
            gana = secuencia > vigente_sec
        else:
            orden_vigente = int(actual.get("sesion_orden") or 0)
            if int(sesion_orden) != orden_vigente:
                gana = int(sesion_orden) > orden_vigente         # BR-138: la sesión más reciente, sin importar el orden de llegada
            else:
                gana = secuencia > vigente_sec                   # mismo instante de apertura: decide la secuencia
        if gana:
            entrada["historial"] = _con_historial(actual, _historial(actual, "reemplazada"))
            por_pregunta[ref] = entrada
            resultado.aceptadas.append(ref)
        else:
            actual["historial"] = _con_historial(actual, _historial(entrada, "superada"))
            por_pregunta[ref] = actual
            resultado.superadas.append(ref)
    return [por_pregunta[r] for r in orden], resultado


def secuencia_maxima(respuestas: list[dict]) -> int:
    return max([int(r.get("secuencia") or 0) for r in respuestas] or [0])


# --------------------------------------------------------------------------------- puntajes (DEC-003, INV-016)

def porcentaje(puntaje: float | None, maximo: float | None) -> float | None:
    """Escala interna de 0 a 100 (DEC-003). Sin máximo no hay porcentaje. Nunca se redondea a entero antes de guardar."""
    if puntaje is None or not maximo:
        return None
    return round(max(0.0, min(100.0, 100.0 * float(puntaje) / float(maximo))), 4)


def puntaje_de(respuesta: dict) -> tuple[float | None, float | None]:
    """(puntaje, máximo) de una respuesta: la revisión del profesor manda sobre el veredicto de la biblioteca. Un veredicto pendiente sin revisión
    no tiene puntaje."""
    revision = respuesta.get("revision")
    veredicto = respuesta.get("veredicto") or {}
    maximo = veredicto.get("puntaje_maximo")
    if revision and revision.get("puntaje") is not None:
        return float(revision["puntaje"]), (float(maximo) if maximo is not None else None)
    if veredicto.get("pendiente") or veredicto.get("puntaje") is None:
        return None, (float(maximo) if maximo is not None else None)
    return float(veredicto["puntaje"]), (float(maximo) if maximo is not None else None)


def totales(respuestas: list[dict], armado: list[str], puntos: dict[str, float]) -> dict:
    """Los totales del intento en la escala interna. Una pregunta del armado sin responder suma CERO sobre su máximo (se omitió); una respuesta
    pendiente de revisión no suma ni resta hasta que el profesor la puntúe (`sin_calificar`)."""
    por_pregunta = {str(r["pregunta_ref"]): r for r in respuestas}
    suma = maximo = 0.0
    sin_calificar = 0
    for ref in armado:
        maximo_ref = float(puntos.get(ref, 1.0))
        r = por_pregunta.get(ref)
        if r is None:
            maximo += maximo_ref                         # omitida: cero sobre su máximo
            continue
        puntaje, max_v = puntaje_de(r)
        if puntaje is None:
            sin_calificar += 1
            continue
        suma += puntaje
        maximo += max_v if max_v is not None else maximo_ref
    calificadas = len(armado) - sin_calificar
    return {"puntaje": round(suma, 4) if calificadas else None, "puntaje_maximo": round(maximo, 4) if calificadas else None,
            "porcentaje": porcentaje(suma, maximo) if calificadas else None, "sin_calificar": sin_calificar,
            "pendientes_de_revision": len(pendientes_de_revision(respuestas))}


def pendientes_de_revision(respuestas: list[dict]) -> list[str]:
    """Las preguntas que sólo un profesor puede puntuar (BR-069): la biblioteca devolvió veredicto, pero marcado para corrección manual (o sin
    puntaje), y nadie lo ha revisado. Una respuesta SIN veredicto no es esto: es una calificación pendiente de la biblioteca."""
    return [str(r["pregunta_ref"]) for r in respuestas
            if r.get("veredicto") and (r["veredicto"].get("requiere_correccion_manual") or r["veredicto"].get("pendiente"))
            and not (r.get("revision") or {}).get("revisada_en")]


def requiere_revision(respuestas: list[dict]) -> bool:
    return bool(pendientes_de_revision(respuestas))


def sin_veredicto(respuestas: list[dict]) -> list[dict]:
    """Las respuestas a las que la biblioteca aún no puso veredicto (nunca se calificaron, o la biblioteca no estaba)."""
    return [r for r in respuestas if r.get("veredicto") is None and not r.get("revision")]

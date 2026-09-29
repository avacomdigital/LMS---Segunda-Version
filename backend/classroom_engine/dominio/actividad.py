"""
La actividad lanzada en clase: cronómetro, aceptación de lo que llega tarde, fusión idempotente de
respuestas y detección de rezagados. Dominio puro: no importa Django ni sabe de HTTP.

Reglas del Documento Maestro que se cumplen aquí:
  - BR-062 / INV-017: ninguna marca temporal con valor académico sale del reloj del dispositivo. La tableta
    manda cuándo capturó (`capturada_en`), ya normalizado con el desfase que aprendió del nodo; el nodo
    conserva ese dato como adicional y decide con SU reloj (`recibida_en`).
  - BR-052 / DEC-019: tras el cierre se siguen aceptando los envíos capturados antes del cierre dentro de la
    ventana de gracia de 15 minutos. Fuera de ella no se descartan en silencio: quedan pendientes de la decisión
    del profesor. Lo capturado DESPUÉS del cierre no existe para la actividad.
  - INV-013 / DEC-023: una respuesta por (intento, pregunta, sesión, secuencia). Reenviar el mismo paquete no
    duplica nada y se acusa recibo igual; entre dos secuencias de la misma sesión prevalece la mayor.
  - DEC-003 / INV-016: el puntaje almacenado vive en la escala interna de 0 a 100.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import sesion as dom

# ------------------------------------------------------------------ cronómetro (CMP-003)

CRONO_EN_CURSO, CRONO_CONGELADO, CRONO_CON_GRACIA, CRONO_VENCIDO = "en_curso", "congelado", "vencido_con_gracia", "vencido"
CRONOMETROS = (CRONO_EN_CURSO, CRONO_CONGELADO, CRONO_CON_GRACIA, CRONO_VENCIDO)


def cronometro(*, abierta_en: int, tiempo_limite_seg: int | None, pausada_ms: int, ahora: int,
               suspendida_en: int | None = None, cerrada_en: int | None = None,
               gracia_ms: int = dom.GRACIA_ENTREGA_MS) -> dict | None:
    """El tiempo de una actividad con límite, contado en el reloj del nodo desde que se lanzó.

    Suspender la clase lo CONGELA (la pausa acumulada `pausada_ms` no cuenta). Al agotarse el tiempo la
    actividad sigue recibiendo lo capturado dentro de la gracia; después, vence. Sin límite no hay cronómetro."""
    if not tiempo_limite_seg:
        return None
    limite_ms = int(tiempo_limite_seg) * 1000
    if cerrada_en is not None:
        transcurrido = max(0, cerrada_en - abierta_en - pausada_ms)
        return {"estado": CRONO_VENCIDO, "limite_ms": limite_ms, "restante_ms": 0, "transcurrido_ms": min(transcurrido, limite_ms)}
    referencia = suspendida_en if suspendida_en is not None else ahora
    transcurrido = max(0, referencia - abierta_en - pausada_ms)
    restante = limite_ms - transcurrido
    if suspendida_en is not None:
        estado = CRONO_CONGELADO
    elif restante > 0:
        estado = CRONO_EN_CURSO
    elif -restante <= gracia_ms:
        estado = CRONO_CON_GRACIA
    else:
        estado = CRONO_VENCIDO
    return {"estado": estado, "limite_ms": limite_ms, "restante_ms": max(0, restante), "transcurrido_ms": min(transcurrido, limite_ms)}


# ----------------------------------------------------------- lo que llega tarde (BR-052, DEC-019)

ACEPTAR, DECIDE_EL_PROFESOR, RECHAZAR = "aceptar", "decide_el_profesor", "rechazar"


def politica_de_recepcion(*, cerrada_en: int | None, capturada_en: int | None, recibida_en: int,
                          gracia_ms: int = dom.GRACIA_ENTREGA_MS) -> str:
    """¿Qué se hace con un envío que llega ahora? Abierta: se acepta. Cerrada: lo capturado antes del cierre se
    acepta dentro de la gracia y, pasada esta, queda para decisión del profesor; lo capturado después se rechaza."""
    if cerrada_en is None:
        return ACEPTAR
    capturada = recibida_en if capturada_en is None else capturada_en
    if capturada > cerrada_en:
        return RECHAZAR
    return ACEPTAR if recibida_en - cerrada_en <= gracia_ms else DECIDE_EL_PROFESOR


# --------------------------------------------------- respuestas de un intento (INV-013, BR-138)

@dataclass
class ResultadoFusion:
    aceptadas: list[str]
    duplicadas: list[str]
    superadas: list[str]     # llegaron con una secuencia menor que la vigente: se conservan solo en la bitácora


def fusionar_respuestas(vigentes: list[dict], nuevas: list[dict], *, sesion_usuario_id: str = "") -> tuple[list[dict], ResultadoFusion]:
    """Aplica las respuestas nuevas sobre las vigentes de un intento, sin duplicar nada.

    Cada elemento lleva `pregunta_ref` y `secuencia` (contador monotónico por intento que la tableta persiste
    antes de enviar). La misma secuencia de la misma pregunta es un reenvío: se acusa y no se toca. Una mayor
    sustituye a la vigente; una menor llega tarde y no la pisa (la más reciente gana con independencia del orden
    de llegada)."""
    por_pregunta = {str(r["pregunta_ref"]): dict(r) for r in vigentes}
    resultado = ResultadoFusion([], [], [])
    for nueva in nuevas:
        ref = str(nueva["pregunta_ref"])
        secuencia = int(nueva.get("secuencia") or 0)
        actual = por_pregunta.get(ref)
        if actual is not None:
            vigente = int(actual.get("secuencia") or 0)
            if secuencia == vigente and (not sesion_usuario_id or actual.get("sesion_usuario_id", "") == sesion_usuario_id):
                resultado.duplicadas.append(ref)
                continue
            if secuencia < vigente:
                resultado.superadas.append(ref)
                continue
        por_pregunta[ref] = {**nueva, "pregunta_ref": ref, "secuencia": secuencia, "sesion_usuario_id": sesion_usuario_id}
        resultado.aceptadas.append(ref)
    orden = [str(r["pregunta_ref"]) for r in vigentes] + [r for r in por_pregunta if r not in {str(v["pregunta_ref"]) for v in vigentes}]
    return [por_pregunta[r] for r in orden], resultado


# ------------------------------------------------------------------------ puntajes (INV-016)

def porcentaje(puntaje: float | None, maximo: float | None) -> float | None:
    """Escala interna de 0 a 100 (DEC-003). Sin máximo no hay porcentaje."""
    if puntaje is None or not maximo:
        return None
    return round(max(0.0, min(100.0, 100.0 * float(puntaje) / float(maximo))), 2)


def totales_del_intento(respuestas: list[dict]) -> tuple[float | None, float | None, int]:
    """(puntaje, máximo, sin_calificar) de las respuestas ya calificadas. Las pendientes de revisión manual
    o de la biblioteca no suman: no se inventa nota (§5 del mapeo)."""
    puntaje = maximo = 0.0
    calificadas = 0
    for r in respuestas:
        v = r.get("veredicto") or {}
        if v.get("pendiente") or v.get("puntaje") is None:
            continue
        puntaje += float(v["puntaje"])
        maximo += float(v.get("puntaje_maximo") or 0)
        calificadas += 1
    sin_calificar = len(respuestas) - calificadas
    return (puntaje if calificadas else None), (maximo if calificadas else None), sin_calificar


# ----------------------------------------------------------------------------- rezagados (CAP-043)

def marcar_rezagados(filas: list[dict]) -> int:
    """Marca `rezagado` en las filas de resultados de una actividad abierta y devuelve cuántos son.

    Rezagado es quien no ha entregado y va al menos un tercio de las preguntas por detrás de la mediana del
    grupo, o no ha empezado cuando alguien ya avanzó. Con menos de dos participantes no hay con quién comparar."""
    if len(filas) < 2:
        for f in filas:
            f["rezagado"] = False
        return 0
    avances = sorted(f["avance"] for f in filas)
    mediana = avances[len(avances) // 2] if len(avances) % 2 else (avances[len(avances) // 2 - 1] + avances[len(avances) // 2]) / 2
    cuantos = 0
    for f in filas:
        pendiente = f["estado"] in (dom.SIN_EMPEZAR, dom.RESPONDIENDO)
        atrasado = pendiente and (f["avance"] + 0.34 <= mediana or (f["avance"] == 0 and mediana > 0))
        f["rezagado"] = bool(atrasado)
        cuantos += 1 if atrasado else 0
    return cuantos

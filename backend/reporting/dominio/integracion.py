"""
El estado de integración de los equipos de un reporte (BR-083, FUN-145): cuántas tabletas del grupo todavía tienen algo por enviar, en el instante del corte.

Lo que el nodo SABE de una tableta es lo que ella avisó o lo que el aula observó; no hay un contador universal de «cola local» (el nodo no la ve). Por eso las señales son
tres, todas observables, y se dicen tal cual (`MOTIVOS_DE_INTEGRACION`):
  · `conexion_perdida`   un participante quedó «reconectando»: su tableta guarda lo que responde y lo enviará al volver (el nodo aún acepta lo de la cola unos minutos tras cerrar)
  · `entrega_pendiente`  un intento de una actividad de clase sigue abierto o pendiente de decisión
  · `cola_de_estudio`    la tableta avisó, al cerrar su sesión de estudio, de que le quedaba trabajo por enviar
Cada señal CADUCA (`hasta_en`): pasado ese instante el nodo ya no espera nada de esa tableta y la señal deja de contar sin que ocurra ningún evento (la caducidad se evalúa al
leer; el hilo del nodo además la limpia de lo guardado). Lo que no se sabe no se inventa: un equipo sin señales cuenta como sincronizado «hasta donde el nodo sabe».
Este archivo no importa Django.
"""
from __future__ import annotations

from collections.abc import Iterable

from . import catalogos as cat
from .metricas import plural


def senal(equipo: str, motivo: str, hasta_en: int) -> dict:
    """Una señal tal como se guarda en las filas derivadas (JSON): el equipo (o `persona:<id>` si el participante no tiene equipo conocido), el motivo y hasta cuándo vale."""
    if motivo not in cat.MOTIVOS_DE_INTEGRACION:
        raise ValueError(f"Motivo de integración fuera del catálogo: {motivo}")
    return {"equipo": str(equipo), "motivo": motivo, "hasta_en": int(hasta_en)}


def vigentes(senales: Iterable[dict], ahora: int) -> list[dict]:
    """Las señales que aún valen en `ahora`, sin repetidas y en un orden fijo (así el mismo dato siempre da el mismo reporte)."""
    vistas = {(s["equipo"], s["motivo"]): s for s in senales if int(s.get("hasta_en") or 0) > ahora}
    return [vistas[k] for k in sorted(vistas)]


_TEXTO_DE_MOTIVO = {
    cat.CONEXION_PERDIDA: ("tableta perdió la conexión y aún no envía lo que guardó", "tabletas perdieron la conexión y aún no envían lo que guardaron"),
    cat.ENTREGA_PENDIENTE: ("tableta tiene una entrega sin confirmar", "tabletas tienen entregas sin confirmar"),
    cat.COLA_DE_ESTUDIO: ("tableta guarda trabajo de estudio por enviar", "tabletas guardan trabajo de estudio por enviar"),
}


def resumir(senales: Iterable[dict], equipos_total: int, ahora: int) -> dict:
    """El bloque `integracion` de un reporte: `estado` (`completa` | `incompleta`), cuántos equipos se consideran, cuántos siguen sin sincronizar y por qué. Es lo que se
    muestra («Datos al 15 oct · 10:42 · 2 tabletas sin sincronizar») y lo que se escribe en el archivo exportado."""
    vivas = vigentes(senales, ahora)
    equipos = sorted({s["equipo"] for s in vivas})
    por_motivo = []
    for motivo in cat.MOTIVOS_DE_INTEGRACION:
        n = len({s["equipo"] for s in vivas if s["motivo"] == motivo})
        if n:
            sing, plur = _TEXTO_DE_MOTIVO[motivo]
            por_motivo.append({"codigo": motivo, "equipos": n, "texto": f"{n} {sing if n == 1 else plur}"})
    total = max(int(equipos_total), len(equipos))
    k = len(equipos)
    if k:
        corto = f"{k} {'tableta sin sincronizar' if k == 1 else 'tabletas sin sincronizar'}"
        largo = f"{k} {'tableta aún no sincroniza' if k == 1 else 'tabletas aún no sincronizan'}"
    else:
        corto = "Todo sincronizado" if total else "Sin tabletas en este reporte"
        largo = ""
    return {"estado": "incompleta" if k else "completa", "equipos": total, "sin_sincronizar": k, "motivos": por_motivo, "texto": corto, "motivo_linea": largo}


def unir(*bloques: Iterable[dict]) -> list[dict]:
    """Junta las señales de varias fuentes (clases, equipos de estudio) en una sola lista, sin repetir."""
    todo: list[dict] = []
    for b in bloques:
        todo.extend(b)
    return todo


def nueva_incompletitud(antes: dict | None, despues: dict) -> bool:
    """¿El reporte pasó de completo a incompleto, o ganó un motivo nuevo? Es lo que dispara `reporte.marcado_incompleto.v1` (una sola vez por cambio, no por cada lectura)."""
    if despues["estado"] != "incompleta":
        return False
    if not antes or antes.get("estado") != "incompleta":
        return True
    previos = {m["codigo"] for m in antes.get("motivos", [])}
    return any(m["codigo"] not in previos for m in despues["motivos"])

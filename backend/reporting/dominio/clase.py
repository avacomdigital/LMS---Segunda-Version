"""
El reporte de UNA clase terminada (CAP-081): de lo que el aula entrega (`detalle_de_sesion`: participantes, actividades lanzadas, intentos con sus cifras) a la fila de cada
alumno y a los totales de la clase. Función PURA: mismo detalle, mismo resultado (la prueba de BR-007 depende de eso).

Cómo se cuenta (todo con `Decimal`, `mitad_arriba`, y sin cifra cuando no hay datos):
  · Entró de verdad quien estuvo conectado, reconectando, salió o fue expulsado; no el que esperaba ni el rechazado. Su presencia es la que tenía ANTES de que el cierre de la clase
    pasara a todos a «salió»: es la que dice si su tableta se quedó sin conexión.
  · Una actividad se RECIBIÓ si el participante estaba entre sus destinatarios al lanzarla; se ENTREGÓ si tiene un intento entregado (cuenta el último entregado).
  · La participación es entregadas ÷ recibidas. Los aciertos son los PUNTOS que el aula ya calificó ÷ los puntos que valían esas respuestas (lo que lo pendiente de revisión
    no suma: no se inventa una nota). Una clase sin actividades no tiene participación ni aciertos: no es un cero.
  · El promedio de la clase es la media simple de los ALUMNOS que tienen cifra.
  · La integración (BR-083): un participante que quedó «reconectando» o un intento que sigue abierto marcan su equipo como «sin sincronizar» mientras dure la gracia del nodo.
Este archivo no importa Django.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from . import catalogos as cat
from . import integracion
from .metricas import CERO, a_decimal, como_numero, porcentaje, promedio, redondear


def _equipo(p: dict) -> str:
    """El equipo de un participante: su dispositivo, o `persona:<id>` cuando la tableta no dio huella (no hay equipo que contar, sí una persona)."""
    return p.get("dispositivo_id") or f"persona:{p['persona_id']}"


def _ultimo_entregado(intentos: list[dict]) -> dict | None:
    entregados = [i for i in intentos if i["estado"] == cat.INTENTO_ENTREGADO]
    return max(entregados, key=lambda i: (i["numero"], i.get("enviado_en") or 0)) if entregados else None


def resumir(detalle: dict, ahora: int) -> dict | None:
    """`{clase, alumnos}` listos para guardar, o None si la sesión aún no terminó (su reporte se arma al cerrarla). `clase` lleva la cabecera, los totales, las señales de
    integración y la huella; no lleva `corte_en` (lo pone quien guarda)."""
    s = detalle["sesion"]
    if s["estado"] not in cat.SESIONES_TERMINADAS or s.get("finalizada_en") is None:
        return None
    finalizada = int(s["finalizada_en"])
    inicio = s.get("iniciada_en") or s.get("creado_en") or finalizada
    hasta_en = finalizada + cat.GRACIA_DE_INTEGRACION_MS
    participantes = [p for p in detalle["participantes"] if (p.get("presencia_al_cerrar") or p["estado"]) in cat.PRESENCIAS_QUE_CUENTAN]
    actividades = detalle["actividades"]
    intentos_por: dict[tuple[str, str], list[dict]] = {}
    for i in detalle["intentos"]:
        intentos_por.setdefault((i["distribucion_id"], i["participante_id"]), []).append(i)

    alumnos: list[dict] = []
    senales: list[dict] = []
    for p in sorted(participantes, key=lambda x: (x["ingreso"], x["persona_id"])):
        presencia = p.get("presencia_al_cerrar") or p["estado"]
        recibidas = [a for a in actividades if p["id"] in a["destinatarios"]]
        entregadas = 0
        puntos = maximos = CERO
        calificadas = aciertos = por_cola = 0
        for a in recibidas:
            propios = intentos_por.get((a["distribucion_id"], p["id"]), [])
            entregado = _ultimo_entregado(propios)
            if entregado is not None:
                entregadas += 1
                if entregado.get("recuperado_de_cola") or entregado.get("origen_envio") == "cola":
                    por_cola += 1
                pt, mx = a_decimal(entregado.get("puntaje")), a_decimal(entregado.get("puntaje_maximo"))
                if pt is not None and mx is not None and mx > 0:
                    puntos, maximos = puntos + pt, maximos + mx
                calificadas += int(entregado.get("calificadas") or 0)
                aciertos += int(entregado.get("aciertos") or 0)
            elif any(i["estado"] in (cat.INTENTO_EN_CURSO, cat.INTENTO_PENDIENTE) for i in propios):
                senales.append(integracion.senal(_equipo(p), cat.ENTREGA_PENDIENTE, hasta_en))
        if presencia == cat.PRESENCIA_RECONECTANDO:
            senales.append(integracion.senal(_equipo(p), cat.CONEXION_PERDIDA, hasta_en))
        salida = p.get("salida")
        alumnos.append({
            "alumno_id": p["persona_id"], "estado": presencia, "dispositivo_id": p.get("dispositivo_id") or "", "ingreso_en": int(p["ingreso"]),
            "salida_en": int(salida) if salida is not None else None, "presente_ms": max(0, int(salida if salida is not None else finalizada) - int(p["ingreso"])),
            "actividades_recibidas": len(recibidas), "actividades_entregadas": entregadas, "calificadas": calificadas, "aciertos": aciertos,
            "puntos": redondear(puntos), "puntos_maximos": redondear(maximos),
            "porcentaje_participacion": porcentaje(entregadas, len(recibidas)) if recibidas else None,
            "porcentaje_aciertos": porcentaje(puntos, maximos) if maximos > 0 else None, "entregas_por_cola": por_cola})

    equipos = {_equipo(p) for p in participantes}
    clase = {
        "sesion_id": s["id"], "grupo_id": s.get("grupo_id") or "", "profesor_id": s.get("profesor_id") or "", "curso_ref": s.get("curso_ref") or "",
        "leccion_ref": s.get("leccion_ref") or "", "iniciada_en": int(inicio) if inicio is not None else None, "finalizada_en": finalizada,
        "duracion_ms": max(0, finalizada - int(inicio)), "participantes": len(alumnos), "actividades": len(actividades), "equipos": len(equipos),
        "promedio_participacion": promedio(a["porcentaje_participacion"] for a in alumnos), "promedio_aciertos": promedio(a["porcentaje_aciertos"] for a in alumnos),
        "senales": integracion.vigentes(senales, ahora)}
    clase["estado_integracion"] = "incompleta" if clase["senales"] else "completa"
    clase["huella"] = huella({**clase, "alumnos": alumnos})
    return {"clase": clase, "alumnos": alumnos}


def _plano(valor):
    if isinstance(valor, Decimal):
        return str(valor)
    raise TypeError(type(valor).__name__)


def huella(datos: dict) -> str:
    """Huella de lo que se guarda (sin el instante del corte): recalcular lo mismo da la misma huella y no escribe nada."""
    return hashlib.sha256(json.dumps(datos, sort_keys=True, default=_plano, ensure_ascii=False).encode("utf-8")).hexdigest()


def fila_para_pantalla(fila: dict) -> dict:
    """Una fila de `m13_clase_alumno` como viaja en el JSON (números, no `Decimal`)."""
    return {
        "alumno_id": fila["alumno_id"], "estado": fila["estado"], "presente_ms": fila["presente_ms"], "actividades_recibidas": fila["actividades_recibidas"],
        "actividades_entregadas": fila["actividades_entregadas"], "calificadas": fila["calificadas"], "aciertos": fila["aciertos"],
        "porcentaje_participacion": como_numero(fila["porcentaje_participacion"]), "porcentaje_aciertos": como_numero(fila["porcentaje_aciertos"]),
        "entregas_por_cola": fila["entregas_por_cola"]}

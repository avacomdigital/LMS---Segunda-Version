"""
La política de licenciamiento COMO DATO (P-13): una sola tabla; nada comercial está cableado en el código.

Los valores de abajo son PROVISIONALES: el Documento Maestro dice «falta el modelo comercial definitivo, que se decide fuera de este documento» (pregunta Q-L1 para el CTO).
Lo que decide cada licencia concreta —vigencia, días de gracia, límites, módulos— viaja DENTRO de ella (`licencia.py`); esta política sólo cubre lo que una licencia no puede
decir: qué pasa sin licencia, cuánto se tolera un reloj raro y cuándo se avisa.
"""
from __future__ import annotations

from dataclasses import dataclass

from .licencia import Limites

HORA_MS = 3_600_000
DIA_MS = 24 * HORA_MS


@dataclass(frozen=True)
class Politica:
    # Un nodo sin licencia (recién instalado o actualizado, P-14) tiene una ventana de evaluación desde su primer arranque con esta versión.
    evaluacion_dias: int = 30
    # Con qué margen se avisa antes de vencer (se emite UN aviso al cruzar cada umbral).
    avisos_dias: tuple[int, ...] = (30, 14, 7, 3, 1)
    # Evaluación: el aviso (`evaluacion` en `avisos[]`) existe durante TODA la ventana, desde el primer día (P-14: «el administrador ve el aviso» al actualizar; si no, en treinta días de
    # evaluación nadie con rol de administración se entera). El tono lo decide el cliente: informativo al principio y de atención con `evaluacion_urgente_dias` o menos.
    evaluacion_aviso_dias: int = 30
    evaluacion_urgente_dias: int = 7
    # El reloj del nodo puede bajar esto respecto de la marca alta sin que se considere un retroceso (ajustes de hora y sincronización normales).
    tolerancia_retroceso_ms: int = 5 * 60_000
    # Un salto del reloj hacia adelante mayor que esto, DENTRO de un proceso en marcha, se toma como sospechoso: no degrada a nadie y espera confirmación.
    salto_adelante_ms: int = 7 * DIA_MS
    # Lo máximo que una sospecha de salto hacia adelante puede aplazar una degradación (para que no sea una palanca para no degradar nunca).
    diferimiento_salto_ms: int = 72 * HORA_MS
    # Histéresis: la condición de degradar tiene que sostenerse tanto tiempo antes de aplicarse.
    histeresis_ms: int = 24 * HORA_MS
    # Cuánto tiempo después de una reactivación (tras una restauración, FUN-194) se muestra el estado «reactivada».
    ventana_reactivada_ms: int = 72 * HORA_MS
    # Una licencia puede empezar hasta tanto tiempo DESPUÉS de hoy y regir ya: quien la emite y este nodo no comparten reloj ni huso horario. Es UNA sola tolerancia para los dos lados:
    # `Instalar` la usa para aceptar el archivo y `calcular` para decidir si ya rige; si fueran distintas, una licencia aceptada dejaría al nodo sin licencia hasta que llegara su `desde`.
    tolerancia_inicio_ms: int = DIA_MS
    # Cupo: a partir de este porcentaje del límite se avisa.
    cupo_aviso_pct: int = 90
    # Límites sin licencia (ventana de evaluación): los de hoy (BR-063 50/100) y topes de equipos y usuarios holgados, para no bloquear a nadie por actualizar.
    limites_evaluacion: Limites = Limites(equipos=100, usuarios=3000, concurrentes_normal=50, concurrentes_pico=100)


POLITICA_PROVISIONAL = Politica()

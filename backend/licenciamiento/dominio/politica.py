"""
La política de licenciamiento COMO DATO (P-13): una sola tabla; nada comercial está cableado en el código.

El Documento Maestro dice «falta el modelo comercial definitivo, que se decide fuera de este documento» (pregunta Q-L1). Decidido por el CTO (2026-10-20): el tamaño máximo de un aula
—60 equipos y 1200 usuarios en una misma pantalla—, la gracia de 30 días corridos exactos (Q-L16, sin histéresis) y que una fecha adelantada no se acepta (Q-L13). Lo demás sigue siendo
PROVISIONAL. Lo que decide cada licencia concreta —vigencia, días de gracia, límites, módulos— viaja DENTRO de ella (`licencia.py`); esta política sólo cubre lo que una licencia no
puede decir: qué pasa sin licencia, cuánto se tolera un reloj raro y cuándo se avisa.
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
    # Un salto del reloj hacia adelante mayor que esto, DENTRO de un proceso en marcha, es una FECHA ADELANTADA (Q-L13): el nodo no la acepta —ni la marca alta, ni el vencimiento, ni
    # ninguna ancla la guardan—, no degrada nada por ella y avisa con un error hasta que la fecha concuerde otra vez (o la administración confirme que la de hoy es la correcta).
    salto_adelante_ms: int = 7 * DIA_MS
    # La fecha «concuerda» con la que el nodo lleva (el instante confiable) si no está más adelantada que esto: con eso se quita el aviso de fecha adelantada (Q-L13).
    tolerancia_fecha_ms: int = DIA_MS
    # Histéresis: la condición de degradar tiene que sostenerse tanto tiempo antes de aplicarse. CERO (Q-L16): la gracia son 30 días corridos EXACTOS y degrada en el instante en que
    # se acaban. No hace falta amortiguar nada: el instante confiable jamás baja (marca alta), así que el estado no puede oscilar en el borde.
    histeresis_ms: int = 0
    # Cuánto tiempo después de una reactivación (tras una restauración, FUN-194) se muestra el estado «reactivada».
    ventana_reactivada_ms: int = 72 * HORA_MS
    # Una licencia puede empezar hasta tanto tiempo DESPUÉS de hoy y regir ya: quien la emite y este nodo no comparten reloj ni huso horario. Es UNA sola tolerancia para los dos lados:
    # `Instalar` la usa para aceptar el archivo y `calcular` para decidir si ya rige; si fueran distintas, una licencia aceptada dejaría al nodo sin licencia hasta que llegara su `desde`.
    tolerancia_inicio_ms: int = DIA_MS
    # Cupo: a partir de este porcentaje del límite se avisa.
    cupo_aviso_pct: int = 90
    # Límites sin licencia (ventana de evaluación): el tamaño máximo de un aula (Q-L1: 60 equipos y 1200 usuarios en una misma pantalla) y la concurrencia de hoy (BR-063 50/100).
    # El cupo sólo cuenta al crear algo nuevo: lo que ya existe sigue funcionando aunque supere estos topes, así que actualizar no bloquea a nadie.
    limites_evaluacion: Limites = Limites(equipos=60, usuarios=1200, concurrentes_normal=50, concurrentes_pico=100)


POLITICA_PROVISIONAL = Politica()

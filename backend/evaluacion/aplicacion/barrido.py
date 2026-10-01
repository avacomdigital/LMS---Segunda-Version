"""
Lo que la evaluación hace SOLA, sin que nadie pulse nada (D-15, INV-010, BR-051). Lo llama el programador del nodo; la corrección no depende de él
(cada caso de uso aplica las mismas transiciones perezosamente), el barrido sólo las persiste aunque nadie pregunte.

  BarrerNodo             cada 5 s: activa lo programado, vence plazos, pausa a quien dejó de dar señal, entrega a quien agotó el tiempo y reintenta las
                         calificaciones que la biblioteca no pudo hacer
  RecuperarTrasReinicio  al arrancar: todo intento abierto pasa a `restaurando` con el reloj congelado en su último latido. NUNCA entrega ni anula
                         (INV-010, INV-018, AC-073)
  ArchivarCerradas       `cerrada` hace más de 24 h → `archivada`
"""
from __future__ import annotations

import logging

from ..dominio import catalogos as cat
from ..dominio import intento as int_dom
from .base import _CasoDeUso
from .motor import Motor

SISTEMA = cat.SISTEMA
log = logging.getLogger("avacom.evaluacion.programador")


class _Nodo(_CasoDeUso):
    def __init__(self, servicios):
        super().__init__(servicios)
        self.motor = Motor(servicios)


class BarrerNodo(_Nodo):
    def ejecutar(self) -> dict:
        ahora = self.s.reloj.ahora_ms()
        resumen = {"asignaciones": 0, "pausados": 0, "entregados": 0, "recalificados": 0, "errores": 0}
        for asignacion_id in self._asignaciones_abiertas():
            try:
                with self.s.uow() as uow:
                    fila = uow.asignaciones.por_id(asignacion_id)
                    if fila is None:
                        continue
                    nueva = self.motor.asegurar_asignacion(uow, fila, ahora)
                    resumen["asignaciones"] += 1 if nueva["estado"] != fila["estado"] else 0
            except Exception:   # noqa: BLE001 — una asignación rara no frena al resto del aula
                log.exception("El barrido no pudo poner al día la asignación %s", asignacion_id)
                resumen["errores"] += 1
        # una transacción por intento Y un fallo aislado por intento: un caso raro no frena al resto del aula (y, como el orden es siempre el mismo,
        # tampoco lo repite en cada ronda con los demás detrás)
        for intento_id, asignacion_id in self._corriendo():
            try:
                with self.s.uow() as uow:
                    intento = uow.intentos.por_id(intento_id)
                    asignacion = uow.asignaciones.por_id(asignacion_id)
                    if intento is None or asignacion is None or intento["estado"] not in cat.CORRIENDO:
                        continue
                    despues = self.motor.asegurar_intento(uow, intento, asignacion, ahora)
                    if despues["estado"] == cat.PAUSADO:
                        resumen["pausados"] += 1
                    elif despues["estado"] in cat.ENTREGADOS:
                        resumen["entregados"] += 1
            except Exception:   # noqa: BLE001
                log.exception("El barrido no pudo poner al día el intento %s", intento_id)
                resumen["errores"] += 1
        for intento_id, asignacion_id in self._con_calificacion_pendiente():
            try:
                with self.s.uow() as uow:
                    intento = uow.intentos.por_id(intento_id)
                    asignacion = uow.asignaciones.por_id(asignacion_id)
                    if intento is None or asignacion is None or not intento["calificacion_pendiente"] or intento["estado"] not in cat.ENTREGADOS:
                        continue
                    despues = self.motor.recalificar(uow, intento, asignacion, ahora)
                    resumen["recalificados"] += 0 if despues["calificacion_pendiente"] else 1
            except Exception:   # noqa: BLE001
                log.exception("El barrido no pudo recalificar el intento %s", intento_id)
                resumen["errores"] += 1
        return resumen

    def _asignaciones_abiertas(self) -> list[str]:
        with self.s.uow() as uow:
            return [a["id"] for a in uow.asignaciones.listar(estados=(cat.PROGRAMADA, cat.ACTIVA, cat.ACTIVA_FUERA_DE_PLAZO))]

    def _corriendo(self) -> list[tuple[str, str]]:
        with self.s.uow() as uow:
            return [(i["id"], i["asignacion_id"]) for i in uow.intentos.en_estados(*cat.CORRIENDO)]

    def _con_calificacion_pendiente(self) -> list[tuple[str, str]]:
        with self.s.uow() as uow:
            return [(i["id"], i["asignacion_id"]) for i in uow.intentos.en_estados(cat.ENTREGADO) if i["calificacion_pendiente"]]


class RecuperarTrasReinicio(_Nodo):
    """BR-051: el nodo se reinició con intentos abiertos. Cada uno pasa a `restaurando` con el reloj congelado en su último latido (el alumno no pierde
    tiempo por la caída) y queda esperando a su tableta; con reactivación del profesor, a que éste lo reactive. Ninguno cambia a `entregado` ni a `anulado`."""

    def ejecutar(self) -> dict:
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            abiertos = [(i["id"], i["asignacion_id"]) for i in uow.intentos.en_estados(*cat.ABIERTOS_PARA_EL_NODO)]
        restaurados = 0
        for intento_id, asignacion_id in abiertos:
            with self.s.uow() as uow:
                intento = uow.intentos.por_id(intento_id)
                asignacion = uow.asignaciones.por_id(asignacion_id)
                if intento is None or asignacion is None or intento["estado"] not in cat.ABIERTOS_PARA_EL_NODO:
                    continue
                cambios = int_dom.restaurar(intento, ahora)
                intento = uow.intentos.actualizar(intento_id, **cambios)
                self.motor.incidente(uow, intento, "reinicio_nodo", ahora, detalle={}, asignacion=asignacion)
                self.motor.publicar(uow, "Intento", intento_id, cat.EV_INTENTO_RESTAURADO, {
                    "intento_id": intento_id, "asignacion_id": asignacion_id, "alumno_id": intento["alumno_id"]}, ahora)
                uow.auditoria.registrar(SISTEMA, "evaluacion.intento.restaurado", "m10_intento_formal", intento_id,
                                        nuevo={"estado": cat.RESTAURANDO}, dispositivo_id=intento.get("dispositivo_id") or None)
                restaurados += 1
        return {"restaurados": restaurados}


class ArchivarCerradas(_Nodo):
    def ejecutar(self) -> int:
        ahora = self.s.reloj.ahora_ms()
        archivadas = 0
        with self.s.uow() as uow:
            for fila in uow.asignaciones.listar(estados=(cat.CERRADA,)):
                nueva = self.motor.asegurar_asignacion(uow, fila, ahora)
                archivadas += 1 if nueva["estado"] == cat.ARCHIVADA else 0
        return archivadas

"""
Un ciclo del vigilante de MOD-016 (lo llama el hilo del proceso ASGI y las pruebas). Sin Django. Lo que hace, en este orden:

  arranque    catalogar los `.avbak` que la base no conoce (CAP-104, restauración), marcar `interrumpido` lo que quedó a medias y REANUDARLO con el mismo identificador (FUN-177),
              aplicar la retención
  programado  el respaldo automático del calendario (FUN-170/171): si toca y no hay clase. Con una clase abierta se APLAZA (nunca se frena una clase por un respaldo)
  verificar   los respaldos que terminaron y no se verificaron (un fallo de verificación se reintenta cada 6 horas, no en cada ciclo) y la prueba periódica de recuperación (CAP-103)

Un ciclo que falla en un paso no impide los demás (R-04).
"""
from __future__ import annotations

import logging

from ..dominio import catalogos as cat
from ..dominio import programacion
from .base import _CasoDeUso
from .motor import Motor
from .puertos import Actor

log = logging.getLogger("avacom.respaldo")

REINTENTO_DE_FALLO_MS = cat.HORA_MS                      # un respaldo automático que falló se reintenta a la hora
REINTENTO_DE_VERIFICACION_MS = 6 * cat.HORA_MS
REANUDAR_HASTA_MS = cat.DIA_MS                           # lo interrumpido hace más de un día no se reanuda: se deja dicho


class Tick(_CasoDeUso):
    def ejecutar(self, origen: str = "tick") -> dict:
        s = self.s
        resultado: dict = {"origen": origen, "pasos": {}}
        with s.bloqueo:
            motor = Motor(s)
            sistema = Actor(id=cat.SISTEMA)
            pasos = []
            if origen == "arranque":
                pasos += [("catalogo", lambda: motor.reconciliar(sistema)), ("reanudar", lambda: self._reanudar(motor, sistema)), ("retencion", lambda: motor._retener(sistema))]
            pasos += [("programado", lambda: self._programado(motor, sistema)), ("verificar", lambda: self._verificar(motor, sistema))]
            for nombre, paso in pasos:
                try:
                    resultado["pasos"][nombre] = paso()
                except Exception:   # noqa: BLE001 — el paso siguiente y el siguiente ciclo siguen
                    log.exception("El ciclo del vigilante de respaldos falló en «%s»", nombre, extra={"evento": "respaldo.vigilante_fallo", "ruta": "bad"})
                    resultado["pasos"][nombre] = "error"
        return resultado

    # ------------------------------------------------------------------------------------------------------------------ reanudar (FUN-177)
    def _reanudar(self, motor: Motor, sistema: Actor) -> list[str]:
        s, ahora = self.s, self.ahora()
        with s.uow(lectura=True) as uow:
            fichas = motor.fichas(uow)
        reanudados = []
        for f in fichas:
            if f["estado"] != cat.E_INCOMPLETO:
                continue
            with s.uow() as uow:
                filas = uow.historial.de_respaldo(f["respaldo_id"])
                if not filas or filas[-1]["tipo"] != cat.H_INTERRUMPIDO:
                    motor._h(uow, f["respaldo_id"], cat.H_INTERRUMPIDO, sistema.id, {"al_arrancar": True})
            if ahora - int(f["creado_en"]) > REANUDAR_HASTA_MS:
                continue
            try:
                motor.respaldar(sistema, f["tipo"], f["disparo"], respaldo_id=f["respaldo_id"])
                reanudados.append(f["respaldo_id"])
            except Exception:   # noqa: BLE001 — queda `fallido` en el historial; no se reintenta en bucle
                log.exception("No se pudo reanudar el respaldo interrumpido", extra={"evento": "respaldo.reanudar_fallo", "ruta": "bad"})
        return reanudados

    # ------------------------------------------------------------------------------------------------------------------ el calendario (FUN-169/170/171)
    def _programado(self, motor: Motor, sistema: Actor) -> str | None:
        s, ahora = self.s, self.ahora()
        with s.uow(lectura=True) as uow:
            fichas = motor.fichas(uow)
            programa = motor.programa(uow)
        if s.vivo.en_marcha():
            return "en_marcha"
        automaticos = [f for f in fichas if f["disparo"] == cat.D_PROGRAMADO and f["creado_en"]]
        buenos = [f["creado_en"] for f in automaticos if f["estado"] not in (cat.E_FALLIDO, cat.E_INCOMPLETO)]
        recientes_malos = [f["creado_en"] for f in automaticos if f["estado"] in (cat.E_FALLIDO, cat.E_INCOMPLETO) and ahora - int(f["creado_en"]) < REINTENTO_DE_FALLO_MS]
        ultimo = max(buenos + recientes_malos, default=None)
        horario = programacion.corresponde(programa, ahora, ultimo, s.reloj.desfase_min())
        if horario is None:
            s.vivo.aplazar(None)
            return None
        if s.aula.sesiones_activas() > 0:
            s.vivo.aplazar(horario)
            return "aplazado_por_clase"
        completos = [f["creado_en"] for f in fichas if f["restaurable"] and f["tipo"] == cat.T_COMPLETO]
        tipo = programacion.tipo_que_toca(programa, max(completos, default=None), ahora)
        try:
            motor.respaldar(sistema, tipo, cat.D_PROGRAMADO)
        finally:
            s.vivo.aplazar(None)
        return tipo

    # ------------------------------------------------------------------------------------------------------------------ verificar (FUN-173, CAP-103)
    def _verificar(self, motor: Motor, sistema: Actor) -> str | None:
        s, ahora = self.s, self.ahora()
        if s.vivo.en_marcha():
            return None
        with s.uow(lectura=True) as uow:
            fichas = motor.fichas(uow)
        for f in sorted((f for f in fichas if f["estado"] == cat.E_NO_VERIFICADO), key=lambda x: x["creado_en"]):
            with s.uow(lectura=True) as uow:
                malas = [r["en"] for r in uow.historial.de_respaldo(f["respaldo_id"]) if r["tipo"] == cat.H_NO_VERIFICADO]
            if malas and ahora - max(malas) < REINTENTO_DE_VERIFICACION_MS:
                continue
            motor.verificar(sistema, f["respaldo_id"])
            return f["respaldo_id"]
        # la prueba periódica de recuperación: el último restaurable se vuelve a probar cada `prueba_de_recuperacion_cada_dias`
        restaurables = [f for f in fichas if f["restaurable"]]
        if restaurables:
            ultimo = max(restaurables, key=lambda f: f["verificado_en"] or 0)
            if ahora - int(ultimo["verificado_en"] or 0) >= s.config.prueba_de_recuperacion_cada_dias * cat.DIA_MS:
                motor.verificar(sistema, ultimo["respaldo_id"])
                return ultimo["respaldo_id"]
        return None

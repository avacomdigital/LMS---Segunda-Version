"""
El arranque y la parada del nodo, en lo que toca a la cola (P-10 en su parte de la Fase 2; la máquina de estados completa, la recuperación y los programadores supervisados son
de la Fase 5):

  1. comprobar el modo de transacción (P-02: sin `IMMEDIATE` el orden de la secuencia no está garantizado → restringido) y `PRAGMA quick_check`;
  2. aplicar las anclas (P-12): si la base trae MENOS que el ancla (o no hay ancla y sí hay eventos) es una RESTAURACIÓN y el contador salta con margen, queda en `m15_arranque`
     y se publica `nodo.recuperacion_completada.v1` con los campos del Maestro; la marca alta del reloj se lee de las anclas y de la base (P-13);
  3. abrir la fila de `m15_arranque` (si la anterior no se cerró, el apagado fue sucio: se deja dicho);
  4. publicar `nodo.servicios_iniciados.v1` (FUN-158).

La parada limpia cierra la fila y escribe el ancla.
"""
from __future__ import annotations

import logging
import os

from ..dominio import catalogos as cat
from ..dominio.anclas import Ancla, al_arrancar, marca_siguiente
from ..dominio.corte import piso_del_contador
from .base import _CasoDeUso
from .publicar import Publicar

log = logging.getLogger("avacom.nodo")


class Arrancar(_CasoDeUso):
    def ejecutar(self) -> dict:
        vivo = self.s.vivo
        cfg = self.s.config
        vivo.arrancado = False
        vivo.cambiar_estado(cat.ARRANCANDO, ())
        salud = self.s.salud.leer()
        vivo.transaccion_inmediata = salud.transaccion_inmediata
        vivo.base_integra = salud.base_integra
        if not salud.transaccion_inmediata:
            log.error("La base no usa transaction_mode=IMMEDIATE: el orden de la secuencia global ya no está garantizado (P-02); el nodo queda restringido",
                      extra={"evento": "nodo.transaccion_no_inmediata", "ruta": "bad"})
        if not salud.base_integra:
            log.error("PRAGMA quick_check no respondió «ok»: el nodo queda restringido", extra={"evento": "nodo.base_danada", "ruta": "bad"})
        ancla = self._leer_ancla()
        reloj = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            vivo.marca_alta = marca_siguiente(marca_siguiente(ancla.marca_alta if ancla else 0, uow.marca_alta.valor()), reloj)
            ahora = vivo.marca_alta
            max_en_base = uow.eventos.ultima_secuencia()
            contador = uow.eventos.contador()
            piso_de_cortes = piso_del_contador(uow.cortes.todos())        # P-05 / D-28: ningún módulo cortado publica por debajo de su corte
            decision = al_arrancar(max(max_en_base, contador), ancla.secuencia if ancla else None, cfg.margen_secuencia)
            restauracion = None
            if decision.restauracion:
                contador = uow.eventos.asegurar_contador(max(decision.contador_minimo, piso_de_cortes))
                restauracion = {"max_en_base": decision.max_en_base, "ancla": decision.ancla, "sin_ancla": decision.sin_ancla, "contador": contador, "detectada_en": ahora}
                log.error("Restauración detectada: la base trae hasta la secuencia %s y el ancla recordaba %s; el contador salta a %s para no repetir ninguna (INV-002)",
                          decision.max_en_base, decision.ancla, contador, extra={"evento": "nodo.restauracion_detectada", "ruta": "bad"})
            elif contador < piso_de_cortes:
                # Una reconstrucción de `m15_evento` (SQLite la hace al alterar una columna) devuelve el AUTOINCREMENT a max(secuencia): si una migración olvidó reponer el piso,
                # el siguiente evento de un módulo cortado saldría por debajo de su corte y la fachada no lo serviría jamás. Se repone aquí, antes de publicar nada.
                contador = uow.eventos.asegurar_contador(piso_de_cortes)
                log.error("El contador de la cola estaba por debajo del corte de un módulo (%s < %s): se repuso al arrancar para que ningún módulo publique bajo su corte (D-28)",
                          decision.max_en_base, piso_de_cortes, extra={"evento": "nodo.contador_bajo_el_corte", "ruta": "bad"})
            vivo.emitida(contador)
            ultimo = uow.arranques.ultimo()
            vivo.apagado_sucio = bool(ultimo and ultimo.get("cerrado_en") is None)
            fila = uow.arranques.abrir(ahora, cfg.version_del_nodo, os.getpid(), max_en_base, ancla.secuencia if ancla else 0, decision.restauracion, contador,
                                       {"apagado_sucio_previo": vivo.apagado_sucio, "transaccion_inmediata": salud.transaccion_inmediata, "base_integra": salud.base_integra,
                                        "sin_ancla": decision.sin_ancla})
            vivo.arranque_id = fila["id"]
            uow.marca_alta.subir(vivo.marca_alta, ahora)
            if restauracion is not None:
                uow.auditoria.registrar(cat.SISTEMA, cat.A_RESTAURACION_DETECTADA, "m15_arranque", str(fila["id"]), nuevo=restauracion)
                if cfg.eventos_tecnicos:
                    Publicar(self.s).ejecutar(uow, modulo=cat.MODULO, agregado_tipo="Arranque", agregado_id=str(fila["id"]), tipo=cat.EV_RECUPERACION_COMPLETADA, actor=cat.SISTEMA, carga={
                        "incidente": "restauracion_detectada", "inicio": ahora, "fin": ahora, "ultima_secuencia_valida": decision.max_en_base, "eventos_reprocesados": 0,
                        "marcas_ajustadas": 0, "contador": contador, "instante": ahora})
            if cfg.eventos_tecnicos:
                Publicar(self.s).ejecutar(uow, modulo=cat.MODULO, agregado_tipo="Arranque", agregado_id=str(fila["id"]), tipo=cat.EV_SERVICIOS_INICIADOS, actor=cat.SISTEMA, carga={
                    "version": cfg.version_del_nodo, "apagado_sucio_previo": vivo.apagado_sucio, "restauracion": decision.restauracion, "instante": ahora})
        vivo.restauracion = restauracion
        vivo.arrancado = True
        self._escribir_ancla(ahora)
        log.info("Nodo arrancado (arranque %s, contador %s, apagado sucio previo: %s)", vivo.arranque_id, contador, vivo.apagado_sucio, extra={"evento": "nodo.arrancado"})
        return {"arranque_id": vivo.arranque_id, "contador": contador, "restauracion": restauracion, "apagado_sucio_previo": vivo.apagado_sucio,
                "transaccion_inmediata": salud.transaccion_inmediata, "base_integra": salud.base_integra}

    def _leer_ancla(self) -> Ancla | None:
        try:
            return self.s.anclas.leer()
        except Exception:   # noqa: BLE001 — un ancla ilegible equivale a ausente (se dice): nunca impide arrancar
            log.exception("No se pudo leer el ancla de la secuencia: se trata como ausente", extra={"evento": "nodo.ancla_ilegible", "ruta": "bad"})
            return None

    def _escribir_ancla(self, ahora: int) -> None:
        try:
            self.s.anclas.escribir(self.s.vivo.ancla_actual(ahora))
        except Exception:   # noqa: BLE001
            log.exception("No se pudo escribir el ancla al arrancar", extra={"evento": "nodo.ancla_fallo", "ruta": "bad"})


class Parar(_CasoDeUso):
    """La parada limpia: cierra la fila del arranque y deja el ancla al día. Idempotente; nunca lanza."""

    def ejecutar(self) -> None:
        vivo = self.s.vivo
        try:
            ahora = self.s.ahora_ms()
            if vivo.arranque_id is not None:
                with self.s.uow() as uow:
                    uow.arranques.cerrar(vivo.arranque_id, ahora)
                    uow.marca_alta.subir(vivo.marca_alta, ahora)
            self.s.anclas.escribir(vivo.ancla_actual(ahora))
            vivo.arrancado = False
            vivo.cambiar_estado(cat.DETENIDO, ())
        except Exception:   # noqa: BLE001
            log.exception("La parada limpia del nodo no se pudo registrar", extra={"evento": "nodo.parada_fallo", "ruta": "bad"})

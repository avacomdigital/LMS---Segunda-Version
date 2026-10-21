"""
El estado del nodo y su salud (FUN-167, P-09, P-16): se evalúa con la lectura de la infraestructura (disco, WAL, modo de transacción, integridad) y el estado de los consumidores,
se recuerda en memoria y SÓLO al cambiar se publica `nodo.salud_evaluada.v1` (BR-130) y, si entra o sale del modo restringido, `nodo.modo_restringido.v1` (extensión) con su asiento.
Lo que `/health/` lee es `resumido()`: nunca lanza y nunca escribe.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from ..dominio import catalogos as cat
from ..dominio.estado import LecturaDeSalud, evaluar
from ..dominio.anclas import leer_reloj
from .base import _CasoDeUso
from .consumidores import EstadoDeCola
from .publicar import Publicar
from .puertos import Actor

log = logging.getLogger("avacom.nodo")


class EstadoDelNodo(_CasoDeUso):
    def lectura(self, consumidores: list[dict] | None = None) -> LecturaDeSalud:
        """La lectura completa: lo que mide la infraestructura más lo que el nodo sabe de sí mismo (arranque, integridad, reloj) y de sus consumidores núcleo."""
        base = self.s.salud.leer()
        vivo = self.s.vivo
        suspendidos = tuple(c["nombre"] for c in (consumidores or []) if c["estado"] == cat.C_SUSPENDIDO and c["nombre"] in self.s.config.consumidores_nucleo)
        reloj = leer_reloj(self.s.reloj.ahora_ms(), vivo.marca_alta, tolerancia_ms=cat.TOLERANCIA_RETROCESO_MS, restringe_ms=self.s.config.umbrales.retroceso_restringe_ms)
        return replace(base, transaccion_inmediata=base.transaccion_inmediata and vivo.transaccion_inmediata, base_integra=base.base_integra and vivo.base_integra,
                       consumidores_nucleo_suspendidos=suspendidos, retroceso_ms=reloj.atras_ms if reloj.retroceso else 0, arrancando=not vivo.arrancado)

    def evaluar(self, *, publicar: bool = True) -> dict:
        """Evalúa y, si cambió, lo publica y lo asienta. Es lo que el programador de la Fase 5 llamará cada minuto; aquí lo llama `/api/nodo/estado/`."""
        ahora = self.s.ahora_ms()
        with self.s.uow(lectura=True) as uow:
            cola = EstadoDeCola(self.s).resumen(uow, ahora)
        lectura = self.lectura(cola["consumidores"])
        resultado = evaluar(lectura, self.s.config.umbrales, estado_previo=self.s.vivo.estado)
        previo = self.s.vivo.estado
        cambio = self.s.vivo.cambiar_estado(resultado.estado, resultado.motivos)
        if cambio and publicar:
            self._anunciar(previo, resultado.estado, resultado.motivos, ahora)
        return self._armar(resultado.estado, resultado.motivos, lectura, cola, ahora)

    def _anunciar(self, previo: str, estado: str, motivos: tuple[str, ...], ahora: int) -> None:
        if not self.s.config.eventos_tecnicos:
            return
        try:
            with self.s.uow() as uow:
                carga = {"estado": estado, "estado_anterior": previo, "motivos": list(motivos), "instante": ahora}
                Publicar(self.s).ejecutar(uow, modulo=cat.MODULO, agregado_tipo="Nodo", agregado_id=cat.MODULO, tipo=cat.EV_SALUD_EVALUADA, carga=carga, actor=cat.SISTEMA)
                if cat.RESTRINGIDO in (previo, estado):
                    Publicar(self.s).ejecutar(uow, modulo=cat.MODULO, agregado_tipo="Nodo", agregado_id=cat.MODULO, tipo=cat.EV_MODO_RESTRINGIDO, carga=carga, actor=cat.SISTEMA)
                    uow.auditoria.registrar(cat.SISTEMA, cat.A_MODO_RESTRINGIDO, "m15_arranque", str(self.s.vivo.arranque_id or ""), nuevo=carga)
            nivel = log.error if estado == cat.RESTRINGIDO else log.info
            nivel("El nodo pasó de %s a %s (%s)", previo, estado, ", ".join(motivos) or "sin motivos", extra={"evento": "nodo.estado_cambiado", "ruta": "bad" if estado == cat.RESTRINGIDO else "happy"})
        except Exception:   # noqa: BLE001 — R-01: anunciar el estado nunca detiene nada
            log.exception("No se pudo publicar el cambio de estado del nodo")

    def _armar(self, estado: str, motivos: tuple[str, ...], lectura: LecturaDeSalud, cola: dict, ahora: int) -> dict:
        vivo = self.s.vivo
        return {
            "estado": estado, "motivos": list(motivos), "restringido": estado == cat.RESTRINGIDO, "version": self.s.config.version_del_nodo,
            "arranque": {"id": vivo.arranque_id, "apagado_sucio_previo": vivo.apagado_sucio, "restauracion": vivo.restauracion},
            "base": {"transaccion_inmediata": lectura.transaccion_inmediata, "integra": lectura.base_integra, "wal_bytes": lectura.wal_bytes},
            "disco": {"libre_bytes": lectura.disco_libre_bytes, "total_bytes": lectura.disco_total_bytes},
            "reloj": {"ahora": ahora, "marca_alta": vivo.marca_alta, "retroceso_ms": lectura.retroceso_ms},
            "cola": {"eventos": cola["eventos"], "ultima_secuencia": cola["ultima_secuencia"], "contador": cola["contador"], "problemas": cola["problemas"],
                     "consumidores": [{"nombre": c["nombre"], "estado": c["estado"], "pendientes": c["pendientes"], "problemas": c["problemas"]} for c in cola["consumidores"]]},
            "purga": cola["purga"], "servidor_en": ahora,
        }

    def ejecutar(self, actor: Actor) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_HEALTH)
        return self.evaluar()

    def resumido(self) -> dict:
        """Lo que `/health/` añade (campo ADITIVO `nodo`): sólo el estado, sin tocar la base ni publicar. Nunca lanza."""
        try:
            vivo = self.s.vivo
            return {"estado": vivo.estado, "motivos": list(vivo.motivos), "restringido": vivo.estado == cat.RESTRINGIDO, "apagado_sucio_previo": vivo.apagado_sucio,
                    "version": self.s.config.version_del_nodo}
        except Exception as error:   # noqa: BLE001
            return {"estado": "desconocido", "motivos": [], "restringido": False, "error": str(error)}

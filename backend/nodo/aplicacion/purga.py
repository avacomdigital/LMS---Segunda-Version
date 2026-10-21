"""
La purga (P-08): construida y APAGADA. Recorre los eventos más antiguos, aplica la regla pura (`dominio/purga.py`: BR-017 con sus cuatro condiciones, BR-018, BR-019, INV-009) y borra
sólo lo elegible, en orden y sin huecos. Sin MOD-016 el respaldo no cubre nada, así que nada es elegible y la cola crece (Q-N3). `AVACOM_NODO_PURGA=0` por defecto ni siquiera mira.
"""
from __future__ import annotations

import logging

from ..dominio import catalogo
from ..dominio import catalogos as cat
from ..dominio import purga as dom
from .base import _CasoDeUso
from .puertos import Actor

log = logging.getLogger("avacom.nodo")


class Purgar(_CasoDeUso):
    def ejecutar(self, actor: Actor | None = None, *, lote: int = 500, forzar: bool = False) -> dict:
        cfg = self.s.config
        if not cfg.purga_habilitada and not forzar:
            return {"habilitada": False, "evaluados": 0, "purgados": 0, "motivos": {}}
        ahora = self.s.ahora_ms()
        motivos: dict[str, int] = {}
        with self.s.uow() as uow:
            # La marca de un consumidor sobre UNA fuente sólo dice algo de los eventos de ESA fuente: a cada evento lo retienen las marcas de los consumidores activos de su módulo.
            marcas_por_fuente: dict[str, list[int]] = {}
            for marca in uow.marcas.todas():
                if marca["activo"]:
                    marcas_por_fuente.setdefault(marca["fuente"], []).append(marca["marca"])
            candidatos: list[dom.Evento] = []
            por_secuencia: dict[int, str] = {}
            for fila in uow.eventos.primeros(lote):
                definicion = catalogo.resolver(fila["tipo"], cfg.ciclo_meses)
                retencion = definicion.retencion_dias if definicion else cat.retencion_dias(cat.CLASE_AUDITORIA)      # lo no catalogado se conserva como lo más largo
                candidatos.append(dom.Evento(fila["secuencia"], fila["creado_en"], retencion, inmutable=(fila["clase"] in cat.INMUTABLES)))
                por_secuencia[fila["secuencia"]] = fila["modulo"]
            comunes = dict(ahora=ahora, respaldo_cubre=self.s.respaldo.cubre, sincronizacion_habilitada=self.s.sincronizacion.habilitada(),
                           reconocida_hasta=self.s.sincronizacion.reconocida_hasta(), retencion_minima_dias=cfg.retencion_minima_dias)
            purgables: list[int] = []
            for evento in candidatos:
                condiciones = dom.evaluar(evento, marcas=marcas_por_fuente.get(por_secuencia[evento.secuencia], []), **comunes)
                for motivo in condiciones.motivos():
                    motivos[motivo] = motivos.get(motivo, 0) + 1
                if condiciones.elegible and len(purgables) == len([c for c in candidatos if c.secuencia < evento.secuencia]):
                    purgables.append(evento.secuencia)          # BR-019: contiguas desde la más baja; la primera no elegible detiene el lote
            borrados = uow.eventos.borrar(purgables) if purgables else 0
            if borrados:
                uow.auditoria.registrar((actor.id if actor else None) or cat.SISTEMA, cat.A_PURGA_EJECUTADA, "m15_evento", str(purgables[-1]),
                                        nuevo={"desde": purgables[0], "hasta": purgables[-1], "borrados": borrados})
                log.info("Purga de la cola: %s eventos (%s–%s)", borrados, purgables[0], purgables[-1], extra={"evento": "nodo.purga"})
        return {"habilitada": True, "evaluados": len(candidatos), "purgados": borrados, "motivos": motivos, "servidor_en": ahora}

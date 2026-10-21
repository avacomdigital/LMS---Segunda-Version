"""
La FACHADA de lectura (P-05) y el CORTE de un módulo. `leer(modulo, desde, limite, tipos)` presenta un flujo continuo por fuente: primero lo que quedó en la tabla antigua del
módulo (por el lector que el propio módulo registró: la cola no lee tablas ajenas, R-09), después las filas de `m15_evento` de ese módulo. Un consumidor con una marca previa al
corte no pierde ni repite nada; uno reconstruido (marca 0) reproduce toda la historia (BR-007).
"""
from __future__ import annotations

import logging

from ..dominio import catalogos as cat
from ..dominio.corte import Corte, contador_tras_corte, fusionar, planear
from ..dominio.errores import ErrorNodo, FueraDeTransaccion, ModuloYaCortado
from .base import _CasoDeUso
from .puertos import UnidadDeTrabajo

log = logging.getLogger("avacom.nodo")


class FuenteLegadaAusente(ErrorNodo):
    """Ese módulo está cortado pero en este proceso nadie registró el lector de su tabla antigua: no se puede servir su historia completa (y no se sirve a medias)."""
    codigo = "fuente_legada_ausente"
    http = 500


class Leer(_CasoDeUso):
    def ejecutar(self, uow: UnidadDeTrabajo, modulo: str, desde: int, limite: int, tipos: tuple[str, ...] | None = None) -> tuple[list[dict], int]:
        plan = planear(desde, limite, uow.cortes.get(modulo))

        def leer_nuevo(d: int, n: int) -> tuple[list[dict], int]:
            return uow.eventos.leer(modulo, d, n, tuple(tipos) if tipos else None)

        if plan.legado is None:
            return leer_nuevo(*plan.nuevo)
        lector = self.s.legados.get(modulo)
        if lector is None:
            raise FuenteLegadaAusente(f"El módulo «{modulo}» está cortado a la cola única pero en este proceso no registró el lector de su cola antigua.", modulo=modulo)
        d, n, tope = plan.legado
        legados, hasta_legado = lector(d, n, tuple(tipos) if tipos else None, tope)
        return fusionar(plan, [_normalizar_legado(e, modulo) for e in legados], hasta_legado, leer_nuevo)


def _normalizar_legado(evento: dict, modulo: str) -> dict:
    """Una fila de la tabla antigua con la forma del sobre: lo que no tenía (actor, aparato, correlación, clase, sensibilidad) queda vacío y se dice que es legado."""
    e = dict(evento)
    e.setdefault("modulo", modulo)
    e.setdefault("evento_id", f"{modulo}:{e.get('secuencia')}")
    e.setdefault("version", _version_de(str(e.get("tipo") or "")))
    for campo in ("actor", "dispositivo_id", "correlacion_id", "clase", "sensibilidad"):
        e.setdefault(campo, "")
    e.setdefault("agregado_tipo", "")
    e.setdefault("agregado_id", "")
    e["legado"] = True
    return e


def _version_de(tipo: str) -> int:
    try:
        return int(tipo.rsplit(".v", 1)[1])
    except (IndexError, ValueError):
        return 1


class Cortar(_CasoDeUso):
    """El corte de un módulo (Fase 3): una fila en `m15_corte` y el salto del contador global, en la MISMA transacción (P-05). De una sola vía."""

    def ejecutar(self, uow: UnidadDeTrabajo, modulo: str, ultima_legada: int, *, actor: str = cat.SISTEMA, version_contrato: int = 1, asentar: bool = True) -> Corte:
        """`asentar=False` es para la migración de datos de un módulo (D-24): la fila del corte y el salto del contador, sin asiento ni evento técnico."""
        if not uow.en_transaccion():
            raise FueraDeTransaccion("El corte de un módulo va en una transacción: la fila del corte y el salto del contador se confirman juntos.", modulo=modulo)
        if uow.cortes.get(modulo) is not None:
            raise ModuloYaCortado(f"El módulo «{modulo}» ya escribe en la cola única.", modulo=modulo)
        ahora = self.s.ahora_ms()
        corte = Corte(modulo, int(ultima_legada or 0), ahora)
        uow.cortes.crear(corte, version_contrato)
        contador = uow.eventos.asegurar_contador(contador_tras_corte(uow.eventos.contador(), corte.ultima_legada))
        self.s.vivo.emitida(contador)
        if not asentar:
            log.info("Módulo %s cortado a la cola única por su migración (última legada %s, contador %s)", modulo, corte.ultima_legada, contador, extra={"evento": "nodo.modulo_cortado"})
            return corte
        uow.auditoria.registrar(actor, cat.A_MODULO_CORTADO, "m15_corte", modulo, nuevo={"ultima_legada": corte.ultima_legada, "contador": contador, "version_contrato": version_contrato})
        if self.s.config.eventos_tecnicos:
            from .publicar import Publicar
            Publicar(self.s).ejecutar(uow, modulo=cat.MODULO, agregado_tipo="Modulo", agregado_id=modulo, tipo=cat.EV_MODULO_CORTADO,
                                      carga={"modulo": modulo, "ultima_legada": corte.ultima_legada, "contador": contador, "instante": ahora}, actor=actor)
        log.info("Módulo %s cortado a la cola única (última legada %s, contador %s)", modulo, corte.ultima_legada, contador, extra={"evento": "nodo.modulo_cortado"})
        return corte

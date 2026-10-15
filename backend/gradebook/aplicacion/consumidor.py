"""
El consumidor de los eventos de MOD-010 (`evaluacion.*.v1`) y la reconstrucción tras una restauración.

  ConsumirEventos          lee la cola de salida de la evaluación desde su marca de lectura, en el orden de su secuencia monótona, y pone al día el libro
  ReproducirYReconstruir   FUN-129 completo: vuelve a leer desde el principio y reconstruye lo derivado (lo que se hace tras restaurar un respaldo)

Reglas, todas comprobadas por pruebas:
  · IDEMPOTENTE. Un evento no lleva el resultado: avisa que algo cambió y el libro vuelve a leer el intento (la fuente de verdad). Procesar dos veces el
    mismo evento no duplica una calificación ni un ajuste (una calificación por intento, una fila de historial por clave de solicitud).
  · ORDEN. Los eventos se aplican por secuencia; la marca sólo avanza dentro de la MISMA transacción que lo que se aplicó.
  · AISLADO. Un evento que no se puede aplicar se registra y se salta: no detiene a los que vienen detrás.
  · SIN RELOJ DEL CLIENTE. Toda marca de tiempo es del nodo.
No es una segunda cola: lee la de MOD-010 por su interfaz y guarda sólo su marca. Cuando exista MOD-015 la marca se llevará allí.
"""
from __future__ import annotations

import logging

from ..dominio import catalogos as cat
from .base import _CasoDeUso
from .derivados import RecalcularResultado, ReconstruirDerivados
from .puertos import Actor
from .registro import Registrador

log = logging.getLogger("avacom.gradebook.consumidor")


class _Aplicador(_CasoDeUso):
    """Aplica UN evento dentro de la transacción del consumidor."""

    def aplicar(self, uow, evento: dict, ahora: int) -> None:
        carga = evento.get("carga") or {}
        tipo = evento["tipo"]
        intento_id, asignacion_id, alumno_id = carga.get("intento_id"), carga.get("asignacion_id"), carga.get("alumno_id")
        if tipo in (cat.EV10_INTENTO_CALIFICADO, cat.EV10_INTENTO_ANULADO) and intento_id:
            Registrador(self.s).registrar(uow, intento_id, ahora, actor_id=cat.SISTEMA, evento_en=carga.get("instante") or evento.get("creado_en"))
        elif asignacion_id and alumno_id:
            asignacion = uow.evaluacion.asignacion(asignacion_id)
            if asignacion is not None:
                RecalcularResultado(self.s).resultado(uow, asignacion, alumno_id, ahora)


class ConsumirEventos(_CasoDeUso):
    def ejecutar(self, limite: int | None = None) -> dict:
        limite = limite or self.s.config.lote_eventos
        # Sin nada nuevo que leer no hace falta el bloqueo de escritura del nodo: se mira primero SIN transacción (cada consulta de un `GET` pasa por aquí).
        with self.s.uow(lectura=True) as uow:
            marca = uow.marcas.get(cat.CONSUMIDOR)
            eventos, nueva = uow.evaluacion.eventos_desde(marca, limite, cat.EVENTOS_CONSUMIDOS)
        if not eventos and nueva <= marca:
            return {"leidos": 0, "procesados": 0, "fallidos": [], "marca_anterior": marca, "marca": marca, "pendientes": False}
        ahora = self.s.reloj.ahora_ms()
        procesados = 0
        fallidos: list[dict] = []
        with self.s.uow() as uow:
            estado = uow.marcas.estado(cat.CONSUMIDOR)           # se vuelve a leer ya con el bloqueo: otro ciclo pudo adelantarse
            marca = estado["secuencia"]
            eventos, nueva = uow.evaluacion.eventos_desde(marca, limite, cat.EVENTOS_CONSUMIDOS)
            aplicador = _Aplicador(self.s)
            primero: dict | None = None
            for evento in eventos:
                try:
                    with uow.aislado():
                        aplicador.aplicar(uow, evento, ahora)
                    procesados += 1
                except Exception as error:      # noqa: BLE001 — un evento que no se puede aplicar no detiene a los demás: se registra y se sigue con ellos
                    fallidos.append({"secuencia": evento["secuencia"], "tipo": evento["tipo"], "error": type(error).__name__})
                    log.exception("El libro no pudo aplicar el evento %s (%s)", evento["secuencia"], evento["tipo"])
                    primero = primero or {"evento": evento, "error": type(error).__name__}
            hasta, fallo_secuencia, fallos = nueva, 0, 0
            if primero is not None:
                # La marca NO pasa de largo del evento que falló: se reintenta en el ciclo siguiente (lo que va detrás ya quedó aplicado y reaplicarlo es idempotente).
                # Sólo tras `MAX_FALLOS_DE_EVENTO` ciclos seguidos se deja atrás, y entonces con un asiento en la bitácora: nunca se pierde en silencio.
                evento = primero["evento"]
                secuencia = evento["secuencia"]
                fallos = (estado["fallos"] if estado["fallo_secuencia"] == secuencia else 0) + 1
                if fallos >= cat.MAX_FALLOS_DE_EVENTO:
                    carga = evento.get("carga") or {}
                    uow.auditoria.registrar(cat.SISTEMA, cat.A_EVENTO_OMITIDO, "m10_evento_salida", str(secuencia), nuevo={
                        "tipo": evento["tipo"], "intento_id": carga.get("intento_id"), "asignacion_id": carga.get("asignacion_id"), "alumno_id": carga.get("alumno_id"),
                        "error": primero["error"], "fallos": fallos})
                    log.error("El libro dejó atrás el evento %s (%s) tras %s fallos seguidos: queda en la bitácora; se registra con POST …/intentos/{id}/registrar/",
                              secuencia, evento["tipo"], fallos)
                    fallo_secuencia, fallos = 0, 0
                else:
                    hasta, fallo_secuencia = max(marca, min(nueva, secuencia - 1)), secuencia
            if hasta > marca or fallo_secuencia != estado["fallo_secuencia"] or fallos != estado["fallos"]:
                uow.marcas.guardar(cat.CONSUMIDOR, cat.FUENTE_EVENTOS, max(marca, hasta), ahora, fallo_secuencia=fallo_secuencia, fallos=fallos)
            return {"leidos": len(eventos), "procesados": procesados, "fallidos": fallidos, "marca_anterior": marca, "marca": max(marca, hasta),
                    "pendientes": len(eventos) >= limite and not fallidos}

    def hasta_vaciar(self, paginas: int = 20) -> dict:
        """Procesa lotes hasta alcanzar la cola (o `paginas` lotes): lo que usa un `GET` para responder con el libro al día. Un lote con fallos se detiene ahí:
        cada ciclo (una consulta, el hilo del nodo) es UN reintento del evento que falló, no cinco seguidos."""
        total = {"leidos": 0, "procesados": 0, "fallidos": []}
        for _ in range(paginas):
            r = self.ejecutar()
            total["leidos"] += r["leidos"]
            total["procesados"] += r["procesados"]
            total["fallidos"] += r["fallidos"]
            total["marca"] = r["marca"]
            if not r["pendientes"]:
                break
        return total


class ReproducirYReconstruir(_CasoDeUso):
    """FUN-129 completo. `reproducir`: la marca vuelve a cero y se reaplican TODOS los eventos de MOD-010 (idempotente: sólo se registra lo que faltaba) antes
    de reconstruir lo derivado. Sin `reproducir`, sólo se reconstruye lo derivado."""

    def ejecutar(self, actor: Actor, *, reproducir: bool = True, desde_el_sistema: bool = False) -> dict:
        ahora = self.s.reloj.ahora_ms()
        reproduccion = None
        if reproducir:
            with self.s.uow() as uow:
                if not desde_el_sistema:
                    self.s.autorizacion.exigir(actor, cat.P_MODE_SET)
                uow.marcas.guardar(cat.CONSUMIDOR, cat.FUENTE_EVENTOS, 0, ahora)
            reproduccion = ConsumirEventos(self.s).hasta_vaciar(paginas=10_000)
        derivados = ReconstruirDerivados(self.s).ejecutar(actor, desde_el_sistema=desde_el_sistema)
        return {"reproduccion": reproduccion, "derivados": derivados, "servidor_en": ahora}

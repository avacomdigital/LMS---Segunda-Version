"""
Lo que MOD-017 hace SOLO, sin que nadie pulse nada: un `tick` que el hilo de `infraestructura/vigilante.py` llama al arrancar y cada pocos segundos (y que las pruebas llaman a mano).

  1. `resultado.json` (FUN-187, P-06): si el Host dejó un resultado, se registra en el historial —aplicado, revertido, reversión fallida o aplazada—, con sus eventos y asientos, y se
     archiva el archivo para no registrarlo dos veces. Al arrancar es lo PRIMERO: así el 503 del inicio de clases se levanta en cuanto el nodo vuelve.
  2. Ventanas (P-08): un paquete `programado` cuya ventana está abierta, sin clase y lejos de la próxima, recibe su orden; si hay clase, se deja una fila `bloqueada` (una por ventana) y
     se espera; vencida la ventana, vuelve a `verificado`.
  3. Plazo de reversión (P-09): un `aplicado` de más de 14 días pasa a `archivado` (el Host borra la instantánea en la Fase 4).
  4. Detección (FUN-179): cada candidato nuevo en una fuente se anuncia UNA vez por proceso con `actualizacion.disponible_detectada.v1` (sin historial: no es un hecho del paquete).

Cada paso va en su propio `try/except`: un fallo se registra y el siguiente tick lo reintenta. Nada de aquí detiene una clase (R-01) ni lanza hacia el programador.
"""
from __future__ import annotations

import logging

from ..dominio import catalogos as cat
from ..dominio import estados, orden as dom_orden, ventana as dom_ventana
from ..dominio.errores import ErrorActualizacion
from .acciones import Aplicar, _Base
from .base import derivado_de
from .puertos import Actor

log = logging.getLogger("avacom.actualizacion")
SISTEMA = Actor(id=cat.SISTEMA, rotulo="Sistema", nivel=3, autenticado=False)


class Tick(_Base):
    def ejecutar(self, origen: str = "tick") -> dict:
        salida = {"origen": origen, "resultado": None, "ordenes": [], "bloqueadas": [], "vencidas": [], "archivados": [], "detectados": [], "errores": []}
        for paso, funcion in (("resultado", self.procesar_resultado), ("ventanas", self.abrir_ventanas), ("archivar", self.archivar), ("detectar", self.detectar)):
            try:
                funcion(salida)
            except Exception as error:   # noqa: BLE001 — el siguiente tick lo reintenta
                log.exception("El vigilante de actualizaciones falló en «%s»", paso, extra={"evento": "actualizacion.vigilante_fallo", "ruta": "bad", "detalle": {"paso": paso}})
                salida["errores"].append({"paso": paso, "error": str(error)[:300]})
        return salida

    # ------------------------------------------------------------------------------------------------------------- 1 · el resultado del Host (FUN-187)
    def procesar_resultado(self, salida: dict) -> None:
        crudo = self.s.almacen.leer_resultado()
        if crudo is None:
            self._recalcular_en_curso()
            return
        resultado = dom_orden.leer_resultado(crudo)
        ahora = self.ahora()
        with self.s.bloqueo, self.s.uow() as uow:
            paquete = uow.paquetes.obtener(resultado.paquete_id)
            filas = uow.historial.de_paquete(resultado.paquete_id) if paquete else []
            d = derivado_de(filas, self.s.config.dias_reversion)
            if paquete is None or not d.en_curso or (d.orden_id and d.orden_id != resultado.orden_id):
                log.error("Un resultado del Host no corresponde a ninguna orden en curso: se archiva sin registrar", extra={"evento": "actualizacion.resultado_huerfano", "ruta": "bad",
                                                                                                                       "detalle": {"orden_id": resultado.orden_id, "paquete_id": resultado.paquete_id}})
                self.s.almacen.archivar_resultado(resultado.orden_id)
                salida["resultado"] = {"orden_id": resultado.orden_id, "registrado": False}
                return
            tipo = estados.resultado_a_fila(resultado.resultado, resultado.accion)
            detalle = {"orden_id": resultado.orden_id, "accion": resultado.accion, "resultado": resultado.resultado, "paso": resultado.paso, "duracion_ms": resultado.duracion_ms,
                       "iniciado_en": resultado.iniciado_en, "terminado_en": resultado.terminado_en, "respaldo": bool(resultado.respaldo), "migraciones": list(resultado.migraciones),
                       "error": resultado.error, "nota": resultado.detalle}
            if tipo == cat.H_APLICADO:
                self._fila(uow, cat.SISTEMA, paquete, cat.H_APLICADO, ahora, detalle, accion_bitacora=cat.A_APLICADO, evento=cat.EV_APLICADA)
                for g in resultado.migraciones:
                    uow.eventos.publicar(cat.AGREGADO_PAQUETE, paquete["paquete_id"], cat.EV_MIGRACION, {"paquete_id": paquete["paquete_id"], "modulo": g["modulo"], "migracion": g["nombre"], "ok": g["ok"]})
            elif tipo == cat.H_REVERTIDO:
                self._fila(uow, cat.SISTEMA, paquete, cat.H_REVERTIDO, ahora, detalle, accion_bitacora=cat.A_REVERTIDO, evento=cat.EV_REVERTIDA)
            elif tipo == cat.H_REVERSION_FALLIDA:
                self._fila(uow, cat.SISTEMA, paquete, cat.H_REVERSION_FALLIDA, ahora, detalle, accion_bitacora=cat.A_REVERSION_FALLIDA, evento=cat.EV_REVERSION_FALLIDA)
            else:
                self._fila(uow, cat.SISTEMA, paquete, cat.H_APLAZADA, ahora, detalle, accion_bitacora=cat.A_APLAZADA, evento=cat.EV_BLOQUEADA)
            uow.eventos.publicar(cat.AGREGADO_PAQUETE, paquete["paquete_id"], cat.EV_RESULTADO, {"paquete_id": paquete["paquete_id"], "serie": paquete["serie"], "resultado": resultado.resultado,
                                                                                                "accion": resultado.accion, "duracion_ms": resultado.duracion_ms, "orden_id": resultado.orden_id})
            self.s.almacen.archivar_resultado(resultado.orden_id)
            self.s.almacen.borrar_staging(paquete["paquete_id"])
            self.s.vivo.marcar_en_curso(False)
        salida["resultado"] = {"orden_id": resultado.orden_id, "paquete_id": paquete["paquete_id"], "tipo": tipo, "registrado": True}

    def _recalcular_en_curso(self) -> None:
        """Sin resultado y sin orden en disco, una fila `aplicando` huérfana (el Host nunca llegó a leer la orden) se cierra como aplazada: el aula no se queda con el 503 para siempre."""
        if self.s.almacen.hay_orden():
            self.s.vivo.marcar_en_curso(True)
            return
        ahora = self.ahora()
        with self.s.bloqueo, self.s.uow() as uow:
            en_curso = False
            for paquete_id, filas in uow.historial.de_todos().items():
                d = derivado_de(filas, self.s.config.dias_reversion)
                if not d.en_curso:
                    continue
                if d.ultima_en is not None and ahora - d.ultima_en < HUERFANA_MS:
                    en_curso = True                       # recién emitida: el Host todavía no la tomó
                    continue
                paquete = uow.paquetes.obtener(paquete_id)
                if paquete is not None:
                    self._fila(uow, cat.SISTEMA, paquete, cat.H_APLAZADA, ahora, {"orden_id": d.orden_id, "accion": d.accion, "motivo": "orden_sin_resultado"}, accion_bitacora=cat.A_APLAZADA)
            self.s.vivo.marcar_en_curso(en_curso)

    # ------------------------------------------------------------------------------------------------------------- 2 · ventanas (P-08)
    def abrir_ventanas(self, salida: dict) -> None:
        ahora = self.ahora()
        with self.s.uow(lectura=True) as uow:
            historial = uow.historial.de_todos()
        programados = [(pid, derivado_de(filas, self.s.config.dias_reversion), filas) for pid, filas in historial.items()]
        programados = [(pid, d, filas) for pid, d, filas in programados if d.estado == cat.PROGRAMADO and d.ventana]
        if not programados:
            return
        if any(derivado_de(f, self.s.config.dias_reversion).en_curso for f in historial.values()) or self.s.almacen.hay_orden():
            return
        sesiones = self.s.aula.sesiones_activas()
        proxima = self.s.aula.proxima_clase_en()
        for pid, d, filas in sorted(programados, key=lambda x: x[1].ventana["desde"]):
            v = dom_ventana.Ventana(d.ventana["desde"], d.ventana["hasta"])
            if v.vencida(ahora):
                with self.s.bloqueo, self.s.uow() as uow:
                    paquete = uow.paquetes.obtener(pid)
                    if paquete:
                        self._fila(uow, cat.SISTEMA, paquete, cat.H_VENTANA_VENCIDA, ahora, {"ventana": v.como_dict()}, accion_bitacora=cat.A_DESPROGRAMADO)
                salida["vencidas"].append(pid)
                continue
            puede, motivo = dom_ventana.decidir(ahora, v, sesiones, proxima, self.s.config.margen_clase_ms)
            if not puede:
                if motivo != dom_ventana.FUERA_DE_VENTANA and not self._ya_bloqueada_en_esta_ventana(filas, v):
                    with self.s.bloqueo, self.s.uow() as uow:
                        paquete = uow.paquetes.obtener(pid)
                        if paquete:
                            self._fila(uow, cat.SISTEMA, paquete, cat.H_BLOQUEADA, ahora, {"sesiones_activas": sesiones, "motivo": motivo, "ventana": v.como_dict()},
                                       accion_bitacora=cat.A_BLOQUEADA, evento=cat.EV_BLOQUEADA)
                    salida["bloqueadas"].append({"paquete_id": pid, "motivo": motivo})
                continue
            try:
                resultado = Aplicar(self.s).ejecutar(SISTEMA, pid, desde_ventana=True)
                salida["ordenes"].append({"paquete_id": pid, "orden_id": resultado["orden"]["orden_id"]})
            except ErrorActualizacion as error:
                log.warning("La ventana de %s se abrió y la orden no se pudo emitir: %s", pid, error.codigo, extra={"evento": "actualizacion.ventana_no_aplicada", "detalle": {"codigo": error.codigo}})
                salida["bloqueadas"].append({"paquete_id": pid, "motivo": error.codigo})
            return                                        # una orden por tick: el aula se para UNA vez

    @staticmethod
    def _ya_bloqueada_en_esta_ventana(filas: list[dict], v: dom_ventana.Ventana) -> bool:
        for fila in reversed(filas):
            if fila["tipo"] == cat.H_PROGRAMADO:
                return False
            if fila["tipo"] == cat.H_BLOQUEADA and (fila.get("detalle") or {}).get("ventana") == v.como_dict():
                return True
        return False

    # ------------------------------------------------------------------------------------------------------------- 3 · plazo de reversión (P-09)
    def archivar(self, salida: dict) -> None:
        ahora = self.ahora()
        with self.s.uow(lectura=True) as uow:
            historial = uow.historial.de_todos()
        vencidos = [pid for pid, filas in historial.items() if derivado_de(filas, self.s.config.dias_reversion).plazo_vencido(ahora)]
        for pid in vencidos:
            with self.s.bloqueo, self.s.uow() as uow:
                paquete = uow.paquetes.obtener(pid)
                filas = uow.historial.de_paquete(pid)
                if paquete and derivado_de(filas, self.s.config.dias_reversion).plazo_vencido(ahora):
                    self._fila(uow, cat.SISTEMA, paquete, cat.H_ARCHIVADO, ahora, {"dias_reversion": self.s.config.dias_reversion}, accion_bitacora=cat.A_ARCHIVADO)
                    salida["archivados"].append(pid)

    # ------------------------------------------------------------------------------------------------------------- 4 · detección (FUN-179)
    def detectar(self, salida: dict) -> None:
        for candidato in self.s.fuentes.candidatos():
            if self.s.vivo.anunciado(candidato.id):
                continue
            with self.s.uow() as uow:
                uow.eventos.publicar(cat.AGREGADO_PAQUETE, f"candidato:{candidato.id}", cat.EV_DISPONIBLE, {"candidato": candidato.id, "origen": candidato.origen, "bytes": candidato.bytes,
                                                                                                           "nombre": candidato.nombre[:cat.MAX_NOMBRE]})
            self.s.vivo.anunciar(candidato.id)
            salida["detectados"].append(candidato.id)


HUERFANA_MS = 10 * cat.MINUTO_MS      # una orden emitida hace menos de esto puede estar esperando a que el Host pare el servicio

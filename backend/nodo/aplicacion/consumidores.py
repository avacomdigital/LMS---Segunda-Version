"""
Los consumidores sobre el registro (P-06, P-07, FUN-160…164): registrar (con la comprobación de compatibilidad del contrato, BR-011/INV-006), el ayudante ÚNICO `aplicar_lote`
que hace lo que hoy repite cada consumidor (leer sin bloqueo, bloquear y releer, aislar cada evento en un savepoint, avanzar la marca en la MISMA transacción, reintentar con espera
creciente y apartar), reproducir desde cero (BR-007) y reprocesar un evento apartado (FUN-164). Nada de aquí interpreta la carga de un evento: la aplica quien la entiende.
"""
from __future__ import annotations

import logging

from ..dominio import catalogo
from ..dominio import catalogos as cat
from ..dominio import reintentos as rt
from ..dominio.estado import estado_del_consumidor, peor
from ..dominio.errores import (ConsumidorDesconocido, ConsumidorSinAplicador, ContratoIncompatible, DatosInvalidos, NoEncontrado, ProblemaYaResuelto, ReprocesoFallido)
from .base import _CasoDeUso
from .leer import Leer
from .publicar import Publicar
from .puertos import Actor, Aplicador, UnidadDeTrabajo

log = logging.getLogger("avacom.nodo.consumidores")

LIMITE_DE_PROBLEMAS = 500


def _tipos_de_fuente(tipos: list[str] | tuple[str, ...], fuente: str) -> tuple[str, ...] | None:
    """
    De los tipos que declaró el consumidor, los que publica esa fuente, y de cada uno TODAS las versiones iguales o superiores a la declarada (BR-011, INV-006: un consumidor escrito
    para la v1 recibe la v2 e ignora lo que desconoce). Sin tipos declarados, todos los de la fuente (None).
    """
    if not tipos:
        return None
    propios: list[str] = []
    for declarado in tipos:
        try:
            nombre = catalogo.analizar(declarado)
        except Exception:   # noqa: BLE001 — un nombre que no se puede analizar sólo coincide consigo mismo
            propios.append(declarado)
            continue
        versiones = [t for t, (m, *_r) in catalogo.TIPOS.items() if m == fuente and t.rsplit(".v", 1)[0] == nombre.base and catalogo.compatible(nombre.version, catalogo.analizar(t).version)]
        propios += versiones or ([declarado] if (catalogo.resolver(declarado) or _Desconocido).modulo == fuente else [])
    return tuple(dict.fromkeys(propios)) or ("__ninguno__",)        # declaró tipos pero ninguno de esta fuente: no lee nada de ella


class _Desconocido:
    modulo = ""


def incompatibles(tipos: list[str] | tuple[str, ...]) -> list[dict]:
    """Los tipos declarados que el nodo no produce en esa versión (INV-006: v N procesa N o superior; una versión que nadie publica, no) o que no existen."""
    salida = []
    for tipo in tipos:
        try:
            nombre = catalogo.analizar(tipo)
        except Exception as error:   # noqa: BLE001
            salida.append({"tipo": tipo, "motivo": "nombre_invalido", "detalle": str(error)})
            continue
        producidas = [catalogo.analizar(t).version for t in catalogo.TIPOS if t.rsplit(".v", 1)[0] == nombre.base]
        if not producidas:
            salida.append({"tipo": tipo, "motivo": "no_producido"})
        elif not catalogo.compatible(nombre.version, max(producidas)):
            salida.append({"tipo": tipo, "motivo": "version_no_producida", "producida": max(producidas)})
    return salida


class RegistrarConsumidor(_CasoDeUso):
    def ejecutar(self, uow: UnidadDeTrabajo, nombre: str, modulo: str, fuentes: list[str] | tuple[str, ...], tipos: list[str] | tuple[str, ...] = (), *, version_contrato: int = 1,
                 limite_rezago: int | None = None, actor: str = cat.SISTEMA, aplicar: Aplicador | None = None) -> dict:
        if not nombre or not modulo or not fuentes:
            raise DatosInvalidos("Un consumidor declara su nombre, su módulo y al menos una fuente.")
        malos = incompatibles(tipos)
        if malos:
            # El asiento lo deja quien llama FUERA de esta transacción (que se revierte con el error): un contrato rechazado también es un hecho.
            raise ContratoIncompatible(f"El consumidor «{nombre}» declara tipos que el nodo no produce en esa versión (INV-007).", consumidor=nombre, tipos=malos,
                                       asiento={"modulo": modulo, "tipos": malos, "version_contrato": version_contrato})
        ahora = self.s.ahora_ms()
        existente = uow.consumidores.get(nombre)
        registro = uow.consumidores.registrar(nombre, modulo, list(fuentes), list(tipos), int(version_contrato), limite_rezago, ahora)
        for fuente in fuentes:
            marca, reintento, reconstruyendose = uow.marcas.estado(nombre, fuente)
            if existente is None or not any(m["fuente"] == fuente for m in uow.marcas.de_consumidor(nombre)):
                uow.marcas.guardar(nombre, fuente, marca, reintento, ahora, reconstruyendose=reconstruyendose)     # BR-007: marca cero para uno nuevo
        if aplicar is not None:
            self.s.aplicadores[nombre] = aplicar
        if existente is None or existente.get("version_contrato") != int(version_contrato) or sorted(existente.get("fuentes") or []) != sorted(fuentes):
            uow.auditoria.registrar(actor, cat.A_CONSUMIDOR_REGISTRADO, "m15_consumidor", nombre, nuevo={"modulo": modulo, "fuentes": list(fuentes), "tipos": len(tipos),
                                                                                                        "version_contrato": version_contrato})
        return registro


class DesregistrarConsumidor(_CasoDeUso):
    """BR-018: un consumidor desinstalado deja de bloquear la purga. Sus marcas se conservan (si vuelve, sigue donde iba)."""

    def ejecutar(self, uow: UnidadDeTrabajo, nombre: str, *, actor: str = cat.SISTEMA) -> bool:
        if uow.consumidores.get(nombre) is None:
            raise ConsumidorDesconocido(f"No hay ningún consumidor «{nombre}».", consumidor=nombre)
        hubo = uow.consumidores.desregistrar(nombre, self.s.ahora_ms())
        self.s.aplicadores.pop(nombre, None)
        if hubo:
            uow.auditoria.registrar(actor, cat.A_CONSUMIDOR_DESREGISTRADO, "m15_consumidor", nombre)
        return hubo


class AplicarLote(_CasoDeUso):
    """UN lote de UNA fuente para UN consumidor. Abre sus propias transacciones (la de lectura sin bloqueo y la de aplicación)."""

    def ejecutar(self, consumidor: str, fuente: str, aplicar: Aplicador | None = None, limite: int | None = None) -> dict:
        cfg = self.s.config
        limite = int(limite or cfg.lote)
        # Sin nada nuevo que leer no hace falta el bloqueo de escritura del nodo: se mira primero SIN transacción (R-08: cada `GET` pasa por aquí).
        with self.s.uow(lectura=True) as uow:
            registro = self._registro(uow, consumidor, fuente)
            aplicar = aplicar or self.s.aplicadores.get(consumidor)
            if aplicar is None:
                raise ConsumidorSinAplicador(f"El consumidor «{consumidor}» no tiene quién aplique sus eventos en este proceso.", consumidor=consumidor)
            tipos = _tipos_de_fuente(registro.get("tipos") or (), fuente)
            marca, reintento, reconstruyendose = uow.marcas.estado(consumidor, fuente)
            ahora = self.s.ahora_ms()
            if reintento.activo and not rt.toca_reintentar(reintento, ahora):
                return self._resultado(marca, marca, 0, 0, [], False, esperando=True, proximo_en=reintento.proximo_en)
            eventos, nueva = Leer(self.s).ejecutar(uow, fuente, marca, limite, tipos)
        if not eventos and nueva <= marca:
            if reconstruyendose:
                with self.s.uow() as uow:
                    uow.marcas.guardar(consumidor, fuente, marca, reintento, ahora, reconstruyendose=False)
                    self._estado(uow, consumidor, ahora)
            return self._resultado(marca, marca, 0, 0, [], False)
        procesados, fallidos = 0, []
        with self.s.uow() as uow:
            marca, reintento, reconstruyendose = uow.marcas.estado(consumidor, fuente)       # se vuelve a leer ya con el bloqueo: otro ciclo pudo adelantarse
            eventos, nueva = Leer(self.s).ejecutar(uow, fuente, marca, limite, tipos)
            primero: tuple[dict, BaseException] | None = None
            for evento in eventos:
                try:
                    with uow.aislado():
                        aplicar(evento)
                    procesados += 1
                    reintento = rt.tras_exito(reintento, evento["secuencia"])
                except Exception as error:      # noqa: BLE001 — un evento que no se puede aplicar no detiene a los demás (aislado): se registra y se sigue
                    fallidos.append({"secuencia": evento["secuencia"], "tipo": evento["tipo"], "error": type(error).__name__})
                    log.exception("El consumidor %s no pudo aplicar el evento %s de %s (%s)", consumidor, evento["secuencia"], fuente, evento["tipo"])
                    primero = primero or (evento, error)
            hasta = nueva
            apartado = None
            if primero is not None:
                evento, error = primero
                descripcion = rt.describir_error(error)
                reintento, apartar = rt.tras_fallo(reintento, evento["secuencia"], ahora, descripcion, max_intentos=cfg.max_intentos, base_ms=cfg.espera_base_ms,
                                                   tope_ms=cfg.espera_tope_ms, jitter=cfg.jitter, rng=self.s.rng)
                if apartar:
                    # FUN-163: a la cola de problemas y la marca AVANZA hasta él (lo que falló detrás se vuelve a leer en el siguiente lote: reaplicar es idempotente, BR-008).
                    apartado = uow.problemas.apartar(consumidor, fuente, evento, cfg.max_intentos, descripcion, ahora)
                    hasta = int(evento["secuencia"])
                    uow.auditoria.registrar(cat.SISTEMA, cat.A_EVENTO_APARTADO, "m15_problema", str(apartado["id"]), nuevo={
                        "consumidor": consumidor, "fuente": fuente, "secuencia": evento["secuencia"], "evento_id": evento.get("evento_id"), "tipo": evento["tipo"],
                        "intentos": cfg.max_intentos, "error": descripcion})
                    log.error("El consumidor %s apartó el evento %s de %s (%s) tras %s intentos: queda en la cola de problemas", consumidor, evento["secuencia"], fuente,
                              evento["tipo"], cfg.max_intentos, extra={"evento": "nodo.evento_apartado", "ruta": "bad"})
                    self._tecnico(uow, cat.EV_EVENTO_APARTADO, "Problema", str(apartado["id"]), {"consumidor": consumidor, "fuente": fuente, "secuencia": evento["secuencia"],
                                                                                                   "tipo": evento["tipo"], "intentos": cfg.max_intentos, "instante": ahora})
                else:
                    # FUN-162: la marca NO pasa de largo del evento que falló; se reintenta cuando pase la espera (lo de detrás ya quedó aplicado y reaplicarlo es idempotente).
                    hasta = max(marca, min(nueva, int(evento["secuencia"]) - 1))
                    self._tecnico(uow, cat.EV_ENTREGA_REINTENTADA, "Consumidor", consumidor, {"consumidor": consumidor, "fuente": fuente, "secuencia": evento["secuencia"],
                                                                                              "tipo": evento["tipo"], "intento": reintento.intentos, "proximo_en": reintento.proximo_en,
                                                                                              "instante": ahora})
            al_dia = hasta >= nueva and not fallidos
            uow.marcas.guardar(consumidor, fuente, max(marca, hasta), reintento, ahora, reconstruyendose=(False if (reconstruyendose and al_dia) else None))
            if procesados and cfg.eventos_tecnicos:
                self._tecnico(uow, cat.EV_MARCA_AVANZADA, "Consumidor", consumidor, {"consumidor": consumidor, "fuente": fuente, "desde": marca, "hasta": max(marca, hasta),
                                                                                     "aplicados": procesados, "fallidos": len(fallidos), "instante": ahora})
            estado = self._estado(uow, consumidor, ahora)
            return self._resultado(marca, max(marca, hasta), len(eventos), procesados, fallidos, len(eventos) >= limite and not fallidos, estado=estado,
                                   apartado=None if apartado is None else apartado["id"])

    def hasta_vaciar(self, consumidor: str, fuente: str, aplicar: Aplicador | None = None, paginas: int = 20, limite: int | None = None) -> dict:
        """Lotes hasta alcanzar la cola (o `paginas` lotes). Un lote con fallos se detiene ahí: cada ciclo es UN reintento, no cinco seguidos."""
        total = {"leidos": 0, "procesados": 0, "fallidos": [], "marca": 0, "pendientes": False}
        for _ in range(int(paginas)):
            r = self.ejecutar(consumidor, fuente, aplicar, limite)
            total["leidos"] += r["leidos"]
            total["procesados"] += r["procesados"]
            total["fallidos"] += r["fallidos"]
            total["marca"] = r["marca"]
            total["pendientes"] = r["pendientes"]
            if not r["pendientes"]:
                break
        return total

    # ------------------------------------------------------------------------------------------------------------------------------ ayudas
    @staticmethod
    def _registro(uow: UnidadDeTrabajo, consumidor: str, fuente: str) -> dict:
        registro = uow.consumidores.get(consumidor)
        if registro is None or not registro.get("activo", True):
            raise ConsumidorDesconocido(f"No hay ningún consumidor «{consumidor}» registrado.", consumidor=consumidor)
        if fuente not in (registro.get("fuentes") or []):
            raise DatosInvalidos(f"El consumidor «{consumidor}» no declaró la fuente «{fuente}».", consumidor=consumidor, fuente=fuente)
        return registro

    def _tecnico(self, uow: UnidadDeTrabajo, tipo: str, agregado_tipo: str, agregado_id: str, carga: dict) -> None:
        """Los eventos `nodo.*` del transporte (P-15): en la misma transacción, agregados por lote. Un evento nodo.* jamás provoca otro."""
        if not self.s.config.eventos_tecnicos:
            return
        Publicar(self.s).ejecutar(uow, modulo=cat.MODULO, agregado_tipo=agregado_tipo, agregado_id=agregado_id, tipo=tipo, carga=carga, actor=cat.SISTEMA)

    def _estado(self, uow: UnidadDeTrabajo, consumidor: str, ahora: int) -> str:
        estado = estado_global(uow, consumidor, self.s.config.rezago_limite)
        if uow.consumidores.actualizar_estado(consumidor, estado, ahora) and estado == cat.C_SUSPENDIDO:
            log.error("El consumidor %s quedó suspendido por rezago: supera el límite de %s eventos sin aplicar (BR-018)", consumidor, self.s.config.rezago_limite,
                      extra={"evento": "nodo.consumidor_suspendido", "ruta": "bad"})
            self._tecnico(uow, cat.EV_CONSUMIDOR_REZAGADO, "Consumidor", consumidor, {"consumidor": consumidor, "estado": estado, "limite": self.s.config.rezago_limite, "instante": ahora})
        return estado

    @staticmethod
    def _resultado(marca_anterior: int, marca: int, leidos: int, procesados: int, fallidos: list, pendientes: bool, **extra) -> dict:
        return {"leidos": leidos, "procesados": procesados, "fallidos": fallidos, "marca_anterior": marca_anterior, "marca": marca, "pendientes": pendientes, **extra}


def estado_global(uow: UnidadDeTrabajo, consumidor: str, limite_rezago: int) -> str:
    """El estado de un consumidor: el peor de sus fuentes."""
    registro = uow.consumidores.get(consumidor) or {}
    limite = registro.get("limite_rezago") or limite_rezago
    estados = []
    for m in uow.marcas.de_consumidor(consumidor):
        ultima = uow.eventos.ultima_secuencia(m["fuente"])
        estados.append(estado_del_consumidor(m["marca"], max(ultima, _hasta_legado(uow, m["fuente"])), reconstruyendose=m["reconstruyendose"], limite_rezago=limite)[0])
    return peor(estados)


def _hasta_legado(uow: UnidadDeTrabajo, fuente: str) -> int:
    corte = uow.cortes.get(fuente)
    return corte.ultima_legada if corte else 0


class Reproducir(_CasoDeUso):
    """BR-007 / FUN-164: la marca vuelve a cero (de una fuente o de todas) y el consumidor queda `reconstruyendose` hasta alcanzar la cola. Exige `node.queue.replay` y deja asiento."""

    def ejecutar(self, actor: Actor, consumidor: str, fuente: str | None = None, *, desde_el_sistema: bool = False) -> dict:
        if not desde_el_sistema:
            self.s.autorizacion.exigir(actor, cat.P_REPLAY)
        ahora = self.s.ahora_ms()
        with self.s.uow() as uow:
            registro = uow.consumidores.get(consumidor)
            if registro is None:
                raise ConsumidorDesconocido(f"No hay ningún consumidor «{consumidor}».", consumidor=consumidor)
            if fuente and fuente not in (registro.get("fuentes") or []):
                raise DatosInvalidos(f"El consumidor «{consumidor}» no declaró la fuente «{fuente}».", consumidor=consumidor, fuente=fuente)
            marcas = uow.marcas.reiniciar(consumidor, fuente, ahora)
            uow.consumidores.actualizar_estado(consumidor, cat.C_RECONSTRUYENDOSE, ahora)
            uow.auditoria.registrar(actor.id or cat.SISTEMA, cat.A_CONSUMIDOR_REPRODUCIDO, "m15_marca_lectura", consumidor, nuevo={"fuente": fuente or "todas", "marcas": marcas})
        return {"consumidor": consumidor, "fuente": fuente, "marcas_reiniciadas": marcas, "estado": cat.C_RECONSTRUYENDOSE, "servidor_en": ahora}


class Reprocesar(_CasoDeUso):
    """FUN-164: vuelve a aplicar UN evento apartado, de forma idempotente, con el `aplicar` del consumidor que corre en este proceso. Exige `node.queue.replay` y deja asiento."""

    def ejecutar(self, actor: Actor, problema_id: int) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_REPLAY)
        ahora = self.s.ahora_ms()
        por = actor.id or cat.SISTEMA
        with self.s.uow(lectura=True) as uow:
            problema = uow.problemas.get(int(problema_id))
        if problema is None:
            raise NoEncontrado("No existe ese evento apartado.", problema_id=problema_id)
        if problema["estado"] != cat.PR_APARTADO:
            raise ProblemaYaResuelto("Ese evento apartado ya fue reprocesado.", problema_id=problema_id, estado=problema["estado"])
        aplicar = self.s.aplicadores.get(problema["consumidor"])
        if aplicar is None:
            raise ConsumidorSinAplicador(f"El consumidor «{problema['consumidor']}» no corre en este proceso: no hay quién aplique el evento.", consumidor=problema["consumidor"])
        try:
            with self.s.uow() as uow:
                evento = self._evento(uow, problema)
                with uow.aislado():
                    aplicar(evento)
                resuelto = uow.problemas.resolver(int(problema_id), cat.PR_REPROCESADO, ahora, por)
                uow.auditoria.registrar(por, cat.A_EVENTO_REPROCESADO, "m15_problema", str(problema_id), nuevo={
                    "consumidor": problema["consumidor"], "fuente": problema["fuente"], "secuencia": problema["secuencia"], "tipo": problema["tipo"]})
                if self.s.config.eventos_tecnicos:
                    Publicar(self.s).ejecutar(uow, modulo=cat.MODULO, agregado_tipo="Problema", agregado_id=str(problema_id), tipo=cat.EV_EVENTO_REPROCESADO, actor=por, carga={
                        "consumidor": problema["consumidor"], "fuente": problema["fuente"], "secuencia": problema["secuencia"], "tipo": problema["tipo"], "instante": ahora})
        except ReprocesoFallido:
            raise
        except Exception as error:      # noqa: BLE001 — vuelve a fallar: sigue apartado, con un intento más y el error nuevo (saneado)
            descripcion = rt.describir_error(error)
            log.exception("El reproceso del problema %s volvió a fallar", problema_id)
            with self.s.uow() as uow:
                uow.problemas.fallo_de_reproceso(int(problema_id), descripcion, ahora)
                uow.auditoria.registrar(por, cat.A_REPROCESO_FALLIDO, "m15_problema", str(problema_id), nuevo={"consumidor": problema["consumidor"], "error": descripcion})
            raise ReprocesoFallido("El evento volvió a fallar al reprocesarlo: sigue apartado.", problema_id=problema_id, error=descripcion)
        return {**resuelto, "servidor_en": ahora}

    def _evento(self, uow: UnidadDeTrabajo, problema: dict) -> dict:
        """El evento apartado, tal como lo vio el consumidor: por la fachada (puede ser una fila de la cola antigua de un módulo cortado)."""
        eventos, _ = Leer(self.s).ejecutar(uow, problema["fuente"], int(problema["secuencia"]) - 1, 1, None)
        evento = next((e for e in eventos if int(e["secuencia"]) == int(problema["secuencia"])), None)
        if evento is None:
            raise NoEncontrado("El evento de ese problema ya no está en la cola.", secuencia=problema["secuencia"])
        return evento


class EstadoDeCola(_CasoDeUso):
    """CAP-097: por consumidor, cada fuente con su marca, lo último publicado, el rezago y el estado; más los problemas abiertos. SIN carga útil (R-13)."""

    def ejecutar(self, actor: Actor, *, desde_el_sistema: bool = False) -> dict:
        if not desde_el_sistema:
            self.s.autorizacion.exigir(actor, cat.P_READ)
        ahora = self.s.ahora_ms()
        with self.s.uow(lectura=True) as uow:
            return self.resumen(uow, ahora)

    def resumen(self, uow: UnidadDeTrabajo, ahora: int) -> dict:
        cfg = self.s.config
        consumidores = []
        for c in uow.consumidores.todos(activos=True):
            fuentes = []
            limite = c.get("limite_rezago") or cfg.rezago_limite
            for m in uow.marcas.de_consumidor(c["nombre"]):
                ultima = max(uow.eventos.ultima_secuencia(m["fuente"]), _hasta_legado(uow, m["fuente"]))
                estado, rezago = estado_del_consumidor(m["marca"], ultima, reconstruyendose=m["reconstruyendose"], limite_rezago=limite)
                fuentes.append({"fuente": m["fuente"], "marca": m["marca"], "ultima_secuencia": ultima, "pendientes": rezago, "estado": estado,
                                "actualizada_en": m["actualizada_en"], "reintento": {"secuencia": m["fallo_secuencia"], "intentos": m["fallos"], "proximo_en": m["proximo_intento_en"],
                                                                                     "error": m["ultimo_error"]} if m["fallo_secuencia"] else None})
            consumidores.append({"nombre": c["nombre"], "modulo": c["modulo"], "version_contrato": c["version_contrato"], "estado": peor([f["estado"] for f in fuentes]),
                                 "fuentes": fuentes, "pendientes": sum(f["pendientes"] for f in fuentes), "problemas": uow.problemas.contar(c["nombre"], cat.PR_APARTADO),
                                 "registrado_en": c["registrado_en"], "actualizado_en": c["actualizado_en"]})
        return {"consumidores": consumidores, "eventos": uow.eventos.contar(), "ultima_secuencia": uow.eventos.ultima_secuencia(), "contador": uow.eventos.contador(),
                "problemas": uow.problemas.contar(None, cat.PR_APARTADO), "cortes": [{"modulo": k.modulo, "ultima_legada": k.ultima_legada, "cortado_en": k.cortado_en} for k in uow.cortes.todos()],
                "purga": {"habilitada": cfg.purga_habilitada, "respaldo_verificado_hasta": self.s.respaldo.verificado_hasta()}, "servidor_en": ahora}


class ListarProblemas(_CasoDeUso):
    def ejecutar(self, actor: Actor, consumidor: str | None = None, estado: str | None = None, limite: int = 100) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_READ)
        if estado and estado not in cat.ESTADOS_PROBLEMA:
            raise DatosInvalidos("Ese estado de problema no existe.", estado=estado)
        limite = max(1, min(int(limite or 100), LIMITE_DE_PROBLEMAS))
        ahora = self.s.ahora_ms()
        with self.s.uow(lectura=True) as uow:
            problemas = uow.problemas.listar(consumidor, estado or cat.PR_APARTADO, limite)
            return {"problemas": problemas, "total": uow.problemas.contar(consumidor, estado or cat.PR_APARTADO), "servidor_en": ahora}



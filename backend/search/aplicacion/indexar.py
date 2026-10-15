"""
La indexación de Search: mantener el índice al día con lo que cambia en los módulos propietarios y reconstruirlo cuando hace falta.

  Sincronizar     FUN-209 · FUN-214 · FUN-217  lee la cola de salida de cada módulo desde SU marca, vuelve a leer cada entidad que cambió (el evento avisa que algo cambió;
                  la verdad se lee del dueño) y la indexa, la actualiza o la purga. Incremental, idempotente y aislado.
  Reconstruir     FUN-215 · CAP-128            vacía el índice y lo vuelve a construir desde los módulos propietarios (tras restaurar un respaldo, o la primera vez).
  Purgar          FUN-217                      quita del índice lo que el dueño ya no tiene (lo usa la búsqueda cuando lo descubre al verificar).

Reglas, todas con prueba:
  · IDEMPOTENTE. Un evento repetido no duplica nada: indexar una entidad cuya huella no cambió no escribe ni emite evento.
  · ORDEN Y ATOMICIDAD. La marca sólo avanza en la MISMA transacción que lo que se aplicó (un fallo a medias no pierde ni repite).
  · AISLADO. Una entidad que no se puede indexar no detiene a las demás: se reintenta en el ciclo siguiente y, tras `MAX_FALLOS_DE_EVENTO`, se deja atrás CON un asiento.
  · NO ES FUENTE DE VERDAD. Nada de esto escribe en los módulos propietarios.
"""
from __future__ import annotations

import logging

from ..dominio import catalogos as cat
from ..dominio.errores import ErrorBusqueda, ReconstruccionEnCurso, SesionActiva
from .base import _CasoDeUso
from .puertos import Actor

log = logging.getLogger("avacom.search.indexar")


def _aplicar(uow, fuente, entidad_id: str, ahora: int) -> str:
    """Pone el índice como está la entidad AHORA en su módulo. Devuelve `nuevo` | `actualizado` | `igual` | `purgado` | `ausente`."""
    documento = fuente.documento(entidad_id)
    if documento is None:
        return "purgado" if uow.indice.quitar(fuente.tipo, entidad_id) else "ausente"
    resultado = uow.indice.guardar(documento, ahora)
    if resultado in ("nuevo", "actualizado"):
        uow.outbox.publicar(cat.EV_ENTIDAD_INDEXADA, f"{fuente.tipo}:{entidad_id}", {
            "tipo": fuente.tipo, "entidad_id": entidad_id, "resultado": resultado, "instante": ahora})
    return resultado


class Sincronizar(_CasoDeUso):
    def ejecutar(self, limite: int | None = None) -> dict:
        """UN ciclo sobre todas las fuentes. `pendientes` es True si alguna tiene más eventos que un lote."""
        limite = limite or self.s.config.lote_eventos
        # Sin índice (la primera vez) o con una reconstrucción abandonada, no hay marcas que seguir: se construye antes. Si otra ya está en marcha, se espera.
        with self.s.uow(lectura=True) as uow:
            estado = uow.estado.leer()
        if estado["estado"] in (cat.CONSTRUYENDOSE, cat.RECONSTRUYENDOSE):
            desde = estado.get("reconstruccion_desde")
            if desde and self.s.reloj.ahora_ms() - desde < cat.RECONSTRUCCION_ABANDONADA_MS:
                return {"leidos": 0, "indexados": 0, "purgados": 0, "fallidos": [], "pendientes": False, "omitido": estado["estado"]}
            try:
                Reconstruir(self.s).ejecutar(Actor(id=cat.SISTEMA), desde_el_sistema=True, inicial=estado["estado"] == cat.CONSTRUYENDOSE)
            except ErrorBusqueda as error:        # p. ej. hay una clase en curso: se vuelve a intentar en el ciclo siguiente
                return {"leidos": 0, "indexados": 0, "purgados": 0, "fallidos": [], "pendientes": False, "omitido": error.codigo}
        total = {"leidos": 0, "indexados": 0, "purgados": 0, "fallidos": [], "pendientes": False}
        for fuente in self.s.fuentes.values():
            r = self._fuente(fuente, limite)
            total["leidos"] += r["leidos"]
            total["indexados"] += r["indexados"]
            total["purgados"] += r["purgados"]
            total["fallidos"] += r["fallidos"]
            total["pendientes"] = total["pendientes"] or r["pendientes"]
        return total

    def _fuente(self, fuente, limite: int) -> dict:
        vacio = {"leidos": 0, "indexados": 0, "purgados": 0, "fallidos": [], "pendientes": False}
        # Sin nada nuevo no hace falta el bloqueo de escritura del nodo: se mira primero SIN transacción de escritura.
        with self.s.uow(lectura=True) as uow:
            marca = uow.marcas.estado(fuente.fuente)["secuencia"]
        try:
            eventos, nueva = fuente.eventos_desde(marca, limite)
        except Exception as error:   # noqa: BLE001 — la cola de un módulo que no contesta no detiene a los demás
            self._anotar_error(fuente, error)
            return {**vacio, "fallidos": [{"fuente": fuente.fuente, "error": type(error).__name__}]}
        if not eventos and nueva <= marca:
            self._limpiar_error()
            return vacio
        ahora = self.s.reloj.ahora_ms()
        indexados = purgados = 0
        fallidos: list[dict] = []
        with self.s.uow() as uow:
            estado = uow.marcas.estado(fuente.fuente)          # se vuelve a leer ya con el bloqueo: otro ciclo pudo adelantarse
            marca = estado["secuencia"]
            eventos, nueva = fuente.eventos_desde(marca, limite)
            vistos: set[str] = set()
            primero: dict | None = None
            for evento in eventos:
                entidad_id = str(evento["entidad_id"])
                if entidad_id in vistos:                      # varios eventos de la misma entidad: se lee UNA vez (el estado actual es el mismo)
                    continue
                vistos.add(entidad_id)
                try:
                    with uow.aislado():
                        resultado = _aplicar(uow, fuente, entidad_id, ahora)
                except Exception as error:   # noqa: BLE001 — una entidad que no se puede indexar no detiene a las demás
                    fallidos.append({"secuencia": evento["secuencia"], "entidad_id": entidad_id, "error": type(error).__name__})
                    log.exception("No se pudo indexar %s %s (evento %s)", fuente.tipo, entidad_id, evento["secuencia"])
                    primero = primero or {"evento": evento, "error": type(error).__name__}
                    continue
                if resultado in ("nuevo", "actualizado"):
                    indexados += 1
                elif resultado == "purgado":
                    purgados += 1
            hasta, fallo_secuencia, fallos = nueva, 0, 0
            if primero is not None:
                # La marca NO pasa de largo del evento que falló: se reintenta en el ciclo siguiente. Sólo tras `MAX_FALLOS_DE_EVENTO` ciclos seguidos se deja atrás, y
                # entonces con un asiento en la bitácora: nunca se pierde en silencio.
                secuencia = primero["evento"]["secuencia"]
                fallos = (estado["fallos"] if estado["fallo_secuencia"] == secuencia else 0) + 1
                if fallos >= cat.MAX_FALLOS_DE_EVENTO:
                    uow.auditoria.registrar(cat.SISTEMA, cat.A_EVENTO_OMITIDO, "m21_documento", f"{fuente.tipo}:{primero['evento']['entidad_id']}",
                                            nuevo={"fuente": fuente.fuente, "secuencia": secuencia, "error": primero["error"], "fallos": fallos})
                    log.error("Search dejó atrás el evento %s de %s tras %s fallos seguidos: queda en la bitácora; se corrige con una reconstrucción", secuencia,
                              fuente.fuente, fallos)
                    fallo_secuencia, fallos = 0, 0
                else:
                    hasta, fallo_secuencia = max(marca, min(nueva, secuencia - 1)), secuencia
            if purgados:
                uow.outbox.publicar(cat.EV_ENTRADAS_PURGADAS, fuente.tipo, {"tipo": fuente.tipo, "entradas": purgados, "causa": "evento", "instante": ahora})
            if hasta > marca or fallo_secuencia != estado["fallo_secuencia"] or fallos != estado["fallos"]:
                uow.marcas.guardar(fuente.fuente, max(marca, hasta), ahora, fallo_secuencia=fallo_secuencia, fallos=fallos)
            if eventos:
                uow.outbox.publicar(cat.EV_REINDEXACION_INCREMENTAL, fuente.fuente, {
                    "fuente": fuente.fuente, "tipo": fuente.tipo, "eventos": len(eventos), "indexadas": indexados, "purgadas": purgados,
                    "marca_anterior": marca, "marca": max(marca, hasta), "instante": ahora})
            uow.estado.escribir(sincronizado_en=ahora, **({} if fallidos else {"error": "", "error_en": None}))
            if fallidos:
                uow.estado.escribir(error=fallidos[0]["error"], error_en=ahora)
            return {"leidos": len(eventos), "indexados": indexados, "purgados": purgados, "fallidos": fallidos,
                    "pendientes": len(eventos) >= limite and not fallidos}

    def _anotar_error(self, fuente, error: Exception) -> None:
        log.warning("La cola de %s no contestó: %s", fuente.fuente, type(error).__name__)
        try:
            with self.s.uow() as uow:
                uow.estado.escribir(error=f"{fuente.fuente}: {type(error).__name__}", error_en=self.s.reloj.ahora_ms())
        except Exception:   # noqa: BLE001
            log.exception("No se pudo anotar el fallo de la cola de %s", fuente.fuente)

    def _limpiar_error(self) -> None:
        with self.s.uow(lectura=True) as uow:
            estado = uow.estado.leer()
        if estado.get("error"):
            with self.s.uow() as uow:
                uow.estado.escribir(error="", error_en=None, sincronizado_en=self.s.reloj.ahora_ms())

    def hasta_vaciar(self, paginas: int = 20) -> dict:
        """Procesa lotes hasta alcanzar la cola (o `paginas` lotes): lo que usa una consulta para responder con el índice al día. Un lote con fallos se detiene ahí."""
        total = {"leidos": 0, "indexados": 0, "purgados": 0, "fallidos": []}
        for _ in range(paginas):
            r = self.ejecutar()
            total["leidos"] += r["leidos"]
            total["indexados"] += r["indexados"]
            total["purgados"] += r["purgados"]
            total["fallidos"] += r["fallidos"]
            if not r["pendientes"]:
                break
        return total


class Reconstruir(_CasoDeUso):
    """FUN-215 · CAP-128. Vacía el índice y lo construye de nuevo con lo que HOY hay en los módulos propietarios. Mientras dura, el índice se sigue consultando (la
    lectura ve el índice anterior hasta que la reconstrucción se confirma de golpe). Precondición: no hay una clase en curso (se puede reconstruir fuera de clase;
    la primera construcción —sin índice todavía— no la exige)."""

    def ejecutar(self, actor: Actor, *, desde_el_sistema: bool = False, inicial: bool = False) -> dict:
        if not desde_el_sistema:
            self.s.autorizacion.exigir(actor, cat.P_REINDEXAR)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            estado = uow.estado.leer()
            desde = estado.get("reconstruccion_desde")
            if estado["estado"] in (cat.CONSTRUYENDOSE, cat.RECONSTRUYENDOSE) and desde and ahora - desde < cat.RECONSTRUCCION_ABANDONADA_MS:
                raise ReconstruccionEnCurso("El índice ya se está reconstruyendo; espera a que termine.")
            if not inicial and self.s.aula.hay_sesion_activa():
                raise SesionActiva("Hay una clase en curso: reconstruir el índice completo espera a que termine, para no competir con ella.")
            anterior = estado["estado"]
            uow.estado.escribir(estado=cat.CONSTRUYENDOSE if inicial else cat.RECONSTRUYENDOSE, reconstruccion_desde=ahora)
        # Lo anterior queda confirmado: quien consulta ya ve «se está reconstruyendo». Lo que sigue es UNA transacción.
        try:
            with self.s.uow() as uow:
                # Las marcas se fijan ANTES de leer las entidades: lo que cambie mientras se lee tiene secuencia mayor y se aplicará después (idempotente).
                marcas = {f.fuente: f.ultima_secuencia() for f in self.s.fuentes.values()}
                uow.indice.vaciar()
                conteo: dict[str, int] = {}
                for tipo, fuente in self.s.fuentes.items():
                    n = 0
                    for documento in fuente.todos():
                        uow.indice.guardar(documento, ahora)
                        n += 1
                    conteo[tipo] = n
                for nombre, secuencia in marcas.items():
                    uow.marcas.guardar(nombre, secuencia, ahora)
                fin = self.s.reloj.ahora_ms()
                uow.estado.escribir(estado=cat.CONSULTABLE, construido_en=fin, sincronizado_en=fin, error="", error_en=None, reconstruccion_desde=None)
                carga = {"documentos": conteo, "total": sum(conteo.values()), "duracion_ms": fin - ahora, "inicial": inicial, "instante": fin}
                uow.outbox.publicar(cat.EV_INDICE_RECONSTRUIDO, "indice", carga)
                uow.auditoria.registrar(actor.id or cat.SISTEMA, cat.A_INDICE_RECONSTRUIDO, "m21_documento", "", nuevo=carga)
        except Exception as error:
            log.exception("La reconstrucción del índice falló")
            with self.s.uow() as uow:
                uow.estado.escribir(estado=cat.CONSTRUYENDOSE if inicial else (anterior if anterior != cat.RECONSTRUYENDOSE else cat.CONSULTABLE),
                                    error=f"reconstruccion: {type(error).__name__}", error_en=self.s.reloj.ahora_ms(), reconstruccion_desde=None)
            raise
        return {"documentos": conteo, "total": sum(conteo.values()), "duracion_ms": fin - ahora, "estado": cat.CONSULTABLE}


class Purgar(_CasoDeUso):
    """FUN-217. Quita del índice las entidades que su dueño ya no tiene (o ya no deja buscar). Lo usa la búsqueda cuando lo descubre al verificar en vivo: así una
    entidad retirada no vuelve a ser candidata aunque se haya perdido su evento."""

    def ejecutar(self, tipo: str, entidad_ids: list[str], causa: str = "verificacion") -> int:
        if not entidad_ids:
            return 0
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            n = uow.indice.quitar_ids(tipo, list(entidad_ids))
            if n:
                uow.outbox.publicar(cat.EV_ENTRADAS_PURGADAS, tipo, {"tipo": tipo, "entradas": n, "causa": causa, "instante": ahora})
        return n


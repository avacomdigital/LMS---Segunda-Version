"""
El motor de MOD-016: lo que de verdad respalda, verifica, exporta y restaura. Los casos de uso (`acciones.py`) deciden QUIÉN puede pedirlo y con qué pase; aquí se hace. Sin Django.

  respaldar   instantánea consistente de la base + carpetas de la institución → `.avbak` cifrado, escrito como `.parcial` y renombrado al terminar (FUN-170, FUN-171)
  verificar   descifra TODO, comprueba cada huella y la integridad de la base, y la cadena de un incremental (FUN-173, TST-058): un respaldo que falla NO se descarta, se marca
  exportar    copia el respaldo (y su cadena) a una unidad extraíble con su constancia (FUN-176)
  restaurar   todo en un lugar de trabajo ANTES de tocar nada vivo (TST-059); punto de retorno; aplicar; rehacer lo derivado; informe de qué se recupera y qué se pierde (FUN-174)
  reconciliar catalogar los `.avbak` que la base no conoce (una restauración devuelve la base al pasado; los archivos siguen ahí) y marcar los que ya no están
  retener     caducar lo que sobra según la retención, sin dejar sin base a un incremental ni sin el último restaurable (BR-017)
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3

from ..dominio import catalogos as cat
from ..dominio import cripto, formato, informes, programacion
from ..dominio.errores import (CustodiaRequerida, ClaveNoDisponible, EspacioInsuficiente, EstadoInvalido, NoEncontrado, PaseInvalido, RespaldoEnCurso, RespaldoFallido,
                               RespaldoRechazado, RestauracionAbortada, SesionActiva, SinRespaldoPrevio)
from .base import Servicios, _CasoDeUso, corto, nuevo_id, respaldo_a_dict
from .puertos import Actor

log = logging.getLogger("avacom.respaldo")

_PROTOCOLO_DE_LECTURA = 1024 * 1024


def _sha256_de(archivo) -> str:
    h = hashlib.sha256()
    for bloque in iter(lambda: archivo.read(_PROTOCOLO_DE_LECTURA), b""):
        h.update(bloque)
    return h.hexdigest()


class Motor(_CasoDeUso):
    def __init__(self, servicios: Servicios):
        super().__init__(servicios)

    # ------------------------------------------------------------------------------------------------------------------ lo común
    def _h(self, uow, respaldo_id: str, tipo: str, actor: str, detalle: dict | None = None, en: int | None = None) -> dict:
        return uow.historial.insertar({"respaldo_id": respaldo_id, "tipo": tipo, "en": self.ahora() if en is None else int(en), "actor": (actor or cat.SISTEMA)[:cat.MAX_ACTOR],
                                       "detalle": detalle or {}})

    def _evento(self, uow, respaldo_id: str, tipo: str, carga: dict) -> None:
        # un identificador por hecho: la cola deduplica por agregado y el mismo respaldo se verifica o se exporta más de una vez
        uow.eventos.publicar("Respaldo", f"{respaldo_id}:{self.ahora()}:{tipo.split('.')[1]}"[:256], tipo, {**carga, "respaldo_id": respaldo_id, "instante": self.ahora()})

    def fichas(self, uow) -> list[dict]:
        filas = uow.historial.de_todos()
        registrados = {r["respaldo_id"]: r for r in uow.respaldos.todos()}
        marcha = self.s.vivo.en_marcha() or {}
        ids = set(registrados) | set(filas)
        salida = [respaldo_a_dict(registrados.get(i), filas.get(i, []), marcha.get("respaldo_id") == i, i) for i in ids]
        return sorted(salida, key=lambda f: (f["creado_en"], f["respaldo_id"]), reverse=True)

    def ficha(self, uow, respaldo_id: str) -> dict:
        fila = uow.respaldos.obtener(respaldo_id)
        filas = uow.historial.de_respaldo(respaldo_id)
        if fila is None and not filas:
            raise NoEncontrado("No existe ese respaldo.")
        marcha = self.s.vivo.en_marcha() or {}
        return respaldo_a_dict(fila, filas, marcha.get("respaldo_id") == respaldo_id, respaldo_id)

    def programa(self, uow) -> programacion.Programa:
        return programacion.validar(uow.ajuste.obtener())

    def cadena(self, fichas: dict[str, dict], respaldo_id: str) -> list[dict]:
        """Del más viejo al más nuevo: la base completa y los incrementales hasta `respaldo_id`. Falla si falta alguno o ya no existe su archivo."""
        cadena, actual, visto = [], respaldo_id, set()
        while actual:
            f = fichas.get(actual)
            if f is None or not f["existe"] or actual in visto:
                raise RespaldoRechazado("cadena_incompleta")
            visto.add(actual)
            cadena.append(f)
            actual = f["base_id"]
        cadena.reverse()
        if cadena[0]["tipo"] != cat.T_COMPLETO:
            raise RespaldoRechazado("cadena_incompleta")
        return cadena

    def _ultimo_existente(self, fichas: list[dict]) -> dict | None:
        por_id = {f["respaldo_id"]: f for f in fichas}
        for f in fichas:                                                        # del más nuevo al más viejo
            if f["existe"]:
                try:
                    self.cadena(por_id, f["respaldo_id"])
                    return f
                except RespaldoRechazado:
                    continue
        return None

    # ------------------------------------------------------------------------------------------------------------------ respaldar
    def respaldar(self, actor: Actor, tipo: str, disparo: str, respaldo_id: str | None = None, verificar: bool | None = None) -> dict:
        """FUN-170 y FUN-171. Un solo respaldo o restauración a la vez (`RespaldoEnCurso`). Devuelve la ficha."""
        if not self.s.en_operacion.acquire(blocking=False):
            raise RespaldoEnCurso()
        try:
            return self._respaldar(actor, tipo, disparo, respaldo_id, self.s.config.verificar_al_terminar if verificar is None else verificar)
        finally:
            self.s.en_operacion.release()

    def _respaldar(self, actor: Actor, tipo: str, disparo: str, respaldo_id: str | None, verificar: bool) -> dict:
        s = self.s
        rid = respaldo_id or nuevo_id()
        inicio = self.ahora()
        with s.uow(lectura=True) as uow:
            fichas = self.fichas(uow)
            programa = self.programa(uow)
        base = None
        if tipo == cat.T_INCREMENTAL:
            base = self._ultimo_existente(fichas)
            if base is None:
                raise SinRespaldoPrevio()
        with s.uow() as uow:
            self._h(uow, rid, cat.H_REANUDADO if respaldo_id else cat.H_INICIADO, actor.id, {"tipo": tipo, "disparo": disparo, "base_id": base["respaldo_id"] if base else ""})
            if respaldo_id:
                uow.auditoria.registrar(actor.id, cat.A_REANUDADO, "m16_respaldo", rid, nuevo={"tipo": tipo, "disparo": disparo})
                self._evento(uow, rid, cat.EV_REANUDADO, {"tipo": tipo, "disparo": disparo})
        s.vivo.marcar(rid, "respaldo", inicio)
        trabajo = manija = None
        try:
            archivos, omitidos = s.origen.archivos(programa.incluir_reinstalable, None if base is None else max(0, int(base["creado_en"]) - cat.MINUTO_MS))
            necesario = 2 * s.origen.bytes_de_la_base() + sum(a.bytes for a in archivos) + s.config.margen_espacio
            libre = s.almacen.espacio_libre()
            if libre is not None and libre < necesario:
                raise EspacioInsuficiente(f"Hacen falta {necesario // cat.MIB} MB libres y hay {libre // cat.MIB} MB.", necesario=necesario, libre=libre)
            secuencia = s.nodo.ultima_secuencia()
            trabajo = s.almacen.carpeta_de_trabajo(f"respaldo-{corto(rid).lower()}")
            instantanea = trabajo / formato.BASE_DE_DATOS
            tam_base = s.origen.instantanea_de_la_base(instantanea)
            entradas = [formato.Entrada(formato.BASE_DE_DATOS, cat.CLASE_PRIMARIO, tam_base, lambda: open(instantanea, "rb"))]
            entradas += [formato.Entrada(a.nombre, a.clase, a.bytes, a.abrir) for a in archivos]
            dek = cripto.generar_clave()
            custodia = s.clavero.custodia()
            claves = formato.envolver_dek(rid, dek, s.clavero.clave_del_nodo(), (custodia["clave"], custodia["sal"]) if custodia else None)
            salida, manija = s.almacen.abrir_para_escribir(rid)
            creado = self.ahora()
            resultado = formato.escribir(salida, {"respaldo_id": rid, "tipo": tipo, "base_id": base["respaldo_id"] if base else "", "disparo": disparo, "creado_en": creado,
                                                  "producto": s.nodo.version_producto(), "secuencia_global": secuencia, "nodo_id": s.clavero.nodo_id(),
                                                  "incluye_reinstalable": bool(programa.incluir_reinstalable), "archivos": len(archivos), "omitidos": len(omitidos)},
                                         entradas, dek, claves)
            nombre = s.almacen.terminar(manija, rid, creado, tipo)
            manija = None
        except Exception as error:   # noqa: BLE001 — se registra el fallo y se relanza con su forma pública
            if manija is not None:
                s.almacen.descartar(manija)
            self._fallo(actor, rid, tipo, error)
            raise self._publico(error) from error
        finally:
            if trabajo is not None:
                s.almacen.limpiar_trabajo(trabajo)
            s.vivo.liberar()
        manifiesto = resultado["manifiesto"]
        with s.uow() as uow:
            uow.respaldos.insertar({"respaldo_id": rid, "tipo": tipo, "base_id": base["respaldo_id"] if base else "", "disparo": disparo, "archivo": nombre, "sha256": resultado["sha256"],
                                    "bytes": resultado["bytes"], "bytes_claro": manifiesto["bytes_claro"], "creado_en": creado, "secuencia_global": secuencia,
                                    "version_producto": manifiesto["producto"], "nodo_id": manifiesto["nodo_id"], "entradas": manifiesto["entradas"], "archivos": len(archivos),
                                    "incluye_reinstalable": bool(programa.incluir_reinstalable), "con_custodia": custodia is not None, "creado_por": actor.id[:cat.MAX_ACTOR]})
            self._h(uow, rid, cat.H_COMPLETO if tipo == cat.T_COMPLETO else cat.H_INCREMENTAL, actor.id,
                    {"bytes": resultado["bytes"], "entradas": manifiesto["entradas"], "archivos": len(archivos), "omitidos": len(omitidos), "huella": resultado["sha256"][:16],
                     "disparo": disparo, "duracion_ms": max(0, self.ahora() - inicio)})
            uow.auditoria.registrar(actor.id, cat.A_COMPLETO if tipo == cat.T_COMPLETO else cat.A_INCREMENTAL, "m16_respaldo", rid,
                                    nuevo={"tipo": tipo, "disparo": disparo, "bytes": resultado["bytes"], "entradas": manifiesto["entradas"], "huella": resultado["sha256"][:16]})
            self._evento(uow, rid, cat.EV_COMPLETO if tipo == cat.T_COMPLETO else cat.EV_INCREMENTAL,
                         {"tipo": tipo, "disparo": disparo, "bytes": resultado["bytes"], "entradas": manifiesto["entradas"], "secuencia_global": secuencia,
                          "con_custodia": custodia is not None})
        if verificar:
            try:
                self._verificar(Actor(id=cat.SISTEMA), rid)
            except Exception:   # noqa: BLE001 — la verificación se repite en el siguiente ciclo
                log.exception("No se pudo verificar el respaldo recién hecho", extra={"evento": "respaldo.verificacion_fallo", "ruta": "bad"})
        self.informes(rid)
        try:
            self._retener(Actor(id=cat.SISTEMA))
        except Exception:   # noqa: BLE001
            log.exception("No se pudo aplicar la retención", extra={"evento": "respaldo.retencion_fallo", "ruta": "bad"})
        with s.uow(lectura=True) as uow:
            return self.ficha(uow, rid)

    def _fallo(self, actor: Actor, rid: str, tipo: str, error: Exception) -> None:
        motivo = self._motivo(error)
        if motivo == "error_inesperado":
            log.exception("El respaldo falló", extra={"evento": "respaldo.fallo", "ruta": "bad"})
        try:
            with self.s.uow() as uow:
                self._h(uow, rid, cat.H_FALLIDO, actor.id, {"motivo": motivo, "tipo": tipo})
                uow.auditoria.registrar(actor.id, cat.A_FALLIDO, "m16_respaldo", rid, nuevo={"motivo": motivo, "tipo": tipo})
                self._evento(uow, rid, cat.EV_FALLIDO, {"motivo": motivo, "tipo": tipo})
        except Exception:   # noqa: BLE001
            log.exception("No se pudo anotar el fallo del respaldo", extra={"evento": "respaldo.fallo_sin_anotar", "ruta": "bad"})

    @staticmethod
    def _motivo(error: Exception) -> str:
        if isinstance(error, EspacioInsuficiente):
            return "espacio_insuficiente"
        if isinstance(error, formato.ArchivoCambio):
            return "archivo_cambio"
        if isinstance(error, sqlite3.Error):
            return "sin_origen"
        if isinstance(error, OSError):
            return "error_de_escritura"
        return "error_inesperado"

    @staticmethod
    def _publico(error: Exception) -> Exception:
        if isinstance(error, EspacioInsuficiente):
            return error
        return RespaldoFallido(Motor._motivo(error), "El respaldo no terminó; lo anterior sigue intacto.")

    # ------------------------------------------------------------------------------------------------------------------ verificar
    def verificar(self, actor: Actor, respaldo_id: str, custodia: str | None = None) -> dict:
        return self._verificar(actor, respaldo_id, custodia)

    def _verificar(self, actor: Actor, rid: str, custodia: str | None = None) -> dict:
        s = self.s
        with s.uow(lectura=True) as uow:
            fichas = {f["respaldo_id"]: f for f in self.fichas(uow)}
        ficha = fichas.get(rid)
        if ficha is None:
            raise NoEncontrado("No existe ese respaldo.")
        if not ficha["existe"]:
            raise EstadoInvalido("Ese respaldo ya no existe en el equipo.", estado=ficha["estado"])
        motivo, entradas = "", 0
        trabajo = None
        try:
            for f in self.cadena(fichas, rid):                                    # la cadena completa o nada
                archivo = s.almacen.abrir(f["archivo"])
                if archivo is None:
                    raise RespaldoRechazado("cadena_incompleta")
                with archivo:
                    if f["sha256"] and _sha256_de(archivo) != f["sha256"]:
                        raise RespaldoRechazado("huella_distinta")
                    archivo.seek(0)
                    manifiesto, cabecera = formato.leer_manifiesto(archivo)
                    if manifiesto["respaldo_id"] != f["respaldo_id"] or int(s.almacen.tamano(f["archivo"]) or 0) != int(f["bytes"]):
                        raise RespaldoRechazado("integridad_alterada")
                    dek = formato.abrir_dek(manifiesto, s.clavero.clave_del_nodo(), custodia)
                    for nombre, _info, bloques in formato.recorrer(archivo, manifiesto, cabecera, dek):
                        if nombre == formato.BASE_DE_DATOS and f["respaldo_id"] == rid:
                            trabajo = trabajo or s.almacen.carpeta_de_trabajo(f"verificacion-{corto(rid).lower()}")
                            with open(trabajo / "base.sqlite3", "wb") as salida:
                                for b in bloques:
                                    salida.write(b)
                        else:
                            for _ in bloques:
                                pass
                        if f["respaldo_id"] == rid:
                            entradas += 1
                    if f["respaldo_id"] == rid and entradas != manifiesto["entradas"]:
                        raise RespaldoRechazado("integridad_alterada")
            if trabajo is None:
                raise RespaldoRechazado("integridad_alterada")
            comprobacion = s.aplicador.comprobar_base(trabajo / "base.sqlite3")
            if not comprobacion.get("integra"):
                raise RespaldoRechazado("base_danada")
        except ClaveNoDisponible:
            motivo = "clave_no_disponible"
        except RespaldoRechazado as error:
            motivo = error.motivo
        finally:
            if trabajo is not None:
                s.almacen.limpiar_trabajo(trabajo)
        ok = not motivo
        with s.uow() as uow:
            self._h(uow, rid, cat.H_VERIFICADO if ok else cat.H_NO_VERIFICADO, actor.id, {"entradas": entradas} if ok else {"motivo": motivo})
            uow.auditoria.registrar(actor.id, cat.A_VERIFICADO if ok else cat.A_NO_VERIFICADO, "m16_respaldo", rid, nuevo={"resultado": "ok" if ok else motivo})
            self._evento(uow, rid, cat.EV_VERIFICADO, {"resultado": "ok" if ok else "falla", "motivo": motivo, "entradas": entradas})
        self.informes(rid)
        return {"respaldo_id": rid, "verificado": ok, "motivo": motivo or None, "entradas": entradas}

    # ------------------------------------------------------------------------------------------------------------------ exportar
    def exportar(self, actor: Actor, respaldo_id: str, unidad_id: str) -> dict:
        s = self.s
        with s.uow(lectura=True) as uow:
            fichas = {f["respaldo_id"]: f for f in self.fichas(uow)}
        ficha = fichas.get(respaldo_id)
        if ficha is None:
            raise NoEncontrado("No existe ese respaldo.")
        if not ficha["existe"]:
            raise EstadoInvalido("Ese respaldo ya no existe en el equipo.", estado=ficha["estado"])
        try:
            cadena = self.cadena(fichas, respaldo_id)
        except RespaldoRechazado:
            raise EstadoInvalido("Falta algún respaldo de la cadena: no se puede exportar completo.", estado=ficha["estado"]) from None
        rotulo = ""
        for f in cadena:
            ruta = s.almacen.ruta_de(f["archivo"])
            if ruta is None:
                raise NoEncontrado("El archivo del respaldo ya no está.")
            extras = {f"constancia-{corto(f['respaldo_id'])}.txt": informes.constancia(f, s.nodo.institucion(), s.reloj.desfase_min())}
            rotulo = s.unidades.copiar(unidad_id, ruta, f["archivo"], extras)
        with s.uow() as uow:
            self._h(uow, respaldo_id, cat.H_EXPORTADO, actor.id, {"unidad": rotulo, "archivos": len(cadena)})
            uow.auditoria.registrar(actor.id, cat.A_EXPORTADO, "m16_respaldo", respaldo_id, nuevo={"unidad": rotulo, "archivos": len(cadena)})
            self._evento(uow, respaldo_id, cat.EV_EXPORTADO, {"unidad": rotulo, "archivos": len(cadena)})
        self.informes(respaldo_id)
        return {"respaldo_id": respaldo_id, "exportado": True, "unidad": rotulo, "archivos": len(cadena)}

    # ------------------------------------------------------------------------------------------------------------------ informes para el personal administrativo
    def informes(self, respaldo_id: str | None = None) -> None:
        """La constancia del respaldo y el resumen CSV. Nunca lanza (R-04): un informe que no se pudo escribir no deshace un respaldo."""
        s = self.s
        try:
            with s.uow(lectura=True) as uow:
                fichas = self.fichas(uow)
            desfase, institucion = s.reloj.desfase_min(), s.nodo.institucion()
            for f in fichas:
                if respaldo_id and f["respaldo_id"] == respaldo_id and f["archivo"]:
                    s.almacen.guardar_informe(self.nombre_de_constancia(f, desfase), informes.constancia(f, institucion, desfase))
            s.almacen.guardar_informe("resumen-de-respaldos.csv", informes.resumen_csv([f for f in fichas if f["archivo"] or f["estado"] == cat.E_FALLIDO], desfase), con_bom=True)
        except Exception:   # noqa: BLE001
            log.exception("No se pudieron escribir los informes del respaldo", extra={"evento": "respaldo.informes_fallo", "ruta": "bad"})

    @staticmethod
    def nombre_de_constancia(ficha: dict, desfase_min: int) -> str:
        from datetime import datetime, timedelta, timezone
        fecha = datetime.fromtimestamp(int(ficha["creado_en"]) / 1000, tz=timezone(timedelta(minutes=desfase_min))).strftime("%Y%m%d-%H%M")
        return f"constancia-{fecha}-{corto(ficha['respaldo_id']).lower()}.txt"

    # ------------------------------------------------------------------------------------------------------------------ retención y catálogo
    def _retener(self, actor: Actor) -> list[str]:
        s = self.s
        with s.uow(lectura=True) as uow:
            fichas = self.fichas(uow)
            programa = self.programa(uow)
        candidatos = [programacion.Candidato(f["respaldo_id"], f["creado_en"], f["tipo"], f["base_id"] or None, f["restaurable"], f["existe"]) for f in fichas]
        por_id = {f["respaldo_id"]: f for f in fichas}
        caducados = []
        for rid in programacion.caducables(candidatos, programa.retencion):
            f = por_id[rid]
            if f["estado"] == cat.E_NO_VERIFICADO and self.ahora() - int(f["creado_en"]) < cat.DIA_MS:
                continue                                                          # uno recién hecho que todavía espera su verificación no se retira
            s.almacen.borrar(f["archivo"])
            with s.uow() as uow:
                self._h(uow, rid, cat.H_CADUCADO, actor.id, {"motivo": "retencion"})
                uow.auditoria.registrar(actor.id, cat.A_CADUCADO, "m16_respaldo", rid, nuevo={"motivo": "retencion"})
                self._evento(uow, rid, cat.EV_CADUCADO, {"motivo": "retencion"})
            caducados.append(rid)
        if caducados:
            self.informes()
        return caducados

    def reconciliar(self, actor: Actor) -> dict:
        """Cataloga los `.avbak` de la carpeta que la base no conoce y marca como caducados los registrados cuyo archivo ya no está."""
        s = self.s
        with s.uow(lectura=True) as uow:
            fichas = {f["respaldo_id"]: f for f in self.fichas(uow)}
            registrados = {r["respaldo_id"]: r for r in uow.respaldos.todos()}
        en_carpeta = set(s.almacen.listar())
        nuevos, perdidos = [], []
        conocidos = {r["archivo"] for r in registrados.values()}
        for nombre in sorted(en_carpeta - conocidos):
            archivo = s.almacen.abrir(nombre)
            if archivo is None:
                continue
            try:
                with archivo:
                    manifiesto, _ = formato.leer_manifiesto(archivo)
                    archivo.seek(0)
                    huella = _sha256_de(archivo)
            except RespaldoRechazado:
                continue
            rid = manifiesto["respaldo_id"]
            if rid in registrados:
                continue
            with s.uow() as uow:
                uow.respaldos.insertar({"respaldo_id": rid, "tipo": manifiesto["tipo"], "base_id": manifiesto.get("base_id") or "", "disparo": manifiesto.get("disparo") or cat.D_MANUAL,
                                        "archivo": nombre, "sha256": huella, "bytes": int(s.almacen.tamano(nombre) or 0), "bytes_claro": manifiesto["bytes_claro"],
                                        "creado_en": manifiesto["creado_en"], "secuencia_global": int(manifiesto.get("secuencia_global") or 0),
                                        "version_producto": str(manifiesto.get("producto") or ""), "nodo_id": str(manifiesto.get("nodo_id") or ""), "entradas": manifiesto["entradas"],
                                        "archivos": int(manifiesto.get("archivos") or 0), "incluye_reinstalable": bool(manifiesto.get("incluye_reinstalable")),
                                        "con_custodia": "custodia" in manifiesto["claves"], "creado_por": actor.id[:cat.MAX_ACTOR]})
                self._h(uow, rid, cat.H_COMPLETO if manifiesto["tipo"] == cat.T_COMPLETO else cat.H_INCREMENTAL, actor.id, {"catalogado": True, "huella": huella[:16]})
            nuevos.append(rid)
        for rid, f in fichas.items():
            if f["existe"] and f["archivo"] and f["archivo"] not in en_carpeta:
                with s.uow() as uow:
                    self._h(uow, rid, cat.H_CADUCADO, actor.id, {"motivo": "archivo_ausente"})
                    uow.auditoria.registrar(actor.id, cat.A_CADUCADO, "m16_respaldo", rid, nuevo={"motivo": "archivo_ausente"})
                perdidos.append(rid)
        if nuevos or perdidos:
            self.informes()
        return {"catalogados": nuevos, "ausentes": perdidos}

    # ------------------------------------------------------------------------------------------------------------------ restaurar
    def restaurar(self, actor: Actor, *, respaldo_id: str | None, candidato_id: str | None, custodia: str | None, motivo: str, nota: str, pase) -> dict:
        s = self.s
        if s.aula.sesiones_activas() > 0:
            raise SesionActiva()
        if not s.en_operacion.acquire(blocking=False):
            raise RespaldoEnCurso()
        trabajos = []
        try:
            return self._restaurar(actor, respaldo_id, candidato_id, custodia, motivo, nota, pase, trabajos)
        finally:
            for t in trabajos:
                s.almacen.limpiar_trabajo(t)
            s.vivo.liberar()
            s.en_operacion.release()

    def _abortar(self, actor: Actor, rid: str, motivo: str, error: Exception | None = None) -> RestauracionAbortada:
        try:
            with self.s.uow() as uow:
                self._h(uow, rid, cat.H_RESTAURACION_ABORTADA, actor.id, {"motivo": motivo})
                uow.auditoria.registrar(actor.id, cat.A_RESTAURACION_ABORTADA, "m16_respaldo", rid, nuevo={"motivo": motivo})
                self._evento(uow, rid, cat.EV_RESTAURACION_ABORTADA, {"motivo": motivo})
        except Exception:   # noqa: BLE001
            log.exception("No se pudo anotar la restauración abortada", extra={"evento": "respaldo.aborto_sin_anotar", "ruta": "bad"})
        return RestauracionAbortada(motivo, cat.MENSAJES_DE_MOTIVO.get(motivo, "La restauración se abortó antes de tocar los datos del equipo."))

    def _resolver_fuente(self, candidato_id: str | None, respaldo_id: str | None, trabajos: list) -> tuple[list[dict], str]:
        """La cadena a restaurar como una lista de `{ficha o manifiesto, abrir}` del más viejo al más nuevo, y el identificador del respaldo elegido."""
        s = self.s
        with s.uow(lectura=True) as uow:
            fichas = {f["respaldo_id"]: f for f in self.fichas(uow)}
        externos: dict[str, dict] = {}
        elegido = respaldo_id
        if candidato_id:
            entrada = s.almacen.carpeta_de_trabajo("entrada")
            trabajos.append(entrada)
            lista = s.unidades.candidatos()
            if not any(c.id == candidato_id for c in lista):
                raise NoEncontrado("Ese respaldo ya no está en la unidad.")
            pedidos = [candidato_id] + [c.id for c in lista if c.id != candidato_id]
            for i, cid in enumerate(pedidos):
                destino = entrada / f"c{i}"
                destino.mkdir(parents=True, exist_ok=True)
                cand = s.unidades.traer(cid, destino)
                if cand is None:
                    continue
                with open(destino / cand.nombre, "rb") as f:
                    try:
                        manifiesto, _ = formato.leer_manifiesto(f)
                    except RespaldoRechazado:
                        if cid == candidato_id:
                            raise
                        continue
                externos[manifiesto["respaldo_id"]] = {"manifiesto": manifiesto, "ruta": destino / cand.nombre}
                if cid == candidato_id:
                    elegido = manifiesto["respaldo_id"]
        if not elegido:
            raise NoEncontrado("Indica qué respaldo restaurar.")
        cadena, actual, visto = [], elegido, set()
        while actual:
            if actual in visto:
                raise RespaldoRechazado("cadena_incompleta")
            visto.add(actual)
            local = fichas.get(actual)
            if local is not None and local["existe"] and s.almacen.tamano(local["archivo"]) is not None:
                cadena.append({"id": actual, "ficha": local, "abrir": (lambda n=local["archivo"]: s.almacen.abrir(n)), "base": local["base_id"], "tipo": local["tipo"]})
                actual = local["base_id"]
            elif actual in externos:
                e = externos[actual]
                cadena.append({"id": actual, "ficha": None, "abrir": (lambda r=e["ruta"]: open(r, "rb")), "base": e["manifiesto"].get("base_id") or "", "tipo": e["manifiesto"]["tipo"]})
                actual = e["manifiesto"].get("base_id") or ""
            else:
                raise NoEncontrado("No existe ese respaldo.") if actual == elegido else RespaldoRechazado("cadena_incompleta")
        cadena.reverse()
        if cadena[0]["tipo"] != cat.T_COMPLETO:
            raise RespaldoRechazado("cadena_incompleta")
        return cadena, elegido

    def _restaurar(self, actor, respaldo_id, candidato_id, custodia, motivo, nota, pase, trabajos) -> dict:
        s = self.s
        inicio = self.ahora()
        try:
            cadena, rid = self._resolver_fuente(candidato_id, respaldo_id, trabajos)
        except RespaldoRechazado as error:
            raise self._abortar(actor, respaldo_id or "", error.motivo) from error
        s.vivo.marcar(rid, "restauracion", inicio)
        staging = s.almacen.carpeta_de_trabajo(f"restauracion-{corto(rid).lower()}")
        trabajos.append(staging)
        manifiesto_elegido, nueva_huella = {}, False
        try:
            # 1 · TODO en un lugar de trabajo: descifrar, comprobar cada huella y extraer. Nada vivo se toca todavía (TST-059).
            archivos_restaurados = 0
            for paso in cadena:
                es_ultimo = paso is cadena[-1]
                archivo = paso["abrir"]()
                if archivo is None:
                    raise RespaldoRechazado("cadena_incompleta")
                with archivo:
                    manifiesto, cabecera = formato.leer_manifiesto(archivo)
                    if manifiesto["respaldo_id"] != paso["id"]:
                        raise RespaldoRechazado("integridad_alterada")
                    try:
                        dek = formato.abrir_dek(manifiesto, s.clavero.clave_del_nodo(), custodia)
                    except ClaveNoDisponible:
                        if not custodia:
                            raise CustodiaRequerida() from None
                        raise
                    for nombre, _info, bloques in formato.recorrer(archivo, manifiesto, cabecera, dek):
                        if nombre == formato.BASE_DE_DATOS:
                            destino = (staging / "base.sqlite3") if es_ultimo else None
                        else:
                            destino = staging / "archivos" / nombre
                            archivos_restaurados += 1
                        if destino is None:
                            for _ in bloques:
                                pass
                            continue
                        destino.parent.mkdir(parents=True, exist_ok=True)
                        with open(destino, "wb") as salida:
                            for b in bloques:
                                salida.write(b)
                    if es_ultimo:
                        manifiesto_elegido = manifiesto
            if not (staging / "base.sqlite3").exists():
                raise RespaldoRechazado("integridad_alterada")
            comprobacion = s.aplicador.comprobar_base(staging / "base.sqlite3")
            if not comprobacion.get("integra"):
                raise RespaldoRechazado("base_danada")
            if comprobacion.get("migraciones_desconocidas"):
                raise RespaldoRechazado("base_de_version_posterior")
            nueva_huella = str(manifiesto_elegido.get("nodo_id") or "") != s.clavero.nodo_id()
        except RespaldoRechazado as error:
            raise self._abortar(actor, rid, error.motivo) from error
        except CustodiaRequerida:
            raise self._abortar(actor, rid, "clave_no_disponible") from None
        except OSError:
            log.exception("La restauración no pudo preparar sus archivos", extra={"evento": "respaldo.restauracion_preparacion", "ruta": "bad"})
            raise self._abortar(actor, rid, "formato_invalido") from None
        # 2 · punto de no retorno: se gasta el pase y se toma el respaldo de seguridad
        if pase is not None:
            with s.uow() as uow:
                if not uow.pases.usar(pase.pase_id, self.ahora(), cat.P_RESTAURAR, pase.tecnico, pase.kid, rid):
                    raise PaseInvalido("ya_usado")
        secuencia_antes = s.nodo.ultima_secuencia()
        try:
            retorno = self._respaldar(Actor(id=cat.SISTEMA), cat.T_COMPLETO, cat.D_PREVIO_RESTAURACION, None, True)
            if not retorno.get("restaurable"):
                raise RespaldoRechazado("punto_de_retorno")
        except Exception as error:   # noqa: BLE001 — sin punto de retorno no se restaura
            raise self._abortar(actor, rid, "punto_de_retorno", error) from error
        s.vivo.marcar(rid, "restauracion", self.ahora())
        with s.uow() as uow:
            self._h(uow, rid, cat.H_RESTAURACION_INICIADA, actor.id, {"motivo": motivo, "punto_de_retorno": retorno["respaldo_id"], "nueva_huella": nueva_huella})
        # 3 · aplicar
        try:
            s.aplicador.aplicar_base(staging / "base.sqlite3")
            aplicados = 0
            carpeta_de_archivos = staging / "archivos"
            if carpeta_de_archivos.exists():
                for sub in sorted(p for p in carpeta_de_archivos.iterdir() if p.is_dir()):
                    aplicados += s.aplicador.aplicar_archivos(sub.name, cat.CLASE_PRIMARIO, sub)
        except Exception as error:   # noqa: BLE001
            log.exception("La restauración falló al aplicarse", extra={"evento": "respaldo.restauracion_fallo", "ruta": "bad"})
            raise RestauracionAbortada("aplicacion_parcial", "La restauración falló al aplicarse. El respaldo de seguridad previo está intacto: avisa al personal de AVACOM.",
                                       punto_de_retorno=retorno["respaldo_id"]) from error
        # 4 · rehacer lo derivado y dejar constancia EN LA BASE RESTAURADA
        if nueva_huella and custodia:
            self._reanclar_custodia(manifiesto_elegido, custodia)
        post = s.tras.ejecutar(nueva_huella)
        fin = self.ahora()
        reconciliado = self.reconciliar(Actor(id=cat.SISTEMA))
        perdidas = {"horas": round(max(0, fin - int(manifiesto_elegido["creado_en"])) / cat.HORA_MS, 1), "eventos": max(0, secuencia_antes - int(manifiesto_elegido.get("secuencia_global") or 0))}
        with s.uow() as uow:
            if pase is not None:
                uow.pases.usar(pase.pase_id, fin, cat.P_RESTAURAR, pase.tecnico, pase.kid, rid)       # la base restaurada no sabe que este pase ya se gastó
            self._h(uow, rid, cat.H_RESTAURADO, actor.id, {"motivo": motivo, "nota": nota[:cat.MAX_NOTA], "punto_de_retorno": retorno["respaldo_id"], "perdidas": perdidas,
                                                           "nueva_huella": nueva_huella, "duracion_ms": max(0, fin - inicio)})
            if post.get("reconstruidos"):
                self._h(uow, rid, cat.H_INDICE, cat.SISTEMA, {"modulos": post["reconstruidos"]})
            uow.auditoria.registrar(actor.id, cat.A_RESTAURADO, "m16_respaldo", rid, nuevo={"motivo": motivo, "punto_de_retorno": retorno["respaldo_id"], "perdidas": perdidas,
                                                                                               "nueva_huella": nueva_huella})
            self._evento(uow, rid, cat.EV_RESTAURADO, {"motivo": motivo, "punto_de_retorno": retorno["respaldo_id"], "perdidas": perdidas, "nueva_huella": nueva_huella})
            if post.get("reconstruidos"):
                self._evento(uow, rid, cat.EV_INDICE, {"modulos": post["reconstruidos"]})
        with s.uow(lectura=True) as uow:
            ficha = self.ficha(uow, rid)
        resultado = {"ok": True, "en": fin, "respaldo_id": rid, "punto_de_retorno": retorno["respaldo_id"], "archivos": aplicados, "perdidas": perdidas, "post": post,
                     "licencia": post.get("licencia"), "reconstruidos": ", ".join(post.get("reconstruidos") or []) or None, "catalogados": reconciliado["catalogados"],
                     "nueva_huella": nueva_huella, "reinicio_recomendado": True}
        texto = informes.informe_de_restauracion(ficha, resultado, s.nodo.institucion(), s.reloj.desfase_min())
        nombre = f"restauracion-{corto(rid).lower()}-{fin}.txt"
        try:
            s.almacen.guardar_informe(nombre, texto)
        except Exception:   # noqa: BLE001
            log.exception("No se pudo guardar el informe de restauración", extra={"evento": "respaldo.informes_fallo", "ruta": "bad"})
        self.informes()
        return {**resultado, "informe": nombre, "informe_texto": texto}

    def _reanclar_custodia(self, manifiesto: dict, codigo: str) -> None:
        """Restauraste en un equipo NUEVO con el código de la institución: este equipo guarda desde ahora la clave de custodia derivada (envuelta con SU clave), el código no cambia."""
        custodia = (manifiesto.get("claves") or {}).get("custodia")
        secreto = cripto.secreto_de_custodia(codigo)
        if not custodia or secreto is None:
            return
        sal = bytes.fromhex(custodia["sal"])
        self.s.clavero.guardar_custodia(self.ahora(), sal, cripto.clave_de_custodia(secreto, sal, int(custodia.get("n", cripto.SCRYPT_N)), int(custodia.get("r", cripto.SCRYPT_R)),
                                                                                    int(custodia.get("p", cripto.SCRYPT_P))))

"""
Los casos de uso de MOD-017 (FUN-180…187), uno por acción del administrador o del técnico, más las consultas. Cada uno: permiso → reglas puras del dominio → UNA transacción corta
con el hecho, su asiento y su evento juntos (BR-001). Ninguno escribe fuera de `m17_*` ni toca `backend/` (P-06: quien aplica es el Host).

  Importar(candidato)     FUN-180 + FUN-181: lee el `.avupd` de la fuente, lo VERIFICA entero en memoria (firma, forma, SHA) y, sólo si pasa, lo copia a `paquetes\\` y lo registra como
                          recibido + verificado (o incompatible). Un rechazo deja SÓLO una fila `rechazado` con el motivo y ningún archivo escrito (TST-048, TST-062).
  Programar(id, ventana)  FUN-182: una ventana única (P-08). Desprogramar la cancela.
  Aplicar(id)             FUN-184: con cero clases, compatible y con espacio, escribe la ORDEN para el Host (202) y deja el paquete `aplicando`; con clase, 409 `sesion_activa` y una
                          fila `bloqueada` (FUN-183). Nunca cierra una sesión (R-01).
  Revertir(id, nota)      FUN-186 manual, dentro de 14 días (P-09): la orden de reversión a la instantánea.
  Consultas               estado, paquetes (candidatos + importados), detalle e historial (FUN-187).
"""
from __future__ import annotations

import logging
from collections.abc import Iterable

from ..dominio import catalogos as cat
from ..dominio import compatibilidad as comp
from ..dominio import estados, orden as dom_orden, paquete as dom_paquete, ventana as dom_ventana
from ..dominio import manifiesto as mf
from ..dominio.errores import (ActualizacionEnCurso, ContratoIncompatible, DatosInvalidos, EspacioInsuficiente, NoEncontrado, PaqueteRechazado, PaqueteRepetido, SerieMenor,
                               SesionActiva, YaAplicado)
from .base import _CasoDeUso, corto, derivado_de, fila_a_dict, nuevo_id, paquete_a_dict
from .puertos import Actor, UnidadDeTrabajo

log = logging.getLogger("avacom.actualizacion")

RECHAZOS_RECORDADOS_MS = 60 * cat.MINUTO_MS      # el mismo archivo rechazado hace menos de una hora no vuelve a dejar asiento ni evento (evita que un USB roto llene la bitácora)


class _Base(_CasoDeUso):
    def _paquete(self, uow: UnidadDeTrabajo, paquete_id: str) -> tuple[dict, list[dict]]:
        paquete = uow.paquetes.obtener(str(paquete_id or ""))
        if paquete is None:
            raise NoEncontrado("No hay un paquete con ese identificador.", paquete_id=str(paquete_id or ""))
        return paquete, uow.historial.de_paquete(paquete["paquete_id"])

    def _fila(self, uow: UnidadDeTrabajo, actor: str, paquete: dict | None, tipo: str, ahora: int, detalle: dict | None = None, accion_bitacora: str | None = None,
              evento: str | None = None, carga: dict | None = None) -> dict:
        """El hecho, su asiento y su evento, juntos (BR-001). `paquete` None sólo para `rechazado`."""
        base = {"paquete_id": paquete["paquete_id"] if paquete else "", "tipo": tipo, "en": int(ahora), "actor": actor, "serie": paquete["serie"] if paquete else 0,
                "version_producto": paquete["version_producto"] if paquete else "", "detalle": dict(detalle or {})}
        fila = uow.historial.insertar(base)
        resumen = {"paquete_id": base["paquete_id"] or None, "serie": base["serie"], "version_producto": base["version_producto"], "tipo": tipo, **(detalle or {})}
        if accion_bitacora:
            uow.auditoria.registrar(actor, accion_bitacora, "m17_historial", str(fila.get("id") or ""), nuevo=resumen)
        if evento:
            uow.eventos.publicar(cat.AGREGADO_PAQUETE, base["paquete_id"] or f"rechazado:{(detalle or {}).get('sha256', '')[:12]}", evento, {**resumen, **(carga or {})})
        return fila

    def _instalacion(self):
        inst = self.s.registro.instalacion()
        admite, motivo = self.s.licencia.admite(())
        if not admite:
            inst = type(inst)(version_producto=inst.version_producto, contrato_biblioteca=inst.contrato_biblioteca, modulos=inst.modulos, licencia_admite=False, motivo_licencia=motivo)
        return inst

    def _compatibilidad(self, manifiesto: mf.Manifiesto, bytes_paquete: int) -> comp.Compatibilidad:
        inst = self._instalacion()
        admite, motivo = self.s.licencia.admite(manifiesto.nombres_de_modulos)
        if not admite:
            inst = type(inst)(version_producto=inst.version_producto, contrato_biblioteca=inst.contrato_biblioteca, modulos=inst.modulos, licencia_admite=False, motivo_licencia=motivo)
        requerido = comp.espacio_requerido(manifiesto, bytes_paquete=bytes_paquete, bytes_base=self.s.almacen.bytes_de_la_base())
        return comp.evaluar(manifiesto, inst, self.s.almacen.espacio_libre(), requerido)

    def _leer_paquete(self, paquete: dict) -> dom_paquete.Paquete:
        datos = self.s.almacen.leer_paquete(paquete["paquete_id"])
        if datos is None:
            raise NoEncontrado("El archivo del paquete ya no está en la carpeta de actualizaciones: vuelve a importarlo.", paquete_id=paquete["paquete_id"])
        verificado = dom_paquete.verificar(datos, self.s.claves.publicas(), self.s.config.max_paquete_bytes)      # se vuelve a verificar: lo guardado pudo cambiar (A5)
        if verificado.sha256 != paquete["sha256"]:
            raise PaqueteRechazado("sha_distinto", "El archivo guardado no es el que se importó.")
        return verificado


# ------------------------------------------------------------------------------------------------------------------- importar (FUN-180, FUN-181)
class Importar(_Base):
    def ejecutar(self, actor: Actor, candidato_id: str) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_IMPORTAR)
        candidato_id = str(candidato_id or "").strip()
        if not candidato_id:
            raise DatosInvalidos("Indica qué paquete importar (`candidato`).")
        leido = self.s.fuentes.leer(candidato_id)
        if leido is None:
            raise NoEncontrado("Ese paquete ya no está en la unidad o en la carpeta de entrada.", candidato=candidato_id)
        candidato, datos = leido
        ahora = self.ahora()
        with self.s.bloqueo:
            try:
                verificado = dom_paquete.verificar(datos, self.s.claves.publicas(), self.s.config.max_paquete_bytes)
            except PaqueteRechazado as error:
                self._rechazar(actor, candidato, datos, error, ahora)
                raise
            return self._aceptar(actor, candidato, verificado, ahora)

    def _rechazar(self, actor: Actor, candidato, datos: bytes, error: PaqueteRechazado, ahora: int) -> None:
        """TST-048 / TST-062: cero archivos escritos; sólo el historial, el asiento y el evento (una vez por archivo y hora)."""
        import hashlib
        sha = hashlib.sha256(datos).hexdigest()
        with self.s.uow() as uow:
            if uow.historial.rechazado_reciente(sha, ahora - RECHAZOS_RECORDADOS_MS):
                return
            accion = cat.A_FIRMA_INVALIDA if error.motivo in cat.MOTIVOS_DE_FIRMA else cat.A_INTEGRIDAD_ALTERADA
            detalle = {"motivo": error.motivo, "codigo": error.codigo, "sha256": sha, "bytes": len(datos), "origen": candidato.origen, "nombre": candidato.nombre[:cat.MAX_NOMBRE]}
            self._fila(uow, actor.id, None, cat.H_RECHAZADO, ahora, detalle, accion_bitacora=accion, evento=cat.EV_RECHAZADO)
            uow.auditoria.registrar(actor.id, cat.A_RECHAZADO, "m17_historial", "", nuevo={"motivo": error.motivo, "sha256": sha})

    def _aceptar(self, actor: Actor, candidato, verificado: dom_paquete.Paquete, ahora: int) -> dict:
        m = verificado.manifiesto
        with self.s.uow() as uow:
            repetido = uow.paquetes.existe_sha(verificado.sha256)
            if repetido is not None:
                paquete, filas = self._paquete(uow, repetido)
                return paquete_a_dict(paquete, filas, ahora, self.s.config.dias_reversion)
            if uow.paquetes.obtener(m.paquete_id) is not None:
                raise PaqueteRepetido("Ya se importó un paquete con ese identificador y otro contenido.", paquete_id=m.paquete_id)
            # el archivo se guarda ANTES de registrar: si la copia falla no queda un paquete sin archivo
            self.s.almacen.guardar_paquete(m.paquete_id, verificado.datos)
            paquete = uow.paquetes.insertar({
                "paquete_id": m.paquete_id, "nombre": m.nombre, "version_producto": m.version_producto, "serie": m.serie, "modulos": list(m.nombres_de_modulos),
                "manifiesto": mf.resumen(m), "kid": verificado.kid, "sha256": verificado.sha256, "bytes": verificado.bytes, "archivo": candidato.nombre[:160], "origen": candidato.origen,
                "recibido_en": ahora, "importado_por": actor.id})
            resumen = {"nombre": m.nombre, "modulos": list(m.nombres_de_modulos), "kid": verificado.kid, "sha256": verificado.sha256, "bytes": verificado.bytes, "origen": candidato.origen}
            self._fila(uow, actor.id, paquete, cat.H_RECIBIDO, ahora, resumen, accion_bitacora=cat.A_IMPORTADO, evento=cat.EV_IMPORTADO)
            compat = self._compatibilidad(m, verificado.bytes)
            detalle = {**resumen, "compatibilidad": compat.como_dict()}
            if compat.ok or compat.solo_espacio:
                # FUN-181: firma e integridad verificadas; el espacio se vuelve a medir al aplicar (puede cambiar) y no hace al paquete «incompatible»
                self._fila(uow, actor.id, paquete, cat.H_VERIFICADO, ahora, detalle, accion_bitacora=cat.A_VERIFICADO, evento=cat.EV_VERIFICADO)
            else:
                self._fila(uow, actor.id, paquete, cat.H_INCOMPATIBLE, ahora, {**detalle, "incompatibilidades": [p.como_dict() for p in compat.problemas]},
                           accion_bitacora=cat.A_VERIFICADO, evento=cat.EV_VERIFICADO, carga={"compatible": False})
            filas = uow.historial.de_paquete(m.paquete_id)
        return paquete_a_dict(paquete, filas, ahora, self.s.config.dias_reversion)


# ------------------------------------------------------------------------------------------------------------------- programar (FUN-182)
class Programar(_Base):
    def ejecutar(self, actor: Actor, paquete_id: str, desde, hasta) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_PROGRAMAR)
        ahora = self.ahora()
        v = dom_ventana.validar(desde, hasta, ahora)
        with self.s.bloqueo, self.s.uow() as uow:
            paquete, filas = self._paquete(uow, paquete_id)
            d = derivado_de(filas, self.s.config.dias_reversion)
            estados.exigir_programable(d)
            self._fila(uow, actor.id, paquete, cat.H_PROGRAMADO, ahora, {"desde": v.desde, "hasta": v.hasta}, accion_bitacora=cat.A_PROGRAMADO, evento=cat.EV_PROGRAMADA)
            filas = uow.historial.de_paquete(paquete["paquete_id"])
        return paquete_a_dict(paquete, filas, ahora, self.s.config.dias_reversion)


class Desprogramar(_Base):
    def ejecutar(self, actor: Actor, paquete_id: str) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_PROGRAMAR)
        ahora = self.ahora()
        with self.s.bloqueo, self.s.uow() as uow:
            paquete, filas = self._paquete(uow, paquete_id)
            d = derivado_de(filas, self.s.config.dias_reversion)
            if d.estado != cat.PROGRAMADO:
                raise estados.EstadoInvalido("Ese paquete no está programado.", estado=d.estado)
            self._fila(uow, actor.id, paquete, cat.H_DESPROGRAMADO, ahora, {"ventana": d.ventana}, accion_bitacora=cat.A_DESPROGRAMADO)
            filas = uow.historial.de_paquete(paquete["paquete_id"])
        return paquete_a_dict(paquete, filas, ahora, self.s.config.dias_reversion)


# ------------------------------------------------------------------------------------------------------------------- aplicar (FUN-183, FUN-184)
class Aplicar(_Base):
    """La ORDEN al Host (P-06). Desde aquí hasta el resultado, el inicio de clases responde 503 (P-08)."""

    def ejecutar(self, actor: Actor, paquete_id: str, *, desde_ventana: bool = False) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_APLICAR)
        ahora = self.ahora()
        with self.s.bloqueo:
            with self.s.uow(lectura=True) as uow:
                paquete, filas = self._paquete(uow, paquete_id)
            d = derivado_de(filas, self.s.config.dias_reversion)
            estados.exigir_aplicable(d)
            if self.s.almacen.hay_orden() or self._otra_en_curso(paquete["paquete_id"]):
                raise ActualizacionEnCurso()
            sesiones = self.s.aula.sesiones_activas()
            if sesiones > 0:
                with self.s.uow() as uow:
                    self._fila(uow, actor.id, paquete, cat.H_BLOQUEADA, ahora, {"sesiones_activas": sesiones, "motivo": dom_ventana.SESION_ACTIVA}, accion_bitacora=cat.A_BLOQUEADA,
                               evento=cat.EV_BLOQUEADA)
                raise SesionActiva(sesiones_activas=sesiones)
            verificado = self._leer_paquete(paquete)
            compat = self._compatibilidad(verificado.manifiesto, verificado.bytes)
            if not compat.ok:
                with self.s.uow() as uow:
                    if not compat.solo_espacio and d.estado != cat.INCOMPATIBLE:
                        self._fila(uow, actor.id, paquete, cat.H_INCOMPATIBLE, ahora, {"incompatibilidades": [p.como_dict() for p in compat.problemas]}, accion_bitacora=cat.A_VERIFICADO)
                self._fallar_por(compat)
            orden_id = nuevo_id()
            orden = dom_orden.armar(orden_id=orden_id, accion=cat.ACCION_APLICAR, m=verificado.manifiesto, sha256=verificado.sha256, bytes_paquete=verificado.bytes, kid=verificado.kid,
                                    ahora=ahora, actor=actor.id, ventana=d.ventana if desde_ventana else None)
            self.s.almacen.extraer(verificado.manifiesto.paquete_id, verificado.archivos())
            with self.s.uow() as uow:
                if d.estado == cat.INCOMPATIBLE:
                    self._fila(uow, actor.id, paquete, cat.H_VERIFICADO, ahora, {"compatibilidad": compat.como_dict()}, accion_bitacora=cat.A_VERIFICADO)
                self._fila(uow, actor.id, paquete, cat.H_APLICANDO, ahora, {"orden_id": orden_id, "accion": cat.ACCION_APLICAR, "limite_minutos": orden["limite_minutos"],
                                                                         "desde_ventana": desde_ventana, "avisos": [a.como_dict() for a in compat.avisos]}, accion_bitacora=cat.A_ORDEN_EMITIDA)
                self.s.almacen.escribir_orden(orden)          # dentro de la transacción: si la escritura falla, no queda la fila `aplicando`
                filas = uow.historial.de_paquete(paquete["paquete_id"])
            self.s.vivo.marcar_en_curso(True)
        return {**paquete_a_dict(paquete, filas, ahora, self.s.config.dias_reversion), "orden": {"orden_id": orden_id, "accion": cat.ACCION_APLICAR, "limite_minutos": orden["limite_minutos"],
                                                                                                  "pasos": orden["pasos"], "emitida_en": ahora}}

    def _otra_en_curso(self, paquete_id: str) -> bool:
        with self.s.uow(lectura=True) as uow:
            for otro_id, filas in uow.historial.de_todos().items():
                if otro_id != paquete_id and derivado_de(filas, self.s.config.dias_reversion).en_curso:
                    return True
        return False

    @staticmethod
    def _fallar_por(compat: comp.Compatibilidad) -> None:
        lista = [p.como_dict() for p in compat.problemas]
        if compat.solo_espacio:
            raise EspacioInsuficiente(espacio_requerido=compat.espacio_requerido, espacio_libre=compat.espacio_libre, incompatibilidades=lista)
        if compat.ya_aplicado:
            raise YaAplicado(incompatibilidades=lista)
        if compat.serie_menor:
            raise SerieMenor(incompatibilidades=lista)
        raise ContratoIncompatible(incompatibilidades=lista)


# ------------------------------------------------------------------------------------------------------------------- revertir (FUN-186 manual, P-09)
class Revertir(_Base):
    def ejecutar(self, actor: Actor, paquete_id: str, nota: str) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_APLICAR)
        nota = str(nota or "").strip()
        if not nota:
            raise DatosInvalidos("Revertir exige una nota escrita: por qué se vuelve atrás.")
        ahora = self.ahora()
        with self.s.bloqueo:
            with self.s.uow(lectura=True) as uow:
                paquete, filas = self._paquete(uow, paquete_id)
            d = derivado_de(filas, self.s.config.dias_reversion)
            estados.exigir_revertible(d, ahora)
            if self.s.almacen.hay_orden():
                raise ActualizacionEnCurso()
            sesiones = self.s.aula.sesiones_activas()
            if sesiones > 0:
                with self.s.uow() as uow:
                    self._fila(uow, actor.id, paquete, cat.H_BLOQUEADA, ahora, {"sesiones_activas": sesiones, "motivo": dom_ventana.SESION_ACTIVA, "accion": cat.ACCION_REVERTIR},
                               accion_bitacora=cat.A_BLOQUEADA, evento=cat.EV_BLOQUEADA)
                raise SesionActiva(sesiones_activas=sesiones)
            verificado = self._leer_paquete(paquete)
            orden_id = nuevo_id()
            orden = dom_orden.armar(orden_id=orden_id, accion=cat.ACCION_REVERTIR, m=verificado.manifiesto, sha256=verificado.sha256, bytes_paquete=verificado.bytes, kid=verificado.kid,
                                    ahora=ahora, actor=actor.id, ventana=None, nota=nota[:cat.MAX_NOTA])
            with self.s.uow() as uow:
                self._fila(uow, actor.id, paquete, cat.H_APLICANDO, ahora, {"orden_id": orden_id, "accion": cat.ACCION_REVERTIR, "nota": nota[:cat.MAX_NOTA], "limite_minutos": orden["limite_minutos"]},
                           accion_bitacora=cat.A_ORDEN_EMITIDA)
                self.s.almacen.escribir_orden(orden)
                filas = uow.historial.de_paquete(paquete["paquete_id"])
            self.s.vivo.marcar_en_curso(True)
        return {**paquete_a_dict(paquete, filas, ahora, self.s.config.dias_reversion), "orden": {"orden_id": orden_id, "accion": cat.ACCION_REVERTIR, "limite_minutos": orden["limite_minutos"],
                                                                                                  "pasos": orden["pasos"], "emitida_en": ahora}}


# ------------------------------------------------------------------------------------------------------------------- consultas
class ConsultarEstado(_Base):
    def ejecutar(self, actor: Actor) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_LEER)
        return self.resumen(con_modulos=True)

    def resumen(self, con_modulos: bool = False) -> dict:
        ahora = self.ahora()
        with self.s.uow(lectura=True) as uow:
            paquetes = {p["paquete_id"]: p for p in uow.paquetes.todos()}
            historial = uow.historial.de_todos()
        fichas = [paquete_a_dict(p, historial.get(pid, []), ahora, self.s.config.dias_reversion) for pid, p in paquetes.items()]
        conteo: dict[str, int] = {}
        for f in fichas:
            conteo[f["estado"]] = conteo.get(f["estado"], 0) + 1
        en_curso = next((f for f in fichas if f["en_curso"]), None)
        programados = sorted((f for f in fichas if f["estado"] == cat.PROGRAMADO), key=lambda f: (f["ventana"] or {}).get("desde", 0))
        revertibles = [f for f in fichas if f["revertible"]]
        salida = {
            "estado": "aplicando" if en_curso else ("programado" if programados else "al_dia"),
            "en_curso": None if en_curso is None else {"paquete_id": en_curso["paquete_id"], "nombre": en_curso["nombre"], "accion": en_curso["accion"], "orden_id": en_curso["orden_id"],
                                                        "desde": en_curso["ultima_en"]},
            "programados": [{"paquete_id": f["paquete_id"], "nombre": f["nombre"], "ventana": f["ventana"]} for f in programados],
            "revertibles": [{"paquete_id": f["paquete_id"], "nombre": f["nombre"], "aplicado_en": f["aplicado_en"], "revertible_hasta": f["revertible_hasta"]} for f in revertibles],
            "paquetes": conteo, "orden_pendiente": self.s.almacen.hay_orden(), "canal": self.s.config.canal or None, "servidor_en": ahora,
        }
        if con_modulos:
            from ..dominio import registro as dom_registro
            inst = self._instalacion()
            salida["version"] = inst.version_producto
            salida["contrato_biblioteca"] = inst.contrato_biblioteca
            salida["modulos"] = [dom_registro.como_dict(m) for m in sorted(inst.modulos.values(), key=lambda x: x.nombre)]
            salida["espacio_libre"] = self.s.almacen.espacio_libre()
            salida["dias_reversion"] = self.s.config.dias_reversion
        return salida


class ListarPaquetes(_Base):
    def ejecutar(self, actor: Actor) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_LEER)
        ahora = self.ahora()
        with self.s.uow(lectura=True) as uow:
            paquetes = uow.paquetes.todos()
            historial = uow.historial.de_todos()
        fichas = [paquete_a_dict(p, historial.get(p["paquete_id"], []), ahora, self.s.config.dias_reversion) for p in paquetes]
        for f in fichas:
            f.pop("historial", None)
        # un candidato con el mismo nombre y tamaño que un paquete ya importado se marca (el técnico ve que ese archivo del USB ya entró; importarlo otra vez no crea otro paquete)
        importados = {(p.get("archivo"), int(p["bytes"])): p["paquete_id"] for p in paquetes}
        candidatos = [{**c.__dict__, "importado": importados.get((c.nombre, c.bytes))} for c in self.s.fuentes.candidatos()]
        return {"candidatos": candidatos, "paquetes": fichas, "servidor_en": ahora}


class VerPaquete(_Base):
    def ejecutar(self, actor: Actor, paquete_id: str) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_LEER)
        ahora = self.ahora()
        with self.s.uow(lectura=True) as uow:
            paquete, filas = self._paquete(uow, paquete_id)
        return paquete_a_dict(paquete, filas, ahora, self.s.config.dias_reversion)


class ConsultarHistorial(_Base):
    def ejecutar(self, actor: Actor, limite: int = 100, tipos: Iterable[str] | None = None) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_LEER)
        limite = max(1, min(int(limite or 100), 500))
        tipos_t = tuple(t for t in (tipos or ()) if t in cat.HISTORIAL) or None
        with self.s.uow(lectura=True) as uow:
            filas = uow.historial.ultimas(limite, tipos_t)
        return {"historial": [fila_a_dict(f) for f in filas], "servidor_en": self.ahora()}


# ------------------------------------------------------------------------------------------------------------------- lo que el resto del nodo pregunta
def hay_orden_en_curso(s) -> bool:
    """Para el 503 del inicio de clases (P-08): de memoria; la primera vez, del historial. Ante cualquier fallo: False (R-04: nunca se cierra el aula por esto)."""
    try:
        sabido = s.vivo.en_curso()
        if sabido is not None:
            return bool(sabido)
        with s.uow(lectura=True) as uow:
            en_curso = any(derivado_de(filas, s.config.dias_reversion).en_curso for filas in uow.historial.de_todos().values())
        s.vivo.marcar_en_curso(en_curso)
        return en_curso
    except Exception:   # noqa: BLE001 — R-04
        log.exception("No se pudo saber si hay una actualización en curso; se asume que no", extra={"evento": "actualizacion.en_curso_fallo", "ruta": "bad"})
        return False

"""
Las acciones del administrador y del técnico sobre la licencia, y las consultas que las acompañan (P-17):

    solicitud   CAP-110 · el nodo escribe su solicitud (`.avreq`): huella hasheada, nonce, versión, nivel; firmada con la llave del nodo
    activar     FUN-188 · instalar un `.avlic` sin internet (también FUN-194: volver a poner la misma licencia tras una restauración)
    renovar     FUN-191 · instalar un `.avlic` posterior de la misma licencia
    liberar     JRN-020 · el nodo viejo escribe su prueba de liberación (`.avrel`) y deja de usar la licencia
    copia       CAP-111 · el `.avlic` vigente, para guardar una copia bajo custodia de la institución (extensión: la ficha del Maestro la pide y P-17 no le da ruta)
    estado · consumo · capacidades   lo que muestra OPS (CAP-112, FUN-190) y lo que el resto consulta

Reglas que ninguna acción rompe (R-01, R-03, R-04): activar, renovar o liberar nunca detienen una clase ni tocan un dato académico; cada acción deja su asiento en la misma transacción
que el hecho (sin contenido de licencia ni huellas crudas: ids, serie, resultado y hash) y su evento; y todo archivo se verifica ANTES de mirar lo que dice.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from ..dominio import catalogos as cat
from ..dominio import huella as hu
from ..dominio import licencia as lic_mod
from ..dominio import solicitud as sol
from ..dominio import tlv
from ..dominio.errores import Conflicto, DatosInvalidos, HuellaNoCoincide, LicenciaInvalida, NoEncontrado
from ..dominio.licencia import HuellaDeLicencia, Licencia
from .base import Actor, _CasoDeUso, corto, limites_a_dict
from .evaluar import Evaluar, tumbas_a_bytes, tumbas_de
from .puertos import Instantanea


def _fecha(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d-%H%M")


def estado_a_dict(snapshot: Instantanea) -> dict:
    """La instantánea tal como la entrega la API: estado, vigencia, huella (sólo cifras y nivel), límites, módulos, avisos y consumo. Nunca la firma ni identificadores."""
    e = snapshot.estado
    licencia = snapshot.licencia
    todas = set(cat.CAPACIDADES_LICENCIABLES)
    consumo = None
    if snapshot.consumo is not None:
        consumo = {"equipos": snapshot.consumo.equipos, "usuarios": snapshot.consumo.usuarios}
    return {
        "estado": e.estado, "motivo": e.motivo, "modo": snapshot.modo, "entorno": snapshot.entorno, "tipo": e.tipo, "restringe": e.restringe, "banderas": sorted(e.banderas),
        "licencia": licencia,
        "vigencia": {"desde": licencia["desde"] if licencia else None, "vence": licencia["vence"] if licencia else None, "gracia_dias": licencia["gracia_dias"] if licencia else None,
                     "hasta": e.hasta, "dias_restantes": e.dias_restantes},
        "huella": snapshot.huella, "limites": limites_a_dict(e.limites),
        "capacidades": {"habilitadas": sorted(e.capacidades), "no_disponibles": sorted(todas - set(e.capacidades))},
        "avisos": list(snapshot.avisos), "consumo": consumo, "calculada_en": snapshot.calculada_en, "ahora": e.ahora,
    }


# ------------------------------------------------------------------------------------------------------------------------- consultas
class _Consulta(_CasoDeUso):
    def _instantanea(self) -> Instantanea:
        return self.s.vivo.leer() or Evaluar(self.s).ejecutar("demanda")


class ConsultarEstado(_Consulta):
    """CAP-112 · FUN-189: el estado de la licencia. Quien lo pide necesita `license.read`."""

    def ejecutar(self, actor: Actor) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_LEER)
        return estado_a_dict(self._instantanea())


class ConsultarConsumo(_Consulta):
    """CAP-112 · FUN-190: cuánto se usa de lo contratado. Se cuenta en el momento (dos consultas pequeñas) para que la pantalla de Licencia no muestre una cifra vieja."""

    def ejecutar(self, actor: Actor) -> dict:
        self.s.autorizacion.exigir(actor, cat.P_LEER)
        snapshot = self._instantanea()
        equipos, usuarios = self.s.conteos.equipos(), self.s.conteos.usuarios()
        lim = limites_a_dict(snapshot.estado.limites)

        def fila(en_uso: int | None, limite: int | None) -> dict:
            from ..dominio.cupo import porcentaje
            return {"en_uso": en_uso, "limite": limite, "porcentaje": None if en_uso is None or limite is None else porcentaje(en_uso, limite)}
        normal, pico = snapshot.limites_de_concurrencia or (None, None)
        return {"equipos": fila(equipos, lim["equipos"]), "usuarios": fila(usuarios, lim["usuarios"]), "concurrentes": {"normal": normal, "pico": pico}, "calculado_en": self.s.reloj.ahora_ms()}


class ConsultarCapacidades(_Consulta):
    """Cualquier sesión: qué módulos están habilitados, SIN detalles de la licencia (el profesor ve «no disponible por licencia», nunca datos de ella)."""

    def ejecutar(self, actor: Actor | None = None) -> dict:
        e = self._instantanea().estado
        todas = set(cat.CAPACIDADES_LICENCIABLES)
        return {"estado": e.estado, "restringe": e.restringe, "habilitadas": sorted(e.capacidades), "no_disponibles": sorted(todas - set(e.capacidades))}


class ConsultarCopia(_Consulta):
    """CAP-111: el archivo de la licencia vigente para guardarlo bajo custodia de la institución (OPS lo escribe en un USB junto con la solicitud y una hoja de texto). Es una LECTURA:
    no cambia nada del nodo. El archivo trae la huella hasheada, los límites y las fechas; ni claves, ni datos de personas."""

    def ejecutar(self, actor: Actor) -> dict:
        s = self.s
        s.autorizacion.exigir(actor, cat.P_LEER)
        with s.uow(lectura=True) as uow:
            fila = uow.historial.vigente()
        if fila is None or not fila["archivo"]:
            raise NoEncontrado("Este equipo no tiene una licencia instalada que copiar.", motivo="sin_licencia_instalada")
        datos = bytes(fila["archivo"])
        sha = hashlib.sha256(datos).hexdigest()
        nombre = f"licencia-{fila['licencia_id'][:8]}-serie{fila['serie']}.avlic"
        return {"archivo": datos, "texto": lic_mod.a_texto(datos), "nombre": nombre, "sha256": sha, "licencia": self._instantanea().licencia}


# ------------------------------------------------------------------------------------------------------------------------- solicitud
class GenerarSolicitud(_CasoDeUso):
    """CAP-110 (primer paso): la solicitud de licencia de ESTE equipo. Lleva la huella hasheada —nunca identificadores crudos—, un nonce, la versión y el nivel de huella."""

    def ejecutar(self, actor: Actor) -> dict:
        s = self.s
        s.autorizacion.exigir(actor, cat.P_ACTIVAR)
        ahora = s.reloj.ahora_ms()
        nivel, k, factores = hu.huella_de_solicitud(hu.factores_validos(s.huella.crudos()), s.nodo.secreto_de_instalacion())
        instantanea = s.vivo.leer()
        vigente = instantanea.licencia["id"] if instantanea is not None and instantanea.licencia else None
        datos = sol.construir_solicitud(s.nodo.clave_privada(), nonce=secrets.token_bytes(16), version_nodo=s.config.version_del_nodo, creada=ahora, nivel=nivel,
                                        huella=HuellaDeLicencia(k, tuple(sorted(factores.items()))), licencia_vigente=vigente)
        sha = hashlib.sha256(datos).hexdigest()
        with s.uow() as uow:
            uow.auditoria.registrar(actor.id, cat.A_SOLICITUD, "m18_licencia", "nodo", nuevo={"nivel": nivel, "k": k, "factores": len(factores), "archivo": corto(sha)})
        return {"archivo": datos, "texto": lic_mod.a_texto(datos, tlv.MAGIC_SOLICITUD), "nombre": f"solicitud-{_fecha(ahora)}.avreq", "nivel": nivel, "k": k, "factores": len(factores),
                "sha256": sha}


# ------------------------------------------------------------------------------------------------------------------------- activar y renovar
class Instalar(_CasoDeUso):
    """FUN-188 (activar) y FUN-191 (renovar). El archivo se verifica antes de mirar nada; se comprueba que sea para ESTE equipo; y las reglas de serie impiden volver a una licencia anterior."""

    def ejecutar(self, actor: Actor, licencia: bytes | str, via: str) -> dict:
        s = self.s
        if via not in ("activar", "renovar"):
            raise DatosInvalidos("La vía es «activar» o «renovar».")
        s.autorizacion.exigir(actor, cat.P_RENOVAR if via == "renovar" else cat.P_ACTIVAR)
        datos = lic_mod.de_texto(licencia) if isinstance(licencia, str) else bytes(licencia)
        with s.bloqueo:
            ahora = s.reloj.ahora_ms()
            try:
                lic = lic_mod.leer(datos, s.claves.publicas())
                if lic.tipo == lic_mod.TIPO_DESARROLLO and s.config.entorno == "produccion":
                    raise LicenciaInvalida("tipo_no_admitido")
                if lic.desde > ahora + s.config.politica.tolerancia_inicio_ms:
                    # Una licencia que empieza en el futuro REEMPLAZARÍA a la vigente y dejaría al nodo sin licencia hasta ese día: se rechaza (D-7). El emisor entrega `desde` ≤ el día de la
                    # entrega y expresa la vigencia extendida en `vence`. La tolerancia (un día) es la MISMA con la que `estado.calcular` decide que ya rige (D-8).
                    raise LicenciaInvalida("aun_no_vigente")
            except LicenciaInvalida as error:
                self._asentar_rechazo(actor, error, datos)
                raise
            coincidencia = hu.comparar(lic.huella, hu.factores_validos(s.huella.crudos()), hu.hash_de_factor(hu.F_INSTALACION, s.nodo.secreto_de_instalacion().hex()))
            if not coincidencia.ok:
                self._asentar_rechazo(actor, HuellaNoCoincide(), datos, motivo="huella_no_coincide")
                raise HuellaNoCoincide("Esta licencia fue emitida para otro equipo.", coinciden=coincidencia.coinciden, k=coincidencia.k)
            tipo = self._regla(actor, lic, via)
            with s.uow() as uow:
                uow.historial.insertar({"licencia_id": lic.id, "serie": lic.serie, "kid": lic.kid, "tipo": tipo, "archivo": datos, "sha256": lic.sha256, "instalada_en": ahora,
                                        "instalada_por": actor.id})
                accion, evento = {cat.H_ACTIVADA: (cat.A_ACTIVADA, cat.EV_ACTIVADA), cat.H_RENOVADA: (cat.A_RENOVADA, cat.EV_RENOVADA),
                                  cat.H_REACTIVADA: (cat.A_REACTIVADA, cat.EV_REACTIVADA)}[tipo]
                carga = {"licencia_id": lic.id, "serie": lic.serie, "tipo": lic.tipo, "archivo": corto(lic.sha256), "vence": lic.vence}
                uow.outbox.publicar("Licencia", lic.id, evento, {**carga, "instante": ahora}, clave=f"{tipo}:{lic.id}:{lic.serie}:{ahora}")
                uow.auditoria.registrar(actor.id, accion, "m18_licencia", lic.id, nuevo=carga)
            s.almacen.escribir(cat.ARCHIVO_ESPEJO, datos)
            tumbas = tumbas_de(s.almacen.leer(cat.ARCHIVO_TUMBAS))
            if (lic.id, lic.serie) in tumbas:
                tumbas.discard((lic.id, lic.serie))
                s.almacen.escribir(cat.ARCHIVO_TUMBAS, tumbas_a_bytes(tumbas))
            instantanea = Evaluar(s).ejecutar("accion")
        return {"accion": tipo, **estado_a_dict(instantanea)}

    def _regla(self, actor: Actor, lic: Licencia, via: str) -> str:
        """Qué es este archivo respecto de lo instalado: `activada`, `renovada` o `reactivada` (o se rechaza)."""
        s = self.s
        with s.uow(lectura=True) as uow:
            fila = uow.historial.vigente()
        vigente = None
        if fila is not None:
            try:
                vigente = lic_mod.leer(bytes(fila["archivo"]), s.claves.publicas())
            except LicenciaInvalida:
                vigente = None
        instantanea = s.vivo.leer()
        if via == "renovar":
            if vigente is None:
                raise LicenciaInvalida("sin_licencia_instalada")
            if lic.id != vigente.id:
                raise LicenciaInvalida("otra_licencia")
            if lic.serie <= vigente.serie or lic.emitida < vigente.emitida:
                raise LicenciaInvalida("serie_no_posterior")
            return cat.H_RENOVADA
        if vigente is None:
            return cat.H_ACTIVADA
        if lic.id == vigente.id:
            if lic.serie < vigente.serie:
                raise LicenciaInvalida("serie_no_posterior")
            if lic.serie == vigente.serie:
                return cat.H_REACTIVADA                              # el mismo archivo otra vez (FUN-194): no cambia nada, sólo se reactiva
            if not lic.huella.es_la_misma(vigente.huella):
                # D-10 · TRASLADO (JRN-020): la serie siguiente de la misma licencia, pero emitida para OTRA huella —el equipo nuevo que restauró la base del viejo, o el mismo con piezas
                # cambiadas—. El Maestro se lo da al TÉCNICO (FUN-188 · `license.activate`): no extiende nada, sólo pone la licencia donde está el equipo ahora.
                return cat.H_ACTIVADA
            s.autorizacion.exigir(actor, cat.P_RENOVAR)              # misma huella, serie posterior: una renovación (FUN-191), aunque venga por «activar»
            return cat.H_RENOVADA
        if instantanea is not None and instantanea.estado.estado in (cat.ACTIVA, cat.REACTIVADA):
            raise LicenciaInvalida("otra_licencia")                  # con una licencia sana no se cambia por otra: primero se libera este equipo
        return cat.H_ACTIVADA

    def _asentar_rechazo(self, actor: Actor, error: LicenciaInvalida | HuellaNoCoincide, datos: bytes, motivo: str | None = None) -> None:
        """Un archivo cuya firma o llave no valen es un hecho auditable (`licencia.firma_invalida`); lo demás es un error de uso. Nunca lleva el contenido del archivo."""
        motivo = motivo or getattr(error, "motivo", "")
        if motivo not in ("firma_invalida", "kid_desconocido", "etiqueta_critica_desconocida", "huella_no_coincide"):
            return
        try:
            with self.s.uow() as uow:
                uow.auditoria.registrar(actor.id, cat.A_FIRMA_INVALIDA, "m18_licencia", "nodo", resultado="denegado",
                                        nuevo={"motivo": motivo, "bytes": len(datos), "archivo": corto(hashlib.sha256(datos).hexdigest())})
        except Exception:   # noqa: BLE001 — el rechazo ya se dio; el asiento es evidencia, no condición
            pass


# ------------------------------------------------------------------------------------------------------------------------- liberar
class Liberar(_CasoDeUso):
    """JRN-020: «Liberar este equipo». El nodo escribe su `.avrel` firmado con su llave y deja de usar la licencia. Se puede deshacer volviendo a activar el mismo archivo."""

    def ejecutar(self, actor: Actor) -> dict:
        s = self.s
        s.autorizacion.exigir(actor, cat.P_ACTIVAR)
        with s.bloqueo:
            ahora = s.reloj.ahora_ms()
            with s.uow(lectura=True) as uow:
                fila = uow.historial.vigente()
            if fila is None:
                raise Conflicto("Este equipo no tiene una licencia instalada que liberar.", motivo="sin_licencia_instalada")
            try:
                lic = lic_mod.leer(bytes(fila["archivo"]), s.claves.publicas())
            except LicenciaInvalida:
                lic = None
            licencia_id, serie = (lic.id, lic.serie) if lic is not None else (fila["licencia_id"], int(fila["serie"]))
            datos = sol.construir_liberacion(s.nodo.clave_privada(), licencia_id=licencia_id, serie=serie, liberada=ahora, nonce=secrets.token_bytes(16))
            sha = hashlib.sha256(datos).hexdigest()
            with s.uow() as uow:
                uow.historial.insertar({"licencia_id": licencia_id, "serie": serie, "kid": fila.get("kid", ""), "tipo": cat.H_LIBERADA, "archivo": None, "sha256": sha, "instalada_en": ahora,
                                        "instalada_por": actor.id})
                carga = {"licencia_id": licencia_id, "serie": serie, "archivo": corto(sha)}
                uow.outbox.publicar("Licencia", licencia_id, cat.EV_LIBERADA, {**carga, "instante": ahora}, clave=f"liberada:{licencia_id}:{serie}:{ahora}")
                uow.auditoria.registrar(actor.id, cat.A_LIBERADA, "m18_licencia", licencia_id, nuevo=carga)
            tumbas = tumbas_de(s.almacen.leer(cat.ARCHIVO_TUMBAS))
            tumbas.add((licencia_id, serie))
            s.almacen.escribir(cat.ARCHIVO_TUMBAS, tumbas_a_bytes(tumbas))
            s.almacen.borrar(cat.ARCHIVO_ESPEJO)
            instantanea = Evaluar(s).ejecutar("accion")
        return {"archivo": datos, "texto": lic_mod.a_texto(datos, tlv.MAGIC_LIBERACION), "nombre": f"liberacion-{_fecha(ahora)}.avrel", "licencia_id": licencia_id, "serie": serie,
                "sha256": sha, **estado_a_dict(instantanea)}


# ------------------------------------------------------------------------------------------------------------------------- reloj
class ConfirmarReloj(_CasoDeUso):
    """P-06: ante un salto del reloj hacia adelante el nodo NO degrada a nadie: avisa y espera. Quien administra confirma que la fecha de hoy es la correcta y la sospecha se apaga."""

    def ejecutar(self, actor: Actor) -> dict:
        s = self.s
        s.autorizacion.exigir(actor, cat.P_ACTIVAR)
        with s.bloqueo:
            ahora = s.reloj.ahora_ms()
            with s.uow() as uow:
                uow.observaciones.registrar(cat.O_CONFIRMADO, ahora, detalle={})
                uow.auditoria.registrar(actor.id, cat.A_RELOJ_CONFIRMADO, "m18_licencia", "nodo", nuevo={"instante": ahora})
            instantanea = Evaluar(s).ejecutar("accion")
        return estado_a_dict(instantanea)

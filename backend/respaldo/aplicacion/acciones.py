"""
Los casos de uso de MOD-016 que se piden desde fuera (la API y el vigilante). Aquí se decide QUIÉN puede y bajo qué condiciones; lo que se hace de verdad está en `motor.py`. Sin Django.

QUIÉN (D-1, D-2): respaldar, programar, verificar, exportar y restaurar son SÓLO del personal técnico de AVACOM WORLD.

  · `backup.read` (estado, respaldos, constancias): la administración y el técnico, sin datos de personas.
  · `backup.run`, `backup.schedule`, `backup.verify`: el técnico. La administración de la institución NO los tiene.
  · `backup.export`, `backup.restore`, `backup.restore.module`: el técnico Y un PASE DE SOPORTE firmado por AVACOM, de un solo uso (reemplaza la escalada ESC-01/ESC-03 del Maestro).
"""
from __future__ import annotations

import base64
import binascii

from ..dominio import catalogos as cat
from ..dominio import cripto, informes, pase as dominio_pase, programacion
from ..dominio.errores import (CustodiaYaEmitida, DatosInvalidos, ModuloSinRestauracionAislada, NoEncontrado, PaseInvalido, PaseRequerido)
from .base import Servicios, _CasoDeUso, corto
from .motor import Motor
from .puertos import Actor


class _Accion(_CasoDeUso):
    def __init__(self, servicios: Servicios):
        super().__init__(servicios)
        self.motor = Motor(servicios)

    def _exigir(self, actor: Actor, permiso: str) -> None:
        self.s.autorizacion.exigir(actor, permiso)

    def _pase(self, actor: Actor, permiso: str, pase_b64: object):
        """Verifica el pase de soporte de AVACOM (firma, vigencia, operación y equipo) SIN gastarlo: se gasta cuando la operación ya no tiene vuelta atrás."""
        if not pase_b64:
            raise PaseRequerido()
        try:
            datos = base64.b64decode(str(pase_b64), validate=True)
        except (binascii.Error, ValueError):
            raise DatosInvalidos("`pase` debe ir en base64.", campo="pase") from None
        try:
            return dominio_pase.abrir(datos, self.s.soporte.llaves_publicas(), self.ahora(), permiso, self.s.clavero.nodo_id())
        except PaseInvalido as error:
            with self.s.uow() as uow:
                uow.auditoria.registrar(actor.id, cat.A_PASE_RECHAZADO, "m16_pase_usado", "", nuevo={"permiso": permiso, "motivo": error.motivo})
            raise


# ------------------------------------------------------------------------------------------------------------------- lectura (backup.read)
class ConsultarEstado(_Accion):
    def ejecutar(self, actor: Actor) -> dict:
        self._exigir(actor, cat.P_LEER)
        return self.resumen()

    def resumen(self) -> dict:
        s, ahora = self.s, self.ahora()
        with s.uow(lectura=True) as uow:
            fichas = self.motor.fichas(uow)
            programa = self.motor.programa(uow)
        existentes = [f for f in fichas if f["existe"]]
        restaurables = [f for f in fichas if f["restaurable"]]
        ultimo = max(restaurables, key=lambda f: f["ejecutado_en"] or 0, default=None)
        dias = None if ultimo is None else max(0, (ahora - int(ultimo["ejecutado_en"] or 0)) // cat.DIA_MS)
        desfase = s.reloj.desfase_min()
        custodia = s.clavero.custodia()
        marcha = s.vivo.en_marcha()
        cuentas: dict[str, int] = {}
        for f in fichas:
            cuentas[f["estado"]] = cuentas.get(f["estado"], 0) + 1
        return {
            "nodo": corto(s.clavero.nodo_id()), "programacion": programacion.a_dict(programa), "siguiente_en": programacion.siguiente_horario(programa, ahora, desfase),
            "ultimo_restaurable": self._resumen_de(ultimo), "ultimo": self._resumen_de(max(existentes, key=lambda f: f["creado_en"], default=None)),
            "dias_sin_respaldo": dias, "aviso_sin_respaldo": dias is None or dias >= s.config.aviso_sin_respaldo_dias,
            "en_marcha": None if not marcha else {"respaldo_id": marcha["respaldo_id"], "operacion": marcha["operacion"], "desde": marcha["en"]},
            "aplazado_por_clase": s.vivo.aplazado_por_clase(),
            "custodia": {"emitida": custodia is not None, "emitida_en": None if custodia is None else custodia["emitida_en"]},
            "espacio_libre": s.almacen.espacio_libre(), "unidades": [{"id": u.id, "rotulo": u.rotulo, "libre_bytes": u.libre_bytes} for u in s.unidades.listar()],
            "respaldos": cuentas, "total": len(fichas), "informes": s.almacen.listar_informes(),
        }

    @staticmethod
    def _resumen_de(f: dict | None) -> dict | None:
        if f is None:
            return None
        return {k: f[k] for k in ("respaldo_id", "tipo", "estado", "creado_en", "verificado_en", "bytes", "exportado")}


class ListarRespaldos(_Accion):
    def ejecutar(self, actor: Actor, limite: int = 100) -> dict:
        self._exigir(actor, cat.P_LEER)
        with self.s.uow(lectura=True) as uow:
            fichas = self.motor.fichas(uow)
        return {"respaldos": fichas[:max(1, min(int(limite), 500))], "total": len(fichas)}


class VerRespaldo(_Accion):
    def ejecutar(self, actor: Actor, respaldo_id: str) -> dict:
        self._exigir(actor, cat.P_LEER)
        with self.s.uow(lectura=True) as uow:
            ficha = self.motor.ficha(uow, respaldo_id)
            filas = uow.historial.de_respaldo(respaldo_id)
        from .base import fila_a_dict
        return {**ficha, "historial": [fila_a_dict(f) for f in filas]}


class ObtenerConstancia(_Accion):
    """La constancia de un respaldo en texto llano, para la administración (JRN-018: «ve el último con su fecha»). Sin datos de personas."""

    def ejecutar(self, actor: Actor, respaldo_id: str) -> dict:
        self._exigir(actor, cat.P_LEER)
        with self.s.uow(lectura=True) as uow:
            ficha = self.motor.ficha(uow, respaldo_id)
        return {"nombre": self.motor.nombre_de_constancia(ficha, self.s.reloj.desfase_min()),
                "texto": informes.constancia(ficha, self.s.nodo.institucion(), self.s.reloj.desfase_min())}


class ObtenerResumen(_Accion):
    def ejecutar(self, actor: Actor) -> dict:
        self._exigir(actor, cat.P_LEER)
        with self.s.uow(lectura=True) as uow:
            fichas = self.motor.fichas(uow)
        return {"nombre": "resumen-de-respaldos.csv",
                "texto": informes.resumen_csv([f for f in fichas if f["archivo"] or f["estado"] == cat.E_FALLIDO], self.s.reloj.desfase_min())}


class LeerInforme(_Accion):
    def ejecutar(self, actor: Actor, nombre: str) -> dict:
        self._exigir(actor, cat.P_LEER)
        texto = self.s.almacen.leer_informe(nombre) if nombre in self.s.almacen.listar_informes() else None
        if texto is None:
            raise NoEncontrado("No existe ese informe.")
        return {"nombre": nombre, "texto": texto}


class ListarDestinos(_Accion):
    """Las unidades extraíbles conectadas y los respaldos que traen (para exportar y para restaurar en un equipo nuevo). Ids opacos: nunca una ruta."""

    def ejecutar(self, actor: Actor) -> dict:
        self._exigir(actor, cat.P_LEER)
        return {"unidades": [{"id": u.id, "rotulo": u.rotulo, "libre_bytes": u.libre_bytes} for u in self.s.unidades.listar()],
                "candidatos": [{"id": c.id, "nombre": c.nombre, "bytes": c.bytes, "fuente": c.fuente} for c in self.s.unidades.candidatos()]}


# ------------------------------------------------------------------------------------------------------------------- el personal de AVACOM
class Programar(_Accion):
    """FUN-169."""

    def ejecutar(self, actor: Actor, datos: dict) -> dict:
        self._exigir(actor, cat.P_PROGRAMAR)
        with self.s.uow() as uow:
            nuevo = programacion.validar({k: v for k, v in (datos or {}).items() if k in programacion.a_dict(programacion.Programa())}, self.motor.programa(uow))
            ahora = self.ahora()
            uow.ajuste.guardar({**programacion.a_dict(nuevo), "dias": list(nuevo.dias)}, ahora, actor.id)
            self.motor._h(uow, "", cat.H_PROGRAMADO, actor.id, programacion.a_dict(nuevo))
            uow.auditoria.registrar(actor.id, cat.A_PROGRAMADO, "m16_ajuste", "1", nuevo=programacion.a_dict(nuevo))
            uow.eventos.publicar("Respaldo", f"programa:{ahora}", cat.EV_PROGRAMADO, {**programacion.a_dict(nuevo), "instante": ahora})
        return {"programacion": programacion.a_dict(nuevo), "siguiente_en": programacion.siguiente_horario(nuevo, self.ahora(), self.s.reloj.desfase_min())}


class EmitirCustodia(_Accion):
    """BR-102 · el código de custodia de la institución. Se muestra UNA vez y el equipo no lo guarda: sólo conserva la clave derivada, envuelta con la suya."""

    def ejecutar(self, actor: Actor, reemplazar: bool = False) -> dict:
        self._exigir(actor, cat.P_PROGRAMAR)
        s = self.s
        actual = s.clavero.custodia()
        if actual is not None and not reemplazar:
            raise CustodiaYaEmitida("La institución ya tiene un código de custodia. Si se perdió, repite pidiendo `reemplazar`: los respaldos anteriores seguirán abriéndose en este equipo.")
        codigo = cripto.generar_codigo_de_custodia()
        secreto, sal = cripto.secreto_de_custodia(codigo), cripto.generar_sal()
        ahora = self.ahora()
        s.clavero.guardar_custodia(ahora, sal, cripto.clave_de_custodia(secreto, sal))
        with s.uow() as uow:
            self.motor._h(uow, "", cat.H_CUSTODIA, actor.id, {"reemplazo": actual is not None})
            uow.auditoria.registrar(actor.id, cat.A_CUSTODIA, "m16_ajuste", "1", nuevo={"reemplazo": actual is not None})
            uow.eventos.publicar("Respaldo", f"custodia:{ahora}", cat.EV_CUSTODIA, {"reemplazo": actual is not None, "instante": ahora})
        hoja = informes.hoja_de_custodia(codigo, s.clavero.nodo_id(), ahora, s.nodo.institucion(), s.reloj.desfase_min())
        return {"codigo": codigo, "hoja": hoja, "emitida_en": ahora, "siguiente_paso": "Imprime la hoja, entrégala a la institución y haz un respaldo completo nuevo: sólo los respaldos hechos desde ahora se abren en otro equipo."}


class RespaldarAhora(_Accion):
    """JRN-018 · «Respaldar ahora»."""

    def ejecutar(self, actor: Actor, tipo: str = cat.T_COMPLETO) -> dict:
        self._exigir(actor, cat.P_EJECUTAR)
        if tipo not in cat.TIPOS:
            raise DatosInvalidos(f"`tipo` es uno de {', '.join(cat.TIPOS)}.", campo="tipo")
        return self.motor.respaldar(actor, tipo, cat.D_MANUAL)


class Verificar(_Accion):
    """FUN-173."""

    def ejecutar(self, actor: Actor, respaldo_id: str, custodia: str | None = None) -> dict:
        self._exigir(actor, cat.P_VERIFICAR)
        return self.motor.verificar(actor, respaldo_id, custodia)


class Exportar(_Accion):
    """FUN-176 · a una unidad extraíble. Sacar datos del equipo: backup.export + pase de soporte."""

    def ejecutar(self, actor: Actor, respaldo_id: str, unidad_id: str, pase_b64: object) -> dict:
        self._exigir(actor, cat.P_EXPORTAR)
        if not unidad_id:
            raise DatosInvalidos("Indica la unidad.", campo="unidad")
        pase = self._pase(actor, cat.P_EXPORTAR, pase_b64)
        if not any(u.id == unidad_id for u in self.s.unidades.listar()):
            raise NoEncontrado("Esa unidad ya no está conectada.")
        with self.s.uow() as uow:
            if not uow.pases.usar(pase.pase_id, self.ahora(), cat.P_EXPORTAR, pase.tecnico, pase.kid, respaldo_id):
                raise PaseInvalido("ya_usado")
        return self.motor.exportar(actor, respaldo_id, unidad_id)


class Restaurar(_Accion):
    """FUN-174 · devolver el equipo a un respaldo. Backup.restore + pase de soporte + una clase cerrada de motivos."""

    def ejecutar(self, actor: Actor, datos: dict) -> dict:
        self._exigir(actor, cat.P_RESTAURAR)
        datos = datos or {}
        respaldo_id, candidato_id = str(datos.get("respaldo_id") or ""), str(datos.get("candidato") or "")
        if bool(respaldo_id) == bool(candidato_id):
            raise DatosInvalidos("Indica `respaldo_id` (uno del equipo) o `candidato` (uno de una unidad), no los dos ni ninguno.", campo="respaldo_id")
        motivo = str(datos.get("motivo") or "")
        if motivo not in cat.MOTIVOS_DE_RESTAURACION:
            raise DatosInvalidos(f"`motivo` es uno de {', '.join(cat.MOTIVOS_DE_RESTAURACION)}.", campo="motivo")
        nota = str(datos.get("nota") or "")
        if len(nota) > cat.MAX_NOTA:
            raise DatosInvalidos(f"`nota` admite hasta {cat.MAX_NOTA} caracteres.", campo="nota")
        custodia = str(datos["custodia"]) if datos.get("custodia") else None
        if custodia is not None and cripto.secreto_de_custodia(custodia) is None:
            raise DatosInvalidos("El código de custodia no es válido: revisa que esté completo.", campo="custodia")
        pase = self._pase(actor, cat.P_RESTAURAR, datos.get("pase"))
        return self.motor.restaurar(actor, respaldo_id=respaldo_id or None, candidato_id=candidato_id or None, custodia=custodia, motivo=motivo, nota=nota, pase=pase)


class RestaurarModulo(_Accion):
    """FUN-175 · «el módulo declara su restauración aislada». Hoy ninguno la declara: se dice con claridad en vez de restaurar tablas sueltas (BR-003)."""

    def ejecutar(self, actor: Actor, datos: dict) -> dict:
        self._exigir(actor, cat.P_RESTAURAR_MODULO)
        datos = datos or {}
        modulo = str(datos.get("modulo") or "")
        if not modulo:
            raise DatosInvalidos("Indica el módulo.", campo="modulo")
        self._pase(actor, cat.P_RESTAURAR_MODULO, datos.get("pase"))
        if not self.s.modulos.declara_restauracion_aislada(modulo):
            raise ModuloSinRestauracionAislada(f"El módulo `{modulo}` no declara restauración aislada: sólo se restaura el equipo completo.", modulo=modulo)
        raise ModuloSinRestauracionAislada("La restauración aislada todavía no está construida (V1, CAP-102).", modulo=modulo)

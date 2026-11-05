"""
Los permisos de MOD-016 (D-1, D-2, D-3). MOD-001 los siembra (`acceso.dominio.plantillas`, migración `acceso/0021`) y aquí se evalúan con SU política, en el nodo:

  backup.read             ver el estado, los respaldos y las constancias, sin datos de personas   (administración y técnico)
  backup.run              «Respaldar ahora»                                                       (técnico)
  backup.schedule         programar el calendario y emitir el código de custodia                   (técnico)
  backup.verify           verificar la restaurabilidad de un respaldo                              (técnico)
  backup.export           sacar un respaldo a una unidad extraíble                                  (técnico + PASE de AVACOM)
  backup.restore          restaurar el equipo                                                      (técnico + PASE de AVACOM)
  backup.restore.module   restaurar un módulo (V1)                                                 (técnico + PASE de AVACOM)

El Maestro pide la escalada temporal ESC-01/ESC-03 (la concede la administración) para estos tres. Aquí la administración NO tiene el permiso, y en MOD-001 nadie concede un permiso que no
tiene: la escalada no existiría. La llave de la segunda persona la da el PASE DE SOPORTE de AVACOM (D-2): firmado, de un solo uso y de un día como máximo.

Respaldar y restaurar son del personal de AVACOM WORLD, no de la institución: la administración sólo LEE (D-1). Para que eso no dependa de cómo se compongan los roles, las operaciones del
personal de AVACOM además exigen que el ROL EFECTIVO de la sesión sea `TECHNICIAN`: un rol personalizado con `backup.*` compuesto por la administración no basta (D-3). Y no hay rama «sin
sesión»: a diferencia de los módulos del prototipo (Q-34), un respaldo jamás se pide de forma anónima.
"""
from __future__ import annotations

from ..aplicacion.puertos import Actor
from ..dominio import catalogos as cat
from ..dominio.errores import SinPermiso

ROL_DE_AVACOM = "TECHNICIAN"


def _alcance(actor: Actor, permiso: str):
    """El alcance con que el rol efectivo del actor tiene el permiso, o None si no lo tiene. Es la política de MOD-001, no una copia de ella."""
    from acceso.aplicacion import casos_uso as acu
    from acceso.infraestructura.contenedor import servicios as servicios_acceso

    s = servicios_acceso()
    base = acu.Base(s)
    with s.uow() as uow:
        ctx = base.contexto(uow, actor.principal)
        previa = base.politica.transversal(ctx, permiso)
        if previa is not None:
            if previa.codigo == "sesion_visitante_limitada":
                previa.exigir()
            return None
        return base.politica.alcance_concedido(ctx, permiso)


class AutorizacionRespaldo:
    def exigir(self, actor: Actor, permiso: str) -> None:
        if permiso not in cat.PERMISOS:
            raise ValueError(f"Permiso fuera del catálogo de MOD-016: {permiso}")
        if not actor.autenticado or actor.principal is None:
            raise SinPermiso("Respaldar y restaurar exigen iniciar sesión.", permiso=permiso)
        if permiso in cat.PERMISOS_DE_AVACOM and actor.rol != ROL_DE_AVACOM:
            raise SinPermiso("Respaldar y restaurar el equipo es del personal técnico de AVACOM.", permiso=permiso)
        if actor.nivel < 2 or _alcance(actor, permiso) is None:
            raise SinPermiso(f"Tu rol no tiene concedido {permiso}.", permiso=permiso)

    def puede(self, actor: Actor, permiso: str) -> bool:
        try:
            self.exigir(actor, permiso)
            return True
        except SinPermiso:
            return False

"""
Los permisos de licenciamiento. MOD-001 los siembra (`acceso.dominio.plantillas`, migración `acceso/0018`) y aquí se evalúan con SU política, en el nodo:

  license.read      ver el estado y el consumo de la licencia (sin datos de personas): técnico y administración
  license.activate  pedir la solicitud, activar, reactivar, liberar y confirmar la fecha: técnico y administración
  license.renew     renovar con un archivo posterior: administración

El profesor, Reportes y el alumno NO tienen ninguno: ven «no disponible por licencia» cuando un módulo se apaga, jamás datos de la licencia (P-15).

  - Con sesión: el permiso debe estar concedido por el rol efectivo (alcance de toda la organización: una licencia es del nodo, no de un grupo).
  - Sin sesión (Q-34, prototipo): se permite, como en los demás módulos; con AVACOM_LMS_EXIGIR_SESION=1 esa rama no existe, porque las vistas ya rechazan lo que no trae sesión.
"""
from __future__ import annotations

from ..aplicacion.puertos import Actor
from ..dominio import catalogos as cat
from ..dominio.errores import SinPermiso


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


class AutorizacionLicencia:
    def exigir(self, actor: Actor, permiso: str) -> None:
        if permiso not in cat.PERMISOS:
            raise ValueError(f"Permiso fuera del catálogo de MOD-018: {permiso}")
        if not actor.autenticado or actor.principal is None:
            return
        if actor.nivel < 2 or _alcance(actor, permiso) is None:
            raise SinPermiso(f"Tu rol no tiene concedido {permiso}.", permiso=permiso)

    def puede(self, actor: Actor, permiso: str) -> bool:
        if not actor.autenticado or actor.principal is None:
            return True
        if actor.nivel < 2:
            return False
        try:
            return _alcance(actor, permiso) is not None
        except SinPermiso:
            return False

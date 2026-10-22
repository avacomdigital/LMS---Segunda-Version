"""
Los permisos de MOD-017 (P-10, C-8). MOD-001 los siembra (`acceso.dominio.plantillas`, migración `acceso/0020`) y aquí se evalúan con SU política, en el nodo:

  update.apply            aplicar y revertir (Maestro: administración «sí»; técnico sólo por escalada temporal ESC-01, 4 h)
  update.package.import   importar un paquete desde una unidad o la carpeta de entrada (ficha J; extensión marcada: técnico y administración)
  update.schedule         programar y cancelar la ventana (ficha J; extensión marcada: administración)
  update.read             ver el estado, los paquetes y el historial, sin datos de personas (extensión técnica propuesta: técnico y administración)

El profesor, Reportes y el alumno NO tienen ninguno: nunca ven esta pantalla.

  - Con sesión: el permiso debe estar concedido por el rol efectivo (alcance de toda la organización: una actualización es del nodo).
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


class AutorizacionActualizacion:
    def exigir(self, actor: Actor, permiso: str) -> None:
        if permiso not in cat.PERMISOS:
            raise ValueError(f"Permiso fuera del catálogo de MOD-017: {permiso}")
        if actor.id == cat.SISTEMA and not actor.autenticado:
            return                                                     # el vigilante (ventanas) y el arranque actúan por el nodo
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

"""
Los permisos de MOD-015. MOD-001 los siembra (`acceso.dominio.plantillas`, migración `acceso/0019`) y aquí se evalúan con SU política, en el nodo:

  node.queue.replay     reprocesar un evento apartado y reproducir un consumidor (FUN-164): la administración; el técnico sólo por escalada temporal (PAN-241)
  node.queue.read       ver la cola por consumidor y los problemas, SIN carga útil (extensión técnica propuesta): administración y técnico
  node.health.read      ver el estado del nodo y su salud (extensión técnica propuesta): administración y técnico

  - Con sesión: el permiso debe estar concedido por el rol efectivo (o por una escalada vigente: `concesiones_efectivas` las suma).
  - Sin sesión (Q-34, prototipo): se permite, igual que en el resto de módulos. Con AVACOM_LMS_EXIGIR_SESION=1 esa rama no existe (las vistas ya rechazan lo anónimo).
"""
from __future__ import annotations

from ..aplicacion.puertos import Actor
from ..dominio import catalogos as cat
from ..dominio.errores import SinPermiso


def _concedido(actor: Actor, permiso: str) -> bool:
    """¿El rol efectivo del actor (más su escalada vigente) tiene el permiso? Es la política de MOD-001, no una copia de ella."""
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
            return False
        return base.politica.alcance_concedido(ctx, permiso) is not None


class AutorizacionNodo:
    def exigir(self, actor: Actor, permiso: str) -> None:
        if permiso not in cat.PERMISOS:
            raise ValueError(f"Permiso fuera del catálogo de MOD-015: {permiso}")
        if not actor.autenticado or actor.principal is None:
            return
        if actor.nivel < 2:
            raise SinPermiso("La cola del nodo es del personal técnico y de la administración.", permiso=permiso)
        if not _concedido(actor, permiso):
            raise SinPermiso(f"Tu rol no tiene concedido {permiso}." + (" El técnico lo recibe por una escalada temporal de la administración." if permiso == cat.P_REPLAY else ""),
                             permiso=permiso)

    def puede(self, actor: Actor, permiso: str) -> bool:
        if not actor.autenticado or actor.principal is None:
            return True
        if actor.nivel < 2:
            return False
        try:
            return _concedido(actor, permiso)
        except SinPermiso:
            return False


class AutorizacionAbierta:
    """Para las pruebas de aplicación: todo se permite."""

    def exigir(self, actor: Actor, permiso: str) -> None:
        return None

    def puede(self, actor: Actor, permiso: str) -> bool:
        return True

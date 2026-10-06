"""
Los ocho permisos `study.*` (§3 del contrato). MOD-001 los siembra (`acceso.dominio.plantillas`, migración `acceso/0007`) y aquí se evalúan con SU
política, en el nodo y con su reloj: quien concede el permiso es el rol (sólo el alumno tiene los seis de estudio; el profesor y la administración
tienen `study.assignment.create` y `study.assignment.review`).

  - Con sesión: el permiso debe estar concedido por el rol efectivo. Un alumno nunca asigna trabajo (nivel 1); el profesor y la administración no
    tienen los del alumno («la administración no accede al modo de estudio del alumno»): 403 `sin_permiso`.
  - Sin sesión (Q-34 abierta, prototipo): se permite, igual que en el expediente, MOD-009 y el aula; la persona la declara el cliente (D-15) o, si
    no la declara, la fija el aparato asignado. Con AVACOM_LMS_EXIGIR_SESION=1 esa rama no existe: las vistas ya rechazan lo que no trae sesión.
"""
from __future__ import annotations

from ..aplicacion.puertos import Actor
from ..dominio import catalogos as cat
from ..dominio.errores import SinPermiso


class AutorizacionEstudio:
    def exigir(self, actor: Actor, permiso: str) -> None:
        if permiso not in cat.PERMISOS:
            raise ValueError(f"Permiso fuera del catálogo de MOD-008: {permiso}")
        if not actor.autenticado or actor.principal is None:
            return
        if permiso in cat.PERMISOS_DEL_DOCENTE and actor.nivel < 2:
            raise SinPermiso(f"La función exige {permiso}; un alumno no asigna trabajo.", permiso=permiso)
        if not self._concedido(actor, permiso):
            raise SinPermiso(f"Tu rol no tiene concedido {permiso}.", permiso=permiso)

    @staticmethod
    def _concedido(actor: Actor, permiso: str) -> bool:
        from acceso.aplicacion import casos_uso as acu
        from acceso.infraestructura.contenedor import servicios as servicios_acceso

        s = servicios_acceso()
        base = acu.Base(s)
        with s.uow() as uow:
            ctx = base.contexto(uow, actor.principal)
            previa = base.politica.transversal(ctx, permiso)
            if previa is not None:
                # RN-43: a una sesión de visitante se le dice qué es (`sesion_visitante_limitada`), no sólo que «su rol no lo tiene».
                if previa.codigo == "sesion_visitante_limitada":
                    previa.exigir()
                return False
            return base.politica.alcance_concedido(ctx, permiso) is not None

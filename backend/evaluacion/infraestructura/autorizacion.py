"""
Los permisos `assessment.*` (§10.3 del modelo). MOD-001 los siembra (`acceso.dominio.plantillas`, migración `acceso/0009`) y aquí se evalúan con SU
política, en el nodo y con su reloj: quien concede el permiso es el rol (el alumno tiene los tres de su intento; el profesor y la administración, los
de asignar, vigilar, reactivar, anular y revisar).

  - Con sesión: el permiso debe estar concedido por el rol efectivo. Un alumno (nivel 1) nunca opera la evaluación del profesor; el personal no tiene los
    permisos del intento del alumno («el administrador no accede al intento del alumno»): 403 `sin_permiso`. Sobre una asignación concreta, el profesor
    debe ser su titular (quien la creó o docente del grupo) o la administración (nivel 3): 403 `no_es_el_titular`.
  - Sin sesión (Q-34 abierta, prototipo): se permite, igual que en el expediente, MOD-009, el aula y el modo de estudio; la persona la declara el cliente.
    Con AVACOM_LMS_EXIGIR_SESION=1 esa rama no existe, porque las vistas ya rechazan lo que no trae sesión.
"""
from __future__ import annotations

from ..aplicacion.puertos import Actor
from ..dominio import catalogos as cat
from ..dominio.errores import NoEsElTitular, SinPermiso


class AutorizacionEvaluacion:
    def exigir(self, actor: Actor, permiso: str, asignacion: dict | None = None) -> None:
        if permiso not in cat.PERMISOS:
            raise ValueError(f"Permiso fuera del catálogo de MOD-010: {permiso}")
        if not actor.autenticado or actor.principal is None:
            return
        if permiso in cat.PERMISOS_DEL_DOCENTE and actor.nivel < 2:
            raise SinPermiso(f"La función exige {permiso}; un alumno no opera la evaluación.", permiso=permiso)
        if permiso in cat.PERMISOS_DEL_ALUMNO and actor.nivel >= 2:
            raise SinPermiso(f"La función exige {permiso}, que sólo tiene el alumno sobre su propio intento.", permiso=permiso)
        if not self._concedido(actor, permiso):
            raise SinPermiso(f"Tu rol no tiene concedido {permiso}.", permiso=permiso)
        if asignacion is not None and actor.nivel == 2 and not self._es_titular(actor, asignacion):
            raise NoEsElTitular(f"La evaluación es de {asignacion.get('profesor_rotulo') or 'otro profesor'}: sólo su titular o la administración la opera.",
                                permiso=permiso, profesor_id=asignacion.get("profesor_id"))

    @staticmethod
    def _es_titular(actor: Actor, asignacion: dict) -> bool:
        if asignacion.get("profesor_id") in ("", actor.id):
            return True
        grupo_id = asignacion.get("grupo_id")
        if not grupo_id:
            return False
        from acceso.models import MiembroGrupo
        return MiembroGrupo.objects.filter(grupo_id=grupo_id, usuario_id=actor.id, papel="DOCENTE", hasta__isnull=True).exists()

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

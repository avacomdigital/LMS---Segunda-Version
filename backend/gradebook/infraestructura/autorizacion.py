"""
Los permisos del Gradebook. MOD-001 los siembra (`acceso.dominio.plantillas`, migración `acceso/0014`) y aquí se evalúan con SU política, en el nodo:

  grades.modify · grades.reopen · grades.rubric.apply   calificar es del PROFESOR sobre SUS grupos
  grades.publish                                        extensión técnica propuesta: publicar es del profesor
  grades.mode.set · grades.export                       configurar y exportar son de la ADMINISTRACIÓN
  results.read                                          leer el libro: el profesor sobre sus grupos; administración y reportes, toda la organización

  - Con sesión: el permiso debe estar concedido por el rol efectivo, y su ALCANCE debe llegar al grupo: el profesor sólo opera los grupos de los que es docente.
    El técnico no tiene ninguno (sin acceso a datos académicos); el alumno sólo lee lo suyo (`exigir_alumno`); la administración no califica directamente.
  - Sin sesión (Q-34, prototipo): se permite, igual que en la evaluación, el aula y el modo de estudio; la persona la declara el cliente. Con
    AVACOM_LMS_EXIGIR_SESION=1 esa rama no existe, porque las vistas ya rechazan lo que no trae sesión.
"""
from __future__ import annotations

from ..aplicacion.puertos import Actor
from ..dominio import catalogos as cat
from ..dominio.errores import AlumnoDesconocido, FaltaAlumno, FueraDeAlcance, SinPermiso
from .identidad import IdentidadAcceso

CATALOGO = cat.PERMISOS + (cat.P_READ,)


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
            if previa.codigo == "sesion_visitante_limitada":       # RN-43: a una visita se le dice qué es, no sólo que «su rol no lo tiene»
                previa.exigir()
            return None
        return base.politica.alcance_concedido(ctx, permiso)


class AutorizacionGradebook:
    def exigir(self, actor: Actor, permiso: str, *, grupo_id: str = "", organizacion: bool = False) -> None:
        """Sin `grupo_id` sólo se comprueba que el rol tenga el permiso; con `organizacion=True` además que lo tenga sobre TODA la organización (lo que se exige a
        lo que no pertenece a ningún grupo: no se deja pasar a quien sólo opera los suyos)."""
        if permiso not in CATALOGO:
            raise ValueError(f"Permiso fuera del catálogo de MOD-011: {permiso}")
        if not actor.autenticado or actor.principal is None:
            return
        if permiso == cat.P_READ and actor.nivel < 2:
            raise SinPermiso("El libro de un grupo es del personal: el alumno consulta sus propios resultados.", permiso=permiso)
        alcance = _alcance(actor, permiso)
        if alcance is None:
            raise SinPermiso(f"Tu rol no tiene concedido {permiso}.", permiso=permiso)
        if grupo_id:
            self._en_alcance(actor, alcance.value, grupo_id, permiso)
        elif organizacion and alcance.value != "ORGANIZATION":
            raise FueraDeAlcance("Esa evaluación no es de ningún grupo tuyo: sólo la opera quien la asignó o quien enseña a sus alumnos.", permiso=permiso)

    def exigir_alguno(self, actor: Actor, permisos: tuple[str, ...], *, grupo_id: str = "", organizacion: bool = False) -> None:
        ultimo: SinPermiso | None = None
        for permiso in permisos:
            try:
                return self.exigir(actor, permiso, grupo_id=grupo_id, organizacion=organizacion)
            except FueraDeAlcance as error:
                ultimo = error
            except SinPermiso as error:
                ultimo = ultimo or error
        raise ultimo or SinPermiso("Tu rol no tiene permiso para esta función.", permisos=list(permisos))

    def exigir_alumno(self, actor: Actor) -> None:
        if actor.autenticado and actor.principal is not None:
            if actor.nivel >= 2:
                raise SinPermiso("Esta consulta es del alumno sobre sus propios resultados.", permiso=cat.P_READ)
            if _alcance(actor, cat.P_READ) is None:
                raise SinPermiso(f"Tu rol no tiene concedido {cat.P_READ}.", permiso=cat.P_READ)
            return
        if not actor.id:
            raise FaltaAlumno("Sin sesión no se sabe de quién son los resultados: falta `alumno_id`.")
        if actor.id not in IdentidadAcceso().alumnos_activos([actor.id]):
            raise AlumnoDesconocido("El alumno que se declara no existe o no está activo: hay que elegir de nuevo quién eres.", alumno_id=actor.id)

    def grupos_visibles(self, actor: Actor, permiso: str) -> list[str] | None:
        identidad = IdentidadAcceso()
        if not actor.autenticado or actor.principal is None:
            # Sin sesión (Q-34) el actor es una declaración del cliente: si es docente de algún grupo, ve los suyos; si no (o no dice quién es), el prototipo no le recorta nada.
            return (identidad.grupos_del_docente(actor.id) if actor.id else []) or None
        alcance = _alcance(actor, permiso)
        if alcance is None:
            raise SinPermiso(f"Tu rol no tiene concedido {permiso}.", permiso=permiso)
        return None if alcance.value == "ORGANIZATION" else identidad.grupos_del_docente(actor.id)

    @staticmethod
    def _en_alcance(actor: Actor, alcance: str, grupo_id: str, permiso: str) -> None:
        if alcance == "ORGANIZATION":
            return
        if alcance != "SELF" and IdentidadAcceso().es_docente_del_grupo(grupo_id, actor.id):
            return
        raise FueraDeAlcance("Ese permiso no llega a este grupo: sólo opera los grupos de los que es docente.", permiso=permiso, grupo_id=grupo_id)

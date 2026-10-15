"""
Los permisos de Reporting. MOD-001 los siembra (`acceso.dominio.plantillas`, migración `acceso/0017`) y aquí se evalúan con SU política, en el nodo:

  reports.view · reports.group.view · reports.student.view   leer reportes: el profesor sobre SUS grupos; reportes y administración, toda la organización
  reports.usage.view                                         el uso de equipos, SIN personas: reportes, administración y soporte técnico
  reports.export                                             exportar a archivo: el profesor sobre sus grupos; reportes y administración
  reports.rebuild                                            reconstruir los agregados: administración y soporte técnico
  reports.settings.manage                                    umbral de privacidad y política de exportación: la administración
  reports.curriculum.view                                    RESERVADO (V1)

  - Con sesión: el permiso debe estar concedido por el rol efectivo y su ALCANCE debe llegar al grupo. El rol técnico no tiene ninguno de lectura académica (BR-097, TST-069) y el
    alumno ninguno (los reportes son del personal).
  - Sin sesión (Q-34, prototipo): se permite, igual que en el libro, la evaluación y el aula; la persona la declara el cliente. Con AVACOM_LMS_EXIGIR_SESION=1 esa rama no existe,
    porque las vistas ya rechazan lo que no trae sesión.
"""
from __future__ import annotations

from ..aplicacion.puertos import Actor
from ..dominio import catalogos as cat
from ..dominio.errores import FueraDeAlcance, SinPermiso
from .identidad import IdentidadAcceso


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


class AutorizacionReporting:
    def exigir(self, actor: Actor, permiso: str, *, grupo_id: str = "", organizacion: bool = False) -> None:
        """Sin `grupo_id` sólo se comprueba que el rol tenga el permiso; con `organizacion=True` además que lo tenga sobre TODA la organización."""
        if permiso not in cat.PERMISOS:
            raise ValueError(f"Permiso fuera del catálogo de MOD-013: {permiso}")
        if not actor.autenticado or actor.principal is None:
            return
        if actor.nivel < 2:
            raise SinPermiso("Los reportes son del personal del colegio.", permiso=permiso)
        alcance = _alcance(actor, permiso)
        if alcance is None:
            raise SinPermiso(f"Tu rol no tiene concedido {permiso}.", permiso=permiso)
        if grupo_id:
            self._en_alcance(actor, alcance.value, grupo_id, permiso)
        elif organizacion and alcance.value != "ORGANIZATION":
            raise FueraDeAlcance("Ese reporte abarca toda la organización y tu permiso sólo llega a tus grupos.", permiso=permiso)

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

    def grupos_visibles(self, actor: Actor, permiso: str) -> list[str] | None:
        identidad = IdentidadAcceso()
        if not actor.autenticado or actor.principal is None:
            # Sin sesión (Q-34) el actor es una declaración del cliente: si es docente de algún grupo, ve los suyos; si no (o no dice quién es), el prototipo no le recorta nada.
            return (identidad.grupos_del_docente(actor.id) if actor.id else []) or None
        alcance = _alcance(actor, permiso)
        if alcance is None:
            raise SinPermiso(f"Tu rol no tiene concedido {permiso}.", permiso=permiso)
        return None if alcance.value == "ORGANIZATION" else identidad.grupos_del_docente(actor.id)

    def puede(self, actor: Actor, permiso: str) -> bool:
        if not actor.autenticado or actor.principal is None:
            return True
        if actor.nivel < 2:
            return False
        try:
            return _alcance(actor, permiso) is not None
        except SinPermiso:
            return False

    @staticmethod
    def _en_alcance(actor: Actor, alcance: str, grupo_id: str, permiso: str) -> None:
        if alcance == "ORGANIZATION":
            return
        if alcance != "SELF" and IdentidadAcceso().es_docente_del_grupo(grupo_id, actor.id):
            return
        raise FueraDeAlcance("Ese permiso no llega a este grupo: sólo ves los reportes de los grupos de los que eres docente.", permiso=permiso, grupo_id=grupo_id)

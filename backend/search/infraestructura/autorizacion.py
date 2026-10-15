"""
Los permisos de Search. MOD-001 los siembra (`acceso.dominio.plantillas`, migración `acceso/0015`) y aquí se evalúan con SU política, en el nodo, en CADA consulta:

  search.query      buscar: profesorado, administración y reportes (no el alumno ni el técnico). Alcance: sus grupos (profesorado) o toda la organización.
  search.reindex    mantener el índice (reconstruir, sincronizar, sinónimos, ver el detalle): administración y técnico.

  Lo que se puede LEER de cada tipo lo decide el permiso de lectura del módulo propietario (`content.read`, `assessment.read`, `study.assignment.review`,
  `classroom.results.view`) y su alcance (BR-088): con alcance de organización se lee todo lo de ese tipo; con alcance de grupos, sólo lo de los grupos de los que la
  persona es docente (y lo que creó sin grupo). Los grupos salen de la política de MOD-001 (`ContextoActor.grupos_docente`), no de lo guardado en el índice.
  Sin sesión (Q-34, prototipo) se permite buscar y la persona la declara el cliente; sin declarar a nadie sólo se ve el catálogo de la biblioteca, nunca lo de un grupo.
  Con AVACOM_LMS_EXIGIR_SESION=1 esa rama no existe: las vistas ya rechazan lo que no trae sesión.
"""
from __future__ import annotations

from ..aplicacion.puertos import Actor
from ..dominio import catalogos as cat
from ..dominio.documento import Visibilidad
from ..dominio.errores import SinPermiso
from .identidad import IdentidadAcceso


class AutorizacionSearch:
    def __init__(self):
        self._contextos: dict[int, tuple] = {}

    def _contexto(self, actor: Actor):
        """`(ctx, politica)` del actor con sesión: el rol EFECTIVO, sus permisos y sus grupos, tal como los entiende MOD-001. Se recuerda mientras dure la petición."""
        clave = id(actor.principal)
        if clave not in self._contextos:
            from acceso.aplicacion import casos_uso as acu
            from acceso.infraestructura.contenedor import servicios as servicios_acceso

            s = servicios_acceso()
            base = acu.Base(s)
            with s.uow() as uow:
                self._contextos[clave] = (base.contexto(uow, actor.principal), base.politica)
        return self._contextos[clave]

    def _alcance(self, actor: Actor, permiso: str):
        ctx, politica = self._contexto(actor)
        previa = politica.transversal(ctx, permiso)
        if previa is not None:
            if previa.codigo == "sesion_visitante_limitada":       # RN-43: a una visita se le dice qué es, no sólo que «su rol no lo tiene»
                previa.exigir()
            return None
        return politica.alcance_concedido(ctx, permiso)

    # ------------------------------------------------------------------------------------------------ puerto
    def tiene(self, actor: Actor, permiso: str) -> bool:
        if not actor.autenticado or actor.principal is None:
            return True
        return self._alcance(actor, permiso) is not None

    def exigir(self, actor: Actor, permiso: str) -> None:
        if permiso not in cat.PERMISOS:
            raise ValueError(f"Permiso fuera del catálogo de MOD-021: {permiso}")
        if not self.tiene(actor, permiso):
            raise SinPermiso(f"Tu rol no tiene concedido {permiso}.", permiso=permiso)

    def visibilidad(self, actor: Actor) -> Visibilidad:
        if not actor.autenticado or actor.principal is None:
            return self._sin_sesion(actor)
        ctx, politica = self._contexto(actor)
        if not self.tiene(actor, cat.P_CONSULTAR):
            return Visibilidad(persona_id=actor.id)
        por_tipo: dict[str, str] = {}
        contenido = False
        for tipo, permiso in cat.PERMISO_DE_LECTURA.items():
            alcance = self._alcance(actor, permiso)
            if alcance is None:
                continue
            if tipo in cat.TIPOS_DE_CATALOGO:
                contenido = True
                por_tipo[tipo] = cat.ORGANIZACION                  # el catálogo no es de ningún grupo: lo que lee `content.read` lo lee toda la organización
            elif alcance.value == "ORGANIZATION":
                por_tipo[tipo] = cat.ORGANIZACION
            elif alcance.value in ("ASSIGNED_GROUPS", "LEVEL"):
                por_tipo[tipo] = cat.GRUPOS
            # SELF (lo propio del alumno) no da lectura sobre lo de un grupo
        return Visibilidad(persona_id=actor.id, por_tipo=por_tipo, grupos=frozenset(ctx.grupos_docente), contenido=contenido)

    @staticmethod
    def _sin_sesion(actor: Actor) -> Visibilidad:
        por_tipo = {t: cat.ORGANIZACION for t in cat.TIPOS_DE_CATALOGO}
        grupos = frozenset(IdentidadAcceso().grupos_del_docente(actor.id)) if actor.id else frozenset()
        for tipo in cat.TIPOS_LOCALES:
            por_tipo[tipo] = cat.GRUPOS
        return Visibilidad(persona_id=actor.id, por_tipo=por_tipo, grupos=grupos, contenido=True)

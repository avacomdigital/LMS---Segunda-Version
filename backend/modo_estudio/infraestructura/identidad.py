"""
MOD-001 visto desde el modo de estudio: el padrón replicado en el módulo de acceso (m01_organizacion, m01_grupo, m01_miembro_grupo,
m01_usuario). SÓLO LECTURA: MOD-008 no es dueño de personas ni de grupos, y nunca escribe aquí (BR-003).

Sin organización instalada (Q-34, el nodo aún sin instalar) `organizacion_id()` es None y el módulo degrada: sin grupos, sin padrón.
"""
from __future__ import annotations


class IdentidadAcceso:
    def organizacion_id(self) -> str | None:
        from acceso.models import Organizacion
        fila = Organizacion.objects.order_by("creado_en").first()
        return fila.id if fila else None

    def rotulo_persona(self, persona_id: str) -> str:
        from acceso.models import Usuario
        fila = Usuario.objects.filter(pk=persona_id).first() if persona_id else None
        return fila.alias if fila else ""

    def rotulos_personas(self, persona_ids: list[str]) -> dict[str, str]:
        ids = [i for i in persona_ids if i]
        if not ids:
            return {}
        from acceso.models import Usuario
        return dict(Usuario.objects.filter(pk__in=ids).values_list("id", "alias"))

    @staticmethod
    def _grupo(fila) -> dict:
        return {"id": fila.id, "codigo": fila.codigo, "nombre": fila.nombre, "nivel_clave": fila.nivel_clave, "activo": fila.activo}

    def grupo(self, grupo_id: str) -> dict | None:
        from acceso.models import Grupo
        fila = Grupo.objects.filter(pk=grupo_id).first() if grupo_id else None
        return self._grupo(fila) if fila else None

    def grupos_activos(self) -> list[dict]:
        from acceso.models import Grupo
        return [self._grupo(g) for g in Grupo.objects.filter(activo=True).order_by("nombre", "codigo")]

    def grupos_del_docente(self, docente_id: str) -> list[dict]:
        from acceso.models import MiembroGrupo
        filas = MiembroGrupo.objects.filter(usuario_id=docente_id, papel="DOCENTE", hasta__isnull=True, grupo__activo=True) \
            .select_related("grupo").order_by("grupo__nombre", "grupo__codigo")
        return [self._grupo(f.grupo) for f in filas]

    def es_docente_del_grupo(self, grupo_id: str, persona_id: str) -> bool:
        from acceso.models import MiembroGrupo
        return bool(grupo_id) and MiembroGrupo.objects.filter(grupo_id=grupo_id, usuario_id=persona_id, papel="DOCENTE", hasta__isnull=True).exists()

    def alumnos_del_grupo(self, grupo_id: str) -> list[dict]:
        from acceso.models import MiembroGrupo
        filas = MiembroGrupo.objects.filter(grupo_id=grupo_id, papel="ESTUDIANTE", hasta__isnull=True, usuario__estado="ACTIVO") \
            .select_related("usuario").order_by("usuario__alias", "usuario_id")
        return [{"id": f.usuario_id, "rotulo": f.usuario.alias} for f in filas]

    def grupos_del_alumno(self, alumno_id: str) -> list[str]:
        from acceso.models import MiembroGrupo
        return list(MiembroGrupo.objects.filter(usuario_id=alumno_id, papel="ESTUDIANTE", hasta__isnull=True, grupo__activo=True)
                    .values_list("grupo_id", flat=True))

    def alumnos_conocidos(self, alumno_ids: list[str]) -> set[str] | None:
        from acceso.models import Organizacion, Usuario
        if not Organizacion.objects.exists():
            return None
        return set(Usuario.objects.filter(pk__in=[i for i in alumno_ids if i]).values_list("id", flat=True))

    def alumnos_activos(self, persona_ids: list[str]) -> dict[str, str]:
        ids = [i for i in persona_ids if i]
        if not ids:
            return {}
        from acceso.models import Usuario
        return dict(Usuario.objects.filter(pk__in=ids, estado="ACTIVO").values_list("id", "alias"))

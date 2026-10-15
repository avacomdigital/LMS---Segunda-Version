"""
MOD-001 visto desde Reporting: el padrón replicado en el módulo de acceso (m01_organizacion, m01_grupo, m01_miembro_grupo, m01_usuario). SÓLO LECTURA: MOD-013 no es dueño de personas
ni de grupos y nunca escribe aquí (BR-003, BR-085). Es la única lectura directa de tablas ajenas: el padrón no tiene una interfaz `servicios` propia (como en el libro y en Search).

Sin organización instalada `organizacion_id()` es None y el módulo degrada: sin grupos, sin padrón.
"""
from __future__ import annotations


class IdentidadAcceso:
    def organizacion_id(self) -> str | None:
        from acceso.models import Organizacion
        fila = Organizacion.objects.order_by("creado_en").first()
        return fila.id if fila else None

    def grupo(self, grupo_id: str) -> dict | None:
        from acceso.models import Grupo
        fila = Grupo.objects.filter(pk=grupo_id).first() if grupo_id else None
        return {"id": fila.id, "codigo": fila.codigo, "nombre": fila.nombre, "periodo": fila.periodo, "nivel_clave": fila.nivel_clave or "", "activo": fila.activo} if fila else None

    def todos_los_grupos(self) -> list[str]:
        from acceso.models import Grupo
        return list(Grupo.objects.filter(activo=True).order_by("id").values_list("id", flat=True))

    def grupos_de_nivel(self, nivel_clave: str) -> list[str]:
        from acceso.models import Grupo
        return list(Grupo.objects.filter(nivel_clave=nivel_clave, activo=True).order_by("id").values_list("id", flat=True))

    def grupos_del_docente(self, persona_id: str) -> list[str]:
        from acceso.models import MiembroGrupo
        return list(MiembroGrupo.objects.filter(usuario_id=persona_id, papel="DOCENTE", hasta__isnull=True, grupo__activo=True).values_list("grupo_id", flat=True))

    def es_docente_del_grupo(self, grupo_id: str, persona_id: str) -> bool:
        from acceso.models import MiembroGrupo
        return bool(grupo_id) and MiembroGrupo.objects.filter(grupo_id=grupo_id, usuario_id=persona_id, papel="DOCENTE", hasta__isnull=True).exists()

    def alumnos_del_grupo(self, grupo_id: str) -> list[dict]:
        from acceso.models import MiembroGrupo
        filas = MiembroGrupo.objects.filter(grupo_id=grupo_id, papel="ESTUDIANTE", hasta__isnull=True, usuario__estado="ACTIVO").select_related("usuario") \
            .order_by("usuario__alias", "usuario_id")
        return [{"id": f.usuario_id, "rotulo": f.usuario.alias} for f in filas]

    def grupos_del_alumno(self, alumno_id: str) -> list[str]:
        from acceso.models import MiembroGrupo
        return list(MiembroGrupo.objects.filter(usuario_id=alumno_id, papel="ESTUDIANTE", hasta__isnull=True, grupo__activo=True).order_by("grupo_id").values_list("grupo_id", flat=True))

    def rotulos_personas(self, persona_ids: list[str]) -> dict[str, str]:
        ids = [i for i in persona_ids if i]
        if not ids:
            return {}
        from acceso.models import Usuario
        return dict(Usuario.objects.filter(pk__in=ids).values_list("id", "alias"))

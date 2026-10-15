"""
MOD-001 visto desde Search: el padrón replicado en el módulo de acceso (m01_grupo, m01_miembro_grupo). SÓLO LECTURA: MOD-021 no es dueño de personas ni de grupos y nunca
escribe aquí (BR-003). Se lee en el momento de CADA consulta: nada de esto se copia al índice.
"""
from __future__ import annotations


class IdentidadAcceso:
    def organizacion_id(self) -> str | None:
        from acceso.models import Organizacion
        fila = Organizacion.objects.order_by("creado_en").first()
        return fila.id if fila else None

    @staticmethod
    def _grupo(fila) -> dict:
        return {"id": fila.id, "codigo": fila.codigo, "nombre": fila.nombre, "periodo": fila.periodo, "nivel_clave": fila.nivel_clave or "", "activo": fila.activo}

    def grupos(self, grupo_ids: list[str]) -> dict[str, dict]:
        ids = [g for g in grupo_ids if g]
        if not ids:
            return {}
        from acceso.models import Grupo
        return {f.id: self._grupo(f) for f in Grupo.objects.filter(pk__in=ids)}

    def grupos_activos(self) -> list[dict]:
        from acceso.models import Grupo
        return [self._grupo(f) for f in Grupo.objects.filter(activo=True).order_by("nombre", "id")]

    def grupos_del_docente(self, persona_id: str) -> list[str]:
        if not persona_id:
            return []
        from acceso.models import MiembroGrupo
        return list(MiembroGrupo.objects.filter(usuario_id=persona_id, papel="DOCENTE", hasta__isnull=True, grupo__activo=True).values_list("grupo_id", flat=True))

    def grupos_de_periodo(self, periodo: str) -> list[str]:
        from acceso.models import Grupo
        return list(Grupo.objects.filter(periodo=periodo, activo=True).values_list("id", flat=True))

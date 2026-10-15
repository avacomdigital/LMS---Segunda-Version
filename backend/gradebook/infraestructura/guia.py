"""
La rúbrica de una pregunta abierta (`grading-guide` de AVACOM Contenido): rúbrica, respuesta modelo y puntos, sólo para calificar A MANO. Nunca se guarda: cada
petición vuelve a preguntar (artículo 14). La capa de biblioteca y las fuentes de curso NO se modifican; aquí sólo se usa lo que ya exponen.

  · fuente `biblioteca`  `biblioteca.contenido_v2.guia_calificacion` (la API real)
  · fuente `ejemplo`     la misma pregunta del manifiesto de ejemplo (`rubric`, `modelAnswer`, `points`)

Si la biblioteca no responde o la pregunta no tiene rúbrica, devuelve None: la revisión manual sigue funcionando; sólo la rúbrica queda sin poder aplicarse.
"""
from __future__ import annotations

import logging

from ..dominio import rubrica as rub

log = logging.getLogger("avacom.gradebook.guia")


class GuiaBiblioteca:
    def de(self, fuente: str, curso_ref: str, version: str, pregunta_ref: str) -> dict | None:
        try:
            crudo = self._crudo(fuente, curso_ref, version, pregunta_ref)
        except Exception as error:      # noqa: BLE001 — la biblioteca cerrada o una pregunta sin guía no deben tumbar la revisión
            log.info("Sin guía de calificación para %s/%s: %s", curso_ref, pregunta_ref, error)
            return None
        if not isinstance(crudo, dict):
            return None
        return {"rubrica": rub.normalizar_rubrica(crudo.get("rubric")), "respuesta_modelo": crudo.get("modelAnswer"), "puntos": crudo.get("points"),
                "formato": crudo.get("responseFormat")}

    @staticmethod
    def _crudo(fuente: str, curso_ref: str, version: str, pregunta_ref: str) -> dict | None:
        if (fuente or "biblioteca") == "biblioteca":
            from biblioteca import contenido_v2 as v2

            return v2.guia_calificacion(curso_ref, pregunta_ref, version or None)
        from classroom_engine.infraestructura.contenedor import servicios as servicios_aula

        manifiesto = servicios_aula().fuente(fuente or None, curso_ref).curso(curso_ref)
        for leccion in manifiesto.get("lessons") or []:
            for objeto in leccion.get("objects") or []:
                for pregunta in objeto.get("questions") or []:
                    if str(pregunta.get("id")) == pregunta_ref:
                        return {"rubric": pregunta.get("rubric"), "modelAnswer": pregunta.get("modelAnswer"), "points": pregunta.get("points"),
                                "responseFormat": pregunta.get("responseFormat")}
        return None

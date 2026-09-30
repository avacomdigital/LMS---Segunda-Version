"""
El expediente visto desde el modo de estudio: el avance de una lección pasa a `expediente.servicios.actualizar_progreso` (upsert MONOTÓNICO:
un avance atrasado no reduce; 100 % sella la sección). El modo de estudio no escribe m05_* por su cuenta.
"""
from __future__ import annotations


class ExpedienteProgreso:
    def actualizar_progreso(self, curso_ref: str, alumno_id: str, leccion_ref: str, porcentaje: float, leccion_rotulo: str = "",
                            version: str = "", actor: str = "") -> None:
        from expediente import servicios
        servicios.actualizar_progreso(curso_ref, alumno_id, leccion_ref, porcentaje, leccion_rotulo=leccion_rotulo,
                                      version_observada=version, actor=actor or alumno_id)

"""
MOD-010 visto desde el Gradebook, SÓLO por su interfaz pública (`evaluacion.servicios`, BR-004): el libro no importa los modelos de `m10_*`. Lo que MOD-010
rechaza (`ErrorEvaluacion`) llega aquí traducido a un error del Gradebook con el mismo código y el mismo estado HTTP, para que la pantalla vea lo de siempre.
"""
from __future__ import annotations

from evaluacion import servicios as mod10

from ..aplicacion.puertos import Actor
from ..dominio.errores import ErrorGradebook


def _actor10(actor: Actor):
    from evaluacion.aplicacion.puertos import Actor as Actor10

    return Actor10(id=actor.id, rotulo=actor.rotulo, nivel=actor.nivel, autenticado=actor.autenticado, dispositivo_id=actor.dispositivo_id, principal=actor.principal)


def traducir(error) -> ErrorGradebook:
    """Un error de MOD-010 → el mismo error para el libro (mismo `codigo`, mismo `http`, mismos datos)."""
    traducido = ErrorGradebook(error.detalle, **error.extra)
    traducido.codigo = error.codigo
    traducido.http = error.http
    sugerencia = getattr(error, "sugerencia", None)
    if sugerencia:
        traducido.extra = {**traducido.extra, "sugerencia": sugerencia}
    return traducido


class EvaluacionMod10:
    def intento(self, intento_id: str) -> dict | None:
        return mod10.intento(intento_id)

    def intentos_del_alumno(self, asignacion_id: str, alumno_id: str) -> list[dict]:
        return mod10.intentos_del_alumno(asignacion_id, alumno_id)

    def intentos_de_asignacion(self, asignacion_id: str) -> list[dict]:
        return mod10.intentos_de_asignacion(asignacion_id)

    def intentos_en_revision(self, asignacion_ids: list[str]) -> list[dict]:
        return mod10.intentos_en_revision(asignacion_ids)

    def asignacion(self, asignacion_id: str) -> dict | None:
        return mod10.asignacion(asignacion_id)

    def asignaciones_de_grupo(self, grupo_id: str) -> list[dict]:
        return mod10.asignaciones_de_grupo(grupo_id)

    def asignaciones_del_alumno(self, alumno_id: str) -> list[dict]:
        return mod10.asignaciones_del_alumno(alumno_id)

    def pares_de_resultados(self) -> list[tuple[str, str]]:
        return mod10.pares_de_resultados()

    def pendientes_de(self, intento: dict) -> list[str]:
        return mod10.pendientes_de_revision(intento)

    def aciertos_de(self, intento: dict) -> tuple[int, int]:
        return mod10.aciertos_de(intento)

    def resultado_liberado(self, asignacion: dict, intento: dict) -> bool:
        return mod10.resultado_liberado(asignacion, intento)

    def asignaciones_sin_grupo(self) -> list[dict]:
        return mod10.asignaciones_sin_grupo()

    def evaluaciones_en_curso(self, grupo_ids: list[str], alumno_ids: list[str] | tuple[str, ...] = ()) -> int:
        return mod10.evaluaciones_en_curso(grupo_ids, alumno_ids)

    def eventos_desde(self, secuencia: int, limite: int, tipos: tuple[str, ...]) -> tuple[list[dict], int]:
        return mod10.eventos_desde(secuencia, limite, tipos)

    # ---------------------------------------------------------------------------- por encargo: las ejecuta MOD-010
    def revision_del_intento(self, actor: Actor, intento_id: str) -> dict:
        return self._pedir(mod10.revision_del_intento, _actor10(actor), intento_id)

    def puntuar(self, actor: Actor, intento_id: str, pregunta_ref: str, datos: dict) -> dict:
        return self._pedir(mod10.puntuar_respuesta, _actor10(actor), intento_id, pregunta_ref, datos)

    def publicar_revision(self, actor: Actor, intento_id: str) -> dict:
        return self._pedir(mod10.publicar_revision, _actor10(actor), intento_id)

    @staticmethod
    def _pedir(funcion, *args):
        from evaluacion.dominio.errores import ErrorEvaluacion

        try:
            return funcion(*args)
        except ErrorEvaluacion as error:
            raise traducir(error) from error

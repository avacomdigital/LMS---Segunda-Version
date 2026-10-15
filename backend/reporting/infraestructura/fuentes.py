"""
Los módulos dueños vistos desde Reporting, SÓLO por su interfaz pública (`<módulo>.servicios`, BR-004) y SÓLO para leer (BR-085): Reporting no importa los modelos de `m07_*`, `m08_*`,
`m09_*`, `m10_*` ni `m11_*` (una prueba de arquitectura lo comprueba) y no llama ninguna función que escriba. Cada adaptador es un delegado: el dueño decide qué devuelve.
"""
from __future__ import annotations


class AulaFuente:
    """MOD-007 · `classroom_engine.servicios`."""

    def detalle_de_sesion(self, sesion_id: str) -> dict | None:
        from classroom_engine import servicios
        return servicios.detalle_de_sesion(sesion_id)

    def sesion(self, sesion_id: str) -> dict | None:
        from classroom_engine import servicios
        return servicios.sesion(sesion_id)

    def sesiones(self, grupo_ids: list[str] | None = None) -> list[dict]:
        from classroom_engine import servicios
        return servicios.sesiones(grupo_ids)

    def hay_sesion_activa(self) -> bool:
        from classroom_engine import servicios
        return servicios.hay_sesion_activa()

    def eventos_desde(self, secuencia: int, limite: int, tipos: tuple[str, ...]) -> tuple[list[dict], int]:
        from classroom_engine import servicios
        return servicios.eventos_desde(secuencia, limite, tipos)

    def ultima_secuencia(self) -> int:
        from classroom_engine import servicios
        return servicios.ultima_secuencia()


class EvaluacionFuente:
    """MOD-010 · `evaluacion.servicios`."""

    def asignaciones_de_grupo(self, grupo_id: str) -> list[dict]:
        from evaluacion import servicios
        return servicios.asignaciones_de_grupo(grupo_id)

    def asignacion(self, asignacion_id: str) -> dict | None:
        from evaluacion import servicios
        return servicios.asignacion(asignacion_id)

    def intentos_de_asignacion(self, asignacion_id: str) -> list[dict]:
        from evaluacion import servicios
        return servicios.intentos_de_asignacion(asignacion_id)

    def eventos_desde(self, secuencia: int, limite: int, tipos: tuple[str, ...]) -> tuple[list[dict], int]:
        from evaluacion import servicios
        return servicios.eventos_desde(secuencia, limite, tipos)

    def ultima_secuencia(self) -> int:
        from evaluacion import servicios
        return servicios.ultima_secuencia()


class LibroFuente:
    """MOD-011 · `gradebook.servicios`: la calificación ya presentada con la escala del nivel (Reporting no convierte nada)."""

    def resultados_del_grupo(self, grupo_id: str) -> dict | None:
        from gradebook import servicios
        return servicios.resultados_del_grupo(grupo_id)

    def eventos_desde(self, secuencia: int, limite: int, tipos: tuple[str, ...]) -> tuple[list[dict], int]:
        from gradebook import servicios
        return servicios.eventos_desde(secuencia, limite, tipos)

    def ultima_secuencia(self) -> int:
        from gradebook import servicios
        return servicios.ultima_secuencia()


class EstudioFuente:
    """MOD-008 · `modo_estudio.servicios`."""

    def asignacion(self, asignacion_id: str) -> dict | None:
        from modo_estudio import servicios
        return servicios.asignacion(asignacion_id)

    def asignaciones_de_estudio(self, grupo_ids: list[str] | None = None) -> list[dict]:
        from modo_estudio import servicios
        return servicios.asignaciones_de_estudio(grupo_ids)

    def tareas_de(self, asignacion_ids: list[str]) -> list[dict]:
        from modo_estudio import servicios
        return servicios.tareas_de(asignacion_ids)

    def eventos_desde(self, secuencia: int, limite: int, tipos: tuple[str, ...]) -> tuple[list[dict], int]:
        from modo_estudio import servicios
        return servicios.eventos_desde(secuencia, limite, tipos)

    def ultima_secuencia(self) -> int:
        from modo_estudio import servicios
        return servicios.ultima_secuencia()


class EquiposFuente:
    """MOD-009 · `device_manager.servicios`: sólo para ponerle nombre a un equipo al mostrarlo."""

    def por_id(self, dispositivo_id: str) -> dict | None:
        from device_manager import servicios
        return servicios.por_id(dispositivo_id)

"""
Los adaptadores pequeños de MOD-017 (P-14, P-15): el aula (¿hay clase?), la licencia y el respaldo —provisionales hasta que MOD-018 y MOD-016 los sustituyan—, el reloj del nodo
(el de MOD-015, con su marca alta: R-09) y la memoria del proceso.
"""
from __future__ import annotations

import threading
from collections.abc import Iterable


class RelojDelNodo:
    """R-09: el reloj del nodo es el de MOD-015 (`max(reloj del sistema, marca alta)`); ninguna copia nueva de `RelojNodo`."""

    def ahora_ms(self) -> int:
        from nodo import servicios as nodo   # frontera entre módulos: sólo en el adaptador
        return int(nodo.ahora_ms())


class AulaDelNodo:
    """FUN-183: lo responde el dueño de las sesiones de clase, por su `servicios.py`. Ante un fallo se asume que SÍ hay clase (R-01: ante la duda, no se para el aula)."""

    def sesiones_activas(self) -> int:
        try:
            from classroom_engine import servicios as aula   # frontera entre módulos: sólo en el adaptador
            return 1 if aula.hay_sesion_activa() else 0
        except Exception:   # noqa: BLE001 — R-01
            return 1

    def proxima_clase_en(self) -> int | None:
        return None                                   # Q-U9: el nodo no conoce el horario de clases (no hay MOD-002)


class LicenciaSinRestriccion:
    """Provisional (P-14): MOD-018 todavía no publica qué habilita una actualización. Siempre «sin restricción»."""

    def admite(self, modulos: Iterable[str]) -> tuple[bool, str]:
        return True, ""


class RespaldoDelHost:
    """Provisional (P-14, P-15): MOD-016 no existe. El respaldo previo lo toma el Host con `Datos.Respaldar` como paso de la orden (base, -wal, -shm y backend.env). Lo que NO hay:
    el punto de recuperación de 5 s de los intentos en curso (FUN-172): por eso aplicar exige cero sesiones."""

    def disponible(self) -> bool:
        return True

    def descripcion(self) -> str:
        return "Copia de la base de datos y de backend.env por el Host (Datos.Respaldar), con el servicio parado"


class MemoriaDelProceso:
    def __init__(self):
        self._candado = threading.Lock()
        self._en_curso: bool | None = None
        self._anunciados: set[str] = set()

    def en_curso(self) -> bool | None:
        with self._candado:
            return self._en_curso

    def marcar_en_curso(self, valor: bool) -> None:
        with self._candado:
            self._en_curso = bool(valor)

    def anunciado(self, candidato_id: str) -> bool:
        with self._candado:
            return candidato_id in self._anunciados

    def anunciar(self, candidato_id: str) -> None:
        with self._candado:
            if len(self._anunciados) > 10_000:
                self._anunciados.clear()
            self._anunciados.add(candidato_id)

"""
La memoria del proceso (R-07): la última instantánea BUENA de la licencia, el último reloj observado (para detectar un salto del reloj de pared contra el monótono) y los bloqueos de licencia
pendientes de asentar. El camino caliente de cada petición lee de aquí y nunca de la base de datos. Una instantánea mala jamás reemplaza a la buena: `publicar` sólo recibe resultados
completos de `Evaluar`.
"""
from __future__ import annotations

import threading
import uuid

from ..aplicacion.puertos import Instantanea


class EstadoVivo:
    def __init__(self):
        self._candado = threading.Lock()
        self._instantanea: Instantanea | None = None
        self._reloj: tuple[int, int] | None = None
        self._pendientes: dict[tuple[int, str, str], int] = {}
        self._asentados: set[tuple[int, str, str]] = set()
        self._cuentas: dict[str, int] = {}
        self._arranque = uuid.uuid4().hex

    def leer(self) -> Instantanea | None:
        return self._instantanea                                   # una referencia a un objeto inmutable: leer no necesita candado

    def publicar(self, instantanea: Instantanea) -> None:
        with self._candado:
            self._instantanea = instantanea

    def reloj_previo(self) -> tuple[int, int] | None:
        return self._reloj

    def recordar_reloj(self, reloj_ms: int, monotono_ms: int) -> None:
        with self._candado:
            self._reloj = (int(reloj_ms), int(monotono_ms))

    def registrar_bloqueo(self, actor: str, clave: str, ahora_ms: int) -> None:
        hora = int(ahora_ms) // 3_600_000
        llave = (hora, actor, clave)
        with self._candado:
            self._cuentas[clave] = self._cuentas.get(clave, 0) + 1
            if llave in self._asentados or len(self._pendientes) >= 2000:     # el tope de memoria: un cliente que invente actores no la llena
                return
            self._pendientes[llave] = self._pendientes.get(llave, 0) + 1

    def tomar_bloqueos(self) -> list[dict]:
        with self._candado:
            tomados = [{"hora": h, "actor": a, "clave": c, "cantidad": n} for (h, a, c), n in sorted(self._pendientes.items())]
            self._asentados.update(self._pendientes)
            self._pendientes = {}
            if tomados:                                                         # se olvidan las horas viejas
                ultima = max(h for h, _, _ in self._asentados)
                self._asentados = {k for k in self._asentados if k[0] >= ultima - 1}
            return tomados

    def bloqueos_contados(self) -> dict[str, int]:
        with self._candado:
            return dict(self._cuentas)

    def arranque_id(self) -> str:
        return self._arranque

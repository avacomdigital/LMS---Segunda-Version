"""
`RespuestaLocal`: lo que la cola entrega en lugar de la respuesta cruda de la biblioteca. Se parece a ella (`status`, `headers.get`, `read(n)`, `close()`),
así que todo el código que ya sabía reenviar un flujo —y las comprobaciones de tamaño del modo estudio— la entiende sin cambios; además sabe leerse sin
bloquear el bucle del servidor (`leer_async`) y SEGUIR una descarga en curso: si lo que pide el reproductor todavía no llegó del todo, espera a que llegue.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from ..dominio import catalogos as cat
from .almacen import Lectores
from .tarea import Tarea


class Cabeceras(dict):
    """Un diccionario que ignora mayúsculas en `get`, como las cabeceras de una respuesta HTTP."""

    def __init__(self, datos: dict[str, str] | None = None):
        super().__init__()
        for k, v in (datos or {}).items():
            self[k] = v

    def __setitem__(self, clave, valor):
        super().__setitem__(str(clave).lower(), str(valor))

    def get(self, clave, defecto=None):
        return super().get(str(clave).lower(), defecto)

    def __getitem__(self, clave):
        return super().__getitem__(str(clave).lower())

    def __contains__(self, clave):
        return super().__contains__(str(clave).lower())


class RespuestaLocal:
    def __init__(self, *, estado: int, cabeceras: dict[str, str], inicio: int, longitud: int, ruta: Path | None, datos: bytes | None,
                 tarea: Tarea | None, recurso_id: str, lectores: Lectores | None, estancado_seg: float, sin_cuerpo: bool = False,
                 en_una_pieza: bool = False):
        self.status = estado
        self.estado = estado
        self.headers = Cabeceras(cabeceras)
        self.longitud = 0 if sin_cuerpo else longitud
        self.sin_cuerpo = sin_cuerpo
        self.en_una_pieza = en_una_pieza              # se responde con el cuerpo entero en una respuesta normal, no por flujo
        self.recurso_id = recurso_id
        self.tarea = tarea
        self._ruta = ruta
        self._datos = datos
        self._pos = inicio
        self._fin = inicio + self.longitud
        self._archivo = None
        self._lectores = lectores
        self._estancado_seg = estancado_seg
        self._cerrada = False
        self._ultimo_avance = time.monotonic()
        if lectores is not None and not sin_cuerpo:
            lectores.entrar(recurso_id)

    # ------------------------------------------------------------ lo que ya se puede leer
    def _hasta(self) -> int:
        """Hasta qué posición absoluta hay bytes legibles (la cola de una descarga en curso crece)."""
        if self._datos is not None or self.tarea is None or self.tarea.estado == cat.DISPONIBLE:
            return self._fin
        return min(self._fin, self.tarea.bytes_hechos)

    def _revisar(self) -> None:
        t = self.tarea
        if t is not None and t.estado in (cat.FALLIDO, cat.CANCELADO):
            raise OSError(f"La preparación del recurso se interrumpió ({t.error_codigo or t.estado}).")
        if time.monotonic() - self._ultimo_avance > self._estancado_seg:
            raise TimeoutError("El recurso dejó de llegar al nodo.")

    def _leer_ya(self, n: int) -> bytes | None:
        """Los bytes que ya se pueden entregar (hasta `n`), b"" si se terminó, None si hay que esperar a que lleguen."""
        if self._cerrada or self._pos >= self._fin:
            return b""
        disponible = self._hasta()
        if self._pos >= disponible:
            self._revisar()
            return None
        cuanto = min(n, disponible - self._pos)
        if self._datos is not None:
            trozo = self._datos[self._pos:self._pos + cuanto]
        else:
            if self._archivo is None:
                self._archivo = open(self._ruta, "rb")
            self._archivo.seek(self._pos)
            trozo = self._archivo.read(cuanto)
            if not trozo:
                raise OSError("La copia del recurso en la caché se acortó mientras se leía.")
        self._pos += len(trozo)
        self._ultimo_avance = time.monotonic()
        return trozo

    def completa_ahora(self) -> bool:
        """¿Todo lo que falta por enviar ya está disponible? (un recurso en la caché, no uno que todavía baja)"""
        return self._datos is not None or self.tarea is None or self.tarea.estado == cat.DISPONIBLE

    # --------------------------------------------------------------------- lectura
    def read(self, n: int = -1) -> bytes:
        """Lectura bloqueante, como la de una respuesta `urllib`. Con `n < 0` lee todo lo que falte."""
        if n is None or n < 0:
            partes = []
            while True:
                trozo = self.read(256 * 1024)
                if not trozo:
                    return b"".join(partes)
                partes.append(trozo)
        while True:
            trozo = self._leer_ya(n)
            if trozo is not None:
                return trozo
            if self.tarea is not None:
                with self.tarea.cond:
                    self.tarea.cond.wait(0.25)
            else:
                time.sleep(0.05)

    async def leer_async(self, n: int) -> bytes:
        """Igual que `read` pero sin bloquear el bucle: lo que espera, espera con `asyncio.sleep`; lo que lee del disco, lo lee en un hilo."""
        while True:
            if self._datos is not None or self._pos >= self._fin or self._cerrada:
                trozo = self._leer_ya(n)
            else:
                disponible = self._hasta()
                if self._pos >= disponible:
                    trozo = self._leer_ya(n)            # sólo revisa fallos y estancamiento
                else:
                    trozo = await asyncio.to_thread(self._leer_ya, n)
            if trozo is not None:
                return trozo
            await asyncio.sleep(0.05)

    # -------------------------------------------------------------------- cierre
    def close(self) -> None:
        if self._cerrada:
            return
        self._cerrada = True
        if self._archivo is not None:
            try:
                self._archivo.close()
            except OSError:
                pass
            self._archivo = None
        if self._lectores is not None and not self.sin_cuerpo:
            self._lectores.salir(self.recurso_id)

    cerrar = close

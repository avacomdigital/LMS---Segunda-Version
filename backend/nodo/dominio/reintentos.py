"""
La máquina de reintentos (P-07, FUN-162, FUN-163): espera creciente por evento y consumidor (1 s, 2 s, 4 s… con tope y jitter) y, al agotar los intentos, el evento se APARTA a la
cola de problemas y la marca avanza. BR-008 hace seguro reintentar (aplicar N veces = aplicar una).

Puro: el tiempo y el azar se inyectan (R-15). Lo que persiste cada consumidor por fuente es un `EstadoDeReintento`: el evento que retiene la marca, cuántas veces falló, cuándo
toca el siguiente intento y el último error ya saneado.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, replace

from . import catalogos as cat


@dataclass(frozen=True)
class EstadoDeReintento:
    secuencia: int = 0              # 0 = ningún evento retiene la marca
    intentos: int = 0
    proximo_en: int = 0             # instante (ms) a partir del cual toca reintentar; 0 = ya
    ultimo_error: str = ""

    @property
    def activo(self) -> bool:
        return self.secuencia > 0


SIN_REINTENTO = EstadoDeReintento()


def espera_ms(intento: int, base_ms: int = cat.ESPERA_BASE_MS, tope_ms: int = cat.ESPERA_TOPE_MS, jitter: float = cat.JITTER, rng: random.Random | None = None) -> int:
    """La espera antes del intento `intento + 1` tras `intento` fallos: base × 2^(intento−1), con tope y ± jitter. Con `rng` fijo es determinista (pruebas por propiedades)."""
    intento = max(1, int(intento))
    bruta = min(int(tope_ms), int(base_ms) * (2 ** (intento - 1)))
    if jitter <= 0:
        return bruta
    azar = (rng or random).uniform(-jitter, jitter)
    return max(0, int(round(bruta * (1 + azar))))


def toca_reintentar(estado: EstadoDeReintento, ahora: int) -> bool:
    """¿Ya pasó la espera del evento que retiene la marca? Sin evento retenido, siempre (no hay nada que esperar)."""
    return not estado.activo or int(ahora) >= int(estado.proximo_en)


def tras_fallo(estado: EstadoDeReintento, secuencia: int, ahora: int, error: str, *, max_intentos: int = cat.MAX_INTENTOS, base_ms: int = cat.ESPERA_BASE_MS,
               tope_ms: int = cat.ESPERA_TOPE_MS, jitter: float = cat.JITTER, rng: random.Random | None = None) -> tuple[EstadoDeReintento, bool]:
    """
    Qué queda tras fallar el evento `secuencia`: `(estado nuevo, apartar)`. Si es el mismo evento que ya retenía la marca, suma un intento; si es otro, empieza de uno. Con
    `max_intentos` alcanzados se APARTA: el estado vuelve a «sin reintento» (la marca puede pasar de largo) y `apartar` es True.
    """
    intentos = (estado.intentos if estado.secuencia == int(secuencia) else 0) + 1
    if intentos >= int(max_intentos):
        return SIN_REINTENTO, True
    return EstadoDeReintento(int(secuencia), intentos, int(ahora) + espera_ms(intentos, base_ms, tope_ms, jitter, rng), sanear_error(error)), False


def tras_exito(estado: EstadoDeReintento, secuencia: int) -> EstadoDeReintento:
    """Si el evento que retenía la marca por fin se aplicó, se suelta; otro evento no cambia nada."""
    return SIN_REINTENTO if estado.secuencia == int(secuencia) else estado


_CORREO = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_NUMERO_LARGO = re.compile(r"\d{5,}")
_ENTRE_COMILLAS = re.compile(r"(['\"«“]).*?(['\"»”])")
_RUTA = re.compile(r"(?:[A-Za-z]:\\|/)[^\s'\"]+")


def sanear_error(texto: str, maximo: int = cat.MAX_ERROR) -> str:
    """El error de un evento SIN datos personales (BR-127): se quitan correos, números largos (documentos, teléfonos), lo entrecomillado (nombres, textos) y las rutas."""
    limpio = str(texto or "")
    limpio = _CORREO.sub("[correo]", limpio)
    limpio = _RUTA.sub("[ruta]", limpio)
    limpio = _ENTRE_COMILLAS.sub("[texto]", limpio)
    limpio = _NUMERO_LARGO.sub("[número]", limpio)
    limpio = " ".join(limpio.split())
    return limpio[:maximo]


def describir_error(error: BaseException, maximo: int = cat.MAX_ERROR) -> str:
    """`TipoDeError: mensaje saneado` (lo que se guarda en un problema y en el estado de reintento)."""
    return sanear_error(f"{type(error).__name__}: {error}", maximo)


def con_espera(estado: EstadoDeReintento, proximo_en: int) -> EstadoDeReintento:
    return replace(estado, proximo_en=int(proximo_en))

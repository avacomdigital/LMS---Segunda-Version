"""
El reloj confiable (P-06, INV-017): el vencimiento se mide contra `max(reloj del nodo, marca alta)`.

La MARCA ALTA es el instante más alto que el nodo ha visto jamás: sólo sube (un trigger de la base lo garantiza) y se guarda además en ANCLAS fuera de la base de datos —la
fecha del último asiento de la bitácora encadenada, un archivo en %ProgramData% y una clave del registro— que una copia de seguridad restaurada no rebobina. Así:

  · Retroceder el reloj NO alarga una licencia: `ahora_confiable` no baja de la marca alta. Se deja constancia (`reloj_sospechoso` + asiento).
  · Restaurar un respaldo viejo no «rebobina» el vencimiento: las anclas externas conservan la marca alta de antes.
  · Adelantar el reloj tampoco perjudica a nadie por sorpresa: un salto hacia adelante enorme dentro de un proceso en marcha NO degrada; avisa y espera confirmación.

El hardware seguro no tiene reloj propio: nada de esto puede apoyarse en el Keystore ni en el TPM. Este archivo es puro: no lee ningún reloj, recibe lo que le dicen.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LecturaDeReloj:
    ahora: int              # el instante confiable: nunca menor que la marca alta
    reloj: int              # lo que dijo el reloj del nodo
    marca_alta: int
    atras_ms: int           # cuánto por debajo de la marca alta está el reloj (0 si no está por debajo)
    retroceso: bool         # más que la tolerancia


def leer(reloj_ms: int, marca_alta_ms: int, tolerancia_ms: int) -> LecturaDeReloj:
    """`ahora = max(reloj, marca alta)`. Hay retroceso si el reloj quedó por debajo de la marca alta más que la tolerancia."""
    atras = max(0, int(marca_alta_ms) - int(reloj_ms))
    return LecturaDeReloj(max(int(reloj_ms), int(marca_alta_ms)), int(reloj_ms), int(marca_alta_ms), atras, atras > tolerancia_ms)


def marca_siguiente(marca_alta_ms: int, ahora_confiable_ms: int) -> int:
    """La marca alta nueva: monótona (jamás baja)."""
    return max(int(marca_alta_ms), int(ahora_confiable_ms))


def salto_adelante(reloj_previo_ms: int, monotono_previo_ms: int, reloj_ms: int, monotono_ms: int, umbral_ms: int) -> bool:
    """
    ¿El reloj de pared se adelantó, entre dos lecturas del MISMO proceso, mucho más de lo que avanzó el reloj monótono del proceso? (Ése no se puede cambiar desde el reloj del
    sistema.) Entre un arranque y otro no hay referencia: un nodo apagado diez días en vacaciones NO es un salto.
    """
    return (int(reloj_ms) - int(reloj_previo_ms)) - (int(monotono_ms) - int(monotono_previo_ms)) > umbral_ms


def retroceso_en_marcha(reloj_previo_ms: int, monotono_previo_ms: int, reloj_ms: int, monotono_ms: int, tolerancia_ms: int) -> bool:
    """¿El reloj de pared retrocedió dentro del proceso (respecto del monótono) más que la tolerancia?"""
    return (int(monotono_ms) - int(monotono_previo_ms)) - (int(reloj_ms) - int(reloj_previo_ms)) > tolerancia_ms

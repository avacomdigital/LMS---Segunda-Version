"""
El reloj confiable (P-06, INV-017): el vencimiento se mide contra `max(reloj del nodo, marca alta)`.

La MARCA ALTA es el instante más alto que el nodo ha visto jamás: sólo sube (un trigger de la base lo garantiza) y se guarda además en ANCLAS fuera de la base de datos —la
fecha del último asiento de la bitácora encadenada, un archivo en %ProgramData% y una clave del registro— que una copia de seguridad restaurada no rebobina. Así:

  · Retroceder el reloj NO alarga una licencia: `ahora_confiable` no baja de la marca alta ni se congela (avanza con el reloj monótono del proceso). Se deja constancia (`reloj_sospechoso`).
  · Restaurar un respaldo viejo no «rebobina» el vencimiento: las anclas externas conservan la marca alta de antes.
  · Adelantar el reloj (Q-L13, decisión del CTO) NO se acepta: un salto hacia adelante mayor que el umbral dentro de un proceso en marcha es una FECHA ADELANTADA. El nodo no la guarda
    —ni en la marca alta, ni en las anclas, ni vale el asiento de la bitácora que se selló con ella—, sigue contando el tiempo real con el reloj monótono, NO degrada nada por ella y avisa
    con un error hasta que la fecha vuelve a concordar (o la administración confirma que la de hoy es la correcta). Un equipo apagado una semana no es un salto: entre un arranque y
    otro no hay referencia, y los días de calendario cuentan (Q-L16).

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


@dataclass(frozen=True)
class Resolucion:
    """Lo que el nodo concluye del reloj en un ciclo: el instante que vale, la marca que vale y qué hacer con un episodio de fecha adelantada (Q-L13)."""

    lectura: LecturaDeReloj
    marca: int              # la marca alta que vale: la de las anclas y la base, más el asiento de la bitácora sólo si no se selló con una fecha adelantada
    adelantado: bool        # la fecha del equipo está adelantada de más y NO se acepta: se avisa y no se guarda
    adelanto_ms: int        # cuánto está adelantada (0 si no lo está)
    abre_episodio: bool     # hay que asentar el inicio del episodio (todavía no está en la base)
    cierra_episodio: bool   # la fecha volvió a concordar y el episodio sigue abierto en la base: hay que asentar el cierre


def piso_monotono(confiable_previo_ms: int | None, monotono_previo_ms: int | None, monotono_ms: int) -> int:
    """
    El instante confiable que el reloj monótono GARANTIZA dentro de un mismo proceso: el confiable de la lectura anterior más lo que de verdad pasó desde entonces (el monótono no se
    cambia desde el reloj del sistema). Sin lectura anterior —el primer ciclo de un proceso— no hay piso: 0 (tras un reinicio sólo se pierde el tiempo apagado, que nadie puede aprovechar).
    """
    if confiable_previo_ms is None or monotono_previo_ms is None:
        return 0
    return int(confiable_previo_ms) + max(0, int(monotono_ms) - int(monotono_previo_ms))


def leer(reloj_ms: int, marca_alta_ms: int, tolerancia_ms: int, piso_ms: int = 0) -> LecturaDeReloj:
    """
    `ahora = max(reloj, marca alta)`. Hay retroceso si el reloj quedó por debajo de la marca alta más que la tolerancia.

    Con retroceso el reloj de pared ya no dice cuánto tiempo pasó, y `max(reloj, marca)` sería un valor FIJO —la marca—: el tiempo de la licencia se congelaría hasta que la hora de
    pared alcanzara la marca y atrasar la fecha alargaría la licencia lo que se atrasó (H-13), o dejaría sin efecto el tope de 72 h de un salto sospechoso (H-14). Por eso, SÓLO con
    retroceso, el instante confiable no baja del piso que garantiza el reloj monótono (`piso_monotono`). Con el reloj en orden no interviene: una deriva de ppm entre el monótono y el
    de pared no puede adelantar el confiable tras meses de funcionamiento.
    """
    atras = max(0, int(marca_alta_ms) - int(reloj_ms))
    retroceso = atras > tolerancia_ms
    ahora = max(int(reloj_ms), int(marca_alta_ms))
    if retroceso:
        ahora = max(ahora, int(piso_ms))
    return LecturaDeReloj(ahora, int(reloj_ms), int(marca_alta_ms), atras, retroceso)


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


def resolver(reloj_ms: int, monotono_ms: int, previo: tuple[int, int, int] | None, marca_propia_ms: int, ultima_audit_ms: int | None, episodio_abierto: bool,
             tolerancia_retroceso_ms: int, salto_adelante_ms: int, tolerancia_fecha_ms: int) -> Resolucion:
    """
    Lo que el nodo concluye del reloj en este ciclo (P-06 · Q-L13). Es la ÚNICA decisión sobre qué hora vale: nadie más lee el reloj de pared para fechar un hecho de la licencia.

    `previo` es `(reloj de pared, monótono, instante confiable)` de la lectura anterior de ESTE proceso (None en el primer ciclo); `marca_propia_ms` la mayor de la base y las anclas
    de afuera; `ultima_audit_ms` la fecha del último asiento de la bitácora; `episodio_abierto` si la base dice que hay una fecha adelantada sin resolver. Sale:

      · Sin episodio, lo de siempre: `max(reloj, marca)`, y con el reloj por debajo de la marca el piso del monótono (H-13).
      · FECHA ADELANTADA: un salto hacia adelante mayor que `salto_adelante_ms` dentro de un proceso en marcha, con el reloj todavía adelantado más que `tolerancia_fecha_ms` del instante
        confiable. El instante que vale NO es el del reloj: es la referencia (la marca o el piso monótono, la mayor), así que la licencia sigue contando el tiempo real y no se vence ni se
        degrada por el salto, y la marca no sube con él. El episodio sigue mientras el reloj siga adelantado, también tras un reinicio (la base lo recuerda), hasta que la fecha concuerde
        (`cierra_episodio`) o la administración la confirme (una `reloj_confirmado` posterior lo cierra desde fuera).
      · Un nodo que arranca con el reloj adelantado y SIN episodio abierto lo acepta: estuvo apagado y los días de calendario cuentan (Q-L16); no hay con qué distinguirlo de un receso.
      · Un salto cuyo reloj queda a menos de `tolerancia_fecha_ms` del confiable no es un episodio: es el reloj que se corrigió (la pila agotada que vuelve de 2010 al sincronizar la hora).
      · El asiento de la bitácora sólo cuenta de ancla si no está en el futuro del confiable más el umbral: lo sellan los demás módulos con el reloj de pared y, tras un salto, lleva la
        fecha adelantada; sin este filtro el salto entraría por ahí en la marca y quedaría para siempre.
    """
    reloj_ms, monotono_ms = int(reloj_ms), int(monotono_ms)
    reloj_previo, monotono_previo, confiable_previo = previo if previo is not None else (None, None, None)
    piso = piso_monotono(confiable_previo, monotono_previo, monotono_ms)
    ancla = max(int(marca_propia_ms), piso)
    audit = int(ultima_audit_ms) if ultima_audit_ms is not None and int(ultima_audit_ms) <= ancla + salto_adelante_ms else 0
    marca = max(int(marca_propia_ms), audit)
    referencia = max(marca, piso)
    adelanto = reloj_ms - referencia
    adelantado_antes = previo is not None and reloj_previo - confiable_previo > tolerancia_fecha_ms
    salto = previo is not None and salto_adelante(reloj_previo, monotono_previo, reloj_ms, monotono_ms, salto_adelante_ms)
    en_episodio = episodio_abierto or adelantado_antes or (salto and adelanto > tolerancia_fecha_ms)
    adelantado = en_episodio and adelanto > tolerancia_fecha_ms
    if adelantado:
        lectura = LecturaDeReloj(referencia, reloj_ms, marca, 0, False)
    else:
        lectura = leer(reloj_ms, marca, tolerancia_retroceso_ms, piso)
    return Resolucion(lectura=lectura, marca=marca, adelantado=adelantado, adelanto_ms=adelanto if adelantado else 0,
                      abre_episodio=adelantado and not episodio_abierto, cierra_episodio=en_episodio and not adelantado and episodio_abierto)

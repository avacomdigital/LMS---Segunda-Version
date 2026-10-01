"""
El intento (ENT-012), el agregado más crítico del producto: los nueve estados del Maestro, el reloj del nodo con su congelamiento y las
transiciones. Cada función recibe el intento como dict plano y devuelve el dict de campos que cambian (nunca lo muta): así el caso de uso
decide cuándo y dentro de qué transacción lo escribe. Ningún archivo de esta carpeta importa Django ni sabe de HTTP.

Estados (Entidad 3 del Maestro) y la ÚNICA regla que no admite excepción: **ninguna flecha hacia `anulado` parte del sistema** (INV-018).
`anular` exige una persona y un motivo; ninguna otra función de este módulo devuelve `estado = anulado`.

    no_iniciado → en_curso → pausado_desconexion ⇄ en_curso · restaurando
    en_curso → en_curso_fuera_de_plazo → entregado → en_revision_docente → calificado
    entregado | en_revision_docente | calificado → anulado        (decisión docente, motivada)

Extensiones al diagrama del Maestro, todas explicadas en D-9 del modelo: `en_curso_fuera_de_plazo ↔ pausado_desconexion` (un alumno puede
desconectarse después de vencido un plazo blando), `no_iniciado → en_curso_fuera_de_plazo` (se abre con el plazo blando ya vencido),
`restaurando → entregado` (el cierre forzado también alcanza a quien el reinicio dejó sin tableta) y `calificado → en_revision_docente`
(un envío tardío aceptado dentro de la gracia trae reactivos que sólo el profesor puntúa).

El reloj (D-8): `consumido_ms` acumula el tiempo en que corrió; `reloj_desde` marca el inicio del tramo en marcha y es NULO mientras está
congelado. Congelar es detener en el ÚLTIMO LATIDO (a favor del alumno); reanudar es continuar desde el valor congelado. Nunca se usa el reloj
de la tableta para decidir (INV-017).
"""
from __future__ import annotations

from . import catalogos as cat
from .errores import DatosInvalidos, TransicionInvalida

TRANSICIONES: dict[str, frozenset[str]] = {
    cat.NO_INICIADO: frozenset({cat.EN_CURSO, cat.EN_CURSO_FUERA_DE_PLAZO}),
    cat.EN_CURSO: frozenset({cat.PAUSADO, cat.RESTAURANDO, cat.EN_CURSO_FUERA_DE_PLAZO, cat.ENTREGADO}),
    cat.PAUSADO: frozenset({cat.EN_CURSO, cat.EN_CURSO_FUERA_DE_PLAZO, cat.RESTAURANDO, cat.ENTREGADO}),
    cat.RESTAURANDO: frozenset({cat.EN_CURSO, cat.EN_CURSO_FUERA_DE_PLAZO, cat.PAUSADO, cat.ENTREGADO}),
    cat.EN_CURSO_FUERA_DE_PLAZO: frozenset({cat.PAUSADO, cat.RESTAURANDO, cat.ENTREGADO}),
    cat.ENTREGADO: frozenset({cat.EN_REVISION, cat.CALIFICADO, cat.ANULADO}),
    cat.EN_REVISION: frozenset({cat.CALIFICADO, cat.ANULADO}),
    # `calificado → en_revision_docente` (extensión E-4): se aceptó un envío tardío dentro de la gracia y trae reactivos que sólo el profesor puntúa.
    cat.CALIFICADO: frozenset({cat.EN_REVISION, cat.ANULADO}),
    cat.ANULADO: frozenset(),
}

MOTIVO_MINIMO = 3          # un motivo de anulación no puede ser vacío ni un signo


def comprobar_transicion(actual: str, nuevo: str) -> None:
    if nuevo not in TRANSICIONES.get(actual, frozenset()):
        raise TransicionInvalida(f"El intento está «{actual}» y no pasa a «{nuevo}».", estado=actual, destino=nuevo)


def vivo(estado: str) -> bool:
    return estado in cat.VIVOS


def entregado(estado: str) -> bool:
    return estado in cat.ENTREGADOS


# ---------------------------------------------------------------------------------------------- reloj

def consumido(intento: dict, ahora: int) -> int:
    """Milisegundos en que el reloj corrió: lo acumulado más el tramo en marcha (si lo hay)."""
    base = int(intento.get("consumido_ms") or 0)
    desde = intento.get("reloj_desde")
    if desde is not None and intento["estado"] in cat.CORRIENDO:
        base += max(0, ahora - int(desde))
    return base


def reloj(intento: dict, ahora: int) -> dict:
    """Lo que ven la tableta y el panel: `restante_ms` es nulo si no hay límite. `corriendo` ⇔ el reloj avanza; `congelado` ⇔ está suspendido."""
    limite_seg = intento.get("tiempo_limite_seg")
    usado = consumido(intento, ahora)
    restante = max(0, int(limite_seg) * 1000 - usado) if limite_seg else None
    corriendo = intento.get("reloj_desde") is not None and intento["estado"] in cat.CORRIENDO
    return {"limite_seg": limite_seg, "restante_ms": restante, "consumido_ms": usado, "corriendo": corriendo,
            "congelado": intento["estado"] in cat.SUSPENDIDOS, "servidor_en": ahora}


def instante_de_agotamiento(intento: dict) -> int | None:
    """El instante exacto (reloj del nodo) en que se acaba el tiempo de un intento que corre. Nulo si no hay límite o el reloj está detenido."""
    limite_seg, desde = intento.get("tiempo_limite_seg"), intento.get("reloj_desde")
    if not limite_seg or desde is None or intento["estado"] not in cat.CORRIENDO:
        return None
    return int(desde) + max(0, int(limite_seg) * 1000 - int(intento.get("consumido_ms") or 0))


def agotado(intento: dict, ahora: int) -> bool:
    momento = instante_de_agotamiento(intento)
    return momento is not None and momento <= ahora


def silencio_ms(intento: dict, ahora: int) -> int:
    """Cuánto lleva la tableta sin dar señal (desde el último latido; si nunca dio, desde que se abrió)."""
    ultimo = intento.get("ultimo_latido_en") or intento.get("reloj_desde") or intento.get("iniciado_en") or ahora
    return max(0, ahora - int(ultimo))


def debe_pausarse(intento: dict, ahora: int, umbral_ms: int) -> bool:
    return intento["estado"] in cat.CORRIENDO and silencio_ms(intento, ahora) > umbral_ms


# -------------------------------------------------------------------------------------- transiciones

def abrir(intento: dict, ahora: int, *, fuera_de_plazo: bool = False) -> dict:
    """`no_iniciado → en_curso` (FUN-109). Si la asignación ya está fuera de plazo nace `en_curso_fuera_de_plazo`."""
    destino = cat.EN_CURSO_FUERA_DE_PLAZO if fuera_de_plazo else cat.EN_CURSO
    comprobar_transicion(intento["estado"], destino)
    return {"estado": destino, "iniciado_en": ahora, "reloj_desde": ahora, "consumido_ms": 0, "ultimo_latido_en": ahora,
            "fuera_de_plazo": bool(fuera_de_plazo)}


def _congelar(intento: dict, ahora: int) -> tuple[int, int]:
    """(`consumido_ms` al congelar, instante del corte). El corte es el último latido, acotado al tramo en marcha."""
    desde = intento.get("reloj_desde")
    if desde is None:
        return int(intento.get("consumido_ms") or 0), ahora
    corte = max(int(desde), min(int(intento.get("ultimo_latido_en") or desde), ahora))
    return int(intento.get("consumido_ms") or 0) + (corte - int(desde)), corte


def pausar(intento: dict, ahora: int, causa: str = cat.C_SIN_LATIDO) -> dict:
    """`en_curso | en_curso_fuera_de_plazo → pausado_desconexion`. El reloj se detiene en el último latido."""
    comprobar_transicion(intento["estado"], cat.PAUSADO)
    consumido_ms, corte = _congelar(intento, ahora)
    pausa = {"desde": corte, "hasta": None, "causa": causa, "estado_previo": intento["estado"], "reactivado_por": ""}
    return {"estado": cat.PAUSADO, "consumido_ms": consumido_ms, "reloj_desde": None, "pausas": [*list(intento.get("pausas") or []), pausa]}


def restaurar(intento: dict, ahora: int) -> dict:
    """El nodo arrancó con el intento abierto (BR-051, INV-010): `→ restaurando`, el reloj congelado en el último latido. Desde una pausa
    sólo cambia el estado (la pausa sigue abierta). NUNCA entrega ni anula."""
    comprobar_transicion(intento["estado"], cat.RESTAURANDO)
    if intento["estado"] == cat.PAUSADO:
        return {"estado": cat.RESTAURANDO}
    consumido_ms, corte = _congelar(intento, ahora)
    pausa = {"desde": corte, "hasta": None, "causa": cat.C_REINICIO_NODO, "estado_previo": intento["estado"], "reactivado_por": ""}
    return {"estado": cat.RESTAURANDO, "consumido_ms": consumido_ms, "reloj_desde": None,
            "pausas": [*list(intento.get("pausas") or []), pausa]}


def pausa_abierta(intento: dict) -> dict | None:
    for pausa in reversed(list(intento.get("pausas") or [])):
        if pausa.get("hasta") is None:
            return pausa
    return None


def _cerrar_pausa(intento: dict, hasta: int, por: str) -> list[dict]:
    pausas = [dict(p) for p in intento.get("pausas") or []]
    for pausa in reversed(pausas):
        if pausa.get("hasta") is None:
            pausa["hasta"] = max(hasta, int(pausa.get("desde") or 0))
            pausa["reactivado_por"] = por
            break
    return pausas


def reactivar(intento: dict, ahora: int, por: str) -> dict:
    """`pausado_desconexion | restaurando → en_curso` (o `en_curso_fuera_de_plazo`, el estado que tenía). El reloj CONTINÚA desde el valor
    congelado: el alumno recupera exactamente el tiempo que le quedaba. `por` es la persona que reactiva, o `sistema` si la asignación es
    de reactivación automática."""
    if intento["estado"] not in cat.SUSPENDIDOS:
        raise TransicionInvalida(f"Sólo se reactiva un intento suspendido; éste está «{intento['estado']}».", estado=intento["estado"],
                                 destino=cat.EN_CURSO)
    pausa = pausa_abierta(intento)
    previo = (pausa or {}).get("estado_previo")
    destino = previo if previo in cat.CORRIENDO else cat.EN_CURSO
    comprobar_transicion(intento["estado"], destino)
    return {"estado": destino, "reloj_desde": ahora, "pausas": _cerrar_pausa(intento, ahora, por), "ultimo_latido_en": ahora}


def pasar_a_pausado(intento: dict) -> dict:
    """`restaurando → pausado_desconexion`: la tableta reapareció tras el reinicio y la asignación exige que el PROFESOR reactive."""
    comprobar_transicion(intento["estado"], cat.PAUSADO)
    return {"estado": cat.PAUSADO}


def vencio_el_plazo_blando(intento: dict) -> dict:
    """FUN-115: el plazo blando venció. `en_curso → en_curso_fuera_de_plazo`; si el intento está suspendido, la pausa recuerda que al volver
    será fuera de plazo. Un intento que no corre ni está suspendido no cambia."""
    estado = intento["estado"]
    if estado == cat.EN_CURSO:
        return {"estado": cat.EN_CURSO_FUERA_DE_PLAZO, "fuera_de_plazo": True}
    if estado in cat.SUSPENDIDOS:
        pausas = [dict(p) for p in intento.get("pausas") or []]
        for pausa in reversed(pausas):
            if pausa.get("hasta") is None:
                pausa["estado_previo"] = cat.EN_CURSO_FUERA_DE_PLAZO
                break
        return {"fuera_de_plazo": True, "pausas": pausas}
    return {}


def entregar(intento: dict, ahora: int, origen: str, hasta: int | None = None) -> dict:
    """FUN-114: `→ entregado`. Detiene el reloj en `hasta` (el instante en que se agotó el tiempo o venció el plazo; por omisión, ahora)."""
    if origen not in cat.ORIGENES_ENTREGA:
        raise DatosInvalidos(f"origen_entrega debe ser uno de: {', '.join(cat.ORIGENES_ENTREGA)}.", origen_entrega=origen)
    comprobar_transicion(intento["estado"], cat.ENTREGADO)
    corte = ahora if hasta is None else min(ahora, hasta)
    base = int(intento.get("consumido_ms") or 0)
    desde = intento.get("reloj_desde")
    if desde is not None:
        base += max(0, corte - int(desde))
    return {"estado": cat.ENTREGADO, "reloj_desde": None, "consumido_ms": base, "entregado_en": corte, "origen_entrega": origen,
            "pausas": _cerrar_pausa(intento, corte, "") if pausa_abierta(intento) else list(intento.get("pausas") or [])}


def tras_calificar(requiere_revision: bool) -> str:
    """El destino de un intento entregado: con reactivos que revisa el profesor, `en_revision_docente`; sin ellos, `calificado`."""
    return cat.EN_REVISION if requiere_revision else cat.CALIFICADO


def anular(intento: dict, por: str, motivo: str, ahora: int) -> dict:
    """La única función del módulo que devuelve `estado = anulado` (INV-018): una PERSONA, con un motivo, desde un intento ya entregado."""
    por = str(por or "").strip()
    motivo = str(motivo or "").strip()
    if not por or por == cat.SISTEMA:
        raise DatosInvalidos("Anular es una decisión humana: la toma una persona, con su nombre, nunca el sistema.", anulado_por=por)
    if len(motivo) < MOTIVO_MINIMO:
        raise DatosInvalidos("Anular exige un motivo escrito.", motivo=motivo)
    if intento["estado"] not in cat.ANULABLES:
        raise TransicionInvalida(
            f"Un intento «{intento['estado']}» no se anula: primero se entrega (con cierre forzado si hace falta).",
            estado=intento["estado"], destino=cat.ANULADO)
    return {"estado": cat.ANULADO, "anulado_por": por[:64], "motivo_anulacion": motivo[:300], "anulado_en": ahora}


def reconciliar_reloj(intento: dict, ahora: int, transcurrido_dispositivo_ms) -> dict:
    """D-8: la tableta puede informar el tiempo que su cronómetro monotónico lleva corrido. El nodo toma el MAYOR de los dos valores, acotado por
    el tiempo real desde que se abrió el intento: desconectarse no regala tiempo, y un valor inflado no puede pasar del reloj de pared.
    Sólo sube. Devuelve los campos a escribir (vacío si no cambia)."""
    if transcurrido_dispositivo_ms in (None, "") or isinstance(transcurrido_dispositivo_ms, bool):
        return {}
    try:
        informado = int(transcurrido_dispositivo_ms)
    except (TypeError, ValueError):
        return {}
    if informado <= 0 or intento.get("iniciado_en") is None or intento["estado"] not in cat.ACEPTAN_RESPUESTAS:
        return {}
    tope = max(0, ahora - int(intento["iniciado_en"]))
    actual = consumido(intento, ahora)
    nuevo = min(max(actual, informado), tope)
    if nuevo <= actual:
        return {}
    if intento.get("reloj_desde") is not None and intento["estado"] in cat.CORRIENDO:
        return {"consumido_ms": nuevo, "reloj_desde": ahora}
    return {"consumido_ms": nuevo}

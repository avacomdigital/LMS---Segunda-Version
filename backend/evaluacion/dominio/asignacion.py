"""
La asignación (ENT-011): estados, transiciones autorizadas, plazos y qué se hace con lo que llega después del cierre. Reglas puras: ningún
archivo de esta carpeta importa Django ni sabe de HTTP.

Estados del Maestro (sección H de MOD-010):
    borrador → programada | activa → activa_fuera_de_plazo → cerrada → archivada
`activa_fuera_de_plazo` SÓLO existe con plazo blando (BR-073). Con plazo endurecido la asignación cierra al vencer (BR-074) y lo capturado
antes del cierre entra por la ventana de gracia (DEC-019). El cierre manual desde `activa` no está en el diagrama del Maestro y es necesario
para que el profesor termine un examen a tiempo (Q-78).
"""
from __future__ import annotations

from . import bloqueo
from . import catalogos as cat
from .errores import DatosInvalidos, TransicionInvalida

TRANSICIONES: dict[str, frozenset[str]] = {
    cat.BORRADOR: frozenset({cat.PROGRAMADA, cat.ACTIVA}),
    cat.PROGRAMADA: frozenset({cat.ACTIVA}),
    cat.ACTIVA: frozenset({cat.ACTIVA_FUERA_DE_PLAZO, cat.CERRADA}),
    cat.ACTIVA_FUERA_DE_PLAZO: frozenset({cat.CERRADA, cat.ACTIVA}),
    cat.CERRADA: frozenset({cat.ACTIVA, cat.ARCHIVADA}),
    cat.ARCHIVADA: frozenset(),
}


def comprobar_transicion(actual: str, nuevo: str) -> None:
    if nuevo not in TRANSICIONES.get(actual, frozenset()):
        raise TransicionInvalida(f"La asignación está «{actual}» y no pasa a «{nuevo}».", estado=actual, destino=nuevo)


def abierta(estado: str) -> bool:
    """¿Recibe intentos y respuestas?"""
    return estado in cat.ABIERTAS


# ------------------------------------------------------------------------------- validación de la entrada

def validar_alcance(alcance, destinatarios, grupo_id) -> tuple[str, list[str]]:
    alcance = str(alcance or cat.GRUPO).strip().lower()
    if alcance not in cat.ALCANCES:
        raise DatosInvalidos(f"alcance debe ser uno de: {', '.join(cat.ALCANCES)}.", alcance=alcance)
    if alcance == cat.GRUPO:
        if not str(grupo_id or "").strip():
            raise DatosInvalidos("Una asignación a todo el grupo exige `grupo_id`.")
        return alcance, []
    if not isinstance(destinatarios, list) or not destinatarios:
        raise DatosInvalidos("Una asignación a alumnos concretos exige `destinatarios` (una lista no vacía de `alumno_id`).")
    ids = list(dict.fromkeys(str(d).strip()[:64] for d in destinatarios if str(d).strip()))
    if not ids:
        raise DatosInvalidos("`destinatarios` no tiene ningún alumno.")
    return alcance, ids


def validar_plazo(plazo, limite_en, abre_en, ahora: int) -> tuple[str, int | None, int | None]:
    """`blando` (por defecto) o `endurecido`. El endurecido exige fecha límite: sin ella no hay cuándo cerrar. `abre_en` no puede ser posterior
    a `limite_en`."""
    plazo = str(plazo or cat.BLANDO).strip().lower()
    if plazo not in cat.PLAZOS:
        raise DatosInvalidos(f"plazo debe ser uno de: {', '.join(cat.PLAZOS)}.", plazo=plazo)
    limite = _instante(limite_en, "limite_en")
    abre = _instante(abre_en, "abre_en")
    if plazo == cat.ENDURECIDO and limite is None:
        raise DatosInvalidos("Con plazo endurecido hay que fijar `limite_en`: al vencer, la asignación cierra.")
    if limite is not None and abre is not None and limite < abre:
        raise DatosInvalidos("`limite_en` no puede ser anterior a `abre_en`.", abre_en=abre, limite_en=limite)
    return plazo, limite, abre


def validar_limite_futuro(limite_en, ahora: int, nombre: str = "limite_en") -> int:
    limite = _instante(limite_en, nombre)
    if limite is None:
        raise DatosInvalidos(f"Falta `{nombre}`.")
    if limite <= ahora:
        raise DatosInvalidos(f"`{nombre}` debe estar en el futuro.", **{nombre: limite})
    return limite


def validar_gracia_ms(gracia_min=None, gracia_ms=None, por_defecto: int = cat.GRACIA_MS_POR_DEFECTO) -> int:
    """La gracia llega en minutos (`gracia_min`) desde las pantallas; `gracia_ms` es para el código. Nunca negativa."""
    if gracia_ms not in (None, ""):
        valor = _entero(gracia_ms, "gracia_ms")
    elif gracia_min not in (None, ""):
        valor = _entero(gracia_min, "gracia_min") * 60_000
    else:
        return por_defecto
    if valor < 0:
        raise DatosInvalidos("La gracia no puede ser negativa.", gracia=valor)
    return valor


def validar_intentos_permitidos(valor) -> int | None:
    """BR-072: el límite de intentos. Nulo (o vacío) = sin tope (TST-030). Quien llama aplica el valor por defecto (uno) cuando la clave no
    viene en la entrada: aquí un nulo EXPLÍCITO significa «ilimitados»."""
    if valor is None or valor == "":
        return None
    n = _entero(valor, "intentos_permitidos")
    if n < 1:
        raise DatosInvalidos("intentos_permitidos debe ser al menos 1 (o nulo para no limitar).", intentos_permitidos=n)
    return n


def validar_tiempo(tiempo) -> tuple[str, int | None]:
    """`{modo: biblioteca | fijo | sin_limite, limite_seg}`. Sin objeto: lo que diga la biblioteca."""
    if tiempo in (None, ""):
        return cat.TIEMPO_BIBLIOTECA, None
    if not isinstance(tiempo, dict):
        raise DatosInvalidos("`tiempo` debe ser un objeto {modo, limite_seg}.")
    modo = str(tiempo.get("modo") or cat.TIEMPO_BIBLIOTECA).strip().lower()
    if modo not in cat.MODOS_TIEMPO:
        raise DatosInvalidos(f"tiempo.modo debe ser uno de: {', '.join(cat.MODOS_TIEMPO)}.", modo=modo)
    if modo == cat.TIEMPO_FIJO:
        limite = _entero(tiempo.get("limite_seg"), "tiempo.limite_seg")
        if limite < 1:
            raise DatosInvalidos("tiempo.limite_seg debe ser al menos 1 segundo.", limite_seg=limite)
        return modo, limite
    return modo, None


def validar_reactivacion(valor, nivel: str) -> str:
    """Por defecto la reactivación es DEL PROFESOR (Guion: «reanudar solo» es lo que el sistema nunca hace). `automatica` es una elección explícita."""
    texto = str(valor or cat.REACTIVA_PROFESOR).strip().lower()
    if texto not in cat.REACTIVACIONES:
        raise DatosInvalidos(f"reactivacion debe ser una de: {', '.join(cat.REACTIVACIONES)}.", reactivacion=texto)
    return texto


def validar_resultados(valor, por_defecto: str = cat.TRAS_LIBERAR) -> str:
    texto = str(valor or por_defecto).strip().lower()
    if texto not in cat.RESULTADOS:
        raise DatosInvalidos(f"resultados debe ser uno de: {', '.join(cat.RESULTADOS)}.", resultados=texto)
    return texto


def validar_recursos(recursos) -> list[dict]:
    """Los recursos que el profesor habilita en `supervisado`: sólo referencias y un rótulo."""
    if recursos in (None, ""):
        return []
    if not isinstance(recursos, list):
        raise DatosInvalidos("`recursos` debe ser una lista de {media_ref, rotulo}.")
    salida = []
    for r in recursos:
        if not isinstance(r, dict) or not str(r.get("media_ref") or "").strip():
            raise DatosInvalidos("Cada recurso exige `media_ref`.")
        salida.append({"media_ref": str(r["media_ref"]).strip()[:120], "rotulo": str(r.get("rotulo") or "")[:250]})
    return salida


def validar_nivel_vigente(declarado: str, vigente: str) -> None:
    """`nivel_examen` no sube respecto de `nivel_declarado` (lo comprueba también un CHECK de la base)."""
    if bloqueo.es_menor(declarado, vigente):
        raise DatosInvalidos("El nivel vigente no puede superar al declarado: el nivel sólo se degrada.",
                             nivel_declarado=declarado, nivel_examen=vigente)


# --------------------------------------------------------------------------------- el reloj decide

def estado_por_tiempo(asignacion: dict, ahora: int, archivo_tras_ms: int = cat.ARCHIVO_TRAS_MS) -> str:
    """El estado que le corresponde HOY a una asignación según su reloj (D-15). Idempotente: aplicarlo dos veces da lo mismo. Nunca retrocede:
    sólo avanza `programada → activa → activa_fuera_de_plazo | cerrada → archivada`."""
    estado = asignacion["estado"]
    limite, abre = asignacion.get("limite_en"), asignacion.get("abre_en")
    if estado == cat.PROGRAMADA and (abre is None or abre <= ahora):
        estado = cat.ACTIVA
    if estado == cat.ACTIVA and limite is not None and limite <= ahora:
        estado = cat.CERRADA if asignacion["plazo"] == cat.ENDURECIDO else cat.ACTIVA_FUERA_DE_PLAZO
    if estado == cat.ACTIVA_FUERA_DE_PLAZO and asignacion["plazo"] == cat.ENDURECIDO and limite is not None and limite <= ahora:
        estado = cat.CERRADA          # se endureció con la asignación ya fuera de plazo
    if estado == cat.CERRADA and asignacion.get("cerrada_en") is not None and ahora - asignacion["cerrada_en"] >= archivo_tras_ms:
        estado = cat.ARCHIVADA
    return estado


def cierre_por_plazo(asignacion: dict) -> int | None:
    """El instante en que cerró por vencer un plazo endurecido: la fecha límite, no el momento en que el nodo lo notó."""
    return asignacion.get("limite_en") if asignacion["plazo"] == cat.ENDURECIDO else None


# ---------------------------------------------------------------- lo que llega después del cierre (BR-074, DEC-019)

ACEPTAR, DECIDE_EL_PROFESOR, RECHAZAR = "aceptar", "decide_el_profesor", "rechazar"


def politica_de_recepcion(*, cerrada_en: int | None, capturada_en: int | None, recibida_en: int,
                          gracia_ms: int = cat.GRACIA_MS_POR_DEFECTO) -> str:
    """¿Qué se hace con un envío que llega ahora? Abierta: se acepta. Cerrada: lo capturado antes del cierre se acepta dentro de la gracia y,
    pasada ésta, queda para decisión del profesor (nunca se descarta en silencio); lo capturado después del cierre se rechaza."""
    if cerrada_en is None:
        return ACEPTAR
    capturada = recibida_en if capturada_en is None else capturada_en
    if capturada > cerrada_en:
        return RECHAZAR
    return ACEPTAR if recibida_en - cerrada_en <= gracia_ms else DECIDE_EL_PROFESOR


def cierre_de_recepcion(intento: dict, asignacion: dict) -> int | None:
    """El instante a partir del cual lo capturado ya no cuenta como anterior al cierre. Si el intento se entregó porque la ASIGNACIÓN cerró (plazo o
    cierre del profesor) es el cierre de la asignación: un intento sin señal se entrega con el reloj detenido en su último latido, pero lo que el
    alumno respondió sin red hasta la fecha límite se capturó antes del cierre. En los demás casos (tiempo agotado, entrega del alumno o cierre
    forzado de ese intento) es el momento en que se entregó ese intento."""
    entregado = intento.get("entregado_en")
    cierre = asignacion.get("cerrada_en")
    if intento.get("origen_entrega") in (cat.O_PLAZO, cat.O_CIERRE) and cierre is not None and (entregado is None or cierre >= entregado):
        return cierre
    return entregado


# ---------------------------------------------------------------------------------------- utilidades

def _entero(valor, nombre: str) -> int:
    if isinstance(valor, bool) or valor in (None, ""):
        raise DatosInvalidos(f"Falta `{nombre}` o no es un entero.", **{nombre.replace(".", "_"): valor})
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise DatosInvalidos(f"`{nombre}` debe ser un entero.", **{nombre.replace(".", "_"): valor})


def _instante(valor, nombre: str) -> int | None:
    if valor in (None, "", 0):
        return None
    entero = _entero(valor, nombre)
    if entero < 0:
        raise DatosInvalidos(f"`{nombre}` debe ser un instante en milisegundos.", **{nombre: valor})
    return entero

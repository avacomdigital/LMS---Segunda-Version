"""
La forma de `response` que exige `POST /v2/evaluate` para cada tipo de pregunta y la
traducción del veredicto que devuelve la biblioteca (§5 del «Mapeo de campos · API de
Contenido v2»).

Reglas que este módulo hace cumplir ANTES de llamar a la biblioteca:
  - Una opción se identifica por su `id`, nunca por su posición: las opciones llegan
    barajadas en cada llamada y dos alumnos no ven el mismo orden.
  - Cada referencia de la respuesta (opción, hueco, pareja, elemento) tiene que existir
    en la pregunta tal como la vio el alumno; una referencia inventada es 400.
  - `score` y `correct` pueden ser nulos, `score`/`maxScore`/`points` decimales.
  - `requiresManualGrading: true` deja el intento PENDIENTE: no se inventa nota.

No importa Django ni sabe de HTTP: es dominio puro.
"""
from __future__ import annotations

from typing import Any

from .errores import DatosInvalidos

# tipo de pregunta → claves admitidas dentro de `response`
FORMAS_RESPUESTA: dict[str, tuple[str, ...]] = {
    "multiple_choice": ("selectedOptionIds",),
    "true_false": ("value",),
    "fill_blanks": ("blanks",),
    "matching": ("pairs",),
    "ordering": ("order",),
    "open": ("text", "drawingRef", "audioRef"),
    "drag_drop": ("placements",),      # contrato 2 (2026-10-07): [{itemId, targetId}], una pieza en una zona como mucho
}


def _refs(pregunta: dict, coleccion: str, clave: str) -> set[str]:
    return {str(x.get(clave, "")) for x in (pregunta.get(coleccion) or []) if isinstance(x, dict)}


def validar_respuesta(pregunta: dict, respuesta: Any) -> dict:
    """Devuelve `response` tal como debe viajar a `/v2/evaluate` o lanza DatosInvalidos.

    `pregunta` es la pregunta de la vista de aula (`tipo`, `opciones`, `espacios`,
    `izquierda`, `derecha`, `elementos`), es decir, lo que el alumno vio."""
    if not isinstance(respuesta, dict) or not respuesta:
        raise DatosInvalidos("`respuesta` debe ser un objeto con la forma del tipo de pregunta.", pregunta_ref=pregunta.get("pregunta_ref"))
    tipo = str(pregunta.get("tipo", ""))
    claves = FORMAS_RESPUESTA.get(tipo)
    ref = pregunta.get("pregunta_ref")
    if claves is None:
        # Tipo que este LMS no conoce (conjunto abierto, §9): se reenvía tal cual; la biblioteca decide.
        return dict(respuesta)
    sobrantes = set(respuesta) - set(claves)
    if sobrantes:
        raise DatosInvalidos(f"Una pregunta «{tipo}» admite {', '.join(claves)} en `respuesta`; sobra: {', '.join(sorted(sobrantes))}.",
                             pregunta_ref=ref, tipo=tipo)

    if tipo == "multiple_choice":
        elegidas = respuesta.get("selectedOptionIds")
        if not isinstance(elegidas, list) or not elegidas or not all(isinstance(x, str) and x for x in elegidas):
            raise DatosInvalidos("`selectedOptionIds` debe ser una lista no vacía de `id` de opción (nunca posiciones).", pregunta_ref=ref)
        elegidas = list(dict.fromkeys(elegidas))
        if not pregunta.get("permite_varias") and len(elegidas) > 1:
            raise DatosInvalidos("Esta pregunta admite una sola opción.", pregunta_ref=ref)
        validas = _refs(pregunta, "opciones", "opcion_ref")
        desconocidas = [x for x in elegidas if x not in validas]
        if desconocidas:
            raise DatosInvalidos(f"Opciones que no están en la pregunta: {', '.join(desconocidas)}.", pregunta_ref=ref)
        return {"selectedOptionIds": elegidas}

    if tipo == "true_false":
        valor = respuesta.get("value")
        if isinstance(valor, str) and valor.lower() in ("true", "false"):
            valor = valor.lower() == "true"
        if not isinstance(valor, bool):
            raise DatosInvalidos("`value` debe ser verdadero o falso.", pregunta_ref=ref)
        return {"value": valor}

    if tipo == "fill_blanks":
        huecos = respuesta.get("blanks")
        if not isinstance(huecos, dict) or not huecos:
            raise DatosInvalidos("`blanks` debe ser un objeto {id_del_hueco: valor}.", pregunta_ref=ref)
        validos = _refs(pregunta, "espacios", "espacio_ref")
        desconocidos = [k for k in huecos if k not in validos]
        if desconocidos:
            raise DatosInvalidos(f"Huecos que no están en la plantilla: {', '.join(desconocidos)}.", pregunta_ref=ref)
        return {"blanks": {str(k): ("" if v is None else str(v)) for k, v in huecos.items()}}

    if tipo == "matching":
        parejas = respuesta.get("pairs")
        if not isinstance(parejas, list) or not parejas:
            raise DatosInvalidos("`pairs` debe ser una lista de {leftId, rightId}.", pregunta_ref=ref)
        izquierda, derecha = _refs(pregunta, "izquierda", "ref"), _refs(pregunta, "derecha", "ref")
        salida = []
        for p in parejas:
            if not isinstance(p, dict) or not p.get("leftId") or not p.get("rightId"):
                raise DatosInvalidos("Cada pareja exige leftId y rightId.", pregunta_ref=ref)
            izq, der = str(p["leftId"]), str(p["rightId"])
            if izq not in izquierda or der not in derecha:
                raise DatosInvalidos(f"La pareja {izq} → {der} usa referencias que no están en la pregunta.", pregunta_ref=ref)
            salida.append({"leftId": izq, "rightId": der})
        return {"pairs": salida}

    if tipo == "ordering":
        orden = respuesta.get("order")
        if not isinstance(orden, list) or not orden or not all(isinstance(x, str) for x in orden):
            raise DatosInvalidos("`order` debe ser la lista de `id` de los elementos en el orden elegido.", pregunta_ref=ref)
        elementos = _refs(pregunta, "elementos", "ref")
        if set(orden) != elementos or len(orden) != len(elementos):
            raise DatosInvalidos("`order` debe contener exactamente los elementos de la pregunta, una vez cada uno.", pregunta_ref=ref)
        return {"order": list(orden)}

    if tipo == "drag_drop":
        colocaciones = respuesta.get("placements")
        if not isinstance(colocaciones, list) or not colocaciones:
            raise DatosInvalidos("`placements` debe ser una lista no vacía de {itemId, targetId}.", pregunta_ref=ref)
        piezas, zonas = _refs(pregunta, "elementos", "ref"), _refs(pregunta, "zonas", "zona_ref")
        salida, vistas = [], set()
        for c in colocaciones:
            if not isinstance(c, dict) or not c.get("itemId") or not c.get("targetId"):
                raise DatosInvalidos("Cada colocación exige itemId y targetId.", pregunta_ref=ref)
            pieza, zona = str(c["itemId"]), str(c["targetId"])
            if pieza not in piezas or zona not in zonas:
                raise DatosInvalidos(f"La colocación {pieza} → {zona} usa referencias que no están en la pregunta.", pregunta_ref=ref)
            if pieza in vistas:
                raise DatosInvalidos(f"La pieza {pieza} se colocó más de una vez.", pregunta_ref=ref)
            vistas.add(pieza)
            salida.append({"itemId": pieza, "targetId": zona})
        return {"placements": salida}

    # open
    presentes = [k for k in ("text", "drawingRef", "audioRef") if respuesta.get(k)]
    if len(presentes) != 1:
        raise DatosInvalidos("Una pregunta abierta lleva exactamente uno de text, drawingRef o audioRef.", pregunta_ref=ref)
    clave = presentes[0]
    valor = str(respuesta[clave])
    maximo = pregunta.get("longitud_maxima")
    if clave == "text" and isinstance(maximo, int) and maximo > 0 and len(valor) > maximo:
        raise DatosInvalidos(f"El texto supera la longitud máxima ({maximo}).", pregunta_ref=ref)
    return {clave: valor}


def _numero(valor) -> float | None:
    """`score`, `maxScore` y `points` pueden ser decimales (1.3333) o nulos. Nunca se redondean a entero."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def veredicto(bruto: dict, pregunta_ref: str = "") -> dict:
    """La respuesta de `/v2/evaluate` traducida a la vista de aula. Sin ninguna clave.

    Con `requiresManualGrading` el puntaje es nulo aunque la biblioteca mandara un
    número: el intento queda pendiente y la nota la pone quien califica a mano."""
    manual = bool(bruto.get("requiresManualGrading"))
    puntaje = None if manual else _numero(bruto.get("score"))
    correcta = bruto.get("correct")
    retro = bruto.get("feedback")
    if isinstance(retro, str):
        retro = [retro]
    return {
        "pregunta_ref": str(bruto.get("questionId") or pregunta_ref),
        "puntaje": puntaje,
        "puntaje_maximo": _numero(bruto.get("maxScore")),
        "correcta": correcta if isinstance(correcta, bool) else None,
        "requiere_correccion_manual": manual,
        "pendiente": manual or puntaje is None,
        "retroalimentacion": [str(x) for x in (retro or []) if x is not None],
    }

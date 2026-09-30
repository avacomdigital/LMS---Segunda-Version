"""
El trabajo sin red que se integra sin duplicar ni exigir sesión (CAP-048, FUN-086, D-10, D-11): validación de lo que manda la cola del
aparato. Dominio puro: no importa Django ni sabe de HTTP.

Reglas del Documento Maestro que se cumplen aquí:
  - BR-059 · BR-060 · BR-138 · TST-029: cada evento de la cola lleva `emisor_id` (la identidad de la instalación) y una `secuencia`
    monotónica persistida ANTES de enviar. `m08_sincronizacion` tiene `UNIQUE(emisor_id, secuencia)`: repetir el envío devuelve el
    mismo resultado sin duplicar nada.
  - BR-062 · INV-017: `ocurrido_en` ya viene normalizado al reloj del nodo; `ocurrido_en_tableta` (la hora cruda del aparato) sólo se
    conserva como dato adicional.
  - BR-127: lo que queda del evento después de integrarse no incluye el contenido de las respuestas.
"""
from __future__ import annotations

from . import catalogos as cat
from .errores import DatosInvalidos

MAX_EVENTOS = cat.MAX_EVENTOS_POR_ENVIO


def _entero(valor, minimo: int = 0) -> int | None:
    if isinstance(valor, bool) or valor in (None, ""):
        return None
    try:
        entero = int(valor)
    except (TypeError, ValueError):
        return None
    return entero if entero >= minimo else None


def normalizar_emisor(valor) -> str:
    texto = str(valor or "").strip()
    if not texto:
        raise DatosInvalidos("Falta emisor_id: la identidad de la instalación que envía la cola.")
    if len(texto) > 64:
        raise DatosInvalidos("emisor_id supera los 64 caracteres.")
    return texto


def validar_envio(eventos) -> list:
    """La lista de eventos de un envío: hasta 200. Cada uno se valida por separado más adelante (un evento malo no tumba a los demás)."""
    if eventos is None:
        return []
    if not isinstance(eventos, list):
        raise DatosInvalidos("`eventos` debe ser una lista.")
    if len(eventos) > MAX_EVENTOS:
        raise DatosInvalidos(f"Un envío admite hasta {MAX_EVENTOS} eventos.", eventos=len(eventos), maximo=MAX_EVENTOS)
    return eventos


def normalizar_evento(bruto) -> dict:
    """`{secuencia, tipo, ocurrido_en, ocurrido_en_tableta, carga}` con la secuencia validada, o DatosInvalidos. Lo demás (el tipo y la
    carga) se valida al integrar (`validar_carga`): un evento con secuencia válida pero mal formado queda en el libro como `rechazado`, y
    reenviarlo devuelve lo mismo. Sin `ocurrido_en` se toma la hora en que llega (no hay otra que sea autoritativa)."""
    if not isinstance(bruto, dict):
        raise DatosInvalidos("Cada evento debe ser un objeto {secuencia, tipo, ocurrido_en, carga}.")
    secuencia = _entero(bruto.get("secuencia"), 1)
    if secuencia is None:
        raise DatosInvalidos("La secuencia debe ser un entero ≥ 1.", secuencia=bruto.get("secuencia"))
    return {"secuencia": secuencia, "tipo": str(bruto.get("tipo") or ""), "ocurrido_en": _entero(bruto.get("ocurrido_en")),
            "ocurrido_en_tableta": _entero(bruto.get("ocurrido_en_tableta")), "carga": bruto.get("carga")}


def _texto(carga: dict, clave: str) -> str:
    valor = carga.get(clave)
    if not isinstance(valor, str) or not valor.strip():
        raise DatosInvalidos(f"Falta {clave} en la carga.", campo=clave)
    return valor.strip()


def validar_carga(tipo: str, carga) -> dict:
    """La carga del evento normalizada según su tipo (§4.5), o DatosInvalidos."""
    if tipo not in cat.TIPOS_EVENTO:
        raise DatosInvalidos(f"Tipo de evento desconocido: {tipo!r}. Tipos: {', '.join(cat.TIPOS_EVENTO)}.", tipo=tipo)
    if not isinstance(carga, dict):
        raise DatosInvalidos("La carga debe ser un objeto.")
    limpia: dict = {"asignacion_id": _texto(carga, "asignacion_id")}
    if tipo == cat.T_BLOQUE_VISTO:
        vistos = carga.get("bloques_vistos") or []
        if not isinstance(vistos, list) or not all(isinstance(r, str) for r in vistos):
            raise DatosInvalidos("`bloques_vistos` debe ser una lista de referencias de bloque.")
        actual = carga.get("bloque_actual")
        if actual is not None and not isinstance(actual, str):
            raise DatosInvalidos("`bloque_actual` debe ser la referencia de un bloque.")
        posicion = carga.get("posicion_seg")
        if posicion is not None and _entero(posicion) is None:
            raise DatosInvalidos("`posicion_seg` debe ser un entero de segundos mayor o igual que 0.")
        if not vistos and not actual:
            raise DatosInvalidos("Un avance lleva bloques_vistos o bloque_actual.")
        limpia.update(bloques_vistos=[r for r in vistos if r], bloque_actual=actual or None, posicion_seg=_entero(posicion))
    elif tipo == cat.T_RESPUESTA_ENVIADA:
        numero = _entero(carga.get("intento_numero"), 1)
        secuencia = _entero(carga.get("secuencia_respuesta"), 1)
        if numero is None or secuencia is None:
            raise DatosInvalidos("`intento_numero` y `secuencia_respuesta` deben ser enteros ≥ 1.")
        if not isinstance(carga.get("respuesta"), dict) or not carga["respuesta"]:
            raise DatosInvalidos("`respuesta` debe ser un objeto con la forma del tipo de pregunta.")
        limpia.update(objeto_ref=_texto(carga, "objeto_ref"), intento_numero=numero, pregunta_ref=_texto(carga, "pregunta_ref"),
                      respuesta=dict(carga["respuesta"]), secuencia_respuesta=secuencia)
    elif tipo == cat.T_PRACTICA_TERMINADA:
        numero = _entero(carga.get("intento_numero"), 1)
        if numero is None:
            raise DatosInvalidos("`intento_numero` debe ser un entero ≥ 1.")
        limpia.update(objeto_ref=_texto(carga, "objeto_ref"), intento_numero=numero)
    # T_LECCION_COMPLETADA: sólo la asignación
    return limpia


def resumen_de_carga(carga) -> dict:
    """Lo que se conserva de la carga una vez integrada o rechazada: sin el contenido de las respuestas (BR-127)."""
    return {k: v for k, v in carga.items() if k != "respuesta"} if isinstance(carga, dict) else {}


def ordenar(eventos: list[dict]) -> list[dict]:
    """Se procesan EN ORDEN de secuencia (una secuencia repetida dentro del envío conserva el orden en que llegó)."""
    return sorted(eventos, key=lambda e: e["secuencia"])


def contar(resultados: list[dict]) -> dict:
    """El resumen del envío: `{integrados, duplicados, rechazados, pendientes_decision}`."""
    return {
        "integrados": sum(1 for r in resultados if r["estado"] == cat.INTEGRADO),
        "duplicados": sum(1 for r in resultados if r["estado"] == cat.DUPLICADO),
        "rechazados": sum(1 for r in resultados if r["estado"] == cat.RECHAZADO),
        "pendientes_decision": sum(1 for r in resultados if r["estado"] == cat.PENDIENTE_DECISION),
    }


def conteos_del_aparato(filas: list[dict]) -> dict:
    """`{synced, rejected, conflict}` de `GET /sync/status/`: el estado del libro tal como lo ve la cola del aparato."""
    return {nombre: sum(1 for f in filas if f["estado"] == estado)
            for estado, nombre in cat.ESTADO_EN_APARATO.items()}

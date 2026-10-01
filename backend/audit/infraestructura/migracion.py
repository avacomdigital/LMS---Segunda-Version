"""
Conversión del historial de `m19_auditoria` a la cadena (§3.4). Funciones puras sobre dicts para que la migración
0001 y las pruebas usen exactamente el mismo código: la cadena nace con el historial actual, por orden
`(momento, id)`, con `origen='migracion'`, `actor_tipo` deducido, `modulo` deducido del prefijo de la acción,
`resultado='ok'` y `valor_anterior` tal como esté.
"""
from __future__ import annotations

from ..dominio import asiento as dom
from ..dominio import catalogos, huella

ACTORES_SISTEMA = ("", "sistema", "cliente", "instalador")


def convertir_fila(fila: dict, secuencia: int) -> dict:
    actor = str(fila.get("actor_id") or "").strip()
    if actor == "instalador":
        actor_tipo, usuario_id = dom.ACTOR_INSTALADOR, None
    elif actor in ACTORES_SISTEMA:
        actor_tipo, usuario_id = dom.ACTOR_SISTEMA, None
    else:
        actor_tipo, usuario_id = dom.ACTOR_DECLARADO, actor[:64]
    accion = str(fila.get("accion") or "desconocida")[:64]
    return {
        "secuencia": secuencia,
        "ocurrido_en": int(fila.get("momento") or 0),
        "usuario_id": usuario_id,
        "actor_tipo": actor_tipo,
        "roles_activos": None,
        "modulo": catalogos.modulo_de(accion),
        "accion": accion,
        "resultado": dom.RESULTADO_OK,
        "objeto_tabla": dom.recortar_objeto(fila.get("objeto_tabla")),
        "objeto_id": dom.recortar_objeto(fila.get("objeto_id")),
        "valor_anterior": fila.get("valor_anterior"),
        "valor_nuevo": fila.get("valor_nuevo"),
        "motivo": None,
        "origen": "migracion",
        "dispositivo_id": None,
        "correlacion_id": None,
        "evento_id": f"m19_auditoria:{fila.get('id')}" if fila.get("id") is not None else None,
    }


def encadenar(filas: list[dict], huella_inicial: str = huella.GENESIS, secuencia_inicial: int = 1) -> list[dict]:
    """Convierte y sella en orden; devuelve los asientos con `huella_previa` y `huella`."""
    salida: list[dict] = []
    previa = huella_inicial
    secuencia = secuencia_inicial
    for fila in sorted(filas, key=lambda f: (int(f.get("momento") or 0), int(f.get("id") or 0))):
        asiento = convertir_fila(fila, secuencia)
        asiento["huella_previa"] = previa
        asiento["huella"] = huella.calcular(previa, asiento)
        salida.append(asiento)
        previa = asiento["huella"]
        secuencia += 1
    return salida

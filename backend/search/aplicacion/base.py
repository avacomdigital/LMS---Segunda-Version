"""Lo común de los casos de uso de Search: la base con sus servicios y el estado del índice (guardado y derivado)."""
from __future__ import annotations

from ..dominio import catalogos as cat
from .puertos import Servicios


class _CasoDeUso:
    def __init__(self, servicios: Servicios):
        self.s = servicios


def estado_del_indice(s: Servicios) -> dict:
    """El estado del índice COMO LO VE QUIEN CONSULTA.

    Se guardan tres estados (construyéndose, consultable, reconstruyéndose); «rezagado» se DERIVA, para que nunca quede un estado viejo: el índice consultable está
    rezagado cuando algún módulo propietario tiene eventos RELEVANTES sin aplicar (los irrelevantes —una respuesta de un examen— no cuentan) o cuando el último ciclo
    de sincronización falló. Un índice rezagado se sigue consultando; sólo se avisa de que los cambios más recientes podrían faltar."""
    with s.uow(lectura=True) as uow:
        guardado = uow.estado.leer()
        marcas = uow.marcas.todas()
    estado = guardado["estado"]
    pendientes: dict[str, int] = {}
    if estado == cat.CONSULTABLE:
        for fuente in s.fuentes.values():
            marca = marcas.get(fuente.fuente, {}).get("secuencia", 0)
            try:
                nuevos, _ = fuente.eventos_desde(marca, 1)
            except Exception:   # noqa: BLE001 — si no se puede mirar la cola, no se puede afirmar que esté al día
                pendientes[fuente.fuente] = -1
                continue
            if nuevos:
                pendientes[fuente.fuente] = pendientes.get(fuente.fuente, 0) + 1
        fallo_reciente = bool(guardado.get("error_en")) and guardado["error_en"] >= (guardado.get("sincronizado_en") or 0)
        if pendientes or fallo_reciente:
            estado = cat.REZAGADO
    return {"estado": estado, "aviso": cat.AVISOS_DEL_INDICE[estado], "guardado": guardado, "marcas": marcas, "pendientes": pendientes}

"""
Aplicar una rúbrica (FUN-121). La rúbrica es de la biblioteca (`grading-guide`) y la respuesta es de MOD-010: aquí sólo se comprueba que lo que el profesor
puntuó por criterio es coherente con la rúbrica y se obtiene el puntaje total. Dominio puro.
"""
from __future__ import annotations

from decimal import Decimal

from . import puntaje as pj
from .errores import DatosInvalidos


def normalizar_rubrica(rubrica) -> list[dict]:
    """La rúbrica de la biblioteca (`[{id, criterion, points}]`) → `[{id, criterio, puntos_max: Decimal}]`. Lo que no sea un criterio válido se ignora."""
    salida = []
    for c in rubrica or []:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        try:
            maximo = pj.a_decimal(c.get("points", c.get("puntos_max", 0)), campo="points")
        except Exception:      # noqa: BLE001 — un criterio sin puntos legibles no se puede aplicar
            continue
        salida.append({"id": str(c["id"]), "criterio": str(c.get("criterion") or c.get("criterio") or ""), "puntos_max": maximo})
    return salida


def aplicar(rubrica: list[dict], aplicados, maximo_pregunta: Decimal | None = None) -> tuple[Decimal, Decimal, list[dict]]:
    """`(puntaje, máximo, detalle)`. Cada criterio de la rúbrica debe traer su puntuación (de 0 a lo que vale ese criterio, con a lo sumo dos decimales);
    un criterio que no existe o repetido se rechaza; el total no supera lo que vale la pregunta."""
    if not rubrica:
        raise DatosInvalidos("La pregunta no tiene rúbrica: puntúala a mano.")
    if not isinstance(aplicados, list) or not aplicados:
        raise DatosInvalidos("`criterios` debe ser una lista con la puntuación de cada criterio de la rúbrica.")
    por_id = {c["id"]: c for c in rubrica}
    dados: dict[str, Decimal] = {}
    for a in aplicados:
        if not isinstance(a, dict):
            raise DatosInvalidos("Cada elemento de `criterios` debe ser {criterio_id, puntos}.")
        criterio_id = str(a.get("criterio_id") or "")
        if criterio_id not in por_id:
            raise DatosInvalidos(f"El criterio «{criterio_id}» no existe en la rúbrica de esta pregunta.", criterio_id=criterio_id)
        if criterio_id in dados:
            raise DatosInvalidos(f"El criterio «{criterio_id}» está repetido.", criterio_id=criterio_id)
        puntos = pj.a_decimal(a.get("puntos"), campo=f"puntos de {criterio_id}")
        if puntos < pj.CERO or puntos > por_id[criterio_id]["puntos_max"]:
            raise DatosInvalidos(f"El criterio «{criterio_id}» vale de 0 a {por_id[criterio_id]['puntos_max']} puntos.", criterio_id=criterio_id,
                                 maximo=float(por_id[criterio_id]["puntos_max"]))
        if pj.decimales_de(puntos) > 2:
            raise DatosInvalidos(f"Los puntos del criterio «{criterio_id}» admiten a lo sumo dos decimales.", criterio_id=criterio_id)
        dados[criterio_id] = puntos
    faltan = [c["id"] for c in rubrica if c["id"] not in dados]
    if faltan:
        raise DatosInvalidos("Falta puntuar criterios de la rúbrica: " + ", ".join(faltan) + ".", faltan=faltan)
    total = sum(dados.values(), pj.CERO)
    posible = sum((c["puntos_max"] for c in rubrica), pj.CERO)
    if maximo_pregunta is not None and total > maximo_pregunta:
        raise DatosInvalidos(f"El total ({total}) supera lo que vale la pregunta ({maximo_pregunta}).", total=float(total), maximo=float(maximo_pregunta))
    detalle = [{"criterio_id": c["id"], "criterio": c["criterio"], "puntos_max": float(c["puntos_max"]), "puntos": float(dados[c["id"]])} for c in rubrica]
    return total, (maximo_pregunta if maximo_pregunta is not None else posible), detalle

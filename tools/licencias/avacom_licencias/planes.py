"""
Los planes como DATO (`planes/*.json`): nada comercial está cableado en el código del emisor. Los valores que entrega la herramienta son PROVISIONALES (pregunta Q-L1 para el CTO).

Un plan dice: tipo, meses de vigencia, días de gracia, los cuatro límites (un número o «sin_tope») y los módulos (`*` = todos). Quien opera puede cambiar cualquiera con una opción
de `emitir`; el plan sólo da los valores por omisión.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .dominio_nodo import RAIZ, catalogos, licencia

CARPETA_POR_OMISION = RAIZ / "planes"
SIN_TOPE = "sin_tope"
TIPOS_EMITIBLES = (licencia.TIPO_PRODUCCION, licencia.TIPO_EVALUACION)


class ErrorDePlan(ValueError):
    """Un plan o una opción no cumple las reglas del módulo."""


@dataclass(frozen=True)
class Plan:
    nombre: str
    descripcion: str
    tipo: str
    meses: int
    gracia_dias: int
    equipos: int
    usuarios: int
    concurrentes_normal: int
    concurrentes_pico: int
    capacidades: tuple[str, ...]
    confirmacion_extra: bool = False


def numero_de_limite(valor: object, nombre: str) -> int:
    """Un límite: un entero > 0 o «sin_tope» (que es 0xFFFFFFFF en el archivo)."""
    if isinstance(valor, str) and valor.strip().lower().replace("-", "_") == SIN_TOPE:
        return licencia.ILIMITADO
    try:
        n = int(valor)
    except (TypeError, ValueError):
        raise ErrorDePlan(f"El límite de {nombre} debe ser un número o «sin_tope».") from None
    if not 1 <= n < licencia.ILIMITADO:
        raise ErrorDePlan(f"El límite de {nombre} debe estar entre 1 y {licencia.ILIMITADO - 1}, o ser «sin_tope».")
    return n


def validar_capacidades(codigos) -> tuple[str, ...]:
    lista = [str(c).strip().lower() for c in codigos]
    if not lista:
        raise ErrorDePlan("Indica al menos un módulo (o «*» para todos).")
    conocidas = set(catalogos.CAPACIDADES_LICENCIABLES) | {catalogos.TODAS}
    desconocidas = sorted(set(lista) - conocidas)
    if desconocidas:
        raise ErrorDePlan(f"Módulos desconocidos: {', '.join(desconocidas)}. Los que existen: {', '.join(sorted(conocidas))}.")
    return tuple(sorted(set(lista)))


def desde_dict(datos: dict) -> Plan:
    try:
        tipo = str(datos["tipo"])
        if tipo not in TIPOS_EMITIBLES:
            raise ErrorDePlan(f"El tipo «{tipo}» no se emite con una llave de producción. Sólo: {', '.join(TIPOS_EMITIBLES)}.")
        limites = datos["limites"]
        plan = Plan(
            nombre=str(datos["nombre"]), descripcion=str(datos.get("descripcion", "")), tipo=tipo, meses=int(datos["meses"]), gracia_dias=int(datos["gracia_dias"]),
            equipos=numero_de_limite(limites["equipos"], "equipos"), usuarios=numero_de_limite(limites["usuarios"], "usuarios"),
            concurrentes_normal=numero_de_limite(limites["concurrentes_normal"], "concurrentes normales"),
            concurrentes_pico=numero_de_limite(limites["concurrentes_pico"], "concurrentes en pico"), capacidades=validar_capacidades(datos["capacidades"]),
            confirmacion_extra=bool(datos.get("confirmacion_extra", False)))
    except (KeyError, TypeError) as error:
        raise ErrorDePlan(f"Al plan le falta un dato: {error}.") from error
    if not 1 <= plan.meses <= 300 or not 0 <= plan.gracia_dias <= licencia.MAX_GRACIA_DIAS:
        raise ErrorDePlan("Los meses deben estar entre 1 y 300 y la gracia entre 0 y 365 días.")
    if plan.concurrentes_normal > plan.concurrentes_pico:
        raise ErrorDePlan("Los concurrentes normales no pueden superar a los de pico.")
    return plan


def cargar(carpeta: Path | str | None = None) -> dict[str, Plan]:
    carpeta = Path(carpeta) if carpeta else CARPETA_POR_OMISION
    planes: dict[str, Plan] = {}
    if not carpeta.is_dir():
        return planes
    for ruta in sorted(carpeta.glob("*.json")):
        try:
            plan = desde_dict(json.loads(ruta.read_text(encoding="utf-8-sig")))
        except (ValueError, ErrorDePlan) as error:
            raise ErrorDePlan(f"El plan «{ruta.name}» no es válido: {error}") from error
        planes[plan.nombre] = plan
    return planes


def obtener(nombre: str, carpeta: Path | str | None = None) -> Plan:
    planes = cargar(carpeta)
    if nombre not in planes:
        raise ErrorDePlan(f"No existe el plan «{nombre}». Los que hay: {', '.join(sorted(planes)) or '(ninguno)'}.")
    return planes[nombre]

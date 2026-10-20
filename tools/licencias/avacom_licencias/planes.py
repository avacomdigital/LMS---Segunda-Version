"""
Los planes como DATO (`planes/*.json`): nada comercial está cableado en el código del emisor. Lo que el CTO decidió del modelo comercial (2026-10-20) está en `planes/reglas.json` y
ninguna licencia puede contradecirlo: la gracia son 30 días corridos EXACTOS (Q-L16) y el tamaño máximo de un aula es de 60 equipos y 1200 usuarios en una misma pantalla (Q-L1). Lo
demás de los planes sigue siendo PROVISIONAL (los concurrentes, los módulos, los meses).

Un plan dice: tipo, meses de vigencia, días de gracia, los cuatro límites (un número o «sin_tope») y los módulos (`*` = todos). Quien opera puede cambiar cualquiera con una opción
de `emitir`, siempre dentro de las reglas; el plan sólo da los valores por omisión.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .dominio_nodo import RAIZ, catalogos, licencia

CARPETA_POR_OMISION = RAIZ / "planes"
ARCHIVO_DE_REGLAS = "reglas.json"
SIN_TOPE = "sin_tope"
TIPOS_EMITIBLES = (licencia.TIPO_PRODUCCION, licencia.TIPO_EVALUACION)


class ErrorDePlan(ValueError):
    """Un plan o una opción no cumple las reglas del módulo."""


@dataclass(frozen=True)
class Reglas:
    """Lo que decidió el CTO y ninguna licencia puede contradecir. Un valor `None` no se exige. Vive en `planes/reglas.json`: cambiarlo no toca código."""

    gracia_dias: int | None = None          # Q-L16: la gracia son esos días corridos exactos
    max_equipos: int | None = None          # Q-L1: el tamaño máximo de un aula
    max_usuarios: int | None = None

    def descripcion(self) -> str:
        partes = []
        if self.gracia_dias is not None:
            partes.append(f"gracia de {self.gracia_dias} días corridos exactos")
        if self.max_equipos is not None or self.max_usuarios is not None:
            partes.append(f"tamaño máximo de un aula: {self.max_equipos if self.max_equipos is not None else 'sin tope'} equipos y "
                          f"{self.max_usuarios if self.max_usuarios is not None else 'sin tope'} usuarios")
        return " · ".join(partes) if partes else "sin reglas"


def cargar_reglas(carpeta: Path | str | None = None) -> Reglas:
    """Las reglas de la carpeta de planes (`reglas.json`). Sin ese archivo no se exige nada."""
    ruta = (Path(carpeta) if carpeta else CARPETA_POR_OMISION) / ARCHIVO_DE_REGLAS
    if not ruta.is_file():
        return Reglas()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
        tamano = datos.get("tamano_maximo") or {}
        entero = lambda valor: None if valor is None else int(valor)      # noqa: E731
        reglas = Reglas(gracia_dias=entero(datos.get("gracia_dias")), max_equipos=entero(tamano.get("equipos")), max_usuarios=entero(tamano.get("usuarios")))
    except (OSError, ValueError, TypeError, AttributeError) as error:
        raise ErrorDePlan(f"«{ARCHIVO_DE_REGLAS}» no es válido: {error}") from error
    if any(valor is not None and valor < 1 for valor in (reglas.max_equipos, reglas.max_usuarios)) or (reglas.gracia_dias is not None and not 0 <= reglas.gracia_dias <= licencia.MAX_GRACIA_DIAS):
        raise ErrorDePlan(f"«{ARCHIVO_DE_REGLAS}» trae un valor fuera de rango.")
    return reglas


def comprobar(reglas: Reglas, *, gracia_dias: int, equipos: int, usuarios: int) -> None:
    """Lanza `ErrorDePlan` si la gracia o el tamaño contradicen lo que decidió el CTO. «Sin tope» siempre supera un máximo."""
    if reglas.gracia_dias is not None and gracia_dias != reglas.gracia_dias:
        raise ErrorDePlan(f"La gracia es de {reglas.gracia_dias} días corridos exactos (decisión del CTO, Q-L16): no se emiten licencias con {gracia_dias}.")
    if (reglas.max_equipos is not None and equipos > reglas.max_equipos) or (reglas.max_usuarios is not None and usuarios > reglas.max_usuarios):
        raise ErrorDePlan(f"El tamaño máximo de un aula es de {reglas.max_equipos if reglas.max_equipos is not None else 'sin tope'} equipos y "
                          f"{reglas.max_usuarios if reglas.max_usuarios is not None else 'sin tope'} usuarios (decisión del CTO, Q-L1): no se emiten licencias con más, ni «sin_tope».")


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


def desde_dict(datos: dict, reglas: Reglas | None = None) -> Plan:
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
    if reglas is not None:
        comprobar(reglas, gracia_dias=plan.gracia_dias, equipos=plan.equipos, usuarios=plan.usuarios)
    return plan


def cargar(carpeta: Path | str | None = None) -> dict[str, Plan]:
    """Los planes de la carpeta. Cada uno tiene que cumplir las reglas del CTO de ESA carpeta (`reglas.json`): un plan que las contradice no se carga."""
    carpeta = Path(carpeta) if carpeta else CARPETA_POR_OMISION
    planes: dict[str, Plan] = {}
    if not carpeta.is_dir():
        return planes
    reglas = cargar_reglas(carpeta)
    for ruta in sorted(carpeta.glob("*.json")):
        if ruta.name == ARCHIVO_DE_REGLAS:
            continue
        try:
            plan = desde_dict(json.loads(ruta.read_text(encoding="utf-8-sig")), reglas)
        except (ValueError, ErrorDePlan) as error:
            raise ErrorDePlan(f"El plan «{ruta.name}» no es válido: {error}") from error
        planes[plan.nombre] = plan
    return planes


def obtener(nombre: str, carpeta: Path | str | None = None) -> Plan:
    planes = cargar(carpeta)
    if nombre not in planes:
        raise ErrorDePlan(f"No existe el plan «{nombre}». Los que hay: {', '.join(sorted(planes)) or '(ninguno)'}.")
    return planes[nombre]

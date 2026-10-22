"""
Compatibilidad (P-04, BR-013, INV-007, P-16): lo que se comprueba ANTES de que una instalación empiece. Si algo falla, la instalación no inicia y se dice por qué. Ante duda,
se conserva la última combinación funcional. Función pura sobre el manifiesto y lo instalado.

Problemas (códigos del contrato; OPS les pone texto):
  modulo_desconocido · modulo_no_actualizable · version_minima_no_cumplida · version_datos_retrocede · contrato_requerido · contrato_incompatible · contrato_biblioteca ·
  serie_menor · ya_aplicado · espacio_insuficiente · licencia
Avisos (no impiden aplicar): cliente_minimo (el nodo no sabe qué Student hay en las tabletas; R-13), contrato_red.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import catalogos as cat
from . import version as ver
from .manifiesto import Manifiesto
from .registro import Instalacion

MARGEN_BYTES = 64 * cat.MIB


@dataclass(frozen=True)
class Problema:
    codigo: str
    modulo: str = ""
    detalle: str = ""

    def como_dict(self) -> dict:
        return {"codigo": self.codigo, "modulo": self.modulo, "detalle": self.detalle}


@dataclass(frozen=True)
class Compatibilidad:
    problemas: tuple[Problema, ...]
    avisos: tuple[Problema, ...]
    espacio_requerido: int
    espacio_libre: int | None

    @property
    def ok(self) -> bool:
        return not self.problemas

    @property
    def solo_espacio(self) -> bool:
        return bool(self.problemas) and all(p.codigo == "espacio_insuficiente" for p in self.problemas)

    @property
    def ya_aplicado(self) -> bool:
        return any(p.codigo == "ya_aplicado" for p in self.problemas) and all(p.codigo in ("ya_aplicado",) for p in self.problemas)

    @property
    def serie_menor(self) -> bool:
        return any(p.codigo == "serie_menor" for p in self.problemas)

    def como_dict(self) -> dict:
        return {"ok": self.ok, "problemas": [p.como_dict() for p in self.problemas], "avisos": [p.como_dict() for p in self.avisos], "espacio_requerido": self.espacio_requerido,
                "espacio_libre": self.espacio_libre}


def espacio_requerido(m: Manifiesto, bytes_paquete: int, bytes_base: int, bytes_instantanea: int | None = None) -> int:
    """Copia de la base (+wal, +shm), instantánea del código que cambia, el staging y el propio paquete, más un margen (P-04)."""
    instantanea = m.bytes_total if bytes_instantanea is None else int(bytes_instantanea)
    return int(bytes_base) + instantanea + m.bytes_total + int(bytes_paquete) + max(int(m.requisitos.espacio_bytes), 0) + MARGEN_BYTES


def evaluar(m: Manifiesto, inst: Instalacion, espacio_libre: int | None, bytes_requeridos: int) -> Compatibilidad:
    problemas: list[Problema] = []
    avisos: list[Problema] = []
    if m.version_minima is not None and ver.comparar(inst.version_producto, m.version_minima) < 0:
        problemas.append(Problema("version_minima_no_cumplida", detalle=f"El paquete exige la versión {m.version_minima} o posterior y el nodo tiene la {inst.version_producto}."))
    if ver.comparar(m.version_producto, inst.version_producto) < 0:
        problemas.append(Problema("serie_menor", detalle=f"El paquete lleva a la versión {m.version_producto}, anterior a la instalada ({inst.version_producto})."))
    if m.requisitos.contrato_biblioteca is not None and m.requisitos.contrato_biblioteca != inst.contrato_biblioteca:
        problemas.append(Problema("contrato_biblioteca", detalle=f"El paquete habla el contrato {m.requisitos.contrato_biblioteca} de AVACOM Biblioteca y este nodo el {inst.contrato_biblioteca}."))
    nuevos = {x.nombre: x for x in m.modulos}
    for x in m.modulos:
        actual = inst.modulos.get(x.nombre)
        if actual is None:
            problemas.append(Problema("modulo_desconocido", x.nombre, "El nodo no tiene ese módulo: un módulo nuevo entra con el instalador completo."))
            continue
        if not actual.actualizable:
            problemas.append(Problema("modulo_no_actualizable", x.nombre, "Ese módulo no se actualiza por separado."))
            continue
        if x.serie < actual.serie:
            problemas.append(Problema("serie_menor", x.nombre, f"El paquete trae la serie {x.serie} y el nodo ya tiene la {actual.serie}: no se degrada."))
        elif x.serie == actual.serie:
            problemas.append(Problema("ya_aplicado", x.nombre, f"La serie {x.serie} ya está aplicada."))
        if x.version_datos < actual.version_datos:
            problemas.append(Problema("version_datos_retrocede", x.nombre, f"El paquete deja los datos en la versión {x.version_datos} y el nodo ya va por la {actual.version_datos}."))
        for otro, minimo in x.requiere.items():
            tiene = nuevos[otro].version_contrato if otro in nuevos else (inst.modulos[otro].version_contrato if otro in inst.modulos else None)
            if tiene is None or tiene < minimo:
                problemas.append(Problema("contrato_requerido", x.nombre, f"Necesita el contrato {minimo} de «{otro}» y el nodo tiene {'ninguno' if tiene is None else tiene}."))
        if x.cambia_contrato or x.version_contrato != actual.version_contrato:
            # INV-007: ningún consumidor instalado (que el paquete no traiga también) puede quedar fuera del rango que acepta
            for nombre, consumidor in inst.modulos.items():
                if nombre in nuevos or x.nombre not in consumidor.consume:
                    continue
                minimo, maximo = consumidor.consume[x.nombre]
                if not minimo <= x.version_contrato <= maximo:
                    problemas.append(Problema("contrato_incompatible", x.nombre, f"«{nombre}» acepta los contratos {minimo}…{maximo} de «{x.nombre}» y el paquete trae el {x.version_contrato}."))
    if not inst.licencia_admite:
        problemas.append(Problema("licencia", detalle=inst.motivo_licencia or "La licencia no admite lo que la actualización habilita."))
    if espacio_libre is not None and espacio_libre < bytes_requeridos:
        problemas.append(Problema("espacio_insuficiente", detalle=f"Hacen falta {bytes_requeridos // cat.MIB} MB libres y hay {espacio_libre // cat.MIB} MB."))
    if m.requisitos.cliente_minimo is not None and ver.comparar(m.requisitos.cliente_minimo, inst.version_producto) > 0:
        avisos.append(Problema("cliente_minimo", detalle=f"Las tabletas y los OPS deben estar en la {m.requisitos.cliente_minimo} o posterior: el nodo no puede comprobarlo (R-13)."))
    if m.requisitos.contrato_red is not None:
        avisos.append(Problema("contrato_red", detalle=f"El paquete cambia el contrato de red con los clientes (contrato {m.requisitos.contrato_red}): actualizar OPS y Student."))
    return Compatibilidad(problemas=tuple(problemas), avisos=tuple(avisos), espacio_requerido=int(bytes_requeridos), espacio_libre=espacio_libre)

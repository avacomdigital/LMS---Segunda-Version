"""
El catálogo de tipos de evento como DATO (P-04): cada tipo declara su módulo productor, su clase (una sola de las siete), su sensibilidad, su clave de deduplicación (BR-133),
su retención y las versiones que existen. Más el validador de nombres (BR-122), que acepta las DOS formas del Maestro: `dominio.hecho.vN` y `dominio.objeto.accion.vN`.

Puro: no importa Django. Los datos viven en `catalogo_datos.py` (generado del inventario del código); lo que el catálogo decide sobre un tipo se pide aquí.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import catalogos as cat
from .catalogo_datos import TIPOS
from .errores import NombreInvalido, TipoNoCatalogado

# BR-122: minúsculas, snake_case, dos o tres segmentos antes de la versión, versión `vN` con N ≥ 1.
_PATRON = re.compile(r"^(?P<dominio>[a-z][a-z0-9_]*)\.(?P<resto>[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?)\.v(?P<version>[1-9][0-9]*)$")
_SEGMENTO = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
# «Acción en participio»: regulares (-ado/-ido y sus plurales y femeninos) e irregulares del español que ya aparecen o pueden aparecer en un nombre de hecho.
_PARTICIPIO_REGULAR = re.compile(r"(ad|id)[oa]s?$")
_PARTICIPIOS_IRREGULARES = frozenset({
    "abierto", "abierta", "abiertos", "abiertas", "cubierto", "cubierta", "descubierto", "descubierta", "escrito", "escrita", "escritos", "escritas", "inscrito", "inscrita",
    "visto", "vista", "vistos", "vistas", "puesto", "puesta", "puestos", "puestas", "compuesto", "compuesta", "dispuesto", "dispuesta", "repuesto", "repuesta", "hecho", "hecha",
    "hechos", "hechas", "deshecho", "deshecha", "dicho", "dicha", "resuelto", "resuelta", "resueltos", "resueltas", "devuelto", "devuelta", "vuelto", "vuelta", "envuelto",
    "envuelta", "roto", "rota", "rotos", "rotas", "impreso", "impresa", "frito", "frita", "satisfecho", "satisfecha", "provisto", "provista", "muerto", "muerta", "absuelto",
    "absuelta", "disuelto", "disuelta", "suelto", "suelta", "descrito", "descrita", "prescrito", "prescrita", "suscrito", "suscrita", "propuesto", "propuesta", "expuesto",
    "expuesta", "supuesto", "supuesta", "detenido", "detenida", "retenido", "retenida",
})


@dataclass(frozen=True)
class Nombre:
    dominio: str
    objeto: str | None        # None en la forma corta `dominio.hecho.vN`
    accion: str               # el último segmento antes de la versión (en la forma corta, el hecho)
    version: int
    base: str                 # el tipo sin la versión

    @property
    def participio(self) -> bool:
        ultimo = self.accion.rsplit("_", 1)[-1]
        return bool(_PARTICIPIO_REGULAR.search(ultimo)) or ultimo in _PARTICIPIOS_IRREGULARES


def analizar(tipo: str) -> Nombre:
    """Separa el nombre en sus partes o lanza `NombreInvalido` (BR-122). NO exige el participio: lo informa (`Nombre.participio`) para que el inventario lo liste."""
    m = _PATRON.match(tipo or "")
    if m is None:
        raise NombreInvalido(f"El tipo de evento «{tipo}» no sigue el patrón dominio.objeto.accion.vN (minúsculas, snake_case, versión vN).", tipo=tipo)
    partes = m.group("resto").split(".")
    for segmento in (m.group("dominio"), *partes):
        if not _SEGMENTO.match(segmento):
            raise NombreInvalido(f"El segmento «{segmento}» de «{tipo}» no es snake_case.", tipo=tipo)
    objeto = partes[0] if len(partes) == 2 else None
    return Nombre(m.group("dominio"), objeto, partes[-1], int(m.group("version")), tipo.rsplit(".v", 1)[0])


def validar_nombre(tipo: str, exigir_participio: bool = True) -> Nombre:
    """`analizar` y, además, la acción en participio (lo que BR-122 exige a un tipo NUEVO)."""
    nombre = analizar(tipo)
    if exigir_participio and not nombre.participio:
        raise NombreInvalido(f"La acción de «{tipo}» («{nombre.accion}») no está en participio (BR-122).", tipo=tipo)
    return nombre


# Un tipo tiene UN autor (R-09)… salvo el caso que el repo ya traía al cortar (Fase 3, D-25): el modo de estudio publica `evaluacion.respuesta_registrada.v1` (FUN-083) por cada
# respuesta de PRÁCTICA, con el nombre del tipo de MOD-010 y una carga propia (práctica y asignación de estudio, no intento). Se declara aquí como COAUTOR para que el corte no lo rechace
# ni lo marque; el sobre lleva `modulo = modo_estudio`, así que quien lea la fuente `evaluacion` no lo recibe y nadie lo confunde con el de un examen. Hallazgo 7 de `01-diseno.md`.
COAUTORES: dict[str, tuple[str, ...]] = {"evaluacion.respuesta_registrada.v1": ("modo_estudio",)}


@dataclass(frozen=True)
class Definicion:
    tipo: str
    modulo: str
    clase: str
    sensibilidad: str
    clave_dedup: tuple[str, ...]
    retencion_dias: int | None          # None = permanente
    versiones: tuple[int, ...]
    inmutable: bool
    coautores: tuple[str, ...] = ()     # los otros módulos que también lo publican (D-25); casi siempre ninguno

    @property
    def version(self) -> int:
        return max(self.versiones)

    @property
    def autores(self) -> tuple[str, ...]:
        return (self.modulo, *self.coautores)


def _definicion(tipo: str, ciclo_meses: int) -> Definicion:
    modulo, clase, sensibilidad, clave, retencion, versiones = TIPOS[tipo]
    dias = cat.retencion_dias(clase, ciclo_meses) if retencion == "clase" else retencion
    return Definicion(tipo, modulo, clase, sensibilidad, tuple(clave), dias, tuple(versiones), clase in cat.INMUTABLES, COAUTORES.get(tipo, ()))


def resolver(tipo: str, ciclo_meses: int = cat.CICLO_MESES_POR_DEFECTO) -> Definicion | None:
    """La definición del tipo, o None si no está en el catálogo."""
    if tipo not in TIPOS:
        return None
    return _definicion(tipo, ciclo_meses)


def exigir(tipo: str, ciclo_meses: int = cat.CICLO_MESES_POR_DEFECTO) -> Definicion:
    d = resolver(tipo, ciclo_meses)
    if d is None:
        raise TipoNoCatalogado(f"El tipo de evento «{tipo}» no está en el catálogo de la cola.", tipo=tipo)
    return d


def clase_por_prefijo(tipo: str) -> str:
    """La clase que le TOCARÍA a un tipo que no está en el catálogo, por su dominio (para aceptarlo en producción marcado `no_catalogado`, R-06)."""
    prefijo = tipo.split(".", 1)[0]
    por_prefijo = {}
    for t, (_, clase, *_resto) in TIPOS.items():
        por_prefijo.setdefault(t.split(".", 1)[0], clase)
    return por_prefijo.get(prefijo, cat.CLASE_TECNICO)


def tipos_de(modulo: str) -> tuple[str, ...]:
    return tuple(sorted(t for t, (m, *_r) in TIPOS.items() if m == modulo))


def modulos() -> tuple[str, ...]:
    return tuple(sorted({m for (m, *_r) in TIPOS.values()}))


def compatible(declarada: int, producida: int) -> bool:
    """BR-011 · INV-006: un consumidor escrito para la versión N procesa N o superior (ignora lo que desconoce). Uno escrito para una versión que el productor aún no publica, no."""
    return int(declarada) <= int(producida)


def hallazgos() -> list[dict]:
    """Los nombres del catálogo que NO cumplen BR-122 al pie de la letra (para `01-diseno.md`; no se corrigen en módulos ajenos: se piden al dueño)."""
    salida = []
    for tipo in sorted(TIPOS):
        try:
            nombre = analizar(tipo)
        except NombreInvalido as error:
            salida.append({"tipo": tipo, "problema": "patron", "detalle": error.detalle})
            continue
        if not nombre.participio:
            salida.append({"tipo": tipo, "problema": "sin_participio", "detalle": f"la acción «{nombre.accion}» no está en participio"})
    return salida

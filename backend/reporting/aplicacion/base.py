"""
Lo común a los casos de uso de MOD-013: los servicios que entrega el composition root, el estado y el corte de las proyecciones (BR-083), el bloque de corte que lleva cada
reporte, el filtro por nodo académico y el alcance de un permiso sobre una clase. Ningún archivo de esta carpeta importa Django.
"""
from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from ..dominio import catalogos as cat
from ..dominio import integracion
from ..dominio import texto as tx
from ..dominio.errores import DatosInvalidos, FueraDeAlcance, NodoNoInstalado
from .puertos import Actor, Autorizacion, Reloj, UnidadDeTrabajo

NODO_PARAMETROS = ("country", "level", "grade", "subject", "topic")      # los mismos filtros del árbol que usa AVACOM Contenido y la búsqueda
_CODIGO_DE_NODO = re.compile(r"^[\w.:-]{1,64}$")


def parametros_de_nodo(consulta: dict) -> dict[str, str]:
    """
    Los códigos del árbol académico que trae una consulta (país, nivel, grado, materia, tema). Cada uno tiene que parecerse a un CÓDIGO —letras, números y `. _ : -`, hasta 64—: se
    guardan en los recientes, en la exportación y en el asiento encadenado de la bitácora (que no se puede podar), así que no pueden ser un texto cualquiera ni de cualquier tamaño.
    """
    salida: dict[str, str] = {}
    for clave in NODO_PARAMETROS:
        valor = consulta.get(clave)
        if valor in (None, ""):
            continue
        texto = str(valor)
        if not _CODIGO_DE_NODO.match(texto):
            raise DatosInvalidos("El filtro por materia trae un código que no es válido.", filtro=clave)
        salida[clave] = texto
    return salida


@dataclass(frozen=True)
class ConfigReporting:
    """Parámetros que decide la instalación (`AVACOM_REPORTES_*`). Los lee el composition root de `settings`; los casos de uso sólo ven este objeto."""

    lote_eventos: int = cat.LOTE_DE_EVENTOS
    sincronizar_al_consultar: bool = True          # el reporte se pone al día con los módulos antes de responder (lo que el hilo aún no alcanzó)
    ttl_exportacion_ms: int = cat.TTL_DE_EXPORTACION_MS
    version_del_nodo: str = ""


@dataclass
class Servicios:
    """Lo que el composition root entrega a todos los casos de uso."""

    uow: Callable[..., UnidadDeTrabajo]
    reloj: Reloj
    autorizacion: Autorizacion
    escritor: object                                # `EscritorDeArchivos` (infraestructura): documento → xlsx/csv
    config: ConfigReporting = ConfigReporting()


def nuevo_id() -> str:
    return str(uuid.uuid4())


def exigir_nodo_instalado(uow: UnidadDeTrabajo) -> str:
    organizacion = uow.identidad.organizacion_id()
    if not organizacion:
        raise NodoNoInstalado("El nodo aún no está instalado: no hay organización a la que atar grupos, alumnos y periodos.")
    return organizacion


def grupo_resumido(grupo: dict | None, grupo_id: str = "") -> dict | None:
    if grupo is None:
        return None if not grupo_id else {"id": grupo_id, "codigo": "", "nombre": "", "periodo": "", "nivel_clave": ""}
    return {"id": grupo["id"], "codigo": grupo["codigo"], "nombre": grupo["nombre"], "periodo": grupo["periodo"], "nivel_clave": grupo["nivel_clave"] or ""}


# ------------------------------------------------------------------------------------------------ estado y corte (H y BR-083)

def _fuente(uow: UnidadDeTrabajo, nombre: str):
    return {cat.AULA: uow.aula, cat.EVALUACION: uow.evaluacion, cat.CALIFICACION: uow.libro, cat.ESTUDIO: uow.estudio}[nombre]


def estado_y_corte(uow: UnidadDeTrabajo, ahora: int) -> tuple[str, int]:
    """`(estado, corte_en)`. Al día: se aplicó TODO lo que los módulos habían publicado, así que los datos son los de este instante. Rezagada: hay eventos relevantes sin aplicar
    y el corte es el instante justo antes del más viejo (lo que el reporte sabe es lo anterior). Reconstruyéndose: lo último que se confirmó. El estado «rezagada» no se guarda:
    se deriva (como en Search) para que nunca quede viejo."""
    guardado = uow.estado.get()
    if guardado["reconstruyendose"]:
        return cat.RECONSTRUYENDOSE, int(guardado["reconstruida_en"] or guardado["actualizada_en"] or ahora)
    mas_viejo: int | None = None
    for nombre in cat.FUENTES:
        eventos, _ = _fuente(uow, nombre).eventos_desde(uow.marcas.get(nombre), 1, cat.EVENTOS_CONSUMIDOS[nombre])
        if eventos:
            instante = int(eventos[0]["creado_en"])
            mas_viejo = instante if mas_viejo is None else min(mas_viejo, instante)
    if mas_viejo is None:
        return cat.AL_DIA, ahora
    return cat.REZAGADA, max(0, mas_viejo - 1)


def bloque_de_corte(s: Servicios, ahora: int, estado: str, corte_en: int, senales: list[dict], equipos_total: int) -> dict:
    """El bloque `corte` de TODO reporte (BR-083): el instante de corte de los datos, qué tan viejos son, el estado de integración de los equipos en ese instante y la línea que
    se muestra («Datos al 15 oct · 10:42 · 2 tabletas sin sincronizar»). El archivo exportado lleva exactamente lo mismo."""
    integ = integracion.resumir(senales, equipos_total, ahora)
    return {"en": corte_en, "antiguedad_ms": max(0, ahora - corte_en), "estado": estado, "incompleto": integ["estado"] == "incompleta", "integracion": integ,
            "texto": tx.linea_de_corte(s.reloj.a_local(corte_en), integ), "explicacion": tx.EXPLICACION_DEL_CORTE}


# ------------------------------------------------------------------------------------------------ el filtro por nodo académico (FUN-143)

def filtro_de_nodo(uow: UnidadDeTrabajo, consulta: dict) -> tuple[set[str] | None, dict | None]:
    """`(curso_refs, aviso)`: los cursos que cuelgan del nodo académico pedido (país, nivel, grado, materia, tema), o None si no se pidió ninguno. Como en la búsqueda, con la
    biblioteca cerrada el filtro NO se aplica y se dice (no se enseña lo que no se pudo filtrar sin avisar)."""
    arbol = parametros_de_nodo(consulta)
    if not arbol:
        return None, None
    cursos = uow.arbol.cursos_del_arbol(arbol)
    if cursos is None:
        return None, {"filtro": "nodo", "aplicado": False, "texto": "No se pudo filtrar por nodo académico porque AVACOM Biblioteca no respondió: se muestra todo."}
    return cursos, {"filtro": "nodo", "aplicado": True, "texto": ""}


# ------------------------------------------------------------------------------------------------ alcance

def exigir_en_clase(autorizacion: Autorizacion, actor: Actor, permiso: str, clase: dict) -> None:
    """El alcance de un permiso sobre UNA clase: el de su grupo; y, con alcance recortado a los grupos propios, también la clase que el mismo profesor abrió (sin padrón,
    Q-34, la clase no tiene grupo y sólo la ve quien la abrió o quien ve toda la organización)."""
    grupo = clase.get("grupo_id") or ""
    if grupo:
        try:
            return autorizacion.exigir(actor, permiso, grupo_id=grupo)
        except FueraDeAlcance:
            if actor.autenticado and actor.id and clase.get("profesor_id") == actor.id:
                return autorizacion.exigir(actor, permiso)
            raise
    if actor.autenticado and actor.id and clase.get("profesor_id") == actor.id:
        return autorizacion.exigir(actor, permiso)
    return autorizacion.exigir(actor, permiso, organizacion=True)


class _CasoDeUso:
    """Base de los casos de uso: una transacción por caso, con sus servicios."""

    def __init__(self, servicios: Servicios):
        self.s = servicios

    @staticmethod
    def _publicar(uow: UnidadDeTrabajo, agregado_tipo: str, agregado_id: str, evento: str, carga: dict, ahora: int) -> None:
        """El evento de salida en la misma transacción que el hecho. Nunca lleva nombres de personas ni el contenido de un reporte."""
        uow.outbox.publicar(agregado_tipo, agregado_id, evento, {**carga, "instante": ahora})

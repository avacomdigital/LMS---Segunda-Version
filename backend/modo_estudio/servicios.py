"""
La interfaz de MOD-008 para los OTROS módulos del mismo proceso (BR-004: quien necesita algo de datos ajenos invoca la interfaz del propietario).
La usa MOD-009: liberar un equipo asignado exige que no conserve un paquete de estudio activo (FUN-093). Se resuelve de forma perezosa desde
`device_manager` (sin importarse al cargar), sin ciclo de importación.

Devuelve y recibe tipos simples; no abre ninguna transacción.
"""
from __future__ import annotations

from .infraestructura.contenedor import RelojNodo
from .infraestructura.unidad_trabajo import Cajones


def paquetes_activos_en(dispositivo_id: str, momento: int | None = None) -> int:
    """Cuántos paquetes de estudio conserva un equipo: `solicitado`, `descargandose` o `disponible`, no retirados y todavía vigentes (con el reloj del
    nodo). Un paquete vencido por vigencia ya no es material que proteger."""
    if not dispositivo_id:
        return 0
    return Cajones().paquetes.activos_en(dispositivo_id, momento if momento is not None else RelojNodo().ahora_ms())


# ------------------------------------------------------------------------------------------------- lectura (MOD-021 · Search)
# Search no lee `m08_*` por su cuenta (BR-004): pide estas lecturas a su dueño. Devuelven dicts planos y no abren ninguna transacción.

_CAMPOS_ASIGNACION = ("id", "grupo_id", "grupo_rotulo", "profesor_id", "fuente_curso", "curso_ref", "curso_rotulo", "leccion_ref", "leccion_rotulo", "titulo", "descripcion",
                      "asignatura_rotulo", "unidad_rotulo", "estado", "creada_en")


def _asignacion(fila) -> dict:
    return {campo: getattr(fila, campo) for campo in _CAMPOS_ASIGNACION}


def asignacion(asignacion_id: str) -> dict | None:
    """La asignación de estudio tal como está AHORA, o None."""
    from . import models as m

    fila = m.Asignacion.objects.filter(pk=asignacion_id).first() if asignacion_id else None
    return _asignacion(fila) if fila else None


def asignaciones(grupo_ids: list[str] | None = None) -> list[dict]:
    """Todas las asignaciones de estudio (o las de esos grupos), de la más antigua a la más reciente."""
    from . import models as m

    filas = m.Asignacion.objects.order_by("creada_en", "id")
    if grupo_ids is not None:
        filas = filas.filter(grupo_id__in=grupo_ids)
    return [_asignacion(f) for f in filas]


MODULO = "modo_estudio"          # el nombre con que este módulo firma sus eventos en la cola única (MOD-015, desde la migración 0002)


def ultima_secuencia() -> int:
    """La última secuencia que este módulo emitió en la cola única (o, si no publicó nada desde el corte, el último id de su cola antigua)."""
    from nodo import servicios as nodo

    corte = nodo.corte_de(MODULO)
    return max(nodo.ultima_secuencia(MODULO), int(corte["ultima_legada"]) if corte else 0)


def eventos_desde(secuencia: int, limite: int, tipos: tuple[str, ...]) -> tuple[list[dict], int]:
    """`(eventos, hasta_donde_se_miró)`: los eventos de esos `tipos` con secuencia MAYOR a la dada, en orden, por la fachada de MOD-015 (P-05): primero lo que quedó en la cola
    antigua (`m08_evento_salida`, por `eventos_legados`) y después `m15_evento`, como un flujo continuo. LECTURA: no marca nada como publicado."""
    from nodo import servicios as nodo

    if not tipos:
        return [], int(secuencia)
    return nodo.leer(MODULO, int(secuencia), int(limite), tuple(tipos))


def eventos_legados(desde: int, limite: int, tipos: tuple[str, ...] | None, hasta: int) -> tuple[list[dict], int]:
    """El lector de la cola ANTIGUA de este módulo (`m08_evento_salida`, intacta desde el corte a la cola única, BR-016), que MOD-015 llama por su fachada: los eventos con
    `desde < id ≤ hasta` (y de esos `tipos`, o todos), en orden, y hasta dónde se miró. Lo registra `apps.ready` (R-09: la cola no lee tablas ajenas). Lectura pura."""
    from . import models as m

    filas = m.EventoSalida.objects.filter(id__gt=int(desde), id__lte=int(hasta))
    if tipos is not None:
        filas = filas.filter(tipo_evento__in=list(tipos))
    filas = list(filas.order_by("id")[: int(limite)])
    return [{"secuencia": f.id, "tipo": f.tipo_evento, "agregado_tipo": f.agregado_tipo, "agregado_id": f.agregado_id, "carga": f.carga, "creado_en": f.creado_en}
            for f in filas], (filas[-1].id if len(filas) >= int(limite) else int(hasta))


# ------------------------------------------------------------------------------------------------- lectura (MOD-013 · Reporting)
# Reporting no lee `m08_*` por su cuenta (BR-004): pide estas lecturas a su dueño. Dicts planos, sin transacción, sin cambiar nada.

def asignaciones_de_estudio(grupo_ids: list[str] | None = None) -> list[dict]:
    """Las asignaciones de estudio (o las de esos grupos) con lo que hace falta para saber quién las debe y si vencieron: `alcance`, `destinatarios`, `fecha_limite`, `plazo`
    y `cerrada_en`. De la más antigua a la más reciente."""
    from . import models as m

    filas = m.Asignacion.objects.order_by("creada_en", "id")
    if grupo_ids is not None:
        filas = filas.filter(grupo_id__in=grupo_ids)
    return [{**_asignacion(f), "alcance": f.alcance, "destinatarios": list(f.destinatarios or []), "fecha_limite": f.fecha_limite, "plazo": f.plazo, "cerrada_en": f.cerrada_en}
            for f in filas]


def tareas_de(asignacion_ids: list[str]) -> list[dict]:
    """El estado de cada alumno en esas asignaciones (`m08_tarea`): sin el detalle de los bloques vistos ni de las prácticas, sólo cifras. Una asignación sin tarea de un alumno
    equivale a `pendiente` (lo decide quien llama)."""
    from . import models as m

    if not asignacion_ids:
        return []
    return [{"asignacion_id": t.asignacion_id, "alumno_id": t.alumno_id, "estado": t.estado, "avance_pct": float(t.avance_pct), "fuera_de_plazo": t.fuera_de_plazo,
             "practica_intentos": t.practica_intentos, "practica_mejor": t.practica_mejor, "practica_total": t.practica_total, "abierta_en": t.abierta_en,
             "ultimo_avance_en": t.ultimo_avance_en, "completada_en": t.completada_en}
            for t in m.Tarea.objects.filter(asignacion_id__in=asignacion_ids).order_by("asignacion_id", "alumno_id")]

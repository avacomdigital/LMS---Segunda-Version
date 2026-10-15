"""
La interfaz de MOD-007 para los OTROS módulos del mismo proceso (BR-004: quien necesita un dato ajeno invoca la interfaz del propietario). La usa Search (MOD-021):
lee las sesiones de clase y su cola de salida sin tocar `m07_*`, y pregunta si hay una clase en curso antes de reconstruir su índice.

Devuelve dicts planos; las lecturas no abren ninguna transacción ni cambian nada.
"""
from __future__ import annotations

_CAMPOS_SESION = ("id", "grupo_id", "grupo_rotulo", "profesor_id", "profesor_rotulo", "via_origen", "fuente_curso", "curso_ref", "curso_rotulo", "leccion_ref",
                  "leccion_rotulo", "objeto_ref", "objeto_rotulo", "estado", "anclajes", "iniciada_en", "finalizada_en", "creado_en")


def _sesion(fila) -> dict:
    return {campo: getattr(fila, campo) for campo in _CAMPOS_SESION}


def sesion(sesion_id: str) -> dict | None:
    """La sesión de clase tal como está AHORA, o None."""
    from . import models as m

    fila = m.SesionDeClase.objects.filter(pk=sesion_id).first() if sesion_id else None
    return _sesion(fila) if fila else None


def sesiones(grupo_ids: list[str] | None = None) -> list[dict]:
    """Todas las sesiones (o las de esos grupos), de la más antigua a la más reciente."""
    from . import models as m

    filas = m.SesionDeClase.objects.order_by("creado_en", "id")
    if grupo_ids is not None:
        filas = filas.filter(grupo_id__in=grupo_ids)
    return [_sesion(f) for f in filas]


def hay_sesion_activa() -> bool:
    """¿Hay una clase abierta o suspendida? (lo que impide reconstruir el índice de búsqueda completo)."""
    from . import models as m
    from .dominio import sesion as dom

    return m.SesionDeClase.objects.filter(estado__in=dom.ACTIVAS).exists()


def ultima_secuencia() -> int:
    from django.db.models import Max

    from . import models as m

    return int(m.EventoSalida.objects.aggregate(u=Max("id"))["u"] or 0)


def eventos_desde(secuencia: int, limite: int, tipos: tuple[str, ...]) -> tuple[list[dict], int]:
    """`(eventos, hasta_donde_se_miró)`: los eventos de esos `tipos` con secuencia MAYOR a la dada, en orden. LECTURA de la cola de salida: no marca nada como publicado."""
    from django.db.models import Max

    from . import models as m

    base = m.EventoSalida.objects.filter(id__gt=secuencia)
    ultimo = base.aggregate(u=Max("id"))["u"]
    if ultimo is None:
        return [], secuencia
    filas = list(base.filter(id__lte=ultimo, tipo_evento__in=tipos).order_by("id")[:limite])
    hasta = filas[-1].id if len(filas) >= limite else ultimo
    return [{"secuencia": f.id, "tipo": f.tipo_evento, "agregado_tipo": f.agregado_tipo, "agregado_id": f.agregado_id, "carga": f.carga, "creado_en": f.creado_en}
            for f in filas], hasta


# ------------------------------------------------------------------------------------------------- lectura (MOD-013 · Reporting)

_DETALLE_DEL_BARRIDO_DE_CIERRE = "cierre de la sesión"       # el `detalle` con que `CerrarSesion` registra el «salió» de cada admitido (aplicacion/casos_uso.py)

def detalle_de_sesion(sesion_id: str) -> dict | None:
    """Lo que Reporting necesita para armar el reporte de UNA clase, sin tocar `m07_*`: la sesión, quiénes participaron (con su equipo y su presencia), las actividades que se
    lanzaron (y a quién) y los intentos con SÓLO sus cifras. Nunca devuelve el contenido de una respuesta ni su veredicto completo: `aciertos` y `calificadas` se cuentan aquí,
    en el módulo dueño. Lectura pura; None si no existe."""
    from . import models as m
    from .dominio import sesion as dom

    fila = m.SesionDeClase.objects.filter(pk=sesion_id).first() if sesion_id else None
    if fila is None:
        return None
    sesion_ = {**_sesion(fila), "origen_cierre": fila.origen_cierre, "nodo_ref": fila.nodo_ref, "creado_por": fila.creado_por}
    # Al cerrar la clase el aula pasa a «salió» a todos los admitidos: lo que de verdad cuenta es cómo estaba cada tableta ANTES de ese barrido (conectada, sin conexión, ya había
    # salido, expulsada). Es el último cambio de presencia que NO es el del cierre (`_DETALLE_DEL_BARRIDO_DE_CIERRE`, el texto con que `CerrarSesion` lo registra).
    antes_del_cierre: dict[str, str] = {}
    for fila_presencia in m.Presencia.objects.filter(participante__sesion_id=sesion_id).exclude(detalle=_DETALLE_DEL_BARRIDO_DE_CIERRE).order_by("participante_id", "momento", "id"):
        antes_del_cierre[fila_presencia.participante_id] = fila_presencia.estado
    participantes = [{"id": p.id, "persona_id": p.persona_id, "estado": p.estado, "presencia_al_cerrar": antes_del_cierre.get(p.id) or p.estado, "ingreso": p.ingreso,
                      "salida": p.salida, "ultimo_latido_en": p.ultimo_latido_en, "dispositivo_id": p.dispositivo_id, "admision_nominal": p.admision_nominal}
                     for p in m.Participante.objects.filter(sesion_id=sesion_id).order_by("ingreso", "id")]
    actividades = []
    for d in m.Distribucion.objects.filter(sesion_id=sesion_id, clase=dom.ACTIVIDAD).order_by("abierta_en", "id").prefetch_related("entregas"):
        actividades.append({"distribucion_id": d.id, "total_preguntas": d.total_preguntas, "abierta_en": d.abierta_en, "cerrada_en": d.cerrada_en,
                            "destinatarios": [e.participante_id for e in d.entregas.all()]})
    intentos = []
    for i in m.Intento.objects.filter(distribucion__sesion_id=sesion_id).order_by("distribucion_id", "participante_id", "numero"):
        veredictos = [(r.get("veredicto") or {}) for r in (i.respuestas or [])]
        calificadas = [v for v in veredictos if not v.get("pendiente") and v.get("puntaje") is not None]
        intentos.append({"distribucion_id": i.distribucion_id, "participante_id": i.participante_id, "persona_id": i.persona_id, "numero": i.numero, "estado": i.estado,
                         "puntaje": i.puntaje, "puntaje_maximo": i.puntaje_maximo, "respondidas": len(veredictos), "calificadas": len(calificadas),
                         "aciertos": sum(1 for v in calificadas if v.get("correcta") is True), "origen_envio": i.origen_envio, "recuperado_de_cola": i.recuperado_de_cola,
                         "enviado_en": i.enviado_en, "iniciado_en": i.iniciado_en, "dispositivo_id": i.dispositivo_id})
    return {"sesion": sesion_, "participantes": participantes, "actividades": actividades, "intentos": intentos}

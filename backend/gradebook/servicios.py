"""
La interfaz de MOD-011 para los OTROS módulos del mismo proceso (BR-004: quien necesita un dato ajeno invoca la interfaz del propietario). La usa Reporting (MOD-013): lee
los resultados del libro YA presentados (con la escala del nivel, o en símbolos en el modo simple) y su cola de salida, sin tocar `m11_*` ni volver a convertir una nota.

Sólo lectura: devuelve dicts planos, no abre ninguna transacción de escritura y no cambia nada. La autorización es de quien llama (Reporting exige sus propios permisos).
"""
from __future__ import annotations


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


def resultados_del_grupo(grupo_id: str) -> dict | None:
    """Lo que el libro dice de un grupo, listo para mostrar: el modo de su nivel (`simple` o `calificaciones`), la escala (si la hay) y, por cada `(asignación, alumno)` con
    resultado, su estado simple, el estado de la calificación, si está publicada y su PRESENTACIÓN ya resuelta (la estampada si se publicó; si no, la provisional con la
    escala vigente; en modo simple, ninguna: ni notas, ni letras, ni números). None si el grupo no existe. Reporting no convierte nada: pide esto."""
    from .aplicacion import base as b
    from .dominio import catalogos as cat
    from .dominio import puntaje as pj
    from .infraestructura.contenedor import servicios as servicios_del_libro

    s = servicios_del_libro()
    with s.uow(lectura=True) as uow:
        grupo = uow.identidad.grupo(grupo_id) if grupo_id else None
        if grupo is None:
            return None
        modo, version = b.modo_del_nivel(uow, grupo["nivel_clave"] or "")
        calificaciones = {c["id"]: c for c in uow.calificaciones.de_grupo(grupo_id)}
        filas = []
        for r in uow.resultados.de_grupo(grupo_id):
            c = calificaciones.get(r["calificacion_aplicable_id"]) if r["calificacion_aplicable_id"] else None
            presentacion = None
            if c is not None:
                if c["estado"] == cat.DEFINITIVA and c.get("presentacion"):
                    presentacion = {**c["presentacion"], "provisional": False}
                elif c["estado"] not in (cat.REABIERTA, cat.ANULADA) and modo == cat.CALIFICACIONES and version is not None:
                    presentacion = {**b.presentar_con(version, c), "provisional": True}
            filas.append({
                "asignacion_id": r["asignacion_id"], "alumno_id": r["alumno_id"], "curso_ref": r["curso_ref"], "estado_simple": r["estado_simple"],
                "estado": r["estado_calificacion"], "publicada": bool(r["publicada"]), "calificacion_id": c["id"] if c else None,
                "puntaje_aplicable": pj.como_numero(r["puntaje_aplicable"]), "presentacion": presentacion,
                "intentos_total": r["intentos_total"], "intentos_registrados": r["intentos_registrados"]})
        escala = None if version is None else {"codigo": version["codigo"], "nombre": version["nombre"], "tipo": version["definicion"].tipo, "numero": version["numero"]}
        return {"grupo_id": grupo_id, "nivel_clave": grupo["nivel_clave"] or "", "modo": modo, "escala": escala, "resultados": filas}

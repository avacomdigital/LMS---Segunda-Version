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


def boletin_de_alumno(alumno_id: str, grupo_id: str, materia: dict | None = None) -> dict | None:
    """Lo que el libro sabe de UN alumno en UN grupo, ya presentado: su resumen, sus cursos (con los puntos brutos sumados y el promedio simple presentado con el sistema del
    nivel), sus insights, lo que el profesor le recomendó y TODAS sus evaluaciones con su nota en bruto y presentada. Es la base del boletín académico de Reportes (MOD-013), que
    autoriza por su cuenta y no convierte nada. `materia` recorta a un nodo académico (`{subject: …}`). None si el grupo no existe o el alumno no está en él."""
    from .aplicacion.boletin import MAXIMO_POR_PAGINA, armar_boletin
    from .infraestructura.contenedor import servicios as servicios_del_libro

    s = servicios_del_libro()
    with s.uow(lectura=True) as uow:
        grupo = uow.identidad.grupo(grupo_id) if grupo_id else None
        if grupo is None:
            return None
        if grupo_id not in uow.identidad.grupos_del_alumno(alumno_id) and not uow.calificaciones.de_alumno(alumno_id, grupo_id):
            return None
        return armar_boletin(uow, alumno_id, grupo, limite=MAXIMO_POR_PAGINA * 10, materia=materia or None, ahora=s.reloj.ahora_ms())


def progreso_del_alumno(alumno_id: str) -> list[dict]:
    """Lo que lleva un alumno en cada curso de cada periodo en que estuvo (los agregados por periodo del libro, de todos sus grupos), con el promedio simple presentado con el
    sistema vigente del nivel de ese grupo: la tercera pregunta del boletín («¿cómo ha progresado?»). Informativo, no ponderado, no oficial."""
    from .aplicacion import base as b
    from .aplicacion.consultas import _presentado
    from .dominio import puntaje as pj
    from .infraestructura.contenedor import servicios as servicios_del_libro

    s = servicios_del_libro()
    with s.uow(lectura=True) as uow:
        salida = []
        grupos: dict[str, dict | None] = {}
        for a in uow.agregados.de_alumno(alumno_id):
            if a["grupo_id"] not in grupos:
                grupos[a["grupo_id"]] = uow.identidad.grupo(a["grupo_id"])
            grupo = grupos[a["grupo_id"]] or {"codigo": "", "nombre": "", "periodo": a["periodo"], "nivel_clave": ""}
            modo, version = b.modo_del_nivel(uow, grupo.get("nivel_clave") or "")
            salida.append({"grupo_id": a["grupo_id"], "grupo_codigo": grupo.get("codigo") or "", "grupo_nombre": grupo.get("nombre") or "", "periodo": a["periodo"],
                           "curso_ref": a["curso_ref"], "calificaciones": a["calificaciones"], "promedio_simple": pj.como_numero(a["promedio_simple"]),
                           "presentado": _presentado(version, modo, pj.como_numero(a["promedio_simple"])), "pendientes": a["pendientes"], "publicadas": a["publicadas"],
                           "modo": modo, "oficial": False, "ponderado": False})
        return sorted(salida, key=lambda x: (x["periodo"], x["grupo_codigo"], x["curso_ref"]))


def politica_institucional() -> dict:
    """La política de evaluación de la institución (país, jurisdicción, institución, política de intentos): lo que el boletín necesita para elegir su plantilla y su encabezado."""
    from .infraestructura.contenedor import servicios as servicios_del_libro

    s = servicios_del_libro()
    with s.uow(lectura=True) as uow:
        p = uow.politica.get()
        return {"pais": p.get("pais") or "", "jurisdiccion": p.get("jurisdiccion") or "", "institucion": p.get("institucion") or "", "politica_intentos": p.get("politica_intentos")}


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

"""
La interfaz de MOD-010 para los OTROS módulos del mismo proceso (BR-004: quien necesita un dato ajeno invoca la interfaz del propietario). La usa el aula
al cerrar una clase (cuenta los intentos que sus alumnos siguen presentando, JRN-011) y el Gradebook (MOD-011), que consume los resultados de la evaluación sin
leer ni escribir `m10_*` por su cuenta. Devuelve cifras y dicts planos; las lecturas no abren ninguna transacción.

Lo que el Gradebook puede PEDIR a MOD-010 (sin que MOD-011 sea dueño de nada de esto):
  · leer intentos y asignaciones, y la cola de salida `m10_evento_salida` desde una secuencia (lectura: marcar lo publicado es oficio de MOD-015)
  · pedirle que asiente la puntuación de un reactivo de revisión docente (`puntuar_respuesta`) y que cierre la revisión (`publicar_revision`): las ejecuta
    MOD-010, dueño de las respuestas, con sus propias reglas y su propia autorización (`assessment.review`), en la transacción del llamador.
"""
from __future__ import annotations

from .infraestructura.unidad_trabajo import Cajones


def intentos_vivos_de(persona_ids: list[str]) -> int:
    """Cuántos intentos de MOD-010 siguen en curso, pausados o restaurándose entre esas personas."""
    return Cajones().intentos.vivos_de_personas(list(persona_ids))


# ---------------------------------------------------------------------------------------------------- lectura (MOD-011)

def intento(intento_id: str) -> dict | None:
    return Cajones().intentos.por_id(intento_id) if intento_id else None


def intentos_del_alumno(asignacion_id: str, alumno_id: str) -> list[dict]:
    return Cajones().intentos.del_alumno(asignacion_id, alumno_id)


def intentos_de_asignacion(asignacion_id: str) -> list[dict]:
    return Cajones().intentos.de_asignacion(asignacion_id)


def intentos_en_revision(asignacion_ids: list[str]) -> list[dict]:
    """Los intentos de esas asignaciones que esperan la revisión del profesor (`en_revision_docente`)."""
    from . import models as m
    from .dominio import catalogos as cat
    from .infraestructura.repositorios import CAMPOS_INTENTO, _d

    if not asignacion_ids:
        return []
    filas = m.Intento.objects.filter(asignacion_id__in=asignacion_ids, estado=cat.EN_REVISION).order_by("entregado_en", "id")
    return [_d(f, CAMPOS_INTENTO) for f in filas]


def asignacion(asignacion_id: str) -> dict | None:
    return Cajones().asignaciones.por_id(asignacion_id) if asignacion_id else None


def asignaciones_de_grupo(grupo_id: str) -> list[dict]:
    return Cajones().asignaciones.listar(grupo_id=grupo_id) if grupo_id else []


def asignaciones_del_alumno(alumno_id: str) -> list[dict]:
    """Las asignaciones (no borrador) que alcanzan al alumno: las de sus grupos y aquellas donde ya tiene un intento (una selección de alumnos sueltos)."""
    from . import models as m
    from .dominio import catalogos as cat
    from .infraestructura.repositorios import CAMPOS_ASIGNACION, _d

    cajones = Cajones()
    vistas: dict[str, dict] = {}
    for grupo_id in cajones.identidad.grupos_del_alumno(alumno_id):
        for a in cajones.asignaciones.listar(grupo_id=grupo_id):
            if a["estado"] != cat.BORRADOR:
                vistas[a["id"]] = a
    con_intento = set(m.Intento.objects.filter(alumno_id=alumno_id).values_list("asignacion_id", flat=True)) - set(vistas)
    for fila in m.Asignacion.objects.filter(pk__in=con_intento).exclude(estado=cat.BORRADOR):
        vistas[fila.id] = _d(fila, CAMPOS_ASIGNACION)
    return sorted(vistas.values(), key=lambda a: (a["creada_en"], a["id"]))


def pares_de_resultados() -> list[tuple[str, str]]:
    """Todos los `(asignacion_id, alumno_id)` con al menos un intento."""
    from . import models as m

    return list(m.Intento.objects.values_list("asignacion_id", "alumno_id").distinct())


def pendientes_de_revision(intento_: dict) -> list[str]:
    from .dominio import respuestas as resp_dom

    return resp_dom.pendientes_de_revision(intento_.get("respuestas") or [])


def aciertos_de(intento_: dict) -> tuple[int, int]:
    """`(aciertos, preguntas)`: una pregunta es un acierto cuando se llevó TODO su puntaje (por la biblioteca o por la revisión del profesor). Las preguntas son
    las del examen de ese alumno, hayan sido respondidas o no."""
    from .dominio import respuestas as resp_dom

    por_ref = {str(r["pregunta_ref"]): r for r in intento_.get("respuestas") or []}
    aciertos = 0
    armado = list(intento_.get("armado") or [])
    for ref in armado:
        r = por_ref.get(ref)
        if r is None:
            continue
        puntaje, maximo = resp_dom.puntaje_de(r)
        if puntaje is not None and maximo and puntaje >= maximo:
            aciertos += 1
    return aciertos, len(armado)


def registrar_compuerta_de_resultado(nombre: str, compuerta) -> None:
    """Un módulo que es dueño de la NOTA (MOD-011) añade su condición a «el alumno ya puede ver su resultado» sin que MOD-010 lo conozca: `compuerta(asignacion, intento)` responde
    `True` si NO lo retiene. Sólo puede cerrar lo que la política de publicación de MOD-010 dejaría abierto, y si falla, cierra (ver `aplicacion/compuertas.py`)."""
    from .aplicacion import compuertas

    compuertas.registrar(nombre, compuerta)


def resultado_liberado(asignacion_: dict, intento_: dict) -> bool:
    """¿Ya liberó MOD-010 este resultado al alumno? (RF-004: lo comprueba el nodo, no la pantalla)."""
    from .aplicacion.motor import Motor

    return Motor.resultado_disponible(asignacion_, intento_)


def asignaciones_sin_grupo() -> list[dict]:
    """Las asignaciones (no borrador) que fueron a alumnos sueltos y no a un grupo: no salen de `asignaciones_de_grupo`."""
    from . import models as m
    from .dominio import catalogos as cat
    from .infraestructura.repositorios import CAMPOS_ASIGNACION, _d

    return [_d(f, CAMPOS_ASIGNACION) for f in m.Asignacion.objects.filter(grupo_id="").exclude(estado=cat.BORRADOR).order_by("creada_en", "id")]


def evaluaciones_en_curso(grupo_ids: list[str], alumno_ids: list[str] | tuple[str, ...] = ()) -> int:
    """Cuántas evaluaciones de esos grupos siguen abiertas, programadas o con algún intento vivo: lo que impide cambiar el modo de calificación de un nivel.
    Con `alumno_ids` (los alumnos de esos grupos) cuentan también las que fueron a alumnos sueltos y los alcanzan: sin grupo, `grupo_id` no las encuentra."""
    from . import models as m
    from .dominio import catalogos as cat

    if not grupo_ids and not alumno_ids:
        return 0
    abiertas = set(m.Asignacion.objects.filter(grupo_id__in=grupo_ids, estado__in=(cat.PROGRAMADA, *cat.ABIERTAS)).values_list("id", flat=True))
    con_vivos = set(m.Intento.objects.filter(asignacion__grupo_id__in=grupo_ids, estado__in=cat.VIVOS).values_list("asignacion_id", flat=True))
    if alumno_ids:
        alumnos = set(alumno_ids)
        for fila in m.Asignacion.objects.filter(grupo_id="", estado__in=(cat.PROGRAMADA, *cat.ABIERTAS)).only("id", "destinatarios"):
            if alumnos & set(fila.destinatarios or []):
                abiertas.add(fila.id)
        con_vivos |= set(m.Intento.objects.filter(asignacion__grupo_id="", alumno_id__in=alumnos, estado__in=cat.VIVOS).values_list("asignacion_id", flat=True))
    return len(abiertas | con_vivos)


def eventos_desde(secuencia: int, limite: int, tipos: tuple[str, ...]) -> tuple[list[dict], int]:
    """`(eventos, hasta_donde_se_miró)`: los eventos de esos `tipos` con secuencia MAYOR a la dada, en orden. Es una LECTURA de la cola de salida: no marca nada
    como publicado. Lo irrelevante (cada respuesta genera uno) se salta en la base; la segunda cifra permite al consumidor no volver a mirarlo."""
    from django.db.models import Max

    from . import models as m

    base = m.EventoSalida.objects.filter(id__gt=secuencia)
    ultimo = base.aggregate(u=Max("id"))["u"]
    if ultimo is None:
        return [], secuencia
    filas = list(base.filter(id__lte=ultimo, tipo_evento__in=tipos).order_by("id")[:limite])
    hasta = filas[-1].id if len(filas) >= limite else ultimo
    return [{"secuencia": f.id, "tipo": f.tipo_evento, "carga": f.carga, "creado_en": f.creado_en} for f in filas], hasta


# -------------------------------------------------------------------------------- escritura por encargo (MOD-011)

def revision_del_intento(actor, intento_id: str) -> dict:
    """Lo que el profesor revisa de un intento: sus preguntas, respuestas y veredictos (`RevisionDelIntento`, permiso `assessment.review`)."""
    from .aplicacion import calificacion as cu
    from .infraestructura.contenedor import servicios

    return cu.RevisionDelIntento(servicios()).ejecutar(actor, intento_id)


def puntuar_respuesta(actor, intento_id: str, pregunta_ref: str, datos: dict) -> dict:
    """MOD-010 asienta la puntuación de un reactivo de revisión docente (`PuntuarRespuesta`): sus reglas, su autorización y su auditoría."""
    from .aplicacion import calificacion as cu
    from .infraestructura.contenedor import servicios

    return cu.PuntuarRespuesta(servicios()).ejecutar(actor, intento_id, pregunta_ref, datos)


def publicar_revision(actor, intento_id: str) -> dict:
    """`en_revision_docente → calificado` cuando no queda nada pendiente (`PublicarIntento`)."""
    from .aplicacion import calificacion as cu
    from .infraestructura.contenedor import servicios

    return cu.PublicarIntento(servicios()).ejecutar(actor, intento_id)


# ------------------------------------------------------------------------------------------------- lectura (MOD-021 · Search)

def ultima_secuencia() -> int:
    """La secuencia del último evento de la cola de salida (0 si no hay). Lectura pura: Search la usa para fijar su marca al construir el índice."""
    from django.db.models import Max

    from . import models as m

    return int(m.EventoSalida.objects.aggregate(u=Max("id"))["u"] or 0)

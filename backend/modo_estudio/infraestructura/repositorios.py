"""
Adaptadores de los puertos de MOD-008 sobre Django: los repositorios de `m08_*` (ORM), la cola de salida y la auditoría (m19 del expediente).

Los casos de uso reciben y devuelven dicts planos; aquí se traducen a filas. Nada se borra (CV-05): un paquete retirado queda con `retirado_en`.
"""
from __future__ import annotations

from django.db.models import Q

from expediente import servicios as expediente_servicios

from .. import models as m
from ..dominio import catalogos as cat

CAMPOS_ASIGNACION = (
    "id", "grupo_id", "grupo_rotulo", "alcance", "destinatarios", "profesor_id", "profesor_rotulo", "fuente_curso", "curso_ref",
    "curso_version", "curso_rotulo", "leccion_ref", "leccion_rotulo", "titulo", "descripcion", "asignatura_rotulo", "unidad_rotulo",
    "consigna", "bloques", "practica", "evaluacion", "bytes_estimados", "paquete_permitido", "fecha_limite", "plazo", "gracia_ms",
    "estado", "creada_en", "cerrada_en", "creado_por",
)
CAMPOS_TAREA = (
    "id", "asignacion_id", "alumno_id", "estado", "bloques_vistos", "ultimo_bloque_ref", "posicion_seg", "avance_pct", "fuera_de_plazo",
    "practica_intentos", "practica_mejor", "practica_ultima", "practica_total", "abierta_en", "ultimo_avance_en", "completada_en", "creada_en",
)
CAMPOS_PAQUETE = (
    "id", "asignacion_id", "alumno_id", "dispositivo_id", "estado", "motivo", "curso_version", "huella", "bytes_total", "archivos",
    "no_incluidos", "vigente_hasta", "solicitado_en", "descarga_iniciada_en", "disponible_en", "retirado_en", "actualizado_en",
)
CAMPOS_PRACTICA = (
    "id", "tarea_id", "alumno_id", "objeto_ref", "objeto_rotulo", "numero", "modo", "estado", "respuestas", "total_preguntas", "aciertos",
    "puntaje", "puntaje_maximo", "origen", "dispositivo_id", "iniciada_en", "terminada_en",
)
CAMPOS_SINCRONIZACION = (
    "id", "emisor_id", "secuencia", "alumno_id", "dispositivo_id", "tipo", "asignacion_id", "estado", "motivo", "ocurrido_en",
    "ocurrido_en_tableta", "recibido_en", "carga", "resultado",
)


def _d(fila, campos) -> dict:
    return {campo: getattr(fila, campo) for campo in campos}


def _filtrado(datos: dict, campos: tuple[str, ...]) -> dict:
    return {k: v for k, v in datos.items() if k in campos}


class AsignacionesDjango:
    def crear(self, datos: dict) -> dict:
        return _d(m.Asignacion.objects.create(**_filtrado(datos, CAMPOS_ASIGNACION)), CAMPOS_ASIGNACION)

    def por_id(self, asignacion_id: str) -> dict | None:
        fila = m.Asignacion.objects.filter(pk=asignacion_id).first()
        return _d(fila, CAMPOS_ASIGNACION) if fila else None

    def actualizar(self, asignacion_id: str, **campos) -> dict:
        m.Asignacion.objects.filter(pk=asignacion_id).update(**_filtrado(campos, CAMPOS_ASIGNACION))
        return self.por_id(asignacion_id)

    def listar(self, *, grupo_id: str | None = None, estado: str | None = None) -> list[dict]:
        filas = m.Asignacion.objects.all()
        if grupo_id:
            filas = filas.filter(grupo_id=grupo_id)
        if estado:
            filas = filas.filter(estado=estado)
        return [_d(f, CAMPOS_ASIGNACION) for f in filas.order_by("-creada_en", "id")]

    def candidatas_del_alumno(self, alumno_id: str, grupo_ids: list[str]) -> list[dict]:
        """De sus grupos, o con él entre los destinatarios. La lista `destinatarios` es JSON: no hay «contiene» portable en SQLite,
        así que las selecciones se filtran aquí (son pocas: una por asignación con alumnos sueltos)."""
        filas = list(m.Asignacion.objects.filter(alcance=cat.GRUPO, grupo_id__in=grupo_ids)) if grupo_ids else []
        filas += [a for a in m.Asignacion.objects.filter(alcance=cat.SELECCION) if alumno_id in (a.destinatarios or [])]
        return [_d(f, CAMPOS_ASIGNACION) for f in filas]


class TareasDjango:
    @staticmethod
    def _a_dict(fila) -> dict:
        datos = _d(fila, CAMPOS_TAREA)
        datos["avance_pct"] = float(datos["avance_pct"])
        return datos

    def crear(self, datos: dict) -> dict:
        return self._a_dict(m.Tarea.objects.create(**_filtrado(datos, CAMPOS_TAREA)))

    def por_id(self, tarea_id: str) -> dict | None:
        fila = m.Tarea.objects.filter(pk=tarea_id).first()
        return self._a_dict(fila) if fila else None

    def obtener(self, asignacion_id: str, alumno_id: str) -> dict | None:
        fila = m.Tarea.objects.filter(asignacion_id=asignacion_id, alumno_id=alumno_id).first()
        return self._a_dict(fila) if fila else None

    def actualizar(self, tarea_id: str, **campos) -> dict:
        m.Tarea.objects.filter(pk=tarea_id).update(**_filtrado(campos, CAMPOS_TAREA))
        return self.por_id(tarea_id)

    def de_alumno(self, alumno_id: str, asignacion_ids: list[str] | None = None) -> dict[str, dict]:
        filas = m.Tarea.objects.filter(alumno_id=alumno_id)
        if asignacion_ids is not None:
            filas = filas.filter(asignacion_id__in=asignacion_ids)
        return {f.asignacion_id: self._a_dict(f) for f in filas}

    def de_asignacion(self, asignacion_id: str) -> list[dict]:
        return [self._a_dict(f) for f in m.Tarea.objects.filter(asignacion_id=asignacion_id).order_by("creada_en", "id")]


class PaquetesDjango:
    def crear(self, datos: dict) -> dict:
        return _d(m.Paquete.objects.create(**_filtrado(datos, CAMPOS_PAQUETE)), CAMPOS_PAQUETE)

    def por_id(self, paquete_id: str) -> dict | None:
        fila = m.Paquete.objects.filter(pk=paquete_id).first()
        return _d(fila, CAMPOS_PAQUETE) if fila else None

    def obtener(self, asignacion_id: str, alumno_id: str, dispositivo_id: str) -> dict | None:
        fila = m.Paquete.objects.filter(asignacion_id=asignacion_id, alumno_id=alumno_id, dispositivo_id=dispositivo_id).first()
        return _d(fila, CAMPOS_PAQUETE) if fila else None

    def actualizar(self, paquete_id: str, **campos) -> dict:
        m.Paquete.objects.filter(pk=paquete_id).update(**_filtrado(campos, CAMPOS_PAQUETE))
        return self.por_id(paquete_id)

    def de_asignacion(self, asignacion_id: str) -> list[dict]:
        filas = m.Paquete.objects.filter(asignacion_id=asignacion_id, retirado_en__isnull=True).order_by("solicitado_en", "id")
        return [_d(f, CAMPOS_PAQUETE) for f in filas]

    def del_aparato(self, alumno_id: str, dispositivo_id: str) -> list[dict]:
        filas = m.Paquete.objects.filter(alumno_id=alumno_id, dispositivo_id=dispositivo_id, retirado_en__isnull=True)
        return [_d(f, CAMPOS_PAQUETE) for f in filas.order_by("solicitado_en", "id")]

    def de_alumno(self, alumno_id: str, asignacion_ids: list[str] | None = None) -> list[dict]:
        filas = m.Paquete.objects.filter(alumno_id=alumno_id, retirado_en__isnull=True)
        if asignacion_ids is not None:
            filas = filas.filter(asignacion_id__in=asignacion_ids)
        return [_d(f, CAMPOS_PAQUETE) for f in filas.order_by("solicitado_en", "id")]

    def activos_en(self, dispositivo_id: str, ahora: int) -> int:
        return (m.Paquete.objects.filter(dispositivo_id=dispositivo_id, estado__in=cat.PAQUETE_ACTIVO, retirado_en__isnull=True)
                .filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=ahora)).count())


class PracticasDjango:
    def crear(self, datos: dict) -> dict:
        return _d(m.Practica.objects.create(**_filtrado(datos, CAMPOS_PRACTICA)), CAMPOS_PRACTICA)

    def por_id(self, practica_id: str) -> dict | None:
        fila = m.Practica.objects.filter(pk=practica_id).first()
        return _d(fila, CAMPOS_PRACTICA) if fila else None

    def actualizar(self, practica_id: str, **campos) -> dict:
        m.Practica.objects.filter(pk=practica_id).update(**_filtrado(campos, CAMPOS_PRACTICA))
        return self.por_id(practica_id)

    def de_tarea(self, tarea_id: str, objeto_ref: str | None = None) -> list[dict]:
        filas = m.Practica.objects.filter(tarea_id=tarea_id)
        if objeto_ref:
            filas = filas.filter(objeto_ref=objeto_ref)
        return [_d(f, CAMPOS_PRACTICA) for f in filas.order_by("objeto_ref", "numero")]

    def obtener(self, tarea_id: str, objeto_ref: str, numero: int) -> dict | None:
        fila = m.Practica.objects.filter(tarea_id=tarea_id, objeto_ref=objeto_ref, numero=numero).first()
        return _d(fila, CAMPOS_PRACTICA) if fila else None

    def en_curso(self, tarea_id: str, objeto_ref: str) -> dict | None:
        fila = m.Practica.objects.filter(tarea_id=tarea_id, objeto_ref=objeto_ref, estado=cat.EN_CURSO).first()
        return _d(fila, CAMPOS_PRACTICA) if fila else None

    def con_en_curso(self, tarea_ids: list[str]) -> set[tuple[str, str]]:
        if not tarea_ids:
            return set()
        return set(m.Practica.objects.filter(tarea_id__in=tarea_ids, estado=cat.EN_CURSO).values_list("tarea_id", "objeto_ref"))


class SincronizacionesDjango:
    def por_emisor_y_secuencia(self, emisor_id: str, secuencia: int) -> dict | None:
        fila = m.Sincronizacion.objects.filter(emisor_id=emisor_id, secuencia=secuencia).first()
        return _d(fila, CAMPOS_SINCRONIZACION) if fila else None

    def crear(self, datos: dict) -> dict:
        return _d(m.Sincronizacion.objects.create(**_filtrado(datos, CAMPOS_SINCRONIZACION)), CAMPOS_SINCRONIZACION)

    def actualizar(self, fila_id: int, **campos) -> dict:
        m.Sincronizacion.objects.filter(pk=fila_id).update(**_filtrado(campos, CAMPOS_SINCRONIZACION))
        return _d(m.Sincronizacion.objects.get(pk=fila_id), CAMPOS_SINCRONIZACION)

    def pendientes_de_decision(self, *, alumno_id: str | None = None, asignacion_id: str | None = None,
                               emisor_id: str | None = None) -> list[dict]:
        filas = m.Sincronizacion.objects.filter(estado=cat.PENDIENTE_DECISION)
        if alumno_id:
            filas = filas.filter(alumno_id=alumno_id)
        if asignacion_id:
            filas = filas.filter(asignacion_id=asignacion_id)
        if emisor_id:
            filas = filas.filter(emisor_id=emisor_id)
        return [_d(f, CAMPOS_SINCRONIZACION) for f in filas.order_by("emisor_id", "secuencia")]

    def por_decision(self, asignacion_id: str, alumno_id: str, secuencia: int, emisor_id: str | None = None) -> list[dict]:
        filas = m.Sincronizacion.objects.filter(asignacion_id=asignacion_id, alumno_id=alumno_id, secuencia=secuencia)
        if emisor_id:
            filas = filas.filter(emisor_id=emisor_id)
        return [_d(f, CAMPOS_SINCRONIZACION) for f in filas.order_by("emisor_id")]

    def del_emisor(self, emisor_id: str, alumno_id: str | None = None) -> list[dict]:
        filas = m.Sincronizacion.objects.filter(emisor_id=emisor_id)
        if alumno_id:
            filas = filas.filter(alumno_id=alumno_id)
        return [_d(f, CAMPOS_SINCRONIZACION) for f in filas.order_by("secuencia")]


class OutboxDjango:
    def publicar(self, agregado_tipo: str, agregado_id: str, tipo_evento: str, carga: dict) -> None:
        if tipo_evento not in cat.EVENTOS:
            raise ValueError(f"Evento fuera del catálogo de MOD-008: {tipo_evento}")
        m.EventoSalida.objects.create(agregado_tipo=agregado_tipo, agregado_id=str(agregado_id)[:64], tipo_evento=tipo_evento, carga=carga)


class AuditoriaExpediente:
    """Anexa a la bitácora encadenada de MOD-019 (`m19_bitacora`, app `audit`) dentro de la transacción del caso de uso.
    El nombre se conserva por compatibilidad con el contenedor."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior=None, nuevo=None, **extra) -> None:
        from audit import servicios as auditoria   # frontera entre módulos: sólo en el adaptador
        auditoria.anexar(actor or "sistema", accion, tabla, str(objeto_id or ""), anterior, nuevo, **extra)

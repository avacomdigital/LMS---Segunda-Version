"""
Adaptadores de los puertos de MOD-010 sobre Django: los repositorios de `m10_*` (ORM), la cola de salida y la auditoría (bitácora encadenada de MOD-019).

Los casos de uso reciben y devuelven dicts planos; aquí se traducen a filas. Nada se borra (CV-05). `m10_incidente` es de SÓLO INSERCIÓN: este archivo no
tiene ninguna operación que lo actualice o lo borre (una prueba lo comprueba).
"""
from __future__ import annotations

from django.db import IntegrityError, transaction

from .. import models as m
from ..dominio import catalogos as cat

CAMPOS_ASIGNACION = (
    "id", "tipo", "sesion_id", "grupo_id", "grupo_rotulo", "alcance", "destinatarios", "profesor_id", "profesor_rotulo", "fuente_curso", "curso_ref",
    "curso_version", "curso_rotulo", "leccion_ref", "objeto_ref", "objeto_rotulo", "titulo", "estrategia", "preguntas_por_alumno", "total_banco",
    "ajustes", "nivel_declarado", "nivel_examen", "tiempo_modo", "tiempo_limite_seg", "intentos_permitidos", "abre_en", "limite_en", "plazo", "gracia_ms",
    "reactivacion", "recursos", "resultados", "liberados_en", "aprobacion_pct", "permite_retroceso", "mezclar_opciones", "estado", "creada_en",
    "publicada_en", "cerrada_en", "archivada_en", "creado_por",
)
CAMPOS_ADMISION = (
    "id", "asignacion_id", "alumno_id", "alumno_rotulo", "dispositivo_id", "dispositivo_rotulo", "nivel_exigido", "nivel_alcanzado", "estado",
    "nivel_admitido", "motivo", "solicitada_en", "decidido_por", "decidido_en",
)
CAMPOS_INTENTO = (
    "id", "asignacion_id", "alumno_id", "alumno_rotulo", "numero", "estado", "nivel_efectivo", "bloqueo", "dispositivo_id", "sesion_ref", "sesiones", "semilla",
    "curso_version", "armado", "armado_meta", "tiempo_limite_seg", "consumido_ms", "reloj_desde", "pausas", "ultimo_latido_en", "pregunta_actual",
    "respuestas", "secuencia_maxima", "puntaje", "puntaje_maximo", "porcentaje", "sin_calificar", "requiere_revision", "calificacion_pendiente",
    "calificado_por", "calificado_en", "fuera_de_plazo", "origen_entrega", "envio_tardio", "respuestas_pendientes", "decision_envio", "anulado_por",
    "motivo_anulacion", "anulado_en", "iniciado_en", "entregado_en", "creado_en",
)
CAMPOS_INCIDENTE = ("id", "intento_id", "tipo", "severidad", "origen", "ocurrido_en", "reportado_en_tableta", "dispositivo_id", "detalle", "resolucion",
                    "ref_cliente")


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

    def listar(self, *, estados: tuple[str, ...] | None = None, grupo_id: str | None = None, sesion_id: str | None = None,
               profesor_id: str | None = None) -> list[dict]:
        filas = m.Asignacion.objects.all()
        if estados:
            filas = filas.filter(estado__in=estados)
        if grupo_id:
            filas = filas.filter(grupo_id=grupo_id)
        if sesion_id:
            filas = filas.filter(sesion_id=sesion_id)
        if profesor_id:
            filas = filas.filter(profesor_id=profesor_id)
        return [_d(f, CAMPOS_ASIGNACION) for f in filas.order_by("-creada_en", "id")[:500]]

    def actualizar(self, asignacion_id: str, **campos) -> dict:
        m.Asignacion.objects.filter(pk=asignacion_id).update(**_filtrado(campos, CAMPOS_ASIGNACION))
        return self.por_id(asignacion_id)


class IntentosDjango:
    def crear(self, datos: dict) -> dict:
        return _d(m.Intento.objects.create(**_filtrado(datos, CAMPOS_INTENTO)), CAMPOS_INTENTO)

    def por_id(self, intento_id: str) -> dict | None:
        fila = m.Intento.objects.filter(pk=intento_id).first()
        return _d(fila, CAMPOS_INTENTO) if fila else None

    def actualizar(self, intento_id: str, **campos) -> dict:
        m.Intento.objects.filter(pk=intento_id).update(**_filtrado(campos, CAMPOS_INTENTO))
        return self.por_id(intento_id)

    def de_asignacion(self, asignacion_id: str, estados: tuple[str, ...] | None = None) -> list[dict]:
        filas = m.Intento.objects.filter(asignacion_id=asignacion_id)
        if estados:
            filas = filas.filter(estado__in=estados)
        return [_d(f, CAMPOS_INTENTO) for f in filas.order_by("alumno_id", "numero")]

    def del_alumno(self, asignacion_id: str, alumno_id: str) -> list[dict]:
        return [_d(f, CAMPOS_INTENTO) for f in m.Intento.objects.filter(asignacion_id=asignacion_id, alumno_id=alumno_id).order_by("numero")]

    def de_alumno_en(self, alumno_id: str, asignacion_ids: list[str]) -> list[dict]:
        return [_d(f, CAMPOS_INTENTO) for f in m.Intento.objects.filter(alumno_id=alumno_id, asignacion_id__in=asignacion_ids).order_by("numero")]

    def en_estados(self, *estados: str) -> list[dict]:
        return [_d(f, CAMPOS_INTENTO) for f in m.Intento.objects.filter(estado__in=estados).order_by("creado_en")]

    def vivos_de_personas(self, personas: list[str]) -> int:
        if not personas:
            return 0
        return m.Intento.objects.filter(alumno_id__in=personas, estado__in=cat.CORRIENDO + cat.SUSPENDIDOS).count()

    def corriendo_en_dispositivo(self, dispositivo_id: str) -> list[dict]:
        return [_d(f, CAMPOS_INTENTO) for f in m.Intento.objects.filter(dispositivo_id=dispositivo_id, estado__in=cat.ACEPTAN_RESPUESTAS)]


class AdmisionesDjango:
    def crear(self, datos: dict) -> dict:
        return _d(m.Admision.objects.create(**_filtrado(datos, CAMPOS_ADMISION)), CAMPOS_ADMISION)

    def por_id(self, admision_id: str) -> dict | None:
        fila = m.Admision.objects.filter(pk=admision_id).first()
        return _d(fila, CAMPOS_ADMISION) if fila else None

    def de_terna(self, asignacion_id: str, alumno_id: str, dispositivo_id: str) -> dict | None:
        fila = m.Admision.objects.filter(asignacion_id=asignacion_id, alumno_id=alumno_id, dispositivo_id=dispositivo_id).first()
        return _d(fila, CAMPOS_ADMISION) if fila else None

    def de_asignacion(self, asignacion_id: str, solo_en_espera: bool = True) -> list[dict]:
        filas = m.Admision.objects.filter(asignacion_id=asignacion_id)
        if solo_en_espera:
            filas = filas.filter(estado=cat.EN_ESPERA)
        return [_d(f, CAMPOS_ADMISION) for f in filas.order_by("solicitada_en", "id")]

    def del_alumno(self, asignacion_id: str, alumno_id: str) -> list[dict]:
        return [_d(f, CAMPOS_ADMISION) for f in m.Admision.objects.filter(asignacion_id=asignacion_id, alumno_id=alumno_id).order_by("solicitada_en")]

    def actualizar(self, admision_id: str, **campos) -> dict:
        m.Admision.objects.filter(pk=admision_id).update(**_filtrado(campos, CAMPOS_ADMISION))
        return self.por_id(admision_id)


class IncidentesDjango:
    """SÓLO INSERCIÓN (BR-077): ni `actualizar` ni `borrar`. Un incidente alimenta el expediente de integridad y nunca toca el estado del intento."""

    def crear(self, datos: dict) -> tuple[dict, bool]:
        ref = datos.get("ref_cliente") or ""
        if ref:
            existente = m.Incidente.objects.filter(intento_id=datos["intento_id"], ref_cliente=ref).first()
            if existente is not None:
                return _d(existente, CAMPOS_INCIDENTE), False
        try:
            with transaction.atomic():
                fila = m.Incidente.objects.create(**_filtrado(datos, CAMPOS_INCIDENTE))
        except IntegrityError:                       # dos envíos simultáneos con la misma clave: gana el primero
            existente = m.Incidente.objects.filter(intento_id=datos["intento_id"], ref_cliente=ref).first()
            if existente is None:
                raise
            return _d(existente, CAMPOS_INCIDENTE), False
        return _d(fila, CAMPOS_INCIDENTE), True

    def de_intento(self, intento_id: str) -> list[dict]:
        return [_d(f, CAMPOS_INCIDENTE) for f in m.Incidente.objects.filter(intento_id=intento_id).order_by("ocurrido_en", "id")]

    def de_intentos(self, intento_ids: list[str]) -> dict[str, list[dict]]:
        salida: dict[str, list[dict]] = {i: [] for i in intento_ids}
        if not intento_ids:
            return salida
        for f in m.Incidente.objects.filter(intento_id__in=intento_ids).order_by("ocurrido_en", "id"):
            salida[f.intento_id].append(_d(f, CAMPOS_INCIDENTE))
        return salida


class OutboxDjango:
    def publicar(self, agregado_tipo: str, agregado_id: str, tipo_evento: str, carga: dict) -> None:
        if tipo_evento not in cat.EVENTOS:
            raise ValueError(f"Evento fuera del catálogo de MOD-010: {tipo_evento}")
        m.EventoSalida.objects.create(agregado_tipo=agregado_tipo, agregado_id=str(agregado_id), tipo_evento=tipo_evento, carga=carga)


class AuditoriaEvaluacion:
    """Anexa a la bitácora encadenada de MOD-019 (`m19_bitacora`, app `audit`) dentro de la transacción del caso de uso."""

    def registrar(self, actor: str, accion: str, tabla: str = "", objeto_id: str = "", anterior=None, nuevo=None, **extra) -> None:
        from audit import servicios as auditoria   # frontera entre módulos: sólo en el adaptador
        auditoria.anexar(actor or cat.SISTEMA, accion, tabla, str(objeto_id or ""), anterior, nuevo, **extra)

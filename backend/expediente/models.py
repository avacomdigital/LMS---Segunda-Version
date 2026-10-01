"""
El expediente del estudiante: lo único que el LMS posee (artículo 13).

Toda columna terminada en `_ref` o `_codigo` es una referencia emitida por
AVACOM Biblioteca (curso_ref = clave del paquete, leccion_codigo = taxonomia_ref
de la sección, elemento_ref/pregunta_ref = referencias del manifiesto). Toda
columna terminada en `_rotulo` es evidencia histórica: se escribe una vez y no
se refresca; sirve para poder mostrar el historial con la biblioteca cerrada y
NUNCA participa en una decisión de disponibilidad.

No existe ninguna tabla de curso, sección, lección, ítem, pregunta ni opción
(artículo 14). Ninguna columna puede contener una clave de corrección.
"""
from __future__ import annotations

import time

from django.db import models
from django.db.models import Q


def ahora_ms() -> int:
    return int(time.time() * 1000)


class Inscripcion(models.Model):
    """Quién está en qué curso. Referencia estable de curso + identificador externo de persona."""

    curso_ref = models.CharField(max_length=200)
    persona_id = models.CharField(max_length=64)
    persona_rotulo = models.CharField(max_length=250, blank=True, default="")
    curso_rotulo = models.CharField(max_length=250, blank=True, default="")
    inscrito_en = models.BigIntegerField(default=ahora_ms)
    retirado_en = models.BigIntegerField(null=True, blank=True)
    creado_por = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "m05_inscripcion"
        constraints = [
            models.UniqueConstraint(fields=["curso_ref", "persona_id"], name="uq_m05_inscripcion"),
            models.CheckConstraint(
                condition=Q(retirado_en__isnull=True) | Q(retirado_en__gte=models.F("inscrito_en")),
                name="ck_m05_inscripcion_retiro_posterior",
            ),
        ]
        indexes = [models.Index(fields=["persona_id"]), models.Index(fields=["curso_ref"])]

    def __str__(self) -> str:
        return f"{self.persona_id} → {self.curso_ref}"


class ProgresoLeccion(models.Model):
    """Avance de una persona en una sección del curso (identidad lógica = código de taxonomía)."""

    NO_INICIADA, EN_CURSO, COMPLETADA = "no_iniciada", "en_curso", "completada"
    ESTADOS = [(NO_INICIADA, "No iniciada"), (EN_CURSO, "En curso"), (COMPLETADA, "Completada")]

    curso_ref = models.CharField(max_length=200)
    persona_id = models.CharField(max_length=64)
    leccion_codigo = models.CharField(max_length=120)
    leccion_rotulo = models.CharField(max_length=250, blank=True, default="")
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    estado = models.CharField(max_length=16, choices=ESTADOS, default=NO_INICIADA)
    version_observada = models.CharField(max_length=32, blank=True, default="")
    iniciado_en = models.BigIntegerField(null=True, blank=True)
    actualizado_en = models.BigIntegerField(default=ahora_ms)
    completado_en = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "m05_progreso_leccion"
        constraints = [
            models.UniqueConstraint(fields=["curso_ref", "persona_id", "leccion_codigo"], name="uq_m05_progreso"),
            models.CheckConstraint(condition=Q(porcentaje__gte=0) & Q(porcentaje__lte=100), name="ck_m05_progreso_rango"),
            models.CheckConstraint(
                condition=~Q(estado="completada") | (Q(porcentaje=100) & Q(completado_en__isnull=False)),
                name="ck_m05_progreso_completada_sella",
            ),
        ]


class AperturaMaterial(models.Model):
    """El «visor del contenido»: qué material abrió cada persona, cuándo y por cuánto tiempo.

    Es el registro de uso del que se deriva el progreso. Se guarda la referencia
    y la versión del elemento, nunca su contenido.
    """

    curso_ref = models.CharField(max_length=200)
    persona_id = models.CharField(max_length=64)
    leccion_codigo = models.CharField(max_length=120, blank=True, default="")
    elemento_ref = models.CharField(max_length=200)
    version_elemento = models.CharField(max_length=32, blank=True, default="")
    tipo = models.CharField(max_length=32, blank=True, default="")
    elemento_rotulo = models.CharField(max_length=250, blank=True, default="")
    dispositivo = models.CharField(max_length=64, blank=True, default="")
    origen = models.CharField(max_length=16, blank=True, default="student")
    abierto_en = models.BigIntegerField(default=ahora_ms)
    cerrado_en = models.BigIntegerField(null=True, blank=True)
    segundos = models.IntegerField(null=True, blank=True)
    progreso_pct = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "m05_apertura_material"
        indexes = [models.Index(fields=["curso_ref", "persona_id"]), models.Index(fields=["elemento_ref"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(progreso_pct__isnull=True) | (Q(progreso_pct__gte=0) & Q(progreso_pct__lte=100)),
                name="ck_m05_apertura_pct",
            ),
        ]


class Intento(models.Model):
    """Un intento de evaluación. Registro autoritativo de la nota."""

    ABIERTO, FINALIZADO, PENDIENTE = "abierto", "finalizado", "pendiente_correccion"
    ESTADOS = [(ABIERTO, "Abierto"), (FINALIZADO, "Finalizado"), (PENDIENTE, "Pendiente de corrección")]

    evaluacion_ref = models.CharField(max_length=200)
    curso_ref = models.CharField(max_length=200, blank=True, default="")
    leccion_codigo = models.CharField(max_length=120, blank=True, default="")
    version_observada = models.CharField(max_length=32, blank=True, default="")
    evaluacion_rotulo = models.CharField(max_length=250, blank=True, default="")
    persona_id = models.CharField(max_length=64)
    persona_rotulo = models.CharField(max_length=250, blank=True, default="")
    dispositivo = models.CharField(max_length=64, blank=True, default="")
    pregunta_actual = models.IntegerField(default=0)
    total_preguntas = models.IntegerField(default=0)
    estado = models.CharField(max_length=24, choices=ESTADOS, default=ABIERTO)
    puntaje = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    aciertos = models.IntegerField(default=0)
    pendientes = models.IntegerField(default=0)
    iniciado_en = models.BigIntegerField(default=ahora_ms)
    finalizado_en = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "m10_intento"
        constraints = [
            # Un solo intento abierto por (evaluación, persona, dispositivo).
            models.UniqueConstraint(
                fields=["evaluacion_ref", "persona_id", "dispositivo"],
                condition=Q(estado="abierto"),
                name="uq_m10_intento_abierto",
            ),
            models.CheckConstraint(
                condition=Q(estado="abierto") | Q(finalizado_en__isnull=False),
                name="ck_m10_intento_cierre_fechado",
            ),
            models.CheckConstraint(
                condition=Q(puntaje__isnull=True) | ~Q(estado="abierto"),
                name="ck_m10_intento_puntaje_solo_cerrado",
            ),
        ]
        indexes = [models.Index(fields=["curso_ref", "persona_id"])]


class IntentoPregunta(models.Model):
    """Qué se le preguntó a quién y en qué orden. No hay columna para la clave, y no es un olvido."""

    intento = models.ForeignKey(Intento, on_delete=models.CASCADE, related_name="preguntas")
    pregunta_ref = models.CharField(max_length=200)
    elemento_ref = models.CharField(max_length=200)
    version_elemento = models.CharField(max_length=32, blank=True, default="")
    orden = models.IntegerField()
    peso = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    corregible = models.BooleanField(default=True)

    class Meta:
        db_table = "m10_intento_pregunta"
        constraints = [
            models.UniqueConstraint(fields=["intento", "pregunta_ref"], name="uq_m10_ip_pregunta"),
            models.UniqueConstraint(fields=["intento", "orden"], name="uq_m10_ip_orden"),
        ]
        ordering = ["orden"]


class IntentoRespuesta(models.Model):
    """Lo que la persona contestó y el veredicto que devolvió la biblioteca. Nunca la clave."""

    intento = models.ForeignKey(Intento, on_delete=models.CASCADE, related_name="respuestas")
    pregunta_ref = models.CharField(max_length=200)
    respuesta = models.TextField(blank=True, default="")
    acierta = models.BooleanField(null=True, blank=True)
    corregido_en = models.BigIntegerField(null=True, blank=True)
    retroalimentacion_rotulo = models.TextField(null=True, blank=True)
    respondido_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m10_intento_respuesta"
        constraints = [models.UniqueConstraint(fields=["intento", "pregunta_ref"], name="uq_m10_ir_pregunta")]


class DisponibilidadObservada(models.Model):
    """La única concesión del artículo 14: memoria de la última revisión, para poder
    explicar una ausencia con la biblioteca cerrada. Guarda fechas, no contenido."""

    CURSO, ELEMENTO = "curso", "elemento"

    referencia = models.CharField(max_length=200)
    clase = models.CharField(max_length=16, default=CURSO)
    disponible_ultima_revision = models.BooleanField(default=True)
    revisado_en = models.BigIntegerField(default=ahora_ms)
    desaparecido_en = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "m05_disponibilidad_observada"
        constraints = [
            models.UniqueConstraint(fields=["referencia", "clase"], name="uq_m05_disponibilidad"),
            # No disponible obliga a fecha.
            models.CheckConstraint(
                condition=Q(disponible_ultima_revision=True) | Q(desaparecido_en__isnull=False),
                name="ck_m05_disp_ausencia_con_fecha",
            ),
        ]


class Auditoria(models.Model):
    """Vista de lectura sobre `m19_bitacora` (MOD-019). Desde 2026-09-30 la bitácora vive en la app `audit`
    (`m19_bitacora`, encadenada e inmutable); `m19_auditoria` es una VISTA con las columnas de siempre para que
    quien consultaba aquí siga leyendo lo mismo. Ningún módulo escribe por este modelo: escriben por su puerto de
    auditoría, que llega a `audit.servicios.anexar`."""

    actor_id = models.CharField(max_length=64, blank=True, default="")
    accion = models.CharField(max_length=64)
    objeto_tabla = models.CharField(max_length=64, blank=True, default="")
    objeto_id = models.CharField(max_length=64, blank=True, default="")
    valor_anterior = models.JSONField(null=True, blank=True)
    valor_nuevo = models.JSONField(null=True, blank=True)
    momento = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m19_auditoria"
        ordering = ["-momento", "-id"]
        managed = False

    def save(self, *args, **kwargs):
        raise ValueError("La auditoría se escribe por audit.servicios.anexar; m19_auditoria es una vista de lectura.")

    def delete(self, *args, **kwargs):
        raise ValueError("La auditoría es de sólo escritura: no se borra.")

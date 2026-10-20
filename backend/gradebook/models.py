"""
MOD-011 · Gradebook · tablas `m11_*`.

Lo que el módulo POSEE (escritor único, BR-003): la calificación normalizada de cada intento y su historial (sólo inserción), las revisiones docentes que
aplicó (puntuación manual y rúbrica), las escalas con sus versiones inmutables, la configuración de modo por nivel educativo, la política institucional, la
clasificación pedagógica de cada evaluación, lo DERIVADO (resultado por asignación y agregado por periodo) y la cola de salida con la marca de lectura de
su consumidor.

Lo que NO hay, y no es un olvido: ni intentos, ni respuestas, ni rúbricas, ni preguntas (de MOD-010 y de la biblioteca; el libro sólo guarda REFERENCIAS
`*_id`), ni grupos, ni periodos, ni personas (MOD-001/002), ni archivos de dibujo o proyecto (MOD-014).

Convenciones del proyecto: prefijo por módulo (CV-01), identificadores de texto (CV-02), tiempo en milisegundos del reloj del NODO (CV-03, BR-062), nada se
borra (CV-05: las FK son PROTECT), estados acotados por restricciones (CV-06) e invariantes como restricciones (CV-07). Las referencias a otros módulos son
lógicas, como en el aula y en la evaluación.

Qué se copia de otros módulos y por qué (lo demás se lee en el momento): `grupo_id`, `nivel_clave`, `periodo`, `curso_ref` y `numero_intento` quedan en la
calificación porque describen el CONTEXTO EN QUE SE CALIFICÓ (un alumno cambia de grupo, un grupo cambia de periodo, y una nota ya expedida debe seguir
significando lo que significó) y porque el libro de un grupo se consulta sin cruzar cuatro módulos.
"""
from __future__ import annotations

import time

from django.db import models
from django.db.models import F, Q

from .dominio import catalogos as cat


def ahora_ms() -> int:
    return int(time.time() * 1000)


def _lista(valores) -> list[tuple[str, str]]:
    return [(v, v) for v in valores]


# ======================================================================================================== escalas

class Escala(models.Model):
    """La escala de una institución: su identidad estable. Lo que define cómo se convierte vive en sus VERSIONES, que no se editan (una nota expedida se
    interpreta con la versión que estaba vigente)."""

    id = models.CharField(max_length=36, primary_key=True)
    codigo = models.CharField(max_length=48, unique=True)
    nombre = models.CharField(max_length=120)
    tipo = models.CharField(max_length=16, choices=_lista(cat.TIPOS_DE_ESCALA))
    pais = models.CharField(max_length=2, blank=True, default="")             # ISO 3166-1; vacío = genérica
    jurisdiccion = models.CharField(max_length=120, blank=True, default="")
    plantilla_origen = models.CharField(max_length=48, blank=True, default="")  # el código de la plantilla que se adoptó; vacío = propia
    activa = models.BooleanField(default=True)
    creada_en = models.BigIntegerField(default=ahora_ms)
    creada_por = models.CharField(max_length=64)

    class Meta:
        db_table = "m11_escala"
        constraints = [models.CheckConstraint(condition=Q(tipo__in=cat.TIPOS_DE_ESCALA), name="ck_m11_escala_tipo")]


class EscalaVersion(models.Model):
    """Una versión de una escala. INMUTABLE: el repositorio sólo inserta. `huella` (SHA-256 de la definición canónica) prueba que no cambió."""

    id = models.CharField(max_length=36, primary_key=True)
    escala = models.ForeignKey(Escala, on_delete=models.PROTECT, related_name="versiones")
    numero = models.PositiveSmallIntegerField()
    conversion = models.CharField(max_length=12, choices=_lista(cat.CONVERSIONES))
    valor_min = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)       # sólo numéricas
    valor_max = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    puntos = models.JSONField(default=list)               # [[interno, valor], …] sólo `interpolada`; los números viajan como texto
    decimales = models.PositiveSmallIntegerField(default=2)
    redondeo = models.CharField(max_length=12, choices=_lista(cat.REDONDEOS), default=cat.MITAD_ARRIBA)
    aprobacion_minima = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    nota = models.CharField(max_length=300, blank=True, default="")          # la política institucional en palabras (de dónde sale esta escala)
    huella = models.CharField(max_length=64)
    vigente_desde = models.BigIntegerField(default=ahora_ms)
    creada_por = models.CharField(max_length=64)

    class Meta:
        db_table = "m11_escala_version"
        constraints = [
            models.UniqueConstraint(fields=["escala", "numero"], name="ux_m11_escala_version_numero"),
            models.CheckConstraint(condition=Q(conversion__in=cat.CONVERSIONES), name="ck_m11_escala_version_conversion"),
            models.CheckConstraint(condition=Q(redondeo__in=cat.REDONDEOS), name="ck_m11_escala_version_redondeo"),
            models.CheckConstraint(condition=Q(decimales__lte=cat.MAX_DECIMALES), name="ck_m11_escala_version_decimales"),
            models.CheckConstraint(condition=Q(valor_min__isnull=True) | Q(valor_max__isnull=True) | Q(valor_min__lt=F("valor_max")), name="ck_m11_escala_version_rango"),
        ]


class EscalaTramo(models.Model):
    """Un intervalo `[desde, hasta)` de la escala interna (el último incluye el 100) de una versión. Con la versión, INMUTABLE."""

    version = models.ForeignKey(EscalaVersion, on_delete=models.PROTECT, related_name="tramos")
    orden = models.PositiveSmallIntegerField()
    clave = models.CharField(max_length=24)
    etiqueta = models.CharField(max_length=80)
    desde = models.DecimalField(max_digits=5, decimal_places=2)
    hasta = models.DecimalField(max_digits=5, decimal_places=2)
    nivel_desempeno = models.CharField(max_length=120, blank=True, default="")
    aprueba = models.BooleanField(null=True, blank=True)
    descripcion = models.CharField(max_length=240, blank=True, default="")

    class Meta:
        db_table = "m11_escala_tramo"
        constraints = [
            models.UniqueConstraint(fields=["version", "orden"], name="ux_m11_escala_tramo_orden"),
            models.UniqueConstraint(fields=["version", "clave"], name="ux_m11_escala_tramo_clave"),
            models.CheckConstraint(condition=Q(desde__gte=0) & Q(hasta__lte=100) & Q(desde__lt=F("hasta")), name="ck_m11_escala_tramo_rango"),
        ]


# ====================================================================================== configuración institucional

class ConfigNivel(models.Model):
    """El modo de un nivel educativo (FUN-125). SIN fila, el nivel está en modo `simple`: el modo simple es el valor por defecto. En modo `calificaciones` la
    escala es obligatoria y es una VERSIÓN concreta (así lo que se presenta hoy no cambia si mañana se publica otra versión)."""

    nivel_clave = models.CharField(max_length=24, primary_key=True)
    modo = models.CharField(max_length=16, choices=_lista(cat.MODOS), default=cat.SIMPLE)
    escala_version = models.ForeignKey(EscalaVersion, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    version = models.PositiveIntegerField(default=1)
    actualizada_en = models.BigIntegerField(default=ahora_ms)
    actualizada_por = models.CharField(max_length=64, blank=True, default="")
    modo_desde = models.BigIntegerField(default=ahora_ms)       # desde cuándo rige el MODO (instante del nodo): cambia sólo al alternar el modo, no al cambiar la escala

    class Meta:
        db_table = "m11_config_nivel"
        constraints = [
            models.CheckConstraint(condition=Q(modo__in=cat.MODOS), name="ck_m11_config_nivel_modo"),
            models.CheckConstraint(condition=~Q(modo=cat.CALIFICACIONES) | Q(escala_version__isnull=False), name="ck_m11_config_nivel_escala"),
            models.CheckConstraint(condition=Q(nivel_clave__in=cat.NIVELES), name="ck_m11_config_nivel_clave"),
        ]


class Politica(models.Model):
    """La política de evaluación de la institución: una sola fila (`institucional`). País y jurisdicción orientan las plantillas; `politica_intentos` decide qué
    intento cuenta; `ponderaciones` queda preparada para V1 (por tipo de actividad, periodo y grupo) y NO se aplica en el MVP."""

    id = models.CharField(max_length=24, primary_key=True, default="institucional")
    pais = models.CharField(max_length=2, blank=True, default="")
    jurisdiccion = models.CharField(max_length=120, blank=True, default="")
    institucion = models.CharField(max_length=200, blank=True, default="")
    politica_intentos = models.CharField(max_length=12, choices=_lista(cat.POLITICAS_DE_INTENTOS), default=cat.POLITICA_PROVISIONAL)
    ponderaciones = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)
    actualizada_en = models.BigIntegerField(default=ahora_ms)
    actualizada_por = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "m11_politica"
        constraints = [models.CheckConstraint(condition=Q(politica_intentos__in=cat.POLITICAS_DE_INTENTOS), name="ck_m11_politica_intentos")]


class Clasificacion(models.Model):
    """Cómo cuenta una evaluación de MOD-010 en el libro: diagnóstica, formativa o sumativa, y si afecta la calificación oficial. MOD-010 no lo sabe (y no se
    le añade): sin fila, un examen es sumativo y oficial y una actividad es formativa. `objetivos` son referencias (de la biblioteca o de MOD-012) a objetivos
    de aprendizaje o competencias; aquí no se definen."""

    asignacion_id = models.CharField(max_length=36, primary_key=True)
    tipo_evaluacion = models.CharField(max_length=12, choices=_lista(cat.TIPOS_DE_EVALUACION))
    afecta_oficial = models.BooleanField(default=True)
    objetivos = models.JSONField(default=list)
    actualizada_en = models.BigIntegerField(default=ahora_ms)
    actualizada_por = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "m11_clasificacion"
        constraints = [models.CheckConstraint(condition=Q(tipo_evaluacion__in=cat.TIPOS_DE_EVALUACION), name="ck_m11_clasificacion_tipo")]


# =================================================================================================== la calificación

class Calificacion(models.Model):
    """ENT-013. UNA por intento de MOD-010 y sólo cuando el intento está calificado del todo: nunca por un intento en curso ni con revisiones pendientes, y nunca
    por completar una actividad en un nivel de modo simple. `puntaje_original` es lo que se registró y NO cambia jamás; `puntaje_efectivo` es el vigente tras
    revisiones y ajustes. Cada cambio es una fila de `VersionCalificacion`. `version` es el control de concurrencia optimista: una escritura que no trae la
    versión que leyó se rechaza. La presentación (valor, letra, concepto) NO se guarda hasta que se publica: entonces queda la instantánea con la VERSIÓN
    de escala usada, para que una escala nueva no altere lo ya publicado."""

    id = models.CharField(max_length=36, primary_key=True)
    intento_id = models.CharField(max_length=36, unique=True)                  # m10_intento_formal (lógica)
    asignacion_id = models.CharField(max_length=36)                            # m10_asignacion (lógica)
    alumno_id = models.CharField(max_length=64)
    grupo_id = models.CharField(max_length=36, blank=True, default="")         # contexto en que se calificó (ver la nota del módulo)
    nivel_clave = models.CharField(max_length=24, blank=True, default="")
    periodo = models.CharField(max_length=16, blank=True, default="")
    curso_ref = models.CharField(max_length=200, blank=True, default="")
    numero_intento = models.PositiveSmallIntegerField(default=1)
    puntaje_original = models.DecimalField(max_digits=5, decimal_places=2)
    puntaje_efectivo = models.DecimalField(max_digits=5, decimal_places=2)
    puntaje_fuente = models.DecimalField(max_digits=5, decimal_places=2)       # lo que MOD-010 dijo la última vez que se registró o recalculó: si cambia, hay un desfase
    aciertos = models.PositiveSmallIntegerField(null=True, blank=True)         # para el modo simple y la retroalimentación: cuántas respondió bien…
    preguntas = models.PositiveSmallIntegerField(null=True, blank=True)        # …de cuántas
    puntos = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)          # los puntos BRUTOS que MOD-010 contó al calificar (14 de 18)…
    puntos_maximos = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # …sobre cuántos; la nota se lee con los tres: puntos, porcentaje y sistema
    regla_puntuacion = models.CharField(max_length=48)
    origen = models.CharField(max_length=12, choices=_lista(cat.ORIGENES))
    evaluador_id = models.CharField(max_length=64)                             # `sistema` o la persona que calificó
    estado = models.CharField(max_length=12, choices=_lista(cat.ESTADOS_CALIFICACION), default=cat.REVISADA)
    version = models.PositiveIntegerField(default=1)
    escala_version = models.ForeignKey(EscalaVersion, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    presentacion = models.JSONField(default=dict)                              # instantánea al publicar
    desempeno_docente = models.CharField(max_length=24, blank=True, default="")     # la valoración del profesor (clave de tramo) cuando difiere del cálculo
    desempeno_motivo = models.CharField(max_length=cat.MAX_MOTIVO, blank=True, default="")
    retroalimentacion = models.JSONField(default=dict)                         # {fortalezas, dificultades, oportunidades, comentario}
    adaptacion = models.CharField(max_length=300, blank=True, default="")      # ajuste razonable de evaluación aplicado (inclusión), si lo hubo
    publicada_en = models.BigIntegerField(null=True, blank=True)
    publicada_por = models.CharField(max_length=64, blank=True, default="")
    registrada_en = models.BigIntegerField(default=ahora_ms)
    actualizada_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m11_calificacion"
        constraints = [
            models.CheckConstraint(condition=Q(estado__in=cat.ESTADOS_CALIFICACION), name="ck_m11_calificacion_estado"),
            models.CheckConstraint(condition=Q(origen__in=cat.ORIGENES), name="ck_m11_calificacion_origen"),
            # Escala interna universal: 0–100 en las dos columnas (los dos decimales los fija el tipo de columna).
            models.CheckConstraint(condition=Q(puntaje_original__gte=0) & Q(puntaje_original__lte=100), name="ck_m11_calificacion_original_rango"),
            models.CheckConstraint(condition=Q(puntaje_efectivo__gte=0) & Q(puntaje_efectivo__lte=100), name="ck_m11_calificacion_efectivo_rango"),
            models.CheckConstraint(condition=Q(puntaje_fuente__gte=0) & Q(puntaje_fuente__lte=100), name="ck_m11_calificacion_fuente_rango"),
            # Los puntos brutos van juntos: o se conocen los dos (y los obtenidos no superan el máximo) o ninguno.
            models.CheckConstraint(condition=(Q(puntos__isnull=True) & Q(puntos_maximos__isnull=True))
                                   | (Q(puntos__isnull=False) & Q(puntos_maximos__isnull=False) & Q(puntos__gte=0) & Q(puntos__lte=F("puntos_maximos"))),
                                   name="ck_m11_calificacion_puntos"),
            # INV-019: toda calificación apunta a un intento, un evaluador y una regla.
            models.CheckConstraint(condition=~Q(evaluador_id="") & ~Q(regla_puntuacion=""), name="ck_m11_calificacion_evaluador_regla"),
            # Publicada ⇔ definitiva: lo que el alumno ve tiene quién lo publicó y cuándo; lo reabierto o anulado no está publicado.
            models.CheckConstraint(
                condition=(Q(estado=cat.DEFINITIVA) & Q(publicada_en__isnull=False) & ~Q(publicada_por=""))
                | (~Q(estado=cat.DEFINITIVA) & Q(publicada_en__isnull=True)),
                name="ck_m11_calificacion_publicada_definitiva"),
            models.CheckConstraint(condition=Q(version__gte=1), name="ck_m11_calificacion_version"),
        ]
        indexes = [models.Index(fields=["asignacion_id", "alumno_id"], name="ix_m11_calif_asignacion"),
                   models.Index(fields=["grupo_id", "periodo"], name="ix_m11_calif_grupo"),
                   models.Index(fields=["alumno_id", "estado"], name="ix_m11_calif_alumno")]


class VersionCalificacion(models.Model):
    """Cada cambio de una calificación: quién, cuándo (reloj del nodo), de qué a qué y por qué. SÓLO INSERCIÓN: ni el repositorio ni ningún caso de uso
    actualiza o borra una fila (una prueba lo comprueba). `solicitud_id` es la clave de idempotencia del cliente: reenviar la misma solicitud no duplica
    el ajuste."""

    id = models.BigAutoField(primary_key=True)
    calificacion = models.ForeignKey(Calificacion, on_delete=models.PROTECT, related_name="versiones")
    numero = models.PositiveIntegerField()
    tipo = models.CharField(max_length=20, choices=_lista(cat.TIPOS_DE_VERSION))
    puntaje_anterior = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    puntaje_nuevo = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    estado_anterior = models.CharField(max_length=12, blank=True, default="")
    estado_nuevo = models.CharField(max_length=12, blank=True, default="")
    motivo = models.CharField(max_length=cat.MAX_MOTIVO, blank=True, default="")
    actor_id = models.CharField(max_length=64)
    en = models.BigIntegerField(default=ahora_ms)
    solicitud_id = models.CharField(max_length=64, blank=True, default="")
    datos = models.JSONField(default=dict)

    class Meta:
        db_table = "m11_calificacion_version"
        constraints = [
            models.UniqueConstraint(fields=["calificacion", "numero"], name="ux_m11_version_numero"),
            models.UniqueConstraint(fields=["calificacion", "solicitud_id"], condition=~Q(solicitud_id=""), name="ux_m11_version_solicitud"),
            models.CheckConstraint(condition=Q(tipo__in=cat.TIPOS_DE_VERSION), name="ck_m11_version_tipo"),
            # Un ajuste o una valoración sin motivo no existe (BR-070).
            models.CheckConstraint(condition=~Q(tipo__in=(cat.V_AJUSTE, cat.V_VALORACION, cat.V_REAPERTURA, cat.V_RETIRO)) | ~Q(motivo=""),
                                   name="ck_m11_version_motivo"),
        ]
        indexes = [models.Index(fields=["calificacion", "numero"], name="ix_m11_version_calificacion")]


class Revision(models.Model):
    """Cada puntuación que el profesor aplicó a un reactivo de revisión docente por la vía del libro: manual (FUN-120) o por rúbrica (FUN-121). El puntaje lo
    guarda MOD-010 (dueño de la respuesta); aquí queda la TRAZA de cómo se llegó a él (el desglose por criterio) y la clave de idempotencia. SÓLO INSERCIÓN."""

    id = models.BigAutoField(primary_key=True)
    intento_id = models.CharField(max_length=36)
    pregunta_ref = models.CharField(max_length=120)
    numero = models.PositiveSmallIntegerField(default=1)                       # la n-ésima vez que se puntúa esa pregunta
    tipo = models.CharField(max_length=8, choices=_lista(cat.TIPOS_DE_REVISION))
    forma = models.CharField(max_length=12, choices=_lista(cat.FORMAS_DE_REVISION), default="abierta")
    puntaje = models.DecimalField(max_digits=7, decimal_places=2)               # en puntos de la pregunta
    puntaje_maximo = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    criterios = models.JSONField(default=list)                                  # [{criterio_id, criterio, puntos_max, puntos}] sólo con rúbrica
    comentario = models.CharField(max_length=cat.MAX_COMENTARIO, blank=True, default="")
    evidencias = models.JSONField(default=list)                                 # referencias a MOD-014 vistas en la respuesta (dibujo, audio): sólo referencias
    revisor_id = models.CharField(max_length=64)
    revisada_en = models.BigIntegerField(default=ahora_ms)
    solicitud_id = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "m11_revision"
        constraints = [
            models.UniqueConstraint(fields=["intento_id", "pregunta_ref", "numero"], name="ux_m11_revision_numero"),
            models.UniqueConstraint(fields=["intento_id", "solicitud_id"], condition=~Q(solicitud_id=""), name="ux_m11_revision_solicitud"),
            models.CheckConstraint(condition=Q(tipo__in=cat.TIPOS_DE_REVISION), name="ck_m11_revision_tipo"),
            models.CheckConstraint(condition=Q(puntaje__gte=0), name="ck_m11_revision_puntaje"),
        ]
        indexes = [models.Index(fields=["intento_id", "pregunta_ref"], name="ix_m11_revision_intento")]


# ========================================================================================= observaciones del docente

class Observacion(models.Model):
    """Lo que el profesor recomienda a UN alumno en UN grupo y UN periodo, en general (`curso_ref` vacío) o sobre un curso: la cuarta pregunta del boletín («¿qué debe
    mejorar?»). `recomendaciones` son claves del catálogo cerrado (`catalogos.RECOMENDACIONES`, que se toca sin teclado) y `texto` es un extra opcional. Cada cambio
    sube `version`, deja su asiento en la bitácora (quién, cuándo, de qué a qué) y publica su evento; repetir lo mismo no deja nada."""

    id = models.CharField(max_length=36, primary_key=True)
    alumno_id = models.CharField(max_length=64)
    grupo_id = models.CharField(max_length=36)
    periodo = models.CharField(max_length=16, blank=True, default="")
    curso_ref = models.CharField(max_length=200, blank=True, default="")
    recomendaciones = models.JSONField(default=list)
    texto = models.CharField(max_length=cat.MAX_OBSERVACION, blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    actualizada_en = models.BigIntegerField(default=ahora_ms)
    actualizada_por = models.CharField(max_length=64)

    class Meta:
        db_table = "m11_observacion"
        constraints = [
            models.UniqueConstraint(fields=["alumno_id", "grupo_id", "periodo", "curso_ref"], name="ux_m11_observacion"),
            models.CheckConstraint(condition=~Q(actualizada_por=""), name="ck_m11_observacion_actor"),
            models.CheckConstraint(condition=Q(version__gte=1), name="ck_m11_observacion_version"),
        ]
        indexes = [models.Index(fields=["grupo_id", "periodo"], name="ix_m11_observacion_grupo")]


# ===================================================================================================== lo derivado

class ResultadoAsignacion(models.Model):
    """DERIVADO (FUN-126, FUN-127, FUN-129): el resultado de UN alumno en UNA asignación — su estado simple, el estado de su calificación y la que cuenta según la
    política de intentos. Se deduce de MOD-010 (intentos) y de `m11_calificacion`; si se pierde o se restaura un respaldo, se reconstruye y queda igual."""

    asignacion_id = models.CharField(max_length=36)
    alumno_id = models.CharField(max_length=64)
    grupo_id = models.CharField(max_length=36, blank=True, default="")
    periodo = models.CharField(max_length=16, blank=True, default="")
    curso_ref = models.CharField(max_length=200, blank=True, default="")
    estado_simple = models.CharField(max_length=12, choices=_lista(cat.ESTADOS_SIMPLES))
    estado_calificacion = models.CharField(max_length=12, choices=_lista(cat.ESTADOS_DE_RESULTADO))
    calificacion_aplicable_id = models.CharField(max_length=36, blank=True, default="")
    puntaje_aplicable = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    politica_intentos = models.CharField(max_length=12, default=cat.POLITICA_PROVISIONAL)
    intentos_total = models.PositiveSmallIntegerField(default=0)
    intentos_registrados = models.PositiveSmallIntegerField(default=0)
    cuenta = models.BooleanField(default=True)                                  # la evaluación afecta la calificación oficial
    publicada = models.BooleanField(default=False)
    actualizado_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m11_resultado"
        constraints = [
            models.UniqueConstraint(fields=["asignacion_id", "alumno_id"], name="ux_m11_resultado"),
            models.CheckConstraint(condition=Q(estado_simple__in=cat.ESTADOS_SIMPLES), name="ck_m11_resultado_simple"),
            models.CheckConstraint(condition=Q(estado_calificacion__in=cat.ESTADOS_DE_RESULTADO), name="ck_m11_resultado_estado"),
            models.CheckConstraint(condition=Q(puntaje_aplicable__isnull=True) | (Q(puntaje_aplicable__gte=0) & Q(puntaje_aplicable__lte=100)),
                                   name="ck_m11_resultado_rango"),
        ]
        indexes = [models.Index(fields=["grupo_id", "periodo"], name="ix_m11_resultado_grupo"),
                   models.Index(fields=["alumno_id"], name="ix_m11_resultado_alumno")]


class AgregadoPeriodo(models.Model):
    """DERIVADO (FUN-127): lo que lleva un alumno en un curso durante un periodo. `promedio_simple` promedia sólo lo registrado y NO es oficial: no hay
    ponderación hasta que la institución la declare (V1)."""

    alumno_id = models.CharField(max_length=64)
    grupo_id = models.CharField(max_length=36)
    periodo = models.CharField(max_length=16, blank=True, default="")
    curso_ref = models.CharField(max_length=200, blank=True, default="")
    calificaciones = models.PositiveSmallIntegerField(default=0)
    promedio_simple = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pendientes = models.PositiveSmallIntegerField(default=0)
    provisionales = models.PositiveSmallIntegerField(default=0)
    publicadas = models.PositiveSmallIntegerField(default=0)
    actualizado_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m11_agregado_periodo"
        constraints = [
            models.UniqueConstraint(fields=["alumno_id", "grupo_id", "periodo", "curso_ref"], name="ux_m11_agregado"),
            models.CheckConstraint(condition=Q(promedio_simple__isnull=True) | (Q(promedio_simple__gte=0) & Q(promedio_simple__lte=100)),
                                   name="ck_m11_agregado_rango"),
        ]
        indexes = [models.Index(fields=["grupo_id", "periodo"], name="ix_m11_agregado_grupo")]


# =================================================================================== consumo y cola de salida

class MarcaConsumidor(models.Model):
    """La marca de lectura de un consumidor de eventos: hasta qué secuencia de la fuente ya procesó. Se avanza en la MISMA transacción que lo que procesó,
    así un fallo no la adelanta y reprocesar (por ejemplo, tras restaurar un respaldo) es seguro: lo que se aplica es idempotente."""

    consumidor = models.CharField(max_length=48, primary_key=True)
    fuente = models.CharField(max_length=32)
    ultima_secuencia = models.BigIntegerField(default=0)
    actualizada_en = models.BigIntegerField(default=ahora_ms)
    secuencia_fallida = models.BigIntegerField(default=0)           # el evento que no se pudo aplicar y retiene la marca (0 = ninguno)
    fallos_seguidos = models.PositiveSmallIntegerField(default=0)   # cuántos ciclos seguidos falló ese mismo evento

    class Meta:
        db_table = "m11_marca_consumidor"


class EventoSalida(models.Model):
    """Transactional Outbox de MOD-011 (`calificacion.*.v1`), con la misma forma que el de cada módulo del nodo. Se escribe en la misma transacción que el
    hecho. Nunca lleva comentarios ni el contenido de una respuesta. Cuando exista MOD-015 (`m15_evento`) las colas de todos los módulos se unifican allí:
    no se crea aquí ningún mecanismo de entrega."""

    agregado_tipo = models.CharField(max_length=32)
    agregado_id = models.CharField(max_length=64)
    tipo_evento = models.CharField(max_length=64)
    carga = models.JSONField(default=dict)
    creado_en = models.BigIntegerField(default=ahora_ms)
    publicado_en = models.BigIntegerField(null=True, blank=True)
    intentos = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "m11_evento_salida"
        indexes = [models.Index(fields=["publicado_en", "creado_en"], name="ix_m11_outbox")]

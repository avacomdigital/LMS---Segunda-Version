"""
MOD-007 · Classroom Engine · tablas `m07_*`.

Lo que el aula POSEE: la sesión de clase, sus participantes y su presencia técnica,
el selector (lo que el profesor tiene seleccionado para proyectar), los controles sobre
las pantallas, las distribuciones (lanzamientos) con su avance de entrega, los avisos y
el resumen de cierre. Ningún otro módulo escribe aquí (escritor único, sección K del Maestro).

Lo que NO hay, y no es un olvido (regla de oro, artículo 14): ninguna tabla de
curso, asignatura, lección, objeto, lámina, bloque, medio, pregunta ni opción. El
curso vive en AVACOM Biblioteca y aquí sólo se guardan sus referencias (`*_ref`,
CV-08) y, como evidencia histórica que no se refresca, su rótulo (`*_rotulo`).

Convenciones del documento de Arquitectura que se aplican: prefijo por módulo
(CV-01), identificadores de texto (CV-02), tiempo en milisegundos (CV-03), nada se
borra (CV-05), estados acotados por el motor (CV-06) e invariantes como índices
parciales (CV-07). Las referencias a MOD-001/MOD-002 (`grupo_id`, `profesor_id`,
`persona_id`) son lógicas, como en el expediente, y las valida el puerto `Identidad`.
Desde el 2026-09-28 MOD-009 tiene dueño (`device_manager`): `dispositivo_id` y
`dim_sesion_alumno_id` del participante son referencias lógicas a m09_* que resuelve el
puerto `Dispositivos` (una tableta bloqueada no entra ni recibe lanzamientos); pasarán a
FK físicas cuando los módulos compartan un motor definitivo.
"""
from __future__ import annotations

import time

from django.db import models
from django.db.models import F, Q

from .dominio import sesion as dom


def ahora_ms() -> int:
    return int(time.time() * 1000)


class SesionDeClase(models.Model):
    """ENT-015. Cerrada nunca se reabre; reanudar conserva el código de unión."""

    id = models.CharField(max_length=36, primary_key=True)
    # --- quién y para quién (referencias lógicas a MOD-001 / MOD-002) ---
    grupo_id = models.CharField(max_length=36, blank=True, default="")      # m01_grupo; vacío = sin padrón (Q-34)
    grupo_rotulo = models.CharField(max_length=120, blank=True, default="")
    profesor_id = models.CharField(max_length=64)                            # m01_usuario.id o identificador del aula
    profesor_rotulo = models.CharField(max_length=120, blank=True, default="")
    relevo_de_sesion_id = models.CharField(max_length=36, blank=True, default="")  # DEC-035
    # --- por dónde empezó (BR-044) y qué se referencia (CV-08) ---
    via_origen = models.CharField(max_length=16, choices=[(v, v) for v in dom.VIAS_ORIGEN])
    plan_id = models.CharField(max_length=36, blank=True, default="")        # MOD-006, por el puerto PlanDeClase
    nodo_ref = models.CharField(max_length=120, blank=True, default="")      # MOD-003, árbol académico
    fuente_curso = models.CharField(max_length=16, blank=True, default="")   # biblioteca | ejemplo
    curso_ref = models.CharField(max_length=200, blank=True, default="")
    curso_version = models.CharField(max_length=32, blank=True, default="")
    curso_rotulo = models.CharField(max_length=250, blank=True, default="")
    leccion_ref = models.CharField(max_length=120, blank=True, default="")
    leccion_rotulo = models.CharField(max_length=250, blank=True, default="")
    objeto_ref = models.CharField(max_length=120, blank=True, default="")
    objeto_rotulo = models.CharField(max_length=250, blank=True, default="")
    # --- ciclo de vida ---
    codigo_union = models.CharField(max_length=8)
    estado = models.CharField(max_length=16, choices=[(e, e) for e in dom.ESTADOS_SESION], default=dom.ABIERTA)
    superficie = models.CharField(max_length=64, blank=True, default="")     # navegador | pantalla | dispositivo
    iniciada_en = models.BigIntegerField(null=True, blank=True)
    suspendida_en = models.BigIntegerField(null=True, blank=True)
    causa_suspension = models.CharField(max_length=24, blank=True, default="")
    finalizada_en = models.BigIntegerField(null=True, blank=True)
    origen_cierre = models.CharField(max_length=16, blank=True, default="")
    archivada_en = models.BigIntegerField(null=True, blank=True)
    creado_en = models.BigIntegerField(default=ahora_ms)
    creado_por = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "m07_sesion"
        constraints = [
            # ux_m07_codigo: un código de unión identifica a lo sumo una sesión activa.
            models.UniqueConstraint(fields=["codigo_union"], condition=Q(estado__in=dom.ACTIVAS), name="ux_m07_codigo"),
            # ux_m07_grupo_activa (DEC-035): un grupo tiene a lo sumo una sesión abierta o suspendida.
            models.UniqueConstraint(fields=["grupo_id"], condition=Q(estado__in=dom.ACTIVAS) & ~Q(grupo_id=""),
                                    name="ux_m07_grupo_activa"),
            # BR-045: un profesor mantiene como máximo una sesión ABIERTA; las suspendidas no cuentan.
            models.UniqueConstraint(fields=["profesor_id"], condition=Q(estado=dom.ABIERTA), name="ux_m07_profesor_abierta"),
            models.CheckConstraint(condition=~Q(estado__in=(dom.CERRADA, dom.ARCHIVADA)) | Q(finalizada_en__isnull=False),
                                   name="ck_m07_sesion_cierre_fechado"),
            models.CheckConstraint(condition=~Q(estado=dom.ARCHIVADA) | Q(archivada_en__isnull=False),
                                   name="ck_m07_sesion_archivo_fechado"),
            models.CheckConstraint(condition=~Q(via_origen="leccion") | (~Q(curso_ref="") & ~Q(leccion_ref="")),
                                   name="ck_m07_sesion_via_leccion"),
            models.CheckConstraint(condition=~Q(via_origen="recurso") | (~Q(curso_ref="") & ~Q(objeto_ref="")),
                                   name="ck_m07_sesion_via_recurso"),
            models.CheckConstraint(condition=~Q(via_origen="arbol") | ~Q(nodo_ref=""), name="ck_m07_sesion_via_arbol"),
        ]
        indexes = [models.Index(fields=["profesor_id", "iniciada_en"], name="ix_m07_sesion_prof"),
                   models.Index(fields=["estado", "finalizada_en"], name="ix_m07_sesion_estado")]

    def __str__(self) -> str:
        return f"{self.id} · {self.estado} · {self.codigo_union}"


class Participante(models.Model):
    """Presencia técnica, que no es asistencia académica. Su `id` es el identificador de
    participación que la tableta vuelve a presentar al reconectar (FUN-077)."""

    id = models.CharField(max_length=36, primary_key=True)
    sesion = models.ForeignKey(SesionDeClase, on_delete=models.CASCADE, related_name="participantes")
    persona_id = models.CharField(max_length=64)
    persona_rotulo = models.CharField(max_length=120, blank=True, default="")
    dispositivo = models.CharField(max_length=64, blank=True, default="")           # huella que declara la tableta; contexto, nunca identidad
    dispositivo_id = models.CharField(max_length=36, blank=True, default="")        # m09_dispositivo (MOD-009), lógica
    dim_sesion_alumno_id = models.CharField(max_length=36, blank=True, default="")  # m09_dim_sesion_alumno (MOD-009), lógica
    sesion_usuario_id = models.CharField(max_length=36, blank=True, default="")     # m01_sesion (MOD-001), lógica
    estado = models.CharField(max_length=16, choices=[(e, e) for e in dom.ESTADOS_PARTICIPANTE], default=dom.CONECTADO)
    admision_nominal = models.BooleanField(default=False)   # BR-047: invitado admitido por el profesor
    ingreso = models.BigIntegerField(default=ahora_ms)
    salida = models.BigIntegerField(null=True, blank=True)
    ultimo_latido_en = models.BigIntegerField(null=True, blank=True)
    admitido_por = models.CharField(max_length=64, blank=True, default="")
    motivo = models.CharField(max_length=200, blank=True, default="")
    creado_en = models.BigIntegerField(default=ahora_ms)
    creado_por = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "m07_participante"
        constraints = [
            # ux_m07_part: una persona participa una sola vez por sesión; readmitir no duplica.
            models.UniqueConstraint(fields=["sesion", "persona_id"], name="ux_m07_part"),
            models.CheckConstraint(condition=~Q(estado__in=dom.CON_SALIDA) | Q(salida__isnull=False),
                                   name="ck_m07_part_salida_fechada"),
        ]
        indexes = [models.Index(fields=["sesion", "estado"], name="ix_m07_part_estado")]


class Presencia(models.Model):
    """Bitácora de presencia técnica (FUN-073): cada cambio de estado, con el reloj del nodo. Append-only."""

    participante = models.ForeignKey(Participante, on_delete=models.CASCADE, related_name="presencias")
    estado = models.CharField(max_length=16, choices=[(e, e) for e in dom.ESTADOS_PARTICIPANTE])
    dispositivo = models.CharField(max_length=64, blank=True, default="")
    detalle = models.CharField(max_length=200, blank=True, default="")
    momento = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m07_presencia"
        indexes = [models.Index(fields=["participante", "momento"], name="ix_m07_presencia")]


class Selector(models.Model):
    """Lo que el profesor tiene seleccionado para proyectar (FUN-069, BR-049): una lámina, una página,
    un objeto o un medio suelto. Bitácora con un solo selector vigente por sesión. No es un
    lanzamiento: cambia varias veces por minuto, no espera confirmación ni genera intentos."""

    id = models.CharField(max_length=36, primary_key=True)
    sesion = models.ForeignKey(SesionDeClase, on_delete=models.CASCADE, related_name="selectores")
    curso_ref = models.CharField(max_length=200, blank=True, default="")
    curso_version = models.CharField(max_length=32, blank=True, default="")
    leccion_ref = models.CharField(max_length=120, blank=True, default="")
    objeto_ref = models.CharField(max_length=120, blank=True, default="")
    objeto_tipo = models.CharField(max_length=24, blank=True, default="")      # lecture, explanation, simulation_lab, activity
    unidad_ref = models.CharField(max_length=120, blank=True, default="")      # lámina, página o pregunta
    unidad_indice = models.IntegerField(null=True, blank=True)
    media_ref = models.CharField(max_length=120, blank=True, default="")       # un medio proyectado suelto
    rotulo = models.CharField(max_length=250, blank=True, default="")
    vigente = models.BooleanField(default=True)
    declarado_en = models.BigIntegerField(default=ahora_ms)
    declarado_por = models.CharField(max_length=64, blank=True, default="")
    sustituido_en = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "m07_selector"
        constraints = [
            models.UniqueConstraint(fields=["sesion"], condition=Q(vigente=True), name="ux_m07_selector_vigente"),
            models.CheckConstraint(condition=Q(vigente=True) | Q(sustituido_en__isnull=False), name="ck_m07_selector_sustitucion"),
            models.CheckConstraint(condition=~Q(curso_ref="") | ~Q(media_ref=""), name="ck_m07_selector_referencia"),
        ]
        indexes = [models.Index(fields=["sesion", "declarado_en"], name="ix_m07_selector")]


class Control(models.Model):
    """Un periodo en que un control está activo sobre el grupo: `seguimiento` (BR-050) o
    `bloqueo` de pantallas (FUN-074). Abierto = `hasta` nulo; a lo sumo uno abierto por tipo."""

    id = models.CharField(max_length=36, primary_key=True)
    sesion = models.ForeignKey(SesionDeClase, on_delete=models.CASCADE, related_name="controles")
    tipo = models.CharField(max_length=16, choices=[(t, t) for t in dom.TIPOS_CONTROL])
    desde = models.BigIntegerField(default=ahora_ms)
    hasta = models.BigIntegerField(null=True, blank=True)
    motivo = models.CharField(max_length=200, blank=True, default="")
    creado_por = models.CharField(max_length=64, blank=True, default="")
    cerrado_por = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "m07_control"
        constraints = [
            models.UniqueConstraint(fields=["sesion", "tipo"], condition=Q(hasta__isnull=True), name="ux_m07_control_abierto"),
            models.CheckConstraint(condition=Q(hasta__isnull=True) | Q(hasta__gte=F("desde")), name="ck_m07_control_vigencia"),
        ]


class Distribucion(models.Model):
    """El lanzamiento: envío de un recurso o de una actividad a todos o a algunos, con avance de entrega
    (CAP-040, FUN-070, FUN-071). Es la tabla `lanzamiento` de la segunda versión del modelo de datos:
    `alcance` y `destinatarios` dicen a quién; `intentos_permitidos` y `tiempo_limite_seg` son las reglas
    con las que se lanzó; una tableta bloqueada (MOD-009) queda fuera y consta en `excluidos_bloqueados`."""

    id = models.CharField(max_length=36, primary_key=True)
    sesion = models.ForeignKey(SesionDeClase, on_delete=models.CASCADE, related_name="distribuciones")
    clase = models.CharField(max_length=16, choices=[(c, c) for c in dom.CLASES_DISTRIBUCION])
    curso_ref = models.CharField(max_length=200, blank=True, default="")
    leccion_ref = models.CharField(max_length=120, blank=True, default="")
    objeto_ref = models.CharField(max_length=120, blank=True, default="")
    objeto_tipo = models.CharField(max_length=24, blank=True, default="")
    media_ref = models.CharField(max_length=120, blank=True, default="")
    rotulo = models.CharField(max_length=250, blank=True, default="")
    alcance = models.CharField(max_length=16, choices=[(a, a) for a in dom.ALCANCES], default=dom.GRUPO)
    destinatarios = models.JSONField(default=list)             # persona_id de quienes lo recibieron al lanzar
    excluidos_bloqueados = models.JSONField(default=list)      # persona_id dejados fuera por tableta bloqueada o retirada
    intentos_permitidos = models.PositiveSmallIntegerField(null=True, blank=True)   # NULL: manda el objeto
    tiempo_limite_seg = models.PositiveIntegerField(null=True, blank=True)
    disponible_estudio = models.BooleanField(default=False)   # MOD-008 decide si lo descarga
    asignacion_ref = models.CharField(max_length=64, blank=True, default="")   # MOD-010, devuelto por el puerto Evaluacion
    abierta_en = models.BigIntegerField(default=ahora_ms)
    cerrada_en = models.BigIntegerField(null=True, blank=True)
    creado_por = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "m07_distribucion"
        constraints = [
            models.CheckConstraint(condition=~Q(objeto_ref="") | ~Q(media_ref=""), name="ck_m07_dist_referencia"),
            models.CheckConstraint(condition=Q(cerrada_en__isnull=True) | Q(cerrada_en__gte=F("abierta_en")),
                                   name="ck_m07_dist_cierre_posterior"),
            models.CheckConstraint(condition=Q(intentos_permitidos__isnull=True) | Q(intentos_permitidos__gte=1),
                                   name="ck_m07_dist_intentos"),
            models.CheckConstraint(condition=Q(tiempo_limite_seg__isnull=True) | Q(tiempo_limite_seg__gte=1),
                                   name="ck_m07_dist_tiempo"),
        ]
        indexes = [models.Index(fields=["sesion", "cerrada_en"], name="ix_m07_dist_abiertas")]


class DistribucionEntrega(models.Model):
    """Avance de entrega por participante: la «confirmación» de CAP-040."""

    distribucion = models.ForeignKey(Distribucion, on_delete=models.CASCADE, related_name="entregas")
    participante = models.ForeignKey(Participante, on_delete=models.CASCADE, related_name="entregas")
    estado = models.CharField(max_length=16, choices=[(e, e) for e in dom.ESTADOS_ENTREGA], default=dom.PENDIENTE)
    confirmada_en = models.BigIntegerField(null=True, blank=True)
    intentos = models.IntegerField(default=0)

    class Meta:
        db_table = "m07_distribucion_entrega"
        constraints = [
            models.UniqueConstraint(fields=["distribucion", "participante"], name="ux_m07_entrega"),
            models.CheckConstraint(condition=~Q(estado=dom.ENTREGADO) | Q(confirmada_en__isnull=False),
                                   name="ck_m07_entrega_confirmada"),
        ]


class Aviso(models.Model):
    """Mensaje de aviso del profesor a un dispositivo o al grupo (FUN-075)."""

    id = models.CharField(max_length=36, primary_key=True)
    sesion = models.ForeignKey(SesionDeClase, on_delete=models.CASCADE, related_name="avisos")
    participante = models.ForeignKey(Participante, on_delete=models.CASCADE, null=True, blank=True, related_name="avisos")
    texto = models.CharField(max_length=300)
    enviado_en = models.BigIntegerField(default=ahora_ms)
    creado_por = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "m07_aviso"
        indexes = [models.Index(fields=["sesion", "enviado_en"], name="ix_m07_aviso")]


class Resumen(models.Model):
    """Consolidado al cerrar (FUN-079, CAP-045). Es lo que se conserva cinco años."""

    sesion = models.OneToOneField(SesionDeClase, on_delete=models.CASCADE, primary_key=True, related_name="resumen")
    participantes = models.IntegerField(default=0)
    conectados_maximo = models.IntegerField(default=0)
    admitidos_nominal = models.IntegerField(default=0)
    selectores = models.IntegerField(default=0)
    distribuciones = models.IntegerField(default=0)
    actividades = models.IntegerField(default=0)
    avisos = models.IntegerField(default=0)
    pendientes = models.IntegerField(default=0)       # intentos abiertos al cierre (MOD-010, por el puerto)
    duracion_ms = models.BigIntegerField(default=0)
    origen_cierre = models.CharField(max_length=16, choices=[(o, o) for o in dom.ORIGENES_CIERRE], default="profesor")
    consolidado_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m07_resumen"


class EventoSalida(models.Model):
    """Transactional Outbox de MOD-007 (`aula.*.v1`). Se escribe en la misma transacción que
    el hecho. Cuando exista MOD-015 (m15_evento) ambas colas se unifican allí."""

    agregado_tipo = models.CharField(max_length=32)
    agregado_id = models.CharField(max_length=36)
    tipo_evento = models.CharField(max_length=64)
    carga = models.JSONField(default=dict)
    creado_en = models.BigIntegerField(default=ahora_ms)
    publicado_en = models.BigIntegerField(null=True, blank=True)
    intentos = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "m07_evento_salida"
        indexes = [models.Index(fields=["publicado_en", "creado_en"], name="ix_m07_outbox")]

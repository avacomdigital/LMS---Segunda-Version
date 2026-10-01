"""
MOD-009 · Device Manager · tablas `m09_*`.

Lo que el módulo POSEE: el inventario de equipos del aula (`m09_dispositivo`) y la sesión
de alumno en cada equipo (`m09_dim_sesion_alumno`: alumno + dispositivo + periodo, la
«Dim Sesión Alumno» de la segunda versión del modelo de datos). El Documento Maestro pone la
sesión de usuario en el dispositivo bajo este módulo (ENT-018, AGG-005: el dispositivo es la
raíz del agregado). Ningún otro módulo escribe aquí: `acceso` consulta dispositivos en el
login por su puerto y `classroom_engine` por el suyo (BR-003, un solo escritor).

Hasta el 2026-09-28 `Dispositivo` vivía en `acceso` (`m01_dispositivo`); la migración 0001 la
trae aquí con sus datos y la renombra `m09_dispositivo`. La organización sigue viniendo de
`acceso` (referencia lógica por FK: el nodo tiene una sola).

Convenciones: prefijo por módulo (CV-01), identificadores de texto (CV-02), tiempo en
milisegundos del reloj del nodo (CV-03), nada se borra (CV-05), invariantes como índices
parciales (CV-07).
"""
from __future__ import annotations

import time

from django.db import models
from django.db.models import F, Q

from .dominio import dispositivo as dom


def ahora_ms() -> int:
    return int(time.time() * 1000)


class Dispositivo(models.Model):
    """ENT-017. Contexto técnico, nunca identidad. `bloqueado` deja a la tableta fuera de las
    sesiones y de los lanzamientos sin darla de baja; `activo=False` la retira conservando su historial."""

    id = models.CharField(max_length=36, primary_key=True)
    organizacion = models.ForeignKey("acceso.Organizacion", on_delete=models.CASCADE, related_name="dispositivos")
    identificador_hw = models.CharField(max_length=128)          # huella de la instalación; con ella se reconoce la tableta
    nombre = models.CharField(max_length=120)
    tipo = models.CharField(max_length=16, default=dom.TABLETA)   # TABLETA · MASTER · OTRO
    plataforma = models.CharField(max_length=16, blank=True, default="")   # windows · android · '' si no lo ha dicho
    version_app = models.CharField(max_length=32, blank=True, default="")
    activo = models.BooleanField(default=True)
    bloqueado = models.BooleanField(default=False)
    registrado_en = models.BigIntegerField(default=ahora_ms)
    ultimo_latido_en = models.BigIntegerField(default=ahora_ms)
    # Última lectura que la tableta declaró con su latido (009-04). El historial va por el evento de inventario.
    espacio_libre_mb = models.IntegerField(null=True, blank=True)
    bateria_pct = models.SmallIntegerField(null=True, blank=True)
    # 009-06 · 008-01: el equipo es del aula (`compartido`) o nominal de una persona (`asignado`). El modo de estudio sirve en cualquier equipo
    # (D-15), pero sólo el dueño de un equipo asignado se lleva la descarga de paquetes (BR-054). `asignado_a_id` es la referencia lógica a
    # `m01_usuario.id` (CV-08).
    perfil = models.CharField(max_length=12, default=dom.COMPARTIDO)
    asignado_a_id = models.CharField(max_length=64, null=True, blank=True)
    asignado_en = models.BigIntegerField(null=True, blank=True)
    # MOD-010 · BR-075: lo que la tableta DECLARA poder garantizar en un examen (`abierto` · `supervisado` · `controlado`; vacío = nunca lo declaró) y el
    # detalle que informa (`bloqueo_sistema`, `motivo`…). El nodo no lo infiere de la plataforma: la app mide e informa.
    capacidad_control = models.CharField(max_length=12, blank=True, default="")
    capacidad_detalle = models.JSONField(default=dict, blank=True)
    capacidad_declarada_en = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "m09_dispositivo"
        constraints = [
            models.UniqueConstraint(fields=["organizacion", "identificador_hw"], name="uq_m09_dispositivo_identificador"),
            # CV-07: ser «asignado» y tener dueño es lo mismo. Un equipo asignado sin dueño (o compartido con dueño) no existe.
            models.CheckConstraint(
                condition=(Q(perfil=dom.ASIGNADO) & Q(asignado_a_id__isnull=False))
                | (~Q(perfil=dom.ASIGNADO) & Q(asignado_a_id__isnull=True)),
                name="ck_m09_dispositivo_perfil_dueno"),
            models.CheckConstraint(condition=Q(perfil__in=dom.PERFILES), name="ck_m09_dispositivo_perfil_valido"),
            models.CheckConstraint(condition=Q(capacidad_control__in=("",) + dom.NIVELES_CONTROL), name="ck_m09_dispositivo_capacidad_valida"),
        ]

    def __str__(self) -> str:
        return f"{self.nombre} · {self.identificador_hw}"


class DimSesionAlumno(models.Model):
    """Desde qué tableta y durante qué periodo está conectado un alumno. De ella cuelga su
    participación en clase (`m07_participante.dim_sesion_alumno_id`).

    INV-011: una tableta compartida tiene cero o una sesión activa (`ux_m09_dsa_dispositivo_abierta`).
    DEC-023: un alumno tiene una sola sesión abierta (`ux_m09_dsa_alumno_abierta`). Abrir otra cierra
    la anterior con motivo `relevo`: el dispositivo nunca bloquea al alumno."""

    id = models.CharField(max_length=36, primary_key=True)
    alumno_id = models.CharField(max_length=64)   # persona_id (referencia lógica a MOD-001, CV-08)
    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.PROTECT, related_name="sesiones_alumno")
    iniciada_en = models.BigIntegerField(default=ahora_ms)
    finalizada_en = models.BigIntegerField(null=True, blank=True)
    motivo_cierre = models.CharField(max_length=16, blank=True, default="")   # usuario · inactividad · sistema · relevo

    class Meta:
        db_table = "m09_dim_sesion_alumno"
        constraints = [
            models.UniqueConstraint(fields=["alumno_id"], condition=Q(finalizada_en__isnull=True), name="ux_m09_dsa_alumno_abierta"),
            models.UniqueConstraint(fields=["dispositivo"], condition=Q(finalizada_en__isnull=True), name="ux_m09_dsa_dispositivo_abierta"),
            models.CheckConstraint(condition=Q(finalizada_en__isnull=True) | Q(finalizada_en__gte=F("iniciada_en")), name="ck_m09_dsa_vigencia"),
            models.CheckConstraint(condition=Q(finalizada_en__isnull=True) | ~Q(motivo_cierre=""), name="ck_m09_dsa_cierre_motivado"),
        ]
        indexes = [
            models.Index(fields=["dispositivo", "finalizada_en"], name="ix_m09_dsa_dispositivo"),
            models.Index(fields=["alumno_id", "iniciada_en"], name="ix_m09_dsa_alumno"),
        ]


class EventoSalida(models.Model):
    """Transactional Outbox de MOD-009 (`dispositivo.*.v1`). Se escribe en la misma transacción que
    el hecho. Cuando exista MOD-015 (m15_evento) las colas de todos los módulos se unifican allí."""

    agregado_tipo = models.CharField(max_length=32)
    agregado_id = models.CharField(max_length=36)
    tipo_evento = models.CharField(max_length=64)
    carga = models.JSONField(default=dict)
    creado_en = models.BigIntegerField(default=ahora_ms)
    publicado_en = models.BigIntegerField(null=True, blank=True)
    intentos = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "m09_evento_salida"
        indexes = [models.Index(fields=["publicado_en", "creado_en"], name="ix_m09_outbox")]

"""
MOD-019 · Audit · tablas `m19_*`.

`m19_bitacora` sustituye a `m19_auditoria` (que queda como vista de lectura sobre esta tabla y como
`m19_auditoria_legado`, de sólo lectura, durante un ciclo de versión). `m19_bitacora_tramo` es nueva: segmentos
contiguos de la cadena; el tramo activo lleva la cabeza. `m19_evento_salida` es la cola de salida propia de los cinco
eventos `auditoria.*` hasta que exista MOD-015.

Inmutabilidad en tres capas (§3.3): (1) aquí el manager no expone update/delete/bulk_* y `save()` de una fila
existente o `delete()` lanzan `BitacoraInmutable` dejando un asiento nuevo `auditoria.alteracion_intentada`;
(2) triggers de SQLite (`infraestructura/triggers.py`, creados por migración) abortan UPDATE y DELETE también por SQL
directo; (3) la verificación comprueba que los triggers existan y recalcula la cadena.

Convenciones: prefijo por módulo (CV-01), identificadores de texto (CV-02), tiempo en milisegundos del reloj del
nodo (CV-03), nada se borra (CV-05), invariantes como índices parciales (CV-07), referencias lógicas (CV-08).
"""
from __future__ import annotations

import time
import uuid

from django.db import models
from django.db.models import Q

from .dominio import asiento as dom
from .dominio import errores
from .dominio import tramo as dom_tramo


def ahora_ms() -> int:
    return int(time.time() * 1000)


def _nuevo_id() -> str:
    return str(uuid.uuid4())


class BitacoraQuerySet(models.QuerySet):
    """Sólo inserción y lectura: cualquier intento de alterar por el ORM deja un asiento y se rechaza."""

    def update(self, **kwargs):
        raise _rechazar("update", self)

    def delete(self):
        raise _rechazar("delete", self)

    def bulk_update(self, objs, fields, batch_size=None):
        raise _rechazar("bulk_update", self)

    def bulk_create(self, objs, *args, **kwargs):
        raise _rechazar("bulk_create", self)

    def update_or_create(self, *args, **kwargs):
        raise _rechazar("update_or_create", self)

    # Django llama a esto al hacer `save()` de una fila existente; se tapa para que no haya atajo.
    def _update(self, values):
        raise _rechazar("update", self)


def _rechazar(operacion: str, qs) -> errores.BitacoraInmutable:
    objeto_id = None
    try:
        primero = qs.order_by("secuencia").values_list("id", flat=True).first()
        objeto_id = str(primero) if primero else None
    except Exception:   # noqa: BLE001 — si no se puede saber el objeto, el intento se asienta igual
        objeto_id = None
    try:
        from . import servicios
        servicios.alteracion_intentada(operacion, "m19_bitacora", objeto_id)
    except Exception:   # noqa: BLE001 — el rechazo no depende de poder asentar el intento
        pass
    return errores.BitacoraInmutable(f"La bitácora sólo se agrega: «{operacion}» no está permitido.", operacion=operacion)


class BitacoraManager(models.Manager.from_queryset(BitacoraQuerySet)):
    use_in_migrations = False


class BitacoraTramo(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=_nuevo_id)
    desde_secuencia = models.BigIntegerField()
    hasta_secuencia = models.BigIntegerField()          # cabeza mientras está activa; desde-1 si aún no tiene asientos
    huella_cierre = models.CharField(max_length=64)     # huella del último asiento; al rotar, huella_previa del siguiente tramo
    estado = models.CharField(max_length=12, default=dom_tramo.ESTADO_ACTIVA)
    abierta = models.BooleanField(default=True)         # el tramo que recibe asientos; False al rotar (índice único parcial)
    verificado_en = models.BigIntegerField(null=True, blank=True)
    verificado_hasta = models.BigIntegerField(null=True, blank=True)   # última secuencia verificada (verificación por bloques)
    salto_en_secuencia = models.BigIntegerField(null=True, blank=True)
    salto_causa = models.CharField(max_length=32, blank=True, default="")
    exportado_en = models.BigIntegerField(null=True, blank=True)
    firma = models.TextField(null=True, blank=True)
    archivo = models.CharField(max_length=260, null=True, blank=True)
    rotado_en = models.BigIntegerField(null=True, blank=True)
    creado_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m19_bitacora_tramo"
        ordering = ["desde_secuencia"]
        constraints = [
            # Un único tramo abierto (sin rotar) a la vez (INV-011/DEC-023: índice único parcial). El tramo abierto puede estar
            # `activa`, `verificada` o `con_salto`; al rotarlo pasa a `rotada` y nace el siguiente.
            models.UniqueConstraint(fields=["abierta"], condition=Q(abierta=True), name="uq_m19_tramo_abierto"),
            models.CheckConstraint(condition=Q(hasta_secuencia__gte=models.F("desde_secuencia") - 1), name="ck_m19_tramo_rango"),
            models.CheckConstraint(condition=Q(estado__in=dom_tramo.ESTADOS), name="ck_m19_tramo_estado"),
            models.CheckConstraint(condition=Q(desde_secuencia__gte=1), name="ck_m19_tramo_desde"),
        ]

    def __str__(self) -> str:
        return f"tramo {self.desde_secuencia}-{self.hasta_secuencia} ({self.estado})"


class Bitacora(models.Model):
    """`bitacora` del v2 (→ m19_bitacora). Sólo inserción. Las columnas canónicas participan en la huella."""

    id = models.CharField(max_length=36, primary_key=True, default=_nuevo_id)
    secuencia = models.BigIntegerField(unique=True)
    huella_previa = models.CharField(max_length=64)
    huella = models.CharField(max_length=64)
    ocurrido_en = models.BigIntegerField()                                  # reloj del NODO, nunca el de la tableta
    usuario_id = models.CharField(max_length=64, null=True, blank=True)     # referencia lógica a m01_usuario (CV-08); NULL = sistema
    actor_tipo = models.CharField(max_length=12, default=dom.ACTOR_SISTEMA)
    roles_activos = models.JSONField(null=True, blank=True)
    modulo = models.CharField(max_length=24)                                # sustituye a modulo_app_id hasta que exista modulo_app
    accion = models.CharField(max_length=64)
    resultado = models.CharField(max_length=16, default=dom.RESULTADO_OK)
    objeto_tabla = models.CharField(max_length=64, null=True, blank=True)
    objeto_id = models.CharField(max_length=64, null=True, blank=True)
    valor_anterior = models.JSONField(null=True, blank=True)                # sólo los campos que cambian
    valor_nuevo = models.JSONField(null=True, blank=True)
    motivo = models.CharField(max_length=250, null=True, blank=True)
    origen = models.CharField(max_length=12)
    dispositivo = models.ForeignKey("device_manager.Dispositivo", on_delete=models.RESTRICT, null=True, blank=True,
                                    db_column="dispositivo_id", related_name="asientos_bitacora")
    correlacion_id = models.CharField(max_length=64, null=True, blank=True)
    evento_id = models.CharField(max_length=64, null=True, blank=True)     # el evento de la cola del que derivó (019-09)
    tramo = models.ForeignKey(BitacoraTramo, on_delete=models.RESTRICT, db_column="tramo_id", related_name="asientos")

    objects = BitacoraManager()

    class Meta:
        db_table = "m19_bitacora"
        ordering = ["secuencia"]
        indexes = [
            models.Index(fields=["usuario_id", "ocurrido_en"], name="ix_m19_bit_usuario"),
            models.Index(fields=["modulo", "ocurrido_en"], name="ix_m19_bit_modulo"),
            models.Index(fields=["resultado", "ocurrido_en"], name="ix_m19_bit_resultado"),
            models.Index(fields=["objeto_tabla", "objeto_id", "ocurrido_en"], name="ix_m19_bit_objeto"),
            models.Index(fields=["accion", "ocurrido_en"], name="ix_m19_bit_accion"),
            models.Index(fields=["dispositivo", "ocurrido_en"], name="ix_m19_bit_dispositivo"),
            models.Index(fields=["correlacion_id"], name="ix_m19_bit_corr"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(resultado__in=dom.RESULTADOS), name="ck_m19_bit_resultado"),
            models.CheckConstraint(condition=Q(origen__in=dom.ORIGENES), name="ck_m19_bit_origen"),
            models.CheckConstraint(condition=Q(actor_tipo__in=dom.ACTORES), name="ck_m19_bit_actor_tipo"),
            models.CheckConstraint(condition=~Q(actor_tipo="usuario") | Q(usuario_id__isnull=False), name="ck_m19_bit_usuario_con_id"),
            models.CheckConstraint(condition=Q(secuencia__gte=1), name="ck_m19_bit_secuencia"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise _rechazar("save", Bitacora.objects.filter(pk=self.pk))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise _rechazar("delete", Bitacora.objects.filter(pk=self.pk))

    def canonico(self) -> dict:
        return {
            "secuencia": self.secuencia, "ocurrido_en": self.ocurrido_en, "usuario_id": self.usuario_id, "actor_tipo": self.actor_tipo,
            "roles_activos": self.roles_activos, "modulo": self.modulo, "accion": self.accion, "resultado": self.resultado,
            "objeto_tabla": self.objeto_tabla, "objeto_id": self.objeto_id, "valor_anterior": self.valor_anterior,
            "valor_nuevo": self.valor_nuevo, "motivo": self.motivo, "origen": self.origen, "dispositivo_id": self.dispositivo_id,
            "correlacion_id": self.correlacion_id, "evento_id": self.evento_id,
        }

    def __str__(self) -> str:
        return f"#{self.secuencia} {self.accion} ({self.resultado})"


class EventoSalida(models.Model):
    """Transactional Outbox de MOD-019 (`auditoria.*.v1`): se escribe en la misma transacción que el hecho.
    Cuando exista MOD-015 (m15_evento) todas las colas se unifican allí."""

    agregado_tipo = models.CharField(max_length=32)
    agregado_id = models.CharField(max_length=36)
    tipo_evento = models.CharField(max_length=64)
    carga = models.JSONField(default=dict)
    creado_en = models.BigIntegerField(default=ahora_ms)
    publicado_en = models.BigIntegerField(null=True, blank=True)
    intentos = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "m19_evento_salida"
        indexes = [models.Index(fields=["publicado_en", "creado_en"], name="ix_m19_outbox")]

"""
MOD-016 · Backup & Recovery · tablas `m16_*`.

Respaldo es dueño de estas cuatro tablas y NO lee ni escribe ninguna otra (INV-023, R-03): lo ajeno —si hay una clase abierta, el reloj, la bitácora, la cola única, los permisos, la
secuencia global— le llega por el `servicios.py` de cada dueño a través de sus puertos. Ninguna clave foránea sale del módulo.

  m16_respaldo     cada archivo `.avbak` que este nodo produjo o catalogó: su manifiesto SIN datos de personas, la huella del archivo y de dónde vino. Sólo inserción (trigger).
  m16_historial    el historial de SÓLO INSERCIÓN: iniciado, completo_ejecutado, verificado, exportado, restauracion_completada… El estado de un respaldo se DERIVA de sus filas
                   (`dominio/estados.py`): no hay un «estado actual» que pueda divergir.
  m16_ajuste       UNA fila: la programación vigente. Es lo único mutable (cada cambio queda además en el historial y en la bitácora). La identidad del nodo para los respaldos y el
                   código de custodia viven FUERA de la base, en la carpeta de respaldos: una restauración no los rebobina.
  m16_pase_usado   los pases de soporte de AVACOM que ya se usaron (un pase vale una vez). Sólo inserción (trigger).

Convenciones del Maestro: prefijo por módulo (CV-01), identificadores de texto (CV-02), tiempo en milisegundos del reloj del NODO (CV-03, BR-062).
"""
from __future__ import annotations

from django.db import models
from django.db.models import Q

from .dominio import catalogos as cat


def _lista(valores) -> list[tuple[str, str]]:
    return [(v, v) for v in valores]


class Respaldo(models.Model):
    respaldo_id = models.CharField(max_length=36, primary_key=True)
    tipo = models.CharField(max_length=12, choices=_lista(cat.TIPOS))
    base_id = models.CharField(max_length=36, blank=True, default="")          # el respaldo del que depende (sólo un incremental)
    disparo = models.CharField(max_length=24, choices=_lista(cat.DISPAROS))
    archivo = models.CharField(max_length=160)                                  # el nombre del archivo, sin carpeta
    sha256 = models.CharField(max_length=64)
    bytes = models.BigIntegerField()
    bytes_claro = models.BigIntegerField(default=0)
    creado_en = models.BigIntegerField()
    secuencia_global = models.BigIntegerField(default=0)                       # la última secuencia de la cola única al tomar el respaldo (qué se pierde al restaurar)
    version_producto = models.CharField(max_length=32, blank=True, default="")
    nodo_id = models.CharField(max_length=36)
    entradas = models.PositiveIntegerField(default=0)
    archivos = models.PositiveIntegerField(default=0)                          # archivos de la institución (sin contar la base)
    incluye_reinstalable = models.BooleanField(default=False)
    con_custodia = models.BooleanField(default=False)                          # ¿se abre también con el código de custodia? (BR-102)
    creado_por = models.CharField(max_length=cat.MAX_ACTOR, blank=True, default="")

    class Meta:
        db_table = "m16_respaldo"
        indexes = [models.Index(fields=["creado_en"], name="ix_m16_resp_creado")]
        constraints = [models.CheckConstraint(condition=Q(tipo__in=cat.TIPOS), name="ck_m16_resp_tipo"),
                       models.CheckConstraint(condition=Q(disparo__in=cat.DISPAROS), name="ck_m16_resp_disparo")]


class Historial(models.Model):
    respaldo_id = models.CharField(max_length=36, blank=True, default="", db_index=True)
    tipo = models.CharField(max_length=24, choices=_lista(cat.HISTORIAL))
    en = models.BigIntegerField()
    actor = models.CharField(max_length=cat.MAX_ACTOR, blank=True, default="")
    detalle = models.JSONField(default=dict)

    class Meta:
        db_table = "m16_historial"
        indexes = [models.Index(fields=["tipo", "en"], name="ix_m16_hist_tipo_en"), models.Index(fields=["en"], name="ix_m16_hist_en")]
        constraints = [models.CheckConstraint(condition=Q(tipo__in=cat.HISTORIAL), name="ck_m16_hist_tipo")]


class Ajuste(models.Model):
    """La programación vigente (FUN-169). Una fila. La identidad del nodo y el código de custodia NO viven aquí: viven en una carpeta fuera de la base (una restauración no los rebobina)."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    activo = models.BooleanField(default=True)
    hora_min = models.PositiveSmallIntegerField(default=cat.HORA_POR_DEFECTO_MIN)
    dias = models.JSONField(default=list)
    completo_cada_dias = models.PositiveSmallIntegerField(default=cat.COMPLETO_CADA_DIAS)
    retencion = models.PositiveSmallIntegerField(default=cat.RETENCION_POR_DEFECTO)
    incluir_reinstalable = models.BooleanField(default=False)
    destino = models.CharField(max_length=12, default="local")
    programado_en = models.BigIntegerField(null=True, blank=True)
    programado_por = models.CharField(max_length=cat.MAX_ACTOR, blank=True, default="")

    class Meta:
        db_table = "m16_ajuste"
        constraints = [models.CheckConstraint(condition=Q(id=1), name="ck_m16_ajuste_unico")]


class PaseUsado(models.Model):
    pase_id = models.CharField(max_length=64, primary_key=True)
    usado_en = models.BigIntegerField()
    permiso = models.CharField(max_length=32)
    tecnico = models.CharField(max_length=120, blank=True, default="")
    kid = models.CharField(max_length=32, blank=True, default="")
    respaldo_id = models.CharField(max_length=36, blank=True, default="")

    class Meta:
        db_table = "m16_pase_usado"


TABLAS_PROPIAS = ("m16_respaldo", "m16_historial", "m16_ajuste", "m16_pase_usado")
TABLAS_DERIVADAS: tuple[str, ...] = ()

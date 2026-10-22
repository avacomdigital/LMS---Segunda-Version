"""
MOD-017 · Update Manager · tablas `m17_*`.

Actualización es dueña de estas dos tablas y NO lee ni escribe ninguna otra (INV-023, R-03): lo ajeno —si hay una clase abierta, el reloj, la bitácora, la cola única, los
permisos— le llega por el `servicios.py` de cada dueño a través de sus puertos. Ninguna clave foránea sale del módulo.

  m17_paquete     cada paquete `.avupd` que pasó la firma y la forma, tal como se importó: su manifiesto (sin la lista de archivos), la llave que lo firmó, la huella SHA-256 del
                  archivo completo, su tamaño, de dónde vino y quién lo importó. Un paquete rechazado NO se guarda aquí (TST-048, TST-062). Sólo inserción (trigger).
  m17_historial   el historial de SÓLO INSERCIÓN (FUN-187, P-05): recibido, verificado, incompatible, programado, bloqueada, aplicando, aplicado, revertido… y `rechazado`, la única
                  fila sin paquete. El estado de un paquete se DERIVA de sus filas (`dominio/estados.py`): no hay un «estado actual» que pueda divergir. Cada fila lleva la marca
                  del reloj del NODO (R-09), quién actuó y un detalle con ids, versiones, serie, resultado y hashes —nunca rutas de personas ni contenido—.

Convenciones del Maestro: prefijo por módulo (CV-01), identificadores de texto (CV-02), tiempo en milisegundos del reloj del NODO (CV-03, BR-062).
"""
from __future__ import annotations

from django.db import models
from django.db.models import Q

from .dominio import catalogos as cat


def _lista(valores) -> list[tuple[str, str]]:
    return [(v, v) for v in valores]


class Paquete(models.Model):
    """Un `.avupd` importado y verificado. Sólo inserción (trigger)."""

    paquete_id = models.CharField(max_length=36, primary_key=True)
    nombre = models.CharField(max_length=cat.MAX_NOMBRE)
    version_producto = models.CharField(max_length=32)
    serie = models.PositiveIntegerField()
    modulos = models.JSONField(default=list)                   # los nombres de los módulos que trae
    manifiesto = models.JSONField(default=dict)                # `manifiesto.resumen`: sin la lista de archivos
    kid = models.CharField(max_length=cat.MAX_KID)
    sha256 = models.CharField(max_length=64)
    bytes = models.BigIntegerField()
    archivo = models.CharField(max_length=160, blank=True, default="")   # el nombre del archivo tal como venía (sin su carpeta)
    origen = models.CharField(max_length=16, choices=_lista(cat.ORIGENES))
    recibido_en = models.BigIntegerField()
    importado_por = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "m17_paquete"
        indexes = [models.Index(fields=["recibido_en"], name="ix_m17_paq_recibido")]
        constraints = [models.CheckConstraint(condition=Q(origen__in=cat.ORIGENES), name="ck_m17_paq_origen")]


class Historial(models.Model):
    """Una fila por hecho del historial. Sólo inserción (trigger). `paquete_id` vacío en un `rechazado` (no hay paquete)."""

    paquete_id = models.CharField(max_length=36, blank=True, default="", db_index=True)
    tipo = models.CharField(max_length=24, choices=_lista(cat.HISTORIAL))
    en = models.BigIntegerField()
    actor = models.CharField(max_length=64, blank=True, default="")
    serie = models.PositiveIntegerField(default=0)
    version_producto = models.CharField(max_length=32, blank=True, default="")
    detalle = models.JSONField(default=dict)

    class Meta:
        db_table = "m17_historial"
        indexes = [models.Index(fields=["tipo", "en"], name="ix_m17_hist_tipo_en"), models.Index(fields=["en"], name="ix_m17_hist_en")]
        constraints = [models.CheckConstraint(condition=Q(tipo__in=cat.HISTORIAL), name="ck_m17_hist_tipo")]


TABLAS_PROPIAS = ("m17_paquete", "m17_historial")
TABLAS_DERIVADAS: tuple[str, ...] = ()

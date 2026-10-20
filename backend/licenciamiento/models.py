"""
MOD-018 · Licensing · tablas `m18_*`.

Licenciamiento es dueño de estas seis tablas y NO lee ni escribe `m01_*` ni `m09_*` (INV-023, R-08): lo ajeno —cuántos equipos y cuántos usuarios hay— le llega como números por el
`servicios.py` de cada dueño. Ninguna clave foránea sale del módulo.

  m18_licencia        el HISTORIAL de licencias, de sólo inserción: cada activación, renovación, reactivación y liberación es una fila (con el `.avlic` tal cual). No se guarda un «estado
                      actual» que pueda divergir de la realidad: el estado se DERIVA de este historial, de las observaciones y del reloj confiable (P-05). Un trigger impide actualizar filas.
  m18_observacion     hechos observados que explican el estado (primera vez que la huella no coincidió, un reloj que retrocedió o saltó, una confirmación del administrador, un ancla
                      alterada…). De sólo inserción, con cifras y sin contenido.
  m18_marca_alta      el instante más alto que el nodo ha visto (P-06). Un trigger impide bajarla. Hay además anclas FUERA de la base (un archivo y una clave del registro) que una copia
                      de seguridad restaurada no rebobina.
  m18_instalacion     cuándo empezó la ventana de evaluación de este nodo (P-14). Una fila.
  m18_consumo         el último conteo de equipos y usuarios (FUN-190). Es DERIVADO: se puede borrar.
  m18_evento_salida   la cola de salida `licencia.*.v1` (Transactional Outbox, como `m09` y `m19`). Con `clave` única, escribir el mismo evento dos veces no hace nada.

Lo que NO hay, y no es un olvido: ni claves de datos, ni datos académicos, ni personas (R-03). La licencia no ata ningún dato del colegio.

Convenciones del Maestro: prefijo por módulo (CV-01), identificadores de texto (CV-02), tiempo en milisegundos del reloj del NODO (CV-03, BR-062).
"""
from __future__ import annotations

import time

from django.db import models
from django.db.models import Q

from .dominio import catalogos as cat


def ahora_ms() -> int:
    return int(time.time() * 1000)


def _lista(valores) -> list[tuple[str, str]]:
    return [(v, v) for v in valores]


class Instalacion(models.Model):
    """Cuándo empezó la ventana de evaluación de este nodo (primer arranque con licenciamiento)."""

    id = models.CharField(max_length=16, primary_key=True, default="nodo")
    instalada_en = models.BigIntegerField()
    version_primera = models.CharField(max_length=32, blank=True, default="")
    creada_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m18_instalacion"


class Licencia(models.Model):
    """Una fila por hecho del historial: activada, renovada, reactivada o liberada. Sólo inserción (trigger)."""

    licencia_id = models.CharField(max_length=36)
    serie = models.PositiveIntegerField()
    kid = models.CharField(max_length=64, blank=True, default="")
    tipo = models.CharField(max_length=12, choices=_lista(cat.HISTORIAL))
    archivo = models.BinaryField(null=True, blank=True)                       # el `.avlic` tal cual; nulo en una liberación
    sha256 = models.CharField(max_length=64, blank=True, default="")           # huella del archivo (de la prueba de liberación, si es una liberación)
    instalada_en = models.BigIntegerField()
    instalada_por = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "m18_licencia"
        indexes = [models.Index(fields=["licencia_id", "serie"], name="ix_m18_lic_id_serie")]
        constraints = [models.CheckConstraint(condition=Q(tipo__in=cat.HISTORIAL), name="ck_m18_lic_tipo")]


class Observacion(models.Model):
    """Un hecho observado (huella distinta, reloj, integridad…). Sólo inserción (trigger)."""

    tipo = models.CharField(max_length=32, choices=_lista(cat.OBSERVACIONES))
    licencia_id = models.CharField(max_length=36, blank=True, default="")
    serie = models.IntegerField(default=0)
    en = models.BigIntegerField()
    detalle = models.JSONField(default=dict)

    class Meta:
        db_table = "m18_observacion"
        indexes = [models.Index(fields=["tipo", "en"], name="ix_m18_obs_tipo_en")]
        constraints = [models.CheckConstraint(condition=Q(tipo__in=cat.OBSERVACIONES), name="ck_m18_obs_tipo")]


class MarcaAlta(models.Model):
    """El instante más alto visto (P-06). Sólo sube: un trigger de SQLite lo garantiza."""

    id = models.CharField(max_length=16, primary_key=True, default="nodo")
    valor = models.BigIntegerField(default=0)
    actualizada_en = models.BigIntegerField(default=0)

    class Meta:
        db_table = "m18_marca_alta"


class Consumo(models.Model):
    """El último conteo de equipos y usuarios (FUN-190). Derivado: se puede borrar y se vuelve a calcular."""

    id = models.CharField(max_length=16, primary_key=True, default="nodo")
    calculado_en = models.BigIntegerField(default=0)
    equipos = models.IntegerField(default=0)
    usuarios = models.IntegerField(default=0)

    class Meta:
        db_table = "m18_consumo"


class EventoSalida(models.Model):
    """Transactional Outbox de MOD-018 (`licencia.*.v1`). Con `clave` es idempotente: la misma clave no se escribe dos veces."""

    agregado_tipo = models.CharField(max_length=32)
    agregado_id = models.CharField(max_length=64)
    tipo_evento = models.CharField(max_length=64)
    carga = models.JSONField(default=dict)
    clave = models.CharField(max_length=190, unique=True, null=True, blank=True)
    creado_en = models.BigIntegerField(default=ahora_ms)
    publicado_en = models.BigIntegerField(null=True, blank=True)
    intentos = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "m18_evento_salida"
        indexes = [models.Index(fields=["publicado_en", "creado_en"], name="ix_m18_outbox")]


# Las tablas que se pueden borrar y volver a calcular, y las que guardan hechos que no se pueden perder.
TABLAS_DERIVADAS = ("m18_consumo",)
TABLAS_PROPIAS = ("m18_instalacion", "m18_licencia", "m18_observacion", "m18_marca_alta", "m18_evento_salida")

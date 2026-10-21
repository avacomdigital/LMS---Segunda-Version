"""
Tablas `m15_*` de MOD-015 · Node Platform y Cola de Salida. `nodo` es su ÚNICO escritor (INV-023, R-09): ningún módulo escribe aquí salvo por `nodo.servicios`, y ninguna clave foránea
sale del módulo.

  m15_evento           la cola única (P-02, P-03): el sobre de doce campos y la carga. `secuencia` es INTEGER PRIMARY KEY AUTOINCREMENT (estrictamente creciente, no se reutiliza);
                       INMUTABLE por trigger (ningún UPDATE); sin trigger de DELETE (el vaciado de las pruebas borra con DELETE; la purga es el único borrado de la aplicación).
  m15_corte            el corte de cada módulo a la cola única (P-05): módulo, último id de su tabla antigua, fecha. De una sola vía.
  m15_modulo           el registro de módulos con su versión de módulo, de datos y de contrato (BR-012, INV-007).
  m15_consumidor       el registro de consumidores (P-06): módulo, fuentes, tipos, versión de contrato declarada, límite de rezago, estado.
  m15_marca_lectura    la marca por (consumidor, fuente), que avanza en la MISMA transacción que el efecto (BR-005), con el evento que la retiene y su reintento (P-07).
  m15_problema         los eventos apartados tras agotar los reintentos (FUN-163) y su reproceso (FUN-164): metadatos, nunca la carga.
  m15_arranque         una fila por arranque; se cierra en la parada limpia (apagado sucio = la anterior sin cerrar) y guarda lo que decidieron las anclas (P-12).
  m15_marca_alta       la marca alta del reloj (P-13): sólo sube (trigger).

Lo que NO hay (artículo 14, BR-127): ninguna columna con contenido de curso ni con datos de personas: la carga es la que trae el productor, ya revisada (R-13), y el técnico nunca la lee.
"""
from __future__ import annotations

import time

from django.db import models

from .dominio import catalogos as cat


def ahora_ms() -> int:
    return int(time.time() * 1000)


def _lista(valores) -> list[tuple[str, str]]:
    return [(v, v) for v in valores]


class Evento(models.Model):
    """La cola única. `secuencia` = AUTOINCREMENT (P-02). El sobre no se reescribe jamás (trigger `m15_evento_inmutable`, migración 0002)."""

    secuencia = models.BigAutoField(primary_key=True)
    evento_id = models.CharField(max_length=64, unique=True)
    tipo = models.CharField(max_length=cat.MAX_TIPO)
    version = models.PositiveSmallIntegerField(default=1)
    modulo = models.CharField(max_length=cat.MAX_MODULO)
    creado_en = models.BigIntegerField()
    agregado_tipo = models.CharField(max_length=cat.MAX_AGREGADO_TIPO)
    agregado_id = models.CharField(max_length=cat.MAX_AGREGADO_ID)
    actor = models.CharField(max_length=cat.MAX_ACTOR)
    dispositivo_id = models.CharField(max_length=cat.MAX_DISPOSITIVO)
    correlacion_id = models.CharField(max_length=cat.MAX_CORRELACION)
    clase = models.CharField(max_length=16, choices=_lista(cat.CLASES))
    sensibilidad = models.CharField(max_length=16, choices=_lista(cat.SENSIBILIDADES))
    carga = models.JSONField(default=dict)
    catalogado = models.BooleanField(default=True)          # False: el tipo no estaba en el catálogo y se aceptó en producción (R-06)
    carga_omitida = models.BooleanField(default=False)      # True: la carga traía datos que no pueden viajar y se reemplazó (R-13)

    class Meta:
        db_table = "m15_evento"
        indexes = [models.Index(fields=["modulo", "secuencia"], name="ix_m15_evento_modulo"), models.Index(fields=["tipo", "secuencia"], name="ix_m15_evento_tipo")]


class Corte(models.Model):
    modulo = models.CharField(max_length=cat.MAX_MODULO, primary_key=True)
    ultima_legada = models.BigIntegerField(default=0)
    cortado_en = models.BigIntegerField()
    version_contrato = models.PositiveSmallIntegerField(default=1)

    class Meta:
        db_table = "m15_corte"


class Modulo(models.Model):
    nombre = models.CharField(max_length=cat.MAX_MODULO, primary_key=True)
    version_modulo = models.CharField(max_length=32, blank=True, default="")
    version_datos = models.CharField(max_length=32, blank=True, default="")
    version_contrato = models.PositiveSmallIntegerField(default=1)
    produce = models.JSONField(default=list)
    consume = models.JSONField(default=list)
    compatible = models.BooleanField(default=True)
    detalle = models.JSONField(default=dict)
    registrado_en = models.BigIntegerField()
    actualizado_en = models.BigIntegerField()

    class Meta:
        db_table = "m15_modulo"


class Consumidor(models.Model):
    nombre = models.CharField(max_length=64, primary_key=True)
    modulo = models.CharField(max_length=cat.MAX_MODULO)
    fuentes = models.JSONField(default=list)
    tipos = models.JSONField(default=list)
    version_contrato = models.PositiveSmallIntegerField(default=1)
    limite_rezago = models.BigIntegerField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=_lista(cat.ESTADOS_CONSUMIDOR), default=cat.C_AL_DIA)
    activo = models.BooleanField(default=True)              # False: desregistrado (BR-018); sus marcas se conservan
    registrado_en = models.BigIntegerField()
    actualizado_en = models.BigIntegerField()

    class Meta:
        db_table = "m15_consumidor"


class MarcaLectura(models.Model):
    consumidor = models.CharField(max_length=64)
    fuente = models.CharField(max_length=cat.MAX_MODULO)
    ultima_secuencia = models.BigIntegerField(default=0)
    actualizada_en = models.BigIntegerField()
    fallo_secuencia = models.BigIntegerField(default=0)     # el evento que retiene la marca (0 = ninguno)
    fallos = models.PositiveSmallIntegerField(default=0)
    proximo_intento_en = models.BigIntegerField(default=0)
    ultimo_error = models.CharField(max_length=cat.MAX_ERROR, blank=True, default="")
    reconstruyendose = models.BooleanField(default=False)

    class Meta:
        db_table = "m15_marca_lectura"
        constraints = [models.UniqueConstraint(fields=["consumidor", "fuente"], name="uq_m15_marca_consumidor_fuente")]


class Problema(models.Model):
    id = models.BigAutoField(primary_key=True)
    consumidor = models.CharField(max_length=64)
    fuente = models.CharField(max_length=cat.MAX_MODULO)
    secuencia = models.BigIntegerField()
    evento_id = models.CharField(max_length=64, blank=True, default="")
    tipo = models.CharField(max_length=cat.MAX_TIPO)
    intentos = models.PositiveSmallIntegerField(default=0)
    intentos_reproceso = models.PositiveSmallIntegerField(default=0)
    ultimo_error = models.CharField(max_length=cat.MAX_ERROR, blank=True, default="")
    estado = models.CharField(max_length=16, choices=_lista(cat.ESTADOS_PROBLEMA), default=cat.PR_APARTADO)
    apartado_en = models.BigIntegerField()
    resuelto_en = models.BigIntegerField(null=True, blank=True)
    resuelto_por = models.CharField(max_length=cat.MAX_ACTOR, blank=True, default="")

    class Meta:
        db_table = "m15_problema"
        indexes = [models.Index(fields=["consumidor", "estado", "apartado_en"], name="ix_m15_problema_consumidor")]


class Arranque(models.Model):
    id = models.BigAutoField(primary_key=True)
    iniciado_en = models.BigIntegerField()
    cerrado_en = models.BigIntegerField(null=True, blank=True)
    pid = models.IntegerField(default=0)
    version = models.CharField(max_length=32, blank=True, default="")
    secuencia_al_iniciar = models.BigIntegerField(default=0)
    ancla_secuencia = models.BigIntegerField(default=0)
    restauracion = models.BooleanField(default=False)
    contador = models.BigIntegerField(default=0)
    detalle = models.JSONField(default=dict)

    class Meta:
        db_table = "m15_arranque"


class MarcaAlta(models.Model):
    """Una sola fila (id=1). Sólo sube: trigger `m15_marca_alta_solo_sube` (migración 0002)."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    valor = models.BigIntegerField(default=0)
    actualizada_en = models.BigIntegerField(default=0)

    class Meta:
        db_table = "m15_marca_alta"


TABLAS = ("m15_arranque", "m15_consumidor", "m15_corte", "m15_evento", "m15_marca_alta", "m15_marca_lectura", "m15_modulo", "m15_problema")

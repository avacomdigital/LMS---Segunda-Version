"""
MOD-013 · Reporting · tablas `m13_*`.

Reporting NO es dueño de ningún dato académico (Maestro, K): arma vistas sobre lo que otros módulos ya calcularon. Sus tablas son de dos clases y conviene no confundirlas:

  DERIVADAS (se pueden borrar y reconstruir desde la cola de los módulos dueños; BR-007)
    m13_clase · m13_clase_alumno          el reporte de una clase terminada y la fila de cada alumno en ella
    m13_avance_grupo · m13_avance_alumno  el avance de un grupo y el de cada alumno (agregados que se actualizan fuera del horario de clase)
    m13_estado_dispositivo                lo que cada tableta avisó de su cola de estudio (integración, BR-083)
    m13_marca_consumidor · m13_estado_proyeccion   hasta dónde se leyó cada cola y el estado técnico de las proyecciones

  PROPIAS (decisiones y hechos de Reporting que NO salen de la cola: perderlas es perder información)
    m13_config          el umbral de privacidad y la política de exportación del nodo (una fila)
    m13_exportacion     cada exportación: autorizada, entregada o caducada, con sus intentos
    m13_reciente        los reportes que cada persona abrió hace poco (sólo los parámetros)
    m13_evento_salida   la cola de salida `reporte.*.v1`

Lo que NO hay, y no es un olvido (artículo 14): ninguna columna con el título de un curso, una lección, una evaluación o una pregunta, ni con una respuesta o su clave. Sólo
referencias (`curso_ref`, `leccion_ref`, `asignacion_id`) y cifras; los rótulos se piden al módulo dueño en el momento de mostrar. Tampoco hay nombres de personas: sólo
`alumno_id`, que se resuelve contra el padrón al leer (borrar o anonimizar a una persona no obliga a tocar estas tablas).

Convenciones del Maestro: prefijo por módulo (CV-01), identificadores de texto (CV-02), tiempo en milisegundos del reloj del NODO (CV-03, BR-062). Las referencias a otros
módulos (`grupo_id`, `alumno_id`, `dispositivo_id`, `sesion_id`) son lógicas, como en el libro y en Search.
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


# =================================================================================================================== derivadas

class Clase(models.Model):
    """El reporte de UNA clase terminada (CAP-081): la cabecera y los totales. Una fila por clase cerrada; se recalcula cuando llega algo tardío (la gracia de 15 minutos)."""

    sesion_id = models.CharField(max_length=36, primary_key=True)              # m07_sesion (lógica)
    grupo_id = models.CharField(max_length=36, blank=True, default="")         # vacío = clase sin padrón (Q-34)
    profesor_id = models.CharField(max_length=64, blank=True, default="")
    periodo = models.CharField(max_length=32, blank=True, default="")
    nivel_clave = models.CharField(max_length=64, blank=True, default="")
    curso_ref = models.CharField(max_length=200, blank=True, default="")
    leccion_ref = models.CharField(max_length=120, blank=True, default="")
    iniciada_en = models.BigIntegerField(null=True, blank=True)
    finalizada_en = models.BigIntegerField()
    duracion_ms = models.BigIntegerField(default=0)
    participantes = models.IntegerField(default=0)
    actividades = models.IntegerField(default=0)
    equipos = models.IntegerField(default=0)
    promedio_participacion = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    promedio_aciertos = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    senales = models.JSONField(default=list)                                    # señales de integración (cada una caduca): ver `dominio/integracion.py`
    estado_integracion = models.CharField(max_length=12, default="completa")    # `completa` | `incompleta`, tal como quedó al calcular
    corte_en = models.BigIntegerField()                                          # el instante del nodo en que se calculó desde el módulo dueño
    huella = models.CharField(max_length=64)

    class Meta:
        db_table = "m13_clase"
        constraints = [
            models.CheckConstraint(condition=Q(estado_integracion__in=("completa", "incompleta")), name="ck_m13_clase_integracion"),
            models.CheckConstraint(condition=Q(participantes__gte=0) & Q(actividades__gte=0) & Q(equipos__gte=0), name="ck_m13_clase_cuentas"),
            models.CheckConstraint(condition=Q(promedio_aciertos__isnull=True) | (Q(promedio_aciertos__gte=0) & Q(promedio_aciertos__lte=100)), name="ck_m13_clase_aciertos"),
        ]
        indexes = [models.Index(fields=["grupo_id", "finalizada_en"], name="ix_m13_clase_grupo"), models.Index(fields=["finalizada_en"], name="ix_m13_clase_fin")]


class ClaseAlumno(models.Model):
    """Lo que hizo UN alumno en UNA clase: presencia, actividades recibidas y entregadas, y sus aciertos. Una fila por participante que entró de verdad."""

    sesion = models.ForeignKey(Clase, on_delete=models.CASCADE, related_name="alumnos")
    alumno_id = models.CharField(max_length=64)                                 # m01_usuario.id (lógica)
    estado = models.CharField(max_length=16)                                    # presencia al terminar: conectado · reconectando · salio · expulsado
    dispositivo_id = models.CharField(max_length=36, blank=True, default="")    # m09_dispositivo (lógica)
    ingreso_en = models.BigIntegerField()
    salida_en = models.BigIntegerField(null=True, blank=True)
    presente_ms = models.BigIntegerField(default=0)
    actividades_recibidas = models.SmallIntegerField(default=0)
    actividades_entregadas = models.SmallIntegerField(default=0)
    calificadas = models.IntegerField(default=0)                                # respuestas ya calificadas (las que esperan al profesor no cuentan)
    aciertos = models.IntegerField(default=0)
    puntos = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    puntos_maximos = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    porcentaje_participacion = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    porcentaje_aciertos = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    entregas_por_cola = models.SmallIntegerField(default=0)                     # llegaron de la cola de la tableta, no en línea

    class Meta:
        db_table = "m13_clase_alumno"
        constraints = [
            models.UniqueConstraint(fields=["sesion", "alumno_id"], name="ux_m13_clase_alumno"),
            models.CheckConstraint(condition=Q(actividades_entregadas__lte=models.F("actividades_recibidas")) | Q(actividades_recibidas=0), name="ck_m13_ca_entrega"),
            models.CheckConstraint(condition=Q(porcentaje_aciertos__isnull=True) | (Q(porcentaje_aciertos__gte=0) & Q(porcentaje_aciertos__lte=100)), name="ck_m13_ca_aciertos"),
        ]
        indexes = [models.Index(fields=["alumno_id"], name="ix_m13_ca_alumno")]


class AvanceGrupo(models.Model):
    """El avance de UN grupo (FUN-139): los totales de lo que llevan sus alumnos. Se marca `desactualizado` cuando algo cambia y se recalcula FUERA del horario de clase
    (FUN-144) o en el momento en que alguien lo pide."""

    grupo_id = models.CharField(max_length=36, primary_key=True)                # m01_grupo (lógica)
    periodo = models.CharField(max_length=32, blank=True, default="")
    nivel_clave = models.CharField(max_length=64, blank=True, default="")
    modo = models.CharField(max_length=16, default="simple")                    # `simple` | `calificaciones`, tal como lo dijo el libro (MOD-011) para el nivel del grupo
    escala = models.JSONField(null=True, blank=True)                            # {codigo, nombre, tipo, numero} de la escala del nivel, o null en modo simple
    alumnos = models.IntegerField(default=0)
    clases = models.IntegerField(default=0)
    evaluaciones = models.IntegerField(default=0)
    estudios = models.IntegerField(default=0)
    en_atencion = models.IntegerField(default=0)
    promedio_participacion = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    promedio_aciertos = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    estado_integracion = models.CharField(max_length=12, default="completa")
    motivos_integracion = models.JSONField(default=list)                        # códigos vigentes al calcular (sirve para detectar un cambio y avisarlo una sola vez)
    desactualizado = models.BooleanField(default=True)
    desactualizado_en = models.BigIntegerField(null=True, blank=True)
    corte_en = models.BigIntegerField(default=0)

    class Meta:
        db_table = "m13_avance_grupo"
        constraints = [models.CheckConstraint(condition=Q(estado_integracion__in=("completa", "incompleta")), name="ck_m13_ag_integracion")]
        indexes = [models.Index(fields=["desactualizado"], name="ix_m13_ag_sucio")]


class AvanceAlumno(models.Model):
    """El avance de UN alumno en UN grupo (CAP-082): clases, actividades, evaluaciones y estudio, más el detalle como JSON de referencias y cifras (sin un solo título)."""

    grupo_id = models.CharField(max_length=36)
    alumno_id = models.CharField(max_length=64)
    clases_total = models.IntegerField(default=0)
    clases_asistidas = models.IntegerField(default=0)
    actividades_recibidas = models.IntegerField(default=0)
    actividades_entregadas = models.IntegerField(default=0)
    porcentaje_aciertos = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    evaluaciones_total = models.IntegerField(default=0)
    evaluaciones_presentadas = models.IntegerField(default=0)
    evaluaciones_sin_presentar = models.IntegerField(default=0)
    estudios_total = models.IntegerField(default=0)
    estudios_completados = models.IntegerField(default=0)
    estudios_vencidos = models.IntegerField(default=0)
    avance_estudio = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    atencion = models.JSONField(default=list)                                   # [{codigo, cantidad, texto}], del más al menos urgente
    ultima_actividad_en = models.BigIntegerField(null=True, blank=True)
    detalle = models.JSONField(default=dict)                                    # {"evaluaciones": [...], "estudios": [...]}: ids, estados y cifras; los rótulos se piden al leer
    corte_en = models.BigIntegerField(default=0)

    class Meta:
        db_table = "m13_avance_alumno"
        constraints = [models.UniqueConstraint(fields=["grupo_id", "alumno_id"], name="ux_m13_avance_alumno")]
        indexes = [models.Index(fields=["alumno_id"], name="ix_m13_aa_alumno")]


class EstadoDispositivo(models.Model):
    """Lo que una tableta avisó de su cola de estudio al cerrar su sesión (`estudio.sesion.cerrada.v1`, `cola_pendiente`), hasta que el nodo integró su trabajo
    (`estudio.trabajo.integrado.v1`). Es la señal `cola_de_estudio` de la integración (BR-083)."""

    alumno_id = models.CharField(max_length=64)
    dispositivo_id = models.CharField(max_length=36)
    cola_pendiente = models.IntegerField(default=0)
    avisada_en = models.BigIntegerField(default=0)

    class Meta:
        db_table = "m13_estado_dispositivo"
        constraints = [models.UniqueConstraint(fields=["alumno_id", "dispositivo_id"], name="ux_m13_estado_dispositivo"),
                       models.CheckConstraint(condition=Q(cola_pendiente__gte=0), name="ck_m13_ed_cola")]


class MarcaConsumidor(models.Model):
    """Hasta qué secuencia de la cola de salida de cada módulo se leyó (BR-007: un consumidor nuevo o reconstruido empieza en cero). Avanza en la misma transacción que lo
    aplicado. `secuencia_fallida` y `fallos_seguidos`: el evento que no se pudo aplicar retiene la marca unos ciclos antes de dejarse atrás con su asiento."""

    fuente = models.CharField(max_length=16, primary_key=True, choices=_lista(cat.FUENTES))
    ultima_secuencia = models.BigIntegerField(default=0)
    actualizada_en = models.BigIntegerField(default=ahora_ms)
    secuencia_fallida = models.BigIntegerField(default=0)
    fallos_seguidos = models.SmallIntegerField(default=0)

    class Meta:
        db_table = "m13_marca_consumidor"


class EstadoProyeccion(models.Model):
    """El estado técnico de las proyecciones (H del Maestro). Sólo se guarda `reconstruyendose`; `rezagada` se DERIVA (hay eventos relevantes sin aplicar) y `al_dia` es el resto.
    La pantalla lo muestra como antigüedad del dato, no como estado interno."""

    id = models.CharField(max_length=16, primary_key=True, default="reportes")
    reconstruyendose = models.BooleanField(default=False)
    reconstruccion_iniciada_en = models.BigIntegerField(null=True, blank=True)
    reconstruida_en = models.BigIntegerField(null=True, blank=True)
    reconstruida_por = models.CharField(max_length=64, blank=True, default="")
    actualizada_en = models.BigIntegerField(null=True, blank=True)              # la última vez que el hilo del nodo (FUN-144) actualizó los agregados
    ultimo_error = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        db_table = "m13_estado_proyeccion"


# =================================================================================================================== propias

class Config(models.Model):
    """La configuración del nodo (una fila, `nodo`): el umbral de privacidad (BR-086, apagado de fábrica) y la política de exportación (por defecto: se puede guardar en
    todas partes y no se pide razón). Sólo la cambia quien tiene `reports.settings.manage`."""

    id = models.CharField(max_length=16, primary_key=True, default="nodo")
    umbral_privacidad = models.BooleanField(default=False)
    extraibles_permitidos = models.BooleanField(default=True)
    exigir_razon = models.BooleanField(default=False)
    version = models.IntegerField(default=1)
    actualizada_en = models.BigIntegerField(null=True, blank=True)
    actualizada_por = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "m13_config"


class Exportacion(models.Model):
    """Una exportación a archivo (FUN-146), registrada en DOS tiempos para que la bitácora no mienta: al autorizar y generar (`autorizada`, «sin confirmar») y cuando el
    cliente confirma qué pasó (`entregada`). Una que nadie confirma `caduca` y no cuenta como entregada. Guarda la huella y las cifras del archivo, NUNCA su contenido ni la
    ruta donde quedó. Los intentos fallidos se anotan sin cerrarla: el profesor puede elegir otro destino sin generar de nuevo."""

    id = models.CharField(max_length=36, primary_key=True)
    tipo = models.CharField(max_length=16, choices=_lista(cat.TIPOS))
    parametros = models.JSONField(default=dict)                                 # el alcance del reporte: sólo identificadores y fechas
    formato = models.CharField(max_length=8, choices=_lista(cat.FORMATOS))
    actor_id = models.CharField(max_length=64, blank=True, default="")
    actor_rol = models.CharField(max_length=32, blank=True, default="")
    nominal = models.BooleanField(default=False)                                # el archivo lleva nombres de personas
    umbral_aplicado = models.BooleanField(default=False)
    filas = models.IntegerField(default=0)
    bytes_total = models.BigIntegerField(default=0)
    huella = models.CharField(max_length=64)
    nombre_archivo = models.CharField(max_length=120, blank=True, default="")
    corte_en = models.BigIntegerField()
    integracion = models.JSONField(default=dict)                                # el bloque de integración declarado dentro del archivo
    destino_autorizado = models.CharField(max_length=16, choices=_lista(cat.DESTINOS))
    razon_codigo = models.CharField(max_length=32, blank=True, default="")
    estado = models.CharField(max_length=12, choices=_lista(cat.ESTADOS_DE_EXPORTACION), default=cat.EXP_AUTORIZADA)
    intentos = models.JSONField(default=list)                                   # [{en, resultado, motivo, destino_tipo}]
    destino_tipo = models.CharField(max_length=16, blank=True, default="")      # el destino donde SÍ quedó guardado
    huella_verificada = models.CharField(max_length=64, blank=True, default="")
    autorizada_en = models.BigIntegerField(default=ahora_ms)
    expira_en = models.BigIntegerField()
    confirmada_en = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "m13_exportacion"
        constraints = [
            models.CheckConstraint(condition=Q(estado__in=cat.ESTADOS_DE_EXPORTACION), name="ck_m13_exp_estado"),
            models.CheckConstraint(condition=~Q(estado=cat.EXP_ENTREGADA) | (Q(confirmada_en__isnull=False) & ~Q(huella_verificada="") & ~Q(destino_tipo="")),
                                   name="ck_m13_exp_entregada_confirmada"),
            models.CheckConstraint(condition=Q(expira_en__gt=models.F("autorizada_en")), name="ck_m13_exp_vigencia"),
        ]
        indexes = [models.Index(fields=["actor_id", "autorizada_en"], name="ix_m13_exp_actor"), models.Index(fields=["estado", "expira_en"], name="ix_m13_exp_estado")]


class Reciente(models.Model):
    """Un reporte que alguien abrió hace poco: sólo sus PARÁMETROS (qué reporte, de qué grupo, de qué periodo), nunca su contenido. Sirve para volver a abrirlo y exportarlo
    sin repetir los filtros; al abrirlo, el nodo vuelve a armarlo con lo que hay ahora (el contenido no se guarda aquí)."""

    actor_id = models.CharField(max_length=64)
    tipo = models.CharField(max_length=16, choices=_lista(cat.TIPOS))
    clave = models.CharField(max_length=40)                                     # huella corta de (tipo, parámetros): un mismo reporte no se repite en la lista
    parametros = models.JSONField(default=dict)
    ultima_vez_en = models.BigIntegerField(default=ahora_ms)
    veces = models.IntegerField(default=1)
    ultima_exportacion_en = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "m13_reciente"
        constraints = [models.UniqueConstraint(fields=["actor_id", "clave"], name="ux_m13_reciente")]
        indexes = [models.Index(fields=["actor_id", "ultima_vez_en"], name="ix_m13_reciente_actor")]


class EventoSalida(models.Model):
    """Transactional Outbox de MOD-013 (`reporte.*.v1`). Se escribe en la misma transacción que el hecho. Cuando exista MOD-015 (m15_evento) las colas se unifican allí."""

    agregado_tipo = models.CharField(max_length=32)
    agregado_id = models.CharField(max_length=64)
    tipo_evento = models.CharField(max_length=64)
    carga = models.JSONField(default=dict)
    creado_en = models.BigIntegerField(default=ahora_ms)
    publicado_en = models.BigIntegerField(null=True, blank=True)
    intentos = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "m13_evento_salida"
        indexes = [models.Index(fields=["publicado_en", "creado_en"], name="ix_m13_outbox")]


# Las tablas que se borran y se reconstruyen desde la cola (BR-007). Una prueba comprueba que TODA tabla m13_* está en exactamente una de las dos listas.
TABLAS_DERIVADAS = ("m13_clase", "m13_clase_alumno", "m13_avance_grupo", "m13_avance_alumno", "m13_estado_dispositivo", "m13_marca_consumidor", "m13_estado_proyeccion")
TABLAS_PROPIAS = ("m13_config", "m13_exportacion", "m13_reciente", "m13_evento_salida")

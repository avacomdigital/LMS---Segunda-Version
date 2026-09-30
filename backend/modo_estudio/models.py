"""
MOD-008 · Modo Estudio · tablas `m08_*`.

Lo que el módulo POSEE (Maestro: «no es propietario de ningún grupo de datos; opera consumiendo hechos de otros módulos»; mientras
MOD-010 —asignaciones e intentos— no tenga dueño, `m08_asignacion`, `m08_tarea` y `m08_practica` viven aquí como PROVISIONALES, igual
que `m07_intento` vive provisional en MOD-007): la asignación de una lección a un grupo o a alumnos, la tarea de cada alumno, el paquete
de estudio de un aparato, la práctica autocalificable, el libro de eventos que llegan de la cola del aparato y la cola de salida.
Ningún otro módulo escribe aquí (escritor único).

Lo que NO hay, y no es un olvido (regla de oro, artículo 14): ninguna tabla ni columna de curso, lección, objeto, lámina, medio,
pregunta u opción, ni ninguna clave de respuesta. El curso vive en AVACOM Biblioteca; aquí sólo hay referencias (`*_ref`, CV-08), los
rótulos que se vieron al asignar (evidencia que no se refresca) y la estructura de bloques como referencias. La clave de una respuesta
sólo vive en la biblioteca: aquí se guarda lo que el alumno contestó y el veredicto que la biblioteca devolvió.

Convenciones: prefijo por módulo (CV-01), identificadores de texto (CV-02), tiempo en milisegundos del reloj del nodo (CV-03, BR-062),
nada se borra (CV-05: el paquete que el alumno borra queda con `retirado_en`), estados acotados por restricciones (CV-06) e invariantes
como restricciones e índices parciales (CV-07). Las referencias a MOD-001 (`grupo_id`, `alumno_id`, `profesor_id`) y a MOD-009
(`dispositivo_id`) son lógicas, como en el aula.
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


class Asignacion(models.Model):
    """Una lección asignada a un grupo o a alumnos con fecha límite (CAP-050). Provisional hasta MOD-010.

    `alcance = grupo` alcanza a todos los alumnos ACTIVOS del grupo, también a los que entren después; `seleccion` sólo a los
    `destinatarios`. `bloques` es la estructura de la lección como referencias (D-4) tal como se vio al asignar: se refresca al abrir
    la lección si la versión del curso cambió. `bytes_estimados` se mide al asignar y se afina al preparar el paquete."""

    id = models.CharField(max_length=36, primary_key=True)
    grupo_id = models.CharField(max_length=36, blank=True, default="")      # m01_grupo (lógica); vacío si son alumnos sueltos
    grupo_rotulo = models.CharField(max_length=120, blank=True, default="")
    alcance = models.CharField(max_length=16, choices=_lista(cat.ALCANCES), default=cat.GRUPO)
    destinatarios = models.JSONField(default=list)                           # lista de alumno_id; sólo con `seleccion`
    profesor_id = models.CharField(max_length=64)                            # quien asigna (m01_usuario.id o identificador del aula)
    profesor_rotulo = models.CharField(max_length=120, blank=True, default="")
    fuente_curso = models.CharField(max_length=16, blank=True, default="")   # biblioteca | ejemplo
    curso_ref = models.CharField(max_length=200)
    curso_version = models.CharField(max_length=32, blank=True, default="")
    curso_rotulo = models.CharField(max_length=250, blank=True, default="")
    leccion_ref = models.CharField(max_length=120)
    leccion_rotulo = models.CharField(max_length=250, blank=True, default="")
    titulo = models.CharField(max_length=250)
    descripcion = models.CharField(max_length=500, blank=True, default="")
    asignatura_rotulo = models.CharField(max_length=120, blank=True, default="")   # classification.subject.name
    unidad_rotulo = models.CharField(max_length=200, blank=True, default="")       # classification.topic.name
    consigna = models.TextField(blank=True, default="")                      # opcional: el profesor no tiene teclado, se ofrece por opciones
    bloques = models.JSONField(default=list)                                 # [{ref, indice, objeto_ref, tipo, titulo, obligatorio, medios}]
    practica = models.JSONField(null=True, blank=True)                       # {objeto_ref, titulo, total_preguntas}: la primera actividad
    evaluacion = models.JSONField(null=True, blank=True)                     # {objeto_ref, titulo}: el primer examen, SÓLO informativo
    bytes_estimados = models.BigIntegerField(null=True, blank=True)
    paquete_permitido = models.BooleanField(default=True)                    # «decide si queda disponible en modo de estudio» (JRN-007)
    fecha_limite = models.BigIntegerField(null=True, blank=True)
    plazo = models.CharField(max_length=12, choices=_lista(cat.PLAZOS), default=cat.BLANDO)
    gracia_ms = models.IntegerField(default=cat.GRACIA_MS_POR_DEFECTO)       # DEC-019
    estado = models.CharField(max_length=12, choices=_lista(cat.ESTADOS_ASIGNACION), default=cat.ACTIVA)
    creada_en = models.BigIntegerField(default=ahora_ms)
    cerrada_en = models.BigIntegerField(null=True, blank=True)
    creado_por = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "m08_asignacion"
        constraints = [
            models.CheckConstraint(condition=Q(alcance__in=cat.ALCANCES), name="ck_m08_asignacion_alcance"),
            models.CheckConstraint(condition=Q(plazo__in=cat.PLAZOS), name="ck_m08_asignacion_plazo"),
            models.CheckConstraint(condition=Q(estado__in=cat.ESTADOS_ASIGNACION), name="ck_m08_asignacion_estado"),
            # `cerrada` y tener fecha de cierre son lo mismo.
            models.CheckConstraint(condition=(Q(estado=cat.CERRADA) & Q(cerrada_en__isnull=False))
                                   | (~Q(estado=cat.CERRADA) & Q(cerrada_en__isnull=True)), name="ck_m08_asignacion_cierre_fechado"),
            models.CheckConstraint(condition=Q(gracia_ms__gte=0), name="ck_m08_asignacion_gracia"),
        ]
        indexes = [models.Index(fields=["grupo_id", "estado"], name="ix_m08_asignacion_grupo"),
                   models.Index(fields=["estado", "fecha_limite"], name="ix_m08_asignacion_plazo")]

    def __str__(self) -> str:
        return f"{self.titulo} · {self.estado}"


class Tarea(models.Model):
    """El estado de una asignación para UN alumno (provisional hasta MOD-010). Se crea al primer contacto del alumno (abrir,
    avanzar, pedir paquete o practicar); una asignación sin tarea equivale a `pendiente`. «Vencida» no se guarda: es derivada."""

    id = models.CharField(max_length=36, primary_key=True)
    asignacion = models.ForeignKey(Asignacion, on_delete=models.CASCADE, related_name="tareas")
    alumno_id = models.CharField(max_length=64)                              # m01_usuario.id (lógica)
    estado = models.CharField(max_length=12, choices=_lista(cat.ESTADOS_TAREA), default=cat.PENDIENTE)
    bloques_vistos = models.JSONField(default=list)                          # sólo referencias que existen en `asignacion.bloques`
    ultimo_bloque_ref = models.CharField(max_length=200, blank=True, default="")   # punto de reanudación
    posicion_seg = models.IntegerField(null=True, blank=True)
    avance_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)   # obligatorios atendidos / obligatorios; NO es una nota
    fuera_de_plazo = models.BooleanField(default=False)                      # completada o avanzada después de la fecha con plazo blando
    practica_intentos = models.SmallIntegerField(default=0)                  # resumen de sus prácticas (aciertos)
    practica_mejor = models.SmallIntegerField(null=True, blank=True)
    practica_ultima = models.SmallIntegerField(null=True, blank=True)
    practica_total = models.SmallIntegerField(default=0)
    abierta_en = models.BigIntegerField(null=True, blank=True)
    ultimo_avance_en = models.BigIntegerField(null=True, blank=True)
    completada_en = models.BigIntegerField(null=True, blank=True)
    creada_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m08_tarea"
        constraints = [
            models.UniqueConstraint(fields=["asignacion", "alumno_id"], name="ux_m08_tarea"),
            models.CheckConstraint(condition=Q(estado__in=cat.ESTADOS_TAREA), name="ck_m08_tarea_estado"),
            models.CheckConstraint(condition=~Q(estado=cat.COMPLETADA) | Q(completada_en__isnull=False), name="ck_m08_tarea_completada_fechada"),
            models.CheckConstraint(condition=Q(avance_pct__gte=0) & Q(avance_pct__lte=100), name="ck_m08_tarea_avance"),
        ]
        indexes = [models.Index(fields=["alumno_id", "estado"], name="ix_m08_tarea_alumno")]


class Paquete(models.Model):
    """El paquete de estudio de UN aparato para UN alumno y una asignación (CAP-047, D-7, D-8): la lección sin claves más los medios
    que referencia, con su huella y su vigencia. Sólo guarda metadatos de los archivos (nunca contenido). Volver a pedirlo reutiliza
    la fila («Actualizar descarga»). `vencido` se calcula al leer y se persiste; el alumno que borra su copia deja `retirado_en`."""

    id = models.CharField(max_length=36, primary_key=True)
    asignacion = models.ForeignKey(Asignacion, on_delete=models.CASCADE, related_name="paquetes")
    alumno_id = models.CharField(max_length=64)
    dispositivo_id = models.CharField(max_length=36)                         # m09_dispositivo (lógica)
    estado = models.CharField(max_length=16, choices=_lista(cat.ESTADOS_PAQUETE), default=cat.SOLICITADO)
    motivo = models.CharField(max_length=48, blank=True, default="")         # denegado o vencido: por qué
    curso_version = models.CharField(max_length=32, blank=True, default="")  # la del curso al preparar el paquete
    huella = models.CharField(max_length=64, blank=True, default="")         # SHA-256 del manifiesto canónico
    bytes_total = models.BigIntegerField(default=0)                          # suma de los medios
    archivos = models.JSONField(default=list)                                # [{media_ref, clase, mime, bytes, sha256}]
    no_incluidos = models.JSONField(default=list)                            # [{media_ref, motivo}]
    vigente_hasta = models.BigIntegerField(null=True, blank=True)
    solicitado_en = models.BigIntegerField(default=ahora_ms)
    descarga_iniciada_en = models.BigIntegerField(null=True, blank=True)
    disponible_en = models.BigIntegerField(null=True, blank=True)
    retirado_en = models.BigIntegerField(null=True, blank=True)
    actualizado_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m08_paquete"
        constraints = [
            models.UniqueConstraint(fields=["asignacion", "alumno_id", "dispositivo_id"], name="ux_m08_paquete"),
            models.CheckConstraint(condition=Q(estado__in=cat.ESTADOS_PAQUETE), name="ck_m08_paquete_estado"),
            # `disponible` exige huella y fecha: un paquete sin huella no se puede verificar.
            models.CheckConstraint(condition=~Q(estado=cat.DISPONIBLE) | (~Q(huella="") & Q(disponible_en__isnull=False)),
                                   name="ck_m08_paquete_disponible_con_huella"),
        ]
        indexes = [models.Index(fields=["dispositivo_id", "estado"], name="ix_m08_paquete_dispositivo")]


class Practica(models.Model):
    """Una práctica autocalificable: actividad de aprendizaje SEPARADA de la evaluación formal (D-5, BR-055). Provisional hasta MOD-010.

    `modo` sólo admite `estudio` (`CHECK`): esta tabla no puede contener intentos formales, y el módulo nunca toca `m07_intento` ni
    `m10_intento`. Sin tope de intentos. Las respuestas por pregunta viven dentro de la práctica, como en `m07_intento` (decisión del CTO
    del 2026-09-24): una por elemento de `respuestas` con su secuencia, su hora capturada y su veredicto. La unicidad (pregunta,
    secuencia) de INV-013 se valida en la aplicación, dentro de la transacción, porque no se puede expresar sobre una lista JSON.
    `puntaje` y `puntaje_maximo` viven en la escala interna y no se publican (DEC-032)."""

    id = models.CharField(max_length=36, primary_key=True)
    tarea = models.ForeignKey(Tarea, on_delete=models.CASCADE, related_name="practicas")
    alumno_id = models.CharField(max_length=64)
    objeto_ref = models.CharField(max_length=120)                            # la `activity` practicada
    objeto_rotulo = models.CharField(max_length=250, blank=True, default="")
    numero = models.SmallIntegerField(default=1)                             # 1, 2, 3… sin tope
    modo = models.CharField(max_length=8, default=cat.MODO_ESTUDIO)
    estado = models.CharField(max_length=12, choices=_lista(cat.ESTADOS_PRACTICA), default=cat.EN_CURSO)
    respuestas = models.JSONField(default=list)                              # {pregunta_ref, respuesta, secuencia, sesion_ref, recibida_en, capturada_en, veredicto}
    total_preguntas = models.SmallIntegerField(default=0)
    aciertos = models.SmallIntegerField(default=0)                           # respuestas con correcta = true
    puntaje = models.FloatField(null=True, blank=True)                       # sólo de lo ya calificado; escala interna, no se publica
    puntaje_maximo = models.FloatField(null=True, blank=True)
    origen = models.CharField(max_length=8, choices=_lista(cat.ORIGENES), default=cat.DIRECTO)
    dispositivo_id = models.CharField(max_length=36, blank=True, default="")
    iniciada_en = models.BigIntegerField(default=ahora_ms)
    terminada_en = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "m08_practica"
        constraints = [
            models.UniqueConstraint(fields=["tarea", "objeto_ref", "numero"], name="ux_m08_practica_numero"),
            # Una en curso por tarea y actividad: se REANUDA en vez de abrir otra (FUN-088).
            models.UniqueConstraint(fields=["tarea", "objeto_ref"], condition=Q(estado=cat.EN_CURSO), name="ux_m08_practica_en_curso"),
            models.CheckConstraint(condition=Q(modo=cat.MODO_ESTUDIO), name="ck_m08_practica_modo_estudio"),
            models.CheckConstraint(condition=Q(estado__in=cat.ESTADOS_PRACTICA), name="ck_m08_practica_estado"),
            models.CheckConstraint(condition=~Q(estado=cat.TERMINADA) | Q(terminada_en__isnull=False), name="ck_m08_practica_terminada_fechada"),
        ]
        indexes = [models.Index(fields=["tarea", "objeto_ref"], name="ix_m08_practica_tarea")]


class Sincronizacion(models.Model):
    """El libro de eventos que llegan de la cola del aparato (CAP-048, D-10, D-11). `UNIQUE(emisor_id, secuencia)`: el reenvío NO
    duplica (BR-060). Sin FK. `carga` sólo se conserva completa mientras el evento está `pendiente_decision`; después queda un resumen
    sin el contenido de las respuestas (BR-127). `resultado` guarda lo que se contestó, para responder igual a un reenvío.
    `ocurrido_en` ya viene normalizado al reloj del nodo; `ocurrido_en_tableta` es la hora cruda del aparato (dato adicional, BR-062)."""

    id = models.BigAutoField(primary_key=True)
    emisor_id = models.CharField(max_length=64)
    secuencia = models.BigIntegerField()
    alumno_id = models.CharField(max_length=64)
    dispositivo_id = models.CharField(max_length=36, blank=True, default="")
    tipo = models.CharField(max_length=40)
    asignacion_id = models.CharField(max_length=36, blank=True, default="")
    estado = models.CharField(max_length=20, choices=_lista(cat.ESTADOS_LIBRO))
    motivo = models.CharField(max_length=64, blank=True, default="")
    ocurrido_en = models.BigIntegerField()
    ocurrido_en_tableta = models.BigIntegerField(null=True, blank=True)
    recibido_en = models.BigIntegerField(default=ahora_ms)
    carga = models.JSONField(default=dict)
    resultado = models.JSONField(default=dict)

    class Meta:
        db_table = "m08_sincronizacion"
        constraints = [
            models.UniqueConstraint(fields=["emisor_id", "secuencia"], name="ux_m08_sync_emisor_secuencia"),
            models.CheckConstraint(condition=Q(estado__in=cat.ESTADOS_LIBRO), name="ck_m08_sync_estado"),
        ]
        indexes = [models.Index(fields=["alumno_id", "estado"], name="ix_m08_sync_alumno"),
                   models.Index(fields=["asignacion_id", "estado"], name="ix_m08_sync_asignacion")]


class EventoSalida(models.Model):
    """Transactional Outbox de MOD-008 (`estudio.*.v1`). Se escribe en la misma transacción que el hecho (DEC-007). Cuando exista
    MOD-015 (m15_evento) las colas de todos los módulos se unifican allí."""

    agregado_tipo = models.CharField(max_length=32)
    agregado_id = models.CharField(max_length=64)
    tipo_evento = models.CharField(max_length=64)
    carga = models.JSONField(default=dict)
    creado_en = models.BigIntegerField(default=ahora_ms)
    publicado_en = models.BigIntegerField(null=True, blank=True)
    intentos = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "m08_evento_salida"
        indexes = [models.Index(fields=["publicado_en", "creado_en"], name="ix_m08_outbox")]

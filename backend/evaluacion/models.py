"""
MOD-010 · Evaluation & Delivery Engine · tablas `m10_*`.

Lo que el módulo POSEE (Maestro, sección K): las asignaciones de evaluación, las admisiones de dispositivos por debajo del nivel, los intentos
(con sus respuestas dentro, decisión del CTO del 2026-09-24), los incidentes del intento y la cola de salida. Ningún otro módulo escribe aquí
(escritor único, BR-003).

Lo que NO hay, y no es un olvido (regla de oro, artículo 14): ninguna tabla ni columna de curso, lección, objeto, pregunta u opción, ni ninguna
clave de respuesta. El examen vive en AVACOM Biblioteca; aquí sólo hay referencias (`*_ref`, CV-08), la versión congelada del curso, los rótulos
que se vieron al asignar (evidencia que no se refresca) y lo que el alumno hizo. La clave de una respuesta sólo vive en la biblioteca: aquí se
guarda lo que el alumno contestó y el veredicto que la biblioteca devolvió.

Convenciones: prefijo por módulo (CV-01), identificadores de texto (CV-02), tiempo en milisegundos del reloj del nodo (CV-03, BR-062), nada se
borra (CV-05: las FK son PROTECT), estados acotados por restricciones (CV-06) e invariantes como restricciones e índices parciales (CV-07). Las
referencias a MOD-001 (`grupo_id`, `alumno_id`, `profesor_id`), MOD-007 (`sesion_id`) y MOD-009 (`dispositivo_id`, `sesion_ref`) son lógicas,
como en el aula y en el modo de estudio.
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


class Asignacion(models.Model):
    """ENT-011. Una evaluación (un `exam` de un curso de la biblioteca, con su versión) asignada a un grupo o a alumnos con su política de plazo,
    su nivel de control y su regla de reactivación. `alcance = grupo` alcanza a todos los alumnos ACTIVOS del grupo, también a los que entren
    después; `seleccion` sólo a los `destinatarios`. `nivel_declarado` es el mínimo con que se creó; `nivel_examen` es el vigente y sólo baja
    (FUN-118). `ajustes` copia los ajustes del examen que se usaron para asignar (estrategia, tolerancias, política de tiempo…): son evidencia y
    parámetros de armado, no contenido."""

    id = models.CharField(max_length=36, primary_key=True)
    tipo = models.CharField(max_length=10, choices=_lista(cat.TIPOS), default=cat.EXAMEN)
    sesion_id = models.CharField(max_length=36, blank=True, default="")          # m07_sesion (lógica) si nació en una clase
    grupo_id = models.CharField(max_length=36, blank=True, default="")           # m01_grupo (lógica); vacío si son alumnos sueltos
    grupo_rotulo = models.CharField(max_length=120, blank=True, default="")
    alcance = models.CharField(max_length=16, choices=_lista(cat.ALCANCES), default=cat.GRUPO)
    destinatarios = models.JSONField(default=list)                                # lista de alumno_id; sólo con `seleccion`
    profesor_id = models.CharField(max_length=64)
    profesor_rotulo = models.CharField(max_length=120, blank=True, default="")
    fuente_curso = models.CharField(max_length=16, blank=True, default="")       # biblioteca | ejemplo
    curso_ref = models.CharField(max_length=200)
    curso_version = models.CharField(max_length=32, blank=True, default="")      # la CONGELADA (INV-024)
    curso_rotulo = models.CharField(max_length=250, blank=True, default="")
    leccion_ref = models.CharField(max_length=120, blank=True, default="")
    objeto_ref = models.CharField(max_length=120)
    objeto_rotulo = models.CharField(max_length=250, blank=True, default="")
    titulo = models.CharField(max_length=250)
    estrategia = models.CharField(max_length=16, blank=True, default="")         # fixed | random_balanced
    preguntas_por_alumno = models.PositiveSmallIntegerField(default=0)
    total_banco = models.PositiveSmallIntegerField(default=0)
    ajustes = models.JSONField(default=dict)
    nivel_declarado = models.CharField(max_length=12, choices=_lista(cat.NIVELES))
    nivel_examen = models.CharField(max_length=12, choices=_lista(cat.NIVELES))
    tiempo_modo = models.CharField(max_length=12, choices=_lista(cat.MODOS_TIEMPO), default=cat.TIEMPO_BIBLIOTECA)
    tiempo_limite_seg = models.PositiveIntegerField(null=True, blank=True)
    intentos_permitidos = models.PositiveSmallIntegerField(null=True, blank=True, default=1)   # BR-072: uno; nulo = sin tope
    abre_en = models.BigIntegerField(null=True, blank=True)
    limite_en = models.BigIntegerField(null=True, blank=True)
    plazo = models.CharField(max_length=12, choices=_lista(cat.PLAZOS), default=cat.BLANDO)
    gracia_ms = models.IntegerField(default=cat.GRACIA_MS_POR_DEFECTO)            # DEC-019
    reactivacion = models.CharField(max_length=12, choices=_lista(cat.REACTIVACIONES), default=cat.REACTIVA_PROFESOR)
    recursos = models.JSONField(default=list)                                     # [{media_ref, rotulo}] habilitados en `supervisado`
    resultados = models.CharField(max_length=16, choices=_lista(cat.RESULTADOS), default=cat.TRAS_LIBERAR)
    liberados_en = models.BigIntegerField(null=True, blank=True)                  # DEC-032: el alumno ve su nota desde aquí
    aprobacion_pct = models.FloatField(null=True, blank=True)
    permite_retroceso = models.BooleanField(default=True)
    mezclar_opciones = models.BooleanField(default=True)
    estado = models.CharField(max_length=24, choices=_lista(cat.ESTADOS_ASIGNACION), default=cat.BORRADOR)
    creada_en = models.BigIntegerField(default=ahora_ms)
    publicada_en = models.BigIntegerField(null=True, blank=True)
    cerrada_en = models.BigIntegerField(null=True, blank=True)
    archivada_en = models.BigIntegerField(null=True, blank=True)
    creado_por = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "m10_asignacion"
        constraints = [
            models.CheckConstraint(condition=Q(tipo__in=cat.TIPOS), name="ck_m10_asignacion_tipo"),
            models.CheckConstraint(condition=Q(alcance__in=cat.ALCANCES), name="ck_m10_asignacion_alcance"),
            models.CheckConstraint(condition=Q(plazo__in=cat.PLAZOS), name="ck_m10_asignacion_plazo"),
            models.CheckConstraint(condition=Q(reactivacion__in=cat.REACTIVACIONES), name="ck_m10_asignacion_reactivacion"),
            models.CheckConstraint(condition=Q(resultados__in=cat.RESULTADOS), name="ck_m10_asignacion_resultados"),
            models.CheckConstraint(condition=Q(tiempo_modo__in=cat.MODOS_TIEMPO), name="ck_m10_asignacion_tiempo_modo"),
            models.CheckConstraint(condition=Q(estado__in=cat.ESTADOS_ASIGNACION), name="ck_m10_asignacion_estado"),
            models.CheckConstraint(condition=Q(nivel_declarado__in=cat.NIVELES) & Q(nivel_examen__in=cat.NIVELES), name="ck_m10_asignacion_nivel"),
            # El nivel vigente NUNCA supera al declarado: controlado ≥ supervisado ≥ abierto (FUN-118 sólo degrada).
            models.CheckConstraint(
                condition=Q(nivel_declarado=cat.CONTROLADO)
                | (Q(nivel_declarado=cat.SUPERVISADO) & Q(nivel_examen__in=(cat.SUPERVISADO, cat.ABIERTO)))
                | (Q(nivel_declarado=cat.ABIERTO) & Q(nivel_examen=cat.ABIERTO)),
                name="ck_m10_asignacion_nivel_no_sube"),
            models.CheckConstraint(condition=~Q(estado__in=cat.CON_CIERRE) | Q(cerrada_en__isnull=False), name="ck_m10_asignacion_cierre_fechado"),
            models.CheckConstraint(condition=~Q(estado=cat.ARCHIVADA) | Q(archivada_en__isnull=False), name="ck_m10_asignacion_archivo_fechado"),
            models.CheckConstraint(condition=Q(abre_en__isnull=True) | Q(limite_en__isnull=True) | Q(limite_en__gte=F("abre_en")),
                                   name="ck_m10_asignacion_vigencia"),
            models.CheckConstraint(condition=Q(gracia_ms__gte=0), name="ck_m10_asignacion_gracia"),
            models.CheckConstraint(condition=Q(intentos_permitidos__isnull=True) | Q(intentos_permitidos__gte=1), name="ck_m10_asignacion_intentos"),
            # `fijo` ⇔ hay un límite de tiempo fijado por el profesor.
            models.CheckConstraint(
                condition=(Q(tiempo_modo=cat.TIEMPO_FIJO) & Q(tiempo_limite_seg__gte=1))
                | (~Q(tiempo_modo=cat.TIEMPO_FIJO) & Q(tiempo_limite_seg__isnull=True)),
                name="ck_m10_asignacion_tiempo_fijo"),
        ]
        indexes = [models.Index(fields=["grupo_id", "estado"], name="ix_m10_asignacion_grupo"),
                   models.Index(fields=["sesion_id"], name="ix_m10_asignacion_sesion"),
                   models.Index(fields=["estado", "limite_en"], name="ix_m10_asignacion_plazo")]

    def __str__(self) -> str:
        return f"{self.titulo} · {self.estado}"


class Admision(models.Model):
    """BR-075, BR-076, FUN-116. Una tableta que no alcanza el nivel NO abre el intento sola: queda `en_espera` hasta que el PROFESOR la admite (en
    un nivel menor, con motivo) o la rechaza. El alumno no queda nunca excluido del examen por su dispositivo: el profesor puede admitirlo, bajar
    el nivel de todo el examen o cambiarle la tableta."""

    id = models.CharField(max_length=36, primary_key=True)
    asignacion = models.ForeignKey(Asignacion, on_delete=models.PROTECT, related_name="admisiones")
    alumno_id = models.CharField(max_length=64)
    alumno_rotulo = models.CharField(max_length=120, blank=True, default="")
    dispositivo_id = models.CharField(max_length=36)                              # m09_dispositivo (lógica)
    dispositivo_rotulo = models.CharField(max_length=120, blank=True, default="")
    nivel_exigido = models.CharField(max_length=12, choices=_lista(cat.NIVELES))
    nivel_alcanzado = models.CharField(max_length=12, choices=_lista(cat.NIVELES))
    estado = models.CharField(max_length=12, choices=_lista(cat.ESTADOS_ADMISION), default=cat.EN_ESPERA)
    nivel_admitido = models.CharField(max_length=12, blank=True, default="")
    motivo = models.CharField(max_length=200, blank=True, default="")
    solicitada_en = models.BigIntegerField(default=ahora_ms)
    decidido_por = models.CharField(max_length=64, blank=True, default="")
    decidido_en = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "m10_admision"
        constraints = [
            models.UniqueConstraint(fields=["asignacion", "alumno_id", "dispositivo_id"], name="ux_m10_admision"),
            models.CheckConstraint(condition=Q(estado__in=cat.ESTADOS_ADMISION), name="ck_m10_admision_estado"),
            models.CheckConstraint(condition=Q(estado=cat.EN_ESPERA) | (~Q(decidido_por="") & Q(decidido_en__isnull=False)),
                                   name="ck_m10_admision_decidida"),
            models.CheckConstraint(condition=~Q(estado=cat.ADMITIDO) | (~Q(nivel_admitido="") & ~Q(motivo="")), name="ck_m10_admision_admitida"),
        ]
        indexes = [models.Index(fields=["asignacion", "estado"], name="ix_m10_admision_estado")]


class Intento(models.Model):
    """ENT-012, el agregado más crítico. Las respuestas por pregunta viven DENTRO del intento (decisión del CTO del 2026-09-24): una por elemento
    de `respuestas`. INV-013 (intento + pregunta + sesión + secuencia) no se puede expresar como restricción sobre una lista JSON: se valida en
    la aplicación, dentro de la transacción, y se prueba con reenvíos. `armado` guarda sólo REFERENCIAS (el examen de este alumno); su texto se
    vuelve a pedir a la biblioteca con la misma `semilla`. El reloj es del nodo: `reloj_desde` es NULO mientras está congelado."""

    id = models.CharField(max_length=36, primary_key=True)
    asignacion = models.ForeignKey(Asignacion, on_delete=models.PROTECT, related_name="intentos")
    alumno_id = models.CharField(max_length=64)
    alumno_rotulo = models.CharField(max_length=120, blank=True, default="")
    numero = models.PositiveSmallIntegerField(default=1)
    estado = models.CharField(max_length=24, choices=_lista(cat.ESTADOS_INTENTO), default=cat.NO_INICIADO)
    nivel_efectivo = models.CharField(max_length=12, choices=_lista(cat.NIVELES))
    bloqueo = models.JSONField(default=dict)                                      # último informe de la tableta (D-12)
    dispositivo_id = models.CharField(max_length=36, blank=True, default="")
    sesion_ref = models.CharField(max_length=36, blank=True, default="")
    sesiones = models.JSONField(default=list)                                     # [{sesion_ref, orden, dispositivo_id, desde, hasta}]
    semilla = models.CharField(max_length=160, blank=True, default="")
    curso_version = models.CharField(max_length=32, blank=True, default="")      # congelada al abrir (INV-024)
    armado = models.JSONField(default=list)                                       # [pregunta_ref] en el orden del alumno
    armado_meta = models.JSONField(default=dict)
    tiempo_limite_seg = models.PositiveIntegerField(null=True, blank=True)
    consumido_ms = models.BigIntegerField(default=0)
    reloj_desde = models.BigIntegerField(null=True, blank=True)
    pausas = models.JSONField(default=list)                                       # [{desde, hasta, causa, estado_previo, reactivado_por}]
    ultimo_latido_en = models.BigIntegerField(null=True, blank=True)
    pregunta_actual = models.CharField(max_length=120, blank=True, default="")
    respuestas = models.JSONField(default=list)
    secuencia_maxima = models.IntegerField(default=0)
    puntaje = models.FloatField(null=True, blank=True)
    puntaje_maximo = models.FloatField(null=True, blank=True)
    porcentaje = models.FloatField(null=True, blank=True)                         # escala interna 0–100 (DEC-003)
    sin_calificar = models.PositiveSmallIntegerField(default=0)
    requiere_revision = models.BooleanField(default=False)
    calificacion_pendiente = models.BooleanField(default=False)                   # la biblioteca no estaba al entregar
    calificado_por = models.CharField(max_length=64, blank=True, default="")      # INV-019: `sistema` o la persona que publicó
    calificado_en = models.BigIntegerField(null=True, blank=True)
    fuera_de_plazo = models.BooleanField(default=False)
    origen_entrega = models.CharField(max_length=12, blank=True, default="")
    envio_tardio = models.CharField(max_length=20, blank=True, default="")
    respuestas_pendientes = models.JSONField(default=list)                        # lo recibido fuera de la gracia, a la espera del profesor
    decision_envio = models.JSONField(default=dict)
    anulado_por = models.CharField(max_length=64, blank=True, default="")
    motivo_anulacion = models.CharField(max_length=300, blank=True, default="")
    anulado_en = models.BigIntegerField(null=True, blank=True)
    iniciado_en = models.BigIntegerField(null=True, blank=True)
    entregado_en = models.BigIntegerField(null=True, blank=True)
    creado_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m10_intento_formal"
        constraints = [
            # INV-012: a lo sumo un intento por (alumno, asignación, número).
            models.UniqueConstraint(fields=["asignacion", "alumno_id", "numero"], name="ux_m10_intf_numero"),
            # Un solo intento VIVO por alumno y asignación.
            models.UniqueConstraint(fields=["asignacion", "alumno_id"], condition=Q(estado__in=cat.VIVOS), name="ux_m10_intf_vivo"),
            models.CheckConstraint(condition=Q(estado__in=cat.ESTADOS_INTENTO), name="ck_m10_intf_estado"),
            models.CheckConstraint(condition=Q(numero__gte=1) & Q(consumido_ms__gte=0), name="ck_m10_intf_numero_consumido"),
            # INV-018 en la base: `anulado` lo decide una PERSONA (jamás `sistema`), con motivo y fecha.
            models.CheckConstraint(
                condition=~Q(estado=cat.ANULADO)
                | (~Q(anulado_por="") & ~Q(anulado_por=cat.SISTEMA) & ~Q(motivo_anulacion="") & Q(anulado_en__isnull=False)),
                name="ck_m10_intf_anulado_humano"),
            models.CheckConstraint(condition=~Q(estado__in=cat.ENTREGADOS) | Q(entregado_en__isnull=False), name="ck_m10_intf_entrega_fechada"),
            # El reloj sólo corre en `en_curso` y `en_curso_fuera_de_plazo`.
            models.CheckConstraint(condition=Q(reloj_desde__isnull=True) | Q(estado__in=cat.CORRIENDO), name="ck_m10_intf_reloj_solo_corriendo"),
            # INV-019: toda calificación apunta a un intento, un evaluador y una regla.
            models.CheckConstraint(condition=~Q(estado=cat.CALIFICADO) | (Q(porcentaje__isnull=False) & ~Q(calificado_por="")),
                                   name="ck_m10_intf_calificado_con_evaluador"),
            models.CheckConstraint(condition=Q(envio_tardio__in=cat.ESTADOS_TARDIO), name="ck_m10_intf_envio_tardio"),
        ]
        indexes = [models.Index(fields=["asignacion", "estado"], name="ix_m10_intf_asignacion"),
                   models.Index(fields=["alumno_id", "estado"], name="ix_m10_intf_alumno"),
                   models.Index(fields=["dispositivo_id", "estado"], name="ix_m10_intf_dispositivo")]


class Incidente(models.Model):
    """CAP-066, FUN-117, BR-077. SÓLO INSERCIÓN: no hay ruta ni caso de uso que actualice o borre una fila. Un incidente alimenta el expediente
    de integridad y NUNCA modifica el estado del intento. `ref_cliente` es la clave de idempotencia que manda la tableta: reenviar su cola no
    duplica incidentes (INV-005)."""

    id = models.CharField(max_length=36, primary_key=True)
    intento = models.ForeignKey(Intento, on_delete=models.PROTECT, related_name="incidentes")
    tipo = models.CharField(max_length=32)
    severidad = models.CharField(max_length=12, choices=_lista(cat.SEVERIDADES))
    origen = models.CharField(max_length=8, choices=_lista(cat.ORIGENES_INCIDENTE))
    ocurrido_en = models.BigIntegerField(default=ahora_ms)                        # reloj del nodo
    reportado_en_tableta = models.BigIntegerField(null=True, blank=True)          # hora cruda del aparato (BR-062: dato adicional)
    dispositivo_id = models.CharField(max_length=36, blank=True, default="")
    detalle = models.JSONField(default=dict)
    resolucion = models.CharField(max_length=24, default=cat.RESOLUCION_REGISTRADO)
    ref_cliente = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "m10_incidente"
        constraints = [
            models.UniqueConstraint(fields=["intento", "ref_cliente"], condition=~Q(ref_cliente=""), name="ux_m10_incidente_cliente"),
            models.CheckConstraint(condition=Q(severidad__in=cat.SEVERIDADES), name="ck_m10_incidente_severidad"),
            models.CheckConstraint(condition=Q(origen__in=cat.ORIGENES_INCIDENTE), name="ck_m10_incidente_origen"),
        ]
        indexes = [models.Index(fields=["intento", "ocurrido_en"], name="ix_m10_incidente_intf")]


class EventoSalida(models.Model):
    """Transactional Outbox de MOD-010 (`evaluacion.*.v1`). Se escribe en la misma transacción que el hecho (DEC-007). Nunca lleva el contenido de
    una respuesta (BR-127). Cuando exista MOD-015 (m15_evento) las colas de todos los módulos se unifican allí."""

    agregado_tipo = models.CharField(max_length=32)
    agregado_id = models.CharField(max_length=64)
    tipo_evento = models.CharField(max_length=64)
    carga = models.JSONField(default=dict)
    creado_en = models.BigIntegerField(default=ahora_ms)
    publicado_en = models.BigIntegerField(null=True, blank=True)
    intentos = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "m10_evento_salida"
        indexes = [models.Index(fields=["publicado_en", "creado_en"], name="ix_m10_outbox")]

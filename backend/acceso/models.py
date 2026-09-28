"""
Esquema del módulo de acceso (tablas `m01_*`). Es el adaptador de persistencia:
Django exige que los modelos vivan aquí, pero ni el dominio ni los casos de uso
los importan. El mapeo a entidades está en `infraestructura/repositorios.py`.

Ninguna columna guarda PII en claro: `*_cifrado` es AES-256-GCM y `*_hmac` es el
índice ciego HMAC-SHA-256. Ningún secreto se guarda: `hash` es Argon2id.
"""
from __future__ import annotations

import time

from django.db import models
from django.db.models import F, Q


def ahora_ms() -> int:
    return int(time.time() * 1000)


class Organizacion(models.Model):
    id = models.CharField(max_length=36, primary_key=True)
    codigo = models.CharField(max_length=32, unique=True)
    nombre = models.CharField(max_length=200)
    pais = models.CharField(max_length=2)        # ISO 3166-1 alpha-2
    idioma = models.CharField(max_length=8)      # ISO 639-1
    locale = models.CharField(max_length=16)     # BCP 47
    zona_horaria = models.CharField(max_length=64, default="America/Bogota")
    creado_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m01_organizacion"


class PoliticaCredencial(models.Model):
    id = models.CharField(max_length=36, primary_key=True)
    organizacion = models.ForeignKey(Organizacion, on_delete=models.CASCADE, related_name="politicas")
    perfil = models.CharField(max_length=16)  # student / teacher / admin
    tipo_identificador = models.CharField(max_length=24)
    tipo_secreto = models.CharField(max_length=16)
    longitud_minima = models.PositiveSmallIntegerField(default=6)
    exige_mayuscula = models.BooleanField(default=False)
    exige_minuscula = models.BooleanField(default=False)
    exige_digito = models.BooleanField(default=False)
    exige_simbolo = models.BooleanField(default=False)
    intentos_maximos = models.PositiveSmallIntegerField(default=5)
    ventana_intentos_min = models.PositiveSmallIntegerField(default=15)
    bloqueo_minutos = models.PositiveSmallIntegerField(default=15)
    duracion_sesion_min = models.PositiveIntegerField(default=240)
    vigencia_credencial_dias = models.PositiveIntegerField(null=True, blank=True)
    permite_acceso_temporal = models.BooleanField(default=False)
    # BR-024: excepción del perfil para un nivel educativo (preescolar con avatar). Nulo = política general.
    nivel_clave = models.CharField(max_length=24, null=True, blank=True)
    # FUN-009: minutos sin actividad tras los que la sesión se cierra sola.
    inactividad_min = models.PositiveSmallIntegerField(default=20)
    creado_en = models.BigIntegerField(default=ahora_ms)
    actualizado_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m01_politica_credencial"
        constraints = [
            models.UniqueConstraint(fields=["organizacion", "perfil"], condition=Q(nivel_clave__isnull=True),
                                    name="uq_m01_politica_perfil"),
            models.UniqueConstraint(fields=["organizacion", "perfil", "nivel_clave"], condition=Q(nivel_clave__isnull=False),
                                    name="uq_m01_politica_perfil_nivel"),
            models.CheckConstraint(condition=Q(longitud_minima__gte=4) | Q(tipo_secreto="AVATAR"), name="ck_m01_politica_longitud"),
            models.CheckConstraint(
                condition=~Q(tipo_secreto="PIN") | (Q(longitud_minima__gte=4) & Q(longitud_minima__lte=8)),
                name="ck_m01_politica_pin_rango",
            ),
        ]


class Permiso(models.Model):
    codigo = models.CharField(max_length=64, primary_key=True)
    modulo = models.CharField(max_length=24)
    descripcion = models.CharField(max_length=200)
    alcance_maximo = models.CharField(max_length=20, default="ORGANIZATION")

    class Meta:
        db_table = "m01_permiso"


class Rol(models.Model):
    id = models.CharField(max_length=36, primary_key=True)
    organizacion = models.ForeignKey(Organizacion, on_delete=models.CASCADE, null=True, blank=True, related_name="roles")
    codigo = models.CharField(max_length=32)
    nombre = models.CharField(max_length=80)
    menu_principal = models.CharField(max_length=16)
    nivel = models.PositiveSmallIntegerField(default=1)
    es_sistema = models.BooleanField(default=False)
    creado_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m01_rol"
        constraints = [
            models.UniqueConstraint(fields=["organizacion", "codigo"], name="uq_m01_rol_codigo"),
            models.UniqueConstraint(fields=["codigo"], condition=Q(organizacion__isnull=True), name="uq_m01_rol_sistema"),
            models.CheckConstraint(condition=~Q(es_sistema=True) | Q(organizacion__isnull=True), name="ck_m01_rol_sistema_global"),
            models.CheckConstraint(condition=Q(nivel__gte=1) & Q(nivel__lte=3), name="ck_m01_rol_nivel"),
        ]


class RolPermiso(models.Model):
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, related_name="permisos")
    permiso = models.ForeignKey(Permiso, on_delete=models.PROTECT, db_column="permiso_codigo")
    alcance = models.CharField(max_length=20)

    class Meta:
        db_table = "m01_rol_permiso"
        constraints = [models.UniqueConstraint(fields=["rol", "permiso"], name="uq_m01_rol_permiso")]


class Usuario(models.Model):
    """La cuenta. Sin datos personales: esos van cifrados en Persona."""

    id = models.CharField(max_length=36, primary_key=True)
    organizacion = models.ForeignKey(Organizacion, on_delete=models.CASCADE, related_name="usuarios")
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name="usuarios")
    estado = models.CharField(max_length=16, default="ACTIVO")
    alias = models.CharField(max_length=64)
    idioma = models.CharField(max_length=8, default="es")
    creado_en = models.BigIntegerField(default=ahora_ms)
    actualizado_en = models.BigIntegerField(default=ahora_ms)
    creado_por = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    ultimo_acceso_en = models.BigIntegerField(null=True, blank=True)
    # Admisión nominal (JRN-007): cuenta creada por el profesor «por su nombre», pendiente de vincular.
    provisional = models.BooleanField(default=False)
    vinculado_a = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="provisionales")

    class Meta:
        db_table = "m01_usuario"
        indexes = [models.Index(fields=["organizacion", "estado"]), models.Index(fields=["rol"]),
                   models.Index(fields=["vinculado_a"])]


class Persona(models.Model):
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, primary_key=True, related_name="persona")
    nombres_cifrado = models.TextField()
    apellidos_cifrado = models.TextField(blank=True, default="")
    fecha_nacimiento_cifrado = models.TextField(null=True, blank=True)
    telefono_cifrado = models.TextField(null=True, blank=True)
    telefono_hmac = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    pais = models.CharField(max_length=2)
    actualizado_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m01_persona"


class IdentificadorUsuario(models.Model):
    id = models.CharField(max_length=36, primary_key=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="identificadores")
    tipo = models.CharField(max_length=24)
    valor_cifrado = models.TextField()
    valor_hmac = models.CharField(max_length=64)
    es_login = models.BooleanField(default=True)
    verificado_en = models.BigIntegerField(null=True, blank=True)
    creado_en = models.BigIntegerField(default=ahora_ms)
    # DEC-048: quién emitió el identificador (la institución o esta instalación). Vincula entre nodos.
    emisor = models.CharField(max_length=64, blank=True, default="")
    principal = models.BooleanField(default=False)
    # CV-05: nada se borra. Un identificador que deja de valer se retira con fecha.
    retirado_en = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "m01_identificador_usuario"
        constraints = [
            models.UniqueConstraint(fields=["tipo", "valor_hmac"], condition=Q(retirado_en__isnull=True),
                                    name="uq_m01_identificador_valor"),
            models.UniqueConstraint(fields=["usuario", "tipo"], condition=Q(retirado_en__isnull=True),
                                    name="uq_m01_identificador_tipo"),
            models.UniqueConstraint(fields=["usuario"], condition=Q(principal=True) & Q(retirado_en__isnull=True),
                                    name="uq_m01_identificador_principal"),
        ]
        indexes = [models.Index(fields=["valor_hmac"])]


class Credencial(models.Model):
    id = models.CharField(max_length=36, primary_key=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="credenciales")
    tipo = models.CharField(max_length=16)
    hash = models.CharField(max_length=255)  # Argon2id codificado (parámetros + sal + hash)
    activa = models.BooleanField(default=True)
    debe_cambiar = models.BooleanField(default=False)
    creado_en = models.BigIntegerField(default=ahora_ms)
    expira_en = models.BigIntegerField(null=True, blank=True)
    sustituida_en = models.BigIntegerField(null=True, blank=True)
    creado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        db_table = "m01_credencial"
        constraints = [
            models.UniqueConstraint(fields=["usuario"], condition=Q(activa=True), name="uq_m01_credencial_activa"),
            models.CheckConstraint(condition=Q(activa=True) | Q(sustituida_en__isnull=False), name="ck_m01_credencial_sustitucion"),
        ]


class UsuarioPermiso(models.Model):
    """Permisos adicionales con alcance y vigencia. No hay columnas de contexto: el contexto lo da la pertenencia."""

    id = models.CharField(max_length=36, primary_key=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="permisos_adicionales")
    permiso = models.ForeignKey(Permiso, on_delete=models.PROTECT, db_column="permiso_codigo")
    alcance = models.CharField(max_length=20)
    otorgado_por = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="+")
    motivo = models.CharField(max_length=200)
    vigente_desde = models.BigIntegerField(default=ahora_ms)
    vigente_hasta = models.BigIntegerField(null=True, blank=True)
    revocado_en = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "m01_usuario_permiso"
        constraints = [
            models.UniqueConstraint(fields=["usuario", "permiso"], condition=Q(revocado_en__isnull=True), name="uq_m01_usuario_permiso_vigente"),
            models.CheckConstraint(condition=Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gt=F("vigente_desde")), name="ck_m01_usuario_permiso_vigencia"),
        ]


class UsuarioRol(models.Model):
    """Asignación de rol con alcance concreto y vigencia (m01_persona_rol del Documento Maestro, BR-021).

    `Usuario.rol` sigue siendo el rol principal (el que se usa si la persona no elige otro al entrar).
    Aquí van todos los roles vigentes de la persona; en cada sesión trabaja con uno solo.
    """

    id = models.CharField(max_length=36, primary_key=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="asignaciones_rol")
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name="asignaciones")
    alcance_tipo = models.CharField(max_length=20, default="ORGANIZATION")  # ORGANIZATION / LEVEL / ASSIGNED_GROUPS
    alcance_id = models.CharField(max_length=36, null=True, blank=True)        # nivel_clave o grupo_id
    desde = models.BigIntegerField(default=ahora_ms)
    hasta = models.BigIntegerField(null=True, blank=True)
    asignado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    revocado_en = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "m01_usuario_rol"
        constraints = [
            models.UniqueConstraint(fields=["usuario", "rol", "alcance_tipo", "alcance_id"],
                                    condition=Q(revocado_en__isnull=True), name="uq_m01_usuario_rol_vigente"),
            models.CheckConstraint(condition=Q(hasta__isnull=True) | Q(hasta__gt=F("desde")), name="ck_m01_usuario_rol_vigencia"),
            models.CheckConstraint(condition=Q(alcance_tipo="ORGANIZATION") | Q(alcance_id__isnull=False),
                                   name="ck_m01_usuario_rol_alcance_id"),
        ]
        indexes = [models.Index(fields=["usuario", "revocado_en"])]


class Grupo(models.Model):
    id = models.CharField(max_length=36, primary_key=True)
    organizacion = models.ForeignKey(Organizacion, on_delete=models.CASCADE, related_name="grupos")
    codigo = models.CharField(max_length=32)
    nombre = models.CharField(max_length=120)
    periodo = models.CharField(max_length=16)
    # Nivel educativo del Documento Maestro: decide la interfaz y permite políticas de acceso por nivel.
    nivel_clave = models.CharField(max_length=24, null=True, blank=True)
    politica_credencial = models.ForeignKey(PoliticaCredencial, on_delete=models.SET_NULL, null=True, blank=True, related_name="grupos")
    activo = models.BooleanField(default=True)
    creado_en = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m01_grupo"
        constraints = [models.UniqueConstraint(fields=["organizacion", "codigo", "periodo"], name="uq_m01_grupo_codigo_periodo")]


class MiembroGrupo(models.Model):
    id = models.CharField(max_length=36, primary_key=True)
    grupo = models.ForeignKey(Grupo, on_delete=models.CASCADE, related_name="miembros")
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="membresias")
    papel = models.CharField(max_length=16)  # ESTUDIANTE / DOCENTE
    desde = models.BigIntegerField(default=ahora_ms)
    hasta = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "m01_miembro_grupo"
        constraints = [
            models.UniqueConstraint(fields=["grupo", "usuario", "papel"], name="uq_m01_miembro_papel"),
            models.CheckConstraint(condition=Q(hasta__isnull=True) | Q(hasta__gte=F("desde")), name="ck_m01_miembro_vigencia"),
        ]
        indexes = [models.Index(fields=["usuario", "papel"])]


# `Dispositivo` vive en MOD-009 (`device_manager`, m09_dispositivo) desde el 2026-09-28. Este módulo lo
# referencia por FK y lo consulta en el login por su puerto `RepositorioDispositivos`, nunca por su ORM.


class Sesion(models.Model):
    id = models.CharField(max_length=36, primary_key=True)  # jti del JWT
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="sesiones")
    dispositivo = models.ForeignKey("device_manager.Dispositivo", on_delete=models.SET_NULL, null=True, blank=True, related_name="sesiones")
    clase = models.CharField(max_length=16, default="NORMAL")
    emitida_en = models.BigIntegerField(default=ahora_ms)
    expira_en = models.BigIntegerField()
    ultimo_uso_en = models.BigIntegerField(null=True, blank=True)
    revocada_en = models.BigIntegerField(null=True, blank=True)
    motivo_revocacion = models.CharField(max_length=64, null=True, blank=True)
    evaluacion_ref = models.CharField(max_length=200, null=True, blank=True)
    # BR-021: el rol EFECTIVO de la sesión, elegido al entrar. Nulo en filas anteriores = rol principal del usuario.
    rol = models.ForeignKey(Rol, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        db_table = "m01_sesion"
        constraints = [
            models.CheckConstraint(condition=Q(expira_en__gt=F("emitida_en")), name="ck_m01_sesion_expira_despues"),
            models.CheckConstraint(condition=Q(revocada_en__isnull=True) | Q(motivo_revocacion__isnull=False), name="ck_m01_sesion_revocacion_motivada"),
        ]
        indexes = [models.Index(fields=["usuario", "revocada_en", "expira_en"])]


class AutorizacionTemporal(models.Model):
    id = models.CharField(max_length=36, primary_key=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="autorizaciones_temporales")
    otorgada_por = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="+")
    tipo = models.CharField(max_length=16)  # DISPOSITIVO / CODIGO
    dispositivo = models.ForeignKey("device_manager.Dispositivo", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    secreto_hash = models.CharField(max_length=255)
    evaluacion_ref = models.CharField(max_length=200, null=True, blank=True)
    creada_en = models.BigIntegerField(default=ahora_ms)
    expira_en = models.BigIntegerField()
    usada_en = models.BigIntegerField(null=True, blank=True)
    revocada_en = models.BigIntegerField(null=True, blank=True)
    sesion = models.OneToOneField(Sesion, on_delete=models.SET_NULL, null=True, blank=True, related_name="autorizacion_origen")
    motivo = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        db_table = "m01_autorizacion_temporal"
        constraints = [
            models.CheckConstraint(condition=~Q(tipo="DISPOSITIVO") | Q(dispositivo__isnull=False), name="ck_m01_autorizacion_dispositivo"),
            models.CheckConstraint(condition=Q(usada_en__isnull=True) | Q(sesion__isnull=False), name="ck_m01_autorizacion_uso_con_sesion"),
        ]
        indexes = [models.Index(fields=["usuario", "expira_en"])]


class IntentoAcceso(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, null=True, blank=True, related_name="intentos_acceso")
    identificador_hmac = models.CharField(max_length=64, blank=True, default="")
    dispositivo = models.ForeignKey("device_manager.Dispositivo", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    resultado = models.CharField(max_length=24)
    motivo = models.CharField(max_length=64, blank=True, default="")
    autorizacion = models.ForeignKey(AutorizacionTemporal, on_delete=models.SET_NULL, null=True, blank=True, related_name="intentos")
    momento = models.BigIntegerField(default=ahora_ms)

    class Meta:
        db_table = "m01_intento_acceso"
        indexes = [models.Index(fields=["usuario", "-momento"]), models.Index(fields=["autorizacion"])]


class EventoSalida(models.Model):
    """Transactional Outbox: se escribe en la misma transacción que el cambio."""

    agregado_tipo = models.CharField(max_length=32)
    agregado_id = models.CharField(max_length=36)
    tipo_evento = models.CharField(max_length=64)
    carga = models.JSONField(default=dict)
    creado_en = models.BigIntegerField(default=ahora_ms)
    publicado_en = models.BigIntegerField(null=True, blank=True)
    intentos = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "m01_evento_salida"
        indexes = [models.Index(fields=["publicado_en", "creado_en"])]

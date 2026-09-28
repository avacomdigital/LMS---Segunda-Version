# Mudanza de `Dispositivo` desde `acceso` (m01_dispositivo) a MOD-009 (m09_dispositivo), 2026-09-28.
#
# 1. Sólo en el estado de las migraciones: este módulo pasa a ser el dueño del modelo tal como existía
#    en `acceso` (misma tabla, mismas columnas). La tabla ya existe con datos: no se crea ni se copia.
# 2. Sobre la tabla real: renombrarla, renombrar las columnas al vocabulario del modelo de datos
#    (identificador_hw, ultimo_latido_en), ampliar `nombre`, y añadir plataforma, version_app y bloqueado.
# 3. Las tablas nuevas del módulo: la sesión de alumno en el dispositivo y la cola de salida.
#
# `acceso/0005` (que depende de esta) repunta sus tres FK a `device_manager.Dispositivo` y borra el
# modelo de su estado. Mientras tanto la FK a la organización lleva un `related_name` provisional para
# no chocar con el del modelo que todavía vive en el estado de `acceso`; `0002` lo deja definitivo.

import django.db.models.deletion
from django.db import migrations, models

import device_manager.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("acceso", "0004_datos_mod001"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Dispositivo",
                    fields=[
                        ("id", models.CharField(max_length=36, primary_key=True, serialize=False)),
                        ("identificador", models.CharField(max_length=128)),
                        ("nombre", models.CharField(max_length=64)),
                        ("tipo", models.CharField(default="TABLETA", max_length=16)),
                        ("activo", models.BooleanField(default=True)),
                        ("registrado_en", models.BigIntegerField(default=device_manager.models.ahora_ms)),
                        ("ultimo_visto_en", models.BigIntegerField(default=device_manager.models.ahora_ms)),
                        ("organizacion", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                           related_name="dispositivos_m09", to="acceso.organizacion")),
                    ],
                    options={"db_table": "m01_dispositivo"},
                ),
                migrations.AddConstraint(
                    model_name="dispositivo",
                    constraint=models.UniqueConstraint(fields=("organizacion", "identificador"), name="uq_m01_dispositivo_identificador"),
                ),
            ],
            database_operations=[],
        ),
        # --- de aquí en adelante, operaciones reales sobre la tabla que ya existe ---
        migrations.AlterModelTable(name="dispositivo", table="m09_dispositivo"),
        migrations.RemoveConstraint(model_name="dispositivo", name="uq_m01_dispositivo_identificador"),
        migrations.RenameField(model_name="dispositivo", old_name="identificador", new_name="identificador_hw"),
        migrations.RenameField(model_name="dispositivo", old_name="ultimo_visto_en", new_name="ultimo_latido_en"),
        migrations.AlterField(model_name="dispositivo", name="nombre", field=models.CharField(max_length=120)),
        migrations.AddField(model_name="dispositivo", name="plataforma", field=models.CharField(blank=True, default="", max_length=16)),
        migrations.AddField(model_name="dispositivo", name="version_app", field=models.CharField(blank=True, default="", max_length=32)),
        migrations.AddField(model_name="dispositivo", name="bloqueado", field=models.BooleanField(default=False)),
        migrations.AddConstraint(
            model_name="dispositivo",
            constraint=models.UniqueConstraint(fields=("organizacion", "identificador_hw"), name="uq_m09_dispositivo_identificador"),
        ),
        migrations.CreateModel(
            name="DimSesionAlumno",
            fields=[
                ("id", models.CharField(max_length=36, primary_key=True, serialize=False)),
                ("alumno_id", models.CharField(max_length=64)),
                ("iniciada_en", models.BigIntegerField(default=device_manager.models.ahora_ms)),
                ("finalizada_en", models.BigIntegerField(blank=True, null=True)),
                ("motivo_cierre", models.CharField(blank=True, default="", max_length=16)),
                ("dispositivo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sesiones_alumno",
                                                  to="device_manager.dispositivo")),
            ],
            options={
                "db_table": "m09_dim_sesion_alumno",
                "indexes": [
                    models.Index(fields=["dispositivo", "finalizada_en"], name="ix_m09_dsa_dispositivo"),
                    models.Index(fields=["alumno_id", "iniciada_en"], name="ix_m09_dsa_alumno"),
                ],
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(("finalizada_en__isnull", True)), fields=("alumno_id",), name="ux_m09_dsa_alumno_abierta"),
                    models.UniqueConstraint(condition=models.Q(("finalizada_en__isnull", True)), fields=("dispositivo",), name="ux_m09_dsa_dispositivo_abierta"),
                    models.CheckConstraint(condition=models.Q(("finalizada_en__isnull", True), ("finalizada_en__gte", models.F("iniciada_en")), _connector="OR"), name="ck_m09_dsa_vigencia"),
                    models.CheckConstraint(condition=models.Q(("finalizada_en__isnull", True), models.Q(("motivo_cierre", ""), _negated=True), _connector="OR"), name="ck_m09_dsa_cierre_motivado"),
                ],
            },
        ),
        migrations.CreateModel(
            name="EventoSalida",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("agregado_tipo", models.CharField(max_length=32)),
                ("agregado_id", models.CharField(max_length=36)),
                ("tipo_evento", models.CharField(max_length=64)),
                ("carga", models.JSONField(default=dict)),
                ("creado_en", models.BigIntegerField(default=device_manager.models.ahora_ms)),
                ("publicado_en", models.BigIntegerField(blank=True, null=True)),
                ("intentos", models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                "db_table": "m09_evento_salida",
                "indexes": [models.Index(fields=["publicado_en", "creado_en"], name="ix_m09_outbox")],
            },
        ),
    ]

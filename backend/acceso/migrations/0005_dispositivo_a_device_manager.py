# `Dispositivo` pasa a MOD-009 (`device_manager`, tabla m09_dispositivo), 2026-09-28. Aquí sólo cambia el
# estado: las tres FK de este módulo apuntan al modelo nuevo (la columna `dispositivo_id` y la tabla
# renombrada por `device_manager/0001` ya son coherentes en la base) y el modelo sale del estado de `acceso`.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("acceso", "0004_datos_mod001"),
        ("device_manager", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="sesion",
                    name="dispositivo",
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                            related_name="sesiones", to="device_manager.dispositivo"),
                ),
                migrations.AlterField(
                    model_name="autorizaciontemporal",
                    name="dispositivo",
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                            related_name="+", to="device_manager.dispositivo"),
                ),
                migrations.AlterField(
                    model_name="intentoacceso",
                    name="dispositivo",
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                            related_name="+", to="device_manager.dispositivo"),
                ),
                migrations.DeleteModel(name="Dispositivo"),
            ],
            database_operations=[],
        ),
    ]

# Cierra la mudanza: `acceso/0005` ya borró su `Dispositivo` del estado, así que la FK a la organización
# recupera el `related_name` definitivo. Sólo cambia el estado (la columna es la misma).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("device_manager", "0001_initial"),
        ("acceso", "0005_dispositivo_a_device_manager"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="dispositivo",
                    name="organizacion",
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dispositivos", to="acceso.organizacion"),
                ),
            ],
            database_operations=[],
        ),
    ]

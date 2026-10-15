"""
`m11_config_nivel.modo_desde`: desde cuándo rige el MODO de un nivel (cambia sólo al alternar el modo, no al cambiar la escala). Antes el consumidor comparaba los
eventos de MOD-010 con `actualizada_en`, que también se movía al cambiar sólo la escala, y descartaba en silencio lo que MOD-010 había calificado y el libro aún no leía.

`m11_marca_consumidor.secuencia_fallida` y `fallos_seguidos`: el evento que no se pudo aplicar retiene la marca unos ciclos antes de dejarse atrás (con un asiento en
la bitácora), en lugar de saltarse sin dejar rastro.
"""
import gradebook.models
from django.db import migrations, models


def modo_desde_de_lo_que_habia(apps, schema_editor):
    """Los niveles que ya existían conservan su comportamiento: su modo rige desde la última vez que se tocó su fila."""
    ConfigNivel = apps.get_model("gradebook", "ConfigNivel")
    for fila in ConfigNivel.objects.all():
        fila.modo_desde = fila.actualizada_en
        fila.save(update_fields=["modo_desde"])


class Migration(migrations.Migration):

    dependencies = [
        ('gradebook', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='confignivel',
            name='modo_desde',
            field=models.BigIntegerField(default=gradebook.models.ahora_ms),
        ),
        migrations.RunPython(modo_desde_de_lo_que_habia, migrations.RunPython.noop),
        migrations.AddField(
            model_name='marcaconsumidor',
            name='fallos_seguidos',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='marcaconsumidor',
            name='secuencia_fallida',
            field=models.BigIntegerField(default=0),
        ),
    ]

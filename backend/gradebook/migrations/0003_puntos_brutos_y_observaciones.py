"""
`m11_calificacion.puntos` y `puntos_maximos`: los puntos BRUTOS que MOD-010 contó al calificar el intento (14 de 18). Hasta ahora el libro sólo guardaba el porcentaje
normalizado (0–100) y la nota presentada; el profesor pidió ver los tres a la vez: puntos, porcentaje y nota en el sistema configurado. Las calificaciones que ya existían
se completan leyendo el intento del que salieron (si MOD-010 todavía lo conserva con sus puntos).

`m11_observacion`: lo que el profesor recomienda a un alumno en un grupo y un periodo (la cuarta pregunta del boletín, «¿qué debe mejorar?»), con frases de un catálogo
cerrado que se tocan sin teclado y un texto opcional.
"""
from decimal import Decimal

import gradebook.models
from django.db import migrations, models
from django.db.models import F, Q


def puntos_de_lo_que_habia(apps, schema_editor):
    """Cada calificación toma los puntos del intento de MOD-010 del que salió: los que ya contó al calificar. Un intento sin puntos (o que ya no está) deja los dos en nulo."""
    Calificacion = apps.get_model("gradebook", "Calificacion")
    Intento = apps.get_model("evaluacion", "Intento")
    for fila in Calificacion.objects.all().only("id", "intento_id"):
        intento = Intento.objects.filter(pk=fila.intento_id).only("puntaje", "puntaje_maximo").first()
        if intento is None or intento.puntaje is None or intento.puntaje_maximo is None or intento.puntaje_maximo <= 0 or intento.puntaje < 0 or intento.puntaje > intento.puntaje_maximo:
            continue
        fila.puntos = Decimal(str(round(float(intento.puntaje), 2)))
        fila.puntos_maximos = Decimal(str(round(float(intento.puntaje_maximo), 2)))
        fila.save(update_fields=["puntos", "puntos_maximos"])


class Migration(migrations.Migration):

    dependencies = [
        ("gradebook", "0002_modo_desde_y_fallos_del_consumidor"),
        ("evaluacion", "0002_publicacion_de_resultados"),
    ]

    operations = [
        migrations.AddField(
            model_name="calificacion",
            name="puntos",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="calificacion",
            name="puntos_maximos",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddConstraint(
            model_name="calificacion",
            constraint=models.CheckConstraint(
                condition=(Q(puntos__isnull=True) & Q(puntos_maximos__isnull=True))
                | (Q(puntos__isnull=False) & Q(puntos_maximos__isnull=False) & Q(puntos__gte=0) & Q(puntos__lte=F("puntos_maximos"))),
                name="ck_m11_calificacion_puntos"),
        ),
        migrations.RunPython(puntos_de_lo_que_habia, migrations.RunPython.noop),
        migrations.CreateModel(
            name="Observacion",
            fields=[
                ("id", models.CharField(max_length=36, primary_key=True, serialize=False)),
                ("alumno_id", models.CharField(max_length=64)),
                ("grupo_id", models.CharField(max_length=36)),
                ("periodo", models.CharField(blank=True, default="", max_length=16)),
                ("curso_ref", models.CharField(blank=True, default="", max_length=200)),
                ("recomendaciones", models.JSONField(default=list)),
                ("texto", models.CharField(blank=True, default="", max_length=600)),
                ("version", models.PositiveIntegerField(default=1)),
                ("actualizada_en", models.BigIntegerField(default=gradebook.models.ahora_ms)),
                ("actualizada_por", models.CharField(max_length=64)),
            ],
            options={
                "db_table": "m11_observacion",
                "indexes": [models.Index(fields=["grupo_id", "periodo"], name="ix_m11_observacion_grupo")],
                "constraints": [
                    models.UniqueConstraint(fields=("alumno_id", "grupo_id", "periodo", "curso_ref"), name="ux_m11_observacion"),
                    models.CheckConstraint(condition=~Q(actualizada_por=""), name="ck_m11_observacion_actor"),
                    models.CheckConstraint(condition=Q(version__gte=1), name="ck_m11_observacion_version"),
                ],
            },
        ),
    ]

"""
El boletín académico individual (2026-10-19): en `m13_config` la plantilla del boletín (`auto` = por el país de la política del libro y el nivel del grupo; `co`, `mx` o
`generica` si la administración la fija), los nombres de los periodos de la institución (los decide su propio sistema de evaluación) y la leyenda que aclara que el boletín
no es un documento oficial.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="config",
            name="plantilla_boletin",
            field=models.CharField(default="auto", max_length=12),
        ),
        migrations.AddField(
            model_name="config",
            name="periodos_boletin",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="config",
            name="leyenda_boletin",
            field=models.CharField(blank=True, default="", max_length=400),
        ),
        migrations.AddConstraint(
            model_name="config",
            constraint=models.CheckConstraint(condition=models.Q(plantilla_boletin__in=("auto", "co", "mx", "generica")), name="ck_m13_config_plantilla_boletin"),
        ),
        # El tipo `boletin` entra al catálogo de reportes (sólo cambia la lista de opciones, no la columna).
        migrations.AlterField(
            model_name="exportacion",
            name="tipo",
            field=models.CharField(choices=[("clase", "clase"), ("alumno", "alumno"), ("grupo", "grupo"), ("uso", "uso"), ("boletin", "boletin")], max_length=16),
        ),
        migrations.AlterField(
            model_name="reciente",
            name="tipo",
            field=models.CharField(choices=[("clase", "clase"), ("alumno", "alumno"), ("grupo", "grupo"), ("uso", "uso"), ("boletin", "boletin")], max_length=16),
        ),
        migrations.AlterField(
            model_name="exportacion",
            name="formato",
            field=models.CharField(choices=[("xlsx", "xlsx"), ("csv", "csv"), ("zip", "zip")], max_length=8),
        ),
    ]

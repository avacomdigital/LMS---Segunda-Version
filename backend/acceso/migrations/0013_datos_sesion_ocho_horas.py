"""
Datos: la sesión dura una jornada escolar completa (480 min) en las instalaciones que ya existen. Idempotente.

0012 subió el reglamento de fábrica a 240 min (cuatro horas). La prueba de 35 tabletas (2026-10-08) pide que ni AVACOM Student ni OPS pierdan la sesión
durante toda una jornada de pruebas, así que el valor de fábrica pasa a 480 min. Sólo se mueve lo que está EXACTAMENTE en el valor de fábrica anterior (240):
si la administración fijó otra cosa desde «Seguridad del aula» —más corta o más larga— se respeta tal cual.
"""
from django.db import migrations

ANTES = 240
AHORA = 480


def alargar(apps, schema_editor):
    Politica = apps.get_model("acceso", "PoliticaCredencial")
    Politica.objects.filter(duracion_sesion_min=ANTES).update(duracion_sesion_min=AHORA)
    Politica.objects.filter(inactividad_min=ANTES).update(inactividad_min=AHORA)


def acortar(apps, schema_editor):
    Politica = apps.get_model("acceso", "PoliticaCredencial")
    Politica.objects.filter(duracion_sesion_min=AHORA).update(duracion_sesion_min=ANTES)
    Politica.objects.filter(inactividad_min=AHORA).update(inactividad_min=ANTES)


class Migration(migrations.Migration):

    dependencies = [
        ("acceso", "0012_datos_sesion_sin_corte_por_inactividad"),
    ]

    operations = [
        migrations.RunPython(alargar, acortar),
    ]

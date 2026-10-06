"""
Datos: la sesión dura una jornada de clase completa también en las instalaciones que ya existen. Idempotente.

El reglamento de fábrica cerraba la sesión a los 20 minutos sin usar (30 para el alumno) aunque el pase valiera 4 horas. Quien dicta clase
proyecta una lámina o un video sin tocar la API durante más tiempo que eso y se encontraba con la sesión denegada a media clase. La
inactividad de fábrica pasa a 240 min (la duración del pase) en todos los perfiles, niveles y grupos.

Sólo se sube, nunca se baja: si la institución ya fijó algo mayor, se respeta. Una inactividad menor que 240 se da por la de fábrica
(20 o 30) o por un valor que la administración puede volver a ajustar desde «Seguridad del aula».
"""
from django.db import migrations

MINUTOS = 240


def alargar(apps, schema_editor):
    Politica = apps.get_model("acceso", "PoliticaCredencial")
    Politica.objects.filter(duracion_sesion_min__lt=MINUTOS).update(duracion_sesion_min=MINUTOS)
    Politica.objects.filter(inactividad_min__lt=MINUTOS).update(inactividad_min=MINUTOS)


class Migration(migrations.Migration):

    dependencies = [
        ("acceso", "0011_datos_pin_maestro_y_alumnos"),
    ]

    operations = [
        migrations.RunPython(alargar, migrations.RunPython.noop),
    ]

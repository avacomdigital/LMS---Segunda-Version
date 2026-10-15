"""
Quita `assessment.review` (puntuar a mano y publicar una revisión, CAP-062) al rol ADMIN en las instalaciones que ya existen: puntuar es calificar, y el Maestro de MOD-011 le niega
a la administración calificar directamente. El profesor conserva el permiso sobre sus grupos. Las instalaciones nuevas ya lo reciben así de las plantillas
(`PERMISOS_DE_EVALUACION_SOLO_DEL_DOCENTE`). Sólo borra la fila (ADMIN, `assessment.review`) del rol del SISTEMA; la inversa la devuelve con alcance de organización. Idempotente.
"""
from django.db import migrations

CODIGO = "assessment.review"


def quitar(apps, schema_editor):
    Rol = apps.get_model("acceso", "Rol")
    RolPermiso = apps.get_model("acceso", "RolPermiso")
    rol = Rol.objects.filter(codigo="ADMIN", organizacion__isnull=True).first()
    if rol is not None:
        RolPermiso.objects.filter(rol=rol, permiso_id=CODIGO).delete()


def devolver(apps, schema_editor):
    Rol = apps.get_model("acceso", "Rol")
    RolPermiso = apps.get_model("acceso", "RolPermiso")
    Permiso = apps.get_model("acceso", "Permiso")
    rol = Rol.objects.filter(codigo="ADMIN", organizacion__isnull=True).first()
    if rol is not None and Permiso.objects.filter(pk=CODIGO).exists():
        RolPermiso.objects.update_or_create(rol=rol, permiso_id=CODIGO, defaults={"alcance": "ORGANIZATION"})


class Migration(migrations.Migration):

    dependencies = [
        ("acceso", "0015_permisos_busqueda"),
    ]

    operations = [
        migrations.RunPython(quitar, devolver),
    ]

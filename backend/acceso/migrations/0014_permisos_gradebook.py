"""
Siembra los seis permisos `grades.*` de MOD-011 · Gradebook en las instalaciones que ya existen: los cuatro de calificar y publicar (`grades.modify`,
`grades.reopen`, `grades.rubric.apply` y la extensión técnica propuesta `grades.publish`) van al profesor sobre sus grupos; `grades.mode.set` y `grades.export` van
a la administración (toda la organización). El administrador NO recibe los de calificar: el Maestro le niega calificar directamente. El técnico y reportes no reciben
ninguno (el técnico no accede a datos académicos; reportes sólo lee con `results.read`). Las instalaciones nuevas los reciben de las plantillas. Idempotente.
"""
from django.db import migrations

from acceso.dominio import plantillas

CODIGOS = tuple(c for c, *_ in plantillas.PERMISOS if c.startswith("grades."))


def sembrar(apps, schema_editor):
    Permiso = apps.get_model("acceso", "Permiso")
    Rol = apps.get_model("acceso", "Rol")
    RolPermiso = apps.get_model("acceso", "RolPermiso")
    for codigo in CODIGOS:
        _, modulo, descripcion, maximo, _sensible = plantillas.PERMISOS_POR_CODIGO[codigo]
        Permiso.objects.update_or_create(codigo=codigo, defaults={
            "modulo": modulo, "descripcion": descripcion, "alcance_maximo": maximo.value})
    for rol_codigo in ("TEACHER", "ADMIN"):
        rol = Rol.objects.filter(codigo=rol_codigo, organizacion__isnull=True).first()
        if rol is None:
            continue
        concedidos = plantillas.ROLES_SISTEMA[rol_codigo][3]
        for codigo in CODIGOS:
            if codigo in concedidos:
                RolPermiso.objects.update_or_create(rol=rol, permiso_id=codigo, defaults={"alcance": concedidos[codigo].value})


class Migration(migrations.Migration):

    dependencies = [
        ("acceso", "0013_datos_sesion_ocho_horas"),
    ]

    operations = [
        migrations.RunPython(sembrar, migrations.RunPython.noop),
    ]

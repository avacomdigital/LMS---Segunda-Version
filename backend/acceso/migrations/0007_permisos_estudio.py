"""
Siembra los ocho permisos `study.*` de MOD-008 · Modo Estudio en las instalaciones que ya existen: los seis del alumno (sobre lo
suyo) van sólo al rol STUDENT, y los dos del proyecto (`study.assignment.create` y `study.assignment.review`) van al profesor
(sobre sus grupos) y a la administración (toda la organización). El administrador NO recibe los del alumno: el Maestro dice que
«no accede al modo de estudio del alumno». Las instalaciones nuevas los reciben de las plantillas.
Idempotente: se puede volver a ejecutar sin duplicar nada.
"""
from django.db import migrations

from acceso.dominio import plantillas

CODIGOS = tuple(c for c, *_ in plantillas.PERMISOS if c.startswith("study."))


def sembrar(apps, schema_editor):
    Permiso = apps.get_model("acceso", "Permiso")
    Rol = apps.get_model("acceso", "Rol")
    RolPermiso = apps.get_model("acceso", "RolPermiso")
    for codigo in CODIGOS:
        _, modulo, descripcion, maximo, _sensible = plantillas.PERMISOS_POR_CODIGO[codigo]
        Permiso.objects.update_or_create(codigo=codigo, defaults={
            "modulo": modulo, "descripcion": descripcion, "alcance_maximo": maximo.value})
    for rol_codigo in ("STUDENT", "TEACHER", "ADMIN"):
        rol = Rol.objects.filter(codigo=rol_codigo, organizacion__isnull=True).first()
        if rol is None:
            continue
        concedidos = plantillas.ROLES_SISTEMA[rol_codigo][3]
        for codigo in CODIGOS:
            if codigo in concedidos:
                RolPermiso.objects.update_or_create(rol=rol, permiso_id=codigo, defaults={"alcance": concedidos[codigo].value})


class Migration(migrations.Migration):

    dependencies = [
        ("acceso", "0006_permisos_aula"),
    ]

    operations = [
        migrations.RunPython(sembrar, migrations.RunPython.noop),
    ]

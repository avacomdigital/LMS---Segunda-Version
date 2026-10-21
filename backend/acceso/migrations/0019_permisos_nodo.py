"""
Siembra los permisos `node.*` de MOD-015 · Node Platform en las instalaciones que ya existen: la administración recibe los tres (`node.queue.replay`, y las extensiones técnicas
`node.queue.read` y `node.health.read`) y el técnico recibe `node.queue.read` y `node.health.read` (NO reprocesa: sólo por escalada temporal). El profesor, Reportes y el alumno no
reciben ninguno. Las instalaciones nuevas los reciben de las plantillas. Idempotente.
"""
from django.db import migrations

from acceso.dominio import plantillas

CODIGOS = tuple(c for c, *_ in plantillas.PERMISOS if c.startswith("node."))


def sembrar(apps, schema_editor):
    Permiso = apps.get_model("acceso", "Permiso")
    Rol = apps.get_model("acceso", "Rol")
    RolPermiso = apps.get_model("acceso", "RolPermiso")
    for codigo in CODIGOS:
        _, modulo, descripcion, maximo, _sensible = plantillas.PERMISOS_POR_CODIGO[codigo]
        Permiso.objects.update_or_create(codigo=codigo, defaults={
            "modulo": modulo, "descripcion": descripcion, "alcance_maximo": maximo.value})
    for rol_codigo in ("ADMIN", "TECHNICIAN"):
        rol = Rol.objects.filter(codigo=rol_codigo, organizacion__isnull=True).first()
        if rol is None:
            continue
        concedidos = plantillas.ROLES_SISTEMA[rol_codigo][3]
        for codigo in CODIGOS:
            if codigo in concedidos:
                RolPermiso.objects.update_or_create(rol=rol, permiso_id=codigo, defaults={"alcance": concedidos[codigo].value})


class Migration(migrations.Migration):

    dependencies = [
        ("acceso", "0018_permisos_licencia"),
    ]

    operations = [
        migrations.RunPython(sembrar, migrations.RunPython.noop),
    ]

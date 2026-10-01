"""
Siembra los permisos de MOD-019 · Audit en las instalaciones que ya existen: `audit.export` (exportar un tramo firmado)
y `diagnostics.read` (leer los logs de diagnóstico sin datos personales), y actualiza la descripción de `audit.read`.
El administrador recibe los tres; el técnico sólo `diagnostics.read` (BR-097: nunca la bitácora). Las instalaciones nuevas
los reciben de las plantillas. Idempotente.
"""
from django.db import migrations

from acceso.dominio import plantillas

CODIGOS = ("audit.read", "audit.export", "diagnostics.read")


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
        ("acceso", "0007_permisos_estudio"),
    ]

    operations = [
        migrations.RunPython(sembrar, migrations.RunPython.noop),
    ]

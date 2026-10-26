"""
Siembra los permisos `backup.*` de MOD-016 · Backup & Recovery en las instalaciones que ya existen. Respaldar y restaurar son SÓLO del personal de AVACOM (D-1): el técnico recibe los siete
(`backup.read`, `backup.run`, `backup.schedule`, `backup.verify`, `backup.export`, `backup.restore` y `backup.restore.module`) y la administración de la institución SÓLO `backup.read`
(estado, último respaldo y constancias). El profesor, Reportes y el alumno no reciben ninguno. Las instalaciones nuevas los reciben de las plantillas. Idempotente.

Si una instalación de pruebas ya le había dado a ADMIN algún `backup.*` de escritura, esta migración se lo retira.
"""
from django.db import migrations

from acceso.dominio import plantillas

CODIGOS = tuple(c for c, *_ in plantillas.PERMISOS if c.startswith("backup."))


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
            else:
                RolPermiso.objects.filter(rol=rol, permiso_id=codigo).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("acceso", "0020_permisos_actualizacion"),
    ]

    operations = [
        migrations.RunPython(sembrar, migrations.RunPython.noop),
    ]

"""
Siembra los dieciséis permisos `assessment.*` de MOD-010 · Evaluation & Delivery Engine en las instalaciones que ya existen: los tres del intento del
alumno (abrir, responder, entregar) van sólo al rol STUDENT y sobre lo suyo; los once del profesor (asignar, nivel, plazos, admitir tabletas, reactivar,
anular, revisar, ver y liberar resultados) van al profesor (sobre sus grupos) y a la administración (toda la organización). El administrador NO recibe los
del intento del alumno: el Maestro le niega «el intento del alumno». `assessment.create` y `assessment.item.create` quedan en el catálogo para el
administrador sin función en el LMS (crear una evaluación es de AVACOM Biblioteca). Las instalaciones nuevas los reciben de las plantillas.
Idempotente: se puede volver a ejecutar sin duplicar nada.
"""
from django.db import migrations

from acceso.dominio import plantillas

CODIGOS = tuple(c for c, *_ in plantillas.PERMISOS if c.startswith("assessment."))


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
        ("acceso", "0008_permisos_auditoria"),
    ]

    operations = [
        migrations.RunPython(sembrar, migrations.RunPython.noop),
    ]

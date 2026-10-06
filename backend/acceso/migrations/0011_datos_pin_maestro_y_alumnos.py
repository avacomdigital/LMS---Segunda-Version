"""
Datos de la migración 0010 (PIN maestro, origen de la cuenta, autoalta del alumno) en las instalaciones que ya existen. Idempotente.

  · Siembra `identity.master_pin.manage` y se lo concede al administrador (RB-08). El técnico NO lo recibe: sólo fija el primer PIN en la
    instalación, que es una ruta sin sesión.
  · Concede al profesor `identity.group.manage` acotado a sus grupos (RB-28): el que crea un grupo queda como docente de él.
  · Pone `origen` a las cuentas que ya existen (RB-03): `INSTALACION` si nadie las creó, `PROFESOR` si las creó un profesor,
    `IMPORTACION` si las creó la administración (padrón o archivo). `confirmado_en` queda nulo sólo para lo nuevo: las cuentas anteriores se
    dan por confirmadas en el momento en que se creó.
  · El profesor puede crear su propio usuario con el PIN maestro (`autoregistro` encendido en su política, RN-20 y RN-37).
  · La política del alumno pasa a lo que piden los requisitos: PIN de 4 dígitos (RN-31, D-A3), autoregistro encendido (RN-37) y castigo a la
    tableta, no a la cuenta (RN-33). Sólo se toca la fila si el reglamento seguía siendo el de fábrica (PIN de 6): si la institución ya lo
    ajustó a su gusto, se respeta.
"""
from django.db import migrations

CODIGO = "identity.master_pin.manage"
DESCRIPCION = "Ver el estado del PIN maestro y cambiarlo (RN-06, RB-08); el técnico lo fija en la instalación"


def sembrar(apps, schema_editor):
    Permiso = apps.get_model("acceso", "Permiso")
    Rol = apps.get_model("acceso", "Rol")
    RolPermiso = apps.get_model("acceso", "RolPermiso")
    Usuario = apps.get_model("acceso", "Usuario")
    Politica = apps.get_model("acceso", "PoliticaCredencial")

    Permiso.objects.update_or_create(codigo=CODIGO, defaults={"modulo": "acceso", "descripcion": DESCRIPCION, "alcance_maximo": "ORGANIZATION"})
    admin = Rol.objects.filter(codigo="ADMIN", organizacion__isnull=True).first()
    if admin is not None:
        RolPermiso.objects.update_or_create(rol=admin, permiso_id=CODIGO, defaults={"alcance": "ORGANIZATION"})
    profesor = Rol.objects.filter(codigo="TEACHER", organizacion__isnull=True).first()
    if profesor is not None and not RolPermiso.objects.filter(rol=profesor, permiso_id="identity.group.manage").exists():
        RolPermiso.objects.create(rol=profesor, permiso_id="identity.group.manage", alcance="ASSIGNED_GROUPS")

    for usuario in Usuario.objects.filter(origen="INSTALACION").select_related("creado_por__rol"):
        if usuario.creado_por_id is None:
            origen = "INSTALACION"
        elif usuario.creado_por.rol.menu_principal == "teacher":
            origen = "PROFESOR"
        else:
            origen = "IMPORTACION"
        cambios = {}
        if origen != usuario.origen:
            cambios["origen"] = origen
        if usuario.confirmado_en is None:
            cambios["confirmado_en"] = usuario.creado_en
        if cambios:
            Usuario.objects.filter(pk=usuario.pk).update(**cambios)

    Politica.objects.filter(perfil="teacher").update(autoregistro=True)
    for fila in Politica.objects.filter(perfil="student"):
        cambios = {"autoregistro": True, "bloqueo_alcance": "DISPOSITIVO"}
        if fila.tipo_secreto == "PIN" and fila.longitud_minima == 6:
            cambios["longitud_minima"] = 4
        Politica.objects.filter(pk=fila.pk).update(**cambios)


class Migration(migrations.Migration):

    dependencies = [
        ("acceso", "0010_pin_maestro_origen_autoalta"),
    ]

    operations = [
        migrations.RunPython(sembrar, migrations.RunPython.noop),
    ]

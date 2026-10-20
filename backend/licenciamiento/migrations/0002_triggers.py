"""
Los tres triggers de MOD-018 (SQLite):

  · `m18_marca_alta`  la marca alta del reloj SÓLO SUBE (P-06): cualquier UPDATE que la baje aborta.
  · `m18_licencia`    el historial de licencias es de SÓLO INSERCIÓN: ningún UPDATE.
  · `m18_observacion` las observaciones son de SÓLO INSERCIÓN: ningún UPDATE.

No hay trigger contra DELETE a propósito: el vaciado de las pruebas (`TransactionTestCase`) borra con DELETE, y la protección contra el borrado no la da un trigger (quien puede borrar filas
de SQLite también puede quitar el trigger) sino el diseño: lo que importa no sólo vive en la base —el espejo de la licencia, las liberadas y las anclas del reloj están FUERA de ella y una
copia de seguridad restaurada no las rebobina.

Si una migración futura reconstruye alguna de estas tablas (SQLite lo hace al alterar columnas), debe terminar con `migrations.RunSQL(SQL_CREAR)`: la reconstrucción se lleva los triggers.
"""
from django.db import migrations

SQL_CREAR = [
    "CREATE TRIGGER IF NOT EXISTS m18_marca_alta_solo_sube BEFORE UPDATE OF valor ON m18_marca_alta WHEN NEW.valor < OLD.valor "
    "BEGIN SELECT RAISE(ABORT, 'La marca alta del reloj solo sube'); END;",
    "CREATE TRIGGER IF NOT EXISTS m18_licencia_solo_insercion BEFORE UPDATE ON m18_licencia "
    "BEGIN SELECT RAISE(ABORT, 'El historial de licencias es de solo insercion'); END;",
    "CREATE TRIGGER IF NOT EXISTS m18_observacion_solo_insercion BEFORE UPDATE ON m18_observacion "
    "BEGIN SELECT RAISE(ABORT, 'Las observaciones de licencia son de solo insercion'); END;",
]
SQL_QUITAR = [
    "DROP TRIGGER IF EXISTS m18_marca_alta_solo_sube;",
    "DROP TRIGGER IF EXISTS m18_licencia_solo_insercion;",
    "DROP TRIGGER IF EXISTS m18_observacion_solo_insercion;",
]


class Migration(migrations.Migration):

    dependencies = [
        ("licenciamiento", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(SQL_CREAR, SQL_QUITAR),
    ]

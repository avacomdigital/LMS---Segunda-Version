"""
Los tres triggers de MOD-016 (SQLite):

  · `m16_respaldo`    un respaldo catalogado no se reescribe: ningún UPDATE (lo que se registró es lo que se produjo; la huella del archivo lo acompaña).
  · `m16_historial`   el historial es de SÓLO INSERCIÓN: ningún UPDATE. El estado se deriva de las filas.
  · `m16_pase_usado`  un pase de soporte usado no se reescribe (un pase vale una vez).

No hay trigger contra DELETE a propósito (el vaciado de las pruebas borra con DELETE): la protección la da la bitácora encadenada de MOD-019, con un asiento por cada hecho que importa.
Si una migración futura reconstruye alguna de estas tablas (SQLite lo hace al alterar columnas), debe terminar con `migrations.RunSQL(SQL_CREAR)`.
"""
from django.db import migrations

SQL_CREAR = [
    "CREATE TRIGGER IF NOT EXISTS m16_respaldo_solo_insercion BEFORE UPDATE ON m16_respaldo "
    "BEGIN SELECT RAISE(ABORT, 'Un respaldo catalogado no se reescribe'); END;",
    "CREATE TRIGGER IF NOT EXISTS m16_historial_solo_insercion BEFORE UPDATE ON m16_historial "
    "BEGIN SELECT RAISE(ABORT, 'El historial de respaldos es de solo insercion'); END;",
    "CREATE TRIGGER IF NOT EXISTS m16_pase_usado_solo_insercion BEFORE UPDATE ON m16_pase_usado "
    "BEGIN SELECT RAISE(ABORT, 'Un pase de soporte usado no se reescribe'); END;",
]
SQL_QUITAR = [
    "DROP TRIGGER IF EXISTS m16_respaldo_solo_insercion;",
    "DROP TRIGGER IF EXISTS m16_historial_solo_insercion;",
    "DROP TRIGGER IF EXISTS m16_pase_usado_solo_insercion;",
]


class Migration(migrations.Migration):

    dependencies = [
        ("respaldo", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(SQL_CREAR, SQL_QUITAR),
    ]

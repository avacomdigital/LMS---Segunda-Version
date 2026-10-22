"""
Los dos triggers de MOD-017 (SQLite):

  · `m17_paquete`    un paquete importado no se reescribe: ningún UPDATE (lo que se guardó es lo que se verificó; la huella del archivo lo acompaña).
  · `m17_historial`  el historial es de SÓLO INSERCIÓN (FUN-187, P-05): ningún UPDATE. El estado se deriva de las filas.

No hay trigger contra DELETE a propósito: el vaciado de las pruebas (`TransactionTestCase`) borra con DELETE, y la protección contra el borrado no la da un trigger (quien puede borrar filas
de SQLite también puede quitar el trigger) sino la bitácora encadenada de MOD-019, que lleva un asiento por cada fila que importa.

Si una migración futura reconstruye alguna de estas tablas (SQLite lo hace al alterar columnas), debe terminar con `migrations.RunSQL(SQL_CREAR)`: la reconstrucción se lleva los triggers.
"""
from django.db import migrations

SQL_CREAR = [
    "CREATE TRIGGER IF NOT EXISTS m17_paquete_solo_insercion BEFORE UPDATE ON m17_paquete "
    "BEGIN SELECT RAISE(ABORT, 'Un paquete de actualizacion importado no se reescribe'); END;",
    "CREATE TRIGGER IF NOT EXISTS m17_historial_solo_insercion BEFORE UPDATE ON m17_historial "
    "BEGIN SELECT RAISE(ABORT, 'El historial de actualizaciones es de solo insercion'); END;",
]
SQL_QUITAR = [
    "DROP TRIGGER IF EXISTS m17_paquete_solo_insercion;",
    "DROP TRIGGER IF EXISTS m17_historial_solo_insercion;",
]


class Migration(migrations.Migration):

    dependencies = [
        ("actualizacion", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(SQL_CREAR, SQL_QUITAR),
    ]

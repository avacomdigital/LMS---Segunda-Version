"""
Los dos triggers de MOD-015 (SQLite):

  · `m15_evento_inmutable`       el sobre y la carga NO se reescriben una vez publicados (P-03): ningún UPDATE sobre `m15_evento`.
  · `m15_marca_alta_solo_sube`   la marca alta del reloj sólo sube (P-13).

NO hay trigger contra DELETE a propósito (P-03): el vaciado de las pruebas (`TransactionTestCase`) borra con DELETE y el corredor ya tiene bastante con los de la bitácora; el único
borrado de la aplicación es la purga, y una prueba de arquitectura comprueba que nadie más lo invoca.

Si una migración futura reconstruye alguna de estas tablas (SQLite lo hace al alterar columnas), debe terminar con `migrations.RunSQL(triggers.SQL_CREAR)`: la reconstrucción se lleva
los triggers.
"""
from django.db import migrations

from nodo.infraestructura.triggers import SQL_CREAR, SQL_QUITAR


class Migration(migrations.Migration):

    dependencies = [
        ("nodo", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(SQL_CREAR, SQL_QUITAR),
    ]

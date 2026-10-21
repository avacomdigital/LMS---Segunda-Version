"""
`m15_evento.agregado_id` pasa de 96 a 256 caracteres (D-26, Fase 3): al cortar el libro de calificaciones se vio que compone el agregado de sus agregados por periodo como
`alumno:grupo:periodo:curso_ref`, y con una referencia de curso de AVACOM Biblioteca supera los 96 que la Fase 2 había propuesto; con el tope viejo esos eventos no entraban
(`SobreIncompleto`) y el consumidor del libro los perdía. Las seis migraciones de corte de la Fase 3 dependen de esta.

En SQLite alterar una columna reconstruye la tabla y la reconstrucción se lleva los triggers y devuelve el AUTOINCREMENT a `max(secuencia)`: por eso termina reponiendo los triggers
(`triggers.SQL_CREAR`) y el piso del contador (`triggers.SQL_REPARAR_CONTADOR`: nunca por debajo del mayor corte registrado en `m15_corte`, D-28). Las dos sentencias son idempotentes.
"""
from django.db import migrations, models

from nodo.infraestructura.triggers import SQL_CREAR, SQL_QUITAR, SQL_REPARAR_CONTADOR


class Migration(migrations.Migration):

    dependencies = [
        ("nodo", "0002_triggers"),
    ]

    operations = [
        migrations.AlterField(model_name="evento", name="agregado_id", field=models.CharField(max_length=256)),
        migrations.RunSQL(SQL_CREAR, SQL_QUITAR),
        migrations.RunSQL(SQL_REPARAR_CONTADOR, migrations.RunSQL.noop),
    ]

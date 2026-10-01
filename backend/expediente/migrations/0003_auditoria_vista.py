"""
MOD-019: `expediente.Auditoria` deja de ser dueño de una tabla. `m19_auditoria` pasa a ser una VISTA de lectura sobre
`m19_bitacora` (la crea `audit.0001_initial`, que también conserva la tabla vieja como `m19_auditoria_legado`).
Aquí sólo cambia el estado del modelo (managed=False): no toca la base.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("expediente", "0002_intento_pendientes"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="auditoria",
            options={"managed": False, "ordering": ["-momento", "-id"]},
        ),
    ]

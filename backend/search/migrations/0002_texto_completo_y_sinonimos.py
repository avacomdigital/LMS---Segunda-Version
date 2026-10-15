"""
El índice de texto completo (SQLite FTS5) y los sinónimos de partida.

`m21_documento_fts` guarda las RAÍCES de las palabras de cada documento (ver `dominio/texto.py`), así que el tokenizador no toca las tildes: la normalización ya
se hizo en Python y es la misma al indexar que al consultar. Su `rowid` es el `id` de `m21_documento`. Es una tabla virtual que Django no conoce: sólo la usa el
repositorio del índice, con SQL parametrizado.
"""
from django.db import migrations

from search.dominio import catalogos as cat

CREAR = "CREATE VIRTUAL TABLE m21_documento_fts USING fts5(titulo, palabras, descripcion, contexto, tokenize='unicode61 remove_diacritics 0')"
BORRAR = "DROP TABLE IF EXISTS m21_documento_fts"


def sembrar_sinonimos(apps, schema_editor):
    Sinonimo = apps.get_model("search", "Sinonimo")
    if Sinonimo.objects.exists():
        return
    for grupo in cat.SINONIMOS_POR_DEFECTO:
        Sinonimo.objects.create(palabras=list(grupo), actualizado_por=cat.SISTEMA)


class Migration(migrations.Migration):

    dependencies = [
        ("search", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(CREAR, BORRAR),
        migrations.RunPython(sembrar_sinonimos, migrations.RunPython.noop),
    ]

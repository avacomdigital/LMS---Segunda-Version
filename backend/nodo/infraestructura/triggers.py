"""
Los triggers de MOD-015 (SQLite), creados por la migración 0002 y repuestos por cualquier migración futura que reconstruya una de estas tablas (SQLite copia y renombra en muchos
`AlterField`, y la reconstrucción se lleva los triggers):

  · `m15_evento_inmutable`         el sobre y la carga NO se reescriben una vez publicados (P-03): ningún UPDATE sobre `m15_evento`.
  · `m15_marca_alta_solo_sube`     la marca alta del reloj sólo sube (P-13).

NO hay trigger contra DELETE a propósito (P-03): el vaciado de las pruebas (`TransactionTestCase`) borra con DELETE y el corredor ya tiene bastante con los de la bitácora. El único
DELETE de la aplicación sobre `m15_evento` es la purga (`repositorios.EventosDjango.borrar`), y una prueba de arquitectura comprueba que nadie más lo invoca.
"""
from __future__ import annotations

NOMBRES = ("m15_evento_inmutable", "m15_marca_alta_solo_sube")

SQL_CREAR = [
    "CREATE TRIGGER IF NOT EXISTS m15_evento_inmutable BEFORE UPDATE ON m15_evento BEGIN SELECT RAISE(ABORT, 'evento_inmutable'); END;",
    "CREATE TRIGGER IF NOT EXISTS m15_marca_alta_solo_sube BEFORE UPDATE OF valor ON m15_marca_alta WHEN NEW.valor < OLD.valor "
    "BEGIN SELECT RAISE(ABORT, 'La marca alta del reloj solo sube'); END;",
]
SQL_QUITAR = [f"DROP TRIGGER IF EXISTS {nombre};" for nombre in NOMBRES]


def existentes(connection) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'm15_%'")
        return {fila[0] for fila in cursor.fetchall()}


def crear(connection) -> None:
    with connection.cursor() as cursor:
        for sentencia in SQL_CREAR:
            cursor.execute(sentencia)

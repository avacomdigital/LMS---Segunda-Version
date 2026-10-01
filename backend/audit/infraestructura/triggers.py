"""
Triggers de inmutabilidad de la bitácora (§3.3, capa 2). Los crea la migración 0001 y los repone el corredor de
pruebas alrededor del vaciado de tablas de `TransactionTestCase`. Un `RAISE(ABORT)` revierte la sentencia y no puede
insertar el asiento del intento: por eso, cuando el intento llega por la aplicación, el manager lo asienta aparte.

`m19_auditoria_legado` (la tabla vieja) queda de sólo lectura durante un ciclo de versión.

Ojo: el editor de esquema de SQLite de Django reconstruye la tabla (copia y renombra) en muchos `AlterField`, lo que
pierde los triggers. Toda migración futura sobre m19_bitacora debe terminar con `migrations.RunSQL(triggers.SQL_CREAR)`.
La verificación (§4.3) detecta su ausencia como `triggers_ausentes`.
"""
from __future__ import annotations

TABLA = "m19_bitacora"
TABLA_LEGADO = "m19_auditoria_legado"
MENSAJE = "bitacora_inmutable"

NOMBRES = ("m19_bitacora_no_update", "m19_bitacora_no_delete")
NOMBRES_LEGADO = ("m19_auditoria_legado_no_update", "m19_auditoria_legado_no_delete", "m19_auditoria_legado_no_insert")

SQL_CREAR = f"""
CREATE TRIGGER IF NOT EXISTS m19_bitacora_no_update BEFORE UPDATE ON {TABLA}
  BEGIN SELECT RAISE(ABORT, '{MENSAJE}'); END;
CREATE TRIGGER IF NOT EXISTS m19_bitacora_no_delete BEFORE DELETE ON {TABLA}
  BEGIN SELECT RAISE(ABORT, '{MENSAJE}'); END;
"""

SQL_QUITAR = "\n".join(f"DROP TRIGGER IF EXISTS {nombre};" for nombre in NOMBRES)

SQL_CREAR_LEGADO = f"""
CREATE TRIGGER IF NOT EXISTS m19_auditoria_legado_no_update BEFORE UPDATE ON {TABLA_LEGADO}
  BEGIN SELECT RAISE(ABORT, 'auditoria_legado_solo_lectura'); END;
CREATE TRIGGER IF NOT EXISTS m19_auditoria_legado_no_delete BEFORE DELETE ON {TABLA_LEGADO}
  BEGIN SELECT RAISE(ABORT, 'auditoria_legado_solo_lectura'); END;
CREATE TRIGGER IF NOT EXISTS m19_auditoria_legado_no_insert BEFORE INSERT ON {TABLA_LEGADO}
  BEGIN SELECT RAISE(ABORT, 'auditoria_legado_solo_lectura'); END;
"""

SQL_QUITAR_LEGADO = "\n".join(f"DROP TRIGGER IF EXISTS {nombre};" for nombre in NOMBRES_LEGADO)


def _ejecutar(connection, sql: str) -> None:
    with connection.cursor() as cursor:
        for sentencia in sentencias(sql):
            cursor.execute(sentencia)


def sentencias(sql: str) -> list[str]:
    """Separa por «END;» (triggers) o por «;» (drops), sin partir el cuerpo de un trigger."""
    salida: list[str] = []
    actual: list[str] = []
    for linea in sql.strip().splitlines():
        actual.append(linea)
        if linea.strip().endswith("END;") or (linea.strip().endswith(";") and "TRIGGER" in linea and "DROP" in linea):
            salida.append("\n".join(actual))
            actual = []
    if any(l.strip() for l in actual):
        salida.append("\n".join(actual))
    return salida


def crear(connection) -> None:
    _ejecutar(connection, SQL_CREAR)


def quitar(connection) -> None:
    _ejecutar(connection, SQL_QUITAR)


def existentes(connection) -> set[str]:
    """Qué triggers de la bitácora hay en sqlite_master (la verificación exige los dos)."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = %s", [TABLA])
        return {fila[0] for fila in cursor.fetchall()}


def completos(connection) -> bool:
    return set(NOMBRES) <= existentes(connection)

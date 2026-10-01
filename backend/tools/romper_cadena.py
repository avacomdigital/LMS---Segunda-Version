"""
Utilidad de PRUEBAS (§2.3.3, §4.5): «rompe» la cadena de la bitácora para comprobar que la verificación detecta el
salto. Desactiva los triggers de inmutabilidad, altera o borra un asiento, y los repone al salir. Nunca con SQL suelto
en un test: siempre por aquí, para que quede claro qué prueba rompió qué.

    python tools/romper_cadena.py --secuencia 7 --campo motivo --valor alterado
    python tools/romper_cadena.py --secuencia 7 --borrar
    python tools/romper_cadena.py --quitar-triggers          # simula que alguien suprimió los triggers

Desde una prueba:  `from tools import romper_cadena; romper_cadena.alterar(7, "motivo", "alterado")`.
Sólo opera con AVACOM_LMS_ENTORNO=pruebas o AVACOM_LMS_DEBUG=1: jamás sobre un nodo instalado.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "avacom_lms.settings")

CAMPOS_PERMITIDOS = ("motivo", "accion", "valor_nuevo", "valor_anterior", "resultado", "usuario_id", "objeto_id", "huella", "huella_previa", "secuencia")


def _asegurar_entorno() -> None:
    from django.conf import settings
    if getattr(settings, "AVACOM_LMS_ENTORNO", "") == "instalado":
        raise SystemExit("romper_cadena sólo opera en desarrollo o pruebas, nunca en un nodo instalado.")


def _sin_triggers(connection, tarea):
    from audit.infraestructura import triggers
    triggers.quitar(connection)
    try:
        return tarea()
    finally:
        triggers.crear(connection)


def alterar(secuencia: int, campo: str = "motivo", valor="alterado") -> int:
    """Cambia un campo de un asiento por debajo de la aplicación. Devuelve las filas tocadas."""
    import json

    from django.db import connection

    _asegurar_entorno()
    if campo not in CAMPOS_PERMITIDOS:
        raise ValueError(f"Campo no permitido: {campo}")
    if campo in ("valor_nuevo", "valor_anterior") and not isinstance(valor, str):
        valor = json.dumps(valor)

    def tarea():
        with connection.cursor() as cursor:
            cursor.execute(f"UPDATE m19_bitacora SET {campo} = %s WHERE secuencia = %s", [valor, secuencia])
            return cursor.rowcount

    return _sin_triggers(connection, tarea)


def borrar(secuencia: int) -> int:
    from django.db import connection

    _asegurar_entorno()

    def tarea():
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM m19_bitacora WHERE secuencia = %s", [secuencia])
            return cursor.rowcount

    return _sin_triggers(connection, tarea)


def quitar_triggers() -> None:
    from django.db import connection

    from audit.infraestructura import triggers

    _asegurar_entorno()
    triggers.quitar(connection)


def reponer_triggers() -> None:
    from django.db import connection

    from audit.infraestructura import triggers

    triggers.crear(connection)


def main(argv: list[str] | None = None) -> int:
    import django

    django.setup()
    p = argparse.ArgumentParser(description="Rompe la cadena de la bitácora (sólo pruebas).")
    p.add_argument("--secuencia", type=int)
    p.add_argument("--campo", default="motivo", choices=CAMPOS_PERMITIDOS)
    p.add_argument("--valor", default="alterado")
    p.add_argument("--borrar", action="store_true")
    p.add_argument("--quitar-triggers", action="store_true")
    args = p.parse_args(argv)
    if args.quitar_triggers:
        quitar_triggers()
        print("Triggers de m19_bitacora retirados (la verificación debe detectarlo).")
        return 0
    if args.secuencia is None:
        p.error("Indique --secuencia o --quitar-triggers.")
    tocadas = borrar(args.secuencia) if args.borrar else alterar(args.secuencia, args.campo, args.valor)
    print(f"{tocadas} fila(s) {'borrada(s)' if args.borrar else 'alterada(s)'} en la secuencia {args.secuencia}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

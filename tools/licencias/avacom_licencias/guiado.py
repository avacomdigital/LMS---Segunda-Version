"""
El MODO GUIADO: un menú numerado para el personal que no usa la línea de comandos. No hace nada que no haga un subcomando: arma el mismo comando con preguntas y lo ejecuta, así que
la guía interna vale igual para los dos caminos.

Una ruta se puede ESCRIBIR o ARRASTRAR al texto de la consola (Windows la pega entre comillas: se limpian).
"""
from __future__ import annotations

from . import archivos, cli
from . import planes as pl

MENU = """
AVACOM · Emisor de Licencias
============================
  1) Ver una solicitud del colegio
  2) Emitir una licencia (nueva, renovación o ampliación)
  3) Emitir para un cambio de computador
  4) Verificar una licencia
  5) Ver el registro de emisiones
  6) Ceremonia de llaves (crear una llave nueva)
  0) Salir
"""


def _preguntar(texto: str, por_omision: str | None = None) -> str:
    sufijo = f" [{por_omision}]" if por_omision else ""
    valor = archivos.limpiar(cli._leer(f"{texto}{sufijo}: "))
    return valor or (por_omision or "")


def _plan() -> str | None:
    try:
        todos = list(pl.cargar().values())
    except pl.ErrorDePlan as error:
        print(f"ERROR: {error}")
        return None
    if not todos:
        return None
    print("Planes:")
    for i, plan in enumerate(todos, start=1):
        print(f"  {i}) {plan.nombre} — {plan.descripcion}")
    eleccion = _preguntar("Elige el plan (número)", "1")
    try:
        return todos[int(eleccion) - 1].nombre
    except (ValueError, IndexError):
        print("Esa opción no existe.")
        return None


def _vigencia() -> list[str]:
    valor = _preguntar("Vigencia: fecha final AAAA-MM-DD, o meses (Intro = lo que dice el plan)")
    if not valor:
        return []
    return ["--hasta", valor] if "-" in valor else ["--meses", valor]


def _emitir(cambio: bool = False) -> int:
    argv = ["emitir", "--solicitud", _preguntar("Solicitud del colegio (ruta del .avreq o su texto AVQ1.…)"),
            "--privada", _preguntar("Llave privada (.avkey)")]
    plan = _plan()
    if plan:
        argv += ["--plan", plan]
    aula = _preguntar("Nombre del aula (Intro = el que trae la solicitud)")
    if aula:
        argv += ["--aula", aula]
    argv += _vigencia()
    if cambio:
        anterior = _preguntar("Código de la licencia anterior (Intro = el que trae la solicitud; si no trae, saldrá una licencia nueva)")
        if anterior:
            argv += ["--licencia", anterior]
        liberacion = _preguntar("Liberación del equipo viejo (.avrel) — Intro si el equipo viejo NO enciende")
        if liberacion:
            argv += ["--reemplaza", liberacion]
        else:
            argv += ["--liberacion-pendiente", _preguntar("Días de plazo para confirmar la liberación", "45")]
    salida = _preguntar("Carpeta de salida (Intro = la de la herramienta)")
    if salida:
        argv += ["--salida", salida]
    return cli.main(argv)


def principal() -> int:
    """El bucle del menú. Devuelve 0 al salir. Cada opción muestra sus errores y vuelve al menú: un dato mal puesto no cierra la herramienta."""
    while True:
        print(MENU)
        try:
            opcion = archivos.limpiar(cli._leer("Elige una opción: "))
        except EOFError:
            return 0
        try:
            if opcion == "0":
                return 0
            elif opcion == "1":
                cli.main(["solicitud", "ver", _preguntar("Solicitud (ruta del .avreq o su texto AVQ1.…)")])
            elif opcion == "2":
                _emitir()
            elif opcion == "3":
                _emitir(cambio=True)
            elif opcion == "4":
                argv = ["verificar", _preguntar("Licencia (ruta del .avlic o su texto AVL1.…)"), "--publica", _preguntar("Llave pública (.pub)")]
                solicitud = _preguntar("Solicitud para comprobar la huella (Intro = omitir)")
                if solicitud:
                    argv += ["--solicitud", solicitud]
                cli.main(argv)
            elif opcion == "5":
                cli.main(["registro", "ver"])
            elif opcion == "6":
                print("\nLa ceremonia de llaves se hace UNA vez, con el CTO presente, en un equipo SIN red.")
                cli.main(["claves", "generar", "--kid", _preguntar("Nombre de la llave (kid)", "prod-2026-1"), "--salida", _preguntar("Carpeta (mejor una memoria USB)")])
            else:
                print("Esa opción no existe: elige un número del menú.")
        except SystemExit:
            print("Alguna opción no es válida. Vuelve a intentarlo.")
        except EOFError:
            return 0
        if opcion in ("1", "2", "3", "4", "5", "6"):
            try:
                cli._leer("\nPulsa Intro para volver al menú…")
            except EOFError:
                return 0

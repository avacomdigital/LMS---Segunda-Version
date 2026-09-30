"""
Mantenimiento rápido de los logs (§2.7 del prompt de MOD-019): abre los archivos JSON Lines de la carpeta de logs,
filtra y los imprime legibles, y resume por ruta (happy · sad · bad).

    python tools/ver_logs.py --ultimos 50 --nivel ERROR --canal escritura
    python tools/ver_logs.py --caso modo_estudio.test_asignaciones --ruta bad
    python tools/ver_logs.py --corr 9c1e…                   # sigue una operación de punta a punta
    python tools/ver_logs.py --carpeta C:\\ProgramData\\AVACOM\\"OPS Master"\\Logs --app student

Sin `--carpeta` usa AVACOM_LMS_DIR_LOGS o, si no está, backend\\logs (desarrollo).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

AQUI = Path(__file__).resolve().parent.parent


def carpeta_por_defecto() -> Path:
    propia = (os.environ.get("AVACOM_LMS_DIR_LOGS") or "").strip()
    return Path(propia) if propia else AQUI / "logs"


def leer(carpeta: Path, archivos: list[str] | None = None) -> list[dict]:
    lineas: list[dict] = []
    for ruta in sorted(carpeta.glob("*.log*")):
        if archivos and ruta.name.split(".log")[0] not in archivos:
            continue
        try:
            with ruta.open(encoding="utf-8", errors="replace") as f:
                for cruda in f:
                    cruda = cruda.strip()
                    if not cruda:
                        continue
                    try:
                        linea = json.loads(cruda)
                    except ValueError:
                        linea = {"ts": "", "nivel": "?", "canal": "?", "mensaje": cruda}
                    linea["_archivo"] = ruta.name
                    lineas.append(linea)
        except OSError as error:
            print(f"(no se pudo leer {ruta.name}: {error})", file=sys.stderr)
    lineas.sort(key=lambda l: str(l.get("ts") or ""))
    return lineas


def filtrar(lineas: list[dict], args) -> list[dict]:
    def pasa(l: dict) -> bool:
        if args.nivel and str(l.get("nivel", "")).upper() != args.nivel.upper():
            return False
        if args.canal and l.get("canal") != args.canal:
            return False
        if args.app and l.get("app") != args.app:
            return False
        if args.ruta and l.get("ruta") != args.ruta:
            return False
        if args.caso and args.caso not in str(l.get("caso") or ""):
            return False
        if args.corr and not str(l.get("corr") or "").startswith(args.corr):
            return False
        if args.evento and args.evento not in str(l.get("evento") or ""):
            return False
        if args.desde and str(l.get("ts") or "") < args.desde:
            return False
        return True

    return [l for l in lineas if pasa(l)]


def imprimir(lineas: list[dict], con_detalle: bool) -> None:
    for l in lineas:
        ts = str(l.get("ts") or "")[11:23]
        cabeza = f"{ts} {str(l.get('nivel') or ''):7} {str(l.get('canal') or ''):12} {str(l.get('app') or ''):7}"
        evento = l.get("evento") or ""
        ruta = f" [{l['ruta']}]" if l.get("ruta") else ""
        corr = f" corr={str(l.get('corr'))[:8]}" if l.get("corr") else ""
        print(f"{cabeza} {evento:36}{ruta} {l.get('mensaje') or ''}{corr}")
        if con_detalle and l.get("detalle") is not None:
            print("        " + json.dumps(l["detalle"], ensure_ascii=False))
        if l.get("traza"):
            for renglon in str(l["traza"]).rstrip().splitlines()[-6:]:
                print("        " + renglon)


def resumen(lineas: list[dict]) -> str:
    rutas = Counter(l.get("ruta") for l in lineas if l.get("ruta"))
    niveles = Counter(l.get("nivel") for l in lineas)
    partes = [f"{r} {rutas.get(r, 0)}" for r in ("happy", "sad", "bad")]
    return " · ".join(partes) + "   |   " + " · ".join(f"{n} {c}" for n, c in sorted(niveles.items(), key=lambda x: str(x[0])))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Lee los logs JSON Lines del nodo de forma legible.")
    p.add_argument("--carpeta", type=Path, default=None)
    p.add_argument("--archivo", action="append", help="nombre sin extensión (backend-app, student-errores…); repetible")
    p.add_argument("--ultimos", type=int, default=100)
    p.add_argument("--nivel")
    p.add_argument("--canal", choices=["escritura", "comunicacion", "dispositivo", "aplicacion", "auditoria", "instalacion"])
    p.add_argument("--app", choices=["backend", "ops", "student"])
    p.add_argument("--ruta", choices=["happy", "sad", "bad"])
    p.add_argument("--caso")
    p.add_argument("--corr")
    p.add_argument("--evento")
    p.add_argument("--desde", help="ISO-8601; se compara como texto")
    p.add_argument("--detalle", action="store_true", help="imprime también el campo detalle")
    args = p.parse_args(argv)
    carpeta = args.carpeta or carpeta_por_defecto()
    if not carpeta.exists():
        print(f"No existe la carpeta de logs {carpeta}", file=sys.stderr)
        return 2
    lineas = filtrar(leer(carpeta, args.archivo), args)
    mostradas = lineas[-args.ultimos:] if args.ultimos > 0 else lineas
    imprimir(mostradas, args.detalle)
    print(f"\n{len(mostradas)} de {len(lineas)} líneas en {carpeta}   ·   {resumen(lineas)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

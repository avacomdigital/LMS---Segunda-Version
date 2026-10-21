"""
Inventario de las colas de salida del nodo (Fase 0 de MOD-015): qué tabla `m*_evento_salida` existe, qué tipos de evento publica cada módulo (las cadenas
`dominio.hecho.vN` / `dominio.objeto.accion.vN` que aparecen en su código, sin las pruebas), quién lee cada cola (`<módulo>.servicios.eventos_desde`) y con qué marca.

    cd backend
    .venv\\Scripts\\python -m nodo.tools.inventario_colas            # tabla Markdown por la salida estándar
    .venv\\Scripts\\python -m nodo.tools.inventario_colas --json     # el inventario como JSON (lo que siembra el catálogo)

Es una lectura del código con expresiones regulares: no importa Django ni abre la base. Lo que cambie en el árbol lo cambia aquí al volver a correrlo.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]            # backend/
TIPO = re.compile(r"[\"']([a-z][a-z0-9_]*\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?\.v\d+)[\"']")
TABLA = re.compile(r"db_table\s*=\s*[\"'](m\d\d_evento_salida)[\"']")
LECTOR = re.compile(r"from\s+(\w+)\s+import\s+servicios(?:\s+as\s+\w+)?|(\w+)\.servicios\.eventos_desde|servicios\.eventos_desde")
MARCA = re.compile(r"db_table\s*=\s*[\"'](m\d\d_marca_[a-z_]+)[\"']")
APPS_EXCLUIDAS = {"avacom_lms", "tools", "nodo", "biblioteca", "expediente", "cache_medios", "cola_medios", "logs"}


def _archivos(app: Path):
    for ruta in app.rglob("*.py"):
        partes = ruta.relative_to(app).parts
        if "tests" in partes or "migrations" in partes or "__pycache__" in partes:
            continue
        yield ruta


def inventario() -> dict:
    colas: dict[str, dict] = {}
    lectores: dict[str, set[str]] = defaultdict(set)
    marcas: dict[str, list[str]] = defaultdict(list)
    for app in sorted(p for p in RAIZ.iterdir() if p.is_dir() and (p / "models.py").exists() and p.name not in APPS_EXCLUIDAS):
        tipos: set[str] = set()
        tabla = None
        for ruta in _archivos(app):
            texto = ruta.read_text(encoding="utf-8", errors="replace")
            if ruta.name == "models.py":
                if (m := TABLA.search(texto)):
                    tabla = m.group(1)
                marcas[app.name] += MARCA.findall(texto)
            tipos |= set(TIPO.findall(texto))
            # ¿Lee la cola de otro módulo? `from <modulo> import servicios` + `eventos_desde` en el mismo archivo.
            if "eventos_desde" in texto:
                for dueno in re.findall(r"from\s+(\w+)\s+import\s+servicios", texto):
                    if dueno != app.name:
                        lectores[dueno].add(app.name)
        if tabla or tipos:
            colas[app.name] = {"tabla": tabla, "tipos": sorted(tipos)}
    # Los tipos que un módulo sólo CONSUME (los nombra en su código pero el prefijo es de otro dominio) se separan de los que produce.
    prefijos = {app: _prefijo_de(app, datos["tipos"]) for app, datos in colas.items()}
    for app, datos in colas.items():
        propios = [t for t in datos["tipos"] if t.split(".")[0] in prefijos[app]]
        ajenos = [t for t in datos["tipos"] if t.split(".")[0] not in prefijos[app]]
        datos["produce"] = propios
        datos["consume"] = ajenos
        datos["prefijos"] = sorted(prefijos[app])
        datos["leida_por"] = sorted(lectores.get(app, ()))
        datos["marcas"] = sorted(set(marcas.get(app, ())))
        del datos["tipos"]
    return colas


_PREFIJOS_CONOCIDOS = {
    "acceso": {"identidad"}, "classroom_engine": {"aula"}, "modo_estudio": {"estudio"}, "device_manager": {"dispositivo"}, "evaluacion": {"evaluacion"},
    "gradebook": {"calificacion"}, "reporting": {"reporte"}, "audit": {"auditoria"}, "search": {"busqueda"}, "licenciamiento": {"licencia"},
}


def _prefijo_de(app: str, tipos: list[str]) -> set[str]:
    if app in _PREFIJOS_CONOCIDOS:
        return _PREFIJOS_CONOCIDOS[app]
    conteo: dict[str, int] = defaultdict(int)
    for t in tipos:
        conteo[t.split(".")[0]] += 1
    return {max(conteo, key=conteo.get)} if conteo else set()


def markdown(inv: dict) -> str:
    lineas = ["| Cola | Módulo | Tipos que produce | Quién la lee hoy | Marca del lector |", "|---|---|---|---|---|"]
    total = 0
    for app, d in inv.items():
        total += len(d["produce"])
        lineas.append(f"| `{d['tabla'] or '—'}` | {app} | {', '.join(d['prefijos'])}.* ({len(d['produce'])}) | {', '.join(d['leida_por']) or 'nadie'} | "
                      f"{', '.join('`' + m + '`' for l in d['leida_por'] for m in inv.get(l, {}).get('marcas', [])) or '—'} |")
    lineas.append(f"\nTotal de tipos producidos: **{total}**.")
    lineas.append("\n### Tipos por módulo\n")
    for app, d in inv.items():
        lineas.append(f"**{app}** ({len(d['produce'])}): " + ", ".join(f"`{t}`" for t in d["produce"]))
        if d["consume"]:
            lineas.append(f"  · consume: " + ", ".join(f"`{t}`" for t in d["consume"]))
        lineas.append("")
    return "\n".join(lineas)


if __name__ == "__main__":
    inv = inventario()
    if "--json" in sys.argv:
        print(json.dumps(inv, ensure_ascii=False, indent=2))
    else:
        print(markdown(inv))

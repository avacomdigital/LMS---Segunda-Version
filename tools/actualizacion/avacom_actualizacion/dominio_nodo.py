"""
Carga el dominio PURO del nodo (`actualizacion.dominio`), que es el que sabe escribir y leer el contenedor, la firma y el manifiesto de un `.avupd`.

Dónde lo busca, en este orden:

  1. `vendor/` junto a la herramienta (una carpeta portátil copia ahí SÓLO `actualizacion/__init__.py` y `actualizacion/dominio/`);
  2. `<repositorio>/backend/` (cuando se corre desde el repositorio).

Sólo se importan módulos de `actualizacion.dominio`: nada de Django, nada de `actualizacion.tests`.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]          # tools/actualizacion (o la raíz de la carpeta portátil)


def _candidatas():
    yield RAIZ / "vendor"
    yield RAIZ.parents[1] / "backend"               # tools/actualizacion → tools → <repositorio>


def _preparar() -> Path:
    for ruta in _candidatas():
        if (ruta / "actualizacion" / "dominio").is_dir():
            if str(ruta) not in sys.path:
                sys.path.insert(0, str(ruta))
            return ruta
    raise RuntimeError("No se encontró el dominio de actualización (actualizacion/dominio): ni en vendor/ ni en backend/.")


ORIGEN = _preparar()

from actualizacion.dominio import catalogos, contenedor, errores, firma, manifiesto, paquete  # noqa: E402

__all__ = ["ORIGEN", "RAIZ", "catalogos", "contenedor", "errores", "firma", "manifiesto", "paquete"]

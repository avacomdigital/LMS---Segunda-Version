"""
Carga el dominio PURO del nodo (`licenciamiento.dominio`), que es el que sabe escribir y leer los tres archivos de licenciamiento.

Dónde lo busca, en este orden:

  1. `vendor/` junto a la herramienta (la carpeta portátil que arma `Build-Emisor.ps1` copia ahí SÓLO `licenciamiento/__init__.py` y `licenciamiento/dominio/`);
  2. `<repositorio>/backend/` (cuando se corre desde el repositorio).

Sólo se importan módulos de `licenciamiento.dominio`: nada de Django, nada de `licenciamiento.tests`.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]          # tools/licencias (o la raíz de la carpeta portátil)


def _candidatas():
    yield RAIZ / "vendor"
    yield RAIZ.parents[1] / "backend"               # tools/licencias → tools → <repositorio>


def _preparar() -> Path:
    for ruta in _candidatas():
        if (ruta / "licenciamiento" / "dominio").is_dir():
            if str(ruta) not in sys.path:
                sys.path.insert(0, str(ruta))
            return ruta
    raise RuntimeError("No se encontró el dominio de licenciamiento (licenciamiento/dominio): ni en vendor/ ni en backend/.")


ORIGEN = _preparar()

from licenciamiento.dominio import catalogos, errores, firma, huella, licencia, politica, solicitud, tlv  # noqa: E402

__all__ = ["ORIGEN", "RAIZ", "catalogos", "errores", "firma", "huella", "licencia", "politica", "solicitud", "tlv"]

"""
¿Este nodo es de producción? (P-12 · «entorno sin puerta trasera»).

`AVACOM_LMS_ENTORNO` se lee de `backend.env`, un TEXTO EDITABLE: sirve para elegir la carpeta de logs, y NO puede decidir si hay licencia. Un administrador que pusiera
`AVACOM_LMS_ENTORNO=pruebas` en ese archivo apagaría la protección. Por eso un nodo es de PRODUCCIÓN si se cumple CUALQUIERA de estas:

  1. existe el marcador de canal `.avacom-canal` que escribe el instalador junto al código (dentro de la huella del paquete);
  2. el código corre bajo `Program Files`;
  3. `AVACOM_LMS_ENTORNO=instalado` (esa variable sólo puede AÑADIR protección, nunca quitarla).

Sólo si NINGUNA se cumple y hay un `.git` en un ancestro del código (un repositorio de desarrollo; el paquete instalado no lo trae, pero sí `manage.py`, así que éste no basta) es
DESARROLLO —y PRUEBAS si el comando es `manage.py test`—. En cualquier otro caso (ni marcador, ni Program Files, ni repositorio) se toma como producción: ante la duda, se licencia.

Un administrador que copie el backend fuera de `Program Files`, borre el marcador y fabrique un `.git` lo evade: eso es A4 (administrador local con conocimientos) y no se promete
impedirlo; deja de ser silencioso porque el marcador forma parte de la huella del paquete (Fase 4: firmado).

Este archivo es puro: recibe el entorno, los argumentos y una función para preguntar si una ruta existe.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

PRODUCCION, DESARROLLO, PRUEBAS = "produccion", "desarrollo", "pruebas"
MARCADOR_DE_CANAL = ".avacom-canal"


def _bajo_program_files(raiz: Path) -> bool:
    return any(parte.lower().startswith("program files") for parte in raiz.parts)


def _hay_git_en_ancestros(raiz: Path, existe: Callable[[Path], bool]) -> bool:
    return any(existe(carpeta / ".git") for carpeta in (raiz, *raiz.parents))


def clasificar(raiz_del_codigo: Path, env: Mapping[str, str], argv: Sequence[str], existe: Callable[[Path], bool] = Path.exists) -> str:
    """`produccion`, `desarrollo` o `pruebas` para el código que vive en `raiz_del_codigo` (la carpeta `backend`)."""
    raiz = Path(raiz_del_codigo)
    if existe(raiz / MARCADOR_DE_CANAL) or _bajo_program_files(raiz) or str(env.get("AVACOM_LMS_ENTORNO", "")).strip().lower() == "instalado":
        return PRODUCCION
    if _hay_git_en_ancestros(raiz, existe):
        return PRUEBAS if len(argv) > 1 and argv[1] == "test" else DESARROLLO
    return PRODUCCION


def es_de_produccion(entorno: str) -> bool:
    return entorno == PRODUCCION

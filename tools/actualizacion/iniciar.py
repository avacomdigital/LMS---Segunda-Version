"""
Punto de entrada de la herramienta (lo usan los `.bat`): pone su propia carpeta en `sys.path` y llama a la línea de comandos.

El Python «embeddable» de una carpeta portátil arranca aislado (no añade el directorio del script ni lee PYTHONPATH), así que la ruta se declara aquí.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from avacom_actualizacion.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

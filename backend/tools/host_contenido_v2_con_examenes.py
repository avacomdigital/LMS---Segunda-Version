"""
Arranca, a mano, el host de pruebas de la API de Contenido v2 CON las dos rutas de examen del contrato 2 (`…/exams/{id}/pool` y `…/exams/{id}/questions`), que sólo usa MOD-010.
`host_contenido_v2_pruebas` no las trae (lo usan las demás pruebas); `evaluacion/tests/host_examenes.py` las añade para las pruebas automáticas y este archivo sólo lo deja
andando para probar a mano un nodo que aplica y califica exámenes (`tools/sembrar_gradebook.py`):

    .venv\\Scripts\\python -m tools.host_contenido_v2_con_examenes %TEMP%\\link-pruebas.json
    set AVACOM_CONTENIDO_ENLACE_V2=%TEMP%\\link-pruebas.json

Sirve el curso de ejemplo (`spec-driven/02-classroom-engine/example.json`) y califica con el calificador de referencia de la biblioteca. NUNCA lo uses en un aula real.
"""
from __future__ import annotations

import json
import os
import sys
import time

from evaluacion.tests.host_examenes import HostConExamenes
from tools.host_contenido_v2_pruebas import PNG_1x1

if __name__ == "__main__":
    ruta = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ.get("TEMP", "."), "link-pruebas.json")
    ejemplo = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "..", "spec-driven", "02-classroom-engine", "example.json")
    with open(ejemplo, encoding="utf-8") as f:
        manifiesto = json.load(f)
    medios = {m["id"]: ("image/png", PNG_1x1) for m in manifiesto.get("media", []) if m.get("kind") == "image"}
    host = HostConExamenes(ruta, {manifiesto["id"]: manifiesto}, medios=medios).iniciar()
    print(f"API de Contenido v2 de pruebas (con exámenes) en http://127.0.0.1:{host.puerto} (medios en {host.puerto_medios}) · link.json en {ruta}", flush=True)
    print("set AVACOM_CONTENIDO_ENLACE_V2=" + ruta, flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        host.detener()

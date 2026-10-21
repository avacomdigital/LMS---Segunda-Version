"""
Concurrencia de hilos y de procesos, restauración de una copia vieja y proceso muerto a mitad de transacción, sobre una base de ARCHIVO temporal (`nodo/tools/prueba_concurrencia.py`
en un subproceso: la base de las pruebas de Django va en memoria y no sirve para esto). Jamás toca `backend/db.sqlite3` ni ProgramData.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parents[2]


@unittest.skipIf(os.environ.get("AVACOM_NODO_SIN_CONCURRENCIA") == "1", "AVACOM_NODO_SIN_CONCURRENCIA=1")
class ConcurrenciaTests(SimpleTestCase):
    def test_hilos_procesos_restauracion_y_proceso_muerto(self):
        carpeta = tempfile.mkdtemp(prefix="avacom-nodo-concurrencia-")
        self.addCleanup(shutil.rmtree, carpeta, ignore_errors=True)
        r = subprocess.run([sys.executable, "-m", "nodo.tools.prueba_concurrencia", carpeta, "--hilos", "20", "--por-hilo", "50", "--procesos", "4", "--por-proceso", "50"],
                           cwd=str(RAIZ), capture_output=True, text=True, timeout=900, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        cifras = json.loads(r.stdout[r.stdout.index("{"):])
        print("\n[medición] concurrencia:", json.dumps(cifras, ensure_ascii=False))
        # 1 · 20 hilos: la secuencia es 1..1000 sin huecos ni repetidos, sin errores de «database is locked»
        self.assertEqual(cifras["hilos"]["errores"], [])
        self.assertEqual((cifras["hilos"]["total"], cifras["hilos"]["sin_huecos"], cifras["hilos"]["repetidas"]), (1000, True, 0))
        # 2 · 4 procesos a la vez contra la misma base
        self.assertEqual(cifras["procesos"]["fallos"], [])
        self.assertEqual((cifras["procesos"]["total"], cifras["procesos"]["sin_huecos"]), (200, True))
        # 3 · restaurar una copia vieja: se detecta y ninguna secuencia nueva repite una emitida (INV-002)
        self.assertTrue(cifras["restauracion"]["restauracion_detectada"])
        self.assertTrue(cifras["restauracion"]["ninguna_repetida"])
        self.assertGreater(cifras["restauracion"]["contador_tras_arranque"], cifras["restauracion"]["max_emitido_antes"])
        # 4 · proceso muerto a mitad de transacción: base íntegra, el hijo llegó a confirmar lotes y ninguna transacción quedó a medias
        self.assertEqual(cifras["proceso_muerto"]["quick_check"], ["ok"])
        self.assertGreaterEqual(cifras["proceso_muerto"]["lotes"], 3)
        self.assertEqual(cifras["proceso_muerto"]["lotes_a_medias"], 0)

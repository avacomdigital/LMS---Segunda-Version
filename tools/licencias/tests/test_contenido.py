"""
Contenido de la herramienta (LIC-E-10, LIC-E-12): sin llaves de desarrollo ni privadas, sin importar las pruebas del nodo, sin red y sin arrastrar Django. Los patrones prohibidos se
construyen por partes para que este archivo no los contenga literalmente.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from avacom_licencias import planes as pl
from avacom_licencias.dominio_nodo import RAIZ, licencia

EXCLUIDAS = {"__pycache__", "dist", "python", "vendor", "datos", "salida", "entrada"}
EXTENSIONES = {".py", ".bat", ".json", ".md", ".ps1", ".txt"}


def archivos_de_la_herramienta():
    for ruta in sorted(RAIZ.rglob("*")):
        relativa = ruta.relative_to(RAIZ)
        if ruta.is_file() and not EXCLUIDAS.intersection(relativa.parts) and ruta.suffix.lower() in EXTENSIONES:
            yield ruta


class ContenidoTests(unittest.TestCase):
    def test_no_importa_las_pruebas_del_nodo_ni_trae_llaves_de_desarrollo_ni_privadas(self):
        prohibidos = {
            "un import de las pruebas del nodo": r"(?m)^\s*(?:from|import)\s+" + "licenciamiento" + r"\.tests",
            "la semilla de las llaves de desarrollo": "avacom-licencia-" + "desarrollo",
            "una llave PEM": "BEGIN (?:[A-Z]+ )?" + "PRIVATE KEY",
            "una llave OpenSSH": "BEGIN " + "OPENSSH",
        }
        for ruta in archivos_de_la_herramienta():
            texto = ruta.read_text(encoding="utf-8-sig", errors="replace")
            for nombre, patron in prohibidos.items():
                self.assertIsNone(re.search(patron, texto), f"{ruta.relative_to(RAIZ)} contiene {nombre}")

    def test_no_hay_llaves_privadas_en_la_carpeta(self):
        self.assertEqual([p for p in RAIZ.rglob("*.avkey") if "dist" not in p.parts], [])

    def test_ningun_modulo_toca_la_red(self):
        red = re.compile(r"^\s*(?:import|from)\s+(?:socket|urllib|http|ssl|ftplib|smtplib|requests|asyncio|xmlrpc|telnetlib)\b", re.MULTILINE)
        for ruta in sorted((RAIZ / "avacom_licencias").glob("*.py")) + [RAIZ / "iniciar.py"]:
            self.assertIsNone(red.search(ruta.read_text(encoding="utf-8")), f"{ruta.name} importa algo de red")

    def test_el_dominio_del_nodo_no_arrastra_django(self):
        codigo = f"import sys; sys.path.insert(0, {str(RAIZ)!r}); import avacom_licencias.cli; print('django' in sys.modules, 'rest_framework' in sys.modules)"
        r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "False False")

    def test_los_planes_de_fabrica_son_validos_y_emitibles(self):
        planes = pl.cargar()
        self.assertEqual(sorted(planes), ["anual-aula", "evaluacion"])
        reglas = pl.cargar_reglas()
        self.assertEqual((reglas.gracia_dias, reglas.max_equipos, reglas.max_usuarios), (30, 60, 1200))      # lo que decidió el CTO: Q-L16 y Q-L1
        for plan in planes.values():
            self.assertIn(plan.tipo, (licencia.TIPO_PRODUCCION, licencia.TIPO_EVALUACION))
            self.assertEqual(plan.gracia_dias, 30, plan.nombre)
            self.assertLessEqual(plan.equipos, 60, plan.nombre)
            self.assertLessEqual(plan.usuarios, 1200, plan.nombre)
            # D-21 (Q-L18): los concurrentes son rendimiento por clase (BR-063) y el tope duro no puede quedar por debajo del tamaño contratado, o una clase se
            # «llenaría» antes de los equipos que el colegio pagó.
            self.assertGreaterEqual(plan.concurrentes_pico, plan.equipos, plan.nombre)
            self.assertLessEqual(plan.concurrentes_normal, plan.concurrentes_pico, plan.nombre)
        self.assertEqual((planes["anual-aula"].equipos, planes["anual-aula"].usuarios), (60, 1200))
        self.assertEqual((planes["anual-aula"].concurrentes_normal, planes["anual-aula"].concurrentes_pico), (50, 100))   # D-21: se quedan

    def test_las_reglas_del_cto_son_un_dato_y_se_comprueban(self):
        with tempfile.TemporaryDirectory() as carpeta:
            self.assertEqual(pl.cargar_reglas(carpeta), pl.Reglas())                          # sin reglas.json no se exige nada
            ruta = Path(carpeta) / pl.ARCHIVO_DE_REGLAS
            ruta.write_text('{"version": 1, "gracia_dias": 30, "tamano_maximo": {"equipos": 60, "usuarios": 1200}}', encoding="utf-8")
            reglas = pl.cargar_reglas(carpeta)
            pl.comprobar(reglas, gracia_dias=30, equipos=60, usuarios=1200)                    # justo en el límite
            for argumentos in (dict(gracia_dias=29, equipos=1, usuarios=1), dict(gracia_dias=31, equipos=1, usuarios=1), dict(gracia_dias=30, equipos=61, usuarios=1),
                               dict(gracia_dias=30, equipos=1, usuarios=1201), dict(gracia_dias=30, equipos=licencia.ILIMITADO, usuarios=1)):
                with self.assertRaises(pl.ErrorDePlan, msg=str(argumentos)):
                    pl.comprobar(reglas, **argumentos)
            ruta.write_text("{ no es json", encoding="utf-8")
            with self.assertRaises(pl.ErrorDePlan):
                pl.cargar_reglas(carpeta)
            ruta.write_text('{"version": 1, "tamano_maximo": {"equipos": 0}}', encoding="utf-8")
            with self.assertRaises(pl.ErrorDePlan):
                pl.cargar_reglas(carpeta)

    def test_reglas_json_no_se_confunde_con_un_plan(self):
        with tempfile.TemporaryDirectory() as carpeta:
            (Path(carpeta) / pl.ARCHIVO_DE_REGLAS).write_text('{"version": 1, "gracia_dias": 30}', encoding="utf-8")
            self.assertEqual(pl.cargar(carpeta), {})

    def test_un_plan_de_desarrollo_o_con_datos_malos_se_rechaza(self):
        base = {"nombre": "x", "tipo": "produccion", "meses": 12, "gracia_dias": 30,
                "limites": {"equipos": 1, "usuarios": 1, "concurrentes_normal": 1, "concurrentes_pico": 1}, "capacidades": ["*"]}
        pl.desde_dict(base)
        malos = [dict(base, tipo="desarrollo"), dict(base, meses=0), dict(base, gracia_dias=400), dict(base, capacidades=["magia"]), dict(base, capacidades=[]),
                 dict(base, limites={"equipos": 0, "usuarios": 1, "concurrentes_normal": 1, "concurrentes_pico": 1}),
                 dict(base, limites={"equipos": 1, "usuarios": 1, "concurrentes_normal": 5, "concurrentes_pico": 1}),
                 {k: v for k, v in base.items() if k != "limites"}]
        for plan in malos:
            with self.assertRaises(pl.ErrorDePlan):
                pl.desde_dict(plan)

    def test_una_carpeta_de_planes_con_un_plan_roto_avisa(self):
        with tempfile.TemporaryDirectory() as carpeta:
            (Path(carpeta) / "roto.json").write_text("{ no es json", encoding="utf-8")
            with self.assertRaises(pl.ErrorDePlan):
                pl.cargar(carpeta)


if __name__ == "__main__":
    unittest.main()

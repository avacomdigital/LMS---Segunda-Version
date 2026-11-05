"""
El paquete cifrado del backend (S2): `installer/build/Cifrar-Backend.py` lo escribe y `installer/src/payload/avacom_boot.py` lo abre. Estas pruebas arman un backend de juguete (un paquete, un
subpaquete tipo `migrations`, datos al lado) y comprueban lo que el diseño promete: nada en claro, la llave equivocada no abre, un byte cambiado se detecta al abrir, y Django-style (importar y listar
con `pkgutil.iter_modules`) funciona desde el paquete. Sólo corren en el repositorio (el instalador no trae `installer/`).
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parents[3]
BOOT = RAIZ / "installer" / "src" / "payload" / "avacom_boot.py"
CIFRAR = RAIZ / "installer" / "build" / "Cifrar-Backend.py"


def _cargar(nombre: str, ruta: Path):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    spec.loader.exec_module(modulo)
    return modulo


@unittest.skipUnless(BOOT.is_file() and CIFRAR.is_file(), "installer/ no está en este árbol")
class PaqueteCifradoTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        sys.path.insert(0, str(BOOT.parent))
        cls.boot = _cargar("avacom_boot", BOOT)
        cls.cifrar = _cargar("cifrar_backend", CIFRAR)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name) / "Backend"
        (self.raiz / "app" / "migrations").mkdir(parents=True)
        (self.raiz / "app" / "__init__.py").write_text("SECRETO_DE_DOMINIO = 'cadena-que-no-debe-verse'\n", encoding="utf-8")
        (self.raiz / "app" / "logica.py").write_text("def doble(x):\n    return 2 * x\n", encoding="utf-8")
        (self.raiz / "app" / "migrations" / "__init__.py").write_text("", encoding="utf-8")
        (self.raiz / "app" / "migrations" / "0001_inicial.py").write_text("NOMBRE = '0001'\n", encoding="utf-8")
        (self.raiz / "app" / "datos.json").write_text('{"publico": true}', encoding="utf-8")
        (self.raiz / "manage.py").write_text("import sys\nprint('manage', sys.argv[1:])\n", encoding="utf-8")
        self.k = bytes(range(32))

    def _armar(self) -> bytes:
        datos, cuantos = self.cifrar.construir(self.raiz, self.k)
        self.assertEqual(cuantos, 5)
        return datos

    def test_en_el_paquete_no_hay_nada_en_claro(self):
        datos = self._armar()
        for texto in (b"cadena-que-no-debe-verse", b"logica", b"doble", b"0001_inicial", b"migrations"):
            self.assertNotIn(texto, datos)

    def test_se_abre_con_su_llave_y_entrega_el_codigo(self):
        p = self.boot.Paquete(self._armar(), self.k)
        self.assertIn("app.logica", p)
        self.assertTrue(p.es_paquete("app.migrations"))
        self.assertEqual(p.hijos("app.migrations"), [("0001_inicial", False)])
        espacio: dict = {}
        exec(p.codigo("app.logica"), espacio)       # noqa: S102
        self.assertEqual(espacio["doble"](21), 42)

    def test_con_otra_llave_no_abre(self):
        with self.assertRaises(self.boot.ErrorDePaquete) as e:
            self.boot.Paquete(self._armar(), bytes(32))
        self.assertEqual(str(e.exception), "llave_distinta")

    def test_un_byte_cambiado_en_cualquier_parte_se_detecta_al_abrir(self):
        base = self._armar()
        for posicion in (len(base) - 1, len(base) // 2, 40, 100):       # datos al final, al medio, índice cifrado, cabecera
            datos = bytearray(base)
            datos[posicion] ^= 1
            with self.assertRaises(self.boot.ErrorDePaquete, msg=f"posición {posicion}"):
                self.boot.Paquete(bytes(datos), self.k)

    def test_un_paquete_truncado_o_ajeno_no_abre(self):
        base = self._armar()
        for datos in (base[:50], base[:len(base) - 10], b"nada", b"AVPK" + bytes(60)):
            with self.assertRaises(self.boot.ErrorDePaquete):
                self.boot.Paquete(datos, self.k)

    def test_un_modulo_no_se_puede_cambiar_de_sitio(self):
        """La ruta es dato asociado de cada módulo: si alguien cambia el índice para que `logica` apunte a otro blob, el descifrado falla."""
        p = self.boot.Paquete(self._armar(), self.k)
        a, b = p._indice["app.logica"], p._indice["manage"]
        a["o"], a["l"], a["n"] = b["o"], b["l"], b["n"]
        with self.assertRaises(self.boot.ErrorDePaquete):
            p.codigo("app.logica")

    def test_la_llave_se_lee_de_la_entrada_y_no_de_otro_lado(self):
        import io
        self.assertEqual(self.boot.leer_clave_de_la_entrada(io.StringIO("AVACOM-CLAVE " + self.k.hex() + "\ndetener\n")), self.k)
        for malo in ("", "hola\n", "AVACOM-CLAVE zz\n", "AVACOM-CLAVE " + "ab" * 16 + "\n"):
            with self.assertRaises(self.boot.ErrorDePaquete):
                self.boot.leer_clave_de_la_entrada(io.StringIO(malo))

    def test_desde_otro_proceso_importa_lista_y_ejecuta_sin_ningun_py(self):
        """Lo que hace el Host: un proceso nuevo, la llave por la entrada estándar, `-c` y `manage` contra el paquete, sin que quede un .py en la carpeta."""
        datos, _ = self.cifrar.construir(self.raiz, self.k)
        (self.raiz / "codigo.avpkg").write_bytes(datos)
        for ruta in list(self.raiz.rglob("*.py")):
            ruta.unlink()
        runtime = Path(self._tmp.name) / "Runtime"
        runtime.mkdir()
        (runtime / "avacom_boot.py").write_bytes(BOOT.read_bytes())
        entrada = "AVACOM-CLAVE " + self.k.hex() + "\n"
        entorno = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        codigo = ("import app, app.logica, pkgutil, app.migrations, importlib\n"
                  "print(app.SECRETO_DE_DOMINIO, app.logica.doble(4), sorted(n for _, n, _ in pkgutil.iter_modules(app.migrations.__path__)), importlib.import_module('app.migrations.0001_inicial').NOMBRE)")
        r = subprocess.run([sys.executable, "-I", str(runtime / "avacom_boot.py"), "code", codigo], input=entrada, capture_output=True, text=True, env=entorno, cwd=self._tmp.name, timeout=60)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "cadena-que-no-debe-verse 8 ['0001_inicial'] 0001"), r.stderr)
        r = subprocess.run([sys.executable, "-I", str(runtime / "avacom_boot.py"), "manage", "check", "--x"], input=entrada, capture_output=True, text=True, env=entorno, cwd=self._tmp.name, timeout=60)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "manage ['check', '--x']"), r.stderr)
        self.assertEqual(list(self.raiz.rglob("*.py")), [])
        r = subprocess.run([sys.executable, "-I", str(runtime / "avacom_boot.py"), "code", "print(1)"], input="AVACOM-CLAVE " + bytes(32).hex() + "\n", capture_output=True, text=True, env=entorno, cwd=self._tmp.name, timeout=60)
        self.assertEqual(r.returncode, 3)
        self.assertIn("llave_distinta", r.stderr)
        self.assertNotIn("print", r.stdout)

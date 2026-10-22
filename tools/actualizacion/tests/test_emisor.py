"""
Pruebas del Emisor de Paquetes de Actualización: lo que emite lo acepta EL NODO (su dominio, el mismo que verifica en producción), y lo alterado, de otra llave, con rutas que
se salen o con archivos que no son del módulo se rechaza. Se corren con el Python del backend:

    backend\\.venv\\Scripts\\python -m unittest discover -s tools\\actualizacion\\tests -t tools\\actualizacion
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import random
import re
import tempfile
import unittest
from pathlib import Path

from avacom_actualizacion import cli, llaves
from avacom_actualizacion.dominio_nodo import errores, firma
from avacom_actualizacion.dominio_nodo import paquete as dom_paquete
from avacom_actualizacion.emision import ErrorDeEmision, emitir, verificar

RAIZ = Path(__file__).resolve().parents[1]
FRASE = "una frase de paso larga de prueba"


def backend_falso(raiz: Path) -> Path:
    archivos = {
        "reporting/dominio/boletin.py": b'"""Boletin."""\nVERSION = "1.4.0"\n',
        "reporting/migrations/0004_boletin.py": b"from django.db import migrations\n\n\nclass Migration(migrations.Migration):\n    dependencies = [('reporting', '0003_x')]\n    operations = []\n",
        "reporting/dominio/__pycache__/x.pyc": b"no debe viajar",
        "avacom_lms/modulos.json": b'{"formato": 1, "modulos": {}}\n',
        "biblioteca/contenido.py": b"intocable\n",
    }
    for ruta, contenido in archivos.items():
        destino = raiz / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido)
    return raiz


def descripcion(**cambios) -> dict:
    d = {
        "paquete_id": "17171717-0002-4000-8000-000000000002", "nombre": "Reportes 1.4.0", "version_producto": "2.13.0", "version_minima": "2.12.0", "nota": "Parche.",
        "requisitos": {"contrato_biblioteca": 2, "cliente_minimo": "2.12.0", "espacio_bytes": 0},
        "modulos": [{"nombre": "reporting", "version": "1.4.0", "version_datos": 4, "version_contrato": 1, "serie": 7, "requiere": {"nodo": 1},
                     "migraciones": [{"nombre": "0004_boletin", "reverso": "0003_x"}], "archivos": ["reporting/dominio/", "reporting/migrations/0004_boletin.py"]}],
        "archivos_extra": ["avacom_lms/modulos.json"],
    }
    d.update(cambios)
    return d


class EmisionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.origen = backend_falso(Path(self._tmp.name) / "backend")
        self.privada, self.publica = firma.par_nuevo()

    def test_lo_que_se_emite_lo_acepta_el_nodo(self):
        datos, manifiesto = emitir(descripcion(), self.origen, "upd-test-1", self.privada, ahora_ms=1_790_000_000_000)
        paquete = dom_paquete.verificar(datos, {"upd-test-1": self.publica})
        self.assertEqual(paquete.kid, "upd-test-1")
        self.assertEqual(paquete.manifiesto.serie, 7)
        rutas = sorted(a.ruta for a in paquete.manifiesto.archivos)
        self.assertEqual(rutas, ["avacom_lms/modulos.json", "reporting/dominio/boletin.py", "reporting/migrations/0004_boletin.py"])    # sin __pycache__ y sin biblioteca
        self.assertEqual(dict(paquete.archivos())["reporting/dominio/boletin.py"], (self.origen / "reporting/dominio/boletin.py").read_bytes())
        self.assertEqual(manifiesto.requisitos.cliente_minimo, "2.12.0")

    def test_es_determinista_con_el_mismo_instante_y_la_misma_llave(self):
        a, _ = emitir(descripcion(), self.origen, "upd-test-1", self.privada, ahora_ms=1_790_000_000_000)
        b, _ = emitir(descripcion(), self.origen, "upd-test-1", self.privada, ahora_ms=1_790_000_000_000)
        self.assertEqual(a, b)

    def test_un_byte_cambiado_en_cualquier_parte_se_rechaza(self):
        datos, _ = emitir(descripcion(), self.origen, "upd-test-1", self.privada, ahora_ms=1_790_000_000_000)
        azar = random.Random(20261021)
        aceptadas = 0
        for _ in range(2000):
            sucio = bytearray(datos)
            sucio[azar.randrange(len(sucio))] ^= azar.randrange(1, 256)
            try:
                dom_paquete.verificar(bytes(sucio), {"upd-test-1": self.publica})
                aceptadas += 1
            except errores.PaqueteRechazado:
                pass
        self.assertEqual(aceptadas, 0)

    def test_una_llave_ajena_no_abre_el_paquete(self):
        datos, _ = emitir(descripcion(), self.origen, "upd-test-1", self.privada)
        _, otra_publica = firma.par_nuevo()
        with self.assertRaises(ErrorDeEmision) as e:
            verificar(datos, {"upd-test-1": otra_publica})
        self.assertIn("firma_invalida", str(e.exception))
        with self.assertRaises(ErrorDeEmision) as e:
            verificar(datos, {"upd-test-2": self.publica})
        self.assertIn("kid_desconocido", str(e.exception))

    def test_el_emisor_se_niega_a_emitir_lo_que_el_nodo_rechazaria(self):
        casos = {
            "una ruta que se sale": descripcion(modulos=[{**descripcion()["modulos"][0], "archivos": ["reporting/../manage.py"]}]),
            "un archivo de la biblioteca": descripcion(modulos=[{**descripcion()["modulos"][0], "archivos": ["biblioteca/contenido.py"]}]),
            "una app que el paquete no declara": descripcion(modulos=[{**descripcion()["modulos"][0], "archivos": ["acceso/x.py"]}]),
            "un archivo que no existe": descripcion(modulos=[{**descripcion()["modulos"][0], "archivos": ["reporting/no_existe.py"]}]),
            "una carpeta que no existe": descripcion(modulos=[{**descripcion()["modulos"][0], "archivos": ["reporting/nada/"]}]),
            "sin nombre": {k: v for k, v in descripcion().items() if k != "nombre"},
            "una version inventada": descripcion(version_producto="dos punto trece"),
            "un modulo intocable": descripcion(modulos=[{**descripcion()["modulos"][0], "nombre": "biblioteca", "archivos": ["biblioteca/contenido.py"]}]),
        }
        for rotulo, d in casos.items():
            with self.subTest(rotulo):
                with self.assertRaises(ErrorDeEmision):
                    emitir(d, self.origen, "upd-test-1", self.privada)

    def test_no_se_aceptan_archivos_que_no_son_de_codigo_ni_datos(self):
        (self.origen / "reporting" / "dominio" / "programa.exe").write_bytes(b"MZ")
        with self.assertRaises(ErrorDeEmision) as e:
            emitir(descripcion(), self.origen, "upd-test-1", self.privada)
        self.assertIn("extension_prohibida", str(e.exception))


class LlavesTests(unittest.TestCase):
    def test_una_frase_corta_no_crea_la_llave(self):
        with self.assertRaises(llaves.ErrorDeLlave):
            llaves.generar("upd-test-1", "corta", "2026-10-21T00:00:00Z")

    def test_la_privada_abre_con_su_frase_y_no_con_otra(self):
        avkey, pub, publica = llaves.generar("upd-test-1", FRASE, "2026-10-21T00:00:00Z")
        abierta = llaves.abrir(avkey, FRASE)
        self.assertEqual(abierta.publica, publica)
        self.assertEqual(firma.publica_de(abierta.privada), publica)
        with self.assertRaises(llaves.ErrorDeLlave):
            llaves.abrir(avkey, FRASE + "x")
        self.assertEqual(llaves.leer_publica(pub), ("upd-test-1", publica))
        self.assertNotIn(abierta.privada.hex(), avkey.decode("utf-8"))
        self.assertNotIn(abierta.privada.hex(), pub)

    def test_un_avkey_alterado_no_abre(self):
        avkey, _, _ = llaves.generar("upd-test-1", FRASE, "2026-10-21T00:00:00Z")
        d = json.loads(avkey)
        d["kid"] = "upd-test-2"
        with self.assertRaises(llaves.ErrorDeLlave):
            llaves.abrir(json.dumps(d).encode(), FRASE)

    def test_la_entrada_para_el_nodo_la_lee_el_cargador_del_nodo(self):
        from actualizacion.infraestructura import claves as claves_del_nodo
        _, _, publica = llaves.generar("upd-test-1", FRASE, "2026-10-21T00:00:00Z")
        with tempfile.TemporaryDirectory() as tmp:
            archivo = Path(tmp) / "produccion.json"
            archivo.write_text(llaves.entrada_para_el_nodo("upd-test-1", publica), encoding="utf-8")
            self.assertEqual(claves_del_nodo.cargar(archivo), {"upd-test-1": publica})


class LineaDeComandosTests(unittest.TestCase):
    def correr(self, *argumentos):
        salida, errores_ = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(errores_):
            codigo = cli.main(list(argumentos))
        return codigo, salida.getvalue(), errores_.getvalue()

    def test_de_la_llave_al_paquete_verificado(self):
        with tempfile.TemporaryDirectory() as tmp, self.subTest("recorrido completo"):
            tmp = Path(tmp)
            os.environ["AVACOM_FRASE_LLAVE"] = FRASE
            self.addCleanup(os.environ.pop, "AVACOM_FRASE_LLAVE", None)
            codigo, _, err = self.correr("llaves", "nueva", "--kid", "upd-test-1", "--salida", str(tmp / "claves"))
            self.assertEqual(codigo, 0, err)
            codigo, _, _ = self.correr("llaves", "nueva", "--kid", "upd-test-1", "--salida", str(tmp / "claves"))
            self.assertEqual(codigo, 2)                                  # una llave no se sobrescribe
            origen = backend_falso(tmp / "backend")
            (tmp / "paquete.json").write_text(json.dumps(descripcion()), encoding="utf-8")
            salida = tmp / "salida" / "reportes.avupd"
            codigo, texto, err = self.correr("emitir", "--descripcion", str(tmp / "paquete.json"), "--privada", str(tmp / "claves" / "upd-test-1.avkey"),
                                             "--salida", str(salida), "--origen", str(origen))
            self.assertEqual(codigo, 0, err)
            self.assertIn("Paquete emitido", texto)
            codigo, texto, err = self.correr("verificar", str(salida), "--publica", str(tmp / "claves" / "upd-test-1.pub"))
            self.assertEqual(codigo, 0, err)
            self.assertIn("Paquete válido", texto)
            codigo, texto, _ = self.correr("ver", str(salida))
            self.assertEqual(codigo, 0)
            self.assertIn("reporting", texto)
            codigo, texto, _ = self.correr("llaves", "nodo", "--publica", str(tmp / "claves" / "upd-test-1.pub"))
            self.assertEqual(codigo, 0)
            self.assertEqual(json.loads(texto)["claves"][0]["kid"], "upd-test-1")
            # no se pisa un paquete ya emitido
            codigo, _, err = self.correr("emitir", "--descripcion", str(tmp / "paquete.json"), "--privada", str(tmp / "claves" / "upd-test-1.avkey"),
                                         "--salida", str(salida), "--origen", str(origen))
            self.assertEqual(codigo, 2)
            # un paquete alterado en disco no verifica
            sucio = bytearray(salida.read_bytes())
            sucio[len(sucio) // 2] ^= 0xFF
            salida.write_bytes(bytes(sucio))
            codigo, _, err = self.correr("verificar", str(salida), "--publica", str(tmp / "claves" / "upd-test-1.pub"))
            self.assertEqual(codigo, 2)


class HigieneTests(unittest.TestCase):
    """El emisor no trae llaves ni el emisor de pruebas del nodo, y el instalador no lo copia."""

    def test_ningun_archivo_del_emisor_trae_una_llave_ni_la_semilla_de_desarrollo(self):
        for a in RAIZ.rglob("*"):
            if not a.is_file() or "__pycache__" in a.parts or a.suffix in (".pyc", ".avkey", ".avupd"):
                continue
            if a.name == "test_emisor.py":
                continue                                                  # esta prueba nombra los patrones que busca
            texto = a.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn("avacom-actualizacion-desarrollo", texto, a.name)
            self.assertNotRegex(texto, r"BEGIN (EC |RSA |OPENSSH )?PRIVATE KEY", a.name)
            self.assertNotRegex(texto, r"(?m)^\s*(from|import)\s+actualizacion\.tests|^\s*from\s+actualizacion\s+import\s+tests", a.name)
        self.assertEqual([p for p in RAIZ.rglob("*.avkey")], [])

    def test_el_instalador_no_lo_copia(self):
        script = (RAIZ.parents[1] / "installer" / "build" / "Build-Installer.ps1").read_text(encoding="utf-8")
        # El instalador sólo copia backend\, App y Runtime: tools\ no está entre sus orígenes.
        self.assertNotRegex(script, r"tools\\actualizacion")
        self.assertTrue(re.search(r"'backend'|backend\\", script))


if __name__ == "__main__":
    unittest.main()

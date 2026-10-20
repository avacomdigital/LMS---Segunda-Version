"""El registro de emisiones: sólo añadir, con la cadena de hashes (LIC-E-06)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from avacom_licencias.registro import GENESIS, Registro, RegistroAlterado


def renglon(i: int, licencia_id: str = "L1", serie: int = 1, nonce: str = "aa") -> dict:
    return {"accion": "emitir", "licencia_id": licencia_id, "serie": serie, "aula": f"Aula {i}", "nonce": nonce + str(i), "sha256_licencia": "f" * 64}


class RegistroTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ruta = Path(self._tmp.name) / "datos" / "registro.jsonl"
        self.registro = Registro(self.ruta)

    def test_un_registro_nuevo_esta_integro_y_vacio(self):
        self.assertEqual(self.registro.verificar(), (True, "La cadena está íntegra.", 0))
        self.assertEqual(self.registro.renglones(), [])
        self.assertEqual(self.registro.ultima_serie("L1"), 0)

    def test_cada_renglon_encadena_al_anterior(self):
        a = self.registro.anadir(renglon(1))
        b = self.registro.anadir(renglon(2, serie=2))
        c = self.registro.anadir(renglon(3, serie=3))
        self.assertEqual((a["n"], b["n"], c["n"]), (1, 2, 3))
        self.assertEqual(a["previo"], GENESIS)
        self.assertEqual((b["previo"], c["previo"]), (a["hash"], b["hash"]))
        self.assertEqual(self.registro.verificar(), (True, "La cadena está íntegra.", 3))

    def test_alterar_un_renglon_rompe_la_cadena_y_no_se_sigue_escribiendo(self):
        self.registro.anadir(renglon(1))
        self.registro.anadir(renglon(2))
        lineas = self.ruta.read_text(encoding="utf-8").splitlines()
        cambiado = json.loads(lineas[0])
        cambiado["aula"] = "Otra aula"
        self.ruta.write_text(json.dumps(cambiado) + "\n" + lineas[1] + "\n", encoding="utf-8")
        bien, mensaje, _ = self.registro.verificar()
        self.assertFalse(bien)
        self.assertIn("renglón 1", mensaje)
        with self.assertRaises(RegistroAlterado):
            self.registro.anadir(renglon(3))

    def test_quitar_o_reordenar_renglones_rompe_la_cadena(self):
        for i in (1, 2, 3):
            self.registro.anadir(renglon(i, serie=i))
        lineas = self.ruta.read_text(encoding="utf-8").splitlines()
        self.ruta.write_text("\n".join([lineas[0], lineas[2]]) + "\n", encoding="utf-8")
        self.assertFalse(self.registro.verificar()[0])
        self.ruta.write_text("\n".join([lineas[1], lineas[0], lineas[2]]) + "\n", encoding="utf-8")
        self.assertFalse(self.registro.verificar()[0])

    def test_un_renglon_ilegible_se_dice(self):
        self.registro.anadir(renglon(1))
        with self.ruta.open("a", encoding="utf-8") as archivo:
            archivo.write("esto no es json\n")
        bien, mensaje, _ = self.registro.verificar()
        self.assertFalse(bien)
        self.assertIn("ilegible", mensaje)

    def test_consultas(self):
        self.registro.anadir(renglon(1, "L1", 1, "aa"))
        self.registro.anadir(renglon(2, "L1", 2, "bb"))
        self.registro.anadir(renglon(3, "L2", 1, "cc"))
        self.assertEqual(self.registro.ultima_serie("L1"), 2)
        self.assertEqual(self.registro.ultima_serie("L2"), 1)
        self.assertEqual(self.registro.ultima_serie("nadie"), 0)
        self.assertEqual(len(self.registro.de_licencia("L1")), 2)
        self.assertEqual(len(self.registro.por_nonce("bb2")), 1)
        self.assertEqual(len(self.registro.de_aula("aula 3")), 1)


if __name__ == "__main__":
    unittest.main()

"""El modo guiado: un menú que arma los mismos comandos con preguntas (LIC-E-01…03)."""
from __future__ import annotations

import unittest
from unittest import mock

from avacom_licencias import cli
from avacom_licencias.dominio_nodo import huella

from .apoyo import BaseConCarpeta, NodoDePrueba, correr

OTROS = {
    huella.F_MACHINE_GUID: "11111111-2222-4333-8444-555555555555", huella.F_SMBIOS_UUID: "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE",
    huella.F_PLACA: "NUEVA-PLACA-0042-XX", huella.F_CHASIS: "CHASIS-NUEVO-7788", huella.F_PROCESADOR: "BFEBFBFF000A0671",
}


class GuiadoTests(BaseConCarpeta):
    def guiado(self, entradas: list[str]):
        with mock.patch.object(cli, "REGISTRO_POR_OMISION", self.registro):
            return correr([], entradas=entradas)

    def test_emitir_desde_el_menu(self):
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        r = self.guiado(["2", f'"{sol}"', str(self.privada), "1", "Colegio Guiado", "2027-10-31", str(self.salida), "EMITIR", "", "0"])
        self.assertEqual(r.codigo, 0, r.error)
        self.assertIn("Licencia emitida y verificada", r.salida)
        lic = self.leer(self.licencias()[0])
        self.assertEqual((lic.aula, lic.serie), ("Colegio Guiado", 1))

    def test_una_ruta_arrastrada_con_comillas_se_limpia(self):
        sol = self.guardar("sol con espacios.avreq", self.nodo.solicitud())
        r = self.guiado(["1", f'"{sol}"', "", "0"])
        self.assertEqual(r.codigo, 0, r.error)
        self.assertIn("SOLICITUD", r.salida)

    def test_sin_la_palabra_el_menu_no_firma(self):
        sol = self.guardar("sol.avreq", self.nodo.solicitud())
        r = self.guiado(["2", str(sol), str(self.privada), "1", "", "2027-10-31", str(self.salida), "no", "", "0"])
        self.assertEqual(r.codigo, 0)
        self.assertIn("Cancelado", r.salida)
        self.assertEqual(self.licencias(), [])

    def test_una_opcion_que_no_existe(self):
        r = self.guiado(["9", "0"])
        self.assertEqual(r.codigo, 0)
        self.assertIn("no existe", r.salida)

    def test_un_error_no_cierra_la_herramienta(self):
        r = self.guiado(["1", str(self.dir / "no-existe.avreq"), "", "0"])
        self.assertEqual(r.codigo, 0)
        self.assertIn("No se encontró", r.error)
        self.assertIn("AVACOM · Emisor de Licencias", r.salida)

    def test_cambio_de_computador_sin_liberacion(self):
        primera = self.guardar("viejo.avreq", self.nodo.solicitud())
        self.assertEqual(self.emitir(primera).codigo, 0)
        id_anterior = self.leer(self.licencias()[0]).id
        nuevo = NodoDePrueba(valores=OTROS)
        sol = self.guardar("nuevo.avreq", nuevo.solicitud())
        r = self.guiado(["3", str(sol), str(self.privada), "1", "", "2027-10-31", id_anterior, "", "45", str(self.salida / "n"), "EMITIR", "", "0"])
        self.assertEqual(r.codigo, 0, r.error)
        self.assertIn("PENDIENTE", r.salida)
        pendiente = self.leer(next((self.salida / "n").glob("*.avlic")))
        self.assertEqual((pendiente.id, pendiente.serie, pendiente.liberacion_dias), (id_anterior, 2, 45))

    def test_verificar_desde_el_menu(self):
        self.assertEqual(self.emitir(self.guardar("sol.avreq", self.nodo.solicitud())).codigo, 0)
        r = self.guiado(["4", str(self.licencias()[0]), str(self.publica), "", "", "0"])
        self.assertEqual(r.codigo, 0, r.error)
        self.assertIn("La firma es válida", r.salida)

    def test_el_fin_de_la_entrada_cierra_sin_error(self):
        r = self.guiado([])
        self.assertEqual(r.codigo, 0)


if __name__ == "__main__":
    unittest.main()

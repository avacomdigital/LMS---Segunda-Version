"""
La cola de medios nunca tumba el nodo: sin carpeta donde guardar (permisos, disco) se apaga sola y lo dice, y un fallo al construirla ni siquiera impide arrancar.
El ensayo del instalador lo encontró con un backend que no arrancaba porque la carpeta de la caché no era accesible.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

from django.test import TestCase

from .. import servicio
from ..aplicacion.config import Config
from ..infraestructura import contenedor, programador


class SinCarpetaTests(TestCase):
    def carpeta_imposible(self) -> str:
        """Una ruta que no se puede crear: cuelga de un archivo."""
        base = tempfile.mkdtemp(prefix="avacom-cola-robustez-")
        archivo = Path(base) / "es-un-archivo"
        archivo.write_text("x")
        self.addCleanup(lambda: [p.unlink() for p in Path(base).iterdir()] and Path(base).rmdir())
        return str(archivo / "CacheMedios")

    def test_sin_carpeta_la_cola_se_construye_apagada_y_dice_por_que(self):
        servidor = contenedor._construir(Config(carpeta=self.carpeta_imposible()))
        self.assertFalse(servidor.cfg.activa)
        self.assertIn("No se pudo preparar la carpeta de la caché de medios", servidor.motivo_apagada)
        estado = servidor.estado()
        self.assertEqual((estado["activa"], bool(estado["motivo_apagada"])), (False, True))

    def test_apagada_sirve_como_siempre(self):
        servidor = contenedor._construir(Config(carpeta=self.carpeta_imposible()))
        with mock.patch.object(contenedor, "_servidor", servidor):
            sirvio = []
            servicio.abrir_medio(fuente="ejemplo", curso_ref="c", media_ref="m", ruta=None, rango=None, metodo="GET", modulo="aula", prioridad=2,
                                 directo=lambda: sirvio.append(True) or object())
        self.assertEqual(sirvio, [True])

    def test_si_la_cola_ni_siquiera_se_puede_construir_el_medio_se_sirve_como_siempre(self):
        sirvio = []
        with mock.patch.object(contenedor, "servidor", side_effect=PermissionError("Acceso denegado")):
            servicio.abrir_medio(fuente=None, curso_ref="c", media_ref="m", ruta=None, rango=None, metodo="GET", modulo="aula", prioridad=2,
                                 directo=lambda: sirvio.append(True) or object())
            self.assertIsNone(servicio.medir_medio(fuente=None, curso_ref="c", media_ref="m", tope_bytes=1, modulo="estudio", prioridad=4))
            self.assertEqual(servicio.preparar_medios([("m", "")], fuente=None, curso_ref="c", modulo="aula", contexto_ref="s", prioridad=0),
                             {"encolados": 0, "omitidos": 1})
        self.assertEqual(sirvio, [True])

    def test_arrancar_los_hilos_no_lanza_aunque_la_cola_no_se_pueda_construir(self):
        with mock.patch.object(programador, "servidor", side_effect=PermissionError("Acceso denegado")):
            self.assertEqual(programador.iniciar(), [])

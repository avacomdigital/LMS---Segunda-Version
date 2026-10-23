"""
P-23 · Integridad del despliegue: lo que el nodo hace con la señal que deja el `Host` (`Config\\integridad.json`).

  · `SenalDeIntegridad` (unidad): sólo «alterada» avisa; lo ausente, ilegible o de otra versión no inventa una alarma.
  · Integración con un nodo real (`BaseLicencia`): una señal «alterada» recorre el camino de siempre de la integridad (una observación, UN asiento al día, la bandera `integridad_alterada`)
    y NO degrada nada ni detiene ninguna clase.
  · El contrato de la señal se prueba con un archivo REAL escrito por el Host (`fixtures/senal_integridad_*.json`, capturado con `Avacom.Ops.Host.exe verificar-integridad`).
"""
import json
import shutil
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from audit.models import Bitacora
from licenciamiento import models as m
from licenciamiento.dominio import catalogos as cat
from licenciamiento.dominio.politica import DIA_MS
from licenciamiento.infraestructura.anclas import AnclasDeLicencia
from licenciamiento.infraestructura.integridad import SenalDeIntegridad

from .base import BaseLicencia

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def senal(**cambios) -> dict:
    base = {"version": 1, "verificado": "2026-10-22T17:00:00Z", "estado": "alterada", "firma": "ok", "kid": "upd-2026-1", "version_producto": "2.16.0", "archivos_comprobados": 5871,
            "hallazgos": [{"tipo": "backend", "detalle": "modificado", "cantidad": 1, "ejemplos": ["Backend/licenciamiento/servicios.py"]}]}
    base.update(cambios)
    return base


class SenalDeIntegridadTests(SimpleTestCase):
    def setUp(self):
        self.carpeta = Path(tempfile.mkdtemp(prefix="avacom-senal-"))
        self.addCleanup(shutil.rmtree, self.carpeta, True)
        self.ruta = self.carpeta / "integridad.json"
        self.senal = SenalDeIntegridad(self.ruta)

    def poner(self, datos) -> None:
        self.ruta.write_text(datos if isinstance(datos, str) else json.dumps(datos), encoding="utf-8")

    def test_sin_archivo_no_avisa(self):
        self.assertEqual(self.senal.alteradas(), ())

    def test_solo_alterada_avisa_y_dice_que_parte(self):
        self.poner(senal(hallazgos=[{"tipo": "backend", "detalle": "modificado", "cantidad": 2, "ejemplos": []}, {"tipo": "nativo", "detalle": "falta", "cantidad": 1, "ejemplos": []},
                                    {"tipo": "backend", "detalle": "sobra", "cantidad": 1, "ejemplos": []}]))
        self.assertEqual(self.senal.alteradas(), ("despliegue:backend", "despliegue:nativo"))

    def test_los_demas_estados_no_avisan(self):
        for estado in ("ok", "sin_firma", "no_verificable"):
            self.poner(senal(estado=estado))
            self.assertEqual(self.senal.alteradas(), (), estado)

    def test_alterada_sin_detalle_legible_sigue_siendo_una_alteracion(self):
        self.poner(senal(hallazgos=[]))
        self.assertEqual(self.senal.alteradas(), ("despliegue:otro",))
        self.poner(senal(hallazgos=[{"tipo": "<script>", "detalle": "x"}, "raro"]))
        self.assertEqual(self.senal.alteradas(), ("despliegue:otro",))             # un tipo desconocido no se copia al asiento tal cual

    def test_lo_que_no_se_entiende_no_inventa_una_alarma(self):
        for texto in ("no es json", "[1, 2]", json.dumps(senal(version=2)), json.dumps({"estado": "alterada"}), "x" * (300 * 1024)):
            self.poner(texto)
            self.assertEqual(self.senal.alteradas(), (), texto[:20])

    def test_se_relee_cuando_el_host_la_reescribe(self):
        self.poner(senal())
        self.assertEqual(self.senal.alteradas(), ("despliegue:backend",))
        self.poner(senal(estado="ok", hallazgos=[]))
        self.assertEqual(self.senal.alteradas(), ())                                # la alteración se corrigió y el Host lo anotó en el siguiente arranque
        self.ruta.unlink()
        self.assertEqual(self.senal.alteradas(), ())

    def test_la_senal_real_del_host_cumple_el_contrato(self):
        real = json.loads((FIXTURES / "senal_integridad_alterada.json").read_text(encoding="utf-8-sig"))
        self.assertEqual({"version", "verificado", "estado", "firma", "kid", "version_producto", "archivos_comprobados", "hallazgos"}, set(real))
        self.poner(real)
        self.assertEqual(self.senal.alteradas(), ("despliegue:backend",))
        sana = json.loads((FIXTURES / "senal_integridad_ok.json").read_text(encoding="utf-8-sig"))
        self.assertEqual((sana["estado"], sana["firma"], sana["hallazgos"]), ("ok", "ok", []))
        self.poner(sana)
        self.assertEqual(self.senal.alteradas(), ())

    def test_la_senal_no_lleva_datos_de_personas_ni_de_licencias(self):
        crudo = (FIXTURES / "senal_integridad_alterada.json").read_text(encoding="utf-8-sig").lower()
        for prohibido in ("licencia", "huella", "usuario", "alumno", "docente", "password", "clave"):
            self.assertNotIn(prohibido, crudo)


class IntegridadDelDespliegueTests(BaseLicencia):
    def setUp(self):
        super().setUp()
        self.ruta = Path(self.carpeta) / "integridad.json"
        self.s.anclas = AnclasDeLicencia(self.s.almacen, self.s.nodo, None, SenalDeIntegridad(self.ruta))      # lo que el contenedor arma en un nodo instalado

    def poner(self, **cambios) -> None:
        self.ruta.write_text(json.dumps(senal(**cambios)), encoding="utf-8")

    def test_una_senal_alterada_avisa_asienta_una_vez_y_no_detiene_nada(self):
        self.activar_ok()
        self.evaluar("arranque")
        self.assertNotIn("integridad_alterada", self.evaluar("tick").estado.banderas)
        self.poner()
        e = self.evaluar("tick")
        self.assertIn("integridad_alterada", e.estado.banderas)
        self.assertEqual(e.estado.estado, "activa")                                                   # es un aviso: la licencia sigue activa
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_INTEGRIDAD).count(), 1)
        self.assertEqual(m.Observacion.objects.filter(tipo=cat.O_INTEGRIDAD).get().detalle["anclas"], ["despliegue:backend"])
        self.assertEqual(self.docente.get("/api/acceso/yo/").status_code, 200)                       # el núcleo sigue igual
        self.evaluar("tick")
        self.evaluar("tick")
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_INTEGRIDAD).count(), 1)                # UN asiento al día, no uno por ciclo
        self.reloj.avanzar(25 * 3600 * 1000)
        self.evaluar("tick")
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_INTEGRIDAD).count(), 2)                # si sigue alterada, vuelve a asentarse al día siguiente

    def test_una_alteracion_no_degrada_un_nodo_en_gracia_ni_en_evaluacion(self):
        self.poner()
        e = self.evaluar("arranque")
        self.assertEqual(e.estado.estado, "sin_licencia")
        self.assertIn("integridad_alterada", e.estado.banderas)
        self.reloj.avanzar(10 * DIA_MS)
        self.assertEqual(self.evaluar("tick").estado.estado, "sin_licencia")
        self.assertEqual(self.admin.get("/api/acceso/yo/").status_code, 200)

    def test_sin_senal_no_cambia_nada_y_el_asiento_no_lleva_rutas(self):
        self.evaluar("arranque")
        self.assertFalse(Bitacora.objects.filter(accion=cat.A_INTEGRIDAD).exists())
        self.poner()
        self.evaluar("tick")
        asiento = Bitacora.objects.get(accion=cat.A_INTEGRIDAD)
        texto = json.dumps([asiento.valor_nuevo, asiento.valor_anterior, asiento.motivo, asiento.objeto_id], default=str)
        self.assertIn("despliegue:backend", texto)                                                   # el asiento dice QUÉ PARTE...
        self.assertNotIn("servicios.py", texto)                                                      # ...no qué archivo ni el contenido

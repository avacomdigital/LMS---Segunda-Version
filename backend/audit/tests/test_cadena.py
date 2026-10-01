"""
019-04 / 019-07 · verificación de la cadena, detección de saltos (con `tools/romper_cadena.py`), rotación por tamaño,
estado y los eventos `auditoria.*`.
"""
from __future__ import annotations

import json
from pathlib import Path

from django.db import connection
from django.test import TestCase, override_settings

from tools import romper_cadena

from .. import servicios
from ..aplicacion import anexar as app
from ..aplicacion import estado, rotar, verificar
from ..dominio import huella
from ..dominio import tramo as dom_tramo
from ..infraestructura import archivos, eventos, firma, triggers
from ..models import Bitacora, BitacoraTramo, EventoSalida
from ..pruebas import LogsDePrueba


def sembrar(n: int = 5) -> list[Bitacora]:
    return [servicios.anexar("u-1", "prueba.cadena", "t", str(i), nuevo={"i": i}) for i in range(n)]


class VerificarTests(LogsDePrueba, TestCase):
    def test_una_cadena_integra_queda_verificada_con_asiento_evento_y_linea(self):
        sembrar()
        r = verificar.verificar_cadena()
        self.assertEqual((r["estado"], r["salto_en"]), ("verificada", None))
        self.assertGreaterEqual(r["verificados"], 6)
        tramo = app.tramo_activo(bloquear=False)
        self.assertEqual(tramo.estado, "verificada")
        self.assertIsNotNone(tramo.verificado_en)
        asiento = Bitacora.objects.get(accion="auditoria.cadena_verificada")
        self.assertEqual(asiento.actor_tipo, "sistema")
        self.assertTrue(EventoSalida.objects.filter(tipo_evento=eventos.EV_CADENA_VERIFICADA).exists())
        self.assertLogged(evento="auditoria.cadena_verificada", canal="auditoria")
        self.assertNoLogged(nivel="ERROR")
        # El asiento de verificación es posterior a lo verificado; la siguiente verificación lo cubre sin volver a empezar.
        self.assertEqual(tramo.verificado_hasta, asiento.secuencia - 1)
        r2 = verificar.verificar_cadena()
        self.assertEqual(r2["estado"], "verificada")
        self.assertEqual(app.tramo_activo(bloquear=False).verificado_hasta, asiento.secuencia)

    def test_con_menos_de_dos_asientos_no_se_verifica(self):
        from .test_bitacora import vaciar_bitacora
        vaciar_bitacora()
        self.assertEqual(verificar.verificar_cadena()["estado"], "insuficiente")

    def test_romper_un_asiento_da_salto_en_la_secuencia_correcta(self):
        filas = sembrar()
        objetivo = filas[2]
        romper_cadena.alterar(objetivo.secuencia, "motivo", "alterado")
        r = verificar.verificar_cadena()
        self.assertEqual((r["estado"], r["salto_en"], r["causa"]), ("con_salto", objetivo.secuencia, dom_tramo.CAUSA_HUELLA))
        tramo = BitacoraTramo.objects.get(abierta=True)
        self.assertEqual((tramo.estado, tramo.salto_en_secuencia, tramo.salto_causa), ("con_salto", objetivo.secuencia, dom_tramo.CAUSA_HUELLA))
        salto = Bitacora.objects.get(accion="auditoria.salto_detectado")
        self.assertEqual((salto.resultado, salto.valor_nuevo["salto_en"]), ("fallido", objetivo.secuencia))
        evento = EventoSalida.objects.get(tipo_evento=eventos.EV_SALTO_DETECTADO)
        self.assertEqual(evento.carga["prioridad"], "alta")
        self.assertLogged(evento="auditoria.salto_detectado", nivel="ERROR", canal="auditoria")
        self.assertEqual(estado.estado()["salto"]["secuencia"], objetivo.secuencia)

    def test_borrar_un_asiento_da_hueco_y_cambiar_la_huella_previa_rompe_el_enlace(self):
        filas = sembrar()
        romper_cadena.borrar(filas[1].secuencia)
        r = verificar.verificar_cadena()
        self.assertEqual((r["estado"], r["salto_en"], r["causa"]), ("con_salto", filas[1].secuencia, dom_tramo.CAUSA_HUECO))

    def test_los_triggers_ausentes_se_detectan(self):
        sembrar(2)
        romper_cadena.quitar_triggers()
        try:
            r = verificar.verificar_cadena()
            self.assertEqual((r["estado"], r["causa"]), ("con_salto", dom_tramo.CAUSA_TRIGGERS))
        finally:
            romper_cadena.reponer_triggers()
        self.assertTrue(triggers.completos(connection))

    def test_una_cabeza_adulterada_se_detecta(self):
        sembrar(2)
        BitacoraTramo.objects.filter(abierta=True).update(huella_cierre="f" * 64)
        r = verificar.verificar_cadena()
        self.assertEqual((r["estado"], r["causa"]), ("con_salto", dom_tramo.CAUSA_CABEZA))

    def test_la_verificacion_por_bloques_recorre_todo(self):
        sembrar(12)
        r = verificar.verificar_cadena(bloque=4)
        self.assertEqual(r["estado"], "verificada")
        self.assertGreaterEqual(r["verificados"], 13)


class RotarTests(LogsDePrueba, TestCase):
    def test_rotar_cierra_el_tramo_escribe_el_archivo_firmado_y_abre_uno_enlazado(self):
        filas = sembrar(4)
        viejo = app.tramo_activo(bloquear=False)
        r = rotar.rotar(motivo="prueba")
        cerrado = BitacoraTramo.objects.get(pk=viejo.pk)
        self.assertEqual((cerrado.estado, cerrado.abierta, cerrado.hasta_secuencia), ("rotada", False, filas[-1].secuencia))
        self.assertTrue(cerrado.rotado_en and cerrado.archivo and cerrado.firma)
        nuevo = app.tramo_activo(bloquear=False)
        self.assertNotEqual(nuevo.pk, viejo.pk)
        self.assertEqual(nuevo.desde_secuencia, cerrado.hasta_secuencia + 1)
        primero = Bitacora.objects.get(secuencia=nuevo.desde_secuencia)
        self.assertEqual((primero.accion, primero.huella_previa, primero.tramo_id), ("auditoria.bitacora_rotada", cerrado.huella_cierre, nuevo.pk))
        # Las filas no se borran (INV-027) y la cadena entera sigue verificando.
        self.assertEqual(Bitacora.objects.filter(tramo=cerrado).count(), cerrado.hasta_secuencia - cerrado.desde_secuencia + 1)
        self.assertEqual(verificar.verificar_cadena(todos=True)["estado"], "verificada")
        # Archivo: manifiesto firmado y un asiento por línea.
        ruta = Path(r["archivo"])
        self.assertTrue(ruta.exists())
        with ruta.open(encoding="utf-8") as f:
            lineas = [json.loads(l) for l in f if l.strip()]
        manifiesto, firma_archivo = lineas[0]["manifiesto"], lineas[0]["firma"]
        self.assertTrue(firma.verificar(manifiesto, firma_archivo))
        self.assertFalse(firma.verificar({**manifiesto, "total": 999}, firma_archivo))
        self.assertEqual((manifiesto["desde"], manifiesto["hasta"], manifiesto["total"]), (cerrado.desde_secuencia, cerrado.hasta_secuencia, len(lineas) - 1))
        self.assertEqual([l["secuencia"] for l in lineas[1:]], list(range(cerrado.desde_secuencia, cerrado.hasta_secuencia + 1)))
        self.assertTrue(EventoSalida.objects.filter(tipo_evento=eventos.EV_BITACORA_ROTADA).exists())
        self.assertLogged(evento="auditoria.bitacora_rotada")

    def test_no_se_rota_un_tramo_con_salto(self):
        filas = sembrar(3)
        romper_cadena.alterar(filas[1].secuencia, "motivo", "x")
        from ..dominio import errores
        with self.assertRaises(errores.CadenaConSalto):
            rotar.rotar()
        self.assertEqual(BitacoraTramo.objects.filter(estado="rotada").count(), 0)

    def test_rotar_si_supera_respeta_el_umbral(self):
        sembrar(3)
        with override_settings(AVACOM_LMS_AUDITORIA_UMBRAL_MB=100):
            self.assertIsNone(rotar.rotar_si_supera())
        with override_settings(AVACOM_LMS_AUDITORIA_UMBRAL_MB=0):
            self.assertIsNotNone(rotar.rotar_si_supera())
        self.assertEqual(BitacoraTramo.objects.filter(estado="rotada").count(), 1)

    def test_el_estado_resume_cabeza_tramo_umbral_y_triggers(self):
        sembrar(2)
        e = estado.estado()
        cabeza = app.tramo_activo(bloquear=False)
        self.assertEqual(e["cabeza"]["secuencia"], cabeza.hasta_secuencia)
        self.assertEqual(e["cabeza"]["huella"], estado.abreviada(cabeza.huella_cierre))
        self.assertEqual((e["salto_detectado"], e["triggers_ok"], e["tramos"]), (False, True, 1))
        self.assertGreater(e["tamano_bytes"], 0)
        self.assertEqual(e["umbral_bytes"], 100 * 1024 * 1024)
        self.assertEqual(e["total_asientos"], Bitacora.objects.count())
        self.assertEqual(huella.LARGO, 64)
        self.assertTrue(str(archivos.carpeta_auditoria()).endswith("auditoria"))

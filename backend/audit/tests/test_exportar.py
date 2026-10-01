"""
019-06 · exportar un tramo firmado: permiso `audit.export` MÁS autorización de salida vigente (escalada por una operación),
rango verificado, archivo con manifiesto firmado, asiento `auditoria.tramo_exportado`, consumo de la escalada (ESC-03),
denegación sin archivo (TST-072, VER-04) y descarga.
"""
from __future__ import annotations

import json
from pathlib import Path

from tools import romper_cadena

from .. import servicios
from ..infraestructura import firma
from ..models import Bitacora, BitacoraTramo, EventoSalida
from .test_api import BaseApiAuditoria


class ExportarTests(BaseApiAuditoria):
    def tramo(self) -> BitacoraTramo:
        return BitacoraTramo.objects.get(abierta=True)

    def test_tst_072_sin_autorizacion_de_salida_no_se_genera_archivo_y_queda_el_intento(self):
        r = self.admin.post("/api/auditoria/exportar/", {"tramo_id": self.tramo().pk, "motivo_codigo": "inspeccion_interna"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "autorizacion_requerida"), r.content)
        denegada = Bitacora.objects.get(accion="auditoria.exportacion_denegada")
        self.assertEqual((denegada.resultado, denegada.usuario_id, denegada.valor_nuevo["causa"]), ("denegado", self.admin_id, "autorizacion_requerida"))
        self.assertFalse(Bitacora.objects.filter(accion="auditoria.tramo_exportado").exists())
        from ..infraestructura import archivos
        self.assertFalse(list(archivos.carpeta_exportaciones().glob("exportacion-*.jsonl")) and
                         any(self.admin_id in p.read_text(encoding="utf-8") for p in archivos.carpeta_exportaciones().glob("exportacion-*.jsonl")))
        self.assertFalse(self.admin.get("/api/auditoria/exportaciones/").json()["autorizacion_vigente"])

    def test_el_tecnico_no_exporta_ni_con_escalada(self):
        r = self.tecnico_cliente.post("/api/auditoria/exportar/", {"tramo_id": self.tramo().pk, "motivo_codigo": "soporte_avacom"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "permiso_denegado"))
        self.assertEqual(Bitacora.objects.filter(accion="acceso.denegado", usuario_id=self.tecnico_id).count(), 1)

    def test_con_autorizacion_vigente_se_exporta_un_tramo_firmado_y_la_escalada_se_consume(self):
        for i in range(3):
            servicios.anexar(self.admin_id, "prueba.exportar", "t", str(i))
        self.escalar(self.admin_id, "audit.export")
        self.assertTrue(self.admin.get("/api/auditoria/exportaciones/").json()["autorizacion_vigente"])
        tramo = self.tramo()
        r = self.admin.post("/api/auditoria/exportar/", {"tramo_id": tramo.pk, "motivo_codigo": "auditoria_externa", "motivo_detalle": "visita anual"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        cuerpo = r.json()
        self.assertEqual((cuerpo["desde"], cuerpo["alcance"]), (tramo.desde_secuencia, f"tramo {tramo.desde_secuencia}-{cuerpo['hasta']}"))
        self.assertEqual(cuerpo["mensaje"], f"Queda registrado que exportaste tramo {tramo.desde_secuencia}-{cuerpo['hasta']}.")
        asiento = Bitacora.objects.get(accion="auditoria.tramo_exportado")
        self.assertEqual((asiento.usuario_id, asiento.motivo, asiento.objeto_id), (self.admin_id, "Auditoría externa: visita anual", cuerpo["exportacion_id"]))
        self.assertEqual(asiento.valor_nuevo["total"], cuerpo["total"])
        self.assertTrue(EventoSalida.objects.filter(tipo_evento="auditoria.tramo_exportado.v1").exists())
        # El archivo: manifiesto firmado por el nodo y los asientos del rango.
        ruta = Path(asiento.valor_nuevo["archivo_ruta"])
        with ruta.open(encoding="utf-8") as f:
            lineas = [json.loads(l) for l in f if l.strip()]
        self.assertTrue(firma.verificar(lineas[0]["manifiesto"], lineas[0]["firma"]))
        self.assertEqual(lineas[0]["manifiesto"]["exportado_por"], self.admin_id)
        self.assertEqual([l["secuencia"] for l in lineas[1:]], list(range(cuerpo["desde"], cuerpo["hasta"] + 1)))
        self.assertEqual(len(lineas) - 1, cuerpo["total"])
        self.assertIsNotNone(BitacoraTramo.objects.get(pk=tramo.pk).exportado_en)
        # ESC-03: la autorización valía una operación.
        consumida = Bitacora.objects.get(accion="acceso.escalada.consumida")
        self.assertEqual(consumida.valor_nuevo["operacion"], f"exportacion:{cuerpo['exportacion_id']}")
        self.assertFalse(self.admin.get("/api/auditoria/exportaciones/").json()["autorizacion_vigente"])
        r = self.admin.post("/api/auditoria/exportar/", {"tramo_id": tramo.pk, "motivo_codigo": "auditoria_externa"}, format="json")
        self.assertEqual(r.json()["codigo"], "autorizacion_requerida")
        # Descarga.
        r = self.admin.get(cuerpo["descarga"])
        self.assertEqual(r.status_code, 200)
        contenido = b"".join(r.streaming_content)
        self.assertEqual(contenido.count(b"\n"), len(lineas))
        self.assertEqual(self.tecnico_cliente.get(cuerpo["descarga"]).status_code, 403)
        self.assertEqual(self.admin.get("/api/auditoria/exportaciones/no-existe/descargar/").status_code, 404)
        listado = self.admin.get("/api/auditoria/exportaciones/").json()
        self.assertEqual((listado["exportaciones"][0]["exportacion_id"], listado["exportaciones"][0]["disponible"]), (cuerpo["exportacion_id"], True))
        self.assertTrue(any(m["codigo"] == "requerimiento_legal" for m in listado["motivos"]))

    def test_un_rango_con_salto_no_se_exporta(self):
        filas = [servicios.anexar(self.admin_id, "prueba.exportar", "t", str(i)) for i in range(3)]
        self.escalar(self.admin_id, "audit.export")
        romper_cadena.alterar(filas[1].secuencia, "motivo", "alterado")
        r = self.admin.post("/api/auditoria/exportar/", {"desde": filas[0].secuencia, "hasta": filas[2].secuencia, "motivo_codigo": "inspeccion_interna"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["salto_en"]), (409, "cadena_con_salto", filas[1].secuencia), r.content)
        self.assertFalse(Bitacora.objects.filter(accion="auditoria.tramo_exportado").exists())
        # La escalada sigue vigente: la operación no ocurrió.
        self.assertTrue(self.admin.get("/api/auditoria/exportaciones/").json()["autorizacion_vigente"])

    def test_entrada_invalida(self):
        self.escalar(self.admin_id, "audit.export")
        self.assertEqual(self.admin.post("/api/auditoria/exportar/", {"motivo_codigo": "inspeccion_interna"}, format="json").status_code, 400)
        self.assertEqual(self.admin.post("/api/auditoria/exportar/", {"desde": 5, "hasta": 2, "motivo_codigo": "inspeccion_interna"}, format="json").status_code, 400)
        r = self.admin.post("/api/auditoria/exportar/", {"desde": 1, "hasta": 2, "motivo_codigo": "porque_si"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        self.assertEqual(self.admin.post("/api/auditoria/exportar/", {"desde": 100000, "hasta": 100001, "motivo_codigo": "inspeccion_interna"}, format="json").status_code, 404)

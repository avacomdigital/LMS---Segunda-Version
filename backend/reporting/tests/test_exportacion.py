"""
FUN-146 · exportar un reporte a archivo para entregarlo sin internet y sin teclado: el alcance declarado antes de confirmar, el archivo (xlsx y csv) con la cabecera de BR-083 DENTRO,
las dos fases (autorizar y generar → confirmar), los intentos fallidos que no obligan a generar otra vez, la caducidad de lo que nadie confirma, la política del administrador, lo que
nunca llega a la bitácora (rutas, nombres, contenido) y quién puede exportar qué.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree as ET

from django.test import SimpleTestCase, override_settings

from nodo.pruebas import cola
from .. import models as m
from ..dominio import catalogos as cat
from ..dominio import documento as doc
from ..infraestructura.archivos import EscritorDeArchivos
from ..infraestructura.contenedor import version_del_nodo
from .base import BaseReporting

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def leer_xlsx(contenido: bytes) -> dict[str, list[list]]:
    """Lee un libro xlsx con la biblioteca estándar: `{hoja: [[celdas…]]}` (texto como texto, números como números). Además comprueba que cada parte esté bien formada."""
    z = zipfile.ZipFile(io.BytesIO(contenido))
    assert z.testzip() is None
    for nombre in z.namelist():
        ET.fromstring(z.read(nombre))                                  # todo el XML bien formado
    libro = ET.fromstring(z.read("xl/workbook.xml"))
    relaciones = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    tipos = ET.fromstring(z.read("[Content_Types].xml"))
    declaradas = {o.get("PartName") for o in tipos if o.tag.endswith("Override")}
    hojas: dict[str, list[list]] = {}
    for hoja in libro.find(f"{NS}sheets"):
        destino = "xl/" + relaciones[hoja.get(f"{NS_R}id")]
        assert "/" + destino in declaradas, f"la hoja {destino} no está declarada en [Content_Types].xml"
        filas = []
        for fila in ET.fromstring(z.read(destino)).iter(f"{NS}row"):
            celdas: dict[int, object] = {}
            for c in fila:
                letras = re.match(r"[A-Z]+", c.get("r")).group()
                columna = 0
                for ch in letras:
                    columna = columna * 26 + ord(ch) - 64
                if c.get("t") == "inlineStr":
                    celdas[columna] = "".join(t.text or "" for t in c.iter(f"{NS}t"))
                else:
                    v = c.find(f"{NS}v")
                    celdas[columna] = float(v.text) if v is not None else None
            filas.append([celdas.get(i) for i in range(1, (max(celdas) if celdas else 0) + 1)])
        hojas[hoja.get("name")] = filas
    return hojas


def como_dict(filas: list[list]) -> dict[str, object]:
    """Las filas de la hoja «Resumen» (etiqueta, valor) como diccionario."""
    return {f[0]: f[1] for f in filas if len(f) >= 2 and isinstance(f[0], str) and f[1] is not None}


class BaseExportacion(BaseReporting):
    def exportar(self, reporte: dict, formato: str = "xlsx", destino: str = "carpeta_local", cliente=None, esperado: int = 201, **extra):
        r = (cliente or self.docente).post("/api/reportes/exportaciones/", {"reporte": reporte, "formato": formato, "destino_tipo": destino, **extra}, format="json")
        self.assertEqual(r.status_code, esperado, r.content if not getattr(r, "streaming", False) else b"")
        if esperado != 201:
            return r.json(), b""
        cuerpo = b"".join(r.streaming_content)
        return r, cuerpo

    def alcance(self, reporte: dict, formato: str = "xlsx", cliente=None, esperado: int = 200) -> dict:
        r = (cliente or self.docente).post("/api/reportes/exportaciones/alcance/", {"reporte": reporte, "formato": formato}, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def confirmar(self, exportacion_id: str, cuerpo: dict, cliente=None, esperado: int = 200) -> dict:
        r = (cliente or self.docente).post(f"/api/reportes/exportaciones/{exportacion_id}/confirmar/", cuerpo, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def grupo_con_clases(self):
        self.clase_cerrada([(5, 5), (3, 5), None, (5, 5), (0, 5)])
        return {"tipo": "grupo", "grupo_id": self.grupo["id"]}


class ArchivoTests(BaseExportacion):
    def test_el_archivo_xlsx_trae_su_cabecera_de_corte_e_integracion_dentro(self):
        d = self.grupo_con_clases()
        r, cuerpo = self.exportar(d)
        self.assertTrue(r["Content-Type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
        hojas = leer_xlsx(cuerpo)
        self.assertEqual(list(hojas), ["Resumen", "Alumnos", "Clases"])
        resumen = como_dict(hojas["Resumen"])
        # BR-083 y lo pedido: el nombre del reporte, el grupo, el periodo, quién generó, cuándo, el corte, la integración, el umbral y la versión del nodo
        self.assertEqual(resumen["Reporte"], "Reporte del grupo")
        self.assertEqual(resumen["Grupo"], "Octavo A")
        self.assertEqual(resumen["Periodo"], "2026")
        self.assertEqual(resumen["Generado por"], "Prof. Gómez")
        self.assertRegex(resumen["Generado el"], r"^21 sep 2026 · \d\d:\d\d$")
        self.assertIn("Datos al corte", resumen)
        self.assertIn("21 sep 2026", resumen["Datos al corte"])
        self.assertIn("Esto es lo que había en el nodo a esa hora.", resumen["Datos al corte"])
        self.assertEqual(resumen["Estado de integración"], "Todo sincronizado")
        self.assertEqual(resumen["Umbral de privacidad aplicado"], "No")
        self.assertTrue(resumen["Versión del nodo"])
        self.assertEqual(resumen["Alumnos"], 5.0)
        # los números son números (no texto) y la tabla trae lo mismo que la pantalla
        pantalla = self.rp(f"/grupos/{self.grupo['id']}/")
        alumnos = hojas["Alumnos"]
        self.assertEqual(len(alumnos), 1 + 5)
        self.assertEqual(alumnos[0][0], "Alumno")
        self.assertTrue(all(isinstance(f[1], float) for f in alumnos[1:]))
        self.assertEqual(sorted(f[0] for f in alumnos[1:]), sorted(a["alumno"] for a in pantalla["alumnos"]))
        self.assertEqual(resumen["Promedio de aciertos (%)"], pantalla["totales"]["promedio_aciertos"])
        self.assertTrue(any("Dominio por objetivo: aún no disponible." in str(f) for f in hojas["Resumen"]))

    def test_el_xlsx_es_un_libro_valido_con_encabezado_fijo_filtro_y_anchos(self):
        _, cuerpo = self.exportar(self.grupo_con_clases())
        z = zipfile.ZipFile(io.BytesIO(cuerpo))
        hoja = z.read("xl/worksheets/sheet2.xml").decode()
        self.assertIn('state="frozen"', hoja)
        self.assertIn("<autoFilter", hoja)
        self.assertIn("<cols>", hoja)
        self.assertEqual(sorted(z.namelist())[:3], ["[Content_Types].xml", "_rels/.rels", "docProps/app.xml"])
        self.assertTrue(all(i.compress_type == zipfile.ZIP_DEFLATED for i in z.infolist()))

    def test_misma_entrada_mismos_bytes(self):
        d = self.grupo_con_clases()
        _, a = self.exportar(d)
        _, b = self.exportar(d)
        self.assertEqual(hashlib.sha256(a).hexdigest(), hashlib.sha256(b).hexdigest())

    def test_el_csv_va_en_utf8_con_bom_punto_y_coma_y_coma_decimal(self):
        self.alumno_nuevo("Ñandú Ávila")
        self.clase_cerrada([(5, 5), (2, 5)])
        r, cuerpo = self.exportar({"tipo": "grupo", "grupo_id": self.grupo["id"]}, formato="csv")
        self.assertEqual(r["Content-Type"], "text/csv; charset=utf-8")
        self.assertTrue(cuerpo.startswith(b"\xef\xbb\xbf"))
        texto = cuerpo.decode("utf-8-sig")
        lineas = texto.split("\r\n")
        self.assertEqual(lineas[0], "Reporte del grupo")
        self.assertIn("Reporte;Reporte del grupo", lineas)
        self.assertTrue(any(l.startswith("Datos al corte;") for l in lineas))
        self.assertTrue(any(l.startswith("Estado de integración;Todo sincronizado") for l in lineas))
        self.assertTrue(any(l.startswith("Umbral de privacidad aplicado;No") for l in lineas))
        self.assertTrue(any(l.startswith("Versión del nodo;") for l in lineas))
        self.assertIn("Ñandú Ávila", texto)                                    # tildes y ñ intactas
        fila = next(l for l in lineas if l.startswith("Alumno 01;") or l.startswith("Ñandú"))
        self.assertGreaterEqual(fila.count(";"), 10)
        self.assertRegex(texto, r";\d+,\d+")                                   # coma decimal
        self.assertNotRegex(texto, r";\d+\.\d+;")                               # nunca punto decimal

    def test_un_texto_que_empieza_como_una_formula_no_se_ejecuta_en_el_csv(self):
        self.alumno_nuevo("=SUMA(1;2)")
        self.clase_cerrada([(5, 5), (5, 5)])
        _, cuerpo = self.exportar({"tipo": "grupo", "grupo_id": self.grupo["id"]}, formato="csv")
        texto = cuerpo.decode("utf-8-sig")
        self.assertIn("'=SUMA(1;2)", texto)
        self.assertNotIn(";=SUMA", texto.replace("'=SUMA", ""))
        # y en el xlsx el texto sigue siendo texto
        _, xlsx = self.exportar({"tipo": "grupo", "grupo_id": self.grupo["id"]})
        self.assertIn("=SUMA(1;2)", [f[0] for f in leer_xlsx(xlsx)["Alumnos"]])

    def test_un_reporte_grande_se_escribe_sin_cargarlo_entero_y_se_lee(self):
        filas = [[f"Alumno {i:04d}", i % 100, i * 1.5, "x" * 30] for i in range(3000)]
        documento = doc.Documento("Reporte grande", "8A", [("Reporte", "grande")], [("Filas", 3000, doc.ENTERO)],
                                  [doc.Tabla("Detalle", [doc.Columna("a", "Alumno"), doc.Columna("b", "Entero", doc.ENTERO), doc.Columna("c", "Decimal", doc.DECIMAL), doc.Columna("d", "Texto")], filas)])
        inicio = time.time()
        archivo = EscritorDeArchivos().escribir(documento, "xlsx")
        self.assertLess(time.time() - inicio, 10)
        try:
            contenido = archivo.contenido.read()
            self.assertEqual(len(contenido), archivo.bytes_total)
            self.assertEqual(hashlib.sha256(contenido).hexdigest(), archivo.huella)
            hojas = leer_xlsx(contenido)
            self.assertEqual(len(hojas["Detalle"]), 3001)
            self.assertEqual(hojas["Detalle"][-1][:3], ["Alumno 2999", 99.0, 4498.5])
        finally:
            archivo.cerrar()


class AlcanceDeclaradoTests(BaseExportacion):
    def test_dice_en_lenguaje_llano_que_se_va_a_guardar_y_advierte_si_lleva_nombres(self):
        a = self.alcance(self.grupo_con_clases())
        self.assertEqual((a["tipo"], a["alumnos"], a["nominal"], a["umbral_aplicado"]), ("grupo", 5, True, False))
        self.assertTrue(a["texto_alcance"].startswith("Vas a guardar el reporte del grupo 8A (5 alumnos, asistencia, participación, aciertos, evaluaciones y estudio, datos al "))
        self.assertEqual(a["advertencia"], "El archivo incluirá nombres de alumnos. Una vez fuera de este equipo, el colegio ya no controla quién lo abre.")
        self.assertTrue(re.fullmatch(r"reporte-grupo-8A-2026-09-2\d-\d{4}\.xlsx", a["nombre_sugerido"]), a["nombre_sugerido"])
        self.assertEqual(a["incluye"], ["asistencia", "participación", "aciertos", "evaluaciones", "estudio"])
        self.assertEqual(a["politica"]["extraibles_permitidos"], True)
        self.assertEqual(a["politica"]["exigir_razon"], False)
        self.assertEqual(a["formatos"], ["xlsx", "csv"])
        self.assertEqual(a["corte"]["integracion"]["estado"], "completa")
        self.assertEqual(self.m_exportaciones(), 0)                            # declarar el alcance no genera ni registra nada

    def m_exportaciones(self) -> int:
        return m.Exportacion.objects.count()

    def test_un_reporte_agregado_dice_sin_datos_de_personas(self):
        self.rp_put("/configuracion/", {"umbral_privacidad": True})
        self.clase_cerrada([(5, 5), (3, 5)])
        a = self.alcance({"tipo": "grupo", "grupo_id": self.grupo["id"]})
        self.assertEqual((a["nominal"], a["umbral_aplicado"], a["advertencia"]), (False, True, "Sin datos de personas."))
        u = self.alcance({"tipo": "uso"}, cliente=self.admin)
        self.assertEqual((u["nominal"], u["advertencia"], u["alumnos"]), (False, "Sin datos de personas.", 0))
        self.assertTrue(u["texto_alcance"].startswith("Vas a guardar el reporte de uso de equipos ("))

    def test_la_clase_y_el_alumno_dicen_lo_suyo_sin_el_nombre_del_alumno(self):
        c = self.clase_cerrada([(5, 5), (3, 5)])
        a = self.alcance({"tipo": "clase", "sesion_id": c["sesion"]["id"]})
        self.assertTrue(a["texto_alcance"].startswith("Vas a guardar el reporte de la clase de 8A (2 alumnos, participación y aciertos, datos al "))
        b = self.alcance({"tipo": "alumno", "alumno_id": c["alumnos"][0][0]})
        self.assertTrue(b["texto_alcance"].startswith("Vas a guardar el reporte de un alumno del grupo 8A (1 alumno, asistencia, participación, aciertos, evaluaciones y calificaciones y estudio, datos al "))
        self.assertNotIn(c["alumnos"][0][1], str(b))
        self.assertNotIn("Alumno", b["texto_alcance"])


class DosTiemposTests(BaseExportacion):
    def test_autorizar_entrega_el_archivo_con_su_huella_y_lo_deja_sin_confirmar(self):
        d = self.grupo_con_clases()
        r, cuerpo = self.exportar(d)
        self.assertEqual(r["Content-Length"], str(len(cuerpo)))
        self.assertEqual(r["X-Avacom-Export-Huella"], hashlib.sha256(cuerpo).hexdigest())
        self.assertEqual((r["X-Avacom-Export-Bytes"], r["X-Avacom-Export-Filas"], r["X-Avacom-Export-Formato"], r["X-Avacom-Export-Nominal"]), (str(len(cuerpo)), "6", "xlsx", "true"))      # filas = lo que lleva el archivo: 5 alumnos y 1 clase
        self.assertRegex(r["X-Avacom-Export-Nombre"], r"^reporte-grupo-8A-2026-09-2\d-\d{4}\.xlsx$")
        self.assertIn("filename*=UTF-8''reporte-grupo-8A-", r["Content-Disposition"])
        self.assertEqual(r["Cache-Control"], "no-store")
        e = m.Exportacion.objects.get(pk=r["X-Avacom-Export-Id"])
        self.assertEqual((e.estado, e.filas, e.bytes_total, e.huella, e.destino_autorizado, e.nominal), ("autorizada", 6, len(cuerpo), hashlib.sha256(cuerpo).hexdigest(), "carpeta_local", True))
        self.assertEqual(e.expira_en, self.t + 15 * 60_000)
        self.assertEqual(self.eventos_rp("reporte.exportado.v1"), [])           # todavía NO se publicó nada: nadie ha dicho que quedó guardado
        asiento, = self.asientos("reporte.exportacion_autorizada")
        self.assertEqual((asiento.valor_nuevo["resultado"], asiento.valor_nuevo["destino_tipo"], asiento.valor_nuevo["huella"]), ("autorizada", "carpeta_local", e.huella))

    def test_confirmar_guardado_con_la_huella_verificada_la_deja_entregada_y_publica_el_evento(self):
        r, cuerpo = self.exportar(self.grupo_con_clases(), destino="extraible")
        eid, huella = r["X-Avacom-Export-Id"], r["X-Avacom-Export-Huella"]
        out = self.confirmar(eid, {"resultado": "guardado", "destino_tipo": "extraible", "huella_verificada": huella})
        self.assertEqual((out["reintento"], out["exportacion"]["estado"], out["exportacion"]["destino_tipo"]), (False, "entregada", "extraible"))
        e = m.Exportacion.objects.get(pk=eid)
        self.assertEqual((e.estado, e.huella_verificada, e.destino_tipo), ("entregada", huella, "extraible"))
        self.assertIsNotNone(e.confirmada_en)
        self.assertEqual(self.eventos_rp("reporte.exportado.v1"), ["reporte.exportado.v1"])
        carga = cola("reporting").get(tipo_evento="reporte.exportado.v1").carga
        self.assertEqual((carga["exportacion_id"], carga["tipo"], carga["formato"], carga["filas"], carga["huella"], carga["destino_tipo"], carga["nominal"], carga["por"]),
                         (eid, "grupo", "xlsx", 6, huella, "extraible", True, self.docente_id))
        self.assertNotIn("Alumno", str(carga))
        asiento, = self.asientos("reporte.exportado")
        self.assertEqual((asiento.valor_nuevo["destino_tipo"], asiento.valor_nuevo["resultado"], asiento.valor_nuevo["filas"], asiento.valor_nuevo["huella"]), ("extraible", "guardado", 6, huella))
        self.assertEqual(asiento.valor_nuevo["alcance"], {"grupo_id": self.grupo["id"]})
        reciente, = self.rp("/recientes/")["recientes"]
        self.assertEqual(reciente["ultima_exportacion_en"], self.t)

    def test_si_no_se_puede_poner_al_dia_la_exportacion_sigue_con_lo_que_hay(self):
        """Antes de armar se pone al día con los módulos; un «database is locked» en plena clase no puede volver la exportación un error 500 (como en cualquier reporte)."""
        d = self.grupo_con_clases()
        with mock.patch("reporting.aplicacion.exportar.ConsumirEventos") as consumidor:
            consumidor.return_value.hasta_vaciar.side_effect = RuntimeError("database is locked")
            a = self.alcance(d)
            _, cuerpo = self.exportar(d)
        self.assertEqual(consumidor.return_value.hasta_vaciar.call_count, 2)           # lo intentó las dos veces…
        self.assertTrue(a["texto_alcance"].startswith("Vas a guardar el reporte del grupo 8A"))      # …y siguió con lo que había
        self.assertEqual(cuerpo[:2], b"PK")                                              # un xlsx de verdad

    def test_confirmar_otra_vez_lo_mismo_es_un_reintento_y_no_repite_nada(self):
        r, _ = self.exportar(self.grupo_con_clases())
        eid, huella = r["X-Avacom-Export-Id"], r["X-Avacom-Export-Huella"]
        cuerpo = {"resultado": "guardado", "destino_tipo": "carpeta_local", "huella_verificada": huella}
        self.confirmar(eid, cuerpo)
        again = self.confirmar(eid, cuerpo)
        self.assertEqual((again["reintento"], again["exportacion"]["estado"]), (True, "entregada"))
        self.assertEqual(len(self.eventos_rp("reporte.exportado.v1")), 1)
        self.assertEqual(len(self.asientos("reporte.exportado")), 1)
        otro = self.confirmar(eid, {"resultado": "fallido", "destino_tipo": "red", "motivo": "sin_espacio"}, esperado=409)
        self.assertEqual(otro["codigo"], "exportacion_ya_confirmada")

    def test_un_intento_fallido_no_cierra_la_exportacion_y_se_puede_guardar_en_otro_destino_sin_generar_de_nuevo(self):
        r, _ = self.exportar(self.grupo_con_clases(), destino="extraible")
        eid, huella = r["X-Avacom-Export-Id"], r["X-Avacom-Export-Huella"]
        f = self.confirmar(eid, {"resultado": "fallido", "destino_tipo": "extraible", "motivo": "medio_retirado"})
        self.assertEqual((f["exportacion"]["estado"], [(i["resultado"], i["motivo"], i["destino_tipo"]) for i in f["exportacion"]["intentos"]]), ("autorizada", [("fallido", "medio_retirado", "extraible")]))
        self.assertEqual(self.eventos_rp("reporte.exportado.v1"), [])                                       # no entregado: ningún evento de exportado
        asiento, = self.asientos("reporte.exportacion_fallida")
        self.assertEqual((asiento.valor_nuevo["motivo"], asiento.valor_nuevo["destino_tipo"], asiento.valor_nuevo["resultado"]), ("medio_retirado", "extraible", "fallido"))
        self.confirmar(eid, {"resultado": "fallido", "destino_tipo": "carpeta_local", "motivo": "sin_espacio"})
        ok = self.confirmar(eid, {"resultado": "guardado", "destino_tipo": "carpeta_local", "huella_verificada": huella})        # mismo archivo, otro destino
        self.assertEqual((ok["exportacion"]["estado"], ok["exportacion"]["destino_tipo"], len(ok["exportacion"]["intentos"])), ("entregada", "carpeta_local", 3))
        self.assertEqual(m.Exportacion.objects.count(), 1)                                                   # y no se generó otro archivo
        self.assertEqual(len(self.eventos_rp("reporte.exportado.v1")), 1)

    def test_el_motivo_del_fallo_sale_de_la_lista(self):
        r, _ = self.exportar(self.grupo_con_clases())
        eid = r["X-Avacom-Export-Id"]
        self.assertEqual(self.confirmar(eid, {"resultado": "fallido", "destino_tipo": "red", "motivo": "porque si"}, esperado=400)["codigo"], "datos_invalidos")
        for motivo in cat.MOTIVOS_DE_FALLO:
            self.confirmar(eid, {"resultado": "fallido", "destino_tipo": "red", "motivo": motivo})
        self.assertEqual(len(m.Exportacion.objects.get(pk=eid).intentos), len(cat.MOTIVOS_DE_FALLO))

    def test_si_la_huella_que_se_verifico_no_coincide_no_se_da_por_entregado(self):
        r, _ = self.exportar(self.grupo_con_clases())
        eid = r["X-Avacom-Export-Id"]
        out = self.confirmar(eid, {"resultado": "guardado", "destino_tipo": "extraible", "huella_verificada": "0" * 64}, esperado=409)
        self.assertEqual(out["codigo"], "huella_distinta")
        e = m.Exportacion.objects.get(pk=eid)
        self.assertEqual((e.estado, e.intentos[0]["motivo"]), ("autorizada", "verificacion_fallida"))
        self.assertEqual(self.eventos_rp("reporte.exportado.v1"), [])
        asiento, = self.asientos("reporte.exportacion_fallida")
        self.assertEqual(asiento.valor_nuevo["motivo"], "verificacion_fallida")
        self.confirmar(eid, {"resultado": "guardado", "destino_tipo": "extraible"}, esperado=400)                # sin huella no hay forma de dar por guardado
        self.confirmar(eid, {"resultado": "guardado", "destino_tipo": "extraible", "huella_verificada": "no es una huella"}, esperado=400)

    def test_una_exportacion_que_nadie_confirma_caduca_y_no_cuenta_como_entregada(self):
        r, _ = self.exportar(self.grupo_con_clases())
        eid, huella = r["X-Avacom-Export-Id"], r["X-Avacom-Export-Huella"]
        self.avanzar(minutos=14)
        self.assertEqual(self.rp(f"/exportaciones/{eid}/")["exportacion"]["estado"], "autorizada")
        self.avanzar(minutos=2)
        self.assertEqual(self.rp(f"/exportaciones/{eid}/")["exportacion"]["estado"], "caducada")
        self.assertEqual(self.asientos("reporte.exportacion_caducada")[0].valor_nuevo["resultado"], "sin_confirmar")
        out = self.confirmar(eid, {"resultado": "guardado", "destino_tipo": "extraible", "huella_verificada": huella}, esperado=409)
        self.assertEqual(out["codigo"], "exportacion_caducada")
        self.assertEqual(self.eventos_rp("reporte.exportado.v1"), [])
        self.assertEqual(len(self.asientos("reporte.exportacion_caducada")), 1)                                  # un solo asiento aunque se pregunte varias veces

    def test_el_hilo_del_nodo_tambien_las_caduca(self):
        self.exportar(self.grupo_con_clases())
        self.avanzar(minutos=16)
        r = self.actualizar()
        self.assertEqual(r["exportaciones_caducadas"], 1)
        self.assertEqual(m.Exportacion.objects.get().estado, "caducada")

    def test_solo_quien_la_pidio_la_confirma_ni_siquiera_se_sabe_que_existe(self):
        r, _ = self.exportar(self.grupo_con_clases())
        _, otro = self.otro_docente()
        self.confirmar(r["X-Avacom-Export-Id"], {"resultado": "fallido", "destino_tipo": "red", "motivo": "otro"}, cliente=otro, esperado=404)
        self.rp(f"/exportaciones/{r['X-Avacom-Export-Id']}/", cliente=otro, esperado=404)
        self.rp("/exportaciones/no-existe/", esperado=404)
        mias = self.rp("/exportaciones/")["exportaciones"]
        self.assertEqual([e["id"] for e in mias], [r["X-Avacom-Export-Id"]])
        self.assertEqual(self.rp("/exportaciones/", cliente=otro)["exportaciones"], [])

    def test_ni_la_ruta_ni_el_nombre_ni_el_contenido_llegan_a_la_bitacora_ni_a_las_tablas(self):
        c = self.clase_cerrada([(5, 5), (3, 5)])
        r, _ = self.exportar({"tipo": "grupo", "grupo_id": self.grupo["id"]}, destino="extraible")
        eid, huella = r["X-Avacom-Export-Id"], r["X-Avacom-Export-Huella"]
        self.confirmar(eid, {"resultado": "guardado", "destino_tipo": "extraible", "huella_verificada": huella, "ruta": "E:\\Reportes\\Alumno 01 notas.xlsx", "contenido": "secreto"})
        todo = "".join(str(a.valor_nuevo) + str(a.valor_anterior) for a in self.asientos("reporte.exportacion_autorizada") + self.asientos("reporte.exportado"))
        todo += str(list(m.Exportacion.objects.values())) + str(list(cola("reporting").values()))
        for prohibido in ("E:\\", "Reportes\\", "secreto", c["alumnos"][0][1], c["alumnos"][1][1], "Prof. Gómez"):
            self.assertNotIn(prohibido, todo, prohibido)
        nombre = m.Exportacion.objects.get(pk=eid).nombre_archivo                      # sí queda el nombre PROPUESTO (código del grupo y fecha), sin ruta y sin personas
        self.assertRegex(nombre, r"^reporte-grupo-8A-\d{4}-\d\d-\d\d-\d{4}\.xlsx$")


class PoliticaDelAdministradorTests(BaseExportacion):
    def test_por_defecto_se_puede_guardar_en_todas_partes_y_no_se_pide_razon(self):
        d = self.grupo_con_clases()
        for destino in cat.DESTINOS:
            self.exportar(d, destino=destino)

    def test_con_los_medios_extraibles_cerrados_no_se_genera_nada_y_se_dice_por_que(self):
        d = self.grupo_con_clases()
        self.rp_put("/configuracion/", {"extraibles_permitidos": False})
        self.assertFalse(self.alcance(d)["politica"]["extraibles_permitidos"])
        r = self.exportar(d, destino="extraible", esperado=403)[0]
        self.assertEqual((r["codigo"], r["destino_tipo"]), ("destino_no_permitido", "extraible"))
        self.assertIn("no permite guardar reportes en memorias extraíbles", r["detail"])
        self.assertEqual(m.Exportacion.objects.count(), 0)
        self.exportar(d, destino="carpeta_local")
        self.exportar(d, destino="red")
        self.assertEqual(self.asientos("reporte.acceso_denegado")[0].valor_nuevo["codigo"], "destino_no_permitido")

    def test_con_razon_obligatoria_se_elige_de_la_lista(self):
        d = self.grupo_con_clases()
        self.rp_put("/configuracion/", {"exigir_razon": True})
        a = self.alcance(d)
        self.assertTrue(a["politica"]["exigir_razon"])
        self.assertIn("entrega_a_familias", [x["codigo"] for x in a["politica"]["razones"]])
        self.assertEqual(self.exportar(d, esperado=400)[0]["codigo"], "razon_requerida")
        self.assertEqual(self.exportar(d, razon_codigo="porque si", esperado=400)[0]["codigo"], "datos_invalidos")
        r, _ = self.exportar(d, razon_codigo="entrega_a_familias")
        self.assertEqual(m.Exportacion.objects.get(pk=r["X-Avacom-Export-Id"]).razon_codigo, "entrega_a_familias")
        self.assertEqual(self.asientos("reporte.exportacion_autorizada")[0].valor_nuevo["razon"], "entrega_a_familias")

    def test_la_razon_es_opcional_si_nadie_la_exige(self):
        d = self.grupo_con_clases()
        r, _ = self.exportar(d, razon_codigo="respaldo_del_profesor")
        self.assertEqual(m.Exportacion.objects.get(pk=r["X-Avacom-Export-Id"]).razon_codigo, "respaldo_del_profesor")

    def test_el_umbral_de_privacidad_aplicado_va_dentro_del_archivo(self):
        """BR-086: con el umbral activo y menos de cinco alumnos, el archivo (y el reporte) sólo traen el agregado y lo dicen."""
        self.rp_put("/configuracion/", {"umbral_privacidad": True})
        self.clase_cerrada([(5, 5), (3, 5)])
        r, cuerpo = self.exportar({"tipo": "grupo", "grupo_id": self.grupo["id"]})
        self.assertEqual((r["X-Avacom-Export-Nominal"], r["X-Avacom-Export-Umbral-Aplicado"]), ("false", "true"))
        hojas = leer_xlsx(cuerpo)
        self.assertNotIn("Alumnos", hojas)
        self.assertEqual(como_dict(hojas["Resumen"])["Umbral de privacidad aplicado"], "Sí")
        self.assertTrue(any("menos de 5" in str(f) for f in hojas["Resumen"]))
        self.assertTrue(any("no incluye datos de personas" in str(f) for f in hojas["Resumen"]))
        self.assertNotIn(b"Alumno 01", cuerpo)
        self.assertFalse(m.Exportacion.objects.get().nominal)
        # La pantalla pone «—» en «necesitan atención» (no se cuenta quién): en el archivo la celda queda vacía, no en 0 («nadie necesita atención» no es lo que se sabe).
        self.assertNotIn("Alumnos que necesitan atención", como_dict(hojas["Resumen"]))
        self.assertTrue(any(f and f[0] == "Alumnos que necesitan atención" for f in hojas["Resumen"]))


class QuienPuedeExportarTests(BaseExportacion):
    def setUp(self):
        super().setUp()
        self.d = self.grupo_con_clases()

    def test_el_profesor_exporta_lo_de_sus_grupos_y_no_lo_ajeno(self):
        self.exportar(self.d)
        _, otro = self.otro_docente()
        r = self.exportar(self.d, cliente=otro, esperado=403)[0]
        self.assertEqual(r["codigo"], "fuera_de_alcance")
        self.assertEqual(m.Exportacion.objects.count(), 1)

    def test_reportes_y_administracion_exportan_cualquier_grupo_y_el_uso(self):
        self.exportar(self.d, cliente=self.reportes())
        self.exportar(self.d, cliente=self.admin)
        r, cuerpo = self.exportar({"tipo": "uso"}, cliente=self.admin)
        self.assertEqual(r["X-Avacom-Export-Nominal"], "false")
        self.assertEqual(list(leer_xlsx(cuerpo)), ["Resumen", "Equipos", "Clases"])

    def test_el_tecnico_no_exporta_nada_ni_el_uso(self):
        tecnico = self.tecnico()
        self.assertEqual(self.exportar(self.d, cliente=tecnico, esperado=403)[0]["codigo"], "sin_permiso")
        self.assertEqual(self.exportar({"tipo": "uso"}, cliente=tecnico, esperado=403)[0]["codigo"], "sin_permiso")
        self.assertEqual(m.Exportacion.objects.count(), 0)
        self.assertTrue(self.asientos("reporte.acceso_denegado"))

    def test_el_profesor_no_exporta_el_uso_de_equipos_porque_no_lo_puede_ver(self):
        self.exportar({"tipo": "uso"}, esperado=403)

    def test_no_se_exporta_lo_que_aun_no_existe_o_esta_reservado(self):
        self.exportar({"tipo": "clase", "sesion_id": "no-existe"}, esperado=404)
        abierta = self.clase_cerrada([(5, 5)], cerrar=False)
        self.assertEqual(self.exportar({"tipo": "clase", "sesion_id": abierta["sesion"]["id"]}, esperado=409)[0]["codigo"], "clase_en_curso")
        self.assertEqual(self.exportar({"tipo": "cobertura"}, esperado=501)[0]["codigo"], "capacidad_reservada")
        self.assertEqual(self.exportar({"tipo": "comparacion"}, esperado=501)[0]["codigo"], "capacidad_reservada")
        self.assertEqual(self.exportar({"tipo": "inventado"}, esperado=400)[0]["codigo"], "datos_invalidos")
        self.assertEqual(self.exportar({}, esperado=400)[0]["codigo"], "datos_invalidos")

    def test_el_formato_y_el_destino_se_validan(self):
        self.assertEqual(self.exportar(self.d, formato="pdf", esperado=400)[0]["formatos"], ["xlsx", "csv"])
        self.assertEqual(self.exportar(self.d, destino="nube", esperado=400)[0]["destinos"], ["extraible", "carpeta_local", "red"])

    def test_el_alumno_no_exporta(self):
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.exportar(self.d, cliente=alumno, esperado=403)

    def test_se_puede_exportar_el_reporte_de_una_clase_y_el_de_un_alumno(self):
        c = self.clase_cerrada([(5, 5), (3, 5)])
        _, clase = self.exportar({"tipo": "clase", "sesion_id": c["sesion"]["id"]})
        hojas = leer_xlsx(clase)
        self.assertEqual(list(hojas), ["Resumen", "Alumnos"])
        self.assertEqual(len(hojas["Alumnos"]), 1 + 2)
        _, alumno = self.exportar({"tipo": "alumno", "alumno_id": c["alumnos"][0][0]}, formato="csv")
        self.assertIn("Reporte del alumno", alumno.decode("utf-8-sig"))
        self.assertIn(c["alumnos"][0][1], alumno.decode("utf-8-sig"))                              # el informe del alumno es nominal: lleva su nombre dentro

    def test_el_nombre_del_archivo_nunca_lleva_el_nombre_de_una_persona(self):
        c = self.clase_cerrada([(5, 5)])
        r, _ = self.exportar({"tipo": "alumno", "alumno_id": c["alumnos"][0][0]})
        self.assertNotIn(c["alumnos"][0][1].replace(" ", "-"), r["X-Avacom-Export-Nombre"])
        self.assertRegex(r["X-Avacom-Export-Nombre"], r"^reporte-alumno-8A-\d{4}-\d\d-\d\d-\d{4}\.xlsx$")


class VersionDelNodoTests(SimpleTestCase):
    """BR-083: cada archivo dice qué versión del producto lo generó. Un nodo INSTALADO la lee del `manifiesto.json` que el instalador deja junto a la carpeta Backend (antes se prometía una
    variable que nadie escribía y un nodo instalado habría dicho «desarrollo»)."""

    def _carpeta(self, manifiesto: str | None = None, version: str | None = None) -> Path:
        raiz = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, raiz, ignore_errors=True)
        (raiz / "Backend").mkdir()
        if manifiesto is not None:
            (raiz / "manifiesto.json").write_text(json.dumps({"producto": "AVACOM OPS Master", "version": manifiesto}), encoding="utf-8-sig")     # PowerShell lo escribe con BOM
        if version is not None:
            (raiz / "installer").mkdir()
            (raiz / "installer" / "version.json").write_text(json.dumps({"version": version}), encoding="utf-8")
        return raiz / "Backend"

    def _version(self, base: Path, entorno: str | None = None) -> str:
        with override_settings(BASE_DIR=base), mock.patch.dict(os.environ, {"AVACOM_LMS_VERSION": entorno} if entorno else {}):
            if not entorno:
                os.environ.pop("AVACOM_LMS_VERSION", None)
            return version_del_nodo()

    def test_un_nodo_instalado_lee_el_manifiesto_y_este_gana_a_version_json(self):
        self.assertEqual(self._version(self._carpeta(manifiesto="2.8.0", version="9.9.9")), "2.8.0")

    def test_en_desarrollo_lee_installer_version_json(self):
        self.assertEqual(self._version(self._carpeta(version="2.8.0")), "2.8.0")

    def test_una_variable_fijada_a_proposito_manda_sobre_todo(self):
        self.assertEqual(self._version(self._carpeta(manifiesto="2.8.0"), entorno="7.7.7"), "7.7.7")

    def test_sin_nada_de_eso_dice_desarrollo_y_no_falla(self):
        self.assertEqual(self._version(self._carpeta()), "desarrollo")
        base = self._carpeta()
        (base.parent / "manifiesto.json").write_text("{esto no es json", encoding="utf-8")                      # un manifiesto roto tampoco tumba un reporte
        self.assertEqual(self._version(base), "desarrollo")

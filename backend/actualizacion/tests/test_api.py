"""
La API real (`/api/actualizacion/`) sobre un nodo real: TST-047 (paquete válido), TST-048 (alterado: rechazo y cero archivos), TST-062 (sin firma), TST-050 (importar durante una
clase sí; aplicar, 409 y la clase intacta), la orden al Host (202 y `orden.json`), el 503 del inicio de clases mientras hay una orden, el resultado del Host registrado en el
historial (FUN-187), la reversión a 14 días, las ventanas, los permisos por rol e INV-023 (ninguna escritura en tablas ajenas).
"""
from __future__ import annotations

import json
import re

from django.db import connection
from django.test.utils import CaptureQueriesContext

from actualizacion import models as m
from actualizacion.dominio import catalogos as cat
from actualizacion.dominio import manifiesto as mf

from . import emisor
from .base import A, BaseActualizacion

TABLAS_QUE_SE_ESCRIBEN = {"m17_paquete", "m17_historial", "m15_evento", "m19_bitacora"}


class ImportarTests(BaseActualizacion):
    def test_tst_047_un_paquete_valido_se_importa_verificado_con_sus_recursos_completos(self):
        candidatos_antes = self.candidatos()
        self.assertEqual(candidatos_antes, [])
        self.dejar_en_usb(self.avupd())
        candidatos = self.candidatos()
        self.assertEqual([(c["nombre"], c["origen"], c["fuente"] == self.usb.name) for c in candidatos], [("reportes-1.4.0.avupd", "unidad", True)])
        self.assertNotIn(str(self.usb), json.dumps(candidatos))                                   # ningún camino de archivo sale por la API (P-11)
        r = self.admin.post(f"{A}/paquetes/importar/", {"candidato": candidatos[0]["id"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        ficha = r.json()
        self.assertEqual((ficha["estado"], ficha["serie"], ficha["modulos"], ficha["kid"], ficha["origen"], ficha["archivo"]), ("verificado", 7, ["reporting"], "upd-dev-1", "unidad", "reportes-1.4.0.avupd"))
        self.assertEqual((ficha["version_producto"], ficha["importado_por"], ficha["en_curso"], ficha["revertible"]), (self.version_nueva, self.admin_id, False, False))
        self.assertEqual([h["tipo"] for h in ficha["historial"]], ["recibido", "verificado"])
        self.assertTrue(ficha["historial"][1]["detalle"]["compatibilidad"]["ok"])
        self.assertEqual(ficha["manifiesto"]["archivos"], 2)
        self.assertNotIn("ruta", json.dumps(ficha))                                                # ni en la ficha
        # el archivo quedó en paquetes\<id>.avupd, tal cual, y nada más se escribió
        self.assertEqual(self.archivos_escritos(), [f"paquetes/{ficha['paquete_id']}.avupd"])
        self.assertEqual((self.carpeta / "paquetes" / f"{ficha['paquete_id']}.avupd").read_bytes(), self.avupd())
        fila = m.Paquete.objects.get()
        self.assertEqual((fila.paquete_id, fila.sha256, fila.importado_por), (emisor.PAQUETE_ID, ficha["sha256"], self.admin_id))
        self.assertEqual(self.acciones_asentadas(), [cat.A_IMPORTADO, cat.A_VERIFICADO])
        self.assertEqual(self.tipos_de_eventos(), [cat.EV_IMPORTADO, cat.EV_VERIFICADO])
        for evento in self.eventos():
            self.assertEqual((evento.modulo, evento.agregado_tipo, evento.agregado_id, evento.catalogado, evento.carga_omitida), ("actualizacion", "paquete_actualizacion", emisor.PAQUETE_ID, True, False))
            self.assertNotIn("ruta", json.dumps(evento.carga))
        # el archivo del USB sigue a la vista, pero marcado como ya importado
        self.assertEqual([c["importado"] for c in self.candidatos()], [ficha["paquete_id"]])
        self.assertEqual([p["paquete_id"] for p in self.admin.get(f"{A}/paquetes/").json()["paquetes"]], [ficha["paquete_id"]])

    def test_importar_dos_veces_el_mismo_archivo_devuelve_el_mismo_paquete(self):
        ficha = self.importar_ok()
        self.dejar_en_usb(self.avupd(), "copia.avupd")
        candidato = [c for c in self.candidatos() if c["nombre"] == "copia.avupd"][0]
        r = self.admin.post(f"{A}/paquetes/importar/", {"candidato": candidato["id"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["paquete_id"], ficha["paquete_id"])
        self.assertEqual(m.Paquete.objects.count(), 1)
        self.assertEqual(self.acciones_asentadas(), [cat.A_IMPORTADO, cat.A_VERIFICADO])          # nada nuevo
        # el mismo identificador con OTRO contenido (firmado) es un conflicto: un paquete_id nombra un solo paquete
        r = self.importar(self.avupd(nombre="Otro nombre, mismo id"), nombre="otro.avupd")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "paquete_repetido"))

    def test_tst_048_un_paquete_alterado_se_rechaza_con_motivo_y_cero_archivos_escritos(self):
        datos = bytearray(self.avupd())
        datos[len(datos) // 2] ^= 0xFF                                                        # un byte a mitad del archivo
        r = self.importar(bytes(datos), nombre="alterado.avupd")
        self.assertEqual(r.status_code, 422, r.content)
        cuerpo = r.json()
        self.assertIn(cuerpo["codigo"], ("paquete_invalido", "firma_invalida"))
        self.assertIn(cuerpo["motivo"], cat.MENSAJES_DE_MOTIVO)
        self.assertEqual(cuerpo["detail"], cat.MENSAJES_DE_MOTIVO[cuerpo["motivo"]])
        self.assertEqual(self.archivos_escritos(), [])                                        # cero archivos escritos
        self.assertEqual(m.Paquete.objects.count(), 0)                                         # no se guarda como paquete (P-05)
        fila = m.Historial.objects.get()
        self.assertEqual((fila.tipo, fila.paquete_id, fila.detalle["motivo"], fila.detalle["nombre"]), (cat.H_RECHAZADO, "", cuerpo["motivo"], "alterado.avupd"))
        self.assertEqual(len(fila.detalle["sha256"]), 64)
        self.assertIn(self.acciones_asentadas()[0], (cat.A_INTEGRIDAD_ALTERADA, cat.A_FIRMA_INVALIDA))
        self.assertEqual(self.acciones_asentadas()[1], cat.A_RECHAZADO)
        self.assertEqual(self.tipos_de_eventos(), [cat.EV_RECHAZADO])
        self.assertEqual(self.admin.get(f"{A}/historial/").json()["historial"][0]["tipo"], "rechazado")
        # el mismo archivo otra vez dentro de la hora: otro 422, pero sin llenar la bitácora
        r = self.importar(bytes(datos), nombre="alterado.avupd")
        self.assertEqual(r.status_code, 422)
        self.assertEqual(m.Historial.objects.count(), 1)

    def test_tst_048_un_archivo_del_paquete_cambiado_se_rechaza_por_su_huella(self):
        archivos = emisor.archivos_de_ejemplo()
        manifiesto = mf.escribir(emisor.manifiesto_de_ejemplo(archivos, version_producto=self.version_nueva, version_minima=self.version_instalada))
        from actualizacion.dominio import firma
        sello = firma.sellar(emisor.KID_DEV_1, emisor.clave_privada(emisor.KID_DEV_1), manifiesto)
        ruta = next(iter(archivos))
        cambiado = {**archivos, ruta: bytes(reversed(archivos[ruta]))}
        r = self.importar(emisor.empaquetar(manifiesto, sello, cambiado), nombre="huella.avupd")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["motivo"]), (422, "paquete_invalido", "sha_distinto"))
        self.assertEqual(self.acciones_asentadas()[0], cat.A_INTEGRIDAD_ALTERADA)
        self.assertEqual(self.archivos_escritos(), [])

    def test_tst_062_un_paquete_sin_firma_se_rechaza_sin_escribir_archivos(self):
        manifiesto = mf.escribir(emisor.manifiesto_de_ejemplo(version_producto=self.version_nueva, version_minima=self.version_instalada))
        r = self.importar(emisor.empaquetar(manifiesto, None, emisor.archivos_de_ejemplo()), nombre="sin-firma.avupd")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["motivo"]), (422, "firma_invalida", "sin_firma"))
        self.assertEqual(self.archivos_escritos(), [])
        self.assertEqual(m.Paquete.objects.count(), 0)
        self.assertEqual(self.acciones_asentadas()[0], cat.A_FIRMA_INVALIDA)
        # firmado por una llave que el nodo no conoce: lo mismo
        r = self.importar(self.avupd(kid="prod-2030-1"), nombre="kid.avupd")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["motivo"], r.json()["kid"]), (422, "firma_invalida", "kid_desconocido", "prod-2030-1"))
        self.assertEqual(self.archivos_escritos(), [])

    def test_un_candidato_que_ya_no_esta_o_que_no_existe(self):
        r = self.admin.post(f"{A}/paquetes/importar/", {"candidato": "no-existe"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "no_encontrado"))
        r = self.admin.post(f"{A}/paquetes/importar/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        r = self.admin.post(f"{A}/paquetes/importar/", {"candidato": str(self.usb / "x.avupd")}, format="json")     # una ruta no es un candidato (P-11)
        self.assertEqual(r.status_code, 404)

    def test_un_paquete_incompatible_se_guarda_como_incompatible_con_su_lista(self):
        ficha = self.importar_ok(self.avupd(requisitos=mf.Requisitos(contrato_biblioteca=3)))
        self.assertEqual(ficha["estado"], "incompatible")
        self.assertEqual([p["codigo"] for p in ficha["incompatibilidades"]], ["contrato_biblioteca"])
        self.assertEqual([h["tipo"] for h in ficha["historial"]], ["recibido", "incompatible"])
        r = self.aplicar(ficha["paquete_id"])
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "contrato_incompatible"))
        self.assertEqual([p["codigo"] for p in r.json()["incompatibilidades"]], ["contrato_biblioteca"])
        self.assertIsNone(self.orden())
        # serie menor que la instalada (la del registro es 1): el paquete de serie 1 «ya está aplicado»; uno de serie 0 no existe (el manifiesto exige ≥ 1)
        ficha = self.importar_ok(self.avupd(paquete_id="17171717-0002-4000-8000-000000000002", modulos=(mf.Modulo("reporting", "1.4.0", 4, 1, 1),)), nombre="serie1.avupd")
        self.assertEqual((ficha["estado"], [p["codigo"] for p in ficha["incompatibilidades"]]), ("incompatible", ["ya_aplicado"]))
        self.assertEqual((self.aplicar(ficha["paquete_id"]).status_code, self.aplicar(ficha["paquete_id"]).json()["codigo"]), (409, "ya_aplicado"))

    def test_inv_023_importar_y_aplicar_solo_escriben_en_m17_m15_y_la_bitacora(self):
        self.dejar_en_usb(self.avupd())
        candidato = self.candidatos()[0]
        with CaptureQueriesContext(connection) as consultas:
            self.assertEqual(self.admin.post(f"{A}/paquetes/importar/", {"candidato": candidato["id"]}, format="json").status_code, 201)
            self.assertEqual(self.aplicar(emisor.PAQUETE_ID).status_code, 202)
        escritas = set()
        for q in consultas.captured_queries:
            sql = q["sql"].strip()
            encontrado = re.match(r"^(?:INSERT INTO|UPDATE|DELETE FROM)\s+\"?([a-z0-9_]+)\"?", sql, re.IGNORECASE)
            if encontrado:
                escritas.add(encontrado.group(1).lower())
        ajenas = {t for t in escritas if not (t.startswith("m17_") or t == "m15_evento" or t.startswith("m19_") or t == "m01_sesion")}
        self.assertEqual(ajenas, set(), escritas)        # `m19_*` las escribe la propia bitácora (MOD-019) al asentar; `m01_sesion`, el middleware de sesión de MOD-001
        self.assertTrue(TABLAS_QUE_SE_ESCRIBEN <= escritas, escritas)


class AplicarTests(BaseActualizacion):
    def test_aplicar_sin_clase_da_202_y_deja_la_orden_al_host(self):
        ficha = self.importar_ok()
        r = self.aplicar(ficha["paquete_id"])
        self.assertEqual(r.status_code, 202, r.content)
        cuerpo = r.json()
        self.assertEqual((cuerpo["estado"], cuerpo["en_curso"], cuerpo["accion"], cuerpo["orden"]["accion"], cuerpo["orden"]["limite_minutos"], cuerpo["orden"]["pasos"]),
                         ("aplicando", True, "aplicar", "aplicar", 5, list(cat.PASOS)))
        orden = self.orden()
        self.assertEqual((orden["formato"], orden["orden_id"], orden["paquete_id"], orden["accion"], orden["emitida_por"], orden["limite_minutos"]), (1, cuerpo["orden"]["orden_id"], ficha["paquete_id"], "aplicar", self.admin_id, 5))
        self.assertEqual(orden["paquete"]["sha256"], ficha["sha256"])
        self.assertEqual([a["ruta"] for a in orden["archivos"]], list(emisor.archivos_de_ejemplo()))
        self.assertEqual(orden["modulos"][0]["migraciones"], [{"nombre": "0004_parche_de_ejemplo", "reverso": "0003_corte_cola_unica"}])
        self.assertEqual(orden["carpetas"], {"staging": f"staging/{ficha['paquete_id']}", "instantanea": f"versiones/{ficha['paquete_id']}/anterior"})
        # el staging tiene exactamente los archivos del paquete, byte a byte
        staging = self.carpeta / "staging" / ficha["paquete_id"]
        for ruta, contenido in emisor.archivos_de_ejemplo().items():
            self.assertEqual((staging / ruta).read_bytes(), contenido)
        self.assertEqual(sorted(p for p in self.archivos_escritos() if p.startswith("staging/")), sorted(f"staging/{ficha['paquete_id']}/{r}" for r in emisor.archivos_de_ejemplo()))
        self.assertEqual(self.acciones_asentadas()[-1], cat.A_ORDEN_EMITIDA)
        self.assertEqual(self.ficha(ficha["paquete_id"])["estado"], "aplicando")
        # el estado del nodo y /health/ lo dicen
        estado = self.admin.get(f"{A}/estado/").json()
        self.assertEqual((estado["estado"], estado["en_curso"]["paquete_id"], estado["orden_pendiente"]), ("aplicando", ficha["paquete_id"], True))
        self.assertEqual(estado["version"], self.version_instalada)
        self.assertEqual([x["nombre"] for x in estado["modulos"] if x["nombre"] == "reporting"], ["reporting"])
        salud = self.api.get("/health/").json()["actualizacion"]
        self.assertEqual((salud["estado"], salud["en_curso"]["paquete_id"], salud["orden_pendiente"]), ("aplicando", ficha["paquete_id"], True))
        # una segunda orden no se acepta hasta que termine; aplicar el mismo paquete tampoco
        self.assertEqual((self.aplicar(ficha["paquete_id"]).status_code, self.aplicar(ficha["paquete_id"]).json()["codigo"]), (409, "estado_invalido"))
        otra = self.importar_ok(self.avupd(paquete_id="17171717-0003-4000-8000-000000000003", modulos=(mf.Modulo("reporting", "1.5.0", 4, 1, 8),)), nombre="otro.avupd")
        self.assertEqual((self.aplicar(otra["paquete_id"]).status_code, self.aplicar(otra["paquete_id"]).json()["codigo"]), (409, "actualizacion_en_curso"))

    def test_mientras_hay_una_orden_el_inicio_de_clases_responde_503_y_lo_demas_sigue(self):
        """P-08, R-01, R-02: sólo `POST /api/aula/sesiones/`, sólo 503 (nunca 4xx), y se levanta con el resultado del Host."""
        ficha = self.importar_ok()
        self.aplicar_ok(ficha["paquete_id"])
        r = self.api.post("/api/aula/sesiones/", {"via": "libre", "profesor_id": self.docente_id}, format="json")
        self.assertEqual(r.status_code, 503, r.content)
        self.assertEqual((r.json()["codigo"], r["Retry-After"]), ("actualizacion_en_curso", "60"))
        self.assertEqual(self.api.get("/api/aula/sesiones/").status_code, 200)                    # listar clases sigue
        self.assertNotEqual(self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": "000000", "persona_id": "x"}, format="json").status_code, 503)   # unirse no se toca (R-02)
        self.assertEqual(self.admin.get(f"{A}/estado/").status_code, 200)
        # el Host termina: el resultado se registra y el aula vuelve a abrir clases
        self.resultado_del_host(self.orden()["orden_id"], ficha["paquete_id"])
        self.assertTrue(self.tick()["resultado"]["registrado"])
        self.assertEqual(self.api.post("/api/aula/sesiones/", {"via": "libre", "profesor_id": self.docente_id}, format="json").status_code, 201)

    def test_tst_050_importar_durante_una_clase_si_aplicar_no_y_la_clase_queda_intacta(self):
        clase = self.abrir_clase()
        ficha = self.importar_ok()                                                                # importar y verificar SÍ (C-1)
        self.assertEqual(ficha["estado"], "verificado")
        r = self.aplicar(ficha["paquete_id"])
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["sesiones_activas"]), (409, "sesion_activa", 1), r.content)
        self.assertIsNone(self.orden())
        self.assertFalse((self.carpeta / "staging").exists() and any((self.carpeta / "staging").iterdir()))
        self.assertEqual(self.ficha(ficha["paquete_id"])["estado"], "verificado")                 # bloqueada no cambia el estado
        self.assertEqual([h["tipo"] for h in self.ficha(ficha["paquete_id"])["historial"]], ["recibido", "verificado", "bloqueada"])
        self.assertEqual(self.acciones_asentadas()[-1], cat.A_BLOQUEADA)
        self.assertEqual(self.tipos_de_eventos()[-1], cat.EV_BLOQUEADA)
        # la clase sigue abierta, con el mismo código, y el inicio de clases no da 503 (no hay orden)
        detalle = self.api.get(f"/api/aula/sesiones/{clase['id']}/").json()
        self.assertEqual((detalle["estado"], detalle["codigo_union"]), (clase["estado"], clase["codigo_union"]))
        r = self.api.post("/api/aula/sesiones/", {"via": "libre", "profesor_id": self.docente_id}, format="json")
        self.assertNotEqual(r.status_code, 503)                                                   # lo que responda es del aula (el mismo profesor ya tiene una clase), no de MOD-017
        self.assertNotEqual(r.json().get("codigo"), "actualizacion_en_curso")
        self.assertEqual(self.api.get("/health/").json()["actualizacion"]["estado"], "al_dia")

    def test_sin_espacio_no_se_aplica(self):
        ficha = self.importar_ok()
        self.s.almacen.espacio_libre = lambda: 10                                                 # diez bytes libres
        r = self.aplicar(ficha["paquete_id"])
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["espacio_libre"]), (409, "espacio_insuficiente", 10))
        self.assertGreater(r.json()["espacio_requerido"], 10)
        self.assertIsNone(self.orden())
        self.assertEqual(self.ficha(ficha["paquete_id"])["estado"], "verificado")                 # el espacio no hace al paquete incompatible: puede cambiar

    def test_un_paquete_guardado_y_luego_alterado_en_disco_no_se_aplica(self):
        """A5: el archivo de `paquetes\\` se vuelve a verificar al aplicar."""
        ficha = self.importar_ok()
        ruta = self.carpeta / "paquetes" / f"{ficha['paquete_id']}.avupd"
        datos = bytearray(ruta.read_bytes())
        datos[-1] ^= 0x01
        ruta.write_bytes(bytes(datos))
        r = self.aplicar(ficha["paquete_id"])
        self.assertEqual(r.status_code, 422, r.content)
        self.assertIsNone(self.orden())


class ResultadoTests(BaseActualizacion):
    def test_el_resultado_aplicado_se_registra_con_sus_eventos_y_libera_la_orden(self):
        ficha = self.importar_ok()
        orden = self.aplicar_ok(ficha["paquete_id"])["orden"]
        self.resultado_del_host(orden["orden_id"], ficha["paquete_id"], duracion_ms=61_000)
        salida = self.tick()
        self.assertEqual(salida["resultado"], {"orden_id": orden["orden_id"], "paquete_id": ficha["paquete_id"], "tipo": "aplicado", "registrado": True})
        f = self.ficha(ficha["paquete_id"])
        self.assertEqual((f["estado"], f["en_curso"], f["revertible"], f["aplicado_en"], f["revertible_hasta"]), ("aplicado", False, True, self.reloj.t, self.reloj.t + 14 * cat.DIA_MS))
        ultima = f["historial"][-1]
        self.assertEqual((ultima["tipo"], ultima["actor"], ultima["detalle"]["resultado"], ultima["detalle"]["duracion_ms"], ultima["detalle"]["respaldo"]), ("aplicado", "sistema", "aplicado", 61_000, True))
        self.assertEqual(self.tipos_de_eventos()[-3:], [cat.EV_APLICADA, cat.EV_MIGRACION, cat.EV_RESULTADO])
        self.assertEqual(self.acciones_asentadas()[-1], cat.A_APLICADO)
        self.assertIsNone(self.orden())
        self.assertFalse((self.carpeta / cat.ARCHIVO_RESULTADO).exists())
        self.assertTrue((self.carpeta / "resultados" / f"{orden['orden_id']}.json").exists())
        self.assertFalse((self.carpeta / "staging" / ficha["paquete_id"]).exists())
        self.assertEqual(self.admin.get(f"{A}/estado/").json()["revertibles"][0]["paquete_id"], ficha["paquete_id"])
        self.assertEqual(self.tick()["resultado"], None)                                            # el mismo resultado no se registra dos veces

    def test_la_reversion_automatica_del_host_deja_el_paquete_revertido(self):
        ficha = self.importar_ok()
        orden = self.aplicar_ok(ficha["paquete_id"])["orden"]
        self.resultado_del_host(orden["orden_id"], ficha["paquete_id"], resultado=cat.R_REVERTIDO, paso=cat.PASO_MIGRAR, error="la migración 0004 falló")
        self.tick()
        f = self.ficha(ficha["paquete_id"])
        self.assertEqual((f["estado"], f["revertible"], f["historial"][-1]["detalle"]["error"]), ("revertido", False, "la migración 0004 falló"))
        self.assertEqual(self.tipos_de_eventos()[-2:], [cat.EV_REVERTIDA, cat.EV_RESULTADO])
        self.assertEqual(self.acciones_asentadas()[-1], cat.A_REVERTIDO)
        self.assertEqual(self.api.post("/api/aula/sesiones/", {"via": "libre", "profesor_id": self.docente_id}, format="json").status_code, 201)

    def test_una_reversion_fallida_se_avisa_y_no_borra_nada(self):
        ficha = self.importar_ok()
        orden = self.aplicar_ok(ficha["paquete_id"])["orden"]
        self.resultado_del_host(orden["orden_id"], ficha["paquete_id"], resultado=cat.R_REVERSION_FALLIDA, paso=cat.PASO_COPIAR, error="copia bloqueada por el antivirus")
        self.tick()
        self.assertEqual(self.ficha(ficha["paquete_id"])["estado"], "reversion_fallida")
        self.assertEqual(self.tipos_de_eventos()[-2:], [cat.EV_REVERSION_FALLIDA, cat.EV_RESULTADO])
        self.assertEqual(self.acciones_asentadas()[-1], cat.A_REVERSION_FALLIDA)
        self.assertTrue((self.carpeta / "paquetes" / f"{ficha['paquete_id']}.avupd").exists())
        # se puede reintentar la reversión
        r = self.admin.post(f"{A}/paquetes/{ficha['paquete_id']}/revertir/", {"nota": "reintento tras apagar el antivirus"}, format="json")
        self.assertEqual((r.status_code, r.json()["orden"]["accion"]), (202, "revertir"), r.content)

    def test_una_aplicacion_aplazada_por_el_host_vuelve_al_estado_anterior(self):
        ficha = self.importar_ok()
        orden = self.aplicar_ok(ficha["paquete_id"])["orden"]
        self.resultado_del_host(orden["orden_id"], ficha["paquete_id"], resultado=cat.R_APLAZADA, paso=cat.PASO_COMPROBAR, error="apareció una clase")
        self.tick()
        self.assertEqual(self.ficha(ficha["paquete_id"])["estado"], "verificado")
        self.assertEqual(self.acciones_asentadas()[-1], cat.A_APLAZADA)
        self.assertEqual(self.tipos_de_eventos()[-2:], [cat.EV_BLOQUEADA, cat.EV_RESULTADO])
        self.assertEqual(self.aplicar(ficha["paquete_id"]).status_code, 202)                        # y se puede volver a intentar

    def test_un_resultado_huerfano_se_archiva_sin_registrar(self):
        ficha = self.importar_ok()
        self.resultado_del_host("orden-inventada", ficha["paquete_id"])
        salida = self.tick()
        self.assertEqual(salida["resultado"], {"orden_id": "orden-inventada", "registrado": False})
        self.assertEqual(self.ficha(ficha["paquete_id"])["estado"], "verificado")
        self.assertFalse((self.carpeta / cat.ARCHIVO_RESULTADO).exists())

    def test_una_orden_sin_resultado_ni_archivo_tras_diez_minutos_se_cierra_como_aplazada(self):
        """El Host nunca tomó la orden (o alguien borró `orden.json`): el aula no se queda con el 503 para siempre."""
        ficha = self.importar_ok()
        self.aplicar_ok(ficha["paquete_id"])
        (self.carpeta / cat.ARCHIVO_ORDEN).unlink()
        self.tick()
        self.assertEqual(self.ficha(ficha["paquete_id"])["estado"], "aplicando")                    # recién emitida: se espera
        self.reloj.avanzar(11 * cat.MINUTO_MS)
        self.tick()
        self.assertEqual(self.ficha(ficha["paquete_id"])["estado"], "verificado")
        self.assertEqual(self.api.post("/api/aula/sesiones/", {"via": "libre", "profesor_id": self.docente_id}, format="json").status_code, 201)


class RevertirTests(BaseActualizacion):
    def aplicado(self) -> dict:
        ficha = self.importar_ok()
        orden = self.aplicar_ok(ficha["paquete_id"])["orden"]
        self.resultado_del_host(orden["orden_id"], ficha["paquete_id"])
        self.tick()
        return self.ficha(ficha["paquete_id"])

    def test_revertir_dentro_de_14_dias_con_nota_deja_la_orden_de_reversion(self):
        ficha = self.aplicado()
        self.reloj.avanzar(13 * cat.DIA_MS)
        r = self.admin.post(f"{A}/paquetes/{ficha['paquete_id']}/revertir/", {"nota": "el boletín sale en blanco"}, format="json")
        self.assertEqual(r.status_code, 202, r.content)
        self.assertEqual((r.json()["estado"], r.json()["accion"], r.json()["orden"]["accion"], r.json()["orden"]["pasos"]), ("aplicando", "revertir", "revertir", list(cat.PASOS_REVERSION)))
        orden = self.orden()
        self.assertEqual((orden["accion"], orden["nota"], orden["modulos"][0]["migraciones"]), ("revertir", "el boletín sale en blanco", [{"nombre": "0004_parche_de_ejemplo", "reverso": "0003_corte_cola_unica"}]))
        self.assertEqual(self.api.post("/api/aula/sesiones/", {"via": "libre", "profesor_id": self.docente_id}, format="json").status_code, 503)
        self.resultado_del_host(orden["orden_id"], ficha["paquete_id"], resultado=cat.R_REVERTIDO, accion=cat.ACCION_REVERTIR)
        self.tick()
        f = self.ficha(ficha["paquete_id"])
        self.assertEqual((f["estado"], f["revertible"], f["aplicado_en"]), ("revertido", False, None))
        self.assertEqual(self.tipos_de_eventos()[-2:], [cat.EV_REVERTIDA, cat.EV_RESULTADO])

    def test_revertir_exige_una_nota(self):
        ficha = self.aplicado()
        r = self.admin.post(f"{A}/paquetes/{ficha['paquete_id']}/revertir/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        self.assertIsNone(self.orden())

    def test_pasados_14_dias_no_se_revierte_y_el_vigilante_archiva(self):
        ficha = self.aplicado()
        self.reloj.avanzar(14 * cat.DIA_MS)
        r = self.admin.post(f"{A}/paquetes/{ficha['paquete_id']}/revertir/", {"nota": "tarde"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "fuera_de_plazo_reversion"))
        self.assertEqual(self.tick()["archivados"], [ficha["paquete_id"]])
        f = self.ficha(ficha["paquete_id"])
        self.assertEqual((f["estado"], f["revertible"]), ("archivado", False))
        self.assertEqual(self.acciones_asentadas()[-1], cat.A_ARCHIVADO)
        r = self.admin.post(f"{A}/paquetes/{ficha['paquete_id']}/revertir/", {"nota": "tarde"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "estado_invalido"))

    def test_revertir_con_una_clase_abierta_se_bloquea(self):
        ficha = self.aplicado()
        self.abrir_clase()
        r = self.admin.post(f"{A}/paquetes/{ficha['paquete_id']}/revertir/", {"nota": "x"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "sesion_activa"))
        self.assertEqual(self.ficha(ficha["paquete_id"])["estado"], "aplicado")

    def test_no_se_revierte_lo_que_no_esta_aplicado(self):
        ficha = self.importar_ok()
        r = self.admin.post(f"{A}/paquetes/{ficha['paquete_id']}/revertir/", {"nota": "x"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "estado_invalido"))


class VentanaTests(BaseActualizacion):
    def programar(self, paquete_id: str, desde_min: int = 30, duracion_min: int = 60):
        return self.admin.post(f"{A}/paquetes/{paquete_id}/programar/", {"desde": self.reloj.t + desde_min * cat.MINUTO_MS, "hasta": self.reloj.t + (desde_min + duracion_min) * cat.MINUTO_MS}, format="json")

    def test_programar_y_desprogramar(self):
        ficha = self.importar_ok()
        r = self.programar(ficha["paquete_id"])
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["estado"], r.json()["ventana"]), ("programado", {"desde": self.reloj.t + 30 * cat.MINUTO_MS, "hasta": self.reloj.t + 90 * cat.MINUTO_MS}))
        self.assertEqual(self.tipos_de_eventos()[-1], cat.EV_PROGRAMADA)
        self.assertEqual(self.acciones_asentadas()[-1], cat.A_PROGRAMADO)
        self.assertEqual(self.admin.get(f"{A}/estado/").json()["estado"], "programado")
        self.assertEqual(self.api.get("/health/").json()["actualizacion"]["programados"], 1)
        r = self.admin.post(f"{A}/paquetes/{ficha['paquete_id']}/desprogramar/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["estado"], r.json()["ventana"]), (200, "verificado", None))
        self.assertEqual(self.acciones_asentadas()[-1], cat.A_DESPROGRAMADO)
        for malo in ({"desde": self.reloj.t - cat.DIA_MS, "hasta": self.reloj.t}, {"desde": self.reloj.t, "hasta": self.reloj.t + cat.MINUTO_MS}, {"desde": "mañana"}, {}):
            r = self.admin.post(f"{A}/paquetes/{ficha['paquete_id']}/programar/", malo, format="json")
            self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"), malo)

    def test_el_vigilante_abre_la_ventana_sin_clase_y_la_aplaza_con_clase(self):
        ficha = self.importar_ok()
        self.programar(ficha["paquete_id"], desde_min=30, duracion_min=60)
        self.assertEqual(self.tick()["ordenes"], [])                                                 # antes de la ventana: nada
        self.reloj.avanzar(31 * cat.MINUTO_MS)
        clase = self.abrir_clase()
        salida = self.tick()
        self.assertEqual((salida["ordenes"], salida["bloqueadas"]), ([], [{"paquete_id": ficha["paquete_id"], "motivo": "sesion_activa"}]))
        self.assertEqual(self.tick()["bloqueadas"], [])                                              # una sola fila `bloqueada` por ventana
        self.assertEqual(self.ficha(ficha["paquete_id"])["estado"], "programado")
        self.assertEqual(self.tipos_de_eventos()[-1], cat.EV_BLOQUEADA)
        self.assertIsNone(self.orden())
        self.assertEqual(self.api.post(f"/api/aula/sesiones/{clase['id']}/cerrar/", {}, format="json").status_code, 200)
        salida = self.tick()
        self.assertEqual(len(salida["ordenes"]), 1)
        orden = self.orden()
        self.assertEqual((orden["paquete_id"], orden["emitida_por"], orden["ventana"]), (ficha["paquete_id"], "sistema", {"desde": self.t0 + 30 * cat.MINUTO_MS, "hasta": self.t0 + 90 * cat.MINUTO_MS}))
        self.assertEqual(self.ficha(ficha["paquete_id"])["estado"], "aplicando")

    def test_una_ventana_vencida_vuelve_a_verificado(self):
        ficha = self.importar_ok()
        self.programar(ficha["paquete_id"], desde_min=30, duracion_min=60)
        self.abrir_clase()
        self.reloj.avanzar(91 * cat.MINUTO_MS)
        self.assertEqual(self.tick()["vencidas"], [ficha["paquete_id"]])
        f = self.ficha(ficha["paquete_id"])
        self.assertEqual((f["estado"], f["ventana"]), ("verificado", None))
        self.assertIsNone(self.orden())

    def test_el_vigilante_anuncia_un_paquete_nuevo_una_sola_vez(self):
        self.dejar_en_usb(self.avupd())
        self.assertEqual(len(self.tick()["detectados"]), 1)
        self.assertEqual(self.tipos_de_eventos(con_deteccion=True), [cat.EV_DISPONIBLE])
        self.assertEqual(self.tick()["detectados"], [])
        self.assertEqual(m.Historial.objects.count(), 0)                                             # detectar no es un hecho del historial


class PermisosTests(BaseActualizacion):
    def test_el_tecnico_importa_y_lee_pero_no_aplica_ni_programa(self):
        tecnico = self.tecnico()
        ficha = self.importar_ok(cliente=tecnico)
        self.assertEqual(ficha["importado_por"] != self.admin_id, True)
        self.assertEqual(tecnico.get(f"{A}/estado/").status_code, 200)
        self.assertEqual(tecnico.get(f"{A}/historial/").status_code, 200)
        r = self.aplicar(ficha["paquete_id"], tecnico)
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["permiso"]), (403, "sin_permiso", "update.apply"), r.content)
        self.assertIsNone(self.orden())
        r = tecnico.post(f"{A}/paquetes/{ficha['paquete_id']}/programar/", {"desde": self.reloj.t, "hasta": self.reloj.t + cat.DIA_MS}, format="json")
        self.assertEqual((r.status_code, r.json()["permiso"]), (403, "update.schedule"))
        r = tecnico.post(f"{A}/paquetes/{ficha['paquete_id']}/revertir/", {"nota": "x"}, format="json")
        self.assertEqual((r.status_code, r.json()["permiso"]), (403, "update.apply"))

    def test_el_profesor_reportes_y_el_alumno_no_ven_nada(self):
        self.dejar_en_usb(self.avupd())
        for cliente, rotulo in ((self.docente, "docente"), (self.reportes(), "reportes")):
            for ruta in ("estado/", "paquetes/", "historial/"):
                r = cliente.get(f"{A}/{ruta}")
                self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"), f"{rotulo} {ruta}")
            r = cliente.post(f"{A}/paquetes/importar/", {"candidato": "x"}, format="json")
            self.assertEqual(r.status_code, 403, rotulo)
        self.assertEqual(self.archivos_escritos(), [])
        estudiante = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, dispositivo=self.TABLETA)
        self.assertEqual(estudiante.get(f"{A}/estado/").status_code, 403)

    def test_sin_sesion_obligatoria_el_prototipo_deja_pasar_y_con_ella_exige_sesion(self):
        from django.test import override_settings
        self.assertEqual(self.api.get(f"{A}/estado/").status_code, 200)
        with override_settings(AVACOM_LMS_EXIGIR_SESION=True):
            self.assertEqual(self.api.get(f"{A}/estado/").status_code, 401)
            self.assertEqual(self.admin.get(f"{A}/estado/").status_code, 200)


class HistorialTests(BaseActualizacion):
    def test_el_historial_del_nodo_lista_lo_ultimo_primero_y_filtra_por_tipo(self):
        ficha = self.importar_ok()
        self.aplicar_ok(ficha["paquete_id"])
        r = self.admin.get(f"{A}/historial/?limite=2")
        self.assertEqual([h["tipo"] for h in r.json()["historial"]], ["aplicando", "verificado"])
        r = self.admin.get(f"{A}/historial/?tipo=recibido&tipo=verificado")
        self.assertEqual(sorted(h["tipo"] for h in r.json()["historial"]), ["recibido", "verificado"])
        self.assertEqual(self.admin.get(f"{A}/historial/?limite=x").status_code, 400)
        self.assertEqual(self.admin.get(f"{A}/paquetes/no-existe/").status_code, 404)
        for fila in r.json()["historial"]:
            self.assertEqual(set(fila), {"id", "paquete_id", "tipo", "en", "actor", "serie", "version_producto", "detalle"})

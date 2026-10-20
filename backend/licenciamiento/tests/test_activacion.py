"""
CAP-110 · FUN-188 · FUN-191 · JRN-020 por la API real, con un nodo real: pedir la solicitud, activar un archivo emitido para ESTE equipo, renovar, liberar y volver a activar. Cada caso mira
lo que importa de verdad: el estado que ve el administrador, el historial, el espejo en la carpeta de estado, el asiento en la bitácora y el evento (sin contenido de licencia).
"""
from __future__ import annotations

import json
import uuid

from audit.models import Bitacora
from licenciamiento import models as m
from licenciamiento.dominio import catalogos as cat
from licenciamiento.dominio import licencia as lic_mod
from licenciamiento.dominio import solicitud as sol
from licenciamiento.dominio.errores import LicenciaInvalida
from licenciamiento.dominio.politica import DIA_MS, HORA_MS

from . import emisor
from .base import CRUDOS_A, CRUDOS_B, L, BaseLicencia


class SolicitudTests(BaseLicencia):
    def test_la_solicitud_la_firma_el_nodo_lleva_la_huella_hasheada_y_deja_asiento(self):
        r = self.admin.post(f"{L}/solicitud/", {}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        cuerpo = r.json()
        self.assertEqual((cuerpo["nivel"], cuerpo["k"], cuerpo["factores"]), ("hardware", 3, 4))
        self.assertTrue(cuerpo["nombre"].startswith("solicitud-") and cuerpo["nombre"].endswith(".avreq"))
        datos = self.bytes_de(cuerpo["archivo_b64"])
        leida = sol.leer_solicitud(datos)                                              # la verifica el emisor contra la llave que declara
        self.assertEqual((leida.nivel, leida.huella.k, len(leida.huella.factores), leida.clave_nodo), ("hardware", 3, 4, self.s.nodo.clave_publica()))
        self.assertEqual(lic_mod.de_texto(cuerpo["texto"], sol.tlv.MAGIC_SOLICITUD), datos)
        for crudo in CRUDOS_A.values():                                                # ningún identificador crudo viaja
            self.assertNotIn(crudo.encode(), datos)
        asiento = Bitacora.objects.filter(modulo="licencia").order_by("secuencia").last()
        self.assertEqual(asiento.accion, cat.A_SOLICITUD)

    def test_cada_solicitud_trae_su_propio_nonce(self):
        a, b = self.solicitud_del_nodo(), self.solicitud_del_nodo()
        self.assertNotEqual(a.nonce, b.nonce)
        self.assertEqual(a.huella, b.huella)

    def test_un_equipo_con_hardware_pobre_pide_una_huella_de_instalacion_y_nunca_se_le_niega(self):
        self.huella.valores = {1: "9f1c2a3e-1111-4b2b-8c3d-aaaaaaaaaa01", 2: "03000200-0400-0500-0006-000700080009", 3: "Default string", 4: "To be filled by O.E.M."}
        s = self.solicitud_del_nodo()
        self.assertEqual((s.nivel, s.huella.k, [f for f, _ in s.huella.factores]), ("instalacion", 1, [6]))


class ActivarTests(BaseLicencia):
    def test_activar_una_licencia_emitida_para_este_equipo(self):
        cuerpo = self.activar_ok()
        self.assertEqual((cuerpo["accion"], cuerpo["estado"], cuerpo["motivo"]), ("activada", "activa", "vigente"))
        self.assertEqual(cuerpo["licencia"]["serie"], 1)
        self.assertEqual(cuerpo["licencia"]["limites"], {"equipos": 55, "usuarios": 1200, "concurrentes_normal": 50, "concurrentes_pico": 100})
        self.assertEqual(sorted(cuerpo["capacidades"]["habilitadas"]), sorted(cat.CAPACIDADES_LICENCIABLES))
        self.assertEqual(cuerpo["vigencia"]["dias_restantes"], 335)
        self.assertEqual(cuerpo["huella"], {"nivel": "hardware", "coincide": True, "parcial": False, "k": 3, "factores": 4, "coinciden": 4})
        fila = m.Licencia.objects.get()
        self.assertEqual((fila.tipo, fila.serie, fila.kid, fila.instalada_por), ("activada", 1, "dev-1", self.admin_id))
        self.assertIsNotNone(self.s.almacen.leer(cat.ARCHIVO_ESPEJO))                    # el espejo para reactivar tras una restauración (FUN-194)
        self.assertEqual(self.estado()["estado"], "activa")

    def test_activar_deja_asiento_y_evento_sin_contenido_de_licencia(self):
        datos = self.avlic()
        texto = lic_mod.a_texto(datos)
        self.assertEqual(self.admin.post(f"{L}/activar/", {"licencia": texto}, format="json").status_code, 200)
        asientos = list(Bitacora.objects.filter(modulo="licencia").order_by("secuencia"))
        self.assertIn(cat.A_ACTIVADA, [a.accion for a in asientos])
        evento = m.EventoSalida.objects.get(tipo_evento=cat.EV_ACTIVADA)
        for a in asientos:
            ahi = json.dumps([a.valor_nuevo, a.valor_anterior], default=str)
            self.assertNotIn(texto, ahi)
            self.assertNotIn(datos.hex(), ahi)
            self.assertNotIn("AVL1.", ahi)
            for crudo in CRUDOS_A.values():
                self.assertNotIn(crudo, ahi)
        carga = json.dumps(evento.carga)
        self.assertEqual(set(evento.carga), {"licencia_id", "serie", "tipo", "archivo", "vence", "instante"})
        self.assertNotIn("AVL1.", carga)

    def test_el_archivo_tambien_se_puede_mandar_en_base64(self):
        import base64
        r = self.admin.post(f"{L}/activar/", {"archivo_b64": base64.b64encode(self.avlic()).decode()}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

    def test_una_licencia_de_otro_equipo_se_rechaza_con_409_y_no_cambia_nada(self):
        r = self.activar(huella=emisor.huella_de(self.factores(CRUDOS_B)))
        self.assertEqual(r.status_code, 409, r.content)
        self.assertEqual((r.json()["codigo"], r.json()["k"]), ("huella_no_coincide", 3))
        self.assertEqual(m.Licencia.objects.count(), 0)
        self.assertEqual(self.estado()["estado"], "sin_licencia")

    def test_un_archivo_con_la_firma_alterada_se_rechaza_y_deja_asiento_de_firma_invalida(self):
        datos = bytearray(self.avlic())
        datos[40] ^= 0x01
        r = self.admin.post(f"{L}/activar/", {"licencia": lic_mod.a_texto(bytes(datos))}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual((r.json()["codigo"], r.json()["motivo"]), ("licencia_invalida", "firma_invalida"))
        self.assertEqual(m.Licencia.objects.count(), 0)
        self.assertTrue(Bitacora.objects.filter(accion=cat.A_FIRMA_INVALIDA, resultado="denegado").exists())

    def test_un_kid_desconocido_se_rechaza(self):
        r = self.activar_con_llave_ajena()
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(r.json()["motivo"], "kid_desconocido")

    def activar_con_llave_ajena(self):
        from licenciamiento.dominio import firma, tlv
        privada = firma.par_nuevo()[0]
        sin_firma = lic_mod.sin_firma(self.licencia(), "llave-ajena")
        datos = tlv.sellar(sin_firma, lambda d: firma.firmar(privada, d))
        return self.admin.post(f"{L}/activar/", {"licencia": lic_mod.a_texto(datos)}, format="json")

    def test_el_texto_sin_la_forma_exacta_se_rechaza(self):
        for malo in ("", "AVL1.", "AVL1.@@@", "hola", "AVL2." + lic_mod.a_texto(self.avlic())[5:]):
            r = self.admin.post(f"{L}/activar/", {"licencia": malo}, format="json")
            self.assertIn(r.status_code, (400,), (malo, r.content))
        r = self.admin.post(f"{L}/activar/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))

    def test_un_copiar_pegar_con_saltos_de_linea_en_los_extremos_se_acepta(self):
        r = self.admin.post(f"{L}/activar/", {"licencia": "\n  " + lic_mod.a_texto(self.avlic()) + "  \r\n"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

    def test_una_licencia_de_desarrollo_no_se_acepta_en_un_nodo_de_produccion(self):
        from dataclasses import replace
        self.s.config = replace(self.s.config, entorno="produccion")
        r = self.activar(tipo="desarrollo")
        self.assertEqual((r.status_code, r.json()["motivo"]), (400, "tipo_no_admitido"))

    def test_reactivar_el_mismo_archivo_no_cambia_nada_y_queda_reactivada(self):
        datos = self.avlic()
        texto = lic_mod.a_texto(datos)
        self.assertEqual(self.admin.post(f"{L}/activar/", {"licencia": texto}, format="json").json()["accion"], "activada")
        self.assertEqual(self.admin.post(f"{L}/activar/", {"licencia": texto}, format="json").json()["accion"], "reactivada")
        self.assertEqual([f.tipo for f in m.Licencia.objects.order_by("id")], ["activada", "reactivada"])


class RenovarTests(BaseLicencia):
    def setUp(self):
        super().setUp()
        self.activar_ok()

    def test_renovar_con_una_serie_posterior_de_la_misma_licencia(self):
        cuerpo = self.activar_ok(via="renovar", serie=2, emitida=self.t0 - DIA_MS, vence=self.t0 + 700 * DIA_MS)
        self.assertEqual((cuerpo["accion"], cuerpo["licencia"]["serie"], cuerpo["vigencia"]["dias_restantes"]), ("renovada", 2, 700))
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento=cat.EV_RENOVADA).exists())
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_RENOVADA).count(), 1)

    def test_no_se_puede_volver_a_una_serie_anterior_ni_repetir_la_misma_como_renovacion(self):
        self.activar_ok(via="renovar", serie=2, emitida=self.t0 - DIA_MS)
        for serie in (1, 2):
            r = self.activar(via="renovar", serie=serie, emitida=self.t0)
            self.assertEqual((r.status_code, r.json()["motivo"]), (400, "serie_no_posterior"), serie)

    def test_renovar_otra_licencia_distinta_se_rechaza(self):
        r = self.activar(via="renovar", id=str(uuid.UUID(int=0xBEEF)), serie=5)
        self.assertEqual((r.status_code, r.json()["motivo"]), (400, "otra_licencia"))

    def test_con_una_licencia_sana_no_se_cambia_por_otra_sin_liberar_primero(self):
        r = self.activar(id=str(uuid.UUID(int=0xBEEF)))
        self.assertEqual((r.status_code, r.json()["motivo"]), (400, "otra_licencia"))

    def test_una_serie_posterior_por_activar_cuenta_como_renovacion_y_la_pide_con_su_permiso(self):
        tecnico = self.tecnico()
        r = self.activar(cliente=tecnico, serie=2, emitida=self.t0 - DIA_MS)
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))
        self.assertEqual(self.activar(serie=2, emitida=self.t0 - DIA_MS).json()["accion"], "renovada")

    def test_renovar_sin_licencia_instalada_se_rechaza(self):
        m.Licencia.objects.all().delete()
        r = self.activar(via="renovar", serie=2)
        self.assertEqual((r.status_code, r.json()["motivo"]), (400, "sin_licencia_instalada"))


class TrasladoTests(BaseLicencia):
    """D-10 · JRN-020: pasar la licencia al equipo nuevo. El Maestro se lo da al TÉCNICO (FUN-188, `license.activate`); renovar (FUN-191, `license.renew`) es de la administración."""

    def la_base_restaurada_trae_la_licencia_del_equipo_viejo(self):
        """El equipo nuevo restauró la base del viejo: el historial trae la serie 1, emitida para el hardware B, y el nodo corre ahora en el hardware A."""
        self.huella.valores = dict(CRUDOS_B)
        self.activar_ok(huella=emisor.huella_de(self.factores(CRUDOS_B)))
        self.huella.valores = dict(CRUDOS_A)
        e = self.evaluar()
        self.assertEqual((e.estado.estado, e.estado.motivo), (cat.EN_GRACIA, cat.M_HUELLA_DISTINTA))

    def test_el_tecnico_pasa_la_licencia_con_la_serie_siguiente_emitida_para_este_equipo(self):
        self.la_base_restaurada_trae_la_licencia_del_equipo_viejo()
        r = self.activar(cliente=self.tecnico(), serie=2, emitida=self.t0 - HORA_MS)                       # huella A: la de este equipo
        self.assertEqual(r.status_code, 200, r.content)
        cuerpo = r.json()
        self.assertEqual((cuerpo["accion"], cuerpo["estado"], cuerpo["licencia"]["serie"], cuerpo["huella"]["coincide"]), ("activada", "activa", 2, True))
        self.assertEqual([f.tipo for f in m.Licencia.objects.order_by("id")], ["activada", "activada"])
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_ACTIVADA).count(), 2)                         # dos activaciones…
        self.assertFalse(Bitacora.objects.filter(accion=cat.A_RENOVADA).exists())                          # …y ninguna renovación

    def test_pasar_la_licencia_no_le_da_al_tecnico_el_poder_de_renovar(self):
        self.la_base_restaurada_trae_la_licencia_del_equipo_viejo()
        r = self.activar(cliente=self.tecnico(), via="renovar", serie=2, emitida=self.t0 - HORA_MS)
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["permiso"]), (403, "sin_permiso", "license.renew"))

    def test_una_serie_posterior_con_la_misma_huella_sigue_siendo_una_renovacion_y_la_pide_con_su_permiso(self):
        self.activar_ok()
        r = self.activar(cliente=self.tecnico(), serie=2, emitida=self.t0 - HORA_MS)                       # misma huella: no es un traslado
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["permiso"]), (403, "sin_permiso", "license.renew"))
        self.assertEqual(self.activar(serie=2, emitida=self.t0 - HORA_MS).json()["accion"], "renovada")


class LiberarTests(BaseLicencia):
    def test_liberar_entrega_el_avrel_firmado_y_el_equipo_deja_de_usar_la_licencia(self):
        activada = self.activar_ok()
        r = self.admin.post(f"{L}/liberar/", {}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        cuerpo = r.json()
        liberacion = sol.leer_liberacion(self.bytes_de(cuerpo["archivo_b64"]))
        self.assertEqual((liberacion.licencia_id, liberacion.serie, liberacion.clave_nodo), (activada["licencia"]["id"], 1, self.s.nodo.clave_publica()))
        self.assertTrue(cuerpo["nombre"].endswith(".avrel") and cuerpo["texto"].startswith("AVR1."))
        self.assertEqual(cuerpo["estado"], "sin_licencia")                              # sigue la ventana de evaluación, que no se reinicia
        self.assertEqual([f.tipo for f in m.Licencia.objects.order_by("id")], ["activada", "liberada"])
        self.assertIsNone(self.s.almacen.leer(cat.ARCHIVO_ESPEJO))
        self.assertTrue(Bitacora.objects.filter(accion=cat.A_LIBERADA).exists())
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento=cat.EV_LIBERADA).exists())

    def test_una_base_restaurada_no_resucita_una_licencia_liberada(self):
        """Se libera; después «se restaura una base vieja» que todavía trae la licencia: las liberadas viven también fuera de la base y se vuelve a liberar."""
        self.activar_ok()
        self.admin.post(f"{L}/liberar/", {}, format="json")
        fila = m.Licencia.objects.filter(tipo="activada").get()
        m.Licencia.objects.filter(tipo="liberada").delete()                              # la base «restaurada» no sabe de la liberación
        self.s.almacen.escribir(cat.ARCHIVO_ESPEJO, bytes(fila.archivo))                 # y hasta el espejo reaparece
        self.assertEqual(self.estado()["estado"], "sin_licencia")
        e = self.evaluar()
        self.assertEqual(e.estado.estado, "sin_licencia")
        self.assertEqual([f.tipo for f in m.Licencia.objects.order_by("id")], ["activada", "liberada"])
        self.assertIsNone(self.s.almacen.leer(cat.ARCHIVO_ESPEJO))

    def test_volver_a_activar_el_mismo_archivo_deshace_la_liberacion(self):
        datos = self.avlic()
        texto = lic_mod.a_texto(datos)
        self.admin.post(f"{L}/activar/", {"licencia": texto}, format="json")
        self.admin.post(f"{L}/liberar/", {}, format="json")
        r = self.admin.post(f"{L}/activar/", {"licencia": texto}, format="json")
        self.assertEqual((r.status_code, r.json()["estado"], r.json()["accion"]), (200, "activa", "activada"))
        self.assertEqual(self.evaluar().estado.estado, "activa")

    def test_sin_licencia_instalada_no_hay_nada_que_liberar(self):
        r = self.admin.post(f"{L}/liberar/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "conflicto"))


class PermisosPorRolTests(BaseLicencia):
    """P-15: el técnico y la administración activan y leen; sólo la administración renueva; el profesor, Reportes y el alumno no ven nada de la licencia pero sí qué módulos hay."""

    def test_la_administracion_hace_todo(self):
        for ruta in ("estado", "consumo", "capacidades"):
            self.assertEqual(self.admin.get(f"{L}/{ruta}/").status_code, 200, ruta)
        self.assertEqual(self.admin.post(f"{L}/solicitud/", {}, format="json").status_code, 201)
        self.assertEqual(self.activar().status_code, 200)
        self.assertEqual(self.admin.post(f"{L}/reloj/confirmar/", {}, format="json").status_code, 200)

    def test_el_tecnico_lee_pide_y_activa_pero_no_renueva(self):
        tecnico = self.tecnico()
        self.assertEqual(tecnico.get(f"{L}/estado/").status_code, 200)
        self.assertEqual(tecnico.get(f"{L}/consumo/").status_code, 200)
        self.assertEqual(tecnico.post(f"{L}/solicitud/", {}, format="json").status_code, 201)
        self.assertEqual(self.activar(cliente=tecnico).status_code, 200)
        r = self.activar(cliente=tecnico, via="renovar", serie=2, emitida=self.t0 - DIA_MS)
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["permiso"]), (403, "sin_permiso", "license.renew"))
        self.assertEqual(tecnico.post(f"{L}/liberar/", {}, format="json").status_code, 201)

    def test_el_profesor_el_alumno_y_reportes_no_ven_datos_de_la_licencia_pero_si_los_modulos(self):
        reportes = self.reportes()
        for cliente in (self.docente, reportes):
            for metodo, ruta in (("get", "estado"), ("get", "consumo"), ("post", "solicitud"), ("post", "activar"), ("post", "renovar"), ("post", "liberar"), ("post", "reloj/confirmar")):
                r = getattr(cliente, metodo)(f"{L}/{ruta}/", **({"data": {}, "format": "json"} if metodo == "post" else {}))
                self.assertEqual(r.status_code, 403, (ruta, r.content))
                self.assertEqual(r.json()["codigo"], "sin_permiso")
            r = cliente.get(f"{L}/capacidades/")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(set(r.json()), {"estado", "restringe", "habilitadas", "no_disponibles"})        # sin un solo detalle de la licencia

    def test_sin_sesion_con_la_sesion_obligatoria_no_se_ve_nada(self):
        from django.test import override_settings
        from rest_framework.test import APIClient
        with override_settings(AVACOM_LMS_EXIGIR_SESION=True):
            for ruta in ("estado", "consumo", "capacidades"):
                self.assertEqual(APIClient().get(f"{L}/{ruta}/").status_code, 401, ruta)
            self.assertEqual(APIClient().post(f"{L}/activar/", {}, format="json").status_code, 401)

    def test_la_denegacion_de_un_permiso_de_licencia_se_asienta_como_acceso_denegado_de_acceso_no_de_licencia(self):
        """El profesor que intenta ver la licencia recibe un 403 normal de permisos (queda como `acceso.denegado`); el «no disponible por licencia» es OTRA cosa y es un 402."""
        self.docente.get(f"{L}/estado/")
        self.assertTrue(Bitacora.objects.filter(accion="acceso.denegado").exists())
        self.assertFalse(Bitacora.objects.filter(accion=cat.A_BLOQUEO).exists())


class LicenciaQueEmpiezaEnElFuturoTests(BaseLicencia):
    def test_una_licencia_que_todavia_no_empieza_se_rechaza_para_no_dejar_al_nodo_sin_licencia(self):
        self.activar_ok()
        r = self.activar(via="renovar", serie=2, emitida=self.t0 + DIA_MS, desde=self.t0 + 20 * DIA_MS, vence=self.t0 + 400 * DIA_MS)
        self.assertEqual((r.status_code, r.json()["motivo"]), (400, "aun_no_vigente"))
        self.assertEqual(self.estado()["estado"], "activa")                                           # la vigente sigue como estaba
        r = self.activar(via="renovar", serie=2, emitida=self.t0 + DIA_MS, desde=self.t0 + DIA_MS // 2, vence=self.t0 + 400 * DIA_MS)       # empieza en menos de un día: se acepta
        self.assertEqual(r.status_code, 200, r.content)

    def test_lo_que_se_acepta_por_empezar_dentro_de_la_tolerancia_rige_desde_ya_aunque_la_evaluacion_haya_vencido(self):
        """Revisión independiente, BUG-1: se aceptaba el archivo (`desde` a menos de un día) pero el estado lo tomaba por «aún no vigente»: el colegio con meses de uso quedaba degradado hasta que llegara `desde`."""
        self.evaluar("arranque")                                                                        # empieza la ventana de evaluación de 30 días…
        self.reloj.avanzar(40 * DIA_MS)                                                                 # …y ya acabó
        self.assertEqual(self.evaluar("tick").estado.estado, cat.DEGRADADA)
        self.assertEqual(self.admin.get("/api/reportes/clases/").status_code, 402)
        ahora = self.reloj.t
        cuerpo = self.activar_ok(emitida=ahora - DIA_MS, desde=ahora + 12 * HORA_MS, vence=ahora + 365 * DIA_MS)
        self.assertEqual((cuerpo["accion"], cuerpo["estado"], cuerpo["motivo"]), ("activada", "activa", "vigente"))
        self.assertEqual(cuerpo["capacidades"]["no_disponibles"], [])
        self.assertNotEqual(self.admin.get("/api/reportes/clases/").status_code, 402)                  # y se nota donde importa: el módulo vuelve ahora, no mañana

    def test_una_renovacion_que_empieza_dentro_de_la_tolerancia_no_le_quita_nada_al_colegio(self):
        self.activar_ok()
        cuerpo = self.activar_ok(via="renovar", serie=2, emitida=self.t0 - HORA_MS, desde=self.t0 + 12 * HORA_MS, vence=self.t0 + 700 * DIA_MS)
        self.assertEqual((cuerpo["accion"], cuerpo["estado"], cuerpo["capacidades"]["no_disponibles"]), ("renovada", "activa", []))
        self.reloj.avanzar(13 * HORA_MS)                                                                # cuando llega su `desde` nada cambia
        self.assertEqual(self.evaluar("tick").estado.estado, cat.ACTIVA)


class CopiaTests(BaseLicencia):
    """CAP-111: guardar una copia de la licencia vigente bajo custodia de la institución."""

    def test_la_copia_es_el_mismo_archivo_firmado_que_se_instalo_y_no_cambia_nada(self):
        datos = self.avlic()
        self.admin.post(f"{L}/activar/", {"licencia": lic_mod.a_texto(datos)}, format="json")
        asientos = Bitacora.objects.filter(modulo="licencia").count()
        r = self.admin.get(f"{L}/copia/")
        self.assertEqual(r.status_code, 200, r.content)
        cuerpo = r.json()
        self.assertEqual(self.bytes_de(cuerpo["archivo_b64"]), datos)
        self.assertEqual(lic_mod.de_texto(cuerpo["texto"]), datos)
        self.assertRegex(cuerpo["nombre"], r"^licencia-[0-9a-f]{8}-serie1\.avlic$")
        self.assertEqual(cuerpo["licencia"]["serie"], 1)
        self.assertEqual(Bitacora.objects.filter(modulo="licencia").count(), asientos)                # leer no deja asiento

    def test_sin_licencia_instalada_no_hay_nada_que_copiar(self):
        r = self.admin.get(f"{L}/copia/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "no_encontrado"))

    def test_la_copia_la_ve_quien_puede_leer_la_licencia_y_nadie_mas(self):
        self.activar_ok()
        self.assertEqual(self.tecnico().get(f"{L}/copia/").status_code, 200)
        self.assertEqual(self.docente.get(f"{L}/copia/").status_code, 403)

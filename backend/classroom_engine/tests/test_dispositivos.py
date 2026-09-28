"""
El aula con MOD-009 delante: la tableta que se une queda en el inventario con su sesión de alumno
(Dim Sesión Alumno); una tableta bloqueada no entra ni recibe lanzamientos; el lanzamiento guarda a
quién llegó, a quién dejó fuera y con qué reglas. Sin biblioteca real ni sesión JWT (Q-34 abierta).
"""
from __future__ import annotations

from acceso.models import Organizacion
from device_manager import models as m9

from .. import models as m
from ..dominio import sesion as dom
from .test_sesiones import ConSesionDeClase


class ConNodoInstalado(ConSesionDeClase):
    """MOD-009 necesita la organización del nodo para inventariar; se crea directa, sin pasar por el login."""

    def setUp(self):
        super().setUp()
        Organizacion.objects.create(id="org-1", codigo="IE-PRUEBA", nombre="IE Prueba", pais="CO", idioma="es",
                                    locale="es-CO", zona_horaria="America/Bogota", creado_en=1)

    def tableta(self, huella: str) -> m9.Dispositivo:
        return m9.Dispositivo.objects.get(identificador_hw=huella)


class TabletaEnLaClaseTests(ConNodoInstalado):
    def test_unirse_registra_la_tableta_y_abre_su_sesion_de_alumno(self):
        s = self.iniciar()
        u = self.unirse(s, dispositivo="tab-1", plataforma="android", version_app="0.4.2")
        tableta = self.tableta("tab-1")
        self.assertEqual((tableta.nombre, tableta.plataforma, tableta.version_app, tableta.bloqueado), ("tab-1", "android", "0.4.2", False))
        p = u["participante"]
        self.assertEqual((p["dispositivo"], p["dispositivo_id"], p["dispositivo_bloqueado"]), ("tab-1", tableta.id, False))
        abierta = m9.DimSesionAlumno.objects.get(pk=p["dim_sesion_alumno_id"])
        self.assertEqual((abierta.alumno_id, abierta.dispositivo_id, abierta.finalizada_en), ("ana", tableta.id, None))
        inventario = self.api.get("/api/dispositivos/").json()
        self.assertEqual((inventario[0]["nombre"], inventario[0]["sesion_abierta"]["alumno_id"], inventario[0]["en_linea"]), ("tab-1", "ana", True))
        # salir cierra la sesión de alumno; volver la reabre
        pid = p["id"]
        ruta = f"/api/aula/sesiones/{s['id']}/participantes/{pid}/presencia/"
        self.api.post(ruta, {"estado": "salio"}, format="json")
        abierta.refresh_from_db()
        self.assertEqual(abierta.motivo_cierre, "usuario")
        r = self.api.post(ruta, {"estado": "conectado"}, format="json")
        nueva = r.json()["participante"]["dim_sesion_alumno_id"]
        self.assertNotEqual(nueva, abierta.id)
        self.assertIsNone(m9.DimSesionAlumno.objects.get(pk=nueva).finalizada_en)
        # el sondeo de la tableta es su latido
        m9.Dispositivo.objects.filter(pk=tableta.id).update(ultimo_latido_en=1)
        self.api.get(f"/api/aula/sesiones/{s['id']}/estado/?participante={pid}")
        self.assertGreater(m9.Dispositivo.objects.get(pk=tableta.id).ultimo_latido_en, 1)

    def test_sin_huella_la_participacion_sigue_valida_sin_tableta(self):
        s = self.iniciar()
        u = self.unirse(s, dispositivo="")
        self.assertEqual((u["participante"]["dispositivo_id"], u["participante"]["dim_sesion_alumno_id"]), ("", ""))
        self.assertEqual(m9.Dispositivo.objects.count(), 0)

    def test_inv_011_dos_alumnos_en_la_misma_tableta_no_coexisten(self):
        s = self.iniciar()
        ana = self.unirse(s, persona="ana", dispositivo="tab-compartida")["participante"]
        luis = self.unirse(s, persona="luis", rotulo="Luis", dispositivo="tab-compartida")["participante"]
        self.assertEqual(ana["dispositivo_id"], luis["dispositivo_id"])
        self.assertEqual(m9.DimSesionAlumno.objects.get(pk=ana["dim_sesion_alumno_id"]).motivo_cierre, "relevo")
        self.assertEqual(m9.DimSesionAlumno.objects.filter(dispositivo_id=ana["dispositivo_id"], finalizada_en__isnull=True).count(), 1)

    def test_cerrar_la_clase_cierra_las_sesiones_de_alumno_en_las_tabletas(self):
        s = self.iniciar()
        p = self.unirse(s, dispositivo="tab-1")["participante"]
        self.api.post(f"/api/aula/sesiones/{s['id']}/cerrar/", {}, format="json")
        cerrada = m9.DimSesionAlumno.objects.get(pk=p["dim_sesion_alumno_id"])
        self.assertEqual((cerrada.motivo_cierre, cerrada.finalizada_en is not None), ("sistema", True))


class TabletaBloqueadaTests(ConNodoInstalado):
    def test_bloqueada_no_entra_ni_se_admite_y_el_profesor_lo_ve(self):
        s = self.iniciar()
        p = self.unirse(s, dispositivo="tab-1")["participante"]
        r = self.api.post(f"/api/dispositivos/{p['dispositivo_id']}/bloquear/", {"motivo": "mal uso"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        detalle = self.api.get(f"/api/aula/sesiones/{s['id']}/").json()
        self.assertTrue(detalle["participantes"][0]["dispositivo_bloqueado"])
        estado = self.api.get(f"/api/aula/sesiones/{s['id']}/estado/?participante={p['id']}").json()
        self.assertTrue(estado["participante"]["dispositivo_bloqueado"])
        # otra persona con esa tableta no entra; la misma persona tampoco vuelve a entrar tras salir
        r = self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": s["codigo_union"], "persona_id": "luis", "dispositivo": "tab-1"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_bloqueado"))
        self.assertEqual(m.Participante.objects.filter(sesion_id=s["id"]).count(), 1)
        self.api.post(f"/api/aula/sesiones/{s['id']}/participantes/{p['id']}/expulsar/", {"motivo": "x"}, format="json")
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/participantes/{p['id']}/admitir/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_bloqueado"))
        self.api.post(f"/api/dispositivos/{p['dispositivo_id']}/desbloquear/", {}, format="json")
        self.assertEqual(self.api.post(f"/api/aula/sesiones/{s['id']}/participantes/{p['id']}/admitir/", {}, format="json").json()["estado"], "conectado")

    def test_una_tableta_retirada_tampoco_entra(self):
        s = self.iniciar()
        p = self.unirse(s, dispositivo="tab-1")["participante"]
        m9.Dispositivo.objects.filter(pk=p["dispositivo_id"]).update(activo=False)
        r = self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": s["codigo_union"], "persona_id": "luis", "dispositivo": "tab-1"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_inactivo"))


class LanzamientoTests(ConNodoInstalado):
    def test_el_lanzamiento_guarda_destinatarios_reglas_y_excluye_tabletas_bloqueadas(self):
        s = self.iniciar()
        ana = self.unirse(s, persona="ana", dispositivo="tab-1")["participante"]
        luis = self.unirse(s, persona="luis", rotulo="Luis", dispositivo="tab-2")["participante"]
        self.api.post(f"/api/dispositivos/{luis['dispositivo_id']}/bloquear/", {}, format="json")
        ruta = f"/api/aula/sesiones/{s['id']}/distribuciones/"
        r = self.api.post(ruta, {"clase": "actividad", "objeto_ref": "l1-activity", "intentos_permitidos": 2, "tiempo_limite_seg": 600}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        d = r.json()
        self.assertEqual((d["alcance"], d["destinatarios"], d["excluidos_bloqueados"]), ("grupo", ["ana"], ["luis"]))
        self.assertEqual((d["intentos_permitidos"], d["tiempo_limite_seg"], d["entregas"]["total"]), (2, 600, 1))
        self.assertEqual(d["entregas"]["detalle"][0]["participante_id"], ana["id"])
        estado_luis = self.api.get(f"/api/aula/sesiones/{s['id']}/estado/?participante={luis['id']}").json()
        self.assertEqual(estado_luis["pendientes"], [])
        carga = m.EventoSalida.objects.get(agregado_id=s["id"], tipo_evento=dom.EV_ACTIVIDAD_LANZADA).carga
        self.assertEqual((carga["destinatarios"], carga["excluidos_bloqueados"], carga["intentos_permitidos"]), (1, 1, 2))
        # una selección que sólo trae tabletas bloqueadas no lanza nada
        r = self.api.post(ruta, {"clase": "actividad", "objeto_ref": "l1-activity", "alcance": "seleccion", "participantes": [luis["id"]]}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["excluidos_bloqueados"]), (409, "sin_participantes_admitidos", ["luis"]))
        # la selección acepta ids de participante o de persona; sin reglas manda el objeto (NULL)
        r = self.api.post(ruta, {"clase": "recurso", "media_ref": "pdf-lab-guide", "alcance": "seleccion", "participantes": ["ana"]}, format="json")
        self.assertEqual((r.status_code, r.json()["destinatarios"], r.json()["intentos_permitidos"]), (201, ["ana"], None))

    def test_reglas_del_lanzamiento_mal_formadas(self):
        s = self.iniciar()
        self.unirse(s, dispositivo="tab-1")
        ruta = f"/api/aula/sesiones/{s['id']}/distribuciones/"
        r = self.api.post(ruta, {"clase": "actividad", "objeto_ref": "l1-activity", "intentos_permitidos": 0}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        r = self.api.post(ruta, {"clase": "actividad", "objeto_ref": "l1-activity", "tiempo_limite_seg": "muchos"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(m.Distribucion.objects.count(), 0)

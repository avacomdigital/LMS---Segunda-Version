"""
El ciclo de vida de la sesión de clase con el curso de ejemplo: iniciar, unirse,
presencia, selector, controles, distribuciones, avisos, código, suspender, reanudar y
cerrar. Sin biblioteca real y sin instalar el módulo de acceso (Q-34 abierta).
"""
from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from acceso.tests.base import BaseAcceso
from expediente.models import Auditoria

from .. import models as m
from ..dominio import sesion as dom

CURSO = "avacom.co.lower-secondary.6.science.states-of-matter"


class ConSesionDeClase(TestCase):
    def setUp(self):
        self.api = APIClient()

    def iniciar(self, profesor="prof-1", **extra):
        cuerpo = {"via": "leccion", "curso_ref": CURSO, "leccion_ref": "l1-three-states", "fuente": "ejemplo",
                  "profesor_id": profesor, "profesor_rotulo": "Prof. Gómez", "superficie": "pantalla", **extra}
        r = self.api.post("/api/aula/sesiones/", cuerpo, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def unirse(self, sesion, persona="ana", rotulo="Ana", dispositivo="tab-1", **extra):
        r = self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": sesion["codigo_union"], "persona_id": persona,
                                                          "persona_rotulo": rotulo, "dispositivo": dispositivo, **extra}, format="json")
        self.assertIn(r.status_code, (200, 201), r.content)
        return r.json()

    def eventos(self, sesion_id):
        return list(m.EventoSalida.objects.filter(agregado_id=sesion_id).order_by("id").values_list("tipo_evento", flat=True))


class IniciarTests(ConSesionDeClase):
    def test_iniciar_desde_una_leccion_deja_codigo_selector_y_rotulos(self):
        s = self.iniciar()
        self.assertEqual(s["estado"], "abierta")
        self.assertTrue(s["activa"])
        self.assertRegex(s["codigo_union"], r"^\d{6}$")
        self.assertEqual((s["via_origen"], s["fuente_curso"]), ("leccion", "ejemplo"))
        self.assertEqual(s["curso_rotulo"], "Estados de la materia y sus cambios")
        self.assertEqual((s["curso_version"], s["leccion_rotulo"]), ("1.0.0", "Los tres estados de la materia"))
        self.assertEqual(s["profesor_rotulo"], "Prof. Gómez")
        self.assertEqual((s["selector"]["objeto_ref"], s["selector"]["objeto_tipo"], s["selector"]["rotulo"]),
                         ("l1-lecture", "lecture", "Todo lo que nos rodea es materia"))
        self.assertTrue(s["selector"]["vigente"])
        self.assertTrue(s["seguimiento"])
        self.assertFalse(s["pantallas_bloqueadas"])
        self.assertEqual(s["conteo"]["total"], 0)
        self.assertEqual(self.eventos(s["id"]), [dom.EV_SESION_INICIADA, dom.EV_CODIGO_GENERADO, dom.EV_RECURSO_PROYECTADO])
        self.assertTrue(Auditoria.objects.filter(accion="aula.sesion.iniciada", objeto_id=s["id"]).exists())

    def test_un_profesor_solo_tiene_una_sesion_abierta(self):
        s = self.iniciar()
        r = self.api.post("/api/aula/sesiones/", {"via": "libre", "profesor_id": "prof-1"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "sesion_activa_existente"))
        self.assertEqual(r.json()["sesion_id"], s["id"])

    def test_un_grupo_solo_tiene_una_sesion_activa(self):
        self.iniciar(grupo_id="grupo-8a")
        r = self.api.post("/api/aula/sesiones/", {"via": "libre", "profesor_id": "prof-2", "grupo_id": "grupo-8a"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "grupo_con_sesion_activa"))

    def test_las_cuatro_vias_producen_el_mismo_tipo_de_sesion(self):
        libre = self.iniciar(profesor="p-libre", via="libre", curso_ref="", leccion_ref="")
        self.assertEqual((libre["via_origen"], libre["curso_ref"], libre["selector"]), ("libre", "", None))
        recurso = self.iniciar(profesor="p-recurso", via="recurso", leccion_ref="", objeto_ref="l2-lab-heating")
        self.assertEqual((recurso["selector"]["objeto_ref"], recurso["leccion_ref"], recurso["objeto_rotulo"]),
                         ("l2-lab-heating", "l2-changes-of-state", "Laboratorio: curva de calentamiento"))
        arbol = self.iniciar(profesor="p-arbol", via="arbol", curso_ref="", leccion_ref="", nodo_ref="CN-6-EJEMPLO")
        self.assertEqual((arbol["via_origen"], arbol["nodo_ref"]), ("arbol", "CN-6-EJEMPLO"))
        for s in (libre, recurso, arbol):
            self.assertRegex(s["codigo_union"], r"^\d{6}$")
            self.assertTrue(s["seguimiento"])

    def test_vias_mal_formadas_y_referencias_inexistentes(self):
        r = self.api.post("/api/aula/sesiones/", {"via": "magia", "profesor_id": "p"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        r = self.api.post("/api/aula/sesiones/", {"via": "leccion", "curso_ref": CURSO, "profesor_id": "p"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.api.post("/api/aula/sesiones/", {"via": "leccion", "curso_ref": CURSO, "leccion_ref": "no", "fuente": "ejemplo",
                                                  "profesor_id": "p"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "referencia_no_encontrada"))
        r = self.api.post("/api/aula/sesiones/", {"via": "recurso", "curso_ref": CURSO, "objeto_ref": "l3-exam", "fuente": "ejemplo",
                                                  "profesor_id": "p"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("MOD-010", r.json()["detail"])
        self.assertEqual(m.SesionDeClase.objects.count(), 0)


class ParticipantesTests(ConSesionDeClase):
    def test_unirse_con_el_codigo_y_readmitirse_sin_duplicar(self):
        s = self.iniciar()
        u = self.unirse(s)
        self.assertTrue(u["nuevo"])
        self.assertFalse(u["en_espera"])
        self.assertEqual(u["participante"]["estado"], "conectado")
        self.assertEqual(u["participante"]["persona_rotulo"], "Ana")
        self.assertEqual(u["selector"]["objeto_ref"], "l1-lecture")
        self.assertTrue(u["seguimiento"])
        self.assertEqual(u["intervalo_sondeo_ms"], 2000)
        self.assertNotIn("codigo_union", u["sesion"])           # la tableta no ve el código ni la lista
        pid = u["participante"]["id"]
        otra = self.unirse(s, dispositivo="tab-2", participante_id=pid)   # la misma persona vuelve desde otra tableta
        self.assertFalse(otra["nuevo"])
        self.assertEqual(otra["participante"]["id"], pid)
        self.assertEqual(otra["participante"]["dispositivo"], "tab-2")
        self.assertEqual(m.Participante.objects.filter(sesion_id=s["id"]).count(), 1)
        detalle = self.api.get(f"/api/aula/sesiones/{s['id']}/").json()
        self.assertEqual(detalle["conteo"], {"total": 1, "conectados": 1, "reconectando": 0, "esperando": 0, "salieron": 0})
        self.assertIn(dom.EV_DISPOSITIVO_ADMITIDO, self.eventos(s["id"]))
        self.assertIn(dom.EV_DISPOSITIVO_READMITIDO, self.eventos(s["id"]))

    def test_codigo_equivocado_y_datos_incompletos(self):
        self.iniciar()
        r = self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": "000000", "persona_id": "x"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "codigo_invalido"))
        r = self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": "123456"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_presencia_declarada_y_estado_para_la_tableta(self):
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        ruta = f"/api/aula/sesiones/{s['id']}/participantes/{pid}/presencia/"
        r = self.api.post(ruta, {"estado": "salio"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["participante"]["estado"], "salio")
        self.assertIsNotNone(r.json()["participante"]["salida"])
        r = self.api.post(ruta, {"estado": "conectado", "dispositivo": "tab-9"}, format="json")
        self.assertEqual((r.json()["participante"]["estado"], r.json()["participante"]["salida"], r.json()["participante"]["dispositivo"]),
                         ("conectado", None, "tab-9"))
        r = self.api.post(ruta, {"estado": "expulsado"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(m.Presencia.objects.filter(participante_id=pid).count(), 3)   # ingreso, salio, conectado
        estado = self.api.get(f"/api/aula/sesiones/{s['id']}/estado/?participante={pid}").json()
        self.assertEqual(estado["participante"]["id"], pid)
        self.assertEqual(estado["selector"]["objeto_ref"], "l1-lecture")
        self.assertIn("servidor_en", estado)

    def test_expulsar_y_readmitir_desde_el_panel(self):
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        base = f"/api/aula/sesiones/{s['id']}/participantes/{pid}"
        r = self.api.post(f"{base}/expulsar/", {"motivo": "uso indebido"}, format="json")
        self.assertEqual((r.status_code, r.json()["estado"]), (200, "expulsado"))
        r = self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": s["codigo_union"], "persona_id": "ana"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "participante_expulsado"))
        r = self.api.post(f"{base}/admitir/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["estado"], r.json()["admision_nominal"]), (200, "conectado", True))
        r = self.api.post(f"{base}/rechazar/", {}, format="json")
        self.assertEqual(r.status_code, 400)   # sólo se rechaza a quien espera
        self.assertIn(dom.EV_DISPOSITIVO_EXPULSADO, self.eventos(s["id"]))


class ClaseEnVivoTests(ConSesionDeClase):
    def test_declarar_el_selector_lo_ve_la_tableta(self):
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/selector/", {"objeto_ref": "l1-lecture", "unidad_ref": "l1-lecture-s2",
                                                                    "profesor_id": "prof-1"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        selector = r.json()
        self.assertEqual((selector["unidad_ref"], selector["unidad_indice"], selector["rotulo"]), ("l1-lecture-s2", 2, "Tres estados, tres formas de ordenarse"))
        estado = self.api.get(f"/api/aula/sesiones/{s['id']}/estado/?participante={pid}").json()
        self.assertEqual(estado["selector"]["unidad_ref"], "l1-lecture-s2")
        self.assertEqual(m.Selector.objects.filter(sesion_id=s["id"]).count(), 2)
        self.assertEqual(m.Selector.objects.filter(sesion_id=s["id"], vigente=True).count(), 1)
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/selector/", {"objeto_ref": "no-existe"}, format="json")
        self.assertEqual(r.status_code, 404)
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/selector/", {"objeto_ref": "l3-exam"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/selector/", {"media_ref": "img-particles", "rotulo": "Modelo de partículas"}, format="json")
        self.assertEqual((r.status_code, r.json()["objeto_tipo"], r.json()["media_ref"]), (201, "medio", "img-particles"))

    def test_bloquear_pantallas_y_liberar_el_seguimiento(self):
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        ruta = f"/api/aula/sesiones/{s['id']}/controles/"
        r = self.api.post(ruta, {"tipo": "bloqueo", "activo": True}, format="json")
        self.assertEqual((r.status_code, r.json()["cambio"], r.json()["pantallas_bloqueadas"]), (200, True, True))
        r = self.api.post(ruta, {"tipo": "bloqueo", "activo": True}, format="json")
        self.assertFalse(r.json()["cambio"])   # idempotente
        r = self.api.post(ruta, {"tipo": "seguimiento", "activo": False}, format="json")
        self.assertEqual((r.json()["seguimiento"], r.json()["pantallas_bloqueadas"]), (False, True))
        estado = self.api.get(f"/api/aula/sesiones/{s['id']}/estado/?participante={pid}").json()
        self.assertEqual((estado["seguimiento"], estado["pantallas_bloqueadas"]), (False, True))
        r = self.api.post(ruta, {"tipo": "bloqueo", "activo": False}, format="json")
        self.assertFalse(r.json()["pantallas_bloqueadas"])
        self.assertEqual(self.eventos(s["id"]).count(dom.EV_DISPOSITIVOS_BLOQUEADOS), 2)
        self.assertEqual(m.Control.objects.filter(sesion_id=s["id"], hasta__isnull=True).count(), 0)
        r = self.api.post(ruta, {"tipo": "otro", "activo": True}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_lanzar_una_actividad_confirmar_y_cerrar(self):
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        ruta = f"/api/aula/sesiones/{s['id']}/distribuciones/"
        r = self.api.post(ruta, {"clase": "actividad", "objeto_ref": "l1-activity"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        d = r.json()
        self.assertEqual((d["clase"], d["objeto_tipo"], d["rotulo"], d["leccion_ref"]), ("actividad", "activity", "Practica: los tres estados", "l1-three-states"))
        self.assertEqual(d["entregas"]["total"], 1)
        self.assertEqual(d["entregas"]["pendientes"], 1)
        estado = self.api.get(f"/api/aula/sesiones/{s['id']}/estado/?participante={pid}").json()
        self.assertEqual([p["id"] for p in estado["pendientes"]], [d["id"]])
        self.assertEqual(estado["pendientes"][0]["entrega"], "pendiente")
        r = self.api.post(f"{ruta}{d['id']}/confirmar/", {"participante_id": pid}, format="json")
        self.assertEqual((r.status_code, r.json()["estado"], r.json()["intentos"]), (200, "entregado", 1))
        r = self.api.post(f"{ruta}{d['id']}/resultados/", {}, format="json")
        self.assertEqual(r.status_code, 200)
        r = self.api.post(f"{ruta}{d['id']}/cerrar/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["abierta"]), (200, False))
        estado = self.api.get(f"/api/aula/sesiones/{s['id']}/estado/?participante={pid}").json()
        self.assertEqual(estado["pendientes"], [])
        eventos = self.eventos(s["id"])
        self.assertIn(dom.EV_ACTIVIDAD_LANZADA, eventos)
        self.assertIn(dom.EV_RESULTADOS_MOSTRADOS, eventos)
        self.assertIn(dom.EV_ACTIVIDAD_CERRADA, eventos)
        # Un recurso también se difunde; una presentación no se «lanza» como actividad; sin admitidos no hay actividad.
        r = self.api.post(ruta, {"clase": "recurso", "media_ref": "pdf-lab-guide", "rotulo": "Guía", "disponible_estudio": True}, format="json")
        self.assertEqual((r.status_code, r.json()["disponible_estudio"]), (201, True))
        r = self.api.post(ruta, {"clase": "actividad", "objeto_ref": "l1-lecture"}, format="json")
        self.assertEqual(r.status_code, 400)
        vacia = self.iniciar(profesor="prof-2")
        r = self.api.post(f"/api/aula/sesiones/{vacia['id']}/distribuciones/", {"clase": "actividad", "objeto_ref": "l1-activity"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "sin_participantes_admitidos"))

    def test_avisos_al_grupo_y_a_una_tableta(self):
        s = self.iniciar()
        u = self.unirse(s)
        pid = u["participante"]["id"]
        ruta = f"/api/aula/sesiones/{s['id']}/avisos/"
        r = self.api.post(ruta, {"texto": "Miren al frente"}, format="json")
        self.assertEqual(r.status_code, 201)
        r = self.api.post(ruta, {"texto": "Ana, revisa la pregunta 2", "participante_id": pid}, format="json")
        self.assertEqual(r.status_code, 201)
        otro = self.unirse(s, persona="luis", rotulo="Luis", dispositivo="tab-2")["participante"]["id"]
        estado_ana = self.api.get(f"/api/aula/sesiones/{s['id']}/estado/?participante={pid}").json()
        estado_luis = self.api.get(f"/api/aula/sesiones/{s['id']}/estado/?participante={otro}").json()
        self.assertEqual(len(estado_ana["avisos"]), 2)
        self.assertEqual(len(estado_luis["avisos"]), 1)
        r = self.api.post(ruta, {"texto": ""}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.eventos(s["id"]).count(dom.EV_MENSAJE_ENVIADO), 2)

    def test_rotar_el_codigo(self):
        s = self.iniciar()
        viejo = s["codigo_union"]
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/codigo/rotar/", {}, format="json")
        self.assertEqual(r.status_code, 200)
        nuevo = r.json()["codigo_union"]
        self.assertNotEqual(viejo, nuevo)
        r = self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": viejo, "persona_id": "x"}, format="json")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": nuevo, "persona_id": "x"}, format="json").status_code, 201)
        asiento = Auditoria.objects.filter(accion="aula.codigo.rotado").first()
        self.assertEqual(asiento.valor_anterior, {"codigo_union": viejo})


class ContinuidadTests(ConSesionDeClase):
    def test_suspender_y_reanudar_conserva_codigo_selector_y_participantes(self):
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/suspender/", {"causa": "caida_nodo"}, format="json")
        self.assertEqual((r.status_code, r.json()["estado"]), (200, "suspendida"))
        self.assertEqual(r.json()["participantes"][0]["estado"], "reconectando")
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/selector/", {"objeto_ref": "l1-lecture"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "transicion_invalida"))
        # La tableta puede volver a presentarse con el mismo código mientras está suspendida.
        u = self.unirse(s, participante_id=pid)
        self.assertEqual(u["participante"]["estado"], "reconectando")
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/reanudar/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["estado"], r.json()["codigo_union"]), (200, "abierta", s["codigo_union"]))
        self.assertEqual(r.json()["selector"]["objeto_ref"], "l1-lecture")
        self.assertEqual(len(r.json()["participantes"]), 1)
        self.assertIn(dom.EV_SESION_REANUDADA, self.eventos(s["id"]))
        carga = m.EventoSalida.objects.get(agregado_id=s["id"], tipo_evento=dom.EV_SESION_REANUDADA).carga
        self.assertEqual((carga["causa"], carga["dispositivos_por_recuperar"]), ("caida_nodo", 1))
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/reanudar/", {}, format="json")
        self.assertEqual(r.status_code, 409)

    def test_cerrar_consolida_el_resumen_y_no_se_reabre(self):
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        self.unirse(s, persona="luis", rotulo="Luis", dispositivo="tab-2")
        self.api.post(f"/api/aula/sesiones/{s['id']}/selector/", {"objeto_ref": "l1-explanation"}, format="json")
        self.api.post(f"/api/aula/sesiones/{s['id']}/avisos/", {"texto": "Vamos a cerrar"}, format="json")
        self.api.post(f"/api/aula/sesiones/{s['id']}/distribuciones/", {"clase": "actividad", "objeto_ref": "l1-activity"}, format="json")
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/cerrar/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "actividades_abiertas"))
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/cerrar/", {"forzar": True}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        s2 = r.json()
        self.assertEqual((s2["estado"], s2["activa"], s2["origen_cierre"]), ("cerrada", False, "profesor"))
        self.assertIsNotNone(s2["finalizada_en"])
        self.assertEqual(s2["resumen"]["participantes"], 2)
        self.assertEqual(s2["resumen"]["conectados_maximo"], 2)
        self.assertEqual((s2["resumen"]["selectores"], s2["resumen"]["distribuciones"], s2["resumen"]["actividades"], s2["resumen"]["avisos"]), (2, 1, 1, 1))
        self.assertEqual(s2["resumen"]["pendientes"], 0)
        self.assertGreaterEqual(s2["resumen"]["duracion_ms"], 0)
        self.assertTrue(all(p["estado"] == "salio" for p in s2["participantes"]))
        self.assertFalse(s2["seguimiento"])
        # BR-052: cerrada no admite participantes nuevos ni cambios de selector.
        r = self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": s["codigo_union"], "persona_id": "nuevo"}, format="json")
        self.assertEqual(r.status_code, 404)
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/selector/", {"objeto_ref": "l1-lecture"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "sesion_cerrada"))
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/reanudar/", {}, format="json")
        self.assertEqual(r.status_code, 409)
        eventos = self.eventos(s["id"])
        self.assertEqual(eventos[-1], dom.EV_SESION_FINALIZADA)
        self.assertIn(dom.EV_ACTIVIDAD_CERRADA, eventos)
        self.assertTrue(set(eventos) <= set(dom.EVENTOS))
        # El profesor ya puede abrir otra clase.
        self.assertEqual(self.api.post("/api/aula/sesiones/", {"via": "libre", "profesor_id": "prof-1"}, format="json").status_code, 201)

    def test_las_cerradas_se_archivan_a_las_veinticuatro_horas(self):
        s = self.iniciar()
        self.api.post(f"/api/aula/sesiones/{s['id']}/cerrar/", {}, format="json")
        r = self.api.get("/api/aula/sesiones/")
        self.assertEqual((r.status_code, r.json()["archivadas_ahora"]), (200, 0))
        m.SesionDeClase.objects.filter(pk=s["id"]).update(finalizada_en=m.ahora_ms() - dom.ARCHIVO_TRAS_MS - 1000)
        r = self.api.get("/api/aula/sesiones/?estado=archivada")
        self.assertEqual(r.json()["archivadas_ahora"], 1)
        self.assertEqual([x["estado"] for x in r.json()["sesiones"]], ["archivada"])
        self.assertIsNotNone(r.json()["sesiones"][0]["archivada_en"])


class ConPadronTests(BaseAcceso):
    """BR-047 con el módulo de acceso instalado: el inscrito entra; el que no está en el grupo espera al profesor."""

    def test_inscrito_entra_y_no_inscrito_espera_admision(self):
        api = APIClient()
        r = api.post("/api/aula/sesiones/", {"via": "libre", "grupo_id": self.grupo["id"], "profesor_id": self.docente_id}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        s = r.json()
        self.assertEqual(s["grupo_rotulo"], "Octavo A")
        self.assertEqual(s["profesor_rotulo"], "Prof. Gómez")
        inscrito = api.post("/api/aula/sesiones/unirse/", {"codigo_union": s["codigo_union"], "persona_id": self.estudiante_id}, format="json").json()
        self.assertEqual((inscrito["participante"]["estado"], inscrito["participante"]["persona_rotulo"]), ("conectado", "Juan P."))
        invitado = api.post("/api/aula/sesiones/unirse/", {"codigo_union": s["codigo_union"], "persona_id": "visitante-1",
                                                           "persona_rotulo": "Lucía"}, format="json").json()
        self.assertTrue(invitado["en_espera"])
        self.assertEqual(invitado["participante"]["estado"], "esperando")
        pid = invitado["participante"]["id"]
        r = api.post(f"/api/aula/sesiones/{s['id']}/participantes/{pid}/admitir/", {"profesor_id": self.docente_id}, format="json")
        self.assertEqual((r.status_code, r.json()["estado"], r.json()["admision_nominal"]), (200, "conectado", True))
        rechazado = api.post("/api/aula/sesiones/unirse/", {"codigo_union": s["codigo_union"], "persona_id": "visitante-2"}, format="json").json()
        r = api.post(f"/api/aula/sesiones/{s['id']}/participantes/{rechazado['participante']['id']}/rechazar/", {"motivo": "no es del grupo"}, format="json")
        self.assertEqual((r.status_code, r.json()["estado"]), (200, "rechazado"))
        # Con sesión de estudiante (JWT) las funciones del profesor se niegan (403), sin necesidad de sembrar classroom.*.
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.TABLETA)
        r = alumno.post(f"/api/aula/sesiones/{s['id']}/selector/", {"media_ref": "x", "rotulo": "x"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))

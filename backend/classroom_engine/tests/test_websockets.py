"""
El canal en tiempo real de verdad: sockets de Django Channels contra el consumidor de `interfaces/websockets.py`, con la
base de pruebas y la capa de canales en memoria (007-01, 007-04). Lo que se comprueba: el profesor ve el conteo de
conectados al conectar y en cuanto cambia; el aviso de un cambio llega a la tableta en menos de un segundo; cada cosa
llega sólo a quien le concierne; y una tableta cuyo socket se cierra pasa a «reconectando» si no vuelve.
"""
from __future__ import annotations

import asyncio
import time
from unittest import mock

from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from ..interfaces import websockets as ws
from .. import models as m

CURSO = "avacom.co.lower-secondary.6.science.states-of-matter"
APLICACION = URLRouter(ws.websocket_urlpatterns)


class ConSockets(TransactionTestCase):
    def setUp(self):
        self.api = APIClient()
        self.abiertos: list[WebsocketCommunicator] = []
        patch = mock.patch.object(ws, "GRACIA_DESCONEXION_S", 0.05)
        patch.start()
        self.addCleanup(patch.stop)

    # -------------------------------------------------------------------- ayudas REST (síncronas, en su hilo)
    def rest(self, metodo, ruta, cuerpo=None):
        return sync_to_async(getattr(self.api, metodo))(ruta, cuerpo, format="json") if cuerpo is not None else sync_to_async(getattr(self.api, metodo))(ruta)

    async def iniciar(self, profesor="prof-1"):
        r = await self.rest("post", "/api/aula/sesiones/", {"via": "leccion", "curso_ref": CURSO, "leccion_ref": "l1-three-states",
                                                            "fuente": "ejemplo", "profesor_id": profesor})
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    async def unirse(self, sesion, persona="ana", dispositivo="t-1"):
        r = await self.rest("post", "/api/aula/sesiones/unirse/", {"codigo_union": sesion["codigo_union"], "persona_id": persona,
                                                                    "persona_rotulo": persona.title(), "dispositivo": dispositivo})
        self.assertIn(r.status_code, (200, 201), r.content)
        return r.json()

    # ------------------------------------------------------------------------ sockets
    async def conectar(self, sesion_id, consulta):
        comm = WebsocketCommunicator(APLICACION, f"/ws/aula/sesiones/{sesion_id}/?{consulta}")
        self.abiertos.append(comm)
        conectado, _ = await comm.connect()
        self.assertTrue(conectado)
        return comm

    async def docente(self, sesion_id):
        comm = await self.conectar(sesion_id, "rol=docente")
        return comm, await comm.receive_json_from(timeout=3)

    async def estudiante(self, sesion_id, participante_id):
        comm = await self.conectar(sesion_id, f"rol=estudiante&participante={participante_id}")
        return comm, await comm.receive_json_from(timeout=3)

    @staticmethod
    async def hasta(comm, predicado, intentos=12, timeout=2):
        """Lee mensajes hasta que uno cumpla `predicado`; falla si no llega."""
        vistos = []
        for _ in range(intentos):
            mensaje = await comm.receive_json_from(timeout=timeout)
            vistos.append(mensaje)
            if predicado(mensaje):
                return mensaje
        raise AssertionError(f"No llegó el mensaje esperado; llegaron: {vistos}")

    @staticmethod
    async def nada(comm, espera=0.4):
        return await comm.receive_nothing(timeout=espera)

    async def cerrar_todo(self):
        for comm in self.abiertos:
            try:
                await comm.disconnect()
            except Exception:   # noqa: BLE001
                pass
        await asyncio.sleep(0.1)   # deja terminar las tareas de «reconectando» pendientes


class ConteoDeConectadosTests(ConSockets):
    async def test_el_profesor_recibe_el_conteo_al_conectar_y_cuando_entra_alguien(self):
        s = await self.iniciar()
        docente, hola = await self.docente(s["id"])
        self.assertEqual((hola["tipo"], hola["rol"], hola["sesion"]["estado"]), ("hola", "docente", "abierta"))
        self.assertEqual((hola["conteo"]["conectados"], hola["conteo"]["total"]), (0, 0))   # el recuadro verde arranca en 0
        self.assertEqual((hola["latido_ms"], hola["capacidad"]["nivel"]), (5000, "normal"))
        await self.unirse(s, "ana", "t-1")
        conteo = await self.hasta(docente, lambda x: x["tipo"] == "conteo")
        self.assertEqual((conteo["conectados"], conteo["total"]), (1, 1))
        await self.unirse(s, "luis", "t-2")
        conteo = await self.hasta(docente, lambda x: x["tipo"] == "conteo" and x["conectados"] == 2)
        self.assertEqual(conteo["total"], 2)

    async def test_el_conteo_baja_al_salir_expulsar_o_cerrar(self):
        s = await self.iniciar()
        a = (await self.unirse(s, "ana", "t-1"))["participante"]["id"]
        b = (await self.unirse(s, "luis", "t-2"))["participante"]["id"]
        docente, hola = await self.docente(s["id"])
        self.assertEqual(hola["conteo"]["conectados"], 2)
        await self.rest("post", f"/api/aula/sesiones/{s['id']}/participantes/{a}/presencia/", {"estado": "salio"})
        conteo = await self.hasta(docente, lambda x: x["tipo"] == "conteo")
        self.assertEqual((conteo["conectados"], conteo["salieron"]), (1, 1))
        await self.rest("post", f"/api/aula/sesiones/{s['id']}/participantes/{b}/expulsar/", {"motivo": "x"})
        conteo = await self.hasta(docente, lambda x: x["tipo"] == "conteo")
        self.assertEqual(conteo["conectados"], 0)

    async def test_una_tableta_que_pierde_el_socket_pasa_a_reconectando_y_el_profesor_lo_ve(self):
        s = await self.iniciar()
        pid = (await self.unirse(s, "ana", "t-1"))["participante"]["id"]
        docente, _ = await self.docente(s["id"])
        alumno, hola = await self.estudiante(s["id"], pid)
        self.assertEqual(hola["participante"]["estado"], "conectado")
        await alumno.disconnect()
        conteo = await self.hasta(docente, lambda x: x["tipo"] == "conteo" and x["reconectando"] == 1)
        self.assertEqual(conteo["conectados"], 0)
        self.assertEqual((await sync_to_async(m.Participante.objects.get)(pk=pid)).estado, "reconectando")

    async def test_volver_antes_de_la_gracia_no_cambia_nada(self):
        s = await self.iniciar()
        pid = (await self.unirse(s, "ana", "t-1"))["participante"]["id"]
        docente, _ = await self.docente(s["id"])
        with mock.patch.object(ws, "GRACIA_DESCONEXION_S", 0.5):
            primero, _ = await self.estudiante(s["id"], pid)
            await primero.disconnect()
            segundo, _ = await self.estudiante(s["id"], pid)   # vuelve enseguida
            await asyncio.sleep(0.8)
        self.assertEqual((await sync_to_async(m.Participante.objects.get)(pk=pid)).estado, "conectado")
        await self.nada(docente, 0.3)

    async def test_abrir_el_socket_recupera_al_que_estaba_reconectando(self):
        s = await self.iniciar()
        pid = (await self.unirse(s, "ana", "t-1"))["participante"]["id"]
        await sync_to_async(m.Participante.objects.filter(pk=pid).update)(estado="reconectando")
        docente, hola = await self.docente(s["id"])
        self.assertEqual((hola["conteo"]["conectados"], hola["conteo"]["reconectando"]), (0, 1))
        await self.estudiante(s["id"], pid)
        conteo = await self.hasta(docente, lambda x: x["tipo"] == "conteo" and x["conectados"] == 1)
        self.assertEqual(conteo["reconectando"], 0)


class CambiosEnTiempoRealTests(ConSockets):
    async def test_el_cambio_de_selector_llega_a_la_tableta_en_menos_de_un_segundo(self):
        s = await self.iniciar()
        pid = (await self.unirse(s, "ana", "t-1"))["participante"]["id"]
        alumno, _ = await self.estudiante(s["id"], pid)
        docente, _ = await self.docente(s["id"])
        t0 = time.monotonic()
        r = await self.rest("post", f"/api/aula/sesiones/{s['id']}/selector/", {"objeto_ref": "l1-lecture", "unidad_ref": "l1-lecture-s2"})
        self.assertEqual(r.status_code, 201, r.content)
        aviso = await self.hasta(alumno, lambda x: x["tipo"] == "cambio" and x["que"] == "selector")
        self.assertLess(time.monotonic() - t0, 1.0)     # BR-049 / NFR-011: ≤ 3 s; aquí, en el mismo proceso, menos de uno
        self.assertEqual(aviso["carga"]["unidad_ref"], "l1-lecture-s2")
        self.assertNotIn("selector", aviso)             # el aviso nunca lleva el contenido: el cliente lo pide por HTTP
        await self.hasta(docente, lambda x: x["tipo"] == "cambio" and x["que"] == "selector")
        # medir: el canal lleva la cuenta de cuánto tardó cada aviso en salir por el socket
        r = await self.rest("get", "/api/aula/tiempo-real/")
        resumen = r.json()
        self.assertGreaterEqual(resumen["demora_ms"]["muestras"], 2)
        self.assertLess(resumen["demora_ms"]["p95"], resumen["objetivo_ms"])
        self.assertEqual(resumen["sesiones"][s["id"]], {"docentes": 1, "alumnos": 1})

    async def test_cada_aviso_llega_solo_a_quien_le_concierne(self):
        s = await self.iniciar()
        a = (await self.unirse(s, "ana", "t-1"))["participante"]["id"]
        b = (await self.unirse(s, "luis", "t-2"))["participante"]["id"]
        ana, _ = await self.estudiante(s["id"], a)
        luis, _ = await self.estudiante(s["id"], b)
        docente, _ = await self.docente(s["id"])
        await self.nada(luis, 0.2)
        # la mano de Ana la ven el profesor y Ana, no Luis
        await self.rest("post", f"/api/aula/sesiones/{s['id']}/participantes/{a}/ayuda/", {"activa": True})
        await self.hasta(docente, lambda x: x["tipo"] == "cambio" and x["que"] == "ayuda")
        await self.hasta(ana, lambda x: x["tipo"] == "cambio" and x["que"] == "ayuda")
        await self.nada(luis)
        # el aviso a Luis sólo le llega a Luis; el del grupo, a todos
        await self.rest("post", f"/api/aula/sesiones/{s['id']}/avisos/", {"texto": "Luis, atento", "participante_id": b})
        await self.hasta(luis, lambda x: x["tipo"] == "cambio" and x["que"] == "aviso")
        await self.nada(ana)
        await self.rest("post", f"/api/aula/sesiones/{s['id']}/avisos/", {"texto": "Miren al frente"})
        await self.hasta(ana, lambda x: x["tipo"] == "cambio" and x["que"] == "aviso")
        await self.hasta(luis, lambda x: x["tipo"] == "cambio" and x["que"] == "aviso")

    async def test_los_resultados_y_el_codigo_son_solo_del_profesor(self):
        s = await self.iniciar()
        pid = (await self.unirse(s, "ana", "t-1"))["participante"]["id"]
        alumno, _ = await self.estudiante(s["id"], pid)
        docente, _ = await self.docente(s["id"])
        d = (await self.rest("post", f"/api/aula/sesiones/{s['id']}/distribuciones/", {"clase": "actividad", "objeto_ref": "l1-activity"})).json()
        await self.hasta(alumno, lambda x: x["tipo"] == "cambio" and x["que"] == "distribucion")    # lo lanzado sí le llega
        await self.rest("post", f"/api/aula/sesiones/{s['id']}/distribuciones/{d['id']}/respuestas/", {
            "participante_id": pid, "respuestas": [{"pregunta_ref": "l1-act-q2", "secuencia": 1, "respuesta": {"value": True}}]})
        await self.hasta(docente, lambda x: x["tipo"] == "cambio" and x["que"] == "resultados")
        await self.rest("post", f"/api/aula/sesiones/{s['id']}/codigo/rotar/", {})
        await self.hasta(docente, lambda x: x["tipo"] == "cambio" and x["que"] == "codigo")
        await self.nada(alumno)      # ni el avance de los demás ni el código de unión salen hacia las tabletas

    async def test_suspender_y_reanudar_avisan_a_todos(self):
        s = await self.iniciar()
        pid = (await self.unirse(s, "ana", "t-1"))["participante"]["id"]
        alumno, _ = await self.estudiante(s["id"], pid)
        docente, _ = await self.docente(s["id"])
        await self.rest("post", f"/api/aula/sesiones/{s['id']}/suspender/", {"causa": "corte_electrico"})
        aviso = await self.hasta(alumno, lambda x: x["tipo"] == "cambio" and x["que"] == "sesion")
        self.assertEqual((aviso["carga"]["estado"], aviso["carga"]["causa"]), ("suspendida", "corte_electrico"))
        conteo = await self.hasta(docente, lambda x: x["tipo"] == "conteo")
        self.assertEqual((conteo["conectados"], conteo["reconectando"]), (0, 1))
        await self.rest("post", f"/api/aula/sesiones/{s['id']}/reanudar/", {})
        aviso = await self.hasta(alumno, lambda x: x["tipo"] == "cambio" and x["que"] == "sesion" and x["carga"]["estado"] == "abierta")
        self.assertEqual(aviso["carga"]["estado"], "abierta")


class MensajesDelClienteTests(ConSockets):
    async def test_ping_pong_para_medir_el_viaje(self):
        s = await self.iniciar()
        docente, _ = await self.docente(s["id"])
        await docente.send_json_to({"tipo": "ping", "t": 12345})
        pong = await docente.receive_json_from(timeout=2)
        self.assertEqual((pong["tipo"], pong["t"]), ("pong", 12345))
        self.assertGreater(pong["servidor_en"], 0)

    async def test_el_latido_actualiza_el_ultimo_latido_y_lleva_telemetria(self):
        s = await self.iniciar()
        pid = (await self.unirse(s, "ana", "t-1"))["participante"]["id"]
        alumno, _ = await self.estudiante(s["id"], pid)
        await sync_to_async(m.Participante.objects.filter(pk=pid).update)(ultimo_latido_en=1)
        await alumno.send_json_to({"tipo": "latido", "telemetria": {"espacio_libre_mb": 900}})
        await asyncio.sleep(0.3)
        self.assertGreater((await sync_to_async(m.Participante.objects.get)(pk=pid)).ultimo_latido_en, 1)

    async def test_declarar_presencia_por_el_socket(self):
        s = await self.iniciar()
        pid = (await self.unirse(s, "ana", "t-1"))["participante"]["id"]
        alumno, _ = await self.estudiante(s["id"], pid)
        docente, _ = await self.docente(s["id"])
        await alumno.send_json_to({"tipo": "presencia", "estado": "reconectando"})     # la app pasó a segundo plano
        conteo = await self.hasta(docente, lambda x: x["tipo"] == "conteo")
        self.assertEqual((conteo["conectados"], conteo["reconectando"]), (0, 1))
        await alumno.send_json_to({"tipo": "presencia", "estado": "conectado"})       # volvió
        conteo = await self.hasta(docente, lambda x: x["tipo"] == "conteo")
        self.assertEqual(conteo["conectados"], 1)
        await alumno.send_json_to({"tipo": "presencia", "estado": "salio"})            # cerró la app
        conteo = await self.hasta(docente, lambda x: x["tipo"] == "conteo")
        self.assertEqual((conteo["conectados"], conteo["salieron"]), (0, 1))

    async def test_el_profesor_solo_escucha(self):
        s = await self.iniciar()
        docente, _ = await self.docente(s["id"])
        await docente.send_json_to({"tipo": "latido"})
        await docente.send_json_to({"tipo": "presencia", "estado": "salio"})
        await self.nada(docente)


class RechazosTests(ConSockets):
    async def esperar_rechazo(self, comm, codigo_cierre, codigo_error):
        error = await comm.receive_json_from(timeout=2)
        self.assertEqual((error["tipo"], error["codigo"]), ("error", codigo_error))
        salida = await comm.receive_output(timeout=2)
        self.assertEqual((salida["type"], salida["code"]), ("websocket.close", codigo_cierre))

    async def test_sesion_inexistente(self):
        comm = await self.conectar("no-existe", "rol=docente")
        await self.esperar_rechazo(comm, 4404, "no_encontrado")

    async def test_participante_inexistente_o_ausente(self):
        s = await self.iniciar()
        comm = await self.conectar(s["id"], "rol=estudiante&participante=fantasma")
        await self.esperar_rechazo(comm, 4404, "no_encontrado")
        comm = await self.conectar(s["id"], "rol=estudiante")
        await self.esperar_rechazo(comm, 4400, "datos_invalidos")

    async def test_el_expulsado_no_entra(self):
        s = await self.iniciar()
        pid = (await self.unirse(s, "ana", "t-1"))["participante"]["id"]
        await self.rest("post", f"/api/aula/sesiones/{s['id']}/participantes/{pid}/expulsar/", {"motivo": "x"})
        comm = await self.conectar(s["id"], f"rol=estudiante&participante={pid}")
        await self.esperar_rechazo(comm, 4403, "participante_expulsado")

    @override_settings(AVACOM_LMS_EXIGIR_SESION=True)
    async def test_con_sesion_obligatoria_hace_falta_token(self):
        comm = await self.conectar("cualquiera", "rol=docente")
        await self.esperar_rechazo(comm, 4401, "sesion_requerida")

    async def test_un_token_roto_se_rechaza_aunque_la_sesion_no_sea_obligatoria(self):
        comm = await self.conectar("cualquiera", "rol=docente&token=basura")
        await self.esperar_rechazo(comm, 4401, "sesion_invalida")


def _limpiando(prueba):
    """Django convierte cada `async def test_` con async_to_sync y no admite `asyncTearDown`: los sockets se cierran aquí,
    dentro del mismo bucle, aunque la prueba falle."""
    async def envuelta(self):
        try:
            await prueba(self)
        finally:
            await self.cerrar_todo()
    envuelta.__name__ = prueba.__name__
    return envuelta


for _clase in (ConteoDeConectadosTests, CambiosEnTiempoRealTests, MensajesDelClienteTests, RechazosTests):
    for _nombre in [n for n in dir(_clase) if n.startswith("test_")]:
        setattr(_clase, _nombre, _limpiando(getattr(_clase, _nombre)))

"""Los puntos de medición de la red (`/api/diagnostico/velocidad/…`): bytes exactos, cupos, apagado y paso intacto de lo demás a Django."""
from __future__ import annotations

import json

from django.test import SimpleTestCase, override_settings

from avacom_lms import velocidad


async def llamar(app, metodo: str, ruta: str, consulta: str = "", cuerpo: bytes = b"", trozos: int = 1, tipo: str = "http"):
    """Una petición ASGI a mano. Devuelve (estado, cabeceras, bytes de la respuesta)."""
    enviados = []
    pendiente = [cuerpo[i * (len(cuerpo) // trozos): (i + 1) * (len(cuerpo) // trozos) if i < trozos - 1 else len(cuerpo)] for i in range(trozos)] if cuerpo else [b""]
    entregados = 0

    async def receive():
        nonlocal entregados
        if entregados < len(pendiente):
            parte = pendiente[entregados]
            entregados += 1
            return {"type": "http.request", "body": parte, "more_body": entregados < len(pendiente)}
        return {"type": "http.disconnect"}

    async def send(mensaje):
        enviados.append(mensaje)

    await app({"type": tipo, "method": metodo, "path": ruta, "query_string": consulta.encode()}, receive, send)
    inicio = next((m for m in enviados if m["type"] == "http.response.start"), {"status": None, "headers": []})
    cuerpo_resp = b"".join(m.get("body", b"") for m in enviados if m["type"] == "http.response.body")
    return inicio["status"], dict(inicio["headers"]), cuerpo_resp


async def django_falso(scope, receive, send):
    await send({"type": "http.response.start", "status": 204, "headers": [(b"x-django", b"si")]})
    await send({"type": "http.response.body", "body": b""})


class VelocidadTests(SimpleTestCase):
    def setUp(self):
        self.app = velocidad.con_velocidad(django_falso)

    async def test_lo_que_no_es_de_la_medicion_pasa_intacto_a_django(self):
        estado, cab, _ = await llamar(self.app, "GET", "/api/aula/sesiones/")
        self.assertEqual((estado, cab[b"x-django"]), (204, b"si"))
        estado, _, _ = await llamar(self.app, "GET", "/api/diagnosticos/otra-cosa/")
        self.assertEqual(estado, 204)

    async def test_ping(self):
        estado, _, cuerpo = await llamar(self.app, "GET", velocidad.PREFIJO + "ping/")
        self.assertEqual(estado, 200)
        self.assertTrue(json.loads(cuerpo)["ok"])

    async def test_la_descarga_entrega_los_megabytes_pedidos_y_su_longitud(self):
        estado, cab, cuerpo = await llamar(self.app, "GET", velocidad.PREFIJO + "descarga/", "mb=3")
        self.assertEqual(estado, 200)
        self.assertEqual(len(cuerpo), 3 * 1024 * 1024)
        self.assertEqual(int(cab[b"content-length"]), 3 * 1024 * 1024)
        self.assertEqual(cab[b"content-encoding"], b"identity")      # nada que comprimir: se miden bytes de red, no del compresor

    async def test_la_descarga_se_acota(self):
        _, cab, _ = await llamar(self.app, "GET", velocidad.PREFIJO + "descarga/", "mb=9999")
        self.assertEqual(int(cab[b"content-length"]), velocidad.MAX_MB * 1024 * 1024)
        _, cab, _ = await llamar(self.app, "GET", velocidad.PREFIJO + "descarga/", "mb=-5")
        self.assertEqual(int(cab[b"content-length"]), 1024 * 1024)
        _, cab, _ = await llamar(self.app, "GET", velocidad.PREFIJO + "descarga/", "mb=abc")
        self.assertEqual(int(cab[b"content-length"]), 10 * 1024 * 1024)

    async def test_la_carga_cuenta_todos_los_bytes_aunque_lleguen_en_trozos(self):
        estado, _, cuerpo = await llamar(self.app, "POST", velocidad.PREFIJO + "carga/", cuerpo=bytes(5 * 1024 * 1024 + 7), trozos=9)
        datos = json.loads(cuerpo)
        self.assertEqual((estado, datos["bytes"]), (200, 5 * 1024 * 1024 + 7))
        self.assertGreater(datos["mbps"], 0)

    async def test_una_ruta_desconocida_o_un_metodo_equivocado_es_404(self):
        self.assertEqual((await llamar(self.app, "GET", velocidad.PREFIJO + "nada/"))[0], 404)
        self.assertEqual((await llamar(self.app, "POST", velocidad.PREFIJO + "descarga/"))[0], 404)

    async def test_con_el_cupo_lleno_responde_429_y_lo_libera_al_terminar(self):
        with override_settings():
            tomados = []
            for _ in range(velocidad.MAX_FLUJOS):
                m = velocidad.Medicion()
                m.__enter__()
                tomados.append(m)
            try:
                estado, cab, _ = await llamar(self.app, "GET", velocidad.PREFIJO + "descarga/", "mb=1")
                self.assertEqual((estado, cab[b"retry-after"]), (429, b"5"))
                estado, _, _ = await llamar(self.app, "GET", velocidad.PREFIJO + "ping/")     # el ping no gasta cupo
                self.assertEqual(estado, 200)
            finally:
                for m in tomados:
                    m.__exit__()
        estado, _, _ = await llamar(self.app, "GET", velocidad.PREFIJO + "descarga/", "mb=1")
        self.assertEqual(estado, 200)

    async def test_un_cliente_que_cuelga_a_media_carga_libera_su_cupo(self):
        antes = velocidad._en_uso
        enviados = []

        async def receive():
            return {"type": "http.disconnect"}

        async def send(m):
            enviados.append(m)

        await self.app({"type": "http", "method": "POST", "path": velocidad.PREFIJO + "carga/", "query_string": b""}, receive, send)
        self.assertEqual(velocidad._en_uso, antes)

    async def test_apagada_por_configuracion(self):
        import os
        os.environ["AVACOM_DIAGNOSTICO_VELOCIDAD"] = "0"
        try:
            estado, _, _ = await llamar(self.app, "GET", velocidad.PREFIJO + "ping/")
            self.assertEqual(estado, 404)
        finally:
            del os.environ["AVACOM_DIAGNOSTICO_VELOCIDAD"]

    async def test_los_websockets_no_se_tocan(self):
        estados = []

        async def ws_falso(scope, receive, send):
            estados.append(scope["type"])

        app = velocidad.con_velocidad(ws_falso)
        await app({"type": "websocket", "path": velocidad.PREFIJO + "ping/"}, None, None)
        self.assertEqual(estados, ["websocket"])

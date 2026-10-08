"""
La respuesta HTTP de la cola: cuerpo asíncrono bajo ASGI (por trozos, sin cargar el archivo entero), síncrono bajo WSGI, cupos de transferencia, tope de ancho de
banda y limpieza cuando la tableta se va a mitad.
"""
from __future__ import annotations

import asyncio
import io
import time

from django.core.handlers.asgi import ASGIRequest
from django.http import HttpRequest
from django.test import SimpleTestCase

from ..dominio import catalogos as cat
from ..dominio.clave import ClaveMedio
from ..infraestructura.http import respuesta_http
from . import falsos
from .falsos import leer_todo, montar

DATOS = bytes(range(256)) * 2000                      # 512 000 bytes
GRANDE = DATOS * 4                                    # 2 048 000 bytes: ocho trozos
MEDIOS = {("c1", "vid-1", ""): ("video/mp4", DATOS), ("c1", "grande", ""): ("video/mp4", GRANDE)}
CLAVE = ClaveMedio.de("biblioteca", "c1", "vid-1")
CLAVE_GRANDE = ClaveMedio.de("biblioteca", "c1", "grande")


def peticion_asgi() -> ASGIRequest:
    return ASGIRequest({"type": "http", "method": "GET", "path": "/x", "query_string": b"", "headers": [], "scheme": "http", "server": ("testserver", 80)},
                       io.BytesIO())


def local(m, rango=None, clave=CLAVE):
    return m.servidor.abrir(clave, rango, "GET", prioridad=cat.CLASE, modulo=cat.MODULO_AULA)


async def juntar(respuesta) -> bytes:
    return b"".join([trozo async for trozo in respuesta.streaming_content])


class CuerpoAsincronoTests(SimpleTestCase):
    def setUp(self):
        self.m = montar(self, MEDIOS)

    def test_bajo_asgi_el_cuerpo_es_asincrono_y_sale_completo(self):
        respuesta = respuesta_http(peticion_asgi(), local(self.m), "GET", self.m.servidor)
        self.assertTrue(respuesta.is_async)
        self.assertEqual((respuesta.status_code, respuesta["Content-Type"], respuesta["Content-Length"], respuesta["Accept-Ranges"]),
                         (200, "video/mp4", str(len(DATOS)), "bytes"))
        self.assertEqual(asyncio.run(juntar(respuesta)), DATOS)
        self.assertEqual(self.m.servidor.cupos.en_uso, 0)

    def test_un_tramo_grande_bajo_asgi(self):
        respuesta = respuesta_http(peticion_asgi(), local(self.m, "bytes=100000-499999"), "GET", self.m.servidor)
        self.assertTrue(respuesta.is_async)
        self.assertEqual((respuesta.status_code, respuesta["Content-Range"]), (206, f"bytes 100000-499999/{len(DATOS)}"))
        self.assertEqual(asyncio.run(juntar(respuesta)), DATOS[100000:500000])

    def test_lo_que_una_fuente_entrega_hecho_en_memoria_sale_como_respuesta_normal_con_su_cuerpo(self):
        ejemplo = ClaveMedio.de("ejemplo", "c1", "vid-1")
        m = montar(self, MEDIOS)
        respuesta = respuesta_http(peticion_asgi(), local(m, "bytes=100-199", clave=ejemplo), "GET", m.servidor)
        self.assertFalse(respuesta.streaming)
        self.assertEqual((respuesta.status_code, respuesta["Content-Range"], respuesta.content), (206, f"bytes 100-199/{len(DATOS)}", DATOS[100:200]))
        self.assertEqual((m.servidor.cupos.en_uso, m.almacen.lectores.total()), (0, 0))

    def test_la_biblioteca_siempre_sale_por_flujo_aunque_el_tramo_sea_corto(self):
        respuesta = respuesta_http(peticion_asgi(), local(self.m, "bytes=100-199"), "GET", self.m.servidor)
        self.assertTrue(respuesta.streaming)
        self.assertEqual(asyncio.run(juntar(respuesta)), DATOS[100:200])
        respuesta = respuesta_http(HttpRequest(), local(self.m, "bytes=0-9"), "GET", self.m.servidor)
        self.assertEqual(b"".join(respuesta.streaming_content), DATOS[:10])           # la forma que ya usaban las pruebas y los clientes

    def test_bajo_wsgi_el_cuerpo_es_sincrono(self):
        respuesta = respuesta_http(HttpRequest(), local(self.m), "GET", self.m.servidor)
        self.assertFalse(respuesta.is_async)
        self.assertEqual(b"".join(respuesta.streaming_content), DATOS)

    def test_head_y_416_no_llevan_cuerpo(self):
        h = respuesta_http(peticion_asgi(), local(self.m), "HEAD", self.m.servidor)
        self.assertEqual((h.status_code, h.content, h["Content-Type"]), (200, b"", "video/mp4"))
        fuera = respuesta_http(peticion_asgi(), local(self.m, f"bytes={len(DATOS)}-"), "GET", self.m.servidor)
        self.assertEqual((fuera.status_code, fuera["Content-Range"]), (416, f"bytes */{len(DATOS)}"))

    def test_el_cupo_se_libera_aunque_la_tableta_se_vaya_a_mitad(self):
        async def a_medias():
            respuesta = respuesta_http(peticion_asgi(), local(self.m), "GET", self.m.servidor)
            iterador = respuesta.streaming_content.__aiter__()
            await iterador.__anext__()
            self.assertEqual(self.m.servidor.cupos.en_uso, 1)          # mientras transmite ocupa un cupo
            await iterador.aclose()                                    # la conexión se cae
            respuesta.close()

        asyncio.run(a_medias())
        self.assertEqual(self.m.servidor.cupos.en_uso, 0)
        self.assertEqual(self.m.almacen.lectores.total(), 0)           # y deja de contar como lector (el archivo se puede expulsar)

    def test_cerrar_la_respuesta_sin_haberla_leido_no_deja_lectores(self):
        respuesta = respuesta_http(peticion_asgi(), local(self.m), "GET", self.m.servidor)
        self.assertEqual(self.m.almacen.lectores.total(), 1)
        respuesta.close()
        self.assertEqual(self.m.almacen.lectores.total(), 0)


class LimitesTests(SimpleTestCase):
    def test_con_todos_los_cupos_ocupados_espera_y_despues_envia_igual(self):
        m = montar(self, MEDIOS, transferencias=1, espera_cupo_seg=0.2)
        self.assertTrue(m.servidor.cupos.intentar())                   # otro ocupa el único cupo
        inicio = time.monotonic()
        respuesta = respuesta_http(peticion_asgi(), local(m), "GET", m.servidor)
        self.assertEqual(asyncio.run(juntar(respuesta)), DATOS)        # no falla: espera su turno y, vencida la espera, envía
        self.assertGreaterEqual(time.monotonic() - inicio, 0.2)
        self.assertEqual(m.servidor.estado()["contadores"].get("cupo_vencido"), 1)

    def test_si_el_cupo_se_libera_a_tiempo_no_hay_espera_de_mas(self):
        m = montar(self, MEDIOS, transferencias=1, espera_cupo_seg=5)
        m.servidor.cupos.intentar()

        async def probar():
            respuesta = respuesta_http(peticion_asgi(), local(m), "GET", m.servidor)
            tarea = asyncio.create_task(juntar(respuesta))
            await asyncio.sleep(0.1)
            m.servidor.cupos.liberar()
            return await tarea

        inicio = time.monotonic()
        self.assertEqual(asyncio.run(probar()), DATOS)
        self.assertLess(time.monotonic() - inicio, 3.0)

    def test_el_tope_de_ancho_de_banda_frena_la_salida(self):
        m = montar(self, MEDIOS, ancho_salida_bps=600_000)             # 600 kB/s: la ráfaga del primer segundo es de 600 kB, medio archivo ya cabe
        m2 = montar(self, MEDIOS, ancho_salida_bps=100_000)            # 100 kB/s: 512 kB tardan unos 4 s
        inicio = time.monotonic()
        asyncio.run(juntar(respuesta_http(peticion_asgi(), local(m), "GET", m.servidor)))
        rapido = time.monotonic() - inicio
        inicio = time.monotonic()
        asyncio.run(juntar(respuesta_http(peticion_asgi(), local(m2), "GET", m2.servidor)))
        lento = time.monotonic() - inicio
        self.assertLess(rapido, 1.0)
        self.assertGreater(lento, 3.0)

    def test_los_bytes_servidos_se_cuentan(self):
        m = montar(self, MEDIOS)
        asyncio.run(juntar(respuesta_http(peticion_asgi(), local(m), "GET", m.servidor)))
        self.assertEqual(m.servidor.estado()["contadores"]["bytes_servidos"], len(DATOS))


class SeguirUnaDescargaTests(SimpleTestCase):
    def test_un_cliente_asincrono_sigue_la_descarga_mientras_llega(self):
        m = montar(self, MEDIOS, hilos=1)
        m.origen.retraso = 0.1
        falsos.lanzar_hilos(self, m.servidor, 1)
        respuesta = respuesta_http(peticion_asgi(), local(m), "GET", m.servidor)
        tarea = m.servidor.planificador.activa(CLAVE.huella())
        self.assertIsNotNone(tarea)
        self.assertEqual(asyncio.run(juntar(respuesta)), DATOS)

    def test_si_la_descarga_se_cancela_el_cuerpo_se_corta_y_no_se_cuelga(self):
        m = montar(self, MEDIOS, hilos=1, estancado_seg=2.0)
        m.origen.retraso = 0.2
        falsos.lanzar_hilos(self, m.servidor, 1)
        respuesta = respuesta_http(peticion_asgi(), local(m, clave=CLAVE_GRANDE), "GET", m.servidor)
        m.servidor.cancelar(m.registro.obtener(CLAVE_GRANDE.huella())["id"])
        with self.assertRaises(OSError):
            asyncio.run(juntar(respuesta))
        self.assertEqual(m.servidor.cupos.en_uso, 0)

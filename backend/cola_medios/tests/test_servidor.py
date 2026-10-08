"""
El servidor de medios con una fuente falsa: se trae una vez, se sirve de disco con `Range`, se sigue una descarga en curso, se reanuda tras un corte, se
expulsa lo menos usado, se respetan las prioridades y la cola nunca le cuesta un medio a nadie.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time

from django.test import SimpleTestCase

from ..dominio import catalogos as cat
from ..dominio import errores as err
from ..dominio.clave import ClaveMedio
from . import falsos
from .falsos import id_de, lanzar_hilos, leer_todo, montar

VIDEO = bytes(range(256)) * 4000                       # 1 024 000 bytes
OTRO = bytes(reversed(range(256))) * 4000
PEQUENO = b"WEBVTT\n\n1\n00:00:00.000 --> 00:00:03.000\nHola"
SHA_VIDEO = hashlib.sha256(VIDEO).hexdigest()
MEDIOS = {
    ("c1", "vid-1", ""): ("video/mp4", VIDEO),
    ("c1", "vid-2", ""): ("video/mp4", OTRO),
    ("c1", "vid-3", ""): ("video/mp4", VIDEO[::-1]),
    ("c1", "vid-1", "subtitulos"): ("text/vtt; charset=utf-8", PEQUENO),
}
CLAVE = ClaveMedio.de("biblioteca", "c1", "vid-1")
CLAVE2 = ClaveMedio.de("biblioteca", "c1", "vid-2")
CLAVE3 = ClaveMedio.de("biblioteca", "c1", "vid-3")
SUBS = ClaveMedio.de("biblioteca", "c1", "vid-1", "subtitulos")


def abrir(m, clave=CLAVE, rango=None, metodo="GET", prioridad=cat.CLASE, modulo=cat.MODULO_AULA, contexto=""):
    return m.servidor.abrir(clave, rango, metodo, prioridad=prioridad, modulo=modulo, contexto_ref=contexto)


def gets(m) -> list:
    return [c for c in m.origen.llamadas if c[2] == "GET"]


def esperar(condicion, segundos=5.0):
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        if condicion():
            return True
        time.sleep(0.02)
    return condicion()


class SirveDeLaCacheTests(SimpleTestCase):
    def setUp(self):
        self.m = montar(self, MEDIOS)

    def test_el_primer_get_baja_de_la_fuente_y_los_siguientes_salen_del_disco(self):
        self.assertEqual(leer_todo(abrir(self.m)), VIDEO)
        self.assertEqual(leer_todo(abrir(self.m, rango="bytes=0-9")), VIDEO[:10])
        self.assertEqual(leer_todo(abrir(self.m, rango="bytes=1000-")), VIDEO[1000:])
        self.assertEqual(len(gets(self.m)), 1)
        fila = self.m.registro.obtener(CLAVE.huella())
        self.assertEqual((fila["estado"], fila["sha256"], fila["bytes_total"], fila["curso_version"]), (cat.DISPONIBLE, SHA_VIDEO, len(VIDEO), "1.0"))
        self.assertEqual(self.m.almacen.tamano(fila["id"]), len(VIDEO))

    def test_las_cabeceras_son_las_de_un_servidor_con_rangos(self):
        r = abrir(self.m)
        self.assertEqual((r.status, r.headers.get("Content-Type"), r.headers.get("Content-Length"), r.headers.get("Accept-Ranges")),
                         (200, "video/mp4", str(len(VIDEO)), "bytes"))
        self.assertEqual(r.headers.get("Cache-Control"), "no-store")
        self.assertEqual(r.headers.get("X-Avacom-Marcador"), "falso")              # lo que la fuente puso se conserva
        r.close()
        p = abrir(self.m, rango="bytes=10-19")
        self.assertEqual((p.status, p.headers.get("Content-Range"), p.headers.get("Content-Length")), (206, f"bytes 10-19/{len(VIDEO)}", "10"))
        p.close()

    def test_sufijo_tramo_abierto_y_fuera_de_rango(self):
        self.assertEqual(leer_todo(abrir(self.m, rango="bytes=-16")), VIDEO[-16:])
        self.assertEqual(leer_todo(abrir(self.m, rango=f"bytes={len(VIDEO) - 5}-")), VIDEO[-5:])
        fuera = abrir(self.m, rango=f"bytes={len(VIDEO)}-")
        self.assertEqual((fuera.status, fuera.headers.get("Content-Range")), (416, f"bytes */{len(VIDEO)}"))
        self.assertEqual(leer_todo(fuera), b"")
        self.assertEqual(leer_todo(abrir(self.m, rango="bytes=basura")), VIDEO)       # un Range ilegible se ignora: archivo entero

    def test_head_sin_copia_no_interviene_y_con_copia_contesta_sin_ir_a_la_fuente(self):
        self.assertIsNone(abrir(self.m, metodo="HEAD"))
        self.assertEqual(self.m.origen.llamadas, [])                                  # un HEAD no pone nada en cola
        leer_todo(abrir(self.m))
        antes = len(self.m.origen.llamadas)
        h = abrir(self.m, metodo="HEAD")
        self.assertEqual((h.status, h.headers.get("Content-Length"), h.headers.get("Content-Type")), (200, str(len(VIDEO)), "video/mp4"))
        self.assertEqual(leer_todo(h), b"")
        self.assertEqual(len(self.m.origen.llamadas), antes)

    def test_los_archivos_internos_y_los_subtitulos_son_recursos_aparte(self):
        self.assertEqual(leer_todo(abrir(self.m, SUBS)), PEQUENO)
        self.assertEqual(leer_todo(abrir(self.m)), VIDEO)
        self.assertEqual(len(self.m.registro.filas), 2)

    def test_lo_pequeno_tambien_vive_en_memoria_y_se_sirve_de_ahi(self):
        leer_todo(abrir(self.m, SUBS))
        fila = self.m.registro.obtener(SUBS.huella())
        self.assertEqual(self.m.memoria.get(f"cm:b:{fila['id']}"), PEQUENO)
        local = abrir(self.m, SUBS)
        self.assertEqual(local._datos, PEQUENO)
        self.assertEqual(leer_todo(local), PEQUENO)

    def test_un_recurso_en_la_caja_sin_archivo_se_vuelve_a_traer(self):
        leer_todo(abrir(self.m))
        os.remove(self.m.almacen.ruta(id_de(self.m, CLAVE)))
        self.assertEqual(leer_todo(abrir(self.m)), VIDEO)
        self.assertEqual(len(gets(self.m)), 2)


class VigenciaDelCursoTests(SimpleTestCase):
    """El curso y su autorización siguen siendo de la biblioteca: la copia no se sirve si el curso cambió, se retiró o la biblioteca no está."""

    def setUp(self):
        self.m = montar(self, MEDIOS)
        leer_todo(abrir(self.m))

    def olvidar_version(self):
        self.m.memoria.datos.pop("cm:v:biblioteca:c1", None)

    def test_una_version_nueva_del_curso_descarta_la_copia_vieja(self):
        self.m.origen.version = "2.0"
        self.m.origen.medios[("c1", "vid-1", "")] = ("video/mp4", OTRO)
        self.olvidar_version()
        self.assertEqual(leer_todo(abrir(self.m)), OTRO)
        self.assertEqual(len(gets(self.m)), 2)
        filas = [f for f in self.m.registro.filas.values() if f["media_ref"] == "vid-1"]
        self.assertEqual([(f["curso_version"], f["estado"]) for f in filas], [("2.0", cat.DISPONIBLE)])    # no se acumula una copia por versión

    def test_dentro_de_la_vigencia_no_se_vuelve_a_preguntar_a_la_biblioteca(self):
        for _ in range(5):
            leer_todo(abrir(self.m))
        self.assertEqual(self.m.origen.versiones_pedidas, 1)

    def test_si_el_curso_ya_no_se_ofrece_no_se_sirve_la_copia(self):
        self.m.origen.cursos = set()
        self.olvidar_version()
        with self.assertRaises(err.ErrorDeOrigen) as c:
            abrir(self.m)
        self.assertFalse(c.exception.transitorio)

    def test_con_la_biblioteca_cerrada_no_se_sirve_la_copia(self):
        self.m.origen.no_disponible = True
        self.olvidar_version()
        with self.assertRaises(err.ErrorDeOrigen) as c:
            abrir(self.m)
        self.assertTrue(c.exception.transitorio)

    def test_si_se_permite_la_copia_sirve_aunque_la_biblioteca_este_cerrada_pero_no_si_retiro_el_curso(self):
        m = montar(self, MEDIOS, servir_sin_biblioteca=True)
        leer_todo(abrir(m))
        m.origen.no_disponible = True
        m.memoria.datos.pop("cm:v:biblioteca:c1", None)
        self.assertEqual(leer_todo(abrir(m)), VIDEO)
        m.origen.no_disponible = False
        m.origen.cursos = set()
        m.memoria.datos.pop("cm:v:biblioteca:c1", None)
        with self.assertRaises(err.ErrorDeOrigen):
            abrir(m)


class FallosTests(SimpleTestCase):
    def test_un_medio_inexistente_pasa_el_error_original_y_no_deja_rastro_en_la_cola(self):
        m = montar(self, MEDIOS)
        fantasma = ClaveMedio.de("biblioteca", "c1", "no-existe")
        with self.assertRaises(err.ErrorDeOrigen) as c:
            abrir(m, fantasma)
        self.assertIsInstance(c.exception.original, LookupError)
        self.assertFalse(c.exception.transitorio)
        self.assertIsNone(m.registro.obtener(fantasma.huella()))      # que la biblioteca diga «no existe» no es una falla de la cola: no sale en el panel
        self.assertIsNone(m.servidor.planificador.activa(fantasma.huella()))
        n = len(m.origen.llamadas)
        with self.assertRaises(err.ErrorDeOrigen):                    # la siguiente petición lo vuelve a preguntar, como el paso a través de siempre
            abrir(m, fantasma)
        self.assertGreater(len(m.origen.llamadas), n)

    def test_una_falla_transitoria_si_se_recuerda_y_no_se_reintenta_de_inmediato(self):
        m = montar(self, MEDIOS)

        def cerrada(clave, rango, metodo):
            raise err.ErrorDeOrigen(RuntimeError("se cerró"), transitorio=True)

        m.origen.abrir = cerrada
        self.assertRaises(err.ErrorDeOrigen, abrir, m)
        fila = m.registro.obtener(CLAVE.huella())
        self.assertEqual((fila["estado"], fila["error_codigo"]), (cat.FALLIDO, cat.ORIGEN_NO_DISPONIBLE))
        self.assertIsNone(abrir(m))                                   # dentro de la espera la cola no interviene: quien llama va directo
        m.reloj.avanzar(61)
        self.assertRaises(err.ErrorDeOrigen, abrir, m)                # pasado un minuto, se vuelve a intentar

    def test_un_corte_a_mitad_se_reanuda_donde_se_quedo(self):
        m = montar(self, MEDIOS)
        m.origen.fallar_tras = 300_000
        self.assertEqual(leer_todo(abrir(m)), VIDEO)
        self.assertEqual([c[1] for c in gets(m)], [None, "bytes=300000-"])
        fila = m.registro.obtener(CLAVE.huella())
        self.assertEqual((fila["estado"], fila["sha256"], fila["intentos"]), (cat.DISPONIBLE, SHA_VIDEO, 2))

    def test_si_la_fuente_ignora_el_range_se_empieza_de_cero(self):
        m = montar(self, MEDIOS)
        original = m.origen.abrir

        def sin_rangos(clave, rango, metodo):
            return original(clave, None, metodo)                  # contesta 200 con todo aunque se le pida desde N

        m.origen.abrir = sin_rangos
        m.origen.fallar_tras = 300_000
        self.assertEqual(leer_todo(abrir(m)), VIDEO)

    def test_si_no_cabe_en_la_cache_falla_con_sin_espacio_y_se_sirve_directo(self):
        m = montar(self, MEDIOS, max_bytes=500_000)
        self.assertIsNone(abrir(m))
        fila = m.registro.obtener(CLAVE.huella())
        self.assertEqual((fila["estado"], fila["error_codigo"]), (cat.FALLIDO, cat.SIN_ESPACIO))
        self.assertGreater(fila["reintentar_despues"], m.reloj.ahora + 500_000)          # no se insiste cada petición
        self.assertEqual(m.almacen.tamano(fila["id"]), 0)

    def test_sin_hilos_ni_cola_lo_que_la_cola_no_puede_se_sirve_directo(self):
        m = montar(self, MEDIOS, activa=False)
        self.assertIsNone(abrir(m))
        self.assertEqual(m.origen.llamadas, [])


class ExpulsionTests(SimpleTestCase):
    def test_sale_lo_menos_usado_para_hacer_sitio(self):
        m = montar(self, MEDIOS, max_bytes=2_500_000)
        leer_todo(abrir(m, CLAVE))
        m.reloj.avanzar(10)
        leer_todo(abrir(m, CLAVE2))
        m.reloj.avanzar(10)
        leer_todo(abrir(m, CLAVE))                                  # A se usó después que B
        m.servidor.mantenimiento()                                   # anota los usos
        m.reloj.avanzar(10)
        leer_todo(abrir(m, CLAVE3))                                  # C no cabe: sale B
        self.assertIsNotNone(m.registro.obtener(CLAVE.huella()))
        self.assertIsNone(m.registro.obtener(CLAVE2.huella()))
        self.assertIsNotNone(m.registro.obtener(CLAVE3.huella()))
        self.assertLessEqual(m.registro.resumen()["bytes_ocupados"], 2_500_000)

    def test_no_se_expulsa_lo_que_se_esta_leyendo(self):
        m = montar(self, MEDIOS, max_bytes=2_500_000)
        leyendo = abrir(m, CLAVE)                                    # A abierto, sin cerrar
        leer_todo(abrir(m, CLAVE2))
        m.reloj.avanzar(10)
        leer_todo(abrir(m, CLAVE3))                                  # sale B, no A (aunque A sea más viejo)
        self.assertIsNotNone(m.registro.obtener(CLAVE.huella()))
        self.assertIsNone(m.registro.obtener(CLAVE2.huella()))
        leyendo.close()

    def test_lo_usado_hace_poco_esta_protegido(self):
        m = montar(self, MEDIOS, max_bytes=2_500_000, proteger_seg=300)
        leer_todo(abrir(m, CLAVE))
        leer_todo(abrir(m, CLAVE2))
        self.assertIsNone(abrir(m, CLAVE3))                          # nada se puede expulsar todavía: no cabe y se sirve directo
        self.assertEqual(m.registro.obtener(CLAVE3.huella())["error_codigo"], cat.SIN_ESPACIO)

    def test_limpiar_vacia_lo_que_nadie_lee(self):
        m = montar(self, MEDIOS)
        leer_todo(abrir(m, CLAVE))
        leyendo = abrir(m, CLAVE2)
        self.assertEqual(m.servidor.limpiar(), 1)
        self.assertIsNotNone(m.registro.obtener(CLAVE2.huella()))
        leyendo.close()

    def test_el_mantenimiento_quita_filas_sin_archivo_y_archivos_sin_fila(self):
        m = montar(self, MEDIOS)
        leer_todo(abrir(m))
        os.remove(m.almacen.ruta(id_de(m, CLAVE)))
        suelto = m.almacen.ruta("ab-suelto")
        suelto.parent.mkdir(parents=True, exist_ok=True)
        suelto.write_bytes(b"x")
        viejo = time.time() - 3600
        os.utime(suelto, (viejo, viejo))
        resultado = m.servidor.mantenimiento()
        self.assertEqual((resultado["faltantes"], resultado["huerfanos"]), (1, 1))
        self.assertIsNone(m.registro.obtener(CLAVE.huella()))
        self.assertFalse(suelto.exists())


class PrioridadTests(SimpleTestCase):
    def preparar(self, m, clave, prioridad, ctx="s1", reemplazar=False):
        return m.servidor.preparar([(clave.media_ref, clave.ruta)], fuente="biblioteca", curso_ref="c1", modulo=cat.MODULO_AULA, contexto_ref=ctx,
                                   prioridad=prioridad, reemplazar=reemplazar)

    def test_sale_primero_lo_proyectado_y_a_igual_prioridad_el_orden_de_llegada(self):
        m = montar(self, MEDIOS)
        self.preparar(m, CLAVE, cat.PRECARGA)
        self.preparar(m, CLAVE2, cat.CLASE)
        self.preparar(m, CLAVE3, cat.PROYECCION)
        orden = [m.servidor.planificador.siguiente(urgente_solo=False, segundos=0.01).clave.media_ref for _ in range(3)]
        self.assertEqual(orden, ["vid-3", "vid-2", "vid-1"])
        self.assertIsNone(m.servidor.planificador.siguiente(urgente_solo=False, segundos=0.01))

    def test_el_hilo_reservado_no_toma_lo_que_no_es_urgente(self):
        m = montar(self, MEDIOS)
        self.preparar(m, CLAVE, cat.PAQUETE)
        self.assertIsNone(m.servidor.planificador.siguiente(urgente_solo=True, segundos=0.01))
        self.preparar(m, CLAVE2, cat.CLASE)
        self.assertEqual(m.servidor.planificador.siguiente(urgente_solo=True, segundos=0.01).clave.media_ref, "vid-2")

    def test_pedirlo_con_mas_prioridad_adelanta_lo_que_ya_esperaba(self):
        m = montar(self, MEDIOS)
        self.preparar(m, CLAVE, cat.PRECARGA)
        self.preparar(m, CLAVE2, cat.PAQUETE)
        self.preparar(m, CLAVE, cat.PROYECCION, ctx="s2")            # lo mismo, ahora proyectado
        self.assertEqual(m.servidor.planificador.siguiente(urgente_solo=False, segundos=0.01).clave.media_ref, "vid-1")
        self.assertEqual(m.servidor.planificador.siguiente(urgente_solo=False, segundos=0.01).clave.media_ref, "vid-2")

    def test_la_proyeccion_que_se_reemplaza_baja_a_clase(self):
        m = montar(self, MEDIOS)
        self.preparar(m, CLAVE, cat.PROYECCION, reemplazar=True)
        self.preparar(m, CLAVE2, cat.PROYECCION, reemplazar=True)
        a, b = id_de(m, CLAVE), id_de(m, CLAVE2)
        self.assertEqual((m.registro.mejor_prioridad(a, m.reloj.ahora), m.registro.mejor_prioridad(b, m.reloj.ahora)), (cat.CLASE, cat.PROYECCION))
        self.assertEqual(m.servidor.planificador.activa(CLAVE.huella()).prioridad, cat.CLASE)

    def test_lanzar_algo_no_baja_lo_que_se_esta_proyectando(self):
        m = montar(self, MEDIOS)
        self.preparar(m, CLAVE, cat.PROYECCION, reemplazar=True)
        self.preparar(m, CLAVE2, cat.PROYECCION, reemplazar=False)   # un lanzamiento
        self.assertEqual(m.registro.mejor_prioridad(id_de(m, CLAVE), m.reloj.ahora), cat.PROYECCION)

    def test_una_proyeccion_vencida_ya_no_cuenta(self):
        m = montar(self, MEDIOS, vigencia_proyeccion_seg=60)
        self.preparar(m, CLAVE, cat.PROYECCION)
        m.reloj.avanzar(61)
        self.assertIsNone(m.registro.mejor_prioridad(id_de(m, CLAVE), m.reloj.ahora))

    def test_preparar_con_la_biblioteca_cerrada_no_lanza_y_no_encola(self):
        m = montar(self, MEDIOS)
        m.origen.no_disponible = True
        self.assertEqual(self.preparar(m, CLAVE, cat.PROYECCION), {"encolados": 0, "omitidos": 1})

    def test_preparar_avisa_a_la_clase(self):
        m = montar(self, MEDIOS)
        self.preparar(m, CLAVE, cat.PROYECCION, ctx="sesion-9")
        self.assertIn((cat.MODULO_AULA, "sesion-9"), m.difusion.avisos)

    def test_preparar_lo_que_ya_esta_en_la_cache_no_lo_vuelve_a_bajar(self):
        m = montar(self, MEDIOS)
        leer_todo(abrir(m))
        self.assertEqual(self.preparar(m, CLAVE, cat.PROYECCION), {"encolados": 1, "omitidos": 0})
        self.assertEqual(len(gets(m)), 1)
        self.assertIsNone(m.servidor.planificador.siguiente(urgente_solo=False, segundos=0.01))


class ConHilosTests(SimpleTestCase):
    """Descargas de verdad, en hilos, contra una fuente lenta."""

    def test_un_hilo_trae_lo_que_se_preparo(self):
        m = montar(self, MEDIOS, hilos=2)
        lanzar_hilos(self, m.servidor, 2)
        m.servidor.preparar([("vid-1", "")], fuente="biblioteca", curso_ref="c1", modulo=cat.MODULO_AULA, contexto_ref="s1", prioridad=cat.PROYECCION)
        self.assertTrue(esperar(lambda: (m.registro.obtener(CLAVE.huella()) or {}).get("estado") == cat.DISPONIBLE))
        self.assertEqual(m.registro.obtener(CLAVE.huella())["sha256"], SHA_VIDEO)
        self.assertGreaterEqual(len(m.difusion.avisos), 2)               # al preparar y al terminar
        self.assertEqual(leer_todo(abrir(m)), VIDEO)
        self.assertEqual(len(gets(m)), 1)

    def test_muchas_tabletas_piden_lo_mismo_y_la_fuente_ve_una_sola_descarga(self):
        m = montar(self, MEDIOS, hilos=2)
        m.origen.retraso = 0.02
        lanzar_hilos(self, m.servidor, 2)
        resultados: list = []

        def tableta():
            resultados.append(leer_todo(abrir(m)))

        hilos = [threading.Thread(target=tableta) for _ in range(12)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(20)
        self.assertEqual(len(resultados), 12)
        self.assertTrue(all(r == VIDEO for r in resultados))
        self.assertEqual(len(gets(m)), 1)

    def test_se_sirve_mientras_baja_sin_esperar_a_que_termine(self):
        m = montar(self, MEDIOS, hilos=1)
        m.origen.retraso = 0.2
        lanzar_hilos(self, m.servidor, 1)
        local = abrir(m)
        tarea = m.servidor.planificador.activa(CLAVE.huella())
        self.assertIsNotNone(tarea)
        self.assertNotEqual(tarea.estado, cat.DISPONIBLE)                  # sigue bajando: la respuesta no esperó al final
        self.assertEqual((local.status, local.headers.get("Content-Length")), (200, str(len(VIDEO))))
        self.assertEqual(leer_todo(local), VIDEO)

    def test_un_tramo_del_medio_de_una_descarga_en_curso(self):
        m = montar(self, MEDIOS, hilos=1)
        m.origen.retraso = 0.1
        lanzar_hilos(self, m.servidor, 1)
        local = abrir(m, rango="bytes=300000-399999")
        self.assertEqual((local.status, local.headers.get("Content-Range")), (206, f"bytes 300000-399999/{len(VIDEO)}"))
        self.assertEqual(leer_todo(local), VIDEO[300000:400000])

    def test_un_salto_lejos_de_lo_descargado_se_sirve_directo(self):
        m = montar(self, MEDIOS, hilos=1, adelanto_max_bytes=100_000)
        m.origen.retraso = 0.3
        lanzar_hilos(self, m.servidor, 1)
        self.assertIsNone(abrir(m, rango="bytes=900000-"))
        self.assertEqual(leer_todo(abrir(m)), VIDEO)                       # la descarga siguió su camino

    def test_si_la_fuente_tarda_mas_que_la_espera_se_sirve_directo_y_la_cola_sigue(self):
        m = montar(self, MEDIOS, hilos=1, espera_inicio_seg=0.3)
        m.origen.puerta = threading.Event()
        lanzar_hilos(self, m.servidor, 1)
        inicio = time.monotonic()
        self.assertIsNone(abrir(m))
        self.assertLess(time.monotonic() - inicio, 2.0)
        m.origen.puerta.set()
        self.assertTrue(esperar(lambda: (m.registro.obtener(CLAVE.huella()) or {}).get("estado") == cat.DISPONIBLE))

    def test_si_se_corta_mientras_se_sirve_la_lectura_falla_y_no_se_queda_colgada(self):
        m = montar(self, MEDIOS, hilos=1, reintentos=1)
        m.origen.retraso = 0.05
        m.origen.fallar_tras = 300_000
        lanzar_hilos(self, m.servidor, 1)
        local = abrir(m)
        with self.assertRaises(OSError):
            local.read(-1)
        local.close()

    def test_cancelar_una_descarga_en_curso_la_detiene_y_borra_lo_bajado(self):
        m = montar(self, MEDIOS, hilos=1)
        m.origen.retraso = 0.2
        lanzar_hilos(self, m.servidor, 1)
        m.servidor.preparar([("vid-1", "")], fuente="biblioteca", curso_ref="c1", modulo=cat.MODULO_AULA, contexto_ref="s1", prioridad=cat.CLASE)
        recurso_id = id_de(m, CLAVE)
        self.assertTrue(esperar(lambda: m.registro.por_id(recurso_id)["estado"] == cat.DESCARGANDO))
        self.assertTrue(m.servidor.cancelar(recurso_id))
        self.assertTrue(esperar(lambda: m.registro.por_id(recurso_id)["estado"] == cat.CANCELADO))
        self.assertEqual(m.almacen.tamano(recurso_id), 0)

    def test_cancelar_lo_que_todavia_espera_turno(self):
        m = montar(self, MEDIOS)
        m.servidor.preparar([("vid-1", "")], fuente="biblioteca", curso_ref="c1", modulo=cat.MODULO_AULA, contexto_ref="s1", prioridad=cat.CLASE)
        recurso_id = id_de(m, CLAVE)
        self.assertTrue(m.servidor.cancelar(recurso_id))
        self.assertEqual(m.registro.por_id(recurso_id)["estado"], cat.CANCELADO)
        self.assertIsNone(m.servidor.planificador.activa(CLAVE.huella()))
        self.assertFalse(m.servidor.cancelar(recurso_id))                    # ya cancelado

    def test_reintentar_un_fallido_lo_vuelve_a_poner_en_cola(self):
        m = montar(self, MEDIOS)
        original = m.origen.abrir

        def cerrada(clave, rango, metodo):
            raise err.ErrorDeOrigen(RuntimeError("la biblioteca se cerró a mitad"), transitorio=True)

        m.origen.abrir = cerrada
        self.assertRaises(err.ErrorDeOrigen, abrir, m)               # se rinde tras sus reintentos y lo dice
        recurso_id = id_de(m, CLAVE)
        fila = m.registro.por_id(recurso_id)
        self.assertEqual((fila["estado"], fila["error_codigo"], fila["intentos"]), (cat.FALLIDO, cat.ORIGEN_NO_DISPONIBLE, 2))
        self.assertIsNone(abrir(m))                                  # un fallido reciente no se reintenta solo: quien llama va directo
        m.origen.abrir = original
        self.assertTrue(m.servidor.reintentar(recurso_id))
        m.servidor.descargador.ejecutar(m.servidor.planificador.siguiente(urgente_solo=False, segundos=0.1))
        self.assertEqual(m.registro.por_id(recurso_id)["estado"], cat.DISPONIBLE)
        self.assertFalse(m.servidor.reintentar(recurso_id))          # ya está lista


class MedirTests(SimpleTestCase):
    def test_se_trae_una_vez_y_todos_reutilizan_la_medida(self):
        m = montar(self, MEDIOS)
        uno = m.servidor.medir(CLAVE, prioridad=cat.PAQUETE, modulo=cat.MODULO_ESTUDIO, contexto_ref="asig-1", tope_bytes=10**9)
        otro = m.servidor.medir(CLAVE, prioridad=cat.PAQUETE, modulo=cat.MODULO_ESTUDIO, contexto_ref="asig-2", tope_bytes=10**9)
        self.assertEqual(uno, {"bytes": len(VIDEO), "sha256": SHA_VIDEO, "mime": "video/mp4"})
        self.assertEqual(uno, otro)
        self.assertEqual(len(gets(m)), 1)
        self.assertEqual(sorted(c for _, c in [(0, s["contexto_ref"]) for s in m.registro.solicitudes]), ["asig-1", "asig-2"])

    def test_un_medio_mas_grande_que_el_tope_se_rechaza(self):
        m = montar(self, MEDIOS)
        leer_todo(abrir(m))
        with self.assertRaises(err.DemasiadoGrande) as c:
            m.servidor.medir(CLAVE, prioridad=cat.PAQUETE, modulo=cat.MODULO_ESTUDIO, contexto_ref="", tope_bytes=1000)
        self.assertEqual(c.exception.bytes, len(VIDEO))

    def test_un_medio_grande_que_baja_en_segundo_plano_se_corta_al_saber_que_pasa_del_tope(self):
        m = montar(self, MEDIOS, hilos=1)
        m.origen.retraso = 0.2
        lanzar_hilos(self, m.servidor, 1)
        with self.assertRaises(err.DemasiadoGrande):
            m.servidor.medir(CLAVE, prioridad=cat.PAQUETE, modulo=cat.MODULO_ESTUDIO, contexto_ref="", tope_bytes=1000)
        self.assertTrue(esperar(lambda: m.registro.obtener(CLAVE.huella())["estado"] == cat.CANCELADO))

    def test_un_medio_inexistente_pasa_el_error_original(self):
        m = montar(self, MEDIOS)
        with self.assertRaises(err.ErrorDeOrigen):
            m.servidor.medir(ClaveMedio.de("biblioteca", "c1", "no-existe"), prioridad=cat.PAQUETE, modulo=cat.MODULO_ESTUDIO, contexto_ref="", tope_bytes=10**9)


class RehidratarTests(SimpleTestCase):
    def test_tras_un_reinicio_lo_que_quedo_a_medias_se_reanuda(self):
        m = montar(self, MEDIOS)
        ahora = m.reloj.ahora
        fila = m.registro.crear({"id": falsos.nuevo_id(), "clave": CLAVE.huella(), "fuente": "biblioteca", "curso_ref": "c1", "media_ref": "vid-1", "ruta": "",
                                 "estado": cat.DESCARGANDO, "creado_en": ahora, "actualizado_en": ahora, "curso_version": "1.0", "bytes_hechos": 300_000,
                                 "bytes_total": len(VIDEO)})
        ruta = m.almacen.ruta(fila["id"])
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(VIDEO[:300_000])
        self.assertEqual(m.servidor.rehidratar(), 1)
        tarea = m.servidor.planificador.siguiente(urgente_solo=False, segundos=0.1)
        self.assertEqual(tarea.id, fila["id"])
        m.servidor.descargador.ejecutar(tarea)
        self.assertEqual([c[1] for c in gets(m)], ["bytes=300000-"])
        self.assertEqual(m.registro.por_id(fila["id"])["sha256"], SHA_VIDEO)
        self.assertEqual(m.almacen.ruta(fila["id"]).read_bytes(), VIDEO)

    def test_si_el_curso_cambio_de_version_mientras_estaba_apagado_se_descarta(self):
        m = montar(self, MEDIOS, version="2.0")
        ahora = m.reloj.ahora
        fila = m.registro.crear({"id": falsos.nuevo_id(), "clave": CLAVE.huella(), "fuente": "biblioteca", "curso_ref": "c1", "media_ref": "vid-1", "ruta": "",
                                 "estado": cat.PENDIENTE, "creado_en": ahora, "actualizado_en": ahora, "curso_version": "1.0"})
        self.assertEqual(m.servidor.rehidratar(), 0)
        self.assertIsNone(m.registro.por_id(fila["id"]))


class EstadoTests(SimpleTestCase):
    def test_el_estado_resume_cola_cache_cupos_y_limites(self):
        m = montar(self, MEDIOS, transferencias=7, ancho_salida_bps=2048 * 1024)
        leer_todo(abrir(m))
        m.servidor.preparar([("vid-2", "")], fuente="biblioteca", curso_ref="c1", modulo=cat.MODULO_AULA, contexto_ref="s1", prioridad=cat.CLASE)
        e = m.servidor.estado()
        self.assertEqual((e["cola"]["pendientes"], e["recursos"]["disponible"], e["recursos"]["pendiente"]), (1, 1, 1))
        self.assertEqual(e["cache"]["bytes_ocupados"], len(VIDEO))
        self.assertEqual((e["transferencias"]["maximo"], e["limites"]["ancho_salida_bps"]), (7, 2048 * 1024))
        self.assertEqual(e["contadores"]["aciertos"] if "aciertos" in e["contadores"] else 0, 0)

    def test_listar_un_contexto_trae_su_avance(self):
        m = montar(self, MEDIOS)
        m.servidor.preparar([("vid-1", ""), ("vid-2", "")], fuente="biblioteca", curso_ref="c1", modulo=cat.MODULO_AULA, contexto_ref="s1", prioridad=cat.CLASE)
        tarea = m.servidor.planificador.siguiente(urgente_solo=False, segundos=0.1)
        m.servidor.descargador.ejecutar(tarea)
        filas = {f["media_ref"]: f for f in m.servidor.listar(contexto_ref="s1")}
        self.assertEqual((filas["vid-1"]["estado"], filas["vid-1"]["porcentaje"]), (cat.DISPONIBLE, 100))
        self.assertEqual((filas["vid-2"]["estado"], filas["vid-2"]["porcentaje"]), (cat.PENDIENTE, None))
        self.assertEqual(m.servidor.listar(contexto_ref="s1", estado=cat.DISPONIBLE)[0]["media_ref"], "vid-1")
        self.assertEqual(m.servidor.listar(contexto_ref="otra"), [])

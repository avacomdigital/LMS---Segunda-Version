"""
La lógica de emitir, sin entrada ni salida (LIC-E-01, LIC-E-04, LIC-E-08, LIC-E-09): fechas, construcción, firma y, sobre todo, que el lector del NODO (`licenciamiento.dominio`) lea
EXACTAMENTE lo que el emisor escribió.
"""
from __future__ import annotations

import calendar
import hashlib
import random
import unittest
import uuid
from datetime import date

from avacom_licencias import emision
from avacom_licencias.dominio_nodo import catalogos, firma, huella, licencia, solicitud

from licenciamiento.dominio import estado  # noqa: E402 — disponible porque avacom_licencias.dominio_nodo ya puso el dominio en sys.path

from .apoyo import AHORA, DIA_MS, NodoDePrueba

OK = huella.Coincidencia(k=3, en_licencia=5, coinciden=5, ok=True, parcial=False, nivel=huella.NIVEL_HARDWARE)


def peticion(**cambios) -> emision.Peticion:
    base = dict(aula="Colegio", tipo="produccion", gracia_dias=30, equipos=55, usuarios=1200, normal=50, pico=100, capacidades=frozenset({"*"}), hasta=date(2027, 10, 31))
    base.update(cambios)
    return emision.Peticion(**base)


def ms(*fecha_hora) -> int:
    return calendar.timegm(fecha_hora) * 1000


class FechasTests(unittest.TestCase):
    def test_desde_es_un_dia_antes_del_inicio_de_hoy_y_vence_al_final_del_dia(self):
        desde, vence = emision.fechas(AHORA, hasta=date(2027, 10, 31), meses=None)
        self.assertEqual(desde, ms(2026, 10, 19, 0, 0, 0))
        self.assertEqual(vence, ms(2027, 10, 31, 23, 59, 59) + 999)

    def test_por_meses_cuenta_desde_hoy(self):
        desde, vence = emision.fechas(AHORA, hasta=None, meses=12)
        self.assertEqual(vence, ms(2027, 10, 20, 23, 59, 59) + 999)
        self.assertEqual(desde, ms(2026, 10, 19, 0, 0, 0))

    def test_los_meses_no_se_salen_del_calendario(self):
        self.assertEqual(emision.sumar_meses(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(emision.sumar_meses(date(2024, 1, 31), 1), date(2024, 2, 29))
        self.assertEqual(emision.sumar_meses(date(2026, 11, 30), 3), date(2027, 2, 28))
        self.assertEqual(emision.sumar_meses(date(2026, 12, 15), 1), date(2027, 1, 15))

    def test_una_vigencia_que_ya_termino_no_se_emite(self):
        with self.assertRaises(emision.ErrorDeEmision):
            emision.fechas(AHORA, hasta=date(2026, 10, 19), meses=None)
        desde, vence = emision.fechas(AHORA, hasta=date(2026, 10, 20), meses=None)       # hoy mismo: vence al final del día
        self.assertGreater(vence, AHORA)

    def test_una_vigencia_de_mas_de_25_anos_no_se_emite(self):
        with self.assertRaises(emision.ErrorDeEmision):
            emision.fechas(AHORA, hasta=date(2060, 1, 1), meses=None)
        emision.fechas(AHORA, hasta=date(2050, 1, 1), meses=None)

    def test_una_licencia_emitida_hoy_vale_para_un_nodo_con_el_reloj_atrasado(self):
        """LIC-E-04 · H-08: el margen del emisor cubre un reloj atrasado hasta casi un día y medio (desde = ayer a las 00:00 UTC)."""
        nodo = NodoDePrueba()
        sol = solicitud.leer_solicitud(nodo.solicitud())
        lic = emision.construir(sol, peticion(), licencia_id="a7a7a7a7-0001-4000-8000-000000000001", serie=1, ahora_ms=AHORA)
        for atraso_horas in (0, 20, 38):
            e = estado.calcular(estado.Contexto(licencia=lic, ahora=AHORA - atraso_horas * 3_600_000, instalada_en=AHORA - 60 * DIA_MS, coincidencia=OK))
            self.assertEqual(e.estado, "activa", f"con {atraso_horas} h de atraso")
        # Más allá del margen (≈ 39 h) el nodo ve la licencia como «aún no vigente» y vuelve a su evaluación; si ésta ya terminó, queda degradado (H-08): el emisor no puede evitarlo
        en_evaluacion = estado.calcular(estado.Contexto(licencia=lic, ahora=AHORA - 40 * 3_600_000, instalada_en=AHORA - 5 * DIA_MS, coincidencia=OK))
        self.assertEqual((en_evaluacion.estado, en_evaluacion.motivo), ("sin_licencia", "aun_no_vigente"))
        evaluacion_vencida = estado.calcular(estado.Contexto(licencia=lic, ahora=AHORA - 40 * 3_600_000, instalada_en=AHORA - 60 * DIA_MS, coincidencia=OK))
        self.assertEqual(evaluacion_vencida.estado, "degradada")


class ValidarTests(unittest.TestCase):
    def test_lo_valido_pasa(self):
        emision.validar(peticion())
        emision.validar(peticion(tipo="evaluacion", equipos=licencia.ILIMITADO, hasta=None, meses=1, capacidades=frozenset({"reportes", "busqueda"})))

    def test_lo_que_no_se_emite(self):
        casos = {
            "tipo desarrollo": peticion(tipo="desarrollo"), "tipo raro": peticion(tipo="otro"), "gracia negativa": peticion(gracia_dias=-1), "gracia de 400": peticion(gracia_dias=400),
            "equipos cero": peticion(equipos=0), "usuarios negativos": peticion(usuarios=-5), "normal mayor que pico": peticion(normal=60, pico=50),
            "capacidad desconocida": peticion(capacidades=frozenset({"magia"})), "sin capacidades": peticion(capacidades=frozenset()),
            "liberación de cero días": peticion(liberacion_dias=0), "liberación de 400 días": peticion(liberacion_dias=400),
            "sin vigencia": peticion(hasta=None, meses=None), "vigencia doble": peticion(hasta=date(2027, 1, 1), meses=3),
        }
        for nombre, p in casos.items():
            with self.subTest(nombre), self.assertRaises(emision.ErrorDeEmision):
                emision.validar(p)


class ConstruirTests(unittest.TestCase):
    def test_la_huella_es_la_de_la_solicitud_tal_cual(self):
        nodo = NodoDePrueba()
        sol = solicitud.leer_solicitud(nodo.solicitud())
        lic = emision.construir(sol, peticion(aula="  Colegio   San  Martín "), licencia_id="a7a7a7a7-0001-4000-8000-000000000001", serie=3, ahora_ms=AHORA)
        self.assertEqual(lic.huella, sol.huella)
        self.assertEqual(lic.hash_clave_nodo, firma.huella_de_clave(sol.clave_nodo))
        self.assertEqual(lic.aula, "Colegio San Martín")
        self.assertEqual((lic.serie, lic.emitida), (3, AHORA))
        self.assertFalse(lic.liberacion_pendiente)
        self.assertLess(lic.desde, AHORA)
        self.assertGreater(lic.vence, AHORA)

    def test_sin_nombre_usa_el_de_la_solicitud(self):
        sol = solicitud.leer_solicitud(NodoDePrueba().solicitud(aula="Aula de la solicitud"))
        lic = emision.construir(sol, peticion(aula=""), licencia_id="a7a7a7a7-0001-4000-8000-000000000001", serie=1, ahora_ms=AHORA)
        self.assertEqual(lic.aula, "Aula de la solicitud")

    def test_la_serie_debe_ser_positiva(self):
        sol = solicitud.leer_solicitud(NodoDePrueba().solicitud())
        with self.assertRaises(emision.ErrorDeEmision):
            emision.construir(sol, peticion(), licencia_id="a7a7a7a7-0001-4000-8000-000000000001", serie=0, ahora_ms=AHORA)

    def test_la_liberacion_pendiente_la_entiende_el_estado_del_nodo(self):
        """LIC-E-08: la licencia con la bandera opera como `liberacion_pendiente` con los días pedidos."""
        sol = solicitud.leer_solicitud(NodoDePrueba().solicitud())
        lic = emision.construir(sol, peticion(liberacion_dias=45), licencia_id="a7a7a7a7-0001-4000-8000-000000000001", serie=2, ahora_ms=AHORA)
        self.assertTrue(lic.liberacion_pendiente)
        e = estado.calcular(estado.Contexto(licencia=lic, ahora=AHORA, instalada_en=AHORA - 100 * DIA_MS, coincidencia=OK, licencia_instalada_en=AHORA))
        self.assertEqual((e.estado, e.dias_restantes), ("liberacion_pendiente", 45))
        despues = estado.calcular(estado.Contexto(licencia=lic, ahora=AHORA + 47 * DIA_MS, instalada_en=AHORA - 100 * DIA_MS, coincidencia=OK, licencia_instalada_en=AHORA))
        self.assertEqual(despues.estado, "degradada")

    def test_nombre_de_archivo(self):
        self.assertEqual(emision.nombre_de_archivo("Colegio San Martín", AHORA, 1), "colegio-san-martin-20261020-s1")
        self.assertEqual(emision.nombre_de_archivo("", AHORA, 2), "aula-20261020-s2")
        self.assertEqual(emision.nombre_de_archivo("¡¡¡ / \\ ???", AHORA, 3), "aula-20261020-s3")
        self.assertLessEqual(len(emision.nombre_de_archivo("x" * 300, AHORA, 1)), 40 + len("-20261020-s1"))


class DiferencialTests(unittest.TestCase):
    """LIC-E-01 · LIC-E-09: el lector del nodo lee exactamente lo que el emisor escribe, en cientos de licencias al azar."""

    def test_el_nodo_lee_lo_que_emite_el_emisor(self):
        azar = random.Random(2026)
        privada, publica = firma.par_nuevo()
        nodo = NodoDePrueba()
        sol = solicitud.leer_solicitud(nodo.solicitud())
        conocidas = sorted(catalogos.CAPACIDADES_LICENCIABLES)
        for i in range(400):
            normal = azar.choice([licencia.ILIMITADO, azar.randint(1, 500)])
            pico = licencia.ILIMITADO if normal == licencia.ILIMITADO else azar.randint(normal, normal + 500)
            capacidades = frozenset({"*"}) if azar.random() < 0.4 else frozenset(azar.sample(conocidas, azar.randint(1, len(conocidas))))
            p = peticion(
                aula=azar.choice(["", "Colegio San Martín", "Escuela Ñandú ✓", "A" * 200]), tipo=azar.choice(["produccion", "evaluacion"]), gracia_dias=azar.randint(0, 365),
                equipos=azar.choice([licencia.ILIMITADO, azar.randint(1, 5000)]), usuarios=azar.choice([licencia.ILIMITADO, azar.randint(1, 100000)]), normal=normal, pico=pico,
                capacidades=capacidades, hasta=date(2026, 10, 20) if azar.random() < 0.05 else date(2026, 11, 1 + azar.randint(0, 27)) if azar.random() < 0.3 else date(2027, 1, 1 + azar.randint(0, 27)),
                liberacion_dias=azar.choice([None, None, azar.randint(1, 365)]))
            esperada = emision.construir(sol, p, licencia_id=str(uuid.UUID(int=azar.getrandbits(128))), serie=azar.randint(1, 100000), ahora_ms=AHORA + azar.randint(0, 400) * 1000)
            datos = emision.firmar(esperada, "prueba-2026-1", privada)
            leida = emision.verificar_salida(datos, "prueba-2026-1", publica, esperada)
            self.assertEqual(leida.sha256, hashlib.sha256(datos).hexdigest())
            self.assertEqual(licencia.leer_texto(licencia.a_texto(datos), {"prueba-2026-1": publica}), leida)

    def test_un_archivo_distinto_de_lo_pedido_no_se_entrega(self):
        privada, publica = firma.par_nuevo()
        sol = solicitud.leer_solicitud(NodoDePrueba().solicitud())
        pedida = emision.construir(sol, peticion(equipos=55), licencia_id="a7a7a7a7-0001-4000-8000-000000000001", serie=1, ahora_ms=AHORA)
        otra = emision.construir(sol, peticion(equipos=99), licencia_id="a7a7a7a7-0001-4000-8000-000000000001", serie=1, ahora_ms=AHORA)
        with self.assertRaises(emision.ErrorDeEmision):
            emision.verificar_salida(emision.firmar(otra, "prueba-2026-1", privada), "prueba-2026-1", publica, pedida)

    def test_firmado_con_otra_llave_no_se_entrega(self):
        privada, _ = firma.par_nuevo()
        _, otra_publica = firma.par_nuevo()
        sol = solicitud.leer_solicitud(NodoDePrueba().solicitud())
        lic = emision.construir(sol, peticion(), licencia_id="a7a7a7a7-0001-4000-8000-000000000001", serie=1, ahora_ms=AHORA)
        with self.assertRaises(emision.ErrorDeEmision):
            emision.verificar_salida(emision.firmar(lic, "prueba-2026-1", privada), "prueba-2026-1", otra_publica, lic)

    def test_ninguna_mutacion_de_una_licencia_emitida_se_acepta(self):
        privada, publica = firma.par_nuevo()
        sol = solicitud.leer_solicitud(NodoDePrueba().solicitud())
        lic = emision.construir(sol, peticion(), licencia_id="a7a7a7a7-0001-4000-8000-000000000001", serie=1, ahora_ms=AHORA)
        datos = emision.firmar(lic, "prueba-2026-1", privada)
        azar = random.Random(7)
        claves = {"prueba-2026-1": publica}
        for _ in range(3000):
            malo = bytearray(datos)
            for _ in range(azar.randint(1, 3)):
                malo[azar.randrange(len(malo))] ^= 1 << azar.randrange(8)
            if bytes(malo) == datos:
                continue
            with self.assertRaises(Exception):
                licencia.leer(bytes(malo), claves)
        for corte in range(1, len(datos)):
            with self.assertRaises(Exception):
                licencia.leer(datos[:corte], claves)
        with self.assertRaises(Exception):
            licencia.leer(datos + b"\x00", claves)


class AdvertenciasTests(unittest.TestCase):
    def test_nivel_de_instalacion_se_avisa(self):
        nodo = NodoDePrueba(valores={huella.F_MACHINE_GUID: "To be filled by O.E.M.", huella.F_SMBIOS_UUID: "00000000-0000-0000-0000-000000000000"})
        sol = solicitud.leer_solicitud(nodo.solicitud())
        self.assertEqual(sol.nivel, huella.NIVEL_INSTALACION)
        avisos = emision.advertencias_de_solicitud(sol, AHORA, huella.NIVEL_INSTALACION)
        self.assertTrue(any("instalación" in a for a in avisos))

    def test_el_reloj_del_colegio_atrasado_o_adelantado_se_avisa(self):
        atrasada = solicitud.leer_solicitud(NodoDePrueba().solicitud(creada=AHORA - 400 * DIA_MS))
        adelantada = solicitud.leer_solicitud(NodoDePrueba().solicitud(creada=AHORA + 5 * DIA_MS))
        normal = solicitud.leer_solicitud(NodoDePrueba().solicitud(creada=AHORA - 2 * DIA_MS))
        self.assertTrue(any("atrasado" in a for a in emision.advertencias_de_solicitud(atrasada, AHORA, huella.NIVEL_INSTALACION)))
        self.assertTrue(any("adelantado" in a for a in emision.advertencias_de_solicitud(adelantada, AHORA, huella.NIVEL_INSTALACION)))
        self.assertEqual(emision.advertencias_de_solicitud(normal, AHORA, huella.NIVEL_INSTALACION), [])


if __name__ == "__main__":
    unittest.main()

"""
El núcleo puro de MOD-015 (Fase 1), sin Django: el sobre y sus validadores (P-03, R-13), el catálogo y el validador de nombres (P-04, BR-122), la máquina de reintentos (P-07), la
regla de purga con su tabla de verdad completa (P-08, BR-017), las anclas de la secuencia y del reloj (P-12, P-13), el corte (P-05) y los estados del nodo (P-09). Las invariantes van
por propiedades con semilla fija: la secuencia nunca baja, tras restaurar nunca se repite, el corte nunca pierde ni repite una marca previa.
"""
from __future__ import annotations

import random
from unittest import TestCase

from ..dominio import anclas, catalogo, corte, estado, purga, reintentos, sobre
from ..dominio import catalogos as cat
from ..dominio.errores import CargaInvalida, NombreInvalido, SobreIncompleto, TipoNoCatalogado

SEMILLA = 20261021


def _sobre(**extra) -> sobre.Sobre:
    base = dict(tipo="evaluacion.intento_abierto.v1", version=1, modulo="evaluacion", clase=cat.CLASE_APRENDIZAJE, sensibilidad=cat.S_PERSONAL_MENOR, agregado_tipo="Intento",
                agregado_id="i-1", carga={"intento_id": "i-1"}, creado_en=1_790_000_000_000, actor="u-1", dispositivo_id="hw-1", correlacion_id="c-1")
    base.update(extra)
    return sobre.armar(**base)


class SobreTests(TestCase):
    def test_el_sobre_lleva_los_doce_campos_y_ninguno_queda_vacio(self):
        s = _sobre()
        for campo in cat.CAMPOS_DEL_SOBRE:
            if campo != "secuencia":
                self.assertTrue(getattr(s, campo), campo)
        self.assertIsNone(s.secuencia)
        self.assertTrue(sobre.completo(s.con_secuencia(7)))
        self.assertEqual(s.con_secuencia(7).secuencia, 7)
        self.assertEqual(len(s.evento_id), 32)                     # UUID4 hexadecimal (P-02)

    def test_lo_que_falte_se_rellena_con_el_sistema_o_falla_si_no_se_puede(self):
        s = _sobre(actor="", dispositivo_id="", correlacion_id="")
        self.assertEqual((s.actor, s.dispositivo_id), (cat.SISTEMA, cat.DISPOSITIVO_NODO))
        self.assertEqual(len(s.correlacion_id), 32)
        for campo in ("tipo", "modulo", "agregado_tipo", "agregado_id"):
            with self.assertRaises(SobreIncompleto):
                _sobre(**{campo: ""})
        with self.assertRaises(SobreIncompleto):
            _sobre(clase="otra")
        with self.assertRaises(SobreIncompleto):
            _sobre(agregado_id="x" * 200)

    def test_r13_una_carga_con_credenciales_o_datos_personales_falla_en_pruebas_y_se_omite_en_produccion(self):
        for carga in ({"password": "x"}, {"intento_id": "i", "alumno": {"nombres": "Juan"}}, {"respuestas": [{"texto_respuesta": "…"}]}, {"Token": "abc"}, {"ruta": "C:\\x"}):
            with self.assertRaises(CargaInvalida, msg=carga):
                _sobre(carga=carga)
            s = _sobre(carga=carga, estricto=False)
            self.assertTrue(s.carga_omitida)
            self.assertEqual(s.carga, sobre.CARGA_OMITIDA)
        self.assertEqual(sobre.claves_prohibidas_en({"a": {"b": [{"email": 1}]}}), ["a.b[0].email"])
        self.assertEqual(sobre.revisar_carga({"intento_id": "i", "clave": "i|q|s", "sesion_ref": "s"}), [])        # `clave` (de deduplicación) no es una credencial

    def test_r13_la_carga_tiene_tope_y_debe_ser_un_objeto_json(self):
        self.assertEqual(sobre.revisar_carga("texto"), ["la carga debe ser un objeto JSON"])
        self.assertIn("pesa más", sobre.revisar_carga({"x": "a" * (cat.CARGA_MAX_BYTES + 1)})[0])
        with self.assertRaises(CargaInvalida):
            _sobre(carga={"x": "a" * (cat.CARGA_MAX_BYTES + 1)})
        self.assertEqual(sobre.revisar_carga({"a": 1, "b": [1, 2], "c": {"d": None}}), [])

    def test_nuevo_id_es_un_uuid_y_nuevo_evento_id_hexadecimal(self):
        self.assertEqual(len(sobre.nuevo_id()), 36)
        self.assertNotEqual(sobre.nuevo_evento_id(), sobre.nuevo_evento_id())


class CatalogoTests(TestCase):
    def test_br122_acepta_las_dos_formas_del_maestro(self):
        corto = catalogo.validar_nombre("evaluacion.intento_abierto.v1")
        self.assertEqual((corto.dominio, corto.objeto, corto.accion, corto.version, corto.base), ("evaluacion", None, "intento_abierto", 1, "evaluacion.intento_abierto"))
        largo = catalogo.validar_nombre("aula.sesion.iniciada.v2")
        self.assertEqual((largo.dominio, largo.objeto, largo.accion, largo.version), ("aula", "sesion", "iniciada", 2))
        self.assertTrue(catalogo.validar_nombre("aula.dispositivo.readmitido.v1").participio)
        self.assertTrue(catalogo.validar_nombre("identidad.sesion.abierta.v1").participio)          # participio irregular

    def test_br122_rechaza_lo_que_no_sigue_el_patron(self):
        for malo in ("Evaluacion.intento_abierto.v1", "evaluacion.intento_abierto", "evaluacion.intento_abierto.v0", "evaluacion..abierto.v1", "a.b.c.d.v1", "aula.sesión.iniciada.v1",
                     "aula.sesion.iniciada.V1", "aula.sesion-x.iniciada.v1", "", "aula.sesion.iniciada.v1.5"):
            with self.assertRaises(NombreInvalido, msg=malo):
                catalogo.validar_nombre(malo)
        with self.assertRaises(NombreInvalido):
            catalogo.validar_nombre("aula.proyeccion.alumno.v1")              # sin participio
        self.assertFalse(catalogo.analizar("aula.proyeccion.alumno.v1").participio)   # `analizar` lo informa sin fallar (es un tipo que ya existe)

    def test_el_catalogo_trae_todos_los_tipos_del_inventario_con_una_sola_clase_y_su_retencion(self):
        self.assertGreaterEqual(len(catalogo.TIPOS), 164 + len(cat.EVENTOS))
        for tipo in catalogo.TIPOS:
            d = catalogo.resolver(tipo)
            self.assertIn(d.clase, cat.CLASES, tipo)
            self.assertIn(d.sensibilidad, cat.SENSIBILIDADES, tipo)
            self.assertTrue(d.clave_dedup, tipo)
            self.assertEqual(d.inmutable, d.clase == cat.CLASE_AUDITORIA, tipo)
            self.assertTrue(d.retencion_dias is None or d.retencion_dias > 0, tipo)
            catalogo.analizar(tipo)                                  # el patrón se cumple en todos (el participio se lista en `hallazgos`)
        self.assertEqual(catalogo.resolver("auditoria.cadena_verificada.v1").retencion_dias, 5 * 365)
        self.assertIsNone(catalogo.resolver("identidad.usuario.creado.v1").retencion_dias)           # dominio: permanente
        self.assertEqual(catalogo.resolver("aula.sesion.iniciada.v1").retencion_dias, 30)
        self.assertEqual(catalogo.resolver("evaluacion.intento_abierto.v1", ciclo_meses=12).retencion_dias, 5 * 12 * 30)
        self.assertEqual(catalogo.resolver("evaluacion.intento_abierto.v1", ciclo_meses=6).retencion_dias, 5 * 6 * 30)
        self.assertEqual(catalogo.resolver("evaluacion.respuesta_registrada.v1").clave_dedup, ("intento_id", "pregunta_ref", "sesion_ref", "secuencia"))
        self.assertIsNone(catalogo.resolver("no.existe.v1"))
        with self.assertRaises(TipoNoCatalogado):
            catalogo.exigir("no.existe.v1")

    def test_los_nueve_eventos_del_maestro_y_las_extensiones_estan_y_cumplen_br122(self):
        self.assertEqual(len(cat.EVENTOS_DEL_MAESTRO), 9)
        for tipo in cat.EVENTOS:
            self.assertIn(tipo, catalogo.TIPOS)
            self.assertEqual(catalogo.resolver(tipo).modulo, cat.MODULO)
            self.assertTrue(catalogo.validar_nombre(tipo).participio, tipo)
            self.assertIn(catalogo.resolver(tipo).clase, (cat.CLASE_TECNICO, cat.CLASE_SINCRONIZACION))
        for tipo in cat.EVENTOS_DE_SINCRONIZACION:
            self.assertEqual(catalogo.resolver(tipo).clase, cat.CLASE_SINCRONIZACION)
        self.assertEqual(catalogo.resolver(cat.EV_SERVICIOS_INICIADOS).clase, cat.CLASE_TECNICO)
        self.assertTrue(set(cat.EVENTOS_EXTENSION).isdisjoint(cat.EVENTOS_DEL_MAESTRO))

    def test_los_hallazgos_listan_los_nombres_fuera_de_norma_sin_corregirlos(self):
        hallazgos = {h["tipo"]: h["problema"] for h in catalogo.hallazgos()}
        self.assertEqual(hallazgos.get("aula.proyeccion.alumno.v1"), "sin_participio")
        self.assertNotIn("evaluacion.intento_abierto.v1", hallazgos)
        self.assertIn("aula.proyeccion.alumno.v1", catalogo.TIPOS)                                    # sigue en el catálogo: no se toca lo ajeno

    def test_clase_por_prefijo_y_compatibilidad(self):
        self.assertEqual(catalogo.clase_por_prefijo("evaluacion.lo_que_sea.v1"), cat.CLASE_APRENDIZAJE)
        self.assertEqual(catalogo.clase_por_prefijo("desconocido.x.v1"), cat.CLASE_TECNICO)
        self.assertTrue(catalogo.compatible(1, 2))
        self.assertTrue(catalogo.compatible(2, 2))
        self.assertFalse(catalogo.compatible(3, 2))
        self.assertIn("evaluacion", catalogo.modulos())
        self.assertIn("evaluacion.intento_abierto.v1", catalogo.tipos_de("evaluacion"))


class ReintentosTests(TestCase):
    def test_la_espera_crece_al_doble_con_tope_y_sin_jitter_es_exacta(self):
        self.assertEqual([reintentos.espera_ms(i, 1000, 60000, 0) for i in range(1, 8)], [1000, 2000, 4000, 8000, 16000, 32000, 60000])
        self.assertEqual(reintentos.espera_ms(0, 1000, 60000, 0), 1000)

    def test_con_semilla_fija_el_jitter_es_determinista_y_queda_dentro_del_margen(self):
        a = [reintentos.espera_ms(i, 1000, 60000, 0.2, random.Random(SEMILLA)) for i in range(1, 6)]
        b = [reintentos.espera_ms(i, 1000, 60000, 0.2, random.Random(SEMILLA)) for i in range(1, 6)]
        self.assertEqual(a, b)
        for intento, valor in enumerate(a, 1):
            bruta = min(60000, 1000 * 2 ** (intento - 1))
            self.assertTrue(bruta * 0.8 <= valor <= bruta * 1.2, (intento, valor))

    def test_tras_fallo_cuenta_intentos_del_mismo_evento_y_aparta_al_maximo(self):
        rng = random.Random(SEMILLA)
        estado, apartar = reintentos.tras_fallo(reintentos.SIN_REINTENTO, 7, 1000, "RuntimeError: x", max_intentos=3, jitter=0, rng=rng)
        self.assertEqual((estado.secuencia, estado.intentos, estado.proximo_en, apartar), (7, 1, 2000, False))
        self.assertTrue(estado.activo)
        self.assertFalse(reintentos.toca_reintentar(estado, 1500))
        self.assertTrue(reintentos.toca_reintentar(estado, 2000))
        estado, apartar = reintentos.tras_fallo(estado, 7, 2000, "RuntimeError: x", max_intentos=3, jitter=0, rng=rng)
        self.assertEqual((estado.intentos, estado.proximo_en, apartar), (2, 4000, False))
        estado, apartar = reintentos.tras_fallo(estado, 7, 4000, "RuntimeError: x", max_intentos=3, jitter=0, rng=rng)
        self.assertEqual((estado, apartar), (reintentos.SIN_REINTENTO, True))
        # otro evento empieza de uno
        estado, _ = reintentos.tras_fallo(reintentos.EstadoDeReintento(7, 2, 0, ""), 8, 0, "x", max_intentos=5, jitter=0)
        self.assertEqual((estado.secuencia, estado.intentos), (8, 1))
        self.assertEqual(reintentos.tras_exito(estado, 8), reintentos.SIN_REINTENTO)
        self.assertEqual(reintentos.tras_exito(estado, 9), estado)
        self.assertTrue(reintentos.toca_reintentar(reintentos.SIN_REINTENTO, 0))

    def test_el_error_se_guarda_sin_datos_personales(self):
        sucio = "ValueError: el alumno 'Juan Pérez' <juan@colegio.edu> con documento 1023456789 en C:\\Users\\juan\\tarea.pdf \"dijo algo\""
        limpio = reintentos.sanear_error(sucio)
        for prohibido in ("Juan Pérez", "juan@colegio.edu", "1023456789", "C:\\Users", "dijo algo"):
            self.assertNotIn(prohibido, limpio)
        self.assertTrue(limpio.startswith("ValueError:"))
        self.assertLessEqual(len(reintentos.sanear_error("x" * 1000)), cat.MAX_ERROR)
        self.assertEqual(reintentos.describir_error(RuntimeError("falló 12345678")), "RuntimeError: falló [número]")


class PurgaTests(TestCase):
    def _evento(self, retencion=30, inmutable=False):
        return purga.Evento(secuencia=10, creado_en=0, retencion_dias=retencion, inmutable=inmutable)

    def test_br017_tabla_de_verdad_completa_de_las_cuatro_condiciones(self):
        """Sólo con las CUATRO a la vez es elegible: 16 combinaciones."""
        for bits in range(16):
            superado, respaldo, retencion, reconocido = ((bits >> i) & 1 == 1 for i in range(4))
            c = purga.evaluar(self._evento(), marcas=[10 if superado else 9], ahora=(31 if retencion else 29) * cat.DIA_MS, respaldo_cubre=lambda s, r=respaldo: r,
                              sincronizacion_habilitada=True, reconocida_hasta=10 if reconocido else 9, retencion_minima_dias=7)
            self.assertEqual(c.elegible, superado and respaldo and retencion and reconocido, bits)
            self.assertEqual(c.motivos(), tuple(m for m, ok in (("consumidor_pendiente", superado), ("sin_respaldo_verificado", respaldo), ("retencion_vigente", retencion),
                                                                 ("sin_reconocer", reconocido)) if not ok))

    def test_sin_sincronizacion_la_cuarta_condicion_se_cumple_sola_y_sin_consumidores_la_primera(self):
        c = purga.evaluar(self._evento(), marcas=[], ahora=40 * cat.DIA_MS, respaldo_cubre=lambda s: True, sincronizacion_habilitada=False)
        self.assertTrue(c.elegible)

    def test_la_retencion_minima_de_siete_dias_manda_sobre_una_retencion_menor_y_lo_permanente_nunca(self):
        c = purga.evaluar(purga.Evento(1, 0, 1), marcas=[], ahora=5 * cat.DIA_MS, respaldo_cubre=lambda s: True)
        self.assertFalse(c.retencion_cumplida)
        c = purga.evaluar(purga.Evento(1, 0, 1), marcas=[], ahora=7 * cat.DIA_MS, respaldo_cubre=lambda s: True)
        self.assertTrue(c.retencion_cumplida)
        c = purga.evaluar(purga.Evento(1, 0, None), marcas=[], ahora=10 ** 15, respaldo_cubre=lambda s: True)
        self.assertFalse(c.elegible)
        c = purga.evaluar(self._evento(inmutable=True), marcas=[], ahora=10 ** 15, respaldo_cubre=lambda s: True)
        self.assertFalse(c.elegible)
        self.assertIn("inmutable", c.motivos())

    def test_br019_el_lote_es_contiguo_desde_la_mas_baja_y_se_detiene_en_la_primera_no_elegible(self):
        eventos = [purga.Evento(s, 0, 1) for s in (1, 2, 3, 4, 5)]
        condiciones = dict(marcas=[3], ahora=40 * cat.DIA_MS, respaldo_cubre=lambda s: True)        # el consumidor sólo superó hasta la 3
        self.assertEqual(purga.lote_purgable(eventos, **condiciones), [1, 2, 3])
        condiciones = dict(marcas=[5], ahora=40 * cat.DIA_MS, respaldo_cubre=lambda s: s != 2)      # la 2 no está respaldada: la 3, 4 y 5 esperan (sin huecos)
        self.assertEqual(purga.lote_purgable(eventos, **condiciones), [1])
        self.assertEqual(purga.lote_purgable([], **condiciones), [])

    def test_br018_un_consumidor_rezagado_bloquea_y_sobre_el_limite_se_avisa(self):
        self.assertEqual(purga.bloquea_la_purga(10, 10, 5), (False, False))
        self.assertEqual(purga.bloquea_la_purga(8, 10, 5), (True, False))
        self.assertEqual(purga.bloquea_la_purga(0, 10, 5), (True, True))


class AnclasTests(TestCase):
    def test_al_arrancar_los_cuatro_casos(self):
        normal = anclas.al_arrancar(100, 90, margen=10)
        self.assertEqual((normal.restauracion, normal.contador_minimo), (False, 0))
        restaurada = anclas.al_arrancar(50, 90, margen=10)
        self.assertEqual((restaurada.restauracion, restaurada.sin_ancla, restaurada.contador_minimo), (True, False, 100))
        nuevo_equipo = anclas.al_arrancar(50, None, margen=10)
        self.assertEqual((nuevo_equipo.restauracion, nuevo_equipo.sin_ancla, nuevo_equipo.contador_minimo), (True, True, 60))
        instalacion = anclas.al_arrancar(0, None, margen=10)
        self.assertEqual((instalacion.restauracion, instalacion.contador_minimo), (False, 0))

    def test_propiedad_tras_restaurar_nunca_se_repite_una_secuencia(self):
        """Con semilla fija: se emiten secuencias, el ancla se refresca por lotes (y por eso va por detrás), se restaura una copia vieja y el contador salta: ninguna secuencia
        nueva coincide con una emitida antes, siempre que el margen cubra lo emitido entre refrescos."""
        rng = random.Random(SEMILLA)
        for _ in range(200):
            cada_eventos = rng.randint(1, 1000)
            margen = cada_eventos + rng.randint(0, 50)
            ancla = anclas.Ancla()
            emitidas = 0
            for _ in range(rng.randint(1, 50)):
                emitidas += rng.randint(1, 300)
                if anclas.hay_que_refrescar(ancla, emitidas, 0, cada_ms=10 ** 12, cada_eventos=cada_eventos):
                    ancla = anclas.ancla_siguiente(ancla, emitidas, 0, 0)
            self.assertLessEqual(emitidas - ancla.secuencia, cada_eventos + 300)
            copia_vieja = rng.randint(0, emitidas)
            decision = anclas.al_arrancar(copia_vieja, ancla.secuencia, margen=margen + 300)
            if copia_vieja < ancla.secuencia:
                self.assertTrue(decision.restauracion)
                self.assertGreater(decision.contador_minimo, emitidas)          # nada de lo emitido se repite
            else:
                self.assertGreaterEqual(copia_vieja, ancla.secuencia)

    def test_el_ancla_se_refresca_por_tiempo_o_por_eventos_y_nunca_baja(self):
        a = anclas.Ancla(100, 5, 1000)
        self.assertFalse(anclas.hay_que_refrescar(a, 100, 1500, cada_ms=5000, cada_eventos=1000))
        self.assertFalse(anclas.hay_que_refrescar(a, 600, 1500, cada_ms=5000, cada_eventos=1000))
        self.assertTrue(anclas.hay_que_refrescar(a, 1100, 1500, cada_ms=5000, cada_eventos=1000))         # por eventos
        self.assertTrue(anclas.hay_que_refrescar(a, 101, 6000, cada_ms=5000, cada_eventos=1000))          # por tiempo
        self.assertFalse(anclas.hay_que_refrescar(a, 100, 60000, cada_ms=5000, cada_eventos=1000))        # nada nuevo que anclar
        self.assertFalse(anclas.hay_que_refrescar(a, 50, 60000, cada_ms=5000, cada_eventos=1000))         # nunca un valor menor
        self.assertEqual(anclas.ancla_siguiente(a, 50, 1, 2000), anclas.Ancla(100, 5, 2000))

    def test_el_reloj_es_el_maximo_con_la_marca_alta_y_declara_el_retroceso(self):
        lectura = anclas.leer_reloj(1000, 500, tolerancia_ms=10, restringe_ms=100)
        self.assertEqual((lectura.ahora, lectura.atras_ms, lectura.retroceso, lectura.restringe), (1000, 0, False, False))
        lectura = anclas.leer_reloj(400, 500, tolerancia_ms=10, restringe_ms=100)
        self.assertEqual((lectura.ahora, lectura.atras_ms, lectura.retroceso, lectura.restringe), (500, 100, True, False))
        lectura = anclas.leer_reloj(100, 500, tolerancia_ms=10, restringe_ms=100)
        self.assertEqual((lectura.ahora, lectura.retroceso, lectura.restringe), (500, True, True))
        self.assertEqual(anclas.marca_siguiente(500, 400), 500)
        self.assertEqual(anclas.marca_siguiente(500, 600), 600)

    def test_propiedad_la_marca_alta_nunca_baja(self):
        rng = random.Random(SEMILLA)
        marca = 0
        for _ in range(5000):
            reloj = rng.randint(0, 10 ** 9)
            nueva = anclas.marca_siguiente(marca, anclas.leer_reloj(reloj, marca).ahora)
            self.assertGreaterEqual(nueva, marca)
            marca = nueva


def _legado(n: int, modulo: str = "device_manager") -> list[dict]:
    return [{"secuencia": i, "tipo": "dispositivo.registrado.v1", "agregado_tipo": "D", "agregado_id": str(i), "carga": {"i": i}, "creado_en": i} for i in range(1, n + 1)]


def _lector(filas: list[dict]):
    def leer(desde, limite, tipos, hasta):
        validas = [f for f in filas if desde < f["secuencia"] <= hasta]
        lote = validas[:limite]
        return [dict(f) for f in lote], (lote[-1]["secuencia"] if len(lote) >= limite else hasta)
    return leer


def _nuevo(filas: list[dict]):
    def leer(desde, limite):
        validas = [f for f in filas if f["secuencia"] > desde]
        lote = validas[:limite]
        return [dict(f) for f in lote], (lote[-1]["secuencia"] if len(lote) >= limite else (filas[-1]["secuencia"] if filas else desde))
    return leer


class CorteTests(TestCase):
    def test_el_contador_salta_a_la_ultima_legada_y_nunca_baja(self):
        self.assertEqual(corte.contador_tras_corte(5, 30), 30)
        self.assertEqual(corte.contador_tras_corte(40, 30), 40)
        self.assertEqual(corte.contador_tras_corte(0, 0), 0)

    def test_planear(self):
        self.assertEqual(corte.planear(0, 10, None), corte.PlanDeLectura(None, (0, 10)))
        c = corte.Corte("m", 30, 0)
        self.assertEqual(corte.planear(0, 10, c), corte.PlanDeLectura((0, 10, 30), (30, 10)))
        self.assertEqual(corte.planear(25, 10, c), corte.PlanDeLectura((25, 10, 30), (30, 10)))
        self.assertEqual(corte.planear(30, 10, c), corte.PlanDeLectura(None, (30, 10)))
        self.assertEqual(corte.planear(31, 10, c), corte.PlanDeLectura(None, (31, 10)))

    def test_fusionar_sirve_el_legado_primero_y_completa_con_lo_nuevo(self):
        legados = _legado(30)
        nuevos = [{"secuencia": s, "tipo": "dispositivo.registrado.v1", "carga": {}} for s in (31, 32, 33)]
        c = corte.Corte("device_manager", 30, 0)
        plan = corte.planear(25, 10, c)
        leidos, hasta_l = _lector(legados)(*plan.legado[:2], None, plan.legado[2])
        eventos, hasta = corte.fusionar(plan, leidos, hasta_l, _nuevo(nuevos))
        self.assertEqual([e["secuencia"] for e in eventos], [26, 27, 28, 29, 30, 31, 32, 33])
        self.assertEqual(hasta, 33)
        plan = corte.planear(0, 7, c)
        leidos, hasta_l = _lector(legados)(*plan.legado[:2], None, plan.legado[2])
        eventos, hasta = corte.fusionar(plan, leidos, hasta_l, _nuevo(nuevos))
        self.assertEqual(([e["secuencia"] for e in eventos], hasta), ([1, 2, 3, 4, 5, 6, 7], 7))

    def test_propiedad_una_marca_previa_al_corte_no_pierde_ni_repite_nada_y_marca_cero_reproduce_todo(self):
        rng = random.Random(SEMILLA)
        for _ in range(150):
            n_legado, n_nuevo, limite = rng.randint(0, 40), rng.randint(0, 40), rng.randint(1, 12)
            legados = _legado(n_legado)
            c = corte.Corte("device_manager", n_legado, 0)
            contador = corte.contador_tras_corte(rng.randint(0, 5), n_legado)
            nuevos = [{"secuencia": contador + i, "tipo": "dispositivo.registrado.v1", "carga": {}} for i in range(1, n_nuevo + 1)]
            todos = [f["secuencia"] for f in legados] + [f["secuencia"] for f in nuevos]
            marca = rng.randint(0, max(0, n_legado + n_nuevo + 3))
            vistos: list[int] = []
            m = marca
            for _ in range(100):
                plan = corte.planear(m, limite, c)
                if plan.legado is not None:
                    leidos, hasta_l = _lector(legados)(*plan.legado[:2], None, plan.legado[2])
                    eventos, hasta = corte.fusionar(plan, leidos, hasta_l, _nuevo(nuevos))
                else:
                    eventos, hasta = _nuevo(nuevos)(*plan.nuevo)
                vistos += [e["secuencia"] for e in eventos]
                if hasta <= m:
                    break
                m = hasta
            esperados = [s for s in todos if s > marca]
            self.assertEqual(vistos, esperados, (n_legado, n_nuevo, limite, marca))         # ni se pierde, ni se repite, ni se desordena
        self.assertTrue(corte.marca_vigente(0, corte.Corte("x", 10, 0)))


class EstadoTests(TestCase):
    def test_el_orden_de_los_estados_manda(self):
        self.assertEqual(estado.evaluar(estado.LecturaDeSalud(detenido=True, arrancando=True)).estado, cat.DETENIDO)
        self.assertEqual(estado.evaluar(estado.LecturaDeSalud(arrancando=True, recuperando=True)).estado, cat.ARRANCANDO)
        self.assertEqual(estado.evaluar(estado.LecturaDeSalud(recuperando=True, transaccion_inmediata=False)).estado, cat.EN_RECUPERACION)
        self.assertEqual(estado.evaluar(estado.LecturaDeSalud()).estado, cat.OPERATIVO)
        r = estado.evaluar(estado.LecturaDeSalud(transaccion_inmediata=False, base_integra=False, wal_bytes=10 ** 10, consumidores_nucleo_suspendidos=("x",), retroceso_ms=10 ** 12,
                                                 disco_libre_bytes=1, disco_total_bytes=10 ** 12))
        self.assertEqual(r.estado, cat.RESTRINGIDO)
        self.assertEqual(set(r.motivos), set(cat.MOTIVOS_RESTRICCION))
        self.assertTrue(r.restringido)

    def test_q_n1_umbrales_del_disco_y_del_wal_con_histeresis(self):
        u = estado.Umbrales(disco_min_bytes=1000, disco_min_pct=5.0, wal_max_bytes=100, histeresis=1.25)
        self.assertEqual(estado.evaluar(estado.LecturaDeSalud(disco_libre_bytes=999, disco_total_bytes=10_000), u).estado, cat.RESTRINGIDO)
        self.assertEqual(estado.evaluar(estado.LecturaDeSalud(disco_libre_bytes=1000, disco_total_bytes=10_000), u).estado, cat.OPERATIVO)
        self.assertEqual(estado.evaluar(estado.LecturaDeSalud(disco_libre_bytes=4000, disco_total_bytes=100_000), u).estado, cat.RESTRINGIDO)    # 4 % < 5 %
        # histéresis: ya restringido, 1100 libres no bastan (hace falta 1250)
        self.assertEqual(estado.evaluar(estado.LecturaDeSalud(disco_libre_bytes=1100, disco_total_bytes=10_000), u, estado_previo=cat.RESTRINGIDO).estado, cat.RESTRINGIDO)
        self.assertEqual(estado.evaluar(estado.LecturaDeSalud(disco_libre_bytes=1300, disco_total_bytes=10_000), u, estado_previo=cat.RESTRINGIDO).estado, cat.OPERATIVO)
        self.assertEqual(estado.evaluar(estado.LecturaDeSalud(wal_bytes=101), u).estado, cat.RESTRINGIDO)
        self.assertEqual(estado.evaluar(estado.LecturaDeSalud(wal_bytes=90), u, estado_previo=cat.RESTRINGIDO).estado, cat.RESTRINGIDO)         # hasta bajar de 80
        self.assertEqual(estado.evaluar(estado.LecturaDeSalud(wal_bytes=79), u, estado_previo=cat.RESTRINGIDO).estado, cat.OPERATIVO)
        self.assertEqual(estado.evaluar(estado.LecturaDeSalud(disco_libre_bytes=None), u).estado, cat.OPERATIVO)                                 # no medido no restringe

    def test_r01_las_rutas_nucleo(self):
        for ruta in ("/health/", "/api/acceso/sesiones/", "/api/aula/sesiones/x/", "/api/evaluacion/intentos/1/respuestas/", "/api/modo-estudio/sync/", "/api/dispositivos/latido/",
                     "/api/logs/clientes/", "/api/nodo/estado/", "/api/m/abc/aula/", "/api/medios/x"):
            self.assertTrue(estado.es_ruta_nucleo(ruta), ruta)
        for ruta in ("/api/reportes/clases/", "/api/acceso/usuarios/importar/", "/api/gradebook/libro/", "/api/search/", "/api/licencia/activar/", ""):
            self.assertFalse(estado.es_ruta_nucleo(ruta), ruta)

    def test_estado_del_consumidor_y_el_peor(self):
        self.assertEqual(estado.estado_del_consumidor(10, 10), (cat.C_AL_DIA, 0))
        self.assertEqual(estado.estado_del_consumidor(5, 10), (cat.C_REZAGADO, 5))
        self.assertEqual(estado.estado_del_consumidor(0, 10, limite_rezago=5), (cat.C_SUSPENDIDO, 10))
        self.assertEqual(estado.estado_del_consumidor(10, 10, reconstruyendose=True), (cat.C_RECONSTRUYENDOSE, 0))
        self.assertEqual(estado.peor([cat.C_AL_DIA, cat.C_REZAGADO]), cat.C_REZAGADO)
        self.assertEqual(estado.peor([cat.C_SUSPENDIDO, cat.C_RECONSTRUYENDOSE]), cat.C_SUSPENDIDO)
        self.assertEqual(estado.peor([]), cat.C_AL_DIA)

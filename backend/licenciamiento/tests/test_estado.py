"""
La máquina de estados (P-05) completa: la tabla ESTADOS × RELOJ × GRACIA, la histéresis, los avisos escalonados, el reloj confiable (P-06), el cupo (P-08), el entorno sin puerta
trasera (P-12) y la clasificación de rutas (R-01). Todo puro: el «ahora» es el que la prueba dice.
"""
from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from licenciamiento.dominio import catalogos as cat
from licenciamiento.dominio import cupo, entorno, estado, reloj, rutas
from licenciamiento.dominio.huella import Coincidencia
from licenciamiento.dominio.licencia import ILIMITADO, Limites
from licenciamiento.dominio.politica import DIA_MS, HORA_MS, POLITICA_PROVISIONAL

from .emisor import AHORA, licencia_de_ejemplo

LIC = licencia_de_ejemplo()
V = LIC.vence                                    # fin de la vigencia
GRACIA = LIC.gracia_dias * DIA_MS


def ctx(**cambios) -> estado.Contexto:
    base = dict(licencia=LIC, ahora=AHORA, instalada_en=AHORA - 5 * DIA_MS, coincidencia=Coincidencia(3, 5, 5, True, False, "hardware"))
    base.update(cambios)
    return estado.Contexto(**base)


def calcular(**cambios) -> estado.Estado:
    return estado.calcular(ctx(**cambios))


TODAS = frozenset(cat.CAPACIDADES_LICENCIABLES)
NINGUNA: frozenset[str] = frozenset()


class TablaDeEstadosTests(SimpleTestCase):
    """Cada fila: (descripción, cambios al contexto, estado, motivo, días restantes, capacidades, banderas)."""

    FILAS = [
        # ---------------------------------------------------------------- sin licencia: la ventana de evaluación desde el primer arranque (P-14)
        ("sin licencia, 5 días después de instalar", dict(licencia=None, coincidencia=None), cat.SIN_LICENCIA, cat.M_EVALUACION, 25, TODAS, set()),
        ("sin licencia, el último día", dict(licencia=None, coincidencia=None, instalada_en=AHORA - 29 * DIA_MS - HORA_MS), cat.SIN_LICENCIA, cat.M_EVALUACION, 1, TODAS, set()),
        ("sin licencia, queda una hora de ventana: sigue evaluando", dict(licencia=None, coincidencia=None, instalada_en=AHORA - 30 * DIA_MS + HORA_MS), cat.SIN_LICENCIA, cat.M_EVALUACION, 1, TODAS, set()),
        ("sin licencia, se cumplen los 30 días exactos: degrada en ese instante (sin histéresis, Q-L16)", dict(licencia=None, coincidencia=None, instalada_en=AHORA - 30 * DIA_MS),
         cat.DEGRADADA, cat.M_EVALUACION_VENCIDA, 0, NINGUNA, set()),
        ("sin licencia, pasó la ventana", dict(licencia=None, coincidencia=None, instalada_en=AHORA - 30 * DIA_MS - 25 * HORA_MS), cat.DEGRADADA, cat.M_EVALUACION_VENCIDA, 0, NINGUNA, set()),
        ("licencia que todavía no empieza: vale la evaluación", dict(licencia=licencia_de_ejemplo(desde=AHORA + 10 * DIA_MS, vence=AHORA + 400 * DIA_MS, emitida=AHORA - DIA_MS)),
         cat.SIN_LICENCIA, cat.M_AUN_NO_VIGENTE, 25, TODAS, set()),
        # La MISMA tolerancia (un día) con la que `Instalar` acepta el archivo: lo aceptado rige desde ya, con la evaluación vencida o sin ella (revisión independiente, BUG-1)
        ("licencia que empieza en 12 h: ya rige aunque la evaluación haya vencido", dict(licencia=licencia_de_ejemplo(desde=AHORA + 12 * HORA_MS, vence=AHORA + 400 * DIA_MS, emitida=AHORA - DIA_MS),
                                                                                       instalada_en=AHORA - 90 * DIA_MS), cat.ACTIVA, cat.M_VIGENTE, 400, TODAS, set()),
        ("licencia que empieza justo dentro del día de tolerancia: ya rige", dict(licencia=licencia_de_ejemplo(desde=AHORA + DIA_MS, vence=AHORA + 400 * DIA_MS, emitida=AHORA - DIA_MS),
                                                                                  instalada_en=AHORA - 90 * DIA_MS), cat.ACTIVA, cat.M_VIGENTE, 400, TODAS, set()),
        ("licencia que empieza pasada la tolerancia: todavía no, y con la evaluación vencida el nodo está degradado", dict(licencia=licencia_de_ejemplo(desde=AHORA + DIA_MS + HORA_MS, vence=AHORA + 400 * DIA_MS,
                                                                                                                       emitida=AHORA - DIA_MS), instalada_en=AHORA - 90 * DIA_MS),
         cat.DEGRADADA, cat.M_EVALUACION_VENCIDA, 0, NINGUNA, set()),
        # ---------------------------------------------------------------- vigente
        ("licencia vigente", dict(), cat.ACTIVA, cat.M_VIGENTE, 335, TODAS, set()),
        ("vence mañana", dict(ahora=V - DIA_MS + HORA_MS), cat.ACTIVA, cat.M_VIGENTE, 1, TODAS, set()),
        ("vence en una hora: sigue activa", dict(ahora=V - HORA_MS), cat.ACTIVA, cat.M_VIGENTE, 1, TODAS, set()),
        ("justo en el instante del vencimiento", dict(ahora=V), cat.ACTIVA, cat.M_VIGENTE, 0, TODAS, set()),
        # ---------------------------------------------------------------- venció: gracia
        ("venció hace una hora: gracia con los 30 días completos", dict(ahora=V + HORA_MS), cat.EN_GRACIA, cat.M_VENCIDA, 30, TODAS, set()),
        ("venció hace 29 días: queda 1 de gracia", dict(ahora=V + 29 * DIA_MS), cat.EN_GRACIA, cat.M_VENCIDA, 1, TODAS, set()),
        ("queda una hora de gracia: sigue en gracia", dict(ahora=V + GRACIA - HORA_MS), cat.EN_GRACIA, cat.M_VENCIDA, 1, TODAS, set()),
        ("se cumplen los 30 días de gracia EXACTOS: degrada en ese instante (Q-L16: sin histéresis, sin día de más)", dict(ahora=V + GRACIA), cat.DEGRADADA, cat.M_VENCIDA, 0, NINGUNA, set()),
        ("pasó la gracia: degradada", dict(ahora=V + GRACIA + 25 * HORA_MS), cat.DEGRADADA, cat.M_VENCIDA, 0, NINGUNA, set()),
        ("degradada mucho tiempo después: sigue igual (nunca se corta nada más)", dict(ahora=V + 400 * DIA_MS), cat.DEGRADADA, cat.M_VENCIDA, 0, NINGUNA, set()),
        # ---------------------------------------------------------------- el reloj
        ("RETROCESO: el reloj bajó pero el vencimiento se mide contra la marca alta; se avisa", dict(reloj_retroceso=True), cat.ACTIVA, cat.M_VIGENTE, 335, TODAS, {cat.B_RELOJ_SOSPECHOSO}),
        ("retroceso con la licencia ya vencida: NO aplaza la degradación", dict(ahora=V + GRACIA + 25 * HORA_MS, reloj_retroceso=True), cat.DEGRADADA, cat.M_VENCIDA, 0, NINGUNA, {cat.B_RELOJ_SOSPECHOSO}),
        # Q-L13 · FECHA ADELANTADA: `ahora` ya es la hora confiable (nunca la del salto); la bandera avisa y no cambia ni aplaza ninguna transición
        ("FECHA ADELANTADA con la licencia vigente: sólo la bandera, nada se pone en pausa", dict(reloj_adelanto_ms=10 * DIA_MS), cat.ACTIVA, cat.M_VIGENTE, 335, TODAS, {cat.B_RELOJ_ADELANTADO}),
        ("fecha adelantada con la gracia vigente: sigue en gracia (no vence ni degrada por el salto)", dict(ahora=V + GRACIA - HORA_MS, reloj_adelanto_ms=400 * DIA_MS),
         cat.EN_GRACIA, cat.M_VENCIDA, 1, TODAS, {cat.B_RELOJ_ADELANTADO}),
        ("fecha adelantada y la gracia de verdad agotada: degrada igual, la bandera no aplaza nada (no es una palanca)", dict(ahora=V + GRACIA, reloj_adelanto_ms=2 * DIA_MS),
         cat.DEGRADADA, cat.M_VENCIDA, 0, NINGUNA, {cat.B_RELOJ_ADELANTADO}),
        ("fecha adelantada sin licencia: la evaluación sigue donde iba", dict(licencia=None, coincidencia=None, instalada_en=AHORA - 5 * DIA_MS, reloj_adelanto_ms=3000 * DIA_MS),
         cat.SIN_LICENCIA, cat.M_EVALUACION, 25, TODAS, {cat.B_RELOJ_ADELANTADO}),
        ("fecha adelantada y reloj atrasado a la vez: las dos banderas", dict(reloj_retroceso=True, reloj_adelanto_ms=DIA_MS), cat.ACTIVA, cat.M_VIGENTE, 335, TODAS,
         {cat.B_RELOJ_SOSPECHOSO, cat.B_RELOJ_ADELANTADO}),
        # ---------------------------------------------------------------- la huella
        ("huella parcial (cambió un componente): sigue activa y avisa", dict(coincidencia=Coincidencia(3, 5, 4, True, True, "hardware")), cat.ACTIVA, cat.M_VIGENTE, 335, TODAS, {cat.B_HUELLA_PARCIAL}),
        ("otro equipo, primera vez que se ve: gracia completa", dict(coincidencia=Coincidencia(3, 5, 1, False, False, "hardware")), cat.EN_GRACIA, cat.M_HUELLA_DISTINTA, 30, TODAS, set()),
        ("otro equipo desde hace 10 días: quedan 20", dict(coincidencia=Coincidencia(3, 5, 1, False, False, "hardware"), huella_distinta_desde=AHORA - 10 * DIA_MS),
         cat.EN_GRACIA, cat.M_HUELLA_DISTINTA, 20, TODAS, set()),
        ("otro equipo con la gracia agotada: degradada (TST-060: se arregla reactivando o liberando, no con un bloqueo)",
         dict(coincidencia=Coincidencia(3, 5, 1, False, False, "hardware"), huella_distinta_desde=AHORA - 31 * DIA_MS - 2 * HORA_MS), cat.DEGRADADA, cat.M_HUELLA_DISTINTA, 0, NINGUNA, set()),
        # ---------------------------------------------------------------- liberación pendiente (JRN-020, MSG-063)
        ("liberación pendiente: «puedes seguir dando clase 11 días»", dict(licencia=licencia_de_ejemplo(liberacion_pendiente=True, liberacion_dias=14), licencia_instalada_en=AHORA - 3 * DIA_MS),
         cat.LIBERACION_PENDIENTE, cat.M_LIBERACION_PENDIENTE, 11, TODAS, set()),
        ("liberación pendiente sin confirmar al acabar su plazo: degradada", dict(licencia=licencia_de_ejemplo(liberacion_pendiente=True, liberacion_dias=14),
                                                                                  licencia_instalada_en=AHORA - 15 * DIA_MS - 2 * HORA_MS), cat.DEGRADADA, cat.M_LIBERACION_NO_CONFIRMADA, 0, NINGUNA, set()),
        ("liberación pendiente: el plazo nunca pasa del vencimiento", dict(licencia=licencia_de_ejemplo(liberacion_pendiente=True, liberacion_dias=365, vence=AHORA + 5 * DIA_MS),
                                                                         licencia_instalada_en=AHORA - DIA_MS), cat.LIBERACION_PENDIENTE, cat.M_LIBERACION_PENDIENTE, 5, TODAS, set()),
        # ---------------------------------------------------------------- reactivada (FUN-194)
        ("reactivada hace un día", dict(reactivada_en=AHORA - DIA_MS), cat.REACTIVADA, cat.M_REACTIVADA, 335, TODAS, set()),
        ("reactivada hace cuatro días: ya es activa", dict(reactivada_en=AHORA - 4 * DIA_MS), cat.ACTIVA, cat.M_VIGENTE, 335, TODAS, set()),
        # ---------------------------------------------------------------- módulos y bandera de integridad
        ("la licencia sólo habilita reportes", dict(licencia=licencia_de_ejemplo(capacidades=frozenset({"reportes"}))), cat.ACTIVA, cat.M_VIGENTE, 335, frozenset({"reportes"}), set()),
        ("la integridad alterada es sólo una bandera: no cambia el estado", dict(integridad_alterada=True), cat.ACTIVA, cat.M_VIGENTE, 335, TODAS, {cat.B_INTEGRIDAD_ALTERADA}),
        ("licencia de evaluación vencida igual que cualquiera", dict(licencia=licencia_de_ejemplo(tipo="evaluacion", vence=AHORA - HORA_MS)), cat.EN_GRACIA, cat.M_VENCIDA, 30, TODAS, set()),
    ]

    def test_la_tabla_completa(self):
        for descripcion, cambios, nombre, motivo, dias, capacidades, banderas in self.FILAS:
            with self.subTest(descripcion):
                e = calcular(**cambios)
                self.assertEqual((e.estado, e.motivo, e.dias_restantes, e.capacidades, set(e.banderas)), (nombre, motivo, dias, capacidades, banderas))

    def test_el_estado_depende_solo_del_contexto_y_es_determinista(self):
        for _, cambios, *_ in self.FILAS:
            self.assertEqual(calcular(**cambios), calcular(**cambios))

    def test_la_degradacion_nunca_toca_el_nucleo_porque_el_nucleo_no_es_una_capacidad(self):
        """Lo que la licencia puede apagar es la lista cerrada de capacidades licenciables; lo demás no es una capacidad."""
        for nombre in ("clase", "aula", "evaluacion", "modo_estudio", "login", "latido", "expediente", "calificaciones", "bitacora", "licencia", "respaldo", "actualizacion"):
            self.assertNotIn(nombre, cat.CAPACIDADES_LICENCIABLES)
        e = calcular(ahora=V + 400 * DIA_MS)
        self.assertTrue(e.restringe)
        self.assertEqual(e.capacidades, NINGUNA)

    def test_los_limites_vienen_de_la_licencia_o_de_la_evaluacion(self):
        self.assertEqual(calcular().limites, LIC.limites)
        self.assertEqual(calcular(licencia=None, coincidencia=None).limites, POLITICA_PROVISIONAL.limites_evaluacion)
        self.assertEqual(calcular(ahora=V + 400 * DIA_MS).limites, LIC.limites)           # degradada no cambia lo que ya se tiene: sólo se apagan módulos

    def test_ninguna_combinacion_produce_un_estado_fuera_del_catalogo(self):
        for ahora in (V - 400 * DIA_MS, V - DIA_MS, V, V + DIA_MS, V + GRACIA, V + GRACIA + 2 * DIA_MS, V + 3000 * DIA_MS):
            for licencia in (None, LIC):
                for coincidencia in (None, Coincidencia(3, 5, 0, False, False, "hardware"), Coincidencia(3, 5, 5, True, False, "hardware")):
                    for retroceso in (False, True):
                        for adelanto in (0, HORA_MS, 100 * DIA_MS):
                            e = calcular(licencia=licencia, ahora=ahora, coincidencia=coincidencia, reloj_retroceso=retroceso, reloj_adelanto_ms=adelanto)
                            self.assertIn(e.estado, cat.ESTADOS)
                            self.assertIn(e.motivo, cat.MOTIVOS)
                            self.assertTrue(e.capacidades <= TODAS)


class AvisosTests(SimpleTestCase):
    def avisos(self, e, consumo=None):
        return estado.avisos(e, consumo)

    def test_activa_lejos_del_vencimiento_no_avisa_nada(self):
        self.assertEqual(self.avisos(calcular()), [])

    def test_los_umbrales_escalonados_30_14_7_3_1(self):
        for dias, umbral in ((40, None), (31, None), (30, 30), (20, 30), (14, 14), (10, 14), (7, 7), (4, 7), (3, 3), (2, 3), (1, 1), (0, 1)):
            self.assertEqual(estado.umbral_de_aviso(dias), umbral, dias)
        e = calcular(ahora=V - 12 * DIA_MS + HORA_MS)
        self.assertEqual(self.avisos(e), [{"codigo": "por_vencer", "dias": 12, "umbral": 14}])

    def test_gracia_degradada_y_liberacion_avisan_con_sus_dias(self):
        self.assertEqual(self.avisos(calcular(ahora=V + 5 * DIA_MS))[0], {"codigo": "gracia", "motivo": "vencida", "dias": 25})
        self.assertEqual(self.avisos(calcular(ahora=V + 400 * DIA_MS))[0], {"codigo": "degradada", "motivo": "vencida"})
        e = calcular(licencia=licencia_de_ejemplo(liberacion_pendiente=True, liberacion_dias=14), licencia_instalada_en=AHORA - 3 * DIA_MS)
        self.assertEqual(self.avisos(e)[0], {"codigo": "liberacion_pendiente", "dias": 11})

    def test_la_evaluacion_avisa_desde_el_primer_dia_y_marca_cuando_es_urgente(self):
        """P-14 y H-10: el administrador se entera desde que el nodo abre su ventana, no sólo en la última semana."""
        self.assertEqual(self.avisos(calcular(licencia=None, coincidencia=None, instalada_en=AHORA - 5 * DIA_MS)), [{"codigo": "evaluacion", "dias": 25, "urgente": False}])
        self.assertEqual(self.avisos(calcular(licencia=None, coincidencia=None, instalada_en=AHORA - 24 * DIA_MS)), [{"codigo": "evaluacion", "dias": 6, "urgente": True}])
        self.assertEqual(self.avisos(calcular(licencia=None, coincidencia=None, instalada_en=AHORA - 23 * DIA_MS - HORA_MS)), [{"codigo": "evaluacion", "dias": 7, "urgente": True}])

    def test_el_cupo_avisa_desde_el_noventa_por_ciento(self):
        e = calcular()
        self.assertEqual(self.avisos(e, cupo.Consumo(equipos=49, usuarios=10)), [])
        self.assertEqual(self.avisos(e, cupo.Consumo(equipos=50, usuarios=10)), [{"codigo": "cupo", "tipo": "equipos", "en_uso": 50, "limite": 55, "porcentaje": 91}])
        self.assertEqual([a["tipo"] for a in self.avisos(e, cupo.Consumo(equipos=55, usuarios=1100))], ["equipos", "usuarios"])
        sin_tope = calcular(licencia=licencia_de_ejemplo(limites=Limites(ILIMITADO, ILIMITADO, 50, 100)))
        self.assertEqual(self.avisos(sin_tope, cupo.Consumo(equipos=10_000, usuarios=10_000)), [])

    def test_las_banderas_tambien_avisan(self):
        e = calcular(reloj_retroceso=True, integridad_alterada=True, coincidencia=Coincidencia(3, 5, 4, True, True, "hardware"))
        self.assertEqual([a["codigo"] for a in self.avisos(e)], ["reloj_sospechoso", "huella_parcial", "integridad_alterada"])

    def test_la_fecha_adelantada_es_un_error_que_va_primero_con_las_dos_fechas(self):
        """Q-L13: el aviso dice cuántos días está adelantada, la fecha que tiene el equipo y la que el aula lleva (la confiable); va antes que el estado y que cualquier otro."""
        adelanto = 10 * DIA_MS + 5_000                                            # diez días y unos segundos (lo que pasa entre el salto y el ciclo que lo ve)
        e = calcular(ahora=V + 5 * DIA_MS, reloj_adelanto_ms=adelanto, reloj_retroceso=True)
        avisos = self.avisos(e)
        self.assertEqual(avisos[0], {"codigo": "reloj_adelantado", "adelanto_dias": 10, "fecha_equipo": V + 5 * DIA_MS + adelanto, "fecha_esperada": V + 5 * DIA_MS})      # 10, no 11
        self.assertEqual([a["codigo"] for a in avisos], ["reloj_adelantado", "gracia", "reloj_sospechoso"])         # no se repite como bandera suelta
        self.assertEqual(e.reloj_adelanto_ms, adelanto)
        self.assertEqual(self.avisos(calcular(reloj_adelanto_ms=1))[0]["adelanto_dias"], 1)                       # 1 ms de adelanto: «1 día», nunca 0
        self.assertEqual(self.avisos(calcular(reloj_adelanto_ms=int(1.4 * DIA_MS)))[0]["adelanto_dias"], 1)       # al día más cercano
        self.assertEqual(self.avisos(calcular(reloj_adelanto_ms=int(1.6 * DIA_MS)))[0]["adelanto_dias"], 2)
        self.assertEqual(self.avisos(calcular(reloj_adelanto_ms=41 * DIA_MS - 60_000))[0]["adelanto_dias"], 41)
        self.assertEqual(self.avisos(calcular()), [])
        self.assertEqual(calcular().reloj_adelanto_ms, 0)


class RelojTests(SimpleTestCase):
    def test_el_ahora_confiable_nunca_baja_de_la_marca_alta(self):
        self.assertEqual(reloj.leer(1000, 400, 50).ahora, 1000)
        self.assertEqual(reloj.leer(300, 400, 50).ahora, 400)

    def test_retroceso_solo_mas_alla_de_la_tolerancia(self):
        self.assertFalse(reloj.leer(400 - 50, 400, 50).retroceso)          # justo la tolerancia: un ajuste normal de hora
        self.assertTrue(reloj.leer(400 - 51, 400, 50).retroceso)
        lectura = reloj.leer(AHORA - 10 * DIA_MS, AHORA, POLITICA_PROVISIONAL.tolerancia_retroceso_ms)
        self.assertEqual((lectura.ahora, lectura.atras_ms, lectura.retroceso), (AHORA, 10 * DIA_MS, True))

    def test_la_marca_alta_solo_sube(self):
        self.assertEqual(reloj.marca_siguiente(100, 50), 100)
        self.assertEqual(reloj.marca_siguiente(100, 150), 150)

    def test_retroceder_el_reloj_no_alarga_una_licencia(self):
        """Con la licencia ya vencida, poner el reloj en el pasado no devuelve el estado «activa»: el vencimiento se mide contra la marca alta."""
        marca = V + 5 * DIA_MS
        lectura = reloj.leer(V - 100 * DIA_MS, marca, POLITICA_PROVISIONAL.tolerancia_retroceso_ms)
        e = calcular(ahora=lectura.ahora, reloj_retroceso=lectura.retroceso)
        self.assertEqual((e.estado, e.dias_restantes), (cat.EN_GRACIA, 25))
        self.assertIn(cat.B_RELOJ_SOSPECHOSO, e.banderas)

    def test_salto_hacia_adelante_dentro_de_un_proceso(self):
        umbral = POLITICA_PROVISIONAL.salto_adelante_ms
        self.assertFalse(reloj.salto_adelante(1_000, 5_000, 1_000 + 60_000, 5_000 + 60_000, umbral))              # un minuto de verdad
        self.assertFalse(reloj.salto_adelante(1_000, 5_000, 1_000 + 3 * DIA_MS, 5_000, umbral))                    # tres días: bajo el umbral
        self.assertTrue(reloj.salto_adelante(1_000, 5_000, 1_000 + 8 * DIA_MS, 5_000 + 60_000, umbral))            # ocho días de pared en un minuto de monótono
        self.assertFalse(reloj.salto_adelante(1_000, 5_000, 1_000 + 8 * DIA_MS, 5_000 + 8 * DIA_MS, umbral))       # el proceso estuvo dormido de verdad ocho días

    def test_retroceso_dentro_de_un_proceso(self):
        tol = POLITICA_PROVISIONAL.tolerancia_retroceso_ms
        self.assertFalse(reloj.retroceso_en_marcha(10_000, 0, 10_000 + 30_000, 30_000, tol))
        self.assertTrue(reloj.retroceso_en_marcha(10 * DIA_MS, 0, 5 * DIA_MS, 60_000, tol))


class CupoTests(SimpleTestCase):
    def test_solo_cuenta_lo_nuevo_y_el_limite_es_inclusivo(self):
        self.assertTrue(cupo.admite(55, 54))
        self.assertFalse(cupo.admite(55, 55))
        self.assertTrue(cupo.admite(55, 50, adicional=5))
        self.assertFalse(cupo.admite(55, 50, adicional=6))
        self.assertFalse(cupo.admite(0, 0))
        self.assertTrue(cupo.admite(ILIMITADO, 10_000_000))

    def test_porcentaje(self):
        self.assertEqual(cupo.porcentaje(45, 50), 90)
        self.assertEqual(cupo.porcentaje(0, 0), 0)
        self.assertEqual(cupo.porcentaje(3, 0), 100)
        self.assertIsNone(cupo.porcentaje(5, ILIMITADO))

    def test_concurrencia_de_la_licencia_con_respaldo_a_settings(self):
        self.assertEqual(cupo.concurrencia(30, 60, 50, 100), (30, 60))
        self.assertEqual(cupo.concurrencia(None, None, 50, 100), (50, 100))
        self.assertEqual(cupo.concurrencia(ILIMITADO, ILIMITADO, 50, 100), (50, 100))
        self.assertEqual(cupo.concurrencia(80, 40, 50, 100), (40, 80))            # nunca normal > pico


# ------------------------------------------------------------------------------------------------------------------------ P-12
class EntornoTests(SimpleTestCase):
    REPO = Path("C:/trabajo/avacom/backend")

    def clasificar(self, raiz=None, env=None, argv=("manage.py", "runserver"), con=()):
        existentes = {Path(p) for p in con}
        return entorno.clasificar(Path(raiz) if raiz else self.REPO, env or {}, list(argv), existe=lambda p: Path(p) in existentes)

    def test_un_repositorio_de_desarrollo_es_desarrollo_o_pruebas_segun_el_comando(self):
        git = "C:/trabajo/avacom/.git"
        self.assertEqual(self.clasificar(con=[git]), entorno.DESARROLLO)
        self.assertEqual(self.clasificar(con=[git], argv=("manage.py", "test")), entorno.PRUEBAS)
        self.assertEqual(self.clasificar(con=[git], argv=("manage.py", "migrate")), entorno.DESARROLLO)

    def test_el_marcador_de_canal_gana_sobre_todo(self):
        marcador = "C:/trabajo/avacom/backend/.avacom-canal"
        git = "C:/trabajo/avacom/.git"
        self.assertEqual(self.clasificar(con=[marcador]), entorno.PRODUCCION)
        self.assertEqual(self.clasificar(con=[marcador, git], argv=("manage.py", "test"), env={"AVACOM_LMS_ENTORNO": "pruebas"}), entorno.PRODUCCION)

    def test_bajo_program_files_es_produccion_aunque_haya_git_y_aunque_digan_pruebas(self):
        for raiz in ("C:/Program Files/AVACOM/OPS Master/Backend", "C:/Program Files (x86)/AVACOM/Backend", "D:/PROGRAM FILES/AVACOM/Backend"):
            self.assertEqual(self.clasificar(raiz=raiz, con=[Path(raiz).parent.parent.as_posix() + "/.git"], env={"AVACOM_LMS_ENTORNO": "desarrollo"}, argv=("manage.py", "test")), entorno.PRODUCCION, raiz)

    def test_la_variable_instalado_solo_puede_anadir_proteccion(self):
        self.assertEqual(self.clasificar(env={"AVACOM_LMS_ENTORNO": "instalado"}, con=["C:/trabajo/avacom/.git"]), entorno.PRODUCCION)

    def test_poner_pruebas_o_desarrollo_en_backend_env_NO_apaga_la_licencia_de_un_nodo_instalado(self):
        """P-12, prueba obligatoria: layout de producción + AVACOM_LMS_ENTORNO=pruebas en backend.env → sigue evaluando la licencia."""
        marcador = "C:/Program Files/AVACOM/OPS Master/Backend/.avacom-canal"
        raiz = "C:/Program Files/AVACOM/OPS Master/Backend"
        for declarado in ("pruebas", "desarrollo", "PRUEBAS", " desarrollo ", "cualquier cosa", ""):
            self.assertEqual(self.clasificar(raiz=raiz, env={"AVACOM_LMS_ENTORNO": declarado}, con=[marcador]), entorno.PRODUCCION, repr(declarado))

    def test_sin_marcador_ni_program_files_ni_git_se_toma_como_produccion(self):
        self.assertEqual(self.clasificar(raiz="D:/aulas/avacom/Backend"), entorno.PRODUCCION)
        self.assertEqual(self.clasificar(raiz="D:/aulas/avacom/Backend", env={"AVACOM_LMS_ENTORNO": "pruebas"}, argv=("manage.py", "test")), entorno.PRODUCCION)

    def test_el_limite_conocido_quien_copia_el_backend_borra_el_marcador_y_fabrica_un_git_lo_evade(self):
        """A4 · administrador local con conocimientos: se documenta, no se promete lo contrario."""
        self.assertEqual(self.clasificar(raiz="D:/copia/Backend", con=["D:/copia/.git"]), entorno.DESARROLLO)


# ------------------------------------------------------------------------------------------------------------------------ R-01
class RutasTests(SimpleTestCase):
    INTOCABLES = [
        ("GET", "/health/"), ("GET", "/api/licencia/estado/"), ("POST", "/api/licencia/activar/"), ("POST", "/api/dispositivos/latido/"), ("POST", "/api/logs/clientes/"),
        ("POST", "/api/acceso/sesiones/"), ("DELETE", "/api/acceso/sesiones/actual/"), ("POST", "/api/acceso/instalacion/"), ("POST", "/api/acceso/docentes/registro/"),
        ("POST", "/api/acceso/estudiantes/registro/"), ("POST", "/api/acceso/estudiantes/abc/pin/"), ("GET", "/api/acceso/yo/"), ("POST", "/api/acceso/autorizaciones-temporales/canjear/"),
        ("POST", "/api/aula/sesiones/unirse/"), ("POST", "/api/aula/sesiones/xyz/distribuciones/"), ("GET", "/api/aula/sesiones/xyz/estado/"), ("GET", "/api/aula/cursos/c1/medios/m1/"),
        ("POST", "/api/modo-estudio/sync/"), ("GET", "/api/modo-estudio/asignaciones/"), ("POST", "/api/modo-estudio/docente/asignaciones/"),
        ("GET", "/api/evaluacion/estudiantes/"), ("GET", "/api/evaluacion/mias/"), ("GET", "/api/evaluacion/asignaciones/a1/antesala/"), ("POST", "/api/evaluacion/asignaciones/a1/intentos/"),
        ("GET", "/api/evaluacion/intentos/i1/estado/"), ("POST", "/api/evaluacion/intentos/i1/latido/"), ("GET", "/api/evaluacion/intentos/i1/preguntas/"),
        ("POST", "/api/evaluacion/intentos/i1/respuestas/"), ("POST", "/api/evaluacion/intentos/i1/incidentes/"), ("POST", "/api/evaluacion/intentos/i1/bloqueo/"),
        ("POST", "/api/evaluacion/intentos/i1/entregar/"), ("GET", "/api/evaluacion/intentos/i1/resultado/"), ("GET", "/api/evaluacion/intentos/i1/medios/m1/"),
        ("GET", "/api/diagnostico/velocidad/bajada/"), ("GET", "/api/m/PASE/aula/cursos/c1/medios/m1/"),
    ]
    LICENCIABLES = [
        ("GET", "/api/reportes/clases/"), ("GET", "/api/reportes/grupos/g1/"), ("GET", "/api/reportes/alumnos/a1/"), ("GET", "/api/reportes/uso/"), ("PUT", "/api/reportes/configuracion/"),
        ("POST", "/api/reportes/reconstruir/"), ("GET", "/api/search/"), ("POST", "/api/search/open/"), ("POST", "/api/acceso/usuarios/importar/"),
        ("POST", "/api/acceso/roles/"), ("POST", "/api/gradebook/escalas/"), ("POST", "/api/gradebook/escalas/adoptar/"), ("POST", "/api/gradebook/escalas/e1/versiones/"),
        ("POST", "/api/gradebook/derivados/reconstruir/"),
    ]
    LIBRES = [
        ("GET", "/api/acceso/usuarios/"), ("POST", "/api/acceso/usuarios/"), ("GET", "/api/acceso/roles/"), ("GET", "/api/gradebook/libro/"), ("GET", "/api/gradebook/mias/"),
        ("GET", "/api/auditoria/asientos/"), ("POST", "/api/auditoria/verificar/"), ("GET", "/api/dispositivos/"), ("POST", "/api/evaluacion/asignaciones/"),
        ("GET", "/api/gradebook/escalas/"), ("GET", "/api/gradebook/escalas/plantillas/"), ("POST", "/api/gradebook/escalas/vista-previa/"), ("GET", "/api/biblioteca/cursos/"),
        # D-6: lo que CIERRA puertas no se licencia, y las calificaciones siempre se pueden sacar (Q-L12: por defecto, no limitar su exportación)
        ("PUT", "/api/acceso/politicas/TEACHER/"), ("PUT", "/api/acceso/politicas/STUDENT/"), ("GET", "/api/acceso/visitantes/"), ("POST", "/api/acceso/usuarios/u1/vincular/"),
        ("GET", "/api/reportes/boletines/"), ("GET", "/api/reportes/boletines/a1/"), ("POST", "/api/reportes/exportaciones/"), ("POST", "/api/reportes/exportaciones/alcance/"),
        ("POST", "/api/reportes/exportaciones/x1/confirmar/"), ("GET", "/api/reportes/exportaciones/x1/"),
    ]

    def test_lo_intocable_no_tiene_capacidad_en_ningun_metodo(self):
        for metodo, ruta in self.INTOCABLES:
            self.assertTrue(rutas.es_intocable(ruta), ruta)
            self.assertIsNone(rutas.capacidad_de(metodo, ruta), (metodo, ruta))

    def test_lo_licenciable_tiene_su_capacidad(self):
        esperadas = {"/api/reportes/": "reportes", "/api/search/": "busqueda", "/api/acceso/usuarios/importar/": "importacion"}
        for metodo, ruta in self.LICENCIABLES:
            capacidad = rutas.capacidad_de(metodo, ruta)
            self.assertIn(capacidad, cat.CAPACIDADES_LICENCIABLES, (metodo, ruta))
            for prefijo, cap in esperadas.items():
                if ruta.startswith(prefijo):
                    self.assertEqual(capacidad, cap, ruta)

    def test_el_resto_pasa_sin_capacidad(self):
        for metodo, ruta in self.LIBRES:
            self.assertIsNone(rutas.capacidad_de(metodo, ruta), (metodo, ruta))

    def test_ninguna_ruta_licenciable_se_solapa_con_una_intocable(self):
        for _metodo, ruta in self.LICENCIABLES:
            self.assertFalse(rutas.es_intocable(ruta), ruta)

    def test_el_metodo_importa_en_las_licenciables_acotadas(self):
        self.assertEqual(rutas.capacidad_de("POST", "/api/acceso/usuarios/importar/"), "importacion")
        self.assertIsNone(rutas.capacidad_de("GET", "/api/acceso/usuarios/importar/"))
        self.assertIsNone(rutas.capacidad_de("GET", "/api/acceso/roles/"))
        self.assertEqual(rutas.capacidad_de("POST", "/api/acceso/roles/"), "administracion_avanzada")

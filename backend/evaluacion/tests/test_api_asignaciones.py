"""
La asignación desde el profesor (FUN-105, 106, 107, 108, 118): crear, validar, cambiar de estado con el reloj del nodo, nivel de control, plazos y la
frontera con la biblioteca (FUN-103 y FUN-104 no se hacen aquí).
"""
from __future__ import annotations

from unittest import mock

from classroom_engine.dominio.errores import FuenteNoDisponible as FuenteCaida

from .. import models as m
from .base import BASE, CURSO, EXAMEN, MIN, BaseEvaluacion


class CrearAsignacionTests(BaseEvaluacion):
    def test_crear_copia_los_ajustes_del_examen_congela_la_version_y_arma_la_vista_previa(self):
        a = self.crear_asignacion("controlado")
        self.assertEqual((a["tipo"], a["estado"], a["fuente_curso"], a["curso_ref"], a["curso_version"], a["objeto_ref"], a["leccion_ref"]),
                         ("examen", "activa", "ejemplo", CURSO, "1.0.0", EXAMEN, "l3-assessment"))
        self.assertEqual((a["nivel_declarado"], a["nivel_examen"], a["plazo"], a["gracia_min"], a["reactivacion"], a["intentos_permitidos"],
                          a["resultados"], a["aprobacion_pct"], a["permite_retroceso"]), ("controlado", "controlado", "blando", 15, "profesor", 1,
                                                                                         "tras_liberar", 60.0, True))
        self.assertEqual((a["estrategia"], a["preguntas_por_alumno"], a["total_banco"], a["grupo_id"], a["grupo_rotulo"], a["titulo"]),
                         ("random_balanced", 4, 12, self.grupo["id"], "Octavo A", "Examen de estados de la materia"))
        previo = a["armado_previo"]
        self.assertEqual((previo["estrategia"], previo["preguntas_por_alumno"], previo["total_banco"]), ("random_balanced", 4, 12))
        self.assertGreater(previo["limite_seg_estimado"], 0)
        self.assertEqual(a["ajustes"]["limite_seg_estimado"], previo["limite_seg_estimado"])
        self.assertEqual(m.Asignacion.objects.get(pk=a["id"]).profesor_id, self.docente_id)

    def test_publicar_deja_los_eventos_del_maestro_y_el_asiento(self):
        a = self.crear_asignacion("controlado", limite_en=self.t + 30 * MIN)
        self.assertEqual(self.eventos(), ["evaluacion.nivel_examen.definido.v1", "evaluacion.fecha_limite.configurada.v1", "evaluacion.asignada.v1"])
        from audit import models as maudit
        acciones = list(maudit.Bitacora.objects.filter(accion="evaluacion.asignada").values_list("objeto_id", flat=True))
        self.assertEqual(acciones, [a["id"]])

    def test_el_nivel_es_obligatorio_y_el_sistema_nunca_lo_preselecciona(self):
        r = self.api.post(f"{BASE}/asignaciones/", {"fuente": "ejemplo", "curso_ref": CURSO, "objeto_ref": EXAMEN, "grupo_id": self.grupo["id"],
                                                     "actor": self.docente_id}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        self.assertIn("nivel", r.json()["detail"])
        self.assertEqual(m.Asignacion.objects.count(), 0)

    def test_sin_iniciar_queda_en_borrador_y_el_alumno_no_la_ve(self):
        a = self.crear_asignacion("supervisado", iniciar=False)
        self.assertEqual(a["estado"], "borrador")
        self.assertEqual(self.eventos("evaluacion.asignada.v1"), [])
        r = self.api.get(f"{BASE}/asignaciones/{a['id']}/antesala/", self.alumno())
        self.assertEqual(r.status_code, 404)                                  # no se revela
        self.assertEqual(self.api.get(f"{BASE}/mias/", self.alumno()).json()["pendientes"], [])
        iniciada = self.accion(f"/asignaciones/{a['id']}/iniciar/")
        self.assertEqual(iniciada["estado"], "activa")
        self.assertEqual(self.eventos("evaluacion.asignada.v1"), ["evaluacion.asignada.v1"])
        self.assertEqual(len(self.api.get(f"{BASE}/mias/", self.alumno()).json()["pendientes"]), 1)

    def test_una_apertura_futura_la_deja_programada_y_se_activa_sola_al_llegar_su_fecha(self):
        a = self.crear_asignacion("supervisado", abre_en=self.t + 10 * MIN)
        self.assertEqual(a["estado"], "programada")
        self.abrir(a["id"], esperado=409)                                      # todavía no recibe intentos
        self.avanzar(minutos=10)
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/")["estado"], "activa")
        self.abrir(a["id"], esperado=201)

    def test_solo_se_acepta_un_examen(self):
        r = self.api.post(f"{BASE}/asignaciones/", {"tipo": "actividad", "fuente": "ejemplo", "curso_ref": CURSO, "objeto_ref": "l1-activity",
                                                     "grupo_id": self.grupo["id"], "nivel_examen": "abierto", "actor": self.docente_id}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        r = self.api.post(f"{BASE}/asignaciones/", {"fuente": "ejemplo", "curso_ref": CURSO, "objeto_ref": "l1-activity", "grupo_id": self.grupo["id"],
                                                     "nivel_examen": "abierto", "actor": self.docente_id}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "no_encontrado"))      # una actividad no es un examen

    def test_validaciones_de_la_entrada(self):
        base = {"fuente": "ejemplo", "curso_ref": CURSO, "objeto_ref": EXAMEN, "grupo_id": self.grupo["id"], "nivel_examen": "supervisado",
                "actor": self.docente_id}
        casos = [
            ({"nivel_examen": "estricto"}, 400), ({"plazo": "endurecido"}, 400), ({"plazo": "flexible"}, 400), ({"gracia_min": -5}, 400),
            ({"intentos_permitidos": 0}, 400), ({"tiempo": {"modo": "fijo"}}, 400), ({"tiempo": {"modo": "eterno"}}, 400),
            ({"reactivacion": "nunca"}, 400), ({"resultados": "siempre"}, 400), ({"abre_en": self.t + 10 * MIN, "limite_en": self.t + 5 * MIN}, 400),
            ({"recursos": [{"rotulo": "sin media_ref"}]}, 400), ({"grupo_id": "no-existe"}, 404), ({"curso_ref": "otro.curso"}, 404),
            ({"objeto_ref": "no-existe"}, 404), ({"alcance": "seleccion", "destinatarios": []}, 400),
            ({"alcance": "seleccion", "destinatarios": ["fantasma"], "grupo_id": ""}, 400), ({"alcance": "todos"}, 400),
            ({"sesion_id": "no-existe"}, 404), ({"curso_ref": ""}, 400),
        ]
        for extra, esperado in casos:
            r = self.api.post(f"{BASE}/asignaciones/", {**base, **extra}, format="json")
            self.assertEqual(r.status_code, esperado, f"{extra}: {r.content}")
        self.assertEqual(m.Asignacion.objects.count(), 0)

    def test_a_alumnos_concretos(self):
        otro, _ = self.alumno_con_tableta("Ana", "200001")
        a = self.crear_asignacion("abierto", alcance="seleccion", destinatarios=[self.estudiante_id])
        self.assertEqual((a["alcance"], a["destinatarios"]), ("seleccion", [self.estudiante_id]))
        self.assertEqual(len(self.api.get(f"{BASE}/mias/", self.alumno()).json()["pendientes"]), 1)
        self.assertEqual(self.api.get(f"{BASE}/mias/", self.alumno(alumno_id=otro, hw="hw-200001")).json()["pendientes"], [])

    def test_sin_biblioteca_no_se_crea_nada_y_responde_503_con_sugerencia(self):
        with mock.patch("evaluacion.infraestructura.contenido.ContenidoEvaluacion.examen",
                        side_effect=__import__("evaluacion.dominio.errores", fromlist=["x"]).FuenteNoDisponible("Biblioteca cerrada", sugerencia="Ábrela")):
            r = self.api.post(f"{BASE}/asignaciones/", {"fuente": "ejemplo", "curso_ref": CURSO, "objeto_ref": EXAMEN, "grupo_id": self.grupo["id"],
                                                         "nivel_examen": "abierto", "actor": self.docente_id}, format="json")
        self.assertEqual(r.status_code, 503)
        self.assertEqual((r.json()["disponible"], r.json()["sugerencia"]), (False, "Ábrela"))
        self.assertEqual(m.Asignacion.objects.count(), 0)

    def test_fun_103_y_fun_104_son_de_la_biblioteca(self):
        for ruta in ("/evaluaciones/", "/reactivos/"):
            for metodo in ("post", "put", "patch", "delete"):
                r = getattr(self.api, metodo)(f"{BASE}{ruta}", {"titulo": "x"}, format="json")
                self.assertEqual((r.status_code, r.json()["codigo"], r.json()["dueno"]), (409, "administracion_no_permitida", "AVACOM Biblioteca"), (ruta, metodo))
        from audit import models as maudit
        self.assertEqual(maudit.Bitacora.objects.filter(accion="administracion.rechazada").count(), 8)      # queda constancia del intento

    def test_cada_eleccion_de_tiempo_se_traduce_en_el_limite_del_examen(self):
        fijo = self.crear_asignacion("abierto", tiempo={"modo": "fijo", "limite_seg": 900})
        sin = self.crear_asignacion("abierto", tiempo={"modo": "sin_limite"})
        self.assertEqual((fijo["tiempo_modo"], fijo["tiempo_limite_seg"], fijo["armado_previo"]["limite_seg_estimado"]), ("fijo", 900, 900))
        self.assertEqual((sin["tiempo_modo"], sin["armado_previo"]["limite_seg_estimado"]), ("sin_limite", None))


class PermisosTests(BaseEvaluacion):
    """Con sesión (JWT) el rol decide y el profesor sólo asigna a sus grupos."""

    def cuerpo(self, **extra):
        return {"fuente": "ejemplo", "curso_ref": CURSO, "objeto_ref": EXAMEN, "alcance": "grupo", "grupo_id": self.grupo["id"], "nivel_examen": "supervisado",
                "iniciar": True, **extra}

    def test_el_profesor_titular_asigna_y_la_asignacion_queda_a_su_nombre(self):
        r = self.docente.post(f"{BASE}/asignaciones/", self.cuerpo(), format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["profesor_id"], self.docente_id)

    def test_el_profesor_no_asigna_a_un_grupo_que_no_es_suyo(self):
        r = self.docente.post(f"{BASE}/asignaciones/", self.cuerpo(grupo_id=self.otro_grupo["id"]), format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "no_es_el_titular"))

    def test_la_administracion_asigna_a_cualquier_grupo(self):
        r = self.admin.post(f"{BASE}/asignaciones/", self.cuerpo(grupo_id=self.otro_grupo["id"]), format="json")
        self.assertEqual(r.status_code, 201, r.content)

    def test_un_alumno_no_asigna_ni_ve_el_panel(self):
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        r = alumno.post(f"{BASE}/asignaciones/", self.cuerpo(), format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))
        a = self.crear_asignacion("supervisado")
        self.assertEqual(alumno.get(f"{BASE}/asignaciones/{a['id']}/panel/").status_code, 403)
        self.assertEqual(alumno.get(f"{BASE}/asignaciones/").status_code, 403)

    def test_otro_profesor_no_opera_una_evaluacion_ajena(self):
        a = self.docente.post(f"{BASE}/asignaciones/", self.cuerpo(), format="json").json()
        r = self.admin.post("/api/acceso/usuarios/", {
            "rol": "TEACHER", "alias": "Prof. Otro", "persona": {"nombres": "Otro", "apellidos": "Profesor"},
            "identificadores": [{"tipo": "DNI", "valor": "70.111.222", "es_login": True}], "secreto": "Otro.2026!!", "secreto_definitivo": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        otro = self.sesion("70.111.222", "Otro.2026!!")
        for ruta in ("panel/", ""):
            self.assertEqual(otro.get(f"{BASE}/asignaciones/{a['id']}/{ruta}").status_code, 403, ruta)
        self.assertEqual(otro.post(f"{BASE}/asignaciones/{a['id']}/cerrar/", {}, format="json").status_code, 403)
        self.assertEqual(self.docente.get(f"{BASE}/asignaciones/{a['id']}/panel/").status_code, 200)

    def test_el_alumno_con_sesion_presenta_pero_la_administracion_no_presenta_por_el(self):
        a = self.crear_asignacion("abierto")
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        r = alumno.post(f"{BASE}/asignaciones/{a['id']}/intentos/", {"dispositivo": self.hw_juan}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        r = self.admin.post(f"{BASE}/asignaciones/{a['id']}/intentos/", {"dispositivo": self.hw_juan}, format="json")
        self.assertEqual(r.status_code, 403)                                  # el Maestro le niega «el intento del alumno»

    def test_el_profesor_con_sesion_no_puede_abrir_un_intento_ajeno(self):
        a = self.crear_asignacion("abierto")
        r = self.docente.post(f"{BASE}/asignaciones/{a['id']}/intentos/", {"dispositivo": self.hw_juan}, format="json")
        self.assertEqual(r.status_code, 403)


class CambiosDeEstadoTests(BaseEvaluacion):
    def test_el_plazo_blando_marca_y_no_cierra(self):
        a = self.crear_asignacion("abierto", limite_en=self.t + 10 * MIN)
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/")["estado"], "activa")
        self.avanzar(minutos=11)
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/")["estado"], "activa_fuera_de_plazo")
        self.abrir(a["id"], esperado=201)                                      # se sigue aceptando (BR-073)

    def test_configurar_el_plazo_cambia_la_fecha_y_la_gracia(self):
        a = self.crear_asignacion("abierto")
        r = self.accion(f"/asignaciones/{a['id']}/plazo/", {"limite_en": self.t + 20 * MIN, "gracia_min": 5}, metodo="patch")
        self.assertEqual((r["limite_en"], r["gracia_ms"], r["plazo"]), (self.t + 20 * MIN, 5 * MIN, "blando"))
        self.assertIn("evaluacion.fecha_limite.configurada.v1", self.eventos())
        self.accion(f"/asignaciones/{a['id']}/plazo/", {}, esperado=400, metodo="patch")                  # nada que cambiar

    def test_endurecer_exige_un_plazo_blando_vigente_y_cierra_al_vencer(self):
        a = self.crear_asignacion("abierto")
        self.accion(f"/asignaciones/{a['id']}/endurecer/", esperado=409)                    # sin fecha no hay cuándo cerrar
        r = self.accion(f"/asignaciones/{a['id']}/endurecer/", {"limite_en": self.t + 10 * MIN})
        self.assertEqual((r["plazo"], r["limite_en"]), ("endurecido", self.t + 10 * MIN))
        self.assertIn("evaluacion.fecha_limite.endurecida.v1", self.eventos())
        self.accion(f"/asignaciones/{a['id']}/endurecer/", {"limite_en": self.t + 20 * MIN}, esperado=409)   # ya está endurecida
        self.avanzar(minutos=10)
        cerrada = self.ver(f"/asignaciones/{a['id']}/")
        self.assertEqual((cerrada["estado"], cerrada["cerrada_en"]), ("cerrada", self.t - 0))        # cerró en la fecha límite

    def test_no_se_endurece_un_plazo_ya_vencido(self):
        a = self.crear_asignacion("abierto", limite_en=self.t + 5 * MIN)
        self.avanzar(minutos=6)
        self.accion(f"/asignaciones/{a['id']}/endurecer/", esperado=409)                    # el blando venció: ya no es «vigente»

    def test_cerrar_a_mano_prorrogar_y_reabrir(self):
        a = self.crear_asignacion("abierto", limite_en=self.t + 5 * MIN)
        self.avanzar(minutos=6)
        r = self.accion(f"/asignaciones/{a['id']}/prorrogar/", {"limite_en": self.t + 30 * MIN})
        self.assertEqual((r["estado"], r["limite_en"]), ("activa", self.t + 30 * MIN))
        self.accion(f"/asignaciones/{a['id']}/prorrogar/", {"limite_en": self.t - MIN}, esperado=400)     # el plazo nuevo debe ser futuro
        cerrada = self.accion(f"/asignaciones/{a['id']}/cerrar/", {"motivo": "Terminó la hora"})
        self.assertEqual((cerrada["estado"], cerrada["cerrada_en"], cerrada["entregados"]), ("cerrada", self.t, 0))
        self.accion(f"/asignaciones/{a['id']}/cerrar/", esperado=409)                        # ya cerró
        self.abrir(a["id"], esperado=409)
        reabierta = self.accion(f"/asignaciones/{a['id']}/reabrir/", {"limite_en": self.t + 60 * MIN})
        self.assertEqual((reabierta["estado"], reabierta["cerrada_en"]), ("activa", None))
        self.abrir(a["id"], esperado=201)

    def test_reabrir_con_plazo_endurecido_vencido_exige_un_plazo_nuevo(self):
        a = self.crear_asignacion("abierto", plazo="endurecido", limite_en=self.t + 5 * MIN)
        self.avanzar(minutos=6)
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/")["estado"], "cerrada")
        self.accion(f"/asignaciones/{a['id']}/reabrir/", esperado=400)
        self.accion(f"/asignaciones/{a['id']}/reabrir/", {"limite_en": self.t + 30 * MIN})

    def test_cerrada_se_archiva_a_las_24_horas(self):
        a = self.crear_asignacion("abierto")
        self.accion(f"/asignaciones/{a['id']}/cerrar/")
        self.avanzar(minutos=24 * 60)
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/")["estado"], "archivada")
        self.accion(f"/asignaciones/{a['id']}/reabrir/", esperado=409)

    def test_listar_filtra_y_trae_los_totales(self):
        a = self.crear_asignacion("abierto")
        self.crear_asignacion("abierto", iniciar=False)
        self.assertEqual(len(self.ver("/asignaciones/")["asignaciones"]), 2)
        self.assertEqual([x["id"] for x in self.ver("/asignaciones/", estado="activa")["asignaciones"]], [a["id"]])
        self.assertEqual(self.ver("/asignaciones/", grupo_id=self.otro_grupo["id"])["asignaciones"], [])
        t = self.ver(f"/asignaciones/{a['id']}/")["totales"]
        self.assertEqual((t["destinatarios"], t["sin_intento"], t["en_curso"]), (1, 1, 0))


class NivelDeControlTests(BaseEvaluacion):
    def test_definir_el_nivel_antes_de_que_haya_intentos_abiertos(self):
        a = self.crear_asignacion("supervisado")
        r = self.accion(f"/asignaciones/{a['id']}/nivel/", {"nivel_examen": "controlado"})
        self.assertEqual((r["nivel_declarado"], r["nivel_examen"]), ("controlado", "controlado"))
        self.assertEqual(self.eventos("evaluacion.nivel_examen.definido.v1").count("evaluacion.nivel_examen.definido.v1"), 2)
        self.accion(f"/asignaciones/{a['id']}/nivel/", {"nivel_examen": "estricto"}, esperado=400)

    def test_con_un_intento_abierto_el_nivel_ya_no_se_redefine(self):
        a = self.crear_asignacion("supervisado")
        self.abrir(a["id"])
        r = self.accion(f"/asignaciones/{a['id']}/nivel/", {"nivel_examen": "controlado"}, esperado=409)
        self.assertEqual(r["codigo"], "intentos_abiertos")

    def test_degradar_solo_baja_exige_motivo_y_deja_incidente_en_cada_intento_afectado(self):
        a = self.crear_asignacion("supervisado", iniciar=True)
        self.accion(f"/asignaciones/{a['id']}/nivel/", {"nivel_examen": "controlado"})
        apertura = self.abrir(a["id"], hw=self._tableta_controlada())
        self.assertEqual(apertura["plan_bloqueo"]["nivel"], "controlado")
        self.accion(f"/asignaciones/{a['id']}/degradar/", {"nivel_examen": "supervisado"}, esperado=400)                # sin motivo
        self.accion(f"/asignaciones/{a['id']}/degradar/", {"nivel_examen": "controlado", "motivo": "No sube"}, esperado=400)
        r = self.accion(f"/asignaciones/{a['id']}/degradar/", {"nivel_examen": "supervisado", "motivo": "Fallan las tabletas"})
        self.assertEqual((r["nivel_declarado"], r["nivel_examen"], r["afectados"]), ("controlado", "supervisado", 1))
        intento = apertura["intento"]["id"]
        self.assertIn("degradacion", self.incidentes(intento))
        self.assertEqual(self.fila(intento).nivel_efectivo, "supervisado")
        # el plan que recibe la tableta en su siguiente latido ya es el del nivel nuevo: suelta lo que ya no se exige
        plan = self.latido(intento, hw=self._tableta_controlada())["plan_bloqueo"]
        self.assertEqual((plan["nivel"], plan["capa_sistema"], plan["capa_app"], plan["nivel_exigido"]), ("supervisado", False, False, "supervisado"))
        self.assertIn("evaluacion.nivel_examen_degradado.v1", self.eventos())
        # una vez degradada, el nivel declarado queda como evidencia y no se puede volver a subir
        self.accion(f"/asignaciones/{a['id']}/degradar/", {"nivel_examen": "controlado", "motivo": "Subir"}, esperado=400)

    def _tableta_controlada(self) -> str:
        if not hasattr(self, "_hw_ctrl"):
            self._hw_ctrl = "hw-juan-controlada"
            self.registrar(self._hw_ctrl, "Tableta aprovisionada", capacidad="controlado")
        return self._hw_ctrl

    def test_la_base_impide_que_el_nivel_vigente_supere_al_declarado(self):
        from django.db import IntegrityError, transaction

        a = self.crear_asignacion("abierto")
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Asignacion.objects.filter(pk=a["id"]).update(nivel_examen="controlado")


class LiberarResultadosTests(BaseEvaluacion):
    def test_no_se_liberan_con_alumnos_presentando_y_la_primera_liberacion_manda(self):
        a = self.crear_asignacion("abierto")
        apertura = self.abrir(a["id"])
        r = self.accion(f"/asignaciones/{a['id']}/liberar-resultados/", esperado=409)
        self.assertEqual(r["codigo"], "intentos_abiertos")
        self.responder_todo(apertura["intento"]["id"])
        self.entregar(apertura["intento"]["id"], confirmar=True)
        primera = self.accion(f"/asignaciones/{a['id']}/liberar-resultados/")
        self.avanzar(minutos=5)
        segunda = self.accion(f"/asignaciones/{a['id']}/liberar-resultados/")
        self.assertEqual((primera["liberados_en"], segunda["liberados_en"]), (self.t - 5 * MIN, self.t - 5 * MIN))
        self.assertEqual(self.eventos("evaluacion.resultados_liberados.v1"), ["evaluacion.resultados_liberados.v1"])

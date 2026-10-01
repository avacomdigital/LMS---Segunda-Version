"""
El intento del alumno (FUN-109, FUN-114; BR-072; INV-012; INV-024; PAN-120, PAN-123): abrir, reanudar sin duplicar, cupo, el examen SIN claves, entregar y
la antesala con las condiciones obligatorias.
"""
from __future__ import annotations

from unittest import mock

from classroom_engine.dominio import curso as curso_aula
from device_manager import models as m09

from .. import models as m
from ..infraestructura import fuentes_examen
from .base import BASE, MIN, BaseEvaluacion, FuenteQueCalifica, respuesta_correcta


class AbrirIntentoTests(BaseEvaluacion):
    def test_abrir_arma_el_examen_del_alumno_congela_la_version_y_arranca_el_reloj(self):
        a = self.crear_asignacion("supervisado")
        r = self.abrir(a["id"], esperado=201)
        i = r["intento"]
        self.assertEqual((i["estado"], i["numero"], i["nivel_efectivo"], i["total"], i["respondidas"], r["preguntas_total"], r["reanudado"]),
                         ("en_curso", 1, "supervisado", 4, 0, 4, False))
        self.assertTrue(r["reloj"]["corriendo"])
        self.assertGreater(r["reloj"]["limite_seg"], 0)
        self.assertEqual(r["reloj"]["restante_ms"], r["reloj"]["limite_seg"] * 1000)
        self.assertEqual((r["plan_bloqueo"]["nivel"], r["plan_bloqueo"]["capa_sistema"], r["plan_bloqueo"]["registrar_salidas"]), ("supervisado", False, True))
        self.assertIn("Puedes consultar los materiales", r["condiciones"]["texto"])
        fila = self.fila(i["id"])
        self.assertEqual((fila.curso_version, fila.alumno_id, fila.dispositivo_id, fila.iniciado_en, fila.reloj_desde, fila.ultimo_latido_en),
                         ("1.0.0", self.estudiante_id, self.tableta_juan["id"], self.t, self.t, self.t))
        self.assertEqual(len(fila.armado), 4)
        self.assertEqual(len(fila.sesiones), 1)
        self.assertEqual(fila.sesion_ref, fila.sesiones[0]["sesion_ref"])
        self.assertTrue(m09.DimSesionAlumno.objects.filter(pk=fila.sesion_ref, alumno_id=self.estudiante_id, finalizada_en__isnull=True).exists())
        self.assertEqual(self.eventos("evaluacion.intento_abierto.v1"), ["evaluacion.intento_abierto.v1"])
        from audit import models as maudit
        self.assertTrue(maudit.Bitacora.objects.filter(accion="evaluacion.iniciada", objeto_id=i["id"]).exists())

    def test_el_examen_de_un_alumno_se_guarda_como_referencias_nunca_como_texto(self):
        a = self.crear_asignacion("abierto")
        i = self.abrir(a["id"])["intento"]["id"]
        fila = self.fila(i)
        self.assertTrue(all(isinstance(x, str) and x.startswith("l3-q") for x in fila.armado))
        self.assertEqual(set(fila.armado_meta["tipos"]), set(fila.armado))
        self.assertNotIn("prompt", str(fila.armado_meta).lower())
        self.assertNotIn("Qué estado", str(fila.armado_meta))

    def test_abrir_dos_veces_devuelve_el_mismo_intento_vivo_inv_012(self):
        a = self.crear_asignacion("abierto")
        primero = self.abrir(a["id"], esperado=201)
        segundo = self.abrir(a["id"], esperado=200)
        self.assertEqual((segundo["intento"]["id"], segundo["reanudado"]), (primero["intento"]["id"], True))
        self.assertEqual(m.Intento.objects.filter(asignacion_id=a["id"]).count(), 1)
        self.assertEqual(self.eventos("evaluacion.intento_abierto.v1"), ["evaluacion.intento_abierto.v1"])

    def test_el_examen_de_un_alumno_es_el_mismo_cada_vez_que_lo_pide(self):
        a = self.crear_asignacion("abierto")
        i = self.abrir(a["id"])["intento"]["id"]
        primero, segundo = self.preguntas(i), self.preguntas(i)
        self.assertEqual([p["pregunta_ref"] for p in primero["preguntas"]], [p["pregunta_ref"] for p in segundo["preguntas"]])
        self.assertEqual([[o["opcion_ref"] for o in p.get("opciones", [])] for p in primero["preguntas"]],
                         [[o["opcion_ref"] for o in p.get("opciones", [])] for p in segundo["preguntas"]])

    def test_dos_alumnos_reciben_examenes_distintos_del_mismo_banco(self):
        a = self.crear_asignacion("abierto")
        otros = [self.alumno_con_tableta(f"Alumno {n}", f"3000{n:02d}", capacidad="supervisado") for n in range(8)]
        examenes = {tuple(sorted(self.fila(self.abrir(a["id"])["intento"]["id"]).armado))}
        for alumno_id, hw in otros:
            examenes.add(tuple(sorted(self.fila(self.abrir(a["id"], hw=hw, alumno_id=alumno_id)["intento"]["id"]).armado)))
        self.assertGreater(len(examenes), 1)

    def test_cupo_por_defecto_de_uno_y_el_segundo_acceso_queda_bloqueado_con_su_motivo(self):
        """BR-072 · TST-031."""
        a = self.crear_asignacion("abierto")
        i = self.abrir(a["id"])["intento"]["id"]
        self.responder_todo(i)
        self.entregar(i, confirmar=True)
        r = self.api.post(f"{BASE}/asignaciones/{a['id']}/intentos/", self.alumno(), format="json")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["intentos_permitidos"]), (409, "intentos_agotados", 1))
        antesala = self.api.get(f"{BASE}/asignaciones/{a['id']}/antesala/", self.alumno()).json()
        self.assertEqual((antesala["puede_comenzar"], antesala["motivo"]), (False, "ya_entregado"))

    def test_intentos_permitidos_configurables_y_numerados(self):
        a = self.crear_asignacion("abierto", intentos_permitidos=2)
        numeros = []
        for _ in range(2):
            i = self.abrir(a["id"], esperado=201)["intento"]
            numeros.append(i["numero"])
            self.entregar(i["id"], confirmar=True)
        self.assertEqual(numeros, [1, 2])
        self.abrir(a["id"], esperado=409)

    def test_intentos_ilimitados_tst_030(self):
        a = self.crear_asignacion("abierto", intentos_permitidos=None)
        for esperado in (1, 2, 3):
            i = self.abrir(a["id"], esperado=201)["intento"]
            self.assertEqual(i["numero"], esperado)
            self.responder_todo(i["id"])
            self.entregar(i["id"], confirmar=True)
        self.assertEqual(m.Intento.objects.filter(asignacion_id=a["id"], estado__in=("calificado", "en_revision_docente")).count(), 3)

    def test_un_intento_anulado_no_consume_el_cupo(self):
        a = self.crear_asignacion("abierto")
        i = self.abrir(a["id"])["intento"]["id"]
        self.entregar(i, confirmar=True)
        self.accion(f"/intentos/{i}/anular/", {"motivo": "Se detectó un problema"})
        self.abrir(a["id"], esperado=201)

    def test_el_alumno_de_otro_grupo_no_ve_ni_abre_la_evaluacion(self):
        a = self.crear_asignacion("abierto")
        ajeno, hw = self.alumno_con_tableta("Ajeno", "400001", grupo_id=self.otro_grupo["id"])
        for metodo, ruta in (("get", f"/asignaciones/{a['id']}/antesala/"), ("post", f"/asignaciones/{a['id']}/intentos/")):
            r = getattr(self.api, metodo)(f"{BASE}{ruta}", self.alumno(hw, ajeno), **({"format": "json"} if metodo == "post" else {}))
            self.assertEqual(r.status_code, 404, (metodo, r.content))                                # no se revela
        self.assertEqual(self.api.get(f"{BASE}/mias/", self.alumno(hw, ajeno)).json()["pendientes"], [])

    def test_identidad_y_aparato(self):
        a = self.crear_asignacion("abierto")
        r = self.api.post(f"{BASE}/asignaciones/{a['id']}/intentos/", {"alumno_id": self.estudiante_id}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "falta_dispositivo"))
        r = self.api.post(f"{BASE}/asignaciones/{a['id']}/intentos/", {"dispositivo": "hw-nueva"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "falta_alumno"))                  # compartida y sin nadie declarado
        r = self.api.post(f"{BASE}/asignaciones/{a['id']}/intentos/", {"dispositivo": self.hw_juan, "alumno_id": "fantasma"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["motivo"]), (403, "sin_permiso", "alumno_desconocido"))

    def test_una_tableta_bloqueada_o_retirada_no_presenta(self):
        a = self.crear_asignacion("abierto")
        self.api.post(f"/api/dispositivos/{self.tableta_juan['id']}/bloquear/", {"actor": self.docente_id}, format="json")
        r = self.api.post(f"{BASE}/asignaciones/{a['id']}/intentos/", self.alumno(), format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_bloqueado"))
        self.api.post(f"/api/dispositivos/{self.tableta_juan['id']}/desbloquear/", {"actor": self.docente_id}, format="json")
        self.abrir(a["id"], esperado=201)

    def test_si_el_curso_cambia_de_version_el_intento_no_se_abre_inv_024(self):
        a = self.crear_asignacion("abierto")
        original = fuentes_examen.examen_pool

        def otra_version(origen, curso_ref, objeto_ref):
            return {**original(origen, curso_ref, objeto_ref), "version": "2.0.0"}

        with mock.patch.object(fuentes_examen, "examen_pool", otra_version):
            r = self.api.post(f"{BASE}/asignaciones/{a['id']}/intentos/", self.alumno(), format="json")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["asignada"], r.json()["instalada"]), (409, "version_no_disponible", "1.0.0", "2.0.0"))
        self.assertEqual(m.Intento.objects.count(), 0)

    def test_sin_biblioteca_no_se_abre_pero_tampoco_se_rompe(self):
        a = self.crear_asignacion("abierto")
        with mock.patch.object(fuentes_examen, "examen_pool", side_effect=__import__("classroom_engine.dominio.errores", fromlist=["x"]).FuenteNoDisponible("cerrada")):
            r = self.api.post(f"{BASE}/asignaciones/{a['id']}/intentos/", self.alumno(), format="json")
        self.assertEqual((r.status_code, r.json()["disponible"]), (503, False))
        self.abrir(a["id"], esperado=201)                                                            # al volver la biblioteca, abre sin más


class PreguntasTests(BaseEvaluacion):
    def test_el_examen_llega_sin_ninguna_clave_y_sin_cache(self):
        a = self.crear_asignacion("abierto")
        i = self.abrir(a["id"])["intento"]["id"]
        r = self.api.get(f"{BASE}/intentos/{i}/preguntas/", self.alumno())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Cache-Control"], "no-store")
        cuerpo = r.json()
        self.assertIsNone(curso_aula.contiene_clave(cuerpo))
        refs = [p["pregunta_ref"] for p in cuerpo["preguntas"]]
        self.assertEqual(refs, self.fila(i).armado)
        self.assertEqual((cuerpo["titulo"], cuerpo["navegacion_atras"], cuerpo["respondidas"], cuerpo["version"]),
                         ("Examen de estados de la materia", True, {}, "1.0.0"))
        for p in cuerpo["preguntas"]:
            self.assertIn(p["componente"], ("opcion_multiple", "verdadero_falso", "completar", "relacionar", "ordenar", "abierta"))
            self.assertTrue(p["enunciado"])

    def test_las_preguntas_incluyen_lo_ya_respondido_para_reanudar(self):
        a = self.crear_asignacion("abierto")
        i = self.abrir(a["id"])["intento"]["id"]
        refs = self.refs_del_examen(i)
        propia = respuesta_correcta(refs[0])
        self.responder(i, [self.r(refs[0], 1, propia)])
        respondidas = self.preguntas(i)["respondidas"]
        self.assertEqual(respondidas, {refs[0]: {"respuesta": propia, "secuencia": 1}})
        self.assertEqual(self.preguntas(i)["pregunta_actual"], refs[0])

    def test_solo_las_tabletas_del_intento_leen_el_examen(self):
        a = self.crear_asignacion("abierto")
        i = self.abrir(a["id"])["intento"]["id"]
        self.registrar("hw-intrusa", "Tableta intrusa", capacidad="controlado")
        r = self.api.get(f"{BASE}/intentos/{i}/preguntas/", self.alumno("hw-intrusa"))
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_ajeno"))
        otro, hw = self.alumno_con_tableta("Otro", "500001", capacidad="supervisado")
        self.assertEqual(self.api.get(f"{BASE}/intentos/{i}/preguntas/", self.alumno(hw, otro)).status_code, 404)       # el intento es de Juan

    def test_entregado_ya_no_se_muestra_el_examen(self):
        a = self.crear_asignacion("abierto")
        i = self.abrir(a["id"])["intento"]["id"]
        self.entregar(i, confirmar=True)
        self.preguntas(i, esperado=409)


class EstadoYEntregaTests(BaseEvaluacion):
    def test_el_estado_dice_que_pintar(self):
        a = self.crear_asignacion("controlado")
        self.registrar("hw-ctrl", "Aprovisionada", capacidad="controlado")
        i = self.abrir(a["id"], hw="hw-ctrl")["intento"]["id"]
        e = self.estado(i, hw="hw-ctrl")
        self.assertEqual((e["intento"]["estado"], e["espera_reactivacion"], e["sesion_activa"], e["resultado_disponible"], e["mensaje"], e["latido_seg"]),
                         ("en_curso", False, True, False, None, 5))
        self.assertEqual((e["plan_bloqueo"]["capa_sistema"], e["plan_bloqueo"]["bloquear_capturas"]), (True, True))
        self.assertEqual(e["servidor_en"], self.t)
        self.avanzar(seg=10)
        self.assertEqual(self.estado(i, hw="hw-ctrl")["reloj"]["restante_ms"], e["reloj"]["restante_ms"] - 10_000)

    def test_entregar_con_preguntas_sin_responder_exige_confirmar(self):
        a = self.crear_asignacion("abierto")
        i = self.abrir(a["id"])["intento"]["id"]
        refs = self.refs_del_examen(i)
        r = self.api.post(f"{BASE}/intentos/{i}/entregar/", self.alumno(), format="json")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["faltan"]), (409, "confirmacion_requerida", refs))
        self.assertEqual(self.fila(i).estado, "en_curso")
        e = self.entregar(i, confirmar=True)
        self.assertEqual((e["intento"]["estado"] in ("calificado", "en_revision_docente"), e["origen_entrega"], e["intento"]["respondidas"]),
                         (True, "alumno", 0))
        self.assertEqual(self.fila(i).porcentaje, 0.0)                                              # lo omitido suma cero

    def test_entregar_es_idempotente_y_reenviar_la_cola_final_no_cambia_nada_inv_005(self):
        a = self.crear_asignacion("abierto")
        i = self.abrir(a["id"])["intento"]["id"]
        refs = self.refs_del_examen(i)
        from .base import respuesta_correcta
        ultimo = [self.r(ref, n, respuesta_correcta(ref)) for n, ref in enumerate(refs, start=1)]
        primero = self.entregar(i, respuestas=ultimo)
        antes = self.fila(i)
        segundo = self.entregar(i, respuestas=ultimo)
        despues = self.fila(i)
        self.assertEqual((primero["intento"]["id"], segundo["intento"]["estado"]), (i, primero["intento"]["estado"]))
        self.assertEqual((antes.respuestas, antes.porcentaje, antes.entregado_en), (despues.respuestas, despues.porcentaje, despues.entregado_en))
        self.assertEqual(self.eventos("evaluacion.intento_entregado.v1"), ["evaluacion.intento_entregado.v1"])         # un solo evento

    def test_la_entrega_nunca_dice_calificado_si_quedan_reactivos_por_revisar(self):
        """Guion paso 13: «Decirle que su examen fue calificado cuando quedan reactivos por revisar» es lo que el sistema nunca hace."""
        a = self.crear_asignacion("abierto", intentos_permitidos=None)
        for _ in range(12):
            i = self.abrir(a["id"])["intento"]["id"]
            tipos = self.fila(i).armado_meta["tipos"]
            self.responder_todo(i)
            e = self.entregar(i, confirmar=True)
            if "open" in tipos.values():
                self.assertEqual((e["intento"]["estado"], e["que_sigue"]["codigo"]), ("en_revision_docente", "en_revision"))
                self.assertNotIn("calific", e["que_sigue"]["texto"].lower())
                self.assertFalse(e["resultado_disponible"])
                return
        self.skipTest("ninguno de los doce exámenes sorteados trajo una pregunta abierta")

    def test_el_alumno_no_entrega_con_el_intento_suspendido(self):
        a = self.crear_asignacion("controlado")
        self.registrar("hw-ctrl", "Aprovisionada", capacidad="controlado")
        i = self.abrir(a["id"], hw="hw-ctrl")["intento"]["id"]
        self.avanzar(seg=40)                                                                          # sin latido más de 30 s: se pausa
        r = self.api.post(f"{BASE}/intentos/{i}/entregar/", {**self.alumno("hw-ctrl"), "confirmar": True}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "transicion_invalida"))
        self.assertEqual(self.fila(i).estado, "pausado_desconexion")           # el rechazo no deshace lo que el reloj ya provocó
        self.assertEqual(self.incidentes(i), ["desconexion"])


class AntesalaYMisEvaluacionesTests(BaseEvaluacion):
    def test_la_antesala_muestra_duracion_condiciones_y_que_se_registra_antes_de_empezar(self):
        a = self.crear_asignacion("controlado", tiempo={"modo": "fijo", "limite_seg": 1200})
        antesala = self.api.get(f"{BASE}/asignaciones/{a['id']}/antesala/", self.alumno()).json()
        self.assertEqual((antesala["asignacion"]["preguntas"], antesala["asignacion"]["duracion_seg"], antesala["asignacion"]["intentos_permitidos"],
                          antesala["asignacion"]["intentos_usados"]), (4, 1200, 1, 0))
        self.assertEqual(antesala["condiciones"]["nivel"], "controlado")
        self.assertIn("Durante este examen tu tableta solo muestra el examen", antesala["condiciones"]["texto"])
        self.assertTrue(antesala["condiciones"]["registra"])
        self.assertEqual(antesala["dispositivo"], {"id": self.tableta_juan["id"], "capacidad": "supervisado", "alcanza": False, "nivel_exigido": "controlado"})
        self.assertTrue(antesala["puede_comenzar"])                         # pulsar «Comenzar» crea la solicitud de admisión: no lo excluye su tableta
        self.assertIsNone(antesala["mi_intento"])

    def test_mias_lista_lo_que_le_alcanza_con_su_intento(self):
        a = self.crear_asignacion("abierto")
        lista = self.api.get(f"{BASE}/mias/", self.alumno()).json()
        self.assertEqual([(x["id"], x["puede_comenzar"], x["mi_intento"]) for x in lista["pendientes"]], [(a["id"], True, None)])
        i = self.abrir(a["id"])["intento"]["id"]
        mia = self.api.get(f"{BASE}/mias/", self.alumno()).json()["pendientes"][0]
        self.assertEqual((mia["mi_intento"]["id"], mia["mi_intento"]["estado"], mia["nivel_examen"], mia["preguntas"]), (i, "en_curso", "abierto", 4))

    def test_quien_eres_lista_a_quien_puede_presentar_algo_ahora_sin_sesion_ni_permiso(self):
        sin_nada = self.api.get(f"{BASE}/estudiantes/")
        self.assertEqual((sin_nada.status_code, sin_nada.json()["disponible"], sin_nada.json()["grupos"]), (200, False, []))
        self.crear_asignacion("abierto", iniciar=False)                                  # un borrador no cuenta
        self.assertEqual(self.api.get(f"{BASE}/estudiantes/").json()["grupos"], [])
        a = self.crear_asignacion("abierto")
        self.nuevo_alumno("Zoe", "910001")
        self.nuevo_alumno("Abel", "910002")
        ajeno, _ = self.alumno_con_tableta("Ajeno", "910003", grupo_id=self.otro_grupo["id"])    # su grupo no tiene evaluación
        cuerpo = self.api.get(f"{BASE}/estudiantes/").json()
        self.assertTrue(cuerpo["disponible"])
        grupo = cuerpo["grupos"][0]
        self.assertEqual((len(cuerpo["grupos"]), grupo["nombre"]), (1, "Octavo A"))
        ids = [x["id"] for x in grupo["alumnos"]]
        self.assertIn(self.estudiante_id, ids)
        self.assertNotIn(ajeno, ids)
        rotulos = [x["rotulo"].lower() for x in grupo["alumnos"]]
        self.assertEqual(rotulos, sorted(rotulos))                                       # por nombre, para encontrarse rápido
        self.accion(f"/asignaciones/{a['id']}/cerrar/")
        self.assertEqual(self.api.get(f"{BASE}/estudiantes/").json()["grupos"], [])      # cerrada: ya no hay nada que presentar

    def test_recientes_solo_con_todas_y_solo_si_tiene_intento(self):
        a = self.crear_asignacion("abierto")
        i = self.abrir(a["id"])["intento"]["id"]
        self.entregar(i, confirmar=True)
        self.accion(f"/asignaciones/{a['id']}/cerrar/")
        self.assertEqual(self.api.get(f"{BASE}/mias/", self.alumno()).json()["recientes"], [])
        recientes = self.api.get(f"{BASE}/mias/", {**self.alumno(), "todas": "1"}).json()["recientes"]
        self.assertEqual([x["id"] for x in recientes], [a["id"]])
        self.avanzar(minutos=8 * 24 * 60)
        self.assertEqual(self.api.get(f"{BASE}/mias/", {**self.alumno(), "todas": "1"}).json()["recientes"], [])

    def test_antesala_con_la_evaluacion_programada_o_cerrada_no_deja_comenzar(self):
        p = self.crear_asignacion("abierto", abre_en=self.t + 10 * MIN)
        self.assertEqual(self.api.get(f"{BASE}/asignaciones/{p['id']}/antesala/", self.alumno()).json()["motivo"], "no_abierta")
        c = self.crear_asignacion("abierto")
        self.accion(f"/asignaciones/{c['id']}/cerrar/")
        antesala = self.api.get(f"{BASE}/asignaciones/{c['id']}/antesala/", self.alumno()).json()
        self.assertEqual((antesala["puede_comenzar"], antesala["motivo"]), (False, "no_abierta"))

    def test_los_medios_de_un_intento_solo_sirven_los_de_sus_preguntas(self):
        a = self.crear_asignacion("abierto")
        i = self.abrir(a["id"])["intento"]["id"]
        r = self.api.get(f"{BASE}/intentos/{i}/medios/img-cover-matter/", self.alumno())
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "no_encontrado"))                   # ese medio no es de este examen
        self.registrar("hw-intrusa", "Tableta intrusa", capacidad="controlado")
        r = self.api.get(f"{BASE}/intentos/{i}/medios/img-cover-matter/", self.alumno("hw-intrusa"))
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_ajeno"))              # ni siquiera se llega a mirar el medio

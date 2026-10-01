"""
Nivel de control contra capacidad de la tableta (CAP-063, CAP-064, FUN-116, FUN-118; BR-075, BR-076; TST-041; AC-046): una tableta que no alcanza el nivel
NO abre el intento sola y espera al profesor; el alumno nunca queda excluido por su dispositivo; lo que la tableta no declara cuenta como `abierto`.
"""
from __future__ import annotations

from device_manager import models as m09

from .. import models as m
from .base import BASE, BaseEvaluacion


class AdmisionTests(BaseEvaluacion):
    def pedir_y_esperar(self, nivel: str = "controlado"):
        a = self.crear_asignacion(nivel)
        r = self.api.post(f"{BASE}/asignaciones/{a['id']}/intentos/", self.alumno(), format="json")
        return a, r

    def test_tst_041_una_tableta_por_debajo_del_nivel_queda_en_espera_con_el_nivel_exigido_visible(self):
        a, r = self.pedir_y_esperar("controlado")
        cuerpo = r.json()
        self.assertEqual(r.status_code, 202, r.content)
        self.assertEqual((cuerpo["intento"]["estado"], cuerpo["admision"]["estado"], cuerpo["admision"]["nivel_exigido"], cuerpo["admision"]["nivel_alcanzado"],
                          cuerpo["mensaje"]["codigo"]), ("no_iniciado", "en_espera", "controlado", "supervisado", "espera_admision"))
        self.assertIn("Tu profesor debe decidir", cuerpo["mensaje"]["texto"])
        self.assertIn("tu tableta solo muestra el examen", cuerpo["condiciones"]["texto"])
        fila = self.fila(cuerpo["intento"]["id"])
        self.assertEqual((fila.estado, fila.reloj_desde, fila.armado, fila.iniciado_en), ("no_iniciado", None, [], None))        # no se abrió: el reloj no corre
        self.assertEqual(self.eventos("evaluacion.intento_abierto.v1"), [])

    def test_volver_a_pulsar_comenzar_no_duplica_la_solicitud_ni_el_intento(self):
        a, primero = self.pedir_y_esperar()
        segundo = self.api.post(f"{BASE}/asignaciones/{a['id']}/intentos/", self.alumno(), format="json")
        self.assertEqual((segundo.status_code, segundo.json()["admision"]["id"]), (202, primero.json()["admision"]["id"]))
        self.assertEqual(m.Admision.objects.count(), 1)
        self.assertEqual(m.Intento.objects.count(), 1)
        self.assertEqual(self.eventos("evaluacion.admision_solicitada.v1"), ["evaluacion.admision_solicitada.v1"])
        antesala = self.api.get(f"{BASE}/asignaciones/{a['id']}/antesala/", self.alumno()).json()
        self.assertEqual((antesala["puede_comenzar"], antesala["motivo"], antesala["admision"]["estado"]), (False, "espera_admision", "en_espera"))

    def test_el_profesor_admite_en_un_nivel_menor_con_motivo_y_queda_registrado(self):
        a, r = self.pedir_y_esperar()
        adm = self.ver(f"/asignaciones/{a['id']}/admisiones/")["admisiones"]
        self.assertEqual([(x["alumno_id"], x["estado"], x["dispositivo_rotulo"]) for x in adm], [(self.estudiante_id, "en_espera", "Tableta de Juan")])
        decidida = self.accion(f"/asignaciones/{a['id']}/admisiones/{adm[0]['id']}/decidir/",
                               {"decision": "admitir", "nivel_admitido": "supervisado", "motivo": "La tableta aún no está aprovisionada"})
        self.assertEqual((decidida["estado"], decidida["nivel_admitido"], decidida["decidido_por"], decidida["motivo"]),
                         ("admitido", "supervisado", self.docente_id, "La tableta aún no está aprovisionada"))
        self.assertEqual(self.ver(f"/asignaciones/{a['id']}/admisiones/")["admisiones"], [])                    # ya no espera
        self.assertIn("evaluacion.dispositivo_admitido_bajo_nivel.v1", self.eventos())
        from audit import models as maudit
        excepcion = maudit.Bitacora.objects.get(accion="aula.nivel.excepcion")
        self.assertEqual((excepcion.objeto_id, excepcion.motivo), (adm[0]["id"], "La tableta aún no está aprovisionada"))
        self.assertIn("admitido_bajo_nivel", self.incidentes(r.json()["intento"]["id"]))
        # el alumno abre su examen con el nivel menor: el plan no bloquea
        apertura = self.abrir(a["id"], esperado=201)
        self.assertEqual((apertura["intento"]["id"], apertura["intento"]["nivel_efectivo"], apertura["plan_bloqueo"]["nivel"],
                          apertura["plan_bloqueo"]["capa_sistema"], apertura["plan_bloqueo"]["capa_app"]), (r.json()["intento"]["id"], "supervisado", "supervisado", False, False))
        self.assertEqual(m.Intento.objects.count(), 1)                                                          # reutiliza el no_iniciado, no crea otro

    def test_admitir_sin_motivo_o_en_un_nivel_que_no_es_menor_se_rechaza(self):
        a, r = self.pedir_y_esperar()
        aid = r.json()["admision"]["id"]
        ruta = f"/asignaciones/{a['id']}/admisiones/{aid}/decidir/"
        self.accion(ruta, {"decision": "admitir", "nivel_admitido": "supervisado"}, esperado=400)                # sin motivo
        self.accion(ruta, {"decision": "admitir", "nivel_admitido": "controlado", "motivo": "Con motivo"}, esperado=400)   # no es menor
        self.accion(ruta, {"decision": "admitir", "nivel_admitido": "inventado", "motivo": "Con motivo"}, esperado=400)
        self.accion(ruta, {"decision": "quizá", "motivo": "Con motivo"}, esperado=400)
        self.assertEqual(m.Admision.objects.get(pk=aid).estado, "en_espera")

    def test_rechazar_deja_al_alumno_con_un_mensaje_y_se_puede_reconsiderar(self):
        a, r = self.pedir_y_esperar()
        aid = r.json()["admision"]["id"]
        ruta = f"/asignaciones/{a['id']}/admisiones/{aid}/decidir/"
        self.accion(ruta, {"decision": "rechazar", "motivo": "Use otra tableta"})
        denegado = self.api.post(f"{BASE}/asignaciones/{a['id']}/intentos/", self.alumno(), format="json")
        self.assertEqual((denegado.status_code, denegado.json()["codigo"]), (403, "admision_rechazada"))
        antesala = self.api.get(f"{BASE}/asignaciones/{a['id']}/antesala/", self.alumno()).json()
        self.assertEqual((antesala["puede_comenzar"], antesala["motivo"]), (False, "rechazada"))
        self.accion(ruta, {"decision": "admitir", "nivel_admitido": "abierto", "motivo": "Cambié de idea"})      # reconsidera
        self.abrir(a["id"], esperado=201)
        self.accion(ruta, {"decision": "rechazar", "motivo": "Ahora no"}, esperado=409)                           # una tableta ya admitida no se rechaza

    def test_el_alumno_nunca_queda_excluido_por_su_dispositivo_puede_cambiar_de_tableta(self):
        """Guion paso 4: «Excluir al alumno del examen por su dispositivo» es lo que el sistema nunca hace."""
        a, _ = self.pedir_y_esperar()
        self.registrar("hw-prestada", "Tableta prestada", capacidad="controlado")
        apertura = self.abrir(a["id"], hw="hw-prestada", esperado=201)
        self.assertEqual((apertura["intento"]["nivel_efectivo"], apertura["plan_bloqueo"]["capa_sistema"]), ("controlado", True))
        self.assertEqual(m.Intento.objects.filter(estado="en_curso").count(), 1)

    def test_degradar_el_nivel_de_todo_el_examen_destraba_a_los_que_esperaban(self):
        a, r = self.pedir_y_esperar()
        self.accion(f"/asignaciones/{a['id']}/degradar/", {"nivel_examen": "supervisado", "motivo": "Ninguna tableta está aprovisionada"})
        apertura = self.abrir(a["id"], esperado=201)
        self.assertEqual((apertura["intento"]["id"], apertura["intento"]["nivel_efectivo"], apertura["plan_bloqueo"]["nivel_exigido"]),
                         (r.json()["intento"]["id"], "supervisado", "supervisado"))

    def test_lo_que_la_tableta_no_declara_cuenta_como_abierto(self):
        a = self.crear_asignacion("supervisado")
        ctx = self.registrar("hw-sin-declarar", "Sin declarar")                                                  # nunca dijo su capacidad
        self.assertEqual(ctx["capacidad_control"], "")
        r = self.api.post(f"{BASE}/asignaciones/{a['id']}/intentos/", self.alumno("hw-sin-declarar"), format="json")
        self.assertEqual((r.status_code, r.json()["admision"]["nivel_alcanzado"]), (202, "abierto"))
        abierta = self.crear_asignacion("abierto")
        self.abrir(abierta["id"], hw="hw-sin-declarar", esperado=201)                                           # a un examen abierto entra cualquiera

    def test_la_capacidad_se_declara_al_abrir_y_se_actualiza_con_el_latido(self):
        a = self.crear_asignacion("controlado")
        # la tableta de Juan (supervisado) declara ahora que está aprovisionada, al presentarse con el intento
        apertura = self.abrir(a["id"], capacidad_control="controlado", esperado=201)
        self.assertEqual(apertura["plan_bloqueo"]["capa_sistema"], True)
        self.assertEqual(m09.Dispositivo.objects.get(identificador_hw=self.hw_juan).capacidad_control, "controlado")
        i = apertura["intento"]["id"]
        # si más tarde declara que perdió la capa del sistema, el plan lo refleja como PARCIAL (no se presume)
        e = self.latido(i, capacidad_control="supervisado")
        self.assertEqual((e["plan_bloqueo"]["capa_sistema"], e["plan_bloqueo"]["parcial"], e["plan_bloqueo"]["capa_app"]), (False, True, True))

    def test_una_capacidad_desconocida_es_un_error_de_datos(self):
        a = self.crear_asignacion("abierto")
        r = self.api.post(f"{BASE}/asignaciones/{a['id']}/intentos/", {**self.alumno(), "capacidad_control": "blindada"}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        r = self.api.post("/api/dispositivos/", {"identificador_hw": "hw-x", "capacidad_control": "blindada"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_cambiar_de_tableta_a_mitad_de_intento_exige_alcanzar_el_nivel_efectivo(self):
        a = self.crear_asignacion("controlado")
        self.registrar("hw-ctrl", "Aprovisionada", capacidad="controlado")
        i = self.abrir(a["id"], hw="hw-ctrl")["intento"]["id"]
        # el alumno intenta seguir desde la tableta de Juan, que sólo es supervisada: no pasa sola
        r = self.api.post(f"{BASE}/asignaciones/{a['id']}/intentos/", self.alumno(), format="json")
        self.assertEqual((r.status_code, r.json()["admision"]["estado"], r.json()["intento"]["id"]), (202, "en_espera", i))
        self.assertEqual(self.fila(i).dispositivo_id, m09.Dispositivo.objects.get(identificador_hw="hw-ctrl").id)      # el intento sigue en su tableta

    def test_elegibilidad_cuenta_las_tabletas_que_no_alcanzan_msg_036(self):
        a = self.crear_asignacion("controlado")
        ana, hw = self.alumno_con_tableta("Ana", "600001", capacidad="controlado")
        # sólo se juzga la tableta que ya se conoce de cada alumno: aquí, la que tiene asignada a su nombre
        for alumno_id, dispositivo_id in ((self.estudiante_id, self.tableta_juan["id"]),
                                           (ana, m09.Dispositivo.objects.get(identificador_hw=hw).id)):
            self.assertEqual(self.admin.post(f"/api/dispositivos/{dispositivo_id}/asignar/", {"alumno_id": alumno_id}, format="json").status_code, 200)
        self.accion(f"/asignaciones/{a['id']}/degradar/", {"nivel_examen": "supervisado", "motivo": "Prueba"}, esperado=200)
        pre = self.ver(f"/asignaciones/{a['id']}/elegibilidad/", nivel="controlado")
        self.assertEqual(pre["resumen"], {"alcanzan": 1, "no_alcanzan": 1, "sin_tableta": 0})
        self.assertEqual({f["rotulo"]: f["alcanza"] for f in pre["filas"]}, {"Juan P.": False, "Ana": True})
        self.assertIn("1 tabletas no alcanzan para el nivel controlado", pre["mensaje"])
        vigente = self.ver(f"/asignaciones/{a['id']}/elegibilidad/")
        self.assertEqual((vigente["nivel_examen"], vigente["resumen"]["no_alcanzan"], vigente["mensaje"]), ("supervisado", 0, None))


class PermisosDeAdmisionTests(BaseEvaluacion):
    def test_el_profesor_titular_decide_y_otro_no(self):
        a = self.docente.post(f"{BASE}/asignaciones/", {"fuente": "ejemplo", "curso_ref": "avacom.co.lower-secondary.6.science.states-of-matter",
                                                         "objeto_ref": "l3-exam", "grupo_id": self.grupo["id"], "nivel_examen": "controlado", "iniciar": True},
                              format="json").json()
        r = self.api.post(f"{BASE}/asignaciones/{a['id']}/intentos/", self.alumno(), format="json")
        aid = r.json()["admision"]["id"]
        decidir = f"{BASE}/asignaciones/{a['id']}/admisiones/{aid}/decidir/"
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual(alumno.post(decidir, {"decision": "admitir", "nivel_admitido": "abierto", "motivo": "Yo mismo"}, format="json").status_code, 403)
        ok = self.docente.post(decidir, {"decision": "admitir", "nivel_admitido": "abierto", "motivo": "Lo autorizo"}, format="json")
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(ok.json()["decidido_por"], self.docente_id)

"""
El panel del profesor, el expediente y la anulación (PAN-060, PAN-061, PAN-062; CAP-061, CAP-066; INV-018): se ordena por quién necesita al profesor, el
expediente es de sólo lectura y anular es una decisión humana con nombre y motivo; el sistema, jamás.
"""
from __future__ import annotations

from audit import models as maudit

from .. import models as m
from .base import BASE, MIN, SEG, BaseEvaluacion, respuesta_correcta


class OrdenDelPanelTests(BaseEvaluacion):
    def test_el_panel_pone_primero_a_quien_necesita_al_profesor_y_al_final_lo_cerrado(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        ana, hw_ana = self.alumno_con_tableta("Ana", "A-100", "supervisado")
        luis, hw_luis = self.alumno_con_tableta("Luis", "L-100", "supervisado")
        eva, hw_eva = self.alumno_con_tableta("Eva", "E-100", "supervisado")
        juan = self.abrir(a["id"])["intento"]["id"]                                       # Juan: se quedará sin señal
        i_ana = self.abrir(a["id"], hw=hw_ana, alumno_id=ana)["intento"]["id"]            # Ana: presentando con normalidad
        i_eva = self.abrir(a["id"], hw=hw_eva, alumno_id=eva)["intento"]["id"]            # Eva: ya entregó
        self.entregar(i_eva, hw=hw_eva, alumno_id=eva, confirmar=True)                    # Luis: no ha entrado
        for _ in range(3):
            self.avanzar(seg=20)
            self.latido(i_ana, hw=hw_ana, alumno_id=ana)
        panel = self.ver(f"/asignaciones/{a['id']}/panel/")
        orden = [(f["alumno_id"], f["estado"]) for f in panel["filas"]]
        self.assertEqual([x[0] for x in orden], [self.estudiante_id, ana, luis, eva])
        self.assertEqual([x[1] for x in orden][:3], ["pausado_desconexion", "en_curso", "sin_intento"])
        self.assertIn(orden[3][1], ("calificado", "en_revision_docente", "entregado"))
        self.assertEqual([f["requiere_reactivacion"] for f in panel["filas"]], [True, False, False, False])
        t = panel["totales"]
        self.assertEqual((t["destinatarios"], t["suspendidos"], t["en_curso"], t["sin_intento"]), (4, 1, 1, 1))
        self.assertEqual(t["entregados"] + t["calificados"] + t["en_revision"], 1)
        self.assertEqual(juan, panel["filas"][0]["intento_id"])

    def test_quien_espera_admision_va_justo_despues_del_suspendido_y_antes_de_los_que_presentan(self):
        a = self.crear_asignacion("controlado", tiempo={"modo": "sin_limite"})
        ana, hw_ana = self.alumno_con_tableta("Ana", "A-100", "controlado")
        luis, _ = self.alumno_con_tableta("Luis", "L-100", "controlado")
        self.abrir(a["id"], hw=hw_ana, alumno_id=ana)                                     # Ana presenta con normalidad
        r = self.api.post(f"{BASE}/asignaciones/{a['id']}/intentos/", self.alumno(), format="json")        # la tableta de Juan no alcanza
        self.assertEqual(r.status_code, 202, r.content)
        panel = self.ver(f"/asignaciones/{a['id']}/panel/")
        self.assertEqual([f["alumno_id"] for f in panel["filas"]], [self.estudiante_id, ana, luis])
        juan = panel["filas"][0]
        self.assertEqual((juan["admision"]["estado"], juan["admision"]["nivel_exigido"], juan["admision"]["nivel_alcanzado"]), ("en_espera", "controlado", "supervisado"))
        self.assertEqual((juan["dispositivo"]["capacidad"], juan["dispositivo"]["alcanza"]), ("supervisado", False))
        self.assertEqual(panel["totales"]["en_espera_admision"], 1)

    def test_una_falla_de_bloqueo_en_controlado_sube_al_alumno_en_la_lista(self):
        a = self.crear_asignacion("controlado", tiempo={"modo": "sin_limite"})
        ana, hw_ana = self.alumno_con_tableta("Ana", "A-100", "controlado")
        luis, hw_luis = self.alumno_con_tableta("Luis", "L-100", "controlado")
        i_ana = self.abrir(a["id"], hw=hw_ana, alumno_id=ana)["intento"]["id"]
        i_luis = self.abrir(a["id"], hw=hw_luis, alumno_id=luis)["intento"]["id"]
        self.api.post(f"{BASE}/intentos/{i_luis}/bloqueo/", {**self.alumno(hw_luis, luis), "resultado": "fallido", "capas": {}}, format="json")
        self.latido(i_ana, hw=hw_ana, alumno_id=ana)
        panel = self.ver(f"/asignaciones/{a['id']}/panel/")
        presentes = [f for f in panel["filas"] if f["intento_id"] in (i_ana, i_luis)]
        self.assertEqual([f["alumno_id"] for f in presentes], [luis, ana])               # primero el del bloqueo fallido
        self.assertEqual(presentes[0]["bloqueo"], {"resultado": "fallido"})

    def test_lo_pendiente_de_decidir_va_antes_que_lo_que_presenta(self):
        a = self.crear_asignacion("supervisado", plazo="endurecido", limite_en=self.t + 10 * MIN, tiempo={"modo": "sin_limite"}, gracia_min=1)
        ana, hw_ana = self.alumno_con_tableta("Ana", "A-100", "supervisado")
        luis, hw_luis = self.alumno_con_tableta("Luis", "L-100", "supervisado")
        i = self.abrir(a["id"])["intento"]["id"]
        refs = self.refs_cerradas(i)
        self.latir_hasta(i, 580)
        self.avanzar(seg=20)
        self.avanzar(minutos=5)                                                           # pasó la gracia de 1 min
        self.responder(i, [self.r(refs[0], 1, respuesta_correcta(refs[0]), capturada_en=a["limite_en"] - SEG)], origen="cola")
        panel = self.ver(f"/asignaciones/{a['id']}/panel/")
        self.assertEqual([f["alumno_id"] for f in panel["filas"]][0], self.estudiante_id)
        self.assertEqual(panel["filas"][0]["envio_tardio"], "pendiente_decision")
        self.assertEqual({f["alumno_id"] for f in panel["filas"]}, {self.estudiante_id, ana, luis})

    def test_el_reloj_de_cada_fila_muestra_lo_que_le_queda_y_no_hay_reloj_para_quien_no_empezo(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "fijo", "limite_seg": 600})
        i = self.abrir(a["id"])["intento"]["id"]
        self.latir_hasta(i, 100)
        fila = next(f for f in self.ver(f"/asignaciones/{a['id']}/panel/")["filas"] if f["alumno_id"] == self.estudiante_id)
        self.assertEqual((fila["reloj"]["restante_ms"], fila["reloj"]["corriendo"], fila["silencio_ms"]), (500 * SEG, True, 0))

    def test_el_panel_solo_lo_ve_el_titular_o_la_administracion(self):
        a = self.crear_asignacion("supervisado")
        self.assertEqual(self.admin.get(f"{BASE}/asignaciones/{a['id']}/panel/").status_code, 200)
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual(alumno.get(f"{BASE}/asignaciones/{a['id']}/panel/").status_code, 403)
        self.assertEqual(self.api.get(f"{BASE}/asignaciones/no-existe/panel/", {"actor": self.docente_id}).status_code, 404)


class ExpedienteTests(BaseEvaluacion):
    def historia(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "fijo", "limite_seg": 900})
        i = self.abrir(a["id"])["intento"]["id"]
        refs = self.refs_cerradas(i)
        self.latir_hasta(i, 40)
        self.api.post(f"{BASE}/intentos/{i}/incidentes/", {**self.alumno(), "incidentes": [{"tipo": "salida_de_app", "ref_cliente": "x"}]}, format="json")
        self.avanzar(minutos=2)                                                           # sin señal: se suspende
        self.estado(i)
        self.accion(f"/intentos/{i}/reactivar/")
        self.latir_hasta(i, 20)
        self.responder(i, [self.r(refs[0], 1, respuesta_correcta(refs[0]))])
        self.entregar(i, confirmar=True)
        return a, i

    def test_la_linea_de_tiempo_cuenta_la_historia_en_orden(self):
        a, i = self.historia()
        e = self.ver(f"/intentos/{i}/")
        lineas = e["linea_de_tiempo"]
        self.assertEqual([x["en"] for x in lineas], sorted(x["en"] for x in lineas))
        tipos = [x["tipo"] for x in lineas]
        self.assertEqual((tipos[0], tipos[-1]), ("intento_abierto", "entregado"))
        for esperado in ("salida_de_app", "desconexion", "pausa", "reactivado"):
            self.assertIn(esperado, tipos)
        self.assertEqual(e["intento"]["origen_entrega"], "alumno")
        self.assertEqual((len(e["pausas"]), e["pausas"][0]["causa"], e["pausas"][0]["reactivado_por"]), (1, "sin_latido", self.docente_id))
        self.assertEqual(e["resumen_incidentes"]["total"], len(e["incidentes"]))

    def test_el_expediente_es_de_solo_lectura(self):
        a, i = self.historia()
        for metodo in ("post", "put", "patch", "delete"):
            r = getattr(self.api, metodo)(f"{BASE}/intentos/{i}/", {"actor": self.docente_id}, format="json")
            self.assertEqual(r.status_code, 405, metodo)

    def test_el_expediente_de_un_intento_que_no_existe_es_404(self):
        self.assertEqual(self.api.get(f"{BASE}/intentos/no-existe/", {"actor": self.docente_id}).status_code, 404)


class AnularTests(BaseEvaluacion):
    """INV-018: el sistema no anula. Anular es de una persona, con su nombre y un motivo, sobre un intento ya entregado."""

    def entregado(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        self.entregar(i, confirmar=True)
        return a, i

    def test_el_profesor_anula_con_su_nombre_y_su_motivo_y_queda_a_la_vista(self):
        a, i = self.entregado()
        r = self.accion(f"/intentos/{i}/anular/", {"motivo": "Se detectó otro dispositivo"})
        self.assertEqual((r["estado"], r["anulado_por"], r["motivo"]), ("anulado", self.docente_id, "Se detectó otro dispositivo"))
        fila = self.fila(i)
        self.assertEqual((fila.estado, fila.anulado_por, fila.motivo_anulacion), ("anulado", self.docente_id, "Se detectó otro dispositivo"))
        self.assertIsNotNone(fila.anulado_en)
        self.assertEqual(self.eventos("evaluacion.intento_anulado.v1"), ["evaluacion.intento_anulado.v1"])
        asiento = maudit.Bitacora.objects.get(accion="evaluacion.anulada", objeto_id=i)
        self.assertEqual((asiento.valor_nuevo["anulado_por"], asiento.motivo), (self.docente_id, "Se detectó otro dispositivo"))
        panel = self.ver(f"/asignaciones/{a['id']}/panel/")["filas"][0]
        self.assertEqual((panel["estado"], panel["anulado_por"]), ("anulado", self.docente_id))
        self.assertEqual(self.ver(f"/intentos/{i}/")["linea_de_tiempo"][-1]["tipo"], "anulado")

    def test_sin_motivo_no_se_anula(self):
        a, i = self.entregado()
        for motivo in ("", "  ", "ab"):
            r = self.accion(f"/intentos/{i}/anular/", {"motivo": motivo}, esperado=400)
            self.assertEqual(r["codigo"], "datos_invalidos", motivo)
        self.assertEqual(self.fila(i).estado, "calificado")

    def test_sin_una_persona_identificada_no_se_anula(self):
        a, i = self.entregado()
        r = self.api.post(f"{BASE}/intentos/{i}/anular/", {"motivo": "Un motivo cualquiera"}, format="json")      # sin `actor` ni sesión
        self.assertIn(r.status_code, (400, 403), r.content)
        self.assertEqual(self.fila(i).estado, "calificado")

    def test_el_alumno_no_anula_ni_el_sistema(self):
        a, i = self.entregado()
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual(alumno.post(f"{BASE}/intentos/{i}/anular/", {"motivo": "No quiero esta nota"}, format="json").status_code, 403)
        # el barrido del nodo, el cierre por plazo y el tiempo agotado entregan: ninguno anula (INV-018)
        self.assertEqual(m.Intento.objects.filter(estado="anulado").count(), 0)

    def test_se_anula_lo_entregado_no_lo_que_sigue_en_curso_y_una_vez(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        self.accion(f"/intentos/{i}/anular/", {"motivo": "Todavía presenta"}, esperado=409)
        self.entregar(i, confirmar=True)
        self.accion(f"/intentos/{i}/anular/", {"motivo": "Ahora sí lo anulo"})
        self.accion(f"/intentos/{i}/anular/", {"motivo": "Otra vez lo anulo"}, esperado=409)

    def test_un_suspendido_no_se_anula_primero_se_cierra_a_la_fuerza_y_luego_si(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        i = self.abrir(a["id"])["intento"]["id"]
        self.latir_hasta(i, 20)
        self.avanzar(minutos=2)
        self.assertEqual(self.estado(i)["intento"]["estado"], "pausado_desconexion")
        self.accion(f"/intentos/{i}/anular/", {"motivo": "No volvió al aula"}, esperado=409)
        self.accion(f"/intentos/{i}/cerrar/")
        r = self.accion(f"/intentos/{i}/anular/", {"motivo": "No volvió al aula"})
        self.assertEqual((r["estado"], r["anulado_por"]), ("anulado", self.docente_id))

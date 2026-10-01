"""
Incidentes y bloqueo de la tableta (FUN-117, CAP-066, BR-077, D-12, D-13; TST-077): la tableta informa lo que vio y lo que logró bloquear, el nodo lo
registra y lo muestra al profesor, y NADA de eso invalida ni cambia el intento. Un bloqueo parcial se informa, no se esconde.
"""
from __future__ import annotations

from audit import models as maudit

from .. import models as m
from .base import BASE, SEG, BaseEvaluacion, respuesta_correcta

TODAS = {"sistema": True, "app": True, "capturas": True, "pantallas": True}


class IncidentesDeLaTabletaTests(BaseEvaluacion):
    def setUp(self):
        super().setUp()
        self.a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        self.i = self.abrir(self.a["id"])["intento"]["id"]

    def informar(self, incidentes: list[dict], esperado: int = 200, hw: str | None = None, alumno_id: str | None = None, intento_id: str | None = None):
        r = self.api.post(f"{BASE}/intentos/{intento_id or self.i}/incidentes/", {**self.alumno(hw, alumno_id), "incidentes": incidentes}, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def test_tst_077_una_salida_de_la_app_se_registra_y_el_intento_sigue_valido(self):
        cuerpo = self.informar([{"tipo": "salida_de_app", "ref_cliente": "c-1", "detalle": {"segundos": 4}}])
        self.assertEqual((cuerpo["registrados"], cuerpo["duplicados"], cuerpo["estado"]), (1, 0, "en_curso"))
        fila = m.Incidente.objects.get(intento_id=self.i)
        self.assertEqual((fila.tipo, fila.origen, fila.severidad, fila.resolucion, fila.detalle), ("salida_de_app", "tableta", "informativa", "registrado", {"segundos": 4}))
        self.assertEqual(fila.dispositivo_id, self.tableta_juan["id"])
        self.assertEqual(self.fila(self.i).estado, "en_curso")
        self.assertEqual(len(self.eventos("evaluacion.incidente_registrado.v1")), 1)
        asiento = maudit.Bitacora.objects.get(accion="evaluacion.incidente.registrado")
        self.assertEqual((asiento.objeto_id, asiento.valor_nuevo["tipo"]), (fila.id, "salida_de_app"))

    def test_br_077_muchos_incidentes_no_anulan_ni_impiden_responder_y_entregar(self):
        for n in range(10):
            self.informar([{"tipo": "salida_de_app", "ref_cliente": f"s-{n}"}, {"tipo": "regreso_a_app", "ref_cliente": f"r-{n}"}])
        self.informar([{"tipo": "pantalla_adicional", "ref_cliente": "p-1"}, {"tipo": "tecla_bloqueada", "ref_cliente": "t-1"}])
        self.latir_hasta(self.i, 20)
        cerradas = self.refs_cerradas(self.i)
        self.responder(self.i, [self.r(cerradas[0], 1, respuesta_correcta(cerradas[0]))])
        self.entregar(self.i, confirmar=True)
        fila = self.fila(self.i)
        self.assertIn(fila.estado, ("calificado", "en_revision_docente"))
        self.assertEqual((fila.anulado_por, fila.anulado_en), ("", None))
        self.assertEqual(m.Incidente.objects.filter(intento_id=self.i).count(), 22)

    def test_inv_005_reenviar_la_cola_de_incidentes_no_duplica_nada(self):
        lote = [{"tipo": "salida_de_app", "ref_cliente": "c-1"}, {"tipo": "regreso_a_app", "ref_cliente": "c-2"}]
        self.informar(lote)
        otra_vez = self.informar(lote)
        self.assertEqual((otra_vez["registrados"], otra_vez["duplicados"]), (0, 2))
        self.assertEqual(m.Incidente.objects.filter(intento_id=self.i).count(), 2)
        self.assertEqual(len(self.eventos("evaluacion.incidente_registrado.v1")), 2)
        self.assertEqual(maudit.Bitacora.objects.filter(accion="evaluacion.incidente.registrado").count(), 2)

    def test_la_tableta_solo_informa_lo_que_ella_ve_no_fabrica_hechos_del_nodo_ni_del_profesor(self):
        for tipo in ("reactivado", "degradacion", "desconexion", "tiempo_agotado", "cambio_de_dispositivo", "admitido_bajo_nivel", "no_existe"):
            cuerpo = self.informar([{"tipo": "salida_de_app", "ref_cliente": f"ok-{tipo}"}, {"tipo": tipo}], esperado=400)
            self.assertEqual(cuerpo["codigo"], "datos_invalidos", tipo)
        self.assertEqual(m.Incidente.objects.filter(intento_id=self.i).count(), 0)     # el lote entero se rechaza: nada a medias

    def test_la_peticion_se_valida(self):
        for incidentes in ([], None, "hola", [{"detalle": {}}], [{"tipo": ""}]):
            self.informar(incidentes, esperado=400)
        self.informar([{"tipo": "salida_de_app"}] * 101, esperado=400)

    def test_la_hora_que_cuenta_la_tableta_solo_vale_si_es_plausible(self):
        self.avanzar(seg=30)
        ahora = self.t
        self.informar([
            {"tipo": "salida_de_app", "ref_cliente": "a", "ocurrido_en": ahora - 4 * SEG, "ocurrido_en_tableta": 12345},
            {"tipo": "regreso_a_app", "ref_cliente": "b", "ocurrido_en": ahora + 60 * SEG},                       # del futuro
            {"tipo": "tecla_bloqueada", "ref_cliente": "c", "ocurrido_en": ahora - 72 * 3_600_000},               # de antes de ayer
            {"tipo": "cierre_bloqueado", "ref_cliente": "d", "ocurrido_en": "mañana"},                           # no es un instante
        ])
        por_ref = {x.ref_cliente: x for x in m.Incidente.objects.filter(intento_id=self.i)}
        self.assertEqual((por_ref["a"].ocurrido_en, por_ref["a"].reportado_en_tableta), (ahora - 4 * SEG, 12345))
        self.assertEqual([por_ref[k].ocurrido_en for k in "bcd"], [ahora] * 3)                                   # vale la hora de recepción

    def test_el_panel_cuenta_por_severidad_y_el_expediente_los_ordena_en_la_linea_de_tiempo(self):
        self.avanzar(seg=10)
        self.informar([{"tipo": "salida_de_app", "ref_cliente": "1"}, {"tipo": "regreso_a_app", "ref_cliente": "2"},
                       {"tipo": "pantalla_adicional", "ref_cliente": "3"}])
        resumen = self.ver(f"/asignaciones/{self.a['id']}/panel/")["filas"][0]["incidentes"]
        self.assertEqual((resumen["total"], resumen["informativa"], resumen["atencion"], resumen["alta"]), (3, 2, 1, 0))
        expediente = self.ver(f"/intentos/{self.i}/")
        tipos = [x["tipo"] for x in expediente["linea_de_tiempo"]]
        self.assertEqual(tipos[0], "intento_abierto")
        self.assertEqual(sorted(tipos[1:]), ["pantalla_adicional", "regreso_a_app", "salida_de_app"])
        self.assertEqual(expediente["resumen_incidentes"]["total"], 3)
        self.assertNotIn("anular", " ".join(expediente))                                  # el expediente es sólo lectura: ni ofrece anular

    def test_el_alumno_no_lee_incidentes_y_el_expediente_es_del_profesor(self):
        self.informar([{"tipo": "salida_de_app"}])
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual(alumno.get(f"{BASE}/intentos/{self.i}/").status_code, 403)

    def test_solo_una_tableta_del_intento_informa(self):
        self.registrar("hw-intrusa", "Intrusa", capacidad="supervisado")
        cuerpo = self.informar([{"tipo": "salida_de_app"}], esperado=403, hw="hw-intrusa")
        self.assertEqual(cuerpo["codigo"], "dispositivo_ajeno")
        otro, hw = self.alumno_con_tableta("Otro", "500001", capacidad="supervisado")
        self.informar([{"tipo": "salida_de_app"}], esperado=404, hw=hw, alumno_id=otro)
        self.assertEqual(m.Incidente.objects.count(), 0)

    def test_informar_despues_de_entregar_sigue_valiendo_como_evidencia(self):
        self.entregar(self.i, confirmar=True)
        self.informar([{"tipo": "regreso_a_app", "ref_cliente": "x"}])
        self.assertEqual(self.incidentes(self.i), ["regreso_a_app"])


class BloqueoTests(BaseEvaluacion):
    """D-12: el nodo DECIDE qué capas se piden; la tableta aplica y DICE lo que logró. El nodo no presume que se aplicó."""

    def setUp(self):
        super().setUp()
        self.ana, self.hw_ana = self.alumno_con_tableta("Ana", "A-100", "controlado")
        self.a = self.crear_asignacion("controlado", tiempo={"modo": "sin_limite"})
        apertura = self.abrir(self.a["id"], hw=self.hw_ana, alumno_id=self.ana)
        self.i, self.plan = apertura["intento"]["id"], apertura["plan_bloqueo"]

    def informar(self, resultado: str, capas: dict | None = None, esperado: int = 200, motivo: str = "", hw: str | None = None, **extra):
        cuerpo = {**self.alumno(hw or self.hw_ana, self.ana), "resultado": resultado, **extra}
        if capas is not None:
            cuerpo["capas"] = capas
        if motivo:
            cuerpo["motivo"] = motivo
        r = self.api.post(f"{BASE}/intentos/{self.i}/bloqueo/", cuerpo, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json()

    def test_el_plan_de_una_tableta_que_garantiza_el_control_pide_todas_las_capas(self):
        self.assertEqual(self.plan, {
            "nivel": "controlado", "nivel_exigido": "controlado", "capacidad": "controlado", "capa_sistema": True, "capa_app": True,
            "registrar_salidas": True, "registrar_consultas": False, "bloquear_capturas": True, "cubrir_pantallas_extra": True, "latido_seg": 5,
            "parcial": False})
        self.assertEqual(self.estado(self.i, self.hw_ana, self.ana)["plan_bloqueo"], self.plan)

    def test_aplicado_se_guarda_en_el_intento_y_no_deja_incidente(self):
        r = self.informar("aplicado", TODAS)
        self.assertEqual((r["incidente"], r["bloqueo"]["resultado"], r["bloqueo"]["capas"]), (None, "aplicado", TODAS))
        self.assertEqual(self.fila(self.i).bloqueo["resultado"], "aplicado")
        self.assertEqual(self.incidentes(self.i), [])

    def test_un_bloqueo_parcial_o_fallido_se_informa_y_el_intento_sigue(self):
        r = self.informar("parcial", {**TODAS, "sistema": False}, motivo="Lock Task no concedido")
        self.assertEqual(r["incidente"], "bloqueo_parcial")
        r = self.informar("fallido", {c: False for c in TODAS}, motivo="Sin Device Owner")
        self.assertEqual(r["incidente"], "bloqueo_fallido")
        fila = {x.tipo: x for x in m.Incidente.objects.filter(intento_id=self.i)}
        self.assertEqual((fila["bloqueo_parcial"].severidad, fila["bloqueo_fallido"].severidad), ("atencion", "alta"))
        self.assertEqual(fila["bloqueo_fallido"].detalle["motivo"], "Sin Device Owner")
        self.assertEqual(self.fila(self.i).estado, "en_curso")
        # el profesor lo ve en el panel: sube en la lista
        panel = self.ver(f"/asignaciones/{self.a['id']}/panel/")
        self.assertEqual([(f["bloqueo"], f["incidentes"]["alta"]) for f in panel["filas"] if f["alumno_id"] == self.ana], [({"resultado": "fallido"}, 1)])

    def test_el_mismo_informe_repetido_no_duplica_el_incidente_pero_uno_distinto_si(self):
        capas = {**TODAS, "sistema": False}
        self.informar("parcial", capas, motivo="a")
        self.informar("parcial", capas, motivo="a")
        self.assertEqual(self.incidentes(self.i), ["bloqueo_parcial"])
        self.informar("parcial", capas, motivo="b")
        self.assertEqual(self.incidentes(self.i), ["bloqueo_parcial", "bloqueo_parcial"])

    def test_soltar_el_bloqueo_con_el_examen_en_marcha_es_un_incidente_alto(self):
        r = self.informar("liberado", {c: False for c in TODAS}, motivo="El usuario salió de Lock Task")
        self.assertEqual(r["incidente"], "bloqueo_liberado")
        self.assertEqual(m.Incidente.objects.get(intento_id=self.i, tipo="bloqueo_liberado").severidad, "alta")

    def test_liberar_el_bloqueo_al_entregar_es_lo_normal_y_no_alarma(self):
        self.entregar(self.i, hw=self.hw_ana, alumno_id=self.ana, confirmar=True)
        r = self.informar("liberado", {c: False for c in TODAS})
        self.assertEqual((r["incidente"], self.incidentes(self.i)), (None, []))

    def test_la_capacidad_que_se_degrada_en_pleno_examen_vuelve_parcial_el_plan_y_se_informa(self):
        e = self.latido(self.i, hw=self.hw_ana, alumno_id=self.ana, capacidad_control="supervisado")
        self.assertEqual((e["plan_bloqueo"]["capa_sistema"], e["plan_bloqueo"]["capa_app"], e["plan_bloqueo"]["parcial"]), (False, True, True))
        r = self.informar("parcial", {**TODAS, "sistema": False}, motivo="Se perdió el Device Owner")
        self.assertEqual((r["incidente"], r["plan_bloqueo"]["parcial"]), ("bloqueo_parcial", True))
        fila = next(f for f in self.ver(f"/asignaciones/{self.a['id']}/panel/")["filas"] if f["alumno_id"] == self.ana)
        self.assertEqual((fila["dispositivo"]["capacidad"], fila["dispositivo"]["alcanza"]), ("supervisado", False))

    def test_en_supervisado_no_se_pide_la_capa_del_sistema_y_un_fallo_no_alarma(self):
        a = self.crear_asignacion("supervisado", tiempo={"modo": "sin_limite"})
        apertura = self.abrir(a["id"], hw=self.hw_ana, alumno_id=self.ana)
        plan = apertura["plan_bloqueo"]
        self.assertEqual((plan["capa_sistema"], plan["capa_app"], plan["registrar_consultas"], plan["parcial"]), (False, False, True, False))
        r = self.api.post(f"{BASE}/intentos/{apertura['intento']['id']}/bloqueo/", {**self.alumno(self.hw_ana, self.ana), "resultado": "fallido"}, format="json")
        self.assertEqual((r.status_code, r.json()["incidente"]), (200, None))

    def test_en_abierto_no_se_pide_nada_y_el_latido_se_espacia(self):
        a = self.crear_asignacion("abierto", tiempo={"modo": "sin_limite"})
        plan = self.abrir(a["id"], hw=self.hw_ana, alumno_id=self.ana)["plan_bloqueo"]
        self.assertEqual((plan["capa_sistema"], plan["capa_app"], plan["registrar_salidas"], plan["bloquear_capturas"], plan["latido_seg"]),
                         (False, False, False, False, 10))

    def test_el_informe_se_valida(self):
        for cuerpo in ({"resultado": ""}, {"resultado": "mas_o_menos"}, {"resultado": "aplicado", "capas": ["sistema"]}):
            r = self.api.post(f"{BASE}/intentos/{self.i}/bloqueo/", {**self.alumno(self.hw_ana, self.ana), **cuerpo}, format="json")
            self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"), cuerpo)

    def test_las_capas_que_no_se_mencionan_cuentan_como_no_logradas(self):
        r = self.informar("parcial", {"app": True})
        self.assertEqual(r["bloqueo"]["capas"], {"sistema": False, "app": True, "capturas": False, "pantallas": False})

    def test_solo_una_tableta_del_intento_informa_su_bloqueo(self):
        self.registrar("hw-intrusa", "Intrusa", capacidad="controlado")
        r = self.informar("aplicado", TODAS, esperado=403, hw="hw-intrusa")
        self.assertEqual(r["codigo"], "dispositivo_ajeno")
        self.assertEqual(self.fila(self.i).bloqueo, {})

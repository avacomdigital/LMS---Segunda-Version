"""
El paquete de estudio (CAP-047, FUN-084, FUN-085, BR-054, D-7, D-8): sólo en un aparato asignado a la persona; el manifiesto canónico y su huella;
los archivos con su tamaño y su SHA-256, reanudables con `Range`; confirmar con la huella correcta; vigencia y versión del curso; retirar y volver a pedir.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile

from django.conf import settings
from django.test import override_settings

from classroom_engine.dominio import curso as curso_aula

from .. import models as m
from .. import servicios
from .base import BASE, CURSO, LECCION_1, BaseEstudio

MSG_046 = "Este material está disponible durante la clase. Para llevártelo necesitas una tableta asignada a ti."
DIA_MS = 24 * 60 * 60 * 1000
T0 = 1_800_000_000_000


def canonico(manifiesto: dict) -> bytes:
    sin = {k: v for k, v in manifiesto.items() if k != "huella"}
    return json.dumps(sin, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class BasePaquetes(BaseEstudio):
    def setUp(self):
        super().setUp()
        self.a = self.crear_asignacion()

    def solicitar(self, hw: str | None = None, asignacion_id: str | None = None, **extra):
        return self.enviar("post", "/paquetes/", {"asignacion_id": asignacion_id or self.a["id"], **extra}, hw=hw)

    def paquete(self, hw: str | None = None, **extra) -> dict:
        """Pide el paquete de la asignación en el aparato de Juan y devuelve el `paquete`."""
        return self.json_ok(self.solicitar(hw, **extra), 201)["paquete"]

    def manifiesto(self, paquete_id: str, hw: str | None = None):
        return self.ver(f"/paquetes/{paquete_id}/manifiesto/", hw=hw)

    def archivo(self, paquete_id: str, media_ref: str, hw: str | None = None, **cabeceras):
        consulta = {"dispositivo": self.hw_juan if hw is None else hw}
        return self.api.get(f"{BASE}/paquetes/{paquete_id}/archivos/{media_ref}/", consulta, **cabeceras)

    def confirmar(self, paquete_id: str, huella: str, bytes_: int | None = None, hw: str | None = None):
        return self.enviar("post", f"/paquetes/{paquete_id}/confirmar/", {"huella": huella, "bytes": bytes_}, hw=hw)


class SolicitarPaqueteTests(BasePaquetes):
    def test_en_un_aparato_asignado_se_prepara_el_paquete_con_archivos_huella_y_vigencia(self):
        with self.reloj(T0):
            r = self.json_ok(self.solicitar(), 201)
        p = r["paquete"]
        self.assertEqual({k: r[k] for k in p}, p)                                   # los mismos campos viajan al nivel superior y dentro de `paquete`
        self.assertEqual((p["estado"], p["motivo"], p["asignacion_id"], p["dispositivo_id"], p["curso_version"]), ("solicitado", "", self.a["id"], self.propia["id"], "1.0.0"))
        self.assertEqual(sorted(x["media_ref"] for x in p["archivos"]), ["aud-summary", "img-particles", "pdf-lab-guide"])
        for x in p["archivos"]:
            self.assertEqual(set(x), {"media_ref", "clase", "mime", "bytes", "sha256"})
            self.assertGreater(x["bytes"], 0)
            self.assertRegex(x["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual({x["media_ref"]: x["clase"] for x in p["archivos"]}, {"aud-summary": "audio", "img-particles": "image", "pdf-lab-guide": "pdf"})
        self.assertEqual(sorted((x["media_ref"], x["motivo"]) for x in p["no_incluidos"]),
                         [("sim-phet-states", "simulacion_requiere_nodo"), ("vid-changes", "medio_no_disponible")])   # la simulación no viaja; el video no está en el ejemplo
        self.assertEqual(p["bytes_total"], sum(x["bytes"] for x in p["archivos"]))
        self.assertRegex(p["huella"], r"^[0-9a-f]{64}$")
        self.assertEqual((p["vigente_hasta"], p["solicitado_en"], p["disponible_en"], p["servidor_en"]), (T0 + 14 * DIA_MS, T0, None, T0))   # D-8: 14 días sin fecha
        fila = m.Paquete.objects.get(pk=p["id"])
        self.assertEqual((fila.alumno_id, fila.estado, fila.huella), (self.estudiante_id, "solicitado", p["huella"]))
        self.assertEqual(m.Asignacion.objects.get(pk=self.a["id"]).bytes_estimados, p["bytes_total"])      # «se afina al preparar el paquete»
        self.assertEqual(m.Tarea.objects.get(asignacion_id=self.a["id"]).estado, "pendiente")            # pedir el paquete es contacto, no empezar

    def test_la_descarga_ofrece_los_mismos_bytes_que_se_midieron(self):
        p = self.paquete()
        for x in p["archivos"]:
            r = self.archivo(p["id"], x["media_ref"])
            self.assertEqual((r.status_code, len(r.content), hashlib.sha256(r.content).hexdigest()), (200, x["bytes"], x["sha256"]))

    def test_volver_a_pedirlo_reutiliza_la_fila_y_refresca_manifiesto_y_vigencia(self):
        with self.reloj(T0):
            p1 = self.paquete()
        with self.reloj(T0 + 3 * DIA_MS):
            otra = self.json_ok(self.solicitar(), 200)["paquete"]                    # 200: no es una fila nueva
        self.assertEqual((otra["id"], otra["solicitado_en"], otra["vigente_hasta"]), (p1["id"], T0 + 3 * DIA_MS, T0 + 17 * DIA_MS))
        self.assertNotEqual(otra["huella"], p1["huella"])                           # el manifiesto es otro: cambian `generado_en` y `vigente_hasta`
        self.assertEqual(self.json_ok(self.manifiesto(otra["id"]))["huella"], otra["huella"])
        self.assertEqual(m.Paquete.objects.filter(asignacion_id=self.a["id"]).count(), 1)

    def test_con_fecha_limite_dura_hasta_la_fecha_mas_la_gracia_y_si_ya_paso_dura_lo_normal(self):
        con_fecha = self.crear_asignacion(fecha_limite=T0 + 10 * DIA_MS, gracia_min=30)
        with self.reloj(T0):
            p = self.json_ok(self.solicitar(asignacion_id=con_fecha["id"]), 201)["paquete"]
        self.assertEqual(p["vigente_hasta"], T0 + 10 * DIA_MS + 30 * 60_000)
        vencida = self.crear_asignacion(fecha_limite=T0 - DIA_MS)                    # plazo blando ya pasado: se sigue aceptando trabajo, el paquete no nace vencido
        with self.reloj(T0):
            p = self.json_ok(self.solicitar(asignacion_id=vencida["id"]), 201)["paquete"]
        self.assertEqual((p["estado"], p["vigente_hasta"]), ("solicitado", T0 + 14 * DIA_MS))

    def test_la_vigencia_por_defecto_sale_de_la_configuracion(self):
        with override_settings(AVACOM_ESTUDIO_VIGENCIA_DIAS=3), self.reloj(T0):
            p = self.paquete()
        self.assertEqual(p["vigente_hasta"], T0 + 3 * DIA_MS)

    def test_con_plazo_endurecido_vencido_ya_no_se_pide_paquete(self):
        dura = self.crear_asignacion(fecha_limite=T0 + 1_000, plazo="endurecido", gracia_min=1)
        with self.reloj(T0 + 10 * 60_000):
            r = self.solicitar(asignacion_id=dura["id"])
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "asignacion_cerrada"))

    def test_sin_aparato_es_400_y_una_asignacion_ajena_es_404(self):
        r = self.api.post(f"{BASE}/paquetes/", {"asignacion_id": self.a["id"]}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "falta_dispositivo"))
        r = self.enviar("post", "/paquetes/", {})
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))
        ajena = self.crear_asignacion(grupo_id=self.otro_grupo["id"])
        self.assertEqual(self.solicitar(asignacion_id=ajena["id"]).status_code, 404)

    def test_una_asignacion_cerrada_no_admite_paquete_nuevo(self):
        self.api.post(f"{BASE}/docente/asignaciones/{self.a['id']}/cerrar/", {}, format="json")
        r = self.solicitar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "asignacion_cerrada"))


class DescargaDenegadaTests(BasePaquetes):
    """BR-054: la descarga para trabajar sin el nodo sólo se permite en un aparato asignado nominalmente."""

    def test_en_un_aparato_compartido_es_403_con_evento_fila_denegada_y_el_mensaje_del_maestro(self):
        r = self.solicitar(hw=self.hw_compartida, alumno_id=self.estudiante_id)
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["mensaje"]), (403, "descarga_denegada", MSG_046))
        cuerpo = r.json()
        self.assertEqual((cuerpo["paquete"]["estado"], cuerpo["paquete"]["motivo"], cuerpo["paquete"]["archivos"], cuerpo["paquete"]["huella"]),
                         ("denegado", "dispositivo_compartido", [], None))
        fila = m.Paquete.objects.get(asignacion_id=self.a["id"])
        self.assertEqual((fila.estado, fila.motivo, fila.dispositivo_id, fila.alumno_id), ("denegado", "dispositivo_compartido", self.compartida["id"], self.estudiante_id))
        carga = m.EventoSalida.objects.get(tipo_evento="estudio.descarga.denegada.v1").carga
        self.assertEqual((carga["paquete_id"], carga["asignacion_id"], carga["alumno_id"], carga["dispositivo_id"], carga["motivo"]),
                         (fila.id, self.a["id"], self.estudiante_id, self.compartida["id"], "dispositivo_compartido"))
        self.assertEqual(m.Tarea.objects.filter(asignacion_id=self.a["id"]).count(), 1)     # la petición cuenta como contacto

    def test_pedirlo_otra_vez_no_duplica_la_fila_pero_deja_otro_evento(self):
        for _ in range(2):
            self.assertEqual(self.solicitar(hw=self.hw_compartida, alumno_id=self.estudiante_id).status_code, 403)
        self.assertEqual(m.Paquete.objects.count(), 1)
        self.assertEqual(len(self.eventos("estudio.descarga.denegada.v1")), 2)

    def test_un_paquete_denegado_no_sirve_ni_manifiesto_ni_archivos_ni_confirmacion(self):
        self.solicitar(hw=self.hw_compartida, alumno_id=self.estudiante_id)
        pid = m.Paquete.objects.get().id
        kw = {"hw": self.hw_compartida}
        for r in (self.ver(f"/paquetes/{pid}/manifiesto/", hw=self.hw_compartida, alumno_id=self.estudiante_id),
                  self.api.get(f"{BASE}/paquetes/{pid}/archivos/img-particles/", {"dispositivo": self.hw_compartida, "alumno_id": self.estudiante_id}),
                  self.enviar("post", f"/paquetes/{pid}/confirmar/", {"huella": "x" * 64, "alumno_id": self.estudiante_id}, **kw)):
            self.assertEqual((r.status_code, r.json()["codigo"]), (403, "descarga_denegada"))

    def test_asignado_a_otra_persona_es_403_descarga_denegada_con_motivo_dispositivo_ajeno_y_deja_constancia(self):
        """D-15: Ana estudia en la tableta de Juan (no hay 403 `dispositivo_ajeno`), pero no se lleva el material: 403 `descarga_denegada` con MSG-046."""
        ana_id = self.nuevo_alumno("Ana R.", "300111")
        ana = self.sesion("300111", "573920")
        r = self.enviar("post", "/paquetes/", {"asignacion_id": self.a["id"]}, hw=self.hw_juan, cliente=ana)       # Ana sobre la tableta de Juan
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["mensaje"]), (403, "descarga_denegada", MSG_046))
        self.assertEqual((r.json()["paquete"]["estado"], r.json()["paquete"]["motivo"]), ("denegado", "dispositivo_ajeno"))
        fila = m.Paquete.objects.get(asignacion_id=self.a["id"])
        self.assertEqual((fila.alumno_id, fila.dispositivo_id, fila.estado, fila.motivo), (ana_id, self.propia["id"], "denegado", "dispositivo_ajeno"))
        self.assertEqual(m.EventoSalida.objects.get(tipo_evento="estudio.descarga.denegada.v1").carga["motivo"], "dispositivo_ajeno")
        # y a Juan, dueño del aparato, no se le niega nada
        self.assertEqual(self.solicitar().status_code, 201)

    def test_lo_mismo_si_el_alumno_no_tiene_sesion_y_solo_se_declara(self):
        ana_id = self.nuevo_alumno("Ana R.", "300111")
        r = self.solicitar(alumno_id=ana_id)                                     # sin sesión: Ana declarada sobre la tableta de Juan
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["paquete"]["motivo"]), (403, "descarga_denegada", "dispositivo_ajeno"))
        self.assertEqual(m.Paquete.objects.get().alumno_id, ana_id)
        r = self.solicitar(alumno_id=self.estudiante_id)                          # y el dueño, declarándose, sí se lo lleva
        self.assertEqual(r.status_code, 201)
        self.assertEqual(m.Paquete.objects.count(), 2)

    def test_con_paquete_permitido_falso_es_403_con_su_propio_mensaje(self):
        cerrada = self.crear_asignacion(paquete_permitido=False)
        r = self.solicitar(asignacion_id=cerrada["id"])
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["paquete"]["motivo"]), (403, "descarga_denegada", "paquete_no_permitido"))
        self.assertNotEqual(r.json()["mensaje"], MSG_046)
        lista = {x["id"]: x for x in self.json_ok(self.ver("/asignaciones/"))["asignaciones"]}
        self.assertEqual(lista[cerrada["id"]]["descarga"], {"permitida": False, "motivo": "paquete_no_permitido"})
        self.assertEqual(lista[self.a["id"]]["descarga"], {"permitida": True, "motivo": ""})

    def test_un_aparato_nuevo_se_registra_como_compartido_y_se_le_niega(self):
        r = self.solicitar(hw="hw-recien-llegada", alumno_id=self.estudiante_id)
        self.assertEqual((r.status_code, r.json()["paquete"]["motivo"]), (403, "dispositivo_compartido"))

    def test_si_despues_se_le_asigna_el_aparato_a_la_persona_ya_puede_llevarse_el_material(self):
        self.solicitar(hw=self.hw_compartida, alumno_id=self.estudiante_id)
        self.assertEqual(m.Paquete.objects.get().estado, "denegado")
        self.admin.post(f"/api/dispositivos/{self.compartida['id']}/asignar/", {"alumno_id": self.estudiante_id}, format="json")
        r = self.solicitar(hw=self.hw_compartida)
        self.assertEqual(r.status_code, 200)                                          # reutiliza la fila: pasa de denegado a solicitado
        self.assertEqual((r.json()["paquete"]["estado"], m.Paquete.objects.count()), ("solicitado", 1))

    def test_un_aparato_bloqueado_no_pide_paquete(self):
        from device_manager import models as m9
        m9.Dispositivo.objects.filter(pk=self.propia["id"]).update(bloqueado=True)
        r = self.solicitar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_bloqueado"))


class ManifiestoYHuellaTests(BasePaquetes):
    def test_el_manifiesto_trae_la_leccion_sin_claves_y_su_huella_es_el_sha256_del_json_canonico(self):
        p = self.paquete()
        man = self.json_ok(self.manifiesto(p["id"]))
        self.assertEqual(set(man), {"paquete_id", "asignacion", "curso", "leccion_ref", "vigente_hasta", "generado_en", "leccion", "archivos", "no_incluidos", "huella"})
        self.assertEqual((man["paquete_id"], man["leccion_ref"], man["vigente_hasta"], man["generado_en"]), (p["id"], LECCION_1, p["vigente_hasta"], p["solicitado_en"]))
        self.assertEqual(man["huella"], hashlib.sha256(canonico(man)).hexdigest())      # el contrato: SHA-256 hexadecimal del JSON canónico sin `huella`
        self.assertEqual(man["huella"], p["huella"])
        self.assertEqual((man["archivos"], man["no_incluidos"]), (p["archivos"], p["no_incluidos"]))
        self.assertIsNone(curso_aula.contiene_clave(man["leccion"]))
        self.assertEqual([o["tipo"] for o in man["leccion"]["objetos"]], ["lecture", "explanation", "simulation_lab", "activity"])
        self.assertEqual((man["curso"]["curso_ref"], man["curso"]["version"]), (CURSO, "1.0.0"))
        self.assertEqual(man["asignacion"]["id"], self.a["id"])
        self.assertEqual(len(man["asignacion"]["bloques"]), 7)
        self.assertNotIn("tarea", man["asignacion"])                                # sólo lo estable: nada del avance ni de las fechas
        self.assertNotIn("fecha_limite", man["asignacion"])

    def test_pide_la_leccion_y_pasa_a_descargandose(self):
        with self.reloj(T0):
            p = self.paquete()
        with self.reloj(T0 + 5_000):
            self.json_ok(self.manifiesto(p["id"]))
        fila = m.Paquete.objects.get(pk=p["id"])
        self.assertEqual((fila.estado, fila.descarga_iniciada_en), ("descargandose", T0 + 5_000))
        self.assertEqual(self.json_ok(self.ver(f"/paquetes/{p['id']}/"))["estado"], "descargandose")

    def test_la_huella_no_cambia_entre_lecturas_ni_porque_el_profesor_mueva_una_fecha(self):
        p = self.paquete()
        h1 = self.json_ok(self.manifiesto(p["id"]))["huella"]
        self.api.patch(f"{BASE}/docente/asignaciones/{self.a['id']}/", {"fecha_limite": T0 * 2, "plazo": "endurecido", "consigna": "otra"}, format="json")
        h2 = self.json_ok(self.manifiesto(p["id"]))["huella"]
        self.assertEqual((h1, h2), (p["huella"], p["huella"]))

    def test_el_manifiesto_normaliza_los_numeros_enteros_para_que_otro_serializador_llegue_a_la_misma_huella(self):
        man = self.json_ok(self.manifiesto(self.paquete()["id"]))
        actividad = next(o for o in man["leccion"]["objetos"] if o["tipo"] == "activity")
        self.assertIsInstance(actividad["puntos_totales"], int)                     # 13.0 viaja como 13 (el hash y el JSON coinciden con cualquier biblioteca)
        self.assertIn('"puntos_totales":13,', canonico(man).decode())

    def test_es_del_aparato_que_lo_pidio_y_de_su_dueno(self):
        p = self.paquete()
        ana_id, hw_ana = self.alumno_con_tableta("Ana R.", "300111")
        r = self.manifiesto(p["id"], hw=hw_ana)                                    # Ana, en su propia tableta, con el id de Juan
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "no_es_el_titular"))
        self.assertEqual(self.manifiesto("no-existe").status_code, 404)
        otra = self.registrar("hw-otra-de-juan")
        self.asignar(otra["id"], self.estudiante_id)
        self.assertEqual(self.manifiesto(p["id"], hw="hw-otra-de-juan").status_code, 404)    # el paquete es de UN aparato


class ArchivosYRangeTests(BasePaquetes):
    def test_el_archivo_lleva_su_sha256_como_etag_y_se_reanuda_con_range(self):
        p = self.paquete()
        x = next(a for a in p["archivos"] if a["media_ref"] == "img-particles")
        r = self.archivo(p["id"], "img-particles")
        self.assertEqual((r.status_code, r["ETag"], r["Accept-Ranges"], r["Content-Type"]), (200, f"\"{x['sha256']}\"", "bytes", "image/png"))
        total = r.content
        parcial = self.archivo(p["id"], "img-particles", HTTP_RANGE="bytes=8-15")
        self.assertEqual((parcial.status_code, parcial.content, parcial["Content-Range"]), (206, total[8:16], f"bytes 8-15/{len(total)}"))
        resto = self.archivo(p["id"], "img-particles", HTTP_RANGE=f"bytes={len(total) - 4}-")
        self.assertEqual((resto.status_code, resto.content), (206, total[-4:]))
        self.assertEqual(self.archivo(p["id"], "img-particles", HTTP_RANGE=f"bytes={len(total) + 10}-").status_code, 416)
        cabeza = self.api.head(f"{BASE}/paquetes/{p['id']}/archivos/img-particles/", {"dispositivo": self.hw_juan})
        self.assertEqual((cabeza.status_code, cabeza["Content-Length"], cabeza.content), (200, str(len(total)), b""))

    def test_solo_los_medios_de_archivos_se_sirven(self):
        p = self.paquete()
        for ref in ("vid-changes", "sim-phet-states", "img-ice-water-steam", "no-existe"):     # no incluidos, simulación, de otra lección, inexistente
            with self.subTest(ref=ref):
                self.assertEqual(self.archivo(p["id"], ref).status_code, 404)

    def test_es_del_aparato_de_su_dueno(self):
        p = self.paquete()
        ana_id, hw_ana = self.alumno_con_tableta("Ana R.", "300111")
        r = self.archivo(p["id"], "img-particles", hw=hw_ana)
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "no_es_el_titular"))


class ConfirmarYRetirarTests(BasePaquetes):
    def test_con_la_huella_correcta_queda_disponible_y_emite_el_evento(self):
        with self.reloj(T0):
            p = self.paquete()
        man = self.json_ok(self.manifiesto(p["id"]))
        with self.reloj(T0 + 60_000):
            r = self.json_ok(self.confirmar(p["id"], man["huella"], p["bytes_total"]))
        self.assertEqual((r["estado"], r["disponible_en"], r["huella"], r["paquete"]["estado"]), ("disponible", T0 + 60_000, p["huella"], "disponible"))
        carga = m.EventoSalida.objects.get(tipo_evento="estudio.paquete.descargado.v1").carga
        self.assertEqual((carga["paquete_id"], carga["asignacion_id"], carga["alumno_id"], carga["dispositivo_id"], carga["bytes"], carga["huella"]),
                         (p["id"], self.a["id"], self.estudiante_id, self.propia["id"], p["bytes_total"], p["huella"]))
        self.json_ok(self.confirmar(p["id"], man["huella"], p["bytes_total"]))                # idempotente: no repite el evento
        self.assertEqual(len(self.eventos("estudio.paquete.descargado.v1")), 1)
        lista = self.json_ok(self.ver("/asignaciones/"))
        self.assertEqual(lista["resumen"]["descargadas"], 1)
        self.assertEqual(lista["asignaciones"][0]["paquete"]["estado"], "disponible")
        self.assertEqual(lista["asignaciones"][0]["paquete"]["huella"], p["huella"])

    def test_con_otra_huella_es_409_y_el_paquete_no_cambia(self):
        p = self.paquete()
        self.json_ok(self.manifiesto(p["id"]))
        r = self.confirmar(p["id"], "0" * 64, p["bytes_total"])
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "huella_invalida"))
        self.assertEqual(m.Paquete.objects.get(pk=p["id"]).estado, "descargandose")
        self.assertEqual(self.eventos("estudio.paquete.descargado.v1"), [])
        self.assertEqual(self.enviar("post", f"/paquetes/{p['id']}/confirmar/", {}).status_code, 400)        # sin huella

    def test_retirar_borra_la_copia_deja_de_listarse_y_volver_a_pedirlo_la_reactiva(self):
        p = self.paquete()
        self.assertEqual([x["id"] for x in self.json_ok(self.ver("/paquetes/"))["paquetes"]], [p["id"]])
        r = self.json_ok(self.borrar(f"/paquetes/{p['id']}/"))
        self.assertEqual((r["retirado"], r["paquete_id"]), (True, p["id"]))
        self.assertIsNotNone(m.Paquete.objects.get(pk=p["id"]).retirado_en)          # nada se borra (CV-05)
        self.assertEqual(self.json_ok(self.ver("/paquetes/"))["paquetes"], [])
        self.assertEqual(self.ver(f"/paquetes/{p['id']}/").status_code, 404)
        self.assertIsNone(self.json_ok(self.ver("/asignaciones/"))["asignaciones"][0]["paquete"])
        self.assertEqual(self.borrar(f"/paquetes/{p['id']}/").status_code, 200)     # idempotente
        otra = self.json_ok(self.solicitar(), 200)["paquete"]
        self.assertEqual((otra["id"], otra["estado"]), (p["id"], "solicitado"))
        self.assertIsNone(m.Paquete.objects.get(pk=p["id"]).retirado_en)

    def test_el_paquete_de_otro_no_se_retira(self):
        p = self.paquete()
        ana_id, hw_ana = self.alumno_con_tableta("Ana R.", "300111")
        self.assertEqual(self.borrar(f"/paquetes/{p['id']}/", hw=hw_ana).status_code, 403)

    def test_el_estado_lo_ven_el_profesor_y_la_lista_de_paquetes(self):
        p = self.paquete()
        man = self.json_ok(self.manifiesto(p["id"]))
        self.json_ok(self.confirmar(p["id"], man["huella"]))
        d = self.json_ok(self.api.get(f"{BASE}/docente/asignaciones/{self.a['id']}/"))
        juan = d["alumnos"][0]
        self.assertEqual(juan["paquete"], {"estado": "disponible"})
        self.assertEqual(self.json_ok(self.ver(f"/paquetes/{p['id']}/"))["paquete"]["estado"], "disponible")


class VigenciaYVersionTests(BasePaquetes):
    def test_pasada_la_vigencia_el_paquete_vence_y_ya_no_sirve_hasta_actualizarlo(self):
        with self.reloj(T0):
            p = self.paquete()
            man = self.json_ok(self.manifiesto(p["id"]))
        despues = T0 + 15 * DIA_MS
        with self.reloj(despues):
            v = self.json_ok(self.ver(f"/paquetes/{p['id']}/"))
            self.assertEqual((v["estado"], v["motivo"]), ("vencido", "vigencia"))
            for r in (self.manifiesto(p["id"]), self.archivo(p["id"], "img-particles"), self.confirmar(p["id"], man["huella"])):
                self.assertEqual((r.status_code, r.json()["codigo"]), (410, "paquete_vencido"))
            lista = self.json_ok(self.ver("/paquetes/"))["paquetes"]
            self.assertEqual([x["estado"] for x in lista], ["vencido"])
        fila = m.Paquete.objects.get(pk=p["id"])
        self.assertEqual((fila.estado, fila.motivo), ("vencido", "vigencia"))          # se evalúa al leer y se persiste
        with self.reloj(despues + 1_000):
            nueva = self.json_ok(self.solicitar(), 200)["paquete"]                      # «Actualizar descarga»
        self.assertEqual((nueva["id"], nueva["estado"], nueva["motivo"], nueva["vigente_hasta"]), (p["id"], "solicitado", "", despues + 1_000 + 14 * DIA_MS))

    def test_la_lista_de_pendientes_tambien_evalua_la_vigencia_sin_leer_la_biblioteca(self):
        with self.reloj(T0):
            p = self.paquete()
        with self.reloj(T0 + 20 * DIA_MS):
            x = self.json_ok(self.ver("/asignaciones/"))["asignaciones"][0]
        self.assertEqual((x["paquete"]["estado"], x["paquete"]["motivo"]), ("vencido", "vigencia"))
        self.assertEqual(m.Paquete.objects.get(pk=p["id"]).estado, "vencido")

    def test_un_paquete_disponible_tambien_vence(self):
        with self.reloj(T0):
            p = self.paquete()
            man = self.json_ok(self.manifiesto(p["id"]))
            self.json_ok(self.confirmar(p["id"], man["huella"]))
        with self.reloj(T0 + 15 * DIA_MS):
            self.assertEqual(self.json_ok(self.ver(f"/paquetes/{p['id']}/"))["estado"], "vencido")

    def test_si_el_curso_tiene_una_version_nueva_el_paquete_venció_por_version(self):
        p = self.paquete()
        man = self.json_ok(self.manifiesto(p["id"]))
        with open(settings.AVACOM_AULA_CURSO_EJEMPLO, encoding="utf-8") as f:
            curso = json.load(f)
        curso["version"] = "2.0.0"
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "example.json")
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(curso, f)
            with override_settings(AVACOM_AULA_CURSO_EJEMPLO=ruta):
                v = self.json_ok(self.ver(f"/paquetes/{p['id']}/"))
                self.assertEqual((v["estado"], v["motivo"]), ("vencido", "version_nueva"))
                r = self.confirmar(p["id"], man["huella"])
                self.assertEqual((r.status_code, r.json()["codigo"]), (410, "paquete_vencido"))
                nuevo = self.json_ok(self.solicitar(), 200)["paquete"]                    # actualizar: pasa a la versión nueva
        self.assertEqual((nuevo["estado"], nuevo["curso_version"]), ("solicitado", "2.0.0"))

    def test_si_la_version_cambia_el_manifiesto_tambien_es_410(self):
        p = self.paquete()
        with open(settings.AVACOM_AULA_CURSO_EJEMPLO, encoding="utf-8") as f:
            curso = json.load(f)
        curso["version"] = "2.0.0"
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "example.json")
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(curso, f)
            with override_settings(AVACOM_AULA_CURSO_EJEMPLO=ruta):
                r = self.manifiesto(p["id"])
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["motivo"]), (410, "paquete_vencido", "version_nueva"))
        self.assertEqual(m.Paquete.objects.get(pk=p["id"]).motivo, "version_nueva")


class ConLaBibliotecaRealTests(BasePaquetes):
    """La fuente «biblioteca» de verdad: la API de Contenido v2 de pruebas en loopback. Los medios llegan como FLUJOS: el nodo los lee por
    trozos para medirlos y `Range` se pasa a la biblioteca."""

    MEDIOS = {
        "img-particles": ("image/png", b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 40),
        "aud-summary": ("audio/mpeg", bytes((i * 7) % 251 for i in range(200_000))),
        "pdf-lab-guide": ("application/pdf", b"%PDF-1.4\n" + b"x" * 50_000),
        "vid-changes": ("video/mp4", bytes((i * 13) % 253 for i in range(300_000))),
    }

    def test_los_medios_en_flujo_se_miden_por_trozos_y_el_range_llega_a_la_biblioteca(self):
        with self.host_de_contenido(self.MEDIOS):
            a = self.crear_asignacion(fuente="biblioteca")
            self.assertEqual(a["bytes_estimados"], sum(len(v[1]) for v in self.MEDIOS.values()))     # HEAD: Content-Length de cada medio
            p = self.json_ok(self.solicitar(asignacion_id=a["id"]), 201)["paquete"]
            por_ref = {x["media_ref"]: x for x in p["archivos"]}
            self.assertEqual(sorted(por_ref), ["aud-summary", "img-particles", "pdf-lab-guide", "vid-changes"])
            for ref, (tipo, datos) in self.MEDIOS.items():
                self.assertEqual((por_ref[ref]["bytes"], por_ref[ref]["sha256"]), (len(datos), hashlib.sha256(datos).hexdigest()))
            self.assertEqual(p["bytes_total"], sum(len(v[1]) for v in self.MEDIOS.values()))
            self.assertEqual([x["media_ref"] for x in p["no_incluidos"]], ["sim-phet-states"])
            video = self.MEDIOS["vid-changes"][1]
            parcial = self.archivo(p["id"], "vid-changes", HTTP_RANGE="bytes=1000-1999")
            self.assertEqual((parcial.status_code, b"".join(parcial.streaming_content)), (206, video[1000:2000]))
            completo = self.archivo(p["id"], "vid-changes")
            self.assertEqual(hashlib.sha256(b"".join(completo.streaming_content)).hexdigest(), por_ref["vid-changes"]["sha256"])
            man = self.json_ok(self.manifiesto(p["id"]))
            self.assertEqual(man["huella"], p["huella"])
            self.assertEqual(man["huella"], hashlib.sha256(canonico(man)).hexdigest())

    def test_un_medio_que_supera_el_tope_se_deja_fuera_del_paquete(self):
        with self.host_de_contenido(self.MEDIOS), override_settings(AVACOM_ESTUDIO_MEDIO_MAX_MB=0):
            a = self.crear_asignacion(fuente="biblioteca")
            p = self.json_ok(self.solicitar(asignacion_id=a["id"]), 201)["paquete"]
        self.assertEqual((p["archivos"], p["bytes_total"]), ([], 0))
        self.assertEqual({x["motivo"] for x in p["no_incluidos"]}, {"medio_demasiado_grande", "simulacion_requiere_nodo"})

    def test_sin_biblioteca_no_se_prepara_el_paquete(self):
        with self.host_de_contenido(self.MEDIOS) as host:
            a = self.crear_asignacion(fuente="biblioteca")
            host.detener()
            r = self.solicitar(asignacion_id=a["id"])
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["disponible"]), (503, "fuente_no_disponible", False))
        self.assertEqual(m.Paquete.objects.count(), 0)


class LiberarElEquipoConPaqueteTests(BasePaquetes):
    """FUN-093 · D-14: un equipo con un paquete de estudio activo no se libera hasta retirarlo (409 `paquete_sin_integrar`)."""

    def liberar(self):
        return self.admin.post(f"/api/dispositivos/{self.propia['id']}/liberar/", {}, format="json")

    def test_el_paquete_activo_lo_impide_y_retirarlo_lo_permite(self):
        p = self.paquete()
        r = self.liberar()
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["paquetes"]), (409, "paquete_sin_integrar", 1))
        man = self.json_ok(self.manifiesto(p["id"]))
        self.json_ok(self.confirmar(p["id"], man["huella"]))                          # disponible tampoco: sigue siendo material en el equipo
        self.assertEqual(self.liberar().status_code, 409)
        self.json_ok(self.borrar(f"/paquetes/{p['id']}/"))
        r = self.liberar()
        self.assertEqual((r.status_code, r.json()["perfil"], r.json()["asignado_a"]), (200, "compartido", None))
        # ya es del aula: el paquete se le niega a quien lo pida desde él
        r = self.solicitar(alumno_id=self.estudiante_id)
        self.assertEqual((r.status_code, r.json()["paquete"]["motivo"]), (403, "dispositivo_compartido"))

    def test_un_paquete_vencido_o_denegado_no_cuenta_como_material_en_el_equipo(self):
        with self.reloj(T0):
            self.paquete()
        with self.reloj(T0 + 20 * DIA_MS):
            self.assertEqual(self.liberar().status_code, 200)                       # venció por vigencia: ya no es material vigente


class PaquetesActivosParaMod009Tests(BasePaquetes):
    def test_la_interfaz_para_otros_modulos_cuenta_los_paquetes_activos_y_vigentes_de_un_equipo(self):
        self.assertEqual(servicios.paquetes_activos_en(self.propia["id"]), 0)
        with self.reloj(T0):
            p = self.paquete()
        self.assertEqual(servicios.paquetes_activos_en(self.propia["id"], T0 + 1), 1)
        self.assertEqual(servicios.paquetes_activos_en(self.propia["id"], T0 + 15 * DIA_MS), 0)     # vencido por vigencia: ya no cuenta
        self.assertEqual(servicios.paquetes_activos_en(self.compartida["id"], T0 + 1), 0)
        self.borrar(f"/paquetes/{p['id']}/")
        self.assertEqual(servicios.paquetes_activos_en(self.propia["id"], T0 + 1), 0)                 # retirado: ya no
        self.assertEqual(servicios.paquetes_activos_en(""), 0)

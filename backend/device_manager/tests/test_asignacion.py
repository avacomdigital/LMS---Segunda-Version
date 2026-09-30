"""
MOD-009 · perfil del equipo (009-06, 008-01, FUN-092, FUN-093): un equipo es del aula (`compartido`) o nominal de una persona (`asignado`). Sólo el dueño de
un equipo asignado se lleva en él los paquetes del modo de estudio. Asignar y liberar son de quien administra dispositivos (técnico y administrador); liberar
exige que el equipo no conserve un paquete de estudio activo.
"""
from __future__ import annotations

from unittest import mock

from django.db import IntegrityError, transaction

from acceso.tests.base import BaseAcceso
from expediente.models import Auditoria

from .. import models as m
from .. import servicios
from ..dominio import dispositivo as dom


class BaseAsignacion(BaseAcceso):
    def setUp(self):
        super().setUp()
        self.did = self.tableta["id"]

    def ruta(self, accion: str, did: str | None = None) -> str:
        return f"/api/dispositivos/{did or self.did}/{accion}/"

    def asignar(self, cliente=None, alumno_id: str | None = None, **extra):
        return (cliente or self.admin).post(self.ruta("asignar"), {"alumno_id": alumno_id or self.estudiante_id, **extra}, format="json")

    def liberar(self, cliente=None):
        return (cliente or self.admin).post(self.ruta("liberar"), {}, format="json")

    def tecnico(self):
        r = self.admin.post("/api/acceso/usuarios/", {
            "rol": "TECHNICIAN", "alias": "Técnico AVACOM", "persona": {"nombres": "Tomás", "apellidos": "Técnico"},
            "identificadores": [{"tipo": "DNI", "valor": "70.111.222", "es_login": True}], "secreto": "Tecnico.2026!Aula", "secreto_definitivo": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return self.sesion("70.111.222", "Tecnico.2026!Aula")


class PerfilDelEquipoTests(BaseAsignacion):
    def test_un_equipo_nuevo_es_compartido_y_no_tiene_dueno(self):
        d = self.api.get(f"/api/dispositivos/{self.did}/").json()
        self.assertEqual((d["perfil"], d["asignado_a"], d["asignado_a_id"], d["asignado_en"]), ("compartido", None, None, None))
        self.assertEqual(self.api.get("/api/dispositivos/").json()[0]["perfil"], "compartido")
        self.assertEqual(self.api.post("/api/dispositivos/latido/", {"identificador_hw": self.TABLETA}, format="json").json()["perfil"], "compartido")

    def test_la_base_de_datos_no_admite_un_equipo_asignado_sin_dueno_ni_uno_compartido_con_dueno(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Dispositivo.objects.filter(pk=self.did).update(perfil="asignado")
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Dispositivo.objects.filter(pk=self.did).update(asignado_a_id="alguien")
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Dispositivo.objects.filter(pk=self.did).update(perfil="prestado", asignado_a_id=None)
        m.Dispositivo.objects.filter(pk=self.did).update(perfil="asignado", asignado_a_id="alguien")       # así sí


class AsignarTests(BaseAsignacion):
    def test_asignar_lo_deja_a_nombre_de_la_persona_con_evento_y_bitacora(self):
        r = self.asignar()
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertEqual((d["perfil"], d["asignado_a"], d["id"]), ("asignado", {"id": self.estudiante_id, "rotulo": "Juan P."}, self.did))
        self.assertEqual((d["asignado_a_id"], d["asignado_en"] is not None), (self.estudiante_id, True))
        fila = m.Dispositivo.objects.get(pk=self.did)
        self.assertEqual((fila.perfil, fila.asignado_a_id), ("asignado", self.estudiante_id))
        evento = m.EventoSalida.objects.get(tipo_evento=dom.EV_ASIGNADO, agregado_id=self.did)
        self.assertEqual((evento.carga["dispositivo_id"], evento.carga["alumno_id"]), (self.did, self.estudiante_id))
        asiento = Auditoria.objects.get(accion="dispositivos.asignado", objeto_id=self.did)
        self.assertEqual((asiento.actor_id, asiento.valor_nuevo["asignado_a_id"], asiento.valor_anterior["perfil"]), (self.admin_id, self.estudiante_id, "compartido"))
        self.assertEqual(self.admin.get("/api/dispositivos/").json()[0]["asignado_a"]["rotulo"], "Juan P.")

    def test_asignar_a_la_misma_persona_es_idempotente(self):
        self.asignar()
        self.assertEqual(self.asignar().status_code, 200)
        self.assertEqual(m.EventoSalida.objects.filter(tipo_evento=dom.EV_ASIGNADO).count(), 1)

    def test_un_equipo_de_otra_persona_no_se_reasigna_primero_se_libera(self):
        self.asignar()
        otro = self.admin.post("/api/acceso/usuarios/", {
            "rol": "STUDENT", "alias": "Ana R.", "persona": {"nombres": "Ana", "apellidos": "R", "fecha_nacimiento": "2012-01-01"},
            "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": "300111", "es_login": True}], "secreto": "573920", "secreto_definitivo": True,
            "grupo_id": self.grupo["id"]}, format="json").json()["id"]
        r = self.asignar(alumno_id=otro)
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["asignado_a_id"]), (409, "dispositivo_ya_asignado", self.estudiante_id))
        self.assertEqual(m.Dispositivo.objects.get(pk=self.did).asignado_a_id, self.estudiante_id)
        self.assertEqual(self.liberar().status_code, 200)
        self.assertEqual(self.asignar(alumno_id=otro).json()["asignado_a"]["rotulo"], "Ana R.")

    def test_lo_mal_pedido_es_404_o_400(self):
        r = self.asignar(alumno_id="nadie")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "no_encontrado"))
        self.assertEqual(self.admin.post(self.ruta("asignar"), {}, format="json").status_code, 400)
        self.assertEqual(self.admin.post(self.ruta("asignar", "no-existe"), {"alumno_id": self.estudiante_id}, format="json").status_code, 404)
        self.assertEqual(m.Dispositivo.objects.get(pk=self.did).perfil, "compartido")

    def test_un_equipo_retirado_no_se_asigna(self):
        self.admin.patch(f"/api/dispositivos/{self.did}/", {"activo": False}, format="json")
        r = self.asignar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_inactivo"))

    def test_asignarlo_cierra_la_sesion_de_otro_alumno_en_el_equipo_compartido(self):
        abierta = servicios.abrir_sesion_alumno("ana", self.did)
        self.assertEqual(self.asignar().status_code, 200)
        cerrada = m.DimSesionAlumno.objects.get(pk=abierta["id"])
        self.assertEqual((cerrada.motivo_cierre, cerrada.finalizada_en is not None), ("sistema", True))

    def test_lo_asigna_quien_administra_dispositivos_no_el_profesor_ni_el_alumno(self):
        juan = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        for cliente in (self.docente, juan):
            r = self.asignar(cliente)
            self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))
        self.assertEqual(self.asignar(self.tecnico()).status_code, 200)              # el técnico administra dispositivos
        self.assertEqual(self.liberar(self.docente).status_code, 403)
        self.assertEqual(self.api.get(f"/api/dispositivos/{self.did}/").json()["perfil"], "asignado")

    def test_sin_sesion_se_permite_como_en_el_resto_de_mod_009(self):
        r = self.api.post(self.ruta("asignar"), {"alumno_id": self.estudiante_id, "actor": "tecnico-1"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Auditoria.objects.get(accion="dispositivos.asignado").actor_id, "tecnico-1")


class LiberarTests(BaseAsignacion):
    def test_liberar_devuelve_el_equipo_al_aula_con_evento_y_bitacora(self):
        self.asignar()
        r = self.liberar()
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertEqual((d["perfil"], d["asignado_a"], d["asignado_a_id"], d["asignado_en"]), ("compartido", None, None, None))
        evento = m.EventoSalida.objects.get(tipo_evento=dom.EV_LIBERADO, agregado_id=self.did)
        self.assertEqual((evento.carga["dispositivo_id"], evento.carga["alumno_id"]), (self.did, self.estudiante_id))
        asiento = Auditoria.objects.get(accion="dispositivos.liberado", objeto_id=self.did)
        self.assertEqual((asiento.actor_id, asiento.valor_anterior["asignado_a_id"], asiento.valor_nuevo["perfil"]), (self.admin_id, self.estudiante_id, "compartido"))

    def test_liberar_un_equipo_compartido_no_hace_nada(self):
        self.assertEqual(self.liberar().status_code, 200)
        self.assertEqual(m.EventoSalida.objects.filter(tipo_evento=dom.EV_LIBERADO).count(), 0)

    def test_con_un_paquete_de_estudio_activo_no_se_libera(self):
        self.asignar()
        with mock.patch("device_manager.infraestructura.repositorios.PaquetesEstudioPerezoso.activos_en", return_value=2):
            r = self.liberar()
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["paquetes"]), (409, "paquete_sin_integrar", 2))
        self.assertEqual(m.Dispositivo.objects.get(pk=self.did).perfil, "asignado")
        self.assertEqual(m.EventoSalida.objects.filter(tipo_evento=dom.EV_LIBERADO).count(), 0)
        self.assertEqual(self.liberar().status_code, 200)                            # sin paquetes, se libera

    def test_liberar_cierra_la_sesion_de_su_dueno_en_el_equipo(self):
        self.asignar()
        abierta = servicios.abrir_sesion_alumno(self.estudiante_id, self.did)
        self.liberar()
        self.assertEqual(m.DimSesionAlumno.objects.get(pk=abierta["id"]).motivo_cierre, "sistema")

    def test_la_interfaz_para_otros_modulos_dice_de_quien_es_el_equipo(self):
        self.assertIsNone(servicios.asignado_a(self.did))
        self.asignar()
        self.assertEqual(servicios.asignado_a(self.did), self.estudiante_id)
        self.assertIsNone(servicios.asignado_a("no-existe"))
        self.assertEqual({k: v["id"] for k, v in servicios.asignados_a([self.estudiante_id, "otro", ""]).items()}, {self.estudiante_id: self.did})
        self.assertEqual(servicios.asignados_a([]), {})
        self.assertIsNotNone(servicios.organizacion_id())


class SesionDeAlumnoEnUnEquipoAsignadoTests(BaseAsignacion):
    """D-15 (modo de estudio, identidad declarada): un equipo asignado ya no rechaza la sesión de quien no es su dueño; se aplica el relevo de siempre
    (INV-011: una sola sesión de alumno por equipo · DEC-023: una sola por alumno)."""

    def test_otro_alumno_abre_sesion_en_el_equipo_asignado_y_releva_la_del_dueno(self):
        self.asignar()
        del_dueno = servicios.abrir_sesion_alumno(self.estudiante_id, self.did)
        del_visitante = servicios.abrir_sesion_alumno("visitante-1", self.did)
        self.assertEqual((del_visitante["alumno_id"], del_visitante["dispositivo_id"], del_visitante["finalizada_en"]), ("visitante-1", self.did, None))
        cerrada = m.DimSesionAlumno.objects.get(pk=del_dueno["id"])
        self.assertEqual((cerrada.motivo_cierre, cerrada.finalizada_en is not None), ("relevo", True))
        self.assertEqual(servicios.sesion_abierta_de_alumno("visitante-1")["id"], del_visitante["id"])
        self.assertEqual(m.Dispositivo.objects.get(pk=self.did).asignado_a_id, self.estudiante_id)        # y el equipo sigue siendo de su dueño

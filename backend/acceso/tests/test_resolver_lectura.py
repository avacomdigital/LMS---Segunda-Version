"""
La validación de la sesión de cada petición (y de cada medio con pase) es de SÓLO LECTURA: no abre la transacción de escritura de SQLite.

Prueba de 35 tabletas (2026-10-08): con `BEGIN IMMEDIATE` en cada petición, 35 tabletas pidiendo medios a la vez hacían fila para escribir sin escribir nada y
el nodo respondía 500 «database is locked» al agotarse el `timeout` (y el aviso de cambio de lámina tardaba hasta 47 s). Aquí se comprueba que la carpeta
de escritura NO se toca cuando no hay nada que escribir, y que sí se usa —igual que antes— cuando lo hay.
"""
from __future__ import annotations

import dataclasses
import time

from .. import models as m
from ..aplicacion import cache_pases
from ..aplicacion.casos_uso import PaseDeMedios, ResolverPrincipal
from ..dominio import errores
from ..infraestructura.contenedor import servicios
from .base import BaseAcceso


def _sin_escritura():
    raise AssertionError("la validación de la sesión abrió una transacción de escritura")


class ValidacionDeSesionDeSoloLecturaTests(BaseAcceso):
    def sin_escritura(self):
        return dataclasses.replace(servicios(), uow=_sin_escritura)

    def sesion_fresca(self):
        r = self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN).json()
        m.Sesion.objects.filter(id=r["sesion_id"]).update(ultimo_uso_en=int(time.time() * 1000))
        return r

    def test_una_peticion_con_sesion_vigente_no_escribe(self):
        r = self.sesion_fresca()
        principal = ResolverPrincipal(self.sin_escritura()).ejecutar(r["token"])
        self.assertEqual((principal.usuario_id, principal.sesion_id), (self.estudiante_id, r["sesion_id"]))

    def test_un_medio_con_pase_tampoco_escribe(self):
        r = self.sesion_fresca()
        pase = PaseDeMedios(servicios()).emitir(self.estudiante_id, r["sesion_id"])
        principal = PaseDeMedios(self.sin_escritura()).resolver(pase)
        self.assertEqual(principal.usuario_id, self.estudiante_id)

    def test_el_ultimo_uso_se_refresca_una_vez_por_minuto_y_eso_si_escribe(self):
        r = self.sesion_fresca()
        hace_dos_minutos = int(time.time() * 1000) - 2 * 60_000
        m.Sesion.objects.filter(id=r["sesion_id"]).update(ultimo_uso_en=hace_dos_minutos)
        with self.assertRaises(AssertionError):
            ResolverPrincipal(self.sin_escritura()).ejecutar(r["token"])      # llegó a lo que hay que escribir y pidió la carpeta de escritura
        ResolverPrincipal(servicios()).ejecutar(r["token"])
        self.assertGreater(m.Sesion.objects.get(id=r["sesion_id"]).ultimo_uso_en, hace_dos_minutos + 60_000)

    def test_los_rechazos_de_la_sesion_se_dan_leyendo(self):
        r = self.sesion_fresca()
        m.Sesion.objects.filter(id=r["sesion_id"]).update(revocada_en=int(time.time() * 1000), motivo_revocacion="usuario")
        with self.assertRaises(errores.SesionRevocada):
            ResolverPrincipal(self.sin_escritura()).ejecutar(r["token"])
        r2 = self.sesion_fresca()
        m.Sesion.objects.filter(id=r2["sesion_id"]).update(expira_en=int(time.time() * 1000) - 1, emitida_en=1)
        with self.assertRaises(errores.SesionExpirada):
            ResolverPrincipal(self.sin_escritura()).ejecutar(r2["token"])

    def test_la_inactividad_sigue_cerrando_la_sesion_y_lo_deja_escrito(self):
        r = self.sesion_fresca()
        m.Sesion.objects.filter(id=r["sesion_id"]).update(ultimo_uso_en=1, emitida_en=1, expira_en=10**14)
        with self.assertRaises(errores.SesionInactiva):
            ResolverPrincipal(servicios()).ejecutar(r["token"])
        self.assertEqual(m.Sesion.objects.get(id=r["sesion_id"]).motivo_revocacion, "inactividad")

    def test_sin_carpeta_de_lectura_funciona_como_antes(self):
        r = self.sesion_fresca()
        sin_lectura = dataclasses.replace(servicios(), uow_lectura=None)
        self.assertEqual(ResolverPrincipal(sin_lectura).ejecutar(r["token"]).usuario_id, self.estudiante_id)


class CachePasesDeMediosTests(BaseAcceso):
    """La persona de un pase se recuerda unos segundos (la comprobación entera era la mitad del trabajo del nodo sirviendo medios), pero nunca a costa de
    seguir dando medios a una sesión que ya no existe."""

    def setUp(self):
        super().setUp()
        cache_pases.limpiar()
        r = self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN).json()
        m.Sesion.objects.filter(id=r["sesion_id"]).update(ultimo_uso_en=int(time.time() * 1000))
        self.sesion_alumno = r
        self.pase = PaseDeMedios(servicios()).emitir(self.estudiante_id, r["sesion_id"])

    def resolver(self, **cambios):
        return PaseDeMedios(dataclasses.replace(servicios(), **cambios)).resolver(self.pase)

    def test_la_segunda_peticion_con_el_mismo_pase_no_toca_la_base(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as primera:
            self.resolver(cache_pases_seg=15)
        self.assertGreater(len(primera), 0)
        with CaptureQueriesContext(connection) as segunda:
            principal = self.resolver(cache_pases_seg=15)
        self.assertEqual(len(segunda), 0)
        self.assertEqual(principal.usuario_id, self.estudiante_id)

    def test_sin_cache_se_comprueba_siempre(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        self.resolver(cache_pases_seg=0)
        with CaptureQueriesContext(connection) as q:
            self.resolver(cache_pases_seg=0)
        self.assertGreater(len(q), 0)

    def test_cerrar_la_sesion_vacia_la_cache_al_instante(self):
        self.resolver(cache_pases_seg=60)
        self.assertEqual(self.con_token(self.sesion_alumno["token"]).delete("/api/acceso/sesiones/actual/").status_code, 204)
        with self.assertRaises(errores.SesionRevocada):
            self.resolver(cache_pases_seg=60)

    def test_suspender_a_la_persona_vacia_la_cache_al_instante(self):
        self.resolver(cache_pases_seg=60)
        r = self.docente.patch(f"/api/acceso/usuarios/{self.estudiante_id}/", {"estado": "SUSPENDIDO"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        with self.assertRaises(errores.ErrorAcceso):
            self.resolver(cache_pases_seg=60)

    def test_restablecer_la_clave_vacia_la_cache(self):
        self.resolver(cache_pases_seg=60)
        r = self.docente.post(f"/api/acceso/usuarios/{self.estudiante_id}/credencial/restablecer/", {}, format="json")
        self.assertIn(r.status_code, (200, 201), r.content)
        with self.assertRaises(errores.ErrorAcceso):      # la sesión de antes se revoca por «credencial restablecida»
            self.resolver(cache_pases_seg=60)

    def test_la_vigencia_se_acaba(self):
        self.resolver(cache_pases_seg=0.05)
        time.sleep(0.12)
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as q:
            self.resolver(cache_pases_seg=0.05)
        self.assertGreater(len(q), 0)

    def test_otro_pase_no_aprovecha_la_cache_de_este(self):
        self.resolver(cache_pases_seg=60)
        otra = self.login(self.DOCENTE_DNI, self.DOCENTE_PASS).json()
        pase = PaseDeMedios(servicios()).emitir(self.docente_id, otra["sesion_id"])
        principal = PaseDeMedios(dataclasses.replace(servicios(), cache_pases_seg=60)).resolver(pase)
        self.assertEqual(principal.usuario_id, self.docente_id)

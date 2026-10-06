"""
`0011_datos_pin_maestro_y_alumnos` sobre una base que YA tiene datos (RB-06): siembra el permiso del PIN maestro, completa `origen` y `confirmado_en` de
las cuentas anteriores y ajusta las políticas de fábrica sin pisar lo que la institución ya eligió. Idempotente.
"""
from __future__ import annotations

import importlib

from django.apps import apps

from acceso import models as m

from .base import BaseAcceso

migracion = importlib.import_module("acceso.migrations.0011_datos_pin_maestro_y_alumnos")


class DatosDeLaMigracionTests(BaseAcceso):
    def volver_al_estado_anterior(self):
        """Deja la base como la dejaba la 0010 en una instalación que ya existía: sin origen, sin confirmación y con las políticas de fábrica de antes."""
        m.Usuario.objects.update(origen="INSTALACION", confirmado_en=None)
        m.PoliticaCredencial.objects.filter(perfil="student").update(autoregistro=False, bloqueo_alcance="CUENTA", longitud_minima=6)
        m.PoliticaCredencial.objects.filter(perfil="teacher").update(autoregistro=False)
        m.RolPermiso.objects.filter(permiso_id="identity.master_pin.manage").delete()
        m.RolPermiso.objects.filter(rol__codigo="TEACHER", permiso_id="identity.group.manage").delete()
        m.Permiso.objects.filter(codigo="identity.master_pin.manage").delete()

    def test_origen_confirmacion_politicas_y_permisos(self):
        self.volver_al_estado_anterior()
        migracion.sembrar(apps, None)
        origen = {u.id: u.origen for u in m.Usuario.objects.all()}
        self.assertEqual(origen[self.admin_id], "INSTALACION")          # nadie lo creó
        self.assertEqual(origen[self.docente_id], "IMPORTACION")        # lo creó la administración
        self.assertEqual(origen[self.estudiante_id], "PROFESOR")        # lo creó un profesor
        for usuario in m.Usuario.objects.all():
            self.assertEqual(usuario.confirmado_en, usuario.creado_en)  # las cuentas anteriores se dan por confirmadas

        alumno = m.PoliticaCredencial.objects.get(perfil="student", nivel_clave__isnull=True)
        self.assertEqual((alumno.longitud_minima, alumno.autoregistro, alumno.bloqueo_alcance), (4, True, "DISPOSITIVO"))
        self.assertTrue(m.PoliticaCredencial.objects.get(perfil="teacher").autoregistro)
        self.assertEqual(m.PoliticaCredencial.objects.get(perfil="admin").bloqueo_alcance, "CUENTA")   # el personal sigue bloqueándose por cuenta

        permisos = {(rp.rol.codigo, rp.permiso_id): rp.alcance for rp in m.RolPermiso.objects.filter(rol__organizacion__isnull=True)}
        self.assertEqual(permisos[("ADMIN", "identity.master_pin.manage")], "ORGANIZATION")
        self.assertNotIn(("TECHNICIAN", "identity.master_pin.manage"), permisos)       # RB-08
        self.assertNotIn(("TEACHER", "identity.master_pin.manage"), permisos)
        self.assertEqual(permisos[("TEACHER", "identity.group.manage")], "ASSIGNED_GROUPS")   # RB-28

    def test_es_idempotente_y_respeta_el_reglamento_que_la_institucion_ya_ajusto(self):
        self.volver_al_estado_anterior()
        # la institución ya había subido el PIN de sus alumnos a 5 dígitos: no se toca (sólo se ajusta el de fábrica, de 6)
        m.PoliticaCredencial.objects.filter(perfil="student").update(longitud_minima=5)
        migracion.sembrar(apps, None)
        migracion.sembrar(apps, None)
        self.assertEqual(m.PoliticaCredencial.objects.get(perfil="student", nivel_clave__isnull=True).longitud_minima, 5)
        self.assertEqual(m.RolPermiso.objects.filter(permiso_id="identity.master_pin.manage").count(), 1)
        self.assertEqual(m.RolPermiso.objects.filter(rol__codigo="TEACHER", permiso_id="identity.group.manage").count(), 1)
        self.assertEqual(m.Permiso.objects.filter(codigo="identity.master_pin.manage").count(), 1)

    def test_una_cuenta_creada_despues_de_la_migracion_no_se_toca(self):
        self.volver_al_estado_anterior()
        m.Usuario.objects.filter(id=self.estudiante_id).update(origen="AUTOALTA_ALUMNO", confirmado_en=None)
        migracion.sembrar(apps, None)
        # `origen != INSTALACION` queda fuera del barrido: sigue «sin confirmar»
        fila = m.Usuario.objects.get(id=self.estudiante_id)
        self.assertEqual((fila.origen, fila.confirmado_en), ("AUTOALTA_ALUMNO", None))

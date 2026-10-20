"""
Las migraciones de MOD-018: la de los permisos en `acceso` (0018) es IDEMPOTENTE y reparte lo que dice el producto (P-15) también en una instalación que ya existía; las de `licenciamiento`
dejan las tablas `m18_*` con sus tres triggers (la marca alta sólo sube; el historial y las observaciones son de sólo inserción).
"""
from __future__ import annotations

import importlib

from django.apps import apps
from django.db import IntegrityError, OperationalError, connection, transaction
from django.test import TestCase

from acceso.models import Permiso, Rol, RolPermiso
from licenciamiento import models as m
from licenciamiento.dominio import catalogos as cat

MIGRACION = importlib.import_module("acceso.migrations.0018_permisos_licencia")
TRIGGERS = importlib.import_module("licenciamiento.migrations.0002_triggers")


class PermisosDeLicenciaTests(TestCase):
    def concedidos(self, rol: str) -> dict[str, str]:
        r = Rol.objects.filter(codigo=rol, organizacion__isnull=True).first()
        if r is None:
            return {}
        return {rp.permiso_id: rp.alcance for rp in RolPermiso.objects.filter(rol=r, permiso_id__in=list(cat.PERMISOS))}

    def test_la_migracion_reparte_los_permisos_en_una_instalacion_que_ya_existia_y_es_idempotente(self):
        self.assertTrue(Rol.objects.filter(codigo="ADMIN", organizacion__isnull=True).exists())        # los roles de sistema los siembran las migraciones anteriores
        RolPermiso.objects.filter(permiso__codigo__startswith="license.").delete()                         # «una instalación anterior a MOD-018»: sin los license.*
        Permiso.objects.filter(codigo__startswith="license.").delete()
        self.assertEqual(self.concedidos("ADMIN"), {})                                  # «antes de actualizar»
        MIGRACION.sembrar(apps, None)
        despues = {rol: self.concedidos(rol) for rol in ("ADMIN", "TECHNICIAN", "TEACHER", "REPORTS", "STUDENT")}
        self.assertEqual(despues["ADMIN"], {"license.activate": "ORGANIZATION", "license.renew": "ORGANIZATION", "license.read": "ORGANIZATION"})
        self.assertEqual(despues["TECHNICIAN"], {"license.activate": "ORGANIZATION", "license.read": "ORGANIZATION"})            # el técnico NO renueva
        for rol in ("TEACHER", "REPORTS", "STUDENT"):
            self.assertEqual(despues[rol], {}, rol)                                       # ven «no disponible por licencia», jamás datos de la licencia
        for _ in range(3):
            MIGRACION.sembrar(apps, None)                                                 # repetirla no duplica ni cambia nada
        self.assertEqual({rol: self.concedidos(rol) for rol in despues}, despues)
        self.assertEqual(Permiso.objects.filter(codigo__startswith="license.").count(), 3)

    def test_los_tres_permisos_estan_en_el_catalogo_del_modulo_dueno(self):
        from acceso.dominio import plantillas
        self.assertEqual(sorted(c for c, *_ in plantillas.PERMISOS if c.startswith("license.")), sorted(cat.PERMISOS))
        for codigo in cat.PERMISOS:
            self.assertEqual(plantillas.PERMISOS_POR_CODIGO[codigo][3], plantillas.Alcance.ORGANIZATION)


class TriggersTests(TestCase):
    def triggers(self) -> set[str]:
        with connection.cursor() as c:
            c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'm18_%'")
            return {fila[0] for fila in c.fetchall()}

    def test_los_tres_triggers_estan_y_la_migracion_se_puede_repetir(self):
        esperados = {"m18_marca_alta_solo_sube", "m18_licencia_solo_insercion", "m18_observacion_solo_insercion"}
        self.assertEqual(self.triggers(), esperados)
        with connection.cursor() as c:
            for sentencia in TRIGGERS.SQL_CREAR:
                c.execute(sentencia)                                                       # IF NOT EXISTS: repetir no falla
        self.assertEqual(self.triggers(), esperados)

    def test_la_marca_alta_sube_pero_no_baja(self):
        m.MarcaAlta.objects.create(valor=1000, actualizada_en=1000)
        m.MarcaAlta.objects.filter(pk="nodo").update(valor=2000)                           # subir se puede
        with self.assertRaises((IntegrityError, OperationalError)), transaction.atomic():
            m.MarcaAlta.objects.filter(pk="nodo").update(valor=1500)                       # bajar aborta
        self.assertEqual(m.MarcaAlta.objects.get().valor, 2000)

    def test_el_historial_y_las_observaciones_son_de_solo_insercion(self):
        licencia = m.Licencia.objects.create(licencia_id="x", serie=1, tipo="activada", instalada_en=1)
        observacion = m.Observacion.objects.create(tipo="reloj_retroceso", en=1)
        with self.assertRaises((IntegrityError, OperationalError)), transaction.atomic():
            m.Licencia.objects.filter(pk=licencia.pk).update(serie=9)
        with self.assertRaises((IntegrityError, OperationalError)), transaction.atomic():
            m.Observacion.objects.filter(pk=observacion.pk).update(en=9)
        self.assertEqual((m.Licencia.objects.get().serie, m.Observacion.objects.get().en), (1, 1))

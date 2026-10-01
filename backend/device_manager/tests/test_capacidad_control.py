"""
MOD-009 · capacidad de control (MOD-010, BR-075, D-11): lo que una tableta DECLARA poder garantizar en un examen (`abierto` · `supervisado` · `controlado`).
La declara la propia tableta al registrarse y en cada latido; vacío significa que no dijo nada (el examen la trata como `abierto`); un valor desconocido
es un error de datos y la base lo impide también.
"""
from __future__ import annotations

from django.db import IntegrityError, transaction

from acceso.tests.base import BaseAcceso

from .. import models as m
from .. import servicios
from ..dominio import dispositivo as dom
from ..dominio.errores import DatosInvalidos


class DeclararCapacidadTests(BaseAcceso):
    def registrar(self, hw: str = "hw-cap", **extra):
        return self.api.post("/api/dispositivos/", {"identificador_hw": hw, "nombre": hw, "plataforma": "android", **extra}, format="json")

    def fila(self, hw: str = "hw-cap") -> m.Dispositivo:
        return m.Dispositivo.objects.get(identificador_hw=hw)

    def test_la_tableta_declara_su_capacidad_al_registrarse(self):
        r = self.registrar(capacidad_control="controlado", capacidad_detalle={"device_owner": True, "lock_task": True})
        self.assertEqual(r.status_code, 201, r.content)
        d = self.fila()
        self.assertEqual((d.capacidad_control, d.capacidad_detalle), ("controlado", {"device_owner": True, "lock_task": True}))
        self.assertIsNotNone(d.capacidad_declarada_en)
        self.assertEqual(r.json()["capacidad_control"], "controlado")

    def test_sin_declarar_queda_vacia_y_volver_a_registrar_sin_decir_nada_no_la_borra(self):
        self.registrar()
        self.assertEqual((self.fila().capacidad_control, self.fila().capacidad_declarada_en), ("", None))
        self.registrar(capacidad_control="supervisado")
        self.registrar(nombre="Renombrada")                                           # no dice nada de la capacidad
        self.assertEqual(self.fila().capacidad_control, "supervisado")

    def test_el_latido_la_actualiza_cuando_la_tableta_pierde_o_gana_capacidad(self):
        self.registrar(capacidad_control="controlado")
        primera = self.fila().capacidad_declarada_en
        r = self.api.post("/api/dispositivos/latido/", {"identificador_hw": "hw-cap", "capacidad_control": "supervisado"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        d = self.fila()
        self.assertEqual(d.capacidad_control, "supervisado")
        self.assertGreaterEqual(d.capacidad_declarada_en, primera)
        self.api.post("/api/dispositivos/latido/", {"identificador_hw": "hw-cap"}, format="json")      # un latido sin el dato no la toca
        self.assertEqual(self.fila().capacidad_control, "supervisado")

    def test_se_normaliza_y_un_valor_desconocido_es_error_de_datos(self):
        self.registrar(capacidad_control="  Controlado ")
        self.assertEqual(self.fila().capacidad_control, "controlado")
        for valor in ("maximo", "total", "1"):
            r = self.registrar("hw-mala", capacidad_control=valor)
            self.assertEqual((r.status_code, r.json().get("codigo")), (400, "datos_invalidos"), valor)
            self.assertFalse(m.Dispositivo.objects.filter(identificador_hw="hw-mala").exists())
        r = self.api.post("/api/dispositivos/latido/", {"identificador_hw": "hw-cap", "capacidad_control": "maximo"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.fila().capacidad_control, "controlado")

    def test_el_detalle_se_acota_para_no_guardar_basura(self):
        detalle = {f"clave_{n:02d}_" + "x" * 60: n for n in range(30)}
        self.registrar(capacidad_control="controlado", capacidad_detalle=detalle)
        guardado = self.fila().capacidad_detalle
        self.assertEqual(len(guardado), 20)
        self.assertTrue(all(len(k) <= 40 for k in guardado))
        self.registrar(capacidad_detalle="no es un objeto")                            # ignorado: el detalle anterior se conserva
        self.assertEqual(len(self.fila().capacidad_detalle), 20)

    def test_la_base_impide_una_capacidad_fuera_de_los_tres_niveles(self):
        self.registrar()
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Dispositivo.objects.filter(identificador_hw="hw-cap").update(capacidad_control="total")
        for valido in ("", "abierto", "supervisado", "controlado"):
            m.Dispositivo.objects.filter(identificador_hw="hw-cap").update(capacidad_control=valido)

    def test_la_interfaz_interna_para_otros_modulos_tambien_la_acepta(self):
        d = servicios.resolver("hw-interna", nombre="Interna", plataforma="windows", capacidad_control="supervisado")
        self.assertEqual(d["capacidad_control"], "supervisado")
        servicios.latido(d["id"], capacidad_control="controlado")
        self.assertEqual(servicios.por_id(d["id"])["capacidad_control"], "controlado")
        with self.assertRaises(DatosInvalidos):
            servicios.latido(d["id"], capacidad_control="maximo")

    def test_el_dominio_valida_los_tres_niveles_y_el_vacio(self):
        self.assertEqual([dom.validar_capacidad_control(v) for v in (None, "", "  ", "ABIERTO", "Supervisado", "controlado")],
                         ["", "", "", "abierto", "supervisado", "controlado"])
        with self.assertRaises(DatosInvalidos):
            dom.validar_capacidad_control("kiosco")

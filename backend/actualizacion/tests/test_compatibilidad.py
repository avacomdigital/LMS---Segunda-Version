"""
Compatibilidad (P-04, BR-013, INV-007) y serie (P-16, A2): qué impide que una instalación empiece, siempre con la lista de motivos. Función pura: la instalación es un dato.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from actualizacion.dominio import catalogos as cat
from actualizacion.dominio import compatibilidad as comp
from actualizacion.dominio import manifiesto as mf
from actualizacion.dominio import registro
from actualizacion.dominio.errores import DatosInvalidos

from .emisor import manifiesto_de_ejemplo

REGISTRO = {
    "formato": 1,
    "modulos": {
        "reporting": {"modulo": "MOD-013", "version": "1.3.0", "version_contrato": 1, "serie": 3, "produce": ["reporte"], "consume": {"nodo": [1, 1], "gradebook": [1, 1]}},
        "gradebook": {"modulo": "MOD-011", "version": "1.2.0", "version_contrato": 1, "serie": 2, "produce": ["calificacion"], "consume": {"reporting": [1, 1]}},
        "nodo": {"modulo": "MOD-015", "version": "1.0.0", "version_contrato": 1, "serie": 1, "produce": ["nodo"]},
        "evaluacion": {"modulo": "MOD-010", "version": "1.1.0", "version_contrato": 1, "serie": 2, "produce": ["evaluacion"]},
        "biblioteca": {"modulo": "frontera", "version": "1.0.0", "version_contrato": 2, "serie": 0, "actualizable": False},
    },
}
DATOS = {"reporting": 3, "gradebook": 4, "nodo": 3, "evaluacion": 2, "biblioteca": 0}


def instalacion(**cambios) -> registro.Instalacion:
    modulos = {n: registro.instalado(m, DATOS[n]) for n, m in registro.leer(REGISTRO).items()}
    base = dict(version_producto="2.11.0", contrato_biblioteca=2, modulos=modulos, licencia_admite=True, motivo_licencia="")
    base.update(cambios)
    return registro.Instalacion(**base)


def codigos(c: comp.Compatibilidad) -> list[tuple[str, str]]:
    return [(p.codigo, p.modulo) for p in c.problemas]


def evaluar(m: mf.Manifiesto, inst: registro.Instalacion | None = None, libre: int | None = 10 * 1024 * cat.MIB) -> comp.Compatibilidad:
    inst = inst or instalacion()
    return comp.evaluar(m, inst, libre, comp.espacio_requerido(m, bytes_paquete=2000, bytes_base=50 * cat.MIB))


def modulo(**cambios) -> mf.Modulo:
    base = manifiesto_de_ejemplo().modulos[0]
    return mf.Modulo(**{**base.__dict__, **cambios})


class RegistroTests(SimpleTestCase):
    def test_se_lee_y_se_completa_con_la_version_de_datos_viva(self):
        modulos = registro.leer(REGISTRO)
        self.assertEqual(sorted(modulos), ["biblioteca", "evaluacion", "gradebook", "nodo", "reporting"])
        r = modulos["reporting"]
        self.assertEqual((r.modulo, r.version, r.version_contrato, r.serie, r.actualizable, r.produce, r.consume), ("MOD-013", "1.3.0", 1, 3, True, ("reporte",), {"nodo": (1, 1), "gradebook": (1, 1)}))
        self.assertFalse(modulos["biblioteca"].actualizable)
        inst = registro.instalado(r, 3)
        self.assertEqual((inst.version_datos, inst.nombre), (3, "reporting"))
        self.assertEqual(registro.como_dict(inst)["consume"], {"nodo": [1, 1], "gradebook": [1, 1]})

    def test_un_registro_mal_formado_se_rechaza(self):
        for malo in ({}, {"formato": 2, "modulos": {}}, {"formato": 1, "modulos": []}, {"formato": 1, "modulos": {"Mal": {"version": "1.0.0"}}},
                     {"formato": 1, "modulos": {"x": {"version": "1"}}}, {"formato": 1, "modulos": {"x": {"version": "1.0.0", "consume": {"y": [2, 1]}}}},
                     {"formato": 1, "modulos": {"x": {"version": "1.0.0", "serie": -1}}}, {"formato": 1, "modulos": {"x": {"version": "1.0.0", "version_contrato": 0}}}):
            with self.assertRaises(DatosInvalidos, msg=malo):
                registro.leer(malo)


class CompatibilidadTests(SimpleTestCase):
    def test_el_paquete_de_ejemplo_es_compatible_con_la_instalacion_de_ejemplo(self):
        c = evaluar(manifiesto_de_ejemplo())
        self.assertTrue(c.ok, c.como_dict())
        self.assertEqual([a.codigo for a in c.avisos], [])
        self.assertGreater(c.espacio_requerido, 50 * cat.MIB)

    def test_serie_menor_e_igual(self):
        c = evaluar(manifiesto_de_ejemplo(modulos=(modulo(serie=2),)))
        self.assertEqual(codigos(c), [("serie_menor", "reporting")])
        self.assertTrue(c.serie_menor)
        c = evaluar(manifiesto_de_ejemplo(modulos=(modulo(serie=3),)))
        self.assertEqual(codigos(c), [("ya_aplicado", "reporting")])
        self.assertTrue(c.ya_aplicado)

    def test_version_del_producto_menor_que_la_instalada(self):
        c = evaluar(manifiesto_de_ejemplo(version_producto="2.10.9"))
        self.assertEqual(codigos(c), [("serie_menor", "")])
        c = evaluar(manifiesto_de_ejemplo(version_producto="2.11.0"))          # la misma versión del producto con una serie mayor del módulo está bien
        self.assertTrue(c.ok)

    def test_version_minima_no_cumplida(self):
        c = evaluar(manifiesto_de_ejemplo(version_minima="2.11.1"))
        self.assertEqual(codigos(c), [("version_minima_no_cumplida", "")])
        self.assertTrue(evaluar(manifiesto_de_ejemplo(version_minima=None)).ok)

    def test_modulo_desconocido_y_no_actualizable(self):
        c = evaluar(manifiesto_de_ejemplo(modulos=(modulo(nombre="respaldo"),)))
        self.assertEqual(codigos(c), [("modulo_desconocido", "respaldo")])
        inst = instalacion()
        inst.modulos["reporting"] = registro.ModuloInstalado(**{**inst.modulos["reporting"].__dict__, "actualizable": False})
        self.assertEqual(codigos(evaluar(manifiesto_de_ejemplo(), inst)), [("modulo_no_actualizable", "reporting")])

    def test_version_de_datos_que_retrocede(self):
        c = evaluar(manifiesto_de_ejemplo(modulos=(modulo(version_datos=2),)))
        self.assertEqual(codigos(c), [("version_datos_retrocede", "reporting")])

    def test_contrato_requerido_de_otro_modulo(self):
        c = evaluar(manifiesto_de_ejemplo(modulos=(modulo(requiere={"nodo": 2}),)))
        self.assertEqual(codigos(c), [("contrato_requerido", "reporting")])
        c = evaluar(manifiesto_de_ejemplo(modulos=(modulo(requiere={"inexistente": 1}),)))
        self.assertEqual(codigos(c), [("contrato_requerido", "reporting")])
        # si el paquete trae también al otro módulo con el contrato nuevo, se satisface con lo que viene en el paquete
        m = manifiesto_de_ejemplo(modulos=(modulo(requiere={"nodo": 2}), mf.Modulo("nodo", "1.1.0", 3, 2, 2, cambia_contrato=True)))
        c = evaluar(m)
        self.assertNotIn(("contrato_requerido", "reporting"), codigos(c))

    def test_contrato_incompatible_con_un_consumidor_instalado(self):
        """INV-007: reporting sube su contrato a 2 y gradebook (instalado) sólo acepta 1…1: no se instala; si el paquete trae también a gradebook, sí."""
        c = evaluar(manifiesto_de_ejemplo(modulos=(modulo(version_contrato=2, cambia_contrato=True),)))
        self.assertEqual(codigos(c), [("contrato_incompatible", "reporting")])
        self.assertIn("gradebook", c.problemas[0].detalle)
        m = manifiesto_de_ejemplo(modulos=(modulo(version_contrato=2, cambia_contrato=True), mf.Modulo("gradebook", "1.3.0", 4, 1, 3)))
        self.assertTrue(evaluar(m).ok, evaluar(m).como_dict())
        # un cambio de contrato que no se declara también se detecta (la versión de contrato ya no coincide)
        c = evaluar(manifiesto_de_ejemplo(modulos=(modulo(version_contrato=2),)))
        self.assertEqual(codigos(c), [("contrato_incompatible", "reporting")])

    def test_contrato_de_la_biblioteca(self):
        c = evaluar(manifiesto_de_ejemplo(requisitos=mf.Requisitos(contrato_biblioteca=3)))
        self.assertEqual(codigos(c), [("contrato_biblioteca", "")])
        self.assertTrue(evaluar(manifiesto_de_ejemplo(requisitos=mf.Requisitos(contrato_biblioteca=None))).ok)

    def test_espacio_insuficiente(self):
        m = manifiesto_de_ejemplo()
        requerido = comp.espacio_requerido(m, bytes_paquete=2000, bytes_base=50 * cat.MIB)
        self.assertEqual(requerido, 50 * cat.MIB + 2 * m.bytes_total + 2000 + comp.MARGEN_BYTES)
        c = evaluar(m, libre=requerido - 1)
        self.assertEqual(codigos(c), [("espacio_insuficiente", "")])
        self.assertTrue(c.solo_espacio)
        self.assertTrue(evaluar(m, libre=requerido).ok)
        self.assertTrue(evaluar(m, libre=None).ok)                  # sin medición no se bloquea por espacio (se dice en el detalle)
        self.assertEqual(comp.espacio_requerido(manifiesto_de_ejemplo(requisitos=mf.Requisitos(espacio_bytes=7)), 0, 0, bytes_instantanea=5), 2 * 249 - 249 + 5 + 7 + comp.MARGEN_BYTES)

    def test_licencia(self):
        c = evaluar(manifiesto_de_ejemplo(), instalacion(licencia_admite=False, motivo_licencia="el plan no incluye reportes"))
        self.assertEqual(codigos(c), [("licencia", "")])
        self.assertEqual(c.problemas[0].detalle, "el plan no incluye reportes")

    def test_los_avisos_no_bloquean(self):
        c = evaluar(manifiesto_de_ejemplo(requisitos=mf.Requisitos(contrato_biblioteca=2, cliente_minimo="2.12.0", contrato_red=2)))
        self.assertTrue(c.ok)
        self.assertEqual([a.codigo for a in c.avisos], ["cliente_minimo", "contrato_red"])
        self.assertEqual(c.como_dict()["avisos"][0]["codigo"], "cliente_minimo")

    def test_varios_problemas_a_la_vez_salen_todos(self):
        c = evaluar(manifiesto_de_ejemplo(version_minima="3.0.0", modulos=(modulo(serie=1, version_datos=1),), requisitos=mf.Requisitos(contrato_biblioteca=9)), libre=0)
        self.assertEqual(sorted(p.codigo for p in c.problemas), ["contrato_biblioteca", "espacio_insuficiente", "serie_menor", "version_datos_retrocede", "version_minima_no_cumplida"])
        self.assertFalse(c.solo_espacio)

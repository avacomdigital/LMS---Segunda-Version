"""
§3 y §4.3 del prompt de MOD-019 · la bitácora encadenada: asiento completo (019-01), cadena (019-02), inmutabilidad en
tres capas (019-03, AC-081), catálogo cerrado, contexto de la petición, compatibilidad con los puertos de los otros
módulos y la migración del historial.
"""
from __future__ import annotations

from unittest import mock

from django.db import DatabaseError, IntegrityError, connection, transaction
from django.test import SimpleTestCase, TestCase, override_settings

from acceso.tests.base import BaseAcceso
from expediente.models import Auditoria

from .. import contexto, servicios
from ..aplicacion import anexar as app
from ..dominio import asiento as dom
from ..dominio import catalogos, errores, huella
from ..dominio import tramo as dom_tramo
from ..infraestructura import migracion, triggers
from ..models import Bitacora, BitacoraTramo
from ..pruebas import LogsDePrueba


class HuellaTests(SimpleTestCase):
    def test_el_contenido_canonico_es_estable_y_la_huella_depende_de_la_previa(self):
        a = {"secuencia": 1, "ocurrido_en": 10, "accion": "x", "valor_nuevo": {"b": 1, "a": [1, 2.0]}, "modulo": "aula"}
        b = {"modulo": "aula", "valor_nuevo": {"a": [1, 2], "b": 1}, "accion": "x", "ocurrido_en": 10, "secuencia": 1}
        self.assertEqual(huella.contenido_canonico(a), huella.contenido_canonico(b))
        self.assertIn('"valor_nuevo":{"a":[1,2],"b":1}', huella.contenido_canonico(a))
        h1 = huella.calcular(huella.GENESIS, a)
        h2 = huella.calcular("f" * 64, a)
        self.assertEqual(len(h1), 64)
        self.assertNotEqual(h1, h2)
        self.assertEqual(h1, huella.calcular(huella.GENESIS, b))

    def test_verificar_detecta_huella_hueco_repeticion_y_enlace(self):
        asientos = migracion.encadenar([{"id": i, "actor_id": "a", "accion": "prueba.x", "momento": i} for i in (1, 2, 3)])
        self.assertTrue(dom_tramo.verificar(asientos, huella.GENESIS, 1).ok)
        alterado = [dict(a) for a in asientos]
        alterado[1]["accion"] = "prueba.y"
        r = dom_tramo.verificar(alterado, huella.GENESIS, 1)
        self.assertEqual((r.ok, r.salto_en_secuencia, r.causa), (False, 2, dom_tramo.CAUSA_HUELLA))
        r = dom_tramo.verificar([asientos[0], asientos[2]], huella.GENESIS, 1)
        self.assertEqual((r.salto_en_secuencia, r.causa), (2, dom_tramo.CAUSA_HUECO))   # la primera que falta
        r = dom_tramo.verificar([asientos[0], asientos[0]], huella.GENESIS, 1)
        self.assertEqual(r.causa, dom_tramo.CAUSA_REPETIDA)
        enlace = [dict(a) for a in asientos]
        enlace[2]["huella_previa"] = "0" * 64
        self.assertEqual(dom_tramo.verificar(enlace, huella.GENESIS, 1).causa, dom_tramo.CAUSA_ENLACE)


class CatalogoTests(SimpleTestCase):
    def test_las_acciones_vigentes_de_los_modulos_estan_en_el_catalogo(self):
        for clave in ("identidad.usuario.creado", "aula.sesion.iniciada", "dispositivos.asignado", "estudio.asignacion.creada",
                      "inscripcion.creada", "aula.control.foco", "aula.distribucion.actividad", "aula.envio.aceptada", "estudio.envio.tarde"):
            self.assertIsNotNone(catalogos.resolver(clave), clave)
        self.assertIsNone(catalogos.resolver("aula.control."))
        self.assertIsNone(catalogos.resolver("inventada.cosa"))
        self.assertTrue(catalogos.ACCIONES["calificacion.modificada"].exige_motivo)
        self.assertEqual(catalogos.modulo_de("identidad.rol.asignado"), "acceso")

    def test_la_migracion_convierte_el_historial_en_orden_y_deduce_actor_y_modulo(self):
        filas = [{"id": 2, "actor_id": "u-1", "accion": "aula.sesion.iniciada", "momento": 5, "objeto_tabla": "m07_sesion", "objeto_id": "s1"},
                 {"id": 1, "actor_id": "sistema", "accion": "identidad.sesion.cerrada", "momento": 5},
                 {"id": 3, "actor_id": "", "accion": "dispositivos.registrado", "momento": 1, "valor_nuevo": {"nombre": "t"}}]
        cadena = migracion.encadenar(filas)
        self.assertEqual([a["secuencia"] for a in cadena], [1, 2, 3])
        self.assertEqual([a["accion"] for a in cadena], ["dispositivos.registrado", "identidad.sesion.cerrada", "aula.sesion.iniciada"])
        self.assertEqual([a["modulo"] for a in cadena], ["dispositivos", "acceso", "aula"])
        self.assertEqual([a["actor_tipo"] for a in cadena], ["sistema", "sistema", "declarado"])
        self.assertEqual(cadena[2]["usuario_id"], "u-1")
        self.assertEqual(cadena[0]["huella_previa"], huella.GENESIS)
        self.assertEqual(cadena[1]["huella_previa"], cadena[0]["huella"])
        self.assertTrue(all(a["origen"] == "migracion" for a in cadena))
        self.assertTrue(dom_tramo.verificar(cadena, huella.GENESIS, 1).ok)


def vaciar_bitacora() -> None:
    """Deja la base como recién creada y vaciada (lo que hace el flush de TransactionTestCase): sin tramos ni asientos.
    Quita los triggers y los repone, como `tools/romper_cadena.py`; nunca SQL suelto en un test."""
    triggers.quitar(connection)
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM m19_bitacora")
            cursor.execute("DELETE FROM m19_bitacora_tramo")
    finally:
        triggers.crear(connection)


class AnexarTests(LogsDePrueba, TestCase):
    def test_el_primer_asiento_abre_la_bitacora_con_el_genesis_y_encadena(self):
        vaciar_bitacora()
        fila = servicios.anexar("u-1", "prueba.uno", "m07_sesion", "s-1", nuevo={"x": 1})
        genesis = Bitacora.objects.get(secuencia=1)
        self.assertEqual((genesis.accion, genesis.huella_previa), ("auditoria.bitacora_abierta", huella.GENESIS))
        self.assertEqual((fila.secuencia, fila.huella_previa), (2, genesis.huella))
        self.assertEqual(fila.huella, huella.calcular(genesis.huella, fila.canonico()))
        tramo = BitacoraTramo.objects.get(estado="activa")
        self.assertEqual((tramo.desde_secuencia, tramo.hasta_secuencia, tramo.huella_cierre), (1, 2, fila.huella))
        self.assertLogged(evento="bitacora.asiento", canal="auditoria")
        for linea in self.lineas_log(evento="bitacora.asiento"):
            self.assertNotIn("valor_nuevo", str(linea["detalle"]))

    def test_la_secuencia_es_monotona_sin_huecos_y_cada_huella_enlaza_con_la_anterior(self):
        for i in range(5):
            servicios.anexar("u-1", "prueba.seq", nuevo={"i": i})
        filas = list(Bitacora.objects.order_by("secuencia"))
        self.assertEqual([f.secuencia for f in filas], list(range(1, len(filas) + 1)))
        for anterior, actual in zip(filas, filas[1:]):
            self.assertEqual(actual.huella_previa, anterior.huella)
            self.assertEqual(actual.huella, huella.calcular(anterior.huella, actual.canonico()))

    def test_tst_071_cinco_acciones_sensibles_dejan_actor_fecha_valor_anterior_y_motivo(self):
        with contexto.con(usuario_id="admin-1", rol_codigo="ADMIN", origen="api", corr="c-1"):
            servicios.anexar("admin-1", "calificacion.modificada", "calificacion", "cal-1", anterior={"valor_interno": 72},
                             nuevo={"valor_interno": 80}, motivo="Error de suma")
            servicios.anexar("admin-1", "identidad.rol.asignado", "m01_usuario_rol", "ur-1", nuevo={"rol": "TEACHER"})
            servicios.anexar("admin-1", "dispositivos.bloqueado", "m09_dispositivo", "d-1", anterior={"bloqueado": False}, nuevo={"bloqueado": True})
            servicios.anexar("admin-1", "identidad.escalada.concedida", "m01_usuario_permiso", "p-1", nuevo={"permiso": "audit.export"})
            servicios.anexar("admin-1", "auditoria.tramo_exportado", "m19_bitacora_tramo", "t-1", nuevo={"desde": 1}, motivo="Inspección")
        filas = list(Bitacora.objects.filter(usuario_id="admin-1").order_by("secuencia"))
        self.assertEqual(len(filas), 5)
        for f in filas:
            self.assertEqual((f.actor_tipo, f.roles_activos, f.origen, f.correlacion_id), ("usuario", ["ADMIN"], "api", "c-1"))
            self.assertGreater(f.ocurrido_en, 0)
        calificacion = filas[0]
        self.assertEqual((calificacion.valor_anterior, calificacion.valor_nuevo, calificacion.motivo, calificacion.modulo),
                         ({"valor_interno": 72}, {"valor_interno": 80}, "Error de suma", "evaluacion"))

    def test_ac_054_una_accion_con_motivo_obligatorio_no_se_anexa_sin_motivo(self):
        antes = Bitacora.objects.count()
        with self.assertRaises(errores.MotivoRequerido):
            servicios.anexar("p-1", "calificacion.modificada", "calificacion", "c-1", anterior={"valor_interno": 72}, nuevo={"valor_interno": 80})
        self.assertEqual(Bitacora.objects.count(), antes)

    def test_una_accion_fuera_del_catalogo_falla_en_pruebas_y_se_asienta_como_desconocida_en_produccion(self):
        with self.assertRaises(errores.AccionDesconocida):
            servicios.anexar("u-1", "inventada.cosa")
        with override_settings(AVACOM_LMS_AUDITORIA_ESTRICTA=False):
            fila = servicios.anexar("u-1", "inventada.cosa", nuevo={"k": 1})
        self.assertEqual((fila.accion, fila.modulo), ("auditoria.accion_desconocida", "auditoria"))
        self.assertEqual(fila.valor_nuevo, {"accion_original": "inventada.cosa", "k": 1})

    def test_el_actor_se_deduce_del_contexto_y_del_declarado(self):
        self.assertEqual(servicios.anexar("", "prueba.a").actor_tipo, "sistema")
        self.assertEqual(servicios.anexar("sistema", "prueba.a").actor_tipo, "sistema")
        declarado = servicios.anexar("docente", "prueba.a")
        self.assertEqual((declarado.actor_tipo, declarado.usuario_id), ("declarado", "docente"))
        with contexto.con(usuario_id="u-9", rol_codigo="TEACHER", origen="ws", dispositivo_id=None):
            con_sesion = servicios.anexar("u-9", "prueba.a")
        self.assertEqual((con_sesion.actor_tipo, con_sesion.usuario_id, con_sesion.origen, con_sesion.roles_activos), ("usuario", "u-9", "ws", ["TEACHER"]))
        with contexto.con(origen="instalador"):
            self.assertEqual(servicios.anexar("instalador", "instalacion.organizacion_creada").actor_tipo, "instalador")

    def test_si_falla_la_escritura_de_la_bitacora_el_caso_de_uso_revierte_entero(self):
        """§1.2 (bad path): rollback completo, traza en backend-errores.log y cero asientos parciales."""
        antes = Bitacora.objects.count()
        with self.assertRaises(errores.BitacoraNoDisponible), transaction.atomic():
            BitacoraTramo.objects.create(desde_secuencia=999, hasta_secuencia=999, huella_cierre="a" * 64, estado="rotada", abierta=False)   # «el hecho»
            with mock.patch.object(Bitacora.objects, "create", side_effect=DatabaseError("disco lleno")):
                servicios.anexar("u-1", "prueba.bad")
        self.assertEqual(Bitacora.objects.count(), antes)
        self.assertFalse(BitacoraTramo.objects.filter(desde_secuencia=999).exists())
        lineas = self.assertLogged(evento="bitacora.escritura_fallo", nivel="ERROR", canal="escritura")
        self.assertIn("disco lleno", lineas[0]["traza"] or "")


class InmutabilidadTests(TestCase):
    """AC-081 / INV-027: editar o borrar → denegado, asiento intacto y asiento NUEVO del intento."""

    def setUp(self):
        self.fila = servicios.anexar("u-1", "prueba.inmutable", nuevo={"a": 1})

    def _intentos(self) -> list[Bitacora]:
        return list(Bitacora.objects.filter(accion="auditoria.alteracion_intentada").order_by("secuencia"))

    def test_save_de_una_fila_existente_y_delete_por_el_orm(self):
        self.fila.motivo = "editado"
        with self.assertRaises(errores.BitacoraInmutable):
            self.fila.save()
        with self.assertRaises(errores.BitacoraInmutable):
            self.fila.delete()
        with self.assertRaises(errores.BitacoraInmutable):
            Bitacora.objects.filter(pk=self.fila.pk).update(motivo="x")
        with self.assertRaises(errores.BitacoraInmutable):
            Bitacora.objects.filter(pk=self.fila.pk).delete()
        with self.assertRaises(errores.BitacoraInmutable):
            Bitacora.objects.bulk_update([self.fila], ["motivo"])
        self.assertIsNone(Bitacora.objects.get(pk=self.fila.pk).motivo)
        intentos = self._intentos()
        self.assertEqual(len(intentos), 5)
        self.assertEqual({i.valor_nuevo["operacion"] for i in intentos}, {"save", "update", "delete", "bulk_update"})
        self.assertTrue(all(i.resultado == "denegado" for i in intentos))

    def test_sql_directo_lo_aborta_el_trigger(self):
        self.assertTrue(triggers.completos(connection))
        for sql in ("UPDATE m19_bitacora SET motivo = 'x' WHERE secuencia = %s", "DELETE FROM m19_bitacora WHERE secuencia = %s"):
            with self.assertRaises((IntegrityError, DatabaseError)) as ctx, transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, [self.fila.secuencia])
            self.assertIn("bitacora_inmutable", str(ctx.exception))
        self.assertTrue(Bitacora.objects.filter(pk=self.fila.pk, motivo__isnull=True).exists())

    def test_la_tabla_vieja_queda_de_solo_lectura_y_la_vista_sigue_respondiendo(self):
        with self.assertRaises((IntegrityError, DatabaseError)), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("INSERT INTO m19_auditoria_legado (actor_id, accion, objeto_tabla, objeto_id, momento) VALUES ('a', 'x', '', '', 1)")
        vista = Auditoria.objects.get(accion="prueba.inmutable")
        self.assertEqual((vista.id, vista.actor_id, vista.valor_nuevo, vista.momento), (self.fila.secuencia, "u-1", {"a": 1}, self.fila.ocurrido_en))


class ContextoDePeticionTests(BaseAcceso):
    def test_los_asientos_de_los_modulos_llevan_actor_dispositivo_origen_y_correlacion(self):
        r = self.admin.post(f"/api/dispositivos/{self.tableta['id']}/bloquear/", {"motivo": "prueba"}, format="json",
                            HTTP_X_AVACOM_DISPOSITIVO=self.tableta["id"], HTTP_X_AVACOM_CORRELACION="ops-corr-0001")
        self.assertEqual(r.status_code, 200, r.content)
        asiento = Bitacora.objects.get(accion="dispositivos.bloqueado", objeto_id=self.tableta["id"])
        self.assertEqual((asiento.actor_tipo, asiento.usuario_id, asiento.roles_activos), ("usuario", self.admin_id, ["ADMIN"]))
        self.assertEqual((asiento.origen, asiento.dispositivo_id, asiento.correlacion_id, asiento.modulo),
                         ("api", self.tableta["id"], "ops-corr-0001", "dispositivos"))
        # Compatibilidad: la vista m19_auditoria sigue mostrando lo mismo que antes.
        self.assertEqual(Auditoria.objects.get(accion="dispositivos.bloqueado", objeto_id=self.tableta["id"]).actor_id, self.admin_id)

    def test_sin_cabecera_de_dispositivo_el_asiento_no_inventa_el_aparato(self):
        self.admin.post(f"/api/dispositivos/{self.tableta['id']}/bloquear/", {"motivo": "prueba"}, format="json")
        self.assertIsNone(Bitacora.objects.get(accion="dispositivos.bloqueado").dispositivo_id)

    def test_los_cuatro_puertos_y_el_expediente_escriben_en_la_misma_cadena(self):
        from acceso.infraestructura.contenedor import servicios as acceso_s
        from classroom_engine.infraestructura.contenedor import servicios as aula_s
        from device_manager.infraestructura.contenedor import servicios as disp_s
        from expediente import servicios as expediente_s
        from modo_estudio.infraestructura.contenedor import servicios as estudio_s
        with acceso_s().uow() as uow:
            uow.auditoria.registrar("u-1", "prueba.acceso", "t", "1", {"n": 1})
        with aula_s().uow() as uow:
            uow.auditoria.registrar("u-1", "prueba.aula", "t", "2", anterior={"a": 0}, nuevo={"a": 1}, motivo="m")
        with disp_s().uow() as uow:
            uow.auditoria.registrar("u-1", "prueba.dispositivos", "t", "3")
        with estudio_s().uow() as uow:
            uow.auditoria.registrar("u-1", "prueba.estudio", "t", "4", resultado="denegado")
        expediente_s.auditar("u-1", "prueba.expediente", "t", "5")
        filas = list(Bitacora.objects.filter(accion__startswith="prueba.").order_by("secuencia"))
        self.assertEqual([f.accion for f in filas], ["prueba.acceso", "prueba.aula", "prueba.dispositivos", "prueba.estudio", "prueba.expediente"])
        self.assertEqual((filas[1].valor_anterior, filas[1].motivo, filas[3].resultado), ({"a": 0}, "m", "denegado"))
        r = dom_tramo.verificar([{**f.canonico(), "huella_previa": f.huella_previa, "huella": f.huella} for f in Bitacora.objects.order_by("secuencia")],
                                huella.GENESIS, 1)
        self.assertTrue(r.ok, r.como_dict())

    def test_toda_denegacion_403_deja_asiento_con_roles_y_permiso(self):
        estudiante = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        r = estudiante.post(f"/api/dispositivos/{self.tableta['id']}/bloquear/", {"motivo": "x"}, format="json")
        self.assertEqual(r.status_code, 403, r.content)
        asiento = Bitacora.objects.get(accion="acceso.denegado")
        self.assertEqual((asiento.resultado, asiento.usuario_id, asiento.roles_activos), ("denegado", self.estudiante_id, ["STUDENT"]))
        self.assertEqual((asiento.valor_nuevo["ruta"], asiento.valor_nuevo["metodo"], asiento.valor_nuevo["codigo"]),
                         (f"/api/dispositivos/{self.tableta['id']}/bloquear/", "POST", "sin_permiso"))
        self.assertTrue(asiento.valor_nuevo.get("permiso_solicitado"))


class CadenaEnLaBaseTests(TestCase):
    def test_la_base_de_pruebas_arranca_con_una_cadena_vacia_pero_valida(self):
        tramo = app.tramo_activo(bloquear=False)
        self.assertIsNotNone(tramo)
        self.assertEqual(tramo.desde_secuencia, 1)
        filas = list(Bitacora.objects.order_by("secuencia"))
        self.assertEqual(filas[0].accion, "auditoria.bitacora_abierta")
        self.assertEqual(filas[0].huella_previa, huella.GENESIS)
        self.assertEqual(tramo.huella_cierre, filas[-1].huella)
        self.assertEqual(dom.ACTOR_SISTEMA, filas[0].actor_tipo)

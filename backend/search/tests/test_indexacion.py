"""
La indexación de Search (FUN-209, FUN-214, FUN-215, FUN-217 · CAP-128): el índice se construye la primera vez, se mantiene con los eventos de los módulos propietarios
(idempotente y atómico), se purga lo retirado, se reconstruye tras una restauración (sin clase en curso) y declara su estado (construyéndose, consultable, rezagado,
reconstruyéndose). Las entidades nacen por las rutas reales de sus módulos: los eventos son los de verdad.
"""
from __future__ import annotations

from unittest import mock

from audit.models import Bitacora
from evaluacion import models as m10
from evaluacion.dominio import catalogos as ev

from nodo.pruebas import cola
from .. import models as m
from ..aplicacion.indexar import Sincronizar
from ..dominio import catalogos as cat
from ..infraestructura.fuentes import FuenteEvaluaciones
from ..infraestructura.repositorios import OutboxDjango
from .base import BaseSearch


class ConstruccionTests(BaseSearch):
    def test_el_indice_nace_construyendose_y_la_primera_consulta_lo_construye(self):
        a = self.evaluacion("Fracciones")
        e = self.estado()
        self.assertEqual(e["index_status"], "construyendose")
        self.assertIn("construyendo", e["index_notice"])
        self.assertEqual(m.Documento.objects.count(), 0)
        r = self.buscar("fracciones")
        self.assertEqual((r["index_status"], self.ids(r)), ("consultable", [a["id"]]))
        self.assertEqual(self.estado()["index_status"], "consultable")
        construido = m.EstadoIndice.objects.get(pk="indice")
        self.assertEqual(construido.estado, "consultable")
        self.assertIsNotNone(construido.construido_en)
        self.assertEqual(self.eventos_search("busqueda.indice_reconstruido.v1"), ["busqueda.indice_reconstruido.v1"])

    def test_construir_indexa_lo_que_ya_existia_de_los_tres_modulos(self):
        self.evaluacion("Fracciones")
        self.estudio("l1-three-states")
        self.clase()
        m10.EventoSalida.objects.all().delete()                  # aunque sus colas ya no tengan los eventos, el índice se construye de las entidades
        self.buscar("fracciones")
        self.assertEqual({t: len(self.documentos(t)) for t in cat.TIPOS_LOCALES}, {"assessment": 1, "study": 1, "class": 1})

    def test_los_borradores_y_los_archivados_no_se_indexan(self):
        self.evaluacion("Borrador de fracciones", iniciar=False)
        archivada = self.evaluacion("Fracciones archivadas")
        m10.Asignacion.objects.filter(pk=archivada["id"]).update(estado=ev.ARCHIVADA, cerrada_en=self.t, archivada_en=self.t)
        visible = self.evaluacion("Fracciones visibles")
        self.assertEqual(self.ids(self.buscar("fracciones")), [visible["id"]])
        self.assertEqual(len(self.documentos("assessment")), 1)

    def test_nunca_se_guarda_una_clave_ni_un_alumno_ni_contenido_de_curso(self):
        self.evaluacion("Fracciones")
        self.buscar("fracciones")
        for fila in self.documentos():
            texto = " ".join(str(v) for v in (fila.titulo, fila.descripcion, fila.palabras, fila.contexto, fila.referencia)).lower()
            for prohibido in ("juan", "clave", "correcta", "respuesta"):
                self.assertNotIn(prohibido, texto)


class IncrementalTests(BaseSearch):
    sincronizar_al_consultar = False

    def setUp(self):
        super().setUp()
        self.reconstruir()                                        # parte de un índice construido: lo que sigue es incremental

    def test_un_evento_indexa_la_entidad_y_emite_los_eventos(self):
        a = self.evaluacion("Fracciones")
        self.assertEqual(self.documentos("assessment"), [])
        r = self.sincronizar()
        self.assertEqual((r["indexados"], r["fallidos"]), (1, []))
        doc = self.documentos("assessment")[0]
        self.assertEqual((doc.entidad_id, doc.titulo, doc.grupo_id, doc.estado), (a["id"], "Fracciones", self.grupo["id"], "activa"))
        self.assertEqual(doc.profesor_id, self.docente_id)
        emitidos = self.eventos_search()
        self.assertEqual(emitidos.count("busqueda.entidad_indexada.v1"), 1)
        self.assertEqual(emitidos.count("busqueda.reindexacion_incremental.v1"), 1)
        carga = cola("search").get(tipo_evento="busqueda.entidad_indexada.v1").carga
        self.assertEqual((carga["tipo"], carga["entidad_id"], carga["resultado"]), ("assessment", a["id"], "nuevo"))
        self.assertEqual(self.buscar("fracciones")["total"], 1)

    def test_eventos_repetidos_no_duplican_nada_ni_emiten_de_nuevo(self):
        self.evaluacion("Fracciones")
        self.sincronizar()
        antes = (len(self.documentos()), self.eventos_search().count("busqueda.entidad_indexada.v1"))
        m.MarcaDeLectura.objects.all().update(secuencia=0)        # se vuelve a leer TODA la cola: cada evento llega otra vez
        for _ in range(2):
            self.sincronizar()
            m.MarcaDeLectura.objects.all().update(secuencia=0)
        despues = (len(self.documentos()), self.eventos_search().count("busqueda.entidad_indexada.v1"))
        self.assertEqual(antes, despues)
        self.assertEqual(self.buscar("fracciones")["total"], 1)

    def test_varios_eventos_de_la_misma_entidad_se_leen_una_vez(self):
        self.evaluacion("Fracciones")                              # nivel definido + asignada: varios eventos, una entidad
        r = self.sincronizar()
        self.assertEqual(r["leidos"] >= 2, True)
        self.assertEqual(r["indexados"], 1)

    def test_un_cambio_en_el_dueno_se_aplica_con_su_evento_y_se_emite_actualizado(self):
        a = self.evaluacion("Fracciones")
        self.sincronizar()
        m10.Asignacion.objects.filter(pk=a["id"]).update(titulo="Fracciones y decimales", descripcion="Nueva guía")
        m10.EventoSalida.objects.create(agregado_tipo="Asignacion", agregado_id=a["id"], tipo_evento=ev.EV_PLAZO_CONFIGURADO,
                                        carga={"asignacion_id": a["id"], "limite_en": self.t + 1000})
        r = self.sincronizar()
        self.assertEqual(r["indexados"], 1)
        doc = self.documentos("assessment")[0]
        self.assertEqual((doc.titulo, doc.descripcion), ("Fracciones y decimales", "Nueva guía"))
        self.assertEqual(self.buscar("decimales")["total"], 1)
        resultados = list(cola("search").filter(tipo_evento="busqueda.entidad_indexada.v1").values_list("carga__resultado", flat=True))
        self.assertEqual(resultados, ["nuevo", "actualizado"])

    def test_una_entidad_cerrada_o_archivada_se_purga_con_su_evento(self):
        a = self.evaluacion("Fracciones")
        self.sincronizar()
        self.assertEqual(len(self.documentos("assessment")), 1)
        m10.Asignacion.objects.filter(pk=a["id"]).update(estado=ev.ARCHIVADA, cerrada_en=self.t, archivada_en=self.t)
        m10.EventoSalida.objects.create(agregado_tipo="Asignacion", agregado_id=a["id"], tipo_evento=ev.EV_ASIGNACION_CERRADA, carga={"asignacion_id": a["id"]})
        r = self.sincronizar()
        self.assertEqual(r["purgados"], 1)
        self.assertEqual(self.documentos("assessment"), [])
        purga = cola("search").get(tipo_evento="busqueda.entradas_purgadas.v1").carga
        self.assertEqual((purga["tipo"], purga["entradas"], purga["causa"]), ("assessment", 1, "evento"))

    def test_una_clase_se_actualiza_al_cerrarse(self):
        c = self.clase()
        self.sincronizar()
        self.assertEqual(self.documentos("class")[0].estado, "abierta")
        self.cerrar_clase(c["id"])
        self.sincronizar()
        self.assertEqual(self.documentos("class")[0].estado, "cerrada")

    def test_una_asignacion_de_estudio_se_indexa(self):
        e = self.estudio("l1-three-states", titulo="Estudio de los estados")
        self.sincronizar()
        self.assertEqual([(d.entidad_id, d.titulo) for d in self.documentos("study")], [(e["id"], "Estudio de los estados")])

    def test_la_marca_avanza_con_lo_aplicado_y_en_la_misma_transaccion(self):
        self.evaluacion("Fracciones")
        self.sincronizar()
        ultima = m10.EventoSalida.objects.order_by("-id").first().id
        self.assertEqual(m.MarcaDeLectura.objects.get(pk="evaluacion").secuencia, ultima)
        self.assertEqual(set(m.MarcaDeLectura.objects.values_list("fuente", flat=True)), {"evaluacion", "estudio", "aula"})
        # un fallo A MEDIAS no deja la marca adelantada sin lo aplicado: se revierte todo
        self.evaluacion("Fracciones dos")
        antes = m.MarcaDeLectura.objects.get(pk="evaluacion").secuencia
        with mock.patch("search.infraestructura.repositorios.OutboxDjango.publicar", side_effect=RuntimeError("se cayó")):
            with self.assertRaises(RuntimeError):
                Sincronizar(self.servicios()).ejecutar()
        self.assertEqual(m.MarcaDeLectura.objects.get(pk="evaluacion").secuencia, antes)
        self.assertEqual(len(self.documentos("assessment")), 1)
        self.sincronizar()
        self.assertEqual(len(self.documentos("assessment")), 2)

    def test_una_entidad_que_falla_no_detiene_a_las_demas_y_se_deja_atras_con_asiento(self):
        a1 = self.evaluacion("Fracciones uno")
        a2 = self.evaluacion("Fracciones dos")
        original = FuenteEvaluaciones.documento

        def documento(fuente, entidad_id):
            if entidad_id == a1["id"]:
                raise RuntimeError("no se puede leer")
            return original(fuente, entidad_id)

        servicios = self.servicios()
        with mock.patch.object(FuenteEvaluaciones, "documento", documento):
            r = Sincronizar(servicios).ejecutar()
            self.assertEqual((r["indexados"], len(r["fallidos"])), (1, 1))
            self.assertEqual([d.entidad_id for d in self.documentos("assessment")], [a2["id"]])           # la otra sí se indexó
            marca = m.MarcaDeLectura.objects.get(pk="evaluacion")
            self.assertEqual(marca.fallos, 1)
            primero = m10.EventoSalida.objects.filter(carga__asignacion_id=a1["id"]).order_by("id").first().id
            self.assertLess(marca.secuencia, primero)                                                      # la marca NO pasó de largo
            self.assertEqual(self.estado()["index_status"], "rezagado")
            for _ in range(cat.MAX_FALLOS_DE_EVENTO - 1):
                Sincronizar(servicios).ejecutar()
        marca = m.MarcaDeLectura.objects.get(pk="evaluacion")
        self.assertEqual((marca.fallos, marca.fallo_secuencia), (0, 0))
        self.assertGreaterEqual(marca.secuencia, primero)                                                  # tras los reintentos se dejó atrás…
        asiento = Bitacora.objects.get(accion="busqueda.evento_omitido")                                   # …pero con asiento: nunca en silencio
        self.assertEqual(asiento.valor_nuevo["fuente"], "evaluacion")
        # Lo dejado atrás no se recupera solo (su evento ya pasó); se corrige con el siguiente evento de esa entidad o con una reconstrucción, y el asiento lo avisa.
        self.sincronizar()
        self.assertEqual([d.entidad_id for d in self.documentos("assessment")], [a2["id"]])
        self.reconstruir()
        self.assertEqual(sorted(d.entidad_id for d in self.documentos("assessment")), sorted([a1["id"], a2["id"]]))

    def test_la_cola_de_un_modulo_que_no_contesta_no_detiene_a_los_demas(self):
        self.evaluacion("Fracciones")
        self.estudio("l1-three-states", titulo="Estudio")
        with mock.patch.object(FuenteEvaluaciones, "eventos_desde", side_effect=RuntimeError("la evaluación no contesta")):
            r = Sincronizar(self.servicios()).ejecutar()
        self.assertEqual(len(self.documentos("study")), 1)
        self.assertEqual(r["fallidos"][0]["fuente"], "evaluacion")
        self.assertEqual(self.estado()["index_status"], "rezagado")
        self.sincronizar()
        self.assertEqual(self.estado()["index_status"], "consultable")


class ReconstruccionTests(BaseSearch):
    def sembrar(self):
        self.a = self.evaluacion("Fracciones")
        self.e = self.estudio("l1-three-states", titulo="Estudio")
        self.c = self.clase()
        self.cerrar_clase(self.c["id"])

    def test_reconstruir_tras_una_restauracion_recupera_todo(self):
        self.sembrar()
        self.buscar("fracciones")
        m.Documento.objects.all().delete()                         # el respaldo se restauró SIN el índice (o con uno viejo)
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM m21_documento_fts")
        m.MarcaDeLectura.objects.all().delete()
        r = self.reconstruir()
        self.assertEqual(r["documentos"], {"assessment": 1, "study": 1, "class": 1})
        self.assertEqual((r["total"], r["estado"]), (3, "consultable"))
        self.assertEqual(self.ids(self.buscar("fracciones")), [self.a["id"]])
        self.assertEqual(self.buscar("estudio")["total"], 1)
        self.assertEqual(self.buscar("estados", type="class")["total"], 1)
        marca = m.MarcaDeLectura.objects.get(pk="evaluacion").secuencia
        self.assertEqual(marca, m10.EventoSalida.objects.order_by("-id").first().id)       # las marcas quedan al día: no se relee lo ya reconstruido

    def test_reconstruir_emite_su_evento_y_deja_asiento(self):
        self.sembrar()
        self.reconstruir()
        carga = cola("search").filter(tipo_evento="busqueda.indice_reconstruido.v1").order_by("-id").first().carga
        self.assertEqual((carga["total"], carga["inicial"]), (3, False))
        asiento = Bitacora.objects.filter(accion="busqueda.indice_reconstruido").order_by("-secuencia").first()
        self.assertEqual(asiento.usuario_id, self.admin_id)

    def test_reconstruir_dos_veces_da_lo_mismo(self):
        self.sembrar()
        self.reconstruir()
        primero = [(d.tipo, d.entidad_id, d.huella) for d in self.documentos()]
        self.reconstruir()
        self.assertEqual([(d.tipo, d.entidad_id, d.huella) for d in self.documentos()], primero)

    def test_con_una_clase_en_curso_no_se_reconstruye(self):
        c = self.clase()
        r = self.admin.post("/api/search/reindex/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "sesion_activa"))
        self.cerrar_clase(c["id"])
        self.reconstruir()

    def test_una_reconstruccion_en_marcha_no_se_pisa_pero_una_abandonada_si(self):
        self.reconstruir()
        m.EstadoIndice.objects.filter(pk="indice").update(estado="reconstruyendose", reconstruccion_desde=self.t)
        r = self.admin.post("/api/search/reindex/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "reconstruccion_en_curso"))
        self.t += cat.RECONSTRUCCION_ABANDONADA_MS + 1                                        # el nodo se apagó a la mitad hace rato
        self.reconstruir()
        self.assertEqual(self.estado()["index_status"], "consultable")

    def test_mientras_se_reconstruye_se_sigue_consultando_y_se_avisa(self):
        a = self.evaluacion("Fracciones")
        self.reconstruir()
        m.EstadoIndice.objects.filter(pk="indice").update(estado="reconstruyendose", reconstruccion_desde=self.t)
        r = self.buscar("fracciones")
        self.assertEqual((r["index_status"], self.ids(r)), ("reconstruyendose", [a["id"]]))
        self.assertIn("reconstruyendo", r["index_notice"])

    def test_si_la_reconstruccion_falla_el_indice_anterior_queda_intacto(self):
        a = self.evaluacion("Fracciones")
        self.reconstruir()
        with mock.patch.object(FuenteEvaluaciones, "todos", side_effect=RuntimeError("se cayó a la mitad")):
            with self.assertRaises(RuntimeError):
                from ..aplicacion.indexar import Reconstruir
                from ..aplicacion.puertos import Actor
                Reconstruir(self.servicios()).ejecutar(Actor(id=cat.SISTEMA), desde_el_sistema=True)
        self.assertEqual([d.entidad_id for d in self.documentos("assessment")], [a["id"]])
        estado = m.EstadoIndice.objects.get(pk="indice")
        self.assertEqual(estado.estado, "consultable")
        self.assertIn("reconstruccion", estado.error)
        self.assertEqual(self.buscar("fracciones")["total"], 1)

    def test_el_comando_de_gestion_reconstruye(self):
        from io import StringIO

        from django.core.management import call_command

        self.sembrar()
        salida = StringIO()
        call_command("search_reconstruir", stdout=salida)
        self.assertIn("3 documentos", salida.getvalue())


class EventosTests(BaseSearch):
    def test_solo_se_emiten_los_eventos_que_ocurren_y_nunca_los_de_la_v1(self):
        self.evaluacion("Fracciones")
        self.buscar("fracciones")
        self.reconstruir()
        m10.Asignacion.objects.all().delete()
        self.buscar("fracciones")
        emitidos = set(self.eventos_search())
        self.assertLessEqual(emitidos, set(cat.EVENTOS_QUE_SE_EMITEN))
        self.assertTrue({"busqueda.indice_reconstruido.v1", "busqueda.entradas_purgadas.v1"} <= emitidos)
        self.assertFalse(emitidos & {"busqueda.texto_indexado.v1", "busqueda.extraccion_encolada.v1"})

    def test_la_cola_rechaza_un_evento_que_no_se_emite_todavia(self):
        for tipo in (cat.EV_TEXTO_INDEXADO, cat.EV_EXTRACCION_ENCOLADA, "busqueda.inventado.v1"):
            with self.assertRaises(ValueError):
                OutboxDjango().publicar(tipo, "x", {})

    def test_los_seis_eventos_del_maestro_estan_declarados_con_sus_identificadores(self):
        self.assertEqual(set(cat.EVENTOS), {
            "busqueda.entidad_indexada.v1", "busqueda.texto_indexado.v1", "busqueda.reindexacion_incremental.v1", "busqueda.indice_reconstruido.v1",
            "busqueda.extraccion_encolada.v1", "busqueda.entradas_purgadas.v1"})

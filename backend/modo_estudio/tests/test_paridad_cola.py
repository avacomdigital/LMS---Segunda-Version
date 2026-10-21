"""
Paridad de MOD-008 con la cola única (MOD-015, Fase 3): los mismos hechos del modo de estudio producen los mismos eventos que antes del corte (tipo, versión, agregado y carga),
UNA sola vez y SÓLO en `m15_evento`; `m08_evento_salida` queda como historia, y `servicios.eventos_desde` —lo que leen Reportes y Search— la sirve con lo nuevo como un flujo
continuo. Además, el único tipo con dos autores del repo (`evaluacion.respuesta_registrada.v1`, D-25) entra firmado por `modo_estudio` y no se sirve a quien lee `evaluacion`.
"""
from __future__ import annotations

from nodo import servicios as nodo
from nodo.pruebas import cola, como_consumidor, espiar, sembrar_historia

from .. import models as m
from .. import servicios
from ..dominio import catalogos as cat
from ..infraestructura.repositorios import OutboxDjango
from .base import BLOQUES_L1
from .test_practica import BasePractica

MODULO = "modo_estudio"
TIPOS = (cat.EV_ASIGNACION_CREADA, cat.EV_LECCION_ABIERTA, cat.EV_LECCION_COMPLETADA)       # parte de lo que Reportes y Search leen de esta fuente


def _publicado(llamada) -> dict:
    (agregado_tipo, agregado_id, tipo, carga), _ = llamada
    return {"tipo": tipo, "agregado_tipo": agregado_tipo, "agregado_id": str(agregado_id)[:64], "carga": carga}


def _en_cola(fila) -> dict:
    return {"tipo": fila.tipo_evento, "agregado_tipo": fila.agregado_tipo, "agregado_id": fila.agregado_id, "carga": fila.carga}


class ParidadEstudioTests(BasePractica):
    def escenario(self) -> tuple[dict, list[dict]]:
        """Una asignación de estudio, la lección abierta y recorrida entera por Juan, y una práctica con una respuesta: lo que publican los casos de uso."""
        with espiar(OutboxDjango) as llamadas:
            a = self.crear_asignacion()
            self.json_ok(self.ver(f"/lecciones/{a['id']}/"))
            self.json_ok(self.bloques(a["id"], BLOQUES_L1))
            self.json_ok(self.enviar("post", f"/lecciones/{a['id']}/completar/"))
            with self.biblioteca_que_califica():
                p = self.abrir(a["id"])["practica"]
                self.json_ok(self.responder(p["id"], self.correctas("l1-act-q1")))
        return a, [_publicado(llamada) for llamada in llamadas]

    def test_cada_hecho_deja_un_solo_evento_en_la_cola_unica_y_ninguno_en_la_antigua(self):
        antes = cola(MODULO).count()
        a, publicados = self.escenario()
        tipos = [p["tipo"] for p in publicados]
        for esperado in (cat.EV_ASIGNACION_CREADA, cat.EV_LECCION_ABIERTA, cat.EV_LECCION_COMPLETADA, cat.EV_RESPUESTA_REGISTRADA):
            self.assertIn(esperado, tipos)
        nuevos = list(cola(MODULO))[antes:]
        self.assertEqual([_en_cola(f) for f in nuevos], publicados)
        self.assertEqual({(f.modulo, f.version, f.catalogado, f.carga_omitida) for f in nuevos}, {(MODULO, 1, True, False)})
        self.assertEqual(m.EventoSalida.objects.count(), 0)                                           # sin doble escritura
        esperados = [t for t in tipos if t in TIPOS]
        self.assertEqual(self.eventos(*TIPOS)[-len(esperados):], esperados)                           # lo que las pruebas del módulo ya comprobaban, leído de la cola única
        # D-25: la respuesta de práctica lleva el tipo de MOD-010 pero la firma el modo de estudio; quien lee la fuente `evaluacion` no la recibe
        practica = [f for f in nuevos if f.tipo_evento == cat.EV_RESPUESTA_REGISTRADA]
        self.assertEqual(len(practica), 1)
        self.assertEqual((practica[0].modulo, practica[0].carga["modo"], practica[0].carga["asignacion_id"]), (MODULO, "estudio", a["id"]))
        self.assertEqual(nodo.leer("evaluacion", 0, 100, (cat.EV_RESPUESTA_REGISTRADA,))[0], [])
        self.assertEqual([e["secuencia"] for e in servicios.eventos_desde(0, 100, (cat.EV_RESPUESTA_REGISTRADA,))[0]], [practica[0].id])

    def test_la_historia_se_sirve_con_lo_nuevo_y_una_marca_previa_al_corte_no_pierde_ni_repite(self):
        _, historia = self.escenario()
        ids = sembrar_historia(m.EventoSalida, MODULO, historia, creado_en=1_000)
        self.assertEqual(servicios.ultima_secuencia(), ids[-1])
        _, _ = self.escenario()
        nuevos = [f.id for f in cola(MODULO) if f.id > ids[-1]]
        self.assertEqual(servicios.ultima_secuencia(), nuevos[-1])
        de_interes = [i for i, e in zip(ids, historia) if e["tipo"] in TIPOS]
        nuevos_de_interes = [f.id for f in cola(MODULO).filter(id__gt=ids[-1], tipo_evento__in=TIPOS)]
        self.assertGreaterEqual(len(de_interes), 3)
        leer = lambda marca, limite, tipos: servicios.eventos_desde(marca, limite, tipos)          # noqa: E731 — lo que llaman Reportes y Search
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, 0, TIPOS)], de_interes + nuevos_de_interes)
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, de_interes[1], TIPOS)], de_interes[2:] + nuevos_de_interes)
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, ids[-1], TIPOS)], nuevos_de_interes)
        self.assertEqual(servicios.eventos_desde(nuevos[-1], 10, TIPOS), ([], nuevos[-1]))
        primero = como_consumidor(leer, 0, TIPOS)[0]
        self.assertEqual((primero["legado"], primero["tipo"], primero["carga"]), (True, historia[0]["tipo"], historia[0]["carga"]))
        self.assertEqual(m.EventoSalida.objects.count(), len(ids))                                    # la historia sigue intacta (BR-016)

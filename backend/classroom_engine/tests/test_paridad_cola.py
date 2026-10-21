"""
Paridad de MOD-007 con la cola única (MOD-015, Fase 3): los mismos hechos del aula producen los mismos eventos que antes del corte (tipo, versión, agregado y carga), UNA sola vez
y SÓLO en `m15_evento`; `m07_evento_salida` queda como historia, y `servicios.eventos_desde` —lo que leen Reportes y Search— la sirve con lo nuevo como un flujo continuo: una
marca previa al corte no pierde ni repite, y la marca cero reproduce toda la historia (BR-007).
"""
from __future__ import annotations

from nodo import servicios as nodo
from nodo.pruebas import cola, como_consumidor, espiar, sembrar_historia

from .. import models as m
from .. import servicios
from ..dominio import sesion as dom
from ..infraestructura.repositorios import OutboxDjango
from .test_sesiones import ConSesionDeClase

MODULO = "classroom_engine"
TIPOS = (dom.EV_SESION_INICIADA, dom.EV_PRESENCIA_REGISTRADA, dom.EV_SESION_FINALIZADA)      # lo que Reportes y Search leen de esta fuente


def _publicado(llamada) -> dict:
    (agregado_tipo, agregado_id, tipo, carga), _ = llamada
    return {"tipo": tipo, "agregado_tipo": agregado_tipo, "agregado_id": agregado_id, "carga": carga}


def _en_cola(fila) -> dict:
    return {"tipo": fila.tipo_evento, "agregado_tipo": fila.agregado_tipo, "agregado_id": fila.agregado_id, "carga": fila.carga}


class ParidadAulaTests(ConSesionDeClase):
    def escenario(self, persona: str) -> tuple[dict, list[dict]]:
        """Una clase: se inicia, se une una tableta y se cierra. Devuelve la sesión y lo que los casos de uso publicaron."""
        with espiar(OutboxDjango) as llamadas:
            s = self.iniciar()
            self.unirse(s, persona=persona, rotulo=persona.title(), dispositivo=f"tab-{persona}")
            r = self.api.post(f"/api/aula/sesiones/{s['id']}/cerrar/", {}, format="json")
            self.assertEqual(r.status_code, 200, r.content)
        return s, [_publicado(llamada) for llamada in llamadas]

    def test_cada_hecho_deja_un_solo_evento_en_la_cola_unica_y_ninguno_en_la_antigua(self):
        antes = cola(MODULO).count()
        s, publicados = self.escenario("ana")
        tipos = [p["tipo"] for p in publicados]
        self.assertEqual((tipos[0], tipos[-1]), (dom.EV_SESION_INICIADA, dom.EV_SESION_FINALIZADA))
        self.assertIn(dom.EV_PRESENCIA_REGISTRADA, tipos)
        nuevos = list(cola(MODULO))[antes:]
        self.assertEqual([_en_cola(f) for f in nuevos], publicados)
        self.assertEqual({(f.modulo, f.version, f.catalogado, f.carga_omitida) for f in nuevos}, {(MODULO, 1, True, False)})
        self.assertEqual({f.agregado_id for f in nuevos}, {s["id"]})
        self.assertEqual(m.EventoSalida.objects.count(), 0)                                           # sin doble escritura
        self.assertEqual(self.eventos(s["id"]), tipos)                                                # lo que las pruebas del aula ya comprobaban, leído de la cola única
        self.assertEqual(servicios.ultima_secuencia(), nuevos[-1].id)

    def test_la_historia_se_sirve_con_lo_nuevo_y_una_marca_previa_al_corte_no_pierde_ni_repite(self):
        _, historia = self.escenario("antes")
        ids = sembrar_historia(m.EventoSalida, MODULO, historia, creado_en=1_000)
        self.assertEqual(servicios.ultima_secuencia(), ids[-1])                                       # sin nada nuevo, la última secuencia es la última de la historia
        s2, _ = self.escenario("despues")
        nuevos = [f.id for f in cola(MODULO) if f.id > ids[-1]]
        self.assertEqual(servicios.ultima_secuencia(), nuevos[-1])
        de_interes = [i for i, e in zip(ids, historia) if e["tipo"] in TIPOS]
        nuevos_de_interes = [f.id for f in cola(MODULO).filter(id__gt=ids[-1], tipo_evento__in=TIPOS)]
        leer = lambda marca, limite, tipos: servicios.eventos_desde(marca, limite, tipos)          # noqa: E731 — lo que llaman Reportes y Search
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, 0, TIPOS)], de_interes + nuevos_de_interes)                 # marca cero (BR-007)
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, de_interes[0], TIPOS)], de_interes[1:] + nuevos_de_interes)  # iba por la primera de la historia
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, ids[-1], TIPOS)], nuevos_de_interes)                         # justo en el corte
        self.assertEqual(servicios.eventos_desde(nuevos[-1], 10, TIPOS), ([], nuevos[-1]))                                           # al día
        self.assertEqual(servicios.eventos_desde(0, 10, ()), ([], 0))                                                                # sin tipos no hay nada que leer
        primero = como_consumidor(leer, 0, TIPOS)[0]
        self.assertEqual((primero["legado"], primero["tipo"], primero["carga"]), (True, historia[0]["tipo"], historia[0]["carga"]))
        self.assertNotIn("legado", como_consumidor(leer, ids[-1], TIPOS)[0])
        self.assertEqual([e["agregado_id"] for e in como_consumidor(leer, ids[-1], TIPOS)], [s2["id"]] * len(nuevos_de_interes))
        self.assertEqual(m.EventoSalida.objects.count(), len(ids))                                    # la historia sigue intacta (BR-016)
        self.assertEqual(nodo.corte_de(MODULO)["ultima_legada"], ids[-1])

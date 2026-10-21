"""
Paridad de MOD-011 con la cola única (MOD-015, Fase 3): los mismos hechos del libro producen los mismos eventos que antes del corte (tipo, versión, agregado y carga), UNA sola
vez y SÓLO en `m15_evento`; `m11_evento_salida` queda como historia, y `servicios.eventos_desde` —lo que Reportes lee por su `LibroFuente`— la sirve con lo nuevo como un flujo
continuo: una marca previa al corte no pierde ni repite, y la marca cero reproduce toda la historia (BR-007).
"""
from __future__ import annotations

from nodo.pruebas import cola, como_consumidor, espiar, sembrar_historia
from reporting.dominio import catalogos as rp
from reporting.infraestructura.fuentes import LibroFuente

from .. import models as m
from .. import servicios
from ..dominio import catalogos as cat
from ..infraestructura.repositorios import OutboxDjango
from .base import BaseGradebook

MODULO = "gradebook"
TIPOS = rp.EVENTOS_CONSUMIDOS[rp.CALIFICACION]           # lo que Reportes lee de esta fuente


def _publicado(llamada) -> dict:
    (agregado_tipo, agregado_id, tipo, carga), _ = llamada
    return {"tipo": tipo, "agregado_tipo": agregado_tipo, "agregado_id": str(agregado_id), "carga": carga}


def _en_cola(fila) -> dict:
    return {"tipo": fila.tipo_evento, "agregado_tipo": fila.agregado_tipo, "agregado_id": fila.agregado_id, "carga": fila.carga}


class ParidadLibroTests(BaseGradebook):
    def escenario(self) -> list[dict]:
        """Juan presenta y entrega un examen sin abiertas (queda calificado en MOD-010) y el libro lo registra al sincronizar: lo que publican los casos de uso."""
        with espiar(OutboxDjango) as llamadas:
            self.examen_entregado(abiertas=False)
            self.sincronizar()
        return [_publicado(llamada) for llamada in llamadas]

    def test_cada_hecho_deja_un_solo_evento_en_la_cola_unica_y_ninguno_en_la_antigua(self):
        antes = cola(MODULO).count()
        publicados = self.escenario()
        tipos = [p["tipo"] for p in publicados]
        self.assertIn(cat.EV_REGISTRADA, tipos)
        self.assertIn("calificacion.estado_simple_calculado.v1", tipos)
        nuevos = list(cola(MODULO))[antes:]
        self.assertEqual([_en_cola(f) for f in nuevos], publicados)
        self.assertEqual({(f.modulo, f.version, f.catalogado, f.carga_omitida) for f in nuevos}, {(MODULO, 1, True, False)})
        self.assertEqual(m.EventoSalida.objects.count(), 0)                                           # sin doble escritura
        self.assertEqual(self.eventos_gb(cat.EV_REGISTRADA), [cat.EV_REGISTRADA])
        self.assertEqual(servicios.ultima_secuencia(), nuevos[-1].id)

    def test_la_historia_se_sirve_con_lo_nuevo_y_una_marca_previa_al_corte_no_pierde_ni_repite(self):
        historia = self.escenario()
        ids = sembrar_historia(m.EventoSalida, MODULO, historia, creado_en=1_000)
        self.assertEqual(servicios.ultima_secuencia(), ids[-1])
        self.escenario()
        nuevos = [f.id for f in cola(MODULO) if f.id > ids[-1]]
        self.assertEqual(servicios.ultima_secuencia(), nuevos[-1])
        de_interes = [i for i, e in zip(ids, historia) if e["tipo"] in TIPOS]
        nuevos_de_interes = [f.id for f in cola(MODULO).filter(id__gt=ids[-1], tipo_evento__in=TIPOS)]
        self.assertGreaterEqual(len(de_interes), 2)
        fuente = LibroFuente()                                                                        # el adaptador con que Reportes lee el libro
        leer = lambda marca, limite, tipos: fuente.eventos_desde(marca, limite, tipos)              # noqa: E731
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, 0, TIPOS)], de_interes + nuevos_de_interes)
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, de_interes[0], TIPOS)], de_interes[1:] + nuevos_de_interes)
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, ids[-1], TIPOS)], nuevos_de_interes)
        self.assertEqual(fuente.eventos_desde(nuevos[-1], 10, TIPOS), ([], nuevos[-1]))
        self.assertEqual(fuente.ultima_secuencia(), nuevos[-1])
        primero = como_consumidor(leer, 0, TIPOS)[0]
        self.assertEqual((primero["legado"], primero["tipo"], primero["carga"]), (True, [e for e in historia if e["tipo"] in TIPOS][0]["tipo"],
                                                                                  [e for e in historia if e["tipo"] in TIPOS][0]["carga"]))
        self.assertEqual(m.EventoSalida.objects.count(), len(ids))                                    # la historia sigue intacta (BR-016)

"""
Paridad de MOD-021 con la cola única (MOD-015, Fase 3), en sus dos papeles:

  · como PRODUCTOR: las mismas sincronizaciones y reconstrucciones producen los mismos eventos que antes del corte (tipo, versión, agregado y carga), UNA sola vez y SÓLO en
    `m15_evento`; `m21_evento_salida` queda como historia y la fachada la sirve con lo nuevo (nadie lee hoy la cola de la búsqueda: se demuestra por la fachada);
  · como CONSUMIDOR de `aula` y `estudio` (ya cortados): su sincronización real, con una marca tomada ANTES del corte (un id de la cola antigua), indexa lo de la historia que le
    faltaba y lo nuevo, sin perder ni repetir, y deja las marcas al día.
"""
from __future__ import annotations

from classroom_engine import models as m7
from classroom_engine import servicios as aula
from classroom_engine.infraestructura.repositorios import OutboxDjango as OutboxAula
from modo_estudio import models as m8
from modo_estudio import servicios as estudio
from modo_estudio.infraestructura.repositorios import OutboxDjango as OutboxEstudio
from nodo import servicios as nodo
from nodo.pruebas import cola, como_consumidor, espiar, sembrar_historia

from .. import models as m
from ..aplicacion.indexar import Sincronizar
from ..dominio import catalogos as cat
from ..infraestructura.repositorios import OutboxDjango
from .base import BaseSearch

MODULO = "search"


def _publicado(llamada) -> dict:
    (tipo, agregado_id, carga), _ = llamada
    return {"tipo": tipo, "agregado_tipo": OutboxDjango._AGREGADO[tipo], "agregado_id": str(agregado_id)[:80], "carga": carga}


def _ajeno(llamada) -> dict:
    (agregado_tipo, agregado_id, tipo, carga), _ = llamada
    return {"tipo": tipo, "agregado_tipo": agregado_tipo, "agregado_id": str(agregado_id)[:64], "carga": carga}


def _en_cola(fila) -> dict:
    return {"tipo": fila.tipo_evento, "agregado_tipo": fila.agregado_tipo, "agregado_id": fila.agregado_id, "carga": fila.carga}


class ParidadBusquedaComoProductorTests(BaseSearch):
    sincronizar_al_consultar = False

    def setUp(self):
        super().setUp()
        self.sincronizar()                                      # la primera sincronización construye el índice entero: lo que sigue ya es incremental

    def escenario(self, titulo: str) -> list[dict]:
        """Una evaluación nueva indexada de forma incremental y una reconstrucción: lo que publica la búsqueda."""
        with espiar(OutboxDjango) as llamadas:
            self.evaluacion(titulo)
            self.sincronizar()
            self.reconstruir()
        return [_publicado(llamada) for llamada in llamadas]

    def test_cada_hecho_deja_un_solo_evento_en_la_cola_unica_y_ninguno_en_la_antigua(self):
        antes = cola(MODULO).count()
        publicados = self.escenario("Fracciones")
        tipos = [p["tipo"] for p in publicados]
        for esperado in (cat.EV_ENTIDAD_INDEXADA, cat.EV_REINDEXACION_INCREMENTAL, cat.EV_INDICE_RECONSTRUIDO):
            self.assertIn(esperado, tipos)
        nuevos = list(cola(MODULO))[antes:]
        self.assertEqual([_en_cola(f) for f in nuevos], publicados)
        self.assertEqual({(f.modulo, f.version, f.catalogado, f.carga_omitida) for f in nuevos}, {(MODULO, 1, True, False)})
        self.assertEqual(m.EventoSalida.objects.count(), 0)                                           # sin doble escritura
        self.assertEqual(self.eventos_search(cat.EV_INDICE_RECONSTRUIDO), [cat.EV_INDICE_RECONSTRUIDO] * 2)      # la construcción inicial del setUp y la del escenario

    def test_la_historia_se_sirve_con_lo_nuevo_y_una_marca_previa_al_corte_no_pierde_ni_repite(self):
        historia = self.escenario("Fracciones")
        ids = sembrar_historia(m.EventoSalida, MODULO, historia, creado_en=1_000)
        self.escenario("Decimales")
        nuevos = [f.id for f in cola(MODULO) if f.id > ids[-1]]
        self.assertGreaterEqual(len(nuevos), 2)
        leer = lambda marca, limite, tipos: nodo.leer(MODULO, marca, limite, tipos)                  # noqa: E731
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, 0)], ids + nuevos)
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, ids[0])], ids[1:] + nuevos)
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, ids[-1])], nuevos)
        self.assertEqual(nodo.leer(MODULO, nuevos[-1], 10), ([], nuevos[-1]))
        self.assertEqual(m.EventoSalida.objects.count(), len(ids))


class ParidadBusquedaComoConsumidorTests(BaseSearch):
    sincronizar_al_consultar = False

    def marca(self, fuente: str) -> int:
        fila = m.MarcaDeLectura.objects.filter(pk=fuente).first()
        return fila.secuencia if fila else 0

    def poner_marca(self, fuente: str, secuencia: int) -> None:
        m.MarcaDeLectura.objects.update_or_create(fuente=fuente, defaults={"secuencia": secuencia, "fallo_secuencia": 0, "fallos": 0})

    def test_clases_y_estudios_con_una_marca_previa_al_corte_se_indexan_sin_perder_ni_repetir(self):
        # ANTES del corte: una clase cerrada y un estudio, copiados a las colas antiguas como la historia que había al migrar.
        with espiar(OutboxAula) as de_aula, espiar(OutboxEstudio) as de_estudio:
            c1 = self.clase()
            self.cerrar_clase(c1["id"])
            e1 = self.estudio(titulo="Estudio de antes")
        ids_aula = sembrar_historia(m7.EventoSalida, "classroom_engine", [_ajeno(ll) for ll in de_aula], creado_en=self.t)
        ids_estudio = sembrar_historia(m8.EventoSalida, "modo_estudio", [_ajeno(ll) for ll in de_estudio], creado_en=self.t)
        iniciada = [i for i, (args, _) in zip(ids_aula, de_aula) if args[2] == "aula.sesion.iniciada.v1"][0]
        # DESPUÉS del corte: otra clase y otro estudio, sólo en la cola única.
        c2 = self.clase()
        self.cerrar_clase(c2["id"])
        e2 = self.estudio(titulo="Estudio de después")
        # El índice iba por la apertura de la primera clase (un id de la historia) y no había leído ningún estudio.
        self.poner_marca(cat.FUENTE_AULA, iniciada)
        r = Sincronizar(self.servicios()).ejecutar()
        self.assertEqual(r["fallidos"], [])
        self.assertEqual(sorted(d.entidad_id for d in self.documentos("class")), sorted([c1["id"], c2["id"]]))
        self.assertEqual(sorted(d.entidad_id for d in self.documentos("study")), sorted([e1["id"], e2["id"]]))
        self.assertEqual((self.marca(cat.FUENTE_AULA), self.marca(cat.FUENTE_ESTUDIO)), (aula.ultima_secuencia(), estudio.ultima_secuencia()))
        self.assertGreater(self.marca(cat.FUENTE_AULA), ids_aula[-1])
        # Al día: otra pasada no lee nada.
        r = Sincronizar(self.servicios()).ejecutar()
        self.assertEqual((r["leidos"], r["indexados"]), (0, 0))
        # Con la marca justo en el corte sólo se relee lo nuevo, y reindexar lo mismo no duplica nada.
        self.poner_marca(cat.FUENTE_AULA, ids_aula[-1])
        r = Sincronizar(self.servicios()).ejecutar()
        self.assertEqual([d.entidad_id for d in self.documentos("class")].count(c2["id"]), 1)
        self.assertEqual(len(self.documentos("class")), 2)
        self.assertEqual((m7.EventoSalida.objects.count(), m8.EventoSalida.objects.count()), (len(ids_aula), len(ids_estudio)))     # la historia sigue intacta (BR-016)
        self.assertEqual(self.buscar("estudio")["total"], 2)

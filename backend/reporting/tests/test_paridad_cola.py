"""
Paridad de MOD-013 con la cola única (MOD-015, Fase 3), en sus dos papeles:

  · como PRODUCTOR: los mismos reportes producen los mismos eventos que antes del corte (tipo, versión, agregado y carga), UNA sola vez y SÓLO en `m15_evento`; `m13_evento_salida`
    queda como historia y la fachada la sirve con lo nuevo (nadie lee hoy la cola de los reportes: se demuestra por la fachada);
  · como CONSUMIDOR de `aula` y `estudio` (ya cortados): su consumidor real, con una marca tomada ANTES del corte (un id de la cola antigua), sigue sin perder ni repetir un
    evento, y con la marca en cero reproduce toda la historia y deja las mismas proyecciones (BR-007).
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
from ..aplicacion.consumidor import ConsumirEventos, _Aplicador
from ..dominio import catalogos as cat
from ..infraestructura.contenedor import servicios
from ..infraestructura.repositorios import MarcasDjango, OutboxDjango
from .base import BaseReporting

MODULO = "reporting"


def _publicado(llamada, recorte: int = 64) -> dict:
    (agregado_tipo, agregado_id, tipo, carga), _ = llamada
    return {"tipo": tipo, "agregado_tipo": agregado_tipo, "agregado_id": str(agregado_id)[:recorte], "carga": carga}


def _en_cola(fila) -> dict:
    return {"tipo": fila.tipo_evento, "agregado_tipo": fila.agregado_tipo, "agregado_id": fila.agregado_id, "carga": fila.carga}


class ParidadReportesComoProductorTests(BaseReporting):
    sincronizar_al_consultar = False

    def escenario(self) -> list[dict]:
        """Una clase completa, el consumidor al día, el reporte del grupo y una reconstrucción: lo que Reportes publica."""
        with espiar(OutboxDjango) as llamadas:
            self.clase_cerrada([(5, 5)])
            ConsumirEventos(servicios()).hasta_vaciar()
            self.rp(f"/grupos/{self.grupo['id']}/")
            self.reconstruir()
        return [_publicado(llamada) for llamada in llamadas]

    def test_cada_hecho_deja_un_solo_evento_en_la_cola_unica_y_ninguno_en_la_antigua(self):
        antes = cola(MODULO).count()
        publicados = self.escenario()
        tipos = [p["tipo"] for p in publicados]
        self.assertIn(cat.EV_GRUPO_GENERADO, tipos)
        self.assertIn(cat.EV_AGREGADOS_RECONSTRUIDOS, tipos)
        nuevos = list(cola(MODULO))[antes:]
        self.assertEqual([_en_cola(f) for f in nuevos], publicados)
        self.assertEqual({(f.modulo, f.version, f.catalogado, f.carga_omitida) for f in nuevos}, {(MODULO, 1, True, False)})
        self.assertEqual(m.EventoSalida.objects.count(), 0)                                           # sin doble escritura
        self.assertEqual(self.eventos_rp(cat.EV_GRUPO_GENERADO), [cat.EV_GRUPO_GENERADO])

    def test_la_historia_se_sirve_con_lo_nuevo_y_una_marca_previa_al_corte_no_pierde_ni_repite(self):
        historia = self.escenario()
        ids = sembrar_historia(m.EventoSalida, MODULO, historia, creado_en=1_000)
        self.escenario()
        nuevos = [f.id for f in cola(MODULO) if f.id > ids[-1]]
        leer = lambda marca, limite, tipos: nodo.leer(MODULO, marca, limite, tipos)                  # noqa: E731
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, 0)], ids + nuevos)
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, ids[0])], ids[1:] + nuevos)
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, ids[-1])], nuevos)
        self.assertEqual(nodo.leer(MODULO, nuevos[-1], 10), ([], nuevos[-1]))
        self.assertEqual(m.EventoSalida.objects.count(), len(ids))


class ParidadReportesComoConsumidorTests(BaseReporting):
    """El consumidor de Reportes sobre las fuentes ya cortadas: con historia en la cola antigua (sembrada como estaba al migrar) y lo nuevo en la cola única."""

    sincronizar_al_consultar = False

    def aplicados(self, fuente: str) -> list[int]:
        """Corre el consumidor hasta vaciar y devuelve las secuencias que aplicó de esa fuente, en orden."""
        with espiar(_Aplicador, "aplicar") as llamadas:
            ConsumirEventos(servicios()).hasta_vaciar()
        return [args[2]["secuencia"] for args, _ in llamadas if args[1] == fuente]

    def test_aula_una_marca_previa_al_corte_no_pierde_ni_repite_y_marca_cero_reproduce_todo(self):
        # Una clase completa ANTES del corte: sus eventos se copian a `m07_evento_salida` como la historia que la instalación tenía al migrar.
        with espiar(OutboxAula) as llamadas:
            s1 = self.clase_cerrada([(5, 5)])["sesion"]
        ids = sembrar_historia(m7.EventoSalida, "classroom_engine", [_publicado(ll, 10 ** 6) for ll in llamadas], creado_en=self.t)
        de_interes = [i for i, (args, _) in zip(ids, llamadas) if args[2] in cat.EVENTOS_CONSUMIDOS[cat.AULA]]
        self.assertGreaterEqual(len(de_interes), 3)
        # Y una clase DESPUÉS del corte: sus eventos sólo están en la cola única.
        s2 = self.clase_cerrada([(3, 5)])["sesion"]
        nuevos_de_interes = [f.id for f in cola("classroom_engine").filter(id__gt=ids[-1], tipo_evento__in=cat.EVENTOS_CONSUMIDOS[cat.AULA])]
        self.assertGreaterEqual(len(nuevos_de_interes), 3)
        # El consumidor iba por el segundo evento de la historia cuando se cortó: sigue desde ahí, cruza el corte y llega al día sin perder ni repetir.
        MarcasDjango().guardar(cat.AULA, de_interes[1], self.t)
        self.assertEqual(self.aplicados(cat.AULA), de_interes[2:] + nuevos_de_interes)
        self.assertEqual(MarcasDjango().get(cat.AULA), aula.ultima_secuencia())
        self.assertEqual(self.aplicados(cat.AULA), [])                                                # al día: nada más que aplicar
        self.assertEqual(set(m.Clase.objects.filter(sesion_id__in=[s1["id"], s2["id"]]).values_list("sesion_id", flat=True)), {s1["id"], s2["id"]})
        # Marca cero: toda la historia y después lo nuevo (BR-007), y las proyecciones quedan iguales.
        antes = list(m.ClaseAlumno.objects.order_by("id").values_list("alumno_id", "porcentaje_aciertos"))
        MarcasDjango().guardar(cat.AULA, 0, self.t)
        self.assertEqual(self.aplicados(cat.AULA), de_interes + nuevos_de_interes)
        self.assertEqual(list(m.ClaseAlumno.objects.order_by("id").values_list("alumno_id", "porcentaje_aciertos")), antes)
        self.assertEqual(m7.EventoSalida.objects.count(), len(ids))                                   # la historia sigue intacta (BR-016)

    def test_estudio_una_marca_previa_al_corte_no_pierde_ni_repite(self):
        with espiar(OutboxEstudio) as llamadas:
            e1 = self.estudio(titulo="Estudio de antes")
        ids = sembrar_historia(m8.EventoSalida, "modo_estudio", [_publicado(ll) for ll in llamadas], creado_en=self.t)
        de_interes = [i for i, (args, _) in zip(ids, llamadas) if args[2] in cat.EVENTOS_CONSUMIDOS[cat.ESTUDIO]]
        self.assertEqual(len(de_interes), 1)
        e2 = self.estudio(titulo="Estudio de después")
        nuevos_de_interes = [f.id for f in cola("modo_estudio").filter(id__gt=ids[-1], tipo_evento__in=cat.EVENTOS_CONSUMIDOS[cat.ESTUDIO])]
        self.assertEqual(len(nuevos_de_interes), 1)
        # la marca estaba en cero (aún no había leído la historia)
        self.assertEqual(self.aplicados(cat.ESTUDIO), de_interes + nuevos_de_interes)
        self.assertEqual(MarcasDjango().get(cat.ESTUDIO), estudio.ultima_secuencia())
        # y con la marca justo en el corte sólo llega lo nuevo
        MarcasDjango().guardar(cat.ESTUDIO, ids[-1], self.t)
        self.assertEqual(self.aplicados(cat.ESTUDIO), nuevos_de_interes)
        self.assertEqual({e1["grupo_id"], e2["grupo_id"]}, {self.grupo["id"]})                       # las dos asignaciones son del grupo cuyo avance se proyecta
        self.assertEqual(m8.EventoSalida.objects.count(), len(ids))

    def test_el_estado_del_consumidor_ve_la_historia_y_lo_nuevo_como_una_sola_cola(self):
        """`/estado/`: con una marca anterior al corte y eventos sin aplicar en los dos lados, el corte es el instante anterior al evento más viejo de la HISTORIA."""
        with espiar(OutboxAula) as llamadas:
            self.clase_cerrada([(5, 5)])
        hace_diez_minutos = self.t - 600_000
        ids = sembrar_historia(m7.EventoSalida, "classroom_engine", [_publicado(ll, 10 ** 6) for ll in llamadas], creado_en=hace_diez_minutos)
        self.avanzar(seg=1)
        self.clase_cerrada([(4, 5)])
        e = self.rp("/estado/", cliente=self.admin)
        self.assertEqual((e["estado"], e["corte_en"]), ("rezagada", hace_diez_minutos - 1))
        self.assertEqual([x["fuente"] for x in e["fuentes"] if x["pendientes"]], [cat.AULA])
        self.assertEqual([x["ultima"] for x in e["fuentes"] if x["fuente"] == cat.AULA], [aula.ultima_secuencia()])
        self.assertGreater(aula.ultima_secuencia(), ids[-1])
        ConsumirEventos(servicios()).hasta_vaciar()
        self.assertEqual(self.rp("/estado/", cliente=self.admin)["estado"], "al_dia")

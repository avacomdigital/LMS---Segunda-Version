"""
019-08 · cobertura de Classroom Engine: avisos, transiciones de presencia (sólo la transición, nunca el latido),
duración de la proyección (DEC-034) y denegaciones del aula con los roles activos.
"""
from __future__ import annotations

import time

from classroom_engine import models as m
from classroom_engine.aplicacion import casos_uso_tiempo_real as tr
from classroom_engine.infraestructura.contenedor import servicios as servicios_aula
from classroom_engine.tests.test_sesiones import ConSesionDeClase

from ..models import Bitacora


class CoberturaAulaTests(ConSesionDeClase):
    def _asientos(self, accion: str) -> list[Bitacora]:
        return list(Bitacora.objects.filter(accion=accion).order_by("secuencia"))

    def test_un_aviso_deja_asiento_con_alcance_y_sin_texto(self):
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/avisos/", {"texto": "Guarden silencio, Juan Pérez", "profesor_id": "prof-1"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        r = self.api.post(f"/api/aula/sesiones/{s['id']}/avisos/", {"texto": "Ana, ven", "participante_id": pid, "profesor_id": "prof-1"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        asientos = self._asientos("aula.aviso.enviado")
        self.assertEqual([a.valor_nuevo["alcance"] for a in asientos], ["grupo", "participante"])
        self.assertEqual((asientos[1].valor_nuevo["participante_id"], asientos[1].objeto_tabla, asientos[1].usuario_id), (pid, "m07_aviso", "prof-1"))
        self.assertNotIn("Juan", str(asientos[0].valor_nuevo))
        self.assertEqual(asientos[0].valor_nuevo["largo"], len("Guarden silencio, Juan Pérez"))

    def test_solo_las_transiciones_de_presencia_se_auditan_nunca_el_latido(self):
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        ruta = f"/api/aula/sesiones/{s['id']}/participantes/{pid}/presencia/"
        for _ in range(3):
            self.assertEqual(self.api.post(ruta, {"estado": "conectado"}, format="json").status_code, 200)   # latidos: sin asiento
        self.assertEqual(self._asientos("aula.presencia.perdida") + self._asientos("aula.presencia.recuperada"), [])
        self.assertEqual(self.api.post(ruta, {"estado": "reconectando"}, format="json").status_code, 200)
        perdida = self._asientos("aula.presencia.perdida")
        self.assertEqual(len(perdida), 1)
        self.assertEqual((perdida[0].valor_anterior, perdida[0].valor_nuevo["estado"], perdida[0].valor_nuevo["causa"], perdida[0].usuario_id),
                         ({"estado": "conectado"}, "reconectando", "declarada por la tableta", "ana"))
        self.assertEqual(self.api.post(ruta, {"estado": "conectado"}, format="json").status_code, 200)
        recuperada = self._asientos("aula.presencia.recuperada")
        self.assertEqual((len(recuperada), recuperada[0].valor_anterior), (1, {"estado": "reconectando"}))
        # El barrido del nodo también deja sólo la transición: latido vencido → reconectando, ausencia → salió.
        m.Participante.objects.filter(pk=pid).update(ultimo_latido_en=int(time.time() * 1000) - 10 * 60 * 1000)
        tr.BarrerPresencia(servicios_aula()).ejecutar()
        self.assertEqual(m.Participante.objects.get(pk=pid).estado, "reconectando")
        tr.BarrerPresencia(servicios_aula()).ejecutar()
        self.assertEqual(m.Participante.objects.get(pk=pid).estado, "salio")
        causas = [a.valor_nuevo["causa"] for a in self._asientos("aula.presencia.perdida")]
        self.assertEqual(causas, ["declarada por la tableta", "latido vencido", "ausencia prolongada"])
        self.assertTrue(all(a.actor_tipo == "sistema" for a in self._asientos("aula.presencia.perdida")[1:]))

    def test_la_proyeccion_terminada_lleva_autor_y_duracion_en_segundos(self):
        s = self.iniciar()
        pid = self.unirse(s)["participante"]["id"]
        ruta = f"/api/aula/sesiones/{s['id']}/participantes/{pid}/proyeccion/"
        self.assertEqual(self.api.post(ruta, {"activa": True, "profesor_id": "prof-1"}, format="json").status_code, 200)
        m.Participante.objects.filter(pk=pid).update(proyectado_desde=int(time.time() * 1000) - 65_000)
        self.assertEqual(self.api.post(ruta, {"activa": False, "profesor_id": "prof-1"}, format="json").status_code, 200)
        terminada = self._asientos("aula.proyeccion.terminada")[0]
        self.assertEqual((terminada.usuario_id, terminada.valor_anterior["autor"]), ("prof-1", "prof-1"))
        self.assertGreaterEqual(terminada.valor_nuevo["duracion_seg"], 65)
        self.assertEqual(terminada.valor_nuevo["duracion_seg"], terminada.valor_nuevo["duracion_ms"] // 1000)
        self.assertEqual(self._asientos("aula.proyeccion.iniciada")[0].valor_nuevo["persona_id"], "ana")

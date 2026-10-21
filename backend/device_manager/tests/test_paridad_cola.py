"""
Paridad de MOD-009 con la cola única (MOD-015, Fase 3): los mismos hechos producen los mismos eventos que antes del corte (tipo, versión, agregado y carga), UNA sola vez y SÓLO en
`m15_evento`; la cola antigua `m09_evento_salida` queda como historia y la fachada la sirve con lo nuevo como un flujo continuo; una marca previa al corte no pierde ni repite, y la
marca cero reproduce toda la historia (BR-007). Nadie lee hoy la cola de los dispositivos: se demuestra por la fachada, que es lo que leería un consumidor.
"""
from __future__ import annotations

from acceso.tests.base import BaseAcceso
from nodo import servicios as nodo
from nodo.pruebas import cola, como_consumidor, espiar, sembrar_historia

from .. import models as m
from .. import servicios
from ..dominio import dispositivo as dom
from ..infraestructura.repositorios import OutboxDjango

MODULO = "device_manager"


def _publicado(llamada) -> dict:
    (agregado_tipo, agregado_id, tipo, carga), _ = llamada
    return {"tipo": tipo, "agregado_tipo": agregado_tipo, "agregado_id": agregado_id, "carga": carga}


def _en_cola(fila) -> dict:
    return {"tipo": fila.tipo_evento, "agregado_tipo": fila.agregado_tipo, "agregado_id": fila.agregado_id, "carga": fila.carga}


class ParidadDispositivosTests(BaseAcceso):
    def escenario(self, hw: str) -> list[dict]:
        """Registrar una tableta nueva, bloquearla y desbloquearla, asignarla a Juan y liberarla: cinco hechos, cinco eventos. Devuelve lo que los casos de uso publicaron."""
        with espiar(OutboxDjango) as llamadas:
            r = self.api.post("/api/dispositivos/", {"identificador_hw": hw, "nombre": f"Tableta {hw}"}, format="json")
            self.assertEqual(r.status_code, 201, r.content)
            did = r.json()["id"]
            for accion, cuerpo in (("bloquear", {"motivo": "paridad"}), ("desbloquear", {}), ("asignar", {"alumno_id": self.estudiante_id}), ("liberar", {})):
                r = self.admin.post(f"/api/dispositivos/{did}/{accion}/", cuerpo, format="json")
                self.assertEqual(r.status_code, 200, (accion, r.content))
        return [_publicado(llamada) for llamada in llamadas]

    def test_cada_hecho_deja_un_solo_evento_en_la_cola_unica_y_ninguno_en_la_antigua(self):
        antes = cola(MODULO).count()
        publicados = self.escenario("hw-paridad")
        self.assertEqual([p["tipo"] for p in publicados], [dom.EV_REGISTRADO, dom.EV_BLOQUEADO, dom.EV_DESBLOQUEADO, dom.EV_ASIGNADO, dom.EV_LIBERADO])
        nuevos = list(cola(MODULO))[antes:]
        self.assertEqual([_en_cola(f) for f in nuevos], publicados)                                  # tipo, agregado y carga: exactamente lo que cada caso de uso publicó
        self.assertEqual({(f.modulo, f.version, f.catalogado, f.carga_omitida) for f in nuevos}, {(MODULO, 1, True, False)})
        self.assertEqual(len({f.evento_id for f in nuevos}), len(nuevos))
        self.assertEqual(m.EventoSalida.objects.count(), 0)                                           # la cola antigua no recibe nada: sin doble escritura
        self.assertEqual([f.actor for f in nuevos][1:], [self.admin_id] * 4)                          # el actor sale del contexto de la petición (MOD-019)
        self.assertEqual(servicios.eventos_legados(0, 100, None, 10 ** 9), ([], 10 ** 9))             # y la historia de este módulo, en una instalación nueva, está vacía

    def test_la_historia_se_sirve_con_lo_nuevo_y_una_marca_previa_al_corte_no_pierde_ni_repite(self):
        historia = self.escenario("hw-antes")
        ids = sembrar_historia(m.EventoSalida, MODULO, historia, creado_en=1_000)                   # la instalación tenía estos cinco en m09 al migrar
        self.assertEqual((cola(MODULO).count() and nodo.corte_de(MODULO)["ultima_legada"]), ids[-1])
        nuevos_publicados = self.escenario("hw-despues")
        nuevos = [f.id for f in cola(MODULO) if f.id > ids[-1]]
        self.assertEqual(len(nuevos), 5)
        self.assertEqual([_en_cola(f) for f in cola(MODULO).filter(id__gt=ids[-1])], nuevos_publicados)
        leer = lambda marca, limite, tipos: nodo.leer(MODULO, marca, limite, tipos)                  # noqa: E731 — lo que leería un consumidor de esta fuente
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, 0)], ids + nuevos)           # marca cero: toda la historia y después lo nuevo (BR-007)
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, ids[1])], ids[2:] + nuevos)  # iba por la mitad de la historia cuando se cortó: ni pierde ni repite
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, nuevos[1])], nuevos[2:])     # ya en la zona nueva
        self.assertEqual(nodo.leer(MODULO, nuevos[-1], 10), ([], nuevos[-1]))                         # al día: nada, y `hasta` no retrocede
        legado = como_consumidor(leer, 0)[0]
        self.assertEqual((legado["legado"], legado["modulo"], legado["evento_id"], legado["tipo"], legado["carga"]),
                         (True, MODULO, f"{MODULO}:{ids[0]}", historia[0]["tipo"], historia[0]["carga"]))
        self.assertEqual([e["secuencia"] for e in como_consumidor(leer, 0, (dom.EV_BLOQUEADO,))], [ids[1], nuevos[1]])   # los tipos filtran en los dos lados
        # el lector legado, tal cual lo llama la fachada: `desde < id ≤ hasta`, y `hasta` es la última leída si el lote se llenó o el tope si no
        lote, hasta = servicios.eventos_legados(ids[0], 2, None, ids[-1])
        self.assertEqual(([e["secuencia"] for e in lote], hasta), (ids[1:3], ids[2]))
        self.assertEqual(set(lote[0]), {"secuencia", "tipo", "agregado_tipo", "agregado_id", "carga", "creado_en"})                    # la forma de la cola antigua
        self.assertEqual(([e["secuencia"] for e in servicios.eventos_legados(ids[3], 10, None, ids[-1])[0]], servicios.eventos_legados(ids[3], 10, None, ids[-1])[1]),
                         (ids[4:], ids[-1]))
        self.assertEqual(servicios.eventos_legados(ids[-1], 10, None, ids[-1]), ([], ids[-1]))
        self.assertEqual(m.EventoSalida.objects.count(), len(ids))                                    # la historia sigue intacta (BR-016)

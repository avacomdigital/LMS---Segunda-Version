"""
Dónde queda constancia de lo que pasa con el agente de IA: la BITÁCORA (m19_bitacora, encadenada, «quién hizo qué y con qué resultado») y el LOG de diagnóstico (`backend-app.log`,
y `backend-errores.log` desde WARNING; el técnico lo lee en texto plano).

Privacidad: ni la pregunta ni la respuesta se guardan en ninguno de los dos (el servicio local tampoco las registra por omisión). Sólo cifras (longitudes, milisegundos, trozos), el código
del fallo y una huella corta de la conversación. Las claves de `detalle` se eligen para que el saneamiento de logs (§2.6: «token», «respuesta», «pin»…) no las confunda con un secreto.

Nada de aquí rompe a quien llama: un fallo al asentar la bitácora o al escribir el log se traga y se intenta decir por el log de Python, y nada más.
"""
from __future__ import annotations

import logging

from audit import servicios as auditoria
from audit.dominio import asiento

from ..aplicacion.agente import Actor
from ..dominio.conversacion import huella_de
from ..dominio.errores import ErrorDeIa

log = logging.getLogger("avacom.agente_ia")

MODULO = "agente_ia"
TABLA = "agente_ia"


class RegistroDeAuditoriaYLog:
    # -------------------------------------------------------------------------------- éxito

    def consulta_ok(self, actor: Actor, conversacion: str | None, cifras: dict) -> None:
        self._escribir(logging.INFO, "agente_ia.consulta", "El agente de IA respondió una pregunta.", cifras, ruta="happy")
        self._asentar("agente_ia.consulta_realizada", actor, conversacion, asiento.RESULTADO_OK, cifras)

    def voz_ok(self, actor: Actor, cifras: dict) -> None:
        self._escribir(logging.INFO, "agente_ia.voz", "El agente de IA generó la voz de una respuesta.", cifras, ruta="happy")

    # -------------------------------------------------------------------------------- fallo

    def fallo(self, accion: str, actor: Actor, conversacion: str | None, error: ErrorDeIa, cifras: dict) -> None:
        detalle = {**cifras, "codigo": error.codigo, "estado_http": error.http, "estado_servicio": error.origen_http, "reintentable": error.reintentable,
                   "detalle_tecnico": error.detalle[:500]}
        # Un defecto (respuesta inválida, error interno, voz sin instalar) es un ERROR con `ruta: bad`; un estado normal del aula (servicio apagado, ocupado, tiempo agotado), una ADVERTENCIA.
        if error.es_defecto:
            self._escribir(logging.ERROR, accion, f"El agente de IA falló: {error.codigo}. {error.detalle}"[:500], detalle, ruta="bad", canal="aplicacion")
        else:
            self._escribir(logging.WARNING, accion, f"El agente de IA no está disponible: {error.codigo}. {error.detalle}"[:500], detalle, ruta="sad", canal="comunicacion")
        self._asentar(accion, actor, conversacion, asiento.RESULTADO_FALLIDO, detalle)

    def validacion(self, operacion: str, actor: Actor, error: ErrorDeIa) -> None:
        """La petición no salió hacia el servicio: la pregunta venía vacía o demasiado larga. Sólo al log (nivel INFO): no es un fallo de la IA ni un hecho que auditar."""
        self._escribir(logging.INFO, "agente_ia.peticion_rechazada", f"{operacion}: {error.codigo}", {"codigo": error.codigo, "operacion": operacion}, ruta="sad")

    def estado(self, actor: Actor, cifras: dict, disponible: bool) -> None:
        nivel = logging.INFO if disponible else logging.WARNING
        self._escribir(nivel, cifras.get("evento", "agente_ia.estado"), "Estado del agente de IA: " + ("disponible." if disponible else "no disponible."),
                       {k: v for k, v in cifras.items() if k != "evento"}, ruta="happy" if disponible else "sad", canal="comunicacion")

    # -------------------------------------------------------------------------------- apoyo

    @staticmethod
    def _escribir(nivel: int, evento: str, mensaje: str, detalle: dict, *, ruta: str, canal: str | None = None) -> None:
        try:
            extra = {"evento": evento, "ruta": ruta, "detalle": detalle, "modulo": MODULO}
            if canal:
                extra["canal"] = canal
            log.log(nivel, mensaje, extra=extra)
        except Exception:   # noqa: BLE001 — escribir el log nunca rompe la respuesta
            pass

    def _asentar(self, accion: str, actor: Actor, conversacion: str | None, resultado: str, detalle: dict) -> None:
        try:
            auditoria.anexar(actor.id or "cliente", accion, TABLA, huella_de(conversacion) if conversacion else "", nuevo=detalle, resultado=resultado)
        except Exception as error:   # noqa: BLE001 — si la bitácora no puede asentar, el aula sigue; se avisa por el log para que el técnico lo vea
            self._escribir(logging.ERROR, "agente_ia.bitacora_no_disponible", f"No se pudo asentar «{accion}» en la bitácora: {error.__class__.__name__}: {error}"[:500],
                           {"accion": accion}, ruta="bad", canal="escritura")

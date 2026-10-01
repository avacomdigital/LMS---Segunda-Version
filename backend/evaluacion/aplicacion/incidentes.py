"""
Los incidentes que informa la tableta y el informe del bloqueo (FUN-117, CAP-066, BR-077, D-12, D-13):

  RegistrarIncidentes  la tableta informa lo que vio: salió de la app, intentó cerrar, hay otra pantalla, consultó un recurso. Idempotente por
                       `ref_cliente`: reenviar su cola no duplica nada (INV-005). Una tableta sólo puede informar los tipos de origen `tableta`: no
                       puede fabricar `reactivado`, `degradacion` ni `desconexion`.
  InformarBloqueo      lo que la tableta LOGRÓ aplicar del plan de bloqueo. El nodo no presume que se aplicó: la tableta lo dice.

Un incidente se registra, alimenta el expediente de integridad y NUNCA modifica el estado del intento ni lo invalida.
"""
from __future__ import annotations

import hashlib
import json

from ..dominio import bloqueo
from ..dominio import catalogos as cat
from ..dominio.errores import DatosInvalidos, TransicionInvalida
from .alumno import _Alumno
from .puertos import Actor

MAX_INCIDENTES_POR_ENVIO = 100


class RegistrarIncidentes(_Alumno):
    """`datos`: `{dispositivo, alumno_id, incidentes: [{tipo, detalle?, ocurrido_en?, ocurrido_en_tableta?, ref_cliente?}]}`."""

    def ejecutar(self, actor: Actor, intento_id: str, datos: dict) -> dict:
        entrada = datos.get("incidentes")
        if not isinstance(entrada, list) or not entrada:
            raise DatosInvalidos("`incidentes` debe ser una lista con al menos un incidente.")
        if len(entrada) > MAX_INCIDENTES_POR_ENVIO:
            raise DatosInvalidos(f"Un envío admite hasta {MAX_INCIDENTES_POR_ENVIO} incidentes.", incidentes=len(entrada))
        for i in entrada:
            tipo = str(i.get("tipo") or "") if isinstance(i, dict) else ""
            if tipo not in cat.INCIDENTES_DE_LA_TABLETA:
                raise DatosInvalidos(f"La tableta sólo informa incidentes de estos tipos: {', '.join(cat.INCIDENTES_DE_LA_TABLETA)}.", tipo=tipo)
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self.contexto(uow, actor, datos, ahora)
            intento, asignacion = self.cargar(uow, ctx, intento_id, ahora)
            self.sesion_de(ctx, intento)
            if intento["estado"] == cat.NO_INICIADO:
                raise TransicionInvalida("El intento todavía no empieza.", estado=intento["estado"])
            registrados = duplicados = 0
            for i in entrada:
                detalle = i.get("detalle") if isinstance(i.get("detalle"), dict) else {}
                ocurrido = self._instante(i.get("ocurrido_en"), ahora)
                _, creada = self.motor.incidente(
                    uow, intento, i["tipo"], ahora, detalle=detalle, dispositivo_id=ctx.dispositivo_id or None, ref_cliente=str(i.get("ref_cliente") or ""),
                    reportado_en_tableta=self._entero(i.get("ocurrido_en_tableta")), ocurrido_en=ocurrido, actor=ctx.alumno_id, asignacion=asignacion)
                registrados += 1 if creada else 0
                duplicados += 0 if creada else 1
            return {"registrados": registrados, "duplicados": duplicados, "estado": intento["estado"], "servidor_en": ahora}

    @staticmethod
    def _entero(valor) -> int | None:
        if valor is None or isinstance(valor, bool) or valor == "":
            return None
        try:
            return int(valor)
        except (TypeError, ValueError):
            return None

    def _instante(self, valor, ahora: int) -> int:
        """La hora la normaliza la tableta con el desfase que aprendió del nodo; el nodo sólo la acepta si es plausible (ni del futuro ni de antes
        de ayer): si no, vale la de recepción. Nunca decide nada: es un dato adicional (BR-062)."""
        entero = self._entero(valor)
        if entero is None or entero > ahora + self.s.config.desfase_reloj_ms or entero < ahora - 48 * 3_600_000:
            return ahora
        return entero


class InformarBloqueo(_Alumno):
    """`datos`: `{dispositivo, alumno_id, resultado: aplicado | parcial | fallido | liberado, capas: {sistema, app, capturas, pantallas}, motivo?}`.
    Si el plan pedía la capa del sistema y la tableta no la logró, se registra `bloqueo_parcial` o `bloqueo_fallido`; si soltó el bloqueo con el
    examen en marcha, `bloqueo_liberado`. El intento sigue: el nodo no invalida por esto (BR-077)."""

    def ejecutar(self, actor: Actor, intento_id: str, datos: dict) -> dict:
        resultado, capas = bloqueo.valida_informe_de_bloqueo(datos.get("resultado"), datos.get("capas"))
        motivo = str(datos.get("motivo") or "")[:200]
        ahora = self.s.reloj.ahora_ms()
        with self.s.uow() as uow:
            ctx = self.contexto(uow, actor, datos, ahora)
            intento, asignacion = self.cargar(uow, ctx, intento_id, ahora)
            self.sesion_de(ctx, intento)
            plan = self.motor.plan_de_bloqueo(intento, asignacion, ctx.capacidad)
            informe = {"resultado": resultado, "capas": capas, "motivo": motivo, "informado_en": ahora}
            intento = uow.intentos.actualizar(intento["id"], bloqueo=informe)
            exigia_sistema = plan["capa_sistema"] or plan["parcial"]
            tipo = None
            if resultado == cat.B_LIBERADO and intento["estado"] in cat.CORRIENDO:
                tipo = cat.BLOQUEO_LIBERADO
            elif exigia_sistema and resultado == cat.B_PARCIAL:
                tipo = cat.BLOQUEO_PARCIAL
            elif exigia_sistema and resultado == cat.B_FALLIDO:
                tipo = cat.BLOQUEO_FALLIDO
            if tipo and intento["estado"] != cat.NO_INICIADO:
                huella = hashlib.sha256(json.dumps([resultado, capas, motivo], sort_keys=True).encode()).hexdigest()[:16]
                self.motor.incidente(uow, intento, tipo, ahora, detalle={"resultado": resultado, "motivo": motivo, "capas": capas},
                                     dispositivo_id=ctx.dispositivo_id or None, ref_cliente=f"bloqueo:{huella}", actor=ctx.alumno_id,
                                     asignacion=asignacion)
            else:
                self.motor.avisar(uow, asignacion, "evaluacion_panel", intento_id=intento["id"])
            return {"bloqueo": informe, "plan_bloqueo": plan, "incidente": tipo, "servidor_en": ahora}

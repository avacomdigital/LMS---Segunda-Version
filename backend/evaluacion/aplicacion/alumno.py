"""
Lo común a los casos de uso del ALUMNO sobre un intento: resolver quién es y desde qué tableta (D-19), cargar su intento al día con el reloj
y saber en qué sesión de tableta está escribiendo (D-7, BR-138). Ningún archivo de esta carpeta importa Django.
"""
from __future__ import annotations

from ..dominio import bloqueo
from ..dominio.errores import DispositivoAjeno, NoEncontrado
from .base import Contexto, Servicios, _CasoDeUso, resolver_contexto
from .motor import Motor
from .puertos import Actor, UnidadDeTrabajo


class _Alumno(_CasoDeUso):
    def __init__(self, servicios: Servicios):
        super().__init__(servicios)
        self.motor = Motor(servicios)

    # ---------------------------------------------------------------------------------- quién y desde dónde

    def contexto(self, uow: UnidadDeTrabajo, actor: Actor, datos: dict, ahora: int, *, registrar: bool = False,
                 exigir_aparato: bool = False) -> Contexto:
        """El alumno y su tableta. `registrar` (sólo al abrir un intento) reconoce o da de alta la tableta y guarda lo que declara: nombre,
        plataforma, versión de la app y su CAPACIDAD de control (D-11)."""
        registro: dict = {}
        if registrar:
            for clave in ("nombre", "plataforma", "version_app"):
                if datos.get(clave) not in (None, ""):
                    registro[clave] = str(datos[clave])
            if datos.get("capacidad_control") not in (None, ""):
                registro["capacidad_control"] = bloqueo.validar_capacidad(datos.get("capacidad_control"))
        return resolver_contexto(uow, actor, datos.get("dispositivo"), ahora=ahora, declarado=datos.get("alumno_id"), registrar=registrar,
                                 exigir_aparato=exigir_aparato, registro=registro or None)

    def cargar(self, uow: UnidadDeTrabajo, ctx: Contexto, intento_id: str, ahora: int) -> tuple[dict, dict]:
        """(intento, asignación) al día con el reloj: si el tiempo se agotó o el plazo venció, el intento ya viene entregado. Un intento ajeno no
        se revela (404)."""
        intento = uow.intentos.por_id(intento_id) if intento_id else None
        if intento is None or intento["alumno_id"] != ctx.alumno_id:
            raise NoEncontrado("No existe ese intento para este alumno.", intento_id=intento_id)
        asignacion = uow.asignaciones.por_id(intento["asignacion_id"])
        asignacion = self.motor.asegurar_asignacion(uow, asignacion, ahora)
        intento = uow.intentos.por_id(intento_id)                  # cerrar la asignación pudo entregarlo
        intento = self.motor.asegurar_intento(uow, intento, asignacion, ahora)
        return intento, asignacion

    @staticmethod
    def sesion_de(ctx: Contexto, intento: dict) -> dict:
        """La sesión de tableta desde la que escribe quien llama: la última en que esta tableta participó en el intento. Una tableta que nunca
        estuvo en el intento no escribe en él (para continuar desde otra se abre el intento de nuevo desde ella). Con JWT y sin tableta
        declarada se usa la actual."""
        sesiones = intento.get("sesiones") or []
        if not ctx.dispositivo_id:
            if ctx.actor.autenticado and sesiones:
                return sesiones[-1]
            raise DispositivoAjeno("Falta la tableta desde la que se escribe.", intento_id=intento["id"])
        propias = [s for s in sesiones if s.get("dispositivo_id") == ctx.dispositivo_id]
        if not propias:
            raise DispositivoAjeno(intento_id=intento["id"], dispositivo_id=ctx.dispositivo_id)
        return propias[-1]

    @staticmethod
    def es_la_tableta_actual(ctx: Contexto, intento: dict) -> bool:
        return not ctx.dispositivo_id or ctx.dispositivo_id == intento.get("dispositivo_id")

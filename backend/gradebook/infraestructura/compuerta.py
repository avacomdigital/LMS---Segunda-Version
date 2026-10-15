"""
La compuerta de MOD-011 sobre los resultados de MOD-010: en un nivel en MODO CALIFICACIONES, el alumno no ve el resultado de un intento (porcentaje, puntaje, aciertos por
pregunta) hasta que su calificación esté PUBLICADA en el libro. Sin esto, la política de liberación de MOD-010 y la publicación del libro eran dos controles independientes y
un `al_entregar` (o una liberación en MOD-010) enseñaba el porcentaje de una calificación que el profesor aún no había publicado.

  · Nivel en modo SIMPLE (el valor por defecto de todo nivel sin configurar): no veta nada; la política de MOD-010 sigue mandando (decisión S0: vetar aquí quitaría los resultados de
    MOD-010 a toda instalación que no haya activado el modo calificaciones; para no mostrar cifras a los más pequeños el profesor usa la política `nunca` de la evaluación).
  · Nivel en modo CALIFICACIONES: el resultado sale sólo si la calificación de ESE intento está `definitiva`. Si el libro todavía no la registró (el consumidor de eventos va unos
    segundos detrás, o la revisión está pendiente) queda retenido: ante la duda, el alumno no ve una nota que quizá no esté publicada. Retirar la publicación lo vuelve a cerrar.

Se registra al arrancar la aplicación (`GradebookConfig.ready`) por la interfaz pública de MOD-010 (`evaluacion.servicios`): MOD-010 no importa el libro.
"""
from __future__ import annotations

from ..aplicacion.base import contexto_de
from ..dominio import catalogos as cat
from .unidad_trabajo import Cajones

NOMBRE = "libro_de_calificaciones"


def compuerta_de_resultado(asignacion: dict, intento: dict) -> bool:
    """`True` si el libro NO retiene el resultado de este intento. Sólo se consulta cuando la política de MOD-010 ya lo mostraría."""
    cajones = Cajones()
    contexto = contexto_de(cajones, asignacion, intento["alumno_id"])
    nivel = cajones.niveles.get(contexto["nivel_clave"]) if contexto["nivel_clave"] else None
    en_calificaciones = nivel is not None and nivel["modo"] == cat.CALIFICACIONES and bool(nivel.get("escala_version_id"))
    if not en_calificaciones:
        return True
    calificacion = cajones.calificaciones.por_intento(intento["id"])
    return calificacion is not None and calificacion["estado"] == cat.DEFINITIVA

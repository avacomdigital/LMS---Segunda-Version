r"""
Qué rutas puede apagar la licencia y cuáles NUNCA (R-01 · «nunca se detiene una clase»).

Hay dos listas, y la primera manda sobre la segunda:

  · INTOCABLES: lo que ninguna licencia ni ningún fallo puede bloquear. Salen de los `urls.py` REALES de cada módulo (no de una enumeración a mano: una prueba recorre el resolvedor
    de rutas del proyecto y comprueba que cada ruta intocable responde IGUAL con la licencia degradada). Incluyen el aula para quien ya fue admitido, la evaluación mientras se
    presenta (abrir, responder, latido, incidentes, entregar), el modo estudio completo, el inicio de sesión, el latido de los equipos, los logs de los clientes, `/health/` y la
    propia licencia.
  · LICENCIABLES: la tabla «método + ruta → capacidad». Sólo lo que está AQUÍ puede responder «no disponible por licencia» (402), y sólo si la capacidad no está habilitada. Todo lo
    que no aparece (la inmensa mayoría) pasa tal cual.

El WebSocket no pasa por el middleware y nunca se bloquea.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import catalogos as cat

_TODOS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD")

# ---------------------------------------------------------------------------------------------------------------------- intocables (R-01)
_INTOCABLES = tuple(re.compile(patron) for patron in (
    r"^/health/?$",
    r"^/api/licencia/",                                                  # la propia licencia: sin ella no se puede renovar
    r"^/api/diagnostico/",                                               # medición de la red y diagnóstico
    r"^/api/logs/clientes/$",                                            # logs de OPS y Student
    r"^/api/dispositivos/latido/$",                                      # el latido de los equipos (se registran o se reconocen)
    r"^/api/acceso/(sesiones|instalacion|yo|configuracion|pin-maestro|aula)(/|$)",           # inicio y cierre de sesión, instalación, mi cuenta, PIN, grupos del aula
    r"^/api/acceso/(docentes/registro|docentes/restablecer|estudiantes/registro|estudiantes/[^/]+/pin)/$",   # registro propio y PIN del alumno
    r"^/api/acceso/autorizaciones-temporales/canjear/$",
    r"^/api/aula/",                                                      # la clase: unirse, readmitirse, actividades, estado, medios (el WebSocket ni pasa por aquí)
    r"^/api/modo-estudio/",                                              # estudio completo, incluido `sync` (que acepta sin sesión)
    r"^/api/evaluacion/(estudiantes|mias)/$",
    r"^/api/evaluacion/asignaciones/[^/]+/(antesala|intentos)/$",        # abrir el examen
    r"^/api/evaluacion/intentos/[^/]+/(estado|latido|preguntas|incidentes|bloqueo|entregar|resultado)/$",
    r"^/api/evaluacion/intentos/[^/]+/(medios|respuestas)/",             # medios del examen y respuestas
    r"^/api/m/",                                                         # el pase de medios (el middleware de acceso lo reescribe antes, esto es por si acaso)
))

# ---------------------------------------------------------------------------------------------------------------------- licenciables
@dataclass(frozen=True)
class RutaLicenciable:
    metodos: tuple[str, ...]
    patron: re.Pattern
    capacidad: str


def _l(metodos: tuple[str, ...], patron: str, capacidad: str) -> RutaLicenciable:
    return RutaLicenciable(metodos, re.compile(patron), capacidad)


_LICENCIABLES = (
    # reportes (CAP-081…086): todo `/api/reportes/` MENOS los boletines y las exportaciones. Ésas son hoy la ÚNICA vía para sacar las calificaciones y la pregunta Q-L12 del CTO
    # («¿puede un vencimiento limitar la exportación de calificaciones al cierre del ciclo?») tiene por defecto «no»: quedan como núcleo hasta que conteste (D-6).
    _l(_TODOS, r"^/api/reportes/(?!boletines/|exportaciones/)", cat.CAP_REPORTES),
    # búsqueda (MOD-021)
    _l(_TODOS, r"^/api/search/", cat.CAP_BUSQUEDA),
    # importaciones nuevas: el alta MASIVA de usuarios (el alta de uno a uno se rige por el cupo, no por la capacidad)
    _l(("POST",), r"^/api/acceso/usuarios/importar/$", cat.CAP_IMPORTACION),
    # administración avanzada (propuesta, Q-L1): crear roles, crear/adoptar/versionar escalas de calificación y reconstruir derivados. NUNCA lo que CIERRA puertas: las políticas de
    # acceso (`PUT /api/acceso/politicas/…`, con los interruptores del registro de profesores, el autorregistro y los visitantes) no se licencian (D-6).
    _l(("POST",), r"^/api/acceso/roles/$", cat.CAP_ADMIN_AVANZADA),
    _l(("POST",), r"^/api/gradebook/escalas/(adoptar/|[^/]+/versiones/)?$", cat.CAP_ADMIN_AVANZADA),
    _l(("POST",), r"^/api/gradebook/derivados/reconstruir/$", cat.CAP_ADMIN_AVANZADA),
)

RUTAS_INTOCABLES = tuple(p.pattern for p in _INTOCABLES)
RUTAS_LICENCIABLES = tuple((r.metodos, r.patron.pattern, r.capacidad) for r in _LICENCIABLES)


def es_intocable(ruta: str) -> bool:
    return any(p.search(ruta) for p in _INTOCABLES)


def capacidad_de(metodo: str, ruta: str) -> str | None:
    """La capacidad que gobierna esta petición, o None si ninguna la gobierna. Una ruta intocable no la tiene nunca."""
    if es_intocable(ruta):
        return None
    metodo = metodo.upper()
    for entrada in _LICENCIABLES:
        if metodo in entrada.metodos and entrada.patron.search(ruta):
            return entrada.capacidad
    return None

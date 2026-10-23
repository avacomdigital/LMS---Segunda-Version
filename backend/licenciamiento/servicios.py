"""
La interfaz de MOD-018 para los OTROS módulos del mismo proceso (BR-004): quien necesita saber qué puede hacer esta instalación pregunta aquí; nadie lee `m18_*`. La usan el middleware
de licencia, el cupo de equipos (`device_manager`) y de usuarios (`acceso`), los límites de concurrencia del aula (BR-063) y `/health/`.

Dos reglas que este archivo hace cumplir:

  · R-07  todo se lee de MEMORIA: cero consultas a la base de datos en el camino de una petición (una prueba lo comprueba con `assertNumQueries(0)`).
  · R-04  NINGÚN fallo interno de licenciamiento llega a quien pregunta: una excepción, una instantánea que no existe todavía, una carpeta de estado ilegible… se registra y se deja pasar
          (se usa el último estado bueno; si no lo hay, el de la política: la evaluación, con todo habilitado). La única excepción que sale es `CupoAgotado`, y es a propósito.

En desarrollo y pruebas (`LicenciaIlimitada`) todo está habilitado y no hay cupo; los límites de concurrencia son los de `settings`.
"""
from __future__ import annotations

import logging

from .dominio import catalogos as cat
from .dominio import cupo as dominio_cupo
from .dominio.errores import CupoAgotado, IdentidadRequerida

log = logging.getLogger("avacom.licenciamiento")


def _instantanea():
    from .infraestructura import contenedor, proveedores
    return proveedores.proveedor(contenedor.servicios()).instantanea()


def _modo() -> str:
    from .infraestructura import contenedor
    return contenedor.modo()


def instantanea():
    """La última instantánea buena (o None si todavía no se calculó). Nunca lanza."""
    try:
        return _instantanea()
    except Exception:   # noqa: BLE001 — R-04
        log.exception("No se pudo leer el estado de la licencia", extra={"evento": "licencia.lectura_fallo", "ruta": "bad"})
        return None


def capacidad_habilitada(capacidad: str) -> bool:
    """¿Está habilitado este módulo licenciable? Sin estado todavía (o ante cualquier fallo): sí. Lo que no es una capacidad licenciable (el núcleo) siempre está habilitado."""
    if capacidad not in cat.CAPACIDADES_LICENCIABLES:
        return True
    snap = instantanea()
    return True if snap is None else capacidad in snap.estado.capacidades


def estado_resumido() -> dict:
    """Lo que `/health/` añade (sólo el estado, sin detalles): `{estado, modo, restringe, dias_restantes}`. Nunca lanza."""
    snap = instantanea()
    if snap is None:
        return {"estado": "desconocido", "modo": _safe_modo(), "restringe": False, "dias_restantes": None}
    e = snap.estado
    return {"estado": e.estado, "modo": snap.modo, "restringe": e.restringe, "dias_restantes": e.dias_restantes}


def _safe_modo() -> str:
    try:
        return _modo()
    except Exception:   # noqa: BLE001
        return "desconocido"


def concurrencia(normal_por_defecto: int, pico_por_defecto: int) -> tuple[int, int]:
    """BR-063: `(normal, pico)` de dispositivos concurrentes: los de la licencia; sin licencia (desarrollo y pruebas, o aún sin evaluar), los valores de `settings` que se pasan."""
    try:
        if _modo() == "ilimitada":
            return int(normal_por_defecto), int(pico_por_defecto)
        snap = _instantanea()
        if snap is None or snap.limites_de_concurrencia is None:
            return int(normal_por_defecto), int(pico_por_defecto)
        lim = snap.estado.limites
        return dominio_cupo.concurrencia(lim.concurrentes_normal, lim.concurrentes_pico, normal_por_defecto, pico_por_defecto)
    except Exception:   # noqa: BLE001 — R-04
        log.exception("No se pudieron leer los límites de concurrencia de la licencia", extra={"evento": "licencia.concurrencia_fallo", "ruta": "bad"})
        return int(normal_por_defecto), int(pico_por_defecto)


def _exigir_cupo(tipo: str, en_uso: int) -> None:
    try:
        if _modo() == "ilimitada":
            return
        snap = _instantanea()
        if snap is None:
            return
        limite = snap.estado.limites.equipos if tipo == dominio_cupo.TIPO_EQUIPOS else snap.estado.limites.usuarios
        if dominio_cupo.admite(limite, en_uso):
            return
    except Exception:   # noqa: BLE001 — R-04: ante un fallo no se bloquea un alta
        log.exception("No se pudo comprobar el cupo de la licencia", extra={"evento": "licencia.cupo_fallo", "ruta": "bad"})
        return
    _contar(f"cupo:{tipo}")
    nombre = "equipos" if tipo == dominio_cupo.TIPO_EQUIPOS else "usuarios"
    raise CupoAgotado(f"Se alcanzó el cupo de {nombre} de la licencia ({limite}). Lo que ya existe sigue funcionando; para dar de alta más hace falta ampliar la licencia.",
                      tipo=tipo, limite=int(limite), en_uso=int(en_uso))


def exigir_equipo_nuevo(en_uso: int, identidad: dict | None = None, identificador_hw: str = "") -> dict | None:
    """P-08 · FUN-091: un equipo NUEVO cuenta contra el límite de equipos. `en_uso` = cuántos hay ya (sin el equipo maestro). Nunca se llama para uno que ya existe.

    Fase 5 (P-24): si el equipo trae su prueba de clave (`identidad`), se verifica aquí y se devuelve lo que `device_manager` guarda en el equipo nuevo (`clave_publica`, `clave_huella`,
    `garantia`, `garantia_detalle`); sin prueba (o con una que no pasa) se devuelve None y el equipo entra como `declarada`. En un nodo de producción la licencia puede pedir un nivel
    mínimo (`AVACOM_LICENCIA_IDENTIDAD_MINIMA`): sin él, `IdentidadRequerida` (402) y el equipo NUEVO no se da de alta. Nunca afecta a un equipo que ya existe. R-04: un fallo interno
    de la verificación deja pasar (sin identidad)."""
    _exigir_cupo(dominio_cupo.TIPO_EQUIPOS, en_uso)
    return _identidad_de_equipo_nuevo(identidad, identificador_hw)


def _identidad_de_equipo_nuevo(identidad: dict | None, identificador_hw: str) -> dict | None:
    try:
        from .aplicacion.identidad import identidad_de_equipo_nuevo
        from .infraestructura import contenedor
        return identidad_de_equipo_nuevo(contenedor.servicios(), identidad, identificador_hw, estricta=contenedor.modo() == "firmada")
    except IdentidadRequerida:
        _contar("identidad_requerida")
        raise
    except Exception:   # noqa: BLE001 — R-04
        log.exception("No se pudo verificar la identidad de un equipo nuevo", extra={"evento": "licencia.identidad_fallo", "ruta": "bad"})
        return None


def exigir_usuario_nuevo(en_uso: int) -> None:
    """P-08 · BR-027: una identidad NUEVA cuenta contra el límite de usuarios. `en_uso` = cuántas identidades activas hay ya (sin visitantes)."""
    _exigir_cupo(dominio_cupo.TIPO_USUARIOS, en_uso)


def _contar(clave: str) -> None:
    """Cuenta el bloqueo en memoria; el programador lo asienta (UNA vez por actor, clave y hora). Nunca lanza."""
    try:
        from .infraestructura import contenedor
        s = contenedor.servicios()
        s.vivo.registrar_bloqueo(_actor_actual(), clave, s.reloj.ahora_ms())
    except Exception:   # noqa: BLE001
        pass


def _actor_actual() -> str:
    try:
        from audit import contexto
        c = contexto.actual()
        return str(c.usuario_id or c.dispositivo_id or "anonimo")
    except Exception:   # noqa: BLE001
        return "anonimo"


def registrar_bloqueo_de_modulo(capacidad: str, actor: str | None = None) -> None:
    """Lo llama el middleware cuando responde «no disponible por licencia»."""
    try:
        from .infraestructura import contenedor
        s = contenedor.servicios()
        s.vivo.registrar_bloqueo(actor or _actor_actual(), capacidad, s.reloj.ahora_ms())
    except Exception:   # noqa: BLE001
        pass


def evaluar_ahora(origen: str = "accion"):
    """Recalcula la licencia en este instante (el arranque, el programador y las pruebas lo usan). Nunca lanza."""
    try:
        from .aplicacion.evaluar import Evaluar
        from .infraestructura import contenedor
        if contenedor.modo() == "ilimitada":
            return _instantanea()
        return Evaluar(contenedor.servicios()).ejecutar(origen)
    except Exception:   # noqa: BLE001
        log.exception("No se pudo evaluar la licencia", extra={"evento": "licencia.evaluacion_fallo", "ruta": "bad"})
        return None

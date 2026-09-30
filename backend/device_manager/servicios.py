"""
La interfaz de MOD-009 para los OTROS módulos del mismo proceso (BR-004: quien necesita un cambio en
datos ajenos invoca la interfaz del propietario). La usan el login de `acceso` y la sesión de clase de
`classroom_engine`, siempre dentro de su propia transacción: aquí no se abre ninguna.

Devuelve y recibe dicts planos; los errores son los de `device_manager.dominio.errores` y cada
llamador los traduce a los suyos en su adaptador.
"""
from __future__ import annotations

import time

from .aplicacion import casos_uso as cu
from .dominio import dispositivo as dom
from .infraestructura.unidad_trabajo import Cajones


def _ahora(momento: int | None) -> int:
    return momento if momento is not None else int(time.time() * 1000)


def resolver(identificador_hw: str, nombre: str = "", tipo: str = dom.TABLETA, plataforma: str = "",
             version_app: str = "", momento: int | None = None, actor: str = "") -> dict | None:
    """Reconoce (o registra la primera vez) la tableta que se presenta con su huella. None si no
    trae huella o el nodo no está instalado: el aula sigue sin dispositivo, como hasta ahora."""
    if not str(identificador_hw or "").strip():
        return None
    cajones = Cajones()
    if not cajones.organizaciones.unica_id():
        return None
    dispositivo, _ = cu.resolver(cajones, _ahora(momento), identificador_hw, nombre, tipo, plataforma, version_app, actor)
    return dispositivo


def por_id(dispositivo_id: str) -> dict | None:
    return Cajones().dispositivos.por_id(dispositivo_id) if dispositivo_id else None


def por_identificador(organizacion_id: str, identificador_hw: str) -> dict | None:
    return Cajones().dispositivos.por_identificador(organizacion_id, identificador_hw)


def listar(organizacion_id: str, solo_activos: bool = True) -> list[dict]:
    return Cajones().dispositivos.listar(organizacion_id, solo_activos)


def latido(dispositivo_id: str, momento: int | None = None, plataforma: str = "", version_app: str = "",
           espacio_libre_mb: int | None = None, bateria_pct: int | None = None) -> dict | None:
    if not dispositivo_id:
        return None
    return cu.latido(Cajones(), _ahora(momento), dispositivo_id, plataforma, version_app, espacio_libre_mb, bateria_pct)


def renombrar(dispositivo_id: str, nombre: str) -> dict | None:
    """Lo único que el login de `acceso` cambia de un dispositivo además del latido."""
    nombre = dom.normalizar_nombre(nombre)
    if not dispositivo_id or not nombre:
        return por_id(dispositivo_id)
    return Cajones().dispositivos.actualizar(dispositivo_id, nombre=nombre)


def bloqueados_entre(dispositivo_ids: list[str]) -> set[str]:
    """Los que no deben recibir lanzamientos: bloqueados o retirados."""
    return Cajones().dispositivos.bloqueados_entre(list(dispositivo_ids))


def abrir_sesion_alumno(alumno_id: str, dispositivo_id: str, momento: int | None = None, actor: str = "") -> dict:
    """Lanza DispositivoBloqueado / DispositivoInactivo (dominio de MOD-009)."""
    return cu.abrir_sesion_alumno(Cajones(), _ahora(momento), alumno_id, dispositivo_id, actor)


def cerrar_sesion_alumno(sesion_id: str, momento: int | None = None, motivo: str = dom.USUARIO, actor: str = "") -> dict | None:
    if not sesion_id:
        return None
    return cu.cerrar_sesion_alumno(Cajones(), _ahora(momento), sesion_id, motivo, actor)


def sesion_abierta_de_alumno(alumno_id: str) -> dict | None:
    return Cajones().sesiones_alumno.abierta_de_alumno(alumno_id)


def organizacion_id() -> str | None:
    """La organización del nodo; None si aún no está instalado (quien pregunta decide cómo degradar)."""
    return Cajones().organizaciones.unica_id()


def asignado_a(dispositivo_id: str) -> str | None:
    """A quién pertenece el equipo (perfil `asignado`); None si es compartido o no existe. El modo de estudio lo usa para saber quién
    puede llevarse un paquete en él (BR-054): estudiar en línea sirve en cualquier equipo, aunque no sea suyo."""
    fila = por_id(dispositivo_id)
    return fila["asignado_a_id"] if fila and fila.get("perfil") == dom.ASIGNADO else None


def asignados_a(alumno_ids: list[str]) -> dict[str, dict]:
    """Por cada alumno, el equipo activo que tiene asignado (el más reciente si tuviera varios)."""
    return Cajones().dispositivos.asignados_a(list(alumno_ids))

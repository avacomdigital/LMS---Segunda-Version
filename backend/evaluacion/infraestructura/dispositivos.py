"""
MOD-009 visto desde la evaluación: por su interfaz (`device_manager.servicios`), dentro de la transacción del caso de uso (BR-004: la evaluación no
escribe m09_*, pide). Sus errores se traducen a los del módulo. La CAPACIDAD DE CONTROL la declara la tableta (registro y latido) y la guarda MOD-009.
"""
from __future__ import annotations

from ..dominio import errores as e10


class DispositivosDeviceManager:
    @staticmethod
    def _traducir(fn, *args, **kwargs):
        from device_manager.dominio import errores as e9
        try:
            return fn(*args, **kwargs)
        except e9.DispositivoBloqueado as error:
            raise e10.DispositivoBloqueado(error.detalle, **error.extra) from error
        except e9.DispositivoInactivo as error:
            raise e10.DispositivoInactivo(error.detalle, **error.extra) from error
        except e9.NoEncontrado as error:
            raise e10.NoEncontrado(error.detalle, **error.extra) from error
        except e9.ErrorDispositivos as error:
            raise e10.DatosInvalidos(error.detalle, **error.extra) from error

    def por_identificador(self, organizacion_id: str, huella: str) -> dict | None:
        from device_manager import servicios
        return servicios.por_identificador(organizacion_id, huella)

    def resolver(self, huella: str, nombre: str = "", plataforma: str = "", version_app: str = "", momento: int | None = None,
                 capacidad_control: str | None = None) -> dict | None:
        from device_manager import servicios
        return self._traducir(servicios.resolver, huella, nombre=nombre, plataforma=plataforma, version_app=version_app, momento=momento,
                              capacidad_control=capacidad_control)

    def por_id(self, dispositivo_id: str) -> dict | None:
        from device_manager import servicios
        return servicios.por_id(dispositivo_id)

    def asignados_a(self, alumno_ids: list[str]) -> dict[str, dict]:
        from device_manager import servicios
        return servicios.asignados_a(alumno_ids)

    def latido(self, dispositivo_id: str, momento: int, capacidad_control: str | None = None, telemetria: dict | None = None) -> dict | None:
        from device_manager import servicios
        telemetria = telemetria or {}
        return servicios.latido(dispositivo_id, momento, espacio_libre_mb=telemetria.get("espacio_libre_mb"),
                                bateria_pct=telemetria.get("bateria_pct"), capacidad_control=capacidad_control)

    def abrir_sesion_alumno(self, alumno_id: str, dispositivo_id: str, momento: int, actor: str = "") -> dict:
        from device_manager import servicios
        return self._traducir(servicios.abrir_sesion_alumno, alumno_id, dispositivo_id, momento, actor)

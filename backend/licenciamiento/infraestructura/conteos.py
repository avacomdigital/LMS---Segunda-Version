"""
Lo que cuentan los módulos dueños, por su `servicios.py` (R-08: licenciamiento NO lee `m01_*` ni `m09_*`). Devuelve None cuando no se pudo contar (el nodo aún no está instalado, la base está
ocupada): el cupo no se aplica y la pantalla lo dice; contar nunca lanza ni interrumpe una clase.

  · equipos   los equipos activos del inventario, SIN el equipo maestro (tipo MASTER, que es el que corre OPS): el cupo es de las tabletas y los portátiles de los alumnos
  · usuarios  las identidades activas, sin las cuentas efímeras de visitantes (RN-45) ni las retiradas (BR-027)
"""
from __future__ import annotations

import logging

log = logging.getLogger("avacom.licenciamiento")

TIPO_EQUIPO_MAESTRO = "MASTER"


class ConteosDeLosDuenos:
    def equipos(self) -> int | None:
        try:
            from device_manager import servicios as dispositivos
            organizacion = dispositivos.organizacion_id()
            if not organizacion:
                return None
            return sum(1 for d in dispositivos.listar(organizacion, True) if str(d.get("tipo") or "").upper() != TIPO_EQUIPO_MAESTRO)
        except Exception:   # noqa: BLE001 — contar nunca interrumpe nada
            log.exception("No se pudieron contar los equipos", extra={"evento": "licencia.conteo_equipos_fallo", "ruta": "bad"})
            return None

    def usuarios(self) -> int | None:
        try:
            from acceso import servicios as identidad
            return identidad.contar_usuarios_activos()
        except Exception:   # noqa: BLE001
            log.exception("No se pudieron contar los usuarios", extra={"evento": "licencia.conteo_usuarios_fallo", "ruta": "bad"})
            return None

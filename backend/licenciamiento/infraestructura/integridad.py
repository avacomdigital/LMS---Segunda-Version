r"""
La SEÑAL de integridad del despliegue (MOD-018, P-23): lo que el `Host` del instalador deja en `%ProgramData%\AVACOM\OPS Master\Config\integridad.json` cuando arranca el servicio y verifica
que el código instalado es el que firmó el instalador (firma del manifiesto, huellas de Backend, Runtime, App y la DLL nativa).

Contrato (versión 1; sin datos de personas ni de licencias; las rutas son de CÓDIGO del producto):

    {"version": 1, "verificado": "2026-10-22T17:00:00Z", "estado": "ok|alterada|sin_firma|no_verificable",
     "firma": "ok|ausente|ilegible|kid_desconocido|invalida|sin_llave", "kid": "upd-2026-1", "version_producto": "2.16.0", "archivos_comprobados": 5871,
     "hallazgos": [{"tipo": "backend|runtime|app|nativo|manifiesto|firma|otro", "detalle": "modificado|falta|sobra|…", "cantidad": 2, "ejemplos": ["Backend/x.py"]}]}

Qué hace el nodo con ella: SÓLO `estado == "alterada"` cuenta. Cada TIPO de hallazgo entra a la lectura de anclas como `despliegue:<tipo>` (por ejemplo `despliegue:backend`), de modo que recorre el
mismo camino que las demás alteraciones: una observación, el asiento `licencia.integridad_alterada` y el evento `.v1` (UNA vez al día), la bandera `integridad_alterada` del estado y el aviso al
administrador en OPS. NUNCA degrada una función ni detiene una clase (la bandera es un aviso): es EVIDENCIA, no prevención. El `Host` también es un archivo que quien administra el equipo puede
parchear, y con él esta señal (A4; ver 04-proteccion.md).

Un archivo ausente, ilegible, de otra versión o de un estado que no es «alterada» no avisa nada: el nodo no inventa una alarma por algo que no entiende. Se relee sólo cuando cambia (fecha y tamaño).
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

log = logging.getLogger("avacom.licenciamiento")

ARCHIVO = "integridad.json"
TIPOS = ("backend", "runtime", "app", "nativo", "manifiesto", "firma", "otro")
PREFIJO = "despliegue:"
MAX_BYTES = 256 * 1024          # la señal mide unos cientos de bytes; un archivo enorme no es la señal


class SenalDeIntegridad:
    """Lee la señal del `Host`. Nunca lanza: lo que no se entiende no avisa."""

    def __init__(self, ruta: Path | str):
        self._ruta = Path(ruta)
        self._candado = threading.Lock()
        self._marca: tuple[int, int] | None = None
        self._cache: tuple[str, ...] = ()

    @property
    def ruta(self) -> Path:
        return self._ruta

    def alteradas(self) -> tuple[str, ...]:
        """Los tipos alterados como `despliegue:<tipo>`, ordenados y sin repetir; vacío si no hay nada que avisar."""
        try:
            info = self._ruta.stat()
        except OSError:
            self._marca, self._cache = None, ()
            return ()
        marca = (info.st_mtime_ns, info.st_size)
        with self._candado:
            if marca == self._marca:
                return self._cache
            self._cache = self._leer(info.st_size)
            self._marca = marca
            return self._cache

    def _leer(self, tamano: int) -> tuple[str, ...]:
        if tamano > MAX_BYTES:
            return ()
        try:
            datos = json.loads(self._ruta.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            log.warning("La señal de integridad del despliegue no se pudo leer; se ignora", extra={"evento": "licencia.senal_integridad_ilegible", "ruta": "bad"})
            return ()
        if not isinstance(datos, dict) or datos.get("version") != 1 or datos.get("estado") != "alterada":
            return ()
        tipos: set[str] = set()
        for hallazgo in datos.get("hallazgos", []) if isinstance(datos.get("hallazgos"), list) else []:
            tipo = hallazgo.get("tipo") if isinstance(hallazgo, dict) else None
            tipos.add(tipo if tipo in TIPOS else "otro")
        return tuple(PREFIJO + t for t in sorted(tipos or {"otro"}))      # «alterada» sin detalle legible sigue siendo una alteración

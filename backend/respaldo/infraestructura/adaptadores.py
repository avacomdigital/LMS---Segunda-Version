"""
Los adaptadores pequeños de MOD-016: el reloj y la versión del nodo, el aula, el registro de módulos, la memoria del proceso, las llaves de soporte de AVACOM y lo que otros módulos rehacen
tras una restauración. Cada uno toca a su vecino SÓLO por la interfaz que el vecino publica (`servicios.py`, comandos de gestión): BR-003.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime
from pathlib import Path

from django.conf import settings

log = logging.getLogger("avacom.respaldo")

_KID = re.compile(r"^[a-z0-9._-]{1,32}$")
PRODUCCION = "produccion"


class RelojDelNodo:
    def ahora_ms(self) -> int:
        from nodo import servicios as nodo   # frontera entre módulos: sólo en el adaptador
        return int(nodo.ahora_ms())

    def desfase_min(self) -> int:
        desfase = datetime.now().astimezone().utcoffset()
        return int(desfase.total_seconds() // 60) if desfase is not None else 0


class NodoDelProducto:
    def ultima_secuencia(self) -> int:
        try:
            from nodo import servicios as nodo
            return int(nodo.ultima_secuencia())
        except Exception:   # noqa: BLE001 — un respaldo sin la marca de secuencia sigue siendo un respaldo
            log.exception("No se pudo leer la última secuencia de la cola única", extra={"evento": "respaldo.secuencia_ilegible", "ruta": "bad"})
            return 0

    def version_producto(self) -> str:
        configurada = str(getattr(settings, "AVACOM_LMS_VERSION", "") or os.environ.get("AVACOM_LMS_VERSION", "")).strip()
        if configurada:
            return configurada
        raiz = Path(settings.BASE_DIR).parent
        for ruta in (raiz / "manifiesto.json", raiz / "installer" / "version.json"):
            try:
                version = str(json.loads(ruta.read_text(encoding="utf-8-sig")).get("version") or "").strip()
            except Exception:   # noqa: BLE001 — la versión es un rótulo, no un requisito
                continue
            if version:
                return version
        return "0.0.0"

    def institucion(self) -> str:
        try:
            from acceso import servicios as acceso
            return acceso.nombre_de_la_organizacion()
        except Exception:   # noqa: BLE001
            return ""


class AulaDelNodo:
    """Lo responde el dueño de las sesiones de clase. Ante un fallo se asume que SÍ hay clase (R-01: ante la duda, no se toca el aula)."""

    def sesiones_activas(self) -> int:
        try:
            from classroom_engine import servicios as aula
            return 1 if aula.hay_sesion_activa() else 0
        except Exception:   # noqa: BLE001
            return 1


class ModulosDelNodo:
    """FUN-175: un módulo declara su restauración aislada en `avacom_lms/modulos.json` (`restauracion_aislada: true`). Hoy ninguno la declara."""

    def declara_restauracion_aislada(self, modulo: str) -> bool:
        try:
            datos = json.loads((Path(settings.BASE_DIR) / "avacom_lms" / "modulos.json").read_text(encoding="utf-8-sig"))
            return bool(datos.get("modulos", {}).get(modulo, {}).get("restauracion_aislada"))
        except Exception:   # noqa: BLE001
            return False


class MemoriaDelProceso:
    def __init__(self):
        self._candado = threading.Lock()
        self._marcha: dict | None = None
        self._aplazado: int | None = None

    def en_marcha(self) -> dict | None:
        with self._candado:
            return None if self._marcha is None else dict(self._marcha)

    def marcar(self, respaldo_id: str, operacion: str, en: int) -> None:
        with self._candado:
            self._marcha = {"respaldo_id": respaldo_id, "operacion": operacion, "en": int(en)}

    def liberar(self) -> None:
        with self._candado:
            self._marcha = None

    def aplazado_por_clase(self) -> int | None:
        with self._candado:
            return self._aplazado

    def aplazar(self, en: int | None) -> None:
        with self._candado:
            self._aplazado = en


class SoporteDeAvacom:
    """Las llaves PÚBLICAS con las que AVACOM firma los pases de soporte: en producción sólo `claves/produccion.json`; en desarrollo y pruebas, también `claves/desarrollo.json`."""

    def __init__(self, carpeta: Path, entorno: str):
        self._carpeta, self._entorno = Path(carpeta), entorno

    @staticmethod
    def _cargar(archivo: Path) -> dict[str, bytes]:
        if not archivo.is_file():
            return {}
        try:
            datos = json.loads(archivo.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            log.exception("El archivo de llaves de soporte %s no se pudo leer", archivo.name, extra={"evento": "respaldo.claves_ilegibles", "ruta": "bad"})
            return {}
        salida: dict[str, bytes] = {}
        for entrada in datos.get("claves", []) if isinstance(datos, dict) else []:
            try:
                kid, estado, publica = str(entrada["kid"]), str(entrada.get("estado", "vigente")), bytes.fromhex(str(entrada["publica"]))
            except (KeyError, ValueError, TypeError, AttributeError):
                continue
            if _KID.match(kid) and len(publica) == 32 and estado in ("vigente", "siguiente"):
                salida[kid] = publica
        return salida

    def llaves_publicas(self) -> dict[str, bytes]:
        llaves = self._cargar(self._carpeta / "produccion.json")
        if self._entorno != PRODUCCION:
            llaves.update(self._cargar(self._carpeta / "desarrollo.json"))
        return llaves


class TrasRestaurarDelNodo:
    """
    Lo que se rehace tras restaurar, cada paso en lo suyo y por su interfaz (BR-003). Un paso que falla se anota y los demás siguen: la restauración ya se aplicó y el técnico decide
    qué repetir. Orden: esquema (la base puede ser de una versión anterior) → nodo (INV-002: la secuencia nunca retrocede) → sesiones (MOD-001) → licencia (MOD-018) → índices y reportes.
    """

    COMANDOS = (("search_reconstruir", {}), ("reporting_reconstruir", {}), ("gradebook_reconstruir", {"reproducir": True}))

    def ejecutar(self, huella_nueva: bool) -> dict:
        resultado: dict = {"esquema": None, "nodo": None, "sesiones": None, "licencia": None, "reconstruidos": [], "fallos": []}

        def paso(nombre: str, funcion) -> None:
            try:
                resultado[nombre] = funcion()
            except Exception as error:   # noqa: BLE001 — R-04
                log.exception("Tras restaurar, falló «%s»", nombre, extra={"evento": "respaldo.tras_restaurar_fallo", "ruta": "bad"})
                resultado["fallos"].append(f"{nombre}: {str(error)[:120]}")

        from django.core.management import call_command

        def esquema():
            call_command("migrate", interactive=False, verbosity=0)
            return "al día"

        def nodo():
            from nodo import servicios as n
            r = n.arrancar()
            return "arranque registrado" if r else "sin cambios"

        def sesiones():
            from acceso import servicios as a
            return a.revocar_sesiones_por_restauracion()

        def licencia():
            from licenciamiento import servicios as l
            l.evaluar_ahora("restauracion")
            return "revalidada contra la huella del equipo"

        paso("esquema", esquema)
        paso("nodo", nodo)
        paso("sesiones", sesiones)
        paso("licencia", licencia)
        for comando, argumentos in self.COMANDOS:
            try:
                call_command(comando, verbosity=0, **argumentos)
                resultado["reconstruidos"].append(comando.split("_")[0])
            except Exception as error:   # noqa: BLE001
                log.exception("Tras restaurar, falló «%s»", comando, extra={"evento": "respaldo.tras_restaurar_fallo", "ruta": "bad"})
                resultado["fallos"].append(f"{comando}: {str(error)[:120]}")
        return resultado

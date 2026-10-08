"""
Apoyo a las pruebas del sistema de logs (§2.3 del prompt de MOD-019).

    CorredorDePruebas   el TEST_RUNNER del backend: marca cada caso en el contexto (todas las líneas de un test llevan
                        `caso=<id del test>`), y al terminar imprime la carpeta de logs si algo falló o la borra si
                        todo pasó (AVACOM_LMS_CONSERVAR_LOGS=1 la conserva).
    LogsDePrueba        mixin para TestCase: `lineas_log(...)`, `assertLogged(...)`, `assertNoLogged(...)` sobre las
                        líneas de ESTE caso, para garantizar que un happy path no deja errores escondidos.
"""
from __future__ import annotations

import json
import os
import shutil
import unittest
from pathlib import Path

from django.conf import settings
from django.test.runner import DiscoverRunner

from . import contexto


def _reiniciar_cola_de_medios() -> None:
    """La cola de medios guarda en memoria y en disco lo que ya trajo de la fuente: cada caso empieza con la suya vacía (los casos usan servidores de
    contenido distintos y no deben verse entre sí)."""
    try:
        from cola_medios.infraestructura import contenedor
        contenedor.reiniciar()
    except Exception:   # noqa: BLE001 — sin la app (o sin migrar) las pruebas siguen
        pass


class ResultadoConCaso(unittest.TextTestResult):
    """Fija `caso` en el contexto al empezar cada test y lo limpia al terminar."""

    def startTest(self, test):   # noqa: N802 — nombre de unittest
        self._token_caso = contexto.establecer(caso=test.id(), origen=contexto.ORIGEN_PRUEBA)
        _reiniciar_cola_de_medios()
        super().startTest(test)

    def stopTest(self, test):   # noqa: N802
        super().stopTest(test)
        token = getattr(self, "_token_caso", None)
        if token is not None:
            try:
                contexto.restaurar(token)
            except ValueError:
                contexto.limpiar()
            self._token_caso = None


class CorredorDePruebas(DiscoverRunner):
    """Además: `TransactionTestCase` vacía las tablas con DELETE, que los triggers de la bitácora abortan. Aquí, y
    sólo aquí (pruebas), el vaciado quita los triggers antes y los repone después; la base de producción no pasa por esto."""

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        from django.db.backends.base.operations import BaseDatabaseOperations

        from .infraestructura import triggers

        original = BaseDatabaseOperations.execute_sql_flush
        if getattr(original, "_avacom_envuelto", False):
            return

        def con_triggers(self, sql_list):
            try:
                triggers.quitar(self.connection)
            except Exception:   # noqa: BLE001 — sin tabla aún
                pass
            try:
                return original(self, sql_list)
            finally:
                try:
                    triggers.crear(self.connection)
                except Exception:   # noqa: BLE001
                    pass

        con_triggers._avacom_envuelto = True
        BaseDatabaseOperations.execute_sql_flush = con_triggers

    def get_resultclass(self):
        base = super().get_resultclass()
        if base is None:
            return ResultadoConCaso
        return type("ResultadoConCasoY" + base.__name__, (ResultadoConCaso, base), {})

    def run_suite(self, suite, **kwargs):
        resultado = super().run_suite(suite, **kwargs)
        carpeta = Path(getattr(settings, "AVACOM_LMS_DIR_LOGS_EFECTIVO", ""))
        if not carpeta or not carpeta.exists():
            return resultado
        conservar = os.environ.get("AVACOM_LMS_CONSERVAR_LOGS", "0") == "1"
        if resultado.wasSuccessful() and not conservar:
            shutil.rmtree(carpeta, ignore_errors=True)
        else:
            print(f"\nLogs de la corrida: {carpeta}")
        return resultado


class LogsDePrueba:
    """Mixin: lectura de los logs JSON Lines de la corrida filtrados por el caso en curso."""

    ARCHIVOS_LOG = ("backend-app.log", "backend-errores.log", "backend-auditoria.log", "backend-clientes.log", "instalacion.log")

    @staticmethod
    def carpeta_logs() -> Path:
        return Path(settings.AVACOM_LMS_DIR_LOGS_EFECTIVO)

    def lineas_log(self, canal: str | None = None, nivel: str | None = None, evento: str | None = None,
                   archivo: str | None = None, ruta: str | None = None, todos_los_casos: bool = False) -> list[dict]:
        caso = contexto.actual().caso
        archivos = [archivo] if archivo else list(self.ARCHIVOS_LOG)
        salida: list[dict] = []
        vistos: set[tuple] = set()
        for nombre in archivos:
            ruta_archivo = self.carpeta_logs() / nombre
            if not ruta_archivo.exists():
                continue
            with ruta_archivo.open(encoding="utf-8") as f:
                for cruda in f:
                    cruda = cruda.strip()
                    if not cruda:
                        continue
                    try:
                        linea = json.loads(cruda)
                    except ValueError:
                        continue
                    if not todos_los_casos and caso and linea.get("caso") != caso:
                        continue
                    if canal and linea.get("canal") != canal:
                        continue
                    if nivel and linea.get("nivel") != nivel:
                        continue
                    if evento and linea.get("evento") != evento:
                        continue
                    if ruta and linea.get("ruta") != ruta:
                        continue
                    clave = (linea.get("ts"), linea.get("logger"), linea.get("mensaje"), linea.get("evento"))
                    if clave in vistos:   # la misma línea puede estar en app y en errores
                        continue
                    vistos.add(clave)
                    salida.append(linea)
        return salida

    def assertLogged(self, **filtros) -> list[dict]:   # noqa: N802 — estilo unittest
        lineas = self.lineas_log(**filtros)
        self.assertTrue(lineas, f"No hay ninguna línea de log con {filtros} para el caso {contexto.actual().caso}")
        return lineas

    def assertNoLogged(self, **filtros) -> None:   # noqa: N802
        lineas = self.lineas_log(**filtros)
        self.assertFalse(lineas, f"Había líneas de log con {filtros}: {[l.get('mensaje') for l in lineas][:5]}")

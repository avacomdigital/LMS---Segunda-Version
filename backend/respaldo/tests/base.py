"""
Base común de las pruebas de integración de MOD-016: un nodo REAL (instalado por HTTP como lo hace OPS: organización, administración, un docente y un estudiante), la carpeta de respaldos,
una «memoria USB» y una carpeta de archivos de la institución en carpetas temporales, la clave del nodo y la cola única y la bitácora de verdad. Lo único falso es el reloj del nodo (que la
prueba mueve), el aplicador de la restauración (que apunta a una base de archivo aparte, no a la conexión de la prueba) y lo que otros módulos rehacen tras restaurar.
"""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

from django.db import connection
from django.test import override_settings
from rest_framework.test import APIClient

from acceso.tests.base import BaseAcceso
from respaldo.dominio import catalogos as cat
from respaldo.infraestructura import contenedor
from respaldo.infraestructura.aplicador import AplicadorSqlite

from . import emisor

R = "/api/respaldo"


class RelojFalso:
    def __init__(self, t: int):
        self.t = int(t)

    def ahora_ms(self) -> int:
        return self.t

    def desfase_min(self) -> int:
        return 0

    def avanzar(self, ms: int) -> None:
        self.t += int(ms)


class TrasFalso:
    """Lo que otros módulos rehacen tras restaurar: aquí sólo se anota que se pidió (lo real se prueba aparte)."""

    def __init__(self):
        self.llamadas: list[bool] = []

    def ejecutar(self, huella_nueva: bool) -> dict:
        self.llamadas.append(huella_nueva)
        return {"esquema": "al día", "nodo": "arranque registrado", "sesiones": 3, "licencia": "revalidada contra la huella del equipo", "reconstruidos": ["search", "reporting", "gradebook"],
                "fallos": []}


class BaseRespaldo(BaseAcceso):
    """Un nodo real con la carpeta de respaldos, una memoria USB y una carpeta de archivos de la institución temporales. `self.t0` es el instante de la prueba."""

    def setUp(self):
        super().setUp()
        from nodo.pruebas import nodo_limpio
        self.carpeta = Path(tempfile.mkdtemp(prefix="avacom-respaldo-prueba-"))
        self.usb = Path(tempfile.mkdtemp(prefix="avacom-usb-respaldo-"))
        self.archivos = Path(tempfile.mkdtemp(prefix="avacom-archivos-"))
        self.carpeta_nodo = Path(tempfile.mkdtemp(prefix="avacom-nodo-prueba-"))
        self.viva = Path(tempfile.mkdtemp(prefix="avacom-base-viva-"))
        for c in (self.carpeta, self.usb, self.archivos, self.carpeta_nodo, self.viva):
            self.addCleanup(shutil.rmtree, c, True)
        sobre = override_settings(AVACOM_RESPALDO_DIR=str(self.carpeta), AVACOM_RESPALDO_UNIDADES=str(self.usb), AVACOM_RESPALDO_CARPETAS=f"evidencias={self.archivos}",
                                  AVACOM_NODO_DIR=str(self.carpeta_nodo))
        sobre.enable()
        self.addCleanup(sobre.disable)
        nodo_limpio()
        self.addCleanup(nodo_limpio)
        contenedor.reiniciar()
        self.addCleanup(contenedor.reiniciar)
        self.s = contenedor.servicios()
        self.reloj = RelojFalso(int(time.time() * 1000))
        self.s.reloj = self.reloj
        self.s.config = type(self.s.config)(**{**self.s.config.__dict__, "verificar_al_terminar": True})
        self.t0 = self.reloj.t
        self.tras = TrasFalso()
        self.s.tras = self.tras
        # La «base viva» de la restauración es un archivo aparte: la conexión de la prueba está dentro de una transacción y SQLite no deja copiarle encima.
        self.base_viva = self.viva / "viva.sqlite3"
        sqlite3.connect(str(self.base_viva)).close()
        self.conexion_viva = sqlite3.connect(str(self.base_viva))
        self.addCleanup(self.conexion_viva.close)
        self.s.aplicador = AplicadorSqlite(self.s.origen, destino=lambda: self.conexion_viva)
        # La API de respaldo de SQLite no copia desde una conexión que está en medio de una escritura (la envoltura de un `TestCase`). En producción el vigilante y las peticiones la
        # usan SIN transacción abierta (probado aparte con `copiar_base`); aquí la instantánea sale de `iterdump`, que lee con la misma conexión: esquema, triggers y datos.
        self.s.origen.instantanea_de_la_base = self._instantanea_de_prueba

    def _instantanea_de_prueba(self, destino: Path) -> int:
        connection.ensure_connection()
        copia = sqlite3.connect(str(destino))
        try:
            copia.executescript(chr(10).join(connection.connection.iterdump()))
            copia.commit()
        finally:
            copia.close()
        return Path(destino).stat().st_size

    # ----------------------------------------------------------------------------------------------------------------------- personas
    def crear_usuario(self, rol: str, dni: str, secreto: str, alias: str):
        r = self.admin.post("/api/acceso/usuarios/", {
            "rol": rol, "alias": alias, "persona": {"nombres": alias, "apellidos": "Prueba"},
            "identificadores": [{"tipo": "DNI", "valor": dni, "es_login": True}], "secreto": secreto, "secreto_definitivo": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"], self.sesion(dni, secreto)

    def tecnico(self) -> APIClient:
        if not hasattr(self, "_tecnico"):
            self._tecnico_id, self._tecnico = self.crear_usuario("TECHNICIAN", "70.111.222", "Tecnico.2026!Aula", "Técnico AVACOM")
        return self._tecnico

    def reportes(self) -> APIClient:
        _, cliente = self.crear_usuario("REPORTS", "60.222.333", "Reportes.2026!Aula", "Reportes")
        return cliente

    # ----------------------------------------------------------------------------------------------------------------------- pases y respaldos
    def pase(self, *acciones: str, **kw) -> str:
        return emisor.emitir_b64(acciones or (cat.P_RESTAURAR, cat.P_EXPORTAR), self.reloj.t, **kw)

    def respaldar(self, tipo: str = "completo", cliente: APIClient | None = None) -> dict:
        r = (cliente or self.tecnico()).post(f"{R}/respaldos/ahora/", {"tipo": tipo}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def ficha(self, respaldo_id: str, cliente: APIClient | None = None) -> dict:
        r = (cliente or self.admin).get(f"{R}/respaldos/{respaldo_id}/")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def emitir_custodia(self) -> str:
        r = self.tecnico().post(f"{R}/custodia/emitir/", {}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["codigo"]

    def dejar_archivo(self, nombre: str, contenido: bytes, mtime_ms: int | None = None) -> Path:
        ruta = self.archivos / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)
        if mtime_ms is not None:
            import os
            os.utime(ruta, (mtime_ms / 1000, mtime_ms / 1000))
        return ruta

    # ----------------------------------------------------------------------------------------------------------------------- lo que dejó
    def eventos(self) -> list:
        from nodo import pruebas
        return list(pruebas.cola(cat.MODULO))

    def tipos_de_eventos(self) -> list[str]:
        return [e.tipo_evento for e in self.eventos()]

    def acciones_asentadas(self) -> list[str]:
        from audit.models import Bitacora
        return [a.accion for a in Bitacora.objects.filter(modulo="respaldo").order_by("secuencia")]

    def archivos_escritos(self) -> list[str]:
        return sorted(str(p.relative_to(self.carpeta)).replace("\\", "/") for p in self.carpeta.rglob("*") if p.is_file())

    def tick(self, origen: str = "prueba") -> dict:
        from respaldo.aplicacion.vigilante import Tick
        return Tick(self.s).ejecutar(origen)


__all__ = ["R", "BaseRespaldo", "RelojFalso", "TrasFalso"]

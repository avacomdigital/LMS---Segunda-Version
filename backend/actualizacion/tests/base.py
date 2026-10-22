"""
Base común de las pruebas de integración de MOD-017: un nodo REAL (instalado por HTTP como lo hace OPS: organización, administración, un grupo, un docente, un estudiante y una
tableta), la carpeta de actualizaciones y una «memoria USB» en carpetas temporales, la llave de desarrollo, la cola única y la bitácora de verdad, los permisos por rol y los dos
middleware. Lo único falso es el reloj del nodo, que la prueba mueve.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path

from django.test import override_settings
from rest_framework.test import APIClient

from acceso.tests.base import BaseAcceso
from actualizacion.dominio import catalogos as cat
from actualizacion.dominio import version as ver
from actualizacion.infraestructura import contenedor
from actualizacion.infraestructura.registro_modulos import version_del_producto

from . import emisor

A = "/api/actualizacion"


class RelojFalso:
    def __init__(self, t: int):
        self.t = int(t)

    def ahora_ms(self) -> int:
        return self.t

    def avanzar(self, ms: int) -> None:
        self.t += int(ms)


class BaseActualizacion(BaseAcceso):
    """Un nodo real con la carpeta de actualizaciones y una memoria USB temporales. `self.t0` es el instante de la prueba."""

    def setUp(self):
        super().setUp()
        from nodo.pruebas import nodo_limpio
        self.carpeta = Path(tempfile.mkdtemp(prefix="avacom-actualizacion-prueba-"))
        self.usb = Path(tempfile.mkdtemp(prefix="avacom-usb-prueba-"))
        self.carpeta_nodo = Path(tempfile.mkdtemp(prefix="avacom-nodo-prueba-"))       # las anclas de la cola única de ESTA prueba: dos corridas a la vez no se pisan la secuencia
        self.addCleanup(shutil.rmtree, self.carpeta, True)
        self.addCleanup(shutil.rmtree, self.usb, True)
        self.addCleanup(shutil.rmtree, self.carpeta_nodo, True)
        sobre = override_settings(AVACOM_ACTUALIZACION_DIR=str(self.carpeta), AVACOM_ACTUALIZACION_UNIDADES=str(self.usb), AVACOM_NODO_DIR=str(self.carpeta_nodo))
        sobre.enable()
        self.addCleanup(sobre.disable)
        nodo_limpio()
        self.addCleanup(nodo_limpio)
        contenedor.reiniciar()
        self.addCleanup(contenedor.reiniciar)
        self.s = contenedor.servicios()
        self.reloj = RelojFalso(int(time.time() * 1000))
        self.s.reloj = self.reloj
        self.t0 = self.reloj.t
        # la versión del producto instalada la decide `installer/version.json` (que otras sesiones suben): el paquete de pruebas se arma relativo a ella
        self.version_instalada = version_del_producto()
        mayor, menor, parche = ver.analizar(self.version_instalada) or (0, 0, 0)
        self.version_nueva = f"{mayor}.{menor}.{parche + 1}"

    # ----------------------------------------------------------------------------------------------------------------------- paquetes
    def avupd(self, **cambios) -> bytes:
        cambios.setdefault("version_producto", self.version_nueva)
        cambios.setdefault("version_minima", self.version_instalada)
        return emisor.emitir(**cambios)

    def dejar_en_usb(self, datos: bytes, nombre: str = "reportes-1.4.0.avupd") -> Path:
        ruta = self.usb / nombre
        ruta.write_bytes(datos)
        return ruta

    def candidatos(self, cliente: APIClient | None = None) -> list[dict]:
        r = (cliente or self.admin).get(f"{A}/paquetes/")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["candidatos"]

    def importar(self, datos: bytes | None = None, cliente: APIClient | None = None, nombre: str = "reportes-1.4.0.avupd"):
        self.dejar_en_usb(datos if datos is not None else self.avupd(), nombre)
        candidatos = [c for c in self.candidatos(cliente) if c["nombre"] == nombre]
        self.assertEqual(len(candidatos), 1, candidatos)
        return (cliente or self.admin).post(f"{A}/paquetes/importar/", {"candidato": candidatos[0]["id"]}, format="json")

    def importar_ok(self, datos: bytes | None = None, cliente: APIClient | None = None, **kw) -> dict:
        r = self.importar(datos, cliente, **kw)
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def aplicar(self, paquete_id: str, cliente: APIClient | None = None):
        return (cliente or self.admin).post(f"{A}/paquetes/{paquete_id}/aplicar/", {}, format="json")

    def aplicar_ok(self, paquete_id: str) -> dict:
        r = self.aplicar(paquete_id)
        self.assertEqual(r.status_code, 202, r.content)
        return r.json()

    def ficha(self, paquete_id: str) -> dict:
        r = self.admin.get(f"{A}/paquetes/{paquete_id}/")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    # ----------------------------------------------------------------------------------------------------------------------- el Host (simulado) y el vigilante
    def resultado_del_host(self, orden_id: str, paquete_id: str, resultado: str = cat.R_APLICADO, accion: str = cat.ACCION_APLICAR, paso: str = cat.PASO_VERIFICAR, error: str | None = None,
                           duracion_ms: int = 95_000, migraciones: list[dict] | None = None) -> None:
        """Lo que el Host dejaría en `resultado.json` al terminar (P-06): la orden se consume y queda el resultado."""
        cuerpo = {"formato": 1, "orden_id": orden_id, "paquete_id": paquete_id, "accion": accion, "resultado": resultado, "paso": paso, "iniciado_en": self.reloj.t,
                  "terminado_en": self.reloj.t + duracion_ms, "duracion_ms": duracion_ms, "detalle": "simulado por la prueba", "respaldo": str(self.carpeta / "Respaldos" / "x") if accion == cat.ACCION_APLICAR else None,
                  "migraciones": migraciones if migraciones is not None else [{"modulo": "reporting", "nombre": "0004_parche_de_ejemplo", "ok": resultado == cat.R_APLICADO}], "error": error}
        (self.carpeta / cat.ARCHIVO_ORDEN).unlink(missing_ok=True)
        (self.carpeta / cat.ARCHIVO_RESULTADO).write_text(json.dumps(cuerpo), encoding="utf-8")

    def tick(self, origen: str = "prueba") -> dict:
        from actualizacion.aplicacion.vigilante import Tick
        return Tick(self.s).ejecutar(origen)

    def orden(self) -> dict | None:
        return self.s.almacen.leer_orden()

    # ----------------------------------------------------------------------------------------------------------------------- lo que dejó
    def eventos(self) -> list:
        from nodo import pruebas
        return list(pruebas.cola(cat.MODULO))

    def tipos_de_eventos(self, con_deteccion: bool = False) -> list[str]:
        """Los tipos publicados, en orden. Sin `actualizacion.disponible_detectada.v1` salvo que se pida: el vigilante lo publica en cualquier tick con un USB a la vista."""
        return [e.tipo_evento for e in self.eventos() if con_deteccion or e.tipo_evento != cat.EV_DISPONIBLE]

    def asientos(self) -> list:
        from audit.models import Bitacora
        return list(Bitacora.objects.filter(modulo="actualizacion").order_by("secuencia"))

    def acciones_asentadas(self) -> list[str]:
        return [a.accion for a in self.asientos()]

    def archivos_escritos(self) -> list[str]:
        """Todo lo que hay en la carpeta de actualizaciones (relativo), sin las carpetas vacías."""
        return sorted(str(p.relative_to(self.carpeta)).replace("\\", "/") for p in self.carpeta.rglob("*") if p.is_file())

    # ----------------------------------------------------------------------------------------------------------------------- personas y clases
    def crear_usuario(self, rol: str, dni: str, secreto: str, alias: str):
        r = self.admin.post("/api/acceso/usuarios/", {
            "rol": rol, "alias": alias, "persona": {"nombres": alias, "apellidos": "Prueba"},
            "identificadores": [{"tipo": "DNI", "valor": dni, "es_login": True}], "secreto": secreto, "secreto_definitivo": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"], self.sesion(dni, secreto)

    def tecnico(self) -> APIClient:
        _, cliente = self.crear_usuario("TECHNICIAN", "70.111.222", "Tecnico.2026!Aula", "Técnico AVACOM")
        return cliente

    def reportes(self) -> APIClient:
        _, cliente = self.crear_usuario("REPORTS", "60.222.333", "Reportes.2026!Aula", "Reportes")
        return cliente

    def abrir_clase(self) -> dict:
        """Una clase REAL (MOD-007), libre, del docente: lo que FUN-183 mira."""
        r = self.api.post("/api/aula/sesiones/", {"via": "libre", "profesor_id": self.docente_id}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()


__all__ = ["A", "BaseActualizacion", "RelojFalso"]

"""
Base común de las pruebas de integración de MOD-018: un nodo REAL (instalado por HTTP como lo hace OPS: organización, administración, un grupo, un docente, un estudiante y una tableta) con la
licencia en modo `firmada` y las dos únicas cosas falsas que el módulo recibe del mundo —el reloj del nodo y el hardware de «este equipo»— bajo control de la prueba.

  · RelojFalso   el reloj del nodo (`ahora_ms`) y el monótono, que la prueba mueve: `avanzar` mueve los dos (pasa el tiempo de verdad); `saltar` sólo el de pared (alguien cambió la hora).
                 Arranca en el instante REAL de la prueba: la bitácora encadenada ya trae asientos con el reloj real y es una de las anclas.
  · HuellaFalsa  los factores de hardware de «este equipo». `CRUDOS_A` es un panel con cuatro factores de unidad válidos; `CRUDOS_B`, otro equipo (el disco clonado conserva el MachineGuid).
  · Todo lo demás es de verdad: la base de datos, las anclas en una carpeta temporal, las llaves de desarrollo, la bitácora encadenada, los permisos por rol y el middleware.
"""
from __future__ import annotations

import base64
import shutil
import tempfile
import time

from django.test import override_settings
from rest_framework.test import APIClient

from acceso.tests.base import BaseAcceso
from licenciamiento.aplicacion.evaluar import Evaluar
from licenciamiento.dominio import huella as hu
from licenciamiento.dominio import licencia as lic_mod
from licenciamiento.dominio import solicitud as sol
from licenciamiento.dominio.licencia import ILIMITADO, Limites
from licenciamiento.dominio.politica import DIA_MS, HORA_MS
from licenciamiento.infraestructura import contenedor

from . import emisor

L = "/api/licencia"
CRUDOS_A = {hu.F_MACHINE_GUID: "9f1c2a3e-1111-4b2b-8c3d-aaaaaaaaaa01", hu.F_SMBIOS_UUID: "4C4C4544-0042-3510-8058-B6C04F425A32", hu.F_PLACA: "BRD-7781-ZX-2209", hu.F_CHASIS: "CH-55-0192-77"}
CRUDOS_B = {hu.F_MACHINE_GUID: "9f1c2a3e-1111-4b2b-8c3d-aaaaaaaaaa01", hu.F_SMBIOS_UUID: "5D5D5655-0099-4022-9122-C7D15F536B43", hu.F_PLACA: "BRD-9900-QA-0001", hu.F_CHASIS: "CH-77-1100-33"}


class RelojFalso:
    def __init__(self, t: int):
        self.t = int(t)
        self.mono = 5_000_000

    def ahora_ms(self) -> int:
        return self.t

    def monotono_ms(self) -> int:
        return self.mono

    def avanzar(self, ms: int) -> None:
        """Pasa el tiempo de verdad: el reloj de pared y el monótono avanzan juntos."""
        self.t += int(ms)
        self.mono += int(ms)

    def saltar(self, ms: int) -> None:
        """Alguien cambia la hora del sistema: el de pared se mueve (hacia adelante o hacia atrás) y el monótono no."""
        self.t += int(ms)


class HuellaFalsa:
    def __init__(self, crudos: dict):
        self.valores = dict(crudos)

    def crudos(self) -> dict:
        return dict(self.valores)


class ClavesFalsas:
    def __init__(self, claves: dict):
        self.claves = dict(claves)

    def publicas(self) -> dict:
        return dict(self.claves)


class BaseLicencia(BaseAcceso):
    """Un nodo real con la licencia en modo firmada. `self.t0` es el instante de la prueba; las licencias se arman relativas a él."""

    def setUp(self):
        super().setUp()
        self.carpeta = tempfile.mkdtemp(prefix="avacom-licencia-prueba-")
        self.addCleanup(shutil.rmtree, self.carpeta, True)
        sobre = override_settings(AVACOM_LICENCIA_MODO="firmada", AVACOM_LICENCIA_DIR=self.carpeta)
        sobre.enable()
        self.addCleanup(sobre.disable)
        contenedor.reiniciar()
        self.addCleanup(contenedor.reiniciar)
        self.s = contenedor.servicios()
        self.reloj = RelojFalso(int(time.time() * 1000))
        self.s.reloj = self.reloj
        self.huella = HuellaFalsa(CRUDOS_A)
        self.s.huella = self.huella
        self.t0 = self.reloj.t

    # ----------------------------------------------------------------------------------------------------------------------- evaluar
    def evaluar(self, origen: str = "accion"):
        return Evaluar(self.s).ejecutar(origen)

    def estado(self) -> dict:
        r = self.admin.get(f"{L}/estado/")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    # ----------------------------------------------------------------------------------------------------------------------- licencias
    def factores(self, crudos: dict | None = None) -> dict:
        return hu.factores_validos(crudos if crudos is not None else CRUDOS_A)

    def licencia(self, **cambios) -> lic_mod.Licencia:
        """Una licencia de producción para «este equipo» (hardware A), vigente desde hace 30 días y por un año; los `cambios` sobrescriben cualquier campo."""
        base = dict(emitida=self.t0 - 31 * DIA_MS, desde=self.t0 - 30 * DIA_MS, vence=self.t0 + 335 * DIA_MS, huella=emisor.huella_de(self.factores()),
                    limites=Limites(equipos=55, usuarios=1200, concurrentes_normal=50, concurrentes_pico=100))
        base.update(cambios)
        return emisor.licencia_de_ejemplo(**base)

    def avlic(self, **cambios) -> bytes:
        kid = cambios.pop("kid", emisor.KID_DEV_1)
        return emisor.emitir(self.licencia(**cambios), kid=kid)

    def activar(self, cliente: APIClient | None = None, via: str = "activar", **cambios):
        datos = self.avlic(**cambios)
        return (cliente or self.admin).post(f"{L}/{via}/", {"licencia": lic_mod.a_texto(datos)}, format="json")

    def activar_ok(self, via: str = "activar", **cambios) -> dict:
        r = self.activar(via=via, **cambios)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    # ----------------------------------------------------------------------------------------------------------------------- personas
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

    # ----------------------------------------------------------------------------------------------------------------------- archivos
    @staticmethod
    def bytes_de(texto_b64: str) -> bytes:
        return base64.b64decode(texto_b64)

    def solicitud_del_nodo(self, cliente: APIClient | None = None) -> sol.Solicitud:
        r = (cliente or self.admin).post(f"{L}/solicitud/", {}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return sol.leer_solicitud(self.bytes_de(r.json()["archivo_b64"]))


__all__ = ["BaseLicencia", "CRUDOS_A", "CRUDOS_B", "ClavesFalsas", "DIA_MS", "HORA_MS", "HuellaFalsa", "ILIMITADO", "L", "Limites", "RelojFalso"]

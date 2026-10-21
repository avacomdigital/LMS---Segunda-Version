"""
Base común de las pruebas de MOD-015: una carpeta de anclas TEMPORAL por prueba (jamás ProgramData), el composition root reiniciado (el estado vivo incluido), el reloj del nodo que la
prueba mueve a voluntad (el mismo `RelojNodo` de la evaluación que mueven las demás suites) y atajos para publicar dentro de una transacción, como hace cualquier hecho.

`BaseNodoConRoles` añade el nodo instalado de `BaseAcceso` (administrador, docente, alumno con sesión de verdad) y un técnico, para probar la API por rol.
"""
from __future__ import annotations

import shutil
import tempfile
from unittest import mock

from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from acceso.tests.base import BaseAcceso
from evaluacion.infraestructura.contenedor import RelojNodo

from .. import models as m
from .. import servicios
from ..dominio import catalogos as cat
from ..infraestructura import contenedor

T0 = 1_790_000_000_000          # 2026-09-21: el origen del reloj de las pruebas (el mismo de la evaluación)
SEG, MIN, HORA, DIA = 1_000, 60_000, 3_600_000, 86_400_000
TIPO = "evaluacion.intento_abierto.v1"


class _Nodo:
    """Lo que comparten las dos bases: carpeta temporal, contenedor limpio, reloj inyectado y atajos."""

    def _preparar_nodo(self) -> None:
        self.carpeta = tempfile.mkdtemp(prefix="avacom-nodo-pruebas-")
        self.addCleanup(shutil.rmtree, self.carpeta, ignore_errors=True)
        sobre = override_settings(AVACOM_NODO_DIR=self.carpeta, AVACOM_NODO_ESTRICTO=True, AVACOM_NODO_EVENTOS_TECNICOS=True, AVACOM_NODO_PURGA=False)
        sobre.enable()
        self.addCleanup(sobre.disable)
        contenedor.reiniciar()
        self.addCleanup(contenedor.reiniciar)
        if not hasattr(self, "t"):
            self.t = T0
            parche = mock.patch.object(RelojNodo, "ahora_ms", side_effect=lambda: self.t)
            parche.start()
            self.addCleanup(parche.stop)

    # ------------------------------------------------------------------------------------------ reloj
    def avanzar(self, ms: int = 0, seg: int = 0, minutos: int = 0, horas: int = 0, dias: int = 0) -> int:
        self.t += ms + seg * SEG + minutos * MIN + horas * HORA + dias * DIA
        return self.t

    # ------------------------------------------------------------------------------------------ atajos
    @property
    def s(self):
        return contenedor.servicios()

    def publicar(self, tipo: str = TIPO, modulo: str | None = None, agregado: tuple[str, str] = ("Intento", "i-1"), carga: dict | None = None, **extra) -> dict:
        """Un hecho con su evento: dentro de una transacción, como cualquier caso de uso."""
        from ..dominio import catalogo
        modulo = modulo or (catalogo.resolver(tipo).modulo if catalogo.resolver(tipo) else "evaluacion")
        with transaction.atomic():
            return servicios.publicar(modulo, agregado[0], agregado[1], tipo, carga if carga is not None else {"intento_id": agregado[1], "instante": self.t}, **extra)

    def publicar_varios(self, n: int, tipo: str = TIPO, **extra) -> list[dict]:
        return [self.publicar(tipo, agregado=("Intento", f"i-{i}"), **extra) for i in range(n)]

    @staticmethod
    def eventos(modulo: str | None = None, tipo: str | None = None) -> list[m.Evento]:
        filas = m.Evento.objects.order_by("secuencia")
        if modulo:
            filas = filas.filter(modulo=modulo)
        if tipo:
            filas = filas.filter(tipo=tipo)
        return list(filas)

    @staticmethod
    def asientos(accion: str) -> list:
        from audit.models import Bitacora
        return list(Bitacora.objects.filter(accion=accion).order_by("secuencia"))

    def consumidor_de_prueba(self, nombre: str = "prueba", fuente: str = "evaluacion", tipos: tuple[str, ...] = (), falla_en: set[int] | None = None, **extra) -> "ConsumidorFalso":
        falso = ConsumidorFalso(falla_en or set())
        servicios.registrar_consumidor(nombre, "pruebas", (fuente,), tipos, aplicar=falso.aplicar, **extra)
        falso.nombre, falso.fuente = nombre, fuente
        return falso


class ConsumidorFalso:
    """Un consumidor idempotente (BR-008): recuerda los `evento_id` aplicados y descarta los repetidos; falla en las secuencias que se le digan (para probar reintentos y problemas)."""

    def __init__(self, falla_en: set[int]):
        self.falla_en = set(falla_en)
        self.aplicados: list[int] = []
        self.vistos: set[str] = set()
        self.cargas: list[dict] = []
        self.nombre = self.fuente = ""

    def aplicar(self, evento: dict) -> None:
        if int(evento["secuencia"]) in self.falla_en:
            raise RuntimeError(f"no puedo con la {evento['secuencia']} (prueba)")
        if evento["evento_id"] in self.vistos:
            return
        self.vistos.add(evento["evento_id"])
        self.aplicados.append(int(evento["secuencia"]))
        self.cargas.append(evento.get("carga") or {})

    def lote(self, **extra) -> dict:
        return servicios.aplicar_lote(self.nombre, self.fuente, **extra)

    def hasta_vaciar(self, **extra) -> dict:
        return servicios.aplicar_hasta_vaciar(self.nombre, self.fuente, **extra)


class BaseNodo(_Nodo, TestCase):
    def setUp(self):
        super().setUp()
        self._preparar_nodo()


class BaseNodoTransaccional(_Nodo, TransactionTestCase):
    """Sin la transacción que `TestCase` abre alrededor de cada prueba: para lo que necesita ver `in_atomic_block` de verdad."""

    # El vaciado entre `TransactionTestCase` borra las filas pero no el AUTOINCREMENT: desde la Fase 3 otras suites transaccionales (el WebSocket del aula) publican en `m15_evento`
    # antes que éstas, y una prueba que espera «la secuencia 1» recibía la 100. Con esto Django reinicia `sqlite_sequence` antes de cada una.
    reset_sequences = True

    def setUp(self):
        super().setUp()
        self._preparar_nodo()


class BaseNodoConRoles(_Nodo, BaseAcceso):
    """El nodo instalado (administrador, docente y alumno con sesión) más un técnico, para probar `/api/nodo/` por rol."""

    TECNICO_DNI, TECNICO_PASS = "70.111.222", "Tecnico.2026!Aula"

    def setUp(self):
        super().setUp()
        self._preparar_nodo()
        r = self.admin.post("/api/acceso/usuarios/", {
            "rol": "TECHNICIAN", "alias": "Técnico AVACOM", "persona": {"nombres": "Técnico", "apellidos": "AVACOM"},
            "identificadores": [{"tipo": "DNI", "valor": self.TECNICO_DNI, "es_login": True}], "secreto": self.TECNICO_PASS, "secreto_definitivo": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.tecnico_id = r.json()["id"]
        self.tecnico = self.sesion(self.TECNICO_DNI, self.TECNICO_PASS)

    def alumno(self) -> APIClient:
        return self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.TABLETA)

    def escalar(self, usuario_id: str, permiso: str = cat.P_REPLAY, horas: int = 2) -> dict:
        """La administración concede una escalada temporal (PAN-241, `identity.escalation.grant`). El módulo de acceso fecha con el reloj real: la vigencia también."""
        import time
        r = self.admin.post(f"/api/acceso/usuarios/{usuario_id}/escaladas/", {"permiso": permiso, "alcance": "ORGANIZATION", "motivo": "reproceso de la cola (prueba)",
                                                                              "vigente_hasta": int(time.time() * 1000) + horas * HORA}, format="json")
        self.assertIn(r.status_code, (200, 201), r.content)
        return r.json()

    def nd(self, ruta: str, cliente: APIClient | None = None, esperado: int = 200, **params) -> dict:
        r = (cliente or self.admin).get(f"/api/nodo{ruta}", params)
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json() if r.content else {}

    def nd_post(self, ruta: str, cuerpo: dict | None = None, cliente: APIClient | None = None, esperado: int = 200) -> dict:
        r = (cliente or self.admin).post(f"/api/nodo{ruta}", cuerpo or {}, format="json")
        self.assertEqual(r.status_code, esperado, r.content)
        return r.json() if r.content else {}

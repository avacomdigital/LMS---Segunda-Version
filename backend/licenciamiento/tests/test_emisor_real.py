"""
INTEROPERABILIDAD emisor ↔ nodo (MOD-018): lo que firma la herramienta de `tools/licencias/` lo activa, lo renueva y lo traslada el nodo REAL (por su API, con su middleware, su historial y su
estado), con el reloj y el hardware de «este equipo» bajo control de la prueba. Es la prueba de que las dos mitades —la que firma y la que verifica— hablan el mismo idioma: si alguna cambia un
campo, una etiqueta o un margen de fechas, aquí se nota antes de que un colegio reciba un archivo que su equipo no acepta.

Reglas de esta prueba:
  · Se salta sola si `tools/licencias` no está en el árbol (el instalador no copia ni `tests/` ni `tools/`) o si la herramienta no se puede importar aquí (le falta `cryptography`).
  · No usa ninguna llave del repositorio, ni la de desarrollo del nodo ni una de producción: la herramienta crea la suya (`claves generar`) en una carpeta temporal y muere con ella. El nodo la
    acepta porque la prueba se la entrega como llave pública (`ClavesFalsas`), igual que haría `produccion.json`.
  · Todo lo que escribe (llaves, registro de emisiones, archivos entregados) va a carpetas temporales que se borran al terminar. Nada toca el repositorio ni `tools/licencias/datos/`.
  · Los días de vigencia se calculan con el reloj de la prueba (nunca una fecha fija: una fecha fija caduca y la prueba se rompe sin que nada haya cambiado).
"""
from __future__ import annotations

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from django.test import override_settings


def _herramienta() -> Path | None:
    """La carpeta `tools/licencias` del primer ancestro que la trae, o `None` si este árbol no la tiene."""
    for carpeta in Path(__file__).resolve().parents:
        candidata = carpeta / "tools" / "licencias"
        if (candidata / "avacom_licencias").is_dir():
            return candidata
    return None


_HERRAMIENTA = _herramienta()
if _HERRAMIENTA is None:
    raise unittest.SkipTest("tools/licencias no está en este árbol: la prueba de interoperabilidad con el emisor corre sólo en el repositorio.")
if str(_HERRAMIENTA) not in sys.path:
    sys.path.insert(0, str(_HERRAMIENTA))
try:
    from avacom_licencias import cli, llaves
except ImportError as fallo:                         # `cryptography` u otra dependencia de la herramienta que este Python no tiene
    raise unittest.SkipTest(f"la herramienta de emisión no se puede importar aquí: {fallo}") from fallo

from licenciamiento.dominio import licencia as lic_mod  # noqa: E402
from licenciamiento.infraestructura import contenedor  # noqa: E402

from .base import CRUDOS_B, DIA_MS, HORA_MS, L, BaseLicencia, ClavesFalsas, HuellaFalsa  # noqa: E402

FRASE = "una frase de paso larga solo para esta prueba"
KID = "integracion-1"


class HerramientaDeEmision:
    """La herramienta tal como la usa el personal de AVACOM, con el reloj del emisor y la frase de paso bajo control de la prueba."""

    def __init__(self, carpeta: Path, reloj_ms):
        self.dir, self.reloj_ms = carpeta, reloj_ms
        self.registro = carpeta / "registro.jsonl"
        self.privada, self.publica = carpeta / "llaves" / f"{KID}.avkey", carpeta / "llaves" / f"{KID}.pub"
        codigo, _, error = self.correr(["claves", "generar", "--kid", KID, "--salida", str(carpeta / "llaves")])
        assert codigo == 0, error
        self.kid, self.clave_publica = llaves.leer_publica(self.publica.read_text(encoding="utf-8"))
        self._n = 0

    def correr(self, argv: list[str]) -> tuple[int, str, str]:
        salida, error = io.StringIO(), io.StringIO()
        with mock.patch.object(cli, "_leer_frase", lambda pregunta="": FRASE), mock.patch.object(cli, "_ahora_ms", self.reloj_ms), \
                contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
            try:
                codigo = cli.main(argv)
            except SystemExit as fin:
                codigo = int(fin.code or 0)
        return codigo, salida.getvalue(), error.getvalue()

    def hasta(self, dias: int) -> str:
        """El último día de vigencia (AAAA-MM-DD, UTC) a `dias` días del reloj del emisor."""
        return (datetime.fromtimestamp(self.reloj_ms() / 1000, tz=timezone.utc) + timedelta(days=dias)).date().isoformat()

    def emitir(self, avreq: bytes, *extra: str, dias: int | None = 420) -> bytes:
        """Emite el `.avlic` para esa solicitud. `dias=None` deja que mande el plan (por ejemplo «evaluacion»)."""
        self._n += 1
        entrada = self.dir / f"sol-{self._n}.avreq"
        entrada.write_bytes(avreq)
        salida = self.dir / f"salida-{self._n}"
        argv = ["emitir", "--solicitud", str(entrada), "--privada", str(self.privada), "--registro", str(self.registro), "--salida", str(salida), "--yo-confirmo"]
        if dias is not None:
            argv += ["--hasta", self.hasta(dias)]
        codigo, texto, error = self.correr(argv + list(extra))
        if codigo != 0:
            raise AssertionError(f"la herramienta no emitió (código {codigo}): {error or texto}")
        return next(salida.glob("*.avlic")).read_bytes()


class BaseConHerramienta(BaseLicencia):
    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp(prefix="avacom-emisor-real-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.herr = HerramientaDeEmision(self.tmp, lambda: self.reloj.t)
        self.s.claves = ClavesFalsas({self.herr.kid: self.herr.clave_publica})

    def pedir(self, cliente=None) -> bytes:
        r = (cliente or self.admin).post(f"{L}/solicitud/", {}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return self.bytes_de(r.json()["archivo_b64"])

    def instalar(self, avlic: bytes, via: str = "activar", cliente=None):
        return (cliente or self.admin).post(f"{L}/{via}/", {"licencia": lic_mod.a_texto(avlic)}, format="json")

    @contextlib.contextmanager
    def equipo_nuevo(self):
        """«El equipo nuevo»: otra carpeta de estado y otro hardware (B). La base de datos es la misma, que es lo que ocurre cuando el técnico restaura la copia del equipo viejo (JRN-020)."""
        carpeta = tempfile.mkdtemp(prefix="avacom-equipo-nuevo-")
        self.addCleanup(shutil.rmtree, carpeta, True)
        with override_settings(AVACOM_LICENCIA_MODO="firmada", AVACOM_LICENCIA_DIR=carpeta):
            contenedor.reiniciar()
            nuevo = contenedor.servicios()
            nuevo.reloj, nuevo.huella, nuevo.claves = self.reloj, HuellaFalsa(CRUDOS_B), ClavesFalsas({self.herr.kid: self.herr.clave_publica})
            self.s = nuevo
            yield nuevo


class ActivarLoQueEmiteLaHerramientaTests(BaseConHerramienta):
    def test_licencia_nueva_de_punta_a_punta(self):
        avlic = self.herr.emitir(self.pedir(), "--aula", "Colegio San Martín")
        r = self.instalar(avlic)
        self.assertEqual(r.status_code, 200, r.content)
        e = r.json()
        self.assertEqual((e["accion"], e["estado"], e["motivo"]), ("activada", "activa", "vigente"))
        self.assertEqual(e["licencia"]["serie"], 1)
        self.assertEqual(e["limites"], {"equipos": 60, "usuarios": 1200, "concurrentes_normal": 50, "concurrentes_pico": 100})       # el tamaño máximo de un aula (Q-L1)
        self.assertEqual(e["licencia"]["gracia_dias"], 30)                                                                             # la gracia exacta (Q-L16)
        self.assertEqual(sorted(e["capacidades"]["habilitadas"]), ["administracion_avanzada", "busqueda", "importacion", "reportes"])
        self.assertTrue(e["huella"]["coincide"] and not e["huella"]["parcial"])
        self.assertEqual(e["tipo"], "produccion")
        self.assertGreater(e["vigencia"]["dias_restantes"], 400)

    def test_la_herramienta_y_el_nodo_leen_lo_mismo(self):
        avlic = self.herr.emitir(self.pedir())
        self.assertEqual(self.instalar(avlic).status_code, 200)
        copia = self.admin.get(f"{L}/copia/")
        self.assertEqual(copia.status_code, 200)
        self.assertEqual(self.bytes_de(copia.json()["archivo_b64"]), avlic)

    def test_una_licencia_sin_la_llave_publica_del_nodo_no_se_acepta(self):
        avlic = self.herr.emitir(self.pedir())
        self.s.claves = ClavesFalsas({})
        r = self.instalar(avlic)
        self.assertEqual((r.status_code, r.json()["motivo"]), (400, "kid_desconocido"))

    def test_el_plan_de_evaluacion_sale_como_evaluacion(self):
        e = self.instalar(self.herr.emitir(self.pedir(), "--plan", "evaluacion", dias=None)).json()
        self.assertEqual(e["tipo"], "evaluacion")
        self.assertEqual(e["limites"]["equipos"], 20)

    def test_limites_y_modulos_a_mano_llegan_tal_cual(self):
        e = self.instalar(self.herr.emitir(self.pedir(), "--equipos", "7", "--usuarios", "40", "--normal", "5", "--pico", "6", "--capacidades", "reportes")).json()
        self.assertEqual(e["limites"], {"equipos": 7, "usuarios": 40, "concurrentes_normal": 5, "concurrentes_pico": 6})
        self.assertEqual(e["capacidades"]["habilitadas"], ["reportes"])
        self.assertEqual(sorted(e["capacidades"]["no_disponibles"]), ["administracion_avanzada", "busqueda", "importacion"])
        busqueda = self.admin.get("/api/search/?q=algo")
        self.assertEqual((busqueda.status_code, busqueda.json()["codigo"]), (402, "no_disponible_por_licencia"))


class RenovarYTrasladarTests(BaseConHerramienta):
    def test_renovar_con_la_serie_siguiente(self):
        self.assertEqual(self.instalar(self.herr.emitir(self.pedir())).status_code, 200)
        self.reloj.avanzar(10 * DIA_MS)
        r = self.instalar(self.herr.emitir(self.pedir(), dias=800), via="renovar")
        self.assertEqual(r.status_code, 200, r.content)
        e = r.json()
        self.assertEqual((e["accion"], e["licencia"]["serie"], e["estado"]), ("renovada", 2, "activa"))

    def test_el_tecnico_no_renueva_ni_por_la_puerta_de_activar(self):
        """La misma huella con la serie siguiente es una renovación (`license.renew`, sólo la administración), vengan los bytes por «activar» o por «renovar»."""
        self.assertEqual(self.instalar(self.herr.emitir(self.pedir())).status_code, 200)
        self.reloj.avanzar(10 * DIA_MS)
        renovacion = self.herr.emitir(self.pedir(), dias=800)
        tecnico = self.tecnico()
        for via in ("activar", "renovar"):
            self.assertEqual(self.instalar(renovacion, via=via, cliente=tecnico).status_code, 403, via)
        self.assertEqual(self.estado()["licencia"]["serie"], 1)

    def test_el_traslado_a_otro_equipo_con_la_liberacion_del_viejo(self):
        """JRN-020 caso A: el equipo viejo libera, el nuevo pide, la herramienta emite la definitiva con --reemplaza y la activa quien instala (aquí, el técnico)."""
        self.assertEqual(self.instalar(self.herr.emitir(self.pedir())).status_code, 200)
        primera = self.estado()["licencia"]
        liberacion = self.admin.post(f"{L}/liberar/", {}, format="json")
        self.assertEqual(liberacion.status_code, 201, liberacion.content)
        avrel_ruta = self.tmp / "viejo.avrel"
        avrel_ruta.write_bytes(self.bytes_de(liberacion.json()["archivo_b64"]))

        with self.equipo_nuevo():
            avlic = self.herr.emitir(self.pedir(), "--reemplaza", str(avrel_ruta))
            r = self.instalar(avlic, cliente=self.tecnico())
            self.assertEqual(r.status_code, 200, r.content)
            e = r.json()
            self.assertEqual((e["estado"], e["licencia"]["serie"]), ("activa", 2))
            self.assertEqual(e["licencia"]["id"], primera["id"])

    def test_si_el_equipo_viejo_no_enciende_sale_con_liberacion_pendiente(self):
        """JRN-020 caso B: el equipo nuevo restauró la base del viejo, así que la licencia anterior sigue en el historial y la nueva se activa como renovación de la misma licencia."""
        self.assertEqual(self.instalar(self.herr.emitir(self.pedir())).status_code, 200)
        id_anterior = self.estado()["licencia"]["id"]
        with self.equipo_nuevo():
            avlic = self.herr.emitir(self.pedir(), "--licencia", id_anterior, "--liberacion-pendiente", "45")
            r = self.instalar(avlic, via="renovar")
            self.assertEqual(r.status_code, 200, r.content)
            e = r.json()
            self.assertEqual((e["estado"], e["motivo"]), ("liberacion_pendiente", "liberacion_pendiente"))
            self.assertEqual(e["vigencia"]["dias_restantes"], 45)

    def test_el_tecnico_traslada_la_licencia_al_equipo_que_restauro_la_base(self):
        """D-10: la misma licencia, la serie siguiente y OTRA huella es un traslado —lo activa el técnico (`license.activate`) por «activar»—, no una renovación."""
        self.assertEqual(self.instalar(self.herr.emitir(self.pedir())).status_code, 200)
        id_anterior = self.estado()["licencia"]["id"]
        with self.equipo_nuevo():
            avlic = self.herr.emitir(self.pedir(), "--licencia", id_anterior, "--liberacion-pendiente", "45")
            r = self.instalar(avlic, cliente=self.tecnico())
            self.assertEqual(r.status_code, 200, r.content)
            e = r.json()
            self.assertEqual((e["accion"], e["licencia"]["serie"], e["licencia"]["id"]), ("activada", 2, id_anterior))
            self.assertEqual(e["estado"], "liberacion_pendiente")


class RelojDelColegioTests(BaseConHerramienta):
    """El emisor fecha `desde` en el día anterior (a las 00:00 UTC) y el nodo tolera un día de adelanto (D-8): un reloj atrasado hasta ~45 horas activa SIEMPRE, sea la hora que sea."""

    def test_un_reloj_atrasado_30_horas_activa_sin_problema(self):
        avlic = self.herr.emitir(self.pedir())
        self.reloj.avanzar(-30 * HORA_MS)
        e = self.instalar(avlic).json()
        self.assertEqual(e["estado"], "activa", e)

    def test_un_reloj_atrasado_45_horas_activa_sin_degradar(self):
        """BUG-1: entre el margen del emisor (24 a 48 horas antes de emitir) y la tolerancia del nodo (un día) no queda ventana en la que se acepte y se degrade acto seguido."""
        avlic = self.herr.emitir(self.pedir())
        self.reloj.avanzar(-45 * HORA_MS)
        r = self.instalar(avlic)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["estado"], "activa", r.json())
        self.assertEqual(self.estado()["estado"], "activa")

    def test_un_reloj_atrasado_72_horas_se_rechaza_con_claridad(self):
        """Más allá de la tolerancia el nodo no instala (el archivo reemplazaría a la licencia vigente y dejaría al equipo sin ella hasta ese día): dice por qué y no cambia nada."""
        avlic = self.herr.emitir(self.pedir())
        self.reloj.avanzar(-72 * HORA_MS)
        r = self.instalar(avlic)
        self.assertEqual((r.status_code, r.json()["motivo"]), (400, "aun_no_vigente"))
        self.assertIsNone(self.estado()["licencia"])

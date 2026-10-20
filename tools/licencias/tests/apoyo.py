"""
Apoyo de las pruebas del emisor: un «nodo» de mentira que genera solicitudes y liberaciones con el dominio REAL del nodo, un reloj fijo, y una forma de correr la línea de comandos
capturando lo que escribe. No usa las llaves de desarrollo del nodo (`licenciamiento.tests`): cada prueba genera las suyas.
"""
from __future__ import annotations

import calendar
import contextlib
import io
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from avacom_licencias import cli, llaves
from avacom_licencias.dominio_nodo import firma, huella, licencia, solicitud

AHORA = calendar.timegm((2026, 10, 20, 15, 0, 0)) * 1000        # 2026-10-20 15:00 UTC
DIA_MS = 86_400_000
FRASE = "una frase de paso larga y sin usar"

VALORES = {
    huella.F_MACHINE_GUID: "9f1c2a3e-1111-4b2b-8c3d-aaaaaaaaaa01",
    huella.F_SMBIOS_UUID: "4C4C4544-0042-3510-8058-B6C04F425A32",
    huella.F_PLACA: "BRD-7781-ZX-2209",
    huella.F_CHASIS: "CH-55-0192-77",
    huella.F_PROCESADOR: "BFEBFBFF000906EA",
}


def huella_de(valores: dict | None = None, secreto: bytes | None = None):
    """`(nivel, HuellaDeLicencia)` como la que un nodo declararía en su solicitud (el `k` lo decide el dominio del nodo)."""
    validos = huella.factores_validos(valores if valores is not None else VALORES)
    nivel, k_efectivo, factores = huella.huella_de_solicitud(validos, secreto or os.urandom(32))
    return nivel, licencia.HuellaDeLicencia(k_efectivo, tuple(sorted(factores.items())))


class NodoDePrueba:
    """Un nodo con su llave propia: pide licencias y las libera."""

    def __init__(self, valores: dict | None = None):
        self.privada, self.publica = firma.par_nuevo()
        self.valores = valores

    def solicitud(self, *, creada: int = AHORA - 1000, licencia_vigente: str | None = None, aula: str = "Colegio de pruebas", nonce: bytes | None = None,
                  valores: dict | None = None) -> bytes:
        nivel, h = huella_de(valores if valores is not None else self.valores)
        return solicitud.construir_solicitud(self.privada, nonce=nonce or os.urandom(16), version_nodo="2.8.5", creada=creada, nivel=nivel, huella=h,
                                             licencia_vigente=licencia_vigente, aula=aula)

    def liberacion(self, licencia_id: str, serie: int, liberada: int = AHORA - 500) -> bytes:
        return solicitud.construir_liberacion(self.privada, licencia_id=licencia_id, serie=serie, liberada=liberada, nonce=os.urandom(16))


class Salida:
    def __init__(self, codigo: int, salida: str, error: str):
        self.codigo, self.salida, self.error = codigo, salida, error


def correr(argv: list[str], *, entradas: list[str] | None = None, frase: str = FRASE, ahora: int = AHORA) -> Salida:
    """Corre `cli.main(argv)` con el reloj fijo, la frase de paso dada y las respuestas dadas a las preguntas; devuelve el código y lo que escribió."""
    cola = list(entradas or [])

    def leer(pregunta: str = "") -> str:
        if not cola:
            raise EOFError("la prueba no previó esta pregunta: " + pregunta)
        return cola.pop(0)

    salida, error = io.StringIO(), io.StringIO()
    with mock.patch.object(cli, "_leer", leer), mock.patch.object(cli, "_leer_frase", lambda pregunta="": frase), mock.patch.object(cli, "_ahora_ms", lambda: ahora), \
            mock.patch.dict(os.environ, {}, clear=False), contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        os.environ.pop(cli.VARIABLE_FRASE, None)
        try:
            codigo = cli.main(argv)
        except SystemExit as fin:
            codigo = int(fin.code or 0)
    return Salida(codigo, salida.getvalue(), error.getvalue())


class BaseConCarpeta(unittest.TestCase):
    """Una carpeta temporal por prueba, con una llave de emisión ya creada y un nodo de prueba."""

    kid = "prueba-2026-1"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.llaves_dir = self.dir / "llaves"
        r = correr(["claves", "generar", "--kid", self.kid, "--salida", str(self.llaves_dir)])
        self.assertEqual(r.codigo, 0, r.error)
        self.privada = self.llaves_dir / f"{self.kid}.avkey"
        self.publica = self.llaves_dir / f"{self.kid}.pub"
        self.kid_leido, self.publica_bytes = llaves.leer_publica(self.publica.read_text(encoding="utf-8"))
        self.registro = self.dir / "registro.jsonl"
        self.salida = self.dir / "salida"
        self.nodo = NodoDePrueba()

    def guardar(self, nombre: str, datos: bytes) -> Path:
        ruta = self.dir / nombre
        ruta.write_bytes(datos)
        return ruta

    def emitir(self, ruta_solicitud: Path, *extra: str, entradas: list[str] | None = None, frase: str = FRASE, ahora: int = AHORA, hasta: str | None = "2027-10-31") -> Salida:
        argv = ["emitir", "--solicitud", str(ruta_solicitud), "--privada", str(self.privada), "--registro", str(self.registro), "--salida", str(self.salida),
                "--aula", "Colegio San Martín"] + (["--hasta", hasta] if hasta else []) + list(extra)
        if entradas is None and "--yo-confirmo" not in argv:
            argv.append("--yo-confirmo")
        return correr(argv, entradas=entradas, frase=frase, ahora=ahora)

    def licencias(self) -> list[Path]:
        return sorted(self.salida.glob("*.avlic")) if self.salida.is_dir() else []

    def leer(self, ruta: Path) -> licencia.Licencia:
        return licencia.leer(ruta.read_bytes(), {self.kid: self.publica_bytes})


def nuevo_uuid() -> str:
    return str(uuid.uuid4())

"""
Adaptadores de la identidad de dispositivo (Fase 5): los retos en memoria, los datos de atestación que viajan en el paquete y la frontera con `device_manager`.

  · `RetosEnMemoria`   un reto por activación, de un solo uso, con vencimiento corto y un tope de pendientes (un cliente que pide miles de retos no llena la memoria). Se pierden al reiniciar.
  · `AtestacionEmpaquetada`  lee `atestacion/raices_google.json` (raíces PÚBLICAS), `revocadas.json` (lista de Google al día de la compilación) y `app.json` (paquete y firmas de la app).
                             Todo se lee una vez y se guarda; si un archivo falta o está dañado, la atestación NO puede dar `hardware` (cae a `software`): jamás se frena a un equipo.
  · `EquiposDeDispositivos`  el servicio público de `device_manager`: licenciamiento no escribe `m09_*` (R-08).
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from ..dominio import atestacion as at
from ..dominio import errores

log = logging.getLogger("avacom.licenciamiento")

CARPETA = Path(__file__).resolve().parent.parent / "atestacion"
VIDA_DEL_RETO_MS = 5 * 60_000
MAX_PENDIENTES = 2000


class RetosEnMemoria:
    def __init__(self, vida_ms: int = VIDA_DEL_RETO_MS, maximo: int = MAX_PENDIENTES):
        self._vida, self._maximo = vida_ms, maximo
        self._pendientes: dict[bytes, int] = {}
        self._candado = threading.Lock()

    def entregar(self, ahora_ms: int) -> tuple[bytes, int]:
        nonce = secrets.token_bytes(32)
        vence = ahora_ms + self._vida
        with self._candado:
            self._limpiar(ahora_ms)
            if len(self._pendientes) >= self._maximo:                          # el más viejo sale: un cliente que pide sin parar sólo se tira sus propios retos
                self._pendientes.pop(min(self._pendientes, key=self._pendientes.get))
            self._pendientes[nonce] = vence
        return nonce, vence

    def consumir(self, nonce: bytes, ahora_ms: int) -> bool:
        with self._candado:
            vence = self._pendientes.pop(bytes(nonce), None)                   # `pop`: sale al usarse, tenga éxito o no lo que sigue
            return vence is not None and ahora_ms <= vence

    def _limpiar(self, ahora_ms: int) -> None:
        for nonce in [n for n, v in self._pendientes.items() if v < ahora_ms]:
            del self._pendientes[nonce]

    def pendientes(self) -> int:
        with self._candado:
            return len(self._pendientes)


def _ms(texto: str) -> int:
    return int(datetime.strptime(texto, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


class AtestacionEmpaquetada:
    def __init__(self, carpeta: Path = CARPETA, firmas_extra: str | None = None):
        self._carpeta = Path(carpeta)
        self._extra = os.environ.get("AVACOM_LICENCIA_APP_FIRMAS", "") if firmas_extra is None else firmas_extra
        self._raices: list[at.Raiz] | None = None
        self._revocadas: frozenset[str] | None = None
        self._app: at.PoliticaDeApp | None = None

    def _json(self, nombre: str) -> dict:
        try:
            datos = json.loads((self._carpeta / nombre).read_text(encoding="utf-8-sig"))
            return datos if isinstance(datos, dict) else {}
        except (OSError, ValueError):
            log.exception("No se pudo leer %s: la atestación de Android no podrá dar nivel hardware", nombre, extra={"evento": "licencia.atestacion_datos", "ruta": "bad"})
            return {}

    def raices(self) -> list[at.Raiz]:
        if self._raices is None:
            salida: list[at.Raiz] = []
            for entrada in self._json("raices_google.json").get("raices", []):
                try:
                    c = x509.load_pem_x509_certificate(str(entrada["pem"]).encode("ascii"))
                    spki = c.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
                    salida.append(at.Raiz(str(entrada.get("nombre", "")), spki, _ms(entrada["valida_desde"]), _ms(entrada["valida_hasta"]) + 86_400_000 - 1))
                except (KeyError, ValueError, TypeError):
                    continue
            self._raices = salida
        return list(self._raices)

    def revocadas(self) -> frozenset[str]:
        if self._revocadas is None:
            self._revocadas = frozenset(str(s).lower() for s in self._json("revocadas.json").get("seriales", []))
        return self._revocadas

    def app(self) -> at.PoliticaDeApp:
        if self._app is None:
            datos = self._json("app.json")
            firmas = {bytes.fromhex(e["sha256"]) for e in datos.get("firmas_sha256", []) if isinstance(e, dict) and len(str(e.get("sha256", ""))) == 64}
            for texto in self._extra.split(","):
                texto = texto.strip().replace(":", "").lower()
                if len(texto) == 64:
                    try:
                        firmas.add(bytes.fromhex(texto))
                    except ValueError:
                        continue
            self._app = at.PoliticaDeApp(frozenset(str(p) for p in datos.get("paquetes", [])), frozenset(firmas))
        return self._app


class EquiposDeDispositivos:
    """La frontera con `device_manager`: sus errores se traducen a los de este módulo."""

    def registrar(self, identificador_hw: str, clave_publica: str, clave_huella: str, garantia: str | None, detalle: dict, momento: int, actor: str) -> dict:
        from device_manager import servicios as dispositivos
        from device_manager.dominio import errores as e
        try:
            return dispositivos.registrar_identidad(identificador_hw, clave_publica, clave_huella, garantia, detalle, momento, actor)
        except e.NoEncontrado as error:
            raise errores.NoEncontrado(error.detalle, codigo_interno="dispositivo_no_registrado") from error
        except e.ClaveDistinta as error:
            raise errores.ClaveDistinta(error.detalle) from error
        except e.ClaveEnUso as error:
            raise errores.ClaveEnUso(error.detalle) from error
        except e.NodoNoInstalado as error:
            raise errores.Conflicto(error.detalle) from error

    def de(self, identificador_hw: str) -> dict | None:
        from device_manager import servicios as dispositivos
        return dispositivos.identidad_de(identificador_hw)

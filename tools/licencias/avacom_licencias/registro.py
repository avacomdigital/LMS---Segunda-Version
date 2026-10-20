"""
El registro de emisiones: un archivo `registro-emisiones.jsonl` de SÓLO AÑADIR. Cada renglón lleva el hash del anterior, así que alterar, quitar o reordenar uno rompe la cadena (la
misma idea de la bitácora del nodo). Sirve para saber qué serie toca, para no emitir dos veces sobre la misma solicitud y para la conciliación mensual.

Nunca lleva claves, frases de paso ni huellas del equipo: ids, serie, fechas, límites, módulos y los SHA-256 de los archivos.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

GENESIS = "0" * 64


class RegistroAlterado(RuntimeError):
    """La cadena del registro no cuadra. Quien opera debe avisar al CTO: no se sigue escribiendo sobre un registro dudoso."""


def _canonico(cuerpo: dict) -> str:
    return json.dumps(cuerpo, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(previo: str, cuerpo: dict) -> str:
    return hashlib.sha256((previo + "\n" + _canonico(cuerpo)).encode("utf-8")).hexdigest()


class Registro:
    def __init__(self, ruta: Path | str):
        self.ruta = Path(ruta)

    def _renglones(self) -> list[dict]:
        if not self.ruta.is_file():
            return []
        salida = []
        with self.ruta.open("r", encoding="utf-8") as archivo:
            for numero, linea in enumerate(archivo, start=1):
                if not linea.strip():
                    continue
                try:
                    salida.append(json.loads(linea))
                except ValueError as error:
                    raise RegistroAlterado(f"El renglón {numero} del registro está ilegible.") from error
        return salida

    def verificar(self) -> tuple[bool, str, int]:
        """`(¿íntegro?, mensaje, cuántos renglones)`."""
        try:
            renglones = self._renglones()
        except RegistroAlterado as error:
            return False, str(error), 0
        previo = GENESIS
        for posicion, renglon in enumerate(renglones, start=1):
            cuerpo = {k: v for k, v in renglon.items() if k != "hash"}
            if renglon.get("n") != posicion or renglon.get("previo") != previo or renglon.get("hash") != _hash(previo, cuerpo):
                return False, f"La cadena se rompe en el renglón {posicion}.", len(renglones)
            previo = renglon["hash"]
        return True, "La cadena está íntegra.", len(renglones)

    def renglones(self) -> list[dict]:
        return self._renglones()

    def anadir(self, datos: dict) -> dict:
        """Añade un renglón. Se niega si la cadena actual no cuadra."""
        bien, mensaje, cuantos = self.verificar()
        if not bien:
            raise RegistroAlterado(mensaje)
        renglones = self._renglones()
        previo = renglones[-1]["hash"] if renglones else GENESIS
        cuerpo = {**datos, "n": cuantos + 1, "previo": previo}
        renglon = {**cuerpo, "hash": _hash(previo, cuerpo)}
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self.ruta.open("a", encoding="utf-8", newline="\n") as archivo:
            archivo.write(_canonico(renglon) + "\n")
            archivo.flush()
            os.fsync(archivo.fileno())
        return renglon

    # ------------------------------------------------------------------------------------------------ consultas
    def emisiones(self) -> list[dict]:
        return [r for r in self._renglones() if r.get("accion") == "emitir"]

    def de_licencia(self, licencia_id: str) -> list[dict]:
        return [r for r in self.emisiones() if r.get("licencia_id") == licencia_id]

    def ultima_serie(self, licencia_id: str) -> int:
        """La serie más alta emitida para esa licencia (0 si el registro no la conoce)."""
        return max((int(r.get("serie", 0)) for r in self.de_licencia(licencia_id)), default=0)

    def por_nonce(self, nonce_hex: str) -> list[dict]:
        return [r for r in self.emisiones() if r.get("nonce") == nonce_hex]

    def de_aula(self, aula: str) -> list[dict]:
        clave = (aula or "").strip().lower()
        return [r for r in self.emisiones() if str(r.get("aula", "")).strip().lower() == clave]

"""
Qué es «el mismo recurso»: el mismo medio del mismo curso en la misma fuente, y —para un archivo dentro de una simulación o de una página html— la
misma ruta interna. La versión del curso NO forma parte de la clave: se guarda aparte y, si cambia, la copia vieja se descarta y se vuelve a traer
(así la caché no acumula una copia por versión).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class ClaveMedio:
    fuente: str
    curso_ref: str
    media_ref: str
    ruta: str = ""

    @staticmethod
    def de(fuente: str, curso_ref: str, media_ref: str, ruta: str | None = None) -> "ClaveMedio":
        return ClaveMedio(str(fuente or ""), str(curso_ref), str(media_ref), (ruta or "").strip("/"))

    def huella(self) -> str:
        """SHA-256 de la clave canónica: 64 caracteres hexadecimales, estable y sin datos sensibles."""
        texto = "\x1f".join((self.fuente, self.curso_ref, self.media_ref, self.ruta))
        return hashlib.sha256(texto.encode("utf-8")).hexdigest()

    def rotulo(self) -> str:
        return f"{self.media_ref}/{self.ruta}" if self.ruta else self.media_ref

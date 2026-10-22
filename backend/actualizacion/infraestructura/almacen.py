r"""
La carpeta de actualizaciones (P-02, P-06, P-17): `%ProgramData%\AVACOM\OPS Master\Actualizaciones\` en producción; en desarrollo y pruebas, `AVACOM_ACTUALIZACION_DIR` o una temporal.

    entrada\                  donde un técnico (o el canal por internet) deja un `.avupd` a mano: una fuente más (P-11)
    paquetes\<id>.avupd       cada paquete importado y verificado, tal cual
    staging\<id>\             lo extraído del paquete, listo para que el Host lo copie (nunca a backend\)
    versiones\<id>\anterior\  la instantánea del código que cambió, que escribe el Host y conserva 14 días (P-07, C-7)
    orden.json                la orden al Host (una sola a la vez); `resultado.json`, lo que el Host devuelve; `resultados\<orden>.json`, lo ya registrado

Toda escritura es atómica: a un temporal y `os.replace` (o `os.rename`, que en Windows NO sobrescribe: así `orden.json` sólo lo crea uno). Nada de aquí lanza un 500 hacia una vista
de negocio: lo que falla se traduce a un error del módulo.
"""
from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterable
from pathlib import Path

from ..dominio import catalogos as cat
from ..dominio import rutas
from ..dominio.errores import ActualizacionEnCurso, DatosInvalidos

CARPETAS = ("entrada", "paquetes", "staging", "versiones", "resultados")


def escribir_atomico(ruta: Path, datos: bytes, *, sin_sobrescribir: bool = False) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + f".{os.getpid()}.tmp")
    with open(temporal, "wb") as f:
        f.write(datos)
        f.flush()
        os.fsync(f.fileno())
    try:
        if sin_sobrescribir:
            os.rename(temporal, ruta)          # en Windows falla si ya existe; en POSIX `link` + `unlink` daría lo mismo, pero el nodo es Windows
        else:
            os.replace(temporal, ruta)
    finally:
        if temporal.exists():
            temporal.unlink(missing_ok=True)


class AlmacenEnCarpeta:
    def __init__(self, raiz: Path, ruta_base_de_datos: Path | None = None):
        self.raiz = Path(raiz)
        self.ruta_base_de_datos = Path(ruta_base_de_datos) if ruta_base_de_datos else None

    def asegurar(self) -> None:
        for nombre in CARPETAS:
            (self.raiz / nombre).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------------------------------------------------- paquetes
    def _ruta_paquete(self, paquete_id: str) -> Path:
        return self.raiz / "paquetes" / f"{self._id(paquete_id)}{cat.EXTENSION}"

    @staticmethod
    def _id(paquete_id: str) -> str:
        import uuid
        try:
            return str(uuid.UUID(str(paquete_id)))
        except ValueError:
            raise DatosInvalidos("Identificador de paquete inválido.") from None

    def guardar_paquete(self, paquete_id: str, datos: bytes) -> str:
        self.asegurar()
        ruta = self._ruta_paquete(paquete_id)
        escribir_atomico(ruta, datos)
        return str(ruta.relative_to(self.raiz))

    def leer_paquete(self, paquete_id: str) -> bytes | None:
        ruta = self._ruta_paquete(paquete_id)
        try:
            return ruta.read_bytes()
        except OSError:
            return None

    # ------------------------------------------------------------------------------------------------------------- staging
    def extraer(self, paquete_id: str, archivos: Iterable[tuple[str, bytes]]) -> str:
        destino = self.raiz / "staging" / self._id(paquete_id)
        self.borrar_staging(paquete_id)
        destino.mkdir(parents=True, exist_ok=True)
        raiz_real = destino.resolve()
        for ruta, contenido in archivos:
            rutas.validar(ruta)                                            # otra vez: lo que se escribe en disco pasa por la regla, aunque ya pasó
            objetivo = (destino / Path(*ruta.split("/")))
            if raiz_real not in objetivo.resolve().parents:
                raise DatosInvalidos("Una ruta del paquete sale del staging.")
            escribir_atomico(objetivo, contenido)
        return str(destino.relative_to(self.raiz))

    def borrar_staging(self, paquete_id: str) -> None:
        shutil.rmtree(self.raiz / "staging" / self._id(paquete_id), ignore_errors=True)

    # ------------------------------------------------------------------------------------------------------------- orden y resultado
    @property
    def ruta_orden(self) -> Path:
        return self.raiz / cat.ARCHIVO_ORDEN

    @property
    def ruta_resultado(self) -> Path:
        return self.raiz / cat.ARCHIVO_RESULTADO

    def escribir_orden(self, orden: dict) -> None:
        self.asegurar()
        datos = json.dumps(orden, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        try:
            escribir_atomico(self.ruta_orden, datos, sin_sobrescribir=True)
        except FileExistsError:
            raise ActualizacionEnCurso() from None

    def leer_orden(self) -> dict | None:
        return self._leer_json(self.ruta_orden)

    def hay_orden(self) -> bool:
        return self.ruta_orden.exists()

    def leer_resultado(self) -> dict | None:
        return self._leer_json(self.ruta_resultado)

    def archivar_resultado(self, orden_id: str) -> None:
        self.asegurar()
        nombre = "".join(c for c in str(orden_id) if c.isalnum() or c in "-_")[:64] or "sin-orden"
        if self.ruta_resultado.exists():
            os.replace(self.ruta_resultado, self.raiz / "resultados" / f"{nombre}.json")
        self.ruta_orden.unlink(missing_ok=True)

    @staticmethod
    def _leer_json(ruta: Path) -> dict | None:
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            raise DatosInvalidos(f"El archivo {ruta.name} no se puede leer.") from None
        return datos if isinstance(datos, dict) else None

    # ------------------------------------------------------------------------------------------------------------- espacio
    def espacio_libre(self) -> int | None:
        try:
            self.asegurar()
            return int(shutil.disk_usage(self.raiz).free)
        except OSError:
            return None

    def bytes_de_la_base(self) -> int:
        if self.ruta_base_de_datos is None:
            return 0
        total = 0
        for sufijo in ("", "-wal", "-shm"):
            try:
                total += Path(str(self.ruta_base_de_datos) + sufijo).stat().st_size
            except OSError:
                continue
        return total

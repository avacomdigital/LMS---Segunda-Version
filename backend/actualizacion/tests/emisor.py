"""
El EMISOR DE PRUEBAS de paquetes `.avupd`: fabrica paquetes firmados con llaves de DESARROLLO que sólo existen aquí. No es el emisor de producción (ése vivirá fuera del nodo,
en `tools/actualizacion/`; su llave privada nunca está en este repositorio).

  · Las llaves de desarrollo se DERIVAN de una semilla pública (`SEMILLA`) y un `kid` reservado (`upd-dev-1`, `upd-dev-2`): cualquiera que lea este archivo puede firmar un
    paquete de desarrollo, y por eso el nodo sólo las acepta cuando el entorno es de desarrollo o de pruebas POR CONSTRUCCIÓN (el mismo criterio de MOD-018, P-12).
  · El instalador EXCLUYE esta carpeta (`backend/actualizacion/tests`) y `actualizacion/claves/desarrollo.json` y falla si viajan, como hace con los de licenciamiento (`Build-Installer.ps1`,
    P-03). El emisor de AVACOM (producción) vive fuera del nodo, en `tools/actualizacion/`, y sólo trae llaves generadas con la ceremonia de llaves: nunca una semilla derivada.
"""
from __future__ import annotations

import hashlib
import uuid

from actualizacion.dominio import catalogos as cat
from actualizacion.dominio import contenedor, firma
from actualizacion.dominio import manifiesto as mf

SEMILLA = b"avacom-actualizacion-desarrollo-v1"
KID_DEV_1, KID_DEV_2 = "upd-dev-1", "upd-dev-2"
AHORA = 1_790_000_000_000          # un instante fijo (octubre de 2026): las pruebas no dependen del día en que corren
PAQUETE_ID = str(uuid.UUID(int=0x17171717_0001_4000_8000_000000000001))


def clave_privada(kid: str) -> bytes:
    return hashlib.sha256(SEMILLA + b"|" + kid.encode("ascii")).digest()


def claves_publicas(*kids: str) -> dict[str, bytes]:
    return {kid: firma.publica_de(clave_privada(kid)) for kid in (kids or (KID_DEV_1, KID_DEV_2))}


def archivos_de_ejemplo() -> dict[str, bytes]:
    """Dos archivos de `reporting` (un parche y una migración) y el registro de módulos."""
    return {
        "reporting/dominio/parche_de_ejemplo.py": b'"""Parche de ejemplo de un paquete de actualizacion (pruebas de MOD-017)."""\nVERSION = "1.4.0"\n',
        "reporting/migrations/0004_parche_de_ejemplo.py": b"from django.db import migrations\n\n\nclass Migration(migrations.Migration):\n    dependencies = [('reporting', '0003_corte_cola_unica')]\n    operations = []\n",
    }


def _archivos_declarados(archivos: dict[str, bytes]) -> tuple[mf.Archivo, ...]:
    return tuple(mf.Archivo(ruta, len(contenido), hashlib.sha256(contenido).hexdigest()) for ruta, contenido in archivos.items())


def manifiesto_de_ejemplo(archivos: dict[str, bytes] | None = None, **cambios) -> mf.Manifiesto:
    """Un paquete de `reporting` 1.4.0 (serie 7, datos 4, contrato 1) para el producto 2.12.0; los `cambios` sobrescriben cualquier campo."""
    archivos = archivos if archivos is not None else archivos_de_ejemplo()
    base = dict(
        formato=cat.FORMATO_MANIFIESTO, paquete_id=PAQUETE_ID, nombre="Reportes 1.4.0 · corrección del boletín", producto=cat.PRODUCTO, version_producto="2.12.0",
        version_minima="2.11.0", emitido_en=AHORA - 3 * cat.DIA_MS,
        modulos=(mf.Modulo(nombre="reporting", version="1.4.0", version_datos=4, version_contrato=1, serie=7, requiere={"nodo": 1},
                           migraciones=(mf.Migracion("0004_parche_de_ejemplo", "0003_corte_cola_unica"),)),),
        archivos=_archivos_declarados(archivos), requisitos=mf.Requisitos(contrato_biblioteca=2, cliente_minimo="2.10.0", espacio_bytes=0), criticas=(), nota="Paquete de pruebas.")
    base.update(cambios)
    return mf.Manifiesto(**base)


def empaquetar(manifiesto_bytes: bytes | None, firma_bytes: bytes | None, archivos: dict[str, bytes], extra: dict[str, bytes] | None = None,
               atributos: dict[str, int] | None = None, carpeta: str = cat.CARPETA_ARCHIVOS, duplicar: str | None = None) -> bytes:
    """El contenedor canónico (`contenedor.escribir`). `None` omite esa entrada; `extra` añade entradas con cualquier nombre; `duplicar` repite esa ruta (para probar el rechazo)."""
    entradas: list[tuple[str, bytes]] = []
    if manifiesto_bytes is not None:
        entradas.append((cat.NOMBRE_MANIFIESTO, manifiesto_bytes))
    if firma_bytes is not None:
        entradas.append((cat.NOMBRE_FIRMA, firma_bytes))
    for ruta, contenido in archivos.items():
        entradas.append((carpeta + ruta, contenido))
        if duplicar == ruta:
            entradas.append((carpeta + ruta, b"otro contenido con el mismo nombre"))
    for nombre, contenido in (extra or {}).items():
        entradas.append((nombre, contenido))
    atributos_por_nombre = {(carpeta + k if k in archivos else k): v for k, v in (atributos or {}).items()}
    return contenedor.escribir(entradas, atributos=atributos_por_nombre)


def emitir(manifiesto: mf.Manifiesto | None = None, kid: str = KID_DEV_1, archivos: dict[str, bytes] | None = None, clave: bytes | None = None, **cambios) -> bytes:
    """El `.avupd` firmado con la llave de desarrollo `kid` (o con `clave`, para probar una llave ajena)."""
    archivos = archivos if archivos is not None else archivos_de_ejemplo()
    manifiesto = manifiesto or manifiesto_de_ejemplo(archivos, **cambios)
    manifiesto_bytes = mf.escribir(manifiesto)
    return empaquetar(manifiesto_bytes, firma.sellar(kid, clave or clave_privada(kid), manifiesto_bytes), archivos)


def emitir_crudo(manifiesto_json: bytes, kid: str = KID_DEV_1, archivos: dict[str, bytes] | None = None, **kw) -> bytes:
    """Un paquete con un manifiesto ARBITRARIO (aunque sea inválido), firmado CORRECTAMENTE: demuestra que lo que rechaza es la regla de forma y no la firma."""
    archivos = archivos if archivos is not None else archivos_de_ejemplo()
    return empaquetar(manifiesto_json, firma.sellar(kid, clave_privada(kid), manifiesto_json), archivos, **kw)


__all__ = ["AHORA", "KID_DEV_1", "KID_DEV_2", "PAQUETE_ID", "archivos_de_ejemplo", "claves_publicas", "clave_privada", "emitir", "emitir_crudo", "empaquetar", "manifiesto_de_ejemplo"]

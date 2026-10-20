"""
El EMISOR DE PRUEBAS de licencias: fabrica `.avlic` firmados con llaves de DESARROLLO que sólo existen aquí. No es el emisor de producción (ése vive fuera del nodo, en
`tools/licencias/`, y su llave privada nunca está en este repositorio).

  · Las llaves de desarrollo se DERIVAN de una semilla pública (`SEMILLA`) y un `kid` reservado (`dev-1`, `dev-2`): cualquiera que lea este archivo puede firmar una licencia de
    desarrollo, y por eso el nodo sólo las acepta cuando el entorno es de desarrollo o de pruebas POR CONSTRUCCIÓN (`dominio/entorno.py`, P-12).
  · El instalador EXCLUYE esta carpeta (`backend\\licenciamiento\\tests`) y el archivo de llaves de desarrollo: una prueba sobre el contenido del paquete lo comprueba.
"""
from __future__ import annotations

import hashlib
import uuid

from licenciamiento.dominio import firma, huella, licencia, tlv
from licenciamiento.dominio.licencia import ILIMITADO, HuellaDeLicencia, Licencia, Limites
from licenciamiento.dominio.politica import DIA_MS

SEMILLA = b"avacom-licencia-desarrollo-v1"
KID_DEV_1, KID_DEV_2 = "dev-1", "dev-2"
AHORA = 1_790_000_000_000          # un instante fijo (octubre de 2026): las pruebas no dependen del día en que corren
TODAS = frozenset({"*"})


def clave_privada(kid: str) -> bytes:
    return hashlib.sha256(SEMILLA + b"|" + kid.encode("ascii")).digest()


def claves_publicas(*kids: str) -> dict[str, bytes]:
    return {kid: firma.publica_de(clave_privada(kid)) for kid in (kids or (KID_DEV_1, KID_DEV_2))}


def factores_de_ejemplo(n: int = 4) -> dict[int, bytes]:
    """Hasta cuatro factores de unidad válidos y distintos (los hashes que una solicitud llevaría): MachineGuid, UUID de SMBIOS, serie de placa y serie de chasis."""
    valores = {huella.F_MACHINE_GUID: "9f1c2a3e-1111-4b2b-8c3d-aaaaaaaaaa01", huella.F_SMBIOS_UUID: "4C4C4544-0042-3510-8058-B6C04F425A32",
               huella.F_PLACA: "BRD-7781-ZX-2209", huella.F_CHASIS: "CH-55-0192-77"}
    return huella.factores_validos({f: v for f, v in list(valores.items())[:n]})


def huella_de(factores: dict[int, bytes] | None = None, k: int | None = None) -> HuellaDeLicencia:
    factores = factores if factores is not None else factores_de_ejemplo()
    return HuellaDeLicencia(k if k is not None else huella.k_para(len(factores)), tuple(sorted(factores.items())))


def licencia_de_ejemplo(**cambios) -> Licencia:
    """Una licencia de producción vigente un año desde AHORA - 30 días, con un mes de gracia; los `cambios` sobrescriben cualquier campo."""
    base = dict(
        id=str(uuid.UUID(int=0xA7A7A7A7_0001_4000_8000_000000000001)), serie=1, aula="Aula de pruebas", emitida=AHORA - 31 * DIA_MS, desde=AHORA - 30 * DIA_MS,
        vence=AHORA + 335 * DIA_MS, gracia_dias=30, limites=Limites(equipos=55, usuarios=1200, concurrentes_normal=50, concurrentes_pico=100),
        capacidades=TODAS, huella=huella_de(), tipo=licencia.TIPO_PRODUCCION, liberacion_pendiente=False, liberacion_dias=0, hash_clave_nodo=None)
    base.update(cambios)
    return Licencia(**base)


def emitir(lic: Licencia | None = None, kid: str = KID_DEV_1, **cambios) -> bytes:
    """El `.avlic` firmado con la llave de desarrollo `kid`."""
    lic = lic or licencia_de_ejemplo(**cambios)
    return tlv.sellar(licencia.sin_firma(lic, kid), lambda datos: firma.firmar(clave_privada(kid), datos))


def sellar_campos(campos: dict[int, bytes], *, kid: str = KID_DEV_1, version: int = tlv.VERSION_FORMATO, conocidos=None, clave: bytes | None = None) -> bytes:
    """Un archivo con los campos que se quiera (aunque sean inválidos), firmado CORRECTAMENTE: sirve para demostrar que lo que rechaza es la regla de forma y no la firma."""
    conocidos = conocidos if conocidos is not None else {n: (4096, False) for n in range(1, 64)}
    sin_firma = tlv.escribir(tlv.MAGIC_LICENCIA, kid, campos, conocidos, version=version)
    return tlv.sellar(sin_firma, lambda datos: firma.firmar(clave or clave_privada(kid), datos))


__all__ = ["AHORA", "ILIMITADO", "KID_DEV_1", "KID_DEV_2", "claves_publicas", "emitir", "factores_de_ejemplo", "huella_de", "licencia_de_ejemplo", "sellar_campos"]

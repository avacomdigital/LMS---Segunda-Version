"""
Genera `build/corpus.bin` para el harness de mutacion en C (`tests/test_avl.c --mutate`): licencias VALIDAS (variadas) con sus llaves publicas.

Formato (big endian): u32 cantidad · por entrada: u8 largo del kid · kid · pub(32) · semilla(32) · u16 largo · datos.
Se usan las llaves de DESARROLLO del emisor de pruebas del backend (su semilla es publica por construccion y esta en el repositorio): este corpus no lleva ninguna llave de
produccion. La semilla permite al harness RE-FIRMAR cuerpos alterados y asi ejercitar el lector de campos (no solo el rechazo por firma).

Uso:  python tools/gen_corpus.py [salida]     (desde native/avacom-lic; usa el Python del backend)
"""
from __future__ import annotations

import random
import struct
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ.parents[1] / "backend"))

from licenciamiento.dominio import licencia  # noqa: E402
from licenciamiento.dominio.licencia import HuellaDeLicencia, Limites  # noqa: E402
from licenciamiento.tests import emisor  # noqa: E402


def licencias(n: int, semilla: int = 20261022) -> list[tuple[str, bytes, bytes, bytes]]:
    rng = random.Random(semilla)
    salida = []
    for i in range(n):
        kid = rng.choice([emisor.KID_DEV_1, emisor.KID_DEV_2])
        nfact = rng.randrange(1, 5)
        factores = emisor.factores_de_ejemplo(4)
        items = sorted(rng.sample(sorted(factores.items()), min(nfact, len(factores))))
        k = rng.randrange(1, len(items) + 1)
        capacidades = frozenset(rng.sample(["*", "reportes", "busqueda", "importacion", "administracion_avanzada"], rng.randrange(1, 4)))
        desde = emisor.AHORA - rng.randrange(1, 400) * 86_400_000
        normal = rng.randrange(1, 100)
        lic = emisor.licencia_de_ejemplo(
            id=str(uuid.UUID(int=rng.getrandbits(128), version=4)), serie=rng.randrange(1, 50), aula=rng.choice(["", "Aula de pruebas", "Aula ñandú 3", "Sala B"]),
            desde=desde, emitida=desde - 86_400_000, vence=desde + rng.randrange(30, 700) * 86_400_000, gracia_dias=rng.randrange(0, 90),
            limites=Limites(rng.randrange(1, 60), rng.randrange(1, 1200), normal, normal + rng.randrange(0, 80)), capacidades=capacidades,
            huella=HuellaDeLicencia(k, tuple(items)), tipo=rng.choice([licencia.TIPO_PRODUCCION, licencia.TIPO_EVALUACION, licencia.TIPO_DESARROLLO]),
            liberacion_pendiente=(i % 7 == 0), liberacion_dias=(rng.randrange(1, 30) if i % 7 == 0 else 0),
            hash_clave_nodo=(rng.randbytes(32) if i % 5 == 0 else None))
        salida.append((kid, emisor.claves_publicas(kid)[kid], emisor.clave_privada(kid), emisor.emitir(lic, kid)))
    return salida


def main() -> int:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "build" / "corpus.bin"
    destino.parent.mkdir(parents=True, exist_ok=True)
    datos = licencias(64)
    cuerpo = struct.pack(">I", len(datos))
    for kid, pub, semilla, archivo in datos:
        cuerpo += struct.pack(">B", len(kid)) + kid.encode("ascii") + pub + semilla + struct.pack(">H", len(archivo)) + archivo
    destino.write_bytes(cuerpo)
    print(f"{len(datos)} licencias validas -> {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

r"""
Sella el paquete que Build-Installer.ps1 dejo en dist\staging (MOD-018, P-23: integridad del despliegue):

  1. integridad.json        la lista «ruta · SHA-256» de lo que el nodo EJECUTA: Backend, Runtime (Host, Python embebido y site-packages) y, de App, solo lo propio de AVACOM
                            (Avacom.Lms.*.dll/.exe) y la DLL nativa. El Host la vuelve a calcular al arrancar el servicio.
  2. manifiesto.json        se le anota el SHA-256 de la lista (`integridad`) y con que llave se firmo (`firma_del_manifiesto`).
  3. manifiesto.firma.json  la firma Ed25519 de los bytes EXACTOS de manifiesto.json, con la llave de PUBLICACION (la misma de los paquetes .avupd). SOLO si se da `--privada`.

La frase de paso de la llave llega por la variable de entorno AVACOM_FRASE_LLAVE (la pone Build-Installer.ps1 en el proceso hijo, desde la copia DPAPI, y no se escribe en ningun archivo
ni se imprime). Sin `--privada` el paquete queda SIN firma: valido para un desarrollo, rechazado por `-ExigirLlaveDeProduccion`.

Antes de firmar se comprueba que la llave es una de las que `backend/actualizacion/claves/produccion.json` declara vigente o siguiente: una llave que ningun nodo conoce no firma nada.
Despues de firmar se verifica la firma con la publica. Salida: 0 bien · 2 la llave no abre o no es una publica conocida · 3 uso o datos invalidos.
"""
from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "tools" / "actualizacion"))

from avacom_actualizacion import llaves                                           # noqa: E402
from cryptography.exceptions import InvalidSignature                              # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey  # noqa: E402

CARPETAS_IGNORADAS = {"__pycache__"}
PATRONES_DEL_BACKEND = ("*.pyc", "*.log", "*.log.*", "*.sqlite3*", "*.db", ".escritura")
PATRONES_DEL_RUNTIME = ("*.pyc", "*.pdb")
PROPIOS_DE_LA_APP = ("Avacom.Lms.*.dll", "Avacom.Lms.*.exe", "*avacom_lic*")


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def recorrer(base: Path, raiz: Path, patrones_excluidos: tuple[str, ...], solo: tuple[str, ...] | None = None):
    for carpeta, subcarpetas, archivos in os.walk(base):
        subcarpetas[:] = sorted(s for s in subcarpetas if s not in CARPETAS_IGNORADAS)
        for nombre in sorted(archivos):
            if any(fnmatch.fnmatch(nombre, p) for p in patrones_excluidos):
                continue
            if solo is not None and not any(fnmatch.fnmatch(nombre, p) for p in solo):
                continue
            ruta = Path(carpeta) / nombre
            yield ruta.relative_to(raiz).as_posix(), ruta


def lista_de_integridad(staging: Path) -> list[list[str]]:
    filas: list[list[str]] = []
    for carpeta, excluidos, solo in (("Backend", PATRONES_DEL_BACKEND, None), ("Runtime", PATRONES_DEL_RUNTIME, None), ("App", (), PROPIOS_DE_LA_APP)):
        base = staging / carpeta
        if not base.is_dir():
            continue
        filas += [[ruta, sha256(archivo)] for ruta, archivo in recorrer(base, staging, excluidos, solo)]
    filas.sort(key=lambda fila: fila[0])
    return filas


def llaves_del_nodo(produccion: Path) -> dict[str, bytes]:
    return llaves.leer_claves_del_nodo(produccion.read_text(encoding="utf-8-sig"))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--staging", required=True)
    ap.add_argument("--privada", help="la llave de publicacion (.avkey); sin ella el manifiesto queda SIN firma")
    ap.add_argument("--claves-produccion", default=str(RAIZ / "backend" / "actualizacion" / "claves" / "produccion.json"))
    a = ap.parse_args(argv)
    staging = Path(a.staging)
    ruta_manifiesto = staging / "manifiesto.json"
    if not ruta_manifiesto.is_file():
        print(f"No existe {ruta_manifiesto}", file=sys.stderr)
        return 3

    filas = lista_de_integridad(staging)
    if not filas:
        print("La lista de integridad salio vacia: no hay nada que sellar.", file=sys.stderr)
        return 3
    lista = json.dumps({"version": 1, "archivos": filas}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    (staging / "integridad.json").write_bytes(lista)

    manifiesto = json.loads(ruta_manifiesto.read_text(encoding="utf-8-sig"))
    manifiesto["integridad"] = {"archivo": "integridad.json", "sha256": hashlib.sha256(lista).hexdigest(), "archivos": len(filas)}
    firma_con = None
    llave = None
    if a.privada:
        frase = os.environ.get("AVACOM_FRASE_LLAVE", "")
        try:
            llave = llaves.abrir(Path(a.privada).read_bytes(), frase)
        except (llaves.ErrorDeLlave, OSError) as error:
            print(f"No se pudo abrir la llave de publicacion: {error}", file=sys.stderr)
            return 2
        conocidas = llaves_del_nodo(Path(a.claves_produccion))
        if conocidas.get(llave.kid) != llave.publica:
            print(f"La llave {llave.kid} no es una de las vigentes o siguientes de {a.claves_produccion}: ningun nodo la reconoceria.", file=sys.stderr)
            return 2
        firma_con = llave.kid
    manifiesto["firma_del_manifiesto"] = {"archivo": "manifiesto.firma.json", "kid": firma_con} if firma_con else None
    cuerpo = (json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    ruta_manifiesto.write_bytes(cuerpo)

    firma_ruta = staging / "manifiesto.firma.json"
    if llave is None:
        firma_ruta.unlink(missing_ok=True)
        print(f"Paquete SIN firma: lista de integridad de {len(filas)} archivos.")
        return 0
    firma = Ed25519PrivateKey.from_private_bytes(llave.privada).sign(cuerpo)
    try:
        Ed25519PublicKey.from_public_bytes(llave.publica).verify(firma, cuerpo)
    except InvalidSignature:
        print("La firma recien hecha no verifica: no se escribe.", file=sys.stderr)
        return 2
    firma_ruta.write_text(json.dumps({"kid": llave.kid, "alg": "ed25519", "firma": base64.b64encode(firma).decode("ascii")}, indent=2) + "\n", encoding="utf-8")
    print(f"Paquete firmado con {llave.kid}: lista de integridad de {len(filas)} archivos, manifiesto firmado.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

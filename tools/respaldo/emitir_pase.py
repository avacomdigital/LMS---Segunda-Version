r"""
AVACOM · Emisor de PASES DE SOPORTE (uso interno de AVACOM; NO viaja en el instalador del colegio).

Un pase es lo que permite a una persona de AVACOM WORLD EXPORTAR o RESTAURAR los respaldos de un equipo (MOD-016, D-2). Es un archivo firmado con la llave privada de AVACOM, de UN solo uso
y de un día como máximo. El nodo lo verifica con la llave pública que trae `backend/respaldo/claves/produccion.json`.

    python emitir_pase.py emitir  --privada F:\claves\sop-2026-1.pem --kid sop-2026-1 --tecnico "Ana Pérez (AVACOM)" --acciones backup.restore backup.export --horas 4 --salida pase.avsp
    python emitir_pase.py emitir  ... --nodo 3f2a9c1e-....      (un pase para UN equipo; sin --nodo vale para cualquiera: hace falta al restaurar en un equipo NUEVO)
    python emitir_pase.py ver     pase.avsp --publica F:\claves\sop-2026-1.pub.hex
    python emitir_pase.py llave   --salida F:\claves\sop-2026-1.pem      (genera un par: imprime la PÚBLICA para `produccion.json`; la privada queda SÓLO en el archivo)

La llave privada va en su memoria USB, cifrada o bajo custodia, y se genera/rota en la misma ceremonia de llaves que las de licencias y actualizaciones. NUNCA en el repositorio.
En el equipo del colegio el técnico entrega el pase como texto base64 (`--base64` lo imprime) o lo copia desde la memoria USB.

Se ejecuta con el Python del backend (`backend\.venv\Scripts\python`): sólo necesita `cryptography`.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "backend"))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

PERMISOS = ("backup.export", "backup.restore", "backup.restore.module", "backup.schedule")      # backup.schedule: sólo para emitir el código de custodia
HORA_MS = 3_600_000


def _cargar_privada(ruta: Path) -> Ed25519PrivateKey:
    crudo = ruta.read_bytes().strip()
    if crudo.startswith(b"-----BEGIN"):
        llave = serialization.load_pem_private_key(crudo, password=None)
        if not isinstance(llave, Ed25519PrivateKey):
            raise SystemExit("La llave no es Ed25519.")
        return llave
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(crudo.decode("ascii")))


def _publica_hex(llave: Ed25519PrivateKey) -> str:
    return llave.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def _emitir(a) -> int:
    from respaldo.dominio import pase

    for accion in a.acciones:
        if accion not in PERMISOS:
            raise SystemExit(f"«{accion}» no es una operación que un pase pueda autorizar: {', '.join(PERMISOS)}")
    if not 0 < a.horas <= 24:
        raise SystemExit("Un pase vale como máximo 24 horas.")
    ahora = int(time.time() * 1000)
    payload = {"pase_id": str(uuid.uuid4()), "tecnico": a.tecnico, "emitido_en": ahora, "vence_en": ahora + int(a.horas * HORA_MS), "acciones": list(a.acciones), "nodo": a.nodo or "*",
               "motivo": a.motivo or ""}
    datos = pase.firmar(payload, a.kid, _cargar_privada(Path(a.privada)))
    Path(a.salida).write_bytes(datos)
    print(f"Pase escrito en {a.salida}")
    print(f"  Persona de AVACOM : {a.tecnico}")
    print(f"  Autoriza          : {', '.join(a.acciones)}")
    print(f"  Equipo            : {a.nodo or 'cualquiera (*)'}")
    print(f"  Vence             : {time.strftime('%d/%m/%Y %H:%M', time.localtime(payload['vence_en'] / 1000))}  ({a.horas:g} h)")
    print("  Se usa UNA vez.")
    if a.base64:
        print("\nTexto para pegar en la pantalla del equipo:\n" + base64.b64encode(datos).decode("ascii"))
    return 0


def _ver(a) -> int:
    from respaldo.dominio import pase

    datos = Path(a.pase).read_bytes()
    publica = bytes.fromhex(Path(a.publica).read_text(encoding="ascii").strip())
    kid = datos[5:5 + datos[4]].decode("ascii")
    ahora = int(time.time() * 1000)
    try:
        p = pase.abrir(datos, {kid: publica}, ahora, json.loads(datos[5 + datos[4] + 64:])["acciones"][0], json.loads(datos[5 + datos[4] + 64:]).get("nodo", "*"))
    except Exception as error:   # noqa: BLE001 — es una herramienta de consola
        print(f"INVÁLIDO: {getattr(error, 'motivo', error)}")
        return 1
    print(json.dumps(p.a_dict(), indent=2, ensure_ascii=False))
    return 0


def _llave(a) -> int:
    destino = Path(a.salida)
    if destino.exists():
        raise SystemExit(f"{destino} ya existe: no se sobrescribe una llave.")
    llave = Ed25519PrivateKey.generate()
    destino.write_bytes(llave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    print(f"Llave privada escrita en {destino}  (guárdala en su memoria USB y bórrala de aquí).")
    print("Llave PÚBLICA para backend/respaldo/claves/produccion.json:")
    print(json.dumps({"kid": a.kid or "sop-2026-1", "publica": _publica_hex(llave), "estado": "vigente"}, indent=2))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Emisor de pases de soporte de AVACOM (MOD-016)")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("emitir")
    e.add_argument("--privada", required=True)
    e.add_argument("--kid", required=True)
    e.add_argument("--tecnico", required=True, help="quién de AVACOM hará la operación")
    e.add_argument("--acciones", nargs="+", required=True)
    e.add_argument("--horas", type=float, default=4)
    e.add_argument("--nodo", default="")
    e.add_argument("--motivo", default="")
    e.add_argument("--salida", default="pase.avsp")
    e.add_argument("--base64", action="store_true")
    e.set_defaults(f=_emitir)
    v = sub.add_parser("ver")
    v.add_argument("pase")
    v.add_argument("--publica", required=True)
    v.set_defaults(f=_ver)
    k = sub.add_parser("llave")
    k.add_argument("--salida", required=True)
    k.add_argument("--kid", default="sop-2026-1")
    k.set_defaults(f=_llave)
    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    raise SystemExit(main())

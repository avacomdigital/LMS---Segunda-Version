r"""Recorrido de la pantalla Dispositivos de OPS con la identidad por clave (MOD-018, Fase 5): un nodo AISLADO (base temporal, puerto aparte, sesión obligatoria), tres tabletas con garantía distinta
(declarada, con clave propia —una prueba real firmada por la API— y verificada por hardware —fijada en la base: no hay hardware aquí—) y OPS llevada a esa pantalla (`AVACOM_OPS_RUTA=dispositivos`).
Comprueba que las tres líneas «Identidad del equipo: …» están (el árbol de accesibilidad lee la descripción) y deja una captura con la regla de tercios.

  backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\recorrido_dispositivos.py --ops <Avacom.Lms.Ops.exe> --salida <carpeta> [--puerto 8021]

Sale con 0 si todo se cumplió. Mismas reglas del arnés de esta carpeta: nodo aislado, perfil de pruebas de OPS, candado de pantalla. Sólo en un árbol de desarrollo.
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True
RAIZ = Path(__file__).resolve().parent.parent.parent
UIA = Path(__file__).resolve().parent
BACKEND = RAIZ / "backend"
sys.path.insert(0, str(BACKEND))

args = argparse.ArgumentParser()
args.add_argument("--ops", required=True)
args.add_argument("--salida", required=True)
args.add_argument("--puerto", type=int, default=8021)
a = args.parse_args()
os.environ["AVACOM_UIA_PUERTO"] = str(a.puerto)

spec = importlib.util.spec_from_file_location("recorrido_acceso", UIA / "recorrido_acceso.py")
ra = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ra)
ra.PUERTO = a.puerto
ra.NODO = f"http://127.0.0.1:{a.puerto}"

from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

from licenciamiento.dominio import atestacion as at  # noqa: E402

ADMIN_DOC, ADMIN_CLAVE, PIN = "1042888795", "Rectoria.Uia.2026!", "482915"
informe: list[tuple[str, bool, str]] = []


def anotar(paso: str, ok: bool, detalle: str = "") -> bool:
    informe.append((paso, ok, detalle))
    print(("  OK  " if ok else "  FALLA"), paso, ("· " + detalle) if detalle and not ok else "", flush=True)
    return ok


def main() -> int:
    salida = Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="avacom-uia-disp-"))
    db = tmp / "nodo.sqlite3"
    env = {**os.environ, "AVACOM_LMS_DB": str(db), "AVACOM_LMS_EXIGIR_SESION": "1", "PYTHONIOENCODING": "utf-8", "AVACOM_LICENCIA_MODO": "firmada", "AVACOM_LICENCIA_DIR": str(tmp / "lic"),
           "AVACOM_LICENCIA_PROGRAMADOR": "0", "AVACOM_LMS_DIR_LOGS": str(tmp / "logs")}
    py = ra.python_backend()
    subprocess.run([py, "manage.py", "migrate", "--noinput"], cwd=BACKEND, env=env, check=True, capture_output=True)
    nodo = subprocess.Popen([py, "manage.py", "runserver", ra.NODO.removeprefix("http://"), "--noreload"], cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ops = None
    ra.tomar_candado()
    try:
        import urllib.request
        for _ in range(60):
            try:
                urllib.request.urlopen(f"{ra.NODO}/health/", timeout=2)
                break
            except Exception:
                time.sleep(1)
        c, _ = ra.api("POST", "/api/acceso/instalacion/", {
            "organizacion": {"codigo": "IE-UIA-ID", "nombre": "IE Prueba Identidad", "pais": "CO", "idioma": "es", "locale": "es-CO"},
            "administrador": {"alias": "Rectoría", "nombres": "Ana", "apellidos": "Pérez", "dni": ADMIN_DOC, "password": ADMIN_CLAVE}, "pin_maestro": PIN})
        anotar("la organización se instala por la API", c == 201, f"código {c}")
        # tres tabletas: declarada (sin clave), software (clave con prueba real, sin cadena) y hardware (sólo para ver el color: se fija en la base)
        for hw, nombre in (("student-uia-declarada-0001", "Tableta declarada"), ("student-uia-software-0002", "Tableta con clave"), ("student-uia-hardware-0003", "Tableta verificada")):
            c, _ = ra.api("POST", "/api/dispositivos/latido/", {"identificador_hw": hw, "nombre": nombre, "plataforma": "android", "version_app": "uia", "tipo": "TABLETA"})
            anotar(f"se registra {nombre}", c == 200, f"código {c}")
        clave = ec.generate_private_key(ec.SECP256R1())
        spki = clave.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        c, r = ra.api("POST", "/api/licencia/identidad/reto/", {})
        nonce = base64.b64decode(r["nonce"])
        firma = clave.sign(at.mensaje_del_reto(nonce, "student-uia-software-0002"), ec.ECDSA(hashes.SHA256()))
        c, r = ra.api("POST", "/api/licencia/identidad/enrolar/", {"identificador_hw": "student-uia-software-0002", "identidad": {
            "nonce": base64.b64encode(nonce).decode(), "clave_publica": base64.b64encode(spki).decode(), "firma": base64.b64encode(firma).decode()}})
        anotar("la tableta con clave se enrola (garantía software)", c == 200 and r.get("garantia") == "software", f"{c} {r}")
        with sqlite3.connect(db) as cx:
            cx.execute("UPDATE m09_dispositivo SET garantia='hardware', clave_huella='aa'||substr(hex(randomblob(31)),1,62), garantia_detalle='{\"motivo\": \"ok\"}' WHERE identificador_hw='student-uia-hardware-0003'")
        ops = ra.Ops(Path(a.ops), salida, f"uia-disp-{int(time.time())}", ruta="dispositivos")
        ra.entrar(ops, ADMIN_DOC, ADMIN_CLAVE, PIN)
        anotar("la pantalla Dispositivos abre", ops.esperar("Tableta declarada", 30000))
        textos = [t.lower() for t in ops.textos()]
        for esperado in ("identidad del equipo: declarada", "identidad del equipo: con clave propia", "identidad del equipo: verificada por hardware"):
            anotar(f"se lee «{esperado}»", any(esperado in t for t in textos), f"textos: {textos[:12]}")
        ops.captura("dispositivos-identidad")
    finally:
        if ops:
            ops.cerrar()
        nodo.kill()
        ra.soltar_candado()
    fallas = [p for p, ok, _ in informe if not ok]
    print(f"\n{len(informe) - len(fallas)} de {len(informe)} comprobaciones cumplidas", flush=True)
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
New-DeviceOwnerQr.py - genera el JSON (y, si hay libreria, el PNG) del codigo QR de
aprovisionamiento de Device Owner para tabletas Android de AVACOM LMS.

Uso (kiosk.md 3.5, «Muchas tabletas, por QR»):

    python New-DeviceOwnerQr.py --apk Student.apk --url https://servidor/Student.apk --out salida
    python New-DeviceOwnerQr.py --apk Student.apk --url https://servidor/Student.apk --out salida \\
        --wifi-ssid MiRed --wifi-password -          (la clave se pide por teclado)

Que hace:
  * calcula el SHA-256 del APK en Base64 URL-safe SIN relleno (extra
    android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_CHECKSUM);
  * rellena device-owner-qr.template.json (componente, URL de descarga, checksum y
    PROVISIONING_LEAVE_ALL_SYSTEM_APPS_ENABLED=false);
  * agrega las claves de Wi-Fi SOLO si se pasan en la linea de comandos;
  * valida su propia salida (JSON valido, claves obligatorias, checksum correcto);
  * escribe <out>/device-owner-qr.json y, si `qrcode` esta instalado, <out>/device-owner-qr.png.

Solo biblioteca estandar (la libreria `qrcode` es opcional). No usa la red.

AVISO: si pasas --wifi-password, la clave queda EN CLARO en el JSON y en el QR. Trata la
carpeta de salida como secreta y no la subas al repositorio. La plantilla no lleva ninguna clave.

NO PROBADO EN HARDWARE: el flujo de QR se escribio a partir de la documentacion de Android.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import re
import sys
from pathlib import Path

DEFAULT_COMPONENT = (
    "com.avacom.lms.student/com.avacom.lms.student.ExamDeviceAdminReceiver"
)

KEY_COMPONENT = "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME"
KEY_LOCATION = "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION"
KEY_CHECKSUM = "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_CHECKSUM"
KEY_LEAVE_APPS = "android.app.extra.PROVISIONING_LEAVE_ALL_SYSTEM_APPS_ENABLED"
KEY_WIFI_SSID = "android.app.extra.PROVISIONING_WIFI_SSID"
KEY_WIFI_PASSWORD = "android.app.extra.PROVISIONING_WIFI_PASSWORD"
KEY_WIFI_SECURITY = "android.app.extra.PROVISIONING_WIFI_SECURITY_TYPE"

REQUIRED_KEYS = (KEY_COMPONENT, KEY_LOCATION, KEY_CHECKSUM, KEY_LEAVE_APPS)

CHECKSUM_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")  # 32 bytes -> 43 caracteres sin relleno
COMPONENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]*/[.A-Za-z][A-Za-z0-9_.$]*$")


def log(msg: str) -> None:
    print(msg)


def fail(msg: str, code: int = 1) -> None:
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


def apk_checksum(path: Path) -> str:
    """SHA-256 del archivo en Base64 URL-safe, sin relleno '='."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return base64.urlsafe_b64encode(digest.digest()).rstrip(b"=").decode("ascii")


def fill_template(node, values):
    """Sustituye {{MARCADORES}} en todas las cadenas de la plantilla."""
    if isinstance(node, str):
        for marker, value in values.items():
            node = node.replace(marker, value)
        return node
    if isinstance(node, dict):
        return {key: fill_template(val, values) for key, val in node.items()}
    if isinstance(node, list):
        return [fill_template(val, values) for val in node]
    return node


def validate_output(payload: dict, apk: Path, text_min: str, text_pretty: str) -> None:
    """Valida el resultado: JSON valido, claves obligatorias y checksum coherente con el APK."""
    for text in (text_min, text_pretty):
        parsed = json.loads(text)  # lanza ValueError si no es JSON valido
        if parsed != payload:
            raise ValueError("el JSON serializado no coincide con el diccionario original")
    for key in REQUIRED_KEYS:
        if key not in payload:
            raise ValueError("falta la clave obligatoria " + key)
    if re.search(r"\{\{[A-Z_]+\}\}", text_min):
        raise ValueError("quedaron marcadores {{...}} sin sustituir")
    if payload[KEY_LEAVE_APPS] is not False:
        raise ValueError(KEY_LEAVE_APPS + " debe ser false")
    checksum = payload[KEY_CHECKSUM]
    if not CHECKSUM_RE.match(checksum) or "=" in checksum or "+" in checksum or "/" in checksum:
        raise ValueError("el checksum no es Base64 URL-safe sin relleno de 32 bytes")
    raw = base64.urlsafe_b64decode(checksum + "=")
    if len(raw) != 32:
        raise ValueError("el checksum no decodifica a 32 bytes")
    if raw != hashlib.sha256(apk.read_bytes()).digest():
        raise ValueError("el checksum no coincide con el SHA-256 del APK")
    if not COMPONENT_RE.match(payload[KEY_COMPONENT]):
        raise ValueError("componente no valido: " + payload[KEY_COMPONENT])


def write_png(data: str, target: Path) -> tuple[bool, str]:
    """Genera el PNG si la libreria `qrcode` esta disponible. Devuelve (ok, mensaje)."""
    try:
        import qrcode  # type: ignore
    except ImportError:
        return False, (
            "La libreria `qrcode` no esta instalada: no se genero el PNG. "
            "Instalala con:  python -m pip install \"qrcode[pil]\"   "
            "(o pega el JSON impreso arriba en cualquier generador de QR)."
        )
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4
    )
    qr.add_data(data)
    qr.make(fit=True)
    try:
        image = qr.make_image(fill_color="black", back_color="white")
        image.save(str(target))
    except Exception as first_error:  # Pillow ausente u otro fallo de la imagen
        try:
            from qrcode.image.pure import PyPNGImage  # type: ignore

            image = qr.make_image(image_factory=PyPNGImage)
            with target.open("wb") as handle:
                image.save(handle)
        except Exception as second_error:  # noqa: BLE001
            return False, (
                "No se pudo generar el PNG ({0}; {1}). Instala `pip install \"qrcode[pil]\"`."
            ).format(first_error, second_error)
    return True, "PNG escrito en " + str(target)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Genera el JSON/QR de aprovisionamiento de Device Owner (AVACOM LMS Student)."
    )
    parser.add_argument("--apk", required=True, help="ruta del APK ya firmado")
    parser.add_argument("--url", required=True, help="URL de descarga del APK (preferible https)")
    parser.add_argument("--out", required=True, help="carpeta de salida (se crea si no existe)")
    parser.add_argument("--component", default=DEFAULT_COMPONENT, help="paquete/clase del receptor; predeterminado: " + DEFAULT_COMPONENT)
    parser.add_argument("--template", default=None, help="plantilla JSON; predeterminado: device-owner-qr.template.json junto a este script")
    parser.add_argument("--wifi-ssid", default=None, help="SSID de la red Wi-Fi (opcional)")
    parser.add_argument("--wifi-password", default=None, help="clave Wi-Fi (opcional; '-' la pide por teclado sin mostrarla)")
    parser.add_argument("--wifi-security", default=None, choices=["WPA", "WEP", "NONE", "EAP"], help="tipo de seguridad; predeterminado WPA con clave, NONE sin ella")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    try:  # evita fallos de codificacion en consolas de Windows
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:  # noqa: BLE001
        pass

    args = parse_args(argv)

    apk = Path(args.apk)
    if not apk.is_file():
        fail("no existe el APK: " + str(apk), 2)
    if apk.stat().st_size == 0:
        fail("el APK esta vacio: " + str(apk), 2)
    if apk.suffix.lower() != ".apk":
        log("AVISO: el archivo no termina en .apk (" + apk.name + "); se calcula el checksum igualmente.")

    if not COMPONENT_RE.match(args.component):
        fail("componente no valido: " + args.component + " (formato paquete/clase)", 2)

    url = args.url.strip()
    if not (url.startswith("https://") or url.startswith("http://")):
        fail("la URL debe empezar por https:// (o http://): " + url, 2)
    if url.startswith("http://"):
        log("AVISO: la URL usa http://. Android descarga el APK y comprueba el checksum, pero https es lo recomendable.")

    if args.wifi_password is not None and not args.wifi_ssid:
        fail("--wifi-password requiere --wifi-ssid", 2)
    wifi_password = args.wifi_password
    if wifi_password == "-":
        wifi_password = getpass.getpass("Clave Wi-Fi (no se muestra): ")

    template_path = Path(args.template) if args.template else Path(__file__).with_name("device-owner-qr.template.json")
    if not template_path.is_file():
        fail("no existe la plantilla: " + str(template_path), 2)
    try:
        template = json.loads(template_path.read_text(encoding="utf-8"))
    except ValueError as error:
        fail("la plantilla no es JSON valido: " + str(error), 2)

    checksum = apk_checksum(apk)
    payload = fill_template(
        template,
        {
            "{{COMPONENT_NAME}}": args.component,
            "{{DOWNLOAD_LOCATION}}": url,
            "{{PACKAGE_CHECKSUM}}": checksum,
        },
    )
    payload[KEY_LEAVE_APPS] = False  # reduce lo que se puede abrir si el bloqueo fallara

    has_wifi_secret = False
    if args.wifi_ssid:
        payload[KEY_WIFI_SSID] = args.wifi_ssid
        if wifi_password:
            payload[KEY_WIFI_PASSWORD] = wifi_password
            has_wifi_secret = True
        security = args.wifi_security or ("WPA" if wifi_password else "NONE")
        payload[KEY_WIFI_SECURITY] = security
    elif args.wifi_security:
        fail("--wifi-security requiere --wifi-ssid", 2)

    text_min = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    text_pretty = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        validate_output(payload, apk, text_min, text_pretty)
    except ValueError as error:
        fail("la salida no paso la validacion: " + str(error))

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "device-owner-qr.json"
    png_path = out_dir / "device-owner-qr.png"
    json_path.write_text(text_pretty + "\n", encoding="utf-8")
    # Releer lo escrito y validarlo otra vez (lo que se lee es lo que se codificara en el QR).
    json.loads(json_path.read_text(encoding="utf-8"))

    log("Checksum SHA-256 (Base64 URL-safe, sin relleno): " + checksum)
    log("JSON escrito en " + str(json_path) + " (validado).")
    if has_wifi_secret:
        shown = json.loads(text_min)
        shown[KEY_WIFI_PASSWORD] = "********"
        log("AVISO: la clave Wi-Fi esta EN CLARO en el JSON y en el QR; trata la carpeta de salida como secreta.")
        log("JSON (clave oculta en pantalla):")
        log(json.dumps(shown, ensure_ascii=False, separators=(",", ":")))
    else:
        log("JSON que codifica el QR:")
        log(text_min)

    ok, message = write_png(text_min, png_path)
    log(("OK: " if ok else "AVISO: ") + message)

    log("")
    log("Siguiente paso: en la primera pantalla del asistente de una tableta recien restablecida,")
    log("toca seis veces y escanea el QR. La tableta descargara el APK, comprobara el checksum")
    log("y se convertira en Device Owner. NO PROBADO EN HARDWARE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

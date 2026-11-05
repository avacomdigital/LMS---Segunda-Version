#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aprovisionamiento MASIVO del kiosco de examen en tabletas Android 14 con la Android Management API (AMAPI) de Google.

Es la vía oficial: la tableta queda como dispositivo dedicado (Device Owner = Android Device Policy), nuestra app se instala desde Google Play
administrado y se fija con Lock Task por POLÍTICA. Aquí no se usa `adb set-device-owner` ni ningún QR propio.

Subcomandos (en el orden de uso):

  signup-url         1. Crea la URL con la que el administrador del cliente registra su empresa en Google (una sola vez).
  create-enterprise  2. Crea la empresa con el token que Google devuelve al volver de esa URL (una sola vez).
  apply-policy       3. Crea o actualiza la política de kiosco de examen (se puede repetir; es idempotente).
  enrollment-token   4. Crea el token de inscripción y escribe lo que necesita cada vía: QR (descargar y escanear) y zero-touch (JSON de DPC extras).
  devices            5. Informa el estado real de la flota: inscritas, conformes con la política, versión de Android y de la app.

Todos admiten --dry-run: imprimen la petición que harían y NO llaman a Google ni escriben archivos.

Requisitos (solo para el modo real): `pip install google-auth requests` y, opcional, `pip install "qrcode[pil]"` para el PNG del QR.
Credenciales: cuenta de servicio de un proyecto de Google Cloud con la API «Android Management» habilitada; ruta del JSON en
GOOGLE_APPLICATION_CREDENTIALS (o --credentials). El JSON de la cuenta de servicio es un secreto: no se sube al repositorio.

NO PROBADO CONTRA GOOGLE: la lógica pura (política, QR, resumen de flota) tiene pruebas en test_kiosk_fleet.py; las llamadas HTTP no se ejecutaron
contra una empresa real. Los nombres de campo salen de la referencia REST vigente de AMAPI (consultada el 2026-11-03).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

API = "https://androidmanagement.googleapis.com/v1"
SCOPE = "https://www.googleapis.com/auth/androidmanagement"
PAQUETE_STUDENT = "com.avacom.lms.student"
VARIABLE_CLAVE_WIFI = "AVACOM_WIFI_PASSWORD"
CLAVE_TOKEN_ZERO_TOUCH = "com.google.android.apps.work.clouddpc.EXTRA_ENROLLMENT_TOKEN"
EXTRA_ADMIN = "android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE"
ANDROID_MINIMO = 14


# ======================================================================================================= lógica pura (con pruebas)

def construir_politica(paquete: str = PAQUETE_STUDENT, *, tipo_instalacion: str = "REQUIRED_FOR_SETUP",
                       ventana_actualizacion: tuple[int, int] | None = (120, 240), wifi: dict | None = None) -> dict:
    """
    La política de dispositivo dedicado para el examen. Una sola app con el rol KIOSK (queda como pantalla de inicio y se admite en Lock Task);
    el resto de lo que antes hacía nuestro código con SetLockTaskFeatures lo decide aquí `kioskCustomization`.

    `tipo_instalacion` REQUIRED_FOR_SETUP: la tableta no termina de configurarse hasta tener la app instalada (no queda una tableta abierta sin la app).
    `ventana_actualizacion` (minutos desde medianoche, hora local del equipo): las actualizaciones del sistema ocurren de madrugada, nunca en clase.
    """
    politica = {
        "applications": [{
            "packageName": paquete,
            "installType": tipo_instalacion,
            "roles": [{"roleType": "KIOSK"}],
            "userControlSettings": "USER_CONTROL_DISALLOWED",
            "autoUpdateMode": "AUTO_UPDATE_DEFAULT",
        }],
        "playStoreMode": "WHITELIST",
        "kioskCustomLauncherEnabled": False,   # la propia app es el kiosco (rol KIOSK); no se reemplaza el launcher con el genérico de Google
        "kioskCustomization": {
            "powerButtonActions": "POWER_BUTTON_BLOCKED",                      # sin menú de apagado desde la app; el apagado forzado por hardware sigue existiendo
            "systemErrorWarnings": "ERROR_AND_WARNINGS_MUTED",
            "systemNavigation": "NAVIGATION_DISABLED",                         # sin Inicio, Recientes ni Atrás del sistema
            "statusBar": "NOTIFICATIONS_AND_SYSTEM_INFO_DISABLED",
            "deviceSettings": "SETTINGS_ACCESS_BLOCKED",
        },
        "keyguardDisabled": True,
        "screenCaptureDisabled": True,
        "addUserDisabled": True,
        "modifyAccountsDisabled": True,
        "factoryResetDisabled": True,
        "safeBootDisabled": True,
        "installUnknownSourcesAllowed": False,
        "debuggingFeaturesAllowed": False,
        "outgoingCallsDisabled": True,
        "smsDisabled": True,
        "statusReportingSettings": {
            "applicationReportsEnabled": True,   # sin esto `devices` no puede decir qué versión de la app tiene cada tableta
            "softwareInfoEnabled": True,
            "networkInfoEnabled": True,
            "hardwareStatusEnabled": True,
            "deviceSettingsEnabled": True,
        },
    }
    if ventana_actualizacion:
        inicio, fin = ventana_actualizacion
        if not (0 <= inicio < 1440 and 0 <= fin < 1440 and inicio != fin):
            raise ValueError("La ventana de actualización son dos minutos del día (0-1439) distintos entre sí.")
        politica["systemUpdate"] = {"type": "WINDOWED", "startMinutes": inicio, "endMinutes": fin}
    if wifi is not None:
        politica["openNetworkConfiguration"] = validar_wifi(wifi)   # la clave viaja en la política: nunca se imprime en --dry-run
    return politica


SEGURIDAD_ONC = ("None", "WEP-PSK", "WPA-PSK", "WPA-EAP")


def validar_wifi(onc) -> dict:
    """
    Valida la `openNetworkConfiguration` (formato ONC de Chrome OS que usa AMAPI) para redes Wi-Fi: un objeto con `NetworkConfigurations`, cada una con
    GUID, Name, Type «WiFi» y WiFi.SSID; con seguridad distinta de None, WiFi.Passphrase. Devuelve la misma estructura o lanza ValueError.
    """
    if not isinstance(onc, dict):
        raise ValueError("El Wi-Fi debe ser un objeto JSON (openNetworkConfiguration).")
    redes = onc.get("NetworkConfigurations")
    if not isinstance(redes, list) or not redes:
        raise ValueError("El Wi-Fi necesita una lista NetworkConfigurations con al menos una red.")
    for i, red in enumerate(redes, 1):
        if not isinstance(red, dict) or red.get("Type") != "WiFi":
            raise ValueError(f"La red {i} debe tener Type = «WiFi».")
        for campo in ("GUID", "Name"):
            if not str(red.get(campo, "")).strip():
                raise ValueError(f"La red {i} no tiene {campo}.")
        wifi = red.get("WiFi")
        if not isinstance(wifi, dict) or not str(wifi.get("SSID", "")).strip():
            raise ValueError(f"La red {i} no tiene WiFi.SSID.")
        seguridad = wifi.get("Security", "None")
        if seguridad not in SEGURIDAD_ONC:
            raise ValueError(f"La red {i} tiene Security «{seguridad}»; usa una de {', '.join(SEGURIDAD_ONC)}.")
        if seguridad in ("WEP-PSK", "WPA-PSK") and not wifi.get("Passphrase"):
            raise ValueError(f"La red {i} usa {seguridad} y no trae WiFi.Passphrase.")
    return onc


def ocultar_secretos(valor):
    """Copia del JSON con toda `Passphrase`/`Password` reemplazada por ***: lo que se puede imprimir (--dry-run) sin filtrar la clave."""
    if isinstance(valor, dict):
        return {k: ("***" if k in ("Passphrase", "Password") and v else ocultar_secretos(v)) for k, v in valor.items()}
    if isinstance(valor, list):
        return [ocultar_secretos(v) for v in valor]
    return valor


def duracion_segundos(texto: str) -> str:
    """'90m' · '12h' · '7d' · '3600s' → '3600s' (el formato que pide AMAPI). Mínimo 1 minuto."""
    texto = texto.strip().lower()
    unidades = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if len(texto) < 2 or texto[-1] not in unidades or not texto[:-1].isdigit():
        raise ValueError(f"Duración no válida: «{texto}». Usa un número y s, m, h o d (por ejemplo 7d).")
    segundos = int(texto[:-1]) * unidades[texto[-1]]
    if segundos < 60:
        raise ValueError("AMAPI exige al menos 1 minuto de vigencia en el token.")
    return f"{segundos}s"


def armar_qr(qr_google: str, *, ssid: str | None = None, clave_wifi: str | None = None, seguridad: str = "WPA") -> dict:
    """
    El JSON del QR: el que devolvió Google más, si se pide, la red Wi-Fi a la que la tableta debe unirse ANTES de descargar nada (extras estándar de
    aprovisionamiento de Android). Con clave, el QR y su JSON son secretos.
    """
    carga = json.loads(qr_google)
    if ssid:
        carga["android.app.extra.PROVISIONING_WIFI_SSID"] = ssid
        carga["android.app.extra.PROVISIONING_WIFI_SECURITY_TYPE"] = seguridad
        if clave_wifi:
            carga["android.app.extra.PROVISIONING_WIFI_PASSWORD"] = clave_wifi
    return carga


def extras_zero_touch(valor_token: str) -> dict:
    """Lo que se pega en «DPC extras» de la configuración de zero-touch (portal de zero-touch) cuando el DPC elegido es Android Device Policy."""
    return {EXTRA_ADMIN: {CLAVE_TOKEN_ZERO_TOUCH: valor_token}}


def resumir_flota(dispositivos: list[dict], paquete: str = PAQUETE_STUDENT) -> dict:
    """
    Lo que le importa al técnico del aula: ¿cuántas tabletas están listas para examen y cuáles no, y por qué? «Lista» = activa, conforme con la política,
    Android 14 o superior y con la app instalada. Cada tableta no lista trae sus motivos.
    """
    filas, listas = [], 0
    for d in dispositivos:
        motivos = []
        if d.get("state") != "ACTIVE":
            motivos.append(f"estado {d.get('state', 'desconocido')}")
        if not d.get("policyCompliant", False):
            motivos.append("no cumple la política")
        version = str((d.get("softwareInfo") or {}).get("androidVersion", "")).split(".")[0]
        if not version.isdigit() or int(version) < ANDROID_MINIMO:
            motivos.append(f"Android {version or 'desconocido'} (se exige {ANDROID_MINIMO}+)")
        app = next((a for a in d.get("applicationReports", []) if a.get("packageName") == paquete), None)
        if app is None:
            motivos.append("la app no está instalada o no informó")
        elif app.get("state") not in (None, "INSTALLED"):
            motivos.append(f"app {app.get('state')}")
        hardware = d.get("hardwareInfo") or {}
        filas.append({
            "nombre": d.get("name", ""),
            "serie": hardware.get("serialNumber", ""),
            "modelo": hardware.get("model", ""),
            "android": version,
            "version_app": (app or {}).get("versionName", ""),
            "ultimo_informe": d.get("lastStatusReportTime", ""),
            "lista": not motivos,
            "motivos": motivos,
        })
        listas += not motivos
    return {"total": len(filas), "listas": listas, "no_listas": len(filas) - listas, "dispositivos": filas}


# ======================================================================================================= llamadas a Google

class ClienteAmapi:
    def __init__(self, credenciales: str | None):
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import AuthorizedSession
        except ImportError:
            sys.exit("Falta google-auth y requests: pip install google-auth requests")
        ruta = credenciales or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not ruta or not Path(ruta).is_file():
            sys.exit("Indica el JSON de la cuenta de servicio con --credentials o con GOOGLE_APPLICATION_CREDENTIALS.")
        creds = service_account.Credentials.from_service_account_file(ruta, scopes=[SCOPE])
        self.sesion = AuthorizedSession(creds)

    def llamar(self, metodo: str, ruta: str, *, params: dict | None = None, cuerpo: dict | None = None) -> dict:
        respuesta = self.sesion.request(metodo, f"{API}/{ruta}", params=params, json=cuerpo, timeout=60)
        if not respuesta.ok:
            sys.exit(f"AMAPI {metodo} {ruta} → HTTP {respuesta.status_code}: {respuesta.text[:800]}")
        return respuesta.json() if respuesta.content else {}


def mostrar(titulo: str, metodo: str, ruta: str, params: dict | None, cuerpo: dict | None) -> None:
    print(f"[DRY-RUN] {titulo}")
    print(f"  {metodo} {API}/{ruta}" + (f"  params={json.dumps(params)}" if params else ""))
    if cuerpo is not None:
        print("  cuerpo:\n" + "\n".join("    " + linea for linea in json.dumps(cuerpo, indent=2, ensure_ascii=False).splitlines()))


def ruta_empresa(args) -> str:
    empresa = args.enterprise
    return empresa if empresa.startswith("enterprises/") else f"enterprises/{empresa}"


# ======================================================================================================= subcomandos

def cmd_signup_url(args) -> int:
    params = {"projectId": args.project, "callbackUrl": args.callback}
    if args.dry_run:
        mostrar("Crear la URL de registro de la empresa", "POST", "signupUrls", params, None)
        return 0
    r = ClienteAmapi(args.credentials).llamar("POST", "signupUrls", params=params)
    print("Abre esta URL con la cuenta de Google del administrador del cliente y acepta los términos:\n  " + r["url"])
    print("\nGuarda este nombre (lo pide create-enterprise):\n  " + r["name"])
    print("\nAl terminar, Google redirige a la callback con ?enterpriseToken=... en la URL: ese es el token del paso 2.")
    return 0


def cmd_create_enterprise(args) -> int:
    params = {"projectId": args.project, "signupUrlName": args.signup_url_name, "enterpriseToken": args.enterprise_token}
    cuerpo = {"enterpriseDisplayName": args.name}
    if args.dry_run:
        mostrar("Crear la empresa", "POST", "enterprises", params, cuerpo)
        return 0
    r = ClienteAmapi(args.credentials).llamar("POST", "enterprises", params=params, cuerpo=cuerpo)
    print("Empresa creada: " + r["name"])
    return 0


def cmd_apply_policy(args) -> int:
    try:
        wifi = json.loads(Path(args.wifi_json).read_text(encoding="utf-8-sig")) if args.wifi_json else None
    except (OSError, json.JSONDecodeError) as ex:
        raise ValueError(f"No se pudo leer el Wi-Fi de {args.wifi_json}: {ex}") from ex
    ventana = None if args.sin_ventana_de_actualizacion else (args.ventana_inicio, args.ventana_fin)
    politica = construir_politica(args.package, tipo_instalacion=args.install_type, ventana_actualizacion=ventana, wifi=wifi)
    ruta = f"{ruta_empresa(args)}/policies/{args.policy}"
    if args.dry_run:
        mostrar("Crear o actualizar la política de kiosco de examen", "PATCH", ruta, None, ocultar_secretos(politica))
        return 0
    r = ClienteAmapi(args.credentials).llamar("PATCH", ruta, cuerpo=politica)
    print(f"Política aplicada: {r.get('name')} (versión {r.get('version', '?')}).")
    print("Las tabletas ya inscritas la reciben solas; las nuevas la reciben al inscribirse.")
    return 0


def cmd_enrollment_token(args) -> int:
    ruta = f"{ruta_empresa(args)}/enrollmentTokens"
    cuerpo = {
        "policyName": f"{ruta_empresa(args)}/policies/{args.policy}",
        "duration": duracion_segundos(args.duration),
        "oneTimeOnly": args.one_time,
        "allowPersonalUsage": "PERSONAL_USAGE_DISALLOWED",
    }
    if args.etiqueta:
        cuerpo["additionalData"] = args.etiqueta[:1024]   # aparece en cada tableta inscrita: sirve para saber de qué aula vino
    clave_wifi = os.environ.get(VARIABLE_CLAVE_WIFI) if args.wifi_ssid else None
    if args.dry_run:
        mostrar("Crear el token de inscripción", "POST", ruta, None, cuerpo)
        if args.wifi_ssid:
            clave = f"con la clave de {VARIABLE_CLAVE_WIFI}" if clave_wifi else "sin clave"
            print(f"  (el QR llevará la red «{args.wifi_ssid}» {clave})")
        return 0
    token = ClienteAmapi(args.credentials).llamar("POST", ruta, cuerpo=cuerpo)
    salida = Path(args.out)
    salida.mkdir(parents=True, exist_ok=True)
    qr = armar_qr(token["qrCode"], ssid=args.wifi_ssid, clave_wifi=clave_wifi, seguridad=args.wifi_security)
    (salida / "inscripcion-qr.json").write_text(json.dumps(qr, indent=2), encoding="utf-8")
    (salida / "zero-touch-dpc-extras.json").write_text(json.dumps(extras_zero_touch(token["value"]), indent=2), encoding="utf-8")
    png = escribir_png(salida / "inscripcion-qr.png", json.dumps(qr))
    print(f"Token creado; vence {token.get('expirationTimestamp')}.")
    print(f"  QR (JSON): {salida / 'inscripcion-qr.json'}")
    print(f"  QR (PNG):  {png if png else 'no generado (pip install \"qrcode[pil]\"); pega el JSON en cualquier generador de QR'}")
    print(f"  Zero-touch: {salida / 'zero-touch-dpc-extras.json'}  → pégalo en «DPC extras» de la configuración del portal, con DPC = Android Device Policy")
    print("\nESTOS ARCHIVOS SON SECRETOS (quien los tenga inscribe tabletas en tu empresa; con Wi-Fi llevan además la clave). No los subas al repositorio.")
    return 0


def escribir_png(destino: Path, contenido: str) -> Path | None:
    try:
        import qrcode
    except ImportError:
        return None
    qrcode.make(contenido).save(str(destino))
    return destino


def cmd_devices(args) -> int:
    ruta = f"{ruta_empresa(args)}/devices"
    if args.dry_run:
        mostrar("Listar los dispositivos de la empresa (con paginación)", "GET", ruta, {"pageSize": 100, "view": "FULL"}, None)
        return 0
    cliente, lista, pagina = ClienteAmapi(args.credentials), [], None
    while True:
        params = {"pageSize": 100, "view": "FULL", **({"pageToken": pagina} if pagina else {})}
        r = cliente.llamar("GET", ruta, params=params)
        lista += r.get("devices", [])
        pagina = r.get("nextPageToken")
        if not pagina:
            break
    resumen = resumir_flota(lista, args.package)
    if args.json:
        print(json.dumps(resumen, indent=2, ensure_ascii=False))
    else:
        print(f"Tabletas: {resumen['total']} · listas para examen: {resumen['listas']} · NO listas: {resumen['no_listas']}")
        for fila in resumen["dispositivos"]:
            if not fila["lista"]:
                print(f"  ✗ {fila['serie'] or fila['nombre']} ({fila['modelo']}): {'; '.join(fila['motivos'])}")
    return 0 if resumen["no_listas"] == 0 else 1


# ======================================================================================================= línea de comandos

def crear_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Kiosco de examen masivo con la Android Management API (Android 14).")
    p.add_argument("--credentials", help="JSON de la cuenta de servicio (o GOOGLE_APPLICATION_CREDENTIALS)")
    p.add_argument("--dry-run", action="store_true", help="imprime las peticiones y no llama a Google ni escribe archivos")
    sub = p.add_subparsers(dest="comando", required=True)

    s = sub.add_parser("signup-url", help="1. URL de registro de la empresa")
    s.add_argument("--project", required=True, help="id del proyecto de Google Cloud")
    s.add_argument("--callback", required=True, help="URL a la que Google devuelve el enterpriseToken")
    s.set_defaults(f=cmd_signup_url)

    s = sub.add_parser("create-enterprise", help="2. Crear la empresa")
    s.add_argument("--project", required=True)
    s.add_argument("--signup-url-name", required=True, help="el `name` que devolvió signup-url")
    s.add_argument("--enterprise-token", required=True, help="el enterpriseToken de la callback")
    s.add_argument("--name", required=True, help="nombre visible de la empresa (por ejemplo el colegio)")
    s.set_defaults(f=cmd_create_enterprise)

    def comunes(s):
        s.add_argument("--enterprise", required=True, help="enterprises/LC0xxxx o solo LC0xxxx")
        s.add_argument("--package", default=PAQUETE_STUDENT)

    s = sub.add_parser("apply-policy", help="3. Crear o actualizar la política de kiosco")
    comunes(s)
    s.add_argument("--policy", default="aula-examen")
    s.add_argument("--install-type", default="REQUIRED_FOR_SETUP", choices=["REQUIRED_FOR_SETUP", "FORCE_INSTALLED"])
    s.add_argument("--ventana-inicio", type=int, default=120, help="minuto del día (hora local de la tableta) en que empiezan las actualizaciones; 120 = 02:00")
    s.add_argument("--ventana-fin", type=int, default=240, help="minuto del día en que terminan; 240 = 04:00")
    s.add_argument("--sin-ventana-de-actualizacion", action="store_true")
    s.add_argument("--wifi-json", help="archivo con la openNetworkConfiguration (Wi-Fi) que la política debe empujar a las tabletas")
    s.set_defaults(f=cmd_apply_policy)

    s = sub.add_parser("enrollment-token", help="4. Token de inscripción: QR y zero-touch")
    comunes(s)
    s.add_argument("--policy", default="aula-examen")
    s.add_argument("--duration", default="7d", help="vigencia del token (7d para un QR de aula; para zero-touch usa una larga, por ejemplo 365d)")
    s.add_argument("--one-time", action="store_true", help="el token sirve para una sola tableta (no lo uses para 50)")
    s.add_argument("--etiqueta", help="texto libre que queda en cada tableta inscrita (por ejemplo el aula)")
    s.add_argument("--wifi-ssid", help="red a la que la tableta se une antes de descargar (la clave va en la variable " + VARIABLE_CLAVE_WIFI + ")")
    s.add_argument("--wifi-security", default="WPA", choices=["WPA", "WEP", "NONE"])
    s.add_argument("--out", default="salida-flota", help="carpeta de salida (en .gitignore)")
    s.set_defaults(f=cmd_enrollment_token)

    s = sub.add_parser("devices", help="5. Estado de la flota (código de salida 1 si alguna tableta no está lista)")
    comunes(s)
    s.add_argument("--json", action="store_true")
    s.set_defaults(f=cmd_devices)
    return p


def main(argv: list[str] | None = None) -> int:
    args = crear_parser().parse_args(argv)
    try:
        return args.f(args)
    except ValueError as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

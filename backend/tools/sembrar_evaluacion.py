"""
Siembra un nodo EN MARCHA con lo necesario para probar a mano (o con UI Automation) la evaluación de MOD-010: organización, un grupo, un profesor, N alumnos y un
examen del curso de ejemplo aplicado al grupo. Todo por la API, igual que lo haría OPS. Sólo usa la biblioteca estándar.

    set AVACOM_LMS_DB=%TEMP%\\copia-de-db.sqlite3
    set AVACOM_AULA_PERMITIR_EJEMPLO=1      (el curso de ejemplo está apagado en un nodo real; aquí evita depender de la biblioteca)
    .venv\\Scripts\\python manage.py migrate
    .venv\\Scripts\\python manage.py runserver 127.0.0.1:8010 --noreload
    .venv\\Scripts\\python tools\\sembrar_evaluacion.py --base http://127.0.0.1:8010 --nivel supervisado --alumnos 3

Imprime un JSON con los identificadores (grupo, profesor, alumnos, asignación). Es idempotente a medias: si el nodo ya está instalado sigue con el resto y reutiliza lo que encuentre.
NUNCA lo apuntes al nodo real de un aula: crea personas y un examen de prueba.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

CURSO = "avacom.co.lower-secondary.6.science.states-of-matter"
EXAMEN = "l3-exam"
ADMIN_DNI, ADMIN_CLAVE = "1042888795", "Rectoria.2026!"
DOCENTE_DNI, DOCENTE_CLAVE = "80.123.456", "Docente.2026!"
NOMBRES = ["Juan P.", "Ana Ruiz", "Luis Mora", "Eva Soto", "Pablo Gil", "Marta Paz", "Hugo Rey", "Lola Vera"]


def llamar(base: str, metodo: str, ruta: str, cuerpo: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    cabeceras = {"Content-Type": "application/json"}
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    peticion = urllib.request.Request(base + ruta, data=datos, method=metodo, headers=cabeceras)
    try:
        with urllib.request.urlopen(peticion, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def iniciar_sesion(base: str, identificador: str, secreto: str) -> str:
    estado, cuerpo = llamar(base, "POST", "/api/acceso/sesiones/", {"identificador": identificador, "secreto": secreto})
    if estado != 200:
        raise SystemExit(f"No se pudo iniciar sesión como {identificador}: {estado} {cuerpo}")
    return cuerpo["token"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", default="http://127.0.0.1:8010")
    p.add_argument("--nivel", default="supervisado", choices=["abierto", "supervisado", "controlado"])
    p.add_argument("--alumnos", type=int, default=3)
    p.add_argument("--tiempo-seg", type=int, default=0, help="límite fijo en segundos (0 = el del examen)")
    p.add_argument("--sin-asignar", action="store_true", help="no crea la asignación (sólo organización, grupo, profesor y alumnos)")
    a = p.parse_args()
    base = a.base.rstrip("/")

    estado, cuerpo = llamar(base, "POST", "/api/acceso/instalacion/", {
        "organizacion": {"codigo": "IE-PRUEBA", "nombre": "IE de pruebas", "pais": "CO", "idioma": "es", "locale": "es-CO"},
        "administrador": {"alias": "Rectoría", "nombres": "Ana", "apellidos": "Pérez", "dni": ADMIN_DNI, "password": ADMIN_CLAVE}})
    if estado not in (201, 409):
        raise SystemExit(f"No se pudo instalar el nodo: {estado} {cuerpo}")
    admin = iniciar_sesion(base, ADMIN_DNI, ADMIN_CLAVE)

    estado, grupo = llamar(base, "POST", "/api/acceso/grupos/", {"codigo": "8A", "nombre": "Octavo A", "periodo": "2026"}, admin)
    if estado == 409:
        grupos = llamar(base, "GET", "/api/acceso/grupos/", None, admin)[1]
        grupo = next(g for g in (grupos.get("grupos") or grupos.get("resultados") or grupos) if g.get("codigo") == "8A")
    elif estado != 201:
        raise SystemExit(f"No se pudo crear el grupo: {estado} {grupo}")

    estado, docente = llamar(base, "POST", "/api/acceso/usuarios/", {
        "rol": "TEACHER", "alias": "Prof. Gómez", "persona": {"nombres": "Luis", "apellidos": "Gómez"},
        "identificadores": [{"tipo": "DNI", "valor": DOCENTE_DNI, "es_login": True}], "secreto": DOCENTE_CLAVE, "secreto_definitivo": True}, admin)
    if estado == 201:
        llamar(base, "POST", f"/api/acceso/grupos/{grupo['id']}/miembros/", {"usuario_id": docente["id"], "papel": "DOCENTE"}, admin)
    profesor = docente.get("id") if estado == 201 else None

    alumnos = []
    for n in range(a.alumnos):
        nombre = NOMBRES[n % len(NOMBRES)]
        estado, alumno = llamar(base, "POST", "/api/acceso/usuarios/", {
            "rol": "STUDENT", "alias": nombre, "persona": {"nombres": nombre.split()[0], "apellidos": "Prueba", "fecha_nacimiento": "2012-04-09"},
            "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": f"9100{n:02d}", "es_login": True}], "secreto": "573920", "secreto_definitivo": True,
            "grupo_id": grupo["id"]}, admin)
        alumnos.append({"id": alumno.get("id"), "alias": nombre, "codigo": f"9100{n:02d}", "creado": estado == 201})

    salida = {"base": base, "grupo": {"id": grupo["id"], "nombre": grupo.get("nombre")}, "profesor_id": profesor, "alumnos": alumnos}
    if not a.sin_asignar:
        if not profesor:
            raise SystemExit("El profesor ya existía: pasa --sin-asignar y asigna desde OPS, o usa un nodo nuevo.")
        cuerpo = {"fuente": "ejemplo", "curso_ref": CURSO, "objeto_ref": EXAMEN, "alcance": "grupo", "grupo_id": grupo["id"], "nivel_examen": a.nivel,
                  "iniciar": True, "actor": profesor, "actor_rotulo": "Prof. Gómez"}
        if a.tiempo_seg:
            cuerpo["tiempo"] = {"modo": "fijo", "limite_seg": a.tiempo_seg}
        estado, asignacion = llamar(base, "POST", "/api/evaluacion/asignaciones/", cuerpo)
        if estado != 201:
            raise SystemExit(f"No se pudo aplicar el examen: {estado} {asignacion}")
        salida["asignacion"] = {"id": asignacion["id"], "titulo": asignacion["titulo"], "nivel": asignacion["nivel_examen"], "estado": asignacion["estado"]}
    print(json.dumps(salida, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"Falló la siembra: {e}", file=sys.stderr)
        raise SystemExit(1)

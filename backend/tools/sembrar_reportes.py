"""
Siembra un nodo EN MARCHA para probar a mano (o con UI Automation) los Reportes de MOD-013: sobre lo que ya dejó `sembrar_gradebook.py` (organización, grupos 8A de secundaria y P1 de
preescolar, el profesor, alumnos, un examen por grupo con lo que cada alumno hizo) agrega tres alumnos a 8A (siete en total, así el umbral de privacidad no recorta nada), dos CLASES
cerradas de 8A por las rutas reales del aula —una completa y otra con una tableta que se quedó sin conexión: «Incompleto»—, y una tarea de estudio. Todo por la API, igual que lo harían
OPS y Student. Sólo usa la biblioteca estándar.

Necesita el curso de ejemplo del aula (`AVACOM_AULA_PERMITIR_EJEMPLO=1`; sólo para pruebas y desarrollo) además de lo que pide `sembrar_gradebook.py`:

    set AVACOM_LMS_DB=%TEMP%\\copia-de-db.sqlite3
    set AVACOM_AULA_PERMITIR_EJEMPLO=1
    set AVACOM_LMS_EXIGIR_SESION=0
    .venv\\Scripts\\python manage.py migrate
    .venv\\Scripts\\python -m tools.host_contenido_v2_con_examenes %TEMP%\\link-pruebas.json
    set AVACOM_CONTENIDO_ENLACE_V2=%TEMP%\\link-pruebas.json
    .venv\\Scripts\\python manage.py runserver 127.0.0.1:8010 --noreload
    .venv\\Scripts\\python tools\\sembrar_gradebook.py --base http://127.0.0.1:8010 > %TEMP%\\semilla-gradebook.json
    .venv\\Scripts\\python -m tools.sembrar_reportes --base http://127.0.0.1:8010 --semilla %TEMP%\\semilla-gradebook.json
    .venv\\Scripts\\python -m tools.sembrar_reportes --base http://127.0.0.1:8010 --semilla %TEMP%\\semilla-gradebook.json --solo-roles     (opcional: otro profesor, técnico y Reportes)

Lo que queda (la escena para mirar los reportes):

    8A · siete alumnos · modo calificaciones (escala «co-1-5»)
        Clase 1 (completa)    Juan 5/5 · Ana 4/5 · Luis 1/5 · Carlos 5/5 · Diana 3/5 · Mateo 5/5 · Eva NO fue (falta a las dos clases: necesita atención)
        Clase 2 (incompleta)  Juan 5/5 · Ana 5/5 · Carlos que perdió la conexión al cerrar y no alcanzó a enviar lo suyo → «1 tableta aún no sincroniza»
        Estudio               una lección asignada al grupo
    P1 · preescolar · modo simple (no tiene clases: sirve para ver «Sin clases todavía»)

Imprime un JSON con los identificadores. NUNCA lo apuntes al nodo real de un aula: crea personas, clases y tareas de prueba.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from tools.sembrar_gradebook import (CURSO, DOCENTE_CLAVE, DOCENTE_DNI, ADMIN_CLAVE, ADMIN_DNI, PIN_MAESTRO, exigir, iniciar_sesion, llamar, preguntas_del_manifiesto, respuesta)

LECCION = "l1-three-states"
ACTIVIDAD = "l1-activity"
PREGUNTAS = ["l1-act-q1", "l1-act-q2", "l1-act-q3", "l1-act-q4", "l1-act-q5"]
AULA = "/api/aula"


ROLES = {
    "otro_docente": {"rol": "TEACHER", "alias": "Prof. Ruiz", "dni": "90.444.555", "clave": "Docente2.2026!"},
    "tecnico": {"rol": "TECHNICIAN", "alias": "Técnico AVACOM", "dni": "70.111.222", "clave": "Tecnico.2026!Aula"},
    "reportes": {"rol": "REPORTS", "alias": "Reportes", "dni": "60.222.333", "clave": "Reportes.2026!Aula"},
}


def crear_roles(base: str, admin: str) -> None:
    """El otro profesor (con su grupo 9B, que no es del primero), el técnico y el usuario de Reportes: para ver qué ve cada rol en OPS con la sesión obligatoria."""
    estado, g9b = llamar(base, "POST", "/api/acceso/grupos/", {"codigo": "9B", "nombre": "Noveno B", "periodo": "2026", "nivel_clave": "secundaria"}, admin)
    exigir(estado, g9b, (201,), "No se pudo crear el grupo 9B")
    for clave, r in ROLES.items():
        estado, u = llamar(base, "POST", "/api/acceso/usuarios/", {"rol": r["rol"], "alias": r["alias"], "persona": {"nombres": r["alias"], "apellidos": "Prueba"},
                                                                   "identificadores": [{"tipo": "DNI", "valor": r["dni"], "es_login": True}], "secreto": r["clave"], "secreto_definitivo": True}, admin)
        exigir(estado, u, (201,), f"No se pudo crear a {r['alias']}")
        r["id"] = u["id"]
        if clave == "otro_docente":
            exigir(*llamar(base, "POST", f"/api/acceso/grupos/{g9b['id']}/miembros/", {"usuario_id": u["id"], "papel": "DOCENTE"}, admin), (201,), "No se pudo asignar el grupo 9B")
    print(json.dumps({"base": base, "grupo_9B": g9b["id"], "roles": ROLES}, ensure_ascii=False, indent=2))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", default="http://127.0.0.1:8010")
    p.add_argument("--semilla", required=True, help="el JSON que imprimió sembrar_gradebook.py")
    p.add_argument("--solo-roles", action="store_true", help="no siembra clases: sólo crea al otro profesor (con su grupo 9B), al técnico y al usuario de Reportes, para probar los permisos por rol")
    a = p.parse_args()
    base = a.base.rstrip("/")
    semilla = json.loads(pathlib.Path(a.semilla).read_text(encoding="utf-8-sig"))
    profesor = semilla["profesor"]["id"]
    g8a = semilla["grupos"]["8A"]
    alumnos = semilla["alumnos"]
    admin = iniciar_sesion(base, ADMIN_DNI, ADMIN_CLAVE, PIN_MAESTRO)
    manifiesto = preguntas_del_manifiesto()

    if a.solo_roles:
        crear_roles(base, admin)
        return

    # --- tres alumnos más en 8A: siete en total (el umbral de privacidad, si se activa, no los recorta)
    for n, nombre in enumerate(["Carlos Vega", "Diana Rojas", "Mateo León"], start=20):
        estado, al = llamar(base, "POST", "/api/acceso/usuarios/", {
            "rol": "STUDENT", "alias": nombre, "persona": {"nombres": nombre.split()[0], "apellidos": "Prueba", "fecha_nacimiento": "2012-06-11"},
            "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": f"9300{n:02d}", "es_login": True}], "secreto": "573920", "secreto_definitivo": True, "grupo_id": g8a}, admin)
        exigir(estado, al, (201,), f"No se pudo crear a {nombre}")
        hw = f"hw-rp-{n}"
        llamar(base, "POST", "/api/dispositivos/", {"identificador_hw": hw, "nombre": f"Tableta de {nombre}", "capacidad_control": "supervisado"})
        alumnos[nombre] = {"id": al["id"], "grupo": "8A", "hw": hw}

    def clase() -> dict:
        estado, s = llamar(base, "POST", f"{AULA}/sesiones/", {"via": "leccion", "curso_ref": CURSO, "leccion_ref": LECCION, "fuente": "biblioteca", "profesor_id": profesor,
                                                              "profesor_rotulo": "Prof. Gómez", "superficie": "pantalla", "grupo_id": g8a})
        return exigir(estado, s, (201,), "No se pudo abrir la clase")

    def unir(s: dict, nombre: str) -> str:
        al = alumnos[nombre]
        estado, r = llamar(base, "POST", f"{AULA}/sesiones/unirse/", {"codigo_union": s["codigo_union"], "persona_id": al["id"], "persona_rotulo": nombre, "dispositivo": al["hw"]})
        return exigir(estado, r, (200, 201), f"{nombre} no pudo unirse")["participante"]["id"]

    def lanzar(s: dict) -> dict:
        estado, d = llamar(base, "POST", f"{AULA}/sesiones/{s['id']}/distribuciones/", {"clase": "actividad", "objeto_ref": ACTIVIDAD, "intentos_permitidos": 2})
        return exigir(estado, d, (201,), "No se pudo lanzar la actividad")

    def contestar(s: dict, d: dict, pid: str, aciertos: int, entregar: bool = True) -> None:
        respuestas = [{"pregunta_ref": ref, "secuencia": 1, "respuesta": respuesta(manifiesto[ref], i < aciertos)} for i, ref in enumerate(PREGUNTAS)]
        ruta = f"{AULA}/sesiones/{s['id']}/distribuciones/{d['id']}/respuestas/"
        exigir(*llamar(base, "POST", ruta, {"participante_id": pid, "respuestas": respuestas}), (200,), "No se pudieron enviar las respuestas")
        if entregar:
            exigir(*llamar(base, "POST", ruta, {"participante_id": pid, "respuestas": [], "entregar": True, "origen": "directo"}), (200,), "No se pudo entregar")

    def cerrar(s: dict, d: dict) -> None:
        exigir(*llamar(base, "POST", f"{AULA}/sesiones/{s['id']}/distribuciones/{d['id']}/cerrar/", {}), (200,), "No se pudo cerrar la actividad")
        exigir(*llamar(base, "POST", f"{AULA}/sesiones/{s['id']}/cerrar/", {}), (200,), "No se pudo cerrar la clase")

    # --- clase 1: completa; Eva no fue
    s1 = clase()
    resultados = (("Juan P.", 5), ("Ana Ruiz", 4), ("Luis Mora", 1), ("Carlos Vega", 5), ("Diana Rojas", 3), ("Mateo León", 5))
    participantes = {nombre: unir(s1, nombre) for nombre, _ in resultados}          # primero se une la clase: lanzar exige al menos una tableta admitida
    d1 = lanzar(s1)
    for nombre, aciertos in resultados:
        contestar(s1, d1, participantes[nombre], aciertos)
    cerrar(s1, d1)

    # --- clase 2: incompleta; Carlos perdió la conexión y no alcanzó a enviar lo suyo
    s2 = clase()
    pid_juan, pid_ana, pid_carlos = unir(s2, "Juan P."), unir(s2, "Ana Ruiz"), unir(s2, "Carlos Vega")
    d2 = lanzar(s2)
    contestar(s2, d2, pid_juan, 5)
    contestar(s2, d2, pid_ana, 5)
    exigir(*llamar(base, "POST", f"{AULA}/sesiones/{s2['id']}/participantes/{pid_carlos}/presencia/", {"estado": "reconectando"}), (200,), "No se pudo marcar la presencia")
    cerrar(s2, d2)

    # --- una tarea de estudio para el grupo
    estado, estudio = llamar(base, "POST", "/api/modo-estudio/docente/asignaciones/", {"alcance": "grupo", "grupo_id": g8a, "curso_ref": CURSO, "fuente": "biblioteca", "leccion_ref": LECCION,
                                                                                    "actor": profesor, "actor_rotulo": "Prof. Gómez", "titulo": "Leer la lección de los estados"})
    exigir(estado, estudio, (201,), "No se pudo asignar el estudio")

    # --- los reportes se ponen al día con todo lo anterior
    llamar(base, "POST", "/api/reportes/actualizar/", {"actor": profesor})

    print(json.dumps({"base": base, "profesor": semilla["profesor"], "administrador": semilla["administrador"], "grupos": semilla["grupos"], "alumnos": alumnos,
                      "clases": {"completa": s1["id"], "incompleta": s2["id"]}, "estudio": estudio.get("id")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"Falló la siembra: {e}", file=sys.stderr)
        raise SystemExit(1)

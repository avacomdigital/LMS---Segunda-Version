"""
Siembra un nodo EN MARCHA para probar a mano (o con UI Automation) el Gradebook de MOD-011: organización, un grupo de secundaria (8A, modo calificaciones con la escala
colombiana 1,0–5,0) y uno de preescolar (P1, modo simple por defecto), un profesor, alumnos, un examen aplicado a cada grupo y lo que cada alumno hizo con él. Todo por la API,
igual que lo haría OPS y Student. Sólo usa la biblioteca estándar.

El examen se califica de verdad: hace falta una fuente que califique, que es el host de pruebas de la API de Contenido v2 con sus rutas de examen (imita a AVACOM Contenido con el curso de ejemplo):

    set AVACOM_LMS_DB=%TEMP%\\copia-de-db.sqlite3
    .venv\\Scripts\\python manage.py migrate
    .venv\\Scripts\\python -m tools.host_contenido_v2_con_examenes %TEMP%\\link-pruebas.json
    set AVACOM_CONTENIDO_ENLACE_V2=%TEMP%\\link-pruebas.json
    set AVACOM_LMS_EXIGIR_SESION=0          (el .env de desarrollo la exige; la siembra declara a las personas, como el prototipo)
    .venv\\Scripts\\python manage.py runserver 127.0.0.1:8010 --noreload
    .venv\\Scripts\\python tools\\sembrar_gradebook.py --base http://127.0.0.1:8010

Lo que queda (la escena para mirar el libro):

    8A · secundaria · modo calificaciones (escala «co-1-5»)
        Juan P.   respondió TODO bien, incluidas las dos abiertas → en revisión docente (provisional; aparece en la bandeja)
        Ana Ruiz  respondió bien lo cerrado y dejó las abiertas sin responder → calificada y REGISTRADA (revisada) y PUBLICADA
        Luis Mora respondió mal lo cerrado → calificado y REGISTRADO (revisado, sin publicar) con una nota baja
        Eva Soto  no empezó → pendiente (nunca un cero)
    P1 · preescolar · modo simple (sin configuración)
        Pablo Gil terminó su examen → completado (símbolo ●, sin nota)
        Marta Paz lo empezó → en progreso (símbolo ◐)

Imprime un JSON con los identificadores. NUNCA lo apuntes al nodo real de un aula: crea personas y exámenes de prueba.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request

CURSO = "avacom.co.lower-secondary.6.science.states-of-matter"
EXAMEN = "l3-exam"
ADMIN_DNI, ADMIN_CLAVE = "1042888795", "Rectoria.2026!"
PIN_MAESTRO = "482913"
DOCENTE_DNI, DOCENTE_CLAVE = "80.123.456", "Docente.2026!"
MANIFIESTO = pathlib.Path(__file__).resolve().parents[2] / "spec-driven" / "02-classroom-engine" / "example.json"


def llamar(base: str, metodo: str, ruta: str, cuerpo: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    cabeceras = {"Content-Type": "application/json"}
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    peticion = urllib.request.Request(base + ruta, data=datos, method=metodo, headers=cabeceras)
    try:
        with urllib.request.urlopen(peticion, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def exigir(estado: int, cuerpo: dict, validos: tuple[int, ...], que: str) -> dict:
    if estado not in validos:
        raise SystemExit(f"{que}: {estado} {cuerpo}")
    return cuerpo


def iniciar_sesion(base: str, identificador: str, secreto: str, pin_maestro: str = "") -> str:
    entrada = {"identificador": identificador, "secreto": secreto}
    if pin_maestro:
        entrada["pin_maestro"] = pin_maestro
    estado, cuerpo = llamar(base, "POST", "/api/acceso/sesiones/", entrada)
    if estado != 200:
        raise SystemExit(f"No se pudo iniciar sesión como {identificador}: {estado} {cuerpo}")
    return cuerpo["token"]


# ------------------------------------------------------------------------------------------ las respuestas

def preguntas_del_manifiesto() -> dict[str, dict]:
    datos = json.loads(MANIFIESTO.read_text(encoding="utf-8"))
    return {q["id"]: q for leccion in datos["lessons"] for objeto in leccion["objects"] for q in objeto.get("questions", [])}


def respuesta(p: dict, bien: bool) -> dict:
    """Una respuesta de la forma que pide cada tipo: la que la biblioteca da por buena o una que no."""
    tipo = p["type"]
    if tipo == "multiple_choice":
        elegidas = [o["id"] for o in p["options"] if bool(o.get("isCorrect")) == bien]
        return {"selectedOptionIds": (elegidas if bien else elegidas[:1]) or [p["options"][0]["id"]]}
    if tipo == "true_false":
        return {"value": p["answer"] if bien else not p["answer"]}
    if tipo == "fill_blanks":
        return {"blanks": {b["id"]: (b["acceptedAnswers"][0] if bien else "xyz") for b in p["blanks"]}}
    if tipo == "matching":
        derechas = [x["rightId"] for x in p["pairs"]]
        return {"pairs": [{"leftId": x["leftId"], "rightId": x["rightId"] if bien else derechas[(i + 1) % len(derechas)]} for i, x in enumerate(p["pairs"])]}
    if tipo == "ordering":
        return {"order": list(p["correctOrder"]) if bien else list(reversed(p["correctOrder"]))}
    return {"text": "Al enfriarse, las partículas se mueven más despacio y el gas ocupa menos espacio."}


class Nodo:
    def __init__(self, base: str, profesor_id: str):
        self.base, self.profesor_id = base, profesor_id
        self.preguntas = preguntas_del_manifiesto()

    def evaluacion(self, metodo: str, ruta: str, cuerpo: dict | None = None) -> tuple[int, dict]:
        return llamar(self.base, metodo, "/api/evaluacion" + ruta, cuerpo)

    def aplicar(self, grupo_id: str) -> dict:
        estado, a = self.evaluacion("POST", "/asignaciones/", {
            "fuente": "biblioteca", "curso_ref": CURSO, "objeto_ref": EXAMEN, "alcance": "grupo", "grupo_id": grupo_id, "nivel_examen": "supervisado", "iniciar": True,
            "actor": self.profesor_id, "actor_rotulo": "Prof. Gómez", "tiempo": {"modo": "sin_limite"}, "estrategia": "fixed"})
        return exigir(estado, a, (201,), "No se pudo aplicar el examen")

    def presentar(self, asignacion_id: str, alumno_id: str, hw: str, *, bien: bool, abiertas: bool, entregar: bool = True) -> str:
        estado, ap = self.evaluacion("POST", f"/asignaciones/{asignacion_id}/intentos/", {"dispositivo": hw, "alumno_id": alumno_id, "nombre": f"Tableta {hw}",
                                                                                       "plataforma": "windows", "capacidad_control": "supervisado"})
        exigir(estado, ap, (200, 201), "No se pudo abrir el intento")
        intento = ap["intento"]["id"]
        if not entregar:
            return intento
        estado, preguntas = self.evaluacion("GET", f"/intentos/{intento}/preguntas/?dispositivo={hw}&alumno_id={alumno_id}")
        exigir(estado, preguntas, (200,), "No se pudieron leer las preguntas")
        respuestas = []
        for n, pregunta in enumerate(preguntas["preguntas"], start=1):
            crudo = self.preguntas[pregunta["pregunta_ref"]]
            if crudo["type"] == "open" and not abiertas:
                continue
            respuestas.append({"pregunta_ref": pregunta["pregunta_ref"], "secuencia": n, "respuesta": respuesta(crudo, bien)})
        estado, acuse = self.evaluacion("POST", f"/intentos/{intento}/respuestas/", {"dispositivo": hw, "alumno_id": alumno_id, "respuestas": respuestas})
        exigir(estado, acuse, (200,), "No se pudieron enviar las respuestas")
        estado, fin = self.evaluacion("POST", f"/intentos/{intento}/entregar/", {"dispositivo": hw, "alumno_id": alumno_id, "confirmar": True})
        exigir(estado, fin, (200,), "No se pudo entregar")
        return intento


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", default="http://127.0.0.1:8010")
    a = p.parse_args()
    base = a.base.rstrip("/")

    estado, cuerpo = llamar(base, "POST", "/api/acceso/instalacion/", {
        "organizacion": {"codigo": "IE-PRUEBA", "nombre": "IE de pruebas", "pais": "CO", "idioma": "es", "locale": "es-CO"},
        "administrador": {"alias": "Rectoría", "nombres": "Ana", "apellidos": "Pérez", "dni": ADMIN_DNI, "password": ADMIN_CLAVE}, "pin_maestro": PIN_MAESTRO})
    if estado not in (201, 409):
        raise SystemExit(f"No se pudo instalar el nodo: {estado} {cuerpo}")
    admin = iniciar_sesion(base, ADMIN_DNI, ADMIN_CLAVE, PIN_MAESTRO)

    def grupo(codigo: str, nombre: str, nivel: str) -> dict:
        estado, g = llamar(base, "POST", "/api/acceso/grupos/", {"codigo": codigo, "nombre": nombre, "periodo": "2026", "nivel_clave": nivel}, admin)
        if estado == 409:
            lista = llamar(base, "GET", "/api/acceso/grupos/", None, admin)[1]
            g = next(x for x in (lista.get("grupos") or lista.get("resultados") or lista) if x.get("codigo") == codigo)
            llamar(base, "PATCH", f"/api/acceso/grupos/{g['id']}/", {"nivel_clave": nivel}, admin)
            return g
        return exigir(estado, g, (201,), f"No se pudo crear el grupo {codigo}")

    g8a, gp1 = grupo("8A", "Octavo A", "secundaria"), grupo("P1", "Párvulos", "preescolar")
    estado, docente = llamar(base, "POST", "/api/acceso/usuarios/", {
        "rol": "TEACHER", "alias": "Prof. Gómez", "persona": {"nombres": "Luis", "apellidos": "Gómez"},
        "identificadores": [{"tipo": "DNI", "valor": DOCENTE_DNI, "es_login": True}], "secreto": DOCENTE_CLAVE, "secreto_definitivo": True}, admin)
    if estado != 201:
        raise SystemExit("El profesor ya existía: usa un nodo nuevo (la siembra necesita su identificador).")
    for g in (g8a, gp1):
        llamar(base, "POST", f"/api/acceso/grupos/{g['id']}/miembros/", {"usuario_id": docente["id"], "papel": "DOCENTE"}, admin)

    alumnos: dict[str, dict] = {}
    for n, (nombre, g) in enumerate([("Juan P.", g8a), ("Ana Ruiz", g8a), ("Luis Mora", g8a), ("Eva Soto", g8a), ("Pablo Gil", gp1), ("Marta Paz", gp1)]):
        estado, al = llamar(base, "POST", "/api/acceso/usuarios/", {
            "rol": "STUDENT", "alias": nombre, "persona": {"nombres": nombre.split()[0], "apellidos": "Prueba", "fecha_nacimiento": "2012-04-09"},
            "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": f"9200{n:02d}", "es_login": True}], "secreto": "573920", "secreto_definitivo": True,
            "grupo_id": g["id"]}, admin)
        exigir(estado, al, (201,), f"No se pudo crear a {nombre}")
        hw = f"hw-gb-{n}"
        llamar(base, "POST", "/api/dispositivos/", {"identificador_hw": hw, "nombre": f"Tableta de {nombre}", "capacidad_control": "supervisado"})
        alumnos[nombre] = {"id": al["id"], "grupo": g["codigo"], "hw": hw}

    # La administración adopta la escala y activa el modo calificaciones de SECUNDARIA; preescolar queda en el modo simple por defecto.
    estado, escala = llamar(base, "POST", "/api/gradebook/escalas/adoptar/", {"plantilla": "co-1-5", "jurisdiccion": "Antioquia", "actor": docente["id"]}, admin)
    exigir(estado, escala, (201,), "No se pudo adoptar la escala")
    estado, nivel = llamar(base, "PUT", "/api/gradebook/niveles/secundaria/", {"modo": "calificaciones", "escala_id": escala["id"]}, admin)
    exigir(estado, nivel, (200,), "No se pudo activar el modo calificaciones")

    nodo = Nodo(base, docente["id"])
    a8, ap1 = nodo.aplicar(g8a["id"]), nodo.aplicar(gp1["id"])
    intentos = {}
    for nombre, bien, abiertas in (("Juan P.", True, True), ("Ana Ruiz", True, False), ("Luis Mora", False, False)):
        al = alumnos[nombre]
        intentos[nombre] = nodo.presentar(a8["id"], al["id"], al["hw"], bien=bien, abiertas=abiertas)
    intentos["Pablo Gil"] = nodo.presentar(ap1["id"], alumnos["Pablo Gil"]["id"], alumnos["Pablo Gil"]["hw"], bien=True, abiertas=False)
    intentos["Marta Paz"] = nodo.presentar(ap1["id"], alumnos["Marta Paz"]["id"], alumnos["Marta Paz"]["hw"], bien=True, abiertas=False, entregar=False)

    # El libro se pone al día con lo que la evaluación ya publicó; el profesor publica la calificación de Ana.
    llamar(base, "POST", "/api/gradebook/sincronizar/", {"actor": docente["id"]})
    detalle = llamar(base, "GET", f"/api/gradebook/asignaciones/{a8['id']}/?actor={docente['id']}")[1]
    ana = next(f for f in detalle["alumnos"] if f["rotulo"] == "Ana Ruiz")["intentos"][0]["calificacion"]
    estado, publicada = llamar(base, "POST", f"/api/gradebook/calificaciones/{ana['id']}/publicar/", {"actor": docente["id"], "version_esperada": ana["version"]})
    exigir(estado, publicada, (200,), "No se pudo publicar la calificación de Ana")

    print(json.dumps({"base": base, "profesor": {"id": docente["id"], "dni": DOCENTE_DNI, "clave": DOCENTE_CLAVE},
                      "administrador": {"dni": ADMIN_DNI, "clave": ADMIN_CLAVE, "pin_maestro": PIN_MAESTRO},
                      "grupos": {"8A": g8a["id"], "P1": gp1["id"]}, "alumnos": alumnos, "asignaciones": {"8A": a8["id"], "P1": ap1["id"]}, "intentos": intentos,
                      "escala": {"id": escala["id"], "codigo": escala["codigo"]}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"Falló la siembra: {e}", file=sys.stderr)
        raise SystemExit(1)

"""Siembra un nodo AISLADO para el recorrido de acceso del alumno (RF-30). NUNCA contra el nodo del aula ni el de desarrollo (8000).

Deja, por la API y con la sesión del administrador (que entra con su contraseña y el PIN maestro):
  · dos grupos: «Quinto B» (primaria, PIN de 4) y «Preescolar A» (nivel preescolar con política AVATAR, RF-28);
  · un profesor; en Quinto B a «Juan P.» (PIN 1234) y «Ana R.» (PIN 4321) y a «Sofía R.» en PIN pendiente (RN-35); en Preescolar A a «Lía M.» (dibujo «gato»);
  · la tableta de esta máquina registrada en el inventario (MOD-009) como «Tableta 1» (la huella es la que usa Student: «student-<nombre del equipo>»).

Preparación del nodo (desde backend/ del repositorio, con el venv del proyecto):
  set AVACOM_LMS_DB=<archivo .sqlite3 nuevo, fuera del repo>
  set AVACOM_LMS_EXIGIR_SESION=1
  manage.py migrate
  set AVACOM_LMS_PIN_MAESTRO=482915        (el PIN maestro nunca va como argumento)
  manage.py acceso_instalar --codigo IE-PRUEBA --nombre "Aula de prueba" --admin-dni 900001 --admin-nombres Ana --admin-apellidos Admin --admin-password "Rectoria.2026!"
  manage.py runserver 127.0.0.1:8010 --noreload
y luego:  python sembrar_acceso.py   (variables: AVACOM_AULA_URL, AVACOM_LMS_PIN_MAESTRO, AVACOM_ADMIN_DNI, AVACOM_ADMIN_CLAVE)
Escribe salida/acceso-semilla.json con los ids que usa escenario_acceso.py.
"""
import json, os, socket, sys, urllib.error, urllib.request
from pathlib import Path

B = os.environ.get("AVACOM_AULA_URL", "http://127.0.0.1:8010").rstrip("/")
PIN_MAESTRO = os.environ.get("AVACOM_LMS_PIN_MAESTRO", "")
DNI = os.environ.get("AVACOM_ADMIN_DNI", "900001")
CLAVE = os.environ.get("AVACOM_ADMIN_CLAVE", "Rectoria.2026!")
S = Path(__file__).resolve().parent / "salida"
S.mkdir(exist_ok=True)
TOKEN = None


def api(metodo, ruta, cuerpo=None):
    cabeceras = {"Content-Type": "application/json"}
    if TOKEN:
        cabeceras["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(B + ruta, data=json.dumps(cuerpo).encode() if cuerpo is not None else None, method=metodo, headers=cabeceras)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def exigir(estado, cuerpo, que):
    if estado >= 300:
        print(f"FALLÓ {que}: {estado} {cuerpo}")
        sys.exit(1)
    return cuerpo


def main():
    global TOKEN
    if B.endswith(":8000"):
        sys.exit("Este guion no se corre contra el nodo de desarrollo (8000).")
    if not PIN_MAESTRO:
        sys.exit("Falta AVACOM_LMS_PIN_MAESTRO (el administrador entra con su contraseña y el PIN maestro).")
    config = exigir(*api("GET", "/api/acceso/configuracion/"), "configuración")
    if not config.get("sesion_obligatoria"):
        sys.exit("El nodo no exige sesión: arráncalo con AVACOM_LMS_EXIGIR_SESION=1.")
    sesion = exigir(*api("POST", "/api/acceso/sesiones/", {"identificador": DNI, "secreto": CLAVE, "dispositivo": "sembrador-acceso", "pin_maestro": PIN_MAESTRO}), "login admin")
    TOKEN = sesion["token"]

    grupos = {}
    for codigo, nombre, nivel in [("5B", "Quinto B", "primaria"), ("PREA", "Preescolar A", "preescolar")]:
        estado, cuerpo = api("POST", "/api/acceso/grupos/", {"codigo": codigo, "nombre": nombre, "periodo": "2026", "nivel_clave": nivel})
        if estado == 409:
            cuerpo = next(g for g in exigir(*api("GET", "/api/acceso/grupos/"), "grupos") if g["codigo"] == codigo)
        grupos[codigo] = exigir(estado if estado != 409 else 200, cuerpo, f"grupo {codigo}")["id"]
    # RF-28: preescolar entra con dibujos (BR-024, TST-074).
    exigir(*api("PUT", "/api/acceso/politicas/student/?nivel=preescolar", {"tipo_secreto": "AVATAR", "longitud_minima": 4}), "política preescolar")

    profesor = api("POST", "/api/acceso/usuarios/", {
        "rol": "TEACHER", "alias": "Prof. Carter", "persona": {"nombres": "Mía", "apellidos": "Carter"},
        "identificadores": [{"tipo": "DNI", "valor": "700100", "principal": True}], "secreto": "Profe.Aula2026!", "secreto_definitivo": True})
    print("profesor:", profesor[0])

    alumnos = {}
    for alias, nombres, apellidos, grupo, secreto in [
        ("Juan P.", "Juan", "Pérez", "5B", "1234"),
        ("Ana R.", "Ana", "Ríos", "5B", "4321"),
        ("Sofía R.", "Sofía", "Ramírez", "5B", None),
        ("Lía M.", "Lía", "Mora", "PREA", "gato"),
    ]:
        cuerpo = {"rol": "STUDENT", "alias": alias, "persona": {"nombres": nombres, "apellidos": apellidos}, "grupo_id": grupos[grupo]}
        cuerpo.update({"secreto": secreto, "secreto_definitivo": True} if secreto else {"pin_pendiente": True})
        estado, r = api("POST", "/api/acceso/usuarios/", cuerpo)
        if estado < 300:
            alumnos[alias] = r["id"]
        print("alumno", alias, estado, "" if estado < 300 else r)

    huella = f"student-{socket.gethostname()}"
    estado, tableta = api("POST", "/api/dispositivos/", {"identificador_hw": huella, "nombre": "Tableta 1", "tipo": "TABLETA", "plataforma": "windows"})
    print("tableta:", estado, tableta.get("id"), huella)
    (S / "acceso-semilla.json").write_text(json.dumps({"base": B, "grupos": grupos, "alumnos": alumnos, "tableta": tableta.get("id"), "huella": huella},
                                                      ensure_ascii=False, indent=2), encoding="utf-8")
    api("DELETE", "/api/acceso/sesiones/actual/")
    print("listo:", S / "acceso-semilla.json")


if __name__ == "__main__":
    main()

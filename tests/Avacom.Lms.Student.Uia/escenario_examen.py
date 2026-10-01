"""Prueba real de AVACOM Student presentando un examen de MOD-010: el lado del profesor por la API (lo mismo que hace OPS), el lado del alumno en la
app de verdad, manejada por UI Automation y SIN el gancho de teclado ni la cobertura de monitores (AVACOM_EXAM_NO_LOCKDOWN=1: el gancho es global y esta
prueba corre en el equipo de trabajo). Cada paso deja una captura y el texto de la pantalla; al final imprime el veredicto de cada comprobación.

Preparación (una sola vez; NUNCA contra el nodo real del aula):
  1. Un nodo aparte:  set AVACOM_LMS_DB=<copia vacía>  ·  set AVACOM_AULA_PERMITIR_EJEMPLO=1  ·  set AVACOM_EVAL_LATIDO_VENCIDO_MS=16000  ·  manage.py migrate  ·  manage.py runserver 127.0.0.1:8021 --noreload
     (16000 y no menos: el nivel abierto late cada 10 s y un vencimiento menor pausa un examen sano)
  2. Sembrarlo:  backend/.venv/Scripts/python backend/tools/sembrar_evaluacion.py --base http://127.0.0.1:8021 --nivel supervisado --alumnos 3
  3. Lanzar Student con AVACOM_EXAM_NO_LOCKDOWN=1 (lanzar-student.ps1) y dejar su pid en salida/student.pid.
Cada corrida aplica un examen nuevo (el anterior se cierra al terminar). Variables: AVACOM_AULA_URL (nodo), AVACOM_NIVEL (abierto/supervisado/controlado),
AVACOM_MAXIMIZAR=1 (ventana a 1920 x 1040 para juzgar los tercios con tercios.ps1), AVACOM_SIN_SUSPENSION=1 (omite la pausa por falta de latido).
Limitaciones: las preguntas de elegir una opción son filas con gesto táctil que el árbol de accesibilidad no expone como botón, así que sólo se responden
las abiertas y las de ordenar; la calificación de lo respondido necesita AVACOM Contenido en marcha (sin ella queda «pendiente» y el guion lo verifica).
Student comparte `Preferences` con la instancia del usuario: comprobar antes que no la tiene abierta y, al terminar, devolver la dirección del aula y el nombre.
"""
import json, os, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path

S = Path(__file__).resolve().parent / "salida"
S.mkdir(exist_ok=True)
PID = (S / "student.pid").read_text().strip()
B = os.environ.get("AVACOM_AULA_URL", "http://127.0.0.1:8021")
CAP = S / "capturas-examen"; CAP.mkdir(exist_ok=True)
informe = []


def api(m, path, body=None):
    req = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None, method=m, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def ui(accion, nombre="", valor="", salida=""):
    args = ["powershell", "-NoProfile", "-File", str(Path(__file__).resolve().parent / "ui-student.ps1"), "-ProcId", PID, "-Accion", accion]
    if nombre: args += ["-Nombre", nombre]
    if valor: args += ["-Valor", valor]
    if salida: args += ["-Salida", salida]
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip()


def pantalla(nombre):
    ui("shot", salida=str(CAP / f"{nombre}.png"))
    texto = ui("text")
    (CAP / f"{nombre}.txt").write_text(texto, encoding="utf-8")
    return texto


def comprobar(nombre, condicion, detalle=""):
    informe.append((nombre, bool(condicion), detalle))
    print(("OK   " if condicion else "FALLA"), nombre, ("· " + detalle) if detalle else "")


def esperar_texto(sub, timeout=12.0):
    fin = time.time() + timeout
    while time.time() < fin:
        t = ui("text")
        if sub.lower() in t.lower():
            return t
        time.sleep(1)
    return ui("text")


def esperar_sin(sub, timeout=12.0):
    """Sondea hasta que `sub` desaparezca del texto visible."""
    fin = time.time() + timeout
    while time.time() < fin:
        t = ui("text")
        if sub.lower() not in t.lower():
            return t
        time.sleep(1)
    return ui("text")


def botones():
    return [l.split("\t")[1] for l in ui("list").splitlines() if l.startswith("Button")]


def uno(texto):
    return " | ".join(l.strip() for l in texto.splitlines() if l.strip())[:400]


# ------------------------------------------------------------------ 0 · el nodo sembrado
def asegurar_asignacion():
    """El examen se cierra al final de la corrida (para liberar resultados): cada corrida aplica uno nuevo con los datos de la última asignación."""
    st, lista = api("GET", "/api/evaluacion/asignaciones/")
    todas = lista.get("asignaciones", [])
    abiertas = [a for a in todas if a["estado"] in ("activa", "activa_fuera_de_plazo") and not a.get("liberados_en")]
    if abiertas:
        return abiertas[0]
    assert todas, "El nodo no tiene ninguna asignación: corre tools/sembrar_evaluacion.py primero."
    base = todas[0]
    st, nueva = api("POST", "/api/evaluacion/asignaciones/", {
        "fuente": base["fuente_curso"], "curso_ref": base["curso_ref"], "objeto_ref": base["objeto_ref"], "alcance": "grupo", "grupo_id": base["grupo_id"],
        "nivel_examen": os.environ.get("AVACOM_NIVEL", base["nivel_examen"]), "iniciar": True, "actor": base["profesor_id"], "actor_rotulo": base["profesor_rotulo"]})
    assert st == 201, f"No se pudo aplicar un examen nuevo: {st} {nueva}"
    return nueva


ASIG = asegurar_asignacion()
ACTOR = ASIG.get("profesor_id") or "docente"
print("asignación", ASIG["id"], ASIG["titulo"], "nivel", ASIG["nivel_examen"])
st, quien = api("GET", "/api/evaluacion/estudiantes/")
ALUMNOS = [a for g in quien["grupos"] for a in g["alumnos"]]
YO = ALUMNOS[0]
print("el alumno de la prueba:", YO)

# ------------------------------------------------------------------ 1 · entrar al aula y abrir «Exámenes»
if os.environ.get("AVACOM_MAXIMIZAR") == "1":
    print(ui("ajustar", valor="1920x1040"))     # para juzgar la composición a pantalla completa, con la cuadrícula de tercios (tercios.ps1)
    time.sleep(2)
t = pantalla("00-conexion")
print(ui("set", "192.168.1.10", B))        # la dirección del aula (el campo se identifica por su sugerencia)
print(ui("set", "Nombre y apellido", "Alumno de Prueba"))
print(ui("invoke", "Entrar al aula"))
t = esperar_texto("Bienvenido", 12)
print(ui("invoke", "Exámenes"))
t = esperar_texto("Quién eres", 10)
if "Quién eres" not in t and "Mis evaluaciones" not in t:
    t = esperar_texto("Mis evaluaciones", 6)
t = pantalla("01-quien-eres")
if "Quién eres" in t:
    comprobar("¿Quién eres? · sin sesión la tableta pregunta entre los alumnos con un examen abierto", "Toca tu nombre" in t, uno(t))
    print(ui("invoke", YO["rotulo"]))
else:
    print("(la tableta ya recordaba a la persona: no pregunta)")
t = esperar_texto(ASIG["titulo"], 10)
t = pantalla("02-mis-evaluaciones")
comprobar("Mis evaluaciones · la tarjeta del examen con su nivel y «Comenzar»", ASIG["titulo"] in t and "Examen " in t and "Comenzar" in botones(), uno(t))

# ------------------------------------------------------------------ 2 · la antesala (PAN-120)
print(ui("invoke", "Comenzar"))
t = esperar_texto("preguntas", 10)
t = pantalla("03-antesala")
comprobar("Antesala · preguntas, duración y condiciones antes de empezar", "preguntas" in t.lower() and ("Qué se registra" in t or "registra" in t.lower()) and "Examen" in t, uno(t))
comprobar("Antesala · «Comenzar» a la vista", "Comenzar" in botones())

# ------------------------------------------------------------------ 3 · el examen (PAN-121)
print(ui("invoke", "Comenzar"))
t = esperar_texto("Pregunta 1 de", 8)
if "Pregunta 1 de" not in t:
    # Con AVACOM_EXAM_NO_LOCKDOWN la tableta declara «abierto»: un examen supervisado pide la decisión del profesor (FUN-116).
    t = esperar_texto("profesor debe decidir", 8)
    t = pantalla("03b-esperando-admision")
    comprobar("Admisión · «Esperando que tu profesor decida», la pantalla no se cierra", "profesor debe decidir" in t and "No cierres esta pantalla" in t, uno(t))
    st, adm = api("GET", f"/api/evaluacion/asignaciones/{ASIG['id']}/admisiones/")
    pend = [a for a in adm.get("admisiones", []) if a.get("estado") == "en_espera"]
    comprobar("Profesor · ve la solicitud de admisión", len(pend) == 1, str(adm)[:160])
    if pend:
        st, r = api("POST", f"/api/evaluacion/asignaciones/{ASIG['id']}/admisiones/{pend[0]['id']}/decidir/", {"actor": ACTOR, "decision": "admitir", "nivel_admitido": "abierto", "motivo": "Prueba de UI Automation"})
        comprobar("Profesor · admite la tableta en un nivel menor", st == 200, str(r)[:160])
    t = esperar_texto("Pregunta 1 de", 20)
t = pantalla("04-examen-pregunta-1")
comprobar("Examen · «Pregunta 1 de N», cronómetro del nodo y guardado", "Pregunta 1 de" in t and ("Guardado" in t) and (":" in t or "Sin límite" in t), uno(t))
st, panel = api("GET", f"/api/evaluacion/asignaciones/{ASIG['id']}/panel/")
fila = next((f for f in panel["filas"] if f["alumno_id"] == YO["id"]), None)
comprobar("Backend · el panel ve al alumno en curso con su tableta", fila and fila["estado"] == "en_curso", json.dumps({k: fila.get(k) for k in ("estado", "respondidas", "total")}) if fila else "sin fila")
INTENTO = fila["intento_id"] if fila else None

# El banco reparte 4 preguntas al azar: se contesta lo que UI Automation puede tocar (respuesta abierta y orden); las de elegir una opción son filas con
# gesto táctil que el árbol de accesibilidad no expone como botón, así que se dejan sin responder y la confirmación de entrega las cuenta.
respondidas = 0
for n in range(1, 5):
    lista = ui("list")
    if "act-abierta" in lista:
        print(ui("set", "act-abierta", "En Bogotá la presión atmosférica es menor por la altitud, así que el agua hierve antes."))
        time.sleep(4)                               # se guarda sola, sin botón
        respondidas += 1
        tipo = "abierta"
    elif "act-orden-listo" in lista:
        print(ui("invoke", "Listo, este es mi orden"))
        time.sleep(2.5)
        respondidas += 1
        tipo = "orden"
    else:
        tipo = "opción (no tocable por UIA)"
    t = pantalla(f"05-pregunta-{n}")
    comprobar(f"Examen · pregunta {n} ({tipo}): el contador dice «{respondidas} de 4 contestadas»", f"{respondidas} de 4 contestadas" in t and "Guardado" in t, uno(t))
    if n < 4:
        print(ui("invoke", "Siguiente"))
        time.sleep(1.5)
        t = ui("text")
        comprobar(f"Examen · «Siguiente» avanza a la pregunta {n + 1}", f"Pregunta {n + 1} de" in t, uno(t))

# ------------------------------------------------------------------ 4 · entregar con preguntas sin responder (PAN-123, primera parte)
print(ui("invoke", "Entregar"))
faltan = 4 - respondidas
if faltan:
    t = esperar_texto("Te falta", 6)
    t = pantalla("06-confirmar-entrega")
    comprobar(f"Entregar · «Te falta(n) {faltan}…» y «Puedes entregar igual» (sólo lo que de verdad falta)", ("Te faltan %d preguntas" % faltan if faltan > 1 else "Te falta 1 pregunta") in t and "Puedes entregar igual" in t, uno(t))
    print(ui("invoke", "Volver"))
    time.sleep(1)

# ------------------------------------------------------------------ 5 · suspensión: se pierde la señal más de lo que tolera el nodo (PAN-122)
# El nodo se arranca con AVACOM_EVAL_LATIDO_VENCIDO_MS=16000 (el nivel abierto late cada 10 s); la tableta se congela 25 s (sin red no hay latido) y al volver el nodo ya la tiene en pausa.
if os.environ.get("AVACOM_SIN_SUSPENSION") != "1":
    print("… congelando la tableta 25 s para que el nodo la dé por perdida …")
    subprocess.run(["powershell", "-NoProfile", "-File", str(Path(__file__).resolve().parent / "congelar.ps1"), "-ProcId", PID, "-Segundos", "25"], capture_output=True, text=True)
    st, panel = api("GET", f"/api/evaluacion/asignaciones/{ASIG['id']}/panel/")
    fila = next((f for f in panel["filas"] if f["alumno_id"] == YO["id"]), {})
    comprobar("Backend · el nodo suspendió el intento al perder el latido", fila.get("estado") in ("pausado", "pausado_desconexion", "restaurando"), json.dumps({k: fila.get(k) for k in ("estado",)}))
    t = esperar_texto("en pausa", 25)
    t = pantalla("07-suspendido")
    comprobar("Suspendido · «Tu examen está en pausa», sin cuenta atrás en rojo", "en pausa" in t.lower() and "Avisa a tu profesor" in t, uno(t))
    st, r = api("POST", f"/api/evaluacion/intentos/{INTENTO}/reactivar/", {"actor": ACTOR})
    comprobar("Profesor · reactiva", st == 200, str(r)[:120])
    t = esperar_sin("en pausa", 30)             # la tableta se entera en su próximo latido
    t = pantalla("08-reactivado")
    comprobar("Reactivado · la tableta vuelve sola a la pregunta donde iba", "Pregunta 4 de" in t and "en pausa" not in t.lower(), uno(t))

st, panel = api("GET", f"/api/evaluacion/asignaciones/{ASIG['id']}/panel/")
fila = next((f for f in panel["filas"] if f["alumno_id"] == YO["id"]), {})
comprobar(f"Backend · el panel cuenta las {respondidas} respondidas", fila.get("respondidas") == respondidas, json.dumps({k: fila.get(k) for k in ("estado", "respondidas", "total")}))

# ------------------------------------------------------------------ 6 · entregar
print(ui("invoke", "Entregar"))
time.sleep(1.5)
if faltan:
    print(ui("invoke", "Entregar igual"))
t = esperar_texto("quedó entregado", 15)
t = pantalla("09-entrega")
comprobar("Entrega · «Tu examen quedó entregado» y qué sigue, sin la palabra «calificado»", "quedó entregado" in t.lower() and "calificado" not in t.lower(), uno(t))
comprobar("Entrega · no se anuncia nota (DEC-032)", "%" not in t, uno(t))
comprobar(f"Entrega · cuenta lo respondido («Respondiste {respondidas} de 4 preguntas»)", f"Respondiste {respondidas} de 4" in t, uno(t))
st, exp = api("GET", f"/api/evaluacion/intentos/{INTENTO}/")
comprobar("Backend · intento entregado por el alumno", exp["intento"]["estado"] in ("entregado", "en_revision_docente", "calificado") and exp["intento"]["origen_entrega"] == "alumno", json.dumps({k: exp["intento"][k] for k in ("estado", "origen_entrega")}))

# ------------------------------------------------------------------ 7 · el profesor libera y el alumno ve su resultado
st, r = api("POST", f"/api/evaluacion/asignaciones/{ASIG['id']}/cerrar/", {"actor": ACTOR})
# (liberar sólo si nadie más presenta)
st, r = api("POST", f"/api/evaluacion/asignaciones/{ASIG['id']}/liberar-resultados/", {"actor": ACTOR})
comprobar("Profesor · libera los resultados", st == 200, str(r)[:120])

print(ui("invoke", "Volver a mis evaluaciones"))
time.sleep(3)
t = pantalla("10-mis-evaluaciones-despues")
st, exp = api("GET", f"/api/evaluacion/intentos/{INTENTO}/")
if exp["intento"].get("calificacion_pendiente"):
    # Sin AVACOM Contenido en marcha la clave no se puede comparar: el nodo NO inventa una nota (DEC-032) y la tableta lo dice sin dar un 0.
    comprobar("Resultado · calificación pendiente: la tarjeta dice «Entregado · tu profesor publicará los resultados» y no muestra nota", "Entregado · tu profesor publicará los resultados" in t, uno(t))
else:
    print(ui("invoke", "Ver resultado"))
    t = esperar_texto("Pregunta por pregunta", 8)
    t = pantalla("11-resultado")
    comprobar("Resultado · porcentaje y pregunta por pregunta, sin nada en rojo", "%" in t and "Pregunta" in t, uno(t))
    print(ui("invoke", "Volver a mis evaluaciones"))
    time.sleep(2)

# ------------------------------------------------------------------ 8 · dejar todo como estaba
print("RECUERDA: devolver en la pantalla de conexión la dirección del aula y el nombre del usuario (Student comparte Preferences).")

fallas = [i for i in informe if not i[1]]
print(f"\n{len(informe) - len(fallas)} de {len(informe)} comprobaciones OK")
sys.exit(1 if fallas else 0)

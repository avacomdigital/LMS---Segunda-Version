"""Verificación de las correcciones: mandos al liberar/activar el seguimiento sin cambio de selector, sin mandos
al volver de un recurso, código limpio al volver a S1, tarjeta estable entre sondeos."""
import json, os, subprocess, time, urllib.request, urllib.error
from pathlib import Path

S = Path(__file__).resolve().parent / "salida"
S.mkdir(exist_ok=True)
PID = (S / "student.pid").read_text().strip()
B = os.environ.get("AVACOM_AULA_URL", "http://127.0.0.1:8010")
C = "avacom.co.lower-secondary.6.science.states-of-matter"
PROF = {"profesor_id": "prof-prueba-claude"}
CAP = S / "capturas"
informe = []


def api(m, path, body=None):
    req = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None, method=m,
                                 headers={"Content-Type": "application/json"})
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
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()


def botones():
    return [l.split("\t")[1] for l in ui("list").splitlines() if l.startswith("Button")]


def mandos():
    return any("Siguiente" in b for b in botones())


def pantalla(nombre):
    ui("shot", salida=str(CAP / f"{nombre}.png"))
    texto = ui("text") + "\n" + "\n".join("[botón] " + b for b in botones())
    (CAP / f"{nombre}.txt").write_text(texto, encoding="utf-8")
    return texto


def comprobar(nombre, condicion, detalle=""):
    informe.append((nombre, bool(condicion), detalle))
    print(("OK   " if condicion else "FALLA"), nombre, ("· " + detalle[:200]) if detalle else "")


esperar = time.sleep

b = botones()
if any("Clase en vivo" in x for x in b): ui("invoke", "Clase en vivo"); esperar(4); b = botones()
assert "Entrar a la clase" in b, b
st, ab = api("GET", "/api/aula/sesiones/?estado=abierta&profesor=prof-prueba-claude")
for x in ab.get("sesiones", []):
    api("POST", f"/api/aula/sesiones/{x['id']}/cerrar/", {"forzar": True, **PROF})


def nueva_clase():
    st, s = api("POST", "/api/aula/sesiones/", {"via": "leccion", "curso_ref": C, "leccion_ref": "l1-three-states", "fuente": "ejemplo",
                                              **PROF, "profesor_rotulo": "Prof. Prueba", "superficie": "pantalla"})
    assert st == 201, (st, s)
    for d in s["codigo_union"]:
        ui("invoke", d)
    ui("invoke", "Entrar a la clase"); esperar(5)
    return s["id"]


SID = nueva_clase()
t = pantalla("50-s4-inicial")
comprobar("Entra con seguimiento: sin mandos", "Lámina 1 de 3" in t and not mandos(), t.replace("\n", " | ")[:160])
api("POST", f"/api/aula/sesiones/{SID}/controles/", {"tipo": "seguimiento", "activo": False, **PROF}); esperar(4)
comprobar("CORREGIDO · liberar el seguimiento muestra los mandos sin esperar a un cambio de selector", mandos(), str(botones()))
ui("invoke", "Siguiente"); esperar(2)
t = pantalla("51-s4-navega")
comprobar("Navegación libre · el alumno pasa a la lámina 2", "Lámina 2 de 3" in t)
api("POST", f"/api/aula/sesiones/{SID}/controles/", {"tipo": "seguimiento", "activo": True, **PROF}); esperar(4)
t = pantalla("52-s4-seguimiento")
comprobar("CORREGIDO · activar el seguimiento oculta los mandos al instante", not mandos(), str(botones()))
comprobar("Activar el seguimiento no mueve la lámina hasta que el profesor declare otra (queda la 2 elegida por el alumno)", "Lámina 2 de 3" in t, t.replace("\n", " | ")[:160])
api("POST", f"/api/aula/sesiones/{SID}/selector/", {"objeto_ref": "l1-lecture", "unidad_ref": "l1-lecture-s1", **PROF}); esperar(4)
comprobar("El siguiente selector del profesor vuelve a mandar (lámina 1)", "Lámina 1 de 3" in ui("text"))

st, d1 = api("POST", f"/api/aula/sesiones/{SID}/distribuciones/", {"clase": "recurso", "objeto_ref": "l1-lecture", **PROF}); esperar(4)
vistas = [("Abrir" in botones()) for _ in range(4)]
comprobar("CORREGIDO · la tarjeta del recurso es estable entre sondeos (4 lecturas seguidas la ven)", all(vistas), str(vistas))
ui("invoke", "Abrir"); esperar(4)
comprobar("Recurso abierto · mandos propios", mandos())
ui("invoke", "Volver a la clase"); esperar(3)
t = pantalla("53-s4-volver")
comprobar("CORREGIDO · al volver a la clase con seguimiento activo no quedan mandos", "Lámina 1 de 3" in t and not mandos(), str(botones()))
ui("invoke", "Abrir"); esperar(3)
api("POST", f"/api/aula/sesiones/{SID}/distribuciones/{d1['id']}/cerrar/", {**PROF}); esperar(5)
t = pantalla("54-s4-retirado")
comprobar("CORREGIDO · al retirar el recurso abierto no quedan mandos y se ve el selector", "Lámina 1 de 3" in t and not mandos() and "Abrir" not in botones(), str(botones()))

api("POST", f"/api/aula/sesiones/{SID}/cerrar/", {"forzar": True, **PROF}); esperar(5)
ui("invoke", "Volver al men"); esperar(3)
ui("invoke", "Clase en vivo"); esperar(4)
t = pantalla("55-s4-s1-limpio")
comprobar("CORREGIDO · S1 vuelve con las casillas vacías (no queda el código anterior)", "Entrar a la clase" in botones() and not any(len(l.strip()) == 1 and l.strip().isdigit() for l in t.splitlines()), t.replace("\n", " | ")[:160])

print("\n=== INFORME 4 ===")
for n, ok, d in informe:
    print(("OK   " if ok else "FALLA"), n)
(S / "informe4.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")

"""Tercera tanda: dos recursos lanzados seguidos, volver a la clase, retirar. Selector y recurso sin WebView
(la lámina 1) para que UI Automation vea los botones de las tarjetas."""
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


def pantalla(nombre):
    ui("shot", salida=str(CAP / f"{nombre}.png"))
    texto = ui("text") + "\n" + "\n".join("[botón] " + b for b in botones())
    (CAP / f"{nombre}.txt").write_text(texto, encoding="utf-8")
    return texto


def comprobar(nombre, condicion, detalle=""):
    informe.append((nombre, bool(condicion), detalle))
    print(("OK   " if condicion else "FALLA"), nombre, ("· " + detalle[:220]) if detalle else "")


def resumen(t):
    return t.replace("\n", " | ")[:220]


esperar = time.sleep

b = botones()
if any("Volver al men" in x for x in b): ui("invoke", "Volver al men"); esperar(3); b = botones()
if any("Clase en vivo" in x for x in b): ui("invoke", "Clase en vivo"); esperar(4); b = botones()
assert "Entrar a la clase" in b, b
st, ab = api("GET", "/api/aula/sesiones/?estado=abierta&profesor=prof-prueba-claude")
for x in ab.get("sesiones", []):
    api("POST", f"/api/aula/sesiones/{x['id']}/cerrar/", {"forzar": True, **PROF})
ui("invoke", "Borrar")
st, s = api("POST", "/api/aula/sesiones/", {"via": "leccion", "curso_ref": C, "leccion_ref": "l1-three-states", "fuente": "ejemplo",
                                          **PROF, "profesor_rotulo": "Prof. Prueba", "superficie": "pantalla"})
SID = s["id"]
for d in s["codigo_union"]:
    ui("invoke", d)
ui("invoke", "Entrar a la clase"); esperar(5)
st, e = api("GET", f"/api/aula/sesiones/{SID}/"); PART = e["participantes"][0]["id"]

st, d1 = api("POST", f"/api/aula/sesiones/{SID}/distribuciones/", {"clase": "recurso", "objeto_ref": "l1-lecture", **PROF}); esperar(4)
ui("invoke", "Abrir"); esperar(4)
t = pantalla("40-s3-recurso-abierto")
comprobar("Recurso A abierto (misma presentación que el selector): mandos visibles y tarjeta «Recibido · ábrelo cuando quieras» con «Volver a la clase»",
          any("Siguiente" in x for x in botones()) and "Volver a la clase" in botones(), resumen(t))
st, d2 = api("POST", f"/api/aula/sesiones/{SID}/distribuciones/", {"clase": "recurso", "media_ref": "pdf-lab-guide", "rotulo": "Guía del laboratorio", **PROF}); esperar(4)
t = pantalla("41-s3-segundo-recurso")
comprobar("Recurso B lanzado con A abierto · dos tarjetas, las dos con «Volver a la clase» (B no se puede abrir directamente)",
          "Guía del laboratorio" in t and botones().count("Volver a la clase") == 2 and "Abrir" not in botones(), resumen(t))
st, e = api("GET", f"/api/aula/sesiones/{SID}/")
entB = [d for d in e["distribuciones"] if d["id"] == d2["id"]][0]["entregas"]
comprobar("Backend · B sigue pendiente de entrega (OPS: 0 de 1)", entB["entregadas"] == 0, json.dumps(entB)[:100])
ui("invoke", "Volver a la clase"); esperar(4)
t = pantalla("42-s3-volver")
comprobar("Volver a la clase · vuelve al selector (lámina 1, sin mandos) y las dos tarjetas ofrecen «Abrir»",
          "Lámina 1 de 3" in t and botones().count("Abrir") == 2 and not any("Siguiente" in x for x in botones()), resumen(t))
comprobar("Tarjeta A dice «Recibido · ábrelo cuando quieras» y B «Tu profesor te lo acaba de enviar»", "Recibido" in t and "acaba de enviar" in t, resumen(t))
api("POST", f"/api/aula/sesiones/{SID}/distribuciones/{d1['id']}/cerrar/", {**PROF}); esperar(5)
t = pantalla("43-s3-retirada-A")
comprobar("Retirar A · desaparece su tarjeta, queda la de B", botones().count("Abrir") == 1 and "Guía del laboratorio" in t and "Todo lo que nos rodea es materia" not in t.split("[botón]")[0].replace("Presentación · Todo lo que nos rodea es materia", ""), resumen(t))
ui("invoke", "Abrir"); esperar(5)
t = pantalla("44-s3-abrir-B-pdf")
st, e = api("GET", f"/api/aula/sesiones/{SID}/")
entB = [d for d in e["distribuciones"] if d["id"] == d2["id"]][0]["entregas"]
comprobar("Abrir B (pdf suelto por media_ref) · se confirma la entrega", entB["entregadas"] == 1, json.dumps(entB)[:100])
comprobar("Abrir B · la tableta muestra el pdf (o explica por qué no)", "Guía" in t or "pdf" in t.lower() or "documento" in t.lower(), resumen(t))
api("POST", f"/api/aula/sesiones/{SID}/distribuciones/{d2['id']}/cerrar/", {**PROF}); esperar(5)
t = pantalla("45-s3-retirada-B")
comprobar("Retirar B con B abierto · la tableta vuelve al selector (lámina 1) sin tarjetas", "Lámina 1 de 3" in t and "Abrir" not in botones() and "Volver a la clase" not in botones(), resumen(t))

# el alumno cierra la app y vuelve: readmisión
st, c = api("POST", f"/api/aula/sesiones/{SID}/cerrar/", {"forzar": True, **PROF}); esperar(5)
ui("invoke", "Volver al men"); esperar(2)
print("\n=== INFORME 3 ===")
for n, ok, d in informe:
    print(("OK   " if ok else "FALLA"), n)
(S / "informe3.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")

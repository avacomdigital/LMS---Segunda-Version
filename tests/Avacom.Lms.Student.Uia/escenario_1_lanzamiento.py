"""Prueba real de AVACOM Student siguiendo una clase: el lado del profesor por la API (lo mismo que hace OPS),
el lado del alumno en la app de verdad, manejada por UI Automation. Cada paso deja una captura y el texto
de la pantalla; al final imprime el veredicto de cada comprobación."""
import json, os, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path

S = Path(__file__).resolve().parent / "salida"
S.mkdir(exist_ok=True)
PID = (S / "student.pid").read_text().strip()
B = os.environ.get("AVACOM_AULA_URL", "http://127.0.0.1:8010")
C = "avacom.co.lower-secondary.6.science.states-of-matter"
PROF = {"profesor_id": "prof-prueba-claude"}
CAP = S / "capturas"; CAP.mkdir(exist_ok=True)
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
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip()


def pantalla(nombre):
    """Captura + texto visible. Devuelve el texto (una línea por Label)."""
    ui("shot", salida=str(CAP / f"{nombre}.png"))
    texto = ui("text")
    (CAP / f"{nombre}.txt").write_text(texto, encoding="utf-8")
    return texto


def comprobar(nombre, condicion, detalle=""):
    informe.append((nombre, bool(condicion), detalle))
    print(("OK   " if condicion else "FALLA"), nombre, ("· " + detalle) if detalle else "")


def esperar(seg=4.0):
    time.sleep(seg)


def esperar_texto(sub, timeout=8.0):
    """Sondea el texto visible hasta que aparezca `sub` (la tableta refresca cada 2 s)."""
    fin = time.time() + timeout
    while time.time() < fin:
        t = ui("text")
        if sub.lower() in t.lower():
            return t
        time.sleep(1)
    return ui("text")


def botones():
    return [l.split("	")[1] for l in ui("list").splitlines() if l.startswith("Button")]


# ------------------------------------------------------------------ 0 · llegar a S1 limpio
print(ui("invoke", "Clase en vivo"))
esperar(5)
if "Entrar a la clase" not in botones():
    # La tableta conservaba una participación y se readmitió sola (FUN-077): salimos de esa clase.
    t0 = pantalla("00-readmision-automatica")
    comprobar("Readmisión · con una participación guardada la tableta vuelve sola a S2 sin escribir el código",
              "Conectado" in t0 or "Reconectando" in t0, t0.replace("\n", " | ")[:200])
    print(ui("invoke", "Salir"))
    esperar(2)
    print(ui("invoke", "Salir"))     # el botón de confirmación del diálogo
    esperar(4)
    if "Entrar a la clase" not in botones():
        print(ui("invoke", "Clase en vivo")); esperar(4)
comprobar("S1 · teclado numérico y «Entrar a la clase»", "Entrar a la clase" in botones(), str(botones()))


# ------------------------------------------------------------------ 1 · el profesor abre la clase
st, s = api("POST", "/api/aula/sesiones/", {"via": "leccion", "curso_ref": C, "leccion_ref": "l1-three-states", "fuente": "ejemplo",
                                          **PROF, "profesor_rotulo": "Prof. Prueba", "superficie": "pantalla"})
assert st == 201, (st, s)
SID, CODIGO = s["id"], s["codigo_union"]
print("sesion", SID, "codigo", CODIGO, "selector inicial", s["selector"]["objeto_ref"])

# ------------------------------------------------------------------ 2 · el alumno escribe el código en S1
for d in CODIGO:
    print(ui("invoke", d), end=" ")
print()
t = pantalla("01-s1-codigo")
print(ui("invoke", "Entrar a la clase"))
esperar(5)
t = pantalla("02-s2-inicial")
comprobar("S2 · entra a la clase y pinta el selector inicial (lámina 1 de la presentación)",
          "Todo lo que nos rodea es materia" in t or "materia" in t.lower(), t.replace("\n", " | ")[:300])
comprobar("S2 · con seguimiento no hay mandos de navegación", "Siguiente" not in t and "Anterior" not in t)
st, e = api("GET", f"/api/aula/sesiones/{SID}/")
PIDS = [p["id"] for p in e["participantes"]]
comprobar("Backend · el participante quedó conectado", len(PIDS) == 1 and e["participantes"][0]["estado"] == "conectado", str([(p["persona_id"], p["estado"], p.get("dispositivo")) for p in e["participantes"]]))
PART = PIDS[0] if PIDS else ""

# ------------------------------------------------------------------ 3 · el profesor avanza de lámina (selector)
api("POST", f"/api/aula/sesiones/{SID}/selector/", {"objeto_ref": "l1-lecture", "unidad_ref": "l1-lecture-s2", **PROF})
esperar(4)
t = pantalla("03-s2-lamina2")
comprobar("Selector · la tableta sigue a la lámina 2 sin tocar nada (≤ 4 s)", "Tres estados, tres formas" in t, t.replace("\n", " | ")[:200])

# ------------------------------------------------------------------ 4 · el profesor proyecta otro objeto (lectura)
api("POST", f"/api/aula/sesiones/{SID}/selector/", {"objeto_ref": "l1-explanation", **PROF})
esperar(4)
t = pantalla("04-s2-lectura")
comprobar("Selector · cambiar de objeto (lectura) también se sigue solo", "Escucha y repasa" in t or "repasa" in t.lower(), t.replace("\n", " | ")[:200])

# ------------------------------------------------------------------ 5 · lanzamiento de un RECURSO (la presentación) mientras se proyecta la lectura
st, d1 = api("POST", f"/api/aula/sesiones/{SID}/distribuciones/", {"clase": "recurso", "objeto_ref": "l1-lecture", **PROF})
assert st == 201, (st, d1)
esperar(4)
t = pantalla("05-s2-recurso-lanzado")
comprobar("Lanzamiento de recurso · aparece como tarjeta con «Abrir», NO reemplaza lo proyectado",
          "Abrir" in t and ("Escucha y repasa" in t or "repasa" in t.lower()), t.replace("\n", " | ")[:300])
st, e = api("GET", f"/api/aula/sesiones/{SID}/estado/?participante={PART}")
comprobar("Backend · el lanzamiento llega en `pendientes` con entrega pendiente", e["pendientes"] and e["pendientes"][0]["entrega"] == "pendiente", json.dumps(e["pendientes"][0], ensure_ascii=False)[:200] if e["pendientes"] else "sin pendientes")
st, e = api("GET", f"/api/aula/sesiones/{SID}/")
ent = e["distribuciones"][0]["entregas"] if e.get("distribuciones") else {}
comprobar("Backend · OPS vería «0 de 1 tabletas lo abrieron» hasta que el alumno toque Abrir", ent.get("entregados", ent.get("total", 0) - ent.get("pendientes", 0)) == 0, json.dumps(ent))

# ------------------------------------------------------------------ 6 · el alumno abre el recurso; el profesor cambia el selector mientras tanto
print(ui("invoke", "Abrir"))
esperar(4)
t = pantalla("06-s2-recurso-abierto")
comprobar("Recurso abierto · la tableta muestra el recurso lanzado con mandos propios (Anterior/Siguiente)",
          ("Todo lo que nos rodea" in t or "materia" in t.lower()) and ("Siguiente" in t), t.replace("\n", " | ")[:300])
st, e = api("GET", f"/api/aula/sesiones/{SID}/")
ent = e["distribuciones"][0]["entregas"]
comprobar("Backend · al abrir se confirmó la entrega (1 de 1)", ent.get("pendientes") == 0, json.dumps(ent))
api("POST", f"/api/aula/sesiones/{SID}/selector/", {"objeto_ref": "l1-lab-phet", **PROF})
esperar(4)
t = pantalla("07-s2-selector-cambia-con-recurso-abierto")
comprobar("Mientras el recurso está abierto, un cambio de selector del profesor NO se sigue (la tableta se queda en el recurso)",
          "Laboratorio" not in t and "Siguiente" in t, t.replace("\n", " | ")[:300])

# ------------------------------------------------------------------ 7 · bloqueo de pantallas con el recurso abierto
api("POST", f"/api/aula/sesiones/{SID}/controles/", {"tipo": "bloqueo", "activo": True, **PROF})
esperar(4)
t = pantalla("08-s2-bloqueo")
comprobar("Bloqueo · «Mira al frente» se impone aunque el alumno esté en el recurso", "Mira al frente" in t, t.replace("\n", " | ")[:200])
api("POST", f"/api/aula/sesiones/{SID}/controles/", {"tipo": "bloqueo", "activo": False, **PROF})
esperar(4)
t = pantalla("09-s2-desbloqueo")
comprobar("Desbloqueo · vuelve a lo que estaba (el recurso abierto)", "Mira al frente" not in t and "Siguiente" in t, t.replace("\n", " | ")[:200])

# ------------------------------------------------------------------ 8 · el profesor retira el recurso: la tableta debe volver al selector (laboratorio)
api("POST", f"/api/aula/sesiones/{SID}/distribuciones/{d1['id']}/cerrar/", {**PROF})
esperar(5)
t = pantalla("10-s2-recurso-retirado")
comprobar("Retirar el recurso · la tableta vuelve al selector vigente (laboratorio)", "Laboratorio" in t or "Partículas" in t or "part" in t.lower(), t.replace("\n", " | ")[:300])
comprobar("Retirar el recurso · la tarjeta desaparece", "Abrir" not in t and "Volver a la clase" not in t)

# ------------------------------------------------------------------ 9 · lanzamiento de una ACTIVIDAD
api("POST", f"/api/aula/sesiones/{SID}/selector/", {"objeto_ref": "l1-activity", **PROF})
esperar(3)
st, d2 = api("POST", f"/api/aula/sesiones/{SID}/distribuciones/", {"clase": "actividad", "objeto_ref": "l1-activity", "intentos_permitidos": 2, **PROF})
assert st == 201, (st, d2)
esperar(4)
t = pantalla("11-s2-actividad-lanzada")
comprobar("Lanzamiento de actividad · tarjeta verde con «Abrir»; la vista previa de la actividad ya está proyectada por selector",
          "Abrir" in t and "Practica" in t, t.replace("\n", " | ")[:300])
comprobar("Actividad · la vista previa no muestra claves ni botones de responder", "isCorrect" not in t and "Enviar" not in t)
print(ui("invoke", "Abrir"))
esperar(4)
t = pantalla("12-s2-actividad-abierta")
comprobar("Actividad abierta · se ve la actividad con sus preguntas (vista previa, sin envío)", "Practica" in t and ("pregunta" in t.lower() or "Opción" in t), t.replace("\n", " | ")[:300])
st, e = api("GET", f"/api/aula/sesiones/{SID}/")
ent = [d for d in e["distribuciones"] if d["id"] == d2["id"]][0]["entregas"]
comprobar("Backend · la actividad quedó entregada al abrirla", ent.get("pendientes") == 0, json.dumps(ent))

# ------------------------------------------------------------------ 10 · liberar el seguimiento
api("POST", f"/api/aula/sesiones/{SID}/controles/", {"tipo": "seguimiento", "activo": False, **PROF})
print(ui("invoke", "Volver a la clase"))
esperar(4)
t = pantalla("13-s2-sin-seguimiento")
comprobar("Seguimiento liberado · aparecen los mandos y el alumno puede navegar", "Siguiente" in t or "Anterior" in t or "Practica" in t, t.replace("\n", " | ")[:200])
api("POST", f"/api/aula/sesiones/{SID}/controles/", {"tipo": "seguimiento", "activo": True, **PROF})
esperar(4)

# ------------------------------------------------------------------ 11 · aviso y cierre
api("POST", f"/api/aula/sesiones/{SID}/avisos/", {"texto": "Dos minutos para terminar", **PROF})
esperar(3)
t = pantalla("14-s2-aviso")
comprobar("Aviso · banda no bloqueante con el texto", "Dos minutos" in t, t.replace("\n", " | ")[:200])
api("POST", f"/api/aula/sesiones/{SID}/distribuciones/{d2['id']}/cerrar/", {**PROF})
st, c = api("POST", f"/api/aula/sesiones/{SID}/cerrar/", {**PROF})
comprobar("Backend · la clase cierra", st == 200 and c.get("estado") == "cerrada", str((st, c.get("estado"), c.get("detail"))))
esperar(5)
t = pantalla("15-s2-cerrada")
comprobar("Cierre · la tableta avisa «La clase terminó»", "termin" in t.lower(), t.replace("\n", " | ")[:200])
print(ui("invoke", "Volver al men"))
esperar(2)
pantalla("16-final")

print("\n=== INFORME ===")
for n, ok, d in informe:
    print(("OK   " if ok else "FALLA"), n)
(S / "informe.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")

"""Segunda tanda: el recurso lanzado abierto en la tableta frente al selector del profesor, dos recursos
seguidos, seguimiento liberado, tableta bloqueada por MOD-009 y el cierre. Reutiliza los ayudantes de la
primera tanda."""
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
    ui("shot", salida=str(CAP / f"{nombre}.png"))
    texto = ui("text") + "\n" + "\n".join("[botón] " + b for b in botones())
    (CAP / f"{nombre}.txt").write_text(texto, encoding="utf-8")
    return texto


def botones():
    return [l.split("\t")[1] for l in ui("list").splitlines() if l.startswith("Button")]


def comprobar(nombre, condicion, detalle=""):
    informe.append((nombre, bool(condicion), detalle))
    print(("OK   " if condicion else "FALLA"), nombre, ("· " + detalle[:260]) if detalle else "")


def esperar(seg=4.0):
    time.sleep(seg)


def resumen(t):
    return t.replace("\n", " | ")[:260]


# ------------------------------------------------------------------ 0 · S1 y clase nueva
b = botones()
if any("Volver al men" in x for x in b):
    print(ui("invoke", "Volver al men")); esperar(3); b = botones()
if any("Clase en vivo" in x for x in b):
    print(ui("invoke", "Clase en vivo")); esperar(4); b = botones()
if "Entrar a la clase" not in b and "Salir" in b:
    print(ui("invoke", "Salir")); esperar(2); print(ui("invoke", "Salir")); esperar(4)
    if any("Clase en vivo" in x for x in botones()):
        print(ui("invoke", "Clase en vivo")); esperar(4)
assert "Entrar a la clase" in botones(), botones()
# cerrar cualquier clase abierta del profesor de prueba (un profesor sólo tiene una abierta)
st, abiertas = api("GET", "/api/aula/sesiones/?estado=abierta&profesor=prof-prueba-claude")
for x in abiertas.get("sesiones", []):
    api("POST", f"/api/aula/sesiones/{x['id']}/cerrar/", {"forzar": True, **PROF})
ui("invoke", "Borrar")     # HALLAZGO: S1 conserva el código anterior al volver
st, s = api("POST", "/api/aula/sesiones/", {"via": "leccion", "curso_ref": C, "leccion_ref": "l1-three-states", "fuente": "ejemplo",
                                          **PROF, "profesor_rotulo": "Prof. Prueba", "superficie": "pantalla"})
assert st == 201, (st, s)
SID, CODIGO = s["id"], s["codigo_union"]
for d in CODIGO:
    ui("invoke", d)
print(ui("invoke", "Entrar a la clase")); esperar(5)
t = pantalla("20-s2-inicial")
comprobar("S2 · lámina 1 proyectada al entrar", "Lámina 1 de 3" in t, resumen(t))
st, e = api("GET", f"/api/aula/sesiones/{SID}/")
PART = e["participantes"][0]["id"]; DISP = e["participantes"][0].get("dispositivo_id")
print("participante", PART, "dispositivo", DISP)

# ------------------------------------------------------------------ 1 · recurso lanzado y abierto; el profesor sigue proyectando
st, d1 = api("POST", f"/api/aula/sesiones/{SID}/distribuciones/", {"clase": "recurso", "objeto_ref": "l1-lecture", **PROF})
assert st == 201, (st, d1)
esperar(4)
t = pantalla("21-s2-recurso-tarjeta")
comprobar("Recurso lanzado · tarjeta «Tu profesor te lo acaba de enviar» con botón Abrir; lo proyectado (lámina 1) sigue en pantalla",
          "Abrir" in botones() and "Lámina 1 de 3" in t, resumen(t))
print(ui("invoke", "Abrir")); esperar(4)
t = pantalla("22-s2-recurso-abierto")
comprobar("Recurso abierto · se ve la presentación lanzada con mandos Anterior/Siguiente (navegación libre)",
          "Todo lo que nos rodea es materia" in t and any("Siguiente" in b for b in botones()), resumen(t))
st, e = api("GET", f"/api/aula/sesiones/{SID}/")
ent = [d for d in e["distribuciones"] if d["id"] == d1["id"]][0]["entregas"]
comprobar("Backend · al abrir se confirmó la entrega (OPS: 1 de 1 lo abrieron)", ent["entregadas"] == 1, json.dumps(ent)[:120])
print(ui("invoke", "Siguiente")); esperar(2)
t = pantalla("23-s2-recurso-navegado")
comprobar("Recurso abierto · el alumno pasa de lámina por su cuenta", "Lámina 2 de 3" in t, resumen(t))
api("POST", f"/api/aula/sesiones/{SID}/selector/", {"objeto_ref": "l1-activity", **PROF}); esperar(5)
t = pantalla("24-s2-selector-ignorado")
comprobar("HALLAZGO · con el recurso abierto, el nuevo selector del profesor (actividad) NO se sigue: la tableta se queda en el recurso",
          "Practica" not in t and "Lámina 2 de 3" in t, resumen(t))
# bloqueo con el recurso abierto
api("POST", f"/api/aula/sesiones/{SID}/controles/", {"tipo": "bloqueo", "activo": True, **PROF}); esperar(4)
ui("shot", salida=str(CAP / "25-s2-bloqueo-con-recurso.png"))
api("POST", f"/api/aula/sesiones/{SID}/controles/", {"tipo": "bloqueo", "activo": False, **PROF}); esperar(4)
t = pantalla("26-s2-desbloqueo-con-recurso")
comprobar("Desbloqueo · vuelve al recurso abierto, no al selector", "Lámina 2 de 3" in t, resumen(t))

# ------------------------------------------------------------------ 2 · segundo recurso mientras el primero está abierto
st, d2 = api("POST", f"/api/aula/sesiones/{SID}/distribuciones/", {"clase": "recurso", "media_ref": "pdf-lab-guide", "rotulo": "Guía del laboratorio", **PROF})
assert st == 201, (st, d2)
esperar(4)
t = pantalla("27-s2-segundo-recurso")
comprobar("Segundo recurso · aparece otra tarjeta; los botones dicen «Volver a la clase» (no se puede abrir el segundo sin volver)",
          "Guía del laboratorio" in t and botones().count("Volver a la clase") >= 1, resumen(t))
print(ui("invoke", "Volver a la clase")); esperar(4)
t = pantalla("28-s2-volver")
comprobar("Volver a la clase · se pinta el selector vigente (actividad) y las dos tarjetas ofrecen Abrir",
          "Practica" in t and botones().count("Abrir") == 2, resumen(t))
st, e = api("GET", f"/api/aula/sesiones/{SID}/estado/?participante={PART}")
comprobar("Backend · un recurso sólo con media_ref (sin objeto) llega en pendientes con su rótulo",
          any(p["media_ref"] == "pdf-lab-guide" and p["rotulo"] == "Guía del laboratorio" for p in e["pendientes"]), json.dumps(e["pendientes"], ensure_ascii=False)[:200])
b = botones()
print(ui("invoke", "Abrir")); esperar(4)     # abre la primera tarjeta (la presentación)
t = pantalla("29-s2-abrir-primera")
api("POST", f"/api/aula/sesiones/{SID}/distribuciones/{d1['id']}/cerrar/", {**PROF}); esperar(5)
t = pantalla("30-s2-primera-retirada")
comprobar("Retirar el recurso abierto · la tableta vuelve al selector (actividad); queda la tarjeta del segundo",
          "Practica" in t and botones().count("Abrir") == 1, resumen(t))
api("POST", f"/api/aula/sesiones/{SID}/distribuciones/{d2['id']}/cerrar/", {**PROF}); esperar(4)

# ------------------------------------------------------------------ 3 · seguimiento liberado: ¿la tableta sigue al profesor?
api("POST", f"/api/aula/sesiones/{SID}/selector/", {"objeto_ref": "l1-lecture", "unidad_ref": "l1-lecture-s1", **PROF}); esperar(4)
api("POST", f"/api/aula/sesiones/{SID}/controles/", {"tipo": "seguimiento", "activo": False, **PROF}); esperar(4)
t = pantalla("31-s2-sin-seguimiento")
comprobar("Seguimiento liberado · aparecen los mandos SIN esperar a que el profesor cambie el selector", any("Siguiente" in b for b in botones()), resumen(t))
if not any("Siguiente" in b for b in botones()):
    api("POST", f"/api/aula/sesiones/{SID}/selector/", {"objeto_ref": "l1-lecture", "unidad_ref": "l1-lecture-s2", **PROF}); esperar(4)
    comprobar("Seguimiento liberado · los mandos aparecen sólo cuando el profesor cambia el selector (a lámina 2)", any("Siguiente" in b for b in botones()), resumen(pantalla("31b-s2-mandos-tras-selector")))
    print(ui("invoke", "Anterior")); esperar(2)
    t = pantalla("32-s2-alumno-navega")
    comprobar("Seguimiento liberado · el alumno vuelve a la lámina 1 por su cuenta", "Lámina 1 de 3" in t, resumen(t))
else:
    print(ui("invoke", "Siguiente")); esperar(2)
api("POST", f"/api/aula/sesiones/{SID}/selector/", {"objeto_ref": "l1-lecture", "unidad_ref": "l1-lecture-s1", **PROF}); esperar(5)
t = pantalla("33-s2-selector-sin-seguimiento")
comprobar("HALLAZGO · sin seguimiento, un nuevo selector del profesor (lámina 1) igual se impone sobre lo que el alumno estaba viendo",
          "Lámina 1 de 3" in t, resumen(t))
api("POST", f"/api/aula/sesiones/{SID}/controles/", {"tipo": "seguimiento", "activo": True, **PROF}); esperar(4)
t = pantalla("34-s2-seguimiento-de-nuevo")
comprobar("Seguimiento activado de nuevo · desaparecen los mandos SIN esperar a un cambio de selector", not any("Siguiente" in b for b in botones()), resumen(t))

# ------------------------------------------------------------------ 4 · tableta bloqueada por MOD-009: excluida del lanzamiento
st, disp = api("GET", "/api/dispositivos/")
lista = disp if isinstance(disp, list) else disp.get("dispositivos") or disp.get("items") or []
mio = next((d for d in lista if d.get("id") == DISP or "DESKTOP" in str(d.get("identificador"))), None)
print("dispositivo", DISP, "->", mio and mio.get("identificador"), "bloqueado", mio and mio.get("bloqueado"), "| inventario:", [(d.get("identificador"), d.get("bloqueado")) for d in lista][:5], "| respuesta:", str(disp)[:160])
if mio:
    st, r = api("POST", f"/api/dispositivos/{mio['id']}/bloquear/", {**PROF})
    comprobar("MOD-009 · bloquear la tableta responde 200", st == 200, str((st, r.get("detail"))))
    st, d3 = api("POST", f"/api/aula/sesiones/{SID}/distribuciones/", {"clase": "actividad", "objeto_ref": "l1-activity", **PROF})
    comprobar("Lanzar una actividad con la única tableta bloqueada es 409 sin_participantes_admitidos con excluidos_bloqueados",
              st == 409 and d3.get("codigo") == "sin_participantes_admitidos" and d3.get("excluidos_bloqueados") == ["alumno-prueba"], json.dumps(d3, ensure_ascii=False)[:200])
    st, d4 = api("POST", f"/api/aula/sesiones/{SID}/distribuciones/", {"clase": "recurso", "objeto_ref": "l1-explanation", **PROF})
    comprobar("Lanzar un recurso con la tableta bloqueada se crea (201) sin destinatarios y con la tableta en excluidos_bloqueados",
              st == 201 and d4.get("destinatarios") == [] and d4.get("excluidos_bloqueados") == ["alumno-prueba"], json.dumps({k: d4.get(k) for k in ("destinatarios", "excluidos_bloqueados", "entregas")}, ensure_ascii=False)[:200])
    esperar(5)
    t = pantalla("35-s2-tableta-bloqueada")
    comprobar("Tableta bloqueada · la tableta NO recibe la tarjeta del recurso", "Abrir" not in botones(), resumen(t))
    st, e = api("GET", f"/api/aula/sesiones/{SID}/estado/?participante={PART}")
    comprobar("Backend · el estado de la tableta dice dispositivo_bloqueado y sin pendientes",
              e["participante"].get("dispositivo_bloqueado") is True and e["pendientes"] == [], json.dumps(e["participante"], ensure_ascii=False)[:200])
    comprobar("HALLAZGO · la tableta bloqueada sigue viendo el selector y «Conectado»: no se le avisa del bloqueo", "Conectado" in t and ("Lámina" in t or "Laboratorio" in t), resumen(t))
    api("POST", f"/api/dispositivos/{mio['id']}/desbloquear/", {**PROF})
    api("POST", f"/api/aula/sesiones/{SID}/distribuciones/{d4['id']}/cerrar/", {**PROF})

# ------------------------------------------------------------------ 5 · cierre
st, c = api("POST", f"/api/aula/sesiones/{SID}/cerrar/", {"forzar": True, **PROF})
esperar(5)
t = pantalla("36-s2-cerrada")
comprobar("Cierre · diálogo «La clase terminó»", "La clase terminó" in t, resumen(t))
print(ui("invoke", "Volver al men")); esperar(2)

print("\n=== INFORME 2 ===")
for n, ok, d in informe:
    print(("OK   " if ok else "FALLA"), n)
(S / "informe2.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")

"""RF-30 · Recorrido real del acceso del alumno en AVACOM Student, manejado por UI Automation (sin ratón ni foco), contra un nodo AISLADO:

  1. grupo → nombre → PIN (Juan P.) y «Salir»                         (RF-20, AC-A11)
  2. PIN pendiente: Sofía R. elige su PIN dos veces y entra             (RF-22, AC-A17/A18)
  3. alumno nuevo con un alias que ya existe: acepta «Juan Pé.» y entra (RF-21, AC-A12)
  4. visitante: dos toques, banda amarilla, menú limitado y modo estudio de visita (RF-23/24/25, AC-A14)
  5. preescolar: Lía M. entra tocando su dibujo                          (RF-28, TST-074)
  6. tableta en pausa tras 5 PIN equivocados: cuenta atrás, teclado apagado y «Entrar como visitante» a la vista (RF-26, AC-A13)
Cada paso deja una captura (y su copia con la cuadrícula de tercios) y el texto de la pantalla en salida/capturas-acceso/.

Cómo correrlo (una vez por nodo recién sembrado: la pausa de la tableta dura 2 minutos y el alta de «Juan Pé.» no se repite):
  1. Nodo aparte y sembrado: ver el encabezado de sembrar_acceso.py (AVACOM_LMS_EXIGIR_SESION=1, PIN maestro por variable, runserver 127.0.0.1:8010).
  2. Student compilado (mejor a una carpeta aparte: dotnet build ... -p:OutDir=<carpeta>) y lanzado con
     lanzar-student.ps1 -Exe <carpeta>\\Avacom.Lms.Student.exe -SinFoco   (devuelve el foco: lo que se teclee en otra ventana no cae en la tableta).
  3. python escenario_acceso.py   (variables: AVACOM_AULA_URL, AVACOM_TAMANO=1280x800, AVACOM_VERTICAL=800x1280).
Student comparte Preferences con la instancia del usuario: comprobar antes que no la tiene abierta, guardar una copia de
%LOCALAPPDATA%\\User Name\\com.avacom.lms.student\\Settings\\preferences.dat y devolverla al terminar (dirección http://127.0.0.1:8000, «Ethan Martínez»).
"""
import json, os, subprocess, sys, time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
S = AQUI / "salida"
S.mkdir(exist_ok=True)
PID = (S / "student.pid").read_text().strip()
B = os.environ.get("AVACOM_AULA_URL", "http://127.0.0.1:8010")
TAMANO = os.environ.get("AVACOM_TAMANO", "1280x800")
VERTICAL = os.environ.get("AVACOM_VERTICAL", "800x1280")
CAP = S / "capturas-acceso"
CAP.mkdir(exist_ok=True)
informe = []


def ps(guion, *args):
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(AQUI / guion), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip()


def ui(accion, nombre="", valor="", salida=""):
    args = ["-ProcId", PID, "-Accion", accion]
    if nombre: args += ["-Nombre", nombre]
    if valor: args += ["-Valor", valor]
    if salida: args += ["-Salida", salida]
    return ps("ui-student.ps1", *args)


def pantalla(nombre):
    png = CAP / f"{nombre}.png"
    ui("shot", salida=str(png))
    ps("tercios.ps1", "-Entrada", str(png), "-Salida", str(CAP / f"{nombre}-tercios.png"))
    texto = ui("text")
    (CAP / f"{nombre}.txt").write_text(texto, encoding="utf-8")
    return texto


def comprobar(nombre, condicion, detalle=""):
    informe.append((nombre, bool(condicion), detalle))
    print(("OK   " if condicion else "FALLA"), nombre, ("· " + detalle) if detalle else "", flush=True)


def esperar_texto(sub, timeout=15.0):
    fin = time.time() + timeout
    t = ""
    while time.time() < fin:
        t = ui("text")
        if sub.lower() in t.lower():
            return t
        time.sleep(0.8)
    return t


def botones():
    return [l.split("\t")[1] for l in ui("list").splitlines() if l.startswith("Button") and "\t" in l]


def tocar(nombre):
    r = ui("invoke", nombre=nombre)
    time.sleep(0.35)
    return r.startswith("INVOCADO")


def marcar(pin, listo=True):
    for d in pin:
        tocar(f"Número {d}")
    if listo:
        tocar("Listo")


def salir_al_acceso():
    tocar("Salir")
    return esperar_texto("¿Cuál es tu grupo?", 15)


def main():
    ui("ajustar", valor=TAMANO)
    time.sleep(1.5)
    # ------------------------------------------------------------------ paso 0: dirección del aula
    ui("set", nombre="acceso-direccion", valor=B)
    tocar("Entrar al aula")
    t = esperar_texto("¿Cuál es tu grupo?")
    pantalla("01-grupos")
    comprobar("1 · tras conectar se elige el grupo", "¿Cuál es tu grupo?" in t)
    b = botones()
    comprobar("1 · las dos acciones fijas están a la vista", any("soy nuevo" in x for x in b) and "Entrar como visitante" in b, ", ".join(b))

    # ------------------------------------------------------------------ 1. grupo → nombre → PIN
    tocar("Quinto B")
    t = esperar_texto("¿Quién eres?")
    pantalla("02-nombres")
    b = botones()
    comprobar("1 · la lista sólo trae alias", {"Juan P.", "Ana R.", "Sofía R."} <= set(b), ", ".join(b))
    tocar("Juan P.")
    t = esperar_texto("Hola, Juan P.")
    pantalla("03-pin")
    comprobar("1 · pide el PIN con el teclado propio", "Marca tu PIN" in t and "Número 1" in botones())
    marcar("1234")
    t = esperar_texto("Bienvenido, Juan")
    pantalla("04-menu-juan")
    comprobar("1 · Juan entra con su PIN", "Bienvenido, Juan" in t)
    t = salir_al_acceso()
    comprobar("1 · «Salir» vuelve a los grupos sin nada de Juan", "¿Cuál es tu grupo?" in t and "Juan" not in t)

    # ------------------------------------------------------------------ 2. PIN pendiente
    tocar("Quinto B"); esperar_texto("¿Quién eres?")
    tocar("Sofía R.")
    t = esperar_texto("Elige tu PIN")
    pantalla("05-elegir-pin")
    comprobar("2 · Sofía (PIN pendiente) elige su PIN", "Todavía no tienes PIN" in t)
    marcar("2468")
    t = esperar_texto("Márcalo otra vez")
    comprobar("2 · pide confirmarlo", "Márcalo otra vez" in t)
    marcar("2468")
    t = esperar_texto("Bienvenido, Sofía")
    comprobar("2 · entra con el PIN que eligió", "Bienvenido, Sofía" in t)
    salir_al_acceso()

    # ------------------------------------------------------------------ 3. soy nuevo con alias repetido
    tocar("Quinto B"); esperar_texto("¿Quién eres?")
    tocar("soy nuevo")
    t = esperar_texto("Soy nuevo")
    ui("set", nombre="nuevo-nombre", valor="Juan")
    ui("set", nombre="nuevo-apellido", valor="Pérez")
    pantalla("06-nuevo-datos")
    tocar("Siguiente")
    t = esperar_texto("Elige un PIN")
    comprobar("3 · tras el nombre pide el PIN", "Elige un PIN" in t)
    marcar("1122")
    esperar_texto("Márcalo otra vez")
    marcar("1122")
    t = esperar_texto("Ya hay alguien llamado")
    pantalla("07-nuevo-alias-repetido")
    sugerido = next((x for x in botones() if x.startswith("Usar «")), "")
    comprobar("3 · alias repetido: ofrece una letra más", "Ya hay alguien llamado Juan P." in t and sugerido != "", sugerido)
    tocar("Usar «")
    t = esperar_texto("Bienvenido, Juan")
    comprobar("3 · con un toque se crea y entra", "Bienvenido, Juan" in t)
    salir_al_acceso()

    # ------------------------------------------------------------------ 4. visitante
    tocar("Entrar como visitante")
    t = esperar_texto("¿Entrar como visitante?")
    pantalla("08-visitante-confirmar")
    tocar("Sí, entrar como visitante")
    t = esperar_texto("Entraste como visitante")
    pantalla("09-menu-visitante")
    comprobar("4 · entra en dos toques con la banda amarilla", "lo que hagas no se guarda en tu historial" in t)
    comprobar("4 · el menú de visita no ofrece Exámenes", "Exámenes" not in botones())
    tocar("Estudio")
    t = esperar_texto("Estás como visitante")
    pantalla("10-estudio-visitante")
    comprobar("4 · modo estudio de visita: sólo dónde practicar", "Estás como visitante" in t and "¿Quién eres?" not in t)
    tocar("Cerrar el modo estudio")
    esperar_texto("Bienvenido")
    t = salir_al_acceso()
    comprobar("4 · al salir la banda desaparece", "lo que hagas no se guarda" not in t)

    # ------------------------------------------------------------------ 5. preescolar con dibujos
    tocar("Preescolar A"); esperar_texto("¿Quién eres?")
    tocar("Lía M.")
    t = esperar_texto("Toca tu dibujo")
    pantalla("11-dibujos")
    comprobar("5 · preescolar muestra los dibujos", "Gato" in botones())
    tocar("Gato")
    t = esperar_texto("Bienvenido, Lía")
    comprobar("5 · Lía entra tocando su dibujo", "Bienvenido, Lía" in t)
    salir_al_acceso()

    # ------------------------------------------------------------------ composición vertical (tableta en vertical) antes de la pausa
    ui("ajustar", valor=VERTICAL)
    time.sleep(1.5)
    pantalla("12-grupos-vertical")
    tocar("Quinto B"); esperar_texto("¿Quién eres?")
    tocar("Ana R."); esperar_texto("Hola, Ana R.")
    pantalla("13-pin-vertical")
    ui("ajustar", valor=TAMANO)
    time.sleep(1.5)

    # ------------------------------------------------------------------ 6. tableta en pausa (lo último: dura 2 minutos)
    for _ in range(5):
        marcar("9999")
        time.sleep(0.6)
    t = esperar_texto("Esperemos un momento")
    pantalla("14-pausa")
    comprobar("6 · cinco fallos: la tableta espera con cuenta atrás", "Esperemos un momento" in t and "o entra como visitante" in t)
    comprobar("6 · no nombra a ningún compañero", "Juan" not in t and "Sofía" not in t)
    comprobar("6 · el teclado queda apagado", not tocar("Número 1"))
    comprobar("6 · «Entrar como visitante» sigue a la vista", "Entrar como visitante" in botones())
    tocar("Entrar como visitante"); esperar_texto("¿Entrar como visitante?")
    tocar("Sí, entrar como visitante")
    t = esperar_texto("Entraste como visitante")
    comprobar("6 · en pausa, el visitante sigue entrando", "Entraste como visitante" in t)
    salir_al_acceso()

    print()
    fallas = [n for n, ok, _ in informe if not ok]
    print(f"{len(informe) - len(fallas)} de {len(informe)} comprobaciones bien" + (f" · fallaron: {fallas}" if fallas else ""))
    (S / "informe-acceso.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()

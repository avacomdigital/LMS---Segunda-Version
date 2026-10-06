"""
Recorrido de interfaz del acceso de AVACOM OPS Master (RF-31): primer arranque y hoja de acceso, entrada de la administración con PIN maestro y
contraseña provisional, seguridad del aula y cambio del PIN maestro, alta de un profesor con el PIN (con un PIN equivocado antes), grupos con alumnos
«sin confirmar» y «PIN pendiente», «Olvidé mi contraseña», aviso de vencimiento a 12 días, PIN vencido y, en un segundo arranque, que la hoja ya no se
puede ver y el monitor con un visitante vinculado a un alumno.

Todo contra un nodo AISLADO que levanta este mismo guion (base temporal, 127.0.0.1:8010, sesión obligatoria), nunca contra el del aula. OPS corre con un
perfil de pruebas propio (AVACOM_OPS_PERFIL): no toca las preferencias de la OPS de quien trabaja en el equipo. Las ventanas se manejan por UI Automation
(ui-ops.ps1), sin ratón ni teclado, y se capturan con PrintWindow; cada captura sale también con la cuadrícula de tercios (tercios.ps1).

Uso (desde la raíz del repositorio, con OPS compilado para Windows):
    backend\\.venv\\Scripts\\python.exe tests\\Avacom.Lms.Ops.Uia\\recorrido_acceso.py --ops <ruta a Avacom.Lms.Ops.exe> [--salida <carpeta>]

Sale con 0 si todo se cumplió; con 1 y la lista de lo que falló si no.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
BACKEND = RAIZ / "backend"
PUERTO = 8010
NODO = f"http://127.0.0.1:{PUERTO}"
CANDADO = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Temp" / "avacom-gui.lock"

ADMIN_DOC, ADMIN_CLAVE = "1042888795", "Rectoria.Uia.2026!"
PIN_1, PIN_2 = "482915", "739104"
PROFE_DOC, PROFE_CLAVE, PROFE_NUEVA = "52100200", "Profe.Uia.2026", "Nueva.Clave.2026"
TABLETA = "student-uia-01"

resultados: list[tuple[str, bool, str]] = []


def anotar(paso: str, ok: bool, detalle: str = "") -> bool:
    resultados.append((paso, ok, detalle))
    print(("  OK   " if ok else "  FALLA ") + paso + (f" · {detalle}" if detalle else ""), flush=True)
    return ok


# ------------------------------------------------------------------------------------------------------------------------ nodo aislado

def python_backend() -> str:
    for candidato in (BACKEND / ".venv" / "Scripts" / "python.exe", RAIZ.parent.parent.parent / "backend" / ".venv" / "Scripts" / "python.exe"):
        if candidato.exists():
            return str(candidato)
    return sys.executable


def levantar_nodo(db: Path) -> subprocess.Popen:
    env = {**os.environ, "AVACOM_LMS_DB": str(db), "AVACOM_LMS_EXIGIR_SESION": "1", "PYTHONIOENCODING": "utf-8"}
    py = python_backend()
    subprocess.run([py, "manage.py", "migrate", "--noinput"], cwd=BACKEND, env=env, check=True, capture_output=True)
    nodo = subprocess.Popen([py, "manage.py", "runserver", NODO.removeprefix("http://"), "--noreload"], cwd=BACKEND, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{NODO}/health/", timeout=2)
            return nodo
        except Exception:
            time.sleep(1)
    nodo.kill()
    raise RuntimeError(f"El nodo de prueba no arrancó en {NODO}")


def puerto_ocupado(puerto: int) -> bool:
    import socket
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def api(metodo: str, ruta: str, cuerpo: dict | None = None, token: str | None = None) -> tuple[int, dict | list | None]:
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(f"{NODO}{ruta}", data=datos, method=metodo, headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            texto = r.read().decode()
            return r.status, (json.loads(texto) if texto else None)
    except urllib.error.HTTPError as e:
        texto = e.read().decode()
        return e.code, (json.loads(texto) if texto.startswith(("{", "[")) else {"detail": texto})


def mover_vencimiento(db: Path, dias: float) -> None:
    """Simula el paso del tiempo: la versión activa del PIN maestro vence dentro de `dias` días (negativo = ya venció)."""
    vence = int((time.time() + dias * 86400) * 1000)
    with sqlite3.connect(db) as c:
        c.execute("UPDATE m01_pin_maestro SET vence_en = ? WHERE activa = 1", (vence,))


# ------------------------------------------------------------------------------------------------------------------------ OPS por UIA

class Ops:
    def __init__(self, exe: Path, salida: Path, perfil: str, ruta: str | None = None):
        env = {**os.environ, "AVACOM_OPS_PERFIL": perfil, "AVACOM_OPS_SERVIDOR": NODO}
        if ruta:
            env["AVACOM_OPS_RUTA"] = ruta
        self.salida = salida
        self.proceso = subprocess.Popen([str(exe)], env=env)
        self.pid = self.proceso.pid
        time.sleep(6)

    def ui(self, accion: str, nombre: str = "", valor: str = "", salida: str = "", espera: int = 0) -> tuple[int, str]:
        cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(AQUI / "ui-ops.ps1"), "-ProcId", str(self.pid), "-Accion", accion]
        if nombre:
            cmd += ["-Nombre", nombre]
        if valor:
            cmd += ["-Valor", valor]
        if salida:
            cmd += ["-Salida", salida]
        if espera:
            cmd += ["-Espera", str(espera)]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "").strip()

    def esperar(self, texto: str, ms: int = 15000) -> bool:
        return self.ui("esperar", valor=texto, espera=ms)[0] == 0

    def invocar(self, boton: str) -> bool:
        codigo, salida = self.ui("invoke", nombre=boton)
        if codigo != 0:
            print(f"     ({salida})", flush=True)
        return codigo == 0

    def escribir(self, campo: str, valor: str) -> bool:
        return self.ui("set", nombre=campo, valor=valor)[0] == 0

    def pin(self, digitos: str) -> bool:
        return self.ui("pin", valor=digitos)[0] == 0

    def textos(self) -> list[str]:
        return self.ui("text")[1].splitlines()

    def captura(self, nombre: str) -> Path:
        destino = self.salida / f"{nombre}.png"
        time.sleep(1.2)   # que terminen las animaciones (fundidos, sacudidas)
        self.ui("shot", salida=str(destino))
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(AQUI / "tercios.ps1"),
                        "-Entrada", str(destino), "-Salida", str(self.salida / f"{nombre}-tercios.png")], capture_output=True)
        return destino

    def cerrar(self) -> None:
        subprocess.run(["taskkill", "/PID", str(self.pid), "/F"], capture_output=True)


def tomar_candado() -> None:
    limite = time.time() + 15 * 60
    while True:
        try:
            CANDADO.mkdir(parents=False)
            return
        except FileExistsError:
            if time.time() > limite:
                raise RuntimeError(f"Otra prueba visual tiene el candado {CANDADO} desde hace 15 minutos")
            print("  (otra prueba visual tiene la pantalla; espero 20 s)", flush=True)
            time.sleep(20)


def soltar_candado() -> None:
    try:
        CANDADO.rmdir()
    except OSError:
        pass


def siguiente_a(textos: list[str], rotulo: str) -> str | None:
    for i, t in enumerate(textos):
        if t.startswith(rotulo) and i + 1 < len(textos):
            return textos[i + 1]
    return None


def cerrar_sesion(ops: Ops) -> None:
    ops.invocar("Cerrar sesión")
    ops.esperar("Escribe tu documento y tu contraseña", 15000)


def entrar(ops: Ops, documento: str, clave: str, pin: str | None = None) -> None:
    ops.escribir("Documento", documento)
    ops.escribir("Contraseña", clave)
    ops.invocar("Entrar")
    if pin:
        ops.esperar("PIN maestro de la escuela", 20000)
        ops.pin(pin)


# ------------------------------------------------------------------------------------------------------------------------ el recorrido

def recorrido(exe: Path, salida: Path, db: Path) -> None:
    perfil = f"uia-{int(time.time())}"
    ops = Ops(exe, salida, perfil)
    try:
        # 1 · primer arranque (AC-A01, AC-A02)
        anotar("el acceso abre solo el primer arranque con el nodo sin instalar", ops.esperar("Paso 1 de 5", 25000))
        ops.captura("01-primer-arranque-pais")
        ops.invocar("México")
        ops.invocar("Siguiente")
        ops.esperar("Paso 2 de 5")
        ops.escribir("Nombre del aula", "IE Prueba UIA · Sede norte")
        anotar("el código del aula sale solo del nombre", ops.esperar("IE-PRUEBA-UIA-SEDE-NORTE", 5000))
        ops.invocar("Siguiente")
        ops.esperar("Paso 3 de 5")
        ops.escribir("Documento del administrador", ADMIN_DOC)
        ops.escribir("Nombres del administrador", "Ana")
        ops.escribir("Apellidos del administrador", "Pérez")
        ops.invocar("Siguiente")
        anotar("paso del PIN maestro con la regla explicada", ops.esperar("Paso 4 de 5", 8000))
        ops.captura("02-primer-arranque-pin")
        ops.pin("123456")
        anotar("AC-A02 · 123456 se rechaza por trivial y se explica", ops.esperar("demasiado fácil de adivinar", 8000))
        ops.pin(PIN_1)
        anotar("pide marcar el PIN otra vez", ops.esperar("Márcalo otra vez para confirmar", 5000))
        ops.pin(PIN_1)
        anotar("AC-A01 · instalado con el PIN: aparece la hoja de acceso", ops.esperar("Paso 5 de 5", 30000))
        textos = ops.textos()
        clave_inicial = siguiente_a(textos, "Contraseña inicial del administrador")
        anotar("la hoja muestra la contraseña inicial y el PIN maestro", bool(clave_inicial) and "482 915" in textos, f"contraseña de {len(clave_inicial or '')} caracteres")
        ops.captura("03-hoja-de-acceso")
        ops.invocar("Ya la entregué")
        anotar("al confirmar la hoja vuelve al acceso con el aviso", ops.esperar("el aula quedó instalada", 15000))
        ops.captura("04-acceso-documento-contrasena")
        anotar("con PIN vigente se ofrecen «Crear mi usuario» y «Olvidé mi contraseña»", "Crear mi usuario" in ops.ui("list")[1] and "Olvidé mi contraseña" in ops.ui("list")[1])

        # 2 · la administración entra con contraseña provisional + PIN maestro y elige su contraseña
        entrar(ops, ADMIN_DOC, clave_inicial or "", PIN_1)
        anotar("la administración pasa por el PIN maestro y llega a «Elige tu contraseña»", ops.esperar("Entraste con una contraseña provisional", 20000))
        ops.captura("05-elige-tu-contrasena")
        ops.escribir("Contraseña nueva", ADMIN_CLAVE)
        ops.escribir("Repite la contraseña nueva", ADMIN_CLAVE)
        ops.invocar("Guardar y entrar")
        anotar("con la contraseña propia llega al tablero, con «Seguridad del aula»", ops.invocar("Seguridad del aula"))

        # 3 · seguridad del aula y cambio del PIN maestro
        anotar("seguridad del aula lee el estado real del PIN", ops.esperar("Vigente", 15000) and ops.esperar("Días restantes", 3000))
        ops.captura("06-seguridad-del-aula")
        ops.invocar("Cambiar el PIN maestro")
        ops.esperar("Marca el PIN maestro nuevo", 8000)
        ops.pin(PIN_2)
        ops.esperar("Márcalo otra vez", 5000)
        ops.pin(PIN_2)
        anotar("cambio del PIN maestro: nueva versión con su vencimiento", ops.esperar("El PIN maestro nuevo ya vale", 20000))
        ops.captura("07-pin-cambiado")
        ops.invocar("Menú principal")
        cerrar_sesion(ops)

        # Datos del aula por la API, como los dejaría la administración: un grupo, un alumno del padrón (PIN pendiente), una tableta, un alumno que se
        # registró solo (sin confirmar) y un visitante.
        codigo, s = api("POST", "/api/acceso/sesiones/", {"identificador": ADMIN_DOC, "secreto": ADMIN_CLAVE, "dispositivo": "", "pin_maestro": PIN_2})
        token = s.get("token") if isinstance(s, dict) else None
        _, grupo = api("POST", "/api/acceso/padron/grupos/", {"nombre": "Quinto B", "nivel_clave": "primaria"}, token)
        grupo_id = grupo.get("id") if isinstance(grupo, dict) else None
        api("POST", "/api/acceso/padron/estudiantes/", {"nombres": "Sofía", "apellidos": "Gómez", "documento": "", "grupo_id": grupo_id}, token)
        api("POST", "/api/dispositivos/latido/", {"identificador_hw": TABLETA, "nombre": "Tableta 7", "plataforma": "android", "version_app": "uia", "tipo": "TABLETA"})
        api("POST", "/api/acceso/estudiantes/registro/", {"grupo_id": grupo_id, "nombres": "Luis", "apellidos": "Mora", "pin": "2468", "dispositivo": TABLETA})
        codigo_v, _ = api("POST", "/api/acceso/sesiones/visitante/", {"dispositivo": TABLETA, "grupo_id": grupo_id})
        anotar("datos del aula sembrados por la API", codigo == 200 and bool(grupo_id) and codigo_v == 200, f"login {codigo}, visitante {codigo_v}")

        # 4 · crear mi usuario (RF-06, AC-A08) con un PIN equivocado antes
        ops.invocar("Crear mi usuario")
        ops.esperar("Paso 1 de 4", 10000)
        ops.escribir("Documento", PROFE_DOC)
        ops.escribir("Nombres", "Marta")
        ops.escribir("Apellidos", "Ríos")
        ops.invocar("Siguiente")
        ops.esperar("Paso 2 de 4")
        ops.escribir("Contraseña", PROFE_CLAVE)
        ops.escribir("Repite la contraseña", PROFE_CLAVE)
        ops.invocar("Siguiente")
        ops.esperar("Paso 3 de 4")
        anotar("los grupos del aula se ofrecen como fichas", ops.invocar("Quinto B"))
        ops.invocar("Siguiente")
        ops.esperar("Paso 4 de 4")
        ops.pin("111222")
        anotar("PIN equivocado: conserva lo escrito y dice los intentos que quedan", ops.esperar("Te quedan 4 intentos", 15000))
        ops.captura("08-crear-mi-usuario-pin")
        ops.pin(PIN_2)
        anotar("AC-A08 · registrado, entra directo al tablero", ops.esperar("Bienvenido, Marta", 25000))
        anotar("el profesor no ve «Seguridad del aula» ni la banda del PIN",
               "Seguridad del aula" not in ops.ui("list")[1] and not any("PIN maestro vence" in t for t in ops.textos()))

        # 5 · grupos: «sin confirmar» y «PIN pendiente» (RF-09b)
        ops.invocar("Grupos")
        anotar("grupos marca «sin confirmar» y «PIN pendiente»", ops.esperar("sin confirmar", 15000) and ops.esperar("PIN pendiente", 3000))
        ops.captura("09-grupos")
        anotar("confirmar al alumno que se registró solo", ops.invocar("Confirmar a Luis M.") and ops.esperar("quedó confirmado", 10000))
        anotar("«Nuevo PIN» no muestra ningún número", ops.invocar("Nuevo PIN para Luis M.") and ops.esperar("elegirá un PIN nuevo", 10000)
               and not any(t.strip().isdigit() and len(t.strip()) >= 4 for t in ops.textos()))
        ops.invocar("Menú principal")
        cerrar_sesion(ops)

        # 6 · olvidé mi contraseña (RF-07, AC-A09)
        ops.invocar("Olvidé mi contraseña")
        ops.esperar("Paso 1 de 3", 10000)
        ops.escribir("Documento", PROFE_DOC)
        ops.invocar("Siguiente")
        ops.esperar("Paso 2 de 3")
        ops.pin(PIN_2)
        ops.esperar("Paso 3 de 3")
        ops.escribir("Contraseña nueva", PROFE_NUEVA)
        ops.escribir("Repite la contraseña nueva", PROFE_NUEVA)
        ops.captura("10-olvide-mi-contrasena")
        ops.invocar("Cambiar mi contraseña")
        anotar("AC-A09 · vuelve al acceso con «Cerramos tus sesiones abiertas»", ops.esperar("Cerramos tus sesiones abiertas", 20000))
        entrar(ops, PROFE_DOC, PROFE_NUEVA)
        anotar("el profesor entra con la contraseña nueva", ops.esperar("CLASSROOM", 20000))
        cerrar_sesion(ops)

        # 7 · vencimiento: a 12 días la administración ve la banda con los días (AC-A05); vencido, nadie se registra (AC-A04)
        mover_vencimiento(db, 11.5)
        entrar(ops, ADMIN_DOC, ADMIN_CLAVE, PIN_2)
        anotar("AC-A05 · banda «vence en 12 días» para la administración", ops.esperar("El PIN maestro vence en 12 días", 20000))
        ops.captura("11-tablero-aviso-vencimiento")
        cerrar_sesion(ops)
        mover_vencimiento(db, -1)
        ops.esperar("Crear mi usuario", 5000)
        ops.invocar("Crear mi usuario")
        anotar("AC-A04 · con el PIN vencido «Crear mi usuario» explica qué pasó", ops.esperar("El PIN maestro venció", 10000))
        ops.captura("12-acceso-pin-vencido")
        entrar(ops, ADMIN_DOC, ADMIN_CLAVE)
        anotar("RN-09 · vencido, la administración entra sin PIN y ve la banda", ops.esperar("El PIN maestro venció", 20000))
        ops.captura("13-tablero-pin-vencido")
        cerrar_sesion(ops)
        entrar(ops, PROFE_DOC, PROFE_NUEVA)
        anotar("RN-09 · vencido, los profesores registrados siguen entrando", ops.esperar("CLASSROOM", 20000))
        cerrar_sesion(ops)
    finally:
        ops.cerrar()

    # 8 · segundo arranque: la hoja confirmada no vuelve (AC-A03) y el monitor muestra al visitante (RF-09c)
    mover_vencimiento(db, 200)
    ops = Ops(exe, salida, perfil, ruta="activity-monitor")
    try:
        anotar("AC-A03 · al volver a abrir OPS la hoja ya no aparece", ops.esperar("Escribe tu documento y tu contraseña", 25000)
               and not any("Hoja de acceso" in t for t in ops.textos()))
        entrar(ops, PROFE_DOC, PROFE_NUEVA)
        anotar("el monitor lista al visitante con su tableta", ops.esperar("Visitante", 20000) and ops.esperar("1 ahora", 5000))
        ops.captura("14-monitor-visitantes")
        ops.invocar("Vincular Visitante")
        ops.esperar("¿Quién era?", 10000)
        anotar("RN-44 · la visita se vincula a un alumno", ops.invocar("Sofía Gómez") and ops.esperar("quedó acreditado a Sofía Gómez", 15000))
        ops.captura("15-monitor-vinculado")
    finally:
        ops.cerrar()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ops", required=True, help="Ruta a Avacom.Lms.Ops.exe compilado para Windows")
    p.add_argument("--salida", default=str(AQUI / "salida"), help="Carpeta de capturas (por defecto, salida/ junto al guion)")
    p.add_argument("--puerto", type=int, default=PUERTO, help="Puerto del nodo aislado (8010 por defecto; otro si ya hay una prueba usándolo)")
    args = p.parse_args()
    global NODO
    NODO = f"http://127.0.0.1:{args.puerto}"
    if puerto_ocupado(args.puerto):
        print(f"El puerto {args.puerto} ya está en uso: usa --puerto con otro libre.")
        return 2
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    trabajo = Path(tempfile.mkdtemp(prefix="ops-uia-"))
    db = trabajo / "nodo.sqlite3"
    print(f"Nodo aislado en {NODO} con la base {db}", flush=True)
    nodo = levantar_nodo(db)
    tomar_candado()
    try:
        recorrido(Path(args.ops), salida, db)
    finally:
        soltar_candado()
        nodo.kill()
        shutil.rmtree(trabajo, ignore_errors=True)
    fallos = [r for r in resultados if not r[1]]
    print(f"\n{len(resultados) - len(fallos)} de {len(resultados)} comprobaciones cumplidas. Capturas en {salida}")
    for paso, _, detalle in fallos:
        print(f"  FALLÓ: {paso} {detalle}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())

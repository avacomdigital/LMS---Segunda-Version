r"""
MOD-018 · aceptación de la licencia sobre lo que se ENTREGA, sin ventanas: el backend EMPAQUETADO del instalador (dist/staging/Runtime + Backend, con su Python embebido y Daphne, clasificado como
PRODUCCIÓN por su marcador `.avacom-canal`) trabajando con el paquete PORTÁTIL del emisor (tools/licencias/dist). Todo ocurre en una carpeta temporal: copia el paquete, redirige %ProgramData%
y el puerto es propio, así que no toca ni el nodo del aula (:8000) ni ninguna instalación real.

Fase A · como se entrega (produccion.json vacío)
  · el nodo dice modo «firmada», entorno «produccion» y «sin_licencia» (evaluación de unos 30 días);
  · escribe su solicitud con la huella de ESTE equipo;
  · una licencia firmada con la llave de DESARROLLO se rechaza (400 kid_desconocido) y el estado no cambia;
  · una licencia del emisor empaquetado con una llave que el nodo todavía no conoce, también.
Fase B · tras la «ceremonia» (la pública del emisor entra en produccion.json de la COPIA)
  · la de desarrollo sigue rechazada; la del emisor empaquetado se activa y el nodo queda «activa» con el aula, la serie, los límites y los módulos del plan;
  · tras reiniciar el proceso del nodo la licencia sigue activa (espejo y anclas en la carpeta de estado);
  · la carpeta de estado quedó en el %ProgramData% redirigido y el real no se tocó.

Uso (desde la raíz del repositorio, después de compilar el instalador —deja dist/staging— y el emisor —deja tools/licencias/dist—):
    backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\licencia_paquete.py [--puerto 8016] [--staging <dist\staging>] [--emisor <carpeta del emisor portátil>]
Sale con 0 si todo se cumplió; con 1 y la lista de lo que falló si no (≈ 1 minuto). Sólo corre en un árbol de desarrollo: usa la llave de desarrollo de las pruebas para comprobar que el paquete NO la acepta.
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True                   # que el guion no deje __pycache__ en tests/ (git no lo ignora ahí)
AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
FRASE = "frase-de-aceptacion-0123456789"         # sólo para la llave de esta prueba (el emisor la toma de AVACOM_EMISOR_FRASE)

spec = importlib.util.spec_from_file_location("recorrido_licencia", AQUI / "recorrido_licencia.py")
rl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rl)                      # define la siembra y la firma de licencias de prueba; no corre nada
ra = rl.ra
anotar = ra.anotar


def copiar(origen: Path, destino: Path) -> None:
    r = subprocess.run(["robocopy", str(origen), str(destino), "/E", "/MT:16", "/NFL", "/NDL", "/NJH", "/NJS", "/NP"], capture_output=True, text=True)
    if r.returncode >= 8:                        # 0 a 7 son éxitos de robocopy
        raise RuntimeError(f"robocopy {origen} -> {destino}: {r.stdout[-400:]} {r.stderr[-400:]}")


def entorno_del_nodo(trabajo: Path, puerto: int) -> dict:
    """El entorno del nodo: el del equipo sin ninguna variable de licencia ni de entorno que pudiera torcer la clasificación, y con lo propio de la prueba (carpetas temporales, %ProgramData% redirigido)."""
    propio = {
        "AVACOM_LMS_DB": str(trabajo / "expediente.sqlite3"), "AVACOM_LMS_DIR_LOGS": str(trabajo / "logs"), "ProgramData": str(trabajo / "ProgramData"),
        "AVACOM_OPS_BACKEND_HOST": "127.0.0.1", "AVACOM_OPS_BACKEND_PORT": str(puerto), "AVACOM_LMS_EXIGIR_SESION": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
    }
    pisadas = {k.upper() for k in propio}        # en Windows los nombres no distinguen mayúsculas: no puede haber dos «ProgramData»
    env = {k: v for k, v in os.environ.items() if k.upper() not in pisadas and not k.upper().startswith(("AVACOM_LICENCIA_", "AVACOM_LMS_ENTORNO", "AVACOM_EMISOR_"))}
    env.update(propio)
    return env


def migrar(instalacion: Path, env: dict) -> None:
    py = instalacion / "Runtime" / "Python" / "python.exe"
    r = subprocess.run([str(py), "manage.py", "migrate", "--noinput"], cwd=instalacion / "Backend", env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    anotar("el backend empaquetado migra su base", r.returncode == 0, (r.stdout + r.stderr)[-200:].replace("\n", " ") if r.returncode else "")


def arrancar(instalacion: Path, env: dict, log: Path) -> subprocess.Popen:
    """Arranca el nodo como lo hace el servicio: el lanzador del Runtime con la entrada estándar abierta (al cerrarla, el nodo se detiene limpio)."""
    py = instalacion / "Runtime" / "Python" / "python.exe"
    nodo = subprocess.Popen([str(py), str(instalacion / "Runtime" / "avacom_ops_backend.py")], cwd=instalacion / "Backend", env=env, stdin=subprocess.PIPE,
                            stdout=open(log, "ab"), stderr=subprocess.STDOUT)
    for _ in range(120):
        try:
            urllib.request.urlopen(f"{ra.NODO}/health/", timeout=2)
            return nodo
        except Exception:
            if nodo.poll() is not None:
                raise RuntimeError(f"El nodo empaquetado se cerró al arrancar (código {nodo.returncode}); mira {log}")
            time.sleep(1)
    nodo.kill()
    raise RuntimeError("El nodo empaquetado no arrancó")


def parar(nodo: subprocess.Popen, puerto: int) -> None:
    try:
        nodo.stdin.write(b"detener\n")
        nodo.stdin.flush()
        nodo.stdin.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        nodo.wait(timeout=40)
    except subprocess.TimeoutExpired:
        nodo.kill()
        nodo.wait()
    for _ in range(60):
        if not ra.puerto_ocupado(puerto):
            return
        time.sleep(0.5)


def emisor(carpeta: Path, args: list[str]) -> subprocess.CompletedProcess:
    py = carpeta / "python" / "python.exe"
    env = {**os.environ, "AVACOM_EMISOR_FRASE": FRASE, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    return subprocess.run([str(py), str(carpeta / "iniciar.py"), *args], cwd=carpeta, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")


def activar(token: str, avlic: Path):
    return ra.api("POST", "/api/licencia/activar/", {"archivo_b64": base64.b64encode(avlic.read_bytes()).decode()}, token)


def entrar(documento: str, clave: str, pin: str | None = None) -> str:
    cuerpo = {"identificador": documento, "secreto": clave, "dispositivo": ""}
    if pin:
        cuerpo["pin_maestro"] = pin
    return ra.api("POST", "/api/acceso/sesiones/", cuerpo)[1]["token"]


def aceptar(staging: Path, emisor_dist: Path, puerto: int) -> int:
    trabajo = Path(tempfile.mkdtemp(prefix="aceptacion-paquete-"))
    instalacion = trabajo / "Instalacion"
    nodo = None
    try:
        copiar(staging / "Runtime", instalacion / "Runtime")
        copiar(staging / "Backend", instalacion / "Backend")
        copiar(emisor_dist, trabajo / "Emisor")
        marcador = (instalacion / "Backend" / ".avacom-canal").read_text(encoding="utf-8", errors="replace").strip().replace("\n", " ") if (instalacion / "Backend" / ".avacom-canal").exists() else ""
        anotar("la copia del paquete lleva el marcador de canal de producción", "canal=produccion" in marcador, marcador)
        anotar("la copia NO lleva la llave de desarrollo ni las pruebas de la licencia",
               not (instalacion / "Backend" / "licenciamiento" / "claves" / "desarrollo.json").exists() and not (instalacion / "Backend" / "licenciamiento" / "tests").exists())
        env = entorno_del_nodo(trabajo, puerto)
        migrar(instalacion, env)
        nodo = arrancar(instalacion, env, trabajo / "nodo.log")

        # ------------------------------------------------------------------------------------------------ fase A · como se entrega
        lector = rl.sembrar()
        admin = entrar(rl.ADMIN_DOC, rl.ADMIN_CLAVE, rl.PIN)
        e = rl.estado_api(lector)
        anotar("producción: modo «firmada» y entorno «produccion»", e.get("modo") == "firmada" and e.get("entorno") == "produccion", f"modo={e.get('modo')} entorno={e.get('entorno')}")
        dias = (e.get("vigencia") or {}).get("dias_restantes", 0)
        anotar("sin licencia: evaluación de unos 30 días", e.get("estado") == "sin_licencia" and 28 <= dias <= 30, f"{e.get('estado')} · {e.get('motivo')} · {dias} días")
        codigo, sol = ra.api("POST", "/api/licencia/solicitud/", {}, admin)
        anotar("el nodo empaquetado escribe su solicitud con la huella de ESTE equipo", codigo in (200, 201) and bool(sol.get("archivo_b64")),
               f"{codigo} nivel={sol.get('nivel')} k={sol.get('k')} factores={sol.get('factores')}")
        avreq = trabajo / "solicitud.avreq"
        avreq.write_bytes(base64.b64decode(sol["archivo_b64"]))

        dev = rl.firmar(avreq, trabajo / "desarrollo.avlic", serie=1)
        c, r = activar(admin, dev)
        anotar("una licencia firmada con la llave de DESARROLLO se rechaza", c == 400 and r.get("motivo") == "kid_desconocido", f"{c} {r.get('motivo') or r}")
        anotar("el estado no cambia tras el rechazo", rl.estado_api(lector).get("estado") == "sin_licencia")

        llaves = trabajo / "llaves"
        r = emisor(trabajo / "Emisor", ["claves", "generar", "--kid", "acepta-1", "--salida", str(llaves)])
        anotar("el emisor empaquetado genera el par de llaves", r.returncode == 0 and (llaves / "acepta-1.avkey").exists(), (r.stdout + r.stderr)[-160:].replace("\n", " ") if r.returncode else "")
        salida = trabajo / "salida"
        r = emisor(trabajo / "Emisor", ["emitir", "--solicitud", str(avreq), "--privada", str(llaves / "acepta-1.avkey"), "--aula", "Colegio Aceptacion", "--plan", "anual-aula",
                                          "--hasta", "2027-10-31", "--salida", str(salida), "--registro", str(trabajo / "registro.jsonl"), "--yo-confirmo"])
        avlics = sorted(salida.glob("*.avlic")) if salida.exists() else []
        anotar("el emisor empaquetado emite la licencia", r.returncode == 0 and len(avlics) == 1, (r.stdout + r.stderr)[-200:].replace("\n", " ") if r.returncode else avlics[0].name)
        if not avlics:
            return 1
        c, r = activar(admin, avlics[0])
        anotar("una licencia de una llave que el nodo todavía no conoce se rechaza", c == 400 and r.get("motivo") == "kid_desconocido", f"{c} {r.get('motivo') or r}")

        # ------------------------------------------------------------------------------------------------ fase B · después de la ceremonia
        parar(nodo, puerto)
        nodo = None
        publica = llaves / "acepta-1.produccion.json"
        anotar("la ceremonia deja el archivo de llaves públicas en el formato del nodo", publica.exists(), publica.name)
        shutil.copyfile(publica, instalacion / "Backend" / "licenciamiento" / "claves" / "produccion.json")
        nodo = arrancar(instalacion, env, trabajo / "nodo2.log")
        admin = entrar(rl.ADMIN_DOC, rl.ADMIN_CLAVE, rl.PIN)
        lector = entrar(rl.LECTOR_DOC, rl.LECTOR_CLAVE)
        c, r = activar(admin, dev)
        anotar("con la pública de producción cargada, la de DESARROLLO sigue rechazada", c == 400 and r.get("motivo") == "kid_desconocido", f"{c} {r.get('motivo') or r}")
        c, r = activar(admin, avlics[0])
        anotar("la licencia del emisor empaquetado se activa en el nodo empaquetado", c == 200 and r.get("estado") == "activa", f"{c} {r.get('estado') or r}")
        e = rl.estado_api(lector)
        lic = e.get("licencia") or {}
        limites = e.get("limites") or {}
        anotar("el nodo queda «activa» con el aula, la serie y los límites del plan", e.get("estado") == "activa" and lic.get("aula") == "Colegio Aceptacion" and lic.get("serie") == 1
               and all(isinstance(limites.get(k), int) and limites[k] >= 1 for k in ("equipos", "usuarios", "concurrentes_normal", "concurrentes_pico")),
               f"{e.get('estado')} aula={lic.get('aula')} serie={lic.get('serie')} limites={limites}")
        habilitadas = sorted((e.get("capacidades") or {}).get("habilitadas", []))
        anotar("los cuatro módulos licenciables quedan habilitados", habilitadas == ["administracion_avanzada", "busqueda", "importacion", "reportes"], str(habilitadas))

        parar(nodo, puerto)
        nodo = arrancar(instalacion, env, trabajo / "nodo3.log")
        e = rl.estado_api(entrar(rl.LECTOR_DOC, rl.LECTOR_CLAVE))
        anotar("tras reiniciar el proceso del nodo, la licencia sigue «activa»", e.get("estado") == "activa", f"{e.get('estado')} {e.get('motivo')}")
        estado_dir = trabajo / "ProgramData" / "AVACOM" / "OPS Master" / "Config" / "licencia"
        archivos = sorted(p.name for p in estado_dir.glob("*")) if estado_dir.exists() else []
        anotar("la carpeta de estado quedó en el %ProgramData% redirigido", "actual.avlic" in archivos, str(archivos))
        real = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "AVACOM" / "OPS Master" / "Config" / "licencia"
        anotar("el %ProgramData% REAL no se tocó", not real.exists() or not any(p.name == "actual.avlic" and p.stat().st_mtime > time.time() - 600 for p in real.glob("*")), str(real))
    finally:
        if nodo is not None:
            parar(nodo, puerto)
        shutil.rmtree(trabajo, ignore_errors=True)
    fallos = [x for x in ra.resultados if not x[1]]
    print(f"\n{len(ra.resultados) - len(fallos)} de {len(ra.resultados)} comprobaciones cumplidas")
    for paso, _, detalle in fallos:
        print(f"  FALLÓ: {paso} {detalle}")
    return 1 if fallos else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--puerto", type=int, default=8016)
    p.add_argument("--staging", type=Path, default=RAIZ / "dist" / "staging", help="la carpeta que deja Build-Installer.ps1")
    p.add_argument("--emisor", type=Path, help="la carpeta del emisor portátil (por omisión, la más reciente de tools/licencias/dist)")
    args = p.parse_args()
    ra.NODO = f"http://127.0.0.1:{args.puerto}"
    emisor_dist = args.emisor
    if emisor_dist is None:
        candidatas = sorted((d for d in (RAIZ / "tools" / "licencias" / "dist").glob("AVACOM-Emisor-Licencias-*") if d.is_dir()), key=lambda d: d.stat().st_mtime)
        emisor_dist = candidatas[-1] if candidatas else None
    if not (args.staging / "Backend" / "manage.py").exists() or not (args.staging / "Runtime" / "Python" / "python.exe").exists():
        print(f"No hay un instalador preparado en {args.staging}: compílalo primero (installer/build/Build-Installer.ps1).")
        return 2
    if emisor_dist is None or not (emisor_dist / "python" / "python.exe").exists():
        print("No hay un emisor portátil compilado: ejecuta tools/licencias/Build-Emisor.ps1 primero.")
        return 2
    if ra.puerto_ocupado(args.puerto):
        print(f"El puerto {args.puerto} ya está en uso: usa --puerto con otro libre.")
        return 2
    return aceptar(args.staging, emisor_dist, args.puerto)


if __name__ == "__main__":
    sys.exit(main())

r"""
MOD-018 · verificación EN VIVO de la licencia, por HTTP real contra un nodo AISLADO (sin ventanas): las rutas del backend con la licencia en cada estado, y el cupo.

  rutas   Recorre TODAS las rutas del backend (el inventario sale del resolvedor de Django en el momento: una ruta nueva entra sola) con la licencia en cuatro estados (evaluación, activa,
          en gracia, degradada) y comprueba:
            · una ruta licenciable con su módulo apagado responde EXACTAMENTE 402 `no_disponible_por_licencia` con su capacidad; con el módulo encendido no responde ese 402;
            · una ruta intocable o de núcleo no responde NUNCA ese 402 (R-01) y responde lo mismo en los cuatro estados que con la licencia activa;
            · ninguna ruta responde 5xx por la licencia. Se imprimen los 5xx que haya, para que un humano los clasifique (un 503 de biblioteca apagada o un 501 reservado no son defectos).
  cupo    Con una licencia de 2 equipos y 6 usuarios: la tercera tableta recibe 402 `cupo_agotado`, las registradas y el equipo maestro siguen dando latido, una tableta sin registrar entra a la
          clase y el visitante entra siempre (R-01, RN-33); el séptimo usuario recibe 402 `cupo_agotado` y lo que ya existe sigue funcionando.

Uso (desde la raíz del repositorio; sólo en un árbol de desarrollo: las licencias se firman con las llaves de desarrollo de las pruebas):
    backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\licencia_en_vivo.py rutas|cupo|todo [--puerto 8014]
Sale con 0 si todo se cumplió; con 1 y la lista de desvíos si no. Tarda unos 5 minutos (rutas) y medio minuto (cupo). No toca el nodo del aula (:8000).
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
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True                   # que el guion no deje __pycache__ en tests/ (git no lo ignora ahí)
AQUI = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("recorrido_licencia", AQUI / "recorrido_licencia.py")
rl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rl)                      # define el nodo aislado, la siembra y la firma de licencias de prueba; no corre nada
ra = rl.ra
anotar = ra.anotar

# El inventario se arma en OTRO proceso (con Django levantado sobre una base y unos logs temporales) y vuelve como JSON.
INVENTARIO = r'''
import json, os, re, sys, tempfile
raiz = tempfile.mkdtemp(prefix="inventario-rutas-")
os.environ["AVACOM_LMS_DIR_LOGS"] = os.path.join(raiz, "logs")
os.environ["AVACOM_LMS_DB"] = os.path.join(raiz, "inventario.sqlite3")
os.environ["DJANGO_SETTINGS_MODULE"] = "avacom_lms.settings"
sys.path.insert(0, sys.argv[1])
import django
django.setup()
from django.urls import get_resolver
from licenciamiento.dominio import rutas as clasificador

METODOS = ("get", "post", "put", "patch", "delete")

def ejemplo(patron):
    s = re.sub(r"\(\?P<[^>]+>([a-z_]+(?:\|[a-z_]+)+)\)", lambda m: m.group(1).split("|")[0], patron)
    s = re.sub(r"\(\?P<ruta>[^)]*\)", "a/b", s)
    s = re.sub(r"\(\?P<[^>]+>[^)]*\)", "X", s)
    s = re.sub(r"<path:[^>]+>", "a/b", s)
    s = re.sub(r"<int:[^>]+>", "1", s)
    s = re.sub(r"<[^>]+>", "X", s)
    s = s.replace("^", "").replace("$", "")
    return "/" + s.lstrip("/")

def recorrer(patrones, prefijo=""):
    for p in patrones:
        if hasattr(p, "url_patterns"):
            yield from recorrer(p.url_patterns, prefijo + str(p.pattern))
        else:
            yield prefijo + str(p.pattern), p

filas = []
for plantilla, p in recorrer(get_resolver().url_patterns):
    ruta = ejemplo(plantilla)
    vista = getattr(p.callback, "view_class", None) or getattr(p.callback, "cls", None)
    metodos = ["GET"] if vista is None else ([m.upper() for m in METODOS if hasattr(vista, m)] or ["GET"])
    for m in metodos:
        if clasificador.es_intocable(ruta):
            clase, cap = "A_intocable", ""
        else:
            cap = clasificador.capacidad_de(m, ruta) or ""
            clase = "C_licenciable" if cap else "B_nucleo"
        filas.append({"metodo": m, "ruta": ruta, "clase": clase, "capacidad": cap})
print(json.dumps(filas))
'''


def inventario() -> list[dict]:
    r = subprocess.run([ra.python_backend(), "-c", INVENTARIO, str(rl.BACKEND)], capture_output=True, text=True, encoding="utf-8", cwd=rl.BACKEND, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if r.returncode != 0:
        raise RuntimeError("No se pudo armar el inventario de rutas:\n" + r.stderr[-1500:])
    return json.loads(r.stdout.strip().splitlines()[-1])


# ------------------------------------------------------------------------------------------------------------------------ HTTP con reingreso
SESION = {"token": ""}


def entrar_de_nuevo() -> str:
    """Un barrido con rutas que cambian cosas puede cerrar la sesión de la administración: se vuelve a entrar."""
    _, s = ra.api("POST", "/api/acceso/sesiones/", {"identificador": rl.ADMIN_DOC, "secreto": rl.ADMIN_CLAVE, "dispositivo": "", "pin_maestro": rl.PIN})
    SESION["token"] = s["token"]
    return SESION["token"]


def _una_peticion(metodo: str, ruta: str, token: str) -> tuple[int, dict | None]:
    cuerpo = b"{}" if metodo in ("POST", "PUT", "PATCH", "DELETE") else None
    req = urllib.request.Request(f"{ra.NODO}{ruta}", data=cuerpo, method=metodo, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            texto = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(texto) if texto.startswith(("{", "[")) else None)
    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8", "replace")
        return e.code, (json.loads(texto) if texto.startswith(("{", "[")) else None)
    except Exception as e:  # noqa: BLE001
        return -1, {"detail": repr(e)}


def pedir(metodo: str, ruta: str) -> tuple[int, dict | None]:
    codigo, cuerpo = _una_peticion(metodo, ruta, SESION["token"])
    if codigo == 401 and not ruta.startswith("/api/acceso/sesiones"):
        entrar_de_nuevo()
        codigo, cuerpo = _una_peticion(metodo, ruta, SESION["token"])
    return codigo, cuerpo


def barrer(filas: list[dict]) -> dict:
    salida = {}
    for f in filas:
        if f["ruta"].startswith("/api/licencia/") and f["metodo"] != "GET":
            continue                                                   # cambiaría la licencia misma
        salida[(f["metodo"], f["ruta"])] = pedir(f["metodo"], f["ruta"])
    return salida


def es_402_de_licencia(codigo: int, cuerpo) -> bool:
    return codigo == 402 and isinstance(cuerpo, dict) and cuerpo.get("codigo") == "no_disponible_por_licencia"


def soltar_nodo(nodo: subprocess.Popen) -> None:
    """Detiene el nodo y espera a que el sistema suelte el puerto: el nodo siguiente (o la corrida siguiente) lo necesita libre."""
    nodo.kill()
    try:
        nodo.wait(timeout=20)
    except subprocess.TimeoutExpired:
        pass
    puerto = int(ra.NODO.rsplit(":", 1)[1])
    for _ in range(60):
        if not ra.puerto_ocupado(puerto):
            return
        time.sleep(0.5)


def instalar_serie(avreq_dir: Path, nombre: str, serie: int, via: str, token: str, **kw) -> dict:
    _, r = ra.api("POST", "/api/licencia/solicitud/", {}, token)
    avreq = avreq_dir / f"{nombre}.avreq"
    avreq.write_bytes(base64.b64decode(r["archivo_b64"]))
    avlic = rl.firmar(avreq, avreq_dir / f"{nombre}.avlic", serie=serie, **kw)
    _, r2 = ra.api("POST", f"/api/licencia/{via}/", {"archivo_b64": base64.b64encode(avlic.read_bytes()).decode()}, token)
    return r2


# ------------------------------------------------------------------------------------------------------------------------ rutas
def rutas() -> None:
    filas = inventario()
    trabajo = Path(tempfile.mkdtemp(prefix="licencia-rutas-"))
    nodo = rl.levantar_nodo(trabajo / "nodo.sqlite3", trabajo / "estado")
    desvios: list[str] = []
    cinco_xx: dict[str, set] = defaultdict(set)
    try:
        rl.sembrar()
        token = entrar_de_nuevo()
        resultados = {"evaluacion": barrer(filas)}
        token = entrar_de_nuevo()
        for nombre, serie, via, kw in (("activa", 1, "activar", {}), ("en_gracia", 2, "renovar", {"desde_dias": -90, "vence_dias": -5}), ("degradada", 3, "renovar", {"desde_dias": -200, "vence_dias": -60})):
            instalar_serie(trabajo, nombre, serie, via, token, **kw)
            estado = rl.estado_api(token)["estado"]
            anotar(f"el nodo queda «{nombre}»", estado == nombre, estado)
            resultados[nombre] = barrer(filas)
            token = entrar_de_nuevo()
        base = resultados["activa"]
        for estado, barrido in resultados.items():
            apagadas = {"reportes", "busqueda", "importacion", "administracion_avanzada"} if estado == "degradada" else set()
            for f in filas:
                clave = (f["metodo"], f["ruta"])
                if clave not in barrido:
                    continue
                codigo, cuerpo = barrido[clave]
                if codigo >= 500 or codigo == -1:
                    cinco_xx[f"{f['metodo']} {f['ruta']}"].add((estado, codigo))
                if f["clase"] == "C_licenciable":
                    if f["capacidad"] in apagadas:
                        if not es_402_de_licencia(codigo, cuerpo) or cuerpo.get("capacidad") != f["capacidad"]:
                            desvios.append(f"[{estado}] {f['metodo']} {f['ruta']} debía dar 402 de «{f['capacidad']}» y dio {codigo}")
                    elif es_402_de_licencia(codigo, cuerpo):
                        desvios.append(f"[{estado}] {f['metodo']} {f['ruta']} dio 402 de licencia con «{f['capacidad']}» encendida")
                elif es_402_de_licencia(codigo, cuerpo):
                    desvios.append(f"[{estado}] {f['metodo']} {f['ruta']} ({f['clase']}) dio 402 de licencia: una ruta que nunca se apaga")
                elif codigo != base[clave][0] and not (estado == "evaluacion" and f["ruta"].startswith("/api/licencia/")):
                    desvios.append(f"[{estado}] {f['metodo']} {f['ruta']} ({f['clase']}) responde {codigo} y con la licencia activa respondía {base[clave][0]}")
        total = sum(len(b) for b in resultados.values())
        anotar(f"{len(filas)} rutas · {total} peticiones en 4 estados: ningún desvío de la clasificación", not desvios, f"{len(desvios)} desvíos")
        for d in desvios[:60]:
            print("  DESVÍO:", d)
        if cinco_xx:
            print(f"  (5xx en {len(cinco_xx)} rutas, iguales en todos los estados: para clasificarlos a mano)")
        for ruta, estados in sorted(cinco_xx.items()):
            print("  5xx:", ruta, sorted(estados)[:2])
    finally:
        soltar_nodo(nodo)
        shutil.rmtree(trabajo, ignore_errors=True)


# ------------------------------------------------------------------------------------------------------------------------ cupo
def cupo() -> None:
    trabajo = Path(tempfile.mkdtemp(prefix="licencia-cupo-"))
    nodo = rl.levantar_nodo(trabajo / "nodo.sqlite3", trabajo / "estado")
    try:
        rl.sembrar()
        admin = entrar_de_nuevo()
        r = instalar_serie(trabajo, "cupo", 1, "activar", admin, limites=rl.Limites(equipos=2, usuarios=6, concurrentes_normal=50, concurrentes_pico=100))
        anotar("se activa una licencia de 2 equipos y 6 usuarios", r.get("estado") == "activa", str(r.get("estado")))

        def latido(hw: str, tipo: str = "TABLETA"):
            return ra.api("POST", "/api/dispositivos/latido/", {"identificador_hw": hw, "nombre": hw, "plataforma": "android", "version_app": "uia", "tipo": tipo})

        c1, _ = latido("tab-1")
        c2, _ = latido("tab-2")
        anotar("las dos primeras tabletas se registran", c1 in (200, 201) and c2 in (200, 201), f"{c1}, {c2}")
        c3, b3 = latido("tab-3")
        anotar("la tercera recibe 402 cupo_agotado de equipos", c3 == 402 and b3.get("codigo") == "cupo_agotado" and b3.get("tipo") == "equipos", f"{c3} {b3.get('codigo')} {b3.get('tipo')}")
        anotar("el 402 trae el límite y lo que se usa", b3.get("limite") == 2 and b3.get("en_uso") == 2)
        c1b, _ = latido("tab-1")
        c2b, _ = latido("tab-2")
        anotar("las ya registradas siguen dando latido con el cupo lleno", c1b in (200, 201) and c2b in (200, 201), f"{c1b}, {c2b}")
        cm, _ = latido("ops-master-uia", "MASTER")
        anotar("el equipo maestro da latido con el cupo lleno (no cuenta)", cm in (200, 201), str(cm))
        c3b, _ = latido("tab-3")
        anotar("la tercera sigue sin poder registrarse", c3b == 402, str(c3b))
        _, sesion = ra.api("POST", "/api/aula/sesiones/", {"via": "libre", "profesor_id": "prof-1"}, admin)
        cu, _ = ra.api("POST", "/api/aula/sesiones/unirse/", {"codigo_union": sesion.get("codigo_union"), "persona_id": "ana", "persona_rotulo": "ana", "dispositivo": "tab-3"}, admin)
        anotar("R-01 · la tableta sin registrar entra a la clase por el aula", cu in (200, 201), str(cu))
        cv, _ = ra.api("POST", "/api/acceso/sesiones/visitante/", {"dispositivo": "tab-1"})
        anotar("RN-33 · el visitante entra con el cupo de equipos lleno", cv == 200, str(cv))

        creados = []
        for n in range(1, 5):
            c, b = ra.api("POST", "/api/acceso/usuarios/", {"rol": "TEACHER", "alias": f"P{n}", "persona": {"nombres": f"Profe{n}", "apellidos": "Uno"},
                                                           "identificadores": [{"tipo": "DNI", "valor": f"9000000{n}", "es_login": True}], "secreto": "Profe.Cupo.2026!", "secreto_definitivo": True}, admin)
            creados.append((c, b.get("codigo") if isinstance(b, dict) else None, b.get("tipo") if isinstance(b, dict) else None))
        anotar("caben dos usuarios más (4 + 2 = 6)", creados[0][0] == 201 and creados[1][0] == 201, str(creados[:2]))
        anotar("el séptimo usuario recibe 402 cupo_agotado de usuarios", creados[2] == (402, "cupo_agotado", "usuarios"), str(creados[2]))
        anotar("lo que ya existe sigue funcionando con el cupo de usuarios lleno", ra.api("GET", "/api/acceso/yo/", None, admin)[0] == 200)
        # El aviso sale de la instantánea que el programador recalcula cada AVACOM_LICENCIA_INTERVALO_S (5 s aquí, 5 min en producción): se espera al ciclo siguiente en lugar de exigirlo al instante.
        inicio, avisos = time.time(), []
        while time.time() - inicio < 25:
            avisos = [a["codigo"] for a in rl.estado_api(admin).get("avisos", [])]
            if "cupo" in avisos:
                break
            time.sleep(1)
        anotar("el estado avisa del cupo (≥ 90 %) en el ciclo siguiente", "cupo" in avisos, f"{time.time() - inicio:.0f} s · {avisos}")
    finally:
        soltar_nodo(nodo)
        shutil.rmtree(trabajo, ignore_errors=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("que", choices=("rutas", "cupo", "todo"))
    p.add_argument("--puerto", type=int, default=8014)
    args = p.parse_args()
    ra.NODO = f"http://127.0.0.1:{args.puerto}"
    if ra.puerto_ocupado(args.puerto):
        print(f"El puerto {args.puerto} ya está en uso: usa --puerto con otro libre.")
        return 2
    if args.que in ("rutas", "todo"):
        rutas()
    if args.que in ("cupo", "todo"):
        cupo()
    fallos = [r for r in ra.resultados if not r[1]]
    print(f"\n{len(ra.resultados) - len(fallos)} de {len(ra.resultados)} comprobaciones cumplidas")
    for paso, _, detalle in fallos:
        print(f"  FALLÓ: {paso} {detalle}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())

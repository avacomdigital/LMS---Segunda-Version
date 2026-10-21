"""
Concurrencia, restauración y proceso muerto sobre una base SQLite de ARCHIVO (la de las pruebas de Django va en memoria y no sirve para hilos ni procesos):

    cd backend
    .venv\\Scripts\\python -m nodo.tools.prueba_concurrencia <carpeta_temporal> [--hilos 20] [--por-hilo 100] [--procesos 4] [--por-proceso 100]

Hace, en una base nueva migrada en esa carpeta:
  1. HILOS: N hilos publican a la vez (cada evento en su propia transacción): la secuencia resultante es 1..N×k sin huecos ni repetidos y en orden de commit.
  2. PROCESOS: M procesos hijos publican a la vez contra la misma base: mismo resultado.
  3. RESTAURACIÓN (P-12): se copia la base, se publican más eventos, se devuelve la copia vieja y se arranca el nodo: el contador salta y ninguna secuencia nueva coincide con una emitida.
  4. PROCESO MUERTO (CAP-098 en lo que toca a la cola): un hijo publica lotes de 10 eventos por transacción (misma correlación por lote) y se lo mata a mitad; al reabrir,
     `PRAGMA quick_check` es «ok» y cada correlación tiene 0 o 10 eventos: ninguna transacción a medias.

Imprime UN JSON con las cifras. Lo corre `tests/test_concurrencia.py` en un subproceso y lo lee. Pensado para esta máquina: no mide hardware de aula.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


def _preparar(carpeta: Path, nombre: str) -> dict:
    """El entorno de un nodo aislado: base propia, anclas propias, logs propios. Jamás ProgramData ni la base del desarrollador."""
    base = carpeta / f"{nombre}.sqlite3"
    entorno = dict(os.environ)
    entorno.update({"AVACOM_LMS_DB": str(base), "AVACOM_NODO_DIR": str(carpeta / f"anclas-{nombre}"), "AVACOM_LMS_DIR_LOGS": str(carpeta / "logs"), "AVACOM_LMS_ENTORNO": "desarrollo",
                    "AVACOM_LMS_DEBUG": "1", "AVACOM_NODO_ESTRICTO": "1", "AVACOM_NODO_ANCLA_CADA_EVENTOS": "50", "PYTHONIOENCODING": "utf-8", "AVACOM_AULA_PROGRAMADOR": "0",
                    "AVACOM_EVAL_PROGRAMADOR": "0", "AVACOM_SEARCH_PROGRAMADOR": "0", "AVACOM_REPORTES_PROGRAMADOR": "0", "AVACOM_LICENCIA_PROGRAMADOR": "0",
                    "AVACOM_LMS_AUDITORIA_VERIFICAR_CADA_S": "0"})
    return entorno


def _django(entorno: dict) -> None:
    os.environ.update(entorno)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "avacom_lms.settings")
    import django
    django.setup()


def _migrar(entorno: dict) -> None:
    r = subprocess.run([sys.executable, "manage.py", "migrate", "--noinput", "-v", "0"], env=entorno, cwd=str(Path(__file__).resolve().parents[2]), capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("migrate falló: " + r.stderr[-2000:])


def _publicar(n: int, etiqueta: str, correlacion: str | None = None, por_transaccion: int = 1, pausa_s: float = 0.0) -> list[int]:
    from django.db import close_old_connections, transaction

    from nodo import servicios
    secuencias: list[int] = []
    i = 0
    while i < n:
        with transaction.atomic():
            corr = f"{correlacion or etiqueta}-{i // por_transaccion}"
            for _ in range(por_transaccion):
                if i >= n:
                    break
                s = servicios.publicar("evaluacion", "Intento", f"{etiqueta}-{i}", "evaluacion.intento_abierto.v1", {"intento_id": f"{etiqueta}-{i}"}, correlacion_id=corr)
                secuencias.append(s["secuencia"])
                i += 1
            if pausa_s:
                time.sleep(pausa_s)
    close_old_connections()
    return secuencias


def hijo_publicar(entorno: dict, n: int, etiqueta: str, por_transaccion: int = 1, pausa_s: float = 0.0) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-m", "nodo.tools.prueba_concurrencia", "--hijo", str(n), etiqueta, str(por_transaccion), str(pausa_s)], env=entorno,
                            cwd=str(Path(__file__).resolve().parents[2]), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _contar(base: Path) -> dict:
    import sqlite3
    c = sqlite3.connect(str(base))
    try:
        secuencias = [r[0] for r in c.execute("SELECT secuencia FROM m15_evento ORDER BY secuencia")]
        quick = [r[0] for r in c.execute("PRAGMA quick_check")]
        por_corr = [r[0] for r in c.execute("SELECT COUNT(*) FROM m15_evento GROUP BY correlacion_id")]
        contador = c.execute("SELECT seq FROM sqlite_sequence WHERE name='m15_evento'").fetchone()
        return {"secuencias": secuencias, "quick_check": quick, "por_correlacion": por_corr, "contador": int(contador[0]) if contador else 0}
    finally:
        c.close()


def principal(carpeta: Path, hilos: int, por_hilo: int, procesos: int, por_proceso: int) -> dict:
    carpeta.mkdir(parents=True, exist_ok=True)
    entorno = _preparar(carpeta, "cola")
    base = Path(entorno["AVACOM_LMS_DB"])
    _migrar(entorno)
    _django(entorno)
    from django.db import close_old_connections

    salida: dict = {}
    # 1 · hilos
    resultados: dict[int, list[int]] = {}
    errores: list[str] = []

    def trabajo(k: int) -> None:
        try:
            resultados[k] = _publicar(por_hilo, f"h{k}")
        except Exception as error:   # noqa: BLE001
            errores.append(f"{type(error).__name__}: {error}")
        finally:
            close_old_connections()

    t0 = time.perf_counter()
    lista = [threading.Thread(target=trabajo, args=(k,)) for k in range(hilos)]
    for t in lista:
        t.start()
    for t in lista:
        t.join()
    duracion = time.perf_counter() - t0
    todas = sorted(s for r in resultados.values() for s in r)
    salida["hilos"] = {"hilos": hilos, "por_hilo": por_hilo, "errores": errores, "total": len(todas), "sin_huecos": todas == list(range(1, len(todas) + 1)),
                       "repetidas": len(todas) - len(set(todas)), "segundos": round(duracion, 2), "por_segundo": round(len(todas) / duracion, 1) if duracion else None}
    base_hilos = len(todas)
    # 2 · procesos
    t0 = time.perf_counter()
    hijos = [hijo_publicar(entorno, por_proceso, f"p{k}") for k in range(procesos)]
    fallos = []
    for h in hijos:
        out, err = h.communicate(timeout=600)
        if h.returncode != 0:
            fallos.append(err[-500:])
    duracion = time.perf_counter() - t0
    estado = _contar(base)
    esperado = base_hilos + procesos * por_proceso
    salida["procesos"] = {"procesos": procesos, "por_proceso": por_proceso, "fallos": fallos, "total": len(estado["secuencias"]) - base_hilos,
                          "sin_huecos": estado["secuencias"] == list(range(1, esperado + 1)), "segundos": round(duracion, 2)}
    # 3 · restauración
    copia = carpeta / "copia-vieja.sqlite3"
    close_old_connections()
    _checkpoint()
    shutil.copyfile(base, copia)
    max_copia = _contar(copia)["secuencias"][-1]
    _publicar(120, "despues")                     # ≥ ANCLA_CADA_EVENTOS (50) para que el ancla se refresque por encima de la copia
    from nodo import servicios
    from nodo.infraestructura import contenedor
    servicios.parar()                             # ancla al día
    max_emitido = _contar(base)["secuencias"][-1]
    close_old_connections()
    from django.db import connections
    connections.close_all()
    _checkpoint()
    for sufijo in ("-wal", "-shm"):
        try:
            os.remove(str(base) + sufijo)
        except FileNotFoundError:
            pass
    shutil.copyfile(copia, base)                  # «alguien restauró la copia vieja»
    contenedor.reiniciar()
    arranque = servicios.arrancar()
    nuevas = _publicar(5, "tras-restaurar")
    salida["restauracion"] = {"max_copia": max_copia, "max_emitido_antes": max_emitido, "restauracion_detectada": bool(arranque and arranque["restauracion"]),
                              "contador_tras_arranque": arranque["contador"] if arranque else None, "primera_nueva": nuevas[0], "ninguna_repetida": nuevas[0] > max_emitido}
    # 4 · proceso muerto a mitad de transacción: el hijo publica lotes de 10 (una transacción por lote, con una pausa dentro de ella) y se lo mata cuando ya lleva varios
    connections.close_all()
    hijo = hijo_publicar(entorno, 100_000, "muerto", por_transaccion=10, pausa_s=0.02)
    limite = time.monotonic() + 60
    while time.monotonic() < limite and _eventos_del_hijo(base) < 50:
        time.sleep(0.05)
    hijo.kill()
    hijo.wait(timeout=30)
    estado = _contar(base)
    lotes = _lotes_del_hijo(base)
    salida["proceso_muerto"] = {"quick_check": estado["quick_check"], "lotes": len(lotes), "lotes_a_medias": sum(1 for n in lotes if n != 10), "eventos_del_hijo": sum(lotes),
                                "lotes_completos": all(n == 10 for n in lotes)}
    return salida


def _eventos_del_hijo(base: Path) -> int:
    import sqlite3
    c = sqlite3.connect(str(base))
    try:
        return int(c.execute("SELECT COUNT(*) FROM m15_evento WHERE agregado_id LIKE 'muerto-%'").fetchone()[0])
    except sqlite3.OperationalError:
        return 0
    finally:
        c.close()


def _lotes_del_hijo(base: Path) -> list[int]:
    import sqlite3
    c = sqlite3.connect(str(base))
    try:
        return [int(r[0]) for r in c.execute("SELECT COUNT(*) FROM m15_evento WHERE agregado_id LIKE 'muerto-%' GROUP BY correlacion_id")]
    finally:
        c.close()


def _checkpoint() -> None:
    from django.db import connection
    with connection.cursor() as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    connection.close()


def _hijo(n: int, etiqueta: str, por_transaccion: int, pausa_s: float) -> None:
    _django(dict(os.environ))
    secuencias = _publicar(n, etiqueta, por_transaccion=por_transaccion, pausa_s=pausa_s)
    print(json.dumps({"n": len(secuencias)}))


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--hijo":
        _hijo(int(args[1]), args[2], int(args[3]), float(args[4]))
        sys.exit(0)
    carpeta = Path(args[0])
    opciones = {"--hilos": 20, "--por-hilo": 100, "--procesos": 4, "--por-proceso": 100}
    for i, a in enumerate(args):
        if a in opciones:
            opciones[a] = int(args[i + 1])
    print(json.dumps(principal(carpeta, opciones["--hilos"], opciones["--por-hilo"], opciones["--procesos"], opciones["--por-proceso"]), ensure_ascii=False, indent=2))

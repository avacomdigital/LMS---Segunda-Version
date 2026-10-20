r"""
MOD-018 · Q-L13 (decisión del CTO) · recorrido de interfaz de la FECHA ADELANTADA en AVACOM OPS contra un nodo AISLADO: ante un salto accidental de la fecha hacia el futuro el nodo ya no lo
guarda ni degrada a las 72 horas: lanza un error hasta que la fecha concuerde con la actual.

Para mover la fecha sin tocar la del equipo de quien trabaja en él, el nodo de prueba arranca con un `sitecustomize.py` (sólo de este guion: vive en una carpeta temporal) que le suma a
`time.time()` un desfase leído de un archivo, y SÓLO a quien llama desde el módulo de licencia: las sesiones, la bitácora y el resto del nodo siguen con la hora de verdad. Así «alguien
adelantó la fecha 40 días» pasa de verdad dentro del proceso del nodo, que es lo único que Q-L13 trata como salto (el reloj monótono no se mueve), y OPS lo ve como lo vería el colegio.

Recorre, en cuatro fases cortas (cada una con una OPS recién abierta): (1) licencia activa sin error · fecha adelantada 40 días: el nodo la detecta en su siguiente ciclo, no la acepta, no
degrada ni apaga ningún módulo y avisa con las dos fechas · la pantalla Licencia y el menú principal lo dicen como un error, con «Confirmar la fecha de hoy»; (2) la hoja de confirmación
habla de la fecha del equipo; (3) al corregir la fecha el error se quita solo; (4) de nuevo adelantada, la administración confirma que es la correcta: el aviso se quita y sólo entonces el
aula guarda esa fecha · y volver atrás después es otro aviso.

Por qué en fases: OPS (WinUI) se cae a veces —0xc0000005 dentro de Microsoft.UI.Xaml.dll— o vuelve al acceso cuando la UI Automation la maneja, SIN que esta pantalla tenga nada que ver
(se reproduce yendo y viniendo de Licencia con la fecha en orden). Si pasa a mitad de una fase, se ve en el código de salida o en la pantalla de acceso, la fase se repite con otra OPS y
sus anotaciones se descartan (queda dicho en la salida); una falla con OPS viva sigue siendo una falla. La fase 4 cambia lo que el nodo guardó, así que corre sobre un nodo propio.

Uso (desde la raíz del repositorio, con OPS compilado para Windows):
    backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\recorrido_fecha.py --ops <Avacom.Lms.Ops.exe> --salida <carpeta> [--puerto 8017]
Sale con 0 si todo se cumplió; con 1 y la lista de lo que falló si no (≈ 6 minutos, con las ventanas de OPS en primer plano). No toca el nodo del aula (:8000) ni la OPS de quien trabaja en
el equipo (perfil de pruebas propio). Sólo corre en un árbol de desarrollo (usa las llaves de desarrollo de las pruebas).
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True                   # que el guion no deje __pycache__ en tests/ (git no lo ignora ahí)
AQUI = Path(__file__).resolve().parent

spec = importlib.util.spec_from_file_location("recorrido_licencia", AQUI / "recorrido_licencia.py")
rl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rl)                      # define el nodo aislado, la siembra y la firma de licencias de prueba; no corre nada
ra = rl.ra
anotar = ra.anotar

DIA_S = 86_400
DESFASE = 40 * DIA_S
ACCESO = "Escribe tu documento y tu contraseña"
REPETIDAS: list[str] = []                        # las fases que hubo que repetir porque OPS se cayó, para decirlo al final

SITECUSTOMIZE = r'''
import os, sys, time as _t
_ARCHIVO = os.environ.get("AVACOM_UIA_DESFASE_ARCHIVO", "")
if _ARCHIVO:
    _original = _t.time
    _ultimo = [0.0, 0.0]                         # (cuándo se leyó el archivo, desfase en segundos)

    def _hora():
        ahora = _original()
        if ahora - _ultimo[0] > 0.2:
            try:
                with open(_ARCHIVO, "r", encoding="ascii") as f:
                    _ultimo[1] = float(f.read().strip() or 0)
            except Exception:
                pass
            _ultimo[0] = ahora
        # sólo el módulo de licencia ve el salto: las sesiones, la bitácora y el resto del nodo siguen con la hora de verdad. El reloj de la licencia es el de la evaluación
        # (INV-017: `licenciamiento.RelojDelNodo` llama a `evaluacion.RelojNodo`), así que se mira quién llama hasta tres marcos más arriba.
        f = sys._getframe(1)
        for _ in range(3):
            if f is None:
                break
            if "licenciamiento" in f.f_code.co_filename:
                return ahora + _ultimo[1]
            f = f.f_back
        return ahora

    _t.time = _hora
'''


def levantar_nodo(db: Path, estado: Path, carpeta_reloj: Path, archivo_desfase: Path) -> subprocess.Popen:
    """Como `recorrido_licencia.levantar_nodo`, pero con el `sitecustomize` que mueve el reloj del módulo de licencia."""
    carpeta_reloj.mkdir(parents=True, exist_ok=True)
    (carpeta_reloj / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
    archivo_desfase.write_text("0", encoding="ascii")
    env = {**os.environ, "AVACOM_LMS_DB": str(db), "AVACOM_LMS_EXIGIR_SESION": "1", "PYTHONIOENCODING": "utf-8", "AVACOM_LICENCIA_MODO": "firmada", "AVACOM_LICENCIA_DIR": str(estado),
           "AVACOM_LICENCIA_INTERVALO_S": "5", "AVACOM_LMS_DIR_LOGS": str(estado / "logs"), "AVACOM_UIA_DESFASE_ARCHIVO": str(archivo_desfase),
           "PYTHONPATH": str(carpeta_reloj) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    py = ra.python_backend()
    subprocess.run([py, "manage.py", "migrate", "--noinput"], cwd=rl.BACKEND, env=env, check=True, capture_output=True)
    nodo = subprocess.Popen([py, "manage.py", "runserver", ra.NODO.removeprefix("http://"), "--noreload"], cwd=rl.BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import urllib.request
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{ra.NODO}/health/", timeout=2)
            return nodo
        except Exception:
            time.sleep(1)
    nodo.kill()
    raise RuntimeError(f"El nodo de prueba no arrancó en {ra.NODO}")


def esperar_boton(ops, nombre: str, milisegundos: int = 25000) -> bool:
    """Espera a que haya un botón con ese nombre (el menú sin avisos no tiene ningún texto que diga «Licencia»: sólo el botón)."""
    fin = time.time() + milisegundos / 1000
    while time.time() < fin:
        if nombre in rl.botones(ops):
            return True
        time.sleep(1)
    return False


def entrar(ops) -> bool:
    """Como `rl.entrar`, pero si la clave no llega al campo enmascarado (pasa si se escribe antes de que la pantalla esté lista y el acceso dice «no coinciden») vuelve a escribir los
    dos campos: sólo se sigue al PIN maestro cuando la pantalla del PIN aparece de verdad."""
    for _ in range(3):
        ops.escribir("Documento", rl.ADMIN_DOC)
        ops.escribir("Contraseña", rl.ADMIN_CLAVE)
        ops.invocar("Entrar")
        if ops.esperar("PIN maestro de la escuela", 12000):
            return ops.pin(rl.PIN)
    return False


def mover_fecha(archivo: Path, segundos: int) -> None:
    archivo.write_text(str(int(segundos)), encoding="ascii")
    time.sleep(0.5)


def esperar_estado(token: str, condicion, segundos: int = 40) -> dict:
    """Pregunta por el estado del nodo (con la cuenta lectora) hasta que `condicion(estado)` se cumpla o se acabe el plazo; devuelve el último estado."""
    fin = time.time() + segundos
    e: dict = {}
    while time.time() < fin:
        e = rl.estado_api(token)
        if isinstance(e, dict) and condicion(e):
            return e
        time.sleep(1.5)
    return e


def con_error(e: dict) -> bool:
    return "reloj_adelantado" in (e.get("banderas") or [])


def sin_error(e: dict) -> bool:
    return not con_error(e)


def activar_por_la_api(trabajo: Path) -> None:
    """La licencia de prueba se instala por la API (lo que se prueba aquí es la fecha, no la activación en tres pasos, que ya recorre `recorrido_licencia.py`)."""
    _, s = ra.api("POST", "/api/acceso/sesiones/", {"identificador": rl.ADMIN_DOC, "secreto": rl.ADMIN_CLAVE, "dispositivo": "", "pin_maestro": rl.PIN})
    admin = s["token"]
    _, r = ra.api("POST", "/api/licencia/solicitud/", {}, admin)
    avreq = trabajo / "solicitud.avreq"
    avreq.write_bytes(base64.b64decode(r["archivo_b64"]))
    avlic = rl.firmar(avreq, trabajo / "licencia.avlic", serie=1)
    codigo, r2 = ra.api("POST", "/api/licencia/activar/", {"archivo_b64": base64.b64encode(avlic.read_bytes()).decode()}, admin)
    anotar("la licencia de prueba queda activa", codigo == 200 and r2.get("estado") == "activa", f"{codigo} {r2.get('estado')}")
    ra.api("DELETE", "/api/acceso/sesiones/actual/", None, admin)        # la sesión del personal es única: se suelta para que OPS entre con la suya


# ------------------------------------------------------------------------------------------------------------------------ un nodo con el reloj movible

class Nodo:
    """Un nodo aislado (base y carpeta de estado temporales), con la organización sembrada, la licencia de prueba activa y el reloj de la licencia movible."""

    def __init__(self) -> None:
        self.trabajo = Path(tempfile.mkdtemp(prefix="ops-uia-fecha-"))
        self.desfase = self.trabajo / "desfase.txt"
        self.proceso: subprocess.Popen | None = None
        try:
            self.proceso = levantar_nodo(self.trabajo / "nodo.sqlite3", self.trabajo / "estado", self.trabajo / "reloj", self.desfase)
            print(f"Nodo aislado en {ra.NODO}, con el reloj de la licencia movible (archivo {self.desfase})", flush=True)
            self.token = rl.sembrar()
            activar_por_la_api(self.trabajo)
        except BaseException:
            self.cerrar()
            raise

    def cerrar(self) -> None:
        if self.proceso is not None:
            self.proceso.kill()
            try:
                self.proceso.wait(timeout=20)
            except subprocess.TimeoutExpired:
                pass
            self.proceso = None
        shutil.rmtree(self.trabajo, ignore_errors=True)
        puerto = int(ra.NODO.rsplit(":", 1)[1])
        for _ in range(30):                                          # el puerto tarda un instante en soltarse
            if not ra.puerto_ocupado(puerto):
                break
            time.sleep(1)


# ------------------------------------------------------------------------------------------------------------------------ las fases

class OpsCaida(Exception):
    """OPS se cerró o volvió al acceso a mitad de una fase: es ruido del arnés (WinUI con la UI Automation), no un resultado del producto; la fase se repite."""


def verificar(ops) -> None:
    """Lanza `OpsCaida` si OPS ya no está donde la fase la dejó: el proceso terminó (con su código de salida) o la pantalla volvió al acceso."""
    codigo = ops.proceso.poll()
    if codigo is not None:
        raise OpsCaida(f"OPS terminó con el código {codigo & 0xFFFFFFFF:#x}")
    if rl.hay(ops, ACCESO):
        raise OpsCaida("OPS volvió a la pantalla de acceso")


def comprobar(ops, paso: str, ok: bool, detalle: str = "") -> bool:
    """`anotar`, pero antes de dar por fallida una comprobación de pantalla mira que OPS siga ahí: si no, la fase se repite en lugar de culpar al producto."""
    if not ok:
        verificar(ops)
    return anotar(paso, ok, detalle)


def acceso(ops) -> None:
    """Entra con la administración y espera el menú principal. Lanza `OpsCaida` si no lo logra."""
    if not ops.esperar(ACCESO, 30000):
        raise OpsCaida("OPS no mostró la pantalla de acceso")
    if not entrar(ops) or not esperar_boton(ops, "Licencia"):
        raise OpsCaida("OPS no llegó al menú principal")


def en_fase(nombre: str, exe: Path, salida: Path, nodo: Nodo | None, preparar, cuerpo, intentos: int = 4) -> None:
    """
    Una fase con una OPS recién abierta. `preparar(nodo)` deja el nodo como la fase lo necesita (la fecha) y `cuerpo(ops, nodo)` hace las comprobaciones. Con `nodo=None` cada intento levanta
    un nodo propio (la fase cambia lo que el nodo guardó y no se puede repetir sobre el mismo). Si OPS se cae a mitad de la fase se repite con otra y se descartan sus anotaciones.
    """
    for intento in range(1, intentos + 1):
        marca = len(ra.resultados)
        propio = Nodo() if nodo is None else None
        actual = propio or nodo
        ops = None
        try:
            if preparar is not None:
                preparar(actual)
            ops = ra.Ops(exe, salida, f"uia-lic-fecha-{int(time.time() * 1000)}")
            acceso(ops)
            cuerpo(ops, actual)
            verificar(ops)                                          # si se cayó justo al final, tampoco vale
            return
        except OpsCaida as caida:
            del ra.resultados[marca:]
            REPETIDAS.append(f"{nombre} (intento {intento}: {caida})")
            print(f"  (fase «{nombre}», intento {intento} de {intentos}: {caida}; se repite con otra OPS)", flush=True)
        finally:
            if ops is not None:
                ops.cerrar()
            if propio is not None:
                propio.cerrar()
    anotar(f"la fase «{nombre}» corre completa", False, f"OPS se cayó {intentos} veces seguidas")


def preparar_en_orden(nodo: Nodo) -> None:
    """Fase 1: la fecha en orden y sin error (si una vuelta anterior dejó un episodio abierto, se cierra al concordar la fecha)."""
    mover_fecha(nodo.desfase, 0)
    esperar_estado(nodo.token, sin_error)


def preparar_adelantada(nodo: Nodo) -> None:
    """Fases 2 y 3: la fecha ya adelantada 40 días y el error puesto."""
    mover_fecha(nodo.desfase, DESFASE)
    esperar_estado(nodo.token, con_error)


def fase_adelanta(ops, nodo: Nodo) -> None:
    token, desfase = nodo.token, nodo.desfase
    comprobar(ops, "con la fecha en orden el menú no dice nada de la fecha", not rl.hay(ops, "adelantada"))
    ops.captura("30-menu-sin-error")

    # alguien adelanta la fecha 40 días
    mover_fecha(desfase, DESFASE)
    e = esperar_estado(token, con_error)
    aviso = (e.get("avisos") or [{}])[0]
    ahora_real = time.time() * 1000
    anotar("el nodo detecta la fecha adelantada en su siguiente ciclo", con_error(e), str(e.get("banderas")))
    anotar("la hora del aula no se movió: sigue siendo la de verdad, no la del salto", abs(e.get("ahora", 0) - ahora_real) < 10 * 60_000,
           f"el aula lleva {(e.get('ahora', 0) - ahora_real) / DIA_S / 1000:+.2f} días respecto de la hora real")
    anotar("no degrada ni apaga ningún módulo: sigue «activa» y con los cuatro módulos", e.get("estado") == "activa" and len(e.get("capacidades", {}).get("habilitadas", [])) == 4,
           f"{e.get('estado')} {e.get('capacidades', {}).get('habilitadas')}")
    anotar("el aviso trae los 40 días y las dos fechas, y va primero", aviso.get("codigo") == "reloj_adelantado" and aviso.get("adelanto_dias") == 40
           and abs(aviso.get("fecha_equipo", 0) - aviso.get("fecha_esperada", 0) - DESFASE * 1000) < 10 * 60_000, str(aviso))
    codigo, _ = ra.api("GET", "/api/reportes/estado/", None, token)
    anotar("con la fecha adelantada ningún módulo está en pausa (Reportes no responde 402)", codigo != 402, str(codigo))

    comprobar(ops, "la pantalla Licencia abre", rl.ir_a_licencia(ops))
    comprobar(ops, "la pantalla dice, con las dos fechas, que la fecha está adelantada y que el aula no la aceptó",
              ops.esperar("está adelantada", 20000) and rl.hay(ops, "el aula esperaba el") and rl.hay(ops, "No se aceptó"))
    comprobar(ops, "la píldora dice «Fecha adelantada» y la pantalla sigue en «Licencia activa»", rl.hay(ops, "Fecha adelantada") and rl.hay(ops, "Licencia activa"))
    comprobar(ops, "ofrece «Confirmar la fecha de hoy»", any("Confirmar la fecha de hoy" in b for b in rl.botones(ops)))          # es un botón (con su descripción como nombre), no un texto
    ops.captura("31-licencia-fecha-adelantada")
    comprobar(ops, "vuelve al menú principal", ops.invocar("Menú principal"))
    comprobar(ops, "el menú principal lo dice como un error, con «Ver la licencia»", ops.esperar("está adelantada", 20000) and "Ver la licencia" in rl.botones(ops))
    ops.captura("32-menu-fecha-adelantada")


def fase_hoja(ops, nodo: Nodo) -> None:
    comprobar(ops, "al abrir OPS con la fecha adelantada, el menú principal ya la dice como un error", ops.esperar("está adelantada", 25000) and "Ver la licencia" in rl.botones(ops))
    comprobar(ops, "la hoja de confirmación abre", rl.ir_a_licencia(ops) and rl.toque(ops, "licencia-fecha") and ops.esperar("FECHA DEL EQUIPO", 10000))
    comprobar(ops, "la hoja habla de la fecha del equipo y de corregirla en Windows", rl.hay(ops, "Si hoy es") and rl.hay(ops, "corrígela en la configuración de Windows"))
    ops.captura("33-confirmar-la-fecha")
    rl.toque(ops, "licencia-hoja-cerrar")


def fase_se_corrige(ops, nodo: Nodo) -> None:
    mover_fecha(nodo.desfase, 0)
    e = esperar_estado(nodo.token, sin_error)
    anotar("al corregir la fecha el nodo quita el error solo", sin_error(e) and e.get("estado") == "activa", str(e.get("banderas")))
    anotar("y no queda nada detrás: ni marca adelantada ni aviso de reloj atrasado", "reloj_sospechoso" not in (e.get("banderas") or []) and abs(e.get("ahora", 0) - time.time() * 1000) < 10 * 60_000)
    comprobar(ops, "la pantalla Licencia abre", rl.ir_a_licencia(ops) and ops.esperar("Licencia activa", 15000))
    comprobar(ops, "la pantalla ya no muestra el error ni ofrece confirmar", not rl.hay(ops, "está adelantada") and not any("Confirmar la fecha de hoy" in b for b in rl.botones(ops)))
    ops.captura("34-licencia-fecha-corregida")
    comprobar(ops, "vuelve al menú principal", ops.invocar("Menú principal"))
    comprobar(ops, "el menú principal tampoco", esperar_boton(ops, "Licencia", 15000) and not rl.hay(ops, "adelantada"))


def fase_confirma(ops, nodo: Nodo) -> None:
    token, desfase = nodo.token, nodo.desfase
    mover_fecha(desfase, DESFASE)
    esperar_estado(token, con_error)
    comprobar(ops, "de nuevo adelantada: el error vuelve", rl.ir_a_licencia(ops) and ops.esperar("está adelantada", 20000))
    comprobar(ops, "la administración abre «Confirmar la fecha de hoy»", rl.toque(ops, "licencia-fecha") and ops.esperar("FECHA DEL EQUIPO", 10000))
    comprobar(ops, "y confirma que la fecha del equipo es la correcta", rl.toque(ops, "licencia-fecha-confirmar") and ops.esperar("Fecha confirmada", 20000))
    ops.captura("35-fecha-confirmada")
    rl.toque(ops, "licencia-listo")
    e = esperar_estado(token, sin_error, 20)
    anotar("el aviso se quita y sólo entonces el aula guarda esa fecha", sin_error(e) and abs(e.get("ahora", 0) - (time.time() * 1000 + DESFASE * 1000)) < 10 * 60_000,
           f"el aula lleva {(e.get('ahora', 0) - time.time() * 1000) / DIA_S / 1000:+.2f} días respecto de la hora real")
    comprobar(ops, "la pantalla ya no muestra el error", ops.esperar("Licencia activa", 15000) and not rl.hay(ops, "está adelantada"))

    # volver atrás después de confirmar es otro aviso
    mover_fecha(desfase, 0)
    e = esperar_estado(token, lambda x: "reloj_sospechoso" in (x.get("banderas") or []))
    anotar("confirmada una fecha, devolver el reloj es un reloj atrasado (otro aviso, no el de la fecha adelantada)", "reloj_sospechoso" in (e.get("banderas") or []) and sin_error(e), str(e.get("banderas")))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ops", required=True)
    p.add_argument("--salida", required=True)
    p.add_argument("--puerto", type=int, default=8017)
    args = p.parse_args()
    ra.NODO = f"http://127.0.0.1:{args.puerto}"
    if ra.puerto_ocupado(args.puerto):
        print(f"El puerto {args.puerto} ya está en uso: usa --puerto con otro libre.")
        return 2
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    exe = Path(args.ops)
    ra.tomar_candado()
    nodo: Nodo | None = None
    try:
        nodo = Nodo()
        en_fase("la fecha se adelanta", exe, salida, nodo, preparar_en_orden, fase_adelanta)
        en_fase("la hoja de confirmación", exe, salida, nodo, preparar_adelantada, fase_hoja)
        en_fase("la fecha se corrige", exe, salida, nodo, preparar_adelantada, fase_se_corrige)
        nodo.cerrar()
        nodo = None
        en_fase("la administración confirma", exe, salida, None, None, fase_confirma)           # cambia lo que el nodo guardó: cada intento, un nodo nuevo
    finally:
        ra.soltar_candado()
        if nodo is not None:
            nodo.cerrar()
    fallos = [r for r in ra.resultados if not r[1]]
    print(f"\n{len(ra.resultados) - len(fallos)} de {len(ra.resultados)} comprobaciones cumplidas. Capturas en {salida}")
    if REPETIDAS:
        print(f"Fases repetidas porque OPS se cayó o volvió al acceso ({len(REPETIDAS)}; ruido del arnés, no una falla de la pantalla):")
        for r in REPETIDAS:
            print(f"  · {r}")
    for paso, _, detalle in fallos:
        print(f"  FALLÓ: {paso} {detalle}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())

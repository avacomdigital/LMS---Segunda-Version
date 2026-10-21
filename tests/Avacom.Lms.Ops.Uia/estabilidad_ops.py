r"""
Estabilidad de AVACOM OPS bajo UI Automation (Bugfix 03, 2026-10-21): tres comprobaciones contra un nodo AISLADO (puerto propio, base temporal, sesión obligatoria) y OPS con perfil de pruebas,
sin ratón ni teclado y con el candado de pantalla. Nacieron de dos fallas de OPS que se veían sólo cuando la UI Automation la manejaba, ir y volver de «Licencia»:

  · «OPS vuelve al acceso con el proceso vivo y sin ningún 401»: era un fallo de OPS, no del arnés. «Menú principal» activado DOS veces seguidas (un doble toque en la pantalla táctil, o el
    reintento de `Invoke()` tras una excepción de UI Automation) hacía `GoToAsync("..")` dos veces: la primera deja el menú a la vista y la segunda lo saca a él y lleva al acceso.
  · APPCRASH `Avacom.Lms.Ops.exe`, 0xc0000005 en `Microsoft.UI.Xaml.dll` 3.1.7.0 +0x940f4d: un fallo de Windows App SDK 1.7 (XAML) con la UI Automation activa. Es un NULL que se lee (0x110)
    en una devolución de llamada que XAML se encola a sí mismo justo después de descargar el menú (651 elementos, 92 lienzos Win2D) al abrir otra pantalla. No hay fuga que lo explique.

Subcomandos (desde la raíz del repositorio, con OPS compilado para Windows; ≈ minutos cada uno):

  doble   [--repeticiones 3]      LA REGRESIÓN del primer fallo: desde Licencia, dos «Menú principal» seguidos y dos toques seguidos en «Licencia» del menú. Debe quedar siempre en el menú
                                  (y con una sola pantalla de Licencia). Con una OPS anterior al arreglo falla en la primera repetición con «OPS volvió al acceso».
  vueltas [--vueltas 60]          Ir y volver de «Licencia» con el patrón endurecido del arnés (un toque UNA vez, lecturas baratas, se mira la pantalla antes de repetir) y, por vuelta, memoria
                                  privada, manejadores, objetos GDI/USER e hilos de OPS. Falla si OPS se cae, vuelve al acceso o un contador (GDI, USER, manejadores) no se queda quieto.
  estres  [--vueltas 600 --lectores 2 --asentar 0]
                                  La carga que tumbó a OPS: UN cliente que invoca ir y volver de «Licencia» sin pausas y N lectores que recorren el árbol sin parar. Sale con 1 si OPS se cae
                                  (con el código, el módulo y el desplazamiento que dice el Visor de eventos), con 0 si aguantó y con 3 si alguien cerró la ventana (código de salida 0:
                                  no es una caída). Es la prueba más pesada: la ventana de OPS se ve lenta mientras corre; mejor con el equipo libre. Una caída por cada 200–600 vueltas es lo normal con la carga
                                  máxima: el resultado de un solo intento no prueba nada; sirve para comparar `--asentar` o `--lectores` con muchas vueltas.

    backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\estabilidad_ops.py doble --ops C:\temp\ops-uia\Avacom.Lms.Ops.exe --salida C:\temp\ops-uia\estab [--puerto 8018]

No toca el nodo del aula (:8000) ni la OPS de quien trabaja en el equipo (perfil de pruebas propio). Sólo corre en un árbol de desarrollo (usa las llaves de desarrollo de las pruebas).
"""
from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from ctypes import wintypes as wt
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True                   # que el guion no deje __pycache__ en tests/ (git no lo ignora ahí)
AQUI = Path(__file__).resolve().parent

spec = importlib.util.spec_from_file_location("recorrido_fecha", AQUI / "recorrido_fecha.py")
rf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rf)                      # define el nodo aislado, el acceso y OpsCaida; no corre nada
rl, ra = rf.rl, rf.ra
anotar = ra.anotar


# ------------------------------------------------------------------------------------------------------------------------ contadores del proceso de OPS
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_u32 = ctypes.WinDLL("user32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi", use_last_error=True)


class _Memoria(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t), ("PrivateUsage", ctypes.c_size_t)]


class _Hilo(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD), ("th32OwnerProcessID", wt.DWORD), ("tpBasePri", wt.LONG), ("tpDeltaPri", wt.LONG), ("dwFlags", wt.DWORD)]


_k32.OpenProcess.restype = wt.HANDLE
_k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
_k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
_k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
_k32.Thread32First.argtypes = [wt.HANDLE, ctypes.POINTER(_Hilo)]
_k32.Thread32Next.argtypes = [wt.HANDLE, ctypes.POINTER(_Hilo)]
_k32.CloseHandle.argtypes = [wt.HANDLE]
_k32.GetProcessHandleCount.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
_u32.GetGuiResources.restype = wt.DWORD
_u32.GetGuiResources.argtypes = [wt.HANDLE, wt.DWORD]
_psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(_Memoria), wt.DWORD]


def _hilos(pid: int) -> int:
    instantanea = _k32.CreateToolhelp32Snapshot(0x4, 0)
    n = 0
    try:
        e = _Hilo()
        e.dwSize = ctypes.sizeof(e)
        ok = _k32.Thread32First(instantanea, ctypes.byref(e))
        while ok:
            n += e.th32OwnerProcessID == pid
            ok = _k32.Thread32Next(instantanea, ctypes.byref(e))
    finally:
        _k32.CloseHandle(instantanea)
    return n


def contadores(pid: int) -> dict:
    """Memoria privada (MB), manejadores, objetos GDI y USER e hilos del proceso; {} si ya no existe."""
    h = _k32.OpenProcess(0x1000 | 0x0400 | 0x0010, False, pid)
    if not h:
        return {}
    try:
        m = _Memoria()
        m.cb = ctypes.sizeof(m)
        _psapi.GetProcessMemoryInfo(h, ctypes.byref(m), m.cb)
        n = wt.DWORD()
        _k32.GetProcessHandleCount(h, ctypes.byref(n))
        return {"priv_mb": round(m.PrivateUsage / 1048576, 1), "handles": n.value, "gdi": _u32.GetGuiResources(h, 0), "user": _u32.GetGuiResources(h, 1), "hilos": _hilos(pid)}
    finally:
        _k32.CloseHandle(h)


def elementos_uia(ops) -> int | None:
    """Cuántos elementos tiene hoy el árbol de UI Automation de OPS (`ui-ops.ps1 contar`); None si no se pudo leer."""
    codigo, salida = ops.ui("contar")
    m = re.search(r"ELEMENTOS (\d+)", salida)
    return int(m.group(1)) if codigo == 0 and m else None


# ------------------------------------------------------------------------------------------------------------------------ qué dijo Windows de una caída
def informe_de_caida(pid: int, desde: float) -> list[str]:
    """Lo que dejó una caída de OPS: el código de salida lo da quien llama; aquí, el «Application Error» del Visor de eventos (se filtra por ProviderName: con Level=2 y -First se pierde entre los
    eventos de otros programas) y las líneas de `fallos-ops.log` de ese pid."""
    lineas: list[str] = []
    inicio = datetime.fromtimestamp(desde - 5).strftime("%Y-%m-%dT%H:%M:%S")
    guion = (f"$ErrorActionPreference='SilentlyContinue'; Get-WinEvent -FilterHashtable @{{LogName='Application'; ProviderName='Application Error'; StartTime=[datetime]'{inicio}'}} | "
             "Where-Object { $_.Message -match 'Avacom.Lms.Ops' } | Select-Object -First 3 | ForEach-Object { $_.TimeCreated.ToString('HH:mm:ss') + ' ' + ($_.Message -replace '\\s+', ' ') }")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", guion], capture_output=True, text=True, encoding="utf-8", errors="replace")
    for l in (r.stdout or "").splitlines():
        if l.strip():
            lineas.append("Visor de eventos · " + l.strip()[:420])
    log = Path(os.environ.get("LOCALAPPDATA", "")) / "AVACOM" / "lms" / "fallos-ops.log"
    if log.exists():
        texto = log.read_text(encoding="utf-8", errors="replace")
        for bloque in re.split(r"\n\s*\n(?=\[)", texto)[-40:]:
            if f"pid={pid}" in bloque:
                lineas.append("fallos-ops.log · " + " ".join(bloque.split())[:300])
    return lineas


# ------------------------------------------------------------------------------------------------------------------------ nodo, OPS y candado
class Sesion:
    """Un nodo aislado con la licencia de prueba activa y una OPS con perfil de pruebas, ya en el menú principal."""

    def __init__(self, args) -> None:
        ra.NODO = f"http://127.0.0.1:{args.puerto}"
        if ra.puerto_ocupado(args.puerto):
            raise SystemExit(f"El puerto {args.puerto} ya está en uso: usa --puerto con otro libre.")
        self.salida = Path(args.salida)
        self.salida.mkdir(parents=True, exist_ok=True)
        self.inicio = time.time()
        ra.tomar_candado()
        self.nodo = None
        self.ops = None
        try:
            self.nodo = rf.Nodo()
            self.ops = ra.Ops(Path(args.ops), self.salida, f"uia-estab-{int(time.time() * 1000)}")
            rf.acceso(self.ops)
        except BaseException:
            self.cerrar()
            raise

    @property
    def vivo(self) -> bool:
        return self.ops.proceso.poll() is None

    def codigo_de_salida(self) -> str:
        c = self.ops.proceso.poll()
        return "sigue vivo" if c is None else f"{c & 0xFFFFFFFF:#x}"

    def cerrar(self) -> None:
        try:
            if self.ops is not None:
                self.ops.cerrar()
        finally:
            if self.nodo is not None:
                self.nodo.cerrar()
            ra.soltar_candado()


_CERRADA_A_MANO = [False]


def caida(sesion: Sesion, que: str) -> None:
    """
    Anota que OPS ya no está, con todo lo que se sabe de por qué. Código de salida 0 NO es una caída: es un cierre normal (quien usa el equipo cerró la ventana de prueba, que toma la pantalla
    mientras dura y con `estres` se ve lenta); la prueba queda interrumpida, no fallada por OPS (y sale con 3).
    """
    codigo = sesion.codigo_de_salida()
    if codigo == "0x0":
        _CERRADA_A_MANO[0] = True
        anotar(que, False, "OPS se cerró sin error (código 0x0): alguien cerró la ventana; la prueba quedó interrumpida, no es una caída")
        return
    anotar(que, False, f"OPS terminó con el código {codigo}")
    for l in informe_de_caida(sesion.ops.pid, sesion.inicio):
        print("     " + l, flush=True)


# ------------------------------------------------------------------------------------------------------------------------ doble: la regresión del «Menú principal» repetido
def cmd_doble(args) -> int:
    s = Sesion(args)
    try:
        for i in range(1, args.repeticiones + 1):
            if not anotar(f"{i}: la pantalla Licencia abre", rl.ir_a_licencia(s.ops)):
                break
            codigo, salida = s.ops.ui("doble", nombre="licencia-volver")
            time.sleep(2.5)
            if not s.vivo:
                caida(s, f"{i}: dos «Menú principal» seguidos no tumban a OPS")
                break
            sitio = rl.donde_estoy(s.ops)
            if not anotar(f"{i}: dos «Menú principal» seguidos dejan a OPS en el menú principal, no en el acceso", sitio == "menu", f"quedó en «{sitio}» ({salida})"):
                break
            # el doble toque en «Licencia» del menú: una sola pantalla de Licencia, y un solo «Menú principal» basta para volver
            s.ops.ui("doble", nombre="dashboard-licencia")
            ok = s.ops.esperar("Licencia de este equipo", 15000)
            time.sleep(1.5)
            anotar(f"{i}: dos toques seguidos en «Licencia» abren la pantalla", ok and rl.donde_estoy(s.ops) == "licencia")
            rl.toque(s.ops, "licencia-volver")
            time.sleep(2.0)
            sitio = rl.donde_estoy(s.ops)
            if not anotar(f"{i}: un solo «Menú principal» vuelve al menú aunque se hayan pedido dos Licencias", sitio == "menu", f"quedó en «{sitio}»"):
                break
    finally:
        s.cerrar()
    return _resumen()


# ------------------------------------------------------------------------------------------------------------------------ vueltas: el patrón endurecido, con contadores
def cmd_vueltas(args) -> int:
    s = Sesion(args)
    pid = s.ops.pid
    historia: list[dict] = []
    try:
        base = contadores(pid)
        print(f"OPS pid {pid} en el menú; {args.vueltas} vueltas. Contadores iniciales: {base}", flush=True)
        for v in range(1, args.vueltas + 1):
            t = time.time()
            ok = rl.ir_a_licencia(s.ops)
            uia_licencia = elementos_uia(s.ops) if ok else None
            ok = ok and rl.volver_al_menu(s.ops)
            uia_menu = elementos_uia(s.ops) if ok else None
            c = contadores(pid)
            historia.append({"vuelta": v, "s": round(time.time() - t, 1), **c, "uia_licencia": uia_licencia, "uia_menu": uia_menu})
            print(f"vuelta {v:3d}: {time.time() - t:5.1f} s  {c}  elementos UIA: licencia {uia_licencia}, menú {uia_menu}", flush=True)
            if not s.vivo:
                caida(s, f"vuelta {v}: OPS sigue viva")
                break
            if not ok:
                sitio = rl.donde_estoy(s.ops)
                anotar(f"vuelta {v}: ir y volver de Licencia", False, f"OPS quedó en «{sitio}»")
                break
        else:
            anotar(f"{args.vueltas} vueltas sin caída ni retorno al acceso", True)
        # Los objetos de ventana y los manejadores se quedan quietos; la memoria privada puede subir (se informa la pendiente, no se exige).
        if len(historia) >= 10:
            mitad = historia[len(historia) // 2:]
            for clave, tope in (("gdi", 20), ("user", 20), ("handles", 400)):
                subio = max(h[clave] for h in mitad) - historia[0][clave]
                anotar(f"«{clave}» no crece sin parar (+{subio} desde la primera vuelta)", subio <= tope)
            for clave in ("uia_licencia", "uia_menu"):
                valores = [h[clave] for h in historia if h[clave] is not None]
                if valores:
                    anotar(f"los elementos del árbol de UI Automation de «{clave[4:]}» no crecen ({min(valores)} a {max(valores)})", max(valores) - min(valores) <= 6)
            pend = (historia[-1]["priv_mb"] - historia[min(4, len(historia) - 1)]["priv_mb"]) / max(1, len(historia) - 5)
            print(f"memoria privada: {historia[0]['priv_mb']} → {historia[-1]['priv_mb']} MB ({pend:+.2f} MB por vuelta)", flush=True)
    finally:
        (s.salida / "vueltas.jsonl").write_text("\n".join(json.dumps(h) for h in historia), encoding="utf-8")
        s.cerrar()
    return _resumen()


# ------------------------------------------------------------------------------------------------------------------------ estres: la carga que tumbó a OPS
def cmd_estres(args) -> int:
    s = Sesion(args)
    pid = s.ops.pid
    clientes: list[subprocess.Popen] = []
    base = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(AQUI / "ui-carga.ps1"), "-ProcId", str(pid)]
    try:
        for i in range(args.lectores):
            clientes.append(subprocess.Popen(base + ["-Modo", "leer", "-Segundos", str(args.maximo), "-Registro", str(s.salida / f"lector{i}.jsonl"), "-Quien", f"l{i}"],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        invocador = subprocess.Popen(base + ["-Modo", "vueltas", "-Vueltas", str(args.vueltas), "-Asentar", str(args.asentar), "-Registro", str(s.salida / "invocador.jsonl")]
                                     + (["-Completo"] if args.completo else []), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"OPS pid {pid}: {args.vueltas} vueltas con un cliente que invoca (asentar {args.asentar} ms) y {args.lectores} lectores", flush=True)
        fin = time.time() + args.maximo
        while time.time() < fin and invocador.poll() is None and s.vivo:
            time.sleep(5)
        vueltas = 0
        reg = s.salida / "invocador.jsonl"
        if reg.exists():
            vueltas = sum('"ev":"vuelta"' in l.replace(" ", "") for l in reg.read_text(encoding="utf-8", errors="replace").splitlines())
        if not s.vivo:
            caida(s, f"OPS aguanta la carga (se cayó tras {vueltas} vueltas, a los {time.time() - s.inicio:.0f} s)")
        elif invocador.poll() not in (None, 0):
            sitio = rl.donde_estoy(s.ops)
            anotar("el cliente que invoca terminó bien", False, f"código {invocador.poll()}; OPS en «{sitio}»")
        else:
            anotar(f"OPS aguanta la carga ({vueltas} vueltas)", True)
    finally:
        for c in clientes:
            c.kill()
        s.cerrar()
    return _resumen()


# ------------------------------------------------------------------------------------------------------------------------
def _resumen() -> int:
    fallos = [r for r in ra.resultados if not r[1]]
    print(f"\n{len(ra.resultados) - len(fallos)} de {len(ra.resultados)} comprobaciones cumplidas.")
    for paso, _, detalle in fallos:
        print(f"  FALLÓ: {paso} {detalle}")
    if _CERRADA_A_MANO[0]:
        print("  (prueba interrumpida: alguien cerró OPS; sale con 3 para que no se confunda con una caída)")
        return 3
    return 1 if fallos else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="orden", required=True)
    for nombre in ("doble", "vueltas", "estres"):
        q = sub.add_parser(nombre)
        q.add_argument("--ops", required=True)
        q.add_argument("--salida", required=True)
        q.add_argument("--puerto", type=int, default=8018)
        if nombre == "doble":
            q.add_argument("--repeticiones", type=int, default=3)
        if nombre == "vueltas":
            q.add_argument("--vueltas", type=int, default=60)
        if nombre == "estres":
            q.add_argument("--vueltas", type=int, default=600)
            q.add_argument("--lectores", type=int, default=2)
            q.add_argument("--asentar", type=int, default=0, help="ms de pausa tras cada toque, antes de volver a preguntarle a OPS")
            q.add_argument("--completo", action="store_true", help="el cliente espera recorriendo todo el árbol (como el arnés de antes)")
            q.add_argument("--maximo", type=int, default=1500, help="segundos como máximo")
    args = p.parse_args()
    return {"doble": cmd_doble, "vueltas": cmd_vueltas, "estres": cmd_estres}[args.orden](args)


if __name__ == "__main__":
    sys.exit(main())

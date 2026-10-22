r"""
MOD-017 · recorrido de interfaz de la pantalla ACTUALIZACIONES de AVACOM OPS contra un nodo AISLADO (Fase 3).

Reutiliza el arnés de `tests/Avacom.Lms.Ops.Uia` (UIA sin ratón ni teclado, PrintWindow, regla de tercios). Qué hace:
  · levanta un nodo propio (base y carpeta de actualizaciones temporales, puerto aparte, sesión obligatoria, vigilante cada 3 s) con la organización instalada y administración, soporte
    técnico, un profesor y una cuenta LECTORA que sólo usa el guion, por la API, para mirar el estado (la sesión del personal es única: entrar por la API cerraría la de OPS);
  · mapea una carpeta temporal como unidad (subst) que hace de memoria USB, con un paquete bueno, uno alterado y otro bueno para el técnico, firmados con la llave de DESARROLLO;
  · recorre como la administración: el paquete alterado se rechaza, el bueno se trae, se programa y se desprograma, se aplica con UNA confirmación, el aula responde 503 al iniciar clases mientras
    dura, el «Host» (simulado por el guion: escribe resultado.json) termina y la pantalla lo dice solo, se vuelve a la versión anterior con un motivo de la lista, el historial;
  · el soporte técnico trae un paquete pero no ve Aplicar ni Programar, y el profesor no ve nada.

Aquí el Host se SIMULA (la Fase 4 construye el real): lo que se prueba es la pantalla y el contrato con el nodo, no la aplicación de los archivos.

Uso (desde la raíz del repositorio, con OPS compilado para Windows):
    backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\recorrido_actualizacion.py --ops <Avacom.Lms.Ops.exe> --salida <carpeta> [--puerto 8010]
Sale con 0 si todo se cumplió; con 1 y la lista de lo que falló si no. No toca el nodo del aula (:8000) ni la OPS de quien trabaja en el equipo: perfil de pruebas propio.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

sys.dont_write_bytecode = True                   # que el guion no deje __pycache__ en tests/
AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
BACKEND = RAIZ / "backend"
sys.path.insert(0, str(BACKEND))

spec = importlib.util.spec_from_file_location("recorrido_acceso", AQUI / "recorrido_acceso.py")
ra = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ra)                      # sólo define funciones y constantes: no corre nada

from actualizacion.tests import emisor  # noqa: E402

ADMIN_DOC, ADMIN_CLAVE, PIN = "1042888795", "Rectoria.Uia.2026!", "482915"
TECNICO_DOC, TECNICO_CLAVE = "70111222", "Tecnico.Uia.2026!"
LECTOR_DOC, LECTOR_CLAVE = "70999888", "Lector.Uia.2026!"          # sólo la usa el guion, por la API, para mirar el estado sin cerrar la sesión de OPS
PROFE_DOC, PROFE_CLAVE = "52100200", "Profe.Uia.2026!"

resultados = ra.resultados
anotar = ra.anotar


# ------------------------------------------------------------------------------------------------------------------------ nodo y datos
def levantar_nodo(db: Path, estado: Path, usb: str) -> subprocess.Popen:
    env = {**os.environ, "AVACOM_LMS_DB": str(db), "AVACOM_LMS_EXIGIR_SESION": "1", "PYTHONIOENCODING": "utf-8", "AVACOM_ACTUALIZACION_DIR": str(estado / "Actualizaciones"),
           "AVACOM_ACTUALIZACION_UNIDADES": usb, "AVACOM_ACTUALIZACION_INTERVALO_S": "3", "AVACOM_LMS_DIR_LOGS": str(estado / "logs"), "AVACOM_LICENCIA_DIR": str(estado / "licencia"),
           "AVACOM_NODO_DIR": str(estado / "nodo")}
    py = ra.python_backend()
    subprocess.run([py, "manage.py", "migrate", "--noinput"], cwd=BACKEND, env=env, check=True, capture_output=True)
    nodo = subprocess.Popen([py, "manage.py", "runserver", ra.NODO.removeprefix("http://"), "--noreload"], cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{ra.NODO}/health/", timeout=2)
            return nodo
        except Exception:
            time.sleep(1)
    nodo.kill()
    raise RuntimeError(f"El nodo de prueba no arrancó en {ra.NODO}")


def sembrar() -> str:
    """Instala la organización y crea soporte técnico, un profesor y la cuenta lectora. Devuelve el token de la LECTORA (soporte técnico: update.read), no el de la administración."""
    codigo, _ = ra.api("POST", "/api/acceso/instalacion/", {
        "organizacion": {"codigo": "IE-UIA-ACT", "nombre": "IE Prueba Actualizaciones", "pais": "CO", "idioma": "es", "locale": "es-CO"},
        "administrador": {"alias": "Rectoría", "nombres": "Ana", "apellidos": "Pérez", "dni": ADMIN_DOC, "password": ADMIN_CLAVE}, "pin_maestro": PIN})
    anotar("la organización se instala por la API", codigo == 201, f"código {codigo}")
    codigo, s = ra.api("POST", "/api/acceso/sesiones/", {"identificador": ADMIN_DOC, "secreto": ADMIN_CLAVE, "dispositivo": "", "pin_maestro": PIN})
    token = s["token"]
    for rol, doc, clave, alias, nombres in (("TECHNICIAN", TECNICO_DOC, TECNICO_CLAVE, "Soporte", "Tomás"), ("TEACHER", PROFE_DOC, PROFE_CLAVE, "Prof. Ríos", "Marta"),
                                            ("TECHNICIAN", LECTOR_DOC, LECTOR_CLAVE, "Lector", "Lía")):
        c, _ = ra.api("POST", "/api/acceso/usuarios/", {"rol": rol, "alias": alias, "persona": {"nombres": nombres, "apellidos": "Prueba"},
                                                        "identificadores": [{"tipo": "DNI", "valor": doc, "es_login": True}], "secreto": clave, "secreto_definitivo": True}, token)
        anotar(f"se crea la cuenta {rol}", c == 201, f"código {c}")
    _, s = ra.api("POST", "/api/acceso/sesiones/", {"identificador": LECTOR_DOC, "secreto": LECTOR_CLAVE, "dispositivo": ""})
    return s["token"]


def libre_para_subst() -> str:
    for letra in "XWVUTSRQ":
        if not Path(f"{letra}:\\").exists():
            return letra
    raise RuntimeError("no hay una letra de unidad libre")


# ------------------------------------------------------------------------------------------------------------------------ paquetes y el Host simulado
def version_del_producto() -> tuple[str, str]:
    actual = json.loads((RAIZ / "installer" / "version.json").read_text(encoding="utf-8"))["version"]
    mayor, menor, parche = (int(x) for x in actual.split("."))
    return actual, f"{mayor}.{menor}.{parche + 1}"


def paquete(nombre: str, *, paquete_id: str, serie: int = 7, alterar: bool = False) -> bytes:
    actual, nueva = version_del_producto()
    datos = emisor.emitir(paquete_id=paquete_id, nombre=nombre, version_producto=nueva, version_minima=actual,
                          modulos=(emisor.mf.Modulo(nombre="reporting", version="1.4.0", version_datos=4, version_contrato=1, serie=serie, requiere={"nodo": 1},
                                                    migraciones=(emisor.mf.Migracion("0004_parche_de_ejemplo", "0003_corte_cola_unica"),)),))
    if alterar:
        b = bytearray(datos)
        b[len(b) // 2] ^= 0xFF                   # un solo byte cambiado: la firma o el contenedor lo rechazan
        return bytes(b)
    return datos


def orden_en_curso(carpeta: Path, espera: float = 20.0) -> dict | None:
    fin = time.time() + espera
    while time.time() < fin:
        ruta = carpeta / "orden.json"
        if ruta.exists():
            try:
                return json.loads(ruta.read_text(encoding="utf-8"))
            except ValueError:
                pass
        time.sleep(0.5)
    return None


def host_termina(carpeta: Path, orden: dict, resultado: str, *, accion: str | None = None) -> None:
    """Lo que el Host real dejará en `resultado.json` al terminar (contrato de 02-api.md §3): la orden se consume y queda el resultado."""
    ahora = int(time.time() * 1000)
    cuerpo = {"formato": 1, "orden_id": orden["orden_id"], "paquete_id": orden["paquete_id"], "accion": accion or orden["accion"], "resultado": resultado, "paso": "verificar",
              "iniciado_en": ahora - 95_000, "terminado_en": ahora, "duracion_ms": 95_000, "detalle": "simulado por el guion de UIA", "respaldo": None,
              "migraciones": [{"modulo": "reporting", "nombre": "0004_parche_de_ejemplo", "ok": resultado in ("aplicado", "revertido")}], "error": None}
    (carpeta / "resultado.json").write_text(json.dumps(cuerpo), encoding="utf-8")
    (carpeta / "orden.json").unlink(missing_ok=True)


# ------------------------------------------------------------------------------------------------------------------------ gestos de UIA
def botones(ops) -> list[str]:
    return [l.split("\t")[1] for l in ops.ui("list")[1].splitlines() if l.startswith("Button\t")]


def hay(ops, fragmento: str) -> bool:
    return any(fragmento.lower() in t.lower() for t in ops.textos())


def existe(ops, ident: str) -> bool:
    return ops.ui("existe", nombre=ident)[0] == 0


def toque(ops, ident: str, intentos: int = 8) -> bool:
    """Un toque por AutomationId, UNA vez. Se repite sólo mientras el control todavía no está (no se tocó nada); con salida 4 (Invoke() lanzó) no se repite y se confirma por la pantalla."""
    for _ in range(intentos):
        codigo, salida = ops.ui("tecla", nombre=ident)
        if codigo == 0:
            return True
        if codigo == 4:
            ops.dudosas.append(f"{ident}: {salida}")
            print(f"     (toque dudoso en «{ident}»: no se repite · {salida[:140]})", flush=True)
            return True
        time.sleep(0.8)
    print(f"     (no hay un control con AutomationId «{ident}»)", flush=True)
    return False


def tocar_tarjeta(ops, fragmento: str, intentos: int = 10) -> bool:
    for _ in range(intentos):
        for nombre in botones(ops):
            if fragmento.lower() in nombre.lower():
                return ops.invocar(nombre)
        time.sleep(1)
    print(f"     (no hay tarjeta con «{fragmento}»; hay: {botones(ops)})", flush=True)
    return False


def al_menu(ops) -> bool:
    if not toque(ops, "actualizaciones-volver"):
        return False
    fin = time.time() + 25
    while time.time() < fin:
        if existe(ops, "dashboard-actualizaciones"):
            return True
        time.sleep(0.5)
    return False


def ir_a_actualizaciones(ops) -> bool:
    return toque(ops, "dashboard-actualizaciones") and ops.esperar("Actualizaciones del aula", 15000)


def profe_token() -> str:
    """La sesión del profesor por la API (la de OPS del profesor viene después y la reemplaza: la sesión es única). Con ella se mira lo que ve quien INICIA una clase."""
    return ra.api("POST", "/api/acceso/sesiones/", {"identificador": PROFE_DOC, "secreto": PROFE_CLAVE, "dispositivo": ""})[1]["token"]


def estado_api(token: str) -> dict:
    return ra.api("GET", "/api/actualizacion/estado/", None, token)[1]


# ------------------------------------------------------------------------------------------------------------------------ el recorrido de la administración
def administracion(exe: Path, salida: Path, lector: str, carpeta: Path, usb: Path) -> None:
    ops = ra.Ops(exe, salida, f"uia-act-{int(time.time())}")
    try:
        anotar("el acceso abre con el nodo instalado", ops.esperar("Escribe tu documento y tu contraseña", 30000))
        ra.entrar(ops, ADMIN_DOC, ADMIN_CLAVE, PIN)
        anotar("llega al menú con el botón «Actualizaciones»", ops.esperar("CLASSROOM", 25000) and existe(ops, "dashboard-actualizaciones") and "Actualizaciones" in botones(ops))
        ops.captura("01-menu-actualizaciones")

        anotar("la pantalla Actualizaciones abre", ir_a_actualizaciones(ops))
        anotar("el aula está al día, con su versión, el espacio y los módulos",
               ops.esperar("El aula está al día", 15000) and hay(ops, "MÓDULOS") and hay(ops, "Reportes") and hay(ops, "datos") and hay(ops, "Espacio libre"))
        anotar("los dos paquetes de la memoria se listan (el aula los leyó de la unidad)", existe(ops, "actualizaciones-candidato-0") and existe(ops, "actualizaciones-candidato-1"))
        anotar("sin paquete elegido dice qué hacer", hay(ops, "Elige un paquete"))
        ops.captura("02-actualizaciones-con-memoria")

        # el paquete alterado: se rechaza con su motivo y no se guarda nada
        anotar("toca el paquete alterado", tocar_tarjeta(ops, "alterado.avupd"))
        anotar("el paquete alterado se rechaza con palabras claras", ops.esperar("El archivo no es un paquete válido", 15000) and hay(ops, "No se guardó nada"))
        anotar("el rechazo no deja un paquete elegido", hay(ops, "Elige un paquete") and "Aplicar ahora" not in botones(ops))
        ops.captura("03-paquete-alterado-rechazado")
        anotar("el aula no guardó el paquete rechazado (ni su archivo)", not list((carpeta / "paquetes").glob("*.avupd")) if (carpeta / "paquetes").exists() else True)

        # el bueno
        anotar("toca el paquete bueno", tocar_tarjeta(ops, "reportes-1.4.0.avupd"))
        anotar("el paquete bueno queda verificado", ops.esperar("Paquete verificado", 20000) and hay(ops, "Listo para aplicar"))
        anotar("el administrador ve Aplicar ahora, Programar y el detalle",
               {"Aplicar ahora", "Programar"} <= set(botones(ops)) and hay(ops, "Qué cambia") and hay(ops, "Peso") and hay(ops, "Espacio") and hay(ops, "Firma"))
        ops.captura("04-paquete-verificado")

        # programar
        anotar("Programar abre la hoja", toque(ops, "actualizaciones-programar") and ops.esperar("¿Cuándo se aplica?", 10000))
        anotar("la hoja ofrece atajos y ajustes sin teclado", existe(ops, "actualizaciones-atajo-0") and existe(ops, "actualizaciones-mas-media") and existe(ops, "actualizaciones-duracion-120"))
        toque(ops, "actualizaciones-mas-media")
        toque(ops, "actualizaciones-duracion-120")
        ops.captura("05-programar")
        anotar("confirmar programa la ventana", toque(ops, "actualizaciones-confirmar-programar") and ops.esperar("Actualización programada", 20000))
        e = estado_api(lector)
        anotar("el nodo quedó con la ventana programada", e.get("estado") == "programado" and len(e.get("programados", [])) == 1, str(e.get("estado")))
        anotar("la pantalla ofrece quitar la programación", "Quitar la programación" in botones(ops))
        ops.captura("06-programado")
        anotar("quitar la programación", toque(ops, "actualizaciones-desprogramar") and ops.esperar("Programación cancelada", 15000))
        anotar("el nodo vuelve a estar al día", estado_api(lector).get("estado") == "al_dia")

        # aplicar: UNA confirmación
        anotar("Aplicar ahora abre la confirmación", toque(ops, "actualizaciones-aplicar") and ops.esperar("¿Aplicar esta actualización?", 10000))
        anotar("la confirmación dice qué cambia y que las clases abiertas siguen", hay(ops, "Qué cambia") and hay(ops, "las que ya estén abiertas siguen"))
        ops.captura("07-confirmar-aplicar")
        anotar("confirmar aplica", toque(ops, "actualizaciones-confirmar-aplicar") and ops.esperar("Aplicando la actualización", 20000))
        print("     textos tras confirmar:", [t for t in ops.textos() if t.strip()][:12], flush=True)
        ops.captura("07b-tras-confirmar")
        orden = orden_en_curso(carpeta / "Actualizaciones")
        anotar("el nodo dejó UNA orden de aplicar para el Host", orden is not None and orden.get("accion") == "aplicar", str(orden and orden.get("orden_id")))
        e = estado_api(lector)
        anotar("el nodo está aplicando", e.get("estado") == "aplicando" and e.get("orden_pendiente") is True)
        codigo, cuerpo = ra.api("POST", "/api/aula/sesiones/", {"via": "libre", "profesor_id": "x", "fuente": "aula", "superficie": "pantalla"}, profe_token())
        anotar("iniciar una clase responde 503 actualizacion_en_curso (nunca un 4xx)", codigo == 503 and (cuerpo or {}).get("codigo") == "actualizacion_en_curso", f"{codigo} {cuerpo}")
        anotar("mientras tanto no hay botones que cambien nada (ni un segundo Aplicar)", "Aplicar ahora" not in botones(ops) and "Volver a la versión anterior" not in botones(ops))
        anotar("la pantalla dice que se está actualizando", hay(ops, "El aula se está actualizando"))
        ops.captura("08-aplicando")
        anotar("la orden sigue siendo UNA sola (un segundo toque no emitió otra)", len(list((carpeta / "Actualizaciones").glob("orden*.json"))) == 1)

        # el Host termina (simulado)
        if orden is None:
            return                                   # sin orden no hay nada que el Host termine: lo que falló ya quedó anotado
        host_termina(carpeta / "Actualizaciones", orden, "aplicado")
        anotar("la pantalla se entera sola de que terminó", ops.esperar("La actualización terminó", 40000))
        anotar("queda aplicado y revertible durante 14 días", hay(ops, "Aplicado") and "Volver a la versión anterior" in botones(ops))
        e = estado_api(lector)
        anotar("el nodo volvió a estar al día y con una reversión disponible", e.get("estado") == "al_dia" and len(e.get("revertibles", [])) == 1)
        profe = profe_token()
        codigo, cuerpo = ra.api("POST", "/api/aula/sesiones/", {"via": "libre", "profesor_id": "x", "fuente": "aula", "superficie": "pantalla"}, profe)
        anotar("el inicio de clases ya no responde 503 de actualización (la clase abre)", codigo == 201, f"{codigo}")
        sesion_id = (cuerpo or {}).get("id")
        ops.captura("09-aplicado")

        # con una clase abierta, volver atrás se difiere: el nodo responde 409 y la clase sigue (R-01)
        anotar("Volver a la versión anterior pide el motivo", toque(ops, "actualizaciones-revertir") and ops.esperar("¿Por qué quieres volver atrás?", 10000))
        anotar("sin motivo no se puede confirmar", "Volver a la versión anterior" in botones(ops))
        toque(ops, "actualizaciones-motivo-pantalla")
        ops.captura("10-motivo-de-reversion")
        anotar("con una clase abierta el nodo no vuelve atrás y la pantalla lo dice", toque(ops, "actualizaciones-confirmar-revertir") and ops.esperar("Hay una clase abierta", 20000))
        anotar("no se dejó ninguna orden y la clase sigue abierta", not (carpeta / "Actualizaciones" / "orden.json").exists() and ra.api("GET", f"/api/aula/sesiones/{sesion_id}/", None, profe)[0] == 200)
        ops.captura("10b-revertir-con-clase-abierta")
        codigo, _ = ra.api("POST", f"/api/aula/sesiones/{sesion_id}/cerrar/", {"forzar": True}, profe)
        anotar("la clase se cierra (como lo haría el profesor)", codigo == 200, f"{codigo}")

        # sin clase abierta: volver atrás
        anotar("sin clase, Volver a la versión anterior pide el motivo otra vez", toque(ops, "actualizaciones-revertir") and ops.esperar("¿Por qué quieres volver atrás?", 10000))
        toque(ops, "actualizaciones-motivo-pantalla")
        anotar("confirmar vuelve atrás", toque(ops, "actualizaciones-confirmar-revertir") and ops.esperar("Volviendo a la versión anterior", 20000))
        orden = orden_en_curso(carpeta / "Actualizaciones")
        anotar("el nodo dejó la orden de revertir con la nota elegida", orden is not None and orden.get("accion") == "revertir" and "pantalla" in (orden.get("nota") or "").lower(), str(orden and orden.get("nota")))
        if orden is None:
            return
        host_termina(carpeta / "Actualizaciones", orden, "revertido")
        anotar("la pantalla dice que el aula volvió a la versión anterior", ops.esperar("El aula volvió a la versión anterior", 40000))
        ops.captura("11-revertido")

        anotar("el historial cuenta lo que pasó", toque(ops, "actualizaciones-tab-historial") and ops.esperar("LO ÚLTIMO QUE PASÓ", 10000) and hay(ops, "Se aplicó con éxito") and hay(ops, "Se volvió a la versión anterior"))
        ops.captura("12-historial")
        anotar("volver al menú con un solo toque", al_menu(ops))
    finally:
        ops.cerrar()


def tecnico(exe: Path, salida: Path, usb: Path) -> None:
    (usb / "otro.avupd").write_bytes(paquete("Reportes 1.5.0 · otro paquete", paquete_id=str(uuid.UUID(int=0x17171717_0002_4000_8000_000000000002)), serie=8))
    ops = ra.Ops(exe, salida, f"uia-act-tec-{int(time.time())}")
    try:
        anotar("el soporte técnico llega al acceso", ops.esperar("Escribe tu documento y tu contraseña", 30000))
        ra.entrar(ops, TECNICO_DOC, TECNICO_CLAVE)
        anotar("el soporte técnico ve «Actualizaciones»", ops.esperar("CLASSROOM", 25000) and existe(ops, "dashboard-actualizaciones") and "Actualizaciones" in botones(ops))
        anotar("abre la pantalla", ir_a_actualizaciones(ops))
        anotar("el soporte técnico trae el paquete (update.package.import)", tocar_tarjeta(ops, "otro.avupd") and ops.esperar("Paquete verificado", 20000))
        anotar("no ve Aplicar ni Programar y le dice a quién pedirlo", not ({"Aplicar ahora", "Programar"} & set(botones(ops))) and hay(ops, "la administración del colegio"))
        ops.captura("13-tecnico-sin-aplicar")
    finally:
        ops.cerrar()


def profesor(exe: Path, salida: Path) -> None:
    ops = ra.Ops(exe, salida, f"uia-act-prof-{int(time.time())}")
    try:
        anotar("el profesor llega al acceso", ops.esperar("Escribe tu documento y tu contraseña", 30000))
        ra.entrar(ops, PROFE_DOC, PROFE_CLAVE)
        anotar("el profesor entra", ops.esperar("CLASSROOM", 25000))
        anotar("el profesor no tiene botón «Actualizaciones»", "Actualizaciones" not in botones(ops) and not existe(ops, "dashboard-actualizaciones"))
        ops.captura("14-profesor-sin-actualizaciones")
    finally:
        ops.cerrar()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ops", required=True)
    p.add_argument("--salida", required=True)
    p.add_argument("--puerto", type=int, default=8010)
    args = p.parse_args()
    ra.NODO = f"http://127.0.0.1:{args.puerto}"
    if ra.puerto_ocupado(args.puerto):
        print(f"El puerto {args.puerto} ya está en uso: usa --puerto con otro libre.")
        return 2
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    trabajo = Path(tempfile.mkdtemp(prefix="ops-uia-act-"))
    usb = trabajo / "memoria"
    usb.mkdir()
    (usb / "alterado.avupd").write_bytes(paquete("Reportes alterado", paquete_id=str(uuid.UUID(int=0x17171717_0009_4000_8000_000000000009)), alterar=True))
    (usb / "reportes-1.4.0.avupd").write_bytes(paquete("Reportes 1.4.0 · corrección del boletín", paquete_id=emisor.PAQUETE_ID))
    letra = libre_para_subst()
    subprocess.run(["subst", f"{letra}:", str(usb)], check=True)
    print(f"Nodo aislado en {ra.NODO}, memoria {letra}: → {usb}", flush=True)
    nodo = levantar_nodo(trabajo / "nodo.sqlite3", trabajo / "estado", f"{letra}:\\")
    ra.tomar_candado()
    try:
        lector = sembrar()
        administracion(Path(args.ops), salida, lector, trabajo / "estado", usb)
        tecnico(Path(args.ops), salida, usb)
        profesor(Path(args.ops), salida)
    finally:
        ra.soltar_candado()
        nodo.kill()
        subprocess.run(["subst", f"{letra}:", "/D"], capture_output=True)
        shutil.rmtree(trabajo, ignore_errors=True)
    fallos = [r for r in resultados if not r[1]]
    print(f"\n{len(resultados) - len(fallos)} de {len(resultados)} comprobaciones cumplidas. Capturas en {salida}")
    for paso, _, detalle in fallos:
        print(f"  FALLÓ: {paso} {detalle}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())

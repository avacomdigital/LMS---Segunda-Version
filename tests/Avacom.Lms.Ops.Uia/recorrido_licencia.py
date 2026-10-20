r"""
Verificación independiente de MOD-018 · recorrido de interfaz de la pantalla LICENCIA de AVACOM OPS contra un nodo AISLADO con la licencia en modo `firmada`.

Reutiliza el arnés de `tests/Avacom.Lms.Ops.Uia` (UIA sin ratón ni teclado, PrintWindow, regla de tercios). Qué hace:
  · levanta un nodo propio (base y carpeta de estado temporales, puerto aparte, sesión obligatoria, programador cada 5 s), instala la organización y crea administración, soporte técnico, un
    profesor y una cuenta LECTORA de soporte que sólo usa el guion, por la API, para mirar el estado (la sesión del personal es única: entrar por la API cerraría la de OPS);
  · mapea una carpeta temporal como unidad (subst) que hace de memoria USB;
  · como lo haría el personal de AVACOM, firma las licencias con la llave de DESARROLLO de las pruebas a partir de la solicitud que OPS guardó en la «memoria»;
  · recorre: evaluación, activar en tres pasos, copia de custodia, renovar, gracia, funciones en pausa, soporte técnico que no renueva, liberar, volver a activar, Reportes y Buscar con la
    licencia en pausa (y el núcleo sin aviso) y el profesor que no ve nada.

Los controles se tocan por AutomationId (`tecla` de ui-ops.ps1 invoca cualquier control por su AutomationId): dos botones pueden llamarse igual en la página y en la hoja.

Uso (desde la raíz del repositorio, con OPS compilado para Windows):
    backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\recorrido_licencia.py --ops <Avacom.Lms.Ops.exe> --salida <carpeta> [--puerto 8013] [--sin-modulos]
Sale con 0 si todo se cumplió; con 1 y la lista de lo que falló si no (≈ 12 minutos, con las ventanas de OPS en primer plano).
No toca el nodo del aula (:8000) ni la OPS de quien trabaja en el equipo: perfil de pruebas propio. Sólo corre en un árbol de desarrollo (usa las llaves de desarrollo de las pruebas).
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
import uuid
from pathlib import Path

sys.dont_write_bytecode = True                   # que el guion no deje __pycache__ en tests/ (git no lo ignora ahí)
AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
BACKEND = RAIZ / "backend"
UIA = AQUI
sys.path.insert(0, str(BACKEND))

spec = importlib.util.spec_from_file_location("recorrido_acceso", UIA / "recorrido_acceso.py")
ra = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ra)                      # sólo define funciones y constantes: no corre nada

from licenciamiento.dominio import solicitud as sol  # noqa: E402
from licenciamiento.dominio.licencia import Limites  # noqa: E402
from licenciamiento.tests import emisor  # noqa: E402

ADMIN_DOC, ADMIN_CLAVE, PIN = "1042888795", "Rectoria.Uia.2026!", "482915"
TECNICO_DOC, TECNICO_CLAVE = "70111222", "Tecnico.Uia.2026!"
LECTOR_DOC, LECTOR_CLAVE = "70999888", "Lector.Uia.2026!"          # sólo la usa el guion, por la API, para mirar el estado sin cerrar la sesión de OPS
PROFE_DOC, PROFE_CLAVE = "52100200", "Profe.Uia.2026!"
DIA = 86_400_000

resultados = ra.resultados
anotar = ra.anotar


# ------------------------------------------------------------------------------------------------------------------------ nodo y datos
def levantar_nodo(db: Path, estado: Path) -> subprocess.Popen:
    env = {**os.environ, "AVACOM_LMS_DB": str(db), "AVACOM_LMS_EXIGIR_SESION": "1", "PYTHONIOENCODING": "utf-8", "AVACOM_LICENCIA_MODO": "firmada",
           "AVACOM_LICENCIA_DIR": str(estado), "AVACOM_LICENCIA_INTERVALO_S": "5", "AVACOM_LMS_DIR_LOGS": str(estado / "logs")}
    py = ra.python_backend()
    subprocess.run([py, "manage.py", "migrate", "--noinput"], cwd=BACKEND, env=env, check=True, capture_output=True)
    nodo = subprocess.Popen([py, "manage.py", "runserver", ra.NODO.removeprefix("http://"), "--noreload"], cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            import urllib.request
            urllib.request.urlopen(f"{ra.NODO}/health/", timeout=2)
            return nodo
        except Exception:
            time.sleep(1)
    nodo.kill()
    raise RuntimeError(f"El nodo de prueba no arrancó en {ra.NODO}")


def sembrar() -> str:
    """Instala la organización y crea soporte técnico, un profesor y la cuenta lectora. Devuelve el token de la LECTORA (soporte técnico: license.read), no el de la administración."""
    codigo, r = ra.api("POST", "/api/acceso/instalacion/", {
        "organizacion": {"codigo": "IE-UIA-LIC", "nombre": "IE Prueba Licencia", "pais": "CO", "idioma": "es", "locale": "es-CO"},
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


def estado_api(token: str) -> dict:
    return ra.api("GET", "/api/licencia/estado/", None, token)[1]


# ------------------------------------------------------------------------------------------------------------------------ la «memoria USB»
def libre_para_subst() -> str:
    for letra in "XWVUTSRQ":
        if not Path(f"{letra}:\\").exists():
            return letra
    raise RuntimeError("no hay una letra de unidad libre")


# ------------------------------------------------------------------------------------------------------------------------ AVACOM firma
def solicitud_mas_reciente(memoria: Path) -> Path:
    archivos = sorted(memoria.glob("solicitud-*.avreq"), key=lambda p: p.stat().st_mtime)
    return archivos[-1]


def firmar(avreq: Path, destino: Path, *, serie: int = 1, licencia_id: str | None = None, desde_dias: int = -1, vence_dias: int = 365, gracia: int = 30, aula: str = "Colegio UIA",
           limites: Limites | None = None, **extra) -> Path:
    """Lo que haría AVACOM con la solicitud: una licencia firmada con la llave de desarrollo, para ESA huella."""
    s = sol.leer_solicitud(avreq.read_bytes())
    ahora = int(time.time() * 1000)
    anterior = getattr(s, "licencia_vigente", None)
    lic = emisor.licencia_de_ejemplo(
        id=licencia_id or anterior or str(uuid.uuid4()), serie=serie, aula=aula, emitida=ahora - 3_600_000 + serie * 1000, desde=ahora + desde_dias * DIA, vence=ahora + vence_dias * DIA,
        gracia_dias=gracia, huella=s.huella, limites=limites or Limites(equipos=55, usuarios=1200, concurrentes_normal=50, concurrentes_pico=100), **extra)
    destino.write_bytes(emisor.emitir(lic))
    return destino


# ------------------------------------------------------------------------------------------------------------------------ gestos de UIA
def botones(ops) -> list[str]:
    return [l.split("\t")[1] for l in ops.ui("list")[1].splitlines() if l.startswith("Button\t")]


def hay(ops, fragmento: str) -> bool:
    return any(fragmento.lower() in t.lower() for t in ops.textos())


def toque(ops, ident: str, intentos: int = 8) -> bool:
    """Un toque a un control por su AutomationId (no por su nombre: la página y la hoja tienen botones que se llaman igual)."""
    for _ in range(intentos):
        codigo, _ = ops.ui("tecla", nombre=ident)
        if codigo == 0:
            return True
        time.sleep(0.8)
    print(f"     (no hay un control con AutomationId «{ident}»)", flush=True)
    return False


def tocar_tarjeta(ops, fragmento: str, intentos: int = 10) -> bool:
    """Las tarjetas son botones transparentes con la descripción como nombre: se busca el que contiene el fragmento."""
    for _ in range(intentos):
        for nombre in botones(ops):
            if fragmento.lower() in nombre.lower():
                return ops.invocar(nombre)
        time.sleep(1)
    print(f"     (no hay tarjeta con «{fragmento}»; hay: {botones(ops)})", flush=True)
    return False


def entrar(ops, doc: str, clave: str, pin: str | None = None) -> None:
    ra.entrar(ops, doc, clave, pin)


def cerrar_sesion(ops) -> None:
    ra.cerrar_sesion(ops)


def ir_a_licencia(ops) -> bool:
    return toque(ops, "dashboard-licencia") and ops.esperar("Licencia de este equipo", 15000)


def guardar_solicitud(ops, letra: str) -> bool:
    """Activar o renovar → elegir la memoria → Guardar la solicitud."""
    ok = toque(ops, "licencia-activar")
    ok = ops.esperar("Guarda la solicitud de este equipo", 15000) and ok
    ok = tocar_tarjeta(ops, f"({letra}:)") and ok
    ok = toque(ops, "licencia-guardar-solicitud") and ok
    return ops.esperar("La solicitud quedó guardada", 25000) and ok


def hasta_la_confirmacion(ops, nombre_archivo: str) -> bool:
    ok = toque(ops, "licencia-continuar")
    ok = ops.esperar("AVACOM firma tu licencia", 10000) and ok
    ok = toque(ops, "licencia-ya-tengo") and ok
    ok = ops.esperar("Elige el archivo de licencia", 20000) and ok
    ok = tocar_tarjeta(ops, nombre_archivo) and ok
    return ops.esperar("Confirma antes de instalar", 10000) and ok


def etiqueta_final(ops) -> str:
    """Lo que dice el botón de instalar: «Renovar la licencia» (licencia sana + administración) o «Instalar la licencia»."""
    for nombre in botones(ops):
        if nombre in ("Renovar la licencia", "Instalar la licencia"):
            return nombre
    return ""


def instalar(ops, nombre_archivo: str, texto_resultado: str) -> tuple[bool, str]:
    ok = hasta_la_confirmacion(ops, nombre_archivo)
    etiqueta = etiqueta_final(ops)
    ok = toque(ops, "licencia-instalar") and ok
    return ops.esperar(texto_resultado, 30000) and ok, etiqueta


def cerrar_hoja(ops) -> bool:
    return toque(ops, "licencia-listo")


# ------------------------------------------------------------------------------------------------------------------------ el recorrido de la pantalla Licencia
def recorrido(exe: Path, salida: Path, token: str, memoria: Path, letra: str) -> None:
    perfil = f"uia-lic-{int(time.time())}"
    ops = ra.Ops(exe, salida, perfil)
    try:
        # 1 · administración: evaluación
        anotar("el acceso abre con el nodo instalado", ops.esperar("Escribe tu documento y tu contraseña", 30000))
        entrar(ops, ADMIN_DOC, ADMIN_CLAVE, PIN)
        anotar("llega al menú principal con el botón «Licencia»", ops.esperar("Licencia", 25000) and "Licencia" in botones(ops))
        anotar("el aviso de evaluación existe desde el primer día", ops.esperar("todavía no tiene licencia", 15000) and hay(ops, "de evaluación"))
        ops.captura("01-menu-evaluacion")
        anotar("el aviso trae el botón «Ver la licencia»", "Ver la licencia" in botones(ops))

        anotar("la pantalla Licencia abre", ir_a_licencia(ops))
        anotar("estado de evaluación a la vista", ops.esperar("En evaluación", 10000) and hay(ops, "periodo de evaluación"))
        anotar("uso de lo contratado y módulos a la vista", hay(ops, "USO DE LO CONTRATADO") and hay(ops, "Reportes") and hay(ops, "Búsqueda"))
        ops.captura("02-licencia-evaluacion")

        # 2 · activar en tres pasos
        anotar("paso 1: la solicitud queda guardada en la memoria", guardar_solicitud(ops, letra))
        ops.captura("03-paso1-solicitud-guardada")
        avreq = solicitud_mas_reciente(memoria)
        anotar("el archivo de solicitud existe en la memoria con su nombre", avreq.exists() and avreq.name.startswith("solicitud-") and avreq.suffix == ".avreq", avreq.name)
        firmar(avreq, memoria / "colegio-uia-s1.avlic", serie=1)
        toque(ops, "licencia-continuar")
        anotar("paso 2 explica que AVACOM firma", ops.esperar("AVACOM firma tu licencia", 10000))
        ops.captura("04-paso2-avacom-firma")
        toque(ops, "licencia-ya-tengo")
        anotar("paso 3: aparece la tarjeta de la licencia", ops.esperar("Elige el archivo de licencia", 20000) and any("colegio-uia-s1.avlic" in b for b in botones(ops)))
        ops.captura("05-paso3-tarjetas")
        tocar_tarjeta(ops, "colegio-uia-s1.avlic")
        anotar("una sola confirmación antes de instalar", ops.esperar("Confirma antes de instalar", 10000) and hay(ops, "Vas a instalar"))
        ops.captura("06-confirmacion")
        anotar("sin licencia el botón final dice «Instalar la licencia»", etiqueta_final(ops) == "Instalar la licencia", etiqueta_final(ops))
        anotar("se instala y dice «Licencia activada»", toque(ops, "licencia-instalar") and ops.esperar("Licencia activada", 30000))
        ops.captura("07-licencia-activada")
        cerrar_hoja(ops)
        anotar("la pantalla muestra «Activa», el aula y la serie", ops.esperar("Licencia activa", 15000) and hay(ops, "Colegio UIA") and hay(ops, "Serie"))
        e = estado_api(token)
        anotar("el nodo coincide: activa, serie 1, límites 55/1200", (e.get("estado"), e.get("licencia", {}).get("serie"), e.get("limites", {}).get("equipos"), e.get("limites", {}).get("usuarios")) == ("activa", 1, 55, 1200),
               str(e.get("estado")))
        ops.captura("08-licencia-activa")

        # 3 · copia de custodia
        anotar("la copia de custodia se abre", toque(ops, "licencia-copia") and ops.esperar("COPIA DE CUSTODIA", 10000))
        anotar("elige la memoria y guarda la copia", tocar_tarjeta(ops, f"({letra}:)") and toque(ops, "licencia-copia-guardar") and ops.esperar("La copia quedó guardada", 30000))
        ops.captura("09-copia-guardada")
        cerrar_hoja(ops)
        copias = sorted(p.name for p in memoria.iterdir() if p.is_file())
        anotar("la copia dejó los tres archivos (.avlic, .avreq y la hoja)", any(n.startswith("licencia-") and n.endswith(".avlic") for n in copias) and "LEEME-licencia-AVACOM.txt" in copias, ", ".join(copias))
        hoja = (memoria / "LEEME-licencia-AVACOM.txt").read_text(encoding="utf-8-sig")
        anotar("la hoja explica cómo reactivar y no lleva documentos ni nombres de personas", "CÓMO VOLVER A ACTIVAR LA LICENCIA" in hoja and ADMIN_DOC not in hoja and "Pérez" not in hoja and "SHA-256" in hoja)

        # 4 · renovar (misma licencia, serie 2): con una licencia sana y la administración el botón dice «Renovar»
        anotar("renovar: guarda una solicitud nueva", guardar_solicitud(ops, letra))
        firmar(solicitud_mas_reciente(memoria), memoria / "colegio-uia-s2.avlic", serie=2, vence_dias=730)
        ok, etiqueta = instalar(ops, "colegio-uia-s2.avlic", "Licencia renovada")
        anotar("renovar: con licencia sana el botón dice «Renovar la licencia» y queda «Licencia renovada»", ok and etiqueta == "Renovar la licencia", etiqueta)
        ops.captura("10-licencia-renovada")
        cerrar_hoja(ops)
        anotar("serie 2 en la pantalla", ops.esperar("Licencia activa", 15000) and estado_api(token)["licencia"]["serie"] == 2)

        # 5 · gracia y funciones en pausa, con licencias ya vencidas (sin tocar la fecha del equipo)
        guardar_solicitud(ops, letra)
        firmar(solicitud_mas_reciente(memoria), memoria / "colegio-uia-s3.avlic", serie=3, desde_dias=-90, vence_dias=-5, gracia=30)
        ok, etiqueta = instalar(ops, "colegio-uia-s3.avlic", "Licencia renovada")
        anotar("licencia vencida dentro de la gracia: se instala", ok, etiqueta)
        cerrar_hoja(ops)
        anotar("estado «Vencida · en gracia»", ops.esperar("Vencida · en gracia", 15000))
        ops.captura("11-licencia-en-gracia")
        anotar("la gracia no pausa nada: los módulos siguen encendidos", not hay(ops, "Algunos módulos están en pausa"))

        guardar_solicitud(ops, letra)
        firmar(solicitud_mas_reciente(memoria), memoria / "colegio-uia-s4.avlic", serie=4, desde_dias=-200, vence_dias=-60, gracia=30)
        ok, etiqueta = instalar(ops, "colegio-uia-s4.avlic", "Licencia renovada")
        anotar("en gracia el botón final dice «Instalar la licencia» (la renovación sana es otra cosa)", ok and etiqueta == "Instalar la licencia", etiqueta)
        cerrar_hoja(ops)
        anotar("estado «Funciones en pausa» con los módulos en pausa", ops.esperar("Funciones en pausa", 15000) and hay(ops, "Algunos módulos están en pausa"))
        anotar("la pantalla dice que las clases siguen", hay(ops, "Las clases, las evaluaciones y el modo de estudio siguen igual"))
        ops.captura("12-licencia-funciones-en-pausa")
        e = estado_api(token)
        anotar("el nodo coincide: degradada y ningún módulo licenciable", e.get("estado") == "degradada" and e.get("capacidades", {}).get("habilitadas") == [], str(e.get("estado")))
        ops.invocar("Menú principal")
        anotar("el menú principal muestra el aviso de funciones en pausa con «Ver la licencia»", ops.esperar("en pausa", 15000) and "Ver la licencia" in botones(ops))
        ops.captura("13-menu-funciones-en-pausa")

        # 6 · soporte técnico: ve la licencia, no renueva
        cerrar_sesion(ops)
        entrar(ops, TECNICO_DOC, TECNICO_CLAVE)
        anotar("el soporte técnico ve el botón «Licencia» y el aviso", ops.esperar("Licencia", 25000) and "Licencia" in botones(ops) and "Ver la licencia" in botones(ops))
        ir_a_licencia(ops)
        anotar("el soporte técnico ve la nota «Renovar la licencia lo hace la administración»", hay(ops, "Renovar la licencia lo hace la administración"))
        guardar_solicitud(ops, letra)
        firmar(solicitud_mas_reciente(memoria), memoria / "colegio-uia-s5.avlic", serie=5, vence_dias=365)
        ok, etiqueta = instalar(ops, "colegio-uia-s5.avlic", "Renovar es de la administración")
        anotar("el soporte técnico no renueva: «Renovar es de la administración»", ok and hay(ops, "Pídeselo a la administración del colegio"), etiqueta)
        ops.captura("14-tecnico-no-renueva")
        anotar("tras el rechazo no se cambió nada: sigue en pausa", estado_api(token).get("estado") == "degradada")
        toque(ops, "licencia-hoja-cerrar")
        ops.invocar("Menú principal")
        cerrar_sesion(ops)

        # 7 · la administración renueva con la serie 5
        entrar(ops, ADMIN_DOC, ADMIN_CLAVE, PIN)
        ir_a_licencia(ops)
        toque(ops, "licencia-activar")
        ops.esperar("Guarda la solicitud de este equipo", 15000)
        toque(ops, "licencia-ya-tengo")
        ops.esperar("Elige el archivo de licencia", 20000)
        tocar_tarjeta(ops, "colegio-uia-s5.avlic")
        ops.esperar("Confirma antes de instalar", 10000)
        anotar("la administración renueva con la serie 5", toque(ops, "licencia-instalar") and ops.esperar("Licencia renovada", 30000))
        cerrar_hoja(ops)
        anotar("vuelve «Activa» y los módulos se encienden", ops.esperar("Licencia activa", 15000) and not hay(ops, "Algunos módulos están en pausa"))
        ops.captura("15-renovada-tras-pausa")

        # 8 · liberar y volver a activar
        anotar("liberar este equipo: abre la hoja y elige la memoria", toque(ops, "licencia-liberar") and ops.esperar("LIBERAR ESTE EQUIPO", 10000) and tocar_tarjeta(ops, f"({letra}:)"))
        anotar("liberar: pide una confirmación", toque(ops, "licencia-continuar") and ops.esperar("Confirma la liberación", 10000))
        ops.captura("16-confirma-liberacion")
        anotar("queda liberado y guarda el archivo .avrel", toque(ops, "licencia-liberar-confirmar") and ops.esperar("quedó liberado", 30000))
        ops.captura("17-liberado")
        cerrar_hoja(ops)
        avrel = list(memoria.glob("liberacion-*.avrel"))
        anotar("el archivo de liberación existe en la memoria", len(avrel) == 1, ", ".join(p.name for p in avrel))
        anotar("el equipo vuelve a «En evaluación»", ops.esperar("En evaluación", 15000))
        ops.captura("18-tras-liberar")
        anotar("el nodo coincide: sin licencia", estado_api(token).get("estado") == "sin_licencia")

        toque(ops, "licencia-activar")
        ops.esperar("Guarda la solicitud de este equipo", 15000)
        toque(ops, "licencia-ya-tengo")
        ops.esperar("Elige el archivo de licencia", 20000)
        tocar_tarjeta(ops, "colegio-uia-s5.avlic")
        ops.esperar("Confirma antes de instalar", 10000)
        anotar("se deshace volviendo a activar el mismo archivo", toque(ops, "licencia-instalar") and ops.esperar("Licencia activada", 30000))
        cerrar_hoja(ops)
        anotar("queda «Activa»", ops.esperar("Licencia activa", 15000))
    finally:
        ops.cerrar()


def modulos_en_pausa(exe: Path, salida: Path, memoria: Path) -> None:
    """Con la licencia degradada: Reportes y Buscar (módulos licenciables) lo dicen en pantalla; Evaluaciones, Calificaciones y Clase de hoy (núcleo) abren sin aviso de licencia."""
    _, s = ra.api("POST", "/api/acceso/sesiones/", {"identificador": ADMIN_DOC, "secreto": ADMIN_CLAVE, "dispositivo": "", "pin_maestro": PIN})
    admin = s["token"]
    _, r = ra.api("POST", "/api/licencia/solicitud/", {}, admin)
    avreq = memoria / "api-solicitud.avreq"
    avreq.write_bytes(base64.b64decode(r["archivo_b64"]))
    avlic = firmar(avreq, memoria / "colegio-uia-s6.avlic", serie=6, desde_dias=-300, vence_dias=-90, gracia=30)
    codigo, r2 = ra.api("POST", "/api/licencia/renovar/", {"archivo_b64": base64.b64encode(avlic.read_bytes()).decode()}, admin)
    anotar("se deja el nodo con las funciones en pausa (serie 6, vencida)", codigo == 200 and r2.get("estado") == "degradada", f"{codigo} {r2.get('estado')}")
    for ruta, esperado, nombre in (("reportes", "No disponible con la licencia de este equipo", "Reportes"), ("buscar", "licencia", "Buscar")):
        ops = ra.Ops(exe, salida, f"uia-lic-mod-{ruta}-{int(time.time())}", ruta=ruta)
        try:
            ops.esperar("Escribe tu documento y tu contraseña", 30000)
            entrar(ops, ADMIN_DOC, ADMIN_CLAVE, PIN)
            anotar(f"{nombre} (módulo en pausa) lo dice en pantalla", ops.esperar(esperado, 30000), "; ".join(t for t in ops.textos() if "licencia" in t.lower())[:200])
            ops.captura(f"20-{ruta}-en-pausa")
        finally:
            ops.cerrar()
    for ruta, nombre in (("evaluaciones", "Evaluaciones"), ("calificaciones", "Calificaciones"), ("clase-hoy", "Clase de hoy")):
        ops = ra.Ops(exe, salida, f"uia-lic-nuc-{ruta}-{int(time.time())}", ruta=ruta)
        try:
            ops.esperar("Escribe tu documento y tu contraseña", 30000)
            entrar(ops, ADMIN_DOC, ADMIN_CLAVE, PIN)
            time.sleep(8)
            textos = " ".join(ops.textos()).lower()
            anotar(f"{nombre} (núcleo) abre sin ningún aviso de licencia", "con la licencia de este equipo" not in textos and "no disponible por la licencia" not in textos, textos[:140])
            ops.captura(f"21-{ruta}-con-licencia-en-pausa")
        finally:
            ops.cerrar()


def profesor(exe: Path, salida: Path) -> None:
    ops = ra.Ops(exe, salida, f"uia-lic-prof-{int(time.time())}")
    try:
        anotar("el profesor llega al acceso", ops.esperar("Escribe tu documento y tu contraseña", 30000))
        entrar(ops, PROFE_DOC, PROFE_CLAVE)
        anotar("el profesor entra", ops.esperar("CLASSROOM", 25000))
        anotar("el profesor no tiene botón «Licencia» ni aviso de licencia", "Licencia" not in botones(ops) and "Ver la licencia" not in botones(ops))
        ops.captura("19-profesor-sin-licencia")
    finally:
        ops.cerrar()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ops", required=True)
    p.add_argument("--salida", required=True)
    p.add_argument("--puerto", type=int, default=8013)
    p.add_argument("--sin-modulos", action="store_true", help="no abre Reportes, Buscar ni el núcleo con la licencia en pausa")
    args = p.parse_args()
    ra.NODO = f"http://127.0.0.1:{args.puerto}"
    if ra.puerto_ocupado(args.puerto):
        print(f"El puerto {args.puerto} ya está en uso: usa --puerto con otro libre.")
        return 2
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    trabajo = Path(tempfile.mkdtemp(prefix="ops-uia-lic-"))
    memoria = trabajo / "memoria"
    memoria.mkdir()
    letra = libre_para_subst()
    subprocess.run(["subst", f"{letra}:", str(memoria)], check=True)
    print(f"Nodo aislado en {ra.NODO}, memoria {letra}: → {memoria}", flush=True)
    nodo = levantar_nodo(trabajo / "nodo.sqlite3", trabajo / "estado")
    ra.tomar_candado()
    try:
        token = sembrar()
        recorrido(Path(args.ops), salida, token, memoria, letra)
        profesor(Path(args.ops), salida)
        if not args.sin_modulos:
            modulos_en_pausa(Path(args.ops), salida, memoria)
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

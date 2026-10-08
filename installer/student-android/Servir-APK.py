"""
Servidor local del APK de AVACOM Student: instala muchas tabletas por la red del aula, sin cable.

    python Servir-APK.py                       # puerto 8080, el APK mas nuevo de esta carpeta, sin meta de tabletas
    python Servir-APK.py --tabletas 55 --abrir # cuenta hasta 55 y abre el panel en el navegador de este equipo
    python Servir-APK.py --puerto 8081         # otro puerto (el 8000 es el de la API de OPS: no lo uses)
    python Servir-APK.py --apk "Student LMS 2.4.0.apk" --aula http://192.168.0.55:8000

Lo normal es tocar Servir-APK.bat, que pide el permiso de administrador una vez, usa el Python que hay (el de esta
carpeta, el de AVACOM OPS Master o el del equipo) y llama a este archivo.

Solo biblioteca estandar de Python: no instala nada y no necesita internet. Atiende unicamente:

    /                       en ESTE equipo: el panel (codigo QR, direccion, cuantas tabletas ya descargaron, boton Detener);
                            desde otra tableta: la pagina de descarga
    /panel/                 el panel, desde cualquier equipo de la red
    /download/              la pagina de descarga que ve la tableta: boton, pasos y direccion del aula
    /download/<archivo>.apk el APK (con Range, para que Chrome pueda reanudar si se corta el Wi-Fi)
    /download/SHA256.txt    la huella del APK, para verificarlo
    /estado.json            lo que cuenta el panel (se actualiza solo)

No toca el backend ni sirve nada mas que el APK de esta carpeta. Pensado para una red cerrada del aula (HTTP, sin
sesion): detenlo (boton Detener o Ctrl+C) cuando acabes de instalar las tabletas. Mientras corre, con permiso de
administrador, abre el puerto en el Firewall de Windows SOLO para la red local, y lo cierra al detenerse.

El codificador de codigos QR de este archivo es propio (modo byte, niveles L/M, versiones 1 a 6: direcciones de hasta
~100 caracteres). Si una direccion no cabe, el panel muestra solo el texto.
"""
import argparse
import csv
import hashlib
import html
import http.client
import http.server
import json
import os
import pathlib
import re
import socket
import string
import subprocess
import sys
import threading
import time
import zipfile

CARPETA = pathlib.Path(__file__).resolve().parent
TIPO_APK = "application/vnd.android.package-archive"
PUERTO_AULA = 8000
REGLA_FIREWALL = "AVACOM Student APK (temporal)"
CSV_DESCARGAS = "descargas-apk.csv"


# ======================================================================================================================
# Codigo QR (ISO/IEC 18004). Modo byte (UTF-8), niveles de correccion L y M, versiones 1 a 6.
# ======================================================================================================================

def _tablas_gf():
    exp, log = [0] * 512, [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    return exp, log


_EXP, _LOG = _tablas_gf()


def _gf_mul(a: int, b: int) -> int:
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _rs_resto(datos: list, n_ec: int) -> list:
    """Resto de dividir datos(x)*x^n entre el generador de grado n (Reed-Solomon sobre GF(256))."""
    g = [1]
    for i in range(n_ec):
        nuevo = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            nuevo[j] ^= c
            nuevo[j + 1] ^= _gf_mul(c, _EXP[i])
        g = nuevo
    resto = [0] * n_ec
    for byte in datos:
        factor = byte ^ resto[0]
        resto = resto[1:] + [0]
        if factor:
            for i in range(n_ec):
                resto[i] ^= _gf_mul(g[i + 1], factor)
    return resto


# (version, nivel) -> (codewords de correccion por bloque, numero de bloques, codewords de datos por bloque)
_BLOQUES = {
    (1, "L"): (7, 1, 19), (2, "L"): (10, 1, 34), (3, "L"): (15, 1, 55), (4, "L"): (20, 1, 80), (5, "L"): (26, 1, 108), (6, "L"): (18, 2, 68),
    (1, "M"): (10, 1, 16), (2, "M"): (16, 1, 28), (3, "M"): (26, 1, 44), (4, "M"): (18, 2, 32), (5, "M"): (24, 2, 43), (6, "M"): (16, 4, 27),
}
_ALINEACION = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34]}
_BITS_NIVEL = {"L": 1, "M": 0}


def _codewords(datos_utf8: bytes, version: int, nivel: str) -> list:
    n_ec, n_bloques, por_bloque = _BLOQUES[(version, nivel)]
    capacidad = n_bloques * por_bloque
    bits = []

    def agregar(valor: int, cuantos: int):
        for i in range(cuantos - 1, -1, -1):
            bits.append((valor >> i) & 1)

    agregar(0b0100, 4)                      # modo byte
    agregar(len(datos_utf8), 8)             # largo (8 bits en versiones 1 a 9)
    for b in datos_utf8:
        agregar(b, 8)
    agregar(0, min(4, capacidad * 8 - len(bits)))   # terminador
    while len(bits) % 8:
        bits.append(0)
    palabras = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    relleno = (0xEC, 0x11)
    while len(palabras) < capacidad:
        palabras.append(relleno[(len(palabras) - len(bits) // 8) % 2])
    bloques = [palabras[i * por_bloque:(i + 1) * por_bloque] for i in range(n_bloques)]
    correccion = [_rs_resto(b, n_ec) for b in bloques]
    salida = []
    for i in range(por_bloque):
        for b in bloques:
            salida.append(b[i])
    for i in range(n_ec):
        for c in correccion:
            salida.append(c[i])
    return salida


def _penalidad(m: list, tam: int) -> int:
    total = 0
    filas = ["".join("1" if v else "0" for v in fila) for fila in m]
    columnas = ["".join("1" if m[y][x] else "0" for y in range(tam)) for x in range(tam)]
    for linea in filas + columnas:                        # N1: rachas de 5 o mas del mismo color
        for racha in re.finditer(r"0{5,}|1{5,}", linea):
            total += 3 + len(racha.group()) - 5
        for patron in ("10111010000", "00001011101"):      # N3: parecido a un localizador
            total += 40 * len(re.findall("(?=%s)" % patron, linea))
    for y in range(tam - 1):                              # N2: bloques de 2x2
        for x in range(tam - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                total += 3
    oscuros = sum(sum(1 for v in fila if v) for fila in m)
    total += 10 * (abs(oscuros * 100 // (tam * tam) - 50) // 5)    # N4: equilibrio de oscuros y claros
    return total


def qr_modulos(texto: str, nivel: str = "M", mascara_fija=None):
    """Matriz de modulos (lista de filas de bool) del codigo QR de `texto`, o None si no cabe (version 6).
    `mascara_fija` (0 a 7) solo existe para las pruebas: normalmente se elige la de menor penalidad."""
    datos = texto.encode("utf-8")
    version = next((v for v in range(1, 7) if 12 + 8 * len(datos) <= 8 * _BLOQUES[(v, nivel)][1] * _BLOQUES[(v, nivel)][2]), None)
    if version is None:
        return None
    tam = 17 + 4 * version
    mods = [[False] * tam for _ in range(tam)]
    funcion = [[False] * tam for _ in range(tam)]

    def poner(x: int, y: int, oscuro: bool):
        mods[y][x] = oscuro
        funcion[y][x] = True

    for i in range(tam):                                  # sincronizacion
        poner(6, i, i % 2 == 0)
        poner(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (tam - 4, 3), (3, tam - 4)):    # localizadores con su separador
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < tam and 0 <= y < tam:
                    poner(x, y, max(abs(dx), abs(dy)) not in (2, 4))
    pos = _ALINEACION[version]
    for i, cy in enumerate(pos):                           # alineacion (versiones 2 a 6: una sola, abajo a la derecha)
        for j, cx in enumerate(pos):
            if (i == 0 and j == 0) or (i == 0 and j == len(pos) - 1) or (i == len(pos) - 1 and j == 0):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    poner(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)

    def formato(mascara: int):
        d = (_BITS_NIVEL[nivel] << 3) | mascara
        resto = d
        for _ in range(10):
            resto = (resto << 1) ^ ((resto >> 9) * 0x537)
        bits = ((d << 10) | resto) ^ 0x5412
        bit = lambda i: ((bits >> i) & 1) != 0
        for i in range(6):
            poner(8, i, bit(i))
        poner(8, 7, bit(6))
        poner(8, 8, bit(7))
        poner(7, 8, bit(8))
        for i in range(9, 15):
            poner(14 - i, 8, bit(i))
        for i in range(8):
            poner(tam - 1 - i, 8, bit(i))
        for i in range(8, 15):
            poner(8, tam - 15 + i, bit(i))
        poner(8, tam - 8, True)                           # el modulo oscuro fijo

    formato(0)                                            # reserva el sitio del formato

    palabras = _codewords(datos, version, nivel)
    i = 0
    for derecha in range(tam - 1, 0, -2):                  # datos: columnas de dos en dos, en zigzag
        if derecha <= 6:
            derecha -= 1
        for vert in range(tam):
            for j in range(2):
                x = derecha - j
                arriba = ((derecha + 1) & 2) == 0
                y = (tam - 1 - vert) if arriba else vert
                if not funcion[y][x] and i < len(palabras) * 8:
                    mods[y][x] = ((palabras[i >> 3] >> (7 - (i & 7))) & 1) != 0
                    i += 1

    def enmascarar(m: int):
        for y in range(tam):
            for x in range(tam):
                if funcion[y][x]:
                    continue
                invertir = (
                    (x + y) % 2 == 0, y % 2 == 0, x % 3 == 0, (x + y) % 3 == 0, (x // 3 + y // 2) % 2 == 0,
                    x * y % 2 + x * y % 3 == 0, (x * y % 2 + x * y % 3) % 2 == 0, ((x + y) % 2 + x * y % 3) % 2 == 0)[m]
                if invertir:
                    mods[y][x] = not mods[y][x]

    mejor, menor = 0, None
    for m in (range(8) if mascara_fija is None else (mascara_fija,)):
        enmascarar(m)
        formato(m)
        p = _penalidad(mods, tam)
        if menor is None or p < menor:
            mejor, menor = m, p
        enmascarar(m)                                     # deshace la mascara
    enmascarar(mejor)
    formato(mejor)
    return mods


def qr_svg(texto: str) -> str:
    """El QR como <svg> en linea (cuatro modulos de margen: la zona de silencio que pide la norma). Vacio si no cabe."""
    mods = qr_modulos(texto)
    if mods is None:
        return ""
    n, borde = len(mods), 4
    trazos = []
    for y, fila in enumerate(mods):
        x = 0
        while x < n:
            if fila[x]:
                ini = x
                while x < n and fila[x]:
                    x += 1
                trazos.append("M%d,%dh%dv1h-%dz" % (ini + borde, y + borde, x - ini, x - ini))
            else:
                x += 1
    lado = n + 2 * borde
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" shape-rendering="crispEdges" role="img" '
            'aria-label="Codigo QR de %s"><rect width="100%%" height="100%%" fill="#fff"/><path d="%s" fill="#000"/></svg>'
            % (lado, lado, html.escape(texto, quote=True), " ".join(trazos)))


# ======================================================================================================================
# Red y sistema
# ======================================================================================================================

def ips_de_la_red() -> list:
    """Las direcciones IPv4 de este equipo en redes reales (sin loopback ni APIPA), la de la ruta por defecto primero."""
    encontradas = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith(("127.", "169.254.")) and ip not in encontradas:
                encontradas.append(ip)
    except OSError:
        pass
    try:   # la que usa para salir a la red: casi siempre la buena (no envia nada)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            if ip not in encontradas and not ip.startswith("127."):
                encontradas.insert(0, ip)
            elif ip in encontradas:
                encontradas.remove(ip)
                encontradas.insert(0, ip)
    except OSError:
        pass
    return encontradas


def es_administrador() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _netsh(*argumentos) -> bool:
    try:
        r = subprocess.run(["netsh", "advfirewall", "firewall", *argumentos], capture_output=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0
    except Exception:
        return False


class Firewall:
    """Regla de entrada temporal para el puerto del servidor, solo para la red local. Se cierra al detenerse (incluso si se cierra la ventana)."""

    def __init__(self, puerto: int):
        self.puerto = puerto
        self.abierto = False
        self._candado = threading.Lock()

    def abrir(self) -> bool:
        if os.name != "nt":
            return False
        if not es_administrador():
            return False
        _netsh("delete", "rule", "name=" + REGLA_FIREWALL)     # por si quedo una de una vez anterior
        self.abierto = _netsh("add", "rule", "name=" + REGLA_FIREWALL, "dir=in", "action=allow", "protocol=TCP",
                              "localport=%d" % self.puerto, "profile=any", "remoteip=localsubnet")
        return self.abierto

    def cerrar(self):
        with self._candado:
            if self.abierto:
                _netsh("delete", "rule", "name=" + REGLA_FIREWALL)
                self.abierto = False


def vigilar_cierre_de_consola(limpiar):
    """Que cerrar la ventana (o apagar Windows) tambien cierre el puerto: Python no ejecuta `finally` en ese caso."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        tipo_funcion = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

        def manejador(evento):
            if evento in (2, 5, 6):          # cerrar la ventana, cerrar sesion, apagar
                limpiar()
            return False                     # Ctrl+C y los demas siguen su camino normal

        vigilar_cierre_de_consola.referencia = tipo_funcion(manejador)    # mantenerlo vivo
        ctypes.windll.kernel32.SetConsoleCtrlHandler(vigilar_cierre_de_consola.referencia, True)
    except Exception:
        pass


def hay_nodo_en_este_equipo(cache={"hora": 0.0, "valor": False}) -> bool:
    """AVACOM OPS Master (su API en el puerto 8000) esta en ESTE equipo? Se pregunta a /health/, con 8 s de memoria."""
    ahora = time.time()
    if ahora - cache["hora"] < 8:
        return cache["valor"]
    valor = False
    try:
        c = http.client.HTTPConnection("127.0.0.1", PUERTO_AULA, timeout=1.5)
        c.request("GET", "/health/")
        r = c.getresponse()
        valor = r.status == 200 and b"avacom-lms-backend" in r.read(8192)
        c.close()
    except Exception:
        valor = False
    cache["hora"], cache["valor"] = ahora, valor
    return valor


# ======================================================================================================================
# Lo que se sirve
# ======================================================================================================================

def elegir_apk(nombre):
    if nombre:
        ruta = pathlib.Path(nombre)
        ruta = ruta if ruta.is_absolute() else CARPETA / ruta
        if not ruta.is_file():
            sys.exit("No existe el APK: %s" % ruta)
        return ruta
    candidatos = sorted(CARPETA.glob("*.apk"), key=lambda p: [int(x) for x in re.findall(r"\d+", p.stem)] or [0])
    if not candidatos:
        sys.exit("No hay ningun .apk en %s\nGenera el APK con installer\\build\\Build-StudentApk.ps1 o copialo aqui." % CARPETA)
    return candidatos[-1]


class Servidor:
    """El APK elegido (con su huella, su firma y su version) y la cuenta de las tabletas que ya lo descargaron."""

    def __init__(self, apk: pathlib.Path, meta: int, aula):
        self.apk = apk
        self.tamano = apk.stat().st_size
        h = hashlib.sha256()
        with apk.open("rb") as f:
            for bloque in iter(lambda: f.read(1 << 20), b""):
                h.update(bloque)
        self.sha256 = h.hexdigest().upper()
        self.nombre_url = re.sub(r"\s+", "-", apk.name)     # «Student LMS 2.4.0.apk» -> «Student-LMS-2.4.0.apk»
        self.meta = meta
        self.aula_indicada = aula
        self.inicio = time.time()
        self.avisos = []
        leeme = apk.parent / "LEEME.txt"
        self.firma, self.version, self.sha_leeme = "", "", ""
        if leeme.is_file():
            texto = leeme.read_text(encoding="utf-8-sig", errors="replace")
            m = re.search(r"digest:\s*([0-9a-f]{64})", texto, re.I)
            self.firma = m.group(1).upper() if m else ""
            m = re.search(r"SHA-256\s*:\s*([0-9A-F]{64})", texto, re.I)
            self.sha_leeme = m.group(1).upper() if m else ""
            m = re.match(r"\s*Student LMS\s+(\d+(?:\.\d+)*)", texto)
            self.version = m.group(1) if m else ""
        if not self.version:
            m = re.search(r"(\d+(?:\.\d+)+)", apk.stem)
            self.version = m.group(1) if m else ""
        # Un APK a medio copiar (USB, correo) se descubre aqui y no en la quinta tableta.
        try:
            with zipfile.ZipFile(apk) as z:
                if "AndroidManifest.xml" not in z.namelist():
                    self.avisos.append("El archivo no parece un APK (no trae AndroidManifest.xml).")
                elif z.testzip() is not None:
                    self.avisos.append("El APK esta danado (falla la comprobacion de su contenido): vuelve a copiarlo.")
        except zipfile.BadZipFile:
            self.avisos.append("El archivo no es un APK valido (esta cortado o danado): vuelve a copiarlo.")
        if self.sha_leeme and self.sha_leeme != self.sha256:
            self.avisos.append("La huella del APK no coincide con la de LEEME.txt: el APK no es el que se compilo (copia danada o cambiada).")
        # Cuenta de descargas. Una tableta CUENTA cuando ya recibio el archivo entero, lo junten las peticiones que lo junten: Chrome
        # reanuda con Range si se corta el Wi-Fi y baja los archivos grandes en varios trozos a la vez, asi que "una peticion que llega
        # al ultimo byte" no significa "tableta lista". Por eso se lleva, por direccion, que bytes ya recibio.
        self._candado = threading.Lock()
        self.completas = {}          # ip -> {"hora": ..., "bytes": ..., "seg": ...}
        self.cobertura = {}          # ip -> tramos [desde, hasta] ya entregados, fusionados
        self.primer_contacto = {}    # ip -> hora de su primera peticion del APK
        self.en_curso = 0
        self.cortadas = 0
        self.recientes = []

    def empieza(self, ip: str):
        with self._candado:
            self.en_curso += 1
            self.primer_contacto.setdefault(ip, time.time())

    def termina(self, ip: str, desde: int, enviado: int, confirmada: bool):
        """Anota lo que se escribio en una peticion. Devuelve (numero, segundos) si con ella ESTA tableta acaba de completar el archivo.

        Los bytes se cuentan tal como se escribieron: una reanudacion (Range) empieza justo donde la tableta se quedo, que nunca pasa de lo
        que se le escribio, asi que los tramos se empalman sin huecos. Pero el archivo solo se da por completo si la peticion que lo
        completa termino bien (la tableta cerro la conexion por las buenas): si se corto justo al final, se espera a la siguiente."""
        with self._candado:
            self.en_curso = max(0, self.en_curso - 1)
            if not confirmada:
                self.cortadas += 1
            if enviado <= 0:
                return None
            tramos = self.cobertura.setdefault(ip, [])
            tramos.append([desde, desde + enviado - 1])
            tramos.sort()
            fusion = [tramos[0]]
            for t in tramos[1:]:
                if t[0] <= fusion[-1][1] + 1:
                    fusion[-1][1] = max(fusion[-1][1], t[1])
                else:
                    fusion.append(t)
            self.cobertura[ip] = fusion
            entero = len(fusion) == 1 and fusion[0][0] == 0 and fusion[0][1] >= self.tamano - 1
            if not entero or not confirmada or ip in self.completas:
                return None
            segundos = time.time() - self.primer_contacto.get(ip, time.time())
            hora = time.strftime("%H:%M:%S")
            self.completas[ip] = {"hora": hora, "bytes": self.tamano, "seg": round(segundos, 1)}
            self.recientes.insert(0, {"ip": ip, "hora": hora, "seg": round(segundos, 1)})
            del self.recientes[12:]
            return len(self.completas), segundos

    def estado(self) -> dict:
        with self._candado:
            return {"completas": len(self.completas), "meta": self.meta, "en_curso": self.en_curso, "cortadas": self.cortadas,
                    "recientes": list(self.recientes), "segundos": int(time.time() - self.inicio)}


_CANDADO_CSV = threading.Lock()


def anotar_csv(ip: str, enviado: int, segundos: float):
    """Una linea por descarga completa, para cuadrar al final cuantas tabletas quedaron. Si la carpeta no se puede escribir, se omite.
    Se serializa: con varias tabletas terminando a la vez, dos aperturas simultaneas del archivo dan error de uso compartido en Windows
    y se perderia una linea."""
    with _CANDADO_CSV:
        for intento in range(3):
            try:
                ruta = CARPETA / CSV_DESCARGAS
                nuevo = not ruta.exists()
                with ruta.open("a", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    if nuevo:
                        w.writerow(["fecha_hora", "ip", "bytes", "segundos"])
                    w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), ip, enviado, round(segundos, 1)])
                return
            except OSError:
                time.sleep(0.2)     # otro programa (el Excel del tecnico) lo tiene abierto un instante: se reintenta


ESTILO = """
:root{--tinta:#18181b;--suave:#52525b;--fondo:#f4f4f5;--tarjeta:#fff;--marca:#e5262b;--ok:#15803d;--linea:#e4e4e7}
@media (prefers-color-scheme:dark){:root{--tinta:#f4f4f5;--suave:#a1a1aa;--fondo:#18181b;--tarjeta:#27272a;--linea:#3f3f46;--ok:#4ade80}}
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;margin:0;background:var(--fondo);color:var(--tinta);line-height:1.5}
main{max-width:46rem;margin:0 auto;padding:1.2rem 1rem 2rem}h1{font-size:1.45rem;margin:.2rem 0 .3rem}h2{font-size:1.05rem;margin:1.4rem 0 .4rem}
.tarjeta{background:var(--tarjeta);border:1px solid var(--linea);border-radius:.9rem;padding:1rem 1.1rem;margin:.9rem 0}
a.boton,button.boton{display:block;width:100%;background:var(--marca);color:#fff;text-align:center;font:inherit;font-size:1.3rem;font-weight:700;
text-decoration:none;padding:1.15rem;border:0;border-radius:.9rem;margin:1.1rem 0;cursor:pointer}button.suave{background:transparent;color:var(--suave);border:1px solid var(--linea);font-size:1rem;padding:.8rem}
code{word-break:break-all;font-size:.82rem}.k{font-size:.85rem;color:var(--suave)}ol{padding-left:1.25rem}li{margin:.35rem 0}
.aula{font-size:1.5rem;font-weight:800;word-break:break-all;margin:.2rem 0}.ok{color:var(--ok);font-weight:700}.aviso{border-left:.4rem solid var(--marca);padding-left:.8rem;margin:.6rem 0}
"""


PAGINA_TABLETA = string.Template("""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AVACOM Student · descarga</title><style>$estilo</style></head><body><main>
<h1>AVACOM Student para Android</h1>
<p class="k">$apk · versión $version · $mb MB</p>
$avisos
<a class="boton" href="/download/$url_apk">Descargar e instalar</a>
<div class="tarjeta"><ol>
<li>Toca <b>Descargar e instalar</b>. Si Chrome avisa que el archivo puede dañar el dispositivo, toca <b>Descargar de todos modos</b> (o <b>Mantener</b>).</li>
<li>Abre el archivo descargado (en la notificación, o en la carpeta Descargas).</li>
<li>La primera vez Android pide <b>permitir instalar apps de esta fuente</b>: actívalo para Chrome y vuelve atrás.</li>
<li>Toca <b>Instalar</b>. Si Play Protect pregunta, toca <b>Instalar de todos modos</b>.</li>
<li>Abre <b>Student LMS</b> y escribe la dirección del aula:</li></ol>
$aula</div>
<p class="k">Huella SHA-256 del APK<br><code>$sha</code></p>$firma
<p class="k">Enlace directo: <code>$enlace</code></p>
</main></body></html>""")


PAGINA_PANEL = string.Template("""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AVACOM Student · servidor de instalación</title><style>$estilo
.cuadro{display:grid;grid-template-columns:minmax(0,26rem) 1fr;gap:1.4rem;align-items:start}@media (max-width:760px){.cuadro{grid-template-columns:1fr}}
.qr{background:#fff;border-radius:.9rem;padding:.4rem;border:1px solid var(--linea)}.qr svg{display:block;width:100%;height:auto}
.cuenta{font-size:3rem;font-weight:800;line-height:1.1}.barra{height:1rem;background:var(--linea);border-radius:.5rem;overflow:hidden;margin:.6rem 0}
.barra i{display:block;height:100%;background:var(--ok);width:0;transition:width .4s}table{width:100%;border-collapse:collapse;font-size:.92rem}td{padding:.25rem .3rem;border-bottom:1px solid var(--linea)}
.url{font-size:1.25rem;font-weight:700;word-break:break-all}.otros .qr{max-width:11rem;display:inline-block;margin:.3rem .5rem .3rem 0}
</style></head><body><main style="max-width:62rem">
<h1>Instalar AVACOM Student en las tabletas</h1>
<p class="k">$apk · versión $version · $mb MB · puerto $puerto</p>
$avisos
<div class="cuadro">
 <div><div class="qr">$qr</div><p class="k" style="margin:.5rem 0 0">En cada tableta: abre la cámara, apunta al código y toca el aviso. Después sigue los pasos de la página.</p></div>
 <div>
  <div class="tarjeta"><div class="k">Descargas completas</div><div class="cuenta"><span id="n">0</span><span class="k" style="font-size:1.4rem"> de $meta</span></div>
   <div class="barra"><i id="b"></i></div><div class="k" id="d"></div></div>
  <div class="tarjeta"><div class="k">O escribe esta dirección en el navegador de la tableta</div><div class="url">$url</div>$otras</div>
  $aula
  <div class="tarjeta"><div class="k">Últimas descargas</div><table id="t"><tr><td class="k">Todavía ninguna</td></tr></table></div>
  <button class="boton suave" id="parar" type="button">Detener el servidor</button>
 </div></div>
$otros
<script>
var meta=$meta_js;
function pinta(e){document.getElementById('n').textContent=e.completas;
 document.getElementById('b').style.width=(meta?Math.min(100,100*e.completas/meta):0)+'%';
 document.getElementById('d').textContent=(e.en_curso?e.en_curso+' descargando ahora · ':'')+(e.cortadas?e.cortadas+' cortada(s) · ':'')+'encendido hace '+Math.floor(e.segundos/60)+' min';
 var f=e.recientes.map(function(r){return '<tr><td>'+r.hora+'</td><td>'+r.ip+'</td><td class="k">'+r.seg+' s</td></tr>'});
 if(f.length)document.getElementById('t').innerHTML=f.join('')}
function lee(){fetch('/estado.json',{cache:'no-store'}).then(function(r){return r.json()}).then(pinta).catch(function(){})}
lee();setInterval(lee,2000);
document.getElementById('parar').onclick=function(){if(confirm('¿Detener el servidor? Las tabletas que ya descargaron el APK no se afectan.')){
 fetch('/detener',{method:'POST'}).then(function(){document.body.innerHTML='<main><h1>Servidor detenido</h1><p>Ya puedes cerrar esta ventana.</p></main>'})}};
</script></main></body></html>""")


def direccion_del_aula(srv: Servidor, host: str):
    """Texto de la dirección del aula para la tableta (o None si no se puede saber): la indicada, o la de este equipo si OPS corre aquí."""
    if srv.aula_indicada:
        return srv.aula_indicada
    if hay_nodo_en_este_equipo() and host:
        return "http://%s:%d" % (host, PUERTO_AULA)
    return None


def manejador(srv: Servidor, puerto: int, parar):
    propias = set(ips_de_la_red()) | {"127.0.0.1", "::1"}

    class Manejador(http.server.BaseHTTPRequestHandler):
        server_version = "AVACOM-APK"
        protocol_version = "HTTP/1.1"
        timeout = 90          # una tableta que se calla no se queda con un hilo para siempre

        def log_message(self, formato, *args):    # una linea por peticion, con la hora (sin ruido de /estado.json)
            if self.path.startswith("/estado.json"):
                return
            sys.stdout.write("%s  %-15s  %s\n" % (time.strftime("%H:%M:%S"), self.client_address[0], formato % args))
            sys.stdout.flush()

        def _enviar(self, codigo: int, cuerpo: str, tipo: str = "text/html; charset=utf-8"):
            datos = cuerpo.encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(datos)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(datos)

        def _redirigir(self, destino: str):
            self.send_response(302)
            self.send_header("Location", destino)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _local(self) -> bool:
            return self.client_address[0] in propias

        def _host(self) -> str:
            return (self.headers.get("Host") or "").split(":")[0]

        def do_HEAD(self):
            self.do_GET()

        def do_POST(self):
            if self.path.split("?", 1)[0] == "/detener" and self._local():
                self._enviar(200, "ok", "text/plain; charset=utf-8")
                threading.Thread(target=parar, daemon=True).start()
            else:
                self._enviar(404, "No encontrado.", "text/plain; charset=utf-8")

        def do_GET(self):
            ruta = self.path.split("?", 1)[0]
            if ruta == "/":
                self._redirigir("/panel/" if self._local() else "/download/")
            elif ruta == "/download":
                self._redirigir("/download/")
            elif ruta == "/download/":
                self._enviar(200, self._pagina_tableta())
            elif ruta == "/panel/":
                self._enviar(200, self._pagina_panel())
            elif ruta == "/estado.json":
                self._enviar(200, json.dumps(srv.estado()), "application/json; charset=utf-8")
            elif ruta == "/download/SHA256.txt":
                self._enviar(200, "%s\nSHA256  %s\n" % (srv.apk.name, srv.sha256), "text/plain; charset=utf-8")
            elif ruta in ("/download/" + srv.nombre_url, "/download/" + srv.apk.name):
                self._apk()
            else:
                self._enviar(404, "No encontrado. La descarga esta en /download/", "text/plain; charset=utf-8")

        # ------------------------------------------------------------------------------------------ paginas
        def _avisos_html(self) -> str:
            return "".join("<p class='aviso'>%s</p>" % html.escape(a) for a in srv.avisos)

        def _pagina_tableta(self) -> str:
            host = self._host() or (ips_de_la_red() or ["localhost"])[0]
            aula = direccion_del_aula(srv, host)
            if aula:
                aula_html = ("<div class='aula'>%s</div><p class='k'>Es la dirección de AVACOM OPS Master en la misma red que esta tableta.</p>"
                             % html.escape(aula))
            else:
                aula_html = ("<p class='k'>La que muestra AVACOM OPS Master al terminar su instalación "
                             "(algo como <b>http://192.168.0.55:8000</b>).</p>")
            enlace = "http://%s/download/%s" % (self.headers.get("Host") or ("%s:%d" % (host, puerto)), srv.nombre_url)
            firma = ("<p class='k'>Firma del APK (SHA-256 del certificado)<br><code>%s</code></p>" % srv.firma) if srv.firma else ""
            return PAGINA_TABLETA.substitute(
                estilo=ESTILO, apk=html.escape(srv.apk.name), version=html.escape(srv.version or "?"), mb="%.1f" % (srv.tamano / 1048576),
                avisos=self._avisos_html(), url_apk=html.escape(srv.nombre_url), aula=aula_html, sha=srv.sha256, firma=firma,
                enlace=html.escape(enlace))

        def _pagina_panel(self) -> str:
            ips = ips_de_la_red() or ["localhost"]
            direcciones = ["http://%s:%d/download/" % (ip, puerto) for ip in ips]
            principal = direcciones[0]
            qr = qr_svg(principal) or "<p class='k' style='padding:1rem'>La dirección es demasiado larga para un código QR.</p>"
            otras, otros = "", ""
            if len(direcciones) > 1:
                otras = "<p class='k' style='margin:.6rem 0 0'>Si la tableta no abre esa, prueba con: %s</p>" % " · ".join(
                    "<code>%s</code>" % html.escape(d) for d in direcciones[1:])
                otros = ("<div class='tarjeta otros'><div class='k'>Este equipo está en más de una red: un código por cada dirección</div>%s</div>"
                         % "".join("<div class='qr'>%s</div>" % qr_svg(d) for d in direcciones[1:] if qr_svg(d)))
            aula = direccion_del_aula(srv, ips[0])
            if aula:
                aula_html = ("<div class='tarjeta'><div class='k'>AVACOM OPS Master está en este equipo. En cada tableta, al abrir Student LMS, "
                             "se escribe:</div><div class='aula'>%s</div></div>" % html.escape(aula))
            else:
                aula_html = ("<div class='tarjeta'><div class='k'>La dirección del aula (la de AVACOM OPS Master, algo como "
                             "http://192.168.0.55:8000) se escribe en cada tableta al abrir Student LMS.</div></div>")
            return PAGINA_PANEL.substitute(
                estilo=ESTILO, apk=html.escape(srv.apk.name), version=html.escape(srv.version or "?"), mb="%.1f" % (srv.tamano / 1048576),
                puerto=puerto, avisos=self._avisos_html(), qr=qr, meta=(srv.meta or "∞"), meta_js=srv.meta or 0,
                url=html.escape(principal), otras=otras, otros=otros, aula=aula_html)

        # ------------------------------------------------------------------------------------------ el APK
        def _esperar_cierre_de_la_tableta(self) -> bool:
            """Cierra el lado de envio y espera a que la tableta cierre el suyo. Cierre limpio (o silencio sin cortes) = lo recibio todo."""
            limite = time.time() + 15
            try:
                self.connection.shutdown(socket.SHUT_WR)
                while time.time() < limite:
                    self.connection.settimeout(max(0.5, limite - time.time()))
                    if not self.connection.recv(4096):
                        return True
                return True        # no cerro, pero tampoco se corto: se da por entregado
            except socket.timeout:
                return True
            except OSError:
                return False       # la conexion se reinicio o se aborto: no se sabe cuanto llego

        def _apk(self):
            inicio, fin, parcial = 0, srv.tamano - 1, False
            rango = self.headers.get("Range")
            if rango and (m := re.match(r"bytes=(\d*)-(\d*)$", rango.strip())):
                a, b = m.groups()
                if a == "" and b:
                    inicio = max(0, srv.tamano - int(b))
                else:
                    inicio = int(a or 0)
                    fin = min(int(b), srv.tamano - 1) if b else srv.tamano - 1
                parcial = True
                if inicio > fin or inicio >= srv.tamano:
                    self.send_response(416)
                    self.send_header("Content-Range", "bytes */%d" % srv.tamano)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
            largo = fin - inicio + 1
            self.send_response(206 if parcial else 200)
            self.send_header("Content-Type", TIPO_APK)
            self.send_header("Content-Length", str(largo))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % srv.nombre_url)
            self.send_header("Cache-Control", "no-cache")
            if parcial:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (inicio, fin, srv.tamano))
            if self.command != "HEAD":
                # Una conexion por descarga: al terminar se cierra y el cierre limpio de la tableta es la prueba de que recibio todo.
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            if self.command == "HEAD":
                return
            ip, enviado, confirmada = self.client_address[0], 0, False
            srv.empieza(ip)
            try:
                with srv.apk.open("rb") as f:
                    f.seek(inicio)
                    restante = largo
                    while restante > 0:
                        bloque = f.read(min(1 << 16, restante))
                        if not bloque:
                            break
                        self.wfile.write(bloque)
                        restante -= len(bloque)
                        enviado += len(bloque)
                if restante == 0:
                    self.wfile.flush()
                    confirmada = self._esperar_cierre_de_la_tableta()
            except (ConnectionError, TimeoutError, OSError):
                pass     # la tableta cancelo o perdio la red (reanudara con Range): no es un error del servidor
            finally:
                completo = srv.termina(ip, inicio, enviado, confirmada)
                if completo:
                    numero, segundos = completo
                    anotar_csv(ip, srv.tamano, segundos)
                    meta = (" de %d" % srv.meta) if srv.meta else ""
                    sys.stdout.write("%s  %-15s  *** TABLETA %d%s: ya tiene el APK completo (%.1f MB en %.0f s)\n"
                                     % (time.strftime("%H:%M:%S"), ip, numero, meta, srv.tamano / 1048576, segundos))
                    sys.stdout.flush()

    return Manejador


class ServidorHttp(http.server.ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 256      # 55 tabletas tocando el codigo casi a la vez: la cola de 5 por defecto las rechazaria
    # En Windows SO_REUSEADDR deja que DOS servidores escuchen en el mismo puerto sin avisar (y se reparten las tabletas).
    # Sin ella, un puerto ocupado da un error claro.
    allow_reuse_address = False


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Sirve el APK de AVACOM Student por la red local.")
    ap.add_argument("--puerto", type=int, default=8080)
    ap.add_argument("--apk", default=None, help="Nombre o ruta del APK (por defecto, el mas nuevo de esta carpeta).")
    ap.add_argument("--escucha", default="0.0.0.0", help="Direccion de escucha (por defecto, todas las interfaces).")
    ap.add_argument("--tabletas", type=int, default=0, help="Cuantas tabletas se van a instalar (para el contador del panel).")
    ap.add_argument("--aula", default=None, help="Direccion del aula para mostrarla en la pagina de la tableta (por defecto, la de este equipo si OPS corre aqui).")
    ap.add_argument("--abrir", action="store_true", help="Abre el panel en el navegador de este equipo.")
    args = ap.parse_args()

    srv = Servidor(elegir_apk(args.apk), max(0, args.tabletas), args.aula.rstrip("/") if args.aula else None)
    firewall = Firewall(args.puerto)
    httpd_ref = []

    def parar():
        if httpd_ref:
            httpd_ref[0].shutdown()

    try:
        httpd = ServidorHttp((args.escucha, args.puerto), manejador(srv, args.puerto, parar))
    except OSError as error:
        sys.exit("No se pudo escuchar en %s:%d: %s\nSi el puerto esta ocupado, usa otro: Servir-APK.bat 8081" % (args.escucha, args.puerto, error))
    httpd_ref.append(httpd)
    vigilar_cierre_de_consola(firewall.cerrar)

    print("AVACOM Student · %s · %.1f MB · version %s" % (srv.apk.name, srv.tamano / 1048576, srv.version or "?"))
    print("SHA-256: %s" % srv.sha256)
    for aviso in srv.avisos:
        print("AVISO: %s" % aviso)
    if os.name == "nt":
        if firewall.abrir():
            print("Firewall: puerto %d abierto SOLO para la red local mientras este servidor este encendido." % args.puerto)
        elif es_administrador():
            print("AVISO: no se pudo abrir el puerto %d en el Firewall de Windows. Si las tabletas no llegan, abre ese puerto a mano." % args.puerto)
        else:
            print("AVISO: sin permiso de administrador no se abrio el puerto %d en el Firewall. Si las tabletas no llegan, "
                  "cierra esta ventana y vuelve a tocar Servir-APK.bat aceptando el permiso." % args.puerto)
    ips = ips_de_la_red()
    print("\nDescarga desde las tabletas (misma red Wi-Fi):")
    for ip in ips or ["(no se encontro la IP de este equipo)"]:
        print("    http://%s:%d/download/" % (ip, args.puerto))
    print("\nPanel con el codigo QR, en ESTE equipo:  http://localhost:%d/" % args.puerto)
    if args.tabletas:
        print("Meta: %d tabletas. El contador sube cuando cada una termina de descargar.\n" % args.tabletas)
    print("Para detener: boton 'Detener el servidor' del panel, o Ctrl+C.\n")

    if args.abrir:
        panel = "http://localhost:%d/" % args.puerto
        try:   # explorer.exe lo abre con el usuario normal aunque este servidor corra con permisos de administrador
            if os.name == "nt":
                subprocess.Popen(["explorer.exe", panel])
            else:
                import webbrowser
                webbrowser.open(panel)
        except Exception:
            pass

    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        firewall.cerrar()
        httpd.server_close()
        estado = srv.estado()
        meta = (" de %d" % srv.meta) if srv.meta else ""
        print("\nDetenido. Tabletas que descargaron el APK completo: %d%s. (%d descarga(s) cortada(s).)" % (estado["completas"], meta, estado["cortadas"]))
        if estado["completas"]:
            print("Quedo el detalle en %s" % (CARPETA / CSV_DESCARGAS))


if __name__ == "__main__":
    main()

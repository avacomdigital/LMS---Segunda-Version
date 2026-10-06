"""
Sirve el APK de AVACOM Student por la red local, para instalarlo en las tabletas sin cable.

    python Servir-APK.py                 # puerto 8080, el APK mas nuevo de esta carpeta
    python Servir-APK.py --puerto 8000   # otro puerto (el 8000 es el de la API de OPS: solo si esta libre)
    python Servir-APK.py --apk "Student LMS 2.3.0.apk"

Solo biblioteca estandar de Python: no instala nada. Atiende unicamente /download/ :

    /download/              pagina con el boton de descarga, la version y la huella SHA-256
    /download/<archivo>.apk el APK (con Range, para que Chrome pueda reanudar)
    /download/SHA256.txt    la huella del APK, para verificarlo

No toca el backend ni sirve nada mas que el APK de esta carpeta. Pensado para una red cerrada del aula
(HTTP, sin sesion): cierralo (Ctrl+C) cuando acabes de instalar las tabletas.
"""
import argparse
import hashlib
import html
import http.server
import pathlib
import re
import socket
import sys
import threading
import time

CARPETA = pathlib.Path(__file__).resolve().parent
TIPO_APK = "application/vnd.android.package-archive"


def ips_de_la_red() -> list[str]:
    """Las direcciones IPv4 de este equipo en redes reales (sin loopback ni las virtuales de Hyper-V/WSL)."""
    encontradas: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith(("127.", "169.254.")) and ip not in encontradas:
                encontradas.append(ip)
    except OSError:
        pass
    # La que usa para salir a la red: casi siempre la buena (no envia nada).
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            if ip not in encontradas and not ip.startswith("127."):
                encontradas.insert(0, ip)
    except OSError:
        pass
    return encontradas


def elegir_apk(nombre: str | None) -> pathlib.Path:
    if nombre:
        ruta = pathlib.Path(nombre)
        ruta = ruta if ruta.is_absolute() else CARPETA / ruta
        if not ruta.is_file():
            sys.exit(f"No existe el APK: {ruta}")
        return ruta
    candidatos = sorted(CARPETA.glob("*.apk"), key=lambda p: [int(x) for x in re.findall(r"\d+", p.stem)] or [0])
    if not candidatos:
        sys.exit(f"No hay ningun .apk en {CARPETA}")
    return candidatos[-1]


class Servidor:
    def __init__(self, apk: pathlib.Path):
        self.apk = apk
        self.tamano = apk.stat().st_size
        h = hashlib.sha256()
        with apk.open("rb") as f:
            for bloque in iter(lambda: f.read(1 << 20), b""):
                h.update(bloque)
        self.sha256 = h.hexdigest().upper()
        # El nombre en la URL no lleva espacios: «Student LMS 2.3.0.apk» -> «Student-LMS-2.3.0.apk».
        self.nombre_url = re.sub(r"\s+", "-", apk.name)
        leeme = apk.parent / "LEEME.txt"
        self.firma = ""
        if leeme.is_file():
            m = re.search(r"digest:\s*([0-9a-f]{64})", leeme.read_text(encoding="utf-8-sig", errors="replace"), re.I)
            self.firma = m.group(1).upper() if m else ""
        self.descargas = 0


def manejador(srv: Servidor, puerto: int):
    class Manejador(http.server.BaseHTTPRequestHandler):
        server_version = "AVACOM-APK"
        protocol_version = "HTTP/1.1"

        def log_message(self, formato, *args):  # una linea por peticion, con la hora
            sys.stdout.write(f"{time.strftime('%H:%M:%S')}  {self.client_address[0]:<15}  {formato % args}\n")
            sys.stdout.flush()

        def _texto(self, codigo: int, cuerpo: str, tipo: str = "text/html; charset=utf-8"):
            datos = cuerpo.encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(datos)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(datos)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            ruta = self.path.split("?", 1)[0]
            if ruta in ("/", "/download"):
                self.send_response(302)
                self.send_header("Location", "/download/")
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif ruta == "/download/":
                self._texto(200, self._pagina())
            elif ruta == "/download/SHA256.txt":
                self._texto(200, f"{srv.apk.name}\nSHA256  {srv.sha256}\n", "text/plain; charset=utf-8")
            elif ruta in (f"/download/{srv.nombre_url}", f"/download/{srv.apk.name}"):
                self._apk()
            else:
                self._texto(404, "No encontrado. La descarga esta en /download/", "text/plain; charset=utf-8")

        def _pagina(self) -> str:
            url = f"http://{self.headers.get('Host') or ('%s:%d' % (ips_de_la_red()[0], puerto))}/download/{srv.nombre_url}"
            firma = f"<p class='k'>Firma del APK (SHA-256 del certificado)<br><code>{srv.firma}</code></p>" if srv.firma else ""
            return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AVACOM Student - descarga</title>
<style>body{{font-family:system-ui,sans-serif;margin:0;background:#f4f4f5;color:#18181b}}main{{max-width:34rem;margin:0 auto;padding:1.5rem 1rem}}
h1{{font-size:1.4rem;margin:.2rem 0}}a.b{{display:block;background:#e5262b;color:#fff;text-align:center;font-size:1.25rem;font-weight:700;
text-decoration:none;padding:1.1rem;border-radius:.8rem;margin:1.2rem 0}}code{{word-break:break-all;font-size:.8rem}}.k{{font-size:.85rem;color:#52525b}}
ol{{padding-left:1.2rem;line-height:1.5}}</style></head><body><main>
<h1>AVACOM Student para Android</h1>
<p>{html.escape(srv.apk.name)} · {srv.tamano / 1048576:.1f} MB</p>
<a class="b" href="/download/{html.escape(srv.nombre_url)}">Descargar e instalar</a>
<ol><li>Toca <b>Descargar e instalar</b> (si Chrome avisa que el archivo puede danar el dispositivo, toca <b>Descargar de todos modos</b>).</li>
<li>Abre el archivo descargado. La primera vez Android pide <b>permitir instalar apps de esta fuente</b>: actívalo para el navegador y vuelve.</li>
<li>Toca <b>Instalar</b>. Si Play Protect pregunta, toca <b>Instalar de todos modos</b>.</li>
<li>Abre AVACOM Student y escribe la dirección del aula que muestra AVACOM OPS Master.</li></ol>
<p class="k">Huella SHA-256 del APK<br><code>{srv.sha256}</code></p>{firma}
<p class="k">Enlace directo: <code>{html.escape(url)}</code></p></main></body></html>"""

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
                    self.send_header("Content-Range", f"bytes */{srv.tamano}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
            largo = fin - inicio + 1
            self.send_response(206 if parcial else 200)
            self.send_header("Content-Type", TIPO_APK)
            self.send_header("Content-Length", str(largo))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Disposition", f'attachment; filename="{srv.nombre_url}"')
            if parcial:
                self.send_header("Content-Range", f"bytes {inicio}-{fin}/{srv.tamano}")
            self.end_headers()
            if self.command == "HEAD":
                return
            if inicio == 0:
                srv.descargas += 1
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
            except (ConnectionError, TimeoutError):
                pass  # la tableta cancelo o perdio la red: no es un error del servidor

    return Manejador


def main() -> None:
    ap = argparse.ArgumentParser(description="Sirve el APK de AVACOM Student por la red local.")
    ap.add_argument("--puerto", type=int, default=8080)
    ap.add_argument("--apk", default=None, help="Nombre o ruta del APK (por defecto, el mas nuevo de esta carpeta).")
    ap.add_argument("--escucha", default="0.0.0.0", help="Direccion de escucha (por defecto, todas las interfaces).")
    args = ap.parse_args()

    srv = Servidor(elegir_apk(args.apk))
    try:
        httpd = http.server.ThreadingHTTPServer((args.escucha, args.puerto), manejador(srv, args.puerto))
    except OSError as error:
        sys.exit(f"No se pudo escuchar en {args.escucha}:{args.puerto}: {error}\n"
                 f"Si el puerto esta ocupado, usa otro: python Servir-APK.py --puerto 8081")
    httpd.daemon_threads = True

    print(f"AVACOM Student · {srv.apk.name} · {srv.tamano / 1048576:.1f} MB")
    print(f"SHA-256: {srv.sha256}")
    print("Descarga desde las tabletas (misma red):")
    for ip in ips_de_la_red():
        print(f"    http://{ip}:{args.puerto}/download/")
    print("Ctrl+C para detener.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\nDetenido. Descargas completas del APK: {srv.descargas}.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
